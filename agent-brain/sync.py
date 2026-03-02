"""
Sync — Brain ↔ Hands Alignment Checker

Ensures that Brain's research findings lead to Hands' execution,
and Hands' results feed back into Brain's learning. The connective
tissue between asking questions and taking action.

Responsibilities:
  1. Task queue — Brain creates action items, Hands picks them up
  2. Alignment check — detect research that suggests actions not yet taken
  3. Feedback loop — execution results inform Brain's knowledge
  4. Subsystem health — verify both Brain and Hands are operational
  5. Stale task detection — flag old unactioned recommendations

Design:
  - Task queue persisted as JSON in logs/sync_tasks.json
  - No LLM calls — pure logic + file system checks
  - Tasks have lifecycle: pending → in_progress → completed | failed | stale
  - Each task links back to the research that created it

Usage:
  from sync import check_sync, create_task, get_pending_tasks
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from config import LOG_DIR, MEMORY_DIR, EXEC_MEMORY_DIR
from utils.atomic_write import atomic_json_write


# ── Configuration ──────────────────────────────────────────────────────────

SYNC_TASKS_FILE = os.path.join(LOG_DIR, "sync_tasks.json")
STALE_TASK_HOURS = 72      # Tasks older than 72h without action → stale
MAX_PENDING_TASKS = 50     # Don't let the queue grow unbounded


# ── Task Lifecycle ─────────────────────────────────────────────────────────

def _load_tasks() -> list[dict]:
    """Load the task queue from disk."""
    if not os.path.exists(SYNC_TASKS_FILE):
        return []
    try:
        with open(SYNC_TASKS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_tasks(tasks: list[dict]):
    """Persist the task queue to disk."""
    os.makedirs(LOG_DIR, exist_ok=True)
    atomic_json_write(SYNC_TASKS_FILE, tasks)


def create_task(
    title: str,
    description: str,
    source_domain: str,
    task_type: str = "action",
    priority: str = "medium",
    source_output_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """
    Create a task from Brain research for Hands to execute.

    Args:
        title: Short task title
        description: What needs to be done
        source_domain: Brain domain that generated this task
        task_type: "action" | "build" | "deploy" | "investigate"
        priority: "critical" | "high" | "medium" | "low"
        source_output_id: Optional link to the research output
        metadata: Additional context

    Returns:
        The created task dict
    """
    tasks = _load_tasks()

    task = {
        "id": f"task_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}",
        "title": title,
        "description": description,
        "status": "pending",
        "task_type": task_type,
        "priority": priority,
        "source_domain": source_domain,
        "source_output_id": source_output_id,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "result": None,
    }

    tasks.append(task)

    # Enforce max pending tasks (drop oldest low-priority)
    pending = [t for t in tasks if t["status"] == "pending"]
    if len(pending) > MAX_PENDING_TASKS:
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        pending.sort(key=lambda t: (
            priority_order.get(t["priority"], 4),
            t["created_at"],
        ))
        # Keep top MAX_PENDING_TASKS, mark rest as dropped
        to_drop = pending[MAX_PENDING_TASKS:]
        drop_ids = {t["id"] for t in to_drop}
        for t in tasks:
            if t["id"] in drop_ids:
                t["status"] = "dropped"
                t["updated_at"] = datetime.now(timezone.utc).isoformat()

    _save_tasks(tasks)
    return task


def update_task(task_id: str, status: str, result: dict | None = None) -> bool:
    """
    Update a task's status.

    Args:
        task_id: The task ID
        status: New status: "in_progress" | "completed" | "failed"
        result: Optional result data from execution

    Returns:
        True if task was found and updated
    """
    tasks = _load_tasks()
    for task in tasks:
        if task["id"] == task_id:
            task["status"] = status
            task["updated_at"] = datetime.now(timezone.utc).isoformat()
            if status in ("completed", "failed"):
                task["completed_at"] = datetime.now(timezone.utc).isoformat()
            if result:
                task["result"] = result
            _save_tasks(tasks)
            return True
    return False


def get_pending_tasks(
    domain: str | None = None,
    task_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Get pending tasks for Hands to work on.

    Args:
        domain: Filter by source domain (optional)
        task_type: Filter by task type (optional)
        limit: Max tasks to return

    Returns:
        List of pending tasks, sorted by priority then age
    """
    tasks = _load_tasks()
    pending = [t for t in tasks if t["status"] == "pending"]

    if domain:
        pending = [t for t in pending if t["source_domain"] == domain]
    if task_type:
        pending = [t for t in pending if t["task_type"] == task_type]

    # Sort: highest priority first, then oldest first
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    pending.sort(key=lambda t: (
        priority_order.get(t["priority"], 4),
        t["created_at"],
    ))

    return pending[:limit]


