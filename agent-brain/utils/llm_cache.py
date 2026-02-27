"""
LLM Response Cache — TTL-based caching for Claude API responses.

Caches API responses keyed on (model, system prompt hash, messages hash).
Identical requests within TTL return cached responses without API calls.
Saves money on repeated or similar queries.

Cache is stored on disk (JSON) for persistence across restarts.
Thread-safe via file locking.

Usage:
    from utils.llm_cache import cached_create_message
    response = cached_create_message(client, model="...", system="...", messages=[...])
"""

import hashlib
import json
import os
import time
import threading
from typing import Any, Optional

from utils.atomic_write import atomic_json_write

# Default TTL: 1 hour (3600 seconds)
DEFAULT_TTL_SECONDS = 3600

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "_llm_cache")

# In-memory index for fast lookups (populated from disk on first access)
_mem_cache: dict[str, dict] = {}
_mem_lock = threading.Lock()
_loaded = False

# Stats
_stats = {"hits": 0, "misses": 0, "evictions": 0}


def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _hash_content(*parts: str) -> str:
    """Create a stable hash from content parts."""
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="replace"))
    return h.hexdigest()[:32]


def _cache_key(model: str, system: str, messages: list, tools: Optional[list] = None) -> str:
    """Generate cache key from request parameters."""
    msg_str = json.dumps(messages, sort_keys=True, default=str)
    tools_str = json.dumps(tools, sort_keys=True, default=str) if tools else ""
    return _hash_content(model, system, msg_str, tools_str)


def _cache_path(key: str) -> str:
    """File path for a cache entry."""
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load_index():
    """Load all cache entries into memory index."""
    global _loaded
    if _loaded:
        return
    _ensure_dir()
    now = time.time()
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        key = fname[:-5]
        try:
            with open(os.path.join(CACHE_DIR, fname)) as f:
                entry = json.load(f)
            if entry.get("expires_at", 0) > now:
                _mem_cache[key] = entry
        except (json.JSONDecodeError, OSError):
            pass
    _loaded = True


def _serialize_response(response) -> dict:
    """Serialize an Anthropic API response to a cacheable dict."""
    # Extract the parts we care about from the response object
    data = {
        "id": getattr(response, "id", ""),
        "type": getattr(response, "type", "message"),
        "role": getattr(response, "role", "assistant"),
        "model": getattr(response, "model", ""),
        "stop_reason": getattr(response, "stop_reason", ""),
    }

    # Serialize content blocks
    content = []
    for block in getattr(response, "content", []):
        block_type = getattr(block, "type", "text")
        if block_type == "text":
            content.append({"type": "text", "text": getattr(block, "text", "")})
        elif block_type == "tool_use":
            content.append({
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": getattr(block, "input", {}),
            })
        else:
            content.append({"type": block_type, "data": str(block)})
    data["content"] = content

    # Usage info
    usage = getattr(response, "usage", None)
    if usage:
        data["usage"] = {
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
        }

    return data


class _CachedResponse:
    """Mimics Anthropic message response from cached data."""

    def __init__(self, data: dict):
        self.id = data.get("id", "cached")
        self.type = data.get("type", "message")
        self.role = data.get("role", "assistant")
        self.model = data.get("model", "")
        self.stop_reason = data.get("stop_reason", "end_turn")
        self.content = []
        self._cached = True

        for block in data.get("content", []):
            if block.get("type") == "text":
                self.content.append(_TextBlock(block["text"]))
            elif block.get("type") == "tool_use":
                self.content.append(_ToolUseBlock(
                    block.get("id", ""),
                    block.get("name", ""),
                    block.get("input", {}),
                ))

        usage_data = data.get("usage", {})
        self.usage = _Usage(
            usage_data.get("input_tokens", 0),
            usage_data.get("output_tokens", 0),
        )


