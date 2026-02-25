"""
Cross-Domain Transfer Agent (Layer 5)

Extracts general research principles from proven strategies across domains,
then seeds new domains with those principles. This is how the system compounds
intelligence, not just data — insights from Domain A become starter strategies
for Domain B.

Pipeline:
1. Collect proven strategies + performance data from all domains with enough data
2. Ask Claude to abstract domain-specific strategies into general principles
3. Store principles with evidence + provenance
4. When entering a new domain, generate a seed strategy from principles + domain context
5. Seed strategies are saved as 'pending' (require human approval)
"""

import json
import os
import sys
from datetime import date, datetime, timezone

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, STRATEGY_DIR, MIN_OUTPUTS_FOR_TRANSFER, MIN_AVG_SCORE_FOR_TRANSFER
from memory_store import load_outputs, get_stats
from strategy_store import (
    get_strategy, get_active_version, get_strategy_status,
    get_strategy_performance, list_versions, save_strategy,
)
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Principles file
PRINCIPLES_FILE = os.path.join(STRATEGY_DIR, "_principles.json")

# Transfer tracking file
TRANSFER_LOG_FILE = os.path.join(STRATEGY_DIR, "_transfer_log.json")


def _build_extraction_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a meta-learning analyst for an autonomous research system. TODAY'S DATE: {today}.

Your job: analyze PROVEN research strategies from multiple domains and extract GENERAL
PRINCIPLES that work universally — not domain-specific tips.

You receive:
1. Proven strategies from one or more domains, each with their performance scores
2. Performance data showing what scored well vs poorly

You must:
1. Identify which strategy elements are GENERAL (apply to any research domain)
   vs DOMAIN-SPECIFIC (only relevant to that domain)
2. Extract general principles with evidence from the performance data
3. Rank principles by confidence (how much evidence supports them)

PRINCIPLE EXTRACTION RULES:
- A principle is GENERAL if it would improve research quality in ANY domain
  Example GENERAL: "Use 3-5 focused searches rather than many broad ones"
  Example DOMAIN-SPECIFIC: "Always check CoinMarketCap for crypto prices" (NOT general)
- Each principle must be actionable — something a researcher can actually DO
- Include the evidence: what scores improved when this principle was followed
- Confidence: "high" = evidence from 2+ domains or 5+ outputs, "medium" = 1 domain with 3+ outputs, "low" = limited data

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{{
    "principles": [
        {{
            "principle": "Specific actionable instruction",
            "category": "search_strategy|output_structure|source_quality|temporal_awareness|depth_vs_breadth|honesty_calibration",
            "evidence": "What data shows this works",
            "source_domains": ["domain1", "domain2"],
            "confidence": "high|medium|low"
        }}
    ],
    "domain_specific_insights": [
        {{
            "domain": "domain_name",
            "insight": "What works specifically in this domain",
            "not_transferable_because": "Why this is domain-specific"
        }}
    ],
    "meta_observations": "Brief summary of cross-domain patterns"
}}
"""


def _build_seed_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a strategy architect for an autonomous research system. TODAY'S DATE: {today}.

Your job: generate a STARTER STRATEGY for a researcher agent entering a NEW domain.
You are given:
1. A set of general research principles proven across other domains
2. The target domain name and (optionally) an example question

You must:
1. Write a complete researcher strategy document
2. Incorporate ALL applicable general principles
3. Add domain-appropriate specifics where you can reasonably infer them
4. Keep it concise — under 500 words. Agents degrade with bloated prompts.

STRATEGY REQUIREMENTS:
- Must include TODAY'S DATE awareness ({today}) and temporal verification rules
- Must include the JSON output format specification
- Must recommend 3-5 searches (hard cap is 10, but 3-5 is optimal)
- Must balance depth vs breadth based on the general principles
- Mark placeholder areas where domain-specific tuning will happen after initial runs

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{{
    "strategy": "THE FULL STRATEGY TEXT",
    "principles_applied": ["principle 1 text", "principle 2 text"],
    "domain_adaptations": ["What was adapted for this specific domain"],
    "expected_improvement": "Why this should outperform the default strategy"
}}
"""


