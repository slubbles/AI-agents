"""
Execution Meta-Analyst — Evolves HOW the system writes code.

Parallel to Brain's meta_analyst.py but for execution strategies.
Reads scored execution outputs → extracts patterns → rewrites execution strategy.

The execution strategy controls:
- How the planner decomposes tasks (granularity, tool selection patterns)
- How the executor writes code (style, patterns, error handling approach)
- What validation checks to emphasize
"""

import json
import os
import sys
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    ANTHROPIC_API_KEY, MODELS, STRATEGY_DIR,
    EXEC_EVOLVE_EVERY_N, EXEC_TRIAL_PERIOD,
)
from hands.exec_memory import load_exec_outputs, get_exec_stats
from strategy_store import (
    get_strategy, save_strategy, list_versions, get_strategy_performance,
)
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json
from utils.atomic_write import atomic_json_write

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MIN_EXEC_OUTPUTS_FOR_ANALYSIS = 3
MAX_EXEC_OUTPUTS_TO_ANALYZE = 10


def _evolution_log_path(domain: str) -> str:
    """Path to execution evolution log."""
    return os.path.join(STRATEGY_DIR, domain, "_exec_evolution_log.json")


def load_exec_evolution_log(domain: str) -> list[dict]:
    """Load the execution evolution log for a domain."""
    path = _evolution_log_path(domain)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_exec_evolution_entry(domain: str, entry: dict) -> None:
    """Append an entry to the exec evolution log."""
    log = load_exec_evolution_log(domain)
    log.append(entry)
    path = _evolution_log_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_json_write(path, log)


def _build_exec_meta_prompt() -> str:
    """Build the execution meta-analyst's system prompt."""
    today = date.today().isoformat()

    return f"""\
You are an execution meta-analyst. You analyze patterns in scored execution outputs
to evolve the system's execution strategy — HOW it writes code and uses tools.

TODAY'S DATE: {today}

Your job:
1. Look at recent execution outputs with their scores (correctness, completeness, 
   code quality, security, KB alignment).
2. Identify patterns: what approaches scored high vs. low.
3. Generate an improved execution strategy that addresses weaknesses.

ANALYSIS FOCUS:
- Are plans too granular or too coarse? (affects planner)
- Is code quality consistently weak? (style, error handling, types)
- Are security issues recurring? (hardcoded values, input validation)
- Do tests get written? Do they pass?
- Are there tool usage patterns that work better? (write+test vs write-all-then-test)

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
    "analysis": {{
        "strongest_dimension": "correctness",
        "weakest_dimension": "code_quality",
        "score_trend": "improving|declining|stable",
        "patterns": ["pattern 1", "pattern 2"],
        "failure_modes": ["common failure 1"]
    }},
    "new_strategy": "The complete new execution strategy text...",
    "changes_made": ["change 1", "change 2"],
    "reasoning": "Why these changes should improve execution quality"
}}

STRATEGY WRITING RULES:
- The strategy is a natural language document read by the planner and executor.
- Be specific: "always write tests alongside code" not "consider testing".
- Include tool usage guidance: when to use code vs terminal tool.
- Include code style preferences learned from what scored well.
- Keep it under 2000 words.
- Every claim should be backed by a pattern you observed.
"""


def _build_targeted_evolution_prompt(weakest_dimension: str) -> str:
    """Build a focused prompt that targets the single weakest scoring dimension."""
    today = date.today().isoformat()
    
    return f"""\
You are an execution meta-analyst performing a TARGETED evolution. You must improve
the system's execution strategy on ONE specific dimension: {weakest_dimension}.

TODAY'S DATE: {today}

TARGETED DIMENSION: {weakest_dimension}

Your job:
1. Look at recent execution outputs. Focus specifically on what causes LOW {weakest_dimension} scores.
2. Identify concrete, actionable patterns that hurt {weakest_dimension}.
3. Generate a MODIFIED execution strategy that specifically addresses {weakest_dimension} weaknesses.
4. Keep all other parts of the strategy UNCHANGED — only patch what affects {weakest_dimension}.

RULES:
- Do NOT rewrite the whole strategy. Make surgical, targeted edits.
- Every change must clearly target {weakest_dimension}.
- Be specific: "add input validation to all handlers" not "improve security".
- Keep the strategy under 2000 words.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
    "target_dimension": "{weakest_dimension}",
    "analysis": {{
        "current_score": 0.0,
        "root_causes": ["cause 1", "cause 2"],
        "patterns": ["pattern 1", "pattern 2"]
    }},
    "new_strategy": "The complete modified execution strategy text...",
    "changes_made": ["change targeting {weakest_dimension}"],
    "reasoning": "Why these specific changes should improve {weakest_dimension}"
}}
"""


