"""
Claim Verifier — Ground-Truth Checking for High-Confidence Claims

Breaks the LLM-judging-LLM circle by checking the system's own
high-confidence claims against external web evidence.

Unlike agents/verifier.py (which handles time-bound predictions),
this module targets general factual claims marked as "high" confidence
in the knowledge base. It:

1. Samples high-confidence claims that haven't been verified recently
2. Constructs a focused web search to check each claim
3. Judges whether external evidence supports or contradicts the claim
4. Updates claim status and confidence in the KB
5. Feeds refutations back as research lessons

This is the system's immune system — catching compounded errors
before they calcify into "known facts" that contaminate future research.
"""

import json
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import (
    MODELS, MEMORY_DIR,
    CLAIM_VERIFY_MAX_PER_CYCLE, CLAIM_VERIFY_MIN_CONFIDENCE,
)
from memory_store import load_knowledge_base, save_knowledge_base
from cost_tracker import log_cost
from utils.json_parser import extract_json


def _build_verification_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a fact-checker verifying a specific claim against web search results.

TODAY'S DATE: {today}

You receive:
1. A claim from an internal knowledge base
2. The claim's stated confidence level
3. Web search results that may confirm or contradict the claim

Your job: determine if the external evidence supports the claim.

RULES:
- "confirmed" — search results clearly support the claim
- "refuted" — search results clearly contradict the claim (provide the correct information)
- "weakened" — evidence suggests the claim is partially wrong or outdated
- "inconclusive" — not enough evidence to judge either way
- Be conservative: only mark "confirmed" if evidence is clear, only "refuted" if contradiction is definitive
- Check for recency: a claim that was true 6 months ago may no longer be true