EXTRACTION_PROMPT = _build_extraction_prompt()
SEED_PROMPT = _build_seed_prompt()


def get_transfer_sources() -> list[dict]:
    """
    Identify domains that qualify as transfer sources.

    Criteria:
    - At least MIN_OUTPUTS_FOR_TRANSFER outputs
    - Average score >= MIN_AVG_SCORE_FOR_TRANSFER
    - Has an active (not trial/pending) strategy with performance data

    Returns:
        List of {domain, stats, strategy, strategy_version, performance} dicts
    """
    # Scan memory directory for domains
    from config import MEMORY_DIR
    if not os.path.exists(MEMORY_DIR):
        return []

    sources = []
    for domain_name in sorted(os.listdir(MEMORY_DIR)):
        domain_dir = os.path.join(MEMORY_DIR, domain_name)
        if not os.path.isdir(domain_dir):
            continue

        stats = get_stats(domain_name)
        if stats["count"] < MIN_OUTPUTS_FOR_TRANSFER:
            continue
        if stats["avg_score"] < MIN_AVG_SCORE_FOR_TRANSFER:
            continue

        # Get the active strategy (if any)
        strategy_text, strategy_version = get_strategy("researcher", domain_name)
        if not strategy_text or strategy_version == "default":
            continue

        status = get_strategy_status("researcher", domain_name)
        if status not in ("active", "trial"):
            continue

        perf = get_strategy_performance(domain_name, strategy_version)

        sources.append({
            "domain": domain_name,
            "stats": stats,
            "strategy": strategy_text,
            "strategy_version": strategy_version,
            "strategy_status": status,
            "performance": perf,
        })

    return sources


