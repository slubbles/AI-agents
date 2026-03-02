"""
Phase 7: Cortex Orchestrator in the Loop — Tests

Tests for:
1. Cortex journal (append, read)
2. cortex_plan_cycle (budget gating, LLM mocking, error tolerance)
3. _apply_cortex_priorities (plan allocation adjustment)
4. cortex_interpret_cycle (post-cycle interpretation, budget gating)
5. cortex_daily_assessment (once-per-day gate, budget gating)
6. Daemon report includes cortex section
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# 1. Cortex Journal Tests
# ============================================================

class TestCortexJournal:
    """Test _append_cortex_journal and get_cortex_journal."""

    def test_append_creates_file(self, tmp_path):
        """Appending a journal entry creates the JSONL file."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import _append_cortex_journal
            _append_cortex_journal({"type": "cycle_plan", "cycle": 1})
            assert os.path.exists(journal_file)
            with open(journal_file) as f:
                lines = f.readlines()
            assert len(lines) == 1
            record = json.loads(lines[0])
            assert record["type"] == "cycle_plan"
            assert record["cycle"] == 1

    def test_append_is_additive(self, tmp_path):
        """Multiple appends create multiple lines."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import _append_cortex_journal
            _append_cortex_journal({"type": "cycle_plan", "cycle": 1})
            _append_cortex_journal({"type": "cycle_interpretation", "cycle": 1})
            _append_cortex_journal({"type": "daily_assessment", "date": "2026-03-03"})
            with open(journal_file) as f:
                lines = f.readlines()
            assert len(lines) == 3

    def test_get_journal_empty(self, tmp_path):
        """get_cortex_journal returns [] when file missing."""
        journal_file = str(tmp_path / "nonexistent.jsonl")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file):
            from scheduler import get_cortex_journal
            assert get_cortex_journal() == []

    def test_get_journal_last_n(self, tmp_path):
        """get_cortex_journal returns last N entries."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with open(journal_file, "w") as f:
            for i in range(10):
                f.write(json.dumps({"cycle": i}) + "\n")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file):
            from scheduler import get_cortex_journal
            entries = get_cortex_journal(last_n=3)
            assert len(entries) == 3
            assert entries[0]["cycle"] == 7
            assert entries[2]["cycle"] == 9

    def test_get_journal_handles_corrupt_lines(self, tmp_path):
        """get_cortex_journal skips corrupt JSON lines."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with open(journal_file, "w") as f:
            f.write(json.dumps({"cycle": 1}) + "\n")
            f.write("not valid json\n")
            f.write(json.dumps({"cycle": 3}) + "\n")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file):
            from scheduler import get_cortex_journal
            entries = get_cortex_journal(last_n=10)
            assert len(entries) == 2
            assert entries[0]["cycle"] == 1
            assert entries[1]["cycle"] == 3


# ============================================================
# 2. cortex_plan_cycle Tests
# ============================================================

class TestCortexPlanCycle:
    """Test cortex_plan_cycle budget gating and LLM integration."""

    def test_budget_gate_skips_when_low(self, tmp_path):
        """cortex_plan_cycle returns None when budget < $0.20."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import cortex_plan_cycle
            result = cortex_plan_cycle(cycle=1, budget_remaining=0.10)
            assert result is None

    def test_budget_gate_allows_when_sufficient(self, tmp_path):
        """cortex_plan_cycle calls Cortex when budget >= $0.20."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        mock_plan_result = {
            "interpretation": "System healthy, focus on AI domain.",
            "key_insights": ["AI domain has highest ROI", "Budget on track"],
            "recommended_actions": [
                {"type": "brain_research", "domain": "ai", "priority": "high"},
                {"type": "brain_research", "domain": "crypto", "priority": "low"},
            ],
            "risks": [],
            "system_health": "healthy",
            "next_question": "Should we expand to new domains?",
        }
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("agents.cortex.plan_next_actions", return_value=mock_plan_result):
            from scheduler import cortex_plan_cycle
            result = cortex_plan_cycle(cycle=1, budget_remaining=1.50)
            assert result is not None
            assert result["system_health"] == "healthy"
            assert "ai" in result["focus_domains"]
            assert len(result["insights"]) == 2
            assert "brain_research" in result["action_types"]

    def test_plan_logs_to_journal(self, tmp_path):
        """cortex_plan_cycle writes to cortex_journal.jsonl."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        mock_result = {
            "interpretation": "All good",
            "key_insights": ["insight1"],
            "recommended_actions": [
                {"type": "research", "domain": "ai", "priority": "critical"},
            ],
            "risks": [],
            "system_health": "healthy",
        }
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("agents.cortex.plan_next_actions", return_value=mock_result):
            from scheduler import cortex_plan_cycle
            cortex_plan_cycle(cycle=5, budget_remaining=1.00)
            
            assert os.path.exists(journal_file)
            with open(journal_file) as f:
                entry = json.loads(f.readline())
            assert entry["type"] == "cycle_plan"
            assert entry["cycle"] == 5
            assert entry["system_health"] == "healthy"

    def test_plan_handles_llm_error(self, tmp_path):
        """cortex_plan_cycle returns None on LLM error, doesn't crash."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("agents.cortex.plan_next_actions", side_effect=Exception("API down")):
            from scheduler import cortex_plan_cycle
            result = cortex_plan_cycle(cycle=1, budget_remaining=1.00)
            assert result is None

    def test_plan_handles_error_response(self, tmp_path):
        """cortex_plan_cycle returns None when Cortex returns error."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        error_result = {"error": "LLM parse failed"}
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("agents.cortex.plan_next_actions", return_value=error_result):
            from scheduler import cortex_plan_cycle
            result = cortex_plan_cycle(cycle=1, budget_remaining=1.00)
            assert result is None

    def test_plan_extracts_focus_domains(self, tmp_path):
        """cortex_plan_cycle correctly identifies high/critical priority domains."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        mock_result = {
            "interpretation": "Focus needed",
            "key_insights": [],
            "recommended_actions": [
                {"type": "research", "domain": "ai", "priority": "critical"},
                {"type": "research", "domain": "seo", "priority": "high"},
                {"type": "review", "domain": "crypto", "priority": "low"},
            ],
            "system_health": "warning",
        }
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("agents.cortex.plan_next_actions", return_value=mock_result):
            from scheduler import cortex_plan_cycle
            result = cortex_plan_cycle(cycle=1, budget_remaining=1.00)
            assert "ai" in result["focus_domains"]
            assert "seo" in result["focus_domains"]
            assert "crypto" not in result["focus_domains"]


# ============================================================
# 3. _apply_cortex_priorities Tests
# ============================================================

class TestApplyCortexPriorities:
    """Test _apply_cortex_priorities plan adjustment."""

    def test_boosts_focus_domain(self):
        """Focus domain gets +1 round from a donor."""
        from scheduler import _apply_cortex_priorities
        plan = {
            "executable": True,
            "allocation": [
                {"domain": "ai", "rounds": 2},
                {"domain": "seo", "rounds": 3},
                {"domain": "crypto", "rounds": 2},
            ],
        }
        cortex_plan = {"focus_domains": ["ai"]}
        _apply_cortex_priorities(plan, cortex_plan)
        
        alloc = {a["domain"]: a["rounds"] for a in plan["allocation"]}
        # AI should be boosted
        assert alloc["ai"] == 3
        # One donor should have lost a round
        assert alloc["seo"] + alloc["crypto"] == 4  # was 5, now 4

    def test_no_boost_when_no_donors(self):
        """No changes when all non-focus domains have rounds=1."""
        from scheduler import _apply_cortex_priorities
        plan = {
            "executable": True,
            "allocation": [
                {"domain": "ai", "rounds": 1},
                {"domain": "seo", "rounds": 1},
            ],
        }
        cortex_plan = {"focus_domains": ["ai"]}
        _apply_cortex_priorities(plan, cortex_plan)
        
        alloc = {a["domain"]: a["rounds"] for a in plan["allocation"]}
        assert alloc["ai"] == 1
        assert alloc["seo"] == 1

    def test_no_boost_for_unknown_domain(self):
        """Focus domain not in plan is ignored."""
        from scheduler import _apply_cortex_priorities
        plan = {
            "executable": True,
            "allocation": [
                {"domain": "ai", "rounds": 3},
                {"domain": "seo", "rounds": 2},
            ],
        }
        cortex_plan = {"focus_domains": ["blockchain"]}
        _apply_cortex_priorities(plan, cortex_plan)
        
        alloc = {a["domain"]: a["rounds"] for a in plan["allocation"]}
        assert alloc["ai"] == 3
        assert alloc["seo"] == 2

    def test_empty_focus_domains_noop(self):
        """Empty focus_domains is a no-op."""
        from scheduler import _apply_cortex_priorities
        plan = {
            "executable": True,
            "allocation": [{"domain": "ai", "rounds": 3}],
        }
        _apply_cortex_priorities(plan, {"focus_domains": []})
        assert plan["allocation"][0]["rounds"] == 3

    def test_multiple_focus_domains(self):
        """Multiple focus domains each get boosted."""
        from scheduler import _apply_cortex_priorities
        plan = {
            "executable": True,
            "allocation": [
                {"domain": "ai", "rounds": 2},
                {"domain": "seo", "rounds": 2},
                {"domain": "crypto", "rounds": 3},
                {"domain": "devops", "rounds": 2},
            ],
        }
        cortex_plan = {"focus_domains": ["ai", "seo"]}
        _apply_cortex_priorities(plan, cortex_plan)
        
        alloc = {a["domain"]: a["rounds"] for a in plan["allocation"]}
        assert alloc["ai"] == 3  # boosted
        assert alloc["seo"] == 3  # boosted
        total = sum(alloc.values())
        assert total == 9  # same total as before


# ============================================================
# 4. cortex_interpret_cycle Tests
# ============================================================

class TestCortexInterpretCycle:
    """Test cortex_interpret_cycle post-cycle analysis."""

    def test_budget_gate_skips_when_low(self, tmp_path):
        """cortex_interpret_cycle returns None when budget < $0.15."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("scheduler.check_budget", return_value={"remaining": 0.05}):
            from scheduler import cortex_interpret_cycle
            result = cortex_interpret_cycle(
                cycle=1, domain_results=[], cycle_avg=7.0,
                cycle_cost=0.05, duration_seconds=120,
            )
            assert result is None

    def test_successful_interpretation(self, tmp_path):
        """cortex_interpret_cycle calls query_orchestrator and logs result."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        mock_result = {
            "interpretation": "Cycle showed strong improvement in AI domain.",
            "key_insights": ["AI scores improving", "Budget efficient"],
            "recommended_actions": [{"type": "continue", "domain": "ai", "priority": "high"}],
            "system_health": "healthy",
        }
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("scheduler.check_budget", return_value={"remaining": 1.50}), \
             patch("agents.cortex.query_orchestrator", return_value=mock_result):
            from scheduler import cortex_interpret_cycle
            domain_results = [
                {"domain": "ai", "rounds_completed": 3, "avg_score": 7.5},
            ]
            result = cortex_interpret_cycle(
                cycle=2, domain_results=domain_results, cycle_avg=7.5,
                cycle_cost=0.08, duration_seconds=300,
            )
            assert result is not None
            assert result["system_health"] == "healthy"
            
            # Verify journal entry
            with open(journal_file) as f:
                entry = json.loads(f.readline())
            assert entry["type"] == "cycle_interpretation"
            assert entry["cycle"] == 2
            assert entry["cycle_avg"] == 7.5

    def test_handles_llm_error(self, tmp_path):
        """cortex_interpret_cycle returns None on error, daemon continues."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("scheduler.check_budget", return_value={"remaining": 1.50}), \
             patch("agents.cortex.query_orchestrator", side_effect=RuntimeError("boom")):
            from scheduler import cortex_interpret_cycle
            result = cortex_interpret_cycle(
                cycle=1, domain_results=[], cycle_avg=5.0,
                cycle_cost=0.03, duration_seconds=60,
            )
            assert result is None


