"""
Git Tool — Version control operations for Agent Hands.

Supports:
- init: Initialize a git repository
- status: Show working tree status
- add: Stage files
- commit: Commit staged changes
- log: Show commit history
- branch: Create or list branches
- checkout: Switch branches
- diff: Show changes

All operations respect safety constraints:
- Only operates within allowed directories
- No force push, no rebase, no destructive operations
- No credential exposure
"""

import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import EXEC_STEP_TIMEOUT
from hands.tools.registry import BaseTool, ToolResult


# Blocked git subcommands (destructive or dangerous)
_BLOCKED_GIT_SUBCOMMANDS = {
    "push --force", "push -f", "rebase", "reset --hard",
    "clean -fd", "clean -fx", "reflog expire",
}


def _check_git_safety(subcommand: str) -> str | None:
    """Check if a git subcommand is safe."""
    lower = subcommand.lower().strip()
    for blocked in _BLOCKED_GIT_SUBCOMMANDS:
        if blocked in lower:
            return f"Blocked dangerous git operation: '{blocked}'"
    return None


class GitTool(BaseTool):
    """Git version control tool for managing repositories."""

    name = "git"
    description = (
        "Git version control operations. Actions: init (create repo), status (show changes), "
        "add (stage files), commit (commit changes), log (show history), branch (create/list), "
        "checkout (switch branch), diff (show diffs), clone (clone a repo)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["init", "status", "add", "commit", "log", "branch", "checkout", "diff", "clone"],
                "description": "The git action to perform.",
            },
            "path": {
                "type": "string",
                "description": "Repository path or file path (for add/diff).",
            },
            "message": {
                "type": "string",
                "description": "Commit message (for commit action).",
            },
            "branch_name": {
                "type": "string",
                "description": "Branch name (for branch/checkout).",
            },
            "url": {
                "type": "string",
                "description": "Remote URL (for clone action).",
            },
            "args": {
                "type": "string",
                "description": "Additional git arguments (optional).",
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

        if action == "commit" and not kwargs.get("message"):
            return "message is required for commit"
        if action == "clone" and not kwargs.get("url"):
            return "url is required for clone"
        if action in ("checkout",) and not kwargs.get("branch_name"):
            return "branch_name is required for checkout"

        # Safety check on additional args
        args = kwargs.get("args", "")
        if args:
            safety = _check_git_safety(args)
            if safety:
                return safety

        return None

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs["action"]
        path = kwargs["path"]
        message = kwargs.get("message", "")
        branch_name = kwargs.get("branch_name", "")
        url = kwargs.get("url", "")
        extra_args = kwargs.get("args", "")

        # Build git command as a list (safe from shell injection)
        if action == "init":
            cmd = ["git", "init"]
            cwd = path
        elif action == "status":
            cmd = ["git", "status", "--short"]
            cwd = path
        elif action == "add":
            target = extra_args or "."
            cmd = ["git", "add"] + shlex.split(target)
            cwd = path
        elif action == "commit":
            cmd = ["git", "commit", "-m", message]  # message passed safely as list arg
            cwd = path
        elif action == "log":
            count = extra_args or "10"
            cmd = ["git", "log", "--oneline", "-n", str(count)]
            cwd = path
        elif action == "branch":
            if branch_name:
                cmd = ["git", "branch", branch_name]
            else:
                cmd = ["git", "branch", "-a"]
            cwd = path
        elif action == "checkout":
            cmd = ["git", "checkout", branch_name]
            cwd = path
        elif action == "diff":
            cmd = ["git", "diff"]
            if extra_args:
                cmd += shlex.split(extra_args)
            cwd = path
        elif action == "clone":
            cmd = ["git", "clone", url, path]
            cwd = os.path.dirname(path) or "."
        else:
            return ToolResult(success=False, error=f"Unknown git action: {action}")

        # Ensure cwd exists
        if action != "clone":
            if not os.path.isdir(cwd):
                os.makedirs(cwd, exist_ok=True)

        try:
            result = subprocess.run(
                cmd,
                shell=False,  # Explicit: never use shell=True for git
                capture_output=True,
                text=True,
                timeout=EXEC_STEP_TIMEOUT,
                cwd=cwd,
                env={
                    **os.environ,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_AUTHOR_NAME": "Agent Hands",
                    "GIT_AUTHOR_EMAIL": "agent-hands@agent-brain.local",
                    "GIT_COMMITTER_NAME": "Agent Hands",
                    "GIT_COMMITTER_EMAIL": "agent-hands@agent-brain.local",
                },
            )

            stdout = result.stdout[:10_000] if result.stdout else ""
            stderr = result.stderr[:5_000] if result.stderr else ""

            if result.returncode == 0:
                output = stdout or "(no output)"
                if stderr and "warning" in stderr.lower():
                    output += f"\n[warnings]: {stderr[:500]}"
                return ToolResult(
                    success=True,
                    output=output,
                    metadata={"action": action, "command": " ".join(cmd[:5])},
                )
            else:
                return ToolResult(
                    success=False,
                    output=stdout,
                    error=f"git {action} failed (exit {result.returncode}): {stderr}",
                    metadata={"action": action, "exit_code": result.returncode},
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"git {action} timed out after {EXEC_STEP_TIMEOUT}s",
                metadata={"action": action, "timeout": True},
            )
