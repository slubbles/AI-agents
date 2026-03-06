"""
Threads Analyst Agent — Analyzes Threads content for Cortex.

Two operating modes:

1. **Research Mode** (for Brain):
   - Searches Threads for niche pain points
   - Extracts user language, complaints, feature requests
   - Scores opportunities by specificity, frequency, buildability
   - Returns structured findings for knowledge base

2. **Content Mode** (for Hands/Growth):
   - Analyzes top-performing posts in a niche
   - Extracts patterns (tone, length, hooks, CTAs)
   - Generates content recommendations
   - Writes draft posts using extracted user language

Uses CHEAPEST_MODEL for analysis (synthesis task) and Threads Search API for data.
"""

import json
import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import MODELS, CHEAPEST_MODEL
from llm_router import call_llm
from cost_tracker import log_cost
from utils.json_parser import extract_json

logger = logging.getLogger("threads_analyst")


def analyze_pain_points(
    domain: str,
    query: str,
    threads_data: list[dict],
    goal: str | None = None,
) -> dict:
    """
    Analyze Threads posts for niche pain points and opportunities.
    
    Args:
        domain: Research domain (e.g., "freelance-invoicing")
        query: Original search query
        threads_data: Raw Threads posts from search results
        goal: Optional domain goal for relevance filtering
    
    Returns:
        {
            "pain_points": [
                {
                    "pain": str,
                    "user_language": str,          # exact quotes from posts
                    "frequency": int,              # how many posts mention this
                    "specificity": float,          # 1-10: how specific/actionable
                    "buildability": float,         # 1-10: can we build a solution?
                    "evidence": [str],             # post excerpts
                    "score": float,                # composite score
                }
            ],
            "user_language_patterns": [str],       # recurring phrases
            "market_signals": [str],               # trends, shifts, demands
            "content_opportunities": [str],        # posts Cortex could write
            "summary": str,
        }
    """
    today = date.today().isoformat()
    
    # Format threads data for the prompt
    posts_text = _format_posts(threads_data)
    
    if not threads_data:
        return {
            "pain_points": [],
            "user_language_patterns": [],
            "market_signals": [],
            "content_opportunities": [],
            "summary": f"No Threads data available for '{query}'.",
        }
    
    goal_section = f"\nDOMAIN GOAL: {goal}\nFilter all analysis through this goal — only extract pain points relevant to it.\n" if goal else ""
    
    prompt = f"""\
You are a market research analyst. TODAY: {today}. Domain: {domain}.

Analyze these Threads posts to extract pain points and opportunities.
{goal_section}
THREADS POSTS (from search: "{query}"):
{posts_text}

Extract:
1. **Pain points** — what are people struggling with? Use THEIR exact words.
2. **User language** — recurring phrases, terms, emotional language they use.
3. **Market signals** — trends, shifts, unmet demands.
4. **Content opportunities** — what posts could Cortex write that would resonate?

For each pain point, score:
- specificity (1-10): How specific and actionable is this pain? Generic = low.
- buildability (1-10): Could we realistically build a solution? 
- frequency: How many posts reference this pain?

Return ONLY a JSON object:
{{
    "pain_points": [
        {{
            "pain": "description of the pain point",
            "user_language": "exact quote from a post",
            "frequency": 3,
            "specificity": 7.5,
            "buildability": 8.0,
            "evidence": ["quote 1", "quote 2"],
            "score": 7.8
        }}
    ],
    "user_language_patterns": ["phrase 1", "phrase 2"],
    "market_signals": ["signal 1"],
    "content_opportunities": ["post idea 1"],
    "summary": "One paragraph summary of findings"
}}

Rules:
- Score is weighted average: specificity * 0.3 + buildability * 0.4 + (frequency/total_posts * 10) * 0.3
- Top 5 pain points max, ranked by score
- User language must be ACTUAL phrases from the posts, not paraphrased
- Be honest about sample size — if only 3 posts, say so
"""
    
    model = CHEAPEST_MODEL  # synthesis task
    
    try:
        response = call_llm(
            model=model,
            system=prompt,
            messages=[{"role": "user", "content": "Analyze these Threads posts and extract pain points."}],
            max_tokens=2000,
        )
        
        text = response.get("text", "") if isinstance(response, dict) else str(response)
        result = extract_json(text)
        
        if result and "pain_points" in result:
            logger.info(f"[THREADS] Found {len(result['pain_points'])} pain points for '{domain}'")
            return result
        
        # Fallback: return raw text as summary
        return {
            "pain_points": [],
            "user_language_patterns": [],
            "market_signals": [],
            "content_opportunities": [],
            "summary": text[:500] if text else "Analysis failed — no structured output.",
        }
    
    except Exception as e:
        logger.error(f"[THREADS] Pain point analysis failed: {e}")
        return {
            "pain_points": [],
            "user_language_patterns": [],
            "market_signals": [],
            "content_opportunities": [],
            "summary": f"Analysis error: {e}",
        }