def _evaluate_last_evolution(domain: str, outputs: list[dict]) -> dict | None:
    """
    Check if the last strategy evolution actually helped.
    
    Looks at the evolution log to find the last targeted change,
    then compares scores before/after on that specific dimension.
    
    Returns evaluation dict or None if no previous evolution to evaluate.
    """
    log = load_exec_evolution_log(domain)
    if not log:
        return None
    
    last = log[-1]
    if last.get("outcome") not in ("pending", "trial"):
        return None  # Already evaluated
    
    target_dim = last.get("target_dimension", "")
    evolution_date = last.get("date", "")
    
    if not target_dim or not evolution_date:
        return None  # Old-style evolution without targeting — skip evaluation
    
    # Split outputs into before/after the evolution
    before = []
    after = []
    for o in outputs:
        ts = o.get("timestamp", "")[:10]
        if ts and ts >= evolution_date:
            after.append(o)
        else:
            before.append(o)
    
    # Need at least 2 outputs after evolution to evaluate
    if len(after) < 2:
        return {"status": "insufficient_data", "after_count": len(after)}
    
    # Compare the targeted dimension specifically
    def avg_dim(outs: list[dict], dim: str) -> float:
        scores = []
        for o in outs:
            val = o.get("validation", {})
            dim_scores = val.get("scores", {})
            if dim in dim_scores:
                scores.append(dim_scores[dim])
        return sum(scores) / len(scores) if scores else 0.0
    
    before_score = avg_dim(before[-5:], target_dim) if before else 0.0  # Use last 5 before
    after_score = avg_dim(after, target_dim)
    delta = after_score - before_score
    
    evaluation = {
        "status": "evaluated",
        "target_dimension": target_dim,
        "before_score": round(before_score, 2),
        "after_score": round(after_score, 2),
        "delta": round(delta, 2),
        "improved": delta > 0.0,
        "version": last.get("version", ""),
    }
    
    # Update the log entry with outcome
    outcome = "improved" if delta > 0.0 else ("neutral" if delta >= -0.3 else "regressed")
    last["outcome"] = outcome
    last["outcome_delta"] = round(delta, 2)
    
    path = _evolution_log_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_json_write(path, log)
    
    return evaluation


