"""
Task Generator — Converts Brain knowledge into coding tasks for Hands.

This is the bridge between Brain (research/knowledge) and Hands (execution).

Pipeline:
1. Read domain KB (claims, strategies, gaps)
2. Read execution history (what's been built, what scored well)
3. Generate coding tasks that:
   a) Apply verified knowledge to real code
   b) Fill knowledge gaps through experimentation
   c) Build on past successes
   d) Fix past failures
4. Deduplicate against past tasks (prevent re-attempting failed goals)
5. Adapt difficulty based on success rates at each complexity level

Uses Haiku (cheap synthesis task) — the judgment happens in the validator.
"""

import json
import os
import re
import sys
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS
from memory_store import load_outputs, load_knowledge_base
from hands.exec_memory import load_exec_outputs, get_exec_stats
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)

MAX_KB_CLAIMS = 20
MAX_PAST_TASKS = 10

# Minimum accept rate at a complexity level to allow generating tasks at that level
MIN_ACCEPT_RATE_FOR_COMPLEXITY = 0.40
# Minimum attempts at a level before enforcing success rate gating
MIN_ATTEMPTS_FOR_GATING = 3


def _get_past_goals(domain: str) -> list[str]:
    """Get list of all previously attempted goals for deduplication."""
    outputs = load_exec_outputs(domain)
    return [o.get("goal", "") for o in outputs if o.get("goal")]


def _get_complexity_stats(domain: str) -> dict[str, dict]:
    """
    Calculate success rates by complexity level.
    
    Returns:
        {"low": {"count": 5, "accepted": 4, "rate": 0.8}, ...}
    """
    outputs = load_exec_outputs(domain)
    stats: dict[str, dict] = {}
    
    for o in outputs:
        # Get complexity from the plan
        complexity = o.get("plan", {}).get("estimated_complexity", "medium")
        if complexity not in stats:
            stats[complexity] = {"count": 0, "accepted": 0}
        stats[complexity]["count"] += 1
        if o.get("accepted"):
            stats[complexity]["accepted"] += 1
    
    # Calculate rates
    for level, data in stats.items():
        data["rate"] = data["accepted"] / data["count"] if data["count"] > 0 else 0
    
    return stats


def _get_max_allowed_complexity(domain: str) -> str:
    """
    Determine the maximum complexity level the system should attempt,
    based on historical success rates.
    
    If high-complexity tasks have <40% accept rate (with 3+ attempts),
    cap at medium. If medium also fails, cap at low.
    """
    stats = _get_complexity_stats(domain)
    levels = ["low", "medium", "high"]
    
    for level in reversed(levels):  # Check high, then medium
        data = stats.get(level, {})
        count = data.get("count", 0)
        rate = data.get("rate", 1.0)
        
        # Only gate if enough attempts at this level
        if count >= MIN_ATTEMPTS_FOR_GATING and rate < MIN_ACCEPT_RATE_FOR_COMPLEXITY:
            # This level is too hard — cap at the previous level
            idx = levels.index(level)
            if idx > 0:
                return levels[idx - 1]
            return "low"  # Even low is failing, but allow it
    
    return "high"  # No restrictions


def _build_task_gen_prompt() -> str:
    """Build the task generator's system prompt."""
    today = date.today().isoformat()

    return f"""\
You are a coding task generator for an autonomous learning system. TODAY'S DATE: {today}.

Your job: analyze the system's domain knowledge and execution history, then generate
the BEST NEXT CODING TASK that advances the system's capabilities.

Task quality criteria:
1. **Applied Knowledge** — The task should USE verified knowledge claims from the KB
2. **Skill Progression** — Build on what scored well, fix what scored poorly
3. **Practical Value** — Build things that are useful, not toy examples
4. **Testability** — The task must produce verifiable output (tests pass, builds compile)
5. **Appropriate Scope** — Not too trivial (> 2 files), not too ambitious (< 15 files)

Task types to consider:
- Build a utility/library applying KB best practices
- Create a project template/boilerplate with KB patterns
- Build a tool that automates something from the KB
- Refactor/improve a previously built project using new KB insights
- Build a test suite that validates KB claims experimentally

Respond with ONLY valid JSON:
{{
    "task": "Clear, specific coding task description (1-3 sentences)",
    "reasoning": "Why this task is the best next step",
    "applies_claims": ["list of KB claim IDs/summaries this task applies"],
    "builds_on": "previous task/execution this improves upon (or 'none')",
    "expected_complexity": "low|medium|high",
    "success_criteria": "How to verify the task was completed correctly",
    "priority": 1
}}

Generate exactly 3 candidate tasks, ranked by priority.
Respond with a JSON array of 3 task objects.
"""


