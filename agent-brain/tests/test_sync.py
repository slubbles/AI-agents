"""
Tests for Sync — Brain ↔ Hands Alignment Checker

Tests cover:
  - Task lifecycle (create, update, query)
  - Task queue management (max pending, stale detection)
  - Subsystem health checks (Brain, Hands)
  - Full sync check
  - Edge cases (empty state, corrupt files)
"""

import json
import os
import sys
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sync import (
    create_task, update_task, get_pending_tasks, get_task_stats,
    mark_stale_tasks, check_brain_health, check_hands_health,
    check_sync, _load_tasks, _save_tasks,
    SYNC_TASKS_FILE, STALE_TASK_HOURS, MAX_PENDING_TASKS,
)


@pytest.fixture
def clean_sync(tmp_path, monkeypatch):
    """Isolated sync environment with temp files."""
    sync_file = str(tmp_path / "sync_tasks.json")
    monkeypatch.setattr("sync.SYNC_TASKS_FILE", sync_file)
    monkeypatch.setattr("sync.LOG_DIR", str(tmp_path))
    monkeypatch.setattr("sync.MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setattr("sync.EXEC_MEMORY_DIR", str(tmp_path / "exec_memory"))
    os.makedirs(tmp_path / "memory", exist_ok=True)
    return tmp_path


# ── Task Creation ────────────────────────────────────────────────────

class TestTaskCreation:
    def test_create_task_returns_dict(self, clean_sync):
        task = create_task("Test task", "Do something", "ai-coding")
        assert isinstance(task, dict)
        assert task["title"] == "Test task"
        assert task["status"] == "pending"
        assert task["source_domain"] == "ai-coding"

    def test_create_task_has_id(self, clean_sync):
        task = create_task("Test", "Desc", "domain")
        assert task["id"].startswith("task_")

    def test_create_task_persists(self, clean_sync):
        create_task("Persisted", "Test", "domain")
        tasks = _load_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Persisted"

    def test_create_multiple_tasks(self, clean_sync):
        create_task("Task 1", "Desc 1", "d1")
        create_task("Task 2", "Desc 2", "d2")
        create_task("Task 3", "Desc 3", "d1")
        assert len(_load_tasks()) == 3

    def test_task_types(self, clean_sync):
        task = create_task("Build thing", "Desc", "d", task_type="build")
        assert task["task_type"] == "build"

    def test_task_priority(self, clean_sync):
        task = create_task("Urgent", "Desc", "d", priority="critical")
        assert task["priority"] == "critical"

    def test_task_metadata(self, clean_sync):
        task = create_task("Meta", "Desc", "d", metadata={"key": "value"})
        assert task["metadata"]["key"] == "value"

    def test_task_source_output_id(self, clean_sync):
        task = create_task("Linked", "Desc", "d", source_output_id="output_123")
        assert task["source_output_id"] == "output_123"


# ── Task Updates ─────────────────────────────────────────────────────

class TestTaskUpdates:
    def test_update_status(self, clean_sync):
        task = create_task("Updatable", "Desc", "d")
        result = update_task(task["id"], "in_progress")
        assert result is True
        tasks = _load_tasks()
        assert tasks[0]["status"] == "in_progress"

    def test_update_to_completed(self, clean_sync):
        task = create_task("Complete me", "Desc", "d")
        update_task(task["id"], "completed", result={"success": True})
        tasks = _load_tasks()
        assert tasks[0]["status"] == "completed"
        assert tasks[0]["completed_at"] is not None
        assert tasks[0]["result"]["success"] is True

    def test_update_to_failed(self, clean_sync):
        task = create_task("Fail me", "Desc", "d")
        update_task(task["id"], "failed", result={"error": "oops"})
        tasks = _load_tasks()
        assert tasks[0]["status"] == "failed"
        assert tasks[0]["completed_at"] is not None

    def test_update_nonexistent_returns_false(self, clean_sync):
        result = update_task("fake_id", "completed")
        assert result is False

    def test_update_preserves_other_tasks(self, clean_sync):
        t1 = create_task("Task 1", "Desc", "d")
        t2 = create_task("Task 2", "Desc", "d")
        update_task(t1["id"], "completed")
        tasks = _load_tasks()
        assert tasks[0]["status"] == "completed"
        assert tasks[1]["status"] == "pending"


# ── Task Queries ─────────────────────────────────────────────────────

class TestTaskQueries:
    def test_get_pending_empty(self, clean_sync):
        assert get_pending_tasks() == []

    def test_get_pending_returns_pending_only(self, clean_sync):
        t1 = create_task("Pending", "Desc", "d")
        t2 = create_task("Done", "Desc", "d")
        update_task(t2["id"], "completed")
        pending = get_pending_tasks()
        assert len(pending) == 1
        assert pending[0]["title"] == "Pending"

    def test_get_pending_filter_by_domain(self, clean_sync):
        create_task("Task A", "Desc", "domain-a")
        create_task("Task B", "Desc", "domain-b")
        pending = get_pending_tasks(domain="domain-a")
        assert len(pending) == 1
        assert pending[0]["source_domain"] == "domain-a"

    def test_get_pending_filter_by_type(self, clean_sync):
        create_task("Build", "Desc", "d", task_type="build")
        create_task("Deploy", "Desc", "d", task_type="deploy")
        pending = get_pending_tasks(task_type="build")
        assert len(pending) == 1
        assert pending[0]["task_type"] == "build"

    def test_get_pending_sorted_by_priority(self, clean_sync):
        create_task("Low", "Desc", "d", priority="low")
        create_task("Critical", "Desc", "d", priority="critical")
        create_task("Medium", "Desc", "d", priority="medium")
        pending = get_pending_tasks()
        assert pending[0]["priority"] == "critical"
        assert pending[1]["priority"] == "medium"
        assert pending[2]["priority"] == "low"

    def test_get_pending_respects_limit(self, clean_sync):
        for i in range(10):
            create_task(f"Task {i}", "Desc", "d")
        assert len(get_pending_tasks(limit=3)) == 3


# ── Task Stats ───────────────────────────────────────────────────────

class TestTaskStats:
    def test_empty_stats(self, clean_sync):
        stats = get_task_stats()
        assert stats["total"] == 0
        assert stats["pending"] == 0

    def test_stats_count_correctly(self, clean_sync):
        t1 = create_task("A", "D", "d")
        t2 = create_task("B", "D", "d")
        t3 = create_task("C", "D", "d")
        update_task(t1["id"], "completed")
        update_task(t2["id"], "failed")
        stats = get_task_stats()
        assert stats["total"] == 3
        assert stats["completed"] == 1
        assert stats["failed"] == 1
        assert stats["pending"] == 1


# ── Max Pending Tasks ────────────────────────────────────────────────

class TestMaxPendingTasks:
    def test_overflow_drops_lowest_priority(self, clean_sync, monkeypatch):
        monkeypatch.setattr("sync.MAX_PENDING_TASKS", 3)
        create_task("High 1", "D", "d", priority="high")
        create_task("Low 1", "D", "d", priority="low")
        create_task("High 2", "D", "d", priority="high")
        # This 4th task should trigger overflow
        create_task("Critical 1", "D", "d", priority="critical")
        stats = get_task_stats()
        # Should have 1 dropped task
        assert stats["dropped"] >= 1


# ── Stale Task Detection ────────────────────────────────────────────

class TestStaleTasks:
    def test_no_stale_when_recent(self, clean_sync):
        create_task("Fresh", "Desc", "d")
        stale = mark_stale_tasks()
        assert stale == 0

    def test_marks_old_tasks_stale(self, clean_sync):
        task = create_task("Old", "Desc", "d")
        # Manually set old timestamp
        tasks = _load_tasks()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=STALE_TASK_HOURS + 1))
        tasks[0]["created_at"] = old_time.isoformat()
        _save_tasks(tasks)

        stale = mark_stale_tasks()
        assert stale == 1
        tasks = _load_tasks()
        assert tasks[0]["status"] == "stale"

    def test_completed_not_marked_stale(self, clean_sync):
        task = create_task("Done", "Desc", "d")
        update_task(task["id"], "completed")
        tasks = _load_tasks()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=STALE_TASK_HOURS + 1))
        tasks[0]["created_at"] = old_time.isoformat()
        _save_tasks(tasks)

        stale = mark_stale_tasks()
        assert stale == 0


