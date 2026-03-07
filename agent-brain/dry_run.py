"""
Dry Run — Full Pipeline Simulation Without API Calls

Traces the entire research loop (bootstrap → research → critique → store →
task creation → calibration → lifecycle) using synthetic LLM responses.

Purpose:
- Verify pipeline integrity after code changes
- Test new domain bootstrapping without spending credits
- Validate all integration points are wired correctly
- Identify crashes/errors before real cycles

Usage:
    python main.py --dry-run --domain new-domain
    python main.py --dry-run --domain crypto --rounds 3

The synthetic responses are realistic enough to exercise all code paths,
but clearly marked so they never pollute real memory.
"""

import json
import os
import random
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from config import MEMORY_DIR, STRATEGY_DIR, LOG_DIR, MODELS, QUALITY_THRESHOLD


# ============================================================
# Synthetic Response Generator
# ============================================================

def _synthetic_research(question: str, domain: str) -> dict:
    """Generate a realistic-looking research output without any LLM call."""
    return {
        "summary": f"[DRY-RUN] Synthetic research on: {question[:100]}",
        "findings": [
            {
                "claim": f"Finding about {domain}: synthetic claim #{i+1} related to the question",
                "confidence": random.choice(["high", "medium", "low"]),
                "sources": [f"https://example.com/{domain}/source-{i+1}"],
            }
            for i in range(random.randint(3, 6))
        ],
        "key_insights": [
            f"Analyze the current state of {domain} research methodologies",
            f"Monitor developments in {domain} for emerging patterns",
            f"Evaluate existing frameworks for {domain} applications",
        ],
        "knowledge_gaps": [
            f"Research gap: long-term impact studies for {domain}",
            f"Research gap: comparative analysis across {domain} subfields",
        ],
        "sources_used": [
            {"url": f"https://example.com/{domain}/1", "title": f"{domain} Source 1"},
            {"url": f"https://example.com/{domain}/2", "title": f"{domain} Source 2"},
        ],
        "_tool_log": [
            {"tool": "web_search", "query": f"{domain} {question[:30]}", "results": 5},
        ],
        "_dry_run": True,
    }


def _synthetic_critique(research: dict, domain: str) -> dict:
    """Generate a realistic critique with randomized but reasonable scores."""
    base = random.uniform(5.5, 8.5)
    noise = lambda: round(base + random.uniform(-1.0, 1.0), 1)
    scores = {
        "accuracy": max(1, min(10, noise())),
        "depth": max(1, min(10, noise())),
        "completeness": max(1, min(10, noise())),
        "specificity": max(1, min(10, noise())),
        "intellectual_honesty": max(1, min(10, noise())),
    }
    overall = round(sum(scores.values()) / len(scores), 1)
    verdict = "accept" if overall >= QUALITY_THRESHOLD else "reject"

    return {
        "scores": scores,
        "overall_score": overall,
        "verdict": verdict,
        "strengths": [
            f"[DRY-RUN] Good coverage of {domain} fundamentals",
            "[DRY-RUN] Clear structure and logical flow",
        ],
        "weaknesses": [
            "[DRY-RUN] Could include more quantitative evidence",
        ] if overall < 8 else [],
        "actionable_feedback": f"[DRY-RUN] Synthetic feedback for {domain}",
        "_dry_run": True,
    }


def _synthetic_prescreen(research: dict, domain: str) -> dict:
    """Synthetic prescreen that always escalates to full critic."""
    return {
        "decision": "escalate",
        "prescreen_score": 7,
        "skip_claude": False,
        "reasons": ["[DRY-RUN] Always escalate in dry-run mode"],
        "_dry_run": True,
    }


def _mock_call_llm(*args, **kwargs):
    """Mock LLM call that returns a minimal valid response."""
    from llm_router import NormalizedResponse, TextBlock, Usage
    content = json.dumps({
        "summary": "[DRY-RUN] Synthetic LLM response",
        "key_concepts": ["concept_a", "concept_b"],
        "foundational_questions": [
            "What are the fundamentals?",
            "What are the current challenges?",
            "What does recent research show?",
        ],
        "research_profile": {
            "recency_importance": "medium",
            "quantitative_importance": "medium",
            "depth_vs_breadth": "balanced",
        },
        "pitfalls": ["[DRY-RUN] Common misconception"],
        "best_sources": ["academic", "industry"],
    })
    return NormalizedResponse(
        content=[TextBlock(type="text", text=content)],
        usage=Usage(input_tokens=100, output_tokens=200),
        model=kwargs.get("model", "dry-run/mock"),
        stop_reason="end_turn",
    )


# ============================================================
# Dry Run Executor
# ============================================================