# ============================================================
# 5. cortex_daily_assessment Tests
# ============================================================

class TestCortexDailyAssessment:
    """Test cortex_daily_assessment once-per-day gate."""

    def test_runs_first_time(self, tmp_path):
        """Daily assessment runs when no previous assessment today."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        mock_result = {
            "interpretation": "System operating well overall.",
            "key_insights": ["Scores improving", "Budget sustainable"],
            "recommended_actions": [],
            "risks": ["scoring drift possible"],
            "system_health": "healthy",
        }
        import scheduler
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("scheduler.check_budget", return_value={"remaining": 1.50}), \
             patch("agents.cortex.assess_system", return_value=mock_result), \
             patch.object(scheduler, "_last_daily_assessment_date", None):
            from scheduler import cortex_daily_assessment
            result = cortex_daily_assessment(cycle=10)
            assert result is not None
            assert result["system_health"] == "healthy"
            
            # Journal should have the assessment
            with open(journal_file) as f:
                entry = json.loads(f.readline())
            assert entry["type"] == "daily_assessment"

    def test_skips_if_already_done_today(self, tmp_path):
        """Daily assessment returns None if already done today."""
        import scheduler
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with patch.object(scheduler, "_last_daily_assessment_date", today):
            from scheduler import cortex_daily_assessment
            result = cortex_daily_assessment(cycle=10)
            assert result is None

    def test_budget_gate_skips_when_low(self, tmp_path):
        """Daily assessment skipped when budget < $0.25."""
        import scheduler
        with patch.object(scheduler, "_last_daily_assessment_date", None), \
             patch("scheduler.check_budget", return_value={"remaining": 0.10}):
            from scheduler import cortex_daily_assessment
            result = cortex_daily_assessment(cycle=1)
            assert result is None

    def test_handles_llm_error(self, tmp_path):
        """Daily assessment returns None on LLM error."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        import scheduler
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch.object(scheduler, "_last_daily_assessment_date", None), \
             patch("scheduler.check_budget", return_value={"remaining": 1.50}), \
             patch("agents.cortex.assess_system", side_effect=Exception("timeout")):
            from scheduler import cortex_daily_assessment
            result = cortex_daily_assessment(cycle=1)
            assert result is None


