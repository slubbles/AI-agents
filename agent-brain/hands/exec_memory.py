"""
Execution Memory Store — Scored execution outputs, per domain.

Parallel to Brain's memory_store.py but for execution (Hands) outputs.
Stores: goal, plan, execution report, validation scores, artifacts.
Used by exec_meta_analyst to evolve execution strategies.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import EXEC_MEMORY_DIR, EXEC_QUALITY_THRESHOLD
from utils.atomic_write import atomic_json_write


def save_exec_output(
    domain: str,
    goal: str,
    plan: dict,
    execution_report: dict,
    validation: dict,
    attempt: int,
    strategy_version: str,
) -> str:
    """
    Save a scored execution output to the exec memory store.

    Returns:
        Path to the saved file
    """
    domain_dir = os.path.join(EXEC_MEMORY_DIR, domain)
    os.makedirs(domain_dir, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    micro = now.strftime("%f")
    pid = os.getpid()
    score = validation.get("overall_score", 0)
    filename = f"{timestamp}_{micro}_{pid}_exec_score{score:.0f}.json"
    filepath = os.path.join(domain_dir, filename)

    accepted = score >= EXEC_QUALITY_THRESHOLD

    record = {
        "timestamp": now.isoformat(),
        "domain": domain,
        "goal": goal,
        "attempt": attempt,
        "strategy_version": strategy_version,
        "plan": {
            "task_summary": plan.get("task_summary", ""),
            "steps_count": len(plan.get("steps", [])),
            "estimated_complexity": plan.get("estimated_complexity", "medium"),
            "success_criteria": plan.get("success_criteria", ""),
        },
        "execution": {
            "success": execution_report.get("success", False),
            "completed_steps": execution_report.get("completed_steps", 0),
            "failed_steps": execution_report.get("failed_steps", 0),
            "total_steps": execution_report.get("total_steps", 0),
            "artifacts": execution_report.get("artifacts", []),
            # Store step results (capped for storage)
            "step_results": [
                {
                    "step": s.get("step", 0),
                    "tool": s.get("tool", ""),
                    "success": s.get("success", False),
                    "output": s.get("output", "")[:500],
                    "error": s.get("error", ""),
                }
                for s in execution_report.get("step_results", [])[:20]
            ],
        },
        "validation": validation,
        "overall_score": score,
        "accepted": accepted,
        "verdict": validation.get("verdict", "unknown"),
    }

    atomic_json_write(filepath, record)

    return filepath


def load_exec_outputs(domain: str, min_score: float = 0) -> list[dict]:
    """
    Load all execution outputs for a domain, optionally filtered by minimum score.
    """
    domain_dir = os.path.join(EXEC_MEMORY_DIR, domain)
    if not os.path.exists(domain_dir):
        return []

    outputs = []
    for filename in sorted(os.listdir(domain_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(domain_dir, filename)
        try:
            with open(filepath) as f:
                record = json.load(f)
            if record.get("overall_score", 0) >= min_score:
                outputs.append(record)
        except (json.JSONDecodeError, IOError):
            continue

    return outputs


def get_exec_stats(domain: str) -> dict:
    """Get aggregate stats for a domain's execution memory."""
    outputs = load_exec_outputs(domain)
    if not outputs:
        return {
            "count": 0,
            "avg_score": 0,
            "accepted": 0,
            "rejected": 0,
            "total_artifacts": 0,
        }

    scores = [o.get("overall_score", 0) for o in outputs]
    total_artifacts = sum(
        len(o.get("execution", {}).get("artifacts", []))
        for o in outputs
    )

    return {
        "count": len(outputs),
        "avg_score": sum(scores) / len(scores),
        "accepted": sum(1 for o in outputs if o.get("accepted")),
        "rejected": sum(1 for o in outputs if not o.get("accepted")),
        "total_artifacts": total_artifacts,
    }


def get_recent_exec_outputs(domain: str, n: int = 5) -> list[dict]:
    """Get the N most recent execution outputs (for meta-analysis)."""
    outputs = load_exec_outputs(domain)
    return outputs[-n:] if outputs else []