def analyze_content_strategy(
    domain: str,
    threads_data: list[dict],
    goal: str | None = None,
) -> dict:
    """
    Analyze top-performing Threads posts to extract content strategy patterns.
    
    Args:
        domain: Target domain/niche
        threads_data: Posts with engagement data
        goal: Domain goal for context
    
    Returns:
        {
            "patterns": {
                "avg_length": int,
                "tone": str,
                "hooks": [str],
                "cta_styles": [str],
                "posting_times": [str],
            },
            "top_formats": [str],
            "draft_posts": [
                {
                    "text": str,
                    "rationale": str,
                    "target_engagement": str,
                }
            ],
            "recommendations": [str],
        }
    """
    today = date.today().isoformat()
    posts_text = _format_posts(threads_data, include_engagement=True)
    
    if not threads_data:
        return {
            "patterns": {"avg_length": 0, "tone": "unknown", "hooks": [], "cta_styles": [], "posting_times": []},
            "top_formats": [],
            "draft_posts": [],
            "recommendations": ["No data available. Search for posts in this niche first."],
        }
    
    goal_section = f"\nDOMAIN: {domain}\nGOAL: {goal}\n" if goal else f"\nDOMAIN: {domain}\n"
    
    prompt = f"""\
You are a social media content strategist specializing in Threads. TODAY: {today}.
{goal_section}
Analyze these high-performing Threads posts and extract content patterns.

POSTS (with engagement data):
{posts_text}

Extract:
1. **Patterns** — what makes these posts work? Tone, length, structure.
2. **Hooks** — how do top posts open? First line patterns.
3. **Formats** — thread types that perform well (story, list, question, insight, etc.)
4. **Draft posts** — write 3 posts Cortex could publish that follow these patterns.

Return ONLY a JSON object:
{{
    "patterns": {{
        "avg_length": 200,
        "tone": "conversational, authentic, specific",
        "hooks": ["opening line pattern 1", "pattern 2"],
        "cta_styles": ["subtle ask pattern"],
        "posting_times": ["morning", "evening"]
    }},
    "top_formats": ["personal story + insight", "contrarian take"],
    "draft_posts": [
        {{
            "text": "Actual post text Cortex could publish",
            "rationale": "Why this format works based on the data",
            "target_engagement": "replies"
        }}
    ],
    "recommendations": ["Strategic recommendation 1"]
}}

Rules:
- Draft posts must sound HUMAN, not corporate
- Use the user language patterns from the analyzed posts
- Each draft post under 500 characters
- Be specific about what works — "be authentic" is useless advice
"""
    
    model = CHEAPEST_MODEL
    
    try:
        response = call_llm(
            model=model,
            system=prompt,
            messages=[{"role": "user", "content": "Analyze content patterns and generate draft posts."}],
            max_tokens=2000,
        )
        
        text = response.get("text", "") if isinstance(response, dict) else str(response)
        result = extract_json(text)
        
        if result and "patterns" in result:
            logger.info(f"[THREADS] Content strategy extracted for '{domain}'")
            return result
        
        return {
            "patterns": {"avg_length": 0, "tone": "unknown", "hooks": [], "cta_styles": [], "posting_times": []},
            "top_formats": [],
            "draft_posts": [],
            "recommendations": [text[:300] if text else "Analysis returned no structured output."],
        }
    
    except Exception as e:
        logger.error(f"[THREADS] Content strategy analysis failed: {e}")
        return {
            "patterns": {"avg_length": 0, "tone": "error", "hooks": [], "cta_styles": [], "posting_times": []},
            "top_formats": [],
            "draft_posts": [],
            "recommendations": [f"Error: {e}"],
        }


