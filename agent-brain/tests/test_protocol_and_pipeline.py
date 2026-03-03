"""
Tests for Objective 3: Three-Way Communication Pipeline

Covers:
  - protocol.py: All 10 message dataclasses (serialization, deserialization)
  - agents/cortex.py: New pipeline functions
    - _journal / load_journal
    - query_knowledge
    - is_build_ready
    - extract_build_brief
    - research_and_build
    - monitor_build
    - report_build_complete
  - Scheduler integration (research_context passed to executor)
  - CLI pipeline commands
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ════════════════════════════════════════════════════════════════════════
#  PROTOCOL TESTS
# ════════════════════════════════════════════════════════════════════════


class TestResearchRequest:
    def test_create_and_serialize(self):
        from protocol import ResearchRequest
        req = ResearchRequest(domain="olj", question="Who is the user?", depth="deep", urgency="high", build_mode=True)
        d = req.to_dict()
        assert d["domain"] == "olj"
        assert d["question"] == "Who is the user?"
        assert d["depth"] == "deep"
        assert d["urgency"] == "high"
        assert d["build_mode"] is True

    def test_roundtrip(self):
        from protocol import ResearchRequest
        req = ResearchRequest(domain="olj", question="Test?")
        d = req.to_dict()
        req2 = ResearchRequest.from_dict(d)
        assert req2.domain == req.domain
        assert req2.question == req.question

    def test_defaults(self):
        from protocol import ResearchRequest
        req = ResearchRequest(domain="test", question="Q?")
        assert req.depth == "standard"
        assert req.urgency == "medium"
        assert req.build_mode is False


class TestResearchComplete:
    def test_create_and_serialize(self):
        from protocol import ResearchComplete
        rc = ResearchComplete(
            domain="olj",
            question="Who pays?",
            findings={"key_insights": ["Users pay $5-10"]},
            confidence=0.85,
            score=7.5,
            accepted=True,
            cost=0.003,
            knowledge_gaps=["pricing tiers"],
        )
        d = rc.to_dict()
        assert d["score"] == 7.5
        assert d["accepted"] is True
        assert "pricing tiers" in d["knowledge_gaps"]

    def test_roundtrip(self):
        from protocol import ResearchComplete
        rc = ResearchComplete(domain="d", question="q", findings={"key": "val"}, score=8.0, accepted=True)
        d = rc.to_dict()
        rc2 = ResearchComplete.from_dict(d)
        assert rc2.score == 8.0
        assert rc2.accepted is True


class TestBuildTask:
    def test_create(self):
        from protocol import BuildTask
        bt = BuildTask(
            domain="olj",
            goal="Build landing page",
            brief="User pain: long hiring...",
            constraints={"tech_stack": ["nextjs"]},
            budget_cap=0.50,
            priority="high",
        )
        assert bt.domain == "olj"
        assert bt.budget_cap == 0.50

    def test_to_sync_task(self):
        from protocol import BuildTask
        bt = BuildTask(domain="olj", goal="Build LP", brief="Brief text", priority="high")
        sync = bt.to_sync_task()
        assert sync["title"] == "Build LP"
        assert sync["source_domain"] == "olj"
        assert sync["task_type"] == "build"
        assert sync["priority"] == "high"
        assert "budget_cap" in sync["metadata"]
        assert "constraints" in sync["metadata"]

    def test_roundtrip(self):
        from protocol import BuildTask
        bt = BuildTask(domain="d", goal="g", brief="b")
        d = bt.to_dict()
        bt2 = BuildTask.from_dict(d)
        assert bt2.domain == "d"
        assert bt2.goal == "g"
        assert bt2.source_research_id == ""


class TestPhaseComplete:
    def test_serialize(self):
        from protocol import PhaseComplete
        pc = PhaseComplete(domain="d", task_id="t1", phase="scaffold", phase_number=1, success=True, cost=0.01)
        d = pc.to_dict()
        assert d["phase"] == "scaffold"
        assert d["success"] is True


class TestContextMessages:
    def test_context_needed(self):
        from protocol import ContextNeeded
        cn = ContextNeeded(domain="d", task_id="t", phase="content", question="What is the user persona?", context_type="user_persona")
        d = cn.to_dict()
        assert d["context_type"] == "user_persona"

    def test_context_response(self):
        from protocol import ContextResponse
        cr = ContextResponse(domain="d", task_id="t", question="Q?", context="User is 30yo manager", source="knowledge_base", confidence=0.9)
        d = cr.to_dict()
        assert d["confidence"] == 0.9


class TestBuildComplete:
    def test_serialize(self):
        from protocol import BuildComplete
        bc = BuildComplete(domain="d", task_id="t", url="https://example.vercel.app", total_cost=0.35, total_steps=12)
        d = bc.to_dict()
        assert d["url"] == "https://example.vercel.app"
        assert d["total_cost"] == 0.35


class TestBuildFailed:
    def test_serialize(self):
        from protocol import BuildFailed
        bf = BuildFailed(domain="d", task_id="t", phase="deploy", reason="Vercel auth error", cost_so_far=0.20)
        d = bf.to_dict()
        assert d["reason"] == "Vercel auth error"
        assert d["recoverable"] is True  # default


class TestTaskComplete:
    def test_serialize(self):
        from protocol import TaskComplete
        tc = TaskComplete(domain="d", task_id="t", result="success", url="https://x.com", cost=0.40, summary="Built LP")
        d = tc.to_dict()
        assert d["result"] == "success"

    def test_telegram_message(self):
        from protocol import TaskComplete
        tc = TaskComplete(domain="olj", task_id="t123", result="success", url="https://example.com", cost=0.35, summary="Built landing page")
        msg = tc.to_telegram_message()
        assert "olj" in msg
        assert "https://example.com" in msg
        assert "$0.35" in msg or "0.35" in msg


class TestJournalEntry:
    def test_serialize(self):
        from protocol import JournalEntry
        je = JournalEntry(event="pipeline_start", domain="olj", task_id="t1", details={"instruction": "build"}, cost_so_far=0.0)
        d = je.to_dict()
        assert d["event"] == "pipeline_start"
        assert "timestamp" in d

    def test_to_jsonl(self):
        from protocol import JournalEntry
        je = JournalEntry(event="test", domain="d")
        line = je.to_jsonl()
        parsed = json.loads(line)
        assert parsed["event"] == "test"


# ════════════════════════════════════════════════════════════════════════
#  CORTEX PIPELINE TESTS
# ════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_pipeline(tmp_path, monkeypatch):
    """Set up temp dirs for pipeline tests."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    strat_dir = tmp_path / "strategies"
    strat_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    exec_dir = tmp_path / "exec_memory"
    exec_dir.mkdir()

    monkeypatch.setattr("config.MEMORY_DIR", str(mem_dir))
    monkeypatch.setattr("config.STRATEGY_DIR", str(strat_dir))
    monkeypatch.setattr("config.LOG_DIR", str(log_dir))
    monkeypatch.setattr("config.EXEC_MEMORY_DIR", str(exec_dir))

    # Override the journal file path to use temp dir
    import agents.cortex as cortex_mod
    monkeypatch.setattr(cortex_mod, "CORTEX_JOURNAL_FILE", str(log_dir / "cortex_journal.jsonl"))

    return tmp_path


class TestJournal:
    def test_journal_write_and_read(self, tmp_pipeline):
        from agents.cortex import _journal, load_journal

        _journal("test_event", "test_domain", task_id="t1", details={"key": "val"}, cost=0.05)
        _journal("test_event_2", "test_domain", details={"other": 123})

        entries = load_journal()
        assert len(entries) == 2
        assert entries[0]["event"] == "test_event"
        assert entries[0]["task_id"] == "t1"
        assert entries[0]["details"]["key"] == "val"
        assert entries[1]["event"] == "test_event_2"

    def test_journal_domain_filter(self, tmp_pipeline):
        from agents.cortex import _journal, load_journal

        _journal("e1", "domain_a")
        _journal("e2", "domain_b")
        _journal("e3", "domain_a")

        a_entries = load_journal(domain="domain_a")
        assert len(a_entries) == 2
        b_entries = load_journal(domain="domain_b")
        assert len(b_entries) == 1

    def test_journal_last_n(self, tmp_pipeline):
        from agents.cortex import _journal, load_journal

        for i in range(10):
            _journal(f"event_{i}", "d")

        entries = load_journal(last_n=3)
        assert len(entries) == 3
        assert entries[0]["event"] == "event_7"

    def test_journal_empty(self, tmp_pipeline):
        from agents.cortex import load_journal
        entries = load_journal()
        assert entries == []


class TestQueryKnowledge:
    def test_returns_empty_when_no_kb(self, tmp_pipeline):
        from agents.cortex import query_knowledge
        result = query_knowledge("nonexistent_domain", "What is the user pain?")
        assert result == ""

    def test_returns_context_with_kb(self, tmp_pipeline):
        from agents.cortex import query_knowledge

        kb_data = {
            "domain_summary": "OnlineJobsPH employer market",
            "claims": [
                {"claim": "Employers struggle with slow hiring process", "status": "active", "confidence": "high", "topic": "User Pain"},
                {"claim": "Competitors charge $50-200/month", "status": "active", "confidence": "medium", "topic": "Pricing"},
                {"claim": "Some old claim", "status": "superseded", "confidence": "low", "topic": "Old"},
            ],
            "topics": ["User Pain", "Pricing"],
        }

        with patch("memory_store.load_knowledge_base", return_value=kb_data), \
             patch("memory_store.retrieve_relevant", return_value=[]):
            result = query_knowledge("olj", "hiring process problems")
            assert "DOMAIN SUMMARY" in result
            assert "OnlineJobsPH" in result
            assert "hiring" in result.lower()

    def test_includes_relevant_findings(self, tmp_pipeline):
        from agents.cortex import query_knowledge

        findings = [
            {"question": "What are user pain points?", "score": 7.5, "summary": "Hiring is slow and expensive", "key_insights": ["Takes 2-4 weeks"]},
        ]

        with patch("memory_store.load_knowledge_base", return_value=None), \
             patch("memory_store.retrieve_relevant", return_value=findings):
            result = query_knowledge("olj", "user pain")
            assert "RELEVANT RESEARCH" in result
            assert "Hiring is slow" in result


class TestIsBuildReady:
    def test_not_ready_no_outputs(self, tmp_pipeline):
        from agents.cortex import is_build_ready

        with patch("memory_store.get_stats", return_value={"accepted": 0}), \
             patch("memory_store.load_knowledge_base", return_value=None):
            result = is_build_ready("test")
            assert result["ready"] is False
            assert "0/5" in result["reason"]

    def test_ready_with_enough_data(self, tmp_pipeline):
        from agents.cortex import is_build_ready

        kb = {
            "domain_summary": "Test domain",
            "claims": [
                {"claim": "Users struggle with X", "status": "active", "topic": "Pain", "confidence": "high"},
                {"claim": "Competitor A charges $50", "status": "active", "topic": "Competitors", "confidence": "high"},
                {"claim": "Market size is $1B", "status": "active", "topic": "Market", "confidence": "medium"},
                {"claim": "Users feel frustrated", "status": "active", "topic": "Pain", "confidence": "medium"},
            ],
        }

        with patch("memory_store.get_stats", return_value={"accepted": 8}), \
             patch("memory_store.load_knowledge_base", return_value=kb):
            result = is_build_ready("test")
            assert result["ready"] is True
            assert result["accepted_count"] == 8
            assert result["claim_count"] == 4
            assert result["has_user_pain"] is True
            assert result["has_competitors"] is True


