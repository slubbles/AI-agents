"""
Meta-Analyst Agent (Layer 3 — Behavioral Adaptation)

Reads scored outputs from memory → extracts patterns → rewrites agent strategy documents.
This is the novel piece: strategy evolution driven by empirical performance scoring.

The meta-analyst:
1. Loads recent scored outputs for a domain
2. Loads the evolution log (past decisions + their outcomes)
3. Analyzes what scored well vs. poorly across dimensions
4. Extracts actionable patterns (do more of X, stop doing Y)
5. Generates a new strategy document that incorporates these patterns
6. Logs this evolution decision for future reference
"""

import json
import sys
import os
from datetime import date, datetime, timezone

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    ANTHROPIC_API_KEY, MODELS, MIN_OUTPUTS_FOR_ANALYSIS, MAX_OUTPUTS_TO_ANALYZE,
    EVOLVE_EVERY_N, STRATEGY_DIR, MAX_EVOLUTION_HISTORY, IMMUTABLE_STRATEGY_CLAUSES,
    DRIFT_WARNING_THRESHOLD,
)
from memory_store import load_outputs
from strategy_store import get_strategy, save_strategy, list_versions, get_strategy_performance
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ============================================================
# Evolution Log — persistent memory across meta-analysis runs
# ============================================================

def _evolution_log_path(domain: str) -> str:
    """Return path to evolution log for a domain."""
    return os.path.join(STRATEGY_DIR, domain, "_evolution_log.json")


def load_evolution_log(domain: str) -> list[dict]:
    """Load the full evolution log for a domain."""
    path = _evolution_log_path(domain)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_evolution_entry(domain: str, entry: dict) -> None:
    """Append a new evolution entry to the domain's log."""
    log = load_evolution_log(domain)
    log.append(entry)
    path = _evolution_log_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(log, f, indent=2)


def _format_evolution_history(domain: str) -> str:
    """Format past evolution decisions for injection into the meta-analyst prompt."""
    log = load_evolution_log(domain)
    if not log:
        return "(No previous evolution history — this is the first analysis)"
    
    # Show last N evolutions to keep context manageable
    recent = log[-MAX_EVOLUTION_HISTORY:]
    entries = []
    for entry in recent:
        outcome = entry.get("outcome", "pending")
        score_before = entry.get("score_before", "?")
        score_after = entry.get("score_after", "?")
        entries.append(
            f"- Version {entry.get('version', '?')} ({entry.get('date', '?')}): "
            f"Changes: {'; '.join(entry.get('changes', [])[:3])}. "
            f"Outcome: {outcome} (score {score_before} → {score_after})"
        )
    return "\n".join(entries)


def update_evolution_outcome(domain: str, version: str, outcome: str, score_after: float) -> None:
    """
    Update the outcome of a past evolution entry once we know how it performed.
    Called after trial evaluation (confirm/rollback).
    """
    log = load_evolution_log(domain)
    for entry in reversed(log):
        if entry.get("version") == version:
            entry["outcome"] = outcome
            entry["score_after"] = score_after
            break
    path = _evolution_log_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(log, f, indent=2)


def _build_meta_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a meta-analyst for an autonomous research system. TODAY'S DATE: {today}.

Your job: analyze scored research outputs to find patterns, then rewrite the researcher's
strategy document to improve future performance.

You receive:
1. A set of scored research outputs (each with scores across 5 dimensions + critic feedback)
2. The current strategy document the researcher is using
3. EVOLUTION HISTORY: past decisions you made and their outcomes (did scores improve?)

