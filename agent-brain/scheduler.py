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
from datetime import datetime, timezone, timedelta

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
from utils.atomic_write import atomic_json_write


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


# ============================================================
# Scheduler Daemon — Continuous Autonomous Operation
# ============================================================

import signal
import time
import threading

# Daemon state
_daemon_running = False
_daemon_lock = threading.Lock()
_daemon_stop_event = threading.Event()
_daemon_log = []  # Recent daemon activity log

# Cycle history file — persistent append-only log of all completed cycles
CYCLE_HISTORY_FILE = os.path.join(LOG_DIR, "cycle_history.jsonl")

# Cortex journal — persistent log of Cortex Orchestrator insights
CORTEX_JOURNAL_FILE = os.path.join(LOG_DIR, "cortex_journal.jsonl")

# Track last daily assessment date to avoid repeating
_last_daily_assessment_date: str | None = None

# Persistent cycle counter file
CYCLE_COUNTER_FILE = os.path.join(LOG_DIR, "cycle_counter.json")


def _load_cycle_counter() -> int:
    """Load the last cycle number from disk for persistence across restarts."""
    if not os.path.exists(CYCLE_COUNTER_FILE):
        return 0
    try:
        with open(CYCLE_COUNTER_FILE) as f:
            data = json.load(f)
        return data.get("cycle", 0)
    except (json.JSONDecodeError, IOError):
        return 0


