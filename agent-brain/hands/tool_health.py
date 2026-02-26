"""
Tool Health Monitor — Tracks tool reliability and suggests alternatives.

When a tool fails repeatedly during an execution, the monitor:
1. Tracks failure rates per tool per session
2. Marks tools as degraded when failure rate exceeds threshold
3. Suggests alternative approaches (e.g., "use code tool to write a script
   instead of chaining terminal commands")

This prevents the executor from wasting retries on a consistently failing tool.
"""

from collections import defaultdict
from typing import Optional


# If a tool fails more than this fraction of attempts, mark as degraded
DEGRADATION_THRESHOLD = 0.7
# Minimum attempts before evaluating degradation
MIN_ATTEMPTS_FOR_DEGRADATION = 3

# Alternative suggestions when a tool is degraded
_TOOL_ALTERNATIVES = {
    "terminal": [
        "Use the 'code' tool to write a shell script, then execute it with 'terminal'",
        "Break the command into smaller individual commands",
        "Use 'code' tool to manually create files instead of using terminal commands",
    ],
    "code": [
        "Use 'terminal' with echo/cat to create files if code tool has path issues",
        "Try a different file path or check permissions",
        "Write smaller files to avoid size limits",
    ],
    "git": [
        "Use 'terminal' to run git commands directly",
        "Skip git operations and focus on code creation",
    ],
    "http": [
        "Use 'terminal' with curl/wget instead",
        "Skip network operations if not critical",
    ],
    "search": [
        "Use 'terminal' with find/grep commands",
        "Use 'code' tool's list_dir action",
    ],
}


class ToolHealthMonitor:
    """
    Monitors tool health during execution and suggests alternatives.

    Usage:
        monitor = ToolHealthMonitor()
        
        # Record tool results
        monitor.record("terminal", success=True)
        monitor.record("terminal", success=False, error="timeout")
        
        # Check health before execution
        if monitor.is_degraded("terminal"):
            alternatives = monitor.get_alternatives("terminal")
    """

    def __init__(self):
        self._stats: dict[str, dict] = defaultdict(lambda: {
            "attempts": 0,
            "failures": 0,
            "errors": [],
        })

    def record(self, tool_name: str, success: bool, error: str = "") -> None:
        """Record a tool execution result."""
        stats = self._stats[tool_name]
        stats["attempts"] += 1
        if not success:
            stats["failures"] += 1
            if error:
                stats["errors"].append(error[:200])
                if len(stats["errors"]) > 5:
                    stats["errors"] = stats["errors"][-5:]

    def is_degraded(self, tool_name: str) -> bool:
        """Check if a tool is performing poorly."""
        stats = self._stats.get(tool_name)
        if not stats:
            return False
        if stats["attempts"] < MIN_ATTEMPTS_FOR_DEGRADATION:
            return False
        failure_rate = stats["failures"] / stats["attempts"]
        return failure_rate >= DEGRADATION_THRESHOLD

    def get_failure_rate(self, tool_name: str) -> float:
        """Get current failure rate for a tool."""
        stats = self._stats.get(tool_name)
        if not stats or stats["attempts"] == 0:
            return 0.0
        return stats["failures"] / stats["attempts"]

    def get_alternatives(self, tool_name: str) -> list[str]:
        """Get alternative suggestions for a degraded tool."""
        return _TOOL_ALTERNATIVES.get(tool_name, [
            f"Try a different approach that doesn't rely on '{tool_name}'",
        ])

    def get_health_report(self) -> dict:
        """Get health report for all monitored tools."""
        report = {}
        for name, stats in self._stats.items():
            attempts = stats["attempts"]
            failures = stats["failures"]
            rate = failures / attempts if attempts > 0 else 0
            report[name] = {
                "attempts": attempts,
                "failures": failures,
                "failure_rate": round(rate, 2),
                "degraded": self.is_degraded(name),
                "recent_errors": stats["errors"][-3:],
            }
        return report

    def get_degraded_tools(self) -> list[str]:
        """Get list of all currently degraded tools."""
        return [name for name in self._stats if self.is_degraded(name)]

    def get_health_context(self) -> str:
        """
        Get health context string to inject into executor prompt.
        Only returns context if there are degraded tools.
        """
        degraded = self.get_degraded_tools()
        if not degraded:
            return ""

        parts = ["\n⚠ TOOL HEALTH WARNINGS:"]
        for tool in degraded:
            stats = self._stats[tool]
            rate = stats["failures"] / stats["attempts"]
            parts.append(f"  - '{tool}' is failing ({rate:.0%} failure rate)")
            alts = self.get_alternatives(tool)
            if alts:
                parts.append(f"    Alternatives: {alts[0]}")

        parts.append("  Consider using alternative approaches for degraded tools.")
        return "\n".join(parts)

    def reset(self) -> None:
        """Reset all health tracking."""
        self._stats.clear()
