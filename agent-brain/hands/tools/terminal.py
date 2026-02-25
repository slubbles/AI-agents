"""
Terminal Tool — Shell command execution for Agent Hands.

Runs commands via subprocess with safety constraints:
- EXEC_ALLOWED_COMMANDS whitelist
- EXEC_BLOCKED_PATTERNS blacklist
- EXEC_STEP_TIMEOUT per-command timeout
- EXEC_SANDBOX_MODE restricts dangerous operations

Never runs as root. Never allows privilege escalation.
"""

import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import (
    EXEC_ALLOWED_COMMANDS,
    EXEC_BLOCKED_PATTERNS,
    EXEC_SANDBOX_MODE,
    EXEC_STEP_TIMEOUT,
)
from hands.tools.registry import BaseTool, ToolResult


def _check_command_safety(command: str) -> str | None:
    """
    Validate a command against safety rules.
    Returns error string if unsafe, None if OK.
    """
    # Check for blocked patterns (always enforced, sandbox or not)
    for pattern in EXEC_BLOCKED_PATTERNS:
        if pattern in command:
            return f"Blocked dangerous pattern: '{pattern}'"

    # Sandbox mode: check command whitelist
    if EXEC_SANDBOX_MODE:
        # Extract the base command (first word, handling pipes)
        parts = command.split("|")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Handle command chaining with && and ;
            subparts = re.split(r"[;&]+", part)
            for subpart in subparts:
                subpart = subpart.strip()
                if not subpart:
                    continue
                # Handle env vars, cd, etc.
                words = subpart.split()
                # Skip env var assignments at the start
                cmd_word = None
                for word in words:
                    if "=" in word and not word.startswith("-"):
                        continue  # env var like FOO=bar
                    cmd_word = word
                    break

                if cmd_word and cmd_word not in EXEC_ALLOWED_COMMANDS:
                    # Check if it's a path to an allowed command
                    basename = os.path.basename(cmd_word)
                    if basename not in EXEC_ALLOWED_COMMANDS:
                        return f"Command '{cmd_word}' not in allowed list. Allowed: {', '.join(sorted(EXEC_ALLOWED_COMMANDS))}"

    return None


class TerminalTool(BaseTool):
    """Shell command execution tool with safety sandboxing."""

    name = "terminal"
    description = (
        "Run shell commands. Use for: running tests (pytest, npm test), "
        "installing packages (pip install, npm install), building projects, "
        "checking lint, running scripts, git operations. "
        "Commands are sandboxed — only whitelisted commands allowed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command (optional).",
            },
            "timeout": {
                "type": "integer",
                "description": f"Timeout in seconds (default: {EXEC_STEP_TIMEOUT}).",
            },
        },
        "required": ["command"],
    }

    def validate_params(self, **kwargs) -> str | None:
        command = kwargs.get("command", "")
        if not command:
            return "command is required"

        cwd = kwargs.get("cwd")
        if cwd and not os.path.isdir(cwd):
            return f"Working directory does not exist: {cwd}"

        return _check_command_safety(command)

    def execute(self, **kwargs) -> ToolResult:
        command = kwargs["command"]
        cwd = kwargs.get("cwd", None)
        timeout = kwargs.get("timeout", EXEC_STEP_TIMEOUT)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            stdout = result.stdout[:10_000] if result.stdout else ""
            stderr = result.stderr[:5_000] if result.stderr else ""

            if result.returncode == 0:
                output = stdout
                if stderr:
                    output += f"\n[stderr]: {stderr}"
                return ToolResult(
                    success=True,
                    output=output,
                    metadata={
                        "exit_code": result.returncode,
                        "action": "run",
                        "command": command[:200],
                    },
                )
            else:
                return ToolResult(
                    success=False,
                    output=stdout,
                    error=f"Exit code {result.returncode}: {stderr}",
                    metadata={
                        "exit_code": result.returncode,
                        "action": "run",
                        "command": command[:200],
                    },
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Command timed out after {timeout}s: {command[:200]}",
                metadata={"action": "run", "timeout": True},
            )
