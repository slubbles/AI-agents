"""
Source Quality Tracker — learn which domains produce high-scoring content.

After each research cycle, the system records which source URLs contributed
to accepted vs rejected outputs. Over time, this builds a per-domain quality
profile: "stackoverflow.com produces high-accuracy content for crypto domain"
while "medium.com produces low-specificity content."

This data feeds into:
1. Researcher prompt: "prefer these sources" / "avoid these sources"
2. Meta-analyst: source patterns correlated with score improvements
3. Fetch prioritization: high-quality sources fetched first
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from utils.atomic_write import atomic_json_write

SOURCE_DIR = os.path.join(os.path.dirname(__file__), "memory", "_source_quality")
MAX_SOURCES_PER_DOMAIN = 100  # Keep the top 100 source domains per research domain


def _source_path(domain: str) -> str:
    return os.path.join(SOURCE_DIR, f"{domain}.json")


def _load_sources(domain: str) -> dict:
    path = _source_path(domain)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_sources(domain: str, sources: dict) -> None:
    os.makedirs(SOURCE_DIR, exist_ok=True)
    # Prune to top sources by sample count
    if len(sources) > MAX_SOURCES_PER_DOMAIN:
        sorted_sources = sorted(sources.items(), key=lambda x: x[1].get("count", 0), reverse=True)
        sources = dict(sorted_sources[:MAX_SOURCES_PER_DOMAIN])
    atomic_json_write(_source_path(domain), sources)


def _extract_domain(url: str) -> str | None:
    """Extract the base domain from a URL."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "")
        return host if host else None
    except Exception:
        return None


def record_source_quality(domain: str, sources_used: list[str], score: float,
                          verdict: str, tool_log: list[dict] | None = None) -> None:
    """
    Record source quality from a research output.

    Args:
        domain: Research domain
        sources_used: URLs cited in the research output
        score: Overall critic score
        verdict: 'accept' or 'reject'
        tool_log: Optional tool log from researcher (has fetch success/fail data)
    """
    sources = _load_sources(domain)
    now = datetime.now(timezone.utc).isoformat()

    # Track URLs that were successfully fetched (from tool_log)
    fetched_urls = {}
    if tool_log:
        for entry in tool_log:
            if entry.get("tool") in ("fetch_page", "browser_fetch", "search_and_fetch"):
                url = entry.get("url", "")
                if url:
                    fetched_urls[url] = {
                        "success": entry.get("success", False),
                        "chars": entry.get("chars", 0),
                    }

    # Update per-source-domain quality data
    seen_domains = set()
    for url in sources_used:
        source_domain = _extract_domain(url)
        if not source_domain or source_domain in seen_domains:
            continue
        seen_domains.add(source_domain)

        if source_domain not in sources:
            sources[source_domain] = {
                "count": 0,
                "total_score": 0.0,
                "accepted": 0,
                "rejected": 0,
                "fetch_successes": 0,
                "fetch_failures": 0,
                "first_seen": now,
            }

        entry = sources[source_domain]
        entry["count"] += 1
        entry["total_score"] += score
        if verdict == "accept":
            entry["accepted"] += 1
        else:
            entry["rejected"] += 1
        entry["last_seen"] = now

        # Check fetch outcome for this URL
        for fetched_url, fetch_data in fetched_urls.items():
            if source_domain in fetched_url:
                if fetch_data["success"]:
                    entry["fetch_successes"] = entry.get("fetch_successes", 0) + 1
                else:
                    entry["fetch_failures"] = entry.get("fetch_failures", 0) + 1

    _save_sources(domain, sources)


def get_source_rankings(domain: str, min_count: int = 2) -> dict:
    """
    Get ranked source quality for a domain.

    Returns:
        {"high_quality": [...], "low_quality": [...], "unreliable_fetch": [...]}
    """
    sources = _load_sources(domain)
    high = []
    low = []
    unreliable = []

    for source_domain, data in sources.items():
        count = data.get("count", 0)
        if count < min_count:
            continue

        avg_score = data.get("total_score", 0) / count
        accept_rate = data.get("accepted", 0) / count
        fetch_total = data.get("fetch_successes", 0) + data.get("fetch_failures", 0)
        fetch_rate = data.get("fetch_successes", 0) / fetch_total if fetch_total > 0 else 1.0

        info = {
            "domain": source_domain,
            "avg_score": round(avg_score, 1),
            "accept_rate": round(accept_rate, 2),
            "count": count,
            "fetch_success_rate": round(fetch_rate, 2),
        }

        if fetch_rate < 0.3 and fetch_total >= 2:
            unreliable.append(info)
        elif avg_score >= 7.0 and accept_rate >= 0.7:
            high.append(info)
        elif avg_score < 5.0 or accept_rate < 0.3:
            low.append(info)

    high.sort(key=lambda x: x["avg_score"], reverse=True)
    low.sort(key=lambda x: x["avg_score"])

    return {"high_quality": high[:10], "low_quality": low[:10], "unreliable_fetch": unreliable[:5]}


def format_source_hints_for_prompt(domain: str) -> str:
    """Format source quality data for injection into researcher prompt."""
    rankings = get_source_rankings(domain)

    if not any(rankings.values()):
        return ""

    parts = []
    if rankings["high_quality"]:
        good = ", ".join(s["domain"] for s in rankings["high_quality"][:5])
        parts.append(f"HIGH-QUALITY sources (produced good scores): {good}")
    if rankings["low_quality"]:
        bad = ", ".join(s["domain"] for s in rankings["low_quality"][:5])
        parts.append(f"LOW-QUALITY sources (produced low scores — use sparingly): {bad}")
    if rankings["unreliable_fetch"]:
        broken = ", ".join(s["domain"] for s in rankings["unreliable_fetch"][:3])
        parts.append(f"HARD TO FETCH (often blocked — use browser_fetch): {broken}")

    return "\n".join(parts)
