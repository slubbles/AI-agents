"""
Logs Review — Post-Cycle Analysis Dashboard

After Cortex runs cycles (daemon or manual), this module provides
structured review of what happened:

1. Run history: scores, costs, verdicts per domain over time
2. Score trends: improving, declining, or plateau per domain
3. Strategy changes: what evolved, was it approved/rejected/rolled back
4. Anomalies: score drops, budget spikes, error clusters
5. Verification results: what was confirmed/refuted
6. Memory health: stale claims, pruned outputs, KB changes

All data comes from existing log files — no API calls.
Designed for the architect to review after letting Cortex run autonomously.

Usage:
    python main.py --review                  # Full review across all domains
    python main.py --review --domain crypto  # Review for a specific domain
    python main.py --review-cycles 10        # Review last N daemon cycles
"""

import json
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from config import LOG_DIR, MEMORY_DIR, STRATEGY_DIR


# ============================================================
# Run Log Analysis
# ============================================================

def load_run_logs(domain: str | None = None, days: int = 30) -> list[dict]:
    """Load run log entries from JSONL files, optionally filtered by domain and age."""
    if not os.path.exists(LOG_DIR):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries = []

    log_files = []
    if domain:
        log_path = os.path.join(LOG_DIR, f"{domain}.jsonl")
        if os.path.exists(log_path):
            log_files.append((domain, log_path))
    else:
        for f in os.listdir(LOG_DIR):
            if f.endswith(".jsonl") and not f.startswith("_") and f != "costs.jsonl":
                name = f.replace(".jsonl", "")
                log_files.append((name, os.path.join(LOG_DIR, f)))

    for name, path in log_files:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ts = entry.get("timestamp", "")
                        if ts:
                            entry_time = datetime.fromisoformat(ts)
                            if entry_time.tzinfo is None:
                                entry_time = entry_time.replace(tzinfo=timezone.utc)
                            if entry_time < cutoff:
                                continue
                        entry["_domain"] = name
                        entries.append(entry)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except IOError:
            continue

    entries.sort(key=lambda e: e.get("timestamp", ""))
    return entries


def analyze_score_trends(domain: str, entries: list[dict] | None = None, window: int = 5) -> dict:
    """
    Analyze score trends for a domain using a rolling window.

    Returns trend direction, recent average, and whether performance is
    improving, declining, or stable.
    """
    if entries is None:
        entries = load_run_logs(domain)

    domain_entries = [e for e in entries if e.get("_domain") == domain]
    if not domain_entries:
        return {"trend": "no_data", "count": 0}

    scores = [e.get("score", 0) for e in domain_entries if e.get("score", 0) > 0]
    if len(scores) < window:
        return {
            "trend": "insufficient_data",
            "count": len(scores),
            "avg": round(sum(scores) / len(scores), 2) if scores else 0,
        }

    early = scores[:window]
    recent = scores[-window:]
    early_avg = sum(early) / len(early)
    recent_avg = sum(recent) / len(recent)
    delta = recent_avg - early_avg

    if delta > 0.5:
        trend = "improving"
    elif delta < -0.5:
        trend = "declining"
    else:
        trend = "stable"

    accept_rate = sum(1 for e in domain_entries if e.get("verdict") == "accept") / len(domain_entries)

    return {
        "trend": trend,
        "count": len(scores),
        "early_avg": round(early_avg, 2),
        "recent_avg": round(recent_avg, 2),
        "delta": round(delta, 2),
        "overall_avg": round(sum(scores) / len(scores), 2),
        "accept_rate": round(accept_rate, 3),
        "min": min(scores),
        "max": max(scores),
    }


# ============================================================
# Anomaly Detection
# ============================================================

def detect_anomalies(entries: list[dict]) -> list[dict]:
    """
    Detect anomalies in run history: score drops, error clusters, strategy changes.

    Returns a list of anomaly events sorted by severity.
    """
    anomalies = []

    by_domain = defaultdict(list)
    for e in entries:
        by_domain[e.get("_domain", "unknown")].append(e)

    for domain, domain_entries in by_domain.items():
        scores = [e.get("score", 0) for e in domain_entries]

        # Detect sudden score drops (3+ point drop between consecutive runs)
        for i in range(1, len(scores)):
            if scores[i - 1] - scores[i] >= 3.0 and scores[i - 1] > 0:
                anomalies.append({
                    "type": "score_drop",
                    "domain": domain,
                    "severity": "high",
                    "detail": f"Score dropped {scores[i-1]:.1f} → {scores[i]:.1f}",
                    "timestamp": domain_entries[i].get("timestamp", ""),
                })

        # Detect rejection streaks (3+ consecutive rejections)
        streak = 0
        for e in domain_entries:
            if e.get("verdict") == "reject":
                streak += 1
                if streak == 3:
                    anomalies.append({
                        "type": "rejection_streak",
                        "domain": domain,
                        "severity": "medium",
                        "detail": f"3+ consecutive rejections",
                        "timestamp": e.get("timestamp", ""),
                    })
            else:
                streak = 0

        # Detect strategy changes
        versions = set()
        for e in domain_entries:
            sv = e.get("strategy_version", "")
            if sv and sv not in versions:
                if versions:
                    anomalies.append({
                        "type": "strategy_change",
                        "domain": domain,
                        "severity": "info",
                        "detail": f"Strategy changed to {sv}",
                        "timestamp": e.get("timestamp", ""),
                    })
                versions.add(sv)

    anomalies.sort(key=lambda a: {"high": 0, "medium": 1, "info": 2}.get(a.get("severity"), 3))
    return anomalies


