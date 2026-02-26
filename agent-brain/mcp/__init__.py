"""
MCP (Model Context Protocol) Gateway for Agent Brain.

Manages MCP servers running in Docker containers and bridges their tools
into Agent Brain's tool registries (both research and execution layers).

Architecture:
    protocol.py       — JSON-RPC 2.0 message encoding/decoding for MCP
    docker_manager.py — Container lifecycle (start, stop, health check)
    gateway.py        — Multi-server gateway with tool discovery + routing
    context_router.py — Context-efficient tool filtering (avoid flooding Claude)
    tool_bridge.py    — Bridge MCP tools into Agent Brain registries
"""

MCP_AVAILABLE = True
"""Set to False if core dependencies are missing."""

__all__ = [
    "MCP_AVAILABLE",
]
