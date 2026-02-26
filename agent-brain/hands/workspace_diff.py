"""
Workspace Diff Tracker — Tracks file changes during execution.

Snapshots the workspace before execution starts, then computes
the diff (created, modified, deleted files) after execution finishes.
Provides the validator and memory store with concrete change data.
"""

import hashlib
import os

from hands.constants import SKIP_DIRS as _SKIP_DIRS, MAX_WORKSPACE_FILES as _MAX_FILES


def snapshot_workspace(workspace_dir: str) -> dict[str, str]:
    """
    Take a snapshot of file modification times + sizes in the workspace.
    
    Returns dict mapping relative path to a hash of (mtime, size).
    This is lightweight — we don't read file contents.
    """
    if not workspace_dir or not os.path.isdir(workspace_dir):
        return {}
    
    snapshot = {}
    file_count = 0
    
    for root, dirs, files in os.walk(workspace_dir):
        # Skip hidden and build directories
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        
        for fname in files:
            if file_count >= _MAX_FILES:
                break
            
            filepath = os.path.join(root, fname)
            relpath = os.path.relpath(filepath, workspace_dir)
            
            try:
                stat = os.stat(filepath)
                # Use mtime + size as a change fingerprint
                snapshot[relpath] = f"{stat.st_mtime:.6f}:{stat.st_size}"
            except OSError:
                continue
            
            file_count += 1
        
        if file_count >= _MAX_FILES:
            break
    
    return snapshot


def compute_diff(
    before: dict[str, str],
    after: dict[str, str],
) -> dict:
    """
    Compute the difference between two workspace snapshots.
    
    Returns:
        {
            "created": ["path/to/new_file.py", ...],
            "modified": ["path/to/changed_file.py", ...],
            "deleted": ["path/to/removed_file.py", ...],
            "unchanged": 42,
        }
    """
    before_paths = set(before.keys())
    after_paths = set(after.keys())
    
    created = sorted(after_paths - before_paths)
    deleted = sorted(before_paths - after_paths)
    
    modified = []
    unchanged = 0
    for path in sorted(before_paths & after_paths):
        if before[path] != after[path]:
            modified.append(path)
        else:
            unchanged += 1
    
    return {
        "created": created,
        "modified": modified,
        "deleted": deleted,
        "unchanged": unchanged,
    }


def format_diff_summary(diff: dict) -> str:
    """Format a diff as a human-readable summary string."""
    parts = []
    
    if diff["created"]:
        parts.append(f"Created ({len(diff['created'])}):")
        for p in diff["created"][:20]:
            parts.append(f"  + {p}")
        if len(diff["created"]) > 20:
            parts.append(f"  ... and {len(diff['created']) - 20} more")
    
    if diff["modified"]:
        parts.append(f"Modified ({len(diff['modified'])}):")
        for p in diff["modified"][:20]:
            parts.append(f"  ~ {p}")
        if len(diff["modified"]) > 20:
            parts.append(f"  ... and {len(diff['modified']) - 20} more")
    
    if diff["deleted"]:
        parts.append(f"Deleted ({len(diff['deleted'])}):")
        for p in diff["deleted"][:10]:
            parts.append(f"  - {p}")
        if len(diff["deleted"]) > 10:
            parts.append(f"  ... and {len(diff['deleted']) - 10} more")
    
    if not parts:
        return "No file changes detected."
    
    total_changes = len(diff["created"]) + len(diff["modified"]) + len(diff["deleted"])
    parts.append(f"\nTotal: {total_changes} files changed, {diff['unchanged']} unchanged")
    
    return "\n".join(parts)
