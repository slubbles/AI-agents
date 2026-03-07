"""
Strategy Impact Tracker — Post-Approval Validation & Regression Detection

Closes the gap in Guarantee #4: "Strategy evolution measurably improves the next cycle."

Problems solved:
1. After a strategy is confirmed, there's no check that it ACTUALLY improves things.
   This module tracks performance in the post-approval window and flags regressions.
2. Stale evolution entries sit as "pending" forever if a domain goes inactive.
   This module closes them after a timeout.
3. No long-term signal for "did this strategy line of evolution help or hurt?"
   This module computes a cumulative evolution impact score.

No API calls — pure data analysis on existing outputs and evolution logs.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from config import MEMORY_DIR, STRATEGY_DIR
from memory_store import load_outputs, get_stats


POST_APPROVAL_WINDOW = 10  # outputs to track after strategy is confirmed
REGRESSION_THRESHOLD = 0.15  # 15% drop from trial avg triggers regression alert
STALE_EVOLUTION_DAYS = 14  # close pending evolutions older than this


def get_strategy_impact(domain: str, agent_role: str = "researcher") -> dict:
    """
    Measure the cumulative impact of strategy evolution on a domain.

    Compares performance across strategy versions to answer: has evolution
    actually made things better?

    Returns:
        {
            versions: [{version, avg_score, count, period}...],
            trend: "improving" | "declining" | "flat" | "insufficient_data",
            total_improvement: float,  # cumulative score delta from first to latest
            best_version: str,
            worst_version: str,
        }
    """
    outputs = load_outputs(domain, min_score=0)
    if not outputs:
        return {"trend": "insufficient_data", "versions": []}

    by_version = {}
    for o in outputs:
        v = o.get("strategy_version", "default")
        if v not in by_version:
            by_version[v] = {"scores": [], "timestamps": []}
        score = o.get("overall_score", 0)
        if score > 0:
            by_version[v]["scores"].append(score)
            by_version[v]["timestamps"].append(o.get("timestamp", ""))

    versions = []
    for v, data in sorted(by_version.items(), key=lambda x: min((t for t in x[1]["timestamps"] if t), default="")):
        if not data["scores"]:
            continue
        avg = sum(data["scores"]) / len(data["scores"])
        versions.append({
            "version": v,
            "avg_score": round(avg, 2),
            "count": len(data["scores"]),
            "min": min(data["scores"]),
            "max": max(data["scores"]),
            "first_output": min(data["timestamps"]) if data["timestamps"] else "",
            "last_output": max(data["timestamps"]) if data["timestamps"] else "",
        })

    if len(versions) < 2:
        return {"trend": "insufficient_data", "versions": versions}

    first_avg = versions[0]["avg_score"]
    last_avg = versions[-1]["avg_score"]
    total_improvement = last_avg - first_avg

    best = max(versions, key=lambda v: v["avg_score"])
    worst = min(versions, key=lambda v: v["avg_score"])

    # Check if the trend is consistently improving
    deltas = []
    for i in range(1, len(versions)):
        deltas.append(versions[i]["avg_score"] - versions[i - 1]["avg_score"])

    improving_count = sum(1 for d in deltas if d > 0.3)
    declining_count = sum(1 for d in deltas if d < -0.3)

    if improving_count > declining_count and total_improvement > 0.3:
        trend = "improving"
    elif declining_count > improving_count and total_improvement < -0.3:
        trend = "declining"
    else:
        trend = "flat"

    return {
        "trend": trend,
        "versions": versions,
        "total_improvement": round(total_improvement, 2),
        "best_version": best["version"],
        "worst_version": worst["version"],
        "evolution_count": len(versions) - 1,
    }


def check_post_approval_regression(domain: str, agent_role: str = "researcher") -> dict | None:
    """
    Check if the currently active strategy is regressing compared to its trial performance.

    After a strategy is confirmed, the next POST_APPROVAL_WINDOW outputs should
    maintain or improve on the trial average. If they don't, flag a regression.

    Returns None if no regression detected, or a dict describing the regression.
    """
    from strategy_store import get_active_version, get_strategy_performance

    version = get_active_version(agent_role, domain)
    if not version or version == "default":
        return None

    perf = get_strategy_performance(domain, version)
    if perf["count"] < POST_APPROVAL_WINDOW:
        return None

    # Load evolution log to get the trial avg
    evo_log = _load_evolution_log(domain)
    trial_entry = None
    for entry in reversed(evo_log):
        if entry.get("version") == version and entry.get("outcome") == "confirmed":
            trial_entry = entry
            break

    if not trial_entry or not trial_entry.get("score_after"):
        return None

    trial_avg = trial_entry["score_after"]
    current_avg = perf["avg_score"]

    if trial_avg <= 0:
        return None

    drop = (trial_avg - current_avg) / trial_avg

    if drop > REGRESSION_THRESHOLD:
        return {
            "domain": domain,
            "version": version,
            "trial_avg": round(trial_avg, 2),
            "current_avg": round(current_avg, 2),
            "drop_pct": round(drop, 3),
            "output_count": perf["count"],
            "severity": "high" if drop > 0.25 else "medium",
            "recommendation": "Consider triggering strategy evolution or rolling back.",
        }

    return None


def close_stale_evolutions(domain: str) -> int:
    """
    Close evolution entries that have been pending for longer than STALE_EVOLUTION_DAYS.

    Returns the number of entries closed.
    """
    evo_log = _load_evolution_log(domain)
    if not evo_log:
        return 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_EVOLUTION_DAYS)).isoformat()
    closed = 0

    for entry in evo_log:
        if entry.get("outcome") == "pending":
            entry_date = entry.get("date", "")
            if entry_date and entry_date < cutoff:
                entry["outcome"] = "stale_closed"
                entry["closed_at"] = datetime.now(timezone.utc).isoformat()
                entry["close_reason"] = f"No trial activity for {STALE_EVOLUTION_DAYS}+ days"
                closed += 1

    if closed > 0:
        _save_evolution_log(domain, evo_log)

    return closed


def run_impact_check(domain: str | None = None) -> dict:
    """
    Run a full strategy impact check across one or all domains.

    Returns impact summaries and any regression alerts.
    """
    if not os.path.exists(MEMORY_DIR):
        return {"domains": [], "regressions": [], "stale_closed": 0}

    domains = []
    if domain:
        domains = [domain]
    else:
        for name in sorted(os.listdir(MEMORY_DIR)):
            if os.path.isdir(os.path.join(MEMORY_DIR, name)) and not name.startswith("_"):
                stats = get_stats(name)
                if stats.get("count", 0) >= 5:
                    domains.append(name)

    results = {"domains": [], "regressions": [], "stale_closed": 0}

    for d in domains:
        impact = get_strategy_impact(d)
        results["domains"].append({"domain": d, **impact})

        regression = check_post_approval_regression(d)
        if regression:
            results["regressions"].append(regression)

        closed = close_stale_evolutions(d)
        results["stale_closed"] += closed

    return results


def display_impact(results: dict):
    """Display strategy impact results."""
    print(f"\n{'='*60}")
    print(f"  STRATEGY IMPACT ANALYSIS")
    print(f"{'='*60}")

    for d in results["domains"]:
        if d["trend"] == "insufficient_data":
            continue

        trend_icon = {"improving": "+", "declining": "-", "flat": "="}.get(d["trend"], "?")
        print(f"\n  {d['domain']} ({trend_icon} {d['trend']})")
        print(f"    Total improvement: {d['total_improvement']:+.2f} over {d['evolution_count']} evolution(s)")
        print(f"    Best: {d['best_version']} ({d.get('versions', [{}])[-1].get('avg_score', '?')})")
        print(f"    Worst: {d['worst_version']}")

        for v in d.get("versions", []):
            marker = " *" if v["version"] == d.get("best_version") else ""
            print(f"      {v['version']:>10s}: avg {v['avg_score']:.1f}  ({v['count']} outputs){marker}")

    regressions = results.get("regressions", [])
    if regressions:
        print(f"\n  --- REGRESSIONS DETECTED ---")
        for r in regressions:
            print(f"  !! {r['domain']}: {r['version']} dropped {r['drop_pct']:.0%} "
                  f"(trial {r['trial_avg']:.1f} → current {r['current_avg']:.1f})")
            print(f"     {r['recommendation']}")

    stale = results.get("stale_closed", 0)
    if stale > 0:
        print(f"\n  Closed {stale} stale evolution entries.")

    if not results["domains"]:
        print(f"\n  No domains with enough data for impact analysis.")

    print()


# ── Internal helpers ─────────────────────────────────────────

def _load_evolution_log(domain: str) -> list[dict]:
    path = os.path.join(STRATEGY_DIR, domain, "_evolution_log.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _save_evolution_log(domain: str, log: list[dict]):
    from utils.atomic_write import atomic_json_write
    path = os.path.join(STRATEGY_DIR, domain, "_evolution_log.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_json_write(path, log)