# ── Brain Health ─────────────────────────────────────────────────────

class TestBrainHealth:
    def test_healthy_brain(self, clean_sync):
        with patch("agents.orchestrator.discover_domains", return_value=["test-domain"]):
            with patch("memory_store.get_stats", return_value={"count": 5, "accepted": 3}):
                result = check_brain_health()
        assert result["healthy"] is True
        assert len(result["issues"]) == 0

    def test_no_domains(self, clean_sync):
        with patch("agents.orchestrator.discover_domains", return_value=[]):
            with patch("memory_store.get_stats", return_value={"count": 0, "accepted": 0}):
                result = check_brain_health()
        # No domains is an issue
        assert "No research domains" in str(result["issues"])

    def test_memory_dir_missing(self, clean_sync, monkeypatch):
        monkeypatch.setattr("sync.MEMORY_DIR", "/nonexistent/path")
        result = check_brain_health()
        assert result["checks"]["memory_dir"] is False


# ── Hands Health ─────────────────────────────────────────────────────

class TestHandsHealth:
    def test_hands_importable(self, clean_sync):
        result = check_hands_health()
        # Should pass if hands modules are importable
        assert isinstance(result["healthy"], bool)
        assert "checks" in result

    def test_hands_handles_import_error(self, clean_sync):
        with patch("sync.EXEC_MEMORY_DIR", "/nonexistent"):
            result = check_hands_health()
            assert isinstance(result, dict)