def _save_cycle_counter(cycle: int):
    """Persist the current cycle number."""
    os.makedirs(LOG_DIR, exist_ok=True)
    atomic_json_write(CYCLE_COUNTER_FILE, {
        "cycle": cycle,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def _log_daemon(message: str, level: str = "info"):
    """Log a daemon message with timestamp."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    _daemon_log.append(entry)
    # Keep only last 200 entries
    if len(_daemon_log) > 200:
        _daemon_log.pop(0)
    print(f"  [{level.upper()}] {entry['timestamp'][:19]} {message}")


def _save_daemon_state(state: dict):
    """Persist daemon state for recovery and dashboard visibility."""
    state_file = os.path.join(LOG_DIR, "daemon_state.json")
    os.makedirs(LOG_DIR, exist_ok=True)
    atomic_json_write(state_file, state)


def _load_daemon_state() -> dict | None:
    """Load daemon state from disk."""
    state_file = os.path.join(LOG_DIR, "daemon_state.json")
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _append_cycle_history(record: dict):
    """
    Append a cycle summary to the persistent cycle history.
    
    One JSONL line per completed cycle — never overwritten.
    This is the persistent audit trail (vs daemon_state.json which is ephemeral).
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        with open(CYCLE_HISTORY_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except IOError as e:
        _log_daemon(f"Failed to write cycle history: {e}", "warning")


def get_cycle_history(last_n: int = 20) -> list[dict]:
    """
    Read the last N cycle records from the persistent history.
    
    Returns list of dicts, newest last.
    """
    if not os.path.exists(CYCLE_HISTORY_FILE):
        return []
    records = []
    try:
        with open(CYCLE_HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except IOError:
        return []
    return records[-last_n:]


# ============================================================
# Cortex Orchestrator Integration — Strategic Decision Layer
# ============================================================

def _append_cortex_journal(entry: dict):
    """Append an entry to the persistent Cortex journal."""
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        with open(CORTEX_JOURNAL_FILE, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except IOError as e:
        _log_daemon(f"Failed to write cortex journal: {e}", "warning")


def get_cortex_journal(last_n: int = 10) -> list[dict]:
    """Read last N entries from the Cortex journal."""
    if not os.path.exists(CORTEX_JOURNAL_FILE):
        return []
    records = []
    try:
        with open(CORTEX_JOURNAL_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except IOError:
        return []
    return records[-last_n:]


def _apply_cortex_priorities(plan: dict, cortex_plan: dict):
    """
    Adjust plan allocation based on Cortex recommendations.
    
    Strategy: Cortex focus domains get STRONG priority:
      1. Focus domains that are already in the plan get boosted (steal rounds)
      2. Focus domains NOT in the plan get INJECTED with at least 1 round
      3. Non-focus domains with only 1 round may be removed to make room
    
    This is binding, not advisory. Cortex is the strategic brain.
    """
    focus = cortex_plan.get("focus_domains", [])
    if not focus or not plan.get("allocation"):
        return

    # Filter out meta-domains that aren't real research domains.
    # Cortex LLM sometimes returns "all", "general", "system" etc.
    # These cause phantom allocations → downstream failures → watchdog cooldowns.
    real_domains = set()
    try:
        from agents.orchestrator import discover_domains
        real_domains = set(discover_domains())
    except Exception:
        pass
    if real_domains:
        focus = [d for d in focus if d in real_domains]
    else:
        # Fallback: at minimum filter obvious meta-domain names
        _META_DOMAINS = {"all", "system", "general", "none", "meta", "overall"}
        focus = [d for d in focus if d.lower() not in _META_DOMAINS]

    if not focus:
        return

    alloc = plan["allocation"]
    alloc_by_domain = {a["domain"]: a for a in alloc}
    
    # Phase 1: Inject focus domains that aren't in the plan yet
    for d in focus:
        if d not in alloc_by_domain:
            # Steal a round from the lowest-priority non-focus domain
            donors = [a for a in alloc if a["domain"] not in focus and a["rounds"] > 0]
            donors.sort(key=lambda a: a["rounds"], reverse=True)
            if donors:
                donors[0]["rounds"] -= 1
                new_entry = {
                    "domain": d,
                    "rounds": 1,
                    "estimated_cost": 0.05,
                    "current_outputs": 0,
                    "current_accepted": 0,
                    "strategy": "v001",
                    "strategy_status": "cortex_injected",
                    "reasons": ["Cortex priority: focus domain"],
                }
                alloc.append(new_entry)
                alloc_by_domain[d] = new_entry
                _log_daemon(f"Cortex injected domain '{d}' (stole round from '{donors[0]['domain']}')")
            # Remove zero-round allocations
            plan["allocation"] = [a for a in alloc if a["rounds"] > 0]
            alloc = plan["allocation"]
            alloc_by_domain = {a["domain"]: a for a in alloc}
    
    # Phase 2: Boost focus domains already in the plan
    boosted = [d for d in focus if d in alloc_by_domain]
    donors = sorted(
        [a for a in alloc if a["domain"] not in focus and a["rounds"] > 1],
        key=lambda a: a["rounds"], reverse=True
    )
    
    rounds_to_shift = min(len(boosted), len(donors))
    for i in range(rounds_to_shift):
        donors[i]["rounds"] -= 1
        alloc_by_domain[boosted[i]]["rounds"] += 1
    
    # Phase 3: If critical priority actions exist, give even more weight
    for action in cortex_plan.get("action_types", []):
        if action == "hands_build":
            # Flag that post-cycle should try Hands execution
            plan["_cortex_wants_hands"] = True
    
    # Clean up zero-round allocations
    plan["allocation"] = [a for a in plan["allocation"] if a["rounds"] > 0]
    plan["total_rounds"] = sum(a["rounds"] for a in plan["allocation"])
    
    # Phase 4: Reorder so Cortex focus domains run FIRST.
    # Without this, focus domains appended at the end get starved
    # when rounds_per_cycle caps execution before reaching them.
    focus_set = set(focus)
    plan["allocation"].sort(key=lambda a: (0 if a["domain"] in focus_set else 1))
    
    shifted = [d for d in boosted if alloc_by_domain[d]["rounds"] > 0]
    if shifted or rounds_to_shift > 0:
        _log_daemon(
            f"Cortex priorities applied: focus={focus}, "
            f"boosted={shifted}, shifted={rounds_to_shift} rounds"
        )


def cortex_plan_cycle(cycle: int, budget_remaining: float) -> dict | None:
    """
    Ask Cortex Orchestrator to plan the next daemon cycle.
    
    Calls plan_next_actions() and translates Cortex's strategic 
    recommendations into daemon-usable format.
    
    Budget-gated: skips if remaining budget < $0.20 (save budget for 
    actual research, not planning).
    
    Args:
        cycle: Current cycle number
        budget_remaining: Remaining daily budget in USD
        
    Returns:
        Dict with cortex insights, or None if skipped/failed.
        {
            "domain_priorities": ["domain1", "domain2", ...],
            "focus_domains": ["domain1"],  # Cortex-recommended focus
            "action_types": ["brain_research", "strategy_change", ...],
            "insights": ["insight1", ...],
            "interpretation": "...",
            "system_health": "healthy|warning|critical",
            "next_question": "...",
        }
    """
    # Budget gate: don't spend on planning if budget is tight
    if budget_remaining < 0.20:
        _log_daemon(f"Cortex plan skipped: budget ${budget_remaining:.2f} < $0.20", "info")
        return None
    
    try:
        from agents.cortex import plan_next_actions
        
        _log_daemon(f"Cortex planning cycle {cycle}...")
        result = plan_next_actions()
        
        if "error" in result and not result.get("interpretation"):
            _log_daemon(f"Cortex plan failed: {result['error']}", "warning")
            return None
        
        # Extract actionable info
        plan = {
            "domain_priorities": [],
            "focus_domains": [],
            "action_types": [],
            "insights": result.get("key_insights", []),
            "interpretation": result.get("interpretation", ""),
            "system_health": result.get("system_health", "unknown"),
            "next_question": result.get("next_question"),
            "risks": result.get("risks", []),
        }
        
        # Extract domain priorities from recommended actions
        for action in result.get("recommended_actions", []):
            atype = action.get("type", "")
            domain = action.get("domain", "")
            priority = action.get("priority", "medium")
            
            if atype not in plan["action_types"]:
                plan["action_types"].append(atype)
            
            if domain and domain not in plan["domain_priorities"]:
                plan["domain_priorities"].append(domain)
            
            # High/critical priority domains become focus domains
            if domain and priority in ("critical", "high") and domain not in plan["focus_domains"]:
                plan["focus_domains"].append(domain)
        
        # Log to journal
        _append_cortex_journal({
            "type": "cycle_plan",
            "cycle": cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "focus_domains": plan["focus_domains"],
            "action_types": plan["action_types"],
            "insights_count": len(plan["insights"]),
            "system_health": plan["system_health"],
            "interpretation_preview": plan["interpretation"][:200],
        })
        
        insight_summary = "; ".join(plan["insights"][:3]) if plan["insights"] else "none"
        _log_daemon(
            f"Cortex plan: focus={plan['focus_domains'] or 'none'}, "
            f"health={plan['system_health']}, "
            f"insights={insight_summary[:80]}"
        )
        
        return plan
        
    except Exception as e:
        _log_daemon(f"Cortex plan error: {e}", "warning")
        return None


def cortex_interpret_cycle(
    cycle: int,
    domain_results: list[dict],
    cycle_avg: float,
    cycle_cost: float,
    duration_seconds: float,
) -> dict | None:
    """
    Ask Cortex to interpret cycle results and generate insights.
    
    Called after each successful cycle. Logs to cortex_journal.jsonl.
    
    Budget-gated: skips if remaining budget < $0.15.
    
    Returns:
        Cortex interpretation dict, or None if skipped/failed.
    """
    budget = check_budget()
    if budget.get("remaining", 0) < 0.15:
        _log_daemon("Cortex interpretation skipped: low budget", "info")
        return None
    
    try:
        from agents.cortex import query_orchestrator
        
        # Build a focused question about this cycle's results
        results_summary = []
        for dr in domain_results:
            d = dr.get("domain", "?")
            r = dr.get("rounds_completed", 0)
            s = dr.get("avg_score", 0)
            skipped = dr.get("skipped")
            if skipped:
                results_summary.append(f"{d}: skipped ({skipped})")
            else:
                results_summary.append(f"{d}: {r} rounds, avg {s:.1f}")
        
        question = (
            f"Cycle {cycle} just completed. Results:\n"
            f"- Rounds completed: {sum(dr.get('rounds_completed', 0) for dr in domain_results)}\n"
            f"- Average score: {cycle_avg:.1f}\n"
            f"- Cost: ${cycle_cost:.4f}\n"
            f"- Duration: {duration_seconds:.0f}s\n"
            f"- Domain results: {'; '.join(results_summary)}\n\n"
            f"What does this cycle tell us? What should change for the next cycle? "
            f"Are there patterns in which domains score well vs poorly? "
            f"Any concerns about cost efficiency or quality trends?"
        )
        
        _log_daemon(f"Cortex interpreting cycle {cycle}...")
        result = query_orchestrator(
            question,
            include_brain=True,
            include_hands=False,
            include_infra=True,
        )
        
        if "error" in result and not result.get("interpretation"):
            _log_daemon(f"Cortex interpret failed: {result['error']}", "warning")
            return None
        
        # Log to journal
        journal_entry = {
            "type": "cycle_interpretation",
            "cycle": cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle_avg": cycle_avg,
            "cycle_cost": cycle_cost,
            "domain_results": domain_results,
            "interpretation": result.get("interpretation", ""),
            "key_insights": result.get("key_insights", []),
            "recommended_actions": result.get("recommended_actions", []),
            "system_health": result.get("system_health", "unknown"),
        }
        _append_cortex_journal(journal_entry)
        
        insights = result.get("key_insights", [])
        _log_daemon(
            f"Cortex cycle {cycle} insights: "
            f"{'; '.join(insights[:2]) if insights else 'none'}"
        )
        
        return result
        
    except Exception as e:
        _log_daemon(f"Cortex interpret error: {e}", "warning")
        return None


def cortex_daily_assessment(cycle: int) -> dict | None:
    """
    Ask Cortex for a comprehensive daily system assessment.
    
    Called at most once per day (tracks date to avoid repeating).
    Produces a strategic review of the entire system.
    
    Budget-gated: skips if remaining budget < $0.25.
    
    Returns:
        Cortex assessment dict, or None if skipped/already done today.
    """
    global _last_daily_assessment_date
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Already assessed today?
    if _last_daily_assessment_date == today:
        return None
    
    # Budget gate
    budget = check_budget()
    if budget.get("remaining", 0) < 0.25:
        _log_daemon("Cortex daily assessment skipped: low budget", "info")
        return None
    
    try:
        from agents.cortex import assess_system
        
        _log_daemon(f"Cortex daily assessment starting (cycle {cycle})...")
        result = assess_system()
        
        if "error" in result and not result.get("interpretation"):
            _log_daemon(f"Cortex assessment failed: {result['error']}", "warning")
            return None
        
        _last_daily_assessment_date = today
        
        # Log to journal
        journal_entry = {
            "type": "daily_assessment",
            "date": today,
            "cycle": cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interpretation": result.get("interpretation", ""),
            "key_insights": result.get("key_insights", []),
            "recommended_actions": result.get("recommended_actions", []),
            "risks": result.get("risks", []),
            "system_health": result.get("system_health", "unknown"),
        }
        _append_cortex_journal(journal_entry)
        
        health = result.get("system_health", "unknown")
        insights = result.get("key_insights", [])
        risks = result.get("risks", [])
        _log_daemon(
            f"Cortex daily assessment: health={health}, "
            f"{len(insights)} insights, {len(risks)} risks"
        )
        
        return result
        
    except Exception as e:
        _log_daemon(f"Cortex assessment error: {e}", "warning")
        return None


def generate_daemon_report(last_n: int = 10) -> dict:
    """
    Generate a comprehensive daemon health report.
    
    Combines:
    - Current daemon state (running/stopped/etc)
    - Last N cycle summaries from persistent history
    - Budget status
    - Watchdog state + recent events
    - Domain score averages
    - Sync status
    
    This is the "one command = full picture" output.
    """
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "daemon": {},
        "cycles": [],
        "budget": {},
        "watchdog": {},
        "domains": {},
        "sync": {},
        "cortex": {},
    }
    
    # 1. Daemon state
    state = _load_daemon_state()
    report["daemon"] = state or {"status": "no_state_file"}
    report["daemon"]["is_running"] = _daemon_running
    
    # 2. Cycle history
    report["cycles"] = get_cycle_history(last_n)
    
    # 3. Budget status
    try:
        from cost_tracker import get_daily_spend, check_budget
        daily = get_daily_spend()
        budget = check_budget()
        report["budget"] = {
            "spent_today": daily.get("total_usd", 0),
            "daily_limit": DAILY_BUDGET_USD,
            "remaining": budget.get("remaining", 0),
            "within_budget": budget.get("within_budget", True),
        }
    except Exception as e:
        report["budget"] = {"error": str(e)}
    
    # 4. Watchdog status
    try:
        from watchdog import get_watchdog_status
        report["watchdog"] = get_watchdog_status()
    except Exception as e:
        report["watchdog"] = {"error": str(e)}
    
    # 5. Domain scores
    try:
        from agents.orchestrator import discover_domains
        domains = discover_domains()
        for domain in domains:
            stats = get_stats(domain)
            report["domains"][domain] = {
                "count": stats.get("count", 0),
                "avg_score": stats.get("avg_score", 0),
                "latest_score": stats.get("latest_score", 0),
            }
    except Exception as e:
        report["domains"] = {"error": str(e)}
    
    # 6. Sync status
    try:
        from sync import check_sync
        report["sync"] = check_sync()
    except Exception as e:
        report["sync"] = {"error": str(e)}
    
    # 7. Cortex journal (latest insights)
    try:
        journal = get_cortex_journal(last_n=5)
        report["cortex"] = {
            "recent_entries": journal,
            "total_entries": len(get_cortex_journal(last_n=9999)),
            "last_assessment_date": _last_daily_assessment_date,
        }
    except Exception as e:
        report["cortex"] = {"error": str(e)}
    
    return report


def get_daemon_status() -> dict:
    """Get current daemon status (for dashboard API)."""
    state = _load_daemon_state()
    return {
        "running": _daemon_running,
        "state": state,
        "recent_log": _daemon_log[-20:],
    }


# ============================================================
# Strategy Auto-Approval (for fully autonomous mode)
# ============================================================

def _auto_approve_pending_strategies():
    """
    Auto-approve all pending strategies across all agents and domains.
    
    Called when require_approval=False. In fully autonomous mode,
    the daemon can't wait for a human to --approve strategies.
    Strategies still go through trial before becoming active.
    """
    from strategy_store import list_pending as _list_pending, approve_strategy
    from agents.orchestrator import discover_domains as _discover
    
    agent_roles = ["researcher"]  # Only researcher strategies evolve currently
    domains = _discover()
    if not domains:
        return
    
    approved = 0
    for agent in agent_roles:
        for domain in domains:
            try:
                pending = _list_pending(agent, domain)
            except Exception as e:
                _log_daemon(f"Error listing pending strategies for {agent}/{domain}: {e}", "warning")
                continue
            for entry in pending:
                version = entry.get("version", "")
                if not version:
                    continue
                try:
                    result = approve_strategy(agent, domain, version)
                    if result.get("action") == "approved":
                        approved += 1
                        _log_daemon(
                            f"Auto-approved strategy {version} for {agent}/{domain}",
                            "info"
                        )
                    else:
                        _log_daemon(
                            f"Could not auto-approve {version}: {result.get('reason', '?')}",
                            "warning"
                        )
                except Exception as e:
                    _log_daemon(f"Failed to auto-approve {version}: {e}", "warning")
    
    if approved > 0:
        _log_daemon(f"Auto-approved {approved} pending strategy(ies)")


# ============================================================
# Hands Auto-Execution — Daemon dispatches sync tasks to Hands
# ============================================================

# Max hands tasks to execute per daemon cycle
MAX_HANDS_TASKS_PER_CYCLE = 2
# Max seconds for a single hands task
HANDS_TASK_TIMEOUT = 300


def _execute_hands_tasks(cycle: int, budget_remaining: float) -> list[dict]:
    """
    Pick up pending sync tasks and execute them via Hands.
    
    Budget-gated: skips if remaining budget < $0.30.
    Only executes critical/high priority tasks automatically.
    
    Args:
        cycle: Current cycle number
        budget_remaining: Remaining daily budget
        
    Returns:
        List of execution result dicts
    """
    if budget_remaining < 0.30:
        _log_daemon("Hands auto-exec skipped: budget too low", "info")
        return []
    
    try:
        from sync import get_pending_tasks, update_task
        
        # Only execute critical and high priority tasks autonomously
        tasks = get_pending_tasks(limit=MAX_HANDS_TASKS_PER_CYCLE)
        actionable = [t for t in tasks if t.get("priority") in ("critical", "high")]
        
        if not actionable:
            return []
        
        _log_daemon(f"Hands auto-exec: {len(actionable)} task(s) to execute")
        results = []
        
        for task in actionable:
            task_id = task["id"]
            title = task.get("title", "unknown")
            description = task.get("description", "")
            domain = task.get("source_domain", "general")
            task_type = task.get("task_type", "action")
            
            # Auto-execute build, action, and deploy types
            if task_type not in ("build", "action", "deploy"):
                _log_daemon(f"Hands skipping task {task_id}: type={task_type}", "info")
                continue
            
            _log_daemon(f"Hands executing: {title[:80]}...")
            update_task(task_id, "in_progress")
            
            try:
                # Run Hands execution in a thread with timeout
                _exec_result = [None]
                _exec_error = [None]
                
                def _run_hands_task():
                    try:
                        from hands.planner import plan as create_plan_hands
                        from hands.executor import execute_plan
                        from hands.validator import validate_execution
                        from hands.tools.registry import create_default_registry
                        from hands.exec_memory import save_exec_output
                        from strategy_store import get_strategy
                        import config as _cfg
                        
                        # Set up workspace
                        workspace_dir = os.path.join(
                            os.path.dirname(__file__), "output", domain
                        )
                        os.makedirs(workspace_dir, exist_ok=True)
                        
                        # Allow workspace dir for file operations
                        if _cfg.EXEC_ALLOWED_DIRS is None:
                            _cfg.EXEC_ALLOWED_DIRS = [workspace_dir]
                        elif workspace_dir not in _cfg.EXEC_ALLOWED_DIRS:
                            _cfg.EXEC_ALLOWED_DIRS = list(_cfg.EXEC_ALLOWED_DIRS) + [workspace_dir]
                        
                        # Create tool registry + plan
                        registry = create_default_registry()
                        tools_desc = registry.get_tool_descriptions()
                        
                        strategy, strategy_version = get_strategy("executor", domain)
                        
                        goal = f"{title}: {description}"
                        
                        # Fetch research context from Cortex (Brain→Hands bridge)
                        _research_context = ""
                        try:
                            from agents.cortex import query_knowledge
                            _research_context = query_knowledge(domain, goal)
                        except Exception:
                            pass  # Don't block execution if context fetch fails
                        
                        exec_plan = create_plan_hands(
                            goal=goal,
                            tools_description=tools_desc,
                            domain=domain,
                            execution_strategy=strategy or "",
                            workspace_dir=workspace_dir,
                        )
                        
                        if not exec_plan:
                            _exec_result[0] = {
                                "success": False,
                                "error": "Planning failed",
                            }
                            return
                        
                        # Execute
                        result = execute_plan(
                            plan=exec_plan,
                            registry=registry,
                            domain=domain,
                            execution_strategy=strategy or "",
                            workspace_dir=workspace_dir,
                            research_context=_research_context,
                            page_type="app",  # Default to app; future: detect from task
                            visual_context=goal,  # Use task goal as visual context
                        )
                        
                        # Validate execution quality
                        from memory_store import load_knowledge_base
                        domain_knowledge = ""
                        try:
                            kb = load_knowledge_base(domain)
                            if kb and kb.get("claims"):
                                domain_knowledge = "\n".join(
                                    f"- {c.get('claim', '')}" for c in kb["claims"][:15]
                                )
                        except Exception:
                            pass
                        
                        validation = validate_execution(
                            goal=goal,
                            plan=exec_plan,
                            execution_report=result,
                            domain=domain,
                            domain_knowledge=domain_knowledge,
                        )
                        
                        # Store result with proper params
                        save_exec_output(
                            domain=domain,
                            goal=goal,
                            plan=exec_plan,
                            execution_report=result,
                            validation=validation,
                            attempt=1,
                            strategy_version=strategy_version or "none",
                        )
                        
                        # Attach validation to result for upstream consumers
                        result["validation"] = validation
                        _exec_result[0] = result
                        
                    except Exception as exc:
                        _exec_error[0] = exc
                
                hands_thread = threading.Thread(
                    target=_run_hands_task, daemon=True
                )
                hands_thread.start()
                hands_thread.join(timeout=HANDS_TASK_TIMEOUT)
                
                if hands_thread.is_alive():
                    _log_daemon(f"Hands task {task_id}: TIMEOUT after {HANDS_TASK_TIMEOUT}s", "error")
                    update_task(task_id, "failed", {"error": "timeout"})
                    results.append({"task_id": task_id, "success": False, "error": "timeout"})
                    continue
                
                if _exec_error[0]:
                    raise _exec_error[0]
                
                result = _exec_result[0] or {"success": False, "error": "no result"}
                success = result.get("success", False)
                
                update_task(task_id, "completed" if success else "failed", result)
                _log_daemon(
                    f"Hands task {task_id}: {'SUCCESS' if success else 'FAILED'} — {title[:60]}",
                    "info" if success else "warning"
                )
                results.append({"task_id": task_id, "success": success, "title": title})
                
                # Report to Cortex pipeline
                try:
                    from agents.cortex import report_build_complete
                    report_build_complete(
                        domain=domain,
                        task_id=task_id,
                        success=success,
                        url=result.get("url", ""),
                        total_cost=result.get("total_cost", 0.0),
                        total_steps=len(result.get("step_results", [])),
                        error=result.get("error", ""),
                    )
                except Exception:
                    pass  # Cortex reporting should never block execution
                
            except Exception as e:
                _log_daemon(f"Hands task {task_id} error: {e}", "error")
                update_task(task_id, "failed", {"error": str(e)})
                results.append({"task_id": task_id, "success": False, "error": str(e)})
                
                # Report failure to Cortex pipeline
                try:
                    from agents.cortex import report_build_complete
                    report_build_complete(
                        domain=domain,
                        task_id=task_id,
                        success=False,
                        error=str(e),
                    )
                except Exception:
                    pass
        
        return results
        
    except Exception as e:
        _log_daemon(f"Hands auto-exec error: {e}", "warning")
        return []


# ============================================================
# Log Rotation — Prevent unbounded growth during 24/7 operation
# ============================================================

# Maximum size for a single JSONL log file before rotation (5 MB)
LOG_MAX_SIZE_BYTES = 5 * 1024 * 1024
# Maximum number of rotated archives to keep per log file
LOG_MAX_ROTATIONS = 3


def _rotate_logs():
    """
    Rotate JSONL log files that exceed LOG_MAX_SIZE_BYTES.
    
    Rotation scheme:
      costs.jsonl → costs.jsonl.1 → costs.jsonl.2 → costs.jsonl.3 (deleted)
    
    Called at daemon start and between cycles.
    Keeps the 3 most recent rotations. Older ones are deleted.
    """
    if not os.path.exists(LOG_DIR):
        return
    
    rotated = 0
    try:
        for fname in os.listdir(LOG_DIR):
            fpath = os.path.join(LOG_DIR, fname)
            # Only rotate .jsonl files (not .json state files)
            if not fname.endswith(".jsonl") or not os.path.isfile(fpath):
                continue
            
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue
            
            if size < LOG_MAX_SIZE_BYTES:
                continue
            
            # Shift existing rotations: .3 → delete, .2 → .3, .1 → .2
            for i in range(LOG_MAX_ROTATIONS, 0, -1):
                old = f"{fpath}.{i}"
                new = f"{fpath}.{i + 1}" if i < LOG_MAX_ROTATIONS else None
                if os.path.exists(old):
                    if new:
                        os.replace(old, new)
                    else:
                        os.remove(old)
            
            # Current → .1
            os.replace(fpath, f"{fpath}.1")
            rotated += 1
    except OSError as e:
        _log_daemon(f"Log rotation error: {e}", "warning")
    
    if rotated > 0:
        _log_daemon(f"Rotated {rotated} log file(s)")


def run_daemon(
    interval_minutes: int = 60,
    rounds_per_cycle: int = 5,
    max_cycles: int = 0,
    aggressive: bool = False,
    require_approval: bool = True,
):
    """
    Run the scheduler as a continuous daemon.
    
    The daemon:
    1. Wakes up every interval_minutes
    2. Runs watchdog pre-cycle checks (budget ceiling, circuit breaker, cooldown)
    3. Creates an optimal research plan
    4. Executes the plan (orchestrated across domains)
    5. Runs health checks + sync verification
    6. Logs results and goes back to sleep
    7. Repeats until stopped or max_cycles reached
    
    Safety:
    - Watchdog: circuit breaker, crash recovery, hard cost ceiling
    - Budget is checked every cycle (daily limit enforced)
    - Health checks run between cycles (monitoring.py integration)
    - Brain↔Hands sync checked periodically
    - Each cycle is logged to daemon_state.json
    - SIGINT/SIGTERM triggers graceful shutdown
    - Round timeout: each round killed after MAX_ROUND_DURATION_SECONDS (watchdog.py)
    - Strategy changes require human approval unless require_approval=False
    - Maximum rounds per cycle prevents runaway
    
    Args:
        interval_minutes: Time between cycles (default: 60)
        rounds_per_cycle: Max research rounds per cycle (default: 5)
        max_cycles: Stop after N cycles (0 = run forever until stopped)
        aggressive: Use more budget per cycle
        require_approval: If True (default), new strategies need --approve.
            If False, pending strategies are auto-approved on daemon startup
            and between cycles. Use False only for fully autonomous operation.
    """
    global _daemon_running
    
    with _daemon_lock:
        if _daemon_running:
            print("  [DAEMON] Already running!")
            return
        _daemon_running = True
    
    _daemon_stop_event.clear()

    # Initialize watchdog
    from watchdog import get_watchdog
    watchdog = get_watchdog()
    watchdog.start()

    # Setup graceful shutdown
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    
    def _shutdown(signum, frame):
        _log_daemon(f"Received signal {signum} — shutting down gracefully...", "warning")
        _daemon_stop_event.set()
    
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    cycle = _load_cycle_counter()
    cycles_run = 0  # Track how many cycles THIS session has run (for max_cycles)
    _log_daemon(f"Daemon started: interval={interval_minutes}m, rounds={rounds_per_cycle}, "
                f"max_cycles={'∞' if max_cycles == 0 else max_cycles}, "
                f"require_approval={require_approval}, "
                f"resuming from cycle {cycle}")

    # Telegram alert: daemon started
    try:
        from alerts import alert_daemon_started
        _budget = check_budget()
        alert_daemon_started(interval_minutes, rounds_per_cycle,
                             max_cycles, _budget.get("remaining", 0))
    except Exception:
        pass  # alerting is best-effort

    # Auto-approve pending strategies if require_approval is False
    if not require_approval:
        _auto_approve_pending_strategies()

    # Initialize SQLite DB (safe to call multiple times)
    try:
        from db import init_db
        init_db()
        _log_daemon("Database initialized")
    except Exception as e:
        _log_daemon(f"DB init warning: {e}", "warning")

    # Rotate logs at daemon start to prevent unbounded growth
    _rotate_logs()

    try:
        while not _daemon_stop_event.is_set():
            cycle += 1
            cycles_run += 1
            _save_cycle_counter(cycle)
            
            if max_cycles > 0 and cycles_run > max_cycles:
                _log_daemon(f"Reached max cycles ({max_cycles}). Stopping.", "info")
                break

            cycle_start = datetime.now(timezone.utc)
            _log_daemon(f"=== Cycle {cycle} starting ===")

            # Watchdog pre-cycle check (circuit breaker, cooldown, cost ceiling)
            can_proceed, reason = watchdog.check_before_cycle()
            if not can_proceed:
                _log_daemon(f"Watchdog blocked cycle: {reason}", "warning")
                _save_daemon_state({
                    "status": "watchdog_blocked",
                    "cycle": cycle,
                    "last_run": cycle_start.isoformat(),
                    "reason": reason,
                })
                # Telegram alert: watchdog blocked
                try:
                    from alerts import alert_watchdog_event
                    alert_watchdog_event("watchdog_blocked", reason)
                except Exception:
                    pass
                if _daemon_stop_event.wait(timeout=interval_minutes * 60):
                    break
                continue

            watchdog.heartbeat()

            # Check budget (normal daily limit — separate from hard ceiling)
            budget = check_budget()
            if not budget["within_budget"]:
                _log_daemon(f"Budget exceeded (${budget['spent']:.2f}/${budget['limit']:.2f}). "
                           f"Waiting for budget reset.", "warning")
                _save_daemon_state({
                    "status": "waiting_budget",
                    "cycle": cycle,
                    "last_run": cycle_start.isoformat(),
                    "budget_spent": budget["spent"],
                    "budget_limit": budget["limit"],
                })
                # Telegram alert: budget halt
                try:
                    from alerts import alert_budget_halt
                    alert_budget_halt(budget["spent"], budget["limit"])
                except Exception:
                    pass
                # Wait until next interval, then check again
                if _daemon_stop_event.wait(timeout=interval_minutes * 60):
                    break
                continue

            # === Cortex pre-cycle planning (strategic layer) ===
            cortex_plan = cortex_plan_cycle(cycle, budget["remaining"])

            # Create and evaluate plan
            plan = create_plan(aggressive=aggressive)
            
            # If Cortex recommends focus domains, boost their allocation
            if cortex_plan and cortex_plan.get("focus_domains") and plan.get("executable"):
                _apply_cortex_priorities(plan, cortex_plan)

            if not plan["executable"]:
                _log_daemon(f"No executable plan: {plan['reason']}", "warning")
                _save_daemon_state({
                    "status": "no_plan",
                    "cycle": cycle,
                    "last_run": cycle_start.isoformat(),
                    "reason": plan["reason"],
                })
                if _daemon_stop_event.wait(timeout=interval_minutes * 60):
                    break
                continue

            # Cap rounds per cycle
            total_planned = min(plan["total_rounds"], rounds_per_cycle)
            _log_daemon(f"Plan: {total_planned} rounds across "
                       f"{len(plan['allocation'])} domains "
                       f"(est. ${plan['estimated_cost']:.4f})")

            # Execute the plan by importing and calling orchestrate
            # We import here to avoid circular imports
            cycle_results = {
                "status": "running",
                "cycle": cycle,
                "started_at": cycle_start.isoformat(),
                "planned_rounds": total_planned,
                "domains": [a["domain"] for a in plan["allocation"]],
            }
            _save_daemon_state(cycle_results)

            try:
                # Run the Cortex-modified plan directly.
                # Previously this re-computed allocation from scratch,
                # overriding Cortex's domain injections and round shifts.
                allocation = plan["allocation"]
                
                # Enforce rounds_per_cycle cap on the allocation.
                # Trim domains from the end so Cortex-prioritized domains
                # (sorted first by _apply_cortex_priorities) get served first.
                trimmed_alloc = []
                rounds_budget = total_planned
                for alloc_entry in allocation:
                    if rounds_budget <= 0:
                        break
                    entry_rounds = min(alloc_entry["rounds"], rounds_budget)
                    trimmed_alloc.append({**alloc_entry, "rounds": entry_rounds})
                    rounds_budget -= entry_rounds
                allocation = trimmed_alloc
                
                completed = 0
                domain_results = []
                
                # Track cycle cost by measuring daily spend before/after
                from cost_tracker import get_daily_spend
                spend_before = get_daily_spend()["total_usd"]
                
                for alloc in allocation:
                    if _daemon_stop_event.is_set():
                        _log_daemon("Stop requested during execution", "warning")
                        break
                    
                    domain = alloc["domain"]
                    rounds = alloc["rounds"]
                    _log_daemon(f"Running {rounds} round(s) in {domain}...")
                    
                    # Stall check between domains
                    stalled, stall_reason = watchdog.check_stall_and_act()
                    if stalled:
                        _log_daemon(f"Stall detected before {domain}: {stall_reason}", "warning")
                        # Check if watchdog now blocks further execution
                        can_go, block_reason = watchdog.check_before_cycle()
                        if not can_go:
                            _log_daemon(f"Watchdog blocked after stall: {block_reason}", "warning")
                            break
                        # Otherwise skip this domain and continue to next
                        domain_results.append({
                            "domain": domain,
                            "rounds_completed": 0,
                            "avg_score": 0,
                            "skipped": "stall_recovery",
                        })
                        continue
                    
                    domain_scores = []
                    for r in range(rounds):
                        if _daemon_stop_event.is_set():
                            break
                        
                        # Heartbeat — tell watchdog we're alive
                        watchdog.heartbeat()
                        
                        # Budget check each round
                        budget = check_budget()
                        if not budget["within_budget"]:
                            _log_daemon("Budget hit mid-cycle", "warning")
                            break
                        
                        try:
                            # Import late to avoid circular deps
                            from agents.question_generator import get_next_question
                            from domain_seeder import get_seed_question, has_curated_seeds
                            from watchdog import MAX_ROUND_DURATION_SECONDS
                            
                            # Generate question
                            domain_stats = get_stats(domain)
                            if domain_stats["count"] == 0:
                                question = get_seed_question(domain)
                            else:
                                question = get_next_question(domain)
                            
                            if not question:
                                _log_daemon(f"No question for {domain}, skipping", "warning")
                                break
                            
                            # Run the research round with a timeout.
                            # Use a daemon thread (not ThreadPoolExecutor) so
                            # stuck threads don't block process exit via atexit.
                            _round_result = [None]
                            _round_error = [None]

                            def _run_round():
                                try:
                                    import importlib
                                    main_mod = importlib.import_module("main")
                                    _round_result[0] = main_mod.run_loop(
                                        question=question, domain=domain)
                                except Exception as exc:
                                    _round_error[0] = exc

                            round_thread = threading.Thread(
                                target=_run_round, daemon=True)
                            round_thread.start()
                            round_thread.join(
                                timeout=MAX_ROUND_DURATION_SECONDS)

                            if round_thread.is_alive():
                                # Thread stuck — daemon flag means it won't
                                # block process exit
                                _log_daemon(
                                    f"  {domain} round {r+1}: TIMEOUT after "
                                    f"{MAX_ROUND_DURATION_SECONDS}s — killed",
                                    "error"
                                )
                                continue

                            if _round_error[0]:
                                raise _round_error[0]
                            result = _round_result[0]

                            score = result.get("critique", {}).get("overall_score", 0)
                            domain_scores.append(score)
                            completed += 1
                            _log_daemon(f"  {domain} round {r+1}: score {score}/10")
                            
                        except SystemExit:
                            _log_daemon(f"Budget exceeded in {domain}", "warning")
                            break
                        except Exception as e:
                            _log_daemon(f"Error in {domain} round {r+1}: {e}", "error")
                    
                    avg = sum(domain_scores) / len(domain_scores) if domain_scores else 0
                    domain_results.append({
                        "domain": domain,
                        "rounds_completed": len(domain_scores),
                        "avg_score": round(avg, 1),
                    })

                cycle_end = datetime.now(timezone.utc)
                duration = (cycle_end - cycle_start).total_seconds()
                
                # Compute actual cycle cost from daily spend delta
                spend_after = get_daily_spend()["total_usd"]
                cycle_cost = round(spend_after - spend_before, 4)
                
                # Calculate cycle average score
                all_scores = []
                for dr in domain_results:
                    if dr["avg_score"] > 0:
                        all_scores.extend([dr["avg_score"]] * dr["rounds_completed"])
                cycle_avg = sum(all_scores) / len(all_scores) if all_scores else 0
                
                _log_daemon(f"=== Cycle {cycle} complete: {completed} rounds, "
                           f"avg {cycle_avg:.1f}, ${cycle_cost:.4f}, "
                           f"{duration:.0f}s ===")
                
                # Record with watchdog — if zero rounds completed,
                # treat as failure so circuit breaker can accumulate
                if completed > 0:
                    watchdog.record_cycle_success(
                        rounds_completed=completed,
                        avg_score=cycle_avg,
                        cost=cycle_cost,
                        domain_results=domain_results,
                    )
                else:
                    watchdog.record_cycle_failure(
                        "Cycle completed with 0 successful rounds"
                    )
                
                _save_daemon_state({
                    "status": "idle",
                    "cycle": cycle,
                    "last_run": cycle_start.isoformat(),
                    "last_completed": cycle_end.isoformat(),
                    "duration_seconds": round(duration),
                    "rounds_completed": completed,
                    "avg_score": round(cycle_avg, 1),
                    "cycle_cost": round(cycle_cost, 4),
                    "domain_results": domain_results,
                    "next_run": (cycle_end + timedelta(
                        minutes=interval_minutes)).isoformat(),
                })
                
                # Append to persistent cycle history (never overwritten)
                _append_cycle_history({
                    "cycle": cycle,
                    "status": "success",
                    "started_at": cycle_start.isoformat(),
                    "completed_at": cycle_end.isoformat(),
                    "duration_seconds": round(duration),
                    "rounds_completed": completed,
                    "avg_score": round(cycle_avg, 1),
                    "cycle_cost": round(cycle_cost, 4),
                    "domain_results": domain_results,
                })

                # Telegram alert: cycle complete
                try:
                    from alerts import alert_cycle_complete
                    alert_cycle_complete(cycle, completed, cycle_avg,
                                         cycle_cost, duration, domain_results)
                except Exception:
                    pass

                # === Hands auto-execution (build from research) ===
                if not require_approval:
                    hands_budget = check_budget()
                    hands_results = _execute_hands_tasks(
                        cycle, hands_budget.get("remaining", 0)
                    )
                    if hands_results:
                        successes = sum(1 for r in hands_results if r.get("success"))
                        _log_daemon(
                            f"Hands auto-exec: {successes}/{len(hands_results)} tasks succeeded"
                        )

                # === Cortex post-cycle interpretation (strategic layer) ===
                cortex_interpret_cycle(
                    cycle=cycle,
                    domain_results=domain_results,
                    cycle_avg=cycle_avg,
                    cycle_cost=cycle_cost,
                    duration_seconds=duration,
                )

            except Exception as e:
                _log_daemon(f"Cycle {cycle} failed: {e}", "error")
                watchdog.record_cycle_failure(str(e))
                # Telegram alert: cycle error
                try:
                    from alerts import alert_error
                    alert_error(cycle, str(e))
                except Exception:
                    pass
                _save_daemon_state({
                    "status": "error",
                    "cycle": cycle,
                    "error": str(e),
                    "last_run": cycle_start.isoformat(),
                })
                
                # Record failure in persistent cycle history
                _append_cycle_history({
                    "cycle": cycle,
                    "status": "failure",
                    "started_at": cycle_start.isoformat(),
                    "error": str(e),
                })

            # Post-cycle: health check + sync (every cycle)
            _log_daemon("Running post-cycle health check...")
            try:
                health = watchdog.run_health_check()
                health_status = health.get("status", "unknown")
                _log_daemon(f"Health: {health_status} "
                           f"({health.get('alerts_generated', 0)} alerts)")
                
                # Check if watchdog wants to stop
                can_continue, reason = watchdog.check_before_cycle()
                if not can_continue:
                    _log_daemon(f"Watchdog says stop: {reason}", "warning")
                    # Telegram alert: circuit breaker / watchdog stop
                    try:
                        from alerts import alert_circuit_breaker
                        alert_circuit_breaker(reason)
                    except Exception:
                        pass
                    if _daemon_stop_event.wait(timeout=interval_minutes * 60):
                        break
                    continue
            except Exception as e:
                _log_daemon(f"Health check error: {e}", "warning")

            # Sync check (every 5 cycles — not every cycle to reduce noise)
            if cycle % 5 == 0:
                try:
                    from sync import check_sync
                    sync_result = check_sync()
                    if not sync_result["aligned"]:
                        _log_daemon(
                            f"Sync issues: {'; '.join(sync_result['issues'][:3])}",
                            "warning"
                        )
                    else:
                        _log_daemon("Brain↔Hands sync OK")
                except Exception as e:
                    _log_daemon(f"Sync check error: {e}", "warning")

            # Auto-approve pending strategies (every 5 cycles, if autonomous)
            if not require_approval and cycle % 5 == 0:
                _auto_approve_pending_strategies()

            # === Cortex daily assessment (strategic layer) ===
            cortex_daily_assessment(cycle)

            # Log rotation (every 10 cycles to prevent unbounded growth)
            if cycle % 10 == 0:
                _rotate_logs()

            # Wait for next cycle
            _log_daemon(f"Sleeping {interval_minutes} minutes until next cycle...")
            if _daemon_stop_event.wait(timeout=interval_minutes * 60):
                break

    finally:
        _daemon_running = False
        watchdog.stop()
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
        _log_daemon("Daemon stopped.")
        # Telegram alert: daemon stopped
        try:
            from alerts import alert_daemon_stopped
            _stop_reason = "max cycles reached" if (max_cycles > 0 and cycle > max_cycles) else "signal/stop"
            alert_daemon_stopped(cycle, _stop_reason)
        except Exception:
            pass
        # Preserve last cycle results in the stopped state
        prev_state = _load_daemon_state() or {}
        stopped_state = {
            "status": "stopped",
            "total_cycles": cycle,
            "stopped_at": datetime.now(timezone.utc).isoformat(),
        }
        # Carry forward last cycle's results for visibility
        for key in ("last_run", "last_completed", "duration_seconds",
                     "rounds_completed", "avg_score", "cycle_cost",
                     "domain_results"):
            if key in prev_state:
                stopped_state[key] = prev_state[key]
        _save_daemon_state(stopped_state)


def stop_daemon():
    """Signal the daemon to stop gracefully."""
    global _daemon_running
    if _daemon_running:
        _daemon_stop_event.set()
        _log_daemon("Stop signal sent to daemon", "warning")
        return True
    return False