def generate_post(
    domain: str,
    topic: str,
    style: str = "authentic",
    knowledge_context: str = "",
    max_length: int = 500,
) -> dict:
    """
    Generate a Threads post draft using Brain's knowledge.
    
    Args:
        domain: Niche/domain
        topic: What the post should be about
        style: Tone (authentic, insight, question, story, contrarian)
        knowledge_context: Relevant info from Brain's KB
        max_length: Max post length in characters
    
    Returns:
        {
            "text": str,           # The post text
            "hashtags": [str],     # Suggested topic tags
            "hook_type": str,      # What kind of opening
            "estimated_engagement": str,  # low/medium/high
        }
    """
    today = date.today().isoformat()
    
    kb_section = f"\nCONTEXT FROM RESEARCH:\n{knowledge_context[:2000]}\n" if knowledge_context else ""
    
    prompt = f"""\
You are a content writer for Threads. TODAY: {today}. Domain: {domain}.

Write ONE post about: {topic}
Style: {style}
Max length: {max_length} characters
{kb_section}
Rules:
- Sound like a real person sharing a genuine insight, NOT a brand
- No emojis unless they add meaning (max 1-2)
- Open with a strong hook (question, bold claim, or personal observation)
- If mentioning a product, do it naturally — no hard sell
- End with something that invites replies (question, open thought)
- Under {max_length} characters

Return ONLY a JSON object:
{{
    "text": "The actual post text",
    "hashtags": ["relevantTag"],
    "hook_type": "question|insight|story|contrarian|observation",
    "estimated_engagement": "medium"
}}
"""
    
    model = CHEAPEST_MODEL
    
    try:
        response = call_llm(
            model=model,
            system=prompt,
            messages=[{"role": "user", "content": f"Write a {style} post about {topic}."}],
            max_tokens=800,
        )
        
        text = response.get("text", "") if isinstance(response, dict) else str(response)
        result = extract_json(text)
        
        if result and "text" in result:
            # Enforce character limit
            if len(result["text"]) > max_length:
                result["text"] = result["text"][:max_length - 3] + "..."
            return result
        
        return {
            "text": text[:max_length] if text else f"Couldn't generate post about {topic}.",
            "hashtags": [],
            "hook_type": "unknown",
            "estimated_engagement": "low",
        }
    
    except Exception as e:
        logger.error(f"[THREADS] Post generation failed: {e}")
        return {
            "text": f"Error generating post: {e}",
            "hashtags": [],
            "hook_type": "error",
            "estimated_engagement": "none",
        }


# ── Helpers ─────────────────────────────────────────────────────────────

def _format_posts(posts: list[dict], include_engagement: bool = False) -> str:
    """Format Threads posts for LLM consumption."""
    if not posts:
        return "(no posts)"
    
    lines = []
    for i, post in enumerate(posts, 1):
        text = post.get("text", "(no text)")
        username = post.get("username", "unknown")
        timestamp = post.get("timestamp", "")
        permalink = post.get("permalink", "")
        
        line = f"[{i}] @{username} ({timestamp}):\n{text}"
        
        if permalink:
            line += f"\n  Link: {permalink}"
        
        if include_engagement:
            views = post.get("views", 0)
            likes = post.get("likes", 0) 
            replies = post.get("replies", 0)
            if views or likes or replies:
                line += f"\n  Engagement: {views} views, {likes} likes, {replies} replies"
        
        lines.append(line)
    
    return "\n\n".join(lines)


