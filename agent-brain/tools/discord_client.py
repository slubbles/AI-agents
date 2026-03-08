"""Discord REST client for Cortex content factory.

Pure stdlib client for:
1. Reading recent channel messages
2. Posting messages into configured agent channels
3. Verifying channel access without adding a websocket bot runtime
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_MAX_MESSAGE_LEN = 2000


class DiscordAPIError(Exception):
    """Raised when a Discord API call fails."""


def get_configured_channels() -> dict[str, str]:
    """Return the configured content-factory channel ids."""
    return {
        "research": os.environ.get("DISCORD_RESEARCH_CHANNEL_ID", ""),
        "scripts": os.environ.get("DISCORD_SCRIPTS_CHANNEL_ID", ""),
        "thumbnails": os.environ.get("DISCORD_THUMBNAILS_CHANNEL_ID", ""),
    }


def is_configured() -> bool:
    """Return True when the bot token and all channel ids are configured."""
    channels = get_configured_channels()
    return bool(DISCORD_BOT_TOKEN and all(channels.values()))


def _discord_request(
    endpoint: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    timeout: int = 30,
) -> dict | list:
    """Send a request to the Discord REST API."""
    if not DISCORD_BOT_TOKEN:
        raise DiscordAPIError("Discord bot token not configured. Set DISCORD_BOT_TOKEN in .env")

    url = f"{DISCORD_API_BASE}{endpoint}"
    body = None
    req = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bot {DISCORD_BOT_TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise DiscordAPIError(f"HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise DiscordAPIError(f"Connection error: {exc.reason}") from exc
    except Exception as exc:
        raise DiscordAPIError(f"Request failed: {exc}") from exc

    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DiscordAPIError(f"Invalid JSON response: {raw[:200]}") from exc


def get_channel(channel_id: str) -> dict:
    """Fetch channel metadata."""
    return _discord_request(f"/channels/{channel_id}")


def get_channel_messages(channel_id: str, limit: int = 20) -> list[dict]:
    """Fetch recent channel messages, newest first."""
    query = urllib.parse.urlencode({"limit": max(1, min(limit, 100))})
    data = _discord_request(f"/channels/{channel_id}/messages?{query}")
    return data if isinstance(data, list) else []


def _split_message(content: str) -> list[str]:
    """Split long messages into Discord-safe chunks."""
    if not content:
        return ["(empty message)"]

    chunks = []
    remaining = content
    while len(remaining) > DISCORD_MAX_MESSAGE_LEN:
        split_at = remaining.rfind("\n", 0, DISCORD_MAX_MESSAGE_LEN)
        if split_at == -1:
            split_at = DISCORD_MAX_MESSAGE_LEN
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    chunks.append(remaining)
    return chunks


def send_message(channel_id: str, content: str) -> list[dict]:
    """Send a plain text message to a channel, splitting if needed."""
    results = []
    for chunk in _split_message(content):
        payload = {
            "content": chunk,
            "allowed_mentions": {"parse": []},
        }
        results.append(
            _discord_request(
                f"/channels/{channel_id}/messages",
                method="POST",
                payload=payload,
            )
        )
    return results