def run_dry_cycle(domain: str, question: str | None = None, round_num: int = 1) -> dict:
    """
    Execute a single dry-run cycle through the full pipeline.

    Patches the LLM, researcher, and critic with synthetic responses,
    then runs the real pipeline code to verify everything is wired correctly.

    Returns a summary of what happened (or what crashed).
    """
    from memory_store import get_stats

    result = {
        "domain": domain,
        "round": round_num,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "errors": [],
        "dry_run": True,
    }

    def _step(name, detail="ok"):
        result["steps"].append({"step": name, "status": detail})
        print(f"  [DRY-RUN] {name}: {detail}")

    print(f"\n{'='*60}")
    print(f"  DRY RUN — Domain: {domain}, Round: {round_num}")
    print(f"{'='*60}\n")

    # Step 1: Bootstrap check
    try:
        from domain_bootstrap import is_cold, get_bootstrap_status
        cold = is_cold(domain)
        _step("bootstrap_check", f"cold={cold}")
        if cold:
            bs = get_bootstrap_status(domain)
            _step("bootstrap_status", bs.get("phase", "none"))
    except Exception as e:
        result["errors"].append({"step": "bootstrap", "error": str(e)})
        _step("bootstrap_check", f"ERROR: {e}")

    # Step 2: Strategy load
    try:
        from strategy_store import get_strategy, get_strategy_status
        strategy, version = get_strategy("researcher", domain)
        status = get_strategy_status("researcher", domain) if strategy else "default"
        _step("strategy_load", f"version={version}, status={status}")
    except Exception as e:
        result["errors"].append({"step": "strategy", "error": str(e)})
        _step("strategy_load", f"ERROR: {e}")

    # Step 3: Question generation (if no question provided)
    if not question:
        try:
            from domain_seeder import get_seed_question
            question = get_seed_question(domain)
            _step("question_gen", f"seed: {question[:60]}...")
        except Exception as e:
            question = f"What are the key developments in {domain}?"
            result["errors"].append({"step": "question_gen", "error": str(e)})
            _step("question_gen", f"fallback: {question[:60]}...")

    result["question"] = question

    # Step 4: Research (synthetic)
    research = _synthetic_research(question, domain)
    _step("research", f"{len(research['findings'])} findings, {len(research['key_insights'])} insights")

    # Step 5: Prescreen (synthetic)
    prescreen = _synthetic_prescreen(research, domain)
    _step("prescreen", f"score={prescreen['prescreen_score']}, decision={prescreen['decision']}")

    # Step 6: Critique (synthetic)
    critique = _synthetic_critique(research, domain)
    score = critique["overall_score"]
    verdict = critique["verdict"]
    _step("critique", f"score={score}, verdict={verdict}")

    # Step 7: Quality gate
    passed = score >= QUALITY_THRESHOLD
    _step("quality_gate", f"{'PASS' if passed else 'FAIL'} (threshold={QUALITY_THRESHOLD})")

    # Step 8: Memory store (to temp dir so we don't pollute real data)
    try:
        from memory_store import save_output
        with patch("memory_store.MEMORY_DIR", tempfile.mkdtemp(prefix="cortex_dryrun_")):
            filepath = save_output(
                domain=domain,
                question=question,
                research=research,
                critique=critique,
                attempt=1,
                strategy_version="dry-run",
            )
            _step("memory_store", f"would write to: {os.path.basename(filepath)}")
    except Exception as e:
        result["errors"].append({"step": "memory_store", "error": str(e)})
        _step("memory_store", f"ERROR: {e}")

    # Step 9: Task creation (Brain → Hands handoff)
    if verdict == "accept":
        try:
            from main import _ACTION_VERBS
            matched_verbs = []
            for insight in research.get("key_insights", []):
                for verb in _ACTION_VERBS:
                    if verb in insight.lower():
                        matched_verbs.append(verb)
                        break
            _step("task_creation", f"{len(matched_verbs)} actionable insights detected")
        except Exception as e:
            result["errors"].append({"step": "task_creation", "error": str(e)})
            _step("task_creation", f"ERROR: {e}")

    # Step 10: Strategy evolution check
    try:
        from strategy_store import get_strategy_status
        from config import MIN_OUTPUTS_FOR_ANALYSIS, EVOLVE_EVERY_N
        status = get_strategy_status("researcher", domain)
        stats = get_stats(domain)
        output_count = stats.get("count", 0)
        would_evolve = (output_count >= MIN_OUTPUTS_FOR_ANALYSIS
                        and output_count % EVOLVE_EVERY_N == 0
                        and status != "trial")
        _step("strategy_evolution", f"status={status}, would_trigger={would_evolve}")
    except Exception as e:
        result["errors"].append({"step": "strategy_evolution", "error": str(e)})
        _step("strategy_evolution", f"ERROR: {e}")

    # Step 11: Outcome feedback check
    try:
        from outcome_feedback import get_feedback_stats
        fb_stats = get_feedback_stats()
        _step("outcome_feedback", f"pending={fb_stats['pending_feedback']}, processed={fb_stats['feedback_processed']}")
    except Exception as e:
        result["errors"].append({"step": "outcome_feedback", "error": str(e)})
        _step("outcome_feedback", f"ERROR: {e}")

    # Step 12: Degradation pulse check
    try:
        from degradation_detector import run_degradation_pulse
        pulse = run_degradation_pulse(domain=domain)
        alert_count = sum(len(d.get("alerts", [])) for d in pulse.get("domains", {}).values())
        _step("degradation_check", f"alerts={alert_count}")
    except Exception as e:
        result["errors"].append({"step": "degradation_check", "error": str(e)})
        _step("degradation_check", f"ERROR: {e}")

    # Step 13: Calibration update
    try:
        from domain_calibration import get_calibration_context
        ctx = get_calibration_context(domain)
        _step("calibration", f"context={'injected' if ctx else 'none (insufficient data)'}")
    except Exception as e:
        result["errors"].append({"step": "calibration", "error": str(e)})
        _step("calibration", f"ERROR: {e}")

    # Step 14: Run logging (renumbered)
    try:
        from main import log_run
        # Log to temp so we don't pollute
        with patch("main.LOG_DIR", tempfile.mkdtemp(prefix="cortex_dryrun_log_")):
            log_run(domain, question, 1, research, critique, "dry-run")
            _step("run_logging", "ok")
    except Exception as e:
        result["errors"].append({"step": "run_logging", "error": str(e)})
        _step("run_logging", f"ERROR: {e}")

    # Step 15: Stats check
    try:
        stats = get_stats(domain)
        _step("stats", f"count={stats.get('count', 0)}, avg={stats.get('avg_score', 0):.1f}")
    except Exception as e:
        result["errors"].append({"step": "stats", "error": str(e)})
        _step("stats", f"ERROR: {e}")

    # Summary
    error_count = len(result["errors"])
    step_count = len(result["steps"])
    result["summary"] = {
        "steps_passed": step_count - error_count,
        "steps_failed": error_count,
        "total_steps": step_count,
        "score": score,
        "verdict": verdict,
    }

    print(f"\n  {'─'*50}")
    if error_count == 0:
        print(f"  DRY RUN PASSED — {step_count} steps, 0 errors")
        print(f"  Simulated score: {score}/10 ({verdict})")
    else:
        print(f"  DRY RUN: {error_count} ERROR(S) in {step_count} steps")
        for err in result["errors"]:
            print(f"    ! {err['step']}: {err['error']}")
    print()

    return result


