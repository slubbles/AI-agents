"""
Outcome Feedback — Closing the Brain ↔ Hands Loop

This is the MISSING step in the core loop:
    Research → Critique → Store → Strategy → Handoff → Hands Execute → **Outcome Feedback** → Repeat

Without this, Brain creates tasks, Hands executes them, but Brain never learns
from execution results. Research happens in isolation from what actually worked
or failed in practice. The loop is open.

This module:
1. Reads completed/failed sync tasks with their execution results
2. Extracts lessons (what worked, what failed, why)
3. Feeds lessons back into Brain's research_lessons system
4. Optionally updates the KB with proven/disproven practical claims
5. Marks tasks as "feedback_processed" so they're not processed twice

No API calls — pure data extraction from existing execution results.

Usage:
    # Automatically (in scheduler daemon after Hands tasks complete)
    from outcome_feedback import process_pending_feedback
    process_pending_feedback()

    # Manually
    python main.py --process-feedback
"""

import json
import os
from datetime import datetime, timezone

from config import LOG_DIR
from sync import _load_tasks, _save_tasks


def get_completed_tasks(domain: str | None = None, unprocessed_only: bool = True) -> list[dict]:
    """
    Get completed or failed tasks that have not yet had their feedback processed.

    Returns tasks with status "completed" or "failed" that have a result
    and haven't been marked as feedback_processed.
    """
    tasks = _load_tasks()

    candidates = []
    for t in tasks:
        if t.get("status") not in ("completed", "failed"):
            continue
        if not t.get("result") or not isinstance(t.get("result"), dict):
            continue
        if unprocessed_only and t.get("_feedback_processed"):
            continue
        if domain and t.get("source_domain") != domain:
            continue
        candidates.append(t)

    return candidates


def _extract_execution_lessons(task: dict) -> list[dict]:
    """
    Extract actionable lessons from a completed or failed task.

    Reads the execution result and produces structured lessons that
    can feed into Brain's research_lessons system.
    """
    lessons = []
    result = task.get("result") or {}
    if not isinstance(result, dict):
        result = {}
    domain = task.get("source_domain", "general")
    task_type = task.get("task_type", "action")
    status = task.get("status", "unknown")
    title = task.get("title", "Unknown task")

    if status == "completed":
        # Successful execution — extract what worked
        validation_score = result.get("validation_score", result.get("score", 0))

        if isinstance(validation_score, (int, float)) and validation_score >= 7:
            lessons.append({
                "lesson": f"Successful execution: '{title[:80]}' — approach validated in practice",
                "source": "execution_success",
                "details": (f"Task type: {task_type}. "
                           f"Validation score: {validation_score}. "
                           f"This confirms the research insight was actionable."),
                "domain": domain,
            })

        # Extract specific patterns from result
        artifacts = result.get("artifacts", [])
        if artifacts:
            lessons.append({
                "lesson": f"Execution in {domain} produced {len(artifacts)} artifact(s) — domain supports practical output",
                "source": "execution_artifact",
                "details": f"Task: {title[:80]}. Artifacts indicate this domain has executable research-to-action pathways.",
                "domain": domain,
            })

    elif status == "failed":
        error = result.get("error", result.get("reason", "Unknown failure"))
        error_str = str(error)[:200]

        lessons.append({
            "lesson": f"Execution failed for '{title[:80]}' — research insight may not be directly actionable",
            "source": "execution_failure",
            "details": (f"Task type: {task_type}. Error: {error_str}. "
                       f"Brain should refine research to be more specific about practical feasibility."),
            "domain": domain,
        })

        # Detect common failure patterns
        if any(kw in error_str.lower() for kw in ("timeout", "timed out")):
            lessons.append({
                "lesson": f"Execution timeout in {domain} — tasks may be too complex for single-step execution",
                "source": "execution_timeout",
                "details": "Consider breaking research recommendations into smaller, more specific action items.",
                "domain": domain,
            })
        elif any(kw in error_str.lower() for kw in ("permission", "access denied", "forbidden")):
            lessons.append({
                "lesson": f"Access/permission issue in {domain} — research recommendations should account for execution constraints",
                "source": "execution_access",
                "details": f"Error: {error_str}",
                "domain": domain,
            })

    return lessons


def process_task_feedback(task: dict) -> dict:
    """
    Process a single completed/failed task and feed lessons back to Brain.

    Returns a summary of what was extracted and fed back.
    """
    from research_lessons import add_lesson

    lessons = _extract_execution_lessons(task)
    domain = task.get("source_domain", "general")
    fed_back = 0

    for lesson_data in lessons:
        try:
            add_lesson(
                domain=lesson_data["domain"],
                lesson=lesson_data["lesson"],
                source=lesson_data["source"],
                details=lesson_data.get("details", ""),
            )
            fed_back += 1
        except Exception:
            pass

    return {
        "task_id": task.get("id"),
        "domain": domain,
        "status": task.get("status", "unknown"),
        "lessons_extracted": len(lessons),
        "lessons_fed_back": fed_back,
    }


def process_pending_feedback(domain: str | None = None) -> dict:
    """
    Process all completed/failed tasks that haven't had feedback extracted yet.

    This is the main entry point — called by the daemon after task execution
    or manually via CLI.

    Returns summary of all feedback processing.
    """
    # Single load — process — mark — save to avoid TOCTOU race
    all_tasks = _load_tasks()

    tasks_to_process = []
    for t in all_tasks:
        if t.get("status") not in ("completed", "failed"):
            continue
        if not t.get("result") or not isinstance(t.get("result"), dict):
            continue
        if t.get("_feedback_processed"):
            continue
        if domain and t.get("source_domain") != domain:
            continue
        tasks_to_process.append(t)

    if not tasks_to_process:
        return {"processed": 0, "lessons_total": 0, "domains": []}

    results = []
    domains_touched = set()
    now = datetime.now(timezone.utc).isoformat()

    for task in tasks_to_process:
        feedback = process_task_feedback(task)
        results.append(feedback)
        domains_touched.add(feedback["domain"])
        task["_feedback_processed"] = True
        task["_feedback_processed_at"] = now

    _save_tasks(all_tasks)

    total_lessons = sum(r["lessons_fed_back"] for r in results)

    # Log the feedback processing
    _log_feedback_event(results)

    return {
        "processed": len(results),
        "lessons_total": total_lessons,
        "domains": sorted(domains_touched),
        "details": results,
    }


def get_feedback_stats() -> dict:
    """Get statistics on outcome feedback processing."""
    tasks = _load_tasks()
    completed = [t for t in tasks if t["status"] in ("completed", "failed")]
    processed = [t for t in completed if t.get("_feedback_processed")]
    unprocessed = [t for t in completed if not t.get("_feedback_processed") and t.get("result")]

    by_status = {"completed": 0, "failed": 0}
    for t in completed:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1

    return {
        "total_completed": len(completed),
        "feedback_processed": len(processed),
        "pending_feedback": len(unprocessed),
        "by_status": by_status,
    }


def _log_feedback_event(results: list[dict]):
    """Append feedback processing event to the log."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "outcome_feedback.jsonl")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tasks_processed": len(results),
        "total_lessons": sum(r["lessons_fed_back"] for r in results),
        "domains": sorted(set(r["domain"] for r in results)),
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