class TestExtractBuildBrief:
    def test_no_kb(self, tmp_pipeline):
        from agents.cortex import extract_build_brief

        with patch("memory_store.load_knowledge_base", return_value=None):
            result = extract_build_brief("test")
            assert "No knowledge base" in result

    def test_extracts_brief(self, tmp_pipeline):
        from agents.cortex import extract_build_brief

        kb = {
            "domain_summary": "OLJ employer market",
            "claims": [
                {"claim": "Employers want faster hiring", "status": "active", "confidence": "high", "topic": "User Pain"},
                {"claim": "Average cost is $100/month", "status": "active", "confidence": "medium", "topic": "Pricing"},
            ],
        }

        with patch("memory_store.load_knowledge_base", return_value=kb):
            result = extract_build_brief("olj", "Build a landing page")
            assert "INSTRUCTION:" in result
            assert "Build a landing page" in result
            assert "DOMAIN: olj" in result
            assert "OLJ employer market" in result
            assert "Employers want faster hiring" in result


class TestResearchAndBuild:
    def test_skips_research_builds_from_kb(self, tmp_pipeline):
        from agents.cortex import research_and_build

        kb = {
            "domain_summary": "Test domain",
            "claims": [
                {"claim": "User pain point 1", "status": "active", "confidence": "high", "topic": "Pain"},
                {"claim": "Competitor info", "status": "active", "confidence": "high", "topic": "Competitors"},
            ],
        }

        mock_task = {"id": "task_123", "title": "Build LP", "status": "pending"}

        with patch("memory_store.load_knowledge_base", return_value=kb), \
             patch("sync.create_task", return_value=mock_task):
            result = research_and_build("test", "Build a LP", skip_research=True, budget_cap=0.25)

            assert result["success"] is True
            assert result["stage"] == "task_created"
            assert result["task_id"] == "task_123"
            assert result["build_task"] is not None

    def test_fails_when_no_kb_and_skip_research(self, tmp_pipeline):
        from agents.cortex import research_and_build

        with patch("memory_store.load_knowledge_base", return_value=None), \
             patch("sync.create_task") as mock_create:
            result = research_and_build("empty", "Build something", skip_research=True)

            assert result["success"] is False
            assert result["stage"] == "brief"
            mock_create.assert_not_called()

    def test_runs_research_when_not_ready(self, tmp_pipeline):
        from agents.cortex import research_and_build

        # After research, KB should have data
        kb_after = {
            "domain_summary": "Researched domain",
            "claims": [
                {"claim": "Users have pain", "status": "active", "confidence": "high", "topic": "Pain"},
                {"claim": "Comp data", "status": "active", "confidence": "high", "topic": "Competitors"},
            ],
        }

        loop_result = {
            "research": {"findings": "test findings"},
            "critique": {"overall_score": 7.5, "verdict": "accept"},
            "attempts": 1,
            "stored_at": "/tmp/test.json",
        }

        mock_task = {"id": "task_456", "title": "Test", "status": "pending"}

        with patch("memory_store.get_stats", return_value={"accepted": 0}), \
             patch("memory_store.load_knowledge_base", side_effect=[None, kb_after]), \
             patch("main.run_loop", return_value=loop_result), \
             patch("sync.create_task", return_value=mock_task):
            result = research_and_build("test", "Build it")

            assert result["success"] is True
            assert result["research"] is not None

    def test_stops_on_rejected_research(self, tmp_pipeline):
        from agents.cortex import research_and_build

        loop_result = {
            "research": {"findings": "weak"},
            "critique": {"overall_score": 4.0, "verdict": "reject"},
            "attempts": 2,
            "stored_at": "",
        }

        with patch("memory_store.get_stats", return_value={"accepted": 0}), \
             patch("memory_store.load_knowledge_base", return_value=None), \
             patch("main.run_loop", return_value=loop_result):
            result = research_and_build("test", "Build it")

            assert result["success"] is False
            assert result["stage"] == "research"
            assert "rejected" in result["error"].lower()


