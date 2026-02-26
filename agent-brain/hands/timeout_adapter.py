"""
Adaptive Timeout — Learns optimal timeouts per tool from execution history.

Instead of a single global EXEC_STEP_TIMEOUT for all tools, this adapter
suggests per-tool timeouts based on observed execution durations:

- Terminal commands for 'npm install' need ~90s, but 'mkdir' needs 2s.
- Code writes are near-instant; HTTP requests vary by endpoint.

Approach:
1. Tracks actual execution durations from exec_analytics
2. Suggests timeout = max(min_timeout, avg_duration * multiplier)
3. Falls back to the global default for unknown tools

Used by: executor.py (passes suggested timeout to registry.execute)
"""

import json
import os
from typing import Optional

# Sensible defaults (seconds) — conservative baselines per tool
_DEFAULT_TIMEOUTS: dict[str, int] = {
    "terminal": 120,
    "code": 30,
    "git": 60,
    "http": 30,
    "search": 45,
}

# Commands that are known to be slow
_SLOW_COMMAND_PATTERNS: list[tuple[str, int]] = [
    ("npm install", 180),
    ("yarn install", 180),
    ("pip install", 120),
    ("apt install", 180),
    ("apt-get install", 180),
    ("docker build", 300),
    ("docker pull", 180),
    ("git clone", 120),
    ("npm run build", 180),
    ("npx create-", 180),
    ("cargo build", 300),
    ("go build", 120),
    ("mvn ", 300),
    ("gradle ", 300),
    ("make", 180),
    ("pytest", 120),
    ("npm test", 120),
]

MIN_TIMEOUT = 10  # Never go below 10s
MAX_TIMEOUT = 600  # Never exceed 10 minutes
MULTIPLIER = 2.5   # timeout = avg_duration * multiplier (safety margin)


class TimeoutAdapter:
    """
    Suggests per-tool timeouts based on historical execution durations.
    
    Usage:
        adapter = TimeoutAdapter(global_default=120)
        adapter.load_history(exec_analytics_data)
        timeout = adapter.suggest(tool="terminal", params={"command": "npm install"})
    """

    def __init__(self, global_default: int = 120):
        self.global_default = global_default
        # tool -> list of durations (seconds)
        self._history: dict[str, list[float]] = {}

    def load_history(self, exec_outputs: list[dict]) -> None:
        """
        Load historical execution durations from stored exec outputs.
        
        Args:
            exec_outputs: List of execution output dicts (from exec_memory).
                          Each should have execution_report.step_results with
                          timing metadata.
        """
        for output in exec_outputs:
            report = output.get("execution_report", {})
            for step in report.get("step_results", []):
                tool = step.get("tool", "")
                if not tool:
                    continue
                # Duration comes from ToolMetrics (injected by registry.execute)
                duration_ms = step.get("duration_ms", 0)
                if duration_ms <= 0:
                    # Check metadata
                    meta = step.get("metadata", {})
                    duration_ms = meta.get("duration_ms", 0)
                if duration_ms > 0:
                    self._history.setdefault(tool, []).append(duration_ms / 1000.0)

    def record(self, tool: str, duration_s: float) -> None:
        """Record a single execution duration (called by executor after each step)."""
        if duration_s > 0:
            self._history.setdefault(tool, []).append(duration_s)

    def suggest(self, tool: str, params: Optional[dict] = None) -> int:
        """
        Suggest a timeout in seconds for a tool execution.
        
        Priority:
        1. Known slow command patterns (for terminal)
        2. Historical average * multiplier
        3. Tool-specific default
        4. Global default
        """
        params = params or {}

        # Check for known slow commands (terminal tool)
        if tool == "terminal":
            command = params.get("command", "")
            for pattern, timeout in _SLOW_COMMAND_PATTERNS:
                if pattern in command:
                    return min(timeout, MAX_TIMEOUT)

        # Use historical data if available
        durations = self._history.get(tool, [])
        if len(durations) >= 3:
            avg = sum(durations) / len(durations)
            p95 = sorted(durations)[int(len(durations) * 0.95)]
            # Use max of (avg * multiplier, p95 * 1.5) for safety
            suggested = max(avg * MULTIPLIER, p95 * 1.5)
            return max(MIN_TIMEOUT, min(int(suggested), MAX_TIMEOUT))

        # Tool-specific default
        if tool in _DEFAULT_TIMEOUTS:
            return _DEFAULT_TIMEOUTS[tool]

        # Global fallback
        return self.global_default

    def stats(self) -> dict:
        """Return timeout statistics for all tools."""
        result = {}
        for tool, durations in self._history.items():
            if durations:
                result[tool] = {
                    "samples": len(durations),
                    "avg_s": round(sum(durations) / len(durations), 2),
                    "max_s": round(max(durations), 2),
                    "suggested_timeout": self.suggest(tool),
                }
        return result
