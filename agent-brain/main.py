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
    python main.py --synthesize                  Force knowledge synthesis for a domain
    python main.py --kb                           Show synthesized knowledge base
    python main.py --prune                        Archive rejected/low-score outputs
    python main.py --prune-dry                    Preview what --prune would archive
    python main.py --dashboard                    Full system dashboard (all domains at a glance)
    python main.py --orchestrate                  Smart multi-domain auto: prioritize + run across all domains
    python main.py --orchestrate --rounds 10      Orchestrate 10 rounds across domains
    python main.py --orchestrate --target-domains crypto,ai  Orchestrate specific domains only
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
from agents.consensus import consensus_research
from agents.meta_analyst import analyze_and_evolve
from config import (
    QUALITY_THRESHOLD, MAX_RETRIES, DEFAULT_DOMAIN, LOG_DIR,
    MIN_OUTPUTS_FOR_ANALYSIS, EVOLVE_EVERY_N,
    MIN_OUTPUTS_FOR_SYNTHESIS, SYNTHESIZE_EVERY_N,
    CONSENSUS_ENABLED, CONSENSUS_RESEARCHERS,
)
from memory_store import save_output, load_outputs, get_stats, prune_domain, get_archive_stats
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
from agents.synthesizer import synthesize, show_knowledge_base
from agents.orchestrator import (
    prioritize_domains, allocate_rounds, get_post_run_actions,
    get_system_health, discover_domains,
)
from utils.retry import retry_api_call, is_retryable
from analytics import display_analytics, search_memory, display_search_results, full_report
from validator import display_validation
from domain_seeder import get_seed_question, get_seed_questions, has_curated_seeds, list_available_domains
from scheduler import create_plan, display_plan, get_recommendations, display_recommendations, run_daemon, stop_daemon, get_daemon_status
from knowledge_graph import build_graph_from_kb, save_graph, load_graph, get_graph_summary


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

        # Step 1: Research (single or consensus mode)
        if CONSENSUS_ENABLED:
            print(f"[RESEARCHER] Generating findings (consensus mode, {CONSENSUS_RESEARCHERS} researchers)...")
            research_output = consensus_research(
                question=question,
                strategy=strategy,
                critique=previous_critique_feedback,
                domain=domain,
                n_researchers=CONSENSUS_RESEARCHERS,
            )
        else:
            print("[RESEARCHER] Generating findings...")
            research_output = research(
                question=question,
                strategy=strategy,
                critique=previous_critique_feedback,
                domain=domain,
            )

        findings_count = len(research_output.get("findings", []))
        print(f"[RESEARCHER] Produced {findings_count} findings")

        if research_output.get("_parse_error"):
            print("[RESEARCHER] ⚠ Output wasn't structured JSON — wrapped as raw")
        if research_output.get("_zero_findings"):
            print("[RESEARCHER] ⚠ Structured output but 0 actual findings")
        empty_searches = research_output.get("_empty_searches", 0)
        if empty_searches > 0:
            total_searches = research_output.get("_searches_made", 0)
            print(f"[RESEARCHER] ⚠ {empty_searches}/{total_searches} searches returned 0 results")

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
            
            # Smart recovery: enhance feedback when failure was search-related
            if research_output.get("_zero_findings") or research_output.get("_parse_error"):
                feedback += (
                    " CRITICAL: Your previous attempt produced no usable findings. "
                    "Use SIMPLER, BROADER search queries. Break the question into "
                    "smaller sub-topics and search for each separately. Avoid overly "
                    "specific or complex search queries — start broad, then narrow."
                )
            elif research_output.get("_empty_searches", 0) >= 3:
                feedback += (
                    " NOTE: Many of your searches returned 0 results. Simplify your "
                    "search terms — remove dates, quotes, and specific jargon. Search "
                    "for the general topic first."
                )
            
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

    # Step 6.5: Knowledge synthesis — integrate findings into domain knowledge base
    accepted_count = get_stats(domain).get("accepted", 0)
    if accepted_count >= MIN_OUTPUTS_FOR_SYNTHESIS and accepted_count % SYNTHESIZE_EVERY_N == 0:
        # Auto-synthesize every SYNTHESIZE_EVERY_N accepted outputs
        kb = synthesize(domain)
        if kb:
            active_claims = len([c for c in kb.get("claims", []) if c.get("status") == "active"])
            print(f"[SYNTHESIZER] Knowledge base: {active_claims} active claims")
            # Auto-build knowledge graph
            try:
                graph = build_graph_from_kb(domain, kb)
                save_graph(domain, graph)
                gs = get_graph_summary(graph)
                print(f"[GRAPH] ✓ {gs['total_nodes']} nodes, {gs['total_edges']} edges")
            except Exception as e:
                print(f"[GRAPH] ⚠ Graph build failed: {e}")

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
    parser.add_argument("--synthesize", action="store_true", help="Synthesize domain outputs into knowledge base")
    parser.add_argument("--kb", action="store_true", help="Show the synthesized knowledge base for a domain")
    parser.add_argument("--prune", action="store_true", help="Run memory hygiene: archive rejected/low outputs")
    parser.add_argument("--prune-dry", action="store_true", help="Show what --prune would archive without doing it")
    parser.add_argument("--dashboard", action="store_true", help="Show full system dashboard (all domains, strategies, budget)")
    parser.add_argument("--orchestrate", action="store_true", help="Smart multi-domain auto mode: prioritize and run across domains")
    parser.add_argument("--target-domains", default="", help="Comma-separated domains for --orchestrate (default: all)")
    parser.add_argument("--export", action="store_true", help="Export full system report as JSON")
    parser.add_argument("--export-md", action="store_true", help="Export full system report as Markdown")
    parser.add_argument("--analytics", action="store_true", help="Deep performance analytics (domain or system-wide)")
    parser.add_argument("--search", metavar="QUERY", help="Search across all memory for matching outputs")
    parser.add_argument("--validate", action="store_true", help="Validate data integrity across memory, strategies, costs")
    parser.add_argument("--seed", action="store_true", help="Show seed questions for a domain (or list available domains)")
    parser.add_argument("--plan", action="store_true", help="Show recommended research plan without running")
    parser.add_argument("--run-plan", action="store_true", help="Execute the recommended research plan")
    parser.add_argument("--aggressive", action="store_true", help="Use more budget per cycle (with --plan or --run-plan)")
    parser.add_argument("--recommend", action="store_true", help="Show prioritized recommendations for system improvement")
    parser.add_argument("--smart-orchestrate", action="store_true", help="LLM-reasoned multi-domain orchestration")
    parser.add_argument("--consensus", action="store_true", help="Force consensus mode for this run (multi-researcher)")
    parser.add_argument("--no-consensus", action="store_true", help="Force single-researcher mode for this run")
    parser.add_argument("--graph", action="store_true", help="Show knowledge graph summary for a domain")
    parser.add_argument("--daemon", action="store_true", help="Run scheduler daemon (continuous autonomous operation)")
    parser.add_argument("--daemon-stop", action="store_true", help="Stop the running daemon")
    parser.add_argument("--daemon-status", action="store_true", help="Show daemon status")
    parser.add_argument("--interval", type=int, default=60, help="Daemon interval in minutes (default: 60)")
    parser.add_argument("--max-cycles", type=int, default=0, help="Max daemon cycles (0=unlimited)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY environment variable first.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Apply consensus overrides
    import config as _cfg
    if args.consensus:
        _cfg.CONSENSUS_ENABLED = True
        print("  [CONFIG] Consensus mode ENABLED for this run")
    elif getattr(args, 'no_consensus', False):
        _cfg.CONSENSUS_ENABLED = False
        print("  [CONFIG] Consensus mode DISABLED for this run")

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
    if args.synthesize:
        _run_synthesize(args.domain)
        return
    if args.kb:
        _show_kb(args.domain)
        return
    if args.prune or getattr(args, 'prune_dry', False):
        _run_prune(args.domain, dry_run=getattr(args, 'prune_dry', False))
        return
    if args.dashboard:
        _show_dashboard()
        return
    if args.orchestrate:
        targets = [d.strip() for d in args.target_domains.split(",") if d.strip()] or None
        _run_orchestrate(targets, args.rounds)
        return
    if args.export or getattr(args, 'export_md', False):
        _run_export(markdown=getattr(args, 'export_md', False))
        return
    if args.analytics:
        domain_arg = args.domain if args.domain != DEFAULT_DOMAIN else None
        display_analytics(domain_arg)
        return
    if args.search:
        results = search_memory(args.search)
        display_search_results(args.search, results)
        return
    if args.validate:
        display_validation()
        return
    if args.seed:
        _show_seeds(args.domain)
        return
    if args.plan:
        plan = create_plan(aggressive=args.aggressive)
        display_plan(plan)
        return
    if args.run_plan:
        plan = create_plan(aggressive=args.aggressive)
        display_plan(plan)
        if plan["executable"]:
            print("  Executing plan...\n")
            target = [a["domain"] for a in plan["allocation"]]
            total = plan["total_rounds"]
            _run_orchestrate(target, total)
        return
    if args.recommend:
        recs = get_recommendations()
        display_recommendations(recs)
        return
    if getattr(args, 'smart_orchestrate', False):
        _run_smart_orchestrate(args)
        return
    if args.graph:
        _show_graph(args.domain)
        return
    if args.daemon:
        _run_daemon(args)
        return
    if getattr(args, 'daemon_stop', False):
        if stop_daemon():
            print("  Daemon stop signal sent.")
        else:
            print("  No daemon is running.")
        return
    if getattr(args, 'daemon_status', False):
        status = get_daemon_status()
        _show_daemon_status(status)
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
            from strategy_store import load_strategy_file
            vdata = load_strategy_file("researcher", domain, v)
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
    from strategy_store import load_strategy_file

    # Show the strategy before approving
    data = load_strategy_file("researcher", domain, version)
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

    question = None  # Initialize before loop to avoid NameError in summary
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
            # First time in domain — use seed questions
            stats = get_stats(domain)
            if stats["count"] == 0:
                question = get_seed_question(domain)
                curated = "curated" if has_curated_seeds(domain) else "generic"
                print(f"[SEED] Domain '{domain}' has no outputs — using {curated} seed question")
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


def _run_orchestrate(target_domains: list[str] | None, total_rounds: int):
    """
    Smart multi-domain orchestration.
    
    The Orchestrator:
    1. Analyzes all domains → computes priority scores
    2. Allocates rounds based on priority (budget-aware)
    3. Runs auto mode per domain
    4. After each domain: checks for synthesis/evolution triggers
    5. At end: re-extracts cross-domain principles if applicable
    """
    print(f"\n{'='*60}")
    print(f"  ORCHESTRATOR — Multi-Domain Coordination")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    # Budget gate
    budget = check_budget()
    if not budget["within_budget"]:
        print(f"\n  ✗ Budget exceeded (${budget['spent']:.2f}/${budget['limit']:.2f})")
        return

    print(f"\n  Budget: ${budget['remaining']:.2f} remaining today")
    print(f"  Total rounds requested: {total_rounds}")

    # Step 1: Prioritize domains
    print(f"\n  ── Domain Priority Analysis ──")
    priorities = prioritize_domains(target_domains)
    
    if not priorities:
        print(f"  No domains found. Run a manual question first.")
        return

    print(f"  {'Domain':<16} {'Priority':>8} {'Outputs':>7} {'Rate':>6} {'Strategy':<10} {'Action'}")
    print(f"  {'─'*70}")
    for p in priorities:
        count = p["stats"]["count"]
        accepted = p["stats"]["accepted"]
        rate = f"{accepted/count*100:.0f}%" if count > 0 else "—"
        print(f"  {p['domain']:<16} {p['priority']:>8.1f} {count:>7} {rate:>6} {p['strategy']:<10} {p['action']}")
        for reason in p["reasons"][:2]:
            print(f"  {'':>16} ↳ {reason}")

    # Step 2: Allocate rounds
    allocation = allocate_rounds(priorities, total_rounds)
    
    if not allocation:
        print(f"\n  No actionable domains. Check pending approvals.")
        # Show what's blocked
        for p in priorities:
            if p["skip"]:
                print(f"  ⚠ {p['domain']}: {'; '.join(p['reasons'])}")
        return

    print(f"\n  ── Round Allocation ──")
    for a in allocation:
        print(f"  {a['domain']:<16} → {a['rounds']} round(s)")
    total_allocated = sum(a["rounds"] for a in allocation)
    print(f"  {'TOTAL':<16} → {total_allocated} round(s)")

    # Step 3: Execute rounds per domain
    results_summary = []
    total_completed = 0
    
    for i, alloc in enumerate(allocation):
        domain = alloc["domain"]
        rounds = alloc["rounds"]

        print(f"\n{'='*60}")
        print(f"  DOMAIN {i+1}/{len(allocation)}: {domain.upper()}")
        print(f"  Allocated: {rounds} round(s)")
        print(f"{'='*60}")

        # Budget check before each domain
        budget = check_budget()
        if not budget["within_budget"]:
            print(f"\n  ✗ Budget exceeded — stopping orchestration")
            break

        domain_scores = []
        domain_completed = 0
        
        for round_num in range(1, rounds + 1):
            # Budget check each round
            budget = check_budget()
            if not budget["within_budget"]:
                print(f"\n  [BUDGET] ✗ Daily limit reached after {round_num - 1} rounds in {domain}")
                break

            print(f"\n  ── Round {round_num}/{rounds} (${budget['remaining']:.2f} remaining) ──")

            # Generate question (with retry for transient API errors)
            question = None
            domain_stats = get_stats(domain)
            
            if domain_stats["count"] == 0:
                # Use seed questions for empty domains (no API call needed!)
                seed_questions = get_seed_questions(domain, count=rounds)
                seed_idx = round_num - 1
                if seed_idx < len(seed_questions):
                    question = seed_questions[seed_idx]
                    curated = "curated" if has_curated_seeds(domain) else "generic"
                    print(f"  [SEED] Using {curated} seed question ({seed_idx+1}/{len(seed_questions)})")
                else:
                    question = get_seed_question(domain)
                    print(f"  [SEED] Reusing seed question (all seeds exhausted)")
            else:
                try:
                    question = retry_api_call(
                        lambda: get_next_question(domain),
                        max_attempts=5, base_delay=30, verbose=True,
                    )
                except Exception as e:
                    if is_retryable(e):
                        print(f"  ✗ API still overloaded after retries. Skipping {domain}.")
                    else:
                        print(f"  ✗ Question generation error: {e}")
            if not question:
                print(f"  ✗ Failed to generate question for {domain}. Stopping.")
                break

            print(f"  [Q] {question[:80]}")

            # Run the loop (with retry for transient API errors)
            result = None
            try:
                result = retry_api_call(
                    lambda: run_loop(question=question, domain=domain),
                    max_attempts=5, base_delay=30, verbose=True,
                )
            except SystemExit:
                print(f"  ✗ Budget exceeded during run in {domain}")
                break
            except Exception as e:
                if is_retryable(e):
                    print(f"  ✗ API still overloaded after retries. Skipping round.")
                else:
                    print(f"  ✗ Run error: {e}")
            
            if result is None:
                print(f"  ✗ Round failed for {domain}. Continuing...")
                continue

            score = result.get("critique", {}).get("overall_score", 0)
            verdict = result.get("critique", {}).get("verdict", "unknown")
            domain_scores.append(score)
            domain_completed += 1
            total_completed += 1

            print(f"  [RESULT] {score}/10 — {verdict}")

        # Post-run actions for this domain
        post_actions = get_post_run_actions(domain)
        for pa in post_actions:
            if pa["action"] == "synthesize":
                print(f"\n  [POST] Synthesizing knowledge base... ({pa['reason']})")
                try:
                    kb = synthesize(domain, force=True)
                    if kb:
                        active_claims = len([c for c in kb.get("claims", []) if c.get("status") == "active"])
                        print(f"  [SYNTHESIZE] ✓ {active_claims} active claims")
                except Exception as e:
                    print(f"  [SYNTHESIZE] ✗ Failed: {e}")

            elif pa["action"] == "evolve":
                print(f"\n  [POST] Triggering strategy evolution... ({pa['reason']})")
                try:
                    evolution = analyze_and_evolve(domain)
                    if evolution:
                        print(f"  [EVOLVE] ✓ Strategy evolved to {evolution['new_version']}")
                except Exception as e:
                    print(f"  [EVOLVE] ✗ Failed: {e}")

        # Domain summary
        avg = sum(domain_scores) / len(domain_scores) if domain_scores else 0
        stats = get_stats(domain)
        results_summary.append({
            "domain": domain,
            "rounds_completed": domain_completed,
            "rounds_allocated": rounds,
            "avg_score": round(avg, 1),
            "total_outputs": stats["count"],
            "accepted": stats["accepted"],
        })

    # Step 4: Cross-domain principle extraction (if applicable)
    budget = check_budget()
    if budget["within_budget"] and total_completed >= 3:
        from agents.cross_domain import get_transfer_sources
        sources = get_transfer_sources()
        if len(sources) >= 2:
            print(f"\n  ── Cross-Domain Principles ──")
            print(f"  {len(sources)} qualifying domains — extracting updated principles...")
            try:
                principles = extract_principles(force=True)
                if principles:
                    p_count = len(principles.get("principles", []))
                    print(f"  ✓ Extracted {p_count} principles (v{principles.get('version', '?')})")
            except Exception as e:
                print(f"  ✗ Principle extraction failed: {e}")

    # Final Summary
    daily = get_daily_spend()
    health = get_system_health()
    
    print(f"\n{'='*60}")
    print(f"  ORCHESTRATION COMPLETE")
    print(f"{'='*60}")
    print(f"\n  Rounds completed: {total_completed}/{total_allocated}")
    print(f"\n  Results by domain:")
    print(f"  {'Domain':<16} {'Done':>5} {'Avg':>5} {'Total':>6} {'Accepted':>8}")
    print(f"  {'─'*45}")
    for r in results_summary:
        print(f"  {r['domain']:<16} {r['rounds_completed']:>5} {r['avg_score']:>5.1f} {r['total_outputs']:>6} {r['accepted']:>8}")
    
    print(f"\n  Budget: ${daily['total_usd']:.4f} spent today ({daily['calls']} API calls)")
    print(f"  System health: {health['health_score']}/100")
    print(f"{'='*60}\n")


def _run_smart_orchestrate(args):
    """LLM-reasoned orchestration — Claude decides domain allocation."""
    from agents.orchestrator import smart_orchestrate

    print(f"\n{'='*60}")
    print(f"  SMART ORCHESTRATOR — LLM-Reasoned Allocation")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    total = args.rounds if hasattr(args, 'rounds') and args.rounds else 5
    target = args.target.split(",") if hasattr(args, 'target') and args.target else None

    result = smart_orchestrate(total_rounds=total, target_domains=target)

    if not result:
        print("\n  ✗ Smart orchestration failed.")
        return

    print(f"\n  Reasoning: {result.get('reasoning', 'N/A')}")
    print(f"\n  Allocation:")
    allocation = result.get("allocation", [])
    for a in allocation:
        print(f"    {a['domain']:<16} → {a['rounds']} round(s)")
        if a.get("reason"):
            print(f"    {'':>16}   ↳ {a['reason']}")

    actions = result.get("recommended_actions", [])
    if actions:
        print(f"\n  Recommended actions:")
        for act in actions:
            print(f"    • {act}")

    # Execute the allocation
    if allocation:
        print(f"\n  Executing allocation...")
        targets = [a["domain"] for a in allocation]
        total_rounds = sum(a["rounds"] for a in allocation)
        _run_orchestrate(targets, total_rounds)


def _show_graph(domain: str):
    """Display knowledge graph summary for a domain."""
    print(f"\n{'='*60}")
    print(f"  KNOWLEDGE GRAPH — {domain}")
    print(f"{'='*60}")

    graph = load_graph(domain)
    if not graph or not graph.get("nodes"):
        print(f"\n  No knowledge graph found for '{domain}'.")
        print(f"  Run --synthesize first to build knowledge base, then graph auto-builds.")
        print()
        return

    summary = get_graph_summary(graph)

    print(f"\n  Nodes: {summary['total_nodes']}")
    print(f"  Edges: {summary['total_edges']}")
    print(f"  Clusters: {summary['total_clusters']}")

    # Node breakdown by type
    print(f"\n  Node Types:")
    for ntype, count in sorted(summary.get("node_types", {}).items(), key=lambda x: -x[1]):
        print(f"    {ntype:<16} {count:>4}")

    # Edge breakdown by type
    print(f"\n  Edge Types:")
    for etype, count in sorted(summary.get("edge_types", {}).items(), key=lambda x: -x[1]):
        print(f"    {etype:<16} {count:>4}")

    # Contradictions
    from knowledge_graph import get_contradictions
    contradictions = get_contradictions(graph)
    if contradictions:
        print(f"\n  ⚠ Contradictions ({len(contradictions)}):")
        for c in contradictions[:5]:
            src = next((n for n in graph["nodes"] if n["id"] == c["source"]), {})
            tgt = next((n for n in graph["nodes"] if n["id"] == c["target"]), {})
            print(f"    • {src.get('label', c['source'])[:40]}")
            print(f"      ↔ {tgt.get('label', c['target'])[:40]}")

    # Gaps
    gaps = summary.get("gaps", {})
    isolated = gaps.get("isolated_nodes", [])
    if isolated:
        print(f"\n  Knowledge Gaps ({len(isolated)} isolated nodes):")
        for node_id in isolated[:5]:
            node = next((n for n in graph["nodes"] if n["id"] == node_id), {})
            print(f"    • {node.get('label', node_id)[:60]}")

    print()


def _run_daemon(args):
    """Start the autonomous daemon."""
    interval = getattr(args, 'interval', 60) or 60
    max_cycles = getattr(args, 'max_cycles', None)
    aggressive = getattr(args, 'aggressive', False)

    print(f"\n{'='*60}")
    print(f"  DAEMON MODE — Autonomous Operation")
    print(f"{'='*60}")
    print(f"\n  Interval: {interval} minutes")
    print(f"  Max cycles: {max_cycles or 'unlimited'}")
    print(f"  Aggressive: {aggressive}")
    print(f"\n  ⚠ Human approval still required for strategy changes.")
    print(f"  Press Ctrl+C to stop gracefully.\n")

    run_daemon(
        interval_minutes=interval,
        rounds_per_cycle=getattr(args, 'rounds', 3) or 3,
        max_cycles=max_cycles,
        aggressive=aggressive,
        require_approval=True,
    )


def _show_daemon_status(status: dict):
    """Display daemon status."""
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

    print()


def _show_seeds(domain: str):
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


def _run_export(markdown: bool = False):
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
        with open(outpath, "w") as f:
            json.dump(report, f, indent=2)
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


def _run_synthesize(domain: str):
    """Force knowledge synthesis for a domain."""
    print(f"\n{'='*60}")
    print(f"  KNOWLEDGE SYNTHESIS — Domain: {domain}")
    print(f"{'='*60}\n")

    budget = check_budget()
    if not budget["within_budget"]:
        print(f"  ✗ Budget exceeded. Use --budget to see details.")
        return

    result = synthesize(domain, force=True)
    if not result:
        print(f"\n  ✗ Synthesis failed or not enough data.")
        print(f"  Need at least {MIN_OUTPUTS_FOR_SYNTHESIS} accepted outputs.")
    else:
        # Build knowledge graph from the synthesized KB
        print(f"\n[GRAPH] Building knowledge graph...")
        graph = build_graph_from_kb(domain, result)
        save_graph(domain, graph)
        summary = get_graph_summary(graph)
        print(f"[GRAPH] ✓ {summary['total_nodes']} nodes, {summary['total_edges']} edges, "
              f"{summary['total_clusters']} clusters")
    print()


def _show_kb(domain: str):
    """Display the knowledge base for a domain."""
    print(f"\n{'='*60}")
    print(f"  KNOWLEDGE BASE — Domain: {domain}")
    print(f"{'='*60}")

    show_knowledge_base(domain)
    print()


def _run_prune(domain: str, dry_run: bool = False):
    """Run memory hygiene on a domain."""
    action = "DRY RUN" if dry_run else "PRUNING"
    print(f"\n{'='*60}")
    print(f"  MEMORY HYGIENE ({action}) — Domain: {domain}")
    print(f"{'='*60}\n")

    # Show current state
    stats = get_stats(domain)
    print(f"  Before: {stats['count']} outputs, {stats['accepted']} accepted, {stats['rejected']} rejected")

    archive_stats = get_archive_stats(domain)
    if archive_stats["count"] > 0:
        print(f"  Already archived: {archive_stats['count']} outputs")

    result = prune_domain(domain, dry_run=dry_run)

    if result["archived"] == 0:
        print(f"\n  ✓ Memory is clean — nothing to archive")
    else:
        verb = "Would archive" if dry_run else "Archived"
        print(f"\n  {verb} {result['archived']} output(s):")
        for detail in result.get("details", []):
            print(f"    → {detail['filename']} (score {detail['score']}, "
                  f"{detail['verdict']}, {detail['age_days']}d old) — {detail['reason']}")

    print(f"\n  After: {result['kept']} active outputs")
    if not dry_run and result["archived"] > 0:
        print(f"  Archived files in: memory/{domain}/_archive/")
        print(f"  Note: archived outputs can be restored if needed")
    print()


def _show_dashboard():
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
    memory_dir = os.path.join(os.path.dirname(__file__), "memory")
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
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
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


if __name__ == "__main__":
    main()
