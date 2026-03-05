"""
Execution Checkpoint — Save and resume execution progress.

When an execution is interrupted (timeout, crash, API error), the checkpoint
allows resuming from the last successful step instead of starting over.

Checkpoints are stored per-domain in the exec_memory directory.
Only one active checkpoint per domain at a time.

Checkpoint lifecycle:
1. Created when execution starts (WAL: intent recorded before work)
2. WAL entry written before each step (what we're about to do)
3. Updated after each successful step (WAL cleared)
4. Deleted on execution completion (success or final failure)
5. Loaded on execution start to detect resumable work
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from utils.atomic_write import atomic_json_write


class ExecutionCheckpoint:
    """
    Manages execution progress persistence for crash recovery.

    Includes WAL (Write-Ahead Log) style persistence: before starting
    a step, we record intent to disk. If the process crashes mid-step,
    recovery can see what was in-flight.

    Usage:
        cp = ExecutionCheckpoint("/path/to/checkpoints/")
        
        # Start new execution
        cp.create("nextjs-react", goal="Build REST API", plan=plan_dict)
        
        # Before each step (WAL)
        cp.write_ahead(domain, step_index=2, step_info={"tool": "write_file", ...})
        
        # After each step
        cp.update_step(domain, step_result)
        
        # Check for resumable work
        state = cp.load("nextjs-react")
        if state and state.get("wal_pending"):
            # Last step may have partially completed
            ...
        
        # Execution complete
        cp.clear("nextjs-react")
    """

    def __init__(self, checkpoint_dir: str):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

    def _path(self, domain: str) -> str:
        """Get checkpoint file path for a domain."""
        return os.path.join(self.checkpoint_dir, f"{domain}_checkpoint.json")

    def create(self, domain: str, goal: str, plan: dict) -> None:
        """Create a new checkpoint for an execution."""
        checkpoint = {
            "domain": domain,
            "goal": goal,
            "plan": plan,
            "completed_steps": [],
            "artifacts": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
        }
        atomic_json_write(self._path(domain), checkpoint)

    def update_step(self, domain: str, step_result: dict) -> None:
        """Record a completed step in the checkpoint and clear WAL."""
        path = self._path(domain)
        if not os.path.exists(path):
            return

        try:
            with open(path) as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        checkpoint["completed_steps"].append(step_result)
        if step_result.get("artifacts"):
            checkpoint["artifacts"].extend(step_result["artifacts"])
        checkpoint["last_updated"] = datetime.now(timezone.utc).isoformat()
        # Clear WAL — step completed successfully
        checkpoint.pop("wal_pending", None)

        atomic_json_write(path, checkpoint)

    def write_ahead(self, domain: str, step_index: int,
                    step_info: dict) -> None:
        """
        WAL: Record intent before starting a step.

        If the process crashes during this step, recovery can see
        wal_pending in the checkpoint and know what was in-flight.
        """
        path = self._path(domain)
        if not os.path.exists(path):
            return

        try:
            with open(path) as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        checkpoint["wal_pending"] = {
            "step_index": step_index,
            "step_info": step_info,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        checkpoint["last_updated"] = datetime.now(timezone.utc).isoformat()
        atomic_json_write(path, checkpoint)

    def clear_wal(self, domain: str) -> None:
        """Clear WAL entry without recording a completed step."""
        path = self._path(domain)
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                checkpoint = json.load(f)
            checkpoint.pop("wal_pending", None)
            atomic_json_write(path, checkpoint)
        except (json.JSONDecodeError, OSError):
            pass

    def load(self, domain: str) -> Optional[dict]:
        """
        Load an active checkpoint for a domain.
        Returns the checkpoint dict, or None if no active checkpoint.
        """
        path = self._path(domain)
        if not os.path.exists(path):
            return None

        try:
            with open(path) as f:
                checkpoint = json.load(f)
            if checkpoint.get("status") == "in_progress":
                return checkpoint
            return None
        except (json.JSONDecodeError, OSError):
            return None

    def clear(self, domain: str) -> bool:
        """Remove the checkpoint for a domain (execution complete)."""
        path = self._path(domain)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def mark_complete(self, domain: str, success: bool) -> None:
        """Mark checkpoint as completed (before clearing)."""
        path = self._path(domain)
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                checkpoint = json.load(f)
            checkpoint["status"] = "completed" if success else "failed"
            checkpoint["finished_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json_write(path, checkpoint)
        except (json.JSONDecodeError, OSError):
            pass

    def list_active(self) -> list[dict]:
        """List all active checkpoints across domains."""
        active = []
        if not os.path.exists(self.checkpoint_dir):
            return active

        for fname in os.listdir(self.checkpoint_dir):
            if fname.endswith("_checkpoint.json"):
                domain = fname.replace("_checkpoint.json", "")
                cp = self.load(domain)
                if cp:
                    active.append({
                        "domain": domain,
                        "goal": cp.get("goal", ""),
                        "completed_steps": len(cp.get("completed_steps", [])),
                        "started_at": cp.get("started_at", ""),
                        "last_updated": cp.get("last_updated", ""),
                    })
        return active

    def get_resume_info(self, domain: str) -> Optional[dict]:
        """
        Get information needed to resume an execution.

        Returns:
            Dict with plan, completed step indices, artifacts,
            and wal_pending if a step was in-flight when crash occurred.
            None if nothing to resume.
        """
        checkpoint = self.load(domain)
        if not checkpoint:
            return None

        completed_steps = checkpoint.get("completed_steps", [])
        if not completed_steps and not checkpoint.get("wal_pending"):
            return None  # Nothing to resume from

        info = {
            "goal": checkpoint["goal"],
            "plan": checkpoint["plan"],
            "completed_step_count": len(completed_steps),
            "completed_steps": completed_steps,
            "artifacts": checkpoint.get("artifacts", []),
            "started_at": checkpoint.get("started_at"),
        }
        if checkpoint.get("wal_pending"):
            info["wal_pending"] = checkpoint["wal_pending"]
        return info