CRITICAL: Use the evolution history to avoid repeating changes that failed. Double down on
changes that worked. If the history shows a pattern (e.g., "adding source verification improved
accuracy"), build on it rather than reverting.

You must:
1. Identify patterns: what behaviors correlate with HIGH scores? What correlates with LOW?
2. Extract specific, actionable improvements (not vague advice)
3. Write a NEW strategy document that preserves what works and fixes what doesn't
4. Optionally recommend rubric weight adjustments if one dimension is consistently weak

ANALYSIS FRAMEWORK:
- Look at score distributions across dimensions (accuracy, depth, completeness, specificity, honesty)
- Read critic feedback for recurring themes
- Compare high-scoring vs low-scoring outputs — what did the high-scorers do differently?
- Identify the weakest dimension — that's the biggest improvement opportunity
- Check evolution history: what was tried before? Did it help or hurt?

STRATEGY WRITING RULES:
- The strategy is a system prompt for the researcher agent
- Must include the JSON output format specification
- Must include TODAY'S DATE awareness (inject {today} and temporal rules)
- Be specific: "search for X before Y" not "search more carefully"
- Keep it concise — under 600 words. Agents perform worse with bloated prompts.
- Preserve behaviors that scored well. Only change what's broken.
- CRITICAL: The researcher has a hard cap of 10 searches. Strategies must recommend 3-8 searches.
  Recommending more than 8 will cause the agent to hit its limit and produce corrupt output.

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{{
    "analysis": {{
        "patterns_found": ["pattern1", "pattern2"],
        "strongest_dimension": "dimension_name",
        "weakest_dimension": "dimension_name",
        "recurring_critic_feedback": ["feedback1", "feedback2"],
        "high_score_behaviors": ["what high scorers did"],
        "low_score_behaviors": ["what low scorers did"]
    }},
    "changes_made": ["specific change 1", "specific change 2"],
    "lessons_from_history": ["what past evolutions taught us"],
    "new_strategy": "THE FULL NEW STRATEGY TEXT HERE",
    "reasoning": "Why these changes should improve scores",
    "rubric_recommendation": {{
        "adjust": true,
        "weights": {{"accuracy": 0.30, "depth": 0.20, "completeness": 0.20, "specificity": 0.15, "intellectual_honesty": 0.15}},
        "reason": "Why these weights should change (or null if no change needed)"
    }}
}}
"""


META_ANALYST_PROMPT = _build_meta_prompt()


def _prepare_analysis_data(outputs: list[dict], current_strategy: str | None, evolution_history: str = "") -> str:
    """Format scored outputs + evolution history for the meta-analyst to analyze."""
    summaries = []
    for i, out in enumerate(outputs):
        critique_data = out.get("critique", {})
        research_data = out.get("research", {})

        summary = {
            "output_number": i + 1,
            "question": out.get("question", "unknown"),
            "overall_score": out.get("overall_score", 0),
            "verdict": out.get("verdict", "unknown"),
            "scores": critique_data.get("scores", {}),
            "strengths": critique_data.get("strengths", []),
            "weaknesses": critique_data.get("weaknesses", []),
            "actionable_feedback": critique_data.get("actionable_feedback", ""),
            "summary": research_data.get("summary", ""),
            "knowledge_gaps": research_data.get("knowledge_gaps", []),
            "findings_count": len(research_data.get("findings", [])),
            "searches_made": research_data.get("_searches_made", 0),
        }
        summaries.append(summary)

    data = {
        "total_outputs_analyzed": len(summaries),
        "score_distribution": {
            "min": min(s["overall_score"] for s in summaries),
            "max": max(s["overall_score"] for s in summaries),
            "avg": sum(s["overall_score"] for s in summaries) / len(summaries),
            "accepted": sum(1 for s in summaries if s["verdict"] == "accept"),
            "rejected": sum(1 for s in summaries if s["verdict"] == "reject"),
        },
        "outputs": summaries,
        "current_strategy": current_strategy or "(default strategy — no custom strategy yet)",
        "evolution_history": evolution_history,
    }

    return json.dumps(data, indent=2)


def analyze_and_evolve(domain: str) -> dict | None:
    """
    Run the meta-analyst: analyze scored outputs → generate improved strategy.

    Returns:
        Dict with analysis results and new strategy, or None if not enough data.
    """
    # Load all outputs for this domain
    all_outputs = load_outputs(domain, min_score=0)

    if len(all_outputs) < MIN_OUTPUTS_FOR_ANALYSIS:
        print(f"[META-ANALYST] Not enough data for domain '{domain}' "
              f"({len(all_outputs)}/{MIN_OUTPUTS_FOR_ANALYSIS} outputs). Skipping.")
        return None

    # Take the most recent outputs (respect context limits)
    recent_outputs = all_outputs[-MAX_OUTPUTS_TO_ANALYZE:]

    # Load current strategy
    current_strategy, current_version = get_strategy("researcher", domain)

    print(f"[META-ANALYST] Analyzing {len(recent_outputs)} outputs for domain '{domain}'...")
    print(f"[META-ANALYST] Current strategy version: {current_version}")

    # Load evolution history for context
    evolution_history = _format_evolution_history(domain)
    if evolution_history and not evolution_history.startswith("(No"):
        print(f"[META-ANALYST] Injecting evolution history ({len(load_evolution_log(domain))} past entries)")

    # Prepare analysis data
    analysis_data = _prepare_analysis_data(recent_outputs, current_strategy, evolution_history)

    user_message = (
        f"Analyze these scored research outputs and generate an improved strategy.\n\n"
        f"DATA:\n{analysis_data}"
    )

    # Call the meta-analyst model
    response = create_message(
        client,
        model=MODELS["meta_analyst"],
        max_tokens=4096,
        system=META_ANALYST_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Track cost
    log_cost(MODELS["meta_analyst"], response.usage.input_tokens, response.usage.output_tokens, "meta_analyst", domain)

    raw_text = response.content[0].text.strip()

    # Robust JSON extraction (handles markdown fences, preamble, etc.)
    EXPECTED_KEYS = {"new_strategy", "changes", "reasoning"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if result is None:
        print("[META-ANALYST] ⚠ Failed to parse meta-analyst output")
        return None

    new_strategy = result.get("new_strategy")
    if not new_strategy:
        print("[META-ANALYST] ⚠ No new strategy in output")
        return None

    # ── Drift Guardrail: enforce immutable clauses ──
    missing_clauses = []
    for clause in IMMUTABLE_STRATEGY_CLAUSES:
        if clause.lower() not in new_strategy.lower():
            missing_clauses.append(clause)
    
    if missing_clauses:
        print(f"[META-ANALYST] ⚠ DRIFT GUARD: New strategy missing {len(missing_clauses)} immutable clause(s):")
        for mc in missing_clauses:
            print(f"  ✗ '{mc}'")
        # Auto-append missing clauses rather than reject entirely
        new_strategy += "\n\n# Immutable constraints (auto-restored by drift guard):\n"
        for mc in missing_clauses:
            new_strategy += f"- {mc}\n"
        print(f"[META-ANALYST]   → Auto-restored missing clauses")

    # Compute new version number
    existing_versions = list_versions("researcher", domain)
    if existing_versions:
        # Extract version numbers, increment
        nums = []
        for v in existing_versions:
            try:
                nums.append(int(v.replace("v", "")))
            except ValueError:
                pass
        next_num = max(nums) + 1 if nums else 1
    else:
        next_num = 1

    new_version = f"v{next_num:03d}"

    # Build reason from analysis
    changes = result.get("changes_made", [])
    reasoning = result.get("reasoning", "")
    reason = f"Changes: {'; '.join(changes)}. Reasoning: {reasoning}"

    # Save new strategy — as PENDING (requires human approval before trial)
    filepath = save_strategy(
        agent_role="researcher",
        domain=domain,
        strategy_text=new_strategy,
        version=new_version,
        reason=reason,
        status="pending",
    )

    print(f"[META-ANALYST] ✓ New strategy saved: {new_version} (PENDING APPROVAL)")
    print(f"[META-ANALYST]   File: {filepath}")
    print(f"[META-ANALYST]   ⚠ Run '--approve {new_version}' to deploy to trial")

    # Print analysis summary
    analysis = result.get("analysis", {})
    print(f"[META-ANALYST]   Strongest dimension: {analysis.get('strongest_dimension', '?')}")
    print(f"[META-ANALYST]   Weakest dimension: {analysis.get('weakest_dimension', '?')}")
    print(f"[META-ANALYST]   Changes made:")
    for change in changes:
        print(f"                  → {change}")

    # Log this evolution decision
    current_perf = get_strategy_performance(domain, current_version)
    save_evolution_entry(domain, {
        "version": new_version,
        "previous_version": current_version,
        "date": date.today().isoformat(),
        "changes": changes,
        "reasoning": reasoning,
        "weakest_dimension": analysis.get("weakest_dimension", ""),
        "score_before": round(current_perf.get("avg_score", 0), 1) if current_perf.get("count", 0) > 0 else None,
        "score_after": None,  # Updated after trial evaluation
        "outcome": "pending",  # Updated after trial evaluation
    })

    # Handle rubric recommendation
    rubric_rec = result.get("rubric_recommendation", {})
    if rubric_rec and rubric_rec.get("adjust"):
        rec_weights = rubric_rec.get("weights", {})
        rec_reason = rubric_rec.get("reason", "Meta-analyst recommendation")
        if rec_weights and all(k in rec_weights for k in ["accuracy", "depth", "completeness", "specificity", "intellectual_honesty"]):
            from agents.critic import save_rubric
            save_rubric(domain, rec_weights, rec_reason)
            print(f"[META-ANALYST]   📊 Rubric weights adjusted: {rec_reason}")

    return {
        "analysis": analysis,
        "changes_made": changes,
        "new_version": new_version,
        "reasoning": reasoning,
        "strategy_filepath": filepath,
    }
