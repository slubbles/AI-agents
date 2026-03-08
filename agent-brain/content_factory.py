"""Discord content factory for Cortex.

Runs a daily pipeline that:
1. Collects current Cortex context and recent channel history
2. Writes a research brief, social drafts, and a thumbnail brief
3. Posts those outputs into Discord agent channels
4. Optionally publishes to X via Buffer and Threads via the direct API
"""

import json
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import (
    CHAT_MODEL,
    CONTENT_FACTORY_AUTO_PUBLISH_THREADS,
    CONTENT_FACTORY_AUTO_PUBLISH_X,
    CONTENT_FACTORY_ENABLED,
    CONTENT_FACTORY_SCHEDULE_HOUR,
    CONTENT_FACTORY_TIMEZONE,
    CONTENT_FACTORY_X_MODE,
    CONTENT_FACTORY_X_SAVE_TO_DRAFT,
    LOG_DIR,
    REASONING_EFFORT,
)
from cost_tracker import log_cost
from llm_router import call_llm
from utils.atomic_write import atomic_json_write
from utils.json_parser import extract_json

logger = logging.getLogger(__name__)

CONTENT_FACTORY_STATE_FILE = os.path.join(LOG_DIR, "content_factory_state.json")
CONTENT_FACTORY_RUN_LOG = os.path.join(LOG_DIR, "content_factory_runs.jsonl")
DAEMON_STATE_FILE = os.path.join(LOG_DIR, "daemon_state.json")
CYCLE_HISTORY_FILE = os.path.join(LOG_DIR, "cycle_history.jsonl")