class _TextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _ToolUseBlock:
    def __init__(self, block_id: str, name: str, tool_input: dict):
        self.type = "tool_use"
        self.id = block_id
        self.name = name
        self.input = tool_input


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


def get(key: str) -> Optional[Any]:
    """Get a cached response. Returns None on miss."""
    with _mem_lock:
        _load_index()
        entry = _mem_cache.get(key)
        if entry is None:
            _stats["misses"] += 1
            return None
        if entry.get("expires_at", 0) <= time.time():
            # Expired
            _mem_cache.pop(key, None)
            try:
                os.remove(_cache_path(key))
            except OSError:
                pass
            _stats["evictions"] += 1
            _stats["misses"] += 1
            return None
        _stats["hits"] += 1
        return _CachedResponse(entry["response"])


def put(key: str, response, ttl: int = DEFAULT_TTL_SECONDS):
    """Cache a response with TTL."""
    _ensure_dir()
    entry = {
        "response": _serialize_response(response),
        "created_at": time.time(),
        "expires_at": time.time() + ttl,
    }
    with _mem_lock:
        _mem_cache[key] = entry
    try:
        atomic_json_write(_cache_path(key), entry)
    except Exception:
        pass  # Cache write failure is non-fatal


def invalidate(key: str):
    """Remove a specific cache entry."""
    with _mem_lock:
        _mem_cache.pop(key, None)
    try:
        os.remove(_cache_path(key))
    except OSError:
        pass


def clear():
    """Clear entire cache."""
    global _loaded
    with _mem_lock:
        _mem_cache.clear()
        _loaded = False
    _ensure_dir()
    for fname in os.listdir(CACHE_DIR):
        if fname.endswith(".json"):
            try:
                os.remove(os.path.join(CACHE_DIR, fname))
            except OSError:
                pass


def get_stats() -> dict:
    """Return cache hit/miss statistics."""
    with _mem_lock:
        _load_index()
        now = time.time()
        active = sum(1 for e in _mem_cache.values() if e.get("expires_at", 0) > now)
    total = _stats["hits"] + _stats["misses"]
    hit_rate = (_stats["hits"] / total * 100) if total > 0 else 0
    return {
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "evictions": _stats["evictions"],
        "active_entries": active,
        "hit_rate_pct": round(hit_rate, 1),
    }


def cached_create_message(
    client,
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
    skip_cache: bool = False,
    max_attempts: int = 5,
    base_delay: float = 15.0,
    verbose: bool = True,
    **kwargs,
):
    """
    Drop-in replacement for create_message() with caching.

    Checks cache before making API call. Caches successful responses.
    Requests with tools (tool_use) that get tool_use responses are NOT cached
    because they are part of an ongoing conversation.

    Args:
        client: Anthropic client
        ttl: Cache TTL in seconds (default: 3600)
        skip_cache: Force bypass cache (default: False)
        max_attempts, base_delay, verbose: Forwarded to retry logic
        **kwargs: All args forwarded to client.messages.create()
    """
    from utils.retry import create_message

    model = kwargs.get("model", "")
    system = kwargs.get("system", "")
    if isinstance(system, list):
        system = json.dumps(system, sort_keys=True, default=str)
    messages = kwargs.get("messages", [])
    tools = kwargs.get("tools")

    # Generate cache key
    key = _cache_key(model, system, messages, tools)

    # Check cache (unless bypassed)
    if not skip_cache:
        cached = get(key)
        if cached is not None:
            if verbose:
                print("  [CACHE] Hit — returning cached response")
            return cached

    # Cache miss — make the real API call
    response = create_message(
        client,
        max_attempts=max_attempts,
        base_delay=base_delay,
        verbose=verbose,
        **kwargs,
    )

    # Only cache non-tool-use responses (tool_use responses are mid-conversation)
    should_cache = True
    if hasattr(response, "stop_reason") and response.stop_reason == "tool_use":
        should_cache = False

    if should_cache and not skip_cache:
        put(key, response, ttl=ttl)

    return response