# ── Image-post convenience functions (Narrator API) ───────────────────────

def post_build_screenshot(
    page_url: str,
    post_text: str,
    full_page: bool = False,
) -> dict:
    """
    Capture a screenshot of a live build and post it to Threads.

    Called by the Narrator / executor when a build phase completes:

        post_build_screenshot(
            page_url="https://invoicer-abc.vercel.app/dashboard",
            post_text=(
                "Dashboard phase complete. Visual score 8.6/10.\\n"
                "Cortex iterated 3 times to get the spacing right.\\n"
                "Built autonomously — zero human code."
            )
        )

    Falls back to text-only post if BLOB_READ_WRITE_TOKEN is not set
    or if the screenshot fails.

    Args:
        page_url:  URL of the live (or local) page to screenshot.
        post_text: Threads post text (max 500 chars).
        full_page: Capture full scroll height instead of viewport.

    Returns:
        {"id": str, "published": bool, "image_url": str}
        or {"error": str, "fallback_published": bool}
    """
    from tools.image_publisher import capture_and_post, blob_configured
    from tools.threads_client import publish_post, ThreadsAPIError

    result = capture_and_post(page_url=page_url, post_text=post_text, full_page=full_page)

    if "error" in result:
        logger.warning(f"[NARRATOR] Image post failed ({result['error']}) — posting text-only")
        try:
            fallback = publish_post(text=post_text)
            fallback["fallback_published"] = True
            fallback["image_error"] = result["error"]
            return fallback
        except ThreadsAPIError as e:
            return {"error": str(e), "fallback_published": False}

    logger.info(f"[NARRATOR] Screenshot post published: {result.get('id')}")
    return result


def post_score_chart(
    domain: str,
    post_text: str | None = None,
) -> dict:
    """
    Pull this domain's accepted output scores from memory, generate a trend
    chart, and publish it to Threads.

    Called periodically by the Narrator to show Brain's improving quality:

        post_score_chart("productized-services")

    If matplotlib is not installed or scores are unavailable, returns an
    error dict (no exception raised — Narrator can decide whether to
    fall back to text-only).

    Args:
        domain:    Domain name (used to load scores from memory_store).
        post_text: Override post text. If None, auto-generated from scores.

    Returns:
        {"id": str, "published": bool, "image_url": str}
        or {"error": str}
    """
    from tools.image_publisher import post_with_chart, blob_configured

    # Load scores from memory store
    try:
        from memory_store import load_outputs
        outputs = load_outputs(domain)
    except Exception as e:
        return {"error": f"Could not load outputs for domain '{domain}': {e}"}

    if not outputs:
        return {"error": f"No scored outputs found for domain '{domain}'"}

    # Build parallel date/score lists from accepted outputs (score >= 6)
    dated_scores = []
    for out in outputs:
        score = out.get("score")
        ts = out.get("timestamp", "")
        if score is not None and float(score) >= 6:
            label = ts[:10] if ts else "?"
            dated_scores.append((label, float(score)))

    if not dated_scores:
        return {"error": f"No accepted outputs (score ≥ 6) for domain '{domain}'"}

    dates = [d for d, _ in dated_scores]
    scores = [s for _, s in dated_scores]
    avg = round(sum(scores) / len(scores), 1)

    if post_text is None:
        post_text = (
            f"Brain research quality improving on '{domain}'.\n"
            f"{len(scores)} accepted outputs. Average score: {avg}/10.\n"
            f"Strategy has rewritten itself based on what worked.\n"
            f"Built by Cortex — autonomous AI research loop."
        )[:500]

    title = f"{domain} — Research Quality"
    return post_with_chart(post_text=post_text, dates=dates, scores=scores, title=title)
