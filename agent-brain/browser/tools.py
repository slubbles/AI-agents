"""
Browser Tool — Claude tool_use integration for stealth browser.

Provides tool definitions and execution handlers so the researcher
agent can use the browser via Claude's tool_use protocol.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Tool definitions for Claude API
BROWSER_FETCH_TOOL = {
    "name": "browser_fetch",
    "description": (
        "Fetch a web page using a stealth browser with JavaScript rendering. "
        "Use this for sites that block regular HTTP requests, require JavaScript, "
        "or need authentication (LinkedIn, Indeed, Cloudflare-protected sites). "
        "Slower than web_fetch but handles anti-bot protections. "
        "Returns page text content, title, and success status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch",
            },
            "extract_mode": {
                "type": "string",
                "enum": ["text", "html", "structured", "links"],
                "description": (
                    "Content extraction mode. "
                    "'text' = visible text only (default, best for analysis). "
                    "'html' = raw HTML. "
                    "'structured' = JSON with title, headings, paragraphs, links. "
                    "'links' = list of all links on page."
                ),
                "default": "text",
            },
            "require_auth": {
                "type": "boolean",
                "description": "Force authentication even if domain isn't in the auto-auth list",
                "default": False,
            },
        },
        "required": ["url"],
    },
}

BROWSER_SEARCH_TOOL = {
    "name": "browser_search",
    "description": (
        "Search within a specific website using Google and fetch the results. "
        "Use for site-specific searches like finding people on LinkedIn, "
        "jobs on Indeed, or articles on paywalled sites. "
        "Returns fetched content from the search results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Short focused search query (3-6 words). Do NOT use the full research question.",
            },
            "site": {
                "type": "string",
                "description": "Domain to search within (e.g. 'linkedin.com', 'indeed.com')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to fetch (default: 3)",
                "default": 3,
            },
        },
        "required": ["query"],
    },
}

# All browser tools
BROWSER_TOOLS = [BROWSER_FETCH_TOOL, BROWSER_SEARCH_TOOL]


async def execute_browser_tool(
    tool_name: str,
    tool_input: dict,
    session=None,
) -> str:
    """Execute a browser tool call and return the result as a string.
    
    Args:
        tool_name: "browser_fetch" or "browser_search"
        tool_input: Tool input parameters from Claude
        session: BrowserSession instance (created if None)
        
    Returns:
        String result suitable for Claude tool_result
    """
    if session is None:
        from browser.session_manager import BrowserSession
        session = BrowserSession(headless=True)
        own_session = True
    else:
        own_session = False

    try:
        if tool_name == "browser_fetch":
            result = await session.fetch(
                url=tool_input["url"],
                extract_mode=tool_input.get("extract_mode", "text"),
                require_auth=tool_input.get("require_auth", False),
            )
            return _format_fetch_result(result)

        elif tool_name == "browser_search":
            results = await session.search_and_fetch(
                query=tool_input["query"],
                site=tool_input.get("site"),
                max_results=tool_input.get("max_results", 3),
            )
            return _format_search_results(results)

        else:
            return f"Unknown browser tool: {tool_name}"

    except Exception as e:
        logger.error(f"Browser tool error: {e}")
        return f"Browser tool error: {e}"

    finally:
        if own_session:
            await session.close_all()


def _format_fetch_result(result: dict) -> str:
    """Format a single fetch result for Claude."""
    if not result["success"]:
        return f"FETCH FAILED: {result.get('error', 'Unknown error')}\nURL: {result['url']}"

    lines = [
        f"URL: {result['url']}",
        f"Title: {result.get('title', 'N/A')}",
        f"Characters: {result.get('char_count', 0)}",
        "---",
    ]

    content = result.get("content", "")
    # Truncate very long content
    if len(content) > 15000:
        content = content[:15000] + "\n\n[... truncated — content exceeded 15000 chars]"

    lines.append(content)
    return "\n".join(lines)


def _format_search_results(results: list[dict]) -> str:
    """Format search results for Claude."""
    if not results:
        return "No results found."

    sections = []
    for i, result in enumerate(results, 1):
        if result["success"]:
            content = result.get("content", "")
            if len(content) > 5000:
                content = content[:5000] + "\n[... truncated]"
            sections.append(
                f"--- Result {i} ---\n"
                f"URL: {result['url']}\n"
                f"Title: {result.get('title', 'N/A')}\n"
                f"{content}"
            )
        else:
            sections.append(
                f"--- Result {i} ---\n"
                f"URL: {result['url']}\n"
                f"FAILED: {result.get('error', 'Unknown error')}"
            )

    return "\n\n".join(sections)
