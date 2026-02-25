"""
Monitoring — Score Trend Detection, Health Checks, and Automated Alerts

Detects:
- Declining score trends (per domain)
- Sudden score drops (> 2 points below rolling average)
- Budget overruns approaching daily limit (>80%)
- Stale domains (no new outputs in configured period)
- High rejection rates (>50% over recent outputs)
- Strategy trial failures
- Error rate spikes

Stores alerts in SQLite via db.py. No API calls — pure computation.
"""

import os
from datetime import datetime, timezone, timedelta
from config import (
    MEMORY_DIR, LOG_DIR, QUALITY_THRESHOLD, DAILY_BUDGET_USD,
)
from memory_store import load_outputs, get_stats
from cost_tracker import get_daily_spend
from analytics import score_trajectory
from db import insert_alert, get_alerts, insert_health_snapshot


# ── Configuration ──────────────────────────────────────────────────────────

DECLINING_TREND_THRESHOLD = -0.5     # Rolling avg drop triggering alert
SUDDEN_DROP_THRESHOLD = 2.0          # Points below rolling avg for sudden drop
BUDGET_WARNING_PCTG = 0.80           # Alert when budget > 80% consumed
STALE_DOMAIN_DAYS = 14               # Days without output = stale
HIGH_REJECTION_WINDOW = 10           # Recent N outputs to check rejection rate
HIGH_REJECTION_RATE = 0.50           # >50% rejects = alert
ERROR_RATE_WINDOW_HOURS = 24         # Time window for error rate check
ERROR_RATE_THRESHOLD = 5             # >5 errors in window = alert


def _discover_domains() -> list[str]:
    """Discover all domains with outputs."""
    if not os.path.exists(MEMORY_DIR):
        return []
    domains = []
    for name in sorted(os.listdir(MEMORY_DIR)):
        path = os.path.join(MEMORY_DIR, name)
        if os.path.isdir(path) and not name.startswith("_"):
            domains.append(name)
    return domains


def check_score_trends(verbose: bool = False) -> list[dict]:
    """
    Check all domains for declining score trends.
    Returns list of alerts generated.
    """
    alerts = []
    for domain in _discover_domains():
        traj = score_trajectory(domain, window=3)
        if traj.get("trend") == "declining":
            improvement = traj.get("improvement", 0)
            msg = (
                f"Domain '{domain}' shows declining scores: "
                f"{improvement:+.2f} change over {traj['total_outputs']} outputs "
                f"(avg {traj.get('avg_score', 0):.1f})"
            )
            alert_id = insert_alert(
                alert_type="declining_scores",
                message=msg,
                severity="warning",
                domain=domain,
                details={
                    "trend": traj["trend"],
                    "improvement": improvement,
                    "total_outputs": traj["total_outputs"],
                    "avg_score": traj.get("avg_score", 0),
                    "last_score": traj.get("last_score", 0),
                },
            )
            alerts.append({"id": alert_id, "type": "declining_scores", "domain": domain, "message": msg})
            if verbose:
                print(f"  [ALERT] {msg}")
    return alerts


def check_sudden_drops(verbose: bool = False) -> list[dict]:
    """
    Check for sudden score drops — latest score significantly below rolling average.
    """
    alerts = []
    for domain in _discover_domains():
        traj = score_trajectory(domain, window=5)
        if traj.get("total_outputs", 0) < 3:
            continue

        rolling = traj.get("rolling_avg", [])
        if len(rolling) < 3:
            continue

        last_score = traj.get("last_score", 0)
        recent_avg = sum(rolling[-5:]) / len(rolling[-5:])

        drop = recent_avg - last_score
        if drop >= SUDDEN_DROP_THRESHOLD:
            msg = (
                f"Domain '{domain}': sudden score drop — "
                f"last score {last_score:.1f} vs rolling avg {recent_avg:.1f} "
                f"(drop of {drop:.1f})"
            )
            alert_id = insert_alert(
                alert_type="sudden_drop",
                message=msg,
                severity="critical",
                domain=domain,
                details={"last_score": last_score, "rolling_avg": recent_avg, "drop": drop},
            )
            alerts.append({"id": alert_id, "type": "sudden_drop", "domain": domain, "message": msg})
            if verbose:
                print(f"  [ALERT] {msg}")
    return alerts


def check_budget_warnings(verbose: bool = False) -> list[dict]:
    """Check if budget consumption is approaching the limit."""
    alerts = []
    daily = get_daily_spend()
    spent = daily.get("total_usd", 0)
    pctg = spent / DAILY_BUDGET_USD if DAILY_BUDGET_USD > 0 else 0

    if pctg >= BUDGET_WARNING_PCTG:
        remaining = DAILY_BUDGET_USD - spent
        msg = (
            f"Budget alert: ${spent:.4f} spent today "
            f"({pctg*100:.0f}% of ${DAILY_BUDGET_USD:.2f} limit, "
            f"${remaining:.4f} remaining)"
        )
        alert_id = insert_alert(
            alert_type="budget_warning",
            message=msg,
            severity="critical" if pctg >= 0.95 else "warning",
            details={"spent": spent, "limit": DAILY_BUDGET_USD, "percentage": pctg},
        )
        alerts.append({"id": alert_id, "type": "budget_warning", "message": msg})
        if verbose:
            print(f"  [ALERT] {msg}")
    return alerts