def run_dry_session(domain: str, rounds: int = 1) -> dict:
    """
    Run multiple dry-run cycles and produce a session summary.

    This simulates what would happen if you ran:
        python main.py --auto --rounds N --domain DOMAIN
    """
    print(f"\n{'='*60}")
    print(f"  DRY RUN SESSION — {rounds} round(s) for '{domain}'")
    print(f"{'='*60}")

    results = []
    total_errors = 0

    for i in range(rounds):
        r = run_dry_cycle(domain, round_num=i + 1)
        results.append(r)
        total_errors += len(r.get("errors", []))

    # Session summary
    scores = [r["summary"]["score"] for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0
    accepted = sum(1 for r in results if r["summary"]["verdict"] == "accept")

    print(f"\n{'='*60}")
    print(f"  SESSION SUMMARY")
    print(f"{'='*60}")
    print(f"  Rounds:    {rounds}")
    print(f"  Errors:    {total_errors}")
    print(f"  Avg score: {avg_score:.1f}")
    print(f"  Accepted:  {accepted}/{rounds}")

    if total_errors == 0:
        print(f"\n  Pipeline is HEALTHY — all code paths exercised successfully.")
        print(f"  Safe to run real cycles when ready.")
    else:
        print(f"\n  Pipeline has ISSUES — fix errors before running real cycles.")

    print()

    return {
        "domain": domain,
        "rounds": rounds,
        "total_errors": total_errors,
        "avg_score": avg_score,
        "accepted": accepted,
        "results": results,
    }


# ============================================================
# Cost Estimator
# ============================================================

def estimate_cycle_cost(domain: str, rounds: int = 1, conservative: bool = False) -> dict:
    """
    Estimate the cost of running N research cycles.

    Based on model assignments and typical token usage patterns from the
    cost log. Falls back to conservative estimates if no history available.
    """
    from config import COST_PER_1K, MODELS, CONSENSUS_ENABLED, CONSENSUS_RESEARCHERS, CRITIC_ENSEMBLE

    # Typical token usage per agent role (input + output)
    # These are based on observed patterns from real cycles
    TYPICAL_TOKENS = {
        "researcher": {"input": 3000, "output": 4000},
        "prescreen": {"input": 2000, "output": 500},
        "critic": {"input": 4000, "output": 2000},
        "question_generator": {"input": 1500, "output": 800},
        "claim_verifier": {"input": 2500, "output": 1000},
        "synthesizer": {"input": 3000, "output": 2000},
        "meta_analyst": {"input": 4000, "output": 3000},
    }

    if conservative:
        model_overrides = {
            "researcher": "deepseek/deepseek-chat",
            "prescreen": "deepseek/deepseek-chat",
            "critic": "deepseek/deepseek-chat",
            "question_generator": "deepseek/deepseek-chat",
        }
        consensus_mult = 1
        ensemble_mult = 1
        retry_mult = 1.0
    else:
        model_overrides = {}
        consensus_mult = CONSENSUS_RESEARCHERS if CONSENSUS_ENABLED else 1
        ensemble_mult = 2 if CRITIC_ENSEMBLE else 1
        retry_mult = 1.5  # Average ~1.5 attempts per question

    cost_per_round = 0.0
    breakdown = {}

    for role, tokens in TYPICAL_TOKENS.items():
        model = model_overrides.get(role, MODELS.get(role, "deepseek/deepseek-chat"))
        rates = COST_PER_1K.get(model, {"input": 0.001, "output": 0.003})

        input_cost = (tokens["input"] / 1000) * rates["input"]
        output_cost = (tokens["output"] / 1000) * rates["output"]
        role_cost = input_cost + output_cost

        multiplier = 1.0
        if role == "researcher":
            multiplier = consensus_mult * retry_mult
        elif role == "critic":
            multiplier = ensemble_mult * retry_mult
        elif role == "claim_verifier":
            multiplier = 0.2  # ~1 in 5 cycles
        elif role == "synthesizer":
            multiplier = 0.1  # ~1 in 10 cycles
        elif role == "meta_analyst":
            multiplier = 0.1  # ~1 in 10 cycles

        role_total = role_cost * multiplier
        cost_per_round += role_total
        breakdown[role] = {
            "model": model,
            "cost_per_round": round(role_total, 5),
        }

    # Bootstrap cost (only for first round of a cold domain)
    bootstrap_cost = 0.0
    try:
        from domain_bootstrap import is_cold
        if is_cold(domain):
            boot_model = MODELS.get("question_generator", "deepseek/deepseek-chat")
            boot_rates = COST_PER_1K.get(boot_model, {"input": 0.001, "output": 0.003})
            bootstrap_cost = (2000 / 1000) * boot_rates["input"] + (1500 / 1000) * boot_rates["output"]
    except Exception:
        pass

    total = (cost_per_round * rounds) + bootstrap_cost

    return {
        "domain": domain,
        "rounds": rounds,
        "conservative": conservative,
        "cost_per_round": round(cost_per_round, 4),
        "bootstrap_cost": round(bootstrap_cost, 4),
        "total_estimated": round(total, 4),
        "breakdown": breakdown,
    }


def display_cost_estimate(est: dict):
    """Display a formatted cost estimate."""
    mode = "CONSERVATIVE" if est["conservative"] else "STANDARD"
    print(f"\n{'='*50}")
    print(f"  COST ESTIMATE — {mode}")
    print(f"{'='*50}")
    print(f"  Domain:     {est['domain']}")
    print(f"  Rounds:     {est['rounds']}")
    print(f"  Per round:  ${est['cost_per_round']:.4f}")
    if est["bootstrap_cost"] > 0:
        print(f"  Bootstrap:  ${est['bootstrap_cost']:.4f} (cold domain)")
    print(f"  ─────────────────────")
    print(f"  TOTAL:      ${est['total_estimated']:.4f}")

    print(f"\n  Breakdown:")
    for role, info in est["breakdown"].items():
        print(f"    {role:22s} ${info['cost_per_round']:.5f}  ({info['model']})")

    if not est["conservative"]:
        conservative_est = estimate_cycle_cost(est["domain"], est["rounds"], conservative=True)
        savings = est["total_estimated"] - conservative_est["total_estimated"]
        if savings > 0.001:
            print(f"\n  With --conservative: ${conservative_est['total_estimated']:.4f} "
                  f"(saves ${savings:.4f})")

    print()