# ============================================================
# 6. Daemon Report Includes Cortex Section
# ============================================================

class TestDaemonReportCortex:
    """Verify generate_daemon_report includes cortex journal data."""

    def test_report_has_cortex_key(self, tmp_path):
        """Daemon report includes 'cortex' section."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        import scheduler
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("scheduler.CYCLE_HISTORY_FILE", str(tmp_path / "cycles.jsonl")), \
             patch("scheduler._load_daemon_state", return_value={"status": "idle"}), \
             patch("scheduler._daemon_running", False), \
             patch.object(scheduler, "_last_daily_assessment_date", "2026-03-03"):
            from scheduler import generate_daemon_report
            report = generate_daemon_report()
            assert "cortex" in report
            assert report["cortex"]["total_entries"] == 0
            assert report["cortex"]["last_assessment_date"] == "2026-03-03"

    def test_report_includes_journal_entries(self, tmp_path):
        """Daemon report shows recent cortex journal entries."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        # Write some journal entries
        with open(journal_file, "w") as f:
            for i in range(3):
                f.write(json.dumps({"type": "cycle_plan", "cycle": i}) + "\n")
        
        import scheduler
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("scheduler.CYCLE_HISTORY_FILE", str(tmp_path / "cycles.jsonl")), \
             patch("scheduler._load_daemon_state", return_value={"status": "idle"}), \
             patch("scheduler._daemon_running", False), \
             patch.object(scheduler, "_last_daily_assessment_date", None):
            from scheduler import generate_daemon_report
            report = generate_daemon_report()
            assert report["cortex"]["total_entries"] == 3
            assert len(report["cortex"]["recent_entries"]) == 3


