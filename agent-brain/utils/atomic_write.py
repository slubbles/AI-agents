"""
Atomic file operations for Agent Brain.

Prevents data corruption from mid-write crashes (OOM kill, Ctrl+C, power failure)
by writing to a temp file first, then using os.replace() which is atomic on POSIX.
"""

import json
import os
import tempfile


def atomic_json_write(filepath: str, data, indent: int = 2) -> None:
    """
    Write JSON data to file atomically.
    
    Writes to a temp file in the same directory, then uses os.replace()
    to atomically swap it into place. This guarantees that the target file
    is either the old version or the new version — never a partial write.
    
    Args:
        filepath: Target file path
        data: JSON-serializable data
        indent: JSON indent level (default 2)
    """
    dir_name = os.path.dirname(filepath) or "."
    os.makedirs(dir_name, exist_ok=True)
    
    # Write to temp file in the same directory (required for os.replace atomicity)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent)
        os.replace(tmp_path, filepath)
    except BaseException:
        # Clean up temp file on any error (including KeyboardInterrupt)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
