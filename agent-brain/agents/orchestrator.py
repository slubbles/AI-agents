"""
Orchestrator Agent — Multi-Domain Coordination

The Orchestrator manages the entire system's learning across all domains.
It decides:
  1. Which domains need attention (priority scoring)
  2. How many rounds to allocate per domain (budget-aware)
  3. When to trigger synthesis, evolution, or cross-domain transfers
  4. What the overall system health looks like

Two modes:
  - Deterministic (default): Pure logic scoring. No API calls. Fast and cheap.
  - LLM-Reasoned (--smart-orchestrate): Uses Claude to reason about allocation
    when the deterministic approach would benefit from nuance (e.g., score plateaus,
    cross-domain synergies, strategic pivots).

Usage (via main.py):
    python main.py --orchestrate                    # Deterministic allocation
    python main.py --orchestrate --rounds 10        # 10 total rounds, split intelligently
    python main.py --orchestrate --target-domains crypto,ai  # Only orchestrate specific domains
    python main.py --smart-orchestrate              # LLM-reasoned allocation
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    QUALITY_THRESHOLD, MIN_OUTPUTS_FOR_ANALYSIS, EVOLVE_EVERY_N,
    MIN_OUTPUTS_FOR_SYNTHESIS, SYNTHESIZE_EVERY_N,
    MIN_OUTPUTS_FOR_TRANSFER, MIN_AVG_SCORE_FOR_TRANSFER,
    MEMORY_DIR,
)
from memory_store import get_stats, load_outputs, get_archive_stats, load_knowledge_base
from strategy_store import (
    get_active_version, get_strategy_status, list_pending,
    get_strategy_performance,
)
from cost_tracker import check_budget, get_daily_spend
from agents.cross_domain import load_principles


# ============================================================
# Domain Priority Scoring
# ============================================================

def _score_domain_priority(domain: str, stats: dict, strategy_version: str,
                           strategy_status: str, pending_count: int,
                           has_kb: bool) -> dict:
    """
    Score a domain's priority for receiving attention.
    
    Higher score = more urgent.
    
    Factors:
    - Data scarcity (fewer outputs → higher priority)
    - Acceptance rate (low rate → may need strategy fix, but not useless)
    - Strategy maturity (default/trial → needs proving)
    - Knowledge gaps (no KB → higher priority if has enough accepted outputs)
    - Near evolution trigger (close to EVOLVE_EVERY_N → push to trigger)
    - Near synthesis trigger (close to SYNTHESIZE_EVERY_N)
    - Pending approvals (blocked → skip, don't waste budget)
    
    Returns:
        Dict with priority score, reasons, and recommended action
    """
    score = 0.0
    reasons = []
    action = "auto"  # default: run auto mode
    skip = False

    count = stats["count"]
    accepted = stats["accepted"]
    rejected = stats["rejected"]
    avg_score = stats["avg_score"]
    acceptance_rate = accepted / count if count > 0 else 0

    # ── Pending approvals block research ──
    if pending_count > 0:
        reasons.append(f"has {pending_count} pending strategy(ies) — needs human approval")
        action = "approve"
        skip = True
        score -= 100  # Don't run, just flag

    # ── Data scarcity (0-5 outputs is "starving") ──
    if count == 0:
        score += 50
        reasons.append("zero outputs — needs seed data")
        action = "seed"
    elif count < 3:
        score += 40
        reasons.append(f"only {count} output(s) — needs volume")
    elif count < 5:
        score += 25
        reasons.append(f"only {count} outputs — approaching cross-domain threshold")
    elif count < 10:
        score += 10
        reasons.append(f"{count} outputs — maturing")

    # ── Acceptance rate health ──
    if count >= 3:
        if acceptance_rate < 0.4:
            score += 15
            reasons.append(f"low acceptance rate ({acceptance_rate:.0%}) — strategy may need work")
        elif acceptance_rate >= 0.8:
            score += 5
            reasons.append(f"high acceptance rate ({acceptance_rate:.0%}) — healthy")

    # ── Strategy maturity ──
    if strategy_version == "default" and count > 0:
        score += 15
        reasons.append("still on default strategy")
    elif strategy_status == "trial":
        score += 10
        reasons.append(f"strategy {strategy_version} in trial — needs data to evaluate")

    # ── Near evolution trigger ──
    if count >= MIN_OUTPUTS_FOR_ANALYSIS:
        outputs_until_evolve = EVOLVE_EVERY_N - (count % EVOLVE_EVERY_N)
        if outputs_until_evolve <= 2 and strategy_status != "trial":
            score += 20
            reasons.append(f"{outputs_until_evolve} output(s) until evolution trigger")

    # ── Knowledge base status ──
    if accepted >= MIN_OUTPUTS_FOR_SYNTHESIS and not has_kb:
        score += 10
        reasons.append("has enough accepted outputs but no knowledge base")

    # ── Cross-domain transfer readiness ──
    if count >= MIN_OUTPUTS_FOR_TRANSFER and avg_score >= MIN_AVG_SCORE_FOR_TRANSFER:
        if strategy_version != "default":
            score += 3
            reasons.append("qualifies as cross-domain transfer source")

    return {
        "domain": domain,
        "priority": round(score, 1),
        "reasons": reasons,
        "action": action,
        "skip": skip,
        "stats": stats,
        "strategy": strategy_version,
        "strategy_status": strategy_status,
    }


def discover_domains() -> list[str]:
    """Discover all domains that have memory directories."""
    if not os.path.exists(MEMORY_DIR):
        return []
    domains = []
    for d in sorted(os.listdir(MEMORY_DIR)):
        if os.path.isdir(os.path.join(MEMORY_DIR, d)) and not d.startswith("_"):
            domains.append(d)
    return domains


def prioritize_domains(target_domains: list[str] | None = None) -> list[dict]:
    """
    Analyze all domains and return them ranked by priority.
    
    Args:
        target_domains: If specified, only analyze these domains
    
    Returns:
        List of domain priority dicts, sorted by priority (descending)
    """
    domains = target_domains or discover_domains()
    
    priorities = []
    for domain in domains:
        stats = get_stats(domain)
        strategy_version = get_active_version("researcher", domain)
        strategy_status = get_strategy_status("researcher", domain)
        pending = list_pending("researcher", domain)
        has_kb = load_knowledge_base(domain) is not None

        priority = _score_domain_priority(
            domain=domain,
            stats=stats,
            strategy_version=strategy_version,
            strategy_status=strategy_status,
            pending_count=len(pending),
            has_kb=has_kb,
        )
        priorities.append(priority)

    # Sort by priority (descending)
    priorities.sort(key=lambda p: p["priority"], reverse=True)
    return priorities


# ============================================================
# Round Allocation
# ============================================================

def allocate_rounds(priorities: list[dict], total_rounds: int,
                    max_per_domain: int = 5) -> list[dict]:
    """
    Allocate research rounds across domains based on priority.
    
    Rules:
    - Skip domains with pending approvals
    - Skip domains with 0 outputs (need manual seed)
    - Higher priority gets more rounds
    - No domain gets more than max_per_domain rounds
    - Minimum 1 round per active domain
    
    Returns:
        List of {domain, rounds, action, reasons} dicts
    """
    # Filter to actionable domains (not skipped, has at least some data or is seedable)
    active = [p for p in priorities if not p["skip"] and p["stats"]["count"] > 0]
    skipped = [p for p in priorities if p["skip"] or p["stats"]["count"] == 0]

    if not active:
        return []

    # Calculate proportional allocation based on priority scores
    total_priority = sum(max(p["priority"], 1) for p in active)
    
    allocation = []
    rounds_used = 0

    for p in active:
        if rounds_used >= total_rounds:
            break
        
        # Proportional share, but at least 1 round
        share = max(1, round((max(p["priority"], 1) / total_priority) * total_rounds))
        share = min(share, max_per_domain)  # Cap per domain
        share = min(share, total_rounds - rounds_used)  # Don't exceed total

        allocation.append({
            "domain": p["domain"],
            "rounds": share,
            "action": p["action"],
            "reasons": p["reasons"],
            "stats": p["stats"],
            "strategy": p["strategy"],
            "strategy_status": p["strategy_status"],
        })
        rounds_used += share

    # If we have remaining rounds, distribute to highest priority domains
    remaining = total_rounds - rounds_used
    if remaining > 0:
        for a in allocation:
            if remaining <= 0:
                break
            add = min(remaining, max_per_domain - a["rounds"])
            a["rounds"] += add
            remaining -= add

    return allocation


# ============================================================
# Post-Run Actions
# ============================================================

def get_post_run_actions(domain: str) -> list[dict]:
    """
    Determine what actions should happen after research rounds.
    
    Checks:
    - Should we synthesize the knowledge base?
    - Should we trigger strategy evolution?
    - Should we extract cross-domain principles?
    - Is the domain ready for cross-domain transfer?
    
    Returns:
        List of {action, reason} dicts
    """
    actions = []
    stats = get_stats(domain)
    accepted = stats["accepted"]
    count = stats["count"]
    strategy_version = get_active_version("researcher", domain)
    strategy_status = get_strategy_status("researcher", domain)
    has_kb = load_knowledge_base(domain) is not None

    # Synthesis check
    if accepted >= MIN_OUTPUTS_FOR_SYNTHESIS:
        if not has_kb:
            actions.append({
                "action": "synthesize",
                "reason": f"{accepted} accepted outputs, no knowledge base yet",
            })
        elif accepted % SYNTHESIZE_EVERY_N == 0:
            actions.append({
                "action": "synthesize",
                "reason": f"{accepted} accepted outputs — time to update knowledge base",
            })

    # Evolution check
    if count >= MIN_OUTPUTS_FOR_ANALYSIS and strategy_status != "trial":
        pending = list_pending("researcher", domain)
        if not pending and count % EVOLVE_EVERY_N == 0:
            actions.append({
                "action": "evolve",
                "reason": f"{count} outputs, every-{EVOLVE_EVERY_N} trigger",
            })

    # Cross-domain principle extraction
    if (count >= MIN_OUTPUTS_FOR_TRANSFER and
        stats["avg_score"] >= MIN_AVG_SCORE_FOR_TRANSFER and
        strategy_version != "default"):
        actions.append({
            "action": "principles",
            "reason": f"{domain} qualifies as transfer source (avg {stats['avg_score']:.1f})",
        })

    return actions


def get_system_health() -> dict:
    """
    Compute overall system health metrics.
    
    Returns:
        Dict with health score, metrics, and recommendations.
    """
    domains = discover_domains()
    
    total_outputs = 0
    total_accepted = 0
    total_rejected = 0
    domain_count = len(domains)
    domains_with_strategy = 0
    domains_with_kb = 0
    domains_in_trial = 0
    domains_with_pending = 0
    all_scores = []

    for d in domains:
        stats = get_stats(d)
        total_outputs += stats["count"]
        total_accepted += stats["accepted"]
        total_rejected += stats["rejected"]
        if stats["count"] > 0:
            all_scores.extend([stats["avg_score"]] * stats["count"])
        
        sv = get_active_version("researcher", d)
        if sv != "default":
            domains_with_strategy += 1
        if get_strategy_status("researcher", d) == "trial":
            domains_in_trial += 1
        if list_pending("researcher", d):
            domains_with_pending += 1
        if load_knowledge_base(d) is not None:
            domains_with_kb += 1

    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    acceptance_rate = total_accepted / total_outputs if total_outputs > 0 else 0

    budget = check_budget()
    daily = get_daily_spend()

    principles = load_principles()
    principle_count = len(principles.get("principles", [])) if principles else 0

    # Health score (0-100)
    health = 0
    health += min(30, total_outputs * 1.5)  # Data volume (max 30)
    health += min(20, acceptance_rate * 25)  # Quality (max 20)
    health += min(15, domains_with_strategy * 5)  # Strategy coverage (max 15)
    health += min(15, domains_with_kb * 5)  # Knowledge coverage (max 15)
    health += min(10, principle_count * 2)  # Cross-domain learning (max 10)
    health += min(10, domain_count * 2)  # Domain breadth (max 10)
    health = min(100, round(health))

    return {
        "health_score": health,
        "total_outputs": total_outputs,
        "total_accepted": total_accepted,
        "total_rejected": total_rejected,
        "acceptance_rate": round(acceptance_rate, 3),
        "avg_score": round(avg_score, 1),
        "domain_count": domain_count,
        "domains_with_strategy": domains_with_strategy,
        "domains_with_kb": domains_with_kb,
        "domains_in_trial": domains_in_trial,
        "domains_with_pending": domains_with_pending,
        "principle_count": principle_count,
        "budget_remaining": budget["remaining"],
        "budget_spent_today": budget["spent"],
        "api_calls_today": daily["calls"],
    }


# ============================================================
# LLM-Reasoned Orchestration
# ============================================================

def smart_orchestrate(total_rounds: int = 10,
                      target_domains: list[str] | None = None) -> dict:
    """
    Use LLM reasoning to decide resource allocation across domains.
    
    Instead of purely deterministic scoring, this feeds the full system state
    to Claude Haiku and asks it to reason about:
    - Which domains have the highest learning potential
    - Where diminishing returns are setting in
    - What cross-domain synergies could be exploited
    - Whether to explore new domains or deepen existing ones
    
    Falls back to deterministic allocation if the LLM call fails.
    Uses Haiku to keep costs minimal — this is a routing decision, not content generation.
    
    Returns:
        Dict with allocation, reasoning, and recommended actions
    """
    import json
    from anthropic import Anthropic
    from config import ANTHROPIC_API_KEY, MODELS
    from cost_tracker import log_cost
    from utils.retry import create_message
    from utils.json_parser import extract_json

    # Gather full system state
    health = get_system_health()
    priorities = prioritize_domains(target_domains)
    budget = check_budget()
    principles = load_principles()
    principle_count = len(principles.get("principles", [])) if principles else 0

    # Build domain summaries
    domain_summaries = []
    for p in priorities:
        domain = p["domain"]
        stats = p["stats"]
        kb = load_knowledge_base(domain)
        kb_claims = len(kb.get("claims", [])) if kb else 0
        
        domain_summaries.append({
            "domain": domain,
            "outputs": stats["count"],
            "accepted": stats["accepted"],
            "avg_score": stats["avg_score"],
            "acceptance_rate": f"{stats['accepted']/stats['count']*100:.0f}%" if stats["count"] > 0 else "N/A",
            "strategy": p["strategy"],
            "strategy_status": p["strategy_status"],
            "kb_claims": kb_claims,
            "deterministic_priority": p["priority"],
            "deterministic_reasons": p["reasons"],
            "skip": p["skip"],
        })

    system_prompt = f"""\
You are the Orchestrator for an autonomous research system. Your job is to decide
how to allocate {total_rounds} research rounds across domains to maximize learning.

SYSTEM STATE:
- Health: {health['health_score']}/100
- Total outputs: {health['total_outputs']}
- Budget remaining: ${budget['remaining']:.2f}
- Cross-domain principles: {principle_count}
- Domains: {len(domain_summaries)}

YOUR DECISION:
Allocate exactly {total_rounds} rounds across the domains below. Consider:
1. Which domains have the highest learning potential RIGHT NOW
2. Where scores are plateauing (diminishing returns)
3. Whether new/sparse domains need seeding
4. Cross-domain synergies (knowledge in domain A could help domain B)
5. Budget: each round costs ~$0.05-0.15

RULES:
- Skip domains with pending strategy approvals (skip=true)
- Minimum 1 round per active domain you include
- Maximum 5 rounds per domain (prevent tunnel vision)
- If a domain is healthy (high scores, many outputs), give it fewer rounds
- If a domain is struggling (low acceptance rate), consider strategy fix first

Respond with ONLY this JSON:
{{
    "allocation": [
        {{"domain": "name", "rounds": N, "reason": "why this many"}}
    ],
    "reasoning": "2-3 sentences explaining your overall strategy",
    "recommended_actions": ["action1", "action2"],
    "explore_new_domain": null
}}
"""

    user_message = f"DOMAIN DATA:\n{json.dumps(domain_summaries, indent=2)}"

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = create_message(
            client,
            model=MODELS["question_generator"],  # Haiku — cheap routing decision
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        log_cost(
            MODELS["question_generator"],
            response.usage.input_tokens,
            response.usage.output_tokens,
            "orchestrator",
            "system",
        )

        raw = response.content[0].text.strip()
        result = extract_json(raw, expected_keys={"allocation", "reasoning"})
        
        if result and result.get("allocation"):
            # Validate allocation totals
            allocated = sum(a.get("rounds", 0) for a in result["allocation"])
            result["total_rounds"] = allocated
            result["budget_remaining"] = budget["remaining"]
            result["health_score"] = health["health_score"]
            result["mode"] = "llm_reasoned"
            return result

    except Exception as e:
        print(f"  [ORCHESTRATOR] LLM reasoning failed: {e}")
        print(f"  [ORCHESTRATOR] Falling back to deterministic allocation")

    # Fallback to deterministic
    allocation = allocate_rounds(priorities, total_rounds)
    return {
        "allocation": [
            {"domain": a["domain"], "rounds": a["rounds"], "reason": "; ".join(a["reasons"][:2])}
            for a in allocation
        ],
        "reasoning": "Deterministic allocation based on priority scoring (LLM fallback)",
        "recommended_actions": [],
        "total_rounds": sum(a["rounds"] for a in allocation),
        "budget_remaining": budget["remaining"],
        "health_score": health["health_score"],
        "mode": "deterministic_fallback",
    }

