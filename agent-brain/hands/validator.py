"""
Execution Validator — Scores execution output quality.

Parallel to Brain's critic.py but for code/execution output.
Evaluates on different dimensions suited to execution quality.

Scoring Rubric (5 dimensions):
- Correctness (30%) — Does the code work? Does it do what was asked?
- Completeness (20%) — All requirements met? No missing pieces?
- Code Quality (20%) — Clean, idiomatic, well-structured?
- Security (15%) — Safe patterns? No vulnerabilities?
- KB Alignment (15%) — Uses best practices from Brain's knowledge?
"""

import json
import os
import sys
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, EXEC_QUALITY_THRESHOLD
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json

client = Anthropic(api_key=ANTHROPIC_API_KEY)

DEFAULT_EXEC_RUBRIC = {
    "correctness": 0.30,
    "completeness": 0.20,
    "code_quality": 0.20,
    "security": 0.15,
    "kb_alignment": 0.15,
}


def _build_validator_prompt(rubric: dict | None = None) -> str:
    """Build the validator's system prompt."""
    today = date.today().isoformat()
    w = rubric or DEFAULT_EXEC_RUBRIC

    cor = int(w["correctness"] * 100)
    com = int(w["completeness"] * 100)
    qual = int(w["code_quality"] * 100)
    sec = int(w["security"] * 100)
    kb = int(w["kb_alignment"] * 100)

    return f"""\
You are a strict execution validator. Your job is to evaluate code and execution output
for quality, correctness, and adherence to best practices.

TODAY'S DATE: {today}

You score on 5 dimensions (each 1-10):
1. **Correctness** — Does the code work? Does it accomplish the stated task? Are there bugs?
2. **Completeness** — Are all requirements met? All files created? All features implemented?
3. **Code Quality** — Is the code clean, idiomatic, well-structured? Proper error handling? Types?
4. **Security** — Safe patterns? No vulnerabilities (XSS, injection, exposed secrets)?
5. **KB Alignment** — Does it follow best practices from the domain knowledge base?

Overall score = weighted average (Correctness {cor}%, Completeness {com}%, Quality {qual}%, Security {sec}%, KB {kb}%)

EVALUATION RULES:
- A file with just placeholders or TODO comments is NOT complete — score 1-2.
- working code with minor issues = 6-7. Production-quality = 8+.
- If tests exist and pass, that's a strong correctness signal.
- If tests exist and fail, that's a strong correctness penalty.
- Code without ANY error handling = max 5 on quality.
- Hardcoded secrets = max 3 on security.

Output ONLY valid JSON:
{{
    "scores": {{
        "correctness": 7,
        "completeness": 6,
        "code_quality": 5,
        "security": 8,
        "kb_alignment": 6
    }},
    "overall_score": 6.4,
    "strengths": ["what was done well"],
    "weaknesses": ["what was done poorly"],
    "actionable_feedback": "specific instructions for how to improve if re-executed",
    "verdict": "accept|reject",
    "critical_issues": ["any blocking issues that must be fixed"]
}}

Threshold for accept: overall_score >= {EXEC_QUALITY_THRESHOLD}.
Be harsh but fair. The system depends on honest evaluation.
"""


def validate_execution(
    goal: str,
    plan: dict,
    execution_report: dict,
    domain: str = "general",
    domain_knowledge: str = "",
) -> dict:
    """
    Evaluate execution output quality.

    Args:
        goal: The original task description
        plan: The execution plan that was followed
        execution_report: Full execution report with step results and artifacts
        domain: Domain context
        domain_knowledge: Relevant KB claims for alignment checking

    Returns:
        Validation result dict with scores, feedback, and verdict
    """
    system = _build_validator_prompt()

    # Build the evaluation context
    eval_context = {
        "goal": goal,
        "plan_summary": plan.get("task_summary", ""),
        "success_criteria": plan.get("success_criteria", ""),
        "steps_completed": execution_report.get("completed_steps", 0),
        "steps_failed": execution_report.get("failed_steps", 0),
        "total_steps": execution_report.get("total_steps", 0),
        "artifacts": execution_report.get("artifacts", []),
    }

    # Include step details (capped to avoid huge payloads)
    step_details = []
    for step in execution_report.get("step_results", [])[:20]:
        step_details.append({
            "step": step.get("step", 0),
            "tool": step.get("tool", ""),
            "success": step.get("success", False),
            "output": step.get("output", "")[:500],
            "error": step.get("error", ""),
        })
    eval_context["step_details"] = step_details

    user_message = f"Evaluate this execution:\n\n{json.dumps(eval_context, indent=2)}"

    if domain_knowledge:
        user_message += f"\n\nDOMAIN KNOWLEDGE (best practices):\n{domain_knowledge[:3000]}"

    response = create_message(
        client,
        model=MODELS["exec_validator"],
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    # Track cost
    log_cost(
        model=MODELS["exec_validator"],
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        agent_role="exec_validator",
        domain=domain,
    )

    raw_text = response.content[0].text.strip()

    # Parse JSON
    EXPECTED_KEYS = {"scores", "overall_score", "verdict"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if result is None:
        result = {
            "scores": {
                "correctness": 0, "completeness": 0,
                "code_quality": 0, "security": 0, "kb_alignment": 0,
            },
            "overall_score": 0,
            "strengths": [],
            "weaknesses": ["Validator failed to produce structured output"],
            "actionable_feedback": "Unable to evaluate — retry",
            "verdict": "reject",
            "critical_issues": ["Validation parse error"],
            "_parse_error": True,
        }

    # Ensure verdict aligns with score
    if "overall_score" in result and "verdict" not in result:
        result["verdict"] = "accept" if result["overall_score"] >= EXEC_QUALITY_THRESHOLD else "reject"

    result.setdefault("critical_issues", [])
    result.setdefault("strengths", [])
    result.setdefault("weaknesses", [])
    result.setdefault("actionable_feedback", "")

    return result
