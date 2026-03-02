"""Tests for the loop guard module."""

import pytest
from loop_guard import LoopGuard, LoopGuardError


class TestLoopGuardInit:
    """Initialization and defaults."""

    def test_creates_cleanly(self):
        guard = LoopGuard("test", daily_budget=2.0)
        assert guard.domain == "test"
        assert guard.total_rounds == 0
        assert guard.consecutive_failures == 0

    def test_initial_status_is_healthy(self):
        guard = LoopGuard("test")
        status = guard.get_status()
        assert status["healthy"] is True
        assert status["total_rounds"] == 0


class TestCheckBeforeRound:
    """Pre-round checks (cost velocity, budget exhaustion)."""

    def test_passes_with_budget(self):
        guard = LoopGuard("test", daily_budget=2.0, starting_spend=0.5)
        guard.check_before_round(1)  # should not raise

    def test_blocks_when_budget_exhausted(self):
        guard = LoopGuard("test", daily_budget=2.0, starting_spend=2.0)
        with pytest.raises(LoopGuardError) as exc:
            guard.check_before_round(1)
        assert exc.value.severity == "critical"
        assert "exhausted" in exc.value.reason.lower()

    def test_blocks_high_cost_velocity(self):
        guard = LoopGuard("test", daily_budget=2.0, starting_spend=0.0)
        # Simulate spending 1.8 of 2.0 in first 2 rounds
        guard.run_spend = 1.8
        guard.total_rounds = 2
        with pytest.raises(LoopGuardError) as exc:
            guard.check_before_round(3)
        assert "velocity" in exc.value.reason.lower()


class TestRecordRound:
    """Round recording and state tracking."""

    def test_records_question_and_score(self):
        guard = LoopGuard("test")
        guard.record_round("What is X?", 7.5, "accept", 0.01)
        assert guard.total_rounds == 1
        assert guard.questions == ["What is X?"]
        assert guard.scores == [7.5]

    def test_tracks_consecutive_failures(self):
        guard = LoopGuard("test")
        guard.record_round("Q1", 3.0, "reject", 0.01)
        assert guard.consecutive_failures == 1
        guard.record_round("Q2", 4.0, "reject", 0.01)
        assert guard.consecutive_failures == 2

    def test_resets_consecutive_failures_on_accept(self):
        guard = LoopGuard("test")
        guard.record_round("Q1", 3.0, "reject", 0.01)
        guard.record_round("Q2", 3.5, "reject", 0.01)
        guard.record_round("Q3", 7.0, "accept", 0.01)
        assert guard.consecutive_failures == 0

    def test_detects_similar_questions(self):
        guard = LoopGuard("test")
        guard.record_round("What are the latest Bitcoin ETF developments?", 7.0, "accept", 0.01)
        guard.record_round("What are the latest Bitcoin ETF updates?", 7.0, "accept", 0.01)
        assert guard.similar_question_count >= 1

    def test_accumulates_cost(self):
        guard = LoopGuard("test")
        guard.record_round("Q1", 7.0, "accept", 0.05)
        guard.record_round("Q2", 7.0, "accept", 0.03)
        assert abs(guard.run_spend - 0.08) < 0.001


class TestCheckAfterRound:
    """Post-round checks (failure detection, regression, etc.)."""

    def test_consecutive_failures_triggers(self):
        guard = LoopGuard("test")
        guard.record_round("Q1", 3.0, "reject", 0.01)
        guard.record_round("Q2", 2.5, "reject", 0.01)
        guard.record_round("Q3", 2.0, "reject", 0.01)
        with pytest.raises(LoopGuardError) as exc:
            guard.check_after_round()
        assert exc.value.severity == "critical"

    def test_similar_questions_triggers(self):
        guard = LoopGuard("test")
        guard.record_round("What is the state of AI in 2025?", 7.0, "accept", 0.01)
        guard.record_round("What is the state of AI in 2026?", 7.0, "accept", 0.01)
        # Need 2+ similar question detections
        guard.record_round("What is the state of AI in 2024?", 7.0, "accept", 0.01)
        with pytest.raises(LoopGuardError) as exc:
            guard.check_after_round()
        assert "looping" in exc.value.reason.lower()

    def test_same_error_repeated_triggers(self):
        guard = LoopGuard("test")
        guard.record_round("Q1", 0, "reject", 0.01, error="ConnectionError: timeout")
        guard.record_round("Q2", 0, "reject", 0.01, error="ConnectionError: timeout")
        with pytest.raises(LoopGuardError) as exc:
            guard.check_after_round()
        # Could trigger on consecutive failures or same error
        assert exc.value.severity == "critical"

    def test_healthy_rounds_pass(self):
        guard = LoopGuard("test")
        guard.record_round("What is Bitcoin?", 7.5, "accept", 0.01)
        guard.check_after_round()  # should not raise
        guard.record_round("How does Ethereum work?", 8.0, "accept", 0.01)
        guard.check_after_round()  # should not raise


class TestSummary:
    """Summary output."""

    def test_summary_on_empty(self):
        guard = LoopGuard("test")
        s = guard.summary()
        assert "healthy" in s
        assert "0" in s  # 0 rounds

    def test_summary_after_rounds(self):
        guard = LoopGuard("test")
        guard.record_round("Q1", 7.0, "accept", 0.05)
        guard.record_round("Q2", 8.0, "accept", 0.03)
        s = guard.summary()
        assert "2" in s  # 2 rounds
        assert "healthy" in s

    def test_summary_shows_issues(self):
        guard = LoopGuard("test")
        guard.record_round("Q1", 3.0, "reject", 0.01)
        guard.record_round("Q2", 2.0, "reject", 0.01)
        s = guard.summary()
        assert "2" in s  # 2 consecutive failures
