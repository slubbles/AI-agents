"""
Search Tool — Code and text search for Agent Hands.

Supports:
- grep: Search for patterns in files (regex or literal)
- find: Find files matching name/extension patterns
- count_lines: Count lines in files/directories

Used for:
- Understanding existing codebases before editing
- Finding patterns across multiple files
- Verifying code changes took effect
- Discovering project structure
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import EXEC_STEP_TIMEOUT
from hands.tools.registry import BaseTool, ToolResult


class SearchTool(BaseTool):
    """Code and text search tool for discovering and understanding code."""

    name = "search"
    description = (
        "Search through code and files. Actions: grep (search text/regex in files), "
        "find (find files by name/pattern), count_lines (count lines of code). "
        "Use for understanding codebases, finding patterns, and verifying changes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["grep", "find", "count_lines"],
                "description": "Search action to perform.",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search in.",
            },
            "pattern": {
                "type": "string",
                "description": "Search pattern (regex for grep, glob for find).",
            },
            "include": {
                "type": "string",
                "description": "File pattern to include (e.g. '*.py', '*.ts'). For grep.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 50).",
            },
            "recursive": {
                "type": "boolean",
                "description": "Search recursively (default: true).",
            },
        },
        "required": ["action", "path"],
    }

    def validate_params(self, **kwargs) -> str | None:
        action = kwargs.get("action", "")
        path = kwargs.get("path", "")

        if not action:
            return "action is required"
        if not path:
            return "path is required"
        if not os.path.exists(path):
            return f"Path does not exist: {path}"
        if action == "grep" and not kwargs.get("pattern"):
            return "pattern is required for grep"

        return None

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs["action"]
        path = kwargs["path"]

        if action == "grep":
            return self._grep(
                path=path,
                pattern=kwargs.get("pattern", ""),
                include=kwargs.get("include", ""),
                max_results=kwargs.get("max_results", 50),
                recursive=kwargs.get("recursive", True),
            )
        elif action == "find":
            return self._find(
                path=path,
                pattern=kwargs.get("pattern", ""),
                max_results=kwargs.get("max_results", 100),
            )
        elif action == "count_lines":
            return self._count_lines(
                path=path,
                include=kwargs.get("include", ""),
            )
        else:
            return ToolResult(success=False, error=f"Unknown search action: {action}")

    def _grep(self, path: str, pattern: str, include: str = "",
              max_results: int = 50, recursive: bool = True) -> ToolResult:
        """Search for a pattern in files using grep."""
        cmd_parts = ["grep", "-n", "--color=never"]

        if recursive:
            cmd_parts.append("-r")

        # Try as regex first, fall back to fixed string
        try:
            re.compile(pattern)
            cmd_parts.extend(["-E", pattern])
        except re.error:
            cmd_parts.extend(["-F", pattern])

        if include:
            cmd_parts.extend(["--include", include])

        cmd_parts.append(path)

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=EXEC_STEP_TIMEOUT,
            )

            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

            if len(lines) > max_results:
                shown = lines[:max_results]
                output = "\n".join(shown) + f"\n... ({len(lines) - max_results} more matches)"
            else:
                output = "\n".join(lines) if lines else "(no matches)"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "action": "grep",
                    "matches": len(lines),
                    "pattern": pattern[:100],
                },
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Search timed out after {EXEC_STEP_TIMEOUT}s",
            )

    def _find(self, path: str, pattern: str = "", max_results: int = 100) -> ToolResult:
        """Find files matching a pattern."""
        cmd_parts = ["find", path, "-maxdepth", "5"]

        if pattern:
            # Support glob patterns
            cmd_parts.extend(["-name", pattern])

        # Exclude common noise directories
        cmd_parts.extend([
            "-not", "-path", "*/node_modules/*",
            "-not", "-path", "*/.git/*",
            "-not", "-path", "*/__pycache__/*",
            "-not", "-path", "*/.next/*",
        ])

        cmd_parts.extend(["-type", "f"])

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=EXEC_STEP_TIMEOUT,
            )

            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            # Filter empty lines
            lines = [l for l in lines if l.strip()]

            if len(lines) > max_results:
                shown = lines[:max_results]
                output = "\n".join(shown) + f"\n... ({len(lines) - max_results} more files)"
            else:
                output = "\n".join(lines) if lines else "(no files found)"

            return ToolResult(
                success=True,
                output=output,
                metadata={"action": "find", "count": len(lines)},
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Find timed out after {EXEC_STEP_TIMEOUT}s",
            )

    def _count_lines(self, path: str, include: str = "") -> ToolResult:
        """Count lines of code in files."""
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    count = sum(1 for _ in f)
                return ToolResult(
                    success=True,
                    output=f"{path}: {count} lines",
                    metadata={"action": "count_lines", "lines": count},
                )
            except Exception as e:
                return ToolResult(success=False, error=f"Cannot read {path}: {e}")

        # Directory — use find + wc
        find_cmd = f"find {path} -maxdepth 5 -type f"
        if include:
            find_cmd += f" -name '{include}'"
        find_cmd += " -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/__pycache__/*'"
        cmd = f"{find_cmd} -exec wc -l {{}} + 2>/dev/null | tail -1"

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=EXEC_STEP_TIMEOUT,
            )

            output = result.stdout.strip()
            if output:
                return ToolResult(
                    success=True,
                    output=output,
                    metadata={"action": "count_lines"},
                )
            else:
                return ToolResult(
                    success=True,
                    output="(no matching files)",
                    metadata={"action": "count_lines", "lines": 0},
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Count timed out after {EXEC_STEP_TIMEOUT}s",
            )