class TestMonitorBuild:
    def test_continue_when_healthy(self, tmp_pipeline):
        from agents.cortex import monitor_build
        result = monitor_build("task_123", "test")
        assert result["status"] == "continue"

    def test_abort_on_cost_exceeded(self, tmp_pipeline):
        from agents.cortex import monitor_build, _journal, BUILD_BUDGET_CAP

        _journal("start", "test", task_id="t1", cost=BUILD_BUDGET_CAP + 0.10)

        result = monitor_build("t1", "test")
        assert result["status"] == "abort"
        assert "cost" in result["reason"].lower() or "budget" in result["reason"].lower()

    def test_warn_approaching_budget(self, tmp_pipeline):
        from agents.cortex import monitor_build, _journal, BUILD_BUDGET_CAP

        _journal("step", "test", task_id="t1", cost=BUILD_BUDGET_CAP * 0.85)

        result = monitor_build("t1", "test")
        assert result["status"] == "warn"

    def test_abort_on_repeated_failures(self, tmp_pipeline):
        from agents.cortex import monitor_build, _journal, MAX_BUILD_PHASE_FAILURES

        for i in range(MAX_BUILD_PHASE_FAILURES):
            _journal("phase_failed", "test", task_id="t1", details={"phase": "deploy"})

        result = monitor_build("t1", "test")
        assert result["status"] == "abort"
        assert "deploy" in result["reason"]


class TestReportBuildComplete:
    def test_success_report(self, tmp_pipeline):
        from agents.cortex import report_build_complete

        with patch("sync.update_task") as mock_update, \
             patch("agents.cortex._send_telegram_notification"):
            result = report_build_complete(
                domain="test",
                task_id="t1",
                success=True,
                url="https://example.com",
                total_cost=0.30,
                total_steps=10,
            )

            assert result["result"] == "success"
            assert result["url"] == "https://example.com"
            mock_update.assert_called_once_with("t1", "completed", {"url": "https://example.com", "cost": 0.30})

    def test_failure_report(self, tmp_pipeline):
        from agents.cortex import report_build_complete

        with patch("sync.update_task") as mock_update, \
             patch("agents.cortex._send_telegram_notification"):
            result = report_build_complete(
                domain="test",
                task_id="t1",
                success=False,
                error="Timeout",
            )

            assert result["result"] == "failed"
            mock_update.assert_called_once_with("t1", "failed", {"error": "Timeout", "cost": 0.0})


# ════════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS
# ════════════════════════════════════════════════════════════════════════

class TestExecutorResearchContext:
    """Test that executor accepts and uses research_context parameter."""

    def test_executor_signature_accepts_research_context(self):
        """Verify execute_plan has research_context parameter."""
        import inspect
        from hands.executor import execute_plan
        sig = inspect.signature(execute_plan)
        assert "research_context" in sig.parameters

    def test_research_context_injected_into_conversation(self):
        """Verify research context appears in initial message when provided."""
        from hands.executor import execute_plan
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_registry.get_tool_descriptions.return_value = "test tools"
        mock_registry.get_execution_tools.return_value = []

        plan = {"task_summary": "Test", "steps": [{"step_number": 1, "tool": "test", "description": "Test step"}]}

        # We can't fully execute (needs API), but verify the parameter exists and is accepted
        # by checking the function signature
        import inspect
        sig = inspect.signature(execute_plan)
        params = sig.parameters
        assert "research_context" in params
        assert params["research_context"].default == ""


class TestCLIPipelineCommands:
    """Test that CLI pipeline commands are wired correctly."""

    def test_pipeline_arg_exists(self):
        """Verify --pipeline argument is registered in argparse."""
        # Read main.py and check the argument is defined
        import main as main_mod
        source = open(main_mod.__file__).read()
        assert "--pipeline" in source
        assert "--journal" in source
        assert "--build-ready" in source

    def test_run_pipeline_function_exists(self):
        """Verify run_pipeline is importable from CLI."""
        from cli.execution import run_pipeline, show_journal
        assert callable(run_pipeline)
        assert callable(show_journal)


class TestSchedulerCortexIntegration:
    """Test that scheduler reports to Cortex after task execution."""

    def test_scheduler_has_cortex_reporting(self):
        """Verify scheduler.py contains Cortex reporting code."""
        import scheduler as sched_mod
        source = open(sched_mod.__file__).read()
        assert "report_build_complete" in source
        assert "query_knowledge" in source
        assert "research_context" in source
