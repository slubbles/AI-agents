"""Infrastructure CLI commands — dashboard, export, daemon, seeds, alerts, predictions, migrate."""

import json
import os
from datetime import datetime, timezone

from config import DEFAULT_DOMAIN, LOG_DIR, MIN_OUTPUTS_FOR_SYNTHESIS
from cost_tracker import check_budget, get_daily_spend, get_all_time_spend
from memory_store import get_stats, get_archive_stats, load_outputs
from strategy_store import (
    get_active_version, get_strategy_status, get_strategy_performance,
    list_pending,
)
from agents.cross_domain import load_principles
from agents.orchestrator import get_system_health, discover_domains
from domain_seeder import get_seed_questions, has_curated_seeds, list_available_domains
from knowledge_graph import load_graph, get_graph_summary
from utils.atomic_write import atomic_json_write


def show_dashboard():
    """
    Full system dashboard — all domains, strategies, budget, health at a glance.
    No API calls — pure local data.
    """
    from memory_store import load_knowledge_base

    print(f"\n{'='*60}")
    print(f"  AGENT BRAIN — DASHBOARD")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    # ── Budget ──
    budget = check_budget()
    daily = get_daily_spend()
    alltime = get_all_time_spend()
    budget_icon = "✓" if budget["within_budget"] else "✗ EXCEEDED"
    budget_pct = min(100, (budget["spent"] / budget["limit"]) * 100) if budget["limit"] > 0 else 0
    bar_len = 20
    filled = int(bar_len * budget_pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    print(f"\n  ── Budget ──")
    print(f"  Today: ${budget['spent']:.4f} / ${budget['limit']:.2f}  [{bar}] {budget_pct:.0f}%  {budget_icon}")
    print(f"  API calls: {daily['calls']}  |  All-time: ${alltime['total_usd']:.4f} over {alltime['days']} day(s)")

    # ── Discover domains ──
    memory_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory")
    domains = []
    if os.path.exists(memory_dir):
        for d in sorted(os.listdir(memory_dir)):
            if os.path.isdir(os.path.join(memory_dir, d)) and not d.startswith("_"):
                domains.append(d)

    if not domains:
        print(f"\n  No domains found.")
        print(f"{'='*60}\n")
        return

    # ── Domain Overview Table ──
    print(f"\n  ── Domains ──")
    print(f"  {'Domain':<16} {'Outputs':>7} {'Avg':>5} {'Accept':>7} {'Rate':>6} {'Strategy':<12} {'Status':<8} {'KB':>4}")
    print(f"  {'─'*72}")

    total_outputs = 0
    total_accepted = 0
    total_rejected = 0
    all_scores = []
    domain_data = []

    for d in domains:
        stats = get_stats(d)
        archive = get_archive_stats(d)
        active_v = get_active_version("researcher", d)
        strat_status = get_strategy_status("researcher", d)
        pending = list_pending("researcher", d)
        kb = load_knowledge_base(d)

        count = stats["count"]
        avg = stats["avg_score"]
        accepted = stats["accepted"]
        rejected = stats["rejected"]
        rate = f"{(accepted / count * 100):.0f}%" if count > 0 else "—"
        kb_mark = "✓" if kb else "—"
        strat_label = active_v if active_v != "default" else "—"

        # Status decorators
        status_label = strat_status
        if pending:
            status_label += f"+{len(pending)}P"

        print(f"  {d:<16} {count:>7} {avg:>5.1f} {accepted:>4}/{rejected:<3} {rate:>5} {strat_label:<12} {status_label:<8} {kb_mark:>4}")

        total_outputs += count
        total_accepted += accepted
        total_rejected += rejected
        if count > 0:
            all_scores.extend([avg] * count)

        domain_data.append({
            "domain": d, "stats": stats, "archive": archive,
            "strategy": active_v, "status": strat_status, "pending": pending,
            "has_kb": kb is not None,
        })

    # Totals row
    overall_avg = sum(all_scores) / len(all_scores) if all_scores else 0
    overall_rate = f"{(total_accepted / total_outputs * 100):.0f}%" if total_outputs > 0 else "—"
    print(f"  {'─'*72}")
    print(f"  {'TOTAL':<16} {total_outputs:>7} {overall_avg:>5.1f} {total_accepted:>4}/{total_rejected:<3} {overall_rate:>5}")

    # ── Alerts & Recommendations ──
    alerts = []
    recommendations = []

    for dd in domain_data:
        d = dd["domain"]
        s = dd["stats"]
        # Low acceptance rate
        if s["count"] >= 3 and s["accepted"] / s["count"] < 0.5:
            alerts.append(f"⚠ {d}: acceptance rate {s['accepted']}/{s['count']} ({s['accepted']/s['count']*100:.0f}%) — strategy may need work")
        # Pending approvals
        if dd["pending"]:
            versions = ", ".join(p.get("version", "?") for p in dd["pending"])
            alerts.append(f"⏳ {d}: {len(dd['pending'])} pending strategy(ies): {versions}")
        # Trial in progress
        if dd["status"] == "trial":
            alerts.append(f"🔬 {d}: strategy {dd['strategy']} in trial")
        # Domain ready for cross-domain transfer
        if s["count"] == 0:
            recommendations.append(f"Seed '{d}' with a manual question or --transfer {d}")
        elif s["count"] < 5 and dd["strategy"] == "default":
            recommendations.append(f"'{d}' needs {5 - s['count']} more outputs for cross-domain transfer")
        # Knowledge base missing for mature domains
        if s["count"] >= 3 and s["accepted"] >= 3 and not dd["has_kb"]:
            recommendations.append(f"Run --synthesize --domain {d} (3+ accepted outputs, no KB)")

    if alerts:
        print(f"\n  ── Alerts ──")
        for a in alerts:
            print(f"  {a}")

    if recommendations:
        print(f"\n  ── Recommendations ──")
        for r in recommendations:
            print(f"  → {r}")

    # ── Cross-Domain Principles ──
    principles = load_principles()
    if principles:
        p_count = len(principles.get("principles", []))
        p_version = principles.get("version", "?")
        p_sources = ", ".join(principles.get("source_domains", []))
        print(f"\n  ── Cross-Domain Principles ──")
        print(f"  {p_count} principles (v{p_version}) from: {p_sources}")

    # ── Recent Activity ──
    print(f"\n  ── Recent Activity ──")
    recent_entries = []
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    if os.path.exists(log_dir):
        for logfile in os.listdir(log_dir):
            if logfile.endswith(".jsonl") and logfile != "costs.jsonl":
                domain_name = logfile.replace(".jsonl", "")
                filepath = os.path.join(log_dir, logfile)
                with open(filepath) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            entry["_domain"] = domain_name
                            recent_entries.append(entry)
                        except json.JSONDecodeError:
                            pass

    if recent_entries:
        recent_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        print(f"  {'Time':<20} {'Domain':<14} {'Score':>5} {'Verdict':<8} {'Question'}")
        print(f"  {'─'*72}")
        for entry in recent_entries[:10]:
            ts = entry.get("timestamp", "?")[:16].replace("T", " ")
            domain_name = entry.get("_domain", "?")
            score = entry.get("score", 0)
            verdict = entry.get("verdict", "?")
            q = entry.get("question", "?")[:30]
            print(f"  {ts:<20} {domain_name:<14} {score:>5.1f} {verdict:<8} {q}")
    else:
        print(f"  No activity logged yet.")

    print(f"\n{'='*60}\n")


def run_export(markdown: bool = False):
    """Export a comprehensive system report as JSON or Markdown."""
    from memory_store import load_knowledge_base

    now = datetime.now(timezone.utc)
    domains = discover_domains()
    health = get_system_health()
    budget = check_budget()
    daily = get_daily_spend()
    alltime = get_all_time_spend()
    principles_data = load_principles()

    report = {
        "generated_at": now.isoformat(),
        "system_health": health,
        "budget": {
            "daily_limit": budget["limit"],
            "spent_today": budget["spent"],
            "remaining_today": budget["remaining"],
            "within_budget": budget["within_budget"],
            "all_time": alltime,
        },
        "domains": {},
    }

    for domain in domains:
        stats = get_stats(domain)
        sv = get_active_version("researcher", domain)
        ss = get_strategy_status("researcher", domain)
        pending = list_pending("researcher", domain)
        perf = get_strategy_performance(domain, sv)
        kb = load_knowledge_base(domain)
        outputs = load_outputs(domain)

        # Recent outputs summary
        recent = sorted(outputs, key=lambda o: o.get("timestamp", ""), reverse=True)[:5]
        recent_summary = []
        for o in recent:
            recent_summary.append({
                "timestamp": o.get("timestamp", ""),
                "question": o.get("question", "")[:100],
                "score": o.get("overall_score", 0),
                "accepted": o.get("accepted", False),
                "strategy_version": o.get("strategy_version", ""),
            })

        report["domains"][domain] = {
            "stats": stats,
            "strategy": {
                "active_version": sv,
                "status": ss,
                "pending_count": len(pending),
                "performance": perf,
            },
            "knowledge_base": {
                "exists": kb is not None,
                "claims": len(kb.get("claims", [])) if kb else 0,
                "gaps": len(kb.get("knowledge_gaps", [])) if kb else 0,
            },
            "recent_outputs": recent_summary,
        }

    report["principles"] = {
        "count": len(principles_data.get("principles", [])) if principles_data else 0,
        "version": principles_data.get("version", 0) if principles_data else 0,
        "source_domains": principles_data.get("source_domains", []) if principles_data else [],
    }

    if markdown:
        _export_markdown(report, now)
    else:
        # JSON output
        outpath = os.path.join(LOG_DIR, f"report_{now.strftime('%Y%m%d_%H%M%S')}.json")
        atomic_json_write(outpath, report)
        print(f"Report exported to: {outpath}")
        print(f"  System health: {health['health_score']}/100")
        print(f"  Domains: {len(domains)}")
        print(f"  Total outputs: {health['total_outputs']}")
        print(f"  Acceptance rate: {health['acceptance_rate']:.0%}")


def _export_markdown(report: dict, now: datetime):
    """Generate a Markdown system report."""
    lines = []
    h = report["system_health"]
    b = report["budget"]

    lines.append(f"# Agent Brain — System Report")
    lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append(f"## System Health: {h['health_score']}/100")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Outputs | {h['total_outputs']} |")
    lines.append(f"| Accepted | {h['total_accepted']} |")
    lines.append(f"| Rejected | {h['total_rejected']} |")
    lines.append(f"| Acceptance Rate | {h['acceptance_rate']:.0%} |")
    lines.append(f"| Avg Score | {h['avg_score']} |")
    lines.append(f"| Domains | {h['domain_count']} |")
    lines.append(f"| w/ Strategy | {h['domains_with_strategy']} |")
    lines.append(f"| w/ Knowledge Base | {h['domains_with_kb']} |")
    lines.append(f"| Principles | {h['principle_count']} |")
    lines.append("")
    lines.append(f"## Budget")
    lines.append(f"- Daily limit: ${b['daily_limit']:.2f}")
    lines.append(f"- Spent today: ${b['spent_today']:.4f}")
    lines.append(f"- All-time: ${b['all_time']['total_usd']:.4f} over {b['all_time']['days']} day(s)")
    lines.append("")
    lines.append(f"## Domains")
    lines.append("")

    for domain, data in report["domains"].items():
        s = data["stats"]
        st = data["strategy"]
        kb = data["knowledge_base"]
        lines.append(f"### {domain.title()}")
        lines.append(f"- Outputs: {s['count']} (accepted: {s['accepted']}, rejected: {s['rejected']})")
        lines.append(f"- Avg Score: {s['avg_score']:.1f}")
        rate = f"{s['accepted']/s['count']*100:.0f}%" if s['count'] > 0 else "N/A"
        lines.append(f"- Acceptance Rate: {rate}")
        lines.append(f"- Strategy: {st['active_version']} ({st['status']})")
        if st['pending_count'] > 0:
            lines.append(f"- **Pending approvals: {st['pending_count']}**")
        lines.append(f"- Knowledge Base: {'Yes' if kb['exists'] else 'No'}" +
                     (f" ({kb['claims']} claims, {kb['gaps']} gaps)" if kb['exists'] else ""))
        lines.append("")

        if data["recent_outputs"]:
            lines.append(f"**Recent Activity:**")
            lines.append("")
            lines.append(f"| Time | Score | Status | Question |")
            lines.append(f"|------|-------|--------|----------|")
            for o in data["recent_outputs"]:
                t = o["timestamp"][:16] if o["timestamp"] else ""
                status = "✓" if o["accepted"] else "✗"
                lines.append(f"| {t} | {o['score']:.1f} | {status} | {o['question'][:60]} |")
            lines.append("")

    p = report["principles"]
    if p["count"] > 0:
        lines.append(f"## Cross-Domain Principles")
        lines.append(f"- {p['count']} principles (v{p['version']})")
        lines.append(f"- Source domains: {', '.join(p['source_domains'])}")

    md = "\n".join(lines)
    outpath = os.path.join(LOG_DIR, f"report_{now.strftime('%Y%m%d_%H%M%S')}.md")
    with open(outpath, "w") as f:
        f.write(md)
    print(f"Markdown report exported to: {outpath}")
    print(f"  System health: {h['health_score']}/100")


def run_daemon_mode(args):
    """Start the autonomous daemon."""
    from scheduler import run_daemon

    interval = getattr(args, 'interval', 60) or 60
    max_cycles = getattr(args, 'max_cycles', None)
    aggressive = getattr(args, 'aggressive', False)
    autonomous = getattr(args, 'autonomous', False)
    require_approval = not autonomous

    # Initialize SQLite DB on daemon startup (safe to call multiple times)
    try:
        from db import init_db
        init_db()
    except Exception as e:
        print(f"  ⚠ SQLite init warning: {e}")

    print(f"\n{'='*60}")
    print(f"  DAEMON MODE — {'Fully Autonomous' if autonomous else 'Supervised'} Operation")
    print(f"{'='*60}")
    print(f"\n  Interval: {interval} minutes")
    print(f"  Max cycles: {max_cycles or 'unlimited'}")
    print(f"  Aggressive: {aggressive}")
    if autonomous:
        print(f"  ✓ Auto-approve strategies: ON")
        print(f"  ✓ Auto-execute Hands tasks: ON")
    else:
        print(f"  ⚠ Human approval still required for strategy changes.")
    print(f"  Press Ctrl+C to stop gracefully.\n")

    run_daemon(
        interval_minutes=interval,
        rounds_per_cycle=getattr(args, 'rounds', 3) or 3,
        max_cycles=max_cycles,
        aggressive=aggressive,
        require_approval=require_approval,
    )


def show_daemon_status(status: dict):
    """Display daemon status + VPS deployment info."""
    print(f"\n{'='*60}")
    print(f"  DAEMON STATUS")
    print(f"{'='*60}")

    if not status or not status.get("running"):
        last_run = status.get("last_run", "never") if status else "never"
        print(f"\n  Status: stopped")
        print(f"  Last run: {last_run}")
    else:
        print(f"\n  Status: RUNNING")
        print(f"  Started: {status.get('started_at', 'unknown')}")
        print(f"  Cycles completed: {status.get('cycles_completed', 0)}")
        print(f"  Total rounds: {status.get('total_rounds', 0)}")
        print(f"  Last cycle: {status.get('last_cycle', 'N/A')}")

        cycle_results = status.get("cycle_results", [])
        if cycle_results:
            print(f"\n  Recent cycles:")
            for cr in cycle_results[-5:]:
                print(f"    [{cr.get('timestamp', '?')}] "
                      f"{cr.get('rounds_completed', 0)} rounds, "
                      f"avg {cr.get('avg_score', 0):.1f}")

    # VPS deploy info
    try:
        from deploy.vps_config import load_config as _load_vps_cfg
        vps = _load_vps_cfg()
        if vps.host:
            print(f"\n  VPS: {vps.user}@{vps.host}:{vps.port}")
            print(f"  Remote dir: {vps.remote_dir}")
            print(f"  Cron: {vps.schedule_cron}")
    except Exception:
        pass

    print()


def show_daemon_report():
    """
    Display comprehensive daemon health report.
    
    One command = full picture of system state:
    - Daemon status (running/stopped/idle)
    - Last N cycle summaries (from persistent cycle_history.jsonl)
    - Budget (spent, remaining, ceiling)
    - Watchdog state (circuit breaker, failures, events)
    - Domain scores (per-domain averages)
    - Sync status (Brain↔Hands alignment)
    """
    from scheduler import generate_daemon_report
    
    report = generate_daemon_report(last_n=10)
    
    print(f"\n{'='*60}")
    print(f"  DAEMON HEALTH REPORT")
    print(f"  Generated: {report['generated_at'][:19]}Z")
    print(f"{'='*60}")
    
    # 1. Daemon state
    daemon = report.get("daemon", {})
    status = daemon.get("status", "unknown")
    is_running = daemon.get("is_running", False)
    print(f"\n  ── Daemon ──")
    print(f"  Status: {'RUNNING' if is_running else status.upper()}")
    if daemon.get("last_run"):
        print(f"  Last run: {daemon['last_run'][:19]}Z")
    if daemon.get("last_completed"):
        print(f"  Last completed: {daemon['last_completed'][:19]}Z")
    if daemon.get("next_run"):
        print(f"  Next run: {daemon['next_run'][:19]}Z")
    if daemon.get("total_cycles"):
        print(f"  Total cycles: {daemon['total_cycles']}")
    
    # 2. Cycle history
    cycles = report.get("cycles", [])
    print(f"\n  ── Cycle History ({len(cycles)} recent) ──")
    if not cycles:
        print(f"  No cycle history recorded yet.")
    else:
        for c in cycles:
            ts = c.get("started_at", "?")[:19]
            cstatus = c.get("status", "?")
            if cstatus == "success":
                print(f"  [{ts}] Cycle {c.get('cycle', '?')}: "
                      f"{c.get('rounds_completed', 0)} rounds, "
                      f"avg {c.get('avg_score', 0):.1f}, "
                      f"${c.get('cycle_cost', 0):.4f}, "
                      f"{c.get('duration_seconds', 0)}s")
                domains = c.get("domain_results", [])
                for d in domains:
                    print(f"    {d.get('domain', '?')}: "
                          f"{d.get('rounds_completed', 0)} rounds, "
                          f"avg {d.get('avg_score', 0):.1f}")
            else:
                print(f"  [{ts}] Cycle {c.get('cycle', '?')}: "
                      f"FAILED — {c.get('error', 'unknown')[:60]}")
    
    # 3. Budget
    budget = report.get("budget", {})
    print(f"\n  ── Budget ──")
    if "error" in budget:
        print(f"  Error: {budget['error']}")
    else:
        spent = budget.get("spent_today", 0)
        limit = budget.get("daily_limit", 0)
        remaining = budget.get("remaining", 0)
        within = budget.get("within_budget", True)
        pct = (spent / limit * 100) if limit > 0 else 0
        bar_len = 30
        filled = int(bar_len * min(pct / 100, 1.0))
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  Spent today: ${spent:.4f} / ${limit:.2f} ({pct:.0f}%)")
        print(f"  [{bar}]")
        print(f"  Remaining: ${remaining:.4f}")
        print(f"  Status: {'OK' if within else 'EXCEEDED'}")
    
    # 4. Watchdog
    wd = report.get("watchdog", {})
    print(f"\n  ── Watchdog ──")
    if "error" in wd:
        print(f"  Error: {wd['error']}")
    else:
        print(f"  State: {wd.get('state', 'unknown')}")
        print(f"  Cycles completed: {wd.get('cycles_completed', 0)}")
        print(f"  Consecutive failures: {wd.get('consecutive_failures', 0)}")
        print(f"  Consecutive critical: {wd.get('consecutive_critical_alerts', 0)}")
        hb = wd.get("heartbeat_age_seconds")
        if hb is not None:
            print(f"  Heartbeat age: {hb:.0f}s")
        events = wd.get("recent_events", [])
        if events:
            print(f"  Recent events ({len(events)}):")
            for ev in events[-5:]:
                severity = ev.get("severity", "info")
                marker = "!" if severity == "critical" else ("~" if severity == "warning" else " ")
                print(f"   {marker} [{ev.get('timestamp', '?')[:19]}] "
                      f"{ev.get('message', '?')[:60]}")
    
    # 5. Domain scores
    domains = report.get("domains", {})
    print(f"\n  ── Domain Scores ──")
    if isinstance(domains, dict) and "error" not in domains:
        if not domains:
            print(f"  No domains found.")
        else:
            # Sort by count descending
            sorted_d = sorted(domains.items(), key=lambda x: x[1].get("count", 0), reverse=True)
            for name, info in sorted_d:
                count = info.get("count", 0)
                avg = info.get("avg_score", 0)
                latest = info.get("latest_score", 0)
                print(f"  {name:<20} {count:>3} outputs  avg {avg:.1f}  latest {latest:.1f}")
    else:
        print(f"  Error: {domains.get('error', 'unknown')}")
    
    # 6. Sync
    sync = report.get("sync", {})
    print(f"\n  ── Sync ──")
    if "error" in sync:
        print(f"  Error: {sync['error']}")
    else:
        aligned = sync.get("aligned", True)
        print(f"  Brain↔Hands: {'ALIGNED' if aligned else 'MISALIGNED'}")
        issues = sync.get("issues", [])
        if issues:
            for issue in issues[:5]:
                print(f"  ⚠ {issue}")
    
    print(f"\n{'='*60}\n")


def show_seeds(domain: str):
    """Show seed questions for a domain or list all available seed domains."""
    if domain == DEFAULT_DOMAIN:
        # Show all available seed domains
        print(f"\n{'='*60}")
        print(f"  DOMAIN SEEDS — Available Domains")
        print(f"{'='*60}")

        available = list_available_domains()
        print(f"\n  Curated seed questions available for {len(available)} domains:\n")
        for d in available:
            stats = get_stats(d)
            status = "✓ has data" if stats["count"] > 0 else "○ empty"
            questions = get_seed_questions(d, count=5)
            print(f"  {d:<16} {status}")
            print(f"    → {questions[0][:70]}...")

        print(f"\n  Any domain can also use generic seed questions.")
        print(f"  Usage: python main.py --seed --domain <domain>")
        print()
    else:
        # Show seeds for specific domain
        questions = get_seed_questions(domain, count=5)
        curated = has_curated_seeds(domain)
        stats = get_stats(domain)

        print(f"\n{'='*60}")
        print(f"  DOMAIN SEEDS — {domain}")
        print(f"{'='*60}")
        print(f"\n  Type: {'Curated' if curated else 'Generic'}")
        print(f"  Current outputs: {stats['count']}")

        print(f"\n  Seed Questions:")
        for i, q in enumerate(questions, 1):
            print(f"    {i}. {q}")

        if stats["count"] == 0:
            print(f"\n  → Orchestrator will auto-use these for bootstrapping.")
            print(f"  → Or run manually: python main.py --domain {domain} \"{questions[0]}\"")
        print()


def predictions_extract(domain: str):
    """Extract time-bound predictions from KB for later verification."""
    from agents.verifier import extract_predictions, load_predictions
    print(f"\n{'='*60}")
    print(f"  PREDICTION EXTRACTION — Domain: {domain}")
    print(f"{'='*60}\n")

    if not check_budget():
        print("  ✗ Budget exceeded. Use --budget to see details.")
        return

    new = extract_predictions(domain)
    all_preds = load_predictions(domain)

    print(f"\n  Predictions tracked: {len(all_preds)}")
    if new:
        print(f"  New this run: {len(new)}")
        for p in new[:5]:
            deadline = p.get("deadline", "?")
            print(f"    → {p.get('prediction', '?')[:70]}... (due {deadline})")
        if len(new) > 5:
            print(f"    ... and {len(new) - 5} more")
    print()


def predictions_verify(domain: str):
    """Verify past-deadline predictions against external reality."""
    from agents.verifier import verify_predictions, get_verification_stats
    print(f"\n{'='*60}")
    print(f"  PREDICTION VERIFICATION — Domain: {domain}")
    print(f"{'='*60}\n")

    if not check_budget():
        print("  ✗ Budget exceeded. Use --budget to see details.")
        return

    results = verify_predictions(domain, max_checks=5)

    if results:
        print(f"\n  Verification Summary:")
        stats = get_verification_stats(domain)
        print(f"    Total tracked: {stats['total']}")
        print(f"    Pending: {stats['pending']}")
        print(f"    Confirmed: {stats['confirmed']}")
        print(f"    Refuted: {stats['refuted']}")
        if stats.get('accuracy_rate') is not None:
            print(f"    Accuracy rate: {stats['accuracy_rate']:.1%}")
    print()


def prediction_stats(domain: str):
    """Show prediction accuracy statistics for a domain."""
    from agents.verifier import load_predictions, get_verification_stats
    from datetime import date

    print(f"\n{'='*60}")
    print(f"  PREDICTION STATS — Domain: {domain}")
    print(f"{'='*60}\n")

    predictions = load_predictions(domain)
    if not predictions:
        print("  No predictions tracked for this domain.")
        print("  Use --predictions to extract predictions from the KB.")
        print()
        return

    stats = get_verification_stats(domain)
    print(f"  Total tracked: {stats['total']}")
    print(f"  Pending: {stats['pending']}")
    print(f"  Confirmed: {stats['confirmed']}")
    print(f"  Refuted: {stats['refuted']}")
    print(f"  Partially confirmed: {stats.get('partially_confirmed', 0)}")
    print(f"  Inconclusive: {stats.get('inconclusive', 0)}")

    if stats.get('accuracy_rate') is not None:
        print(f"\n  Accuracy rate: {stats['accuracy_rate']:.1%}")
        print("  (confirmed / (confirmed + refuted))")

    # Show upcoming deadlines
    today = date.today()
    pending = [p for p in predictions if p.get('status') == 'pending']
    if pending:
        print(f"\n  Upcoming deadlines:")
        sorted_pending = sorted(pending, key=lambda x: x.get('deadline', '9999'))[:5]
        for p in sorted_pending:
            dl = p.get('deadline', '?')
            pred_text = p.get('prediction', '?')[:60]
            print(f"    {dl}: {pred_text}...")
    print()


def run_migrate():
    """Migrate JSON/JSONL data to SQLite."""
    from db import migrate_from_json
    from config import MEMORY_DIR, LOG_DIR as _LOG_DIR

    print(f"\n{'='*60}")
    print(f"  DATABASE MIGRATION — JSON → SQLite")
    print(f"{'='*60}\n")
    result = migrate_from_json(MEMORY_DIR, _LOG_DIR, verbose=True)
    print(f"\n{'='*60}\n")


def show_alerts():
    """Show monitoring alerts."""
    from db import get_alerts, get_alert_summary, acknowledge_alert

    print(f"\n{'='*60}")
    print(f"  MONITORING ALERTS")
    print(f"{'='*60}\n")

    summary = get_alert_summary()
    print(f"  Total: {summary['total']}  |  Unacknowledged: {summary['unacknowledged']}")
    if summary["by_severity"]:
        parts = [f"{k}: {v}" for k, v in summary["by_severity"].items()]
        print(f"  By severity: {', '.join(parts)}")

    alerts = get_alerts(acknowledged=False, limit=20)
    if not alerts:
        print(f"\n  No unacknowledged alerts. System is healthy.")
    else:
        print(f"\n  {'ID':>4}  {'Severity':<10} {'Type':<22} {'Domain':<12} Message")
        print(f"  {'─'*80}")
        for a in alerts:
            print(f"  {a['id']:>4}  {a['severity']:<10} {a['alert_type']:<22} {a.get('domain', ''):<12} {a['message'][:50]}")

    print(f"\n{'='*60}\n")


def run_health_check():
    """Run health checks and score trend monitoring."""
    from monitoring import run_health_check as _run_health_check

    print(f"\n{'='*60}")
    print(f"  HEALTH CHECK + MONITORING")
    print(f"{'='*60}\n")

    result = _run_health_check(verbose=True)

    print(f"\n  Status: {result['status'].upper()}")
    if result.get("alerts_generated", 0) > 0:
        print(f"  New alerts: {result['alerts_generated']}")
    print(f"\n{'='*60}\n")


def show_watchdog_status():
    """Show watchdog system status — unified view of daemon, health, budget, sync."""
    from watchdog import get_watchdog_status

    status = get_watchdog_status()

    print(f"\n{'='*60}")
    print(f"  WATCHDOG STATUS")
    print(f"{'='*60}")

    state = status.get("state", "unknown")
    state_icons = {
        "running": "✓",
        "stopped": "●",
        "paused": "⏸",
        "cooldown": "⏳",
        "circuit_open": "🚨",
        "budget_halt": "💰",
    }
    icon = state_icons.get(state, "?")

    print(f"\n  State: {icon} {state.upper()}")
    if status.get("started_at"):
        print(f"  Started: {status['started_at'][:19]} UTC")
    print(f"  Cycles: {status.get('cycles_completed', 0)}")
    print(f"  Total rounds: {status.get('total_rounds', 0)}")

    # Failure tracking
    failures = status.get("consecutive_failures", 0)
    critical = status.get("consecutive_critical_alerts", 0)
    if failures > 0 or critical > 0:
        print(f"\n  ⚠ Consecutive failures: {failures}")
        print(f"  ⚠ Consecutive critical alerts: {critical}")

    if status.get("paused_reason"):
        print(f"  Paused reason: {status['paused_reason']}")

    # Budget
    budget = status.get("budget", {})
    if "error" not in budget:
        spent = budget.get("spent_today", 0)
        limit = budget.get("daily_limit", 0)
        ceiling = budget.get("hard_ceiling", 0)
        pctg = (spent / limit * 100) if limit > 0 else 0
        bar_len = 20
        filled = min(bar_len, int(pctg / 100 * bar_len))
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\n  Budget: [{bar}] ${spent:.4f} / ${limit:.2f} ({pctg:.0f}%)")
        print(f"  Hard ceiling: ${ceiling:.2f}")
        if not budget.get("within_budget", True):
            print(f"  ⚠ OVER BUDGET")

    # Health
    health = status.get("health", {})
    if "error" not in health:
        health_score = health.get("health_score", 0)
        print(f"\n  System health: {health_score}/100")

    # Recent events
    events = status.get("recent_events", [])
    if events:
        print(f"\n  Recent Events ({len(events)}):")
        for e in events[-5:]:
            ts = e.get("timestamp", "")[:19]
            sev = e.get("severity", "info")
            sev_icon = {"critical": "🚨", "warning": "⚠", "info": "·"}.get(sev, "·")
            print(f"    {sev_icon} [{ts}] {e.get('message', '')[:70]}")

    print(f"\n{'='*60}\n")


def show_sync_status():
    """Show Brain↔Hands sync status."""
    from sync import check_sync, get_task_stats

    print(f"\n{'='*60}")
    print(f"  BRAIN ↔ HANDS SYNC")
    print(f"{'='*60}")

    result = check_sync()

    aligned = result.get("aligned", False)
    icon = "✓" if aligned else "✗"
    print(f"\n  Status: {icon} {'ALIGNED' if aligned else 'ISSUES DETECTED'}")

    # Brain health
    brain = result.get("brain_health", {})
    brain_ok = brain.get("healthy", False)
    print(f"\n  Brain: {'✓ healthy' if brain_ok else '✗ ISSUES'}")
    if not brain_ok:
        for issue in brain.get("issues", []):
            print(f"    ⚠ {issue}")

    # Hands health
    hands = result.get("hands_health", {})
    hands_ok = hands.get("healthy", False)
    print(f"  Hands: {'✓ healthy' if hands_ok else '✗ ISSUES'}")
    if not hands_ok:
        for issue in hands.get("issues", []):
            print(f"    ⚠ {issue}")

    # Task queue
    stats = result.get("task_stats", {})
    if stats.get("total", 0) > 0:
        print(f"\n  Task Queue:")
        print(f"    Pending: {stats.get('pending', 0)}")
        print(f"    In Progress: {stats.get('in_progress', 0)}")
        print(f"    Completed: {stats.get('completed', 0)}")
        print(f"    Failed: {stats.get('failed', 0)}")
        print(f"    Stale: {stats.get('stale', 0)}")
    else:
        print(f"\n  Task Queue: empty (no tasks created yet)")

    stale = result.get("stale_tasks_flagged", 0)
    if stale > 0:
        print(f"\n  ⚠ {stale} tasks newly marked stale")

    # Issues
    issues = result.get("issues", [])
    if issues:
        print(f"\n  Issues ({len(issues)}):")
        for issue in issues:
            print(f"    ✗ {issue}")

    # Recommendations
    recs = result.get("recommendations", [])
    if recs:
        print(f"\n  Recommendations ({len(recs)}):")
        for rec in recs:
            print(f"    → {rec}")

    print(f"\n{'='*60}\n")