def extract_principles(force: bool = False) -> dict | None:
    """
    Extract general principles from proven strategies across all qualifying domains.

    Args:
        force: If True, re-extract even if principles already exist

    Returns:
        The principles dict, or None if not enough data
    """
    # Check if principles already exist and are recent
    if not force and os.path.exists(PRINCIPLES_FILE):
        with open(PRINCIPLES_FILE) as f:
            existing = json.load(f)
        age_hours = (
            datetime.now(timezone.utc) -
            datetime.fromisoformat(existing.get("extracted_at", "2000-01-01T00:00:00+00:00"))
        ).total_seconds() / 3600
        if age_hours < 24:
            print(f"[CROSS-DOMAIN] Principles are {age_hours:.1f}h old (< 24h). Use --force to re-extract.")
            return existing

    sources = get_transfer_sources()
    if not sources:
        print("[CROSS-DOMAIN] No domains qualify as transfer sources yet.")
        print(f"  Need: ≥{MIN_OUTPUTS_FOR_TRANSFER} outputs, avg score ≥{MIN_AVG_SCORE_FOR_TRANSFER}, active strategy")
        return None

    print(f"[CROSS-DOMAIN] Found {len(sources)} qualifying domain(s):")
    for s in sources:
        print(f"  {s['domain']}: {s['stats']['count']} outputs, avg {s['stats']['avg_score']:.1f}, "
              f"strategy {s['strategy_version']} ({s['strategy_status']})")

    # Build the analysis data
    analysis_data = {
        "source_domains": [],
    }
    for s in sources:
        # Also load some high-scoring outputs for evidence
        outputs = load_outputs(s["domain"], min_score=6)
        high_score_examples = []
        for o in outputs[-5:]:  # Last 5 accepted outputs
            high_score_examples.append({
                "question": o.get("question", "?"),
                "score": o.get("overall_score", 0),
                "strengths": o.get("critique", {}).get("strengths", []),
                "weaknesses": o.get("critique", {}).get("weaknesses", []),
                "searches_made": o.get("research", {}).get("_searches_made", 0),
            })

        analysis_data["source_domains"].append({
            "domain": s["domain"],
            "strategy_text": s["strategy"],
            "strategy_version": s["strategy_version"],
            "outputs_count": s["stats"]["count"],
            "avg_score": s["stats"]["avg_score"],
            "accepted": s["stats"]["accepted"],
            "rejected": s["stats"]["rejected"],
            "performance": s["performance"],
            "high_score_examples": high_score_examples,
        })

    user_message = (
        f"Extract general research principles from these proven domain strategies.\n\n"
        f"DATA:\n{json.dumps(analysis_data, indent=2)}"
    )

    print(f"[CROSS-DOMAIN] Asking Claude to extract general principles...")

    response = create_message(
        client,
        model=MODELS["cross_domain"],
        max_tokens=4096,
        system=EXTRACTION_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    log_cost(
        MODELS["cross_domain"],
        response.usage.input_tokens,
        response.usage.output_tokens,
        "cross_domain",
        "_transfer",
    )

    raw_text = response.content[0].text.strip()

    # Robust JSON extraction
    EXPECTED_KEYS = {"principles", "domain_specific_insights", "meta_observations"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if result is None:
        print("[CROSS-DOMAIN] ⚠ Failed to parse principle extraction output")
        return None

    principles = result.get("principles", [])
    if not principles:
        print("[CROSS-DOMAIN] ⚠ No principles extracted")
        return None

    # Store principles
    record = {
        "version": _next_principles_version(),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "source_domains": [s["domain"] for s in sources],
        "source_count": len(sources),
        "principles": principles,
        "domain_specific_insights": result.get("domain_specific_insights", []),
        "meta_observations": result.get("meta_observations", ""),
    }

    os.makedirs(os.path.dirname(PRINCIPLES_FILE), exist_ok=True)
    with open(PRINCIPLES_FILE, "w") as f:
        json.dump(record, f, indent=2)

    print(f"[CROSS-DOMAIN] ✓ Extracted {len(principles)} general principles")
    for i, p in enumerate(principles, 1):
        print(f"  {i}. [{p.get('confidence', '?')}] {p.get('principle', '?')}")

    return record


def _next_principles_version() -> int:
    """Get next version number for principles."""
    if os.path.exists(PRINCIPLES_FILE):
        with open(PRINCIPLES_FILE) as f:
            existing = json.load(f)
        return existing.get("version", 0) + 1
    return 1


def load_principles() -> dict | None:
    """Load current general principles. Returns None if none exist."""
    if not os.path.exists(PRINCIPLES_FILE):
        return None
    with open(PRINCIPLES_FILE) as f:
        return json.load(f)


def generate_seed_strategy(target_domain: str, question_hint: str = "") -> dict | None:
    """
    Generate a seed strategy for a new domain using general principles.

    Args:
        target_domain: The domain to generate a strategy for
        question_hint: Optional example question to help tailor the strategy

    Returns:
        Dict with strategy details, or None if no principles exist
    """
    principles = load_principles()
    if not principles or not principles.get("principles"):
        print("[CROSS-DOMAIN] No general principles available. Run --principles --extract first.")
        return None

    # Check if domain already has a custom strategy
    existing_strategy, existing_version = get_strategy("researcher", target_domain)
    if existing_strategy and existing_version != "default":
        existing_versions = list_versions("researcher", target_domain)
        print(f"[CROSS-DOMAIN] Domain '{target_domain}' already has {len(existing_versions)} strategy version(s)")
        print(f"  Active: {existing_version}. Transfer will create a NEW version incorporating general principles.")

    print(f"[CROSS-DOMAIN] Generating seed strategy for domain '{target_domain}'...")

    seed_data = {
        "target_domain": target_domain,
        "question_hint": question_hint or "(no specific question provided)",
        "general_principles": principles["principles"],
        "source_domains": principles.get("source_domains", []),
        "meta_observations": principles.get("meta_observations", ""),
    }

    user_message = (
        f"Generate a seed research strategy for the domain '{target_domain}' "
        f"based on these proven general principles.\n\n"
        f"DATA:\n{json.dumps(seed_data, indent=2)}"
    )

    response = create_message(
        client,
        model=MODELS["cross_domain"],
        max_tokens=4096,
        system=SEED_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    log_cost(
        MODELS["cross_domain"],
        response.usage.input_tokens,
        response.usage.output_tokens,
        "cross_domain",
        target_domain,
    )

    raw_text = response.content[0].text.strip()

    # Strip markdown fences if present
    raw_text = response.content[0].text.strip()

    # Robust JSON extraction
    EXPECTED_KEYS = {"strategy", "principles_applied", "domain_adaptations"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if result is None:
        print("[CROSS-DOMAIN] ⚠ Failed to parse seed strategy output")
        return None

    strategy_text = result.get("strategy")
    if not strategy_text:
        print("[CROSS-DOMAIN] ⚠ No strategy in output")
        return None

    # Compute version number
    existing_versions = list_versions("researcher", target_domain)
    if existing_versions:
        nums = []
        for v in existing_versions:
            try:
                nums.append(int(v.replace("v", "")))
            except ValueError:
                pass
        next_num = max(nums) + 1 if nums else 1
    else:
        next_num = 1

    new_version = f"v{next_num:03d}"

    # Build reason with transfer provenance
    principles_applied = result.get("principles_applied", [])
    domain_adaptations = result.get("domain_adaptations", [])

    reason = (
        f"CROSS-DOMAIN TRANSFER from [{', '.join(principles.get('source_domains', []))}]. "
        f"Applied {len(principles_applied)} general principles. "
        f"Adaptations: {'; '.join(domain_adaptations[:3])}"
    )

    # Save as pending — requires approval
    filepath = save_strategy(
        agent_role="researcher",
        domain=target_domain,
        strategy_text=strategy_text,
        version=new_version,
        reason=reason,
        status="pending",
    )

    print(f"[CROSS-DOMAIN] ✓ Seed strategy saved: {new_version} (PENDING APPROVAL)")
    print(f"  File: {filepath}")
    print(f"  Principles applied: {len(principles_applied)}")
    for p in principles_applied:
        print(f"    • {p}")
    print(f"  Domain adaptations:")
    for a in domain_adaptations:
        print(f"    → {a}")
    print(f"  ⚠ Run: python main.py --domain {target_domain} --approve {new_version}")

    # Log this transfer for tracking
    _log_transfer(
        target_domain=target_domain,
        source_domains=principles.get("source_domains", []),
        version=new_version,
        principles_applied=principles_applied,
    )

    return {
        "version": new_version,
        "strategy_filepath": filepath,
        "principles_applied": principles_applied,
        "domain_adaptations": domain_adaptations,
        "expected_improvement": result.get("expected_improvement", ""),
    }


# ============================================================
# Transfer Tracking — measure if transfers actually help
# ============================================================

def _load_transfer_log() -> list[dict]:
    """Load the transfer log."""
    if not os.path.exists(TRANSFER_LOG_FILE):
        return []
    try:
        with open(TRANSFER_LOG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_transfer_log(log: list[dict]) -> None:
    """Save the transfer log."""
    os.makedirs(os.path.dirname(TRANSFER_LOG_FILE), exist_ok=True)
    with open(TRANSFER_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def _log_transfer(target_domain: str, source_domains: list[str], version: str, principles_applied: list[str]) -> None:
    """Record a transfer event for later tracking."""
    log = _load_transfer_log()
    log.append({
        "target_domain": target_domain,
        "source_domains": source_domains,
        "strategy_version": version,
        "principles_applied": principles_applied,
        "transferred_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",  # pending → active → measured
        "baseline_avg": None,  # Score avg before transfer strategy
        "transfer_avg": None,  # Score avg under transfer strategy
        "lift": None,          # transfer_avg - baseline_avg
    })
    _save_transfer_log(log)


def measure_transfer_lift(target_domain: str) -> dict | None:
    """
    Measure the performance lift from a cross-domain transfer.
    
    Compares scores before the transfer strategy vs scores under it.
    Updates the transfer log and principle confidence.
    
    Returns:
        Dict with lift details, or None if no transfer to measure.
    """
    log = _load_transfer_log()
    
    # Find the most recent pending/active transfer for this domain
    transfer = None
    for entry in reversed(log):
        if entry.get("target_domain") == target_domain and entry.get("status") in ("pending", "active"):
            transfer = entry
            break
    
    if not transfer:
        print(f"[CROSS-DOMAIN] No pending transfer to measure for domain '{target_domain}'")
        return None
    
    version = transfer.get("strategy_version", "")
    
    # Get performance data
    perf = get_strategy_performance(target_domain, version)
    if perf["count"] < 3:
        print(f"[CROSS-DOMAIN] Transfer strategy {version} has only {perf['count']} outputs (need 3+)")
        transfer["status"] = "active"
        _save_transfer_log(log)
        return None
    
    # Get baseline (performance before the transfer strategy)
    all_outputs = load_outputs(target_domain, min_score=0)
    baseline_scores = []
    for o in all_outputs:
        sv = o.get("_strategy_version", "default")
        if sv != version and sv != "":
            baseline_scores.append(o.get("overall_score", 0))
    
    transfer_avg = perf["avg_score"]
    
    if baseline_scores:
        baseline_avg = sum(baseline_scores) / len(baseline_scores)
        lift = transfer_avg - baseline_avg
    else:
        baseline_avg = None
        lift = None
    
    # Update transfer log
    transfer["status"] = "measured"
    transfer["baseline_avg"] = round(baseline_avg, 2) if baseline_avg is not None else None
    transfer["transfer_avg"] = round(transfer_avg, 2)
    transfer["lift"] = round(lift, 2) if lift is not None else None
    transfer["measured_at"] = datetime.now(timezone.utc).isoformat()
    transfer["outputs_measured"] = perf["count"]
    _save_transfer_log(log)
    
    # Update principle confidence based on lift
    if lift is not None:
        _update_principle_confidence(transfer.get("principles_applied", []), lift)
    
    # Report
    if lift is not None:
        direction = "↑" if lift > 0 else "↓" if lift < 0 else "→"
        print(f"[CROSS-DOMAIN] Transfer lift measured for '{target_domain}': "
              f"baseline {baseline_avg:.1f} → transfer {transfer_avg:.1f} ({direction}{abs(lift):.1f})")
    else:
        print(f"[CROSS-DOMAIN] Transfer avg for '{target_domain}': {transfer_avg:.1f} (no baseline to compare)")
    
    return {
        "domain": target_domain,
        "version": version,
        "baseline_avg": baseline_avg,
        "transfer_avg": transfer_avg,
        "lift": lift,
        "outputs_measured": perf["count"],
    }


def _update_principle_confidence(principles_applied: list[str], lift: float) -> None:
    """
    Update principle confidence based on measured transfer lift.
    
    Positive lift → increase confidence of applied principles.
    Negative lift → decrease confidence.
    """
    principles_data = load_principles()
    if not principles_data or not principles_data.get("principles"):
        return
    
    updated = False
    for principle in principles_data["principles"]:
        p_text = principle.get("principle", "")
        if p_text in principles_applied:
            # Track transfer results
            if "transfer_results" not in principle:
                principle["transfer_results"] = []
            principle["transfer_results"].append({
                "lift": lift,
                "measured_at": datetime.now(timezone.utc).isoformat(),
            })
            
            # Adjust confidence based on accumulated evidence
            results = principle["transfer_results"]
            avg_lift = sum(r["lift"] for r in results) / len(results)
            
            if avg_lift > 0.5 and len(results) >= 2:
                principle["confidence"] = "high"
            elif avg_lift > 0 and len(results) >= 1:
                principle["confidence"] = "medium"
            elif avg_lift < -0.5:
                principle["confidence"] = "low"
            
            updated = True
    
    if updated:
        with open(PRINCIPLES_FILE, "w") as f:
            json.dump(principles_data, f, indent=2)


def get_transfer_stats() -> list[dict]:
    """Get summary of all transfer events and their outcomes."""
    log = _load_transfer_log()
    return [
        {
            "target_domain": t.get("target_domain"),
            "source_domains": t.get("source_domains"),
            "version": t.get("strategy_version"),
            "status": t.get("status"),
            "lift": t.get("lift"),
            "transferred_at": t.get("transferred_at"),
        }
        for t in log
    ]
