"""
Tool Registry — Pluggable tool selection and routing for Agent Hands.

Every execution tool inherits from BaseTool and registers itself.
The planner selects tools by name; the executor calls them through the registry.

Adding a new capability = adding a new tool file + registering it here.
"""

import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import EXEC_SANDBOX_MODE


class ToolResult:
    """Standardized result from any tool execution."""

    def __init__(
        self,
        success: bool,
        output: str = "",
        error: str = "",
        artifacts: list[str] | None = None,
        metadata: dict | None = None,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.artifacts = artifacts or []  # file paths, URLs, etc. produced
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output[:5000],  # cap output in serialized form
            "error": self.error[:2000],
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return f"<ToolResult {status}: {self.output[:80]}>"


class BaseTool(ABC):
    """
    Base class for all execution tools.

    Subclasses must implement:
        name: str           — unique identifier (e.g. "code", "terminal")
        description: str    — what this tool does (shown to planner)
        execute(**kwargs)   — perform the action and return ToolResult
    """

    name: str = ""
    description: str = ""

    # Claude tool_use schema — subclasses override this
    # Format matches Anthropic's tool definition spec
    input_schema: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self):
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define a 'name'")

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool action. Must return a ToolResult."""
        ...

    def validate_params(self, **kwargs) -> str | None:
        """
        Optional parameter validation before execution.
        Return an error string if invalid, None if OK.
        """
        return None

    def safe_execute(self, **kwargs) -> ToolResult:
        """
        Execute with validation and error handling.
        This is the main entry point — always call this, not execute() directly.
        """
        # Validate parameters
        error = self.validate_params(**kwargs)
        if error:
            return ToolResult(success=False, error=f"Validation failed: {error}")

        # Execute with catch-all
        try:
            return self.execute(**kwargs)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"{self.__class__.__name__} error: {type(e).__name__}: {str(e)}",
            )

    def to_claude_tool(self) -> dict:
        """Convert to Claude tool_use definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    """
    Central registry for all execution tools.

    Usage:
        registry = ToolRegistry()
        registry.register(CodeTool())
        registry.register(TerminalTool())

        # Get a tool by name
        tool = registry.get("code")
        result = tool.safe_execute(action="write", path="...", content="...")

        # Get all tools as Claude tool definitions (for planner/executor)
        tools = registry.get_claude_tools()
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises if name conflicts."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def get_required(self, name: str) -> BaseTool:
        """Get a tool by name. Raises if not found."""
        tool = self._tools.get(name)
        if not tool:
            available = ", ".join(sorted(self._tools.keys()))
            raise KeyError(f"Tool '{name}' not found. Available: {available}")
        return tool

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return sorted(self._tools.keys())

    def get_claude_tools(self) -> list[dict]:
        """Get all tools as Claude tool_use definitions."""
        return [tool.to_claude_tool() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> str:
        """Get a human-readable list of tools and their descriptions."""
        lines = []
        for name in sorted(self._tools.keys()):
            tool = self._tools[name]
            lines.append(f"  - {name}: {tool.description}")
        return "\n".join(lines)

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name with given parameters.
        Returns ToolResult (never raises — errors captured in result).
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found. Available: {', '.join(self.list_tools())}",
            )
        return tool.safe_execute(**kwargs)


def create_default_registry() -> ToolRegistry:
    """
    Create a registry with all available tools.
    Import and register each tool here.
    """
    registry = ToolRegistry()

    # Import tools (lazy — only when registry is created)
    from hands.tools.code import CodeTool
    from hands.tools.terminal import TerminalTool
    from hands.tools.git import GitTool
    from hands.tools.http import HttpTool
    from hands.tools.search import SearchTool

    registry.register(CodeTool())
    registry.register(TerminalTool())
    registry.register(GitTool())
    registry.register(HttpTool())
    registry.register(SearchTool())

    return registry
