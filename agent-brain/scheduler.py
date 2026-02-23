"""
Smart Scheduler — Adaptive Round Planning

Decides HOW MANY rounds to run and WHERE, based on:
  1. Budget remaining (don't blow it all at once)
  2. Domain maturity (diminishing returns on saturated domains)
  3. Strategy lifecycle (trials need data, pending blocks work)
  4. Time-of-day efficiency (spread budget across hours)
  5. Historical cost-per-output (some domains are more expensive)

Usage (via main.py):
    python main.py --plan             # Show recommended plan without running
    python main.py --run-plan         # Execute the recommended plan
    python main.py --run-plan --aggressive  # Use more budget per cycle
"""

import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from config import DAILY_BUDGET_USD, MEMORY_DIR, LOG_DIR
from cost_tracker import check_budget, get_daily_spend
from memory_store import get_stats, load_knowledge_base
from strategy_store import (
    get_active_version, get_strategy_status, list_pending,
)
from agents.orchestrator import discover_domains, prioritize_domains, allocate_rounds
from agents.cross_domain import load_principles
from domain_seeder import has_curated_seeds, list_available_domains


# ============================================================
# Cost Estimation
# ============================================================

def _estimate_cost_per_round(domain: str) -> float:
    """
    Estimate cost per research round for a domain based on history.
    
    Reads cost log to find average cost per round in this domain.
    Falls back to system-wide average, then to a conservative estimate.
    """
    cost_file = os.path.join(LOG_DIR, "costs.jsonl")
    if not os.path.exists(cost_file):
        return 0.10  # Conservative fallback
    
    domain_costs = []
    all_costs = []
    
    try:
        with open(cost_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    cost = entry.get("estimated_cost_usd", 0)
                    all_costs.append(cost)
                    # Researcher + critic costs are the main per-round cost
                    if entry.get("agent_role") in ("researcher", "critic", "question_generator"):
                        agent_domain = entry.get("domain", "")
                        if agent_domain == domain:
                            domain_costs.append(cost)
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception:
        return 0.10
    
    if domain_costs:
        # Group into approximate rounds (researcher + critic + qgen = ~3-5 calls per round)
        total_domain_cost = sum(domain_costs)
        stats = get_stats(domain)
        output_count = stats["count"]
        if output_count > 0:
            return total_domain_cost / output_count
    
    if all_costs:
        # System average
        total = sum(all_costs)
        domains = discover_domains()
        total_outputs = sum(get_stats(d)["count"] for d in domains)
        if total_outputs > 0:
            return total / total_outputs
    
    return 0.10  # Conservative fallback


def estimate_total_cost(rounds_by_domain: dict[str, int]) -> float:
    """Estimate total cost for a planned set of rounds."""
    total = 0.0
    for domain, rounds in rounds_by_domain.items():
        cost_per = _estimate_cost_per_round(domain)
        total += cost_per * rounds
    return total


# ============================================================
# Smart Planning
# ============================================================

def create_plan(aggressive: bool = False, reserve_pct: float = 0.20) -> dict:
    """
    Create an optimal research plan for the remaining budget.
    
    Args:
        aggressive: If True, use more budget per cycle (lower reserve)
        reserve_pct: Fraction of remaining budget to reserve (0.20 = keep 20%)
    
    Returns:
        Plan dict with rounds, estimated costs, and rationale
    """
    budget = check_budget()
    remaining = budget["remaining"]
    
    if not budget["within_budget"]:
        return {
            "executable": False,
            "reason": f"Budget exceeded: ${budget['spent']:.2f}/${budget['limit']:.2f}",
            "allocation": [],
            "estimated_cost": 0,
            "budget_remaining": 0,
        }
    
    # How much to spend this cycle
    if aggressive:
        spend_target = remaining * 0.80  # Use 80%, keep 20% reserve
        reserve_pct = 0.20
    else:
        spend_target = remaining * (1 - reserve_pct)  # Default: use 80%
    
    if spend_target < 0.05:
        return {
            "executable": False,
            "reason": f"Insufficient budget: ${remaining:.2f} remaining (need at least $0.05)",
            "allocation": [],
            "estimated_cost": 0,
            "budget_remaining": remaining,
        }
    
    # Get priorities
    priorities = prioritize_domains()
    if not priorities:
        return {
            "executable": False,
            "reason": "No domains found",
            "allocation": [],
            "estimated_cost": 0,
            "budget_remaining": remaining,
        }
    
    # Estimate costs per round per domain
    cost_estimates = {}
    for p in priorities:
        domain = p["domain"]
        cost_estimates[domain] = _estimate_cost_per_round(domain)
    
    # Estimate how many total rounds we can afford
    active_costs = [c for c in cost_estimates.values() if c > 0]
    avg_cost = sum(active_costs) / len(active_costs) if active_costs else 0.10
    max_affordable_rounds = max(1, int(spend_target / avg_cost))
    
    # Cap total rounds (don't go crazy)
    cap = 15 if aggressive else 10
    total_rounds = min(max_affordable_rounds, cap)
    
    # Allocate using orchestrator logic
    allocation = allocate_rounds(priorities, total_rounds)
    
    # Estimate total cost
    rounds_by_domain = {a["domain"]: a["rounds"] for a in allocation}
    estimated_cost = estimate_total_cost(rounds_by_domain)
    
    # Safety: if estimated cost exceeds spend target, reduce rounds
    while estimated_cost > spend_target and total_rounds > 1:
        total_rounds -= 1
        allocation = allocate_rounds(priorities, total_rounds)
        rounds_by_domain = {a["domain"]: a["rounds"] for a in allocation}
        estimated_cost = estimate_total_cost(rounds_by_domain)
    
    # Build plan detail
    plan_details = []
    for a in allocation:
        domain = a["domain"]
        stats = a["stats"]
        cost_est = _estimate_cost_per_round(domain) * a["rounds"]
        
        plan_details.append({
            "domain": domain,
            "rounds": a["rounds"],
            "estimated_cost": round(cost_est, 4),
            "current_outputs": stats["count"],
            "current_accepted": stats["accepted"],
            "strategy": a["strategy"],
            "strategy_status": a["strategy_status"],
            "reasons": a["reasons"],
        })
    
    # Identify blocked domains
    blocked = []
    for p in priorities:
        if p["skip"]:
            blocked.append({
                "domain": p["domain"],
                "reasons": p["reasons"],
            })
    
    # Identify seedable domains (have curated seeds but no data)
    seedable = []
    for domain in list_available_domains():
        if domain not in [a["domain"] for a in allocation]:
            if has_curated_seeds(domain):
                stats = get_stats(domain)
                if stats["count"] == 0:
                    seedable.append(domain)
    
    return {
        "executable": len(plan_details) > 0,
        "reason": "Plan ready" if plan_details else "No actionable domains",
        "allocation": plan_details,
        "blocked": blocked,
        "seedable_domains": seedable,
        "total_rounds": sum(a["rounds"] for a in plan_details),
        "estimated_cost": round(estimated_cost, 4),
        "budget_remaining": round(remaining, 4),
        "budget_after": round(remaining - estimated_cost, 4),
        "aggressive": aggressive,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# Recommendations Engine
# ============================================================

def get_recommendations() -> list[dict]:
    """
    Generate prioritized recommendations for the system.
    
    Returns list of {priority, category, message, action} dicts.
    """
    recs = []
    
    domains = discover_domains()
    budget = check_budget()
    
    # Budget recommendations
    if budget["remaining"] < 0.50:
        recs.append({
            "priority": "critical",
            "category": "budget",
            "message": f"Low budget: ${budget['remaining']:.2f} remaining",
            "action": "Consider increasing DAILY_BUDGET_USD or waiting until tomorrow",
        })
    elif budget["remaining"] < 1.00:
        recs.append({
            "priority": "warning",
            "category": "budget",
            "message": f"Budget running low: ${budget['remaining']:.2f} remaining",
            "action": "Limit to 2-3 more rounds",
        })
    
    # Strategy recommendations
    for d in domains:
        pending = list_pending("researcher", d)
        if pending:
            versions = ", ".join(p.get("version", "?") for p in pending)
            recs.append({
                "priority": "high",
                "category": "strategy",
                "message": f"[{d}] Pending strategy approval: {versions}",
                "action": f"Run: python main.py --approve {pending[0].get('version', '?')} --domain {d}",
            })
        
        status = get_strategy_status("researcher", d)
        if status == "trial":
            version = get_active_version("researcher", d)
            stats = get_stats(d)
            recs.append({
                "priority": "medium",
                "category": "strategy",
                "message": f"[{d}] Strategy {version} in trial ({stats['count']} outputs so far)",
                "action": f"Run more rounds to evaluate trial strategy",
            })
    
    # Domain health
    for d in domains:
        stats = get_stats(d)
        if stats["count"] == 0:
            recs.append({
                "priority": "medium",
                "category": "domain",
                "message": f"[{d}] Empty domain — no research outputs",
                "action": f"Run: python main.py --domain {d} 'your question' OR --auto --domain {d}",
            })
        elif stats["count"] > 0 and stats["accepted"] / stats["count"] < 0.3:
            recs.append({
                "priority": "high",
                "category": "domain",
                "message": f"[{d}] Very low acceptance rate ({stats['accepted']}/{stats['count']} = {stats['accepted']/stats['count']:.0%})",
                "action": "Review strategy or question quality for this domain",
            })
    
    # Knowledge base gaps
    for d in domains:
        stats = get_stats(d)
        kb = load_knowledge_base(d)
        if stats["accepted"] >= 3 and kb is None:
            recs.append({
                "priority": "medium",
                "category": "knowledge",
                "message": f"[{d}] {stats['accepted']} accepted outputs but no knowledge base",
                "action": f"Run: python main.py --synthesize --domain {d}",
            })
    
    # Cross-domain transfer
    principles = load_principles()
    principle_count = len(principles.get("principles", [])) if principles else 0
    if principle_count == 0 and len(domains) >= 2:
        recs.append({
            "priority": "low",
            "category": "transfer",
            "message": "No cross-domain principles extracted yet",
            "action": "Run: python main.py --principles --extract",
        })
    
    # New domain suggestions
    seedable = []
    for domain in list_available_domains():
        stats = get_stats(domain)
        if stats["count"] == 0 and has_curated_seeds(domain):
            seedable.append(domain)
    if seedable:
        recs.append({
            "priority": "low",
            "category": "expansion",
            "message": f"Unexplored domains with curated seeds: {', '.join(seedable)}",
            "action": f"Run: python main.py --orchestrate --target-domains {','.join(seedable[:3])} --rounds {len(seedable[:3])}",
        })
    
    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "warning": 2, "medium": 3, "low": 4}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 5))
    
    return recs