OUTPUT FORMAT — respond with ONLY valid JSON, no markdown fencing:
{{
    "verdict": "confirmed|refuted|weakened|inconclusive",
    "evidence_summary": "What the search results actually say",
    "corrected_claim": "If refuted/weakened, what the claim SHOULD say (null if confirmed)",
    "confidence_adjustment": "raise|keep|lower|retract",
    "reasoning": "Brief explanation of your judgment"
}}"""



def _get_verifiable_claims(domain: str, max_claims: int = 10) -> list[dict]:
    """
    Select high-confidence claims that are due for external verification.

    Prioritizes:
    1. Claims never externally verified
    2. Claims not verified in the last 14 days
    3. Highest confidence first

    Skips claims that are already superseded, expired, or recently verified.
    """
    kb = load_knowledge_base(domain)
    if not kb:
        return []

    claims = kb.get("claims", [])
    now = datetime.now(timezone.utc)
    candidates = []

    confidence_order = {"high": 3, "medium": 2, "low": 1}
    min_level = confidence_order.get(CLAIM_VERIFY_MIN_CONFIDENCE, 3)

    for claim in claims:
        if claim.get("status") in ("superseded", "expired"):
            continue

        conf = claim.get("confidence", "low")
        if confidence_order.get(conf, 0) < min_level:
            continue

        last_verified = claim.get("_last_verified")
        if last_verified:
            try:
                lv = datetime.fromisoformat(last_verified)
                if lv.tzinfo is None:
                    lv = lv.replace(tzinfo=timezone.utc)
                days_since = (now - lv).days
                if days_since < 14:
                    continue
            except (ValueError, TypeError):
                pass

        candidates.append({
            "claim_data": claim,
            "confidence_rank": confidence_order.get(conf, 0),
            "never_verified": last_verified is None,
        })

    candidates.sort(key=lambda c: (c["never_verified"], c["confidence_rank"]), reverse=True)
    return [c["claim_data"] for c in candidates[:max_claims]]


def _build_search_query(claim: dict) -> str:
    """Build a focused web search query to verify a claim."""
    claim_text = claim.get("claim", "")
    if len(claim_text) > 150:
        claim_text = claim_text[:150]

    keywords = []
    for word in claim_text.split():
        clean = word.strip(".,;:!?\"'()[]")
        if len(clean) > 3 and clean.lower() not in {
            "that", "this", "with", "from", "have", "been",
            "their", "which", "about", "would", "could",
            "should", "these", "those", "there", "where",
        }:
            keywords.append(clean)

    if len(keywords) > 8:
        keywords = keywords[:8]

    return " ".join(keywords)


def verify_claims(domain: str, max_checks: int = None) -> list[dict]:
    """
    Verify high-confidence claims against external web evidence.

    Returns list of verification results.
    """
    if max_checks is None:
        max_checks = CLAIM_VERIFY_MAX_PER_CYCLE

    claims = _get_verifiable_claims(domain, max_claims=max_checks)
    if not claims:
        return []

    from tools.web_search import web_search
    from llm_router import call_llm

    results = []
    kb = load_knowledge_base(domain)
    kb_claims = kb.get("claims", []) if kb else []
    kb_modified = False

    for claim in claims:
        claim_text = claim.get("claim", "")
        claim_id = claim.get("id", "?")

        query = _build_search_query(claim)
        if not query:
            continue

        try:
            search_results = web_search(query)
        except Exception as e:
            print(f"  [CLAIM-VERIFY] Search failed for claim {claim_id}: {e}")
            continue

        if not search_results:
            continue

        user_message = (
            f"Verify this claim from our knowledge base:\n\n"
            f"CLAIM: {claim_text}\n"
            f"CONFIDENCE: {claim.get('confidence', '?')}\n"
            f"FIRST SEEN: {claim.get('first_seen', '?')}\n\n"
            f"WEB SEARCH RESULTS:\n{json.dumps(search_results[:5], indent=2)}"
        )

        try:
            response = call_llm(
                model=MODELS["verifier"],
                system=_build_verification_prompt(),
                messages=[{"role": "user", "content": user_message}],
                max_tokens=1024,
                temperature=0.2,
            )
            log_cost(MODELS["verifier"], response.usage.input_tokens,
                     response.usage.output_tokens, "claim_verifier", domain)
        except Exception as e:
            print(f"  [CLAIM-VERIFY] LLM call failed for claim {claim_id}: {e}")
            continue

        raw = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw += block.text

        verification = extract_json(raw.strip(), expected_keys={"verdict", "evidence_summary"})
        if not verification:
            continue

        verdict = verification.get("verdict", "inconclusive")
        result = {
            "claim_id": claim_id,
            "claim": claim_text[:120],
            "verdict": verdict,
            "evidence": verification.get("evidence_summary", ""),
            "corrected_claim": verification.get("corrected_claim"),
            "confidence_adjustment": verification.get("confidence_adjustment", "keep"),
            "reasoning": verification.get("reasoning", ""),
        }
        results.append(result)

        # Update the KB claim in-place
        for kb_claim in kb_claims:
            if kb_claim.get("id") == claim_id or kb_claim.get("claim") == claim.get("claim"):
                kb_claim["_last_verified"] = datetime.now(timezone.utc).isoformat()
                kb_claim["_verification_verdict"] = verdict

                adj = verification.get("confidence_adjustment", "keep")
                if adj == "lower" and kb_claim.get("confidence") == "high":
                    kb_claim["confidence"] = "medium"
                    kb_modified = True
                elif adj == "retract":
                    kb_claim["status"] = "disputed"
                    kb_claim["confidence"] = "low"
                    kb_modified = True
                elif adj == "raise" and kb_claim.get("confidence") in ("low", "medium"):
                    kb_claim["confidence"] = "high" if kb_claim["confidence"] == "medium" else "medium"
                    kb_modified = True

                if verdict == "refuted":
                    corrected = verification.get("corrected_claim")
                    if corrected:
                        kb_claim["notes"] = (
                            kb_claim.get("notes", "") +
                            f" [REFUTED {date.today().isoformat()}]: {corrected}"
                        ).strip()
                    kb_claim["status"] = "disputed"
                    kb_modified = True

                break

        icon = {"confirmed": "+", "refuted": "X", "weakened": "~", "inconclusive": "?"}.get(verdict, "?")
        print(f"  [{icon}] {claim_text[:80]}... -> {verdict}")

    if kb_modified and kb:
        save_knowledge_base(domain, kb)

    # Feed refutations back as research lessons
    refuted = [r for r in results if r["verdict"] == "refuted"]
    for r in refuted:
        try:
            from research_lessons import add_lesson
            add_lesson(
                domain,
                lesson=(
                    f"REFUTED CLAIM: \"{r['claim']}\" — "
                    f"Evidence: {r['evidence'][:200]}"
                ),
                source="claim_verifier",
                details=(
                    f"A high-confidence claim was contradicted by external evidence. "
                    f"Corrected: {r.get('corrected_claim', 'N/A')}"
                ),
            )
        except Exception:
            pass

    return results


def get_claim_verification_stats(domain: str) -> dict:
    """Get stats on claim verification status for a domain."""
    kb = load_knowledge_base(domain)
    if not kb:
        return {"total": 0}

    claims = kb.get("claims", [])
    active = [c for c in claims if c.get("status") not in ("superseded", "expired")]

    verified = sum(1 for c in active if c.get("_last_verified"))
    unverified = sum(1 for c in active if not c.get("_last_verified"))

    verdicts = {}
    for c in active:
        v = c.get("_verification_verdict")
        if v:
            verdicts[v] = verdicts.get(v, 0) + 1

    return {
        "total_active": len(active),
        "verified": verified,
        "unverified": unverified,
        "verification_rate": verified / len(active) if active else 0,
        "verdicts": verdicts,
    }
