"""
Critic Agent
Reviews researcher output → scores 1-10 with structured rubric → provides actionable feedback.
"""

import json
from datetime import date

from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, MODELS
from cost_tracker import log_cost
from utils.retry import create_message


client = Anthropic(api_key=ANTHROPIC_API_KEY)

def _build_critic_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a strict research critic. Your job is to evaluate research findings for quality, accuracy, and depth.

TODAY'S DATE: {today}
The current year is {date.today().year}. Events and data from {date.today().year} or earlier are NOT future events.
Do NOT penalize research for reporting on events that have already occurred as of {today}.

You score on 5 dimensions (each 1-10):
1. **Accuracy** — Are the claims factually correct? Are there hallucinations or unsupported assertions?
2. **Depth** — Does the research go beyond surface-level? Are mechanisms explained, not just facts listed?
3. **Completeness** — Are important angles covered? Are there obvious gaps?
4. **Specificity** — Are claims concrete with numbers, dates, sources? Or vague hand-waving?
5. **Intellectual honesty** — Does it flag uncertainty? Does it distinguish established fact from speculation?

Overall score = weighted average (Accuracy 30%, Depth 20%, Completeness 20%, Specificity 15%, Honesty 15%)

Output format — respond with ONLY valid JSON, no markdown fencing:
{{
    "scores": {{
        "accuracy": 7,
        "depth": 5,
        "completeness": 6,
        "specificity": 4,
        "intellectual_honesty": 8
    }},
    "overall_score": 6.1,
    "strengths": ["what was done well"],
    "weaknesses": ["what was done poorly"],
    "actionable_feedback": "specific instructions for how to improve this research if retried",
    "verdict": "accept|reject"
}}

Be harsh but fair. A score of 6 means adequate. 8+ means genuinely good research. Below 5 means significant problems.
Do NOT inflate scores to be nice. The system depends on honest evaluation.
"""

CRITIC_SYSTEM_PROMPT = _build_critic_prompt()


def critique(research_output: dict) -> dict:
    """
    Evaluate research findings and produce a structured score.
    
    Args:
        research_output: The researcher's structured findings dict
    
    Returns:
        Parsed JSON dict with scores, feedback, and verdict
    """
    user_message = f"Evaluate this research output:\n\n{json.dumps(research_output, indent=2)}"

    response = create_message(
        client,
        model=MODELS["critic"],
        max_tokens=2048,
        system=CRITIC_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Track cost
    log_cost(MODELS["critic"], response.usage.input_tokens, response.usage.output_tokens, "critic", "critique")

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [l for l in lines[1:] if l.strip() != "```"]
        raw_text = "\n".join(lines)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback if critic response isn't valid JSON
        result = {
            "scores": {"accuracy": 0, "depth": 0, "completeness": 0, "specificity": 0, "intellectual_honesty": 0},
            "overall_score": 0,
            "strengths": [],
            "weaknesses": ["Critic failed to produce structured output"],
            "actionable_feedback": "Unable to evaluate — retry",
            "verdict": "reject",
            "_parse_error": True,
        }

    # Ensure verdict field exists and aligns with score
    if "overall_score" in result and "verdict" not in result:
        result["verdict"] = "accept" if result["overall_score"] >= 6 else "reject"

    return result