def get_task_stats() -> dict:
    """
    Get task queue statistics.

    Returns:
        {total, pending, in_progress, completed, failed, stale, dropped}
    """
    tasks = _load_tasks()
    stats = {
        "total": len(tasks),
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "stale": 0,
        "dropped": 0,
    }
    for t in tasks:
        status = t.get("status", "pending")
        if status in stats:
            stats[status] += 1
    return stats


# ── Stale Task Detection ──────────────────────────────────────────────────

def mark_stale_tasks() -> int:
    """
    Mark tasks that have been pending too long as stale.

    Returns:
        Number of tasks marked stale
    """
    tasks = _load_tasks()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=STALE_TASK_HOURS)).isoformat()
    stale_count = 0

    for task in tasks:
        if task["status"] == "pending" and task["created_at"] < cutoff:
            task["status"] = "stale"
            task["updated_at"] = datetime.now(timezone.utc).isoformat()
            stale_count += 1

    if stale_count > 0:
        _save_tasks(tasks)

    return stale_count


# ── Subsystem Health ──────────────────────────────────────────────────────

def check_brain_health() -> dict:
    """
    Check Brain subsystem health.

    Verifies:
    - Memory directory exists and is writable
    - At least one domain has data
    - Strategy system is functional
    - Cost tracking is responding

    Returns:
        {healthy: bool, checks: {name: passed}, issues: [str]}
    """
    checks = {}
    issues = []

    # Memory directory
    checks["memory_dir"] = os.path.isdir(MEMORY_DIR)
    if not checks["memory_dir"]:
        issues.append(f"Memory directory missing: {MEMORY_DIR}")

    # Writable
    try:
        test_file = os.path.join(MEMORY_DIR or "/tmp", "_health_check_test")
        os.makedirs(os.path.dirname(test_file), exist_ok=True)
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        checks["memory_writable"] = True
    except (OSError, IOError):
        checks["memory_writable"] = False
        issues.append("Memory directory is not writable")

    # Domain data
    try:
        from memory_store import get_stats
        from agents.orchestrator import discover_domains
        domains = discover_domains()
        checks["has_domains"] = len(domains) > 0
        if not domains:
            issues.append("No research domains found")
        total_outputs = sum(get_stats(d)["count"] for d in domains)
        checks["has_outputs"] = total_outputs > 0
    except Exception as e:
        checks["has_domains"] = False
        checks["has_outputs"] = False
        issues.append(f"Domain check failed: {e}")

    # Strategy system
    try:
        from strategy_store import get_active_version
        checks["strategy_system"] = True
    except Exception as e:
        checks["strategy_system"] = False
        issues.append(f"Strategy system error: {e}")

    # Cost tracking
    try:
        from cost_tracker import check_budget
        budget = check_budget()
        checks["cost_tracking"] = "within_budget" in budget
    except Exception as e:
        checks["cost_tracking"] = False
        issues.append(f"Cost tracking error: {e}")

    return {
        "healthy": len(issues) == 0,
        "checks": checks,
        "issues": issues,
    }


