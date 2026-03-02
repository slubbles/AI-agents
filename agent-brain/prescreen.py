"""
Pre-Screen Critic — Cheap grok-based pre-filter before expensive Claude critic.

The insight: ~40% of research outputs are clearly good (score > 7) or clearly bad
(score < 4). Sending these to Claude Sonnet is wasting money. A cheap model can
identify the obvious cases, and only uncertain outputs go to Claude.

Flow:
    research_output → grok pre-screen → {
        clearly_good (>7): accept with grok score, skip Claude
        clearly_bad (<4):  reject with grok score, skip Claude
        uncertain (4-7):   send to Claude for full evaluation
    }

Cost savings: ~40% reduction in Claude critic calls.
Quality guarantee: uncertain outputs still get Claude's judgment.
"""

import json
import logging
from datetime import date

from config import MODELS, OPENROUTER_API_KEY
from cost_tracker import log_cost
from utils.json_parser import extract_json

logger = logging.getLogger("prescreen")

# Thresholds for pre-screen decisions
PRESCREEN_ACCEPT_THRESHOLD = 7.5   # Clearly good — skip Claude
PRESCREEN_REJECT_THRESHOLD = 3.5   # Clearly bad — skip Claude
# Anything between these goes to Claude for full evaluation

# Model used for pre-screening (must be cheap)
PRESCREEN_MODEL = MODELS.get("researcher")  # grok-4.1-fast


def prescreen(research_output: dict, domain: str = "") -> dict:
    """
    Cheap pre-evaluation of research quality.
    
    Returns:
        {
            "prescreen_score": float,     # 1-10 quick score
            "decision": str,              # "accept" | "reject" | "escalate"
            "reason": str,                # why this decision
            "skip_claude": bool,          # whether to skip expensive critic
        }
    """
    if not OPENROUTER_API_KEY:
        # Can't pre-screen without cheap model — always escalate
        return {
            "prescreen_score": 0,
            "decision": "escalate",
            "reason": "No OpenRouter key — cannot pre-screen",
            "skip_claude": False,
        }

    from llm_router import call_llm

    findings = research_output.get("findings", [])
    summary = research_output.get("summary", "")
    question = research_output.get("question", "")

    # Quick structural checks first (no LLM needed)
    structural = _structural_precheck(research_output)
    if structural:
        return structural

    # Build a compact prompt — we want speed and low tokens
    prompt = f"""\
You are a quick research quality checker. Score this research 1-10 and decide if it needs deep review.

TODAY: {date.today().isoformat()}

Question researched: {question}

Summary: {summary[:500]}

Findings count: {len(findings)}
Sample findings (first 3):
{_format_findings_compact(findings[:3])}

Score 1-10 on overall quality. Then decide:
- ACCEPT (score > 7): clearly good research, no deep review needed
- REJECT (score < 4): clearly bad research, obvious problems
- ESCALATE (score 4-7): uncertain quality, needs expert review

Respond with ONLY valid JSON:
{{"score": 6.5, "decision": "escalate", "reason": "adequate but needs expert check on source quality"}}
"""

    try:
        response = call_llm(
            model=PRESCREEN_MODEL,
            system="You are a fast research quality checker. Respond only with JSON.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,  # Keep response tiny
        )

        log_cost(
            PRESCREEN_MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
            "prescreen",
            domain or "general",
        )

        raw = response.content[0].text.strip()
        result = extract_json(raw, expected_keys={"score", "decision"})

        if result is None:
            logger.warning("Pre-screen failed to parse — escalating to Claude")
            return {
                "prescreen_score": 0,
                "decision": "escalate",
                "reason": "Pre-screen parse failure",
                "skip_claude": False,
            }

        score = float(result.get("score", 5))
        decision = result.get("decision", "escalate").lower().strip()
        reason = result.get("reason", "")

        # Override decision based on our thresholds (don't trust the model's decision blindly)
        if score >= PRESCREEN_ACCEPT_THRESHOLD:
            decision = "accept"
        elif score <= PRESCREEN_REJECT_THRESHOLD:
            decision = "reject"
        else:
            decision = "escalate"

        skip_claude = decision in ("accept", "reject")

        logger.info(
            f"Pre-screen: {score}/10 → {decision} (skip_claude={skip_claude})"
        )

        return {
            "prescreen_score": round(score, 1),
            "decision": decision,
            "reason": reason,
            "skip_claude": skip_claude,
        }

    except Exception as e:
        logger.warning(f"Pre-screen error: {e} — escalating to Claude")
        return {
            "prescreen_score": 0,
            "decision": "escalate",
            "reason": f"Pre-screen error: {e}",
            "skip_claude": False,
        }


def _structural_precheck(research_output: dict) -> dict | None:
    """
    Zero-cost structural checks that don't need an LLM.
    Returns a prescreen result if the output is obviously bad, else None.
    """
    findings = research_output.get("findings", [])

    # Zero findings = obviously bad
    if not findings or research_output.get("_zero_findings"):
        return {
            "prescreen_score": 1.0,
            "decision": "reject",
            "reason": "Zero findings produced",
            "skip_claude": True,
        }

    # Parse error = obviously bad
    if research_output.get("_parse_error"):
        return {
            "prescreen_score": 2.0,
            "decision": "reject",
            "reason": "Research output had parse errors",
            "skip_claude": True,
        }

    # Too few findings with no summary
    if len(findings) <= 1 and not research_output.get("summary"):
        return {
            "prescreen_score": 2.5,
            "decision": "reject",
            "reason": "Only 1 finding and no summary",
            "skip_claude": True,
        }

    # Most searches failed
    empty = research_output.get("_empty_searches", 0)
    total = research_output.get("_searches_made", 0)
    if total > 0 and empty / total > 0.8:
        return {
            "prescreen_score": 3.0,
            "decision": "reject",
            "reason": f"{empty}/{total} searches returned 0 results",
            "skip_claude": True,
        }

    return None  # Can't determine from structure alone


def _format_findings_compact(findings: list[dict]) -> str:
    """Format findings compactly for the pre-screen prompt."""
    lines = []
    for i, f in enumerate(findings, 1):
        claim = f.get("claim", f.get("finding", ""))[:120]
        confidence = f.get("confidence", "?")
        source = f.get("source", "")[:60]
        lines.append(f"  {i}. [{confidence}] {claim} (source: {source})")
    return "\n".join(lines) if lines else "  (none)"


def build_prescreen_critique(prescreen_result: dict) -> dict:
    """
    Convert a pre-screen result into a critique-compatible dict.
    
    Used when skip_claude=True to produce a result that the rest of the system
    can treat like a normal critique output.
    """
    score = prescreen_result["prescreen_score"]
    decision = prescreen_result["decision"]
    reason = prescreen_result["reason"]

    # Map pre-screen score to dimension scores (approximate)
    dim_score = round(score, 0)
    scores = {
        "accuracy": dim_score,
        "depth": dim_score,
        "completeness": dim_score,
        "specificity": dim_score,
        "intellectual_honesty": dim_score,
    }

    return {
        "scores": scores,
        "overall_score": round(score, 2),
        "strengths": ["Pre-screened (not fully evaluated)"] if decision == "accept" else [],
        "weaknesses": [reason] if decision == "reject" else [],
        "actionable_feedback": reason if decision == "reject" else "Passed pre-screen.",
        "verdict": "accept" if decision == "accept" else "reject",
        "_prescreened": True,
        "_prescreen_decision": decision,
    }
