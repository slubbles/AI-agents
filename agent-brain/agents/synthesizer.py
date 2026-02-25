"""
Synthesizer Agent — Integrates findings into a domain knowledge base.

This is the missing piece that turns isolated research outputs into compounding
knowledge. Without it, the brain has 12 separate outputs about crypto but no
coherent "here's what we know" document.

What it does:
1. Reads all ACCEPTED outputs for a domain
2. Extracts individual claims with confidence + provenance
3. Detects contradictions between outputs (claim conflict detection)
4. Marks superseded claims when newer evidence overwrites older
5. Produces a synthesized knowledge base: claims ranked by confidence,
   organized by topic, with contradiction flags

The knowledge base is then available to:
- The researcher (via memory recall — avoids redundant searches)
- The question generator (targets gaps in synthesized knowledge, not raw gaps)
- The meta-analyst (sees which topics have strong vs weak coverage)

Uses Sonnet because synthesis + contradiction detection requires strong reasoning.
"""

import json
import os
import re
import sys
from datetime import date, datetime, timezone

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, MIN_OUTPUTS_FOR_SYNTHESIS, MAX_OUTPUTS_TO_SYNTHESIZE, SYNTHESIZE_EVERY_N
from memory_store import load_outputs, save_knowledge_base, load_knowledge_base, get_stats
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)


def _build_synthesis_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a knowledge synthesizer for an autonomous research system. TODAY'S DATE: {today}.

Your job: take multiple research outputs about a domain and synthesize them into a single,
coherent KNOWLEDGE BASE. This knowledge base becomes the system's "memory" — what it
KNOWS about this domain, organized and deduplicated.

You receive:
1. Multiple research outputs, each with: question, findings (claims + confidence), 
   key insights, knowledge gaps, score, and timestamp
2. An existing knowledge base (if one exists) to UPDATE rather than replace

You must:

1. EXTRACT CLAIMS: Pull every distinct factual claim from all outputs
2. DEDUPLICATE: Merge identical or near-identical claims into one
3. DETECT CONTRADICTIONS: When two outputs disagree, flag both claims as "conflicted"
   and note the contradicting claim
4. SUPERSEDE: When a newer output provides updated data on the same fact (e.g., newer
   price, newer stat), mark the old claim as "superseded" and keep the newer one "active"
5. ASSESS CONFIDENCE: Aggregate confidence across outputs that support the same claim:
   - Claim in 3+ outputs with "high" confidence → "established"
   - Claim in 2+ outputs → "corroborated"
   - Claim in 1 output with "high" → "high"
   - Claim in 1 output with "medium" → "medium"
   - Claim in 1 output with "low" → "low"
   - Contradicted by another claim → "disputed"
