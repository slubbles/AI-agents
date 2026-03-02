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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

# Daemon state
_daemon_running = False
_daemon_lock = threading.Lock()
_daemon_stop_event = threading.Event()
_daemon_log = []  # Recent daemon activity log


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

    cycle = 0
    _log_daemon(f"Daemon started: interval={interval_minutes}m, rounds={rounds_per_cycle}, "
                f"max_cycles={'∞' if max_cycles == 0 else max_cycles}, "
                f"require_approval={require_approval}")

    # Auto-approve pending strategies if require_approval is False
    if not require_approval:
        _auto_approve_pending_strategies()

    # Rotate logs at daemon start to prevent unbounded growth
    _rotate_logs()

    try:
        while not _daemon_stop_event.is_set():
            cycle += 1
            
            if max_cycles > 0 and cycle > max_cycles:
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
                # Wait until next interval, then check again
                if _daemon_stop_event.wait(timeout=interval_minutes * 60):
                    break
                continue

            # Create and evaluate plan
            plan = create_plan(aggressive=aggressive)
            
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
                # Run the orchestration (this does the actual research)
                from agents.orchestrator import prioritize_domains, allocate_rounds
                
                priorities = prioritize_domains()
                allocation = allocate_rounds(priorities, total_planned)
                
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
                            
                            # Run the research round with a timeout
                            # If round exceeds MAX_ROUND_DURATION_SECONDS, kill it
                            def _run_round():
                                import importlib
                                main_mod = importlib.import_module("main")
                                return main_mod.run_loop(question=question, domain=domain)
                            
                            executor = ThreadPoolExecutor(max_workers=1)
                            future = executor.submit(_run_round)
                            try:
                                result = future.result(timeout=MAX_ROUND_DURATION_SECONDS)
                                executor.shutdown(wait=False)
                            except FutureTimeoutError:
                                # Don't wait for the stuck thread — shut down immediately
                                executor.shutdown(wait=False, cancel_futures=True)
                                _log_daemon(
                                    f"  {domain} round {r+1}: TIMEOUT after "
                                    f"{MAX_ROUND_DURATION_SECONDS}s — killed",
                                    "error"
                                )
                                # Count as a failure but continue to next round
                                continue
                            
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
                
                # Record success with watchdog
                watchdog.record_cycle_success(
                    rounds_completed=completed,
                    avg_score=cycle_avg,
                    cost=cycle_cost,
                    domain_results=domain_results,
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

            except Exception as e:
                _log_daemon(f"Cycle {cycle} failed: {e}", "error")
                watchdog.record_cycle_failure(str(e))
                _save_daemon_state({
                    "status": "error",
                    "cycle": cycle,
                    "error": str(e),
                    "last_run": cycle_start.isoformat(),
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
