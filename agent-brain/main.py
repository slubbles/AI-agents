"""
Agent Brain — Main Loop Runner

Usage:
    python main.py "What is the current state of autonomous AI agents?"
    python main.py --domain crypto "What are the latest Bitcoin ETF developments?"
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
    get_active_version, list_versions,
)


def run_loop(question: str, domain: str = DEFAULT_DOMAIN) -> dict:
    """
    Execute the full research → critique → quality gate loop.
    
    1. Load strategy for researcher (if exists)
    2. Researcher produces findings
    3. Critic scores findings
    4. If score < threshold: retry with critique feedback (up to MAX_RETRIES)
    5. Store final output to memory
    """
    print(f"\n{'='*60}")
    print(f"  AGENT BRAIN — Research Loop")
    print(f"  Domain: {domain}")
    print(f"  Question: {question}")
    print(f"{'='*60}\n")

    # Load current strategy
    strategy, strategy_version = get_strategy("researcher", domain)
    if strategy:
        status = get_strategy_status("researcher", domain)
        status_label = " (TRIAL)" if status == "trial" else ""
        print(f"[STRATEGY] Loaded version: {strategy_version}{status_label}")
    else:
        print(f"[STRATEGY] Using default (no custom strategy yet)")

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
    parser.add_argument("--evolve", action="store_true", help="Run meta-analyst strategy evolution only (no research)")
    parser.add_argument("--status", action="store_true", help="Show strategy status and performance for a domain")
    parser.add_argument("--rollback", action="store_true", help="Roll back to previous strategy version")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY environment variable first.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    if args.status:
        _show_status(args.domain)
        return

    if args.rollback:
        _do_rollback(args.domain)
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
        parser.error("question is required unless --evolve, --status, or --rollback is used")

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

    print(f"  Active version: {active} ({status})")
    print(f"  Total versions: {len(versions)}")

    if versions:
        print(f"\n  Version Performance:")
        print(f"  {'Version':<10} {'Outputs':>8} {'Avg Score':>10} {'Accepted':>9} {'Rejected':>9}")
        print(f"  {'-'*46}")

        # Also show default performance
        default_perf = get_strategy_performance(domain, "default")
        if default_perf["count"] > 0:
            print(f"  {'default':<10} {default_perf['count']:>8} {default_perf['avg_score']:>10.1f} "
                  f"{default_perf['accepted']:>9} {default_perf['rejected']:>9}")

        for v in versions:
            perf = get_strategy_performance(domain, v)
            marker = " ←" if v == active else ""
            print(f"  {v:<10} {perf['count']:>8} {perf['avg_score']:>10.1f} "
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


if __name__ == "__main__":
    main()