def _prepare_exec_analysis_data(outputs: list[dict], current_strategy: str | None) -> str:
    """Format execution outputs + strategy + analytics for the meta-analyst."""
    data_parts = []

    # Current strategy
    if current_strategy:
        data_parts.append(f"CURRENT EXECUTION STRATEGY:\n{current_strategy[:2000]}\n")
    else:
        data_parts.append("CURRENT EXECUTION STRATEGY: (none — using defaults)\n")

    # Score summary
    scores = [o.get("overall_score", 0) for o in outputs]
    if scores:
        data_parts.append(
            f"SCORE SUMMARY: {len(outputs)} outputs, "
            f"avg {sum(scores)/len(scores):.1f}, "
            f"min {min(scores):.1f}, max {max(scores):.1f}\n"
        )

    # Inject analytics summary (if available)
    domain = outputs[0].get("domain", "general") if outputs else "general"
    try:
        from hands.exec_analytics import analyze_executions
        analytics = analyze_executions(domain)
        if analytics.get("has_data"):
            # Tool success rates
            tool_stats = analytics.get("tool_stats", {})
            if tool_stats:
                tool_lines = [f"  {t}: {s['success_rate']:.0%} ({s['total_uses']} uses)"
                             for t, s in list(tool_stats.items())[:5]]
                data_parts.append("TOOL SUCCESS RATES:\n" + "\n".join(tool_lines) + "\n")
            
            # Score trend
            traj = analytics.get("score_trajectory", {})
            if traj.get("trend"):
                data_parts.append(
                    f"SCORE TREND: {traj['trend']} "
                    f"({traj['first_third_avg']} → {traj['last_third_avg']})\n"
                )
            
            # Dimension weaknesses
            dims = analytics.get("dimension_averages", {})
            if dims:
                weakest = min(dims, key=dims.get)
                data_parts.append(
                    f"WEAKEST DIMENSION: {weakest} ({dims[weakest]:.1f}/10)\n"
                )
            
            # Efficiency
            eff = analytics.get("efficiency", {})
            if eff.get("failure_rate", 0) > 0.1:
                data_parts.append(
                    f"⚠ HIGH STEP FAILURE RATE: {eff['failure_rate']:.0%}\n"
                )
    except Exception:
        pass  # Analytics are optional enrichment

    # Individual outputs (capped)
    for i, output in enumerate(outputs[-MAX_EXEC_OUTPUTS_TO_ANALYZE:]):
        val = output.get("validation", {})
        dim_scores = val.get("scores", {})
        exec_data = output.get("execution", {})

        entry = (
            f"\n--- Output {i+1} ---\n"
            f"Goal: {output.get('goal', '?')[:200]}\n"
            f"Score: {output.get('overall_score', 0)}/10\n"
            f"Dimensions: {json.dumps(dim_scores)}\n"
            f"Steps: {exec_data.get('completed_steps', 0)} completed, "
            f"{exec_data.get('failed_steps', 0)} failed\n"
            f"Artifacts: {len(exec_data.get('artifacts', []))}\n"
            f"Strengths: {val.get('strengths', [])}\n"
            f"Weaknesses: {val.get('weaknesses', [])}\n"
            f"Feedback: {val.get('actionable_feedback', '')[:300]}\n"
        )
        data_parts.append(entry)

    # Evolution history (last 3)
    log = load_exec_evolution_log(outputs[0].get("domain", "general") if outputs else "general")
    if log:
        data_parts.append("\nPREVIOUS EVOLUTION DECISIONS:")
        for entry in log[-3:]:
            data_parts.append(
                f"  {entry.get('version', '?')}: {'; '.join(entry.get('changes', []))}"
                f" (outcome: {entry.get('outcome', 'pending')})"
            )

    return "\n".join(data_parts)


