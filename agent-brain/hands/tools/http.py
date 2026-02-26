"""
HTTP Tool — Make HTTP requests for Agent Hands.

Supports:
- GET: Fetch a URL (APIs, documentation, etc.)
- POST: Submit data to an API endpoint
- HEAD: Check if a URL exists / get headers

Used for:
- Testing APIs the agent builds
- Fetching documentation or examples
- Verifying deployed services
- Downloading files or data

Safety constraints:
- No requests to internal/private IPs (10.x, 192.168.x, 127.x, etc.)
- Timeout enforced
- Response body capped at 50KB
- No file:// or other dangerous schemes
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import EXEC_STEP_TIMEOUT
from hands.tools.registry import BaseTool, ToolResult


# Block internal/private network ranges
_BLOCKED_HOSTS = re.compile(
    r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|0\.0\.0\.0|localhost|::1|\[::1\])"
)

# Block dangerous schemes
_ALLOWED_SCHEMES = {"http", "https"}

# Max response body size (50KB)
_MAX_RESPONSE_SIZE = 50_000


def _check_url_safety(url: str) -> str | None:
    """Validate URL for safety."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return f"Invalid URL: {url}"

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"Blocked scheme: {parsed.scheme}. Only http/https allowed."

    host = parsed.hostname or ""
    if _BLOCKED_HOSTS.match(host):
        return f"Blocked internal/private host: {host}"

    return None


class HttpTool(BaseTool):
    """HTTP request tool for testing APIs, fetching docs, and verifying services."""

    name = "http"
    description = (
        "Make HTTP requests. Actions: get (fetch URL), post (submit data), head (check headers). "
        "Use for testing APIs, fetching documentation, verifying deployed services, "
        "or downloading data files. Returns status code, headers, and body."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "post", "head"],
                "description": "HTTP method to use.",
            },
            "url": {
                "type": "string",
                "description": "The URL to request.",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs.",
            },
            "body": {
                "type": "string",
                "description": "Request body (for POST). JSON string or form data.",
            },
            "content_type": {
                "type": "string",
                "description": "Content-Type header (default: application/json for POST).",
            },
        },
        "required": ["action", "url"],
    }

    def validate_params(self, **kwargs) -> str | None:
        action = kwargs.get("action", "")
        url = kwargs.get("url", "")

        if not action:
            return "action is required"
        if not url:
            return "url is required"

        return _check_url_safety(url)

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs["action"]
        url = kwargs["url"]
        headers = kwargs.get("headers", {})
        body = kwargs.get("body", "")
        content_type = kwargs.get("content_type", "")

        method = action.upper()

        # Build request
        req_headers = dict(headers) if headers else {}
        req_headers.setdefault("User-Agent", "AgentHands/1.0")

        data = None
        if method == "POST" and body:
            if isinstance(body, dict):
                data = json.dumps(body).encode("utf-8")
                req_headers.setdefault("Content-Type", content_type or "application/json")
            else:
                data = body.encode("utf-8")
                req_headers.setdefault("Content-Type", content_type or "application/json")

        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers=req_headers,
                method=method,
            )

            timeout = min(EXEC_STEP_TIMEOUT, 30)  # Cap at 30s for HTTP

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                resp_headers = dict(resp.headers)

                # Read body (capped)
                if method == "HEAD":
                    body_text = ""
                else:
                    raw = resp.read(_MAX_RESPONSE_SIZE + 1)
                    truncated = len(raw) > _MAX_RESPONSE_SIZE
                    body_text = raw[:_MAX_RESPONSE_SIZE].decode("utf-8", errors="replace")
                    if truncated:
                        body_text += f"\n... (truncated at {_MAX_RESPONSE_SIZE} bytes)"

                # Build output
                output_parts = [
                    f"HTTP {status}",
                    f"Content-Type: {resp_headers.get('Content-Type', 'unknown')}",
                    f"Content-Length: {resp_headers.get('Content-Length', 'unknown')}",
                ]

                if body_text:
                    output_parts.append(f"\n{body_text}")

                return ToolResult(
                    success=True,
                    output="\n".join(output_parts),
                    metadata={
                        "status_code": status,
                        "content_type": resp_headers.get("Content-Type", ""),
                        "action": action,
                        "url": url[:200],
                    },
                )

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read(_MAX_RESPONSE_SIZE).decode("utf-8", errors="replace")
            except Exception:
                pass

            return ToolResult(
                success=False,
                output=error_body[:2000],
                error=f"HTTP {e.code}: {e.reason}",
                metadata={"status_code": e.code, "action": action, "url": url[:200]},
            )

        except urllib.error.URLError as e:
            return ToolResult(
                success=False,
                error=f"URL error: {str(e.reason)}",
                metadata={"action": action, "url": url[:200]},
            )

        except TimeoutError:
            return ToolResult(
                success=False,
                error=f"Request timed out after {timeout}s",
                metadata={"action": action, "url": url[:200], "timeout": True},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"HTTP error: {type(e).__name__}: {str(e)}",
                metadata={"action": action, "url": url[:200]},
            )
