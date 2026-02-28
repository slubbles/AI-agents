"""
Web Search Tool
Provides real web search via DuckDuckGo — free, no API key needed.
"""

import time
import random

from ddgs import DDGS


def web_search(query: str, max_results: int = 5, max_retries: int = 3) -> list[dict]:
    """
    Search the web and return results with automatic retry on transient failures.
    
    DuckDuckGo rate-limits and occasionally returns 5xx errors. Retrying with
    backoff prevents a single transient failure from wasting an entire run.
    Rate-limited globally to prevent rapid-fire abuse across runs.
    
    Returns:
        List of {title, url, snippet} dicts
    """
    # Global rate limiting
    try:
        from utils.rate_limiter import wait_for_slot
        if not wait_for_slot("search", timeout=30):
            return [{"title": "Rate limited", "url": "", "snippet": "Global search rate limit reached. Try again shortly.", "error": True}]
    except ImportError:
        pass

    last_error = None
    for attempt in range(max_retries):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results, timeout=10))
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ]
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Retry on rate limits, server errors, timeouts
            retryable = any(kw in error_str for kw in [
                "rate", "429", "500", "503", "timeout", "timed out",
                "overloaded", "service unavailable", "connection",
            ])
            if retryable and attempt < max_retries - 1:
                delay = 3 * (2 ** attempt) + random.uniform(0, 2)
                print(f"  [SEARCH] Retry {attempt + 1}/{max_retries} after {delay:.0f}s: {e}")
                time.sleep(delay)
                continue
            break
    return [{"title": "Search failed", "url": "", "snippet": str(last_error), "error": True}]


# Claude tool definition for tool_use
SEARCH_TOOL_DEFINITION = {
    "name": "web_search",
    "description": "Search the web for current information. Returns titles, URLs, and snippets. Use SHORT, FOCUSED queries (3-6 words work best). Do NOT dump the entire research question into the query — decompose it into targeted sub-queries instead.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Short focused search query (3-6 words ideal). BAD: 'startup complaints hiring freelance Next.js React developers'. GOOD: 'hiring freelance developers complaints'. Add source hints like 'reddit' or 'survey' to target specific content types.",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}