# ============================================================
# Daemon Cycle History
# ============================================================

def load_cycle_history(last_n: int = 20) -> list[dict]:
    """Load daemon cycle history entries."""
    history_path = os.path.join(LOG_DIR, "cycle_history.jsonl")
    if not os.path.exists(history_path):
        return []

    entries = []
    try:
        with open(history_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except IOError:
        return []

    return entries[-last_n:]


def summarize_cycles(cycles: list[dict]) -> dict:
    """Summarize daemon cycle history."""
    if not cycles:
        return {"total_cycles": 0}

    total_rounds = sum(c.get("rounds_completed", 0) for c in cycles)
    total_cost = sum(c.get("cycle_cost", 0) for c in cycles)
    scores = [c.get("avg_score", 0) for c in cycles if c.get("avg_score", 0) > 0]
    failures = sum(1 for c in cycles if c.get("status") == "failure")

    all_domains = set()
    for c in cycles:
        for dr in c.get("domain_results", []):
            all_domains.add(dr.get("domain", "?"))

    return {
        "total_cycles": len(cycles),
        "total_rounds": total_rounds,
        "total_cost": round(total_cost, 4),
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "failures": failures,
        "success_rate": round((len(cycles) - failures) / len(cycles), 3) if cycles else 0,
        "domains_touched": sorted(all_domains),
        "first_cycle": cycles[0].get("started_at", "?"),
        "last_cycle": cycles[-1].get("started_at", "?"),
    }


# ============================================================
# Cost Analysis
# ============================================================

def analyze_costs(days: int = 7) -> dict:
    """Analyze cost patterns from the cost log."""
    cost_log = os.path.join(LOG_DIR, "costs.jsonl")
    if not os.path.exists(cost_log):
        return {"total": 0, "by_day": {}, "by_agent": {}, "by_domain": {}}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    by_day = defaultdict(float)
    by_agent = defaultdict(float)
    by_domain = defaultdict(float)
    total = 0.0

    try:
        with open(cost_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    date_str = entry.get("date", "")
                    if date_str < cutoff:
                        continue
                    cost = entry.get("estimated_cost_usd", 0)
                    total += cost
                    by_day[date_str] += cost
                    by_agent[entry.get("agent_role", "unknown")] += cost
                    by_domain[entry.get("domain", "unknown")] += cost
                except (json.JSONDecodeError, KeyError):
                    continue
    except IOError:
        pass

    return {
        "total": round(total, 4),
        "by_day": {k: round(v, 4) for k, v in sorted(by_day.items())},
        "by_agent": {k: round(v, 4) for k, v in sorted(by_agent.items(), key=lambda x: -x[1])},
        "by_domain": {k: round(v, 4) for k, v in sorted(by_domain.items(), key=lambda x: -x[1])},
    }


# ============================================================
# Error Log Analysis
# ============================================================

def load_errors(days: int = 7) -> list[dict]:
    """Load recent errors from the error log."""
    error_log = os.path.join(LOG_DIR, "errors.jsonl")
    if not os.path.exists(error_log):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    errors = []

    try:
        with open(error_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")
                    if ts:
                        entry_time = datetime.fromisoformat(ts)
                        if entry_time.tzinfo is None:
                            entry_time = entry_time.replace(tzinfo=timezone.utc)
                        if entry_time < cutoff:
                            continue
                    errors.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue
    except IOError:
        pass

    return errors


# ============================================================
# Full Review
# ============================================================

def generate_review(domain: str | None = None, days: int = 30) -> dict:
    """
    Generate a comprehensive review of system activity.

    This is the main entry point for post-cycle analysis.
    """
    entries = load_run_logs(domain, days=days)

    domains_seen = sorted(set(e.get("_domain", "unknown") for e in entries))

    domain_trends = {}
    for d in domains_seen:
        domain_trends[d] = analyze_score_trends(d, entries)

    anomalies = detect_anomalies(entries)
    cycles = load_cycle_history(last_n=50)
    cycle_summary = summarize_cycles(cycles)
    costs = analyze_costs(days=days)
    errors = load_errors(days=days)

    # Verification stats per domain
    verification_stats = {}
    for d in domains_seen:
        try:
            from agents.claim_verifier import get_claim_verification_stats
            stats = get_claim_verification_stats(d)
            if stats.get("total_active", 0) > 0:
                verification_stats[d] = stats
        except Exception:
            pass

    # Calibration summary
    calibration = {}
    try:
        from domain_calibration import get_domain_difficulty
        for d in domains_seen:
            diff = get_domain_difficulty(d)
            if diff.get("difficulty") != "unknown":
                calibration[d] = diff
    except Exception:
        pass

    return {
        "period_days": days,
        "domain_filter": domain,
        "total_runs": len(entries),
        "domains": domains_seen,
        "trends": domain_trends,
        "anomalies": anomalies,
        "daemon_cycles": cycle_summary,
        "costs": costs,
        "errors": errors[-20:],
        "error_count": len(errors),
        "verification": verification_stats,
        "calibration": calibration,
    }


def display_review(review: dict):
    """Display a formatted review to the terminal."""
    print(f"\n{'='*70}")
    print(f"  CORTEX REVIEW — Last {review['period_days']} Days")
    if review.get("domain_filter"):
        print(f"  Domain: {review['domain_filter']}")
    print(f"{'='*70}")

    # Overview
    print(f"\n  Total runs: {review['total_runs']}")
    print(f"  Domains active: {', '.join(review['domains']) if review['domains'] else 'none'}")

    # Daemon cycles
    dc = review.get("daemon_cycles", {})
    if dc.get("total_cycles", 0) > 0:
        print(f"\n  --- Daemon ---")
        print(f"  Cycles: {dc['total_cycles']} ({dc['failures']} failures)")
        print(f"  Total rounds: {dc['total_rounds']}")
        print(f"  Avg score: {dc['avg_score']}")
        print(f"  Cost: ${dc['total_cost']:.4f}")
        print(f"  Period: {dc.get('first_cycle', '?')[:10]} to {dc.get('last_cycle', '?')[:10]}")

    # Domain trends
    trends = review.get("trends", {})
    if trends:
        print(f"\n  --- Score Trends ---")
        print(f"  {'Domain':<25} {'Trend':<12} {'Avg':>5} {'Recent':>7} {'Accept%':>8} {'Runs':>5}")
        print(f"  {'─'*62}")
        for d, t in sorted(trends.items()):
            if t.get("trend") in ("no_data", "insufficient_data"):
                print(f"  {d:<25} {'(need more data)':<12}")
                continue
            icon = {"improving": "+", "declining": "-", "stable": "="}.get(t["trend"], "?")
            print(f"  {d:<25} {icon} {t['trend']:<10} {t['overall_avg']:>5.1f} "
                  f"{t['recent_avg']:>6.1f} {t['accept_rate']*100:>7.0f}% {t['count']:>5}")

    # Anomalies
    anomalies = review.get("anomalies", [])
    if anomalies:
        print(f"\n  --- Anomalies ({len(anomalies)}) ---")
        for a in anomalies[:10]:
            icon = {"high": "!!", "medium": "!", "info": "i"}.get(a["severity"], "?")
            print(f"  [{icon}] {a['domain']}: {a['detail']} ({a.get('timestamp', '?')[:10]})")

    # Costs
    costs = review.get("costs", {})
    if costs.get("total", 0) > 0:
        print(f"\n  --- Costs ---")
        print(f"  Total: ${costs['total']:.4f}")
        if costs.get("by_domain"):
            top_domains = list(costs["by_domain"].items())[:5]
            for d, c in top_domains:
                print(f"    {d}: ${c:.4f}")
        if costs.get("by_day"):
            days_list = list(costs["by_day"].items())
            if len(days_list) > 1:
                print(f"  Daily range: ${min(costs['by_day'].values()):.4f} — "
                      f"${max(costs['by_day'].values()):.4f}")

    # Errors
    error_count = review.get("error_count", 0)
    if error_count > 0:
        print(f"\n  --- Errors ({error_count}) ---")
        for err in review.get("errors", [])[-5:]:
            print(f"  [{err.get('timestamp', '?')[:16]}] {err.get('domain', '?')}: "
                  f"{err.get('error', '?')[:80]}")

    # Verification
    verification = review.get("verification", {})
    if verification:
        print(f"\n  --- Claim Verification ---")
        for d, v in sorted(verification.items()):
            verdicts = v.get("verdicts", {})
            conf = verdicts.get("confirmed", 0)
            ref = verdicts.get("refuted", 0)
            print(f"  {d}: {v['verified']}/{v['total_active']} verified "
                  f"({conf} confirmed, {ref} refuted)")

    # Calibration
    calibration = review.get("calibration", {})
    if calibration:
        print(f"\n  --- Domain Difficulty ---")
        for d, c in sorted(calibration.items()):
            print(f"  {d}: {c['difficulty']} (mean {c['mean_score']:.1f}, "
                  f"accept {c['accept_rate']:.0%})")

    print(f"\n{'='*70}\n")
