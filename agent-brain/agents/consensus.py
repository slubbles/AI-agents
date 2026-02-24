"""
Consensus Researcher — Multi-Researcher Agreement System

Instead of 1 researcher per question, runs N independent researchers in parallel,
then merges their findings through a synthesizer that resolves disagreements.

Why this is better:
- Single researcher can hallucinate or miss critical sources
- Multiple independent attempts expose different angles
- Disagreements between researchers surface genuine uncertainty
- Consensus findings are inherently higher confidence

Cost: 3 Haiku calls ≈ 1 Sonnet call. The merge step uses Sonnet.
Net effect: ~2x cost for significantly higher quality.

Usage:
    from agents.consensus import consensus_research
    result = consensus_research("What are Bitcoin ETF flows?", domain="crypto", n_researchers=3)
"""

import json
import os
import sys
import concurrent.futures
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS
from agents.researcher import research
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Default number of independent researchers
DEFAULT_N_RESEARCHERS = 3
MAX_N_RESEARCHERS = 5


def _run_single_researcher(args: tuple) -> dict:
    """Run a single researcher (for use with ThreadPoolExecutor)."""
    question, strategy, critique, domain, researcher_id = args
    try:
        result = research(
            question=question,
            strategy=strategy,
            critique=critique,
            domain=domain,
        )
        result["_researcher_id"] = researcher_id
        return result
    except Exception as e:
        return {
            "question": question,
            "findings": [],
            "key_insights": [],
            "knowledge_gaps": [],
            "sources_used": [],
            "summary": f"Researcher {researcher_id} failed: {str(e)}",
            "_researcher_id": researcher_id,
            "_error": str(e),
        }


def _build_merge_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a research synthesizer for an autonomous intelligence system. TODAY'S DATE: {today}.

You receive findings from N INDEPENDENT researchers who each answered the same question
separately. Your job is to MERGE their findings into a single, superior output.

MERGE RULES:
1. AGREEMENT: When 2+ researchers report the same fact → high confidence, cite both sources
2. DISAGREEMENT: When researchers contradict each other → flag as disputed, explain both sides
3. UNIQUE FINDINGS: When only 1 researcher found something → keep it, mark confidence appropriately  
4. DEDUPLICATION: Merge identical/near-identical claims into one, aggregate sources
5. QUALITY FILTER: Drop findings that are vague, unsourced, or clearly wrong
6. COVERAGE: The merged output should cover MORE ground than any single researcher
7. GAPS: Knowledge gaps reported by ALL researchers are real gaps. Gaps unique to one may be filled by another's findings.