def check_stale_domains(verbose: bool = False) -> list[dict]:
    """Check for domains with no recent activity."""
    alerts = []
    now = datetime.now(timezone.utc)

    for domain in _discover_domains():
        outputs = load_outputs(domain)
        if not outputs:
            continue

        # Find most recent output
        latest_ts = max(
            (o.get("timestamp", "2000-01-01") for o in outputs),
            default="2000-01-01",
        )
        try:
            latest = datetime.fromisoformat(latest_ts)
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        age_days = (now - latest).days
        if age_days >= STALE_DOMAIN_DAYS:
            msg = (
                f"Domain '{domain}' is stale — last output was {age_days} days ago "
                f"({len(outputs)} total outputs)"
            )
            alert_id = insert_alert(
                alert_type="stale_domain",
                message=msg,
                severity="info",
                domain=domain,
                details={"days_since_last": age_days, "total_outputs": len(outputs)},
            )
            alerts.append({"id": alert_id, "type": "stale_domain", "domain": domain, "message": msg})
            if verbose:
                print(f"  [ALERT] {msg}")
    return alerts


def check_rejection_rate(verbose: bool = False) -> list[dict]:
    """Check for high rejection rates in recent outputs."""
    alerts = []
    for domain in _discover_domains():
        outputs = load_outputs(domain)
        if len(outputs) < HIGH_REJECTION_WINDOW:
            continue

        # Check most recent N
        recent = sorted(outputs, key=lambda o: o.get("timestamp", ""))[-HIGH_REJECTION_WINDOW:]
        rejected = sum(1 for o in recent if not o.get("accepted", o.get("verdict") == "accept"))
        rate = rejected / len(recent)

        if rate >= HIGH_REJECTION_RATE:
            msg = (
                f"Domain '{domain}': high rejection rate — "
                f"{rejected}/{len(recent)} recent outputs rejected ({rate*100:.0f}%)"
            )
            alert_id = insert_alert(
                alert_type="high_rejection_rate",
                message=msg,
                severity="warning",
                domain=domain,
                details={"rejected": rejected, "total": len(recent), "rate": rate},
            )
            alerts.append({"id": alert_id, "type": "high_rejection_rate", "domain": domain, "message": msg})
            if verbose:
                print(f"  [ALERT] {msg}")
    return alerts


def check_error_rate(verbose: bool = False) -> list[dict]:
    """Check for error rate spikes by reading the error log."""
    alerts = []
    import json
    error_log = os.path.join(LOG_DIR, "errors.jsonl")
    if not os.path.exists(error_log):
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ERROR_RATE_WINDOW_HOURS)).isoformat()
    recent_errors = 0

    with open(error_log) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("timestamp", "") >= cutoff:
                    recent_errors += 1
            except (json.JSONDecodeError, TypeError):
                continue

    if recent_errors >= ERROR_RATE_THRESHOLD:
        msg = f"High error rate: {recent_errors} errors in last {ERROR_RATE_WINDOW_HOURS}h"
        alert_id = insert_alert(
            alert_type="error_rate_spike",
            message=msg,
            severity="critical",
            details={"errors": recent_errors, "window_hours": ERROR_RATE_WINDOW_HOURS},
        )
        alerts.append({"id": alert_id, "type": "error_rate_spike", "message": msg})
        if verbose:
            print(f"  [ALERT] {msg}")
    return alerts


def run_health_check(verbose: bool = False) -> dict:
    """
    Run all monitoring checks and generate a health snapshot.
    
    Returns:
        {status: "healthy"|"warning"|"critical", checks: [...], alerts_generated: int}
    """
    if verbose:
        print("  Running health checks...\n")

    all_alerts = []

    # Run all checks
    checks = [
        ("score_trends", check_score_trends),
        ("sudden_drops", check_sudden_drops),
        ("budget", check_budget_warnings),
        ("stale_domains", check_stale_domains),
        ("rejection_rate", check_rejection_rate),
        ("error_rate", check_error_rate),
    ]

    check_results = []
    for name, check_fn in checks:
        try:
            alerts = check_fn(verbose=verbose)
            all_alerts.extend(alerts)
            check_results.append({
                "name": name,
                "status": "ok" if not alerts else "alert",
                "alerts": len(alerts),
            })
            if verbose:
                status = "✓" if not alerts else f"✗ {len(alerts)} alert(s)"
                print(f"  {name}: {status}")
        except Exception as e:
            check_results.append({
                "name": name,
                "status": "error",
                "error": str(e),
            })
            if verbose:
                print(f"  {name}: ERROR — {e}")

    # Determine overall status
    severities = [a.get("severity", "info") for a in all_alerts if isinstance(a, dict)]
    # Get severity from the alerts we generated (from DB)
    has_critical = any(
        a.get("type") in ("sudden_drop", "error_rate_spike", "loop_crash") or
        a.get("severity") == "critical"
        for a in all_alerts
    )
    has_warning = len(all_alerts) > 0

    if has_critical:
        status = "critical"
    elif has_warning:
        status = "warning"
    else:
        status = "healthy"

    # Store health snapshot
    snapshot = {
        "status": status,
        "checks": check_results,
        "alerts_generated": len(all_alerts),
        "domains_checked": len(_discover_domains()),
    }
    insert_health_snapshot(status, snapshot)

    return snapshot
