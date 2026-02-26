"""
Tool Bridge — Connects MCP tools to Agent Brain's two tool systems.

Agent Brain has two separate tool dispatch mechanisms:
  1. Research tools (researcher.py) — hardcoded dispatch, flat dict definitions
  2. Execution tools (hands/tools/registry.py) — BaseTool class hierarchy

This bridge provides adapters for both:
  - McpProxyTool: BaseTool subclass for the execution registry
  - get_mcp_research_tools(): Returns tool defs + dispatch function for researcher
  - route_mcp_tool_call(): Universal dispatcher for any MCP tool call
"""

import logging
import os
import sys
from typing import Any, Callable

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp.gateway import McpGateway, get_gateway
from mcp.context_router import ContextRouter

logger = logging.getLogger("mcp.tool_bridge")


# ---------------------------------------------------------------------------
# Execution layer bridge (BaseTool subclass)
# ---------------------------------------------------------------------------

class McpProxyTool:
    """
    A proxy tool that adapts an MCP tool for the Agent Hands execution registry.

    Implements the same interface as BaseTool without inheriting from it
    (to avoid circular imports). Can be registered directly in ToolRegistry.

    Attributes match BaseTool: name, description, input_schema, execute(), etc.
    """

    def __init__(
        self,
        tool_def: dict,
        server_name: str,
        gateway: McpGateway | None = None,
    ):
        """
        Args:
            tool_def: Claude tool_use format dict (name, description, input_schema)
            server_name: Which MCP server owns this tool
            gateway: McpGateway to route calls through
        """
        self.name = tool_def["name"]
        self.description = tool_def.get("description", "")
        self.input_schema = tool_def.get("input_schema", {
            "type": "object",
            "properties": {},
            "required": [],
        })
        self._server_name = server_name
        self._gateway = gateway

    @property
    def gateway(self) -> McpGateway:
        if self._gateway is None:
            self._gateway = get_gateway()
        return self._gateway

    def execute(self, **kwargs):
        """
        Execute the MCP tool via the gateway.

        Returns a ToolResult-compatible object.
        """
        # Import here to avoid circular dependency
        from hands.tools.registry import ToolResult

        try:
            result_text = self.gateway.call_tool(self.name, kwargs)

            # Check for MCP error prefix
            is_error = result_text.startswith("[MCP Error]")

            return ToolResult(
                success=not is_error,
                output=result_text if not is_error else "",
                error=result_text if is_error else "",
                metadata={
                    "mcp_server": self._server_name,
                    "mcp_tool": self.name,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"MCP tool execution error: {e}",
                metadata={
                    "mcp_server": self._server_name,
                    "mcp_tool": self.name,
                },
            )

    def safe_execute(self, **kwargs):
        """Execute with error handling (matches BaseTool interface)."""
        error = self.validate_params(**kwargs)
        if error:
            from hands.tools.registry import ToolResult
            return ToolResult(success=False, error=f"Validation failed: {error}")
        try:
            return self.execute(**kwargs)
        except Exception as e:
            from hands.tools.registry import ToolResult
            return ToolResult(
                success=False,
                error=f"McpProxyTool error: {type(e).__name__}: {e}",
            )

    def validate_params(self, **kwargs) -> str | None:
        """Validate parameters against the input_schema. Returns error string or None."""
        required = self.input_schema.get("required", [])
        for param in required:
            if param not in kwargs:
                return f"Missing required parameter: {param}"
        return None

    def to_claude_tool(self) -> dict:
        """Convert to Claude tool_use definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ---------------------------------------------------------------------------
# Research layer bridge
# ---------------------------------------------------------------------------

def get_mcp_research_tools(
    task: str,
    domain: str = "",
    max_tools: int = 10,
    gateway: McpGateway | None = None,
) -> tuple[list[dict], Callable]:
    """
    Get MCP tool definitions and a dispatch function for the researcher.

    Returns:
        (tool_definitions, dispatch_fn)

        tool_definitions: List of Claude tool_use format dicts to add to
            the researcher's tool list.

        dispatch_fn: Callable(tool_name, arguments) -> str
            The researcher calls this to execute MCP tools.
            Returns the tool result as a string.

    Usage in researcher.py:
        mcp_tools, mcp_dispatch = get_mcp_research_tools(question, domain)
        tools = [SEARCH_TOOL_DEFINITION, ...] + mcp_tools

        # In tool dispatch loop:
        if tool_name in mcp_tool_names:
            result = mcp_dispatch(tool_name, tool_input)
    """
    gw = gateway or get_gateway()

    if not gw.is_started:
        return [], lambda name, args: "[MCP Error] Gateway not started"

    # Use context router to select relevant tools
    router = ContextRouter(gw)
    relevant_tools = router.select_tools(
        task=task,
        domain=domain,
        max_tools=max_tools,
    )

    if not relevant_tools:
        return [], lambda name, args: "[MCP Error] No relevant tools found"

    def dispatch(tool_name: str, arguments: dict | None = None) -> str:
        """Dispatch a tool call to the correct MCP server."""
        result = gw.call_tool(tool_name, arguments)
        # Record usage for future routing
        router.record_usage(
            tool_name=tool_name,
            task=task,
            success=not result.startswith("[MCP Error]"),
            domain=domain,
        )
        return result

    return relevant_tools, dispatch


def get_mcp_tool_names(tools: list[dict]) -> set[str]:
    """Extract tool names from a list of tool definitions."""
    return {t["name"] for t in tools}


# ---------------------------------------------------------------------------
# Universal dispatcher
# ---------------------------------------------------------------------------

def route_mcp_tool_call(
    tool_name: str,
    arguments: dict | None = None,
    gateway: McpGateway | None = None,
) -> str:
    """
    Route any MCP tool call through the gateway.

    This is a convenience function for one-off calls without
    the full research/execution pipeline.
    """
    gw = gateway or get_gateway()
    if not gw.is_started:
        return "[MCP Error] Gateway not started"
    return gw.call_tool(tool_name, arguments)


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

def register_mcp_tools_in_registry(
    registry: Any,
    gateway: McpGateway | None = None,
    categories: list[str] | None = None,
) -> int:
    """
    Register all MCP tools as McpProxyTool instances in a ToolRegistry.

    This allows the execution layer (Agent Hands) to call MCP tools
    through the standard registry.execute() interface.

    Args:
        registry: ToolRegistry instance
        gateway: McpGateway instance
        categories: If provided, only register tools from these categories

    Returns:
        Number of tools registered
    """
    gw = gateway or get_gateway()
    if not gw.is_started:
        logger.warning("Cannot register MCP tools: gateway not started")
        return 0

    count = 0
    for server_name, container in gw._containers.items():
        if not container.is_running:
            continue

        # Category filter
        if categories:
            server_cats = set(container.config.categories)
            if not server_cats & set(categories):
                continue

        for tool_def in container.tools:
            # Prefix to avoid collision with native tools
            prefixed_def = {
                "name": f"mcp_{server_name}__{tool_def['name']}",
                "description": f"[MCP:{server_name}] {tool_def.get('description', '')}",
                "input_schema": tool_def.get("input_schema", {
                    "type": "object", "properties": {}, "required": []
                }),
            }

            proxy = McpProxyTool(prefixed_def, server_name, gw)

            try:
                registry.register(proxy)
                count += 1
            except ValueError:
                # Tool name already registered — skip
                logger.debug(f"Skipping duplicate tool: {prefixed_def['name']}")

    logger.info(f"Registered {count} MCP tools in execution registry")
    return count
