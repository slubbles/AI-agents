"""
Threads API Client — Meta Graph API integration for Cortex.

Enables Cortex to:
- Publish posts (text, images, polls)
- Search Threads for pain points and market signals
- Read replies and conversations
- Track engagement analytics (impressions, clicks, replies)
- Reply to threads for engagement

Uses pure stdlib urllib — no external dependencies (same pattern as
telegram_bot.py and alerts.py).

Setup:
    THREADS_ACCESS_TOKEN=... in .env (long-lived OAuth 2.0 token)
    THREADS_USER_ID=... in .env (your Threads user ID)

Rate limits (Meta):
    250 API calls per user per hour
    1,000 posts per 24 hours (publishing)
    We track and respect these limits.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "")

# Meta Graph API base URL
API_BASE = "https://graph.threads.net/v1.0"

# Rate limiting
_call_timestamps: list[float] = []
MAX_CALLS_PER_HOUR = 250
PUBLISH_COOLDOWN_SECONDS = 90  # minimum gap between publishes to avoid spam


def is_configured() -> bool:
    """Check if Threads API credentials are available."""
    return bool(THREADS_ACCESS_TOKEN and THREADS_USER_ID)


# ── HTTP Layer ──────────────────────────────────────────────────────────

def _rate_check() -> bool:
    """Enforce rate limit. Returns True if call is allowed."""
    now = time.time()
    hour_ago = now - 3600
    # Prune old timestamps
    _call_timestamps[:] = [t for t in _call_timestamps if t > hour_ago]
    if len(_call_timestamps) >= MAX_CALLS_PER_HOUR:
        logger.warning(f"[THREADS] Rate limit hit: {len(_call_timestamps)} calls in last hour")
        return False
    _call_timestamps.append(now)
    return True


def _api_request(
    endpoint: str,
    method: str = "GET",
    params: dict | None = None,
    data: dict | None = None,
    timeout: int = 30,
) -> dict:
    """
    Make a request to the Threads API.
    
    Args:
        endpoint: API path (e.g., "/{user_id}/threads")
        method: HTTP method
        params: URL query parameters
        data: POST body (form-encoded)
        timeout: Request timeout in seconds
    
    Returns:
        Parsed JSON response dict
    
    Raises:
        ThreadsAPIError: On API errors
    """
    if not is_configured():
        raise ThreadsAPIError("Threads API not configured. Set THREADS_ACCESS_TOKEN and THREADS_USER_ID in .env")
    
    if not _rate_check():
        raise ThreadsAPIError("Rate limit exceeded (250 calls/hour). Try again later.")
    
    # Build URL
    url = f"{API_BASE}{endpoint}"
    
    # Always include access token
    all_params = {"access_token": THREADS_ACCESS_TOKEN}
    if params:
        all_params.update(params)
    
    # Encode params into URL for GET, or send as POST body
    if method == "GET" or (method == "POST" and not data):
        query = urllib.parse.urlencode(all_params)
        url = f"{url}?{query}"
        body = None
    else:
        # For POST with data, merge token into data
        all_data = {**all_params, **(data or {})}
        body = urllib.parse.urlencode(all_data).encode("utf-8")
    
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", error_body)
            error_code = error_json.get("error", {}).get("code", e.code)
        except (json.JSONDecodeError, KeyError):
            error_msg = error_body
            error_code = e.code
        raise ThreadsAPIError(f"HTTP {error_code}: {error_msg}") from e
    except urllib.error.URLError as e:
        raise ThreadsAPIError(f"Connection error: {e.reason}") from e
    except Exception as e:
        raise ThreadsAPIError(f"Request failed: {e}") from e


import urllib.parse  # needed for urlencode


class ThreadsAPIError(Exception):
    """Raised when a Threads API call fails."""
    pass


# ── Publishing ──────────────────────────────────────────────────────────

# Track last publish time to enforce cooldown
_last_publish_time: float = 0.0


def publish_post(
    text: str,
    image_url: Optional[str] = None,
    reply_to_id: Optional[str] = None,
    link_attachment: Optional[str] = None,
) -> dict:
    """
    Publish a post to Threads.
    
    Two-step process per Meta API:
    1. Create media container (POST /{user_id}/threads)
    2. Publish the container (POST /{user_id}/threads_publish)
    
    Args:
        text: Post text (up to 500 characters)
        image_url: Optional public URL of image to attach
        reply_to_id: Optional thread ID to reply to
        link_attachment: Optional URL to attach as link preview
    
    Returns:
        {"id": "thread_id", "published": True}
    """
    global _last_publish_time
    
    # Enforce cooldown
    elapsed = time.time() - _last_publish_time
    if elapsed < PUBLISH_COOLDOWN_SECONDS and _last_publish_time > 0:
        wait = PUBLISH_COOLDOWN_SECONDS - elapsed
        raise ThreadsAPIError(
            f"Publishing cooldown: wait {wait:.0f}s (prevents spam detection)"
        )
    
    if len(text) > 500:
        raise ThreadsAPIError(f"Post text too long ({len(text)} chars, max 500)")
    
    # Step 1: Create media container
    container_params = {
        "media_type": "TEXT",
        "text": text,
    }
    
    if image_url:
        container_params["media_type"] = "IMAGE"
        container_params["image_url"] = image_url
    
    if reply_to_id:
        container_params["reply_to_id"] = reply_to_id
    
    if link_attachment:
        container_params["link_attachment"] = link_attachment
    
    container = _api_request(
        f"/{THREADS_USER_ID}/threads",
        method="POST",
        params=container_params,
    )
    
    container_id = container.get("id")
    if not container_id:
        raise ThreadsAPIError(f"Failed to create container: {container}")
    
    # Brief wait for container processing (Meta recommendation)
    time.sleep(2)
    
    # Step 2: Publish
    result = _api_request(
        f"/{THREADS_USER_ID}/threads_publish",
        method="POST",
        params={"creation_id": container_id},
    )
    
    _last_publish_time = time.time()
    
    thread_id = result.get("id")
    logger.info(f"[THREADS] Published post {thread_id}: {text[:50]}...")
    
    return {"id": thread_id, "published": True, "text": text}


def reply_to_thread(thread_id: str, text: str) -> dict:
    """Reply to an existing thread. Wrapper around publish_post."""
    return publish_post(text=text, reply_to_id=thread_id)


# ── Reading ─────────────────────────────────────────────────────────────

def get_user_threads(
    limit: int = 25,
    fields: str = "id,text,timestamp,permalink,is_reply,reply_audience",
) -> list[dict]:
    """
    Get the authenticated user's own threads.
    
    Returns:
        List of thread objects
    """
    resp = _api_request(
        f"/{THREADS_USER_ID}/threads",
        params={"fields": fields, "limit": str(limit)},
    )
    return resp.get("data", [])


def get_thread(
    thread_id: str,
    fields: str = "id,text,timestamp,permalink,username,is_reply",
) -> dict:
    """Get a single thread by ID."""
    return _api_request(f"/{thread_id}", params={"fields": fields})


def get_thread_replies(
    thread_id: str,
    limit: int = 25,
    fields: str = "id,text,timestamp,username,permalink,is_reply",
) -> list[dict]:
    """
    Get replies to a thread (conversation view).
    
    Returns:
        List of reply objects
    """
    resp = _api_request(
        f"/{thread_id}/replies",
        params={"fields": fields, "limit": str(limit)},
    )
    return resp.get("data", [])


def get_conversation(
    thread_id: str,
    limit: int = 50,
    fields: str = "id,text,timestamp,username,permalink",
) -> list[dict]:
    """
    Get the full conversation thread.
    
    Returns:
        List of all posts in the conversation (root + all replies)
    """
    resp = _api_request(
        f"/{thread_id}/conversation",
        params={"fields": fields, "limit": str(limit)},
    )
    return resp.get("data", [])


# ── Search ──────────────────────────────────────────────────────────────

def search_threads(
    query: str,
    limit: int = 25,
    fields: str = "id,text,timestamp,username,permalink",
) -> list[dict]:
    """
    Search Threads for posts matching a query.
    
    Uses the Threads Search API endpoint.
    
    Args:
        query: Search query string
        limit: Max results to return
        fields: Comma-separated fields to include
    
    Returns:
        List of matching thread objects
    """
    resp = _api_request(
        "/keyword_search",
        params={
            "q": query,
            "fields": fields,
            "limit": str(limit),
        },
    )
    return resp.get("data", [])


# ── Analytics ───────────────────────────────────────────────────────────

def get_thread_insights(thread_id: str) -> dict:
    """
    Get engagement metrics for a specific thread.
    
    Returns dict with:
        views, likes, replies, reposts, quotes, shares
    """
    resp = _api_request(
        f"/{thread_id}/insights",
        params={"metric": "views,likes,replies,reposts,quotes,shares"},
    )
    
    # Parse the insights response into a flat dict
    insights = {}
    for item in resp.get("data", []):
        name = item.get("name", "")
        values = item.get("values", [{}])
        insights[name] = values[0].get("value", 0) if values else 0
    
    return insights


def get_profile_insights(
    metrics: str = "views,likes,replies,reposts,quotes,followers_count",
) -> dict:
    """
    Get profile-level analytics.
    
    Returns dict with aggregate metrics.
    """
    resp = _api_request(
        f"/{THREADS_USER_ID}/threads_insights",
        params={"metric": metrics},
    )
    
    insights = {}
    for item in resp.get("data", []):
        name = item.get("name", "")
        values = item.get("values", [{}])
        insights[name] = values[0].get("value", 0) if values else 0
    
    return insights


# ── Convenience ─────────────────────────────────────────────────────────

def get_recent_engagement(limit: int = 10) -> dict:
    """
    Quick engagement summary of recent posts.
    
    Returns:
        {
            "posts": [...],
            "total_views": int,
            "total_likes": int,
            "total_replies": int,
            "avg_engagement_rate": float,
            "top_post": {...}
        }
    """
    threads = get_user_threads(limit=limit)
    
    posts = []
    total_views = 0
    total_likes = 0
    total_replies = 0
    top_post = None
    top_engagement = 0
    
    for thread in threads:
        thread_id = thread.get("id")
        if not thread_id:
            continue
        
        try:
            insights = get_thread_insights(thread_id)
        except ThreadsAPIError:
            insights = {}
        
        views = insights.get("views", 0)
        likes = insights.get("likes", 0)
        replies = insights.get("replies", 0)
        engagement = likes + replies
        
        post_data = {
            "id": thread_id,
            "text": thread.get("text", "")[:100],
            "timestamp": thread.get("timestamp", ""),
            "views": views,
            "likes": likes,
            "replies": replies,
            "engagement_rate": (engagement / views * 100) if views > 0 else 0,
        }
        posts.append(post_data)
        
        total_views += views
        total_likes += likes
        total_replies += replies
        
        if engagement > top_engagement:
            top_engagement = engagement
            top_post = post_data
    
    total_engagement = total_likes + total_replies
    avg_rate = (total_engagement / total_views * 100) if total_views > 0 else 0
    
    return {
        "posts": posts,
        "total_views": total_views,
        "total_likes": total_likes,
        "total_replies": total_replies,
        "avg_engagement_rate": round(avg_rate, 2),
        "top_post": top_post,
    }


# ── Tool Definitions (for LLM tool_use) ────────────────────────────────

THREADS_SEARCH_TOOL = {
    "name": "threads_search",
    "description": (
        "Search Threads (Meta's social platform, 320M+ users) for posts matching a query. "
        "Returns post text, username, timestamp, and permalink. "
        "Use for finding pain points, market signals, and user language in a niche."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g., 'freelance invoicing frustrated'). Short focused queries work best.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 10, max 25)",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

THREADS_POST_TOOL = {
    "name": "threads_post",
    "description": (
        "Publish a post to Threads. Use for sharing product launches, insights, "
        "or engaging with the community. Max 500 characters. "
        "Only use when explicitly instructed to post."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Post text (max 500 chars). Write naturally, not like a bot.",
            },
            "link_attachment": {
                "type": "string",
                "description": "Optional URL to attach for link preview.",
            },
        },
        "required": ["text"],
    },
}

THREADS_INSIGHTS_TOOL = {
    "name": "threads_insights",
    "description": (
        "Get engagement analytics for the user's recent Threads posts. "
        "Returns views, likes, replies, engagement rates, and top post."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of recent posts to analyze (default 10)",
                "default": 10,
            },
        },
        "required": [],
    },
}

THREADS_SCREENSHOT_POST_TOOL = {
    "name": "threads_screenshot_post",
    "description": (
        "Take a high-quality Retina screenshot of a URL, upload it to Vercel Blob, "
        "and publish it as an image post on Threads. "
        "Use after a build phase completes to show the real product in action. "
        "Requires BLOB_READ_WRITE_TOKEN in .env."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "page_url": {
                "type": "string",
                "description": "URL to screenshot (e.g. https://your-app.vercel.app or http://localhost:3001).",
            },
            "text": {
                "type": "string",
                "description": "Threads post text (max 500 chars). Describe what was just built.",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full scroll height (true) or viewport only (false, default).",
                "default": False,
            },
        },
        "required": ["page_url", "text"],
    },
}

THREADS_CHART_POST_TOOL = {
    "name": "threads_chart_post",
    "description": (
        "Generate a score trend chart from research quality data, upload it to Vercel Blob, "
        "and post it on Threads. Use to show Brain's improving research quality over time. "
        "Requires BLOB_READ_WRITE_TOKEN in .env and matplotlib installed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Threads post text (max 500 chars). Describe what the chart shows.",
            },
            "dates": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of date/label strings for the X axis.",
            },
            "scores": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Corresponding score values (0-10) for the Y axis.",
            },
            "title": {
                "type": "string",
                "description": "Chart title (default: 'Research Quality Over Time').",
                "default": "Research Quality Over Time",
            },
        },
        "required": ["text", "dates", "scores"],
    },
}


def execute_threads_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a Threads tool call from LLM tool_use.
    
    Returns JSON string result.
    """
    try:
        if tool_name == "threads_search":
            results = search_threads(
                query=tool_input["query"],
                limit=tool_input.get("limit", 10),
            )
            return json.dumps({"results": results, "count": len(results)})
        
        elif tool_name == "threads_post":
            result = publish_post(
                text=tool_input["text"],
                link_attachment=tool_input.get("link_attachment"),
            )
            return json.dumps(result)
        
        elif tool_name == "threads_insights":
            result = get_recent_engagement(
                limit=tool_input.get("limit", 10),
            )
            return json.dumps(result)

        elif tool_name == "threads_screenshot_post":
            from tools.image_publisher import capture_and_post
            result = capture_and_post(
                page_url=tool_input["page_url"],
                post_text=tool_input["text"],
                full_page=tool_input.get("full_page", False),
            )
            return json.dumps(result)

        elif tool_name == "threads_chart_post":
            from tools.image_publisher import post_with_chart
            result = post_with_chart(
                post_text=tool_input["text"],
                dates=tool_input["dates"],
                scores=tool_input["scores"],
                title=tool_input.get("title", "Research Quality Over Time"),
            )
            return json.dumps(result)

        else:
            return json.dumps({"error": f"Unknown Threads tool: {tool_name}"})
    
    except ThreadsAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Threads tool failed: {e}"})
