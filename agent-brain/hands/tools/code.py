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
- Automatic backup before destructive operations (edit/overwrite/delete)
"""

import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import EXEC_MAX_FILE_SIZE, EXEC_ALLOWED_DIRS
from hands.tools.registry import BaseTool, ToolResult


# Directories that MUST NEVER be written to regardless of config
_SYSTEM_DIRS = {
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/dev",
    "/proc", "/sys", "/var/run", "/var/lock",
}

# Backup directory name (within workspace)
_BACKUP_DIR_NAME = ".agent-backups"
# Max backups to keep per workspace (prevent disk fill)
_MAX_BACKUPS = 200
# Track all backups made during the current session for rollback
_session_backups: list[dict] = []


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


def _backup_file(filepath: str) -> str | None:
    """
    Create a backup of a file before a destructive operation.
    Returns the backup path, or None if backup failed/not needed.
    """
    if not os.path.exists(filepath):
        return None

    try:
        # Find a suitable backup directory
        # Use the file's parent directory as the base
        parent = os.path.dirname(os.path.abspath(filepath))
        backup_dir = os.path.join(parent, _BACKUP_DIR_NAME)
        os.makedirs(backup_dir, exist_ok=True)

        # Create a timestamped backup name
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        basename = os.path.basename(filepath)
        backup_name = f"{ts}_{basename}"
        backup_path = os.path.join(backup_dir, backup_name)

        # Enforce backup limit — prune oldest if over limit
        existing = sorted(os.listdir(backup_dir))
        if len(existing) >= _MAX_BACKUPS:
            for old in existing[:len(existing) - _MAX_BACKUPS + 1]:
                try:
                    os.remove(os.path.join(backup_dir, old))
                except OSError:
                    pass

        shutil.copy2(filepath, backup_path)

        # Record for session rollback
        _session_backups.append({
            "original": os.path.abspath(filepath),
            "backup": backup_path,
            "timestamp": ts,
            "action": "backup",
        })

        return backup_path
    except OSError:
        return None  # Backup is best-effort, don't block the operation


def rollback_session() -> list[dict]:
    """
    Rollback all file changes made during the current session.
    Restores all backed-up files to their original locations.

    Returns list of rollback results.
    """
    results = []
    for entry in reversed(_session_backups):
        original = entry["original"]
        backup = entry["backup"]
        try:
            if os.path.exists(backup):
                shutil.copy2(backup, original)
                results.append({"file": original, "status": "restored"})
            else:
                results.append({"file": original, "status": "backup_missing"})
        except OSError as e:
            results.append({"file": original, "status": f"error: {e}"})
    _session_backups.clear()
    return results


def get_session_backups() -> list[dict]:
    """Get list of all backups made during the current session."""
    return list(_session_backups)


def clear_session_backups() -> None:
    """Clear the session backup tracker (call after successful execution)."""
    _session_backups.clear()


class CodeTool(BaseTool):
    """File I/O tool — write, read, edit, append, delete, list files."""

    name = "code"
    description = (
        "Read, write, and edit code files. Actions: write (create/overwrite file), "
        "read (get file contents), edit (replace a string in file), "
        "insert_at_line (insert content at a specific line number), "
        "append (add to end of file), delete (remove file), list_dir (list directory)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["write", "read", "edit", "insert_at_line", "append", "delete", "list_dir"],
                "description": "The file action to perform.",
            },
            "path": {
                "type": "string",
                "description": "File or directory path (absolute or relative to workspace).",
            },
            "content": {
                "type": "string",
                "description": "File content (for write/append/insert_at_line) or new string (for edit).",
            },
            "old_string": {
                "type": "string",
                "description": "String to replace (only for edit action).",
            },
            "line_number": {
                "type": "integer",
                "description": "Line number to insert at (1-based, for insert_at_line action).",
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

        if action == "insert_at_line":
            if "content" not in kwargs:
                return "content is required for insert_at_line action"
            if "line_number" not in kwargs:
                return "line_number is required for insert_at_line action"

        if action == "edit":
            if "old_string" not in kwargs:
                return "old_string is required for edit action"
            if "content" not in kwargs:
                return "content (new_string) is required for edit action"

        # Safety checks for write operations
        if action in ("write", "append", "edit", "insert_at_line", "delete"):
            error = _is_safe_path(path)
            if error:
                return error

        # Size check for writes
        if action in ("write", "append", "insert_at_line"):
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
        elif action == "insert_at_line":
            return self._insert_at_line(path, kwargs["line_number"], kwargs["content"])
        elif action == "append":
            return self._append(path, kwargs["content"])
        elif action == "delete":
            return self._delete(path)
        elif action == "list_dir":
            return self._list_dir(path)
        else:
            return ToolResult(success=False, error=f"Unknown action: {action}")

    def _write(self, path: str, content: str) -> ToolResult:
        """Create or overwrite a file. Backs up existing files before overwrite."""
        # Backup if overwriting an existing file
        backup_path = None
        if os.path.exists(path):
            backup_path = _backup_file(path)

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        size = len(content.encode("utf-8"))

        metadata = {"bytes": size, "action": "write"}
        if backup_path:
            metadata["backup"] = backup_path

        return ToolResult(
            success=True,
            output=f"Wrote {size} bytes to {path}" + (f" (backup: {backup_path})" if backup_path else ""),
            artifacts=[path],
            metadata=metadata,
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
        """Replace a specific string in a file. Backs up the file first."""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"File not found: {path}")

        # Backup before editing
        _backup_file(path)

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

    def _insert_at_line(self, path: str, line_number: int, content: str) -> ToolResult:
        """Insert content at a specific line number (1-based)."""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"File not found: {path}")

        with open(path) as f:
            lines = f.readlines()

        # Clamp line_number to valid range
        line_number = max(1, min(line_number, len(lines) + 1))

        # Insert the content (add newline if missing)
        insert_content = content if content.endswith("\n") else content + "\n"
        lines.insert(line_number - 1, insert_content)

        with open(path, "w") as f:
            f.writelines(lines)

        return ToolResult(
            success=True,
            output=f"Inserted {len(content)} chars at line {line_number} of {path}",
            artifacts=[path],
            metadata={"action": "insert_at_line", "line": line_number},
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
        """Delete a file. Backs up the file first."""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"File not found: {path}")
        if os.path.isdir(path):
            return ToolResult(success=False, error=f"Cannot delete directory: {path}. Use terminal for that.")

        # Backup before deleting
        backup_path = _backup_file(path)

        os.remove(path)
        return ToolResult(
            success=True,
            output=f"Deleted {path}" + (f" (backup: {backup_path})" if backup_path else ""),
            metadata={"action": "delete", "backup": backup_path},
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