You must produce a consensus quality assessment:
- "strong_consensus": 80%+ of findings are agreed upon
- "moderate_consensus": 50-79% agreement
- "weak_consensus": <50% agreement (lots of contradictions)

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{{
    "question": "the original question",
    "findings": [
        {{
            "claim": "the specific factual claim",
            "confidence": "high|medium|low",
            "reasoning": "why this confidence level — how many researchers agreed",
            "source": "URL",
            "agreement": "unanimous|majority|single|disputed"
        }}
    ],
    "key_insights": ["insight1", "insight2"],
    "knowledge_gaps": ["gap1", "gap2"],
    "sources_used": ["url1", "url2"],
    "summary": "2-3 sentence synthesis of all findings",
    "consensus_level": "strong_consensus|moderate_consensus|weak_consensus",
    "consensus_stats": {{
        "researchers_count": 0,
        "total_findings_input": 0,
        "total_findings_merged": 0,
        "agreements": 0,
        "disagreements": 0,
        "unique_findings": 0
    }},
    "disagreements": [
        {{
            "topic": "what they disagree about",
            "positions": ["researcher 1 says X", "researcher 2 says Y"],
            "resolution": "which appears more reliable and why"
        }}
    ]
}}
"""


def merge_findings(question: str, researcher_outputs: list[dict], domain: str) -> dict:
    """
    Merge findings from multiple independent researchers into consensus output.
    
    Uses Sonnet for strong reasoning about agreement/disagreement.
    """
    # Prepare researcher summaries for the merge prompt
    researcher_data = []
    for i, output in enumerate(researcher_outputs):
        if output.get("_error"):
            continue  # Skip failed researchers
        researcher_data.append({
            "researcher_id": i + 1,
            "findings": output.get("findings", []),
            "key_insights": output.get("key_insights", []),
            "knowledge_gaps": output.get("knowledge_gaps", []),
            "sources_used": output.get("sources_used", []),
            "summary": output.get("summary", ""),
            "searches_made": output.get("_searches_made", 0),
        })

    if not researcher_data:
        return {
            "question": question,
            "findings": [],
            "key_insights": [],
            "knowledge_gaps": ["All researchers failed"],
            "sources_used": [],
            "summary": "All independent researchers failed to produce findings.",
            "consensus_level": "weak_consensus",
            "_consensus_failed": True,
        }

    # If only 1 researcher succeeded, just return their output directly
    if len(researcher_data) == 1:
        single = researcher_outputs[0]
        single["consensus_level"] = "single_researcher"
        single["consensus_stats"] = {
            "researchers_count": 1,
            "total_findings_input": len(single.get("findings", [])),
            "total_findings_merged": len(single.get("findings", [])),
            "agreements": 0,
            "disagreements": 0,
            "unique_findings": len(single.get("findings", [])),
        }
        return single

    user_message = (
        f"Merge findings from {len(researcher_data)} independent researchers "
        f"who each answered: \"{question}\"\n\n"
        f"RESEARCHER OUTPUTS:\n{json.dumps(researcher_data, indent=2)}"
    )

    try:
        response = create_message(
            client,
            model=MODELS["synthesizer"],  # Sonnet — needs reasoning for merge
            max_tokens=6144,
            system=_build_merge_prompt(),
            messages=[{"role": "user", "content": user_message}],
        )

        log_cost(
            MODELS["synthesizer"],
            response.usage.input_tokens,
            response.usage.output_tokens,
            "consensus_merge",
            domain,
        )

        raw_text = response.content[0].text.strip()
        EXPECTED_KEYS = {"question", "findings", "summary", "consensus_level"}
        result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

        if result:
            # Preserve metadata
            result["_consensus"] = True
            result["_researchers_used"] = len(researcher_data)
            result["_researchers_total"] = len(researcher_outputs)
            total_searches = sum(o.get("_searches_made", 0) for o in researcher_outputs)
            result["_searches_made"] = total_searches
            result["_empty_searches"] = sum(o.get("_empty_searches", 0) for o in researcher_outputs)
            return result
    except Exception as e:
        print(f"  [CONSENSUS] Merge failed: {e}")

    # Fallback: if merge fails, use the best single researcher output
    best = max(researcher_outputs, key=lambda o: len(o.get("findings", [])))
    best["_consensus_merge_failed"] = True
    best["consensus_level"] = "merge_failed"
    return best


def consensus_research(
    question: str,
    strategy: str | None = None,
    critique: str | None = None,
    domain: str = "general",
    n_researchers: int = DEFAULT_N_RESEARCHERS,
) -> dict:
    """
    Run N independent researchers on the same question, then merge findings.
    
    This is the drop-in replacement for single-researcher research().
    Returns the same output format, enriched with consensus metadata.
    
    Args:
        question: The research question
        strategy: Domain strategy (passed to all researchers)
        critique: Previous critique feedback (for retries)
        domain: Research domain
        n_researchers: Number of independent researchers (default: 3)
    
    Returns:
        Merged findings dict with consensus_level and agreement metadata
    """
    n_researchers = min(n_researchers, MAX_N_RESEARCHERS)
    
    print(f"  [CONSENSUS] Running {n_researchers} independent researchers...")

    # Run researchers in parallel using threads
    # (API calls are I/O bound, threads work fine)
    args_list = [
        (question, strategy, critique, domain, i + 1)
        for i in range(n_researchers)
    ]

    researcher_outputs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_researchers) as executor:
        futures = [executor.submit(_run_single_researcher, args) for args in args_list]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            rid = result.get("_researcher_id", "?")
            findings_count = len(result.get("findings", []))
            error = result.get("_error")
            if error:
                print(f"  [RESEARCHER {rid}] Failed: {error}")
            else:
                print(f"  [RESEARCHER {rid}] {findings_count} findings, "
                      f"{result.get('_searches_made', 0)} searches")
            researcher_outputs.append(result)

    # Sort by researcher_id for deterministic ordering
    researcher_outputs.sort(key=lambda o: o.get("_researcher_id", 0))

    # Merge findings
    print(f"  [CONSENSUS] Merging {len(researcher_outputs)} researcher outputs...")
    merged = merge_findings(question, researcher_outputs, domain)

    consensus = merged.get("consensus_level", "unknown")
    merged_count = len(merged.get("findings", []))
    disagreements = len(merged.get("disagreements", []))
    
    print(f"  [CONSENSUS] ✓ {merged_count} merged findings — {consensus}")
    if disagreements:
        print(f"  [CONSENSUS] ⚠ {disagreements} disagreement(s) flagged")

    return merged
