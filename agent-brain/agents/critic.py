"""
Critic Agent
Reviews researcher output → scores 1-10 with structured rubric → provides actionable feedback.

Supports adaptive rubric weights per domain. If strategies/{domain}/_rubric.json exists,
its weights override the defaults. The meta-analyst can recommend rubric adjustments based
on score patterns (e.g., bump Specificity weight if that dimension is consistently weak).

Enhancements:
  - Recency awareness: penalizes stale data when question implies current information
  - Ensemble mode: runs 2 critics, averages scores (CRITIC_ENSEMBLE config flag)
  - Confidence validation: post-hoc check that "high" claims cite 2+ distinct sources
  - Parse failure logging: raw critic output written to logs/ for debugging
"""

import json
import logging
import os
from datetime import date, datetime

from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, MODELS, STRATEGY_DIR, LOG_DIR
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json
from utils.atomic_write import atomic_json_write

logger = logging.getLogger("critic")

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
    atomic_json_write(rubric_path, data)
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
    
    # Load identity for ethics context
    identity_note = ""
    try:
        from identity_loader import get_identity_summary
        summary = get_identity_summary()
        if summary:
            identity_note = f"\nSYSTEM IDENTITY:\n{summary}\n"
    except Exception:
        pass
    
    return f"""\
You are a strict research critic. Your job is to evaluate research findings for quality, accuracy, and depth.
{identity_note}
TODAY'S DATE: {today}
The current year is {date.today().year}. Events and data from {date.today().year} or earlier are NOT future events.
Do NOT penalize research for reporting on events that have already occurred as of {today}.

RECENCY AWARENESS:
- If the question asks about "current", "latest", "recent", or "2026" topics, data older than 6 months should be flagged.
- Findings that cite outdated statistics when newer data is available should lose Accuracy and Specificity points.
- Recent verification of older claims (e.g., "as of {today}, X is still true") adds value.

You score on 5 dimensions (each 1-10):
1. **Accuracy** — Are the claims factually correct? Are there hallucinations or unsupported assertions? Are cited sources real and actually accessed?
2. **Depth** — Does the research go beyond surface-level? Are mechanisms explained, not just facts listed?
3. **Completeness** — Are important angles covered? Are there obvious gaps?
4. **Specificity** — Are claims concrete with numbers, dates, sources? Or vague hand-waving? Is the data recent enough?
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


def critique(research_output: dict, domain: str = "", sources_summary: list[dict] | None = None) -> dict:
    """
    Evaluate research findings and produce a structured score.
    
    If CRITIC_ENSEMBLE is enabled, runs 2 independent evaluations and averages.
    Applies post-hoc confidence validation if CONFIDENCE_VALIDATION is enabled.
    Logs raw response on parse failure if CRITIC_LOG_PARSE_FAILURES is enabled.
    
    Args:
        research_output: The researcher's structured findings dict
        domain: Optional domain name — loads per-domain rubric weights if available
        sources_summary: Optional list of {url, title, success, chars} from researcher's tool log.
            Allows the critic to verify accuracy by checking whether cited sources were actually fetched.
    
    Returns:
        Parsed JSON dict with scores, feedback, and verdict
    """
    import config as _cfg
    
    # Load adaptive rubric weights for this domain
    weights = load_rubric(domain) if domain else DEFAULT_RUBRIC_WEIGHTS
    
    if getattr(_cfg, "CRITIC_ENSEMBLE", False):
        result = _critique_ensemble(research_output, domain, weights, sources_summary)
    else:
        result = _critique_single(research_output, domain, weights, sources_summary)
    
    # Post-hoc confidence validation
    if getattr(_cfg, "CONFIDENCE_VALIDATION", True) and result.get("overall_score", 0) > 0:
        result = _validate_confidence_claims(research_output, result, sources_summary)
    
    return result


def _critique_single(
    research_output: dict,
    domain: str,
    weights: dict,
    sources_summary: list[dict] | None,
) -> dict:
    """Run a single critic evaluation."""
    import config as _cfg
    
    system_prompt = _build_critic_prompt(weights)
    user_message = _build_user_message(research_output, sources_summary)

    response = create_message(
        client,
        model=MODELS["critic"],
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # Track cost
    log_cost(MODELS["critic"], response.usage.input_tokens, response.usage.output_tokens, "critic", domain or "general")

    raw_text = response.content[0].text.strip()

    # Robust JSON extraction (handles markdown fences, preamble, etc.)
    EXPECTED_KEYS = {"scores", "overall_score", "verdict"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if result is None:
        # Log the raw response for debugging
        if getattr(_cfg, "CRITIC_LOG_PARSE_FAILURES", True):
            _log_parse_failure(domain, raw_text)
        
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


def _critique_ensemble(
    research_output: dict,
    domain: str,
    weights: dict,
    sources_summary: list[dict] | None,
) -> dict:
    """
    Cross-model ensemble critic: Claude Sonnet (A) + DeepSeek V3.2 (B).
    
    Two different model architectures scoring the same output = less correlated
    failure modes and more calibrated scoring. ~40% cheaper than 2x Claude.
    Falls back to same-model ensemble if cross-model config is absent.
    """
    import config as _cfg
    
    # Critic A: Claude Sonnet (the primary, highest-quality critic)
    result_a = _critique_single(research_output, domain, weights, sources_summary)
    
    # Critic B: DeepSeek V3.2 (different architecture, reasoning enabled)
    ensemble_model = getattr(_cfg, "CRITIC_ENSEMBLE_MODEL_B", None)
    if ensemble_model and ensemble_model != MODELS.get("critic"):
        result_b = _critique_cross_model(research_output, domain, weights, sources_summary, ensemble_model)
    else:
        # Fallback: same model, different call (original behavior)
        result_b = _critique_single(research_output, domain, weights, sources_summary)
    
    # If either had a parse error, use the other
    if result_a.get("_parse_error"):
        result_b["_ensemble"] = "fallback_b"
        return result_b
    if result_b.get("_parse_error"):
        result_a["_ensemble"] = "fallback_a"
        return result_a
    
    # Average the scores
    scores_a = result_a.get("scores", {})
    scores_b = result_b.get("scores", {})
    
    avg_scores = {}
    for dim in DEFAULT_RUBRIC_WEIGHTS:
        sa = scores_a.get(dim, 0)
        sb = scores_b.get(dim, 0)
        avg_scores[dim] = round((sa + sb) / 2, 1)
    
    # Recalculate overall from averaged dimension scores
    w = weights or DEFAULT_RUBRIC_WEIGHTS
    overall = sum(avg_scores.get(dim, 0) * weight for dim, weight in w.items())
    overall = round(overall, 2)
    
    # Merge strengths/weaknesses (deduplicated)
    strengths = list(dict.fromkeys(result_a.get("strengths", []) + result_b.get("strengths", [])))
    weaknesses = list(dict.fromkeys(result_a.get("weaknesses", []) + result_b.get("weaknesses", [])))
    
    # Use the more detailed feedback
    feedback_a = result_a.get("actionable_feedback", "")
    feedback_b = result_b.get("actionable_feedback", "")
    feedback = feedback_a if len(feedback_a) >= len(feedback_b) else feedback_b
    
    # Score divergence tracking
    score_a = result_a.get("overall_score", 0)
    score_b = result_b.get("overall_score", 0)
    divergence = abs(score_a - score_b)
    
    result = {
        "scores": avg_scores,
        "overall_score": overall,
        "strengths": strengths[:6],
        "weaknesses": weaknesses[:6],
        "actionable_feedback": feedback,
        "verdict": "accept" if overall >= 6 else "reject",
        "_ensemble": True,
        "_ensemble_scores": [score_a, score_b],
        "_ensemble_divergence": round(divergence, 2),
    }
    
    if divergence > 2.0:
        result["weaknesses"].append(
            f"[ENSEMBLE WARNING] Critics diverged by {divergence:.1f} points "
            f"({score_a:.1f} vs {score_b:.1f}) — reliability uncertain"
        )
    
    return result


def _critique_cross_model(
    research_output: dict,
    domain: str,
    weights: dict,
    sources_summary: list[dict] | None,
    model: str,
) -> dict:
    """
    Run a critic evaluation using an alternative model via llm_router.
    
    Used for the cross-model ensemble: sends the same prompt to DeepSeek V3.2
    (or any configured model) with reasoning enabled for deeper analysis.
    """
    import config as _cfg
    from llm_router import call_llm
    
    system_prompt = _build_critic_prompt(weights)
    user_message = _build_user_message(research_output, sources_summary)
    
    # Get reasoning setting for ensemble critic B
    reasoning = getattr(_cfg, "REASONING_EFFORT", {}).get("critic_ensemble_b", None)
    
    try:
        response = call_llm(
            model=model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=2048,
            temperature=0.3,  # Lower temp for evaluation tasks
            reasoning_effort=reasoning,
        )
        
        # Track cost
        if response.usage:
            log_cost(model, response.usage.input_tokens, response.usage.output_tokens,
                     "critic_ensemble_b", domain or "general")
        
        # Extract text from normalized response
        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text
        raw_text = raw_text.strip()
        
        EXPECTED_KEYS = {"scores", "overall_score", "verdict"}
        result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)
        
        if result is None:
            if getattr(_cfg, "CRITIC_LOG_PARSE_FAILURES", True):
                _log_parse_failure(domain, f"[CROSS-MODEL {model}] {raw_text}")
            return {
                "scores": {"accuracy": 0, "depth": 0, "completeness": 0, "specificity": 0, "intellectual_honesty": 0},
                "overall_score": 0,
                "strengths": [],
                "weaknesses": [f"Cross-model critic ({model}) failed to produce structured output"],
                "actionable_feedback": "Unable to evaluate",
                "verdict": "reject",
                "_parse_error": True,
            }
        
        if "overall_score" in result and "verdict" not in result:
            result["verdict"] = "accept" if result["overall_score"] >= 6 else "reject"
        
        result["_model"] = model
        return result
        
    except Exception as e:
        logger.warning(f"Cross-model critic ({model}) failed: {e}")
        # Fallback to primary critic
        return _critique_single(research_output, domain, weights, sources_summary)


def _build_user_message(research_output: dict, sources_summary: list[dict] | None) -> str:
    """Build the user message for the critic, including source verification if available."""
    user_message = f"Evaluate this research output:\n\n{json.dumps(research_output, indent=2)}"
    
    # If we have source data, append it so the critic can verify accuracy
    if sources_summary:
        fetched_urls = [s for s in sources_summary if s.get("tool") in ("fetch_page", "search_and_fetch")]
        searched_queries = [s for s in sources_summary if s.get("tool") == "web_search"]
        source_block = "\n\n=== SOURCE VERIFICATION DATA ===\n"
        source_block += "The researcher used these tools during research:\n"
        if searched_queries:
            source_block += f"\nSearches ({len(searched_queries)}):\n"
            for s in searched_queries:
                status = "OK" if s.get("success") else "FAILED"
                source_block += f"  [{status}] \"{s.get('query', '?')}\" → {s.get('results', 0)} results\n"
        if fetched_urls:
            source_block += f"\nPages fetched ({len(fetched_urls)}):\n"
            for s in fetched_urls:
                status = "OK" if s.get("success") else "FAILED"
                chars = s.get("chars", 0)
                source_block += f"  [{status}] {s.get('url', s.get('query', '?'))} ({chars} chars)\n"
        source_block += ("\nACCURACY CHECK: Compare the researcher's cited sources against the "
                         "pages actually fetched above. If the researcher cites a URL that was NOT "
                         "fetched, that's a potential hallucination — penalize accuracy. "
                         "If findings include specific data not traceable to any fetched page, flag it.\n"
                         "=== END SOURCE VERIFICATION ===")
        user_message += source_block
    
    return user_message


def _validate_confidence_claims(
    research_output: dict,
    critique_result: dict,
    sources_summary: list[dict] | None,
) -> dict:
    """
    Post-hoc validation: check that 'high' confidence claims actually cite 2+ sources.
    
    If a claim is marked 'high' confidence but cites only 1 or 0 sources,
    apply an accuracy penalty and add a weakness note.
    """
    import config as _cfg
    
    findings = research_output.get("findings", [])
    if not findings:
        return critique_result
    
    # Collect all fetched URLs for cross-reference
    fetched_urls = set()
    if sources_summary:
        for s in sources_summary:
            if s.get("tool") in ("fetch_page", "search_and_fetch") and s.get("success"):
                url = s.get("url", s.get("query", ""))
                if url:
                    fetched_urls.add(url.lower().rstrip("/"))
    
    # Check each high-confidence claim
    invalid_high = []
    for finding in findings:
        if finding.get("confidence", "").lower() != "high":
            continue
        
        # Check source count
        source = finding.get("source", "")
        sources_cited = [s.strip() for s in source.split(",") if s.strip()] if source else []
        
        # A high-confidence claim should cite at least 2 sources
        if len(sources_cited) < 2:
            claim_preview = finding.get("claim", "")[:80]
            invalid_high.append(f"'{claim_preview}...' (high confidence, only {len(sources_cited)} source(s))")
    
    if invalid_high:
        penalty = getattr(_cfg, "CONFIDENCE_PENALTY", 1.0)
        
        # Apply accuracy penalty
        scores = critique_result.get("scores", {})
        original_accuracy = scores.get("accuracy", 0)
        new_accuracy = max(1, original_accuracy - penalty)
        scores["accuracy"] = new_accuracy
        
        # Recalculate overall
        weights = DEFAULT_RUBRIC_WEIGHTS
        overall = sum(scores.get(dim, 0) * w for dim, w in weights.items())
        critique_result["overall_score"] = round(overall, 2)
        critique_result["verdict"] = "accept" if critique_result["overall_score"] >= 6 else "reject"
        
        # Add weakness note
        weaknesses = critique_result.get("weaknesses", [])
        weaknesses.append(
            f"[CONFIDENCE CHECK] {len(invalid_high)} 'high' confidence claim(s) lack multi-source backing "
            f"(accuracy -{penalty}): {invalid_high[0]}"
        )
        critique_result["weaknesses"] = weaknesses
        critique_result["_confidence_penalty"] = {
            "count": len(invalid_high),
            "penalty_applied": penalty,
            "original_accuracy": original_accuracy,
            "new_accuracy": new_accuracy,
        }
    
    return critique_result


def _log_parse_failure(domain: str, raw_text: str) -> None:
    """Write raw critic response to a debug log on parse failure."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        log_path = os.path.join(LOG_DIR, "critic_parse_failures.jsonl")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "domain": domain,
            "raw_text": raw_text[:5000],
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.warning(f"Critic parse failure logged to {log_path}")
    except Exception as e:
        logger.error(f"Failed to log critic parse failure: {e}")
