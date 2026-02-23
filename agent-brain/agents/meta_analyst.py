"""
Meta-Analyst Agent (Layer 3 — Behavioral Adaptation)

Reads scored outputs from memory → extracts patterns → rewrites agent strategy documents.
This is the novel piece: strategy evolution driven by empirical performance scoring.

The meta-analyst:
1. Loads recent scored outputs for a domain
2. Analyzes what scored well vs. poorly across dimensions
3. Extracts actionable patterns (do more of X, stop doing Y)
4. Generates a new strategy document that incorporates these patterns
5. The new strategy replaces the old one for future research runs
"""

import json
import sys
import os
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, MIN_OUTPUTS_FOR_ANALYSIS, MAX_OUTPUTS_TO_ANALYZE, EVOLVE_EVERY_N
from memory_store import load_outputs
from strategy_store import get_strategy, save_strategy, list_versions
from cost_tracker import log_cost


client = Anthropic(api_key=ANTHROPIC_API_KEY)


def _build_meta_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a meta-analyst for an autonomous research system. TODAY'S DATE: {today}.

Your job: analyze scored research outputs to find patterns, then rewrite the researcher's
strategy document to improve future performance.

You receive:
1. A set of scored research outputs (each with scores across 5 dimensions + critic feedback)
2. The current strategy document the researcher is using

You must:
1. Identify patterns: what behaviors correlate with HIGH scores? What correlates with LOW?
2. Extract specific, actionable improvements (not vague advice)
3. Write a NEW strategy document that preserves what works and fixes what doesn't

ANALYSIS FRAMEWORK:
- Look at score distributions across dimensions (accuracy, depth, completeness, specificity, honesty)
- Read critic feedback for recurring themes
- Compare high-scoring vs low-scoring outputs — what did the high-scorers do differently?
- Identify the weakest dimension — that's the biggest improvement opportunity

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
    "new_strategy": "THE FULL NEW STRATEGY TEXT HERE",
    "reasoning": "Why these changes should improve scores"
}}
"""


META_ANALYST_PROMPT = _build_meta_prompt()


def _prepare_analysis_data(outputs: list[dict], current_strategy: str | None) -> str:
    """Format scored outputs for the meta-analyst to analyze."""
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

    # Prepare analysis data
    analysis_data = _prepare_analysis_data(recent_outputs, current_strategy)

    user_message = (
        f"Analyze these scored research outputs and generate an improved strategy.\n\n"
        f"DATA:\n{analysis_data}"
    )

    # Call the meta-analyst model
    response = client.messages.create(
        model=MODELS["meta_analyst"],
        max_tokens=4096,
        system=META_ANALYST_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Track cost
    log_cost(MODELS["meta_analyst"], response.usage.input_tokens, response.usage.output_tokens, "meta_analyst", domain)

    raw_text = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [l for l in lines[1:] if l.strip() != "```"]
        raw_text = "\n".join(lines)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        print("[META-ANALYST] ⚠ Failed to parse meta-analyst output")
        return None

    new_strategy = result.get("new_strategy")
    if not new_strategy:
        print("[META-ANALYST] ⚠ No new strategy in output")
        return None

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

    return {
        "analysis": analysis,
        "changes_made": changes,
        "new_version": new_version,
        "reasoning": reasoning,
        "strategy_filepath": filepath,
    }
