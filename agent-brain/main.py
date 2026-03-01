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

Agent Hands (Execution Layer):
    python main.py --execute --goal 'Build X'    Execute a coding task with Agent Hands
    python main.py --exec-status                  Show execution memory stats
    python main.py --exec-evolve                  Force execution strategy evolution
    python main.py --exec-principles              Show learned execution principles
    python main.py --next-task                    Show next AI-generated coding task
    python main.py --auto-build                   Brain→Hands: generate task from KB + execute
    python main.py --auto-build --build-rounds 3  Run 3 rounds of auto-build
    python main.py --execute --workspace /path    Execute in a specific directory
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from utils.atomic_write import atomic_json_write

from agents.researcher import research
from agents.critic import critique
from agents.consensus import consensus_research
from agents.meta_analyst import analyze_and_evolve
from config import (
    QUALITY_THRESHOLD, MAX_RETRIES, DEFAULT_DOMAIN, LOG_DIR,
    MIN_OUTPUTS_FOR_ANALYSIS, EVOLVE_EVERY_N,
    MIN_OUTPUTS_FOR_SYNTHESIS, SYNTHESIZE_EVERY_N,
    CONSENSUS_ENABLED, CONSENSUS_RESEARCHERS,
    AUTO_PRUNE_ENABLED, AUTO_PRUNE_EVERY_N,
)
from memory_store import save_output, load_outputs, get_stats, prune_domain, get_archive_stats
from strategy_store import (
    get_strategy, get_strategy_status, evaluate_trial,
    get_strategy_performance, get_version_history, rollback,
    get_active_version, list_versions, list_pending,
    approve_strategy, reject_strategy, get_strategy_diff,
)
from cost_tracker import check_budget, check_balance, get_daily_spend, get_all_time_spend
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
    
    Wrapped in error recovery — API failures and agent crashes are caught,
    logged, and reported without killing the process.
    """
    try:
        return _run_loop_inner(question, domain)
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Stopped by user.")
        raise
    except SystemExit:
        raise  # Let sys.exit() through (budget blocks etc.)
    except Exception as e:
        # Log the error
        error_msg = f"{type(e).__name__}: {e}"
        print(f"\n[ERROR] ✗ Loop crashed: {error_msg}")
        _log_error(domain, question, error_msg)
        
        # Generate alert in DB
        try:
            from db import insert_alert
            insert_alert(
                alert_type="loop_crash",
                message=f"Research loop crashed: {error_msg}",
                severity="critical",
                domain=domain,
                details={"question": question, "error": error_msg},
            )
        except Exception as db_err:
            print(f"[DB] \u26a0 Alert insert failed: {db_err}")
        
        return {"error": error_msg, "research": None, "critique": None}


def _log_error(domain: str, question: str, error: str):
    """Log an error to the error log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    error_log = os.path.join(LOG_DIR, "errors.jsonl")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "question": question,
        "error": error,
    }
    try:
        with open(error_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Even error logging shouldn't crash


def _run_loop_inner(question: str, domain: str = DEFAULT_DOMAIN) -> dict:
    """Inner loop — the actual research cycle, separated for error wrapping."""
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
    balance = check_balance()
    print(f"  Budget: ${budget['remaining']:.4f} remaining today | Balance: ${balance['remaining_balance']:.4f} of ${balance['starting_balance']:.2f}")
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
        try:
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
        except Exception as e:
            print(f"[RESEARCHER] ✗ Agent error: {type(e).__name__}: {e}")
            if attempt <= MAX_RETRIES:
                print(f"  Retrying...")
                previous_critique_feedback = f"Previous attempt crashed with error: {e}. Try a different approach."
                continue
            else:
                raise  # Final attempt — let outer handler catch it

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
        try:
            critique_output = critique(research_output, domain=domain, sources_summary=research_output.get("_tool_log"))
        except Exception as e:
            print(f"[CRITIC] ✗ Agent error: {type(e).__name__}: {e}")
            # Use a minimal critique so we can still store the output
            critique_output = {
                "overall_score": 3,
                "verdict": "reject",
                "scores": {},
                "strengths": [],
                "weaknesses": [f"Critic crashed: {e}"],
                "actionable_feedback": "Critic was unable to evaluate. Retry needed.",
                "_error": str(e),
            }

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
            
            # Build structured retry feedback with dimension scores
            dim_scores = critique_output.get("scores", {})
            if dim_scores:
                # Find weakest dimension
                dim_names = ["accuracy", "depth", "completeness", "specificity", "intellectual_honesty"]
                scored_dims = [(d, dim_scores.get(d, 0)) for d in dim_names if d in dim_scores]
                scored_dims.sort(key=lambda x: x[1])
                lowest_dim, lowest_score = scored_dims[0] if scored_dims else ("unknown", 0)
                
                dim_block = "DIMENSION SCORES:\n"
                for d, s in [(d, dim_scores.get(d, 0)) for d in dim_names if d in dim_scores]:
                    marker = " ⚠ FOCUS HERE" if s < 6 else ""
                    dim_block += f"  {d:22s}: {s}/10{marker}\n"
                dim_block += f"\nWEAKEST AREA: {lowest_dim} ({lowest_score}/10)\n"
                
                # Add dimension-specific guidance
                dim_hints = {
                    "accuracy": "VERIFY all claims against fetched page content. Remove anything you can't source.",
                    "depth": "EXPLAIN mechanisms, not just list facts. Answer WHY and HOW, not just WHAT.",
                    "completeness": "Cover MORE angles. Check if you missed important sub-topics or perspectives.",
                    "specificity": "INCLUDE specific numbers, dates, URLs, code examples. Vague claims score low.",
                    "intellectual_honesty": "Clearly DISTINGUISH facts from speculation. Flag uncertainty explicitly.",
                }
                hint = dim_hints.get(lowest_dim, "")
                
                feedback = f"PREVIOUS SCORE: {score}/10\n\n{dim_block}\n{hint}\n\nCRITIC FEEDBACK: {feedback}"
            
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

    # Warmup mode: first N outputs in a domain require explicit approval
    from config import WARMUP_OUTPUTS, WARMUP_APPROVAL_REQUIRED
    if WARMUP_APPROVAL_REQUIRED and stats['accepted'] <= WARMUP_OUTPUTS:
        verdict = final_critique.get("verdict", "unknown")
        if verdict == "accept":
            print(f"\n[WARMUP] ⚠ Domain '{domain}' is in warmup mode ({stats['accepted']}/{WARMUP_OUTPUTS} outputs)")
            print(f"  Results are stored but strategy evolution is suppressed until warmup completes.")
            print(f"  This prevents premature strategy changes based on insufficient data.")

    # Step 6: Evaluate trial strategy (if one is active)
    trial_result = evaluate_trial("researcher", domain)
    if trial_result["action"] == "rollback":
        print(f"\n[SAFETY] ⚠ {trial_result['reason']}")
    elif trial_result["action"] == "confirm":
        print(f"\n[SAFETY] ✓ {trial_result['reason']}")
    elif trial_result["action"] == "continue_trial":
        print(f"\n[SAFETY] ⏳ {trial_result['reason']}")

    # Step 6.5: Knowledge synthesis — integrate findings into domain knowledge base
    # Only trigger on runs that actually produced an accepted output
    final_verdict = final_critique.get("verdict", "unknown")
    accepted_count = get_stats(domain).get("accepted", 0)
    if final_verdict == "accept" and accepted_count >= MIN_OUTPUTS_FOR_SYNTHESIS and accepted_count % SYNTHESIZE_EVERY_N == 0:
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

            # Auto-extract predictions from newly synthesized KB
            try:
                from agents.verifier import extract_predictions, load_predictions
                new_preds = extract_predictions(domain)
                if new_preds:
                    existing = load_predictions(domain)
                    print(f"[VERIFIER] Extracted {len(new_preds)} prediction(s) from KB ({len(existing)} total tracked)")
            except Exception as e:
                print(f"[VERIFIER] ⚠ Prediction extraction failed: {e}")

    # Step 6.75: Auto-verify past-deadline predictions (reality-grounding)
    if final_verdict == "accept":
        try:
            from agents.verifier import verify_predictions, load_predictions
            predictions = load_predictions(domain)
            pending = [p for p in predictions if p.get("status") == "pending"]
            if pending:
                from datetime import date as _date
                past_deadline = [p for p in pending 
                                 if p.get("deadline") and p["deadline"] <= _date.today().isoformat()]
                if past_deadline:
                    print(f"\n[VERIFIER] {len(past_deadline)} prediction(s) past deadline — verifying...")
                    results = verify_predictions(domain, max_checks=3)
                    for r in results:
                        status_icon = {"confirmed": "✓", "refuted": "✗", "partially_confirmed": "~", "inconclusive": "?"}.get(r.get("status"), "?")
                        print(f"  {status_icon} {r.get('prediction', '?')[:80]} → {r.get('status', '?')}")
        except Exception as e:
            pass  # Non-blocking — verification failure shouldn't stop the loop

    # Step 7: Meta-analysis — evolve strategy if enough data
    # SAFETY: Never evolve while a trial is still being evaluated
    # SAFETY: Never evolve during warmup period (insufficient data)
    current_status = get_strategy_status("researcher", domain)
    in_warmup = WARMUP_APPROVAL_REQUIRED and stats['accepted'] <= WARMUP_OUTPUTS
    if in_warmup:
        remaining_warmup = WARMUP_OUTPUTS - stats['accepted']
        print(f"\n[META-ANALYST] Skipping — domain in warmup mode ({remaining_warmup} more output(s) until warmup completes)")
    elif current_status == "trial":
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

    # Step 8: Auto-prune — periodically clean low-quality outputs
    if AUTO_PRUNE_ENABLED and final_verdict == "accept":
        stats = get_stats(domain)
        total_accepted = stats.get("accepted", 0)
        if total_accepted > 0 and total_accepted % AUTO_PRUNE_EVERY_N == 0:
            print(f"\n[AUTO-PRUNE] Trigger: {total_accepted} accepted outputs (every {AUTO_PRUNE_EVERY_N}). Pruning...")
            prune_result = prune_domain(domain)
            archived = prune_result.get("archived", 0) if prune_result else 0
            if archived > 0:
                print(f"[AUTO-PRUNE] Archived {archived} low-scoring output(s)")
            else:
                print(f"[AUTO-PRUNE] Nothing to prune — all outputs above threshold")

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

    # Step 9: Auto-monitoring — run health check after each loop
    try:
        from monitoring import run_health_check
        health = run_health_check(domain)
        if health and health.get("alerts"):
            print(f"[MONITORING] {len(health['alerts'])} alert(s):")
            for alert in health["alerts"][:3]:
                print(f"  ⚠ {alert}")
    except Exception as e:
        pass  # Non-blocking — monitoring failure shouldn't stop the loop

    return {
        "research": final_research,
        "critique": final_critique,
        "attempts": attempt,
        "stored_at": filepath,
    }


def log_run(domain: str, question: str, attempts: int, research: dict, critique: dict, strategy_version: str):
    """Append a line to the run log. Dual-writes to JSONL and SQLite."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"{domain}.jsonl")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "attempts": attempts,
        "score": critique.get("overall_score", 0),
        "verdict": critique.get("verdict", "unknown"),
        "strategy_version": strategy_version,
        "consensus": research.get("_consensus", False),
        "consensus_level": research.get("consensus_level"),
        "researchers_used": research.get("_researchers_used"),
    }

    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Dual-write to SQLite
    try:
        from db import insert_run_log
        entry["domain"] = domain
        insert_run_log(entry)
    except Exception as e:
        print(f"[DB] \u26a0 Run log write failed (non-blocking): {e}")


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
    parser.add_argument("--kb-versions", action="store_true", help="List knowledge base version history")
    parser.add_argument("--kb-rollback", nargs="?", const="latest", metavar="VERSION", help="Rollback KB to previous version")
    parser.add_argument("--predictions", action="store_true", help="Extract time-bound predictions from KB for verification")
    parser.add_argument("--verify", action="store_true", help="Verify past-deadline predictions against reality")
    parser.add_argument("--prediction-stats", action="store_true", help="Show prediction accuracy stats for a domain")
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
    parser.add_argument("--migrate", action="store_true", help="Migrate JSON/JSONL data to SQLite database")
    parser.add_argument("--alerts", action="store_true", help="Show monitoring alerts")
    parser.add_argument("--check-health", action="store_true", help="Run health checks and monitoring")

    # Agent Hands — Execution Layer
    parser.add_argument("--execute", action="store_true", help="Execute a task using Agent Hands (code generation)")
    parser.add_argument("--goal", default="", help="Task goal for --execute mode (alternative to positional arg)")
    parser.add_argument("--exec-status", action="store_true", help="Show execution memory stats")
    parser.add_argument("--exec-evolve", action="store_true", help="Force execution strategy evolution")
    parser.add_argument("--exec-principles", action="store_true", help="Show learned execution principles")
    parser.add_argument("--exec-lessons", action="store_true", help="Show learned execution patterns/lessons")
    parser.add_argument("--workspace", default="", help="Workspace directory for execution output")
    parser.add_argument("--auto-build", action="store_true", help="Brain→Hands pipeline: generate coding task from KB and execute it")
    parser.add_argument("--build-rounds", type=int, default=1, help="Number of auto-build rounds (default: 1)")
    parser.add_argument("--next-task", action="store_true", help="Show next AI-generated coding task for a domain")
    
    # Web Fetching — Scrapling integration
    parser.add_argument("--crawl", default="", help="Crawl a docs site URL and store content locally")
    parser.add_argument("--crawl-max", type=int, default=20, help="Max pages to crawl (default: 20)")
    parser.add_argument("--crawl-pattern", default="", help="URL regex pattern for crawl (default: same domain)")
    parser.add_argument("--fetch", default="", help="Fetch a single URL and display content")
    parser.add_argument("--crawl-inject", action="store_true", help="Inject crawled docs into KB as claims")
    
    # RAG — Vector Store
    parser.add_argument("--rag-status", action="store_true", help="Show RAG vector store stats")
    parser.add_argument("--rag-rebuild", action="store_true", help="Rebuild RAG index for a domain (or all)")
    parser.add_argument("--rag-search", metavar="QUERY", help="Semantic search across vector store")

    # MCP — Docker Tool Gateway
    parser.add_argument("--mcp-status", action="store_true", help="Show MCP gateway and server status")
    parser.add_argument("--mcp-start", action="store_true", help="Start all MCP servers")
    parser.add_argument("--mcp-stop", action="store_true", help="Stop all MCP servers")
    parser.add_argument("--mcp-tools", action="store_true", help="List all available MCP tools")
    parser.add_argument("--mcp-health", action="store_true", help="Run health checks on MCP servers")

    # Credential Vault — Encrypted secret storage
    parser.add_argument("--vault-store", nargs=2, metavar=("KEY", "VALUE"), help="Store a credential (e.g. --vault-store linkedin_com '{\"email\":...,\"password\":...}')")
    parser.add_argument("--vault-get", metavar="KEY", help="Retrieve a credential (prints value)")
    parser.add_argument("--vault-delete", metavar="KEY", help="Delete a credential")
    parser.add_argument("--vault-list", action="store_true", help="List all credential keys")
    parser.add_argument("--vault-stats", action="store_true", help="Show vault statistics")

    # Stealth Browser
    parser.add_argument("--browser-fetch", metavar="URL", help="Fetch a URL using stealth browser (JS rendering)")
    parser.add_argument("--browser-test", action="store_true", help="Test browser stealth detection")

    # Project Orchestrator — Large project management
    parser.add_argument("--project", metavar="DESCRIPTION", help="Decompose and execute a large project")
    parser.add_argument("--project-status", metavar="PROJECT_ID", help="Show project status", nargs="?", const="latest")
    parser.add_argument("--project-resume", metavar="PROJECT_ID", help="Resume a paused project", nargs="?", const="latest")
    parser.add_argument("--project-approve", metavar="PROJECT_ID", help="Approve current phase of a project", nargs="?", const="latest")
    parser.add_argument("--project-list", action="store_true", help="List all projects")

    # VPS Deploy
    parser.add_argument("--deploy", action="store_true", help="Deploy Agent Brain to VPS")
    parser.add_argument("--deploy-dry-run", action="store_true", help="Show what deploy would do (no changes)")
    parser.add_argument("--deploy-health", action="store_true", help="Run health check on remote VPS")
    parser.add_argument("--deploy-logs", action="store_true", help="View remote VPS logs")
    parser.add_argument("--deploy-schedule", action="store_true", help="Setup/update cron schedule on VPS")
    parser.add_argument("--deploy-unschedule", action="store_true", help="Remove cron schedule from VPS")
    parser.add_argument("--deploy-configure", action="store_true", help="Configure VPS connection")
    parser.add_argument("--deploy-host", default="", help="VPS hostname/IP (use with --deploy-configure)")
    parser.add_argument("--deploy-user", default="", help="SSH user (use with --deploy-configure)")

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
    if getattr(args, 'kb_versions', False):
        _show_kb_versions(args.domain)
        return
    if getattr(args, 'kb_rollback', None):
        _run_kb_rollback(args.domain, args.kb_rollback)
        return
    if getattr(args, 'predictions', False):
        _run_predictions_extract(args.domain)
        return
    if getattr(args, 'verify', False):
        _run_predictions_verify(args.domain)
        return
    if getattr(args, 'prediction_stats', False):
        _show_prediction_stats(args.domain)
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

    if args.migrate:
        _run_migrate()
        return
    if args.alerts:
        _show_alerts()
        return
    if getattr(args, 'check_health', False):
        _run_health_check()
        return

    # --- Agent Hands dispatch ---
    if args.execute:
        goal = args.goal or args.question
        if not goal:
            parser.error("--execute requires a goal: --execute --goal 'Build a todo app' OR --execute 'Build a todo app'")
        _run_execute(args.domain, goal, workspace_dir=args.workspace)
        return
    if getattr(args, 'exec_status', False):
        _show_exec_status(args.domain)
        return
    if getattr(args, 'exec_evolve', False):
        _run_exec_evolve(args.domain)
        return
    if getattr(args, 'exec_principles', False):
        _show_exec_principles()
        return
    if getattr(args, 'exec_lessons', False):
        _show_exec_lessons(args.domain)
        return
    if getattr(args, 'auto_build', False):
        _run_auto_build(args.domain, getattr(args, 'build_rounds', 1), workspace_dir=args.workspace)
        return
    if getattr(args, 'next_task', False):
        _show_next_task(args.domain)
        return
    if getattr(args, 'crawl', ''):
        _run_crawl(args.crawl, args.domain, getattr(args, 'crawl_max', 20), getattr(args, 'crawl_pattern', ''))
        return
    if getattr(args, 'fetch', ''):
        _run_fetch(args.fetch)
        return
    if getattr(args, 'crawl_inject', False):
        _run_crawl_inject(args.domain)
        return
    if getattr(args, 'rag_status', False):
        _show_rag_status()
        return
    if getattr(args, 'rag_rebuild', False):
        _run_rag_rebuild(args.domain)
        return
    if getattr(args, 'rag_search', None):
        _run_rag_search(args.rag_search, args.domain)
        return

    # MCP commands
    if getattr(args, 'mcp_status', False):
        _show_mcp_status()
        return
    if getattr(args, 'mcp_start', False):
        _mcp_start_all()
        return
    if getattr(args, 'mcp_stop', False):
        _mcp_stop_all()
        return
    if getattr(args, 'mcp_tools', False):
        _show_mcp_tools()
        return
    if getattr(args, 'mcp_health', False):
        _mcp_health_check()
        return

    # Credential Vault commands
    if getattr(args, 'vault_store', None):
        _vault_store(args.vault_store[0], args.vault_store[1])
        return
    if getattr(args, 'vault_get', None):
        _vault_get(args.vault_get)
        return
    if getattr(args, 'vault_delete', None):
        _vault_delete(args.vault_delete)
        return
    if getattr(args, 'vault_list', False):
        _vault_list()
        return
    if getattr(args, 'vault_stats', False):
        _vault_stats()
        return

    # Stealth Browser commands
    if getattr(args, 'browser_fetch', None):
        _browser_fetch_url(args.browser_fetch)
        return
    if getattr(args, 'browser_test', False):
        _browser_test_stealth()
        return

    # Project Orchestrator commands
    if getattr(args, 'project', None):
        _run_project(args.project, args.domain, workspace_dir=args.workspace)
        return
    if getattr(args, 'project_status', None):
        _show_project_status(args.project_status)
        return
    if getattr(args, 'project_resume', None):
        _resume_project(args.project_resume)
        return
    if getattr(args, 'project_approve', None):
        _approve_project_phase(args.project_approve)
        return
    if getattr(args, 'project_list', False):
        _list_projects()
        return

    # VPS Deploy commands
    if getattr(args, 'deploy', False) or getattr(args, 'deploy_dry_run', False):
        _run_deploy(dry_run=getattr(args, 'deploy_dry_run', False))
        return
    if getattr(args, 'deploy_health', False):
        _run_deploy_health()
        return
    if getattr(args, 'deploy_logs', False):
        _run_deploy_logs(domain=args.domain)
        return
    if getattr(args, 'deploy_schedule', False):
        _run_deploy_schedule()
        return
    if getattr(args, 'deploy_unschedule', False):
        _run_deploy_unschedule()
        return
    if getattr(args, 'deploy_configure', False):
        _run_deploy_configure(host=args.deploy_host, user=args.deploy_user)
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

    # Balance tracking — compare with Claude console
    balance = check_balance()
    print(f"\n  {'='*50}")
    print(f"  API CREDIT BALANCE")
    print(f"  {'='*50}")
    print(f"    Starting:  ${balance['starting_balance']:.2f}")
    print(f"    Spent:     ${balance['total_spent']:.4f} ({balance['total_calls']} calls)")
    print(f"    Remaining: ${balance['remaining_balance']:.4f} (estimated)")
    print(f"    ⚠ {balance['accuracy_note']}")
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


def _generate_digest(domain: str, round_results: list[dict], dedup_skipped: int = 0) -> dict:
    """
    Generate a run digest summarizing what happened.
    
    Includes: questions researched, scores, strategy changes, alerts, spend.
    Returns dict that can be printed or sent via webhook.
    """
    stats = get_stats(domain)
    daily = get_daily_spend()
    
    # Compute score stats from this run
    scores = [r["score"] for r in round_results if r.get("score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    accepted = sum(1 for r in round_results if r.get("verdict") == "accept")
    rejected = len(round_results) - accepted
    
    # Check for strategy changes
    pending = list_pending("researcher", domain)
    
    # Check recent alerts
    try:
        from db import get_alerts
        recent_alerts = get_alerts(limit=10, severity=None, domain=domain)
    except Exception:
        recent_alerts = []
    
    digest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "rounds_completed": len(round_results),
        "dedup_skipped": dedup_skipped,
        "scores": {
            "avg": round(avg_score, 1),
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "accepted": accepted,
            "rejected": rejected,
        },
        "questions": [r.get("question", "")[:80] for r in round_results],
        "domain_totals": {
            "count": stats["count"],
            "avg_score": round(stats["avg_score"], 1),
            "accepted": stats["accepted"],
        },
        "spend_today_usd": round(daily["total_usd"], 4),
        "pending_strategies": len(pending),
        "recent_alerts": len(recent_alerts),
    }
    
    # Print digest summary
    print(f"\n  ── Run Digest ──")
    print(f"  Avg score this run: {avg_score:.1f} ({accepted} accepted, {rejected} rejected)")
    if dedup_skipped > 0:
        print(f"  Dedup skipped: {dedup_skipped} duplicate question(s)")
    if pending:
        print(f"  ⚠ {len(pending)} pending strategy(ies) await approval")
    if recent_alerts:
        print(f"  ⚠ {len(recent_alerts)} recent alert(s) — run --check-health for details")
    
    # Save digest to log file
    digest_path = os.path.join(LOG_DIR, "digests.jsonl")
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        with open(digest_path, "a") as f:
            f.write(json.dumps(digest) + "\n")
    except Exception as e:
        print(f"  [DIGEST] ⚠ Failed to save digest: {e}")
    
    # Webhook push (if configured)
    webhook_url = os.environ.get("AGENT_BRAIN_WEBHOOK_URL")
    if webhook_url:
        _push_webhook(webhook_url, digest)
    
    return digest


def _push_webhook(url: str, payload: dict):
    """Push a digest payload to a webhook URL (Slack, Discord, etc.)."""
    import urllib.request
    import urllib.error
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 300:
                print(f"  [WEBHOOK] ✓ Digest pushed ({resp.status})")
            else:
                print(f"  [WEBHOOK] ⚠ Unexpected status: {resp.status}")
    except urllib.error.URLError as e:
        print(f"  [WEBHOOK] ⚠ Failed to push: {e}")
    except Exception as e:
        print(f"  [WEBHOOK] ⚠ Error: {e}")


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
    round_results = []
    dedup_skipped = 0
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

        # Dedup check — avoid re-researching known questions
        from memory_store import is_duplicate_question
        from config import AUTO_DEDUP_RETRIES
        is_dup, matched = is_duplicate_question(domain, question, threshold=0.80)
        if is_dup:
            # Retry question generation up to AUTO_DEDUP_RETRIES times
            retried = False
            for dedup_attempt in range(AUTO_DEDUP_RETRIES):
                print(f"[DEDUP] ⚠ Too similar to: {matched[:100]}")
                print(f"[DEDUP] Regenerating question (attempt {dedup_attempt + 2})...")
                question = get_next_question(domain)
                if not question:
                    break
                is_dup, matched = is_duplicate_question(domain, question, threshold=0.80)
                if not is_dup:
                    retried = True
                    print(f"[DEDUP] ✓ New question accepted: {question[:80]}")
                    break
            if not retried:
                print(f"[DEDUP] ⚠ Skipping — all {AUTO_DEDUP_RETRIES + 1} attempts were duplicates")
                dedup_skipped += 1
                continue

        # Stages 3+4+5: Research → Evaluate (handled by run_loop)
        print(f"\n[STAGE 3-5] Researching, evaluating, storing...")
        try:
            result = run_loop(question=question, domain=domain)
        except SystemExit:
            # run_loop calls sys.exit on budget exceeded
            print(f"[AUTO] Stopped — budget exceeded during round {round_num}")
            break

        if result is None:
            print(f"\n[ROUND {round_num}] Research failed — no result returned")
            round_results.append({
                "round": round_num,
                "question": question,
                "score": 0,
                "verdict": "failed",
            })
            continue

        score = result.get("critique", {}).get("overall_score", 0)
        verdict = result.get("critique", {}).get("verdict", "unknown")
        round_results.append({
            "round": round_num,
            "question": question,
            "score": score,
            "verdict": verdict,
        })

        print(f"\n[ROUND {round_num} COMPLETE] Score: {score}/10 — {verdict}")

        if round_num < rounds:
            print(f"\n  Continuing to round {round_num + 1}...")

    # Run claim expiry check after auto rounds
    from memory_store import expire_stale_claims
    expiry = expire_stale_claims(domain)
    if expiry["flagged"] > 0 or expiry["expired"] > 0:
        print(f"\n[CLAIM EXPIRY] Flagged {expiry['flagged']} stale, expired {expiry['expired']} claims")

    # Generate digest
    digest = _generate_digest(domain, round_results, dedup_skipped)

    # Summary
    stats = get_stats(domain)
    daily = get_daily_spend()
    print(f"\n{'='*60}")
    print(f"  AUTO MODE COMPLETE")
    print(f"  Rounds completed: {len(round_results)}/{rounds} ({dedup_skipped} skipped as duplicates)")
    print(f"  Domain '{domain}': {stats['count']} total outputs, avg {stats['avg_score']:.1f}")
    print(f"  Today's spend: ${daily['total_usd']:.4f}")
    print(f"{'='*60}\n")

    return digest


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
                        lambda d=domain: get_next_question(d),
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
                    lambda q=question, d=domain: run_loop(question=q, domain=d),
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


def _show_kb_versions(domain: str):
    """List knowledge base version history."""
    from memory_store import list_kb_versions
    print(f"\n{'='*60}")
    print(f"  KB VERSION HISTORY — Domain: {domain}")
    print(f"{'='*60}\n")

    versions = list_kb_versions(domain)
    if not versions:
        print("  No previous versions found.")
        print("  Versions are created automatically each time the KB is synthesized.")
    else:
        print(f"  {len(versions)} version(s) available:\n")
        for v in versions:
            print(f"    {v['version']}  ({v['claims_count']} claims)")
    print()


def _run_kb_rollback(domain: str, version: str):
    """Roll back knowledge base to a previous version."""
    from memory_store import rollback_knowledge_base, list_kb_versions
    print(f"\n{'='*60}")
    print(f"  KB ROLLBACK — Domain: {domain}")
    print(f"{'='*60}\n")

    if version == "latest":
        versions = list_kb_versions(domain)
        if not versions:
            print("  No previous versions found. Nothing to roll back to.")
            print()
            return
        version = None  # rollback_knowledge_base defaults to most recent

    result = rollback_knowledge_base(domain, version)
    if result["status"] == "success":
        print(f"  Rolled back to: {result['version']}")
        print(f"  Claims restored: {result['claims_count']}")
    else:
        print(f"  Error: {result['error']}")
    print()


def _run_predictions_extract(domain: str):
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


def _run_predictions_verify(domain: str):
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


def _show_prediction_stats(domain: str):
    """Show prediction accuracy statistics for a domain."""
    from agents.verifier import load_predictions, get_verification_stats
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
    from datetime import date
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


def _run_migrate():
    """Migrate JSON/JSONL data to SQLite."""
    from db import migrate_from_json
    from config import MEMORY_DIR, LOG_DIR as _LOG_DIR

    print(f"\n{'='*60}")
    print(f"  DATABASE MIGRATION — JSON → SQLite")
    print(f"{'='*60}\n")
    result = migrate_from_json(MEMORY_DIR, _LOG_DIR, verbose=True)
    print(f"\n{'='*60}\n")


def _show_alerts():
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


def _run_health_check():
    """Run health checks and score trend monitoring."""
    from monitoring import run_health_check

    print(f"\n{'='*60}")
    print(f"  HEALTH CHECK + MONITORING")
    print(f"{'='*60}\n")

    result = run_health_check(verbose=True)

    print(f"\n  Status: {result['status'].upper()}")
    if result.get("alerts_generated", 0) > 0:
        print(f"  New alerts: {result['alerts_generated']}")
    print(f"\n{'='*60}\n")


# ============================================================
# Agent Hands — Execution Functions
# ============================================================

def _show_next_task(domain: str):
    """Show the next AI-generated coding task for a domain."""
    from hands.task_generator import generate_tasks

    print(f"\n{'='*60}")
    print(f"  NEXT CODING TASKS — Domain: {domain}")
    print(f"{'='*60}\n")

    tasks = generate_tasks(domain)
    if not tasks:
        print("  Failed to generate tasks. Need more KB data?")
        print(f"  Run some research first: python main.py --auto --domain {domain}")
        return

    for i, task in enumerate(tasks):
        priority = task.get("priority", i + 1)
        complexity = task.get("expected_complexity", "?")
        print(f"  [{priority}] ({complexity}) {task.get('task', '?')}")
        print(f"      Reasoning: {task.get('reasoning', '?')[:100]}")
        if task.get("applies_claims"):
            print(f"      Applies KB: {', '.join(str(c)[:50] for c in task['applies_claims'][:3])}")
        if task.get("builds_on"):
            print(f"      Builds on: {task['builds_on'][:80]}")
        print()

    print(f"  Execute the top task:")
    top = tasks[0].get("task", "")
    print(f"    python main.py --domain {domain} --execute --goal \"{top[:80]}\"")
    print(f"\n  Or run auto-build to generate + execute automatically:")
    print(f"    python main.py --domain {domain} --auto-build")


def _run_auto_build(domain: str, rounds: int = 1, workspace_dir: str = ""):
    """
    Brain→Hands automated pipeline.
    
    The system:
    1. Reads domain KB + execution history
    2. Generates the best next coding task (from task_generator)
    3. Executes it via Hands (plan → execute → validate → store)
    4. Feeds results back into the learning loop
    5. Repeats for N rounds

    This is the full research→build cycle. The system compounds knowledge
    into working software.
    """
    from hands.task_generator import get_next_task
    from hands.exec_memory import get_exec_stats

    print(f"\n{'='*60}")
    print(f"  BRAIN→HANDS AUTO-BUILD PIPELINE")
    print(f"  Domain: {domain}")
    print(f"  Rounds: {rounds}")
    print(f"{'='*60}\n")

    round_results = []

    for round_num in range(1, rounds + 1):
        print(f"\n{'─'*50}")
        print(f"  BUILD ROUND {round_num}/{rounds}")
        print(f"{'─'*50}\n")

        # Budget check
        budget = check_budget()
        if not budget["within_budget"]:
            print(f"[BUDGET] ✗ BLOCKED — daily limit reached after {round_num - 1} rounds")
            break
        print(f"[BUDGET] ${budget['remaining']:.4f} remaining")

        # Step 1: Generate coding task from KB
        print(f"\n[TASK-GEN] Generating coding task from domain knowledge...")
        task = get_next_task(domain)

        if not task:
            # Fallback: if no KB, use a domain-appropriate seed task
            stats = get_exec_stats(domain)
            if stats["count"] == 0:
                task = _get_seed_build_task(domain)
                print(f"[TASK-GEN] Using seed task for new domain")
            else:
                print(f"[TASK-GEN] Failed to generate task. Stopping.")
                break

        print(f"\n[TASK] → {task}")

        # Step 2: Execute via Hands
        print(f"\n[EXECUTE] Running Hands pipeline...")
        _run_execute(domain, task, workspace_dir=workspace_dir)

        # Track result
        stats = get_exec_stats(domain)
        round_results.append({
            "round": round_num,
            "task": task[:200],
            "total_executions": stats["count"],
            "avg_score": stats["avg_score"],
        })

        print(f"\n[ROUND {round_num}] Complete — {stats['count']} total executions, avg {stats['avg_score']:.1f}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  AUTO-BUILD COMPLETE")
    print(f"  Rounds completed: {len(round_results)}/{rounds}")
    if round_results:
        final_stats = get_exec_stats(domain)
        print(f"  Total executions: {final_stats['count']}")
        print(f"  Average score: {final_stats['avg_score']:.1f}")
        print(f"  Accepted: {final_stats['accepted']}, Rejected: {final_stats['rejected']}")
    daily = get_daily_spend()
    print(f"  Daily spend: ${daily:.4f}")
    print(f"{'='*60}\n")


def _get_seed_build_task(domain: str) -> str:
    """Generate a reasonable seed task for a domain with no history."""
    seed_tasks = {
        "nextjs-react": (
            "Build a TypeScript React component library with: a reusable Button component "
            "with variants (primary, secondary, outline), a Card component with header/body/footer slots, "
            "and a Modal component with open/close animation. Include comprehensive unit tests with Jest "
            "and React Testing Library. Export all components with proper TypeScript types."
        ),
        "saas-building": (
            "Build a TypeScript REST API authentication module with: user registration with email validation, "
            "login with JWT token generation, token refresh endpoint, and middleware for protected routes. "
            "Include comprehensive tests. Use proper error handling and input validation."
        ),
        "python-backend": (
            "Build a Python async task queue library with: task registration decorators, "
            "priority-based scheduling, retry with exponential backoff, dead letter queue for failed tasks, "
            "and a simple in-memory broker. Include comprehensive pytest tests."
        ),
        "growth-hacking": (
            "Build a TypeScript analytics event tracking library with: typed event definitions, "
            "batch processing for network efficiency, local storage queue for offline support, "
            "automatic page view and click tracking, and a debug mode. Include comprehensive tests."
        ),
    }

    return seed_tasks.get(domain, (
        f"Build a well-structured TypeScript utility library for the {domain} domain "
        f"with clean exports, comprehensive error handling, full unit tests, "
        f"and proper TypeScript types. Include at least 3 core functions and 20+ test cases."
    ))


def _run_execute(domain: str, goal: str, workspace_dir: str = ""):
    """
    Execute a task using Agent Hands.
    
    Pipeline: Plan → Execute → Validate → (retry if needed) → Store
    """
    from hands.planner import plan as create_plan_hands
    from hands.executor import execute_plan
    from hands.validator import validate_execution, identify_failing_steps
    from hands.exec_memory import save_exec_output, get_exec_stats
    from hands.tools.registry import create_default_registry
    from hands.workspace_diff import snapshot_workspace, compute_diff, format_diff_summary
    from hands.plan_cache import PlanCache
    from hands.checkpoint import ExecutionCheckpoint
    from hands.pattern_learner import PatternLearner
    from hands.planner import plan_repair
    from hands.artifact_tracker import ArtifactQualityDB, score_artifacts
    from hands.code_exemplars import CodeExemplarStore
    from hands.output_polisher import polish_artifacts, format_polish_log
    from hands.feedback_cache import FeedbackCache
    from hands.file_repair import identify_weak_artifacts, repair_files
    from hands.retry_advisor import recommend_strategy, should_skip_strategy, RetryRecommendation
    import config as _cfg

    # Budget check
    budget = check_budget()
    if not budget["within_budget"]:
        print(f"\n[BUDGET] Blocked — daily limit reached")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  AGENT HANDS — Execution Mode")
    print(f"  Domain: {domain}")
    print(f"  Goal: {goal}")
    print(f"  Budget: ${budget['remaining']:.4f} remaining")
    print(f"{'='*60}\n")

    # Set up workspace
    if not workspace_dir:
        workspace_dir = os.path.join(os.path.dirname(__file__), "output", domain)
    workspace_dir = os.path.realpath(workspace_dir)
    os.makedirs(workspace_dir, exist_ok=True)
    print(f"[WORKSPACE] {workspace_dir}")

    # Dynamically allow the workspace dir for file operations
    if _cfg.EXEC_ALLOWED_DIRS is None:
        _cfg.EXEC_ALLOWED_DIRS = [workspace_dir]
    elif workspace_dir not in _cfg.EXEC_ALLOWED_DIRS:
        _cfg.EXEC_ALLOWED_DIRS = list(_cfg.EXEC_ALLOWED_DIRS) + [workspace_dir]

    # Detect if workspace is an existing repo
    is_repo = os.path.isdir(os.path.join(workspace_dir, ".git"))
    if is_repo:
        print(f"[WORKSPACE] Detected existing git repository")

    # Create tool registry
    registry = create_default_registry()
    tools_desc = registry.get_tool_descriptions()
    print(f"[TOOLS] {', '.join(registry.list_tools())}")

    # Load execution strategy (if exists)
    strategy, strategy_version = get_strategy("executor", domain)
    if strategy:
        print(f"[EXEC-STRATEGY] Loaded: {strategy_version}")
    else:
        # Use template as seed strategy
        from hands.exec_templates import get_template
        strategy = get_template(domain)
        strategy_version = "template"
        print(f"[EXEC-STRATEGY] Using template for '{domain}' (no evolved strategy yet)")

    # Collect strategy context sources (assembled with budget later)
    _raw_base_strategy = strategy or ""
    _raw_principles = ""
    _raw_lessons = ""
    _raw_quality_warnings = ""

    # Cross-domain execution principles (if available)
    try:
        from hands.exec_cross_domain import get_principles_for_domain
        _raw_principles = get_principles_for_domain(domain) or ""
        if _raw_principles:
            print(f"[EXEC-PRINCIPLES] Loaded cross-domain execution principles")
    except Exception:
        pass  # Cross-domain learning is optional

    # Learned execution lessons (from pattern_learner)
    _raw_lessons = pattern_learner.format_lessons_for_prompt(domain=domain) or ""
    if _raw_lessons:
        lesson_count = len(pattern_learner.get_lessons(domain=domain))
        print(f"[LESSONS] Loaded {lesson_count} learned execution lessons")

    # Load domain knowledge from Brain (if available)
    domain_knowledge = ""
    try:
        from memory_store import load_knowledge_base
        kb = load_knowledge_base(domain)
        if kb and kb.get("claims"):
            claims_text = []
            for claim in kb["claims"][:15]:
                claims_text.append(f"- {claim.get('claim', '')}")
            domain_knowledge = "\n".join(claims_text)
            print(f"[KB] Loaded {len(kb['claims'])} claims from Brain's knowledge base")
    except Exception:
        pass

    from config import EXEC_MAX_RETRIES, EXEC_QUALITY_THRESHOLD

    # Initialize plan cache, checkpoint, and pattern learner
    cache_path = os.path.join(os.path.dirname(__file__), "exec_memory", "_plan_cache.json")
    plan_cache = PlanCache(cache_path)
    cp_dir = os.path.join(os.path.dirname(__file__), "exec_memory", "_checkpoints")
    checkpoint = ExecutionCheckpoint(cp_dir)
    learner_path = os.path.join(os.path.dirname(__file__), "exec_memory", "_patterns.json")
    pattern_learner = PatternLearner(learner_path)

    # Initialize artifact quality tracker and exemplar store
    quality_db_path = os.path.join(os.path.dirname(__file__), "exec_memory", "_artifact_quality.json")
    artifact_quality_db = ArtifactQualityDB(quality_db_path)
    exemplar_path = os.path.join(os.path.dirname(__file__), "exec_memory", "_exemplars.json")
    exemplar_store = CodeExemplarStore(exemplar_path)

    # Initialize feedback cache (persistent per-dimension failure signals)
    feedback_cache_path = os.path.join(os.path.dirname(__file__), "exec_memory", "_feedback_cache.json")
    feedback_cache = FeedbackCache(feedback_cache_path)

    # Artifact quality warnings (collected for assembler)
    _raw_quality_warnings = artifact_quality_db.format_for_prompt(domain) or ""
    if _raw_quality_warnings:
        print(f"[ARTIFACT-QUALITY] Loaded quality warnings for weak archetypes")

    # Check for resumable checkpoint
    resume_info = checkpoint.get_resume_info(domain)
    if resume_info and resume_info["goal"] == goal:
        print(f"[CHECKPOINT] Found resumable execution ({resume_info['completed_step_count']} steps done)")
        print(f"  Started: {resume_info['started_at']}")

    attempt = 0
    previous_feedback = None
    final_plan = None
    final_report = None
    final_validation = None
    _use_surgical_retry = False
    _resume_data = None

    while attempt <= EXEC_MAX_RETRIES:
        attempt += 1
        print(f"\n--- Attempt {attempt}/{EXEC_MAX_RETRIES + 1} ---\n")

        # Step 1: Plan (with cache)
        cached_plan = None
        if attempt == 1 and not previous_feedback:
            cached_plan = plan_cache.get(goal, domain)
            if cached_plan:
                print(f"[PLAN-CACHE] Hit! Reusing plan from previous score {cached_plan.get('score', '?')}/10")
                plan_data = cached_plan["plan"]
            else:
                print("[PLANNER] Decomposing task into steps...")
        else:
            print("[PLANNER] Decomposing task into steps (retry — no cache)...")

        if not cached_plan:
            context = ""
            if previous_feedback:
                context = f"PREVIOUS ATTEMPT FEEDBACK (fix these issues):\n{previous_feedback}"

            # Inject persistent feedback from previous executions
            feedback_text = feedback_cache.get_for_planner(domain) or ""
            if feedback_text:
                print(f"[FEEDBACK] Injected recurring quality issue warnings")

            # Assemble strategy with budget-aware deduplication (planner gets 4000 chars)
            from hands.strategy_assembler import assemble as assemble_strategy, PLANNER_BUDGET
            planner_assembly = assemble_strategy(
                budget=PLANNER_BUDGET,
                base_strategy=_raw_base_strategy,
                principles=_raw_principles,
                lessons=_raw_lessons,
                quality_warnings=_raw_quality_warnings,
                feedback=feedback_text,
            )
            if planner_assembly.dropped:
                print(f"[STRATEGY] Budget: {planner_assembly.used}/{planner_assembly.budget} chars, dropped: {', '.join(planner_assembly.dropped)}")
            if planner_assembly.was_deduped:
                print(f"[STRATEGY] Deduplicated overlapping advice across sources")

            plan_data = create_plan_hands(
                goal=goal,
                tools_description=tools_desc,
                domain=domain,
                domain_knowledge=domain_knowledge,
                execution_strategy=planner_assembly.text,
                context=context,
                workspace_dir=workspace_dir,
                available_tools=registry.list_tools(),
            )

        if not plan_data:
            print("[PLANNER] Failed to generate plan")
            if attempt <= EXEC_MAX_RETRIES:
                previous_feedback = "Planning failed. Simplify the approach."
                continue
            break

        steps_count = len(plan_data.get("steps", []))
        complexity = plan_data.get("estimated_complexity", "?")
        print(f"[PLANNER] Generated {steps_count}-step plan (complexity: {complexity})")
        for step in plan_data.get("steps", []):
            crit = "!" if step.get("criticality", "required") == "required" else "?"
            print(f"  {step.get('step_number', '?')}{crit} [{step.get('tool', '?')}] {step.get('description', '')[:80]}")

        final_plan = plan_data

        # Step 1.5: Pre-flight validation (zero-cost structural checks)
        from hands.plan_preflight import preflight_check
        preflight = preflight_check(
            plan=plan_data,
            domain=domain,
            pattern_learner=pattern_learner,
            artifact_quality_db=artifact_quality_db,
            cost_ceiling=float(os.environ.get("MAX_EXECUTION_COST", "0.50")),
        )
        if preflight.issues:
            for issue in preflight.blockers:
                print(f"  [PREFLIGHT] BLOCKER: {issue.message}")
            for issue in preflight.warnings:
                print(f"  [PREFLIGHT] WARNING: {issue.message}")
        if not preflight.passed:
            print(f"  [PREFLIGHT] Plan blocked — {len(preflight.blockers)} blocker(s)")
            if attempt <= EXEC_MAX_RETRIES:
                previous_feedback = f"Plan pre-flight check failed:\n{preflight.format()}\nFix these issues."
                continue
            break
        elif preflight.warnings:
            print(f"  [PREFLIGHT] {len(preflight.warnings)} warning(s) — proceeding")
        else:
            print(f"  [PREFLIGHT] All checks passed")

        # Assemble executor strategy with exemplars (3000 char budget)
        from hands.strategy_assembler import assemble as assemble_strategy, EXECUTOR_BUDGET
        _raw_exemplars = ""
        predicted_archetypes = exemplar_store.predict_archetypes(plan_data)
        if predicted_archetypes:
            exemplars = exemplar_store.get_exemplars(domain, archetypes=predicted_archetypes)
            if exemplars:
                _raw_exemplars = exemplar_store.format_for_prompt(exemplars) or ""
                if _raw_exemplars:
                    print(f"[EXEMPLARS] {len(exemplars)} code examples for archetypes: {', '.join(e['archetype'] for e in exemplars)}")

        executor_assembly = assemble_strategy(
            budget=EXECUTOR_BUDGET,
            base_strategy=_raw_base_strategy,
            principles=_raw_principles,
            lessons=_raw_lessons,
            quality_warnings=_raw_quality_warnings,
            exemplars=_raw_exemplars,
        )
        strategy_with_exemplars = executor_assembly.text
        if executor_assembly.dropped:
            print(f"[EXEC-STRATEGY] Budget: {executor_assembly.used}/{executor_assembly.budget} chars, dropped: {', '.join(executor_assembly.dropped)}")

        # Snapshot workspace before execution
        ws_before = snapshot_workspace(workspace_dir) if workspace_dir else {}

        # Create checkpoint for crash recovery
        checkpoint.create(domain, goal, plan_data)

        # Step 2: Execute
        report = execute_plan(
            plan=plan_data,
            registry=registry,
            domain=domain,
            execution_strategy=strategy_with_exemplars,
            workspace_dir=workspace_dir,
            resume_from=_resume_data if _use_surgical_retry else None,
        )
        # Reset surgical retry state after use
        _use_surgical_retry = False
        _resume_data = None

        final_report = report

        # Compute workspace diff
        workspace_changes = {}
        if workspace_dir and ws_before:
            ws_after = snapshot_workspace(workspace_dir)
            workspace_changes = compute_diff(ws_before, ws_after)
            diff_summary = format_diff_summary(workspace_changes)
            print(f"\n[DIFF] {diff_summary}")
            report["workspace_changes"] = workspace_changes

        completed = report.get("completed_steps", 0)
        failed = report.get("failed_steps", 0)
        artifacts = report.get("artifacts", [])
        print(f"\n[EXECUTOR] Steps: {completed} completed, {failed} failed")
        if artifacts:
            print(f"[EXECUTOR] Artifacts: {', '.join(artifacts[:10])}")

        # Step 2.5: Polish artifacts before validation (zero-cost rule-based fixes)
        if artifacts:
            polish_result = polish_artifacts(artifacts, domain=domain)
            polish_log = format_polish_log(polish_result)
            if polish_log:
                print(f"\n{polish_log}")

        # Step 3: Validate
        print("\n[VALIDATOR] Evaluating execution quality...")
        validation = validate_execution(
            goal=goal,
            plan=plan_data,
            execution_report=report,
            domain=domain,
            domain_knowledge=domain_knowledge,
        )

        final_validation = validation

        score = validation.get("overall_score", 0)
        verdict = validation.get("verdict", "unknown")
        print(f"[VALIDATOR] Score: {score}/10 — Verdict: {verdict}")

        scores = validation.get("scores", {})
        if scores:
            for dim, val in scores.items():
                print(f"           {dim}: {val}/10")

        for s in validation.get("strengths", []):
            print(f"  + {s}")
        for w in validation.get("weaknesses", []):
            print(f"  - {w}")
        for ci in validation.get("critical_issues", []):
            print(f"  ! CRITICAL: {ci}")

        # Quality gate
        if score >= EXEC_QUALITY_THRESHOLD:
            print(f"\n[QUALITY] Accepted (score {score} >= threshold {EXEC_QUALITY_THRESHOLD})")
            # Cache the successful plan
            plan_cache.put(goal, domain, plan_data, score)
            # Clear checkpoint — execution complete
            checkpoint.mark_complete(domain, True)
            checkpoint.clear(domain)
            # Record positive feedback + auto-clear improved dimensions
            feedback_cache.auto_clear(domain, validation)
            break
        else:
            print(f"\n[QUALITY] Rejected (score {score} < threshold {EXEC_QUALITY_THRESHOLD})")

            # Record dimension-level failure feedback for future planners
            recorded_dims = feedback_cache.record(domain, validation)
            if recorded_dims:
                print(f"  [FEEDBACK] Recorded weak dimensions: {', '.join(recorded_dims)}")

            if attempt <= EXEC_MAX_RETRIES:
                previous_feedback = validation.get("actionable_feedback", "Improve quality.")
                if validation.get("critical_issues"):
                    previous_feedback += " CRITICAL: " + "; ".join(validation["critical_issues"])

                # Classify failure and get retry recommendation
                weak_artifacts = identify_weak_artifacts(
                    validation, report.get("artifacts", []), threshold=EXEC_QUALITY_THRESHOLD
                )
                strong_count = len(report.get("artifacts", [])) - len(weak_artifacts)

                failing = identify_failing_steps(
                    validation,
                    report.get("step_results", []),
                    plan_data.get("steps", []),
                )

                recommendation = recommend_strategy(
                    validation,
                    attempt=attempt,
                    max_retries=EXEC_MAX_RETRIES,
                    has_weak_artifacts=bool(weak_artifacts) and strong_count > len(weak_artifacts),
                    has_failing_steps=bool(failing) and len(failing) < len(plan_data.get("steps", [])),
                )
                print(f"  [RETRY ADVISOR] {recommendation.failure_class} failure → {recommendation.strategy} (confidence={recommendation.confidence:.0%})")
                if recommendation.skip_strategies:
                    print(f"  [RETRY ADVISOR] Skipping: {', '.join(recommendation.skip_strategies)}")

                # Strategy 1: Targeted file repair (cheapest — single Haiku call ~$0.003)
                if not should_skip_strategy(recommendation, RetryRecommendation.FILE_REPAIR):
                    if weak_artifacts and strong_count > len(weak_artifacts):
                        print(f"  [FILE REPAIR] {len(weak_artifacts)} file(s) need fixes, {strong_count} are good")
                        repair_result = repair_files(
                            files_to_fix=weak_artifacts,
                            goal=goal,
                            plan=plan_data,
                            domain=domain,
                            workspace_dir=workspace_dir,
                        )
                        if repair_result.get("files_fixed", 0) > 0:
                            print(f"  [FILE REPAIR] Fixed {repair_result['files_fixed']} file(s) (${repair_result.get('cost', 0):.4f})")
                            for d in repair_result.get("details", []):
                                if d.get("fixed"):
                                    print(f"    ✓ {d['path']}: {', '.join(d.get('changes', []))[:80]}")
                            # Re-validate with fixed files (skip re-execution)
                            continue
                        else:
                            print(f"  [FILE REPAIR] Could not fix files — trying next strategy")

                # Strategy 2: Surgical retry — only redo failing steps
                if not should_skip_strategy(recommendation, RetryRecommendation.SURGICAL):
                    if failing and len(failing) < len(plan_data.get("steps", [])):
                        print(f"  [SURGICAL RETRY] {len(failing)} steps need repair: {failing}")
                        repair = plan_repair(
                            original_plan=plan_data,
                            failing_steps=failing,
                            feedback=previous_feedback,
                            tools_description=tools_desc,
                            completed_steps=report.get("step_results", []),
                            domain=domain,
                            workspace_dir=workspace_dir,
                        )
                        if repair:
                            # Use repair plan + pass successful steps as resume_from
                            plan_data = repair
                            _use_surgical_retry = True
                            _resume_data = {
                                "completed_steps": [
                                    sr for sr in report.get("step_results", [])
                                    if sr.get("success") and sr.get("step") not in failing
                                ],
                                "artifacts": [
                                    a for sr in report.get("step_results", [])
                                    if sr.get("success") and sr.get("step") not in failing
                                    for a in sr.get("artifacts", [])
                                ],
                            }
                            print(f"  [SURGICAL RETRY] Repair plan: {len(repair.get('steps', []))} steps")
                            continue
                        else:
                            print(f"  [SURGICAL RETRY] Repair plan failed — falling back to full replan")

                print(f"  Retrying with feedback...")
            else:
                print(f"  Max retries reached. Storing as-is.")
                checkpoint.mark_complete(domain, False)
                checkpoint.clear(domain)

    # Step 4: Store result
    if final_plan and final_report and final_validation:
        filepath = save_exec_output(
            domain=domain,
            goal=goal,
            plan=final_plan,
            execution_report=final_report,
            validation=final_validation,
            attempt=attempt,
            strategy_version=strategy_version,
        )
        print(f"\n[MEMORY] Saved execution output: {filepath}")

    # Step 4.5: Track artifact quality and extract exemplars
    if final_plan and final_report and final_validation:
        try:
            scored_arts = score_artifacts(
                final_validation,
                final_report.get("step_results", []),
                final_report.get("artifacts", []),
            )
            if scored_arts:
                artifact_quality_db.update(domain, scored_arts)
                weak = artifact_quality_db.get_weak_archetypes(domain)
                if weak:
                    weak_info = ", ".join(
                        w["archetype"] + "(" + str(w["avg_score"]) + ")"
                        for w in weak[:3]
                    )
                    print(f"[ARTIFACT-QUALITY] Weak archetypes: {weak_info}")

                # Extract exemplars from accepted executions
                if final_validation.get("verdict") == "accept":
                    stored = exemplar_store.extract_and_store(domain, scored_arts)
                    if stored:
                        print(f"[EXEMPLARS] Stored {stored} new code exemplars from this execution")
        except Exception as e:
            print(f"[ARTIFACT-QUALITY] Error: {e}")

    # Step 5: Learn patterns from this execution
    if final_plan and final_report and final_validation:
        exec_output_for_learning = {
            "domain": domain,
            "goal": goal,
            "overall_score": final_validation.get("overall_score", 0),
            "accepted": final_validation.get("verdict") == "accept",
            "execution_report": final_report,
            "plan": final_plan,
            "validation": final_validation,
        }
        new_lessons = pattern_learner.analyze_execution(exec_output_for_learning)
        # Also extract plan-level patterns from successful executions
        plan_lessons = pattern_learner.analyze_plan_structure(exec_output_for_learning)
        all_new = new_lessons + plan_lessons
        if all_new:
            print(f"[PATTERN-LEARNER] Extracted {len(all_new)} new patterns:")
            for lesson in all_new[:5]:
                print(f"  • {lesson[:100]}")

    # Check if exec strategy evolution is due
    stats = get_exec_stats(domain)
    from config import EXEC_EVOLVE_EVERY_N
    if stats["count"] > 0 and stats["count"] % EXEC_EVOLVE_EVERY_N == 0:
        print(f"\n[EXEC-META] Evolution due ({stats['count']} outputs, every {EXEC_EVOLVE_EVERY_N})")
        _run_exec_evolve(domain)

    # Extract cross-domain principles from high-scoring executions
    if final_validation and final_validation.get("overall_score", 0) >= EXEC_QUALITY_THRESHOLD:
        try:
            from hands.exec_cross_domain import extract_exec_principles
            new_p = extract_exec_principles(domain, min_outputs=3)
            if new_p:
                print(f"[EXEC-PRINCIPLES] Extracted {len(new_p)} new execution principles from '{domain}'")
        except Exception:
            pass  # Non-critical

    # Summary
    daily = get_daily_spend()
    print(f"\n{'='*60}")
    print(f"  EXECUTION COMPLETE")
    print(f"  Score: {final_validation.get('overall_score', 0) if final_validation else 0}/10")
    print(f"  Artifacts: {len(final_report.get('artifacts', [])) if final_report else 0}")
    print(f"  Domain '{domain}': {stats['count']} total executions, avg {stats['avg_score']:.1f}")
    print(f"  Daily spend: ${daily:.4f}")
    print(f"{'='*60}\n")


def _show_exec_status(domain: str):
    """Show execution memory stats with full analytics."""
    from hands.exec_memory import get_exec_stats, load_exec_outputs
    from hands.exec_analytics import analyze_executions, format_analytics_report

    print(f"\n{'='*60}")
    print(f"  EXECUTION STATUS — Domain: {domain}")
    print(f"{'='*60}\n")

    stats = get_exec_stats(domain)
    if stats["count"] == 0:
        print(f"  No execution outputs yet for domain '{domain}'.")
        print(f"  Run: python main.py --domain {domain} --execute --goal 'Your task here'")
        return

    # Full analytics
    analytics = analyze_executions(domain)
    print(format_analytics_report(analytics))

    # Show recent outputs
    outputs = load_exec_outputs(domain)
    print(f"\n  Recent executions:")
    for o in outputs[-5:]:
        score = o.get("overall_score", 0)
        goal = o.get("goal", "?")[:60]
        verdict = o.get("verdict", "?")
        ts = o.get("timestamp", "?")[:10]
        print(f"    {ts} | {score}/10 ({verdict}) | {goal}")

    print(f"\n{'='*60}\n")


def _run_exec_evolve(domain: str):
    """Force execution strategy evolution."""
    from hands.exec_meta import analyze_and_evolve_exec

    print(f"\n{'='*60}")
    print(f"  EXEC META-ANALYST — Strategy Evolution")
    print(f"  Domain: {domain}")
    print(f"{'='*60}\n")

    result = analyze_and_evolve_exec(domain)
    if not result:
        print("  Not enough data or evolution failed.")
        return

    print(f"\n  New version: {result['new_version']} (pending approval)")
    print(f"  Run: python main.py --domain {domain} --approve {result['new_version']}")


def _show_exec_principles():
    """Show learned execution principles."""
    from hands.exec_cross_domain import load_exec_principles

    print(f"\n{'='*60}")
    print(f"  LEARNED EXECUTION PRINCIPLES")
    print(f"{'='*60}\n")

    principles = load_exec_principles()
    if not principles:
        print("  No execution principles extracted yet.")
        print("  Principles are extracted after 3+ high-scoring executions in a domain.")
        return

    for i, p in enumerate(principles, 1):
        domains = ", ".join(p.get("domains_observed", ["general"]))
        evidence = p.get("evidence_count", 1)
        category = p.get("category", "general")
        print(f"  {i}. [{category}] {p.get('principle', '?')}")
        print(f"     Evidence: {evidence} | Domains: {domains}")
        if p.get("evidence"):
            print(f"     Detail: {p['evidence'][:120]}")
        print()

    print(f"  Total: {len(principles)} principles")


def _show_exec_lessons(domain: str):
    """Show learned execution patterns/lessons."""
    from hands.pattern_learner import PatternLearner

    print(f"\n{'='*60}")
    print(f"  EXECUTION LESSONS — Domain: {domain or 'all'}")
    print(f"{'='*60}\n")

    learner_path = os.path.join(os.path.dirname(__file__), "exec_memory", "_patterns.json")
    learner = PatternLearner(learner_path)

    # Get all lessons (not just high-evidence ones)
    all_lessons = learner._lessons
    domain_lessons = [l for l in all_lessons if l.domain == domain or not domain]

    if not domain_lessons:
        print("  No execution lessons learned yet.")
        print("  Lessons are extracted after each execution.")
        return

    # Group by category
    by_category = {}
    for lesson in domain_lessons:
        cat = lesson.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(lesson)

    for cat, lessons in sorted(by_category.items()):
        print(f"  [{cat.upper()}]")
        for lesson in sorted(lessons, key=lambda l: l.evidence_count, reverse=True):
            impact = "+" if lesson.success_impact > 0 else "-" if lesson.success_impact < 0 else "~"
            print(f"    {impact} {lesson.lesson[:100]}")
            print(f"      Evidence: {lesson.evidence_count}x | Impact: {lesson.success_impact:+.1f}")
        print()

    stats = learner.stats()
    print(f"  Total: {stats['total_lessons']} lessons, {stats['high_evidence']} with strong evidence")


def _run_crawl(url: str, domain: str, max_pages: int, url_pattern: str):
    """Crawl a documentation site and store content locally."""
    from tools.web_fetcher import crawl_docs_site
    import os
    
    output_dir = os.path.join(os.path.dirname(__file__), "crawl_data", domain or "general")
    
    print(f"\n{'='*60}")
    print(f"CRAWLING: {url}")
    print(f"  Domain: {domain or 'general'}")
    print(f"  Max pages: {max_pages}")
    if url_pattern:
        print(f"  URL pattern: {url_pattern}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")
    
    pages = crawl_docs_site(
        start_url=url,
        max_pages=max_pages,
        url_pattern=url_pattern or None,
        output_dir=output_dir,
    )
    
    total_chars = sum(p.get("content_length", 0) for p in pages)
    print(f"\n{'='*60}")
    print(f"CRAWL COMPLETE")
    print(f"  Pages crawled: {len(pages)}")
    print(f"  Total content: {total_chars:,} chars")
    print(f"  Saved to: {output_dir}")
    print(f"{'='*60}")


def _run_fetch(url: str):
    """Fetch a single URL and display content."""
    from tools.web_fetcher import fetch_page
    
    print(f"\nFetching: {url}")
    result = fetch_page(url)
    
    if not result:
        print("  FAILED — could not fetch page")
        return
    
    print(f"  Title: {result['title']}")
    print(f"  Content: {result['content_length']} chars")
    print(f"  Headings: {len(result['headings'])}")
    print(f"  Code blocks: {len(result['code_blocks'])}")
    print(f"\n--- Content Preview (first 1000 chars) ---")
    print(result['content'][:1000])
    if result['headings']:
        print(f"\n--- Headings ---")
        for h in result['headings'][:15]:
            print(f"  - {h}")


def _run_crawl_inject(domain: str):
    """Inject crawled documentation into knowledge base."""
    from tools.crawl_to_kb import inject_crawl_claims_into_kb
    
    print(f"\n{'='*60}")
    print(f"INJECTING CRAWL DATA → KB")
    print(f"  Domain: {domain}")
    print(f"{'='*60}\n")
    
    result = inject_crawl_claims_into_kb(domain)
    
    print(f"\nResult:")
    print(f"  Total claims extracted: {result['total_claims']}")
    print(f"  Injected into KB: {result['injected']}")
    print(f"  Skipped (duplicates): {result['skipped']}")
    
    if result['injected'] > 0:
        print(f"\n  ✓ KB updated. Run: python main.py --status --domain {domain}")
    else:
        print(f"\n  No new claims to inject. Run --crawl first to gather docs.")


def _show_rag_status():
    """Show RAG vector store statistics."""
    print(f"\n{'='*60}")
    print(f"  RAG VECTOR STORE STATUS")
    print(f"{'='*60}\n")
    
    try:
        from rag.vector_store import get_collection_stats
        stats = get_collection_stats()
        
        if "error" in stats:
            print(f"  Error: {stats['error']}")
            return
        
        print(f"  Claims indexed:    {stats['claims_count']}")
        print(f"  Questions indexed: {stats['questions_count']}")
        print(f"  Storage:           {stats['vectordb_path']}")
        
        # Check RAG config
        from config import RAG_ENABLED, EMBEDDING_MODEL
        print(f"\n  RAG enabled:       {RAG_ENABLED}")
        print(f"  Embedding model:   {EMBEDDING_MODEL}")
        
    except ImportError as e:
        print(f"  RAG not available: {e}")
        print(f"  Install: pip install chromadb sentence-transformers")


def _run_rag_rebuild(domain: str):
    """Rebuild RAG index for a domain (or all domains)."""
    print(f"\n{'='*60}")
    print(f"  RAG INDEX REBUILD")
    print(f"  Domain: {domain if domain != 'general' else 'ALL'}")
    print(f"{'='*60}\n")
    
    try:
        from rag.vector_store import rebuild_index
        from memory_store import load_outputs, load_knowledge_base, MEMORY_DIR
    except ImportError as e:
        print(f"  Error: {e}")
        return
    
    # Determine which domains to rebuild
    if domain == "general":
        # Rebuild all domains
        domains = []
        if os.path.exists(MEMORY_DIR):
            for d in os.listdir(MEMORY_DIR):
                dpath = os.path.join(MEMORY_DIR, d)
                if os.path.isdir(dpath) and not d.startswith("_"):
                    domains.append(d)
        domains.sort()
    else:
        domains = [domain]
    
    if not domains:
        print("  No domains found in memory.")
        return
    
    total_claims = 0
    total_kb = 0
    
    for d in domains:
        outputs = load_outputs(d, min_score=0)
        kb = load_knowledge_base(d)
        
        print(f"  Rebuilding {d}... ({len(outputs)} outputs)", end=" ")
        result = rebuild_index(d, outputs, kb)
        print(f"→ {result['claims_indexed']} claims + {result['kb_claims_indexed']} KB claims")
        
        total_claims += result['claims_indexed']
        total_kb += result['kb_claims_indexed']
    
    print(f"\n  ✓ Total: {total_claims} claims + {total_kb} KB claims indexed across {len(domains)} domain(s)")


def _run_rag_search(query: str, domain: str):
    """Semantic search across the vector store."""
    print(f"\n{'='*60}")
    print(f"  RAG SEMANTIC SEARCH")
    print(f"  Query: {query}")
    print(f"  Domain: {domain}")
    print(f"{'='*60}\n")
    
    try:
        from rag.vector_store import search_claims
    except ImportError as e:
        print(f"  Error: {e}")
        return
    
    target_domain = domain if domain != "general" else None
    results = search_claims(
        query=query,
        domain=target_domain,
        max_results=10,
        accepted_only=True,
    )
    
    if not results:
        print("  No results found. Try --rag-rebuild first to index existing data.")
        return
    
    for i, r in enumerate(results):
        sim = r['similarity']
        sim_bar = "█" * int(sim * 20) + "░" * (20 - int(sim * 20))
        print(f"  {i+1}. [{r['domain']}] (sim: {sim:.3f}) {sim_bar}")
        print(f"     {r['text'][:120]}")
        if r.get('source'):
            print(f"     Source: {r['source'][:80]}")
        print()


# ============================================================
# MCP — Docker Tool Gateway Commands
# ============================================================

def _show_mcp_status():
    """Display MCP gateway status and connected servers."""
    print(f"\n{'='*60}")
    print(f"  MCP GATEWAY STATUS")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        status = gw.get_status()

        print(f"  Started: {status['started']}")
        print(f"  Servers: {status['running_servers']}/{status['total_servers']} running")
        print(f"  Total tools: {status['total_tools']}")
        print()

        for name, srv in status.get("servers", {}).items():
            icon = "●" if srv.get("running") else "○"
            init = "✓" if srv.get("initialized") else "✗"
            print(f"  {icon} {name} (init: {init}, tools: {srv.get('tools_count', 0)})")
            if srv.get("tool_names"):
                for tn in srv["tool_names"][:10]:
                    print(f"      - {tn}")
                if len(srv.get("tool_names", [])) > 10:
                    print(f"      ... and {len(srv['tool_names']) - 10} more")
            print()

    except Exception as e:
        print(f"  Error: {e}")


def _mcp_start_all():
    """Start all configured MCP servers."""
    print(f"\n{'='*60}")
    print(f"  MCP — STARTING ALL SERVERS")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()

        # Load config if no servers registered yet
        if not gw._containers:
            count = gw.load_config(_cfg.MCP_CONFIG_PATH)
            print(f"  Loaded {count} server configurations")

        results = gw.start_all()
        for name, success in results.items():
            icon = "✓" if success else "✗"
            print(f"  {icon} {name}")

        total_tools = len(gw.get_all_tools())
        print(f"\n  Total tools available: {total_tools}")

    except Exception as e:
        print(f"  Error: {e}")


def _mcp_stop_all():
    """Stop all running MCP servers."""
    print(f"\n{'='*60}")
    print(f"  MCP — STOPPING ALL SERVERS")
    print(f"{'='*60}\n")

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        gw.stop_all()
        print("  All MCP servers stopped.")
    except Exception as e:
        print(f"  Error: {e}")


def _show_mcp_tools():
    """List all available MCP tools across all servers."""
    print(f"\n{'='*60}")
    print(f"  MCP TOOLS")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        tools = gw.get_all_tools()

        if not tools:
            print("  No tools available. Start MCP servers with --mcp-start first.")
            return

        # Group by server
        by_server: dict[str, list] = {}
        for tool in tools:
            server = tool["name"].split("__")[0] if "__" in tool["name"] else "unknown"
            by_server.setdefault(server, []).append(tool)

        for server, server_tools in sorted(by_server.items()):
            print(f"  [{server}] ({len(server_tools)} tools)")
            for t in server_tools:
                short_name = t["name"].split("__", 1)[-1] if "__" in t["name"] else t["name"]
                desc = t.get("description", "").replace(f"[{server}] ", "")[:80]
                print(f"    - {short_name}: {desc}")
            print()

    except Exception as e:
        print(f"  Error: {e}")


def _mcp_health_check():
    """Run health checks on all MCP servers."""
    print(f"\n{'='*60}")
    print(f"  MCP HEALTH CHECK")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        health = gw.health_check()

        if not health:
            print("  No servers configured.")
            return

        for name, status in health.items():
            running = status.get("running", False)
            responsive = status.get("responsive", False)
            if running and responsive:
                icon = "●"
                state = "healthy"
            elif running and not responsive:
                icon = "◐"
                state = "unresponsive"
            else:
                icon = "○"
                state = "stopped"
            restarts = status.get("restart_count", 0)
            tools = status.get("tools_count", 0)
            print(f"  {icon} {name}: {state} (tools: {tools}, restarts: {restarts})")

    except Exception as e:
        print(f"  Error: {e}")


# ============================================================
# Credential Vault Handlers
# ============================================================

def _get_vault():
    """Get an unlocked CredentialVault instance."""
    import os
    passphrase = os.environ.get("VAULT_PASSPHRASE", "")
    if not passphrase:
        import getpass
        passphrase = getpass.getpass("Vault passphrase: ")
    if not passphrase:
        print("  ERROR: No vault passphrase provided.")
        print("  Set VAULT_PASSPHRASE env var or enter it when prompted.")
        return None
    try:
        from utils.credential_vault import CredentialVault
        return CredentialVault(passphrase=passphrase)
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def _vault_store(key: str, value: str):
    """Store a credential in the vault."""
    print(f"\n{'='*60}")
    print(f"  VAULT — Store Credential")
    print(f"{'='*60}\n")

    vault = _get_vault()
    if not vault:
        return

    # Try parsing as JSON (for structured creds like {email, password})
    import json
    try:
        parsed = json.loads(value)
        vault.store(key, parsed)
        print(f"  Stored '{key}' (JSON object with {len(parsed)} keys)")
    except json.JSONDecodeError:
        vault.store(key, value)
        print(f"  Stored '{key}' (string, {len(value)} chars)")


def _vault_get(key: str):
    """Retrieve a credential from the vault."""
    vault = _get_vault()
    if not vault:
        return

    try:
        val = vault.retrieve(key)
        import json
        if isinstance(val, dict):
            # Mask passwords in display
            display = {}
            for k, v in val.items():
                if "password" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                    display[k] = f"{str(v)[:3]}{'*' * max(0, len(str(v))-3)}"
                else:
                    display[k] = v
            print(json.dumps(display, indent=2))
        else:
            # Mask if it looks like a secret
            print(f"  {key}: {str(val)[:5]}{'*' * max(0, len(str(val))-5)}")
    except KeyError:
        print(f"  Key '{key}' not found in vault.")


def _vault_delete(key: str):
    """Delete a credential from the vault."""
    vault = _get_vault()
    if not vault:
        return

    if vault.delete(key):
        print(f"  Deleted '{key}'")
    else:
        print(f"  Key '{key}' not found.")


def _vault_list():
    """List all vault credential keys."""
    print(f"\n{'='*60}")
    print(f"  VAULT — Stored Credentials")
    print(f"{'='*60}\n")

    vault = _get_vault()
    if not vault:
        return

    keys = vault.list_keys()
    if keys:
        for k in keys:
            entry = vault.retrieve_full(k)
            updated = entry.get("updated_at", "?")[:10]
            accesses = entry.get("access_count", 0)
            print(f"  {k:30s}  updated: {updated}  accesses: {accesses}")
    else:
        print("  (vault is empty)")
    print()


def _vault_stats():
    """Show vault statistics."""
    print(f"\n{'='*60}")
    print(f"  VAULT — Statistics")
    print(f"{'='*60}\n")

    vault = _get_vault()
    if not vault:
        return

    import json
    stats = vault.stats()
    print(f"  Total credentials: {stats['total_credentials']}")
    print(f"  Vault file size: {stats['vault_file_size']} bytes")
    if stats["keys"]:
        print(f"  Keys: {', '.join(stats['keys'])}")
    print()


# ============================================================
# Stealth Browser Handlers
# ============================================================

def _browser_fetch_url(url: str):
    """Fetch a URL using the stealth browser."""
    print(f"\n{'='*60}")
    print(f"  BROWSER FETCH")
    print(f"{'='*60}\n")
    print(f"  URL: {url}")

    try:
        from browser.session_manager import fetch_with_browser
        vault = _get_vault()
        result = fetch_with_browser(url, vault=vault, headless=True)

        if result["success"]:
            print(f"  Title: {result.get('title', 'N/A')}")
            print(f"  Characters: {result.get('char_count', 0)}")
            print(f"  Domain: {result.get('domain', 'N/A')}")
            print(f"\n--- Content (first 2000 chars) ---")
            print(result.get("content", "")[:2000])
        else:
            print(f"  FAILED: {result.get('error', 'Unknown error')}")
    except ImportError as e:
        print(f"  ERROR: Browser dependencies not installed: {e}")
        print("  Run: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def _browser_test_stealth():
    """Test browser stealth detection."""
    print(f"\n{'='*60}")
    print(f"  BROWSER STEALTH TEST")
    print(f"{'='*60}\n")

    try:
        import asyncio
        from browser.stealth_browser import StealthBrowser

        async def _test():
            async with StealthBrowser(headless=True) as browser:
                page = await browser.new_page()
                await browser.navigate(page, "https://bot.sannysoft.com")
                detection = await browser.check_detection(page)
                await page.close()
                return detection

        result = asyncio.run(_test())
        stealth_ok = result.pop("stealth_ok", False)
        print(f"  Stealth: {'PASS' if stealth_ok else 'FAIL'}")
        for key, val in result.items():
            print(f"    {key}: {val}")
    except ImportError as e:
        print(f"  ERROR: Browser dependencies not installed: {e}")
        print("  Run: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


# ============================================================
# Project Orchestrator Handlers
# ============================================================

def _run_project(description: str, domain: str, workspace_dir: str = ""):
    """Decompose and start executing a large project."""
    print(f"\n{'='*60}")
    print(f"  PROJECT ORCHESTRATOR")
    print(f"{'='*60}\n")
    print(f"  Description: {description}")
    print(f"  Domain: {domain}")

    try:
        from hands.project_orchestrator import decompose_project, execute_project

        print("\n  Phase 1: Decomposing project...")
        project = decompose_project(description)

        if not project:
            print("  ERROR: Failed to decompose project")
            return

        project_id = project.get("id", "unknown")
        phases = project.get("phases", [])
        total_tasks = sum(len(p.get("tasks", [])) for p in phases)

        print(f"  Project ID: {project_id}")
        print(f"  Phases: {len(phases)}")
        print(f"  Total tasks: {total_tasks}")
        print()

        for i, phase in enumerate(phases):
            name = phase.get("name", f"Phase {i+1}")
            tasks = phase.get("tasks", [])
            review = phase.get("requires_review", False)
            print(f"    {i+1}. {name} ({len(tasks)} tasks){' [REVIEW NEEDED]' if review else ''}")

        print(f"\n  Phase 2: Executing project...")
        result = execute_project(project, workspace_dir=workspace_dir or None)

        status = result.get("status", "unknown")
        completed_phases = sum(1 for p in result.get("phases", []) if p.get("status") == "completed")
        print(f"\n  Result: {status}")
        print(f"  Completed phases: {completed_phases}/{len(phases)}")

        if status == "paused":
            print(f"  Project paused (review needed). Resume with: --project-resume {project_id}")

    except ImportError as e:
        print(f"  ERROR: Missing dependency: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def _show_project_status(project_id: str):
    """Show status of a project."""
    print(f"\n{'='*60}")
    print(f"  PROJECT STATUS")
    print(f"{'='*60}\n")

    try:
        from hands.project_orchestrator import load_project, list_projects, PROJECTS_DIR
        import json

        if project_id == "latest":
            projects = list_projects()
            if not projects:
                print("  No projects found.")
                return
            project_id = projects[-1]["id"]

        project = load_project(project_id)
        if not project:
            print(f"  Project '{project_id}' not found.")
            return

        print(f"  ID: {project.get('id')}")
        print(f"  Description: {project.get('description', 'N/A')[:80]}")
        print(f"  Status: {project.get('status', 'unknown')}")
        print(f"  Created: {project.get('created_at', 'N/A')[:19]}")
        print()

        for i, phase in enumerate(project.get("phases", [])):
            name = phase.get("name", f"Phase {i+1}")
            status = phase.get("status", "pending")
            tasks_done = sum(1 for t in phase.get("tasks", []) if t.get("completed"))
            total = len(phase.get("tasks", []))
            icon = {"completed": "✓", "in_progress": "▶", "failed": "✗", "review_needed": "⚠", "skipped": "○"}.get(status, "·")
            print(f"    {icon} {name}: {status} ({tasks_done}/{total} tasks)")

    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def _resume_project(project_id: str):
    """Resume a paused project."""
    print(f"\n  Resuming project: {project_id}")

    try:
        from hands.project_orchestrator import load_project, execute_project, list_projects

        if project_id == "latest":
            projects = list_projects()
            if not projects:
                print("  No projects found.")
                return
            project_id = projects[-1]["id"]

        project = load_project(project_id)
        if not project:
            print(f"  Project '{project_id}' not found.")
            return

        result = execute_project(project)
        print(f"  Result: {result.get('status', 'unknown')}")

    except Exception as e:
        print(f"  ERROR: {e}")


def _approve_project_phase(project_id: str):
    """Approve the current phase of a project needing review."""
    try:
        from hands.project_orchestrator import load_project, approve_phase, list_projects

        if project_id == "latest":
            projects = list_projects()
            if not projects:
                print("  No projects found.")
                return
            project_id = projects[-1]["id"]

        project = load_project(project_id)
        if not project:
            print(f"  Project '{project_id}' not found.")
            return

        # Find the phase needing review
        for i, phase in enumerate(project.get("phases", [])):
            if phase.get("status") == "review_needed":
                approve_phase(project, i)
                print(f"  Approved phase {i+1}: {phase.get('name', 'unknown')}")
                return

        print("  No phases are waiting for review.")

    except Exception as e:
        print(f"  ERROR: {e}")


def _list_projects():
    """List all projects."""
    print(f"\n{'='*60}")
    print(f"  PROJECTS")
    print(f"{'='*60}\n")

    try:
        from hands.project_orchestrator import list_projects

        projects = list_projects()
        if not projects:
            print("  No projects found.")
            return

        for p in projects:
            status = p.get("status", "unknown")
            desc = p.get("description", "N/A")[:60]
            phases = len(p.get("phases", []))
            icon = {"completed": "✓", "in_progress": "▶", "paused": "⏸", "failed": "✗"}.get(status, "·")
            print(f"  {icon} {p['id'][:12]}  {status:12s}  {phases} phases  {desc}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


# ============================================================
# VPS Deploy Handlers
# ============================================================

def _run_deploy(dry_run: bool = False):
    """Deploy Agent Brain to VPS, then auto-setup cron schedule."""
    print(f"\n{'='*60}")
    print(f"  VPS DEPLOYMENT {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}\n")

    try:
        from deploy.deployer import deploy, setup_schedule
        from deploy.vps_config import load_config
        vault = _get_vault()

        result = deploy(vault=vault, dry_run=dry_run)
        for step in result.get("steps", []):
            icon = "✓" if step["status"] == "done" else "○" if step["status"] == "dry_run" else "✗"
            extra = f" ({step['archive_size_mb']} MB)" if "archive_size_mb" in step else ""
            print(f"  {icon} {step['name']}{extra}")

        print(f"\n  Deployment: {result['status']}")
        if result.get("error"):
            print(f"  Error: {result['error']}")

        # Auto-setup cron schedule after successful deploy
        if result.get("status") == "success" and not dry_run:
            config = load_config()
            if config.host and config.schedule_cron:
                print(f"\n  Setting up cron schedule on VPS...")
                sched = setup_schedule(config=config, vault=vault)
                if sched.get("status") == "success":
                    print(f"  ✓ Schedule configured: {sched.get('cron_entry', '')[:60]}")
                else:
                    print(f"  ✗ Schedule failed: {sched.get('error', 'unknown')}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def _run_deploy_health():
    """Run health check on remote VPS."""
    print(f"\n{'='*60}")
    print(f"  VPS HEALTH CHECK")
    print(f"{'='*60}\n")

    try:
        from deploy.deployer import health_check
        vault = _get_vault()

        checks = health_check(vault=vault)
        for key, val in checks.items():
            print(f"  {key}: {val}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def _run_deploy_logs(domain: str = ""):
    """View remote VPS logs."""
    try:
        from deploy.deployer import get_remote_logs
        vault = _get_vault()

        logs = get_remote_logs(vault=vault, domain=domain if domain != DEFAULT_DOMAIN else None)
        print(logs)
    except Exception as e:
        print(f"  ERROR: {e}")


def _run_deploy_schedule():
    """Setup cron schedule on VPS."""
    try:
        from deploy.deployer import setup_schedule
        vault = _get_vault()

        result = setup_schedule(vault=vault)
        print(f"  Schedule: {result.get('status')}")
        if result.get("cron_entry"):
            print(f"  Entry: {result['cron_entry']}")
    except Exception as e:
        print(f"  ERROR: {e}")


def _run_deploy_unschedule():
    """Remove cron schedule from VPS."""
    try:
        from deploy.deployer import remove_schedule
        vault = _get_vault()

        result = remove_schedule(vault=vault)
        print(f"  {result.get('message', result.get('error'))}")
    except Exception as e:
        print(f"  ERROR: {e}")


def _run_deploy_configure(host: str = "", user: str = ""):
    """Configure VPS connection."""
    print(f"\n{'='*60}")
    print(f"  VPS CONFIGURATION")
    print(f"{'='*60}\n")

    try:
        from deploy.vps_config import load_config, save_config

        config = load_config()
        if host:
            config.host = host
        if user:
            config.user = user

        save_config(config)
        print(f"  Host: {config.host or '(not set)'}")
        print(f"  User: {config.user}")
        print(f"  Port: {config.port}")
        print(f"  Schedule: {config.schedule_cron}")
        print(f"  Remote dir: {config.remote_dir}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


if __name__ == "__main__":
    main()
