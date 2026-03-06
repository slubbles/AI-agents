"""
Opportunity Scorer — LLM-based pain point analysis + deterministic ranking.

Takes raw Reddit posts from signal_collector and:
1. Batches posts for efficient LLM analysis (cheap model: DeepSeek)
2. Extracts: pain point, severity, audience, existing solutions
3. Scores each with deterministic formula
4. Generates weekly briefs (premium model for top-3 synthesis only)

Cost design:
    - Analysis: DeepSeek (cheapest tier) — ~$0.01-0.03 per batch of 10
    - Weekly brief top-3: Claude (premium) — ~$0.05 total
    - Everything else: zero LLM cost
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

from config import MODELS, CHEAPEST_MODEL, PREMIUM_MODEL
from llm_router import call_llm
from cost_tracker import log_cost
from signal_collector import (
    get_unanalyzed_posts,
    insert_analysis,
    get_top_opportunities,
    get_collection_stats,
    init_signals_db,
    CATEGORIES,
)
from utils.atomic_write import atomic_json_write
from utils.json_parser import extract_json

logger = logging.getLogger(__name__)


# ── Analysis Prompt ─────────────────────────────────────────────────────

ANALYSIS_PROMPT = """Analyze these Reddit posts for pain points and product opportunities.

For EACH post, extract a JSON object. Return a JSON array of objects.

Categories: {categories}

Posts to analyze:
{posts_block}

---

For each post, return:
{{
    "post_id": <the post id>,
    "pain_point_summary": "One clear sentence describing the user's pain or frustration",
    "category": "One of the categories listed above",
    "severity": <1-5 integer, 5 = extreme frustration>,
    "affected_audience": "Who experiences this (be specific)",
    "potential_solutions": ["Idea 1", "Idea 2", "Idea 3"],
    "market_size_estimate": "Small|Medium|Large - brief reasoning",
    "existing_solutions": ["Tool 1", "Tool 2"],
    "opportunity_score": <1-100 based on: pain severity, urgency, willingness to pay, wedge clarity, lack_of_solutions, switching cost, distribution difficulty, and trust/liability risk>
}}

Rules:
- Be practical and specific. Focus on actionable software/product ideas.
- Penalize broad, generic pain points with no sharp wedge. "Marketing is hard" should not score like a concrete buyer workflow.
- Penalize ideas in crowded categories with strong incumbents, high switching costs, or obvious substitutes.
- Penalize trust-heavy or liability-heavy workflows unless the post suggests a narrow, credible entry wedge.
- Reward concrete pain tied to money, time, compliance, or operational failure.
- Reward opportunities with a clear first buyer and a narrow, underserved entry point.
- If a post has no clear pain point, set opportunity_score to 10 or below.
- Generic market facts should usually score 60 or below unless the post reveals a clear wedge or strong unmet need.
- Return ONLY a JSON array. No markdown, no explanation.
"""

BRIEF_PROMPT = """You are a market research analyst. Given these top pain-point opportunities
discovered from Reddit, write a concise weekly brief.

Top opportunities (ranked by opportunity score):
{opportunities}

Write a brief that:
1. Groups related pain points into themes
2. For each theme: what's the pain, who has it, what exists, what's missing
3. Recommends the single best micro-SaaS to build in 2 weeks
4. Explains WHY this one wins (evidence from the data)