def check_hands_health() -> dict:
    """
    Check Hands subsystem health.

    Verifies:
    - Exec memory directory exists
    - Executor module is importable
    - Tool system is functional

    Returns:
        {healthy: bool, checks: {name: passed}, issues: [str]}
    """
    checks = {}
    issues = []

    # Exec memory directory
    exec_mem_dir = EXEC_MEMORY_DIR if EXEC_MEMORY_DIR else os.path.join(
        os.path.dirname(__file__), "exec_memory"
    )
    checks["exec_memory_dir"] = os.path.isdir(exec_mem_dir)
    if not checks["exec_memory_dir"]:
        # Not an error — just means Hands hasn't been used yet
        checks["exec_memory_dir"] = True  # Acceptable state

    # Executor importable
    try:
        from hands.executor import execute  # noqa: F401
        checks["executor_importable"] = True
    except Exception as e:
        checks["executor_importable"] = False
        issues.append(f"Executor import failed: {e}")

    # Planner importable
    try:
        from hands.planner import plan  # noqa: F401
        checks["planner_importable"] = True
    except Exception as e:
        checks["planner_importable"] = False
        issues.append(f"Planner import failed: {e}")

    # Validator importable
    try:
        from hands.validator import validate  # noqa: F401
        checks["validator_importable"] = True
    except Exception as e:
        checks["validator_importable"] = False
        issues.append(f"Validator import failed: {e}")

    return {
        "healthy": len(issues) == 0,
        "checks": checks,
        "issues": issues,
    }


# ── Full Sync Check ──────────────────────────────────────────────────────

def check_sync() -> dict:
    """
    Run a full synchronization check between Brain and Hands.

    Returns:
        {
            aligned: bool,
            brain_health: {...},
            hands_health: {...},
            task_stats: {...},
            stale_tasks_flagged: int,
            issues: [str],
            recommendations: [str]
        }
    """
    issues = []
    recommendations = []

    # 1. Check subsystem health
    brain = check_brain_health()
    hands = check_hands_health()

    if not brain["healthy"]:
        issues.extend(brain["issues"])
    if not hands["healthy"]:
        issues.extend(hands["issues"])

    # 2. Mark stale tasks
    stale_count = mark_stale_tasks()
    if stale_count > 0:
        issues.append(f"{stale_count} tasks became stale (pending > {STALE_TASK_HOURS}h)")
        recommendations.append(
            "Review stale tasks — some research findings may need action"
        )

    # 3. Task queue health
    stats = get_task_stats()

    if stats["pending"] > 20:
        issues.append(f"Large pending queue: {stats['pending']} tasks")
        recommendations.append("Execute pending tasks or deprioritize low-value ones")

    if stats["failed"] > 5:
        issues.append(f"Many failed tasks: {stats['failed']}")
        recommendations.append("Review failed tasks for systemic issues")

    if stats["in_progress"] > 3:
        issues.append(f"Multiple tasks in-progress: {stats['in_progress']}")
        recommendations.append("Check for stuck executions")

    # 4. Brain has research but no tasks created (potential gap)
    try:
        from memory_store import get_stats
        from agents.orchestrator import discover_domains
        domains = discover_domains()
        total_accepted = sum(get_stats(d)["accepted"] for d in domains)
        if total_accepted > 10 and stats["total"] == 0:
            recommendations.append(
                "Brain has research findings but no tasks queued for Hands. "
                "Consider running task extraction from research outputs."
            )
    except Exception:
        pass

    # 5. Hands has results but Brain doesn't know
    if EXEC_MEMORY_DIR and os.path.isdir(EXEC_MEMORY_DIR):
        exec_domains = [
            d for d in os.listdir(EXEC_MEMORY_DIR)
            if os.path.isdir(os.path.join(EXEC_MEMORY_DIR, d))
            and not d.startswith("_")
        ]
        if exec_domains:
            try:
                from agents.orchestrator import discover_domains
                brain_domains = set(discover_domains())
                exec_only = [d for d in exec_domains if d not in brain_domains]
                if exec_only:
                    recommendations.append(
                        f"Hands has results in domains Brain doesn't track: "
                        f"{', '.join(exec_only)}"
                    )
            except Exception:
                pass

    aligned = len(issues) == 0

    return {
        "aligned": aligned,
        "brain_health": brain,
        "hands_health": hands,
        "task_stats": stats,
        "stale_tasks_flagged": stale_count,
        "issues": issues,
        "recommendations": recommendations,
    }
