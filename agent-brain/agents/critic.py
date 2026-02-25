"""
Critic Agent
Reviews researcher output → scores 1-10 with structured rubric → provides actionable feedback.

Supports adaptive rubric weights per domain. If strategies/{domain}/_rubric.json exists,
its weights override the defaults. The meta-analyst can recommend rubric adjustments based
on score patterns (e.g., bump Specificity weight if that dimension is consistently weak).
"""

import json
import os
from datetime import date

from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, MODELS, STRATEGY_DIR
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Default rubric weights — these can be overridden per domain
DEFAULT_RUBRIC_WEIGHTS = {
    "accuracy": 0.30,
    "depth": 0.20,
    "completeness": 0.20,
    "specificity": 0.15,
    "intellectual_honesty": 0.15,
}


def load_rubric(domain: str) -> dict:
    """
    Load rubric weights for a domain. Falls back to defaults if no custom rubric exists.
    
    Returns dict with dimension names as keys and float weights as values (sum to 1.0).
    """
    rubric_path = os.path.join(STRATEGY_DIR, domain, "_rubric.json")
    if os.path.exists(rubric_path):
        try:
            with open(rubric_path) as f:
                data = json.load(f)
            weights = data.get("weights", {})
            # Validate: must have all 5 dimensions and sum to ~1.0
            if all(k in weights for k in DEFAULT_RUBRIC_WEIGHTS):
                total = sum(weights.values())
                if 0.95 <= total <= 1.05:  # Allow small float imprecision
                    return weights
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_RUBRIC_WEIGHTS.copy()


def save_rubric(domain: str, weights: dict, reason: str = "") -> str:
    """
    Save custom rubric weights for a domain.
    
    Args:
        domain: Target domain
        weights: Dict of dimension → weight (must sum to 1.0)
        reason: Why the rubric was adjusted
    
    Returns:
        Path to saved rubric file
    """
    rubric_path = os.path.join(STRATEGY_DIR, domain, "_rubric.json")
    os.makedirs(os.path.dirname(rubric_path), exist_ok=True)
    
    data = {
        "weights": weights,
        "reason": reason,
        "updated_at": date.today().isoformat(),
    }
    with open(rubric_path, "w") as f:
        json.dump(data, f, indent=2)
    return rubric_path


def _build_critic_prompt(weights: dict | None = None) -> str:
    today = date.today().isoformat()
    w = weights or DEFAULT_RUBRIC_WEIGHTS
    
    # Format weights as percentages for the prompt
    acc_pct = int(w["accuracy"] * 100)
    dep_pct = int(w["depth"] * 100)
    com_pct = int(w["completeness"] * 100)
    spe_pct = int(w["specificity"] * 100)
    hon_pct = int(w["intellectual_honesty"] * 100)
    
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

Overall score = weighted average (Accuracy {acc_pct}%, Depth {dep_pct}%, Completeness {com_pct}%, Specificity {spe_pct}%, Honesty {hon_pct}%)

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


def critique(research_output: dict, domain: str = "") -> dict:
    """
    Evaluate research findings and produce a structured score.
    
    Args:
        research_output: The researcher's structured findings dict
        domain: Optional domain name — loads per-domain rubric weights if available
    
    Returns:
        Parsed JSON dict with scores, feedback, and verdict
    """
    # Load adaptive rubric weights for this domain
    weights = load_rubric(domain) if domain else DEFAULT_RUBRIC_WEIGHTS
    system_prompt = _build_critic_prompt(weights) if domain else CRITIC_SYSTEM_PROMPT
    
    user_message = f"Evaluate this research output:\n\n{json.dumps(research_output, indent=2)}"

    response = create_message(
        client,
        model=MODELS["critic"],
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # Track cost
    log_cost(MODELS["critic"], response.usage.input_tokens, response.usage.output_tokens, "critic", "critique")

    raw_text = response.content[0].text.strip()

    # Robust JSON extraction (handles markdown fences, preamble, etc.)
    EXPECTED_KEYS = {"scores", "overall_score", "verdict"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if result is None:
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
