"""
Verifier Agent — Prediction tracking + outcome verification.

Breaks the circular LLM-judging-LLM problem by introducing external ground truth.
The verifier:
1. Extracts time-bound predictions from knowledge base claims
2. Checks if prediction deadlines have passed
3. Searches the web for actual outcomes
4. Marks predictions as confirmed/refuted/inconclusive
5. Updates prediction confidence in the knowledge base

This is the system's reality check — the only agent that compares internal
beliefs against external facts after the fact.
"""

import json
import os
import sys
from datetime import date, datetime, timezone

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, MEMORY_DIR
from memory_store import load_knowledge_base, save_knowledge_base
from tools.web_search import web_search, SEARCH_TOOL_DEFINITION
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ============================================================
# Prediction Store
# ============================================================

def _predictions_path(domain: str) -> str:
    """Return path to predictions file for a domain."""
    return os.path.join(MEMORY_DIR, domain, "_predictions.json")


def load_predictions(domain: str) -> list[dict]:
    """Load all predictions for a domain."""
    path = _predictions_path(domain)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_predictions(domain: str, predictions: list[dict]) -> str:
    """Save predictions list for a domain."""
    path = _predictions_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(predictions, f, indent=2)
    return path


# ============================================================
# Prediction Extraction
# ============================================================

EXTRACTION_PROMPT = """\
You are a prediction extractor. Given a set of knowledge base claims, identify any that contain
TIME-BOUND PREDICTIONS — statements about what WILL happen by a specific date or timeframe.

Examples of predictions:
- "Bitcoin is expected to reach $100k by end of 2026" → prediction, deadline: 2026-12-31
- "The Fed will cut rates in Q2 2026" → prediction, deadline: 2026-06-30
- "GPU prices will drop 30% by summer 2025" → prediction, deadline: 2025-08-31

NOT predictions (these are historical facts):
- "Bitcoin reached $69k in November 2021"
- "The Fed raised rates 11 times in 2022-2023"

For each prediction found, extract:
1. The prediction text (the specific claim)
2. The deadline (ISO date — when we can check if it came true)
3. The source claim ID from the KB
4. How to verify it (what search query would check the outcome)

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{
    "predictions": [
        {
            "prediction": "The specific prediction text",
            "deadline": "YYYY-MM-DD",
            "source_claim_id": "claim_XXX",
            "verification_query": "search query to check outcome",
            "category": "price|policy|adoption|technology|regulation|other"
        }
    ],
    "total_claims_analyzed": 0,
    "predictions_found": 0
}
"""


