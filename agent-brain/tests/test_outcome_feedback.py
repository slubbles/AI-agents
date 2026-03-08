"""Tests for outcome_feedback.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def feedback_env(tmp_path, monkeypatch):
    sync_file = str(tmp_path / "sync_tasks.json")
    lessons_dir = str(tmp_path / "lessons")
    log_dir = str(tmp_path / "logs")
    os.makedirs(log_dir, exist_ok=True)

    monkeypatch.setattr("sync.SYNC_TASKS_FILE", sync_file)
    monkeypatch.setattr("sync.LOG_DIR", log_dir)
    monkeypatch.setattr("outcome_feedback.LOG_DIR", log_dir)
    monkeypatch.setattr("research_lessons.LESSONS_DIR", lessons_dir)
    return tmp_path


class TestOutcomeFeedback:
    def test_completed_task_feeds_back_success_and_artifact_lessons(self, feedback_env):
        from sync import create_task, update_task, _load_tasks
        from outcome_feedback import process_pending_feedback
        from research_lessons import get_lessons

        task = create_task("Build landing page", "Desc", "productized-services", task_type="build")
        update_task(task["id"], "completed", {
            "success": True,
            "artifacts": ["index.tsx", "styles.css"],
            "validation": {"overall_score": 8.4},
        })

        result = process_pending_feedback()

        assert result["processed"] == 1
        assert result["lessons_total"] == 2

        lessons = get_lessons("productized-services")
        texts = [entry["lesson"] for entry in lessons]
        assert any("Successful execution" in text for text in texts)
        assert any("produced 2 artifact(s)" in text for text in texts)

        tasks = _load_tasks()
        assert tasks[0]["_feedback_processed"] is True
        assert tasks[0]["_feedback_processed_at"]

    def test_failed_timeout_task_feeds_back_failure_and_timeout_lessons(self, feedback_env):
        from sync import create_task, update_task
        from outcome_feedback import process_pending_feedback
        from research_lessons import get_lessons

        task = create_task("Deploy service", "Desc", "micro-saas", task_type="deploy")
        update_task(task["id"], "failed", {"error": "Task timed out after 300s"})

        result = process_pending_feedback()

        assert result["processed"] == 1
        assert result["lessons_total"] == 2

        lessons = get_lessons("micro-saas")
        texts = [entry["lesson"] for entry in lessons]
        assert any("Execution failed" in text for text in texts)
        assert any("Execution timeout" in text for text in texts)

    def test_skips_already_processed_tasks(self, feedback_env):
        from sync import create_task, update_task, _load_tasks, _save_tasks
        from outcome_feedback import process_pending_feedback

        task = create_task("Task", "Desc", "ai", task_type="action")
        update_task(task["id"], "completed", {
            "success": True,
            "validation": {"overall_score": 7.5},
        })

        tasks = _load_tasks()
        tasks[0]["_feedback_processed"] = True
        _save_tasks(tasks)

        result = process_pending_feedback()
        assert result["processed"] == 0
        assert result["lessons_total"] == 0

    def test_feedback_stats_counts_processed_and_pending(self, feedback_env):
        from sync import create_task, update_task, _load_tasks, _save_tasks
        from outcome_feedback import get_feedback_stats

        done = create_task("Done", "Desc", "ai")
        pending = create_task("Pending", "Desc", "ai")
        update_task(done["id"], "completed", {"success": True})
        update_task(pending["id"], "failed", {"error": "boom"})

        tasks = _load_tasks()
        tasks[0]["_feedback_processed"] = True
        _save_tasks(tasks)

        stats = get_feedback_stats()
        assert stats["total_completed"] == 2
        assert stats["feedback_processed"] == 1
        assert stats["pending_feedback"] == 1
        assert stats["by_status"]["completed"] == 1
        assert stats["by_status"]["failed"] == 1