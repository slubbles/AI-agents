"""
MCP Protocol — JSON-RPC 2.0 message encoding/decoding.

MCP uses JSON-RPC 2.0 over stdio (or SSE). This module handles:
  - Building request/notification messages
  - Parsing response messages
  - The MCP-specific methods: initialize, tools/list, tools/call, etc.
"""

import json
from typing import Any

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 building blocks
# ---------------------------------------------------------------------------

_request_id_counter = 0


def _next_id() -> int:
    global _request_id_counter
    _request_id_counter += 1
    return _request_id_counter


def reset_id_counter() -> None:
    """Reset the request ID counter (useful for tests)."""
    global _request_id_counter
    _request_id_counter = 0


def build_request(method: str, params: dict | None = None, req_id: int | None = None) -> bytes:
    """
    Build a JSON-RPC 2.0 request message as bytes (for writing to stdin).

    Returns newline-terminated JSON bytes.
    """
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": req_id if req_id is not None else _next_id(),
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    return json.dumps(msg).encode("utf-8") + b"\n"


def build_notification(method: str, params: dict | None = None) -> bytes:
    """
    Build a JSON-RPC 2.0 notification (no id, no response expected).
    """
    msg: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        msg["params"] = params
    return json.dumps(msg).encode("utf-8") + b"\n"


def parse_response(data: bytes | str) -> dict:
    """
    Parse a JSON-RPC 2.0 response from the server.

    Returns the parsed dict. Raises ValueError on invalid JSON-RPC.
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8")

    # Strip any trailing whitespace/newlines
    data = data.strip()
    if not data:
        raise ValueError("Empty response")

    try:
        msg = json.loads(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(msg, dict):
        raise ValueError(f"Expected JSON object, got {type(msg).__name__}")

    if msg.get("jsonrpc") != "2.0":
        raise ValueError(f"Expected jsonrpc 2.0, got {msg.get('jsonrpc')}")

    return msg


def is_error_response(msg: dict) -> bool:
    """Check if a parsed JSON-RPC message is an error response."""
    return "error" in msg


def get_result(msg: dict) -> Any:
    """
    Extract the result from a successful JSON-RPC response.

    Raises ValueError if the response is an error.
    """
    if is_error_response(msg):
        err = msg["error"]
        code = err.get("code", "unknown")
        message = err.get("message", "Unknown error")
        raise ValueError(f"JSON-RPC error {code}: {message}")
    return msg.get("result")


# ---------------------------------------------------------------------------
# MCP-specific message builders
# ---------------------------------------------------------------------------

MCP_PROTOCOL_VERSION = "2024-11-05"
"""MCP protocol version we support."""


def build_initialize(
    client_name: str = "agent-brain",
    client_version: str = "1.0.0",
) -> bytes:
    """Build an MCP initialize request."""
    return build_request("initialize", {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {
            "roots": {"listChanged": False},
        },
        "clientInfo": {
            "name": client_name,
            "version": client_version,
        },
    })


def build_initialized_notification() -> bytes:
    """Build the initialized notification (sent after initialize response)."""
    return build_notification("notifications/initialized")


def build_tools_list() -> bytes:
    """Build a tools/list request."""
    return build_request("tools/list")


def build_tools_call(tool_name: str, arguments: dict | None = None) -> bytes:
    """Build a tools/call request."""
    params: dict[str, Any] = {"name": tool_name}
    if arguments:
        params["arguments"] = arguments
    return build_request("tools/call", params)


def build_resources_list() -> bytes:
    """Build a resources/list request."""
    return build_request("resources/list")


def build_prompts_list() -> bytes:
    """Build a prompts/list request."""
    return build_request("prompts/list")


def build_ping() -> bytes:
    """Build a ping request (health check)."""
    return build_request("ping")


# ---------------------------------------------------------------------------
# Response parsers for MCP-specific structures
# ---------------------------------------------------------------------------

def parse_tool_definition(raw: dict) -> dict:
    """
    Parse an MCP tool definition into Claude tool_use format.

    MCP tool format:
        {"name": "...", "description": "...", "inputSchema": {...}}

    Claude tool_use format:
        {"name": "...", "description": "...", "input_schema": {...}}

    The only difference is the key name (camelCase → snake_case).
    """
    return {
        "name": raw.get("name", "unknown"),
        "description": raw.get("description", ""),
        "input_schema": raw.get("inputSchema", {"type": "object", "properties": {}}),
    }


def parse_tools_list_result(result: dict | list) -> list[dict]:
    """
    Parse the result of a tools/list response.

    The result may be:
      - A list of tool defs directly
      - A dict with a "tools" key containing the list
    """
    if isinstance(result, list):
        return [parse_tool_definition(t) for t in result]
    if isinstance(result, dict) and "tools" in result:
        return [parse_tool_definition(t) for t in result["tools"]]
    return []


def parse_tool_call_result(result: dict | list) -> str:
    """
    Parse the result of a tools/call response into a text string.

    MCP tool results contain a "content" array of content blocks:
        {"content": [{"type": "text", "text": "..."}, ...], "isError": false}
    """
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        is_error = result.get("isError", False)
        content_blocks = result.get("content", [])
        texts = []
        for block in content_blocks:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    texts.append(f"[image: {block.get('mimeType', 'unknown')}]")
                elif block.get("type") == "resource":
                    uri = block.get("resource", {}).get("uri", "unknown")
                    texts.append(f"[resource: {uri}]")
            elif isinstance(block, str):
                texts.append(block)

        text = "\n".join(texts) if texts else str(result)
        if is_error:
            text = f"[MCP Error] {text}"
        return text

    return str(result)
