"""
Code Tool — File I/O for Agent Hands.

Supports:
- write: Create or overwrite a file with content
- read: Read a file's contents
- edit: Replace a specific string in a file (surgical edit)
- append: Append content to an existing file
- delete: Remove a file
- list_dir: List directory contents

All operations respect safety constraints from config:
- EXEC_MAX_FILE_SIZE caps write size
- EXEC_ALLOWED_DIRS restricts where files can be written
- Never writes to system directories
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import EXEC_MAX_FILE_SIZE, EXEC_ALLOWED_DIRS
from hands.tools.registry import BaseTool, ToolResult


# Directories that MUST NEVER be written to regardless of config
_SYSTEM_DIRS = {
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/dev",
    "/proc", "/sys", "/var/run", "/var/lock",
}


def _is_safe_path(path: str) -> str | None:
    """
    Check if a file path is safe to operate on.
    Returns error string if unsafe, None if OK.
    """
    resolved = os.path.realpath(path)

    # Block system directories
    for sys_dir in _SYSTEM_DIRS:
        if resolved.startswith(sys_dir + "/") or resolved == sys_dir:
            return f"Cannot write to system directory: {sys_dir}"

    # Check allowed dirs whitelist (if configured)
    if EXEC_ALLOWED_DIRS:
        allowed = False
        for allowed_dir in EXEC_ALLOWED_DIRS:
            resolved_allowed = os.path.realpath(allowed_dir)
            if resolved.startswith(resolved_allowed + "/") or resolved == resolved_allowed:
                allowed = True
                break
        if not allowed:
            return f"Path '{path}' not in allowed directories: {EXEC_ALLOWED_DIRS}"

    return None


class CodeTool(BaseTool):
    """File I/O tool — write, read, edit, append, delete, list files."""

    name = "code"
    description = (
        "Read, write, and edit code files. Actions: write (create/overwrite file), "
        "read (get file contents), edit (replace a string in file), "
        "append (add to end of file), delete (remove file), list_dir (list directory)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["write", "read", "edit", "append", "delete", "list_dir"],
                "description": "The file action to perform.",
            },
            "path": {
                "type": "string",
                "description": "File or directory path (absolute or relative to workspace).",
            },
            "content": {
                "type": "string",
                "description": "File content (for write/append) or new string (for edit).",
            },
            "old_string": {
                "type": "string",
                "description": "String to replace (only for edit action).",
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

        if action in ("write", "append") and "content" not in kwargs:
            return f"content is required for {action} action"

        if action == "edit":
            if "old_string" not in kwargs:
                return "old_string is required for edit action"
            if "content" not in kwargs:
                return "content (new_string) is required for edit action"

        # Safety checks for write operations
        if action in ("write", "append", "edit", "delete"):
            error = _is_safe_path(path)
            if error:
                return error

        # Size check for writes
        if action in ("write", "append"):
            content = kwargs.get("content", "")
            if len(content.encode("utf-8")) > EXEC_MAX_FILE_SIZE:
                return f"Content exceeds max file size ({EXEC_MAX_FILE_SIZE} bytes)"

        return None

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs["action"]
        path = kwargs["path"]

        if action == "write":
            return self._write(path, kwargs["content"])
        elif action == "read":
            return self._read(path)
        elif action == "edit":
            return self._edit(path, kwargs["old_string"], kwargs["content"])
        elif action == "append":
            return self._append(path, kwargs["content"])
        elif action == "delete":
            return self._delete(path)
        elif action == "list_dir":
            return self._list_dir(path)
        else:
            return ToolResult(success=False, error=f"Unknown action: {action}")

    def _write(self, path: str, content: str) -> ToolResult:
        """Create or overwrite a file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        size = len(content.encode("utf-8"))
        return ToolResult(
            success=True,
            output=f"Wrote {size} bytes to {path}",
            artifacts=[path],
            metadata={"bytes": size, "action": "write"},
        )

    def _read(self, path: str) -> ToolResult:
        """Read a file's contents."""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"File not found: {path}")
        if os.path.isdir(path):
            return self._list_dir(path)
        with open(path) as f:
            content = f.read()
        # Cap read output
        if len(content) > EXEC_MAX_FILE_SIZE:
            content = content[:EXEC_MAX_FILE_SIZE] + f"\n... (truncated at {EXEC_MAX_FILE_SIZE} bytes)"
        return ToolResult(
            success=True,
            output=content,
            metadata={"bytes": len(content), "action": "read"},
        )

    def _edit(self, path: str, old_string: str, new_string: str) -> ToolResult:
        """Replace a specific string in a file."""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"File not found: {path}")
        with open(path) as f:
            content = f.read()

        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                success=False,
                error=f"String not found in {path}. Cannot edit.",
            )
        if count > 1:
            return ToolResult(
                success=False,
                error=f"String found {count} times in {path}. Need unique match for safe edit.",
            )

        new_content = content.replace(old_string, new_string, 1)
        with open(path, "w") as f:
            f.write(new_content)

        return ToolResult(
            success=True,
            output=f"Edited {path}: replaced 1 occurrence",
            artifacts=[path],
            metadata={"action": "edit"},
        )

    def _append(self, path: str, content: str) -> ToolResult:
        """Append content to a file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as f:
            f.write(content)
        return ToolResult(
            success=True,
            output=f"Appended {len(content)} bytes to {path}",
            artifacts=[path],
            metadata={"bytes": len(content), "action": "append"},
        )

    def _delete(self, path: str) -> ToolResult:
        """Delete a file."""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"File not found: {path}")
        if os.path.isdir(path):
            return ToolResult(success=False, error=f"Cannot delete directory: {path}. Use terminal for that.")
        os.remove(path)
        return ToolResult(
            success=True,
            output=f"Deleted {path}",
            metadata={"action": "delete"},
        )

    def _list_dir(self, path: str) -> ToolResult:
        """List directory contents."""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"Directory not found: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, error=f"Not a directory: {path}")

        entries = sorted(os.listdir(path))
        lines = []
        for entry in entries[:200]:  # cap at 200 entries
            full = os.path.join(path, entry)
            suffix = "/" if os.path.isdir(full) else ""
            lines.append(f"  {entry}{suffix}")

        output = f"{path}/ ({len(entries)} items):\n" + "\n".join(lines)
        if len(entries) > 200:
            output += f"\n  ... and {len(entries) - 200} more"

        return ToolResult(
            success=True,
            output=output,
            metadata={"count": len(entries), "action": "list_dir"},
        )