# ============================================================
# Display Functions
# ============================================================

def display_plan(plan: dict):
    """Display a research plan in formatted output."""
    print(f"\n{'='*60}")
    print(f"  RESEARCH PLAN")
    print(f"  {plan.get('timestamp', 'now')[:19]} UTC")
    print(f"{'='*60}")
    
    if not plan["executable"]:
        print(f"\n  ✗ {plan['reason']}")
        return
    
    mode = "AGGRESSIVE" if plan.get("aggressive") else "CONSERVATIVE"
    print(f"\n  Mode: {mode}")
    print(f"  Budget: ${plan['budget_remaining']:.2f} remaining")
    print(f"  Estimated cost: ${plan['estimated_cost']:.4f}")
    print(f"  Budget after: ${plan['budget_after']:.2f}")
    print(f"  Total rounds: {plan['total_rounds']}")
    
    print(f"\n  ── Allocation ──")
    print(f"  {'Domain':<16} {'Rounds':>6} {'Est.$':>7} {'Outputs':>7} {'Acc':>4} {'Strategy':<10} {'Status'}")
    print(f"  {'─'*70}")
    for a in plan["allocation"]:
        print(f"  {a['domain']:<16} {a['rounds']:>6} ${a['estimated_cost']:>5.3f} "
              f"{a['current_outputs']:>7} {a['current_accepted']:>4} "
              f"{a['strategy']:<10} {a['strategy_status']}")
    
    if plan.get("blocked"):
        print(f"\n  ── Blocked Domains ──")
        for b in plan["blocked"]:
            print(f"  ⚠ {b['domain']}: {'; '.join(b['reasons'])}")
    
    if plan.get("seedable_domains"):
        print(f"\n  ── New Domains Available ──")
        print(f"  Seeds ready: {', '.join(plan['seedable_domains'])}")
        print(f"  These will auto-seed when orchestrated.")
    
    print(f"\n  To execute: python main.py --run-plan" + 
          (" --aggressive" if plan.get("aggressive") else ""))
    print(f"{'='*60}\n")


def display_recommendations(recs: list[dict]):
    """Display recommendations in formatted output."""
    print(f"\n{'='*60}")
    print(f"  RECOMMENDATIONS")
    print(f"{'='*60}")
    
    if not recs:
        print(f"\n  ✓ No urgent recommendations — system is healthy!")
        return
    
    icons = {
        "critical": "🚨",
        "high": "⚠",
        "warning": "⚡",
        "medium": "📌",
        "low": "💡",
    }
    
    for i, r in enumerate(recs, 1):
        icon = icons.get(r["priority"], "•")
        print(f"\n  {icon} [{r['priority'].upper()}] {r['message']}")
        print(f"     → {r['action']}")
    
    print(f"\n{'='*60}\n")