def extract_predictions(domain: str) -> list[dict]:
    """
    Extract time-bound predictions from a domain's knowledge base.
    
    Returns list of new predictions found (not already tracked).
    """
    kb = load_knowledge_base(domain)
    if not kb:
        print(f"[VERIFIER] No knowledge base for domain '{domain}'")
        return []
    
    claims = kb.get("claims", [])
    active_claims = [c for c in claims if c.get("status") == "active"]
    
    if not active_claims:
        print(f"[VERIFIER] No active claims in domain '{domain}'")
        return []
    
    # Format claims for extraction
    claims_text = json.dumps([
        {"id": c.get("id", "?"), "claim": c.get("claim", ""), "confidence": c.get("confidence", "?")}
        for c in active_claims
    ], indent=2)
    
    user_message = f"Extract time-bound predictions from these claims:\n\n{claims_text}"
    
    response = create_message(
        client,
        model=MODELS["verifier"],
        max_tokens=2048,
        system=EXTRACTION_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    
    log_cost(MODELS["verifier"], response.usage.input_tokens, response.usage.output_tokens, "verifier", domain)
    
    raw_text = response.content[0].text.strip()
    EXPECTED_KEYS = {"predictions"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)
    
    if not result:
        print("[VERIFIER] ⚠ Failed to parse prediction extraction output")
        return []
    
    new_predictions = result.get("predictions", [])
    if not new_predictions:
        print(f"[VERIFIER] No time-bound predictions found in {len(active_claims)} claims")
        return []
    
    # Deduplicate against existing predictions
    existing = load_predictions(domain)
    existing_texts = {p.get("prediction", "").lower().strip() for p in existing}
    
    truly_new = []
    for pred in new_predictions:
        if pred.get("prediction", "").lower().strip() not in existing_texts:
            pred["status"] = "pending"  # pending verification
            pred["extracted_at"] = datetime.now(timezone.utc).isoformat()
            pred["domain"] = domain
            truly_new.append(pred)
    
    if truly_new:
        all_predictions = existing + truly_new
        save_predictions(domain, all_predictions)
        print(f"[VERIFIER] ✓ Extracted {len(truly_new)} new predictions ({len(existing)} already tracked)")
    else:
        print(f"[VERIFIER] All {len(new_predictions)} predictions already tracked")
    
    return truly_new


# ============================================================
# Prediction Verification
# ============================================================

VERIFICATION_PROMPT = """\
You are a prediction verifier. You check whether a prediction came true based on web search results.

You receive:
1. The original prediction
2. The deadline (has it passed?)
3. Web search results about the outcome

You must determine:
- "confirmed" — the prediction came true (evidence supports it)
- "refuted" — the prediction was wrong (evidence contradicts it)
- "partially_confirmed" — prediction was directionally correct but specifics were off
- "inconclusive" — not enough evidence yet, or deadline hasn't passed

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{
    "verdict": "confirmed|refuted|partially_confirmed|inconclusive",
    "evidence": "Summary of what the web search found",
    "confidence": "high|medium|low",
    "notes": "Any caveats or context"
}
"""


def verify_predictions(domain: str, max_checks: int = 5) -> list[dict]:
    """
    Verify pending predictions whose deadlines have passed.
    Uses web search to check actual outcomes.
    
    Args:
        domain: Domain to check
        max_checks: Maximum predictions to verify in one run (to limit API costs)
    
    Returns:
        List of verification results
    """
    predictions = load_predictions(domain)
    if not predictions:
        print(f"[VERIFIER] No predictions to verify for domain '{domain}'")
        return []
    
    today = date.today()
    today_str = today.isoformat()
    
    # Find predictions that are due for verification
    due = []
    for pred in predictions:
        if pred.get("status") != "pending":
            continue
        deadline = pred.get("deadline", "")
        try:
            dl = date.fromisoformat(deadline)
            if dl <= today:
                due.append(pred)
        except (ValueError, TypeError):
            continue
    
    if not due:
        pending_count = sum(1 for p in predictions if p.get("status") == "pending")
        print(f"[VERIFIER] No predictions due yet ({pending_count} pending, deadlines in future)")
        return []
    
    print(f"[VERIFIER] Found {len(due)} predictions past deadline, checking up to {max_checks}...")
    
    results = []
    for pred in due[:max_checks]:
        query = pred.get("verification_query", pred.get("prediction", ""))
        print(f"[VERIFIER]   Checking: {pred.get('prediction', '?')[:80]}...")
        
        # Search the web for the outcome
        try:
            search_results = web_search(query)
        except Exception as e:
            print(f"[VERIFIER]   ⚠ Search failed: {e}")
            continue
        
        # Ask the verifier model to judge
        user_message = (
            f"Verify this prediction:\n\n"
            f"PREDICTION: {pred.get('prediction', '')}\n"
            f"DEADLINE: {pred.get('deadline', '')}\n"
            f"TODAY: {today_str}\n\n"
            f"WEB SEARCH RESULTS:\n{json.dumps(search_results[:5], indent=2)}"
        )
        
        response = create_message(
            client,
            model=MODELS["verifier"],
            max_tokens=1024,
            system=VERIFICATION_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        
        log_cost(MODELS["verifier"], response.usage.input_tokens, response.usage.output_tokens, "verifier", domain)
        
        raw_text = response.content[0].text.strip()
        EXPECTED_KEYS = {"verdict", "evidence"}
        verification = extract_json(raw_text, expected_keys=EXPECTED_KEYS)
        
        if not verification:
            print(f"[VERIFIER]   ⚠ Failed to parse verification output")
            continue
        
        # Update prediction status
        pred["status"] = verification.get("verdict", "inconclusive")
        pred["verification"] = {
            "verdict": verification.get("verdict", "inconclusive"),
            "evidence": verification.get("evidence", ""),
            "confidence": verification.get("confidence", "low"),
            "notes": verification.get("notes", ""),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        
        verdict = verification.get("verdict", "?")
        print(f"[VERIFIER]   → {verdict}: {verification.get('evidence', '')[:100]}")
        
        results.append({
            "prediction": pred.get("prediction", ""),
            "verdict": verdict,
            "evidence": verification.get("evidence", ""),
        })
    
    # Save updated predictions
    save_predictions(domain, predictions)
    
    # Print summary
    confirmed = sum(1 for r in results if r["verdict"] == "confirmed")
    refuted = sum(1 for r in results if r["verdict"] == "refuted")
    partial = sum(1 for r in results if r["verdict"] == "partially_confirmed")
    inconclusive = sum(1 for r in results if r["verdict"] == "inconclusive")
    
    print(f"\n[VERIFIER] ✓ Verified {len(results)} predictions:")
    print(f"  Confirmed: {confirmed}, Refuted: {refuted}, Partial: {partial}, Inconclusive: {inconclusive}")
    
    return results


def get_verification_stats(domain: str) -> dict:
    """Get summary statistics of predictions for a domain."""
    predictions = load_predictions(domain)
    if not predictions:
        return {"total": 0}
    
    stats = {
        "total": len(predictions),
        "pending": sum(1 for p in predictions if p.get("status") == "pending"),
        "confirmed": sum(1 for p in predictions if p.get("status") == "confirmed"),
        "refuted": sum(1 for p in predictions if p.get("status") == "refuted"),
        "partially_confirmed": sum(1 for p in predictions if p.get("status") == "partially_confirmed"),
        "inconclusive": sum(1 for p in predictions if p.get("status") == "inconclusive"),
    }
    
    if stats["confirmed"] + stats["refuted"] > 0:
        stats["accuracy_rate"] = stats["confirmed"] / (stats["confirmed"] + stats["refuted"])
    else:
        stats["accuracy_rate"] = None
    
    return stats