def _prepare_context(domain: str) -> str:
    """Prepare context from KB, execution history, dedup list, and difficulty bounds."""
    parts = []

    # Difficulty adaptation — tell the LLM what complexity level to target
    max_complexity = _get_max_allowed_complexity(domain)
    if max_complexity != "high":
        parts.append(f"⚠ COMPLEXITY CAP: Generate tasks at '{max_complexity}' complexity or below.")
        parts.append(f"  (Higher complexity tasks have low success rates for this domain)")
        parts.append("")

    complexity_stats = _get_complexity_stats(domain)
    if complexity_stats:
        parts.append("=== COMPLEXITY SUCCESS RATES ===")
        for level in ["low", "medium", "high"]:
            data = complexity_stats.get(level, {"count": 0, "accepted": 0, "rate": 0})
            if data["count"] > 0:
                parts.append(f"  {level}: {data['accepted']}/{data['count']} accepted ({data['rate']:.0%})")
        parts.append("")

    # Deduplication — past goals as a "DO NOT REPEAT" list
    past_goals = _get_past_goals(domain)
    if past_goals:
        parts.append("=== PREVIOUSLY ATTEMPTED TASKS (DO NOT REPEAT) ===")
        for i, goal in enumerate(past_goals[-15:]):  # Show last 15
            parts.append(f"  {i+1}. {goal[:120]}")
        parts.append("")
        parts.append("IMPORTANT: Do NOT generate tasks identical or very similar to the above.")
        parts.append("Generate tasks that advance the system's capabilities in NEW directions.")
        parts.append("")

    # KB claims
    try:
        kb = load_knowledge_base(domain)
        if kb and kb.get("claims"):
            claims = kb["claims"][:MAX_KB_CLAIMS]
            parts.append("=== DOMAIN KNOWLEDGE BASE ===")
            for i, claim in enumerate(claims):
                parts.append(f"  {i+1}. {claim.get('claim', '?')}")
                if claim.get("evidence"):
                    parts.append(f"     Evidence: {str(claim['evidence'])[:100]}")
            parts.append(f"Total claims: {len(kb['claims'])}")
            parts.append("")
    except Exception as e:
        print(f"  [TASK-GEN] Warning: failed to load KB: {e}")

    # Research history (recent high-scoring)
    try:
        outputs = load_outputs(domain, min_score=6)
        if outputs:
            parts.append("=== RECENT RESEARCH INSIGHTS ===")
            for o in outputs[-5:]:
                score = o.get("score", 0)
                question = o.get("question", "?")[:100]
                parts.append(f"  [{score}/10] {question}")
            parts.append("")
    except Exception as e:
        print(f"  [TASK-GEN] Warning: failed to load research history: {e}")

    # Execution history
    exec_outputs = load_exec_outputs(domain)
    if exec_outputs:
        parts.append("=== PREVIOUS CODING TASKS ===")
        for o in exec_outputs[-MAX_PAST_TASKS:]:
            score = o.get("overall_score", 0)
            goal = o.get("goal", "?")[:100]
            verdict = o.get("verdict", "?")
            val = o.get("validation", {})
            weaknesses = val.get("weaknesses", [])
            parts.append(f"  [{score}/10 {verdict}] {goal}")
            if weaknesses:
                parts.append(f"    Weaknesses: {'; '.join(str(w)[:80] for w in weaknesses[:3])}")
        parts.append("")

    # Execution stats
    stats = get_exec_stats(domain)
    if stats["count"] > 0:
        parts.append(f"=== EXECUTION STATS ===")
        parts.append(f"  Total tasks: {stats['count']}, Avg score: {stats['avg_score']:.1f}")
        parts.append(f"  Accepted: {stats['accepted']}, Rejected: {stats['rejected']}")
        parts.append("")

    if not parts:
        parts.append("(No prior knowledge or execution history for this domain)")
        parts.append("Generate a foundational coding task appropriate for the domain.")

    return "\n".join(parts)


def generate_tasks(domain: str, hint: str = "") -> list[dict]:
    """
    Generate ranked coding task candidates for a domain.

    Args:
        domain: The domain to generate tasks for
        hint: Optional hint/direction from the user

    Returns:
        List of task dicts (ranked by priority), or empty list on failure
    """
    system = _build_task_gen_prompt()
    context = _prepare_context(domain)

    user_msg = f"DOMAIN: {domain}\n\n{context}"
    if hint:
        user_msg += f"\n\nUSER HINT: {hint}"

    response = create_message(
        client,
        model=MODELS.get("task_generator", MODELS["question_generator"]),  # Haiku
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    log_cost(
        model=MODELS.get("task_generator", MODELS["question_generator"]),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        agent_role="task_generator",
        domain=domain,
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # Try to find JSON array first (multiple tasks)
    try:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            tasks = json.loads(match.group())
            if isinstance(tasks, list) and len(tasks) > 0 and all(isinstance(t, dict) for t in tasks):
                return tasks
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fall back to single object
    result = extract_json(text, expected_keys={"task"})
    if result and isinstance(result, dict):
        return [result]

    # Final fallback — try to extract multiple objects split by }{
    tasks = []
    for candidate in text.split("}{"):
        candidate = candidate.strip()
        if not candidate.startswith("{"):
            candidate = "{" + candidate
        if not candidate.endswith("}"):
            candidate = candidate + "}"
        parsed = extract_json(candidate, expected_keys={"task"})
        if parsed:
            tasks.append(parsed)

    return tasks


def get_next_task(domain: str, hint: str = "") -> str | None:
    """
    Get the single best next coding task for a domain.
    Convenience wrapper around generate_tasks.

    Returns:
        Task description string, or None if generation failed.
    """
    tasks = generate_tasks(domain, hint)
    if not tasks:
        return None

    # Return the highest priority task
    tasks.sort(key=lambda t: t.get("priority", 99))
    best = tasks[0]

    task_text = best.get("task", "")
    if not task_text:
        return None

    print(f"  [TASK-GEN] Generated {len(tasks)} candidates")
    print(f"  [TASK-GEN] Reasoning: {best.get('reasoning', '?')[:100]}")
    print(f"  [TASK-GEN] Complexity: {best.get('expected_complexity', '?')}")

    if best.get("applies_claims"):
        print(f"  [TASK-GEN] Applies: {', '.join(str(c)[:60] for c in best['applies_claims'][:3])}")

    return task_text