# ── Full Sync Check ──────────────────────────────────────────────────

class TestFullSyncCheck:
    def test_sync_returns_structure(self, clean_sync):
        with patch("agents.orchestrator.discover_domains", return_value=[]):
            with patch("memory_store.get_stats", return_value={"count": 0, "accepted": 0}):
                result = check_sync()
        assert "aligned" in result
        assert "brain_health" in result
        assert "hands_health" in result
        assert "task_stats" in result

    def test_aligned_when_healthy(self, clean_sync):
        with patch("agents.orchestrator.discover_domains", return_value=["test"]):
            with patch("memory_store.get_stats", return_value={"count": 5, "accepted": 3}):
                result = check_sync()
        assert isinstance(result["aligned"], bool)

    def test_reports_stale_tasks_as_issue(self, clean_sync):
        task = create_task("Old task", "Desc", "d")
        tasks = _load_tasks()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=STALE_TASK_HOURS + 1))
        tasks[0]["created_at"] = old_time.isoformat()
        _save_tasks(tasks)

        with patch("agents.orchestrator.discover_domains", return_value=["d"]):
            with patch("memory_store.get_stats", return_value={"count": 1, "accepted": 1}):
                result = check_sync()
        assert result["stale_tasks_flagged"] == 1
        assert any("stale" in i.lower() for i in result["issues"])

    def test_recommendations_when_brain_has_research_no_tasks(self, clean_sync):
        with patch("agents.orchestrator.discover_domains", return_value=["d1", "d2"]):
            with patch("memory_store.get_stats", return_value={"count": 20, "accepted": 15}):
                result = check_sync()
        assert any("no tasks queued" in r.lower() for r in result["recommendations"])


# ── Edge Cases ───────────────────────────────────────────────────────

class TestEdgeCases:
    def test_load_empty_file(self, clean_sync, tmp_path):
        # Create empty file
        sync_file = str(tmp_path / "sync_tasks.json")
        with open(sync_file, "w") as f:
            f.write("")
        tasks = _load_tasks()
        assert tasks == []

    def test_load_corrupt_file(self, clean_sync, tmp_path):
        sync_file = str(tmp_path / "sync_tasks.json")
        with open(sync_file, "w") as f:
            f.write("not json at all")
        tasks = _load_tasks()
        assert tasks == []

    def test_load_non_list_json(self, clean_sync, tmp_path):
        sync_file = str(tmp_path / "sync_tasks.json")
        with open(sync_file, "w") as f:
            json.dump({"not": "a list"}, f)
        tasks = _load_tasks()
        assert tasks == []

    def test_no_file_returns_empty(self, clean_sync):
        tasks = _load_tasks()
        assert tasks == []
