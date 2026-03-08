"""
Outcome Feedback — close the Brain <- Hands loop.

Reads completed and failed sync tasks, extracts practical lessons from
execution outcomes, feeds them into research_lessons, and marks tasks as
processed so feedback is only applied once.
"""

import json
import os
from datetime import datetime, timezone

from config import LOG_DIR
from sync import _load_tasks, _save_tasks


def _extract_validation_score(result: dict) -> float:
    """Best-effort score extraction across current Hands result shapes."""
    if not isinstance(result, dict):
        return 0.0

    validation = result.get("validation")
    if isinstance(validation, dict):
        score = validation.get("overall_score")
        if isinstance(score, (int, float)):
            return float(score)

    for key in ("overall_score", "validation_score", "score"):
        score = result.get(key)
        if isinstance(score, (int, float)):
            return float(score)

    return 0.0


def get_completed_tasks(domain: str | None = None, unprocessed_only: bool = True) -> list[dict]:
    """Return completed/failed tasks with result payloads."""
    tasks = _load_tasks()

    candidates = []
    for task in tasks:
        if task.get("status") not in ("completed", "failed"):
            continue
        if not isinstance(task.get("result"), dict):
            continue
        if unprocessed_only and task.get("_feedback_processed"):
            continue
        if domain and task.get("source_domain") != domain:
            continue
        candidates.append(task)

    return candidates


def _extract_execution_lessons(task: dict) -> list[dict]:
    """Convert a task result into one or more research lessons."""
    lessons = []
    result = task.get("result") or {}
    if not isinstance(result, dict):
        result = {}

    domain = task.get("source_domain", "general")
    task_type = task.get("task_type", "action")
    status = task.get("status", "unknown")
    title = task.get("title", "Unknown task")
    validation_score = _extract_validation_score(result)

    if status == "completed":
        if validation_score >= 7:
            lessons.append({
                "lesson": f"Successful execution: '{title[:80]}' — approach validated in practice",
                "source": "execution_success",
                "details": (
                    f"Task type: {task_type}. Validation score: {validation_score:.1f}. "
                    "This research-to-execution path produced a strong real result."
                ),
                "domain": domain,
            })

        artifacts = result.get("artifacts", [])
        if isinstance(artifacts, list) and artifacts:
            lessons.append({
                "lesson": f"Execution in {domain} produced {len(artifacts)} artifact(s) — domain supports practical output",
                "source": "execution_artifact",
                "details": f"Task: {title[:80]}. Artifacts suggest the recommendation was concrete enough to execute.",
                "domain": domain,
            })

    elif status == "failed":
        error = result.get("error", result.get("reason", "Unknown failure"))
        error_str = str(error)[:200]

        lessons.append({
            "lesson": f"Execution failed for '{title[:80]}' — research insight may not be directly actionable",
            "source": "execution_failure",
            "details": (
                f"Task type: {task_type}. Error: {error_str}. "
                "Research should be more specific about feasibility, dependencies, or execution constraints."
            ),
            "domain": domain,
        })

        lowered = error_str.lower()
        if "timeout" in lowered or "timed out" in lowered:
            lessons.append({
                "lesson": f"Execution timeout in {domain} — tasks may be too complex for single-step execution",
                "source": "execution_timeout",
                "details": "Break recommendations into smaller, more specific steps before handing them to Hands.",
                "domain": domain,
            })
        elif any(token in lowered for token in ("permission", "access denied", "forbidden")):
            lessons.append({
                "lesson": f"Access or permission issue in {domain} — recommendations should account for execution constraints",
                "source": "execution_access",
                "details": f"Error: {error_str}",
                "domain": domain,
            })

    return lessons


def process_task_feedback(task: dict) -> dict:
    """Process one task and feed lessons into research_lessons."""
    from research_lessons import add_lesson

    lessons = _extract_execution_lessons(task)
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
        "domain": task.get("source_domain", "general"),
        "status": task.get("status", "unknown"),
        "lessons_extracted": len(lessons),
        "lessons_fed_back": fed_back,
    }


def process_pending_feedback(domain: str | None = None) -> dict:
    """Process all completed/failed tasks that have not been fed back yet."""
    all_tasks = _load_tasks()

    tasks_to_process = []
    for task in all_tasks:
        if task.get("status") not in ("completed", "failed"):
            continue
        if not isinstance(task.get("result"), dict):
            continue
        if task.get("_feedback_processed"):
            continue
        if domain and task.get("source_domain") != domain:
            continue
        tasks_to_process.append(task)

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
    _log_feedback_event(results)

    return {
        "processed": len(results),
        "lessons_total": sum(r["lessons_fed_back"] for r in results),
        "domains": sorted(domains_touched),
        "details": results,
    }


def get_feedback_stats() -> dict:
    """Return summary stats for processed vs pending outcome feedback."""
    tasks = _load_tasks()
    completed = [t for t in tasks if t.get("status") in ("completed", "failed")]
    processed = [t for t in completed if t.get("_feedback_processed")]
    unprocessed = [
        t for t in completed
        if not t.get("_feedback_processed") and isinstance(t.get("result"), dict)
    ]

    by_status = {"completed": 0, "failed": 0}
    for task in completed:
        status = task.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total_completed": len(completed),
        "feedback_processed": len(processed),
        "pending_feedback": len(unprocessed),
        "by_status": by_status,
    }


def _log_feedback_event(results: list[dict]) -> None:
    """Append a small audit event for feedback processing."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "outcome_feedback.jsonl")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tasks_processed": len(results),
        "total_lessons": sum(r["lessons_fed_back"] for r in results),
        "domains": sorted({r["domain"] for r in results}),
    }
    try:
        with open(log_path, "a") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        pass