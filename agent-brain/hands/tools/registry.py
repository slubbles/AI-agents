"""
Tool Registry — Pluggable tool selection and routing for Agent Hands.

Every execution tool inherits from BaseTool and registers itself.
The planner selects tools by name; the executor calls them through the registry.

Adding a new capability = adding a new tool file + registering it here.

Includes execution metrics middleware:
- Per-tool invocation count, success rate, average duration
- Error category tracking
- Metrics exported for analytics and meta-analysis
"""

import os
import sys
import time
from abc import ABC, abstractmethod
from collections import defaultdict
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


class ToolMetrics:
    """Tracks per-tool execution metrics during a session."""

    def __init__(self):
        self._metrics: dict[str, dict] = defaultdict(lambda: {
            "invocations": 0,
            "successes": 0,
            "failures": 0,
            "total_duration_ms": 0.0,
            "errors": [],  # last N errors for analysis
        })
        self._max_errors_per_tool = 10

    def record(self, tool_name: str, success: bool, duration_ms: float, error: str = "") -> None:
        """Record a tool invocation result."""
        m = self._metrics[tool_name]
        m["invocations"] += 1
        m["total_duration_ms"] += duration_ms
        if success:
            m["successes"] += 1
        else:
            m["failures"] += 1
            if error:
                m["errors"].append(error[:200])
                # Keep only last N errors
                if len(m["errors"]) > self._max_errors_per_tool:
                    m["errors"] = m["errors"][-self._max_errors_per_tool:]

    def get_metrics(self, tool_name: str = "") -> dict:
        """Get metrics for a specific tool, or all tools if no name given."""
        if tool_name:
            m = self._metrics.get(tool_name)
            if not m:
                return {}
            return {
                **m,
                "success_rate": m["successes"] / m["invocations"] if m["invocations"] > 0 else 0,
                "avg_duration_ms": m["total_duration_ms"] / m["invocations"] if m["invocations"] > 0 else 0,
            }
        # All tools
        result = {}
        for name, m in self._metrics.items():
            result[name] = {
                **m,
                "success_rate": m["successes"] / m["invocations"] if m["invocations"] > 0 else 0,
                "avg_duration_ms": m["total_duration_ms"] / m["invocations"] if m["invocations"] > 0 else 0,
            }
        return result

    def summary(self) -> dict:
        """Get aggregate summary across all tools."""
        total_invocations = sum(m["invocations"] for m in self._metrics.values())
        total_successes = sum(m["successes"] for m in self._metrics.values())
        total_duration = sum(m["total_duration_ms"] for m in self._metrics.values())
        return {
            "total_invocations": total_invocations,
            "total_successes": total_successes,
            "total_failures": total_invocations - total_successes,
            "overall_success_rate": total_successes / total_invocations if total_invocations > 0 else 0,
            "total_duration_ms": total_duration,
            "tools_used": list(self._metrics.keys()),
        }

    def reset(self) -> None:
        """Reset all metrics (call between executions)."""
        self._metrics.clear()


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
        self.metrics = ToolMetrics()

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

    def get_execution_tools(self) -> list[dict]:
        """
        Get all tools as Claude tool_use definitions, plus synthetic control tools
        (_complete and _abort) for the executor to signal execution state.
        """
        tools = self.get_claude_tools()

        # Synthetic control tools
        tools.append({
            "name": "_complete",
            "description": (
                "Signal that execution is complete. Call this after all plan steps have been executed."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "What was accomplished"},
                    "artifacts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of created file paths",
                    },
                },
                "required": ["summary"],
            },
        })

        tools.append({
            "name": "_abort",
            "description": (
                "Abort execution when a required step has failed and cannot be recovered."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why execution cannot continue"},
                    "completed_steps": {"type": "integer", "description": "Number of steps completed"},
                },
                "required": ["reason"],
            },
        })

        tools.append({
            "name": "_consult",
            "description": (
                "Consult the senior architect (Claude) for guidance before making a decision. "
                "Use this when you face architectural choices, are unsure about implementation "
                "approach, hit an unexpected error you can't resolve, or need design feedback. "
                "The architect sees the full project context and will give a concrete answer."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Specific question for the architect. Be precise about what you need: a decision, a code pattern, an error diagnosis, etc.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Relevant context: what you've built so far, what step you're on, what options you see.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["architecture", "code_pattern", "error_diagnosis", "design", "dependency", "other"],
                        "description": "Category of consultation for routing.",
                    },
                },
                "required": ["question", "context"],
            },
        })

        return tools

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
        Records execution metrics (timing, success/failure).
        Returns ToolResult (never raises — errors captured in result).
        """
        tool = self._tools.get(tool_name)
        if not tool:
            self.metrics.record(tool_name, False, 0.0, f"Tool '{tool_name}' not found")
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found. Available: {', '.join(self.list_tools())}",
            )

        start = time.monotonic()
        result = tool.safe_execute(**kwargs)
        duration_ms = (time.monotonic() - start) * 1000

        self.metrics.record(
            tool_name,
            result.success,
            duration_ms,
            result.error if not result.success else "",
        )

        # Inject timing into metadata
        result.metadata["duration_ms"] = round(duration_ms, 1)

        return result


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
    from hands.tools.browser import BrowserTool

    registry.register(CodeTool())
    registry.register(TerminalTool())
    registry.register(GitTool())
    registry.register(HttpTool())
    registry.register(SearchTool())
    registry.register(BrowserTool())

    return registry
