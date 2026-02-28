"""Strategy management CLI commands."""

import json
import os

from config import LOG_DIR
from cost_tracker import check_budget, get_daily_spend, get_all_time_spend
from memory_store import get_stats
from strategy_store import (
    get_strategy, get_strategy_status, get_strategy_performance,
    get_version_history, rollback as strategy_rollback,
    get_active_version, list_versions, list_pending,
    approve_strategy, reject_strategy, get_strategy_diff,
)
from agents.cross_domain import (
    extract_principles, load_principles, generate_seed_strategy,
    get_transfer_sources,
)


def show_status(domain: str):
    """Display strategy status and version performance for a domain."""
    print(f"\n{'='*60}")
    print(f"  STRATEGY STATUS \u2014 Domain: {domain}")
    print(f"{'='*60}\n")

    # Trigger migration if needed (pre-Layer 4 strategies)
    get_strategy("researcher", domain)

    active = get_active_version("researcher", domain)
    status = get_strategy_status("researcher", domain)
    versions = list_versions("researcher", domain)
    pending = list_pending("researcher", domain)

    print(f"  Active version: {active} ({status})")
    print(f"  Total versions: {len(versions)}")
    if pending:
        print(f"  \u26a0 Pending approval: {', '.join(p.get('version', '?') for p in pending)}")

    if versions:
        print(f"\n  Version Performance:")
        print(f"  {'Version':<10} {'Status':<10} {'Outputs':>8} {'Avg Score':>10} {'Accepted':>9} {'Rejected':>9}")
        print(f"  {'-'*56}")

        default_perf = get_strategy_performance(domain, "default")
        if default_perf["count"] > 0:
            print(f"  {'default':<10} {'base':<10} {default_perf['count']:>8} {default_perf['avg_score']:>10.1f} "
                  f"{default_perf['accepted']:>9} {default_perf['rejected']:>9}")

        for v in versions:
            perf = get_strategy_performance(domain, v)
            from strategy_store import load_strategy_file
            vdata = load_strategy_file("researcher", domain, v)
            vstatus = vdata.get("status", "?") if vdata else "?"
            marker = " \u2190" if v == active else ""
            print(f"  {v:<10} {vstatus:<10} {perf['count']:>8} {perf['avg_score']:>10.1f} "
                  f"{perf['accepted']:>9} {perf['rejected']:>9}{marker}")

    history = get_version_history("researcher", domain)
    if len(history) > 1:
        print(f"\n  Version History:")
        for entry in history:
            print(f"    {entry.get('version', '?')} \u2014 {entry.get('status', '?')}"
                  f" ({entry.get('replaced_at', 'current')})")

    stats = get_stats(domain)
    print(f"\n  Domain totals: {stats['count']} outputs, avg {stats['avg_score']:.1f}, "
          f"{stats['accepted']} accepted / {stats['rejected']} rejected")
    print()


def approve(domain: str, version: str):
    """Approve a pending strategy \u2192 promote to trial."""
    from strategy_store import load_strategy_file

    data = load_strategy_file("researcher", domain, version)
    if data is None:
        print(f"\n  \u2717 Strategy {version} not found in domain '{domain}'")
        return
    if data.get("status") != "pending":
        print(f"\n  \u2717 Strategy {version} is '{data.get('status')}', not 'pending'")
        return

    print(f"\n{'='*60}")
    print(f"  APPROVE STRATEGY \u2014 {version}")
    print(f"{'='*60}\n")
    print(f"  Domain:  {domain}")
    print(f"  Created: {data.get('created_at', '?')}")
    print(f"  Reason:  {data.get('reason', 'N/A')}")
    print(f"\n  Strategy preview (first 500 chars):")
    print(f"  {'-'*40}")
    strategy_text = data.get("strategy", "")
    for line in strategy_text[:500].split("\n"):
        print(f"    {line}")
    if len(strategy_text) > 500:
        print(f"    ... ({len(strategy_text) - 500} more chars)")
    print(f"  {'-'*40}")

    result = approve_strategy("researcher", domain, version)
    print(f"\n  {result['reason']}")
    print()


def reject(domain: str, version: str):
    """Reject a pending strategy."""
    result = reject_strategy("researcher", domain, version)
    if result["action"] == "error":
        print(f"\n  \u2717 {result['reason']}")
    else:
        print(f"\n  \u2713 {result['reason']}")
    print()