6. IDENTIFY GAPS: What important questions remain unanswered?
7. ORGANIZE: Group claims into logical topics/subtopics
8. SUMMARIZE: Write a 3-5 sentence domain summary of current understanding

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{{
    "domain_summary": "3-5 sentence summary of everything the system knows about this domain",
    "topics": [
        {{
            "name": "Topic name",
            "subtopics": ["subtopic1", "subtopic2"]
        }}
    ],
    "claims": [
        {{
            "id": "claim_001",
            "claim": "The specific factual claim",
            "topic": "Which topic this belongs to",
            "confidence": "established|corroborated|high|medium|low|disputed",
            "status": "active|superseded|conflicted",
            "first_seen": "ISO timestamp of earliest output containing this",
            "last_confirmed": "ISO timestamp of most recent output confirming this",
            "source_count": 0,
            "sources": ["url1", "url2"],
            "supersedes": null,
            "conflicted_by": null,
            "notes": ""
        }}
    ],
    "contradictions": [
        {{
            "claim_a": "claim_id_a",
            "claim_b": "claim_id_b",
            "description": "What the contradiction is",
            "resolution": "Which claim appears more reliable and why (or 'unresolved')"
        }}
    ],
    "knowledge_gaps": [
        {{
            "gap": "What we don't know",
            "priority": "high|medium|low",
            "related_topic": "Which topic this gap is about"
        }}
    ],
    "synthesis_stats": {{
        "total_claims": 0,
        "active_claims": 0,
        "superseded_claims": 0,
        "disputed_claims": 0,
        "contradictions_found": 0,
        "topics_covered": 0,
        "outputs_synthesized": 0,
        "synthesis_date": "{today}"
    }}
}}
"""


def _build_incremental_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a knowledge synthesizer performing an INCREMENTAL UPDATE. TODAY'S DATE: {today}.

You receive:
1. The EXISTING knowledge base (claims, topics, contradictions, gaps)
2. A small set of NEW research outputs that weren't included in the last synthesis

Your job: MERGE the new findings into the existing knowledge base EFFICIENTLY.

Rules:
- DO NOT rewrite everything. Start from the existing KB structure.
- ADD new claims from the new outputs
- UPDATE existing claims if new evidence confirms or contradicts them
- SUPERSEDE old claims if new data replaces them
- DETECT new contradictions between new and existing claims
- UPDATE confidence levels based on new evidence (e.g., claim now corroborated by 2+ outputs)
- UPDATE the domain summary only if new findings materially change understanding
- REMOVE gaps that the new outputs have addressed
- ADD new gaps discovered in the new outputs

OUTPUT FORMAT: Same as full synthesis — respond with ONLY this JSON, no markdown fencing:
{{
    "domain_summary": "Updated 3-5 sentence summary",
    "topics": [existing + new topics],
    "claims": [all claims — existing updated + new],
    "contradictions": [all contradictions — existing + new],
    "knowledge_gaps": [remaining + new gaps],
    "synthesis_stats": {{
        "total_claims": 0,
        "active_claims": 0,
        "superseded_claims": 0,
        "disputed_claims": 0,
        "contradictions_found": 0,
        "topics_covered": 0,
        "outputs_synthesized": 0,
        "synthesis_date": "{today}",
        "incremental": true,
        "new_outputs_merged": 0
    }}
}}
"""


SYNTHESIS_PROMPT = _build_synthesis_prompt()
INCREMENTAL_PROMPT = _build_incremental_prompt()


def _prepare_synthesis_data(outputs: list[dict], existing_kb: dict | None) -> str:
    """Format accepted outputs + existing KB for synthesis."""
    summaries = []
    for i, out in enumerate(outputs):
        research = out.get("research", {})
        summaries.append({
            "output_number": i + 1,
            "question": out.get("question", ""),
            "timestamp": out.get("timestamp", ""),
            "score": out.get("overall_score", 0),
            "findings": research.get("findings", []),
            "key_insights": research.get("key_insights", []),
            "knowledge_gaps": research.get("knowledge_gaps", []),
            "summary": research.get("summary", ""),
            "sources": research.get("sources_used", []),
        })

    data = {
        "outputs_to_synthesize": summaries,
        "existing_knowledge_base": existing_kb if existing_kb else "(no existing knowledge base — first synthesis)",
    }

    return json.dumps(data, indent=2)


