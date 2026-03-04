"""
Tests for Large Project Orchestrator.

Tests decomposition, state management, execution flow, and status reporting.
Uses mocks to avoid Claude API calls.
"""

import json
import os
import sys
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hands.project_orchestrator import (
    PhaseStatus,
    ProjectStatus,
    save_project,
    load_project,
    list_projects,
    project_status,
    project_report,
    execute_phase,
    approve_phase,
    skip_phase,
    retry_phase,
    MAX_PHASES,
    MAX_TASKS_PER_PHASE,
    MAX_TOTAL_TASKS,
    HUMAN_REVIEW_PHASES,
)


# ── Fixtures ────────────────────────────────────────────────

def _make_project(
    tmp_path,
    num_phases: int = 3,
    tasks_per_phase: int = 2,
    project_id: str = "test-project-001",
) -> dict:
    """Create a minimal test project."""
    phases = []
    for i in range(num_phases):
        tasks = []
        for j in range(tasks_per_phase):
            tasks.append({
                "id": f"task-{i}-{j}",
                "description": f"Task {j} of phase {i}",
                "type": "execute" if j < tasks_per_phase - 1 else "validate",
                "estimated_minutes": 5,
                "depends_on": [f"task-{i}-{j-1}"] if j > 0 else [],
                "status": PhaseStatus.PENDING,
                "result": None,
                "error": None,
            })
        phases.append({
            "id": f"phase-{i:02d}",
            "name": f"Phase {i}",
            "description": f"Description for phase {i}",
            "order": i,
            "estimated_hours": 1,
            "requires_human_review": i == 1,  # Phase 1 requires review
            "gate_condition": f"Phase {i} gate condition",
            "tasks": tasks,
            "status": PhaseStatus.PENDING,
            "started_at": None,
            "completed_at": None,
            "execution_results": [],
            "validation_results": [],
            "retry_count": 0,
        })

    project = {
        "project_id": project_id,
        "project_name": "test-project",
        "description": "A test project",
        "summary": "Testing",
        "tech_stack": ["Python"],
        "total_estimated_hours": 3,
        "status": ProjectStatus.PLANNING,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": str(tmp_path),
        "current_phase_index": 0,
        "phases": phases,
        "execution_log": [],
    }
    return project


@pytest.fixture
def project(tmp_path):
    """Basic test project."""
    return _make_project(tmp_path)


@pytest.fixture
def project_on_disk(tmp_path, project):
    """Project saved to a temp projects dir."""
    with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
        save_project(project)
    return project


# ============================================================
# Constants
# ============================================================

class TestConstants:
    def test_max_phases(self):
        assert MAX_PHASES >= 5
        assert MAX_PHASES <= 20

    def test_max_tasks_per_phase(self):
        assert MAX_TASKS_PER_PHASE >= 5
        assert MAX_TASKS_PER_PHASE <= 50

    def test_max_total_tasks(self):
        assert MAX_TOTAL_TASKS >= 50
        assert MAX_TOTAL_TASKS <= 500

    def test_human_review_phases(self):
        assert "architecture" in HUMAN_REVIEW_PHASES
        assert "deployment" in HUMAN_REVIEW_PHASES
        assert "security" in HUMAN_REVIEW_PHASES


# ============================================================
# Phase/Project Status Enums
# ============================================================

class TestStatusEnums:
    def test_phase_status_values(self):
        assert PhaseStatus.PENDING == "pending"
        assert PhaseStatus.COMPLETED == "completed"
        assert PhaseStatus.FAILED == "failed"
        assert PhaseStatus.REVIEW_NEEDED == "review_needed"

    def test_project_status_values(self):
        assert ProjectStatus.PLANNING == "planning"
        assert ProjectStatus.IN_PROGRESS == "in_progress"
        assert ProjectStatus.COMPLETED == "completed"


# ============================================================
# State Management
# ============================================================

