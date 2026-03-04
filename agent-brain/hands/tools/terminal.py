"""
Terminal Tool — Shell command execution for Agent Hands.

Runs commands via subprocess with safety constraints:
- EXEC_ALLOWED_COMMANDS whitelist
- EXEC_BLOCKED_PATTERNS blacklist
- EXEC_STEP_TIMEOUT per-command timeout
- EXEC_SANDBOX_MODE restricts dangerous operations
- Environment variable sanitization (API keys stripped)
- Working directory validation against EXEC_ALLOWED_DIRS

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
    EXEC_ALLOWED_DIRS,
    EXEC_BLOCKED_PATTERNS,
    EXEC_SANDBOX_MODE,
    EXEC_STEP_TIMEOUT,
)
from hands.tools.registry import BaseTool, ToolResult


# Environment variables that are safe to pass to subprocesses.
# Everything else (especially API keys/tokens/secrets) is stripped.
_SAFE_ENV_VARS = {
    # Core system
    "PATH", "HOME", "USER", "SHELL", "LANG", "TERM", "HOSTNAME",
    "PWD", "OLDPWD", "SHLVL", "LOGNAME", "TZ",
    # Language runtimes
    "NODE_PATH", "NODE_ENV", "NODE_OPTIONS", "NPM_CONFIG_PREFIX",
    "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "VIRTUAL_ENV",
    "PIP_CACHE_DIR", "CONDA_PREFIX",
    # Build tools
    "CC", "CXX", "CFLAGS", "CXXFLAGS", "LDFLAGS",
    "CMAKE_PREFIX_PATH", "PKG_CONFIG_PATH",
    # Display / editor
    "DISPLAY", "EDITOR", "VISUAL", "PAGER", "LESS",
    # Git (non-secret)
    "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
    # Docker / container
    "DOCKER_HOST", "CONTAINER_ID",
    # CI markers (non-secret)
    "CI", "GITHUB_ACTIONS", "GITHUB_WORKSPACE",
    # Temp
    "TMPDIR", "TEMP", "TMP",
    # XDG
    "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
    # Deploy — intentionally passed for automated deployment
    "VERCEL_TOKEN",             # Vercel CLI auth (npx vercel --yes --prod)
    "VERCEL_ORG_ID",            # Vercel project linking
    "VERCEL_PROJECT_ID",        # Vercel project linking
}

# Patterns in env var NAMES that indicate secrets (case-insensitive)
_SECRET_NAME_PATTERNS = {
    "KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
    "AUTH", "API_KEY", "PRIVATE", "PASSWD",
}


def _build_safe_env() -> dict[str, str]:
    """
    Build a sanitized environment dict for subprocess execution.
    Strips API keys, tokens, secrets — keeps only safe system vars.
    """
    safe = {}
    for key, value in os.environ.items():
        # Always include explicitly safe vars
        if key in _SAFE_ENV_VARS:
            safe[key] = value
            continue
        # Block anything with a secret-looking name
        upper_key = key.upper()
        if any(pattern in upper_key for pattern in _SECRET_NAME_PATTERNS):
            continue
        # Allow lowercase/non-sensitive looking vars (e.g., color settings)
        # but block anything we're not sure about by default
        # Only pass through if it looks like a build/system var
        if key.startswith(("npm_", "NVM_", "DENO_", "BUN_", "CARGO_",
                          "GOPATH", "GOROOT", "RUSTUP_", "JAVA_HOME",
                          "ANDROID_", "CHROME_", "FIREFOX_")):
            safe[key] = value
    # Always force these
    safe["PYTHONDONTWRITEBYTECODE"] = "1"
    return safe


def _check_command_safety(command: str) -> str | None:
    """
    Validate a command against safety rules.
    Returns error string if unsafe, None if OK.
    """
    # Check for blocked patterns (always enforced, sandbox or not)
    for pattern in EXEC_BLOCKED_PATTERNS:
        if pattern in command:
            return f"Blocked dangerous pattern: '{pattern}'"

    # Block attempts to read environment secrets
    secret_probes = [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "API_KEY",
        "SECRET_KEY", "ACCESS_TOKEN", "PRIVATE_KEY",
    ]
    for probe in secret_probes:
        # Catch both $VAR and ${VAR} and printenv VAR
        if probe in command:
            return f"Blocked: command references secret '{probe}'"

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


def _validate_cwd(cwd: str) -> str | None:
    """
    Validate that a working directory is within allowed directories.
    Returns error string if invalid, None if OK.
    """
    if not cwd:
        return None
    resolved = os.path.realpath(cwd)
    if EXEC_ALLOWED_DIRS:
        for allowed_dir in EXEC_ALLOWED_DIRS:
            resolved_allowed = os.path.realpath(allowed_dir)
            if resolved.startswith(resolved_allowed + "/") or resolved == resolved_allowed:
                return None
        return f"Working directory '{cwd}' not in allowed directories"
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

        # Validate cwd against allowed directories
        cwd_error = _validate_cwd(cwd)
        if cwd_error:
            return cwd_error

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
                env=_build_safe_env(),
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