def diff(domain: str, v1: str, v2: str):
    """Show differences between two strategy versions."""
    d = get_strategy_diff("researcher", domain, v1, v2)

    if d.get("error"):
        print(f"\n  \u2717 {d['error']}")
        return

    a = d["version_a"]
    b = d["version_b"]

    print(f"\n{'='*60}")
    print(f"  STRATEGY DIFF \u2014 {v1} vs {v2}")
    print(f"{'='*60}\n")

    print(f"  Version A: {a['version']} (status: {a['status']}, created: {a['created_at']})")
    print(f"  Version B: {b['version']} (status: {b['status']}, created: {b['created_at']})")

    if a.get("reason"):
        print(f"\n  A reason: {a['reason'][:200]}")
    if b.get("reason"):
        print(f"  B reason: {b['reason'][:200]}")

    lines_a = a["strategy"].split("\n")
    lines_b = b["strategy"].split("\n")

    print(f"\n  --- {v1} ({len(lines_a)} lines)")
    print(f"  +++ {v2} ({len(lines_b)} lines)")
    print()

    set_a = set(lines_a)
    set_b = set(lines_b)
    removed = [l for l in lines_a if l not in set_b and l.strip()]
    added = [l for l in lines_b if l not in set_a and l.strip()]

    if removed:
        print(f"  Removed from {v1}:")
        for line in removed[:20]:
            print(f"    - {line}")
    if added:
        print(f"\n  Added in {v2}:")
        for line in added[:20]:
            print(f"    + {line}")
    if not removed and not added:
        print(f"  (strategies are identical)")
    print()


def rollback(domain: str):
    """Manually roll back to previous strategy version."""
    current = get_active_version("researcher", domain)
    print(f"\n  Current strategy: {current}")

    rolled_to = strategy_rollback("researcher", domain)
    if rolled_to:
        print(f"  \u2713 Rolled back to: {rolled_to}")
    else:
        print(f"  \u2717 No previous version to roll back to")
    print()


def audit(domain: str):
    """Show a unified audit trail of all system activity for a domain."""
    print(f"\n{'='*60}")
    print(f"  AUDIT TRAIL \u2014 Domain: {domain}")
    print(f"{'='*60}\n")

    log_file = os.path.join(LOG_DIR, f"{domain}.jsonl")
    if os.path.exists(log_file):
        print(f"  Run History:")
        print(f"  {'Time':<22} {'Score':>6} {'Verdict':<8} {'Strategy':<10} {'Question'}")
        print(f"  {'-'*80}")
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp", "?")[:19].replace("T", " ")
                score = entry.get("score", 0)
                verdict = entry.get("verdict", "?")
                sv = entry.get("strategy_version", "?")
                q = entry.get("question", "?")[:40]
                print(f"  {ts:<22} {score:>6.1f} {verdict:<8} {sv:<10} {q}")
    else:
        print(f"  No run history for domain '{domain}'")

    print(f"\n  Strategy Changes:")
    history = get_version_history("researcher", domain)
    if history:
        for entry in history:
            print(f"    {entry.get('version', '?')} \u2014 {entry.get('status', '?')}"
                  f" ({entry.get('replaced_at', 'current')})")
    else:
        print(f"    (no strategy changes)")

    pending = list_pending("researcher", domain)
    if pending:
        print(f"\n  \u26a0 Pending Approval:")
        for p in pending:
            print(f"    {p.get('version', '?')} \u2014 created {p.get('created_at', '?')[:19]}")
            reason = p.get("reason", "")
            if reason:
                print(f"      Reason: {reason[:100]}")
    else:
        print(f"\n  No pending strategies")

    daily = get_daily_spend()
    print(f"\n  Today's Spend: ${daily['total_usd']:.4f} ({daily['calls']} API calls)")
    for role, cost in daily.get("by_agent", {}).items():
        print(f"    {role}: ${cost:.4f}")

    stats = get_stats(domain)
    print(f"\n  Domain Totals: {stats['count']} outputs, avg {stats['avg_score']:.1f}, "
          f"{stats['accepted']} accepted / {stats['rejected']} rejected")
    print()