Be direct. No fluff. Use specific data from the posts.
Format as clean markdown.
"""


# ── Analysis ────────────────────────────────────────────────────────────

def _format_posts_block(posts: list[dict]) -> str:
    """Format posts for the analysis prompt."""
    blocks = []
    for p in posts:
        body_preview = (p.get("body") or "")[:500]
        blocks.append(
            f"[Post ID: {p['id']}] r/{p['subreddit']}\n"
            f"Title: {p['title']}\n"
            f"Upvotes: {p.get('score', 0)} | Comments: {p.get('num_comments', 0)}\n"
            f"Body: {body_preview}\n"
        )
    return "\n---\n".join(blocks)


def analyze_batch(posts: list[dict], model: str = None) -> list[dict]:
    """
    Analyze a batch of posts using LLM.

    Args:
        posts: List of post dicts from get_unanalyzed_posts()
        model: LLM model to use (default: CHEAPEST_MODEL)

    Returns:
        List of analysis dicts, one per post
    """
    if not posts:
        return []

    if model is None:
        model = CHEAPEST_MODEL

    prompt = ANALYSIS_PROMPT.format(
        categories=", ".join(CATEGORIES),
        posts_block=_format_posts_block(posts),
    )

    response = call_llm(
        model=model,
        system="You are a market research analyst. Return only valid JSON arrays.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        temperature=0.3,
    )

    # Log cost
    if hasattr(response, "usage"):
        log_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_role="signal_analyzer",
            domain="signals",
        )

    # Extract response text
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break

    # Parse JSON array — try direct parse first (extract_json only handles dicts)
    analyses = []
    stripped = text.strip()
    # Remove markdown fences
    import re
    stripped = re.sub(r'```(?:json)?\s*\n?', '', stripped).strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            analyses = parsed
        elif isinstance(parsed, dict):
            analyses = [parsed]
    except (json.JSONDecodeError, TypeError):
        # Fallback: use extract_json for single-object responses
        single = extract_json(text)
        if isinstance(single, dict):
            analyses = [single]

    if not analyses:
        logger.warning(f"[SCORER] Failed to parse analysis response: {text[:200]}")

    return analyses


def score_unanalyzed(batch_size: int = 10, max_batches: int = 5) -> dict:
    """
    Score all unanalyzed posts in batches.

    Args:
        batch_size: Posts per LLM call
        max_batches: Maximum batches to process

    Returns:
        {"analyzed": int, "batches": int, "top_score": int}
    """
    init_signals_db()

    total_analyzed = 0
    batches_run = 0
    top_score = 0

    for _ in range(max_batches):
        posts = get_unanalyzed_posts(limit=batch_size)
        if not posts:
            break

        analyses = analyze_batch(posts)
        batches_run += 1

        # Map analyses back to posts by post_id
        analysis_map = {}
        for a in analyses:
            pid = a.get("post_id")
            if pid is not None:
                analysis_map[pid] = a

        # Also try positional matching as fallback
        for i, post in enumerate(posts):
            analysis = analysis_map.get(post["id"])
            if not analysis and i < len(analyses):
                analysis = analyses[i]

            if analysis:
                # Clamp opportunity_score to 0-100
                score = max(0, min(100, analysis.get("opportunity_score", 0)))
                analysis["opportunity_score"] = score
                if score > top_score:
                    top_score = score

                insert_analysis(post["id"], analysis)
                total_analyzed += 1
            else:
                # Mark as analyzed with zero score to avoid re-processing
                insert_analysis(post["id"], {
                    "pain_point_summary": "Analysis failed",
                    "opportunity_score": 0,
                })

    return {
        "analyzed": total_analyzed,
        "batches": batches_run,
        "top_score": top_score,
    }


# ── Weekly Brief ────────────────────────────────────────────────────────

def generate_weekly_brief(top_n: int = 10, premium_top: int = 3) -> str:
    """
    Generate a weekly opportunity brief.

    Fetches top opportunities, then uses premium model to synthesize
    a readable brief from the top results.

    Args:
        top_n: Number of top opportunities to include
        premium_top: How many to do deep synthesis on (premium model)

    Returns:
        Markdown-formatted brief string
    """
    init_signals_db()

    opportunities = get_top_opportunities(limit=top_n)
    if not opportunities:
        return "No opportunities scored yet. Run `--collect-signals` then `--rank-opportunities` first."

    stats = get_collection_stats()

    # Format opportunities for the prompt
    opp_text = []
    for i, opp in enumerate(opportunities[:top_n], 1):
        solutions = opp.get("potential_solutions", [])
        if isinstance(solutions, str):
            try:
                solutions = json.loads(solutions)
            except (json.JSONDecodeError, TypeError):
                solutions = [solutions]
        existing = opp.get("existing_solutions", [])
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                existing = [existing]

        opp_text.append(
            f"#{i} (Score: {opp.get('opportunity_score', 0)}/100)\n"
            f"  Pain: {opp.get('pain_point_summary', 'N/A')}\n"
            f"  Source: r/{opp.get('subreddit', '?')} — \"{opp.get('title', '')}\"\n"
            f"  Engagement: {opp.get('post_score', 0)} upvotes, {opp.get('num_comments', 0)} comments\n"
            f"  Audience: {opp.get('affected_audience', 'N/A')}\n"
            f"  Severity: {opp.get('severity', 0)}/5\n"
            f"  Market: {opp.get('market_size_estimate', 'N/A')}\n"
            f"  Existing: {', '.join(existing) if existing else 'None found'}\n"
            f"  Ideas: {'; '.join(solutions) if solutions else 'None'}\n"
        )

    prompt = BRIEF_PROMPT.format(opportunities="\n".join(opp_text))

    model = PREMIUM_MODEL
    response = call_llm(
        model=model,
        system="You are a concise market research analyst. Write actionable briefs.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        temperature=0.4,
    )

    if hasattr(response, "usage"):
        log_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_role="signal_brief",
            domain="signals",
        )

    brief_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            brief_text = block.text
            break

    # Add header with stats
    header = (
        f"# Weekly Signal Brief\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"**Collection stats:** {stats['total_posts']} posts collected, "
        f"{stats['analyzed']} analyzed, "
        f"{len(stats.get('subreddits', []))} subreddits tracked\n\n"
        f"---\n\n"
    )

    return header + brief_text


# ── Build Spec Generator ───────────────────────────────────────────────

BUILD_SPEC_PROMPT = """You are a product strategist. Given a validated pain point from Reddit, 
generate a detailed build specification for a micro-SaaS product that solves it.

