"""
Web Search Tool
Provides real web search via DuckDuckGo — free, no API key needed.
"""

from ddgs import DDGS


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web and return results.
    
    Returns:
        List of {title, url, snippet} dicts
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
    except Exception as e:
        return [{"title": "Search failed", "url": "", "snippet": str(e)}]


# Claude tool definition for tool_use
SEARCH_TOOL_DEFINITION = {
    "name": "web_search",
    "description": "Search the web for current information. Use this for any question about recent events, current state of things, or data you don't have in training. Returns titles, URLs, and snippets from search results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific and include relevant keywords, dates, or context.",
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