def budget():
    """Show cost tracking and budget status."""
    from config import DAILY_BUDGET_USD

    b = check_budget()
    daily = get_daily_spend()
    alltime = get_all_time_spend()

    print(f"\n{'='*60}")
    print(f"  BUDGET & COST TRACKING")
    print(f"{'='*60}\n")

    status_icon = "\u2713" if b["within_budget"] else "\u2717 EXCEEDED"
    print(f"  Today ({daily['date']}):")
    print(f"    Status:    {status_icon}")
    print(f"    Spent:     ${b['spent']:.4f}")
    print(f"    Limit:     ${b['limit']:.2f}")
    print(f"    Remaining: ${b['remaining']:.4f}")
    print(f"    API calls: {daily['calls']}")

    if daily.get("by_agent"):
        print(f"\n    By agent:")
        for role, cost in sorted(daily["by_agent"].items()):
            print(f"      {role:<15} ${cost:.4f}")

    if daily.get("by_model"):
        print(f"\n    By model:")
        for model, cost in sorted(daily["by_model"].items()):
            short = model.split("-")[1] if "-" in model else model
            print(f"      {short:<15} ${cost:.4f}")

    if alltime["days"] > 0:
        print(f"\n  All time:")
        print(f"    Total:     ${alltime['total_usd']:.4f}")
        print(f"    Days:      {alltime['days']}")
        print(f"    Avg/day:   ${alltime['total_usd'] / alltime['days']:.4f}")
        if alltime.get("by_date"):
            print(f"\n    Daily breakdown:")
            for date_str, cost in alltime["by_date"].items():
                print(f"      {date_str}  ${cost:.4f}")
    print()


def principles(force_extract: bool = False):
    """Show current general principles, optionally re-extracting them."""
    print(f"\n{'='*60}")
    print(f"  CROSS-DOMAIN PRINCIPLES")
    print(f"{'='*60}\n")

    if force_extract:
        result = extract_principles(force=True)
        if not result:
            print("  No qualifying domains for principle extraction.")
            return
    else:
        result = load_principles()
        if not result:
            print("  No principles extracted yet. Attempting extraction...\n")
            result = extract_principles()
            if not result:
                print("  No qualifying domains for principle extraction.")
                return

    print(f"  Version: {result.get('version', '?')}")
    print(f"  Extracted: {result.get('extracted_at', '?')[:19]}")
    print(f"  Source domains: {', '.join(result.get('source_domains', []))}")

    ps = result.get("principles", [])
    print(f"\n  General Principles ({len(ps)}):")
    for i, p in enumerate(ps, 1):
        conf = p.get('confidence', '?')
        cat = p.get('category', '?')
        print(f"\n    {i}. [{conf.upper()}] {p.get('principle', '?')}")
        print(f"       Category: {cat}")
        print(f"       Evidence: {p.get('evidence', 'N/A')}")
        print(f"       From: {', '.join(p.get('source_domains', []))}")

    dsi = result.get("domain_specific_insights", [])
    if dsi:
        print(f"\n  Domain-Specific Insights (not transferred):")
        for d in dsi:
            print(f"    [{d.get('domain', '?')}] {d.get('insight', '?')}")
            print(f"      Why not general: {d.get('not_transferable_because', '?')}")

    meta = result.get("meta_observations", "")
    if meta:
        print(f"\n  Meta observations: {meta}")

    sources = get_transfer_sources()
    print(f"\n  Transfer sources available: {len(sources)}")
    for s in sources:
        print(f"    {s['domain']}: {s['stats']['count']} outputs, avg {s['stats']['avg_score']:.1f}")

    print(f"\n  To seed a new domain: python main.py --transfer <domain> [--hint 'example question']")
    print()


def transfer(target_domain: str, question_hint: str = ""):
    """Generate a seed strategy for a target domain from cross-domain principles."""
    print(f"\n{'='*60}")
    print(f"  CROSS-DOMAIN TRANSFER \u2192 {target_domain}")
    print(f"{'='*60}\n")

    b = check_budget()
    if not b["within_budget"]:
        print(f"  \u2717 Budget exceeded. Use --budget to see details.")
        return

    ps = load_principles()
    if not ps:
        print("  No principles yet. Extracting from qualifying domains...\n")
        ps = extract_principles()
        if not ps:
            print("  \u2717 No qualifying domains. Need \u22655 outputs with avg score \u22655.5 and an active strategy.")
            return

    result = generate_seed_strategy(target_domain, question_hint)
    if result:
        print(f"\n  \u2713 Seed strategy {result['version']} created for '{target_domain}' (PENDING)")
        if result.get("expected_improvement"):
            print(f"  Expected improvement: {result['expected_improvement']}")
    else:
        print(f"  \u2717 Failed to generate seed strategy")
    print()