Pain point data:
- Summary: {pain_point_summary}
- Category: {category}
- Severity: {severity}/5
- Affected audience: {affected_audience}
- Market size: {market_size_estimate}
- Existing solutions: {existing_solutions}
- Previous solution ideas: {potential_solutions}
- Source post title: "{post_title}"
- Source subreddit: r/{subreddit}

Generate a JSON object with:
{{
    "product_name": "Short, memorable product name",
    "problem_statement": "Clear 1-2 sentence problem description",
    "target_audience": "Specific audience (who, how many, where they hang out)",
    "core_features": ["Feature 1", "Feature 2", "Feature 3", "Feature 4", "Feature 5"],
    "tech_stack": "Recommended stack (prefer Next.js + Supabase for speed)",
    "mvp_scope": "What to build in 2 weeks — be specific about pages/endpoints",
    "monetization": "Pricing model and price point with reasoning",
    "existing_competitors": ["Competitor 1 (what they do)", "Competitor 2"],
    "competitive_gap": "What's missing from existing solutions — this is the opportunity",
    "narrow_wedge": "The smallest, most underserved entry segment worth targeting first",
    "distribution_strategy": "Direct, realistic way to reach first customers",
    "killer_objections": ["Objection 1", "Objection 2", "Objection 3"],
    "why_this_could_fail": "The blunt commercial reason this may not be worth building",
    "research_questions": [
        "Question 1 for deeper market validation",
        "Question 2 about technical feasibility",
        "Question 3 about customer acquisition"
    ]
}}