def _get_timezone() -> ZoneInfo:
    """Return the configured timezone or UTC if invalid."""
    try:
        return ZoneInfo(CONTENT_FACTORY_TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid CONTENT_FACTORY_TIMEZONE '%s' - using UTC", CONTENT_FACTORY_TIMEZONE)
        return ZoneInfo("UTC")


def _now_local(now: datetime | None = None) -> datetime:
    """Return timezone-aware local time for content factory scheduling."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(_get_timezone())


def _load_state() -> dict:
    """Load content factory state from disk."""
    if not os.path.exists(CONTENT_FACTORY_STATE_FILE):
        return {}
    try:
        with open(CONTENT_FACTORY_STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict):
    """Persist content factory state to disk."""
    os.makedirs(LOG_DIR, exist_ok=True)
    atomic_json_write(CONTENT_FACTORY_STATE_FILE, state)


def _append_run_log(entry: dict):
    """Append a content-factory run record to the audit log."""
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        with open(CONTENT_FACTORY_RUN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as exc:
        logger.warning("Failed to append content factory run log: %s", exc)


def _load_daemon_state() -> dict:
    """Load the latest daemon state if present."""
    if not os.path.exists(DAEMON_STATE_FILE):
        return {}
    try:
        with open(DAEMON_STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _load_recent_cycle_history(limit: int = 5) -> list[dict]:
    """Load recent cycle history entries."""
    if not os.path.exists(CYCLE_HISTORY_FILE):
        return []
    rows = []
    try:
        with open(CYCLE_HISTORY_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


def _safe_top_opportunities(limit: int = 3) -> list[dict]:
    """Get the strongest current signal opportunities."""
    try:
        from signal_collector import get_top_opportunities

        opportunities = get_top_opportunities(limit=limit)
    except Exception as exc:
        logger.warning("Top opportunities unavailable: %s", exc)
        return []

    trimmed = []
    for item in opportunities[:limit]:
        trimmed.append({
            "title": item.get("title", ""),
            "summary": item.get("pain_point_summary", ""),
            "score": item.get("opportunity_score", 0),
            "subreddit": item.get("subreddit", ""),
            "url": item.get("url", ""),
            "solutions": item.get("potential_solutions", [])[:3],
        })
    return trimmed


def _safe_threads_engagement() -> dict:
    """Get recent Threads engagement if configured."""
    try:
        from tools.threads_client import get_recent_engagement, is_configured

        if not is_configured():
            return {}
        return get_recent_engagement(limit=5)
    except Exception as exc:
        logger.warning("Threads engagement unavailable: %s", exc)
        return {}


def _safe_channel_history() -> dict[str, list[str]]:
    """Read recent Discord channel text to learn local style patterns."""
    try:
        from tools.discord_client import get_channel_messages, get_configured_channels, is_configured

        if not is_configured():
            return {}
        channels = get_configured_channels()
        history = {}
        for name, channel_id in channels.items():
            try:
                messages = get_channel_messages(channel_id, limit=15)
            except Exception as exc:
                logger.warning("Discord history unavailable for %s: %s", name, exc)
                continue
            text_rows = []
            for msg in messages:
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                author = msg.get("author", {}) or {}
                if author.get("bot"):
                    continue
                text_rows.append(content[:400])
            history[name] = text_rows[:8]
        return history
    except Exception as exc:
        logger.warning("Discord history load failed: %s", exc)
        return {}


def _collect_context() -> dict:
    """Collect the inputs used to build the daily content pack."""
    state = _load_state()
    daemon_state = _load_daemon_state()
    cycle_history = _load_recent_cycle_history(limit=5)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "last_pack_summary": state.get("last_pack_summary", {}),
        "daemon_state": {
            "status": daemon_state.get("status"),
            "cycle": daemon_state.get("cycle"),
            "avg_score": daemon_state.get("avg_score"),
            "rounds_completed": daemon_state.get("rounds_completed"),
            "domain_results": daemon_state.get("domain_results", [])[:5],
        },
        "cycle_history": cycle_history,
        "top_opportunities": _safe_top_opportunities(limit=3),
        "threads_engagement": _safe_threads_engagement(),
        "discord_history": _safe_channel_history(),
    }


def _response_text(response) -> str:
    """Extract text from a normalized LLM response."""
    if isinstance(response, dict):
        return response.get("text", "")

    blocks = getattr(response, "content", []) or []
    texts = []
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            texts.append(getattr(block, "text", ""))
    return "\n".join(part for part in texts if part)


def _shorten_post(text: str, max_len: int) -> str:
    """Trim a post to platform limits without breaking badly."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned

    cut = cleaned[: max_len - 1]
    split_at = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if split_at >= 80:
        return cut[: split_at + 1].strip()
    split_at = cut.rfind(" ")
    if split_at >= 80:
        return cut[:split_at].rstrip() + "…"
    return cut.rstrip() + "…"


def _normalize_pack(result: dict) -> dict:
    """Validate and normalize the generated content pack."""
    research = result.get("research_brief") or {}
    scripts = result.get("scripts") or {}
    thumbnail = result.get("thumbnail") or {}
    learning = result.get("learning") or {}

    normalized = {
        "research_brief": {
            "angle": str(research.get("angle", "Daily Cortex brief")).strip(),
            "why_now": str(research.get("why_now", "No fresh signal was available, so keep the brief conservative.")).strip(),
            "evidence": [str(item).strip() for item in research.get("evidence", []) if str(item).strip()][:4],
        },
        "scripts": {
            "x_post": _shorten_post(str(scripts.get("x_post", "")).strip(), 280),
            "threads_post": _shorten_post(str(scripts.get("threads_post", "")).strip(), 500),
            "hook": str(scripts.get("hook", "")).strip(),
            "notes": [str(item).strip() for item in scripts.get("notes", []) if str(item).strip()][:4],
        },
        "thumbnail": {
            "headline": str(thumbnail.get("headline", "")).strip(),
            "subline": str(thumbnail.get("subline", "")).strip(),
            "visual_direction": str(thumbnail.get("visual_direction", "")).strip(),
            "image_notes": [str(item).strip() for item in thumbnail.get("image_notes", []) if str(item).strip()][:4],
        },
        "learning": {
            "patterns_to_keep": [str(item).strip() for item in learning.get("patterns_to_keep", []) if str(item).strip()][:4],
            "patterns_to_avoid": [str(item).strip() for item in learning.get("patterns_to_avoid", []) if str(item).strip()][:4],
        },
    }

    if not normalized["scripts"]["x_post"]:
        raise ValueError("Content pack missing x_post")
    if not normalized["scripts"]["threads_post"]:
        raise ValueError("Content pack missing threads_post")
    return normalized


def generate_content_pack(context: dict) -> dict:
    """Generate the daily content pack from current Cortex context."""
    prompt = f"""You are Cortex's content factory.

Write one daily content pack for Discord and social posting.

Use this context:
{json.dumps(context, indent=2)}

Write like a person.
Rules:
- Use simple words.
- Use specific facts from the context. Do not invent metrics or sources.
- No hype, no fake grand claims, no em dashes.
- No chatbot filler like 'I hope this helps' or 'Great question'.
- Vary sentence rhythm so it does not sound machine-made.
- If the context is thin, say less and stay concrete.
- X draft must fit under 280 characters.
- Threads draft must fit under 500 characters.
- Thumbnail brief should describe a real visual direction, not generic buzzwords.

Return ONLY JSON in this shape:
{{
  "research_brief": {{
    "angle": "short headline for today's angle",
    "why_now": "one short paragraph",
    "evidence": ["bullet 1", "bullet 2", "bullet 3"]
  }},
  "scripts": {{
    "hook": "one short hook line",
    "x_post": "single X post draft",
    "threads_post": "single Threads post draft",
    "notes": ["why this angle fits today", "what tone to keep"]
  }},
  "thumbnail": {{
    "headline": "short headline text",
    "subline": "optional support line",
    "visual_direction": "one paragraph art direction",
    "image_notes": ["composition note", "color note", "subject note"]
  }},
  "learning": {{
    "patterns_to_keep": ["pattern 1", "pattern 2"],
    "patterns_to_avoid": ["pattern 1", "pattern 2"]
  }}
}}"""

    response = call_llm(
        model=CHAT_MODEL,
        system=prompt,
        messages=[{"role": "user", "content": "Build today's content pack."}],
        max_tokens=1800,
        temperature=0.8,
        reasoning_effort=REASONING_EFFORT.get("chat"),
    )

    if getattr(response, "usage", None):
        log_cost(
            CHAT_MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
            "content_factory",
            "growth",
        )

    text = _response_text(response)
    parsed = extract_json(text)
    if not parsed:
        raise ValueError("Could not parse content factory JSON output")
    return _normalize_pack(parsed)


def _format_research_message(pack: dict) -> str:
    research = pack["research_brief"]
    lines = [
        "Research Agent",
        "",
        research["angle"],
        "",
        research["why_now"],
    ]
    if research["evidence"]:
        lines.append("")
        lines.append("Signals")
        lines.extend(f"- {item}" for item in research["evidence"])
    return "\n".join(lines)


def _format_scripts_message(pack: dict) -> str:
    scripts = pack["scripts"]
    lines = [
        "Writing Agent",
        "",
        f"Hook: {scripts['hook']}",
        "",
        "X draft",
        scripts["x_post"],
        "",
        "Threads draft",
        scripts["threads_post"],
    ]
    if scripts["notes"]:
        lines.append("")
        lines.append("Notes")
        lines.extend(f"- {item}" for item in scripts["notes"])
    return "\n".join(lines)


def _format_thumbnail_message(pack: dict) -> str:
    thumbnail = pack["thumbnail"]
    learning = pack["learning"]
    lines = [
        "Thumbnail Agent",
        "",
        f"Headline: {thumbnail['headline']}",
    ]
    if thumbnail["subline"]:
        lines.append(f"Subline: {thumbnail['subline']}")
    lines.extend([
        "",
        "Visual direction",
        thumbnail["visual_direction"],
    ])
    if thumbnail["image_notes"]:
        lines.append("")
        lines.append("Image notes")
        lines.extend(f"- {item}" for item in thumbnail["image_notes"])
    if learning["patterns_to_keep"] or learning["patterns_to_avoid"]:
        lines.append("")
        lines.append("Pattern memory")
        lines.extend(f"- Keep: {item}" for item in learning["patterns_to_keep"])
        lines.extend(f"- Avoid: {item}" for item in learning["patterns_to_avoid"])
    return "\n".join(lines)


def _post_to_discord(pack: dict) -> dict:
    """Push the pack into the configured Discord channels."""
    from tools.discord_client import get_configured_channels, is_configured, send_message

    if not is_configured():
        raise RuntimeError("Discord content factory not configured")

    channels = get_configured_channels()
    messages = {
        "research": _format_research_message(pack),
        "scripts": _format_scripts_message(pack),
        "thumbnails": _format_thumbnail_message(pack),
    }
    results = {}
    for name, channel_id in channels.items():
        posted = send_message(channel_id, messages[name])
        results[name] = len(posted)
    return results


def _publish_social_posts(pack: dict) -> dict:
    """Optionally publish the generated copy to X and Threads."""
    results = {
        "x": {"enabled": CONTENT_FACTORY_AUTO_PUBLISH_X, "status": "skipped"},
        "threads": {"enabled": CONTENT_FACTORY_AUTO_PUBLISH_THREADS, "status": "skipped"},
    }

    if CONTENT_FACTORY_AUTO_PUBLISH_X:
        from tools.buffer_client import create_post, get_x_channels

        x_channels = get_x_channels()
        if not x_channels:
            raise RuntimeError("Buffer auto-publish enabled but no connected X channels were found")
        x_result = create_post(
            channel_id=x_channels[0]["id"],
            text=pack["scripts"]["x_post"],
            mode=CONTENT_FACTORY_X_MODE,
            scheduling_type="automatic",
            save_to_draft=CONTENT_FACTORY_X_SAVE_TO_DRAFT,
            source="cortex-content-factory",
        )
        results["x"] = {
            "enabled": True,
            "status": "posted" if not CONTENT_FACTORY_X_SAVE_TO_DRAFT else "drafted",
            "post_id": x_result.get("post", {}).get("id"),
        }

    if CONTENT_FACTORY_AUTO_PUBLISH_THREADS:
        from tools.threads_client import publish_post

        threads_result = publish_post(text=pack["scripts"]["threads_post"])
        results["threads"] = {
            "enabled": True,
            "status": "posted",
            "post_id": threads_result.get("id"),
        }

    return results


def should_run_now(now: datetime | None = None) -> bool:
    """Return True when the content factory should run for today's slot."""
    if not CONTENT_FACTORY_ENABLED:
        return False

    from tools.discord_client import is_configured

    if not is_configured():
        return False

    local_now = _now_local(now)
    if local_now.hour < CONTENT_FACTORY_SCHEDULE_HOUR:
        return False

    state = _load_state()
    last_run_day = state.get("last_run_local_date", "")
    return last_run_day != local_now.strftime("%Y-%m-%d")


def get_content_factory_status(now: datetime | None = None) -> dict:
    """Return current content-factory status for CLI display."""
    from tools.discord_client import get_configured_channels, is_configured

    state = _load_state()
    local_now = _now_local(now)
    return {
        "enabled": CONTENT_FACTORY_ENABLED,
        "configured": is_configured(),
        "timezone": CONTENT_FACTORY_TIMEZONE,
        "scheduled_hour": CONTENT_FACTORY_SCHEDULE_HOUR,
        "due_now": should_run_now(now),
        "now_local": local_now.isoformat(),
        "last_run_at": state.get("last_run_at"),
        "last_run_local_date": state.get("last_run_local_date"),
        "last_error": state.get("last_error", ""),
        "channels": get_configured_channels(),
        "auto_publish_x": CONTENT_FACTORY_AUTO_PUBLISH_X,
        "auto_publish_threads": CONTENT_FACTORY_AUTO_PUBLISH_THREADS,
        "x_mode": CONTENT_FACTORY_X_MODE,
        "x_save_to_draft": CONTENT_FACTORY_X_SAVE_TO_DRAFT,
    }


def run_content_factory(force: bool = False, now: datetime | None = None) -> dict:
    """Run the content factory once."""
    from tools.discord_client import is_configured

    local_now = _now_local(now)
    if not force and not should_run_now(local_now):
        return {"ok": True, "skipped": True, "reason": "not_due"}

    if not is_configured():
        return {"ok": False, "error": "Discord content factory not configured"}

    run_started = datetime.now(timezone.utc)
    context = _collect_context()
    try:
        pack = generate_content_pack(context)
        discord_results = _post_to_discord(pack)
        publish_results = _publish_social_posts(pack)

        state = {
            "last_run_at": run_started.isoformat(),
            "last_run_local_date": local_now.strftime("%Y-%m-%d"),
            "last_error": "",
            "last_pack_summary": {
                "angle": pack["research_brief"]["angle"],
                "x_post": pack["scripts"]["x_post"],
                "threads_post": pack["scripts"]["threads_post"],
                "thumbnail_headline": pack["thumbnail"]["headline"],
            },
        }
        _save_state(state)

        result = {
            "ok": True,
            "ran_at": run_started.isoformat(),
            "discord": discord_results,
            "publish": publish_results,
            "pack": pack,
        }
        _append_run_log({"status": "success", **result})
        return result
    except Exception as exc:
        state = _load_state()
        state["last_error"] = str(exc)
        state["last_attempt_at"] = run_started.isoformat()
        _save_state(state)
        error_result = {
            "ok": False,
            "ran_at": run_started.isoformat(),
            "error": str(exc),
        }
        _append_run_log({"status": "failure", **error_result})
        logger.warning("Content factory failed: %s", exc)
        return error_result


def run_content_factory_if_due(now: datetime | None = None) -> dict:
    """Run the content factory only if today's slot is due."""
    if not should_run_now(now):
        return {"ok": True, "skipped": True, "reason": "not_due"}
    return run_content_factory(force=True, now=now)