def analyze_and_evolve_exec(domain: str) -> dict | None:
    """
    Run the execution meta-analyst: analyze scored outputs → improve exec strategy.
    
    Uses targeted dimension evolution: identifies the single weakest dimension
    and generates a surgical strategy patch instead of rewriting everything.
    Evaluates whether the last evolution helped; reverts to general evolution
    if targeted approach stalls.

    Returns:
        Dict with analysis + new strategy version, or None if not enough data.
    """
    all_outputs = load_exec_outputs(domain, min_score=0)

    if len(all_outputs) < MIN_EXEC_OUTPUTS_FOR_ANALYSIS:
        print(f"[EXEC-META] Not enough data ({len(all_outputs)}/{MIN_EXEC_OUTPUTS_FOR_ANALYSIS}). Skipping.")
        return None

    # Load current execution strategy
    current_strategy, current_version = get_strategy("executor", domain)

    print(f"[EXEC-META] Analyzing {len(all_outputs)} outputs for '{domain}'...")
    print(f"[EXEC-META] Current exec strategy: {current_version or 'default'}")

    # Evaluate last evolution before proceeding
    last_eval = _evaluate_last_evolution(domain, all_outputs)
    if last_eval:
        if last_eval.get("status") == "evaluated":
            dim = last_eval.get("target_dimension", "?")
            delta = last_eval.get("delta", 0)
            outcome = "improved" if delta > 0 else ("neutral" if delta >= -0.3 else "regressed")
            print(f"[EXEC-META] Last evolution targeting '{dim}': {outcome} (delta: {delta:+.2f})")
            if last_eval.get("improved"):
                print(f"[EXEC-META]   ✓ {dim} improved from {last_eval['before_score']} → {last_eval['after_score']}")
            elif delta < -0.3:
                print(f"[EXEC-META]   ✗ {dim} regressed — will try different approach")
        elif last_eval.get("status") == "insufficient_data":
            print(f"[EXEC-META] Previous evolution still in trial (only {last_eval.get('after_count', 0)} outputs)")

    # Identify weakest dimension for targeted evolution
    weakest_dim = _identify_weakest_dimension(all_outputs)
    use_targeted = weakest_dim is not None
    
    if use_targeted:
        print(f"[EXEC-META] Targeting weakest dimension: {weakest_dim}")
    else:
        print(f"[EXEC-META] Using general evolution (no clear weak dimension)")

    # Prepare analysis data
    analysis_data = _prepare_exec_analysis_data(all_outputs, current_strategy)

    # Choose prompt type — targeted or general
    if use_targeted:
        prompt = _build_targeted_evolution_prompt(weakest_dim)
    else:
        prompt = _build_exec_meta_prompt()

    response = create_message(
        client,
        model=MODELS["exec_meta_analyst"],
        max_tokens=4096,
        system=prompt,
        messages=[{
            "role": "user",
            "content": f"Analyze these scored execution outputs and generate an improved strategy.\n\nDATA:\n{analysis_data}",
        }],
    )

    # Track cost
    log_cost(
        MODELS["exec_meta_analyst"],
        response.usage.input_tokens,
        response.usage.output_tokens,
        "exec_meta_analyst",
        domain,
    )

    raw_text = response.content[0].text.strip()

    # Parse response
    result = extract_json(raw_text, expected_keys={"new_strategy", "changes_made", "reasoning"})
    if not result:
        print("[EXEC-META] Failed to parse output")
        return None

    new_strategy = result.get("new_strategy")
    if not new_strategy:
        print("[EXEC-META] No new strategy in output")
        return None

    # Compute version number
    existing = list_versions("executor", domain)
    if existing:
        nums = []
        for v in existing:
            try:
                nums.append(int(v.replace("v", "")))
            except ValueError:
                pass
        next_num = max(nums) + 1 if nums else 1
    else:
        next_num = 1

    new_version = f"v{next_num:03d}"

    changes = result.get("changes_made", [])
    reasoning = result.get("reasoning", "")
    target_dim_label = f" [targeting: {weakest_dim}]" if use_targeted else ""
    reason = f"Changes{target_dim_label}: {'; '.join(changes)}. Reasoning: {reasoning}"

    # Save as pending (requires approval)
    filepath = save_strategy(
        agent_role="executor",
        domain=domain,
        strategy_text=new_strategy,
        version=new_version,
        reason=reason,
        status="pending",
    )

    print(f"[EXEC-META] New exec strategy: {new_version} (PENDING APPROVAL)")
    if use_targeted:
        print(f"[EXEC-META] Targeted dimension: {weakest_dim}")
    print(f"[EXEC-META] File: {filepath}")

    analysis = result.get("analysis", {})
    strongest = analysis.get("strongest_dimension", "?")
    weakest = analysis.get("weakest_dimension", weakest_dim or "?")
    print(f"[EXEC-META] Strongest: {strongest}")
    print(f"[EXEC-META] Weakest: {weakest}")
    for change in changes:
        print(f"  → {change}")

    # Log evolution entry with target dimension
    _save_exec_evolution_entry(domain, {
        "version": new_version,
        "previous_version": current_version or "default",
        "date": date.today().isoformat(),
        "changes": changes,
        "reasoning": reasoning,
        "target_dimension": weakest_dim or "",
        "targeted": use_targeted,
        "weakest_dimension": analysis.get("weakest_dimension", ""),
        "outcome": "pending",
    })

    return {
        "analysis": analysis,
        "changes_made": changes,
        "new_version": new_version,
        "reasoning": reasoning,
        "strategy_filepath": filepath,
        "targeted": use_targeted,
        "target_dimension": weakest_dim,
        "last_evolution_eval": last_eval,
    }


def _identify_weakest_dimension(outputs: list[dict]) -> str | None:
    """
    Identify the single weakest scoring dimension across recent outputs.
    Returns the dimension name, or None if scores are too uniform.
    """
    dim_totals: dict[str, list[float]] = {}
    
    # Use the last 10 outputs
    recent = outputs[-10:]
    for o in recent:
        val = o.get("validation", {})
        scores = val.get("scores", {})
        for dim, score in scores.items():
            if isinstance(score, (int, float)):
                dim_totals.setdefault(dim, []).append(score)
    
    if not dim_totals:
        return None
    
    # Calculate averages
    dim_avgs = {dim: sum(s) / len(s) for dim, s in dim_totals.items() if s}
    if not dim_avgs:
        return None
    
    # Find weakest
    weakest = min(dim_avgs, key=dim_avgs.get)  # type: ignore
    strongest = max(dim_avgs, key=dim_avgs.get)  # type: ignore
    
    # Only target if there's a meaningful gap (>0.5 points)
    gap = dim_avgs[strongest] - dim_avgs[weakest]
    if gap < 0.5:
        return None  # Scores too uniform, use general evolution
    
    return weakest
