"""
Agent Brain — Main Loop Runner

Usage:
    python main.py "What is the current state of autonomous AI agents?"
    python main.py --domain crypto "What are the latest Bitcoin ETF developments?"

Control commands:
    python main.py --status                     Show strategy status + performance
    python main.py --audit                      Full audit trail of all activity
    python main.py --approve v004               Approve a pending strategy for trial
    python main.py --reject v004                Reject a pending strategy
    python main.py --diff v001 v003             Compare two strategy versions
    python main.py --rollback                   Roll back to previous strategy
    python main.py --budget                     Show cost tracking / budget status
    python main.py --evolve                     Force strategy evolution
    python main.py --principles                  Show/extract general cross-domain principles
    python main.py --transfer ai                 Seed a new domain with cross-domain principles
    python main.py --next                        Show next self-generated questions for a domain
    python main.py --auto                        Self-directed mode: generate question + research it
    python main.py --auto --rounds 5             Self-directed mode: run 5 rounds
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from agents.researcher import research
from agents.critic import critique
from agents.meta_analyst import analyze_and_evolve, MIN_OUTPUTS_FOR_ANALYSIS, EVOLVE_EVERY_N
from config import QUALITY_THRESHOLD, MAX_RETRIES, DEFAULT_DOMAIN, LOG_DIR
from memory_store import save_output, load_outputs, get_stats
from strategy_store import (
    get_strategy, get_strategy_status, evaluate_trial,
    get_strategy_performance, get_version_history, rollback,
    get_active_version, list_versions, list_pending,
    approve_strategy, reject_strategy, get_strategy_diff,
)
from cost_tracker import check_budget, get_daily_spend, get_all_time_spend
from agents.cross_domain import (
    extract_principles, load_principles, generate_seed_strategy,
    get_transfer_sources,
)
from agents.question_generator import generate_questions, get_next_question


def run_loop(question: str, domain: str = DEFAULT_DOMAIN) -> dict:
    """
    Execute the full research → critique → quality gate loop.
    
    1. Check budget — refuse to run if daily limit exceeded
    2. Load strategy for researcher (if exists)
    3. Researcher produces findings
    4. Critic scores findings
    5. If score < threshold: retry with critique feedback (up to MAX_RETRIES)
    6. Store final output to memory
    """
    # Budget check
    budget = check_budget()
    if not budget["within_budget"]:
        print(f"\n[BUDGET] ✗ BLOCKED — Daily spend ${budget['spent']:.4f} exceeds limit ${budget['limit']:.2f}")
        print(f"  Use --budget to see details. Increase DAILY_BUDGET_USD in config.py to override.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  AGENT BRAIN — Research Loop")
    print(f"  Domain: {domain}")
    print(f"  Question: {question}")
    print(f"  Budget: ${budget['remaining']:.4f} remaining today")
    print(f"{'='*60}\n")

    # Load current strategy
    strategy, strategy_version = get_strategy("researcher", domain)
    if strategy:
        status = get_strategy_status("researcher", domain)
        status_label = " (TRIAL)" if status == "trial" else ""
        print(f"[STRATEGY] Loaded version: {strategy_version}{status_label}")
    else:
        print(f"[STRATEGY] Using default (no custom strategy yet)")
        # Auto-suggest cross-domain transfer if principles exist
        principles = load_principles()
        if principles and principles.get("principles"):
            print(f"[CROSS-DOMAIN] 💡 General principles available from {len(principles.get('source_domains', []))} domain(s)")
            print(f"  Seed this domain: python main.py --transfer {domain} --hint \"{question[:50]}\"")

    attempt = 0
    previous_critique_feedback = None
    final_research = None
    final_critique = None

    while attempt <= MAX_RETRIES:
        attempt += 1
        print(f"\n--- Attempt {attempt}/{MAX_RETRIES + 1} ---\n")

        # Step 1: Research
        print("[RESEARCHER] Generating findings...")
        research_output = research(
            question=question,
            strategy=strategy,
            critique=previous_critique_feedback,
        )

        findings_count = len(research_output.get("findings", []))
        print(f"[RESEARCHER] Produced {findings_count} findings")

        if research_output.get("_parse_error"):
            print("[RESEARCHER] ⚠ Output wasn't structured JSON — wrapped as raw")

        # Step 2: Critique
        print("[CRITIC] Evaluating findings...")
        critique_output = critique(research_output)

        score = critique_output.get("overall_score", 0)
        verdict = critique_output.get("verdict", "unknown")
        print(f"[CRITIC] Score: {score}/10 — Verdict: {verdict}")

        # Print score breakdown
        scores = critique_output.get("scores", {})
        if scores:
            for dim, val in scores.items():
                print(f"         {dim}: {val}/10")

        # Print strengths/weaknesses
        for s in critique_output.get("strengths", []):
            print(f"  ✓ {s}")
        for w in critique_output.get("weaknesses", []):
            print(f"  ✗ {w}")

        final_research = research_output
        final_critique = critique_output

        # Step 3: Quality Gate
        if score >= QUALITY_THRESHOLD:
            print(f"\n[QUALITY GATE] ✓ ACCEPTED (score {score} ≥ {QUALITY_THRESHOLD})")
            break
        elif attempt <= MAX_RETRIES:
            feedback = critique_output.get("actionable_feedback", "Improve quality.")
            print(f"\n[QUALITY GATE] ✗ REJECTED — retrying with feedback:")
            print(f"  → {feedback}")
            previous_critique_feedback = feedback
        else:
            print(f"\n[QUALITY GATE] ✗ REJECTED — max retries reached, storing anyway")

    # Step 4: Store to memory
    filepath = save_output(
        domain=domain,
        question=question,
        research=final_research,
        critique=final_critique,
        attempt=attempt,
        strategy_version=strategy_version,
    )
    print(f"\n[MEMORY] Stored to: {filepath}")

    # Step 5: Log the full run
    log_run(domain, question, attempt, final_research, final_critique, strategy_version)

    # Show domain stats
    stats = get_stats(domain)
    print(f"\n[STATS] Domain '{domain}': {stats['count']} outputs, avg score {stats['avg_score']:.1f}, "
          f"{stats['accepted']} accepted / {stats['rejected']} rejected")

    # Step 6: Evaluate trial strategy (if one is active)
    trial_result = evaluate_trial("researcher", domain)
    if trial_result["action"] == "rollback":
        print(f"\n[SAFETY] ⚠ {trial_result['reason']}")
    elif trial_result["action"] == "confirm":
        print(f"\n[SAFETY] ✓ {trial_result['reason']}")
    elif trial_result["action"] == "continue_trial":
        print(f"\n[SAFETY] ⏳ {trial_result['reason']}")

    # Step 7: Meta-analysis — evolve strategy if enough data
    # SAFETY: Never evolve while a trial is still being evaluated
    current_status = get_strategy_status("researcher", domain)
    if current_status == "trial":
        print(f"\n[META-ANALYST] Skipping — trial strategy is still being evaluated")
    else:
        # Check for pending strategies waiting for approval
        pending = list_pending("researcher", domain)
        if pending:
            versions = ", ".join(p.get("version", "?") for p in pending)
            print(f"\n[META-ANALYST] Skipping — {len(pending)} pending strategy(ies) waiting for approval: {versions}")
            print(f"  Run: python main.py --domain {domain} --approve <version>")
        else:
            all_outputs = load_outputs(domain, min_score=0)
            output_count = len(all_outputs)
            if output_count >= MIN_OUTPUTS_FOR_ANALYSIS and output_count % EVOLVE_EVERY_N == 0:
                print(f"\n[META-ANALYST] Evolution trigger ({output_count} outputs, every {EVOLVE_EVERY_N}). Running strategy evolution...")
                evolution = analyze_and_evolve(domain)
                if evolution:
                    print(f"[META-ANALYST] Strategy evolved to {evolution['new_version']}")
            elif output_count < MIN_OUTPUTS_FOR_ANALYSIS:
                remaining = MIN_OUTPUTS_FOR_ANALYSIS - output_count
                print(f"\n[META-ANALYST] Need {remaining} more output(s) before strategy evolution")
            else:
                next_evolve = EVOLVE_EVERY_N - (output_count % EVOLVE_EVERY_N)
                print(f"\n[META-ANALYST] Next evolution in {next_evolve} output(s)")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Score: {final_critique.get('overall_score', 0)}/10")
    print(f"  Attempts: {attempt}")
    print(f"  Verdict: {final_critique.get('verdict', 'unknown')}")
    summary = final_research.get("summary", "No summary available")
    print(f"\n  {summary}")
    print(f"{'='*60}\n")

    return {
        "research": final_research,
        "critique": final_critique,
        "attempts": attempt,
        "stored_at": filepath,
    }


def log_run(domain: str, question: str, attempts: int, research: dict, critique: dict, strategy_version: str):
    """Append a line to the run log."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"{domain}.jsonl")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "attempts": attempts,
        "score": critique.get("overall_score", 0),
        "verdict": critique.get("verdict", "unknown"),
        "strategy_version": strategy_version,
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Agent Brain — Research Loop")
    parser.add_argument("question", nargs="?", help="The research question to investigate")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help=f"Domain context (default: {DEFAULT_DOMAIN})")

    # Control commands
    parser.add_argument("--status", action="store_true", help="Show strategy status and performance")
    parser.add_argument("--audit", action="store_true", help="Full audit trail of all activity")
    parser.add_argument("--approve", metavar="VERSION", help="Approve a pending strategy (e.g., --approve v004)")
    parser.add_argument("--reject", metavar="VERSION", help="Reject a pending strategy")
    parser.add_argument("--diff", nargs=2, metavar=("V1", "V2"), help="Compare two strategy versions (e.g., --diff v001 v003)")
    parser.add_argument("--rollback", action="store_true", help="Roll back to previous strategy version")
    parser.add_argument("--budget", action="store_true", help="Show cost tracking and budget status")
    parser.add_argument("--evolve", action="store_true", help="Run meta-analyst strategy evolution (no research)")
    parser.add_argument("--principles", action="store_true", help="Show/extract general cross-domain principles")
    parser.add_argument("--extract", action="store_true", help="Force re-extraction of principles (use with --principles)")
    parser.add_argument("--transfer", metavar="DOMAIN", help="Seed a domain with cross-domain principles")
    parser.add_argument("--hint", default="", help="Example question to tailor transfer strategy (use with --transfer)")
    parser.add_argument("--next", action="store_true", help="Show next self-generated questions for a domain")
    parser.add_argument("--auto", action="store_true", help="Self-directed mode: generate question and research it")
    parser.add_argument("--rounds", type=int, default=1, help="Number of auto rounds to run (default: 1)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY environment variable first.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Dispatch control commands
    if args.status:
        _show_status(args.domain)
        return
    if args.audit:
        _show_audit(args.domain)
        return
    if args.approve:
        _do_approve(args.domain, args.approve)
        return
    if args.reject:
        _do_reject(args.domain, args.reject)
        return
    if args.diff:
        _show_diff(args.domain, args.diff[0], args.diff[1])
        return
    if args.rollback:
        _do_rollback(args.domain)
        return
    if args.budget:
        _show_budget()
        return
    if args.principles:
        _show_principles(force_extract=args.extract)
        return
    if args.transfer:
        _do_transfer(args.transfer, args.hint)
        return
    if args.next:
        _show_next(args.domain)
        return
    if args.auto:
        _run_auto(args.domain, args.rounds)
        return

    if args.evolve:
        # Manual strategy evolution trigger
        print(f"\n{'='*60}")
        print(f"  META-ANALYST — Strategy Evolution")
        print(f"  Domain: {args.domain}")
        print(f"{'='*60}\n")
        result = analyze_and_evolve(args.domain)
        if not result:
            sys.exit(1)
        return

    if not args.question:
        parser.error("question is required unless a control command is used (--status, --auto, --next, etc.)")

    run_loop(question=args.question, domain=args.domain)


def _show_status(domain: str):
    """Display strategy status and version performance for a domain."""
    print(f"\n{'='*60}")
    print(f"  STRATEGY STATUS — Domain: {domain}")
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
        print(f"  ⚠ Pending approval: {', '.join(p.get('version', '?') for p in pending)}")

    if versions:
        print(f"\n  Version Performance:")
        print(f"  {'Version':<10} {'Status':<10} {'Outputs':>8} {'Avg Score':>10} {'Accepted':>9} {'Rejected':>9}")
        print(f"  {'-'*56}")

        # Also show default performance
        default_perf = get_strategy_performance(domain, "default")
        if default_perf["count"] > 0:
            print(f"  {'default':<10} {'base':<10} {default_perf['count']:>8} {default_perf['avg_score']:>10.1f} "
                  f"{default_perf['accepted']:>9} {default_perf['rejected']:>9}")

        for v in versions:
            perf = get_strategy_performance(domain, v)
            # Get version status from file
            from strategy_store import _load_strategy_file
            vdata = _load_strategy_file("researcher", domain, v)
            vstatus = vdata.get("status", "?") if vdata else "?"
            marker = " ←" if v == active else ""
            print(f"  {v:<10} {vstatus:<10} {perf['count']:>8} {perf['avg_score']:>10.1f} "
                  f"{perf['accepted']:>9} {perf['rejected']:>9}{marker}")

    # Show version history
    history = get_version_history("researcher", domain)
    if len(history) > 1:
        print(f"\n  Version History:")
        for entry in history:
            print(f"    {entry.get('version', '?')} — {entry.get('status', '?')}"
                  f" ({entry.get('replaced_at', 'current')})")

    # Domain stats
    stats = get_stats(domain)
    print(f"\n  Domain totals: {stats['count']} outputs, avg {stats['avg_score']:.1f}, "
          f"{stats['accepted']} accepted / {stats['rejected']} rejected")
    print()


def _do_approve(domain: str, version: str):
    """Approve a pending strategy → promote to trial."""
    from strategy_store import _load_strategy_file

    # Show the strategy before approving
    data = _load_strategy_file("researcher", domain, version)
    if data is None:
        print(f"\n  ✗ Strategy {version} not found in domain '{domain}'")
        return
    if data.get("status") != "pending":
        print(f"\n  ✗ Strategy {version} is '{data.get('status')}', not 'pending'")
        return

    print(f"\n{'='*60}")
    print(f"  APPROVE STRATEGY — {version}")
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


def _do_reject(domain: str, version: str):
    """Reject a pending strategy."""
    result = reject_strategy("researcher", domain, version)
    if result["action"] == "error":
        print(f"\n  ✗ {result['reason']}")
    else:
        print(f"\n  ✓ {result['reason']}")
    print()


def _show_diff(domain: str, v1: str, v2: str):
    """Show differences between two strategy versions."""
    diff = get_strategy_diff("researcher", domain, v1, v2)

    if diff.get("error"):
        print(f"\n  ✗ {diff['error']}")
        return

    a = diff["version_a"]
    b = diff["version_b"]

    print(f"\n{'='*60}")
    print(f"  STRATEGY DIFF — {v1} vs {v2}")
    print(f"{'='*60}\n")

    print(f"  Version A: {a['version']} (status: {a['status']}, created: {a['created_at']})")
    print(f"  Version B: {b['version']} (status: {b['status']}, created: {b['created_at']})")

    if a.get("reason"):
        print(f"\n  A reason: {a['reason'][:200]}")
    if b.get("reason"):
        print(f"  B reason: {b['reason'][:200]}")

    # Simple line-by-line diff
    lines_a = a["strategy"].split("\n")
    lines_b = b["strategy"].split("\n")

    print(f"\n  --- {v1} ({len(lines_a)} lines)")
    print(f"  +++ {v2} ({len(lines_b)} lines)")
    print()

    # Show lines unique to each version
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


def _show_audit(domain: str):
    """Show a unified audit trail of all system activity for a domain."""
    print(f"\n{'='*60}")
    print(f"  AUDIT TRAIL — Domain: {domain}")
    print(f"{'='*60}\n")

    # 1. Run history from log
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

    # 2. Strategy version history
    print(f"\n  Strategy Changes:")
    history = get_version_history("researcher", domain)
    if history:
        for entry in history:
            v = entry.get("version", "?")
            s = entry.get("status", "?")
            t = entry.get("replaced_at", "current")
            if isinstance(t, str) and len(t) > 19:
                t = t[:19].replace("T", " ")
            print(f"    {t:<22} {v:<10} → {s}")
    else:
        print(f"    (no strategy changes)")

    # 3. Pending strategies
    pending = list_pending("researcher", domain)
    if pending:
        print(f"\n  ⚠ Pending Approval:")
        for p in pending:
            print(f"    {p.get('version', '?')} — created {p.get('created_at', '?')[:19]}")
            reason = p.get("reason", "")
            if reason:
                print(f"      Reason: {reason[:100]}")
    else:
        print(f"\n  No pending strategies")

    # 4. Budget summary for today
    daily = get_daily_spend()
    print(f"\n  Today's Spend: ${daily['total_usd']:.4f} ({daily['calls']} API calls)")
    for role, cost in daily.get("by_agent", {}).items():
        print(f"    {role}: ${cost:.4f}")

    # 5. Domain stats
    stats = get_stats(domain)
    print(f"\n  Domain Totals: {stats['count']} outputs, avg {stats['avg_score']:.1f}, "
          f"{stats['accepted']} accepted / {stats['rejected']} rejected")
    print()


def _show_budget():
    """Show cost tracking and budget status."""
    from config import DAILY_BUDGET_USD

    budget = check_budget()
    daily = get_daily_spend()
    alltime = get_all_time_spend()

    print(f"\n{'='*60}")
    print(f"  BUDGET & COST TRACKING")
    print(f"{'='*60}\n")

    status_icon = "✓" if budget["within_budget"] else "✗ EXCEEDED"
    print(f"  Today ({daily['date']}):")
    print(f"    Status:    {status_icon}")
    print(f"    Spent:     ${budget['spent']:.4f}")
    print(f"    Limit:     ${budget['limit']:.2f}")
    print(f"    Remaining: ${budget['remaining']:.4f}")
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
            for d, cost in alltime["by_date"].items():
                print(f"      {d}  ${cost:.4f}")
    print()


def _do_rollback(domain: str):
    """Manually roll back to previous strategy version."""
    current = get_active_version("researcher", domain)
    print(f"\n  Current strategy: {current}")

    rolled_to = rollback("researcher", domain)
    if rolled_to:
        print(f"  ✓ Rolled back to: {rolled_to}")
    else:
        print(f"  ✗ No previous version to roll back to")
    print()


def _show_principles(force_extract: bool = False):
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
        # Show existing or extract if none
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

    principles = result.get("principles", [])
    print(f"\n  General Principles ({len(principles)}):")
    for i, p in enumerate(principles, 1):
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

    # Show transfer-ready domains
    sources = get_transfer_sources()
    print(f"\n  Transfer sources available: {len(sources)}")
    for s in sources:
        print(f"    {s['domain']}: {s['stats']['count']} outputs, avg {s['stats']['avg_score']:.1f}")

    print(f"\n  To seed a new domain: python main.py --transfer <domain> [--hint 'example question']")
    print()


def _do_transfer(target_domain: str, question_hint: str = ""):
    """Generate a seed strategy for a target domain from cross-domain principles."""
    print(f"\n{'='*60}")
    print(f"  CROSS-DOMAIN TRANSFER → {target_domain}")
    print(f"{'='*60}\n")

    # Check budget first
    budget = check_budget()
    if not budget["within_budget"]:
        print(f"  ✗ Budget exceeded. Use --budget to see details.")
        return

    # Ensure principles exist
    principles = load_principles()
    if not principles:
        print("  No principles yet. Extracting from qualifying domains...\n")
        principles = extract_principles()
        if not principles:
            print("  ✗ No qualifying domains. Need ≥5 outputs with avg score ≥5.5 and an active strategy.")
            return

    result = generate_seed_strategy(target_domain, question_hint)
    if result:
        print(f"\n  ✓ Seed strategy {result['version']} created for '{target_domain}' (PENDING)")
        if result.get("expected_improvement"):
            print(f"  Expected improvement: {result['expected_improvement']}")
    else:
        print(f"  ✗ Failed to generate seed strategy")
    print()


def _show_next(domain: str):
    """Show self-generated next questions for a domain."""
    print(f"\n{'='*60}")
    print(f"  NEXT QUESTIONS — Domain: {domain}")
    print(f"  (Stage 1: Diagnose Needs → Stage 2: Set Goals)")
    print(f"{'='*60}\n")

    budget = check_budget()
    if not budget["within_budget"]:
        print(f"  ✗ Budget exceeded. Use --budget to see details.")
        return

    result = generate_questions(domain)
    if not result:
        print("  No questions generated. Need at least 1 output in this domain first.")
        return

    print(f"\n  To auto-research the top question:")
    print(f"    python main.py --domain {domain} --auto")
    print(f"\n  Or pick one manually:")
    for i, q in enumerate(result["questions"], 1):
        print(f"    python main.py --domain {domain} \"{q.get('question', '')}\"")
    print()


def _run_auto(domain: str, rounds: int = 1):
    """
    Self-directed learning mode.
    
    The system:
    1. Diagnoses its own knowledge gaps (Stage 1)
    2. Generates the best next question (Stage 2)
    3. Researches it (Stages 3+4)
    4. Evaluates the result (Stage 5)
    5. Repeats for N rounds
    
    This is the full Knowles self-directed learning cycle, automated.
    """
    print(f"\n{'='*60}")
    print(f"  SELF-DIRECTED LEARNING MODE")
    print(f"  Domain: {domain}")
    print(f"  Rounds: {rounds}")
    print(f"{'='*60}\n")

    for round_num in range(1, rounds + 1):
        print(f"\n{'─'*50}")
        print(f"  ROUND {round_num}/{rounds}")
        print(f"{'─'*50}\n")

        # Budget check each round
        budget = check_budget()
        if not budget["within_budget"]:
            print(f"[BUDGET] ✗ BLOCKED — daily limit reached after {round_num - 1} rounds")
            break

        print(f"[BUDGET] ${budget['remaining']:.4f} remaining")

        # Stage 1+2: Diagnose needs → Set goal
        print(f"\n[STAGE 1+2] Diagnosing knowledge gaps and generating next question...")
        question = get_next_question(domain)

        if not question:
            # First time in domain — no data to diagnose
            stats = get_stats(domain)
            if stats["count"] == 0:
                print(f"[QUESTION-GEN] Domain '{domain}' has no outputs yet.")
                print(f"  Cannot self-direct without seed data. Run a manual question first:")
                print(f"    python main.py --domain {domain} \"Your question here\"")
                break
            else:
                print(f"[QUESTION-GEN] Failed to generate question. Stopping.")
                break

        print(f"\n[QUESTION] → {question}")

        # Stages 3+4+5: Research → Evaluate (handled by run_loop)
        print(f"\n[STAGE 3-5] Researching, evaluating, storing...")
        try:
            result = run_loop(question=question, domain=domain)
        except SystemExit:
            # run_loop calls sys.exit on budget exceeded
            print(f"[AUTO] Stopped — budget exceeded during round {round_num}")
            break

        score = result.get("critique", {}).get("overall_score", 0)
        verdict = result.get("critique", {}).get("verdict", "unknown")

        print(f"\n[ROUND {round_num} COMPLETE] Score: {score}/10 — {verdict}")

        if round_num < rounds:
            print(f"\n  Continuing to round {round_num + 1}...")

    # Summary
    stats = get_stats(domain)
    daily = get_daily_spend()
    print(f"\n{'='*60}")
    print(f"  AUTO MODE COMPLETE")
    print(f"  Rounds completed: {round_num if question else round_num - 1}/{rounds}")
    print(f"  Domain '{domain}': {stats['count']} total outputs, avg {stats['avg_score']:.1f}")
    print(f"  Today's spend: ${daily['total_usd']:.4f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
