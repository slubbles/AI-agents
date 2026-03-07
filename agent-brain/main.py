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
    python main.py --set-goal                    Set goal/intent for a domain (directs research)
    python main.py --show-goal                   Show the current goal for a domain
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

# Raise recursion limit early — ChromaDB 1.5.x triggers deep recursion
# during collection operations, and the daemon's call stack is already deep
# from threading + nested function calls.
sys.setrecursionlimit(10000)

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


from agents.researcher import research
from agents.critic import critique
from agents.consensus import consensus_research
from agents.meta_analyst import analyze_and_evolve
from prescreen import prescreen, build_prescreen_critique
from config import (
    QUALITY_THRESHOLD, MAX_RETRIES, DEFAULT_DOMAIN, LOG_DIR,
    MIN_OUTPUTS_FOR_ANALYSIS, EVOLVE_EVERY_N,
    MIN_OUTPUTS_FOR_SYNTHESIS, SYNTHESIZE_EVERY_N,
    CONSENSUS_ENABLED, CONSENSUS_RESEARCHERS,
    AUTO_PRUNE_ENABLED, AUTO_PRUNE_EVERY_N,
)
from memory_store import save_output, load_outputs, get_stats, prune_domain
from strategy_store import get_strategy, get_strategy_status, evaluate_trial, list_pending
from cost_tracker import check_budget, check_balance
from agents.cross_domain import load_principles
from agents.synthesizer import synthesize
from analytics import display_analytics, search_memory, display_search_results
from validator import display_validation
from scheduler import create_plan, display_plan, get_recommendations, display_recommendations, stop_daemon, get_daemon_status
from knowledge_graph import build_graph_from_kb, save_graph, get_graph_summary


# ============================================================
# Task creation from research findings (Brain → Hands bridge)
# ============================================================

# ============================================================
# Domain-Agnostic Task Classification (Brain → Hands bridge)
# ============================================================

# Action verbs grouped by abstract intent — not tied to coding
_ACTION_VERBS = {
    # Creation intent — applies in any domain
    "build": "build", "create": "build", "implement": "build",
    "develop": "build", "design": "build", "draft": "build",
    "write": "build", "compose": "build", "produce": "build",
    "prototype": "build", "generate": "build",
    # Delivery intent
    "deploy": "deploy", "launch": "deploy", "ship": "deploy",
    "publish": "deploy", "release": "deploy", "submit": "deploy",
    "distribute": "deploy", "deliver": "deploy",
    # Operational intent — the universal "do something" category
    "analyze": "action", "test": "action", "fix": "action",
    "optimize": "action", "integrate": "action", "automate": "action",
    "configure": "action", "migrate": "action", "refactor": "action",
    "upgrade": "action", "scale": "action", "monitor": "action",
    "evaluate": "action", "audit": "action", "verify": "action",
    "investigate": "action", "research": "action", "survey": "action",
    "compare": "action", "benchmark": "action", "measure": "action",
    "track": "action", "review": "action", "assess": "action",
    "plan": "action", "schedule": "action", "organize": "action",
    "contact": "action", "reach out": "action", "engage": "action",
    "negotiate": "action", "propose": "action", "pitch": "action",
    "set up": "action", "establish": "action", "prepare": "action",
}


def _classify_task_priority(task_type: str, source: str) -> str:
    """Classify priority based on task type and source (insight vs gap)."""
    if source == "gap":
        return "low"
    if task_type in ("build", "deploy"):
        return "high"
    return "medium"