def synthesize(domain: str, force: bool = False) -> dict | None:
    """
    Synthesize all accepted outputs for a domain into a unified knowledge base.
    
    Uses INCREMENTAL mode when an existing KB exists and only a few new outputs
    need to be merged. Uses FULL mode for first synthesis or when forced.
    
    Args:
        domain: The domain to synthesize
        force: If True, do full synthesis even if incremental would work
    
    Returns:
        The synthesized knowledge base dict, or None if not enough data.
    """
    # Load accepted outputs
    all_outputs = load_outputs(domain, min_score=0)
    accepted = [o for o in all_outputs if o.get("verdict") == "accept"]

    if len(accepted) < MIN_OUTPUTS_FOR_SYNTHESIS and not force:
        print(f"[SYNTHESIZER] Not enough accepted outputs for domain '{domain}' "
              f"({len(accepted)}/{MIN_OUTPUTS_FOR_SYNTHESIS}). Skipping.")
        return None

    # Check if synthesis is due (based on count since last synthesis)
    existing_kb = load_knowledge_base(domain)
    if existing_kb and not force:
        last_count = existing_kb.get("synthesis_stats", {}).get("outputs_synthesized", 0)
        new_since = len(accepted) - last_count
        if new_since < SYNTHESIZE_EVERY_N:
            print(f"[SYNTHESIZER] Only {new_since} new outputs since last synthesis "
                  f"(need {SYNTHESIZE_EVERY_N}). Use --synthesize --domain {domain} to force.")
            return existing_kb
    
    # Decide: incremental vs full synthesis
    use_incremental = False
    new_outputs = accepted  # Default: all outputs (full mode)
    
    if existing_kb and not force:
        last_count = existing_kb.get("synthesis_stats", {}).get("outputs_synthesized", 0)
        new_since = len(accepted) - last_count
        if new_since > 0 and new_since <= 10 and last_count >= MIN_OUTPUTS_FOR_SYNTHESIS:
            # Incremental: only send new outputs + existing KB
            use_incremental = True
            new_outputs = accepted[-new_since:]
            print(f"[SYNTHESIZER] Incremental mode: merging {new_since} new outputs into existing KB ({last_count} outputs)")
    
    if not use_incremental:
        # Full synthesis: take recent outputs (respect context limits)
        new_outputs = accepted[-MAX_OUTPUTS_TO_SYNTHESIZE:]

    stats = get_stats(domain)

    if use_incremental:
        print(f"[SYNTHESIZER] Incrementally synthesizing {len(new_outputs)} new outputs for domain '{domain}'...")
    else:
        print(f"[SYNTHESIZER] Full synthesis of {len(new_outputs)} accepted outputs for domain '{domain}'...")
    print(f"  Domain stats: {stats['count']} total, {stats['accepted']} accepted, avg {stats['avg_score']:.1f}")

    if existing_kb:
        existing_claims = len(existing_kb.get("claims", []))
        print(f"  Existing KB: {existing_claims} claims, {'updating' if use_incremental else 'rebuilding'}...")
    else:
        print(f"  No existing KB — creating first synthesis")

    # Prepare data
    if use_incremental:
        synthesis_data = _prepare_synthesis_data(new_outputs, existing_kb)
        system_prompt = INCREMENTAL_PROMPT
        context_label = f"{len(new_outputs)} new"
    else:
        synthesis_data = _prepare_synthesis_data(new_outputs, existing_kb)
        system_prompt = SYNTHESIS_PROMPT
        context_label = f"{len(new_outputs)}"

    user_message = (
        f"Synthesize these {context_label} research outputs for domain '{domain}' "
        f"into a unified knowledge base.\n\n"
        f"DATA:\n{synthesis_data}"
    )

    # Call the synthesizer model (Sonnet — needs strong reasoning for contradictions)
    response = create_message(
        client,
        model=MODELS["synthesizer"],  # Sonnet — needs strong reasoning for contradictions
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    log_cost(
        MODELS["synthesizer"],
        response.usage.input_tokens,
        response.usage.output_tokens,
        "synthesizer",
        domain,
    )

    raw_text = response.content[0].text.strip()
    EXPECTED_KEYS = {"claims", "domain_summary", "synthesis_stats"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if not result:
        print("[SYNTHESIZER] ⚠ Failed to parse synthesizer output")
        return None

    claims = result.get("claims", [])
    if not claims:
        print("[SYNTHESIZER] ⚠ No claims extracted")
        return None

    # Enrich with metadata
    result["_synthesized_at"] = datetime.now(timezone.utc).isoformat()
    result["_domain"] = domain
    result["_outputs_count"] = len(new_outputs)
    result["_incremental"] = use_incremental

    # Update synthesis stats
    synth_stats = result.get("synthesis_stats", {})
    synth_stats["outputs_synthesized"] = len(accepted)  # Total accepted, not just recent
    synth_stats["synthesis_date"] = date.today().isoformat()
    synth_stats["incremental"] = use_incremental
    if use_incremental:
        synth_stats["new_outputs_merged"] = len(new_outputs)
    result["synthesis_stats"] = synth_stats

    # Save to disk
    filepath = save_knowledge_base(domain, result)

    # Print summary
    active = [c for c in claims if c.get("status") == "active"]
    superseded = [c for c in claims if c.get("status") == "superseded"]
    disputed = [c for c in claims if c.get("status") == "conflicted"]
    contradictions = result.get("contradictions", [])
    gaps = result.get("knowledge_gaps", [])
    topics = result.get("topics", [])

    print(f"\n[SYNTHESIZER] ✓ Knowledge base synthesized")
    print(f"  File: {filepath}")
    print(f"  Claims:  {len(active)} active, {len(superseded)} superseded, {len(disputed)} disputed")
    print(f"  Topics:  {len(topics)}")
    print(f"  Contradictions: {len(contradictions)}")
    print(f"  Knowledge gaps: {len(gaps)}")

    if result.get("domain_summary"):
        print(f"\n  Summary: {result['domain_summary'][:300]}")

    if contradictions:
        print(f"\n  ⚠ Contradictions found:")
        for c in contradictions[:5]:
            print(f"    → {c.get('description', '?')}")
            print(f"      Resolution: {c.get('resolution', 'unresolved')}")

    if gaps:
        high_gaps = [g for g in gaps if g.get("priority") == "high"]
        if high_gaps:
            print(f"\n  High-priority gaps:")
            for g in high_gaps[:5]:
                print(f"    → {g.get('gap', '?')}")

    return result


def show_knowledge_base(domain: str):
    """Display the current knowledge base for a domain (for CLI)."""
    kb = load_knowledge_base(domain)
    if not kb:
        print(f"  No knowledge base for domain '{domain}'. Run --synthesize first.")
        return

    print(f"\n  Domain: {domain}")
    print(f"  Synthesized: {kb.get('_synthesized_at', '?')[:19]}")
    print(f"  Outputs used: {kb.get('_outputs_count', '?')}")

    if kb.get("domain_summary"):
        print(f"\n  Summary:")
        print(f"    {kb['domain_summary']}")

    # Topics
    topics = kb.get("topics", [])
    if topics:
        print(f"\n  Topics ({len(topics)}):")
        for t in topics:
            subtopics = ", ".join(t.get("subtopics", []))
            print(f"    • {t.get('name', '?')}: {subtopics}")

    # Claims by status
    claims = kb.get("claims", [])
    active = [c for c in claims if c.get("status") == "active"]
    superseded = [c for c in claims if c.get("status") == "superseded"]
    disputed = [c for c in claims if c.get("status") == "conflicted"]

    print(f"\n  Active Claims ({len(active)}):")
    for c in active:
        conf = c.get("confidence", "?")
        print(f"    [{conf:<12}] {c.get('claim', '?')}")

    if disputed:
        print(f"\n  ⚠ Disputed Claims ({len(disputed)}):")
        for c in disputed:
            print(f"    [{c.get('confidence', '?'):<12}] {c.get('claim', '?')}")
            if c.get("conflicted_by"):
                print(f"      Conflicts with: {c['conflicted_by']}")

    if superseded:
        print(f"\n  Superseded Claims ({len(superseded)}):")
        for c in superseded[:10]:
            print(f"    [outdated     ] {c.get('claim', '?')}")
            if c.get("supersedes"):
                print(f"      Replaced by: {c['supersedes']}")

    # Contradictions
    contradictions = kb.get("contradictions", [])
    if contradictions:
        print(f"\n  Contradictions ({len(contradictions)}):")
        for con in contradictions:
            print(f"    → {con.get('description', '?')}")
            print(f"      Resolution: {con.get('resolution', 'unresolved')}")

    # Gaps
    gaps = kb.get("knowledge_gaps", [])
    if gaps:
        print(f"\n  Knowledge Gaps ({len(gaps)}):")
        for g in gaps:
            pri = g.get("priority", "?").upper()
            print(f"    [{pri}] {g.get('gap', '?')}")

    # Stats
    synth_stats = kb.get("synthesis_stats", {})
    print(f"\n  Stats:")
    print(f"    Total claims:      {synth_stats.get('total_claims', '?')}")
    print(f"    Active:            {synth_stats.get('active_claims', '?')}")
    print(f"    Superseded:        {synth_stats.get('superseded_claims', '?')}")
    print(f"    Disputed:          {synth_stats.get('disputed_claims', '?')}")
    print(f"    Contradictions:    {synth_stats.get('contradictions_found', '?')}")
    print(f"    Topics:            {synth_stats.get('topics_covered', '?')}")
    print(f"    Outputs used:      {synth_stats.get('outputs_synthesized', '?')}")