Rules:
- Be specific and practical. This should be buildable by one developer.
- MVP means MINIMUM. Cut anything that isn't essential for first 10 users.
- Price based on pain severity and audience willingness to pay.
- Do NOT assume the idea is good. If the market is crowded or distribution is ugly, say so plainly.
- Prefer a narrow, underserved wedge over a broad SMB or founder category.
- Distribution strategy must be direct and believable, not generic "SEO/content/social" filler.
- Killer objections should reflect why buyers may not switch, trust, or adopt the product.
- Research questions should be answerable via web search.
- Return ONLY valid JSON. No markdown, no explanation.
"""

REALITY_CHECK_EVALUATION_STEPS = [
    "Check whether the pain is tied to concrete financial loss, operational failure, compliance burden, or repeated wasted time.",
    "Check whether the first buyer is narrow, specific, and reachable through a direct channel without brand-scale distribution.",
    "Check whether incumbents, substitutes, switching costs, and trust requirements make adoption materially harder than the build itself.",
    "Check whether a small entry wedge exists that avoids heavy integrations, operational liability, or service expectations.",
    "Prefer ideas with a believable direct GTM path and a clear reason to win, and penalize broad categories with weak differentiation.",
]

REALITY_CHECK_RUBRIC = {
    "go_now": "Sharp wedge, painful workflow, reachable first buyers, and manageable switching/trust risk.",
    "test_first": "Some demand exists, but distribution or differentiation is shaky; validate with a narrow manual or concierge offer.",
    "skip": "Crowded market, weak wedge, ugly distribution, or operational complexity likely kills ROI.",
}


def generate_build_spec(opportunity: dict, model: str = None) -> dict | None:
    """
    Generate a detailed build specification from a scored opportunity.

    Takes a top opportunity dict (from get_top_opportunities) and produces
    a buildable product spec with features, tech stack, pricing, and
    research questions for Brain to investigate further.

    Args:
        opportunity: Opportunity dict with analysis + post context
        model: LLM model (default: CHEAPEST_MODEL)

    Returns:
        Build spec dict, or None on failure
    """
    if model is None:
        model = CHEAPEST_MODEL

    # Format existing solutions/potential solutions for the prompt
    solutions = opportunity.get("potential_solutions", [])
    if isinstance(solutions, str):
        try:
            solutions = json.loads(solutions)
        except (json.JSONDecodeError, TypeError):
            solutions = [solutions] if solutions else []

    existing = opportunity.get("existing_solutions", [])
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except (json.JSONDecodeError, TypeError):
            existing = [existing] if existing else []

    prompt = BUILD_SPEC_PROMPT.format(
        pain_point_summary=opportunity.get("pain_point_summary", "Unknown"),
        category=opportunity.get("category", "Other"),
        severity=opportunity.get("severity", 3),
        affected_audience=opportunity.get("affected_audience", "Unknown"),
        market_size_estimate=opportunity.get("market_size_estimate", "Unknown"),
        existing_solutions=", ".join(existing) if existing else "None found",
        potential_solutions=", ".join(solutions) if solutions else "None",
        post_title=opportunity.get("title", ""),
        subreddit=opportunity.get("subreddit", "unknown"),
    )

    response = call_llm(
        model=model,
        system="You are a product strategist. Return only valid JSON.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        temperature=0.4,
    )

    if hasattr(response, "usage"):
        log_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_role="build_spec_generator",
            domain="signals",
        )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break

    spec = extract_json(text)
    if not spec or not isinstance(spec, dict):
        logger.warning(f"[SPEC] Failed to parse build spec: {text[:200]}")
        return None

    # Store spec to disk for reference
    _save_build_spec(spec, opportunity)

    return spec


def _build_reality_check_evidence(opportunity: dict, spec: dict) -> dict:
    """Build a repeatable commercial-evaluation packet for Cortex."""
    return {
        "opportunity": {
            "pain_point_summary": opportunity.get("pain_point_summary"),
            "category": opportunity.get("category"),
            "severity": opportunity.get("severity"),
            "affected_audience": opportunity.get("affected_audience"),
            "market_size_estimate": opportunity.get("market_size_estimate"),
            "opportunity_score": opportunity.get("opportunity_score"),
            "subreddit": opportunity.get("subreddit"),
            "source_post_title": opportunity.get("title"),
            "existing_solutions": opportunity.get("existing_solutions"),
            "potential_solutions": opportunity.get("potential_solutions"),
        },
        "proposed_product": {
            "product_name": spec.get("product_name"),
            "problem_statement": spec.get("problem_statement"),
            "target_audience": spec.get("target_audience"),
            "core_features": spec.get("core_features", []),
            "mvp_scope": spec.get("mvp_scope"),
            "monetization": spec.get("monetization"),
            "existing_competitors": spec.get("existing_competitors", []),
            "competitive_gap": spec.get("competitive_gap"),
            "narrow_wedge": spec.get("narrow_wedge"),
            "distribution_strategy": spec.get("distribution_strategy"),
            "killer_objections": spec.get("killer_objections", []),
            "why_this_could_fail": spec.get("why_this_could_fail"),
        },
        "commercial_evaluation_steps": REALITY_CHECK_EVALUATION_STEPS,
        "commercial_rubric": REALITY_CHECK_RUBRIC,
    }


def generate_opportunity_decision_packet(
    opportunity: dict,
    model: str = None,
    focus: str = "",
) -> dict | None:
    """
    Generate a build spec plus a Cortex commercial reality check.

    This creates a reusable decision packet so the signals workflow can move
    from raw opportunity -> proposed product -> commercial verdict.
    """
    spec = generate_build_spec(opportunity, model=model)
    if not spec:
        return None

    from agents.cortex import reality_check_opportunity

    evidence = _build_reality_check_evidence(opportunity, spec)
    idea_name = spec.get("product_name") or opportunity.get("pain_point_summary") or "Unnamed opportunity"
    reality_check = reality_check_opportunity(
        idea_name,
        evidence,
        domain="signals",
        focus=focus,
    )

    packet = {
        "opportunity": {
            "post_id": opportunity.get("post_id"),
            "pain_point_summary": opportunity.get("pain_point_summary"),
            "opportunity_score": opportunity.get("opportunity_score"),
            "severity": opportunity.get("severity"),
            "affected_audience": opportunity.get("affected_audience"),
            "subreddit": opportunity.get("subreddit"),
            "title": opportunity.get("title"),
        },
        "build_spec": spec,
        "evaluation_framework": {
            "steps": REALITY_CHECK_EVALUATION_STEPS,
            "rubric": REALITY_CHECK_RUBRIC,
        },
        "reality_check": reality_check,
        "decision_summary": {
            "verdict": reality_check.get("verdict"),
            "worth_building_now": reality_check.get("worth_building_now"),
            "best_wedge": reality_check.get("underserved_wedge") or spec.get("narrow_wedge"),
            "direct_gtm_plan": reality_check.get("direct_gtm_plan") or spec.get("distribution_strategy"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    packet["artifact_path"] = _save_decision_packet(packet, spec)
    return packet


def _save_build_spec(spec: dict, opportunity: dict):
    """Persist build spec to logs/build_specs/ for reference."""
    spec_dir = os.path.join(os.path.dirname(__file__), "logs", "build_specs")
    os.makedirs(spec_dir, exist_ok=True)

    product_name = spec.get("product_name", "unnamed").lower().replace(" ", "_")[:30]
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{product_name}.json"

    record = {
        "spec": spec,
        "source_opportunity": {
            "post_id": opportunity.get("post_id"),
            "opportunity_score": opportunity.get("opportunity_score"),
            "pain_point_summary": opportunity.get("pain_point_summary"),
            "subreddit": opportunity.get("subreddit"),
            "title": opportunity.get("title"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    filepath = os.path.join(spec_dir, filename)
    atomic_json_write(filepath, record)
    logger.info(f"[SPEC] Saved build spec to {filepath}")


def _save_decision_packet(packet: dict, spec: dict) -> str:
    """Persist a combined build-spec + commercial-verdict packet."""
    spec_dir = os.path.join(os.path.dirname(__file__), "logs", "build_specs")
    os.makedirs(spec_dir, exist_ok=True)

    product_name = spec.get("product_name", "unnamed").lower().replace(" ", "_")[:30]
    filename = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
        f"{product_name}_decision.json"
    )

    filepath = os.path.join(spec_dir, filename)
    atomic_json_write(filepath, packet)
    logger.info(f"[SPEC] Saved decision packet to {filepath}")
    return filepath