# ============================================================
# 7. Integration — Cortex Plan Influences Allocation
# ============================================================

class TestCortexPlanInfluencesAllocation:
    """Integration-level: verify cortex_plan → _apply_cortex_priorities chain."""

    def test_plan_result_is_usable_by_apply(self, tmp_path):
        """The dict returned by cortex_plan_cycle works with _apply_cortex_priorities."""
        journal_file = str(tmp_path / "cortex_journal.jsonl")
        mock_result = {
            "interpretation": "Focus AI",
            "key_insights": ["AI strong"],
            "recommended_actions": [
                {"type": "research", "domain": "ai", "priority": "high"},
            ],
            "system_health": "healthy",
        }
        with patch("scheduler.CORTEX_JOURNAL_FILE", journal_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)), \
             patch("agents.cortex.plan_next_actions", return_value=mock_result):
            from scheduler import cortex_plan_cycle, _apply_cortex_priorities
            
            cortex = cortex_plan_cycle(cycle=1, budget_remaining=1.00)
            assert cortex is not None
            
            # Now apply to a plan
            plan = {
                "executable": True,
                "allocation": [
                    {"domain": "ai", "rounds": 2},
                    {"domain": "seo", "rounds": 3},
                ],
            }
            _apply_cortex_priorities(plan, cortex)
            alloc = {a["domain"]: a["rounds"] for a in plan["allocation"]}
            assert alloc["ai"] == 3  # boosted
            assert alloc["seo"] == 2  # donated