def _create_tasks_from_research(domain: str, research: dict, output_id: str) -> None:
    """
    Extract actionable items from accepted research and create sync tasks.

    Domain-agnostic: uses broad action verb detection so tasks are created
    regardless of whether the domain is technical, commercial, scientific, etc.
    No LLM call — uses verb matching to stay free.
    """
    from sync import create_task, _load_tasks

    existing = _load_tasks()
    existing_titles = {t["title"].lower() for t in existing if t["status"] in ("pending", "in_progress")}

    created = 0

    for insight in research.get("key_insights", [])[:5]:
        insight_lower = insight.lower()
        task_type = None
        for verb, ttype in _ACTION_VERBS.items():
            if verb in insight_lower:
                task_type = ttype
                break
        if task_type and insight.lower()[:60] not in existing_titles:
            priority = _classify_task_priority(task_type, "insight")
            create_task(
                title=insight[:80],
                description=f"From research in '{domain}': {insight}",
                source_domain=domain,
                task_type=task_type,
                priority=priority,
                source_output_id=output_id,
            )
            created += 1

    for gap in research.get("knowledge_gaps", [])[:3]:
        if gap.lower()[:60] not in existing_titles:
            create_task(
                title=f"Research gap: {gap[:70]}",
                description=f"Knowledge gap identified in '{domain}': {gap}",
                source_domain=domain,
                task_type="action",
                priority=_classify_task_priority("action", "gap"),
                source_output_id=output_id,
            )
            created += 1

    if created:
        print(f"[SYNC] Created {created} task(s) from research findings")


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

    # Goal check — warn if research is undirected
    from domain_goals import get_goal
    domain_goal = get_goal(domain)
    if not domain_goal:
        print(f"  Goal: ⚠ NOT SET — research will be unfocused")
        print(f"         Set with: python main.py --set-goal --domain {domain}")
    balance = check_balance()
    print(f"  Budget: ${budget['remaining']:.4f} remaining today | Balance: ${balance['remaining_balance']:.4f} of ${balance['starting_balance']:.2f}")
    print(f"{'='*60}\n")

    # Bootstrap detection: auto-initialize cold domains
    try:
        from domain_bootstrap import is_cold, bootstrap_domain, get_bootstrap_status, mark_bootstrap_complete
        from config import BOOTSTRAP_MIN_OUTPUTS
        if is_cold(domain):
            bs = get_bootstrap_status(domain)
            if not bs or bs.get("phase") != "in_progress":
                bootstrap_domain(domain)
    except Exception as e:
        print(f"[BOOTSTRAP] Warning: {e}")

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
            print(f"[CROSS-DOMAIN] General principles available from {len(principles.get('source_domains', []))} domain(s)")
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

        # Step 2: Pre-screen (cheap grok check before expensive Claude critic)
        print("[PRE-SCREEN] Quick quality check...")
        prescreen_result = prescreen(research_output, domain=domain)
        prescreen_decision = prescreen_result.get("decision", "escalate")
        prescreen_score = prescreen_result.get("prescreen_score", 0)

        if prescreen_result.get("skip_claude"):
            print(f"[PRE-SCREEN] {prescreen_score}/10 → {prescreen_decision.upper()} (skipping Claude critic)")
            critique_output = build_prescreen_critique(prescreen_result)
        else:
            print(f"[PRE-SCREEN] {prescreen_score}/10 → ESCALATE to Claude critic")
            # Step 2b: Full Critique (Claude)
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
            # Capture lesson from bad rejection (score < 5 only)
            try:
                from research_lessons import add_rejection_lesson
                dim_scores = critique_output.get("scores", {})
                weakest = min(dim_scores, key=dim_scores.get) if dim_scores else "unknown"
                add_rejection_lesson(domain, score, weakest, critique_output.get("actionable_feedback", ""))
            except Exception:
                pass

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

    # Step 5.1: Record source quality (learn which sources produce good research)
    try:
        from source_quality import record_source_quality
        sources_used = final_research.get("sources_used", [])
        tool_log = final_research.get("_tool_log", [])
        record_source_quality(
            domain=domain,
            sources_used=sources_used,
            score=final_critique.get("overall_score", 0),
            verdict=final_critique.get("verdict", "unknown"),
            tool_log=tool_log,
        )
    except Exception:
        pass  # Non-blocking

    # Step 5.5: Create sync tasks from accepted research (Brain → Hands bridge)
    final_verdict = final_critique.get("verdict", "unknown")
    if final_verdict == "accept":
        try:
            _create_tasks_from_research(domain, final_research, filepath)
        except Exception as e:
            print(f"[SYNC] ⚠ Task creation failed: {e}")

    # Show domain stats
    stats = get_stats(domain)
    print(f"\n[STATS] Domain '{domain}': {stats['count']} outputs, avg score {stats['avg_score']:.1f}, "
          f"{stats['accepted']} accepted / {stats['rejected']} rejected")

    # Update calibration stats after each run
    try:
        from domain_calibration import update_domain_stats
        update_domain_stats(domain)
    except Exception:
        pass

    # Check if bootstrap is now complete
    try:
        from domain_bootstrap import is_cold, mark_bootstrap_complete
        if not is_cold(domain):
            from domain_bootstrap import get_bootstrap_status
            bs = get_bootstrap_status(domain)
            if bs and bs.get("phase") == "in_progress":
                mark_bootstrap_complete(domain)
    except Exception:
        pass

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
    # This is the KEY anti-circular mechanism: verifier checks LLM claims
    # against external reality, breaking the LLM-judging-LLM loop.
    if final_verdict == "accept":
        try:
            from agents.verifier import verify_predictions, load_predictions, get_verification_stats
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
                        status_icon = {"confirmed": "✓", "refuted": "✗", "partially_confirmed": "~", "inconclusive": "?"}.get(r.get("verdict"), "?")
                        print(f"  {status_icon} {r.get('prediction', '?')[:80]} → {r.get('verdict', '?')}")
                    
                    # Feed verification results back as lessons (reality-grounding signal)
                    refuted = [r for r in results if r.get("verdict") == "refuted"]
                    for r in refuted:
                        try:
                            from research_lessons import add_lesson
                            add_lesson(
                                domain,
                                lesson=f"REFUTED prediction: \"{r.get('prediction', '')[:150]}\" — "
                                       f"Evidence: {r.get('evidence', '')[:200]}",
                                source="verifier_refutation",
                                details=f"The system predicted something that turned out to be wrong. "
                                        f"This indicates overconfidence or poor source quality in this area."
                            )
                        except Exception:
                            pass
                    
                    # Print accuracy stats as a reality-check signal
                    stats = get_verification_stats(domain)
                    if stats.get("accuracy_rate") is not None:
                        print(f"\n[VERIFIER] Prediction accuracy: {stats['accuracy_rate']*100:.0f}% "
                              f"({stats['confirmed']} confirmed, {stats['refuted']} refuted)")
        except Exception as e:
            pass  # Non-blocking — verification failure shouldn't stop the loop

    # Step 6.8: Claim verification — check high-confidence claims against web evidence
    # Runs every 5 accepted outputs to avoid excessive API usage
    if final_verdict == "accept" and accepted_count > 0 and accepted_count % 5 == 0:
        try:
            from config import CLAIM_VERIFY_ENABLED
            if CLAIM_VERIFY_ENABLED:
                from memory_store import load_knowledge_base as _load_kb
                if _load_kb(domain):
                    from agents.claim_verifier import verify_claims
                    verifications = verify_claims(domain, max_checks=2)
                    if verifications:
                        confirmed = sum(1 for v in verifications if v["verdict"] == "confirmed")
                        refuted = sum(1 for v in verifications if v["verdict"] == "refuted")
                        if confirmed + refuted > 0:
                            print(f"\n[CLAIM-VERIFY] Checked {len(verifications)} claims: "
                                  f"{confirmed} confirmed, {refuted} refuted")
        except Exception:
            pass

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
        health = run_health_check(verbose=True)
        health_status = health.get("status", "unknown") if health else "unknown"
        alerts_count = health.get("alerts_generated", 0) if health else 0
        if alerts_count > 0:
            print(f"  [INFO] {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')} Health: {health_status} ({alerts_count} alerts)")
        elif health_status != "healthy":
            print(f"  [INFO] {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')} Health: {health_status}")
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
        "dimensions": critique.get("scores", {}),
        "feedback": critique.get("actionable_feedback", ""),
        "weaknesses": critique.get("weaknesses", []),
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
    parser.add_argument("--rounds", type=int, default=None, help="Number of rounds (default: 1 for auto, 5 for daemon)")
    parser.add_argument("--set-goal", action="store_true", help="Set the goal/intent for a domain (interactive prompt)")
    parser.add_argument("--show-goal", action="store_true", help="Show the current goal for a domain")
    parser.add_argument("--progress", action="store_true", help="Show progress toward domain goal")
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
    parser.add_argument("--chat", action="store_true", help="Interactive conversation mode — talk to the system naturally")
    parser.add_argument("--telegram", action="store_true", help="Run Telegram chat bot (interactive mode via Telegram)")
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
    parser.add_argument("--daemon-report", action="store_true", help="Full daemon health report (cycles, budget, watchdog, domains, sync)")
    parser.add_argument("--interval", type=int, default=60, help="Daemon interval in minutes (default: 60)")
    parser.add_argument("--max-cycles", type=int, default=0, help="Max daemon cycles (0=unlimited)")
    parser.add_argument("--autonomous", action="store_true", help="Fully autonomous: auto-approve strategies, auto-execute Hands tasks")
    parser.add_argument("--migrate", action="store_true", help="Migrate JSON/JSONL data to SQLite database")
    parser.add_argument("--alerts", action="store_true", help="Show monitoring alerts")
    parser.add_argument("--check-health", action="store_true", help="Run health checks and monitoring")
    parser.add_argument("--watchdog", action="store_true", help="Show watchdog status (circuit breaker, health, budget)")
    parser.add_argument("--sync", action="store_true", help="Show Brain↔Hands sync status")
    parser.add_argument("--sync-balance", type=float, metavar="AMOUNT", help="Update the API credit balance (e.g., --sync-balance 9.50)")

    # Agent Hands — Execution Layer
    parser.add_argument("--execute", action="store_true", help="Execute a task using Agent Hands (code generation)")
    parser.add_argument("--goal", default="", help="Task goal for --execute mode (alternative to positional arg)")
    parser.add_argument("--exec-status", action="store_true", help="Show execution memory stats")
    parser.add_argument("--exec-evolve", action="store_true", help="Force execution strategy evolution")
    parser.add_argument("--exec-principles", action="store_true", help="Show learned execution principles")
    parser.add_argument("--exec-lessons", action="store_true", help="Show learned execution patterns/lessons")
    parser.add_argument("--lessons", action="store_true", help="Show research lessons learned from failures")
    parser.add_argument("--workspace", default="", help="Workspace directory for execution output")
    parser.add_argument("--auto-build", action="store_true", help="Brain→Hands pipeline: generate coding task from KB and execute it")
    parser.add_argument("--build-rounds", type=int, default=1, help="Number of auto-build rounds (default: 1)")
    parser.add_argument("--next-task", action="store_true", help="Show next AI-generated coding task for a domain")
    
    # Cortex Pipeline — Full three-way communication
    parser.add_argument("--pipeline", metavar="INSTRUCTION", help="Run Cortex pipeline: Brain researches → evaluates → Hands builds")
    parser.add_argument("--skip-research", action="store_true", help="Skip Brain research, use existing KB for --pipeline")
    parser.add_argument("--budget-cap", type=float, default=0.50, help="Budget cap for Hands build (default: $0.50)")
    parser.add_argument("--journal", action="store_true", help="Show Cortex pipeline journal")
    parser.add_argument("--journal-lines", type=int, default=20, help="Number of journal entries to show (default: 20)")
    parser.add_argument("--build-ready", action="store_true", help="Check if domain has enough research for a build")
    
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

    # Signal Intelligence — Reddit pain point collection
    parser.add_argument("--collect-signals", action="store_true", help="Collect pain-point signals from Reddit")
    parser.add_argument("--signal-subs", default="", help="Comma-separated subreddits (default: all targets)")
    parser.add_argument("--signal-time", default="month", help="Time filter: hour, day, week, month, year, all")
    parser.add_argument("--rank-opportunities", action="store_true", help="Score unanalyzed posts and rank opportunities")
    parser.add_argument("--weekly-brief", action="store_true", help="Generate weekly opportunity brief (premium model)")
    parser.add_argument("--signal-status", action="store_true", help="Show signal collection stats and top opportunities")
    parser.add_argument("--enrich-signals", action="store_true", help="Enrich top posts with real engagement data via Scrapling")
    parser.add_argument("--build-spec", type=int, metavar="N", help="Generate build spec for opportunity #N")
    parser.add_argument("--reality-check", type=int, metavar="N", help="Generate a commercial decision packet for opportunity #N")
    parser.add_argument("--reality-focus", default="", help="Optional extra focus for --reality-check")
    parser.add_argument("--engagement-check", action="store_true", help="Check engagement changes on high-scoring opportunities")

    # Transistor Systems (Core Reliability)
    parser.add_argument("--bootstrap", action="store_true", help="Bootstrap a new domain (cold-start reliability)")
    parser.add_argument("--calibration", action="store_true", help="Show cross-domain score calibration stats")
    parser.add_argument("--maintenance", action="store_true", help="Run full memory lifecycle maintenance")
    parser.add_argument("--verify-claims", action="store_true", help="Verify high-confidence KB claims against web evidence")
    parser.add_argument("--claim-stats", action="store_true", help="Show claim verification statistics")
    parser.add_argument("--readiness", action="store_true", help="Check if system is ready to run cycles")

    # Post-Cycle Review
    parser.add_argument("--review", action="store_true", help="Full post-cycle review (scores, trends, anomalies, costs)")
    parser.add_argument("--review-days", type=int, default=30, help="Review period in days (default: 30)")
    parser.add_argument("--review-cycles", type=int, default=0, help="Review last N daemon cycles")

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

    # Load .env before checking keys
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent / ".env")

    # Allow offline commands (validate, review, readiness) without API key
    _OFFLINE_COMMANDS = ("validate", "readiness", "review", "review_cycles")
    _is_offline = any(getattr(args, cmd, False) or getattr(args, cmd, 0) for cmd in _OFFLINE_COMMANDS)
    if not _is_offline and not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: Set OPENROUTER_API_KEY environment variable first.")
        print("  export OPENROUTER_API_KEY=sk-or-...")
        print("  (Use --readiness to check configuration)")
        sys.exit(1)

    # Apply consensus overrides
    import config as _cfg
    if args.consensus:
        _cfg.CONSENSUS_ENABLED = True
        print("  [CONFIG] Consensus mode ENABLED for this run")
    elif getattr(args, 'no_consensus', False):
        _cfg.CONSENSUS_ENABLED = False
        print("  [CONFIG] Consensus mode DISABLED for this run")

    # Dispatch control commands — delegates to cli/ modules
    if args.chat:
        from cli.chat import run_chat
        run_chat(args.domain)
        return
    if args.telegram:
        from telegram_bot import run_telegram_bot
        run_telegram_bot()
        return
    if args.status:
        from cli.strategy import show_status
        show_status(args.domain)
        return
    if args.audit:
        from cli.strategy import audit
        audit(args.domain)
        return
    if args.approve:
        from cli.strategy import approve
        approve(args.domain, args.approve)
        return
    if args.reject:
        from cli.strategy import reject
        reject(args.domain, args.reject)
        return
    if args.diff:
        from cli.strategy import diff
        diff(args.domain, args.diff[0], args.diff[1])
        return
    if args.rollback:
        from cli.strategy import rollback as do_rollback
        do_rollback(args.domain)
        return
    if args.budget:
        from cli.strategy import budget
        budget()
        return
    if args.principles:
        from cli.strategy import principles
        principles(force_extract=args.extract)
        return
    if args.transfer:
        from cli.strategy import transfer
        transfer(args.transfer, args.hint)
        return
    if args.next:
        from cli.research import show_next
        show_next(args.domain)
        return
    if getattr(args, 'set_goal', False):
        from domain_goals import set_goal, get_goal, validate_goal
        current = get_goal(args.domain)
        if current:
            print(f"Current goal for '{args.domain}': {current}")
            print()
        goal_text = input("Enter goal/intent for this domain:\n> ").strip()
        if not goal_text:
            print("No goal entered. Aborting.")
            return
        quality = validate_goal(goal_text)
        if quality["issues"]:
            print(f"\n⚠ Goal quality issues:")
            for issue in quality["issues"]:
                print(f"  - {issue}")
            for suggestion in quality["suggestions"]:
                print(f"  → {suggestion}")
            confirm = input("\nSave anyway? (y/n): ").strip().lower()
            if confirm != "y":
                print("Goal not saved. Try a more specific goal.")
                return
        set_goal(args.domain, goal_text)
        print(f"\n✓ Goal set for '{args.domain}' (quality: {quality['score']})")
        return
    if getattr(args, 'show_goal', False):
        from domain_goals import get_goal, get_goal_record
        record = get_goal_record(args.domain)
        if not record:
            print(f"No goal set for domain '{args.domain}'")
            print(f"Set one with: python main.py --set-goal --domain {args.domain}")
            return
        print(f"\nDomain: {args.domain}")
        print(f"Goal: {record['goal']}")
        print(f"Set: {record.get('set_at', '?')}")
        if record.get('updated_at') != record.get('set_at'):
            print(f"Updated: {record.get('updated_at', '?')}")
        if record.get('previous_goals'):
            print(f"\nPrevious goals ({len(record['previous_goals'])}):")
            for prev in record['previous_goals']:
                print(f"  - {prev['goal'][:80]} (replaced {prev['replaced_at'][:10]})")
        return
    if getattr(args, 'progress', False):
        from progress_tracker import display_progress, assess_progress
        assess_progress(args.domain, force=True)
        display_progress(args.domain)
        return
    if args.auto:
        from cli.research import run_auto
        run_auto(args.domain, args.rounds or 1)
        return
    if args.synthesize:
        from cli.knowledge import run_synthesize
        run_synthesize(args.domain)
        return
    if args.kb:
        from cli.knowledge import show_kb
        show_kb(args.domain)
        return
    if getattr(args, 'kb_versions', False):
        from cli.knowledge import versions as show_kb_versions
        show_kb_versions(args.domain)
        return
    if getattr(args, 'kb_rollback', None):
        from cli.knowledge import kb_rollback
        kb_rollback(args.domain, args.kb_rollback)
        return
    if getattr(args, 'predictions', False):
        from cli.infrastructure import predictions_extract
        predictions_extract(args.domain)
        return
    if getattr(args, 'verify', False):
        from cli.infrastructure import predictions_verify
        predictions_verify(args.domain)
        return
    if getattr(args, 'prediction_stats', False):
        from cli.infrastructure import prediction_stats
        prediction_stats(args.domain)
        return
    if args.prune or getattr(args, 'prune_dry', False):
        from cli.knowledge import prune
        prune(args.domain, dry_run=getattr(args, 'prune_dry', False))
        return
    if args.dashboard:
        from cli.infrastructure import show_dashboard
        show_dashboard()
        return
    if args.orchestrate:
        from cli.research import run_orchestrate
        targets = [d.strip() for d in args.target_domains.split(",") if d.strip()] or None
        run_orchestrate(targets, args.rounds or 5)
        return
    if args.export or getattr(args, 'export_md', False):
        from cli.infrastructure import run_export
        run_export(markdown=getattr(args, 'export_md', False))
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
        from cli.infrastructure import show_seeds
        show_seeds(args.domain)
        return
    if args.plan:
        plan = create_plan(aggressive=args.aggressive)
        display_plan(plan)
        return
    if args.run_plan:
        from cli.research import run_orchestrate
        plan = create_plan(aggressive=args.aggressive)
        display_plan(plan)
        if plan["executable"]:
            print("  Executing plan...\n")
            target = [a["domain"] for a in plan["allocation"]]
            total = plan["total_rounds"]
            run_orchestrate(target, total)
        return
    if args.recommend:
        recs = get_recommendations()
        display_recommendations(recs)
        return
    if getattr(args, 'smart_orchestrate', False):
        from cli.research import run_smart_orchestrate
        run_smart_orchestrate(args)
        return
    if args.graph:
        from cli.knowledge import graph
        graph(args.domain)
        return
    if args.daemon:
        from cli.infrastructure import run_daemon_mode
        run_daemon_mode(args)
        return
    if getattr(args, 'daemon_stop', False):
        if stop_daemon():
            print("  Daemon stop signal sent.")
        else:
            print("  No daemon is running.")
        return
    if getattr(args, 'daemon_status', False):
        from cli.infrastructure import show_daemon_status
        status = get_daemon_status()
        show_daemon_status(status)
        return
    if getattr(args, 'daemon_report', False):
        from cli.infrastructure import show_daemon_report
        show_daemon_report()
        return

    if args.migrate:
        from cli.infrastructure import run_migrate
        run_migrate()
        return
    if args.alerts:
        from cli.infrastructure import show_alerts
        show_alerts()
        return
    if getattr(args, 'check_health', False):
        from cli.infrastructure import run_health_check
        run_health_check()
        return
    if getattr(args, 'watchdog', False):
        from cli.infrastructure import show_watchdog_status
        show_watchdog_status()
        return
    if getattr(args, 'sync', False):
        from cli.infrastructure import show_sync_status
        show_sync_status()
        return
    if getattr(args, 'sync_balance', None) is not None:
        new_balance = args.sync_balance
        if new_balance <= 0:
            print("  ✗ Balance must be positive.")
            return
        # Write to .env file so it persists
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        # Read existing .env, update or add TOTAL_BALANCE_USD
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith("TOTAL_BALANCE_USD="):
                        lines.append(f"TOTAL_BALANCE_USD={new_balance}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"TOTAL_BALANCE_USD={new_balance}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)
        print(f"  ✓ Balance updated to ${new_balance:.2f}")
        print(f"    Saved to .env (takes effect on next run)")
        return

    # --- Agent Hands dispatch ---
    if args.execute:
        from cli.execution import run_execute
        goal = args.goal or args.question
        if not goal:
            parser.error("--execute requires a goal: --execute --goal 'Build a todo app' OR --execute 'Build a todo app'")
        run_execute(args.domain, goal, workspace_dir=args.workspace)
        return
    if getattr(args, 'exec_status', False):
        from cli.execution import show_exec_status
        show_exec_status(args.domain)
        return
    if getattr(args, 'exec_evolve', False):
        from cli.execution import run_exec_evolve
        run_exec_evolve(args.domain)
        return
    if getattr(args, 'exec_principles', False):
        from cli.execution import show_exec_principles
        show_exec_principles()
        return
    if getattr(args, 'exec_lessons', False):
        from cli.execution import show_exec_lessons
        show_exec_lessons(args.domain)
        return
    if getattr(args, 'lessons', False):
        from research_lessons import show_lessons
        show_lessons(args.domain)
        return
    if getattr(args, 'auto_build', False):
        from cli.execution import run_auto_build
        run_auto_build(args.domain, getattr(args, 'build_rounds', 1), workspace_dir=args.workspace)
        return
    if getattr(args, 'next_task', False):
        from cli.execution import show_next_task
        show_next_task(args.domain)
        return
    if getattr(args, 'pipeline', None):
        from cli.execution import run_pipeline
        run_pipeline(
            args.domain,
            args.pipeline,
            skip_research=getattr(args, 'skip_research', False),
            budget_cap=getattr(args, 'budget_cap', 0.50),
        )
        return
    if getattr(args, 'journal', False):
        from cli.execution import show_journal
        show_journal(args.domain, last_n=getattr(args, 'journal_lines', 20))
        return
    if getattr(args, 'build_ready', False):
        from agents.cortex import is_build_ready
        readiness = is_build_ready(args.domain)
        print(f"\n  Build Readiness: {args.domain}")
        print(f"  {'─'*40}")
        print(f"  Accepted outputs: {readiness['accepted_count']}")
        print(f"  KB claims: {readiness['claim_count']}")
        print(f"  User pain signals: {'Yes' if readiness['has_user_pain'] else 'No'}")
        print(f"  Competitor data: {'Yes' if readiness['has_competitors'] else 'No'}")
        print(f"  Status: {'✓ READY' if readiness['ready'] else '✗ ' + readiness['reason']}")
        if readiness.get('domain_summary'):
            print(f"  Summary: {readiness['domain_summary'][:100]}")
        print()
        return
    if getattr(args, 'crawl', ''):
        from cli.tools_cmd import crawl
        crawl(args.crawl, args.domain, getattr(args, 'crawl_max', 20), getattr(args, 'crawl_pattern', ''))
        return
    if getattr(args, 'fetch', ''):
        from cli.tools_cmd import fetch
        fetch(args.fetch)
        return
    if getattr(args, 'crawl_inject', False):
        from cli.tools_cmd import crawl_inject
        crawl_inject(args.domain)
        return
    if getattr(args, 'rag_status', False):
        from cli.tools_cmd import rag_status
        rag_status()
        return
    if getattr(args, 'rag_rebuild', False):
        from cli.tools_cmd import rag_rebuild
        rag_rebuild(args.domain)
        return
    if getattr(args, 'rag_search', None):
        from cli.tools_cmd import rag_search
        rag_search(args.rag_search, args.domain)
        return

    # MCP commands
    if getattr(args, 'mcp_status', False):
        from cli.tools_cmd import mcp_status
        mcp_status()
        return
    if getattr(args, 'mcp_start', False):
        from cli.tools_cmd import mcp_start_all
        mcp_start_all()
        return
    if getattr(args, 'mcp_stop', False):
        from cli.tools_cmd import mcp_stop_all
        mcp_stop_all()
        return
    if getattr(args, 'mcp_tools', False):
        from cli.tools_cmd import mcp_tools
        mcp_tools()
        return
    if getattr(args, 'mcp_health', False):
        from cli.tools_cmd import mcp_health
        mcp_health()
        return

    # Credential Vault commands
    if getattr(args, 'vault_store', None):
        from cli.vault import store as vault_store
        vault_store(args.vault_store[0], args.vault_store[1])
        return
    if getattr(args, 'vault_get', None):
        from cli.vault import get as vault_get
        vault_get(args.vault_get)
        return
    if getattr(args, 'vault_delete', None):
        from cli.vault import delete as vault_delete
        vault_delete(args.vault_delete)
        return
    if getattr(args, 'vault_list', False):
        from cli.vault import list_all as vault_list
        vault_list()
        return
    if getattr(args, 'vault_stats', False):
        from cli.vault import stats as vault_stats
        vault_stats()
        return

    # Stealth Browser commands
    if getattr(args, 'browser_fetch', None):
        from cli.browser_cmd import fetch_url
        fetch_url(args.browser_fetch)
        return
    if getattr(args, 'browser_test', False):
        from cli.browser_cmd import test_stealth
        test_stealth()
        return

    # Signal Intelligence commands
    if getattr(args, 'collect_signals', False):
        from cli.signals_cmd import run_collect_signals
        run_collect_signals(subreddits=args.signal_subs, time_filter=args.signal_time)
        return
    if getattr(args, 'rank_opportunities', False):
        from cli.signals_cmd import run_rank_opportunities
        run_rank_opportunities()
        return
    if getattr(args, 'weekly_brief', False):
        from cli.signals_cmd import run_weekly_brief
        run_weekly_brief()
        return
    if getattr(args, 'signal_status', False):
        from cli.signals_cmd import run_signal_status
        run_signal_status()
        return
    if getattr(args, 'enrich_signals', False):
        from cli.signals_cmd import run_enrich_signals
        run_enrich_signals()
        return
    if getattr(args, 'build_spec', None) is not None:
        from cli.signals_cmd import run_build_spec
        run_build_spec(args.build_spec)
        return
    if getattr(args, 'reality_check', None) is not None:
        from cli.signals_cmd import run_reality_check
        run_reality_check(args.reality_check, focus=getattr(args, 'reality_focus', ''))
        return
    if getattr(args, 'engagement_check', False):
        from cli.signals_cmd import run_engagement_check
        run_engagement_check()
        return

    # Project Orchestrator commands
    if getattr(args, 'project', None):
        from cli.project import run as project_run
        project_run(args.project, args.domain, workspace_dir=args.workspace)
        return
    if getattr(args, 'project_status', None):
        from cli.project import status as project_status
        project_status(args.project_status)
        return
    if getattr(args, 'project_resume', None):
        from cli.project import resume as project_resume
        project_resume(args.project_resume)
        return
    if getattr(args, 'project_approve', None):
        from cli.project import approve_phase
        approve_phase(args.project_approve)
        return
    if getattr(args, 'project_list', False):
        from cli.project import list_all as project_list
        project_list()
        return

    # Transistor Systems (Core Reliability) commands
    if getattr(args, 'bootstrap', False):
        from domain_bootstrap import bootstrap_domain
        result = bootstrap_domain(args.domain, goal=args.goal if hasattr(args, 'goal') else None)
        if result:
            print(f"\n  Bootstrap status: {result.get('phase', '?')}")
            if result.get("orientation"):
                print(f"  Orientation: {result['orientation'].get('summary', '?')[:100]}")
            if result.get("bootstrap_questions"):
                print(f"  Ready to run: python main.py --auto --rounds {len(result['bootstrap_questions'])} --domain {args.domain}")
        return
    if getattr(args, 'calibration', False):
        from domain_calibration import update_all_domains, get_domain_difficulty
        updated = update_all_domains()
        if not updated:
            print("  No domains with enough data for calibration.")
        else:
            print(f"\n  {'Domain':<25} {'Difficulty':<10} {'Mean':>6} {'Accept%':>8} {'StdDev':>7} {'Count':>6}")
            print(f"  {'─'*62}")
            for d, entry in sorted(updated.items()):
                diff = get_domain_difficulty(d)
                print(f"  {d:<25} {diff['difficulty']:<10} {entry['mean']:>6.1f} "
                      f"{entry['accept_rate']*100:>7.0f}% {entry['stddev']:>6.2f} {entry['count']:>6}")
        return
    if getattr(args, 'maintenance', False):
        from memory_lifecycle import run_maintenance_all, run_maintenance
        if args.domain != DEFAULT_DOMAIN:
            result = run_maintenance(args.domain)
            print(f"\n  Actions taken: {result.get('total_actions', 0)}")
        else:
            result = run_maintenance_all()
            print(f"\n  Domains maintained: {result.get('total_domains', 0)}")
            print(f"  Total actions: {result.get('total_actions', 0)}")
        return
    if getattr(args, 'verify_claims', False):
        from agents.claim_verifier import verify_claims
        results = verify_claims(args.domain)
        if not results:
            print(f"  No claims to verify for domain '{args.domain}'")
        else:
            confirmed = sum(1 for r in results if r["verdict"] == "confirmed")
            refuted = sum(1 for r in results if r["verdict"] == "refuted")
            print(f"\n  Verified {len(results)} claims: "
                  f"{confirmed} confirmed, {refuted} refuted")
        return
    if getattr(args, 'claim_stats', False):
        from agents.claim_verifier import get_claim_verification_stats
        stats = get_claim_verification_stats(args.domain)
        if stats.get("total_active", 0) == 0:
            print(f"  No active claims for domain '{args.domain}'")
        else:
            print(f"\n  Claim Verification Stats ({args.domain})")
            print(f"  {'─'*40}")
            print(f"  Active claims: {stats['total_active']}")
            print(f"  Verified:      {stats['verified']}")
            print(f"  Unverified:    {stats['unverified']}")
            print(f"  Rate:          {stats['verification_rate']:.0%}")
            if stats.get("verdicts"):
                print(f"  Verdicts:      {stats['verdicts']}")
        return
    if getattr(args, 'readiness', False):
        from validator import display_readiness
        display_readiness()
        return

    # Post-Cycle Review
    if getattr(args, 'review', False):
        from logs_review import generate_review, display_review
        domain_filter = args.domain if args.domain != DEFAULT_DOMAIN else None
        review = generate_review(domain=domain_filter, days=args.review_days)
        display_review(review)
        return
    if getattr(args, 'review_cycles', 0) > 0:
        from logs_review import load_cycle_history, summarize_cycles
        cycles = load_cycle_history(last_n=args.review_cycles)
        summary = summarize_cycles(cycles)
        if summary["total_cycles"] == 0:
            print("  No daemon cycles found.")
        else:
            print(f"\n  Daemon Cycle Summary (last {args.review_cycles})")
            print(f"  {'─'*45}")
            print(f"  Total cycles:  {summary['total_cycles']}")
            print(f"  Total rounds:  {summary['total_rounds']}")
            print(f"  Avg score:     {summary['avg_score']}")
            print(f"  Total cost:    ${summary['total_cost']:.4f}")
            print(f"  Success rate:  {summary['success_rate']:.0%}")
            print(f"  Domains:       {', '.join(summary['domains_touched'])}")
            print(f"  Period:        {summary.get('first_cycle', '?')[:10]} to "
                  f"{summary.get('last_cycle', '?')[:10]}")
        return

    # VPS Deploy commands
    if getattr(args, 'deploy', False) or getattr(args, 'deploy_dry_run', False):
        from cli.deploy_cmd import deploy
        deploy(dry_run=getattr(args, 'deploy_dry_run', False))
        return
    if getattr(args, 'deploy_health', False):
        from cli.deploy_cmd import health as deploy_health
        deploy_health()
        return
    if getattr(args, 'deploy_logs', False):
        from cli.deploy_cmd import logs as deploy_logs
        deploy_logs(domain=args.domain)
        return
    if getattr(args, 'deploy_schedule', False):
        from cli.deploy_cmd import schedule as deploy_schedule
        deploy_schedule()
        return
    if getattr(args, 'deploy_unschedule', False):
        from cli.deploy_cmd import unschedule as deploy_unschedule
        deploy_unschedule()
        return
    if getattr(args, 'deploy_configure', False):
        from cli.deploy_cmd import configure as deploy_configure
        deploy_configure(host=args.deploy_host, user=args.deploy_user)
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


# --- All CLI handler functions have been extracted to cli/ modules ---
# strategy → cli/strategy.py | knowledge → cli/knowledge.py
# research → cli/research.py | infrastructure → cli/infrastructure.py
# execution → cli/execution.py | tools → cli/tools_cmd.py
# vault → cli/vault.py | browser → cli/browser_cmd.py
# project → cli/project.py | deploy → cli/deploy_cmd.py


_HANDLERS_DELETED = True  # marker — remove once tests pass

if __name__ == "__main__":
    main()