class TestStatePersistence:
    def test_save_and_load(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            loaded = load_project(project["project_id"])
            assert loaded is not None
            assert loaded["project_id"] == project["project_id"]
            assert len(loaded["phases"]) == len(project["phases"])

    def test_load_nonexistent(self, tmp_path):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            assert load_project("nonexistent-id") is None

    def test_list_projects_empty(self, tmp_path):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "empty")):
            assert list_projects() == []

    def test_list_projects(self, tmp_path):
        pdir = tmp_path / "projects"
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(pdir)):
            p1 = _make_project(tmp_path, project_id="proj-1")
            p2 = _make_project(tmp_path, project_id="proj-2")
            save_project(p1)
            save_project(p2)
            
            projects = list_projects()
            assert len(projects) == 2
            ids = {p["project_id"] for p in projects}
            assert "proj-1" in ids
            assert "proj-2" in ids

    def test_save_preserves_phases(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            project["phases"][0]["status"] = PhaseStatus.COMPLETED
            save_project(project)
            loaded = load_project(project["project_id"])
            assert loaded["phases"][0]["status"] == PhaseStatus.COMPLETED


# ============================================================
# Project Status Reporting
# ============================================================

class TestProjectStatus:
    def test_initial_status(self, project):
        s = project_status(project)
        assert s["phases"]["total"] == 3
        assert s["phases"]["completed"] == 0
        assert s["phases"]["pending"] == 3
        assert s["tasks"]["progress_pct"] == 0

    def test_partial_status(self, project):
        project["phases"][0]["status"] = PhaseStatus.COMPLETED
        for task in project["phases"][0]["tasks"]:
            task["status"] = PhaseStatus.COMPLETED
        
        s = project_status(project)
        assert s["phases"]["completed"] == 1
        assert s["tasks"]["completed"] == 2
        assert s["tasks"]["progress_pct"] > 0

    def test_current_phase(self, project):
        project["phases"][0]["status"] = PhaseStatus.COMPLETED
        s = project_status(project)
        assert s["current_phase"]["index"] == 1

    def test_all_complete(self, project):
        for phase in project["phases"]:
            phase["status"] = PhaseStatus.COMPLETED
            for task in phase["tasks"]:
                task["status"] = PhaseStatus.COMPLETED
        
        s = project_status(project)
        assert s["tasks"]["progress_pct"] == 100.0
        assert s["current_phase"] is None


class TestProjectReport:
    def test_report_has_name(self, project):
        report = project_report(project)
        assert "test-project" in report

    def test_report_shows_phases(self, project):
        report = project_report(project)
        assert "Phase 0" in report
        assert "Phase 1" in report
        assert "Phase 2" in report

    def test_report_shows_failed(self, project):
        project["phases"][1]["status"] = PhaseStatus.FAILED
        project["phases"][1]["tasks"][0]["status"] = PhaseStatus.FAILED
        project["phases"][1]["tasks"][0]["error"] = "Something went wrong"
        
        report = project_report(project)
        assert "FAILED" in report
        assert "Something went wrong" in report

    def test_report_shows_progress(self, project):
        project["phases"][0]["status"] = PhaseStatus.COMPLETED
        for task in project["phases"][0]["tasks"]:
            task["status"] = PhaseStatus.COMPLETED
        
        report = project_report(project)
        assert "✓" in report  # Completed phase icon


# ============================================================
# Phase Operations
# ============================================================

class TestPhaseOperations:
    def test_approve_phase(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            project["phases"][1]["status"] = PhaseStatus.REVIEW_NEEDED
            save_project(project)
            
            approve_phase(project, 1)
            assert project["phases"][1]["status"] == PhaseStatus.PENDING
            assert project["phases"][1].get("reviewed_at") is not None

    def test_approve_non_review_raises(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            with pytest.raises(ValueError, match="not REVIEW_NEEDED"):
                approve_phase(project, 0)

    def test_skip_phase(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            skip_phase(project, 1)
            assert project["phases"][1]["status"] == PhaseStatus.SKIPPED
            assert project["phases"][1]["completed_at"] is not None

    def test_skip_invalid_index(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            with pytest.raises(ValueError, match="out of range"):
                skip_phase(project, 99)

    def test_retry_failed_phase(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            # Set phase as failed
            project["phases"][0]["status"] = PhaseStatus.FAILED
            project["phases"][0]["tasks"][0]["status"] = PhaseStatus.FAILED
            project["phases"][0]["tasks"][0]["error"] = "original error"
            save_project(project)
            
            # Mock planner + executor to succeed
            mock_plan = {"steps": [{"description": "do thing"}]}
            mock_exec = {"success": True, "task_summary": "done"}
            mock_validate = {"verdict": "accept"}
            mock_registry = MagicMock()
            mock_registry.get_tool_descriptions.return_value = "mock tools"
            mock_registry.list_tools.return_value = ["mock_tool"]
            
            with patch("hands.project_orchestrator._get_plan_task", return_value=lambda **kw: mock_plan), \
                 patch("hands.project_orchestrator._get_execute_task", return_value=lambda **kw: mock_exec), \
                 patch("hands.project_orchestrator._get_validate", return_value=lambda **kw: mock_validate), \
                 patch("hands.tools.registry.create_default_registry", return_value=mock_registry):
                result = retry_phase(project, 0)
            
            # Tasks should be reset
            assert project["phases"][0]["tasks"][0]["error"] is None or \
                   project["phases"][0]["tasks"][0]["status"] == PhaseStatus.COMPLETED

    def test_retry_non_failed_raises(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            with pytest.raises(ValueError, match="not FAILED"):
                retry_phase(project, 0)


# ============================================================  
# Execution Flow
# ============================================================

class TestExecutePhase:
    def test_requires_previous_phases_done(self, tmp_path, project):
        """Can't execute phase 2 if phase 0 is pending."""
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            with pytest.raises(ValueError, match="phase 0"):
                execute_phase(project, 1)

    def test_human_review_gate(self, tmp_path, project):
        """Phase with requires_human_review stops and marks review_needed."""
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            project["phases"][0]["status"] = PhaseStatus.COMPLETED
            save_project(project)
            
            result = execute_phase(project, 1)  # Phase 1 requires review
            assert result["status"] == PhaseStatus.REVIEW_NEEDED

    def test_dry_run(self, tmp_path, project):
        """Dry run completes all tasks without executing."""
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            
            result = execute_phase(project, 0, dry_run=True)
            assert result["status"] == PhaseStatus.COMPLETED
            for task in result["tasks"]:
                assert task["status"] == PhaseStatus.COMPLETED
                assert task["result"]["dry_run"] is True

    def test_execute_with_mocked_planner(self, tmp_path, project):
        """Execute phase with mocked planner/executor."""
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            
            mock_plan = {"steps": [{"description": "step"}]}
            mock_exec = {"success": True, "task_summary": "done"}
            mock_validate = {"verdict": "accept"}
            mock_registry = MagicMock()
            mock_registry.get_tool_descriptions.return_value = "mock tools"
            mock_registry.list_tools.return_value = ["mock_tool"]
            
            with patch("hands.project_orchestrator._get_plan_task", return_value=lambda **kw: mock_plan), \
                 patch("hands.project_orchestrator._get_execute_task", return_value=lambda **kw: mock_exec), \
                 patch("hands.project_orchestrator._get_validate", return_value=lambda **kw: mock_validate), \
                 patch("hands.tools.registry.create_default_registry", return_value=mock_registry):
                result = execute_phase(project, 0)
            
            assert result["status"] == PhaseStatus.COMPLETED

    def test_task_failure_marks_phase_failed(self, tmp_path, project):
        """If a task fails, phase is marked as failed."""
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            
            # Make planner raise an error
            def raise_err(**kw):
                raise Exception("API error")
            with patch("hands.project_orchestrator._get_plan_task", return_value=raise_err):
                result = execute_phase(project, 0)
            
            assert result["status"] == PhaseStatus.FAILED

    def test_invalid_phase_index(self, tmp_path, project):
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            with pytest.raises(ValueError, match="out of range"):
                execute_phase(project, 99)


class TestExecuteProject:
    def test_full_dry_run(self, tmp_path):
        """Execute entire project in dry-run mode."""
        from hands.project_orchestrator import execute_project
        
        project = _make_project(tmp_path, num_phases=2)
        # Remove human review requirement for clean test
        for phase in project["phases"]:
            phase["requires_human_review"] = False

        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            execute_phase(project, 0, dry_run=True)
            execute_phase(project, 1, dry_run=True)
            
            assert project["phases"][0]["status"] == PhaseStatus.COMPLETED
            assert project["phases"][1]["status"] == PhaseStatus.COMPLETED

    def test_pauses_on_review(self, tmp_path):
        from hands.project_orchestrator import execute_project
        
        project = _make_project(tmp_path, num_phases=3)
        project["phases"][1]["requires_human_review"] = True
        
        with patch("hands.project_orchestrator.PROJECTS_DIR", str(tmp_path / "projects")):
            save_project(project)
            
            mock_plan = {"steps": [{"description": "step"}]}
            mock_exec = {"success": True, "task_summary": "done"}
            mock_validate = {"verdict": "accept"}
            mock_registry = MagicMock()
            mock_registry.get_tool_descriptions.return_value = "mock tools"
            mock_registry.list_tools.return_value = ["mock_tool"]
            
            with patch("hands.project_orchestrator._get_plan_task", return_value=lambda **kw: mock_plan), \
                 patch("hands.project_orchestrator._get_execute_task", return_value=lambda **kw: mock_exec), \
                 patch("hands.project_orchestrator._get_validate", return_value=lambda **kw: mock_validate), \
                 patch("hands.tools.registry.create_default_registry", return_value=mock_registry):
                result = execute_project(project)
            
            assert project["status"] == ProjectStatus.PAUSED
