"""
Tests for Watchdog — Continuous Health Monitoring & Circuit Breaker

Tests cover:
  - Lifecycle (start, stop, heartbeat)
  - Pre-cycle checks (all states)
  - Cycle recording (success, failure, cooldown)
  - Health check integration
  - Circuit breaker
  - Manual controls (pause, resume, kill)
  - State persistence
  - Status reporting
"""

import json
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from watchdog import (
    Watchdog, SystemState, WatchdogEvent,
    HEARTBEAT_TIMEOUT_SECONDS, CIRCUIT_BREAKER_THRESHOLD,
    MAX_CONSECUTIVE_FAILURES, FAILURE_COOLDOWN_SECONDS,
    HARD_COST_CEILING_USD, WATCHDOG_STATE_FILE,
    get_watchdog, get_watchdog_status,
)


@pytest.fixture
def watchdog(tmp_path, monkeypatch):
    """Create a Watchdog with isolated state file."""
    state_file = str(tmp_path / "watchdog_state.json")
    monkeypatch.setattr("watchdog.WATCHDOG_STATE_FILE", state_file)
    monkeypatch.setattr("watchdog.LOG_DIR", str(tmp_path))
    w = Watchdog()
    return w


@pytest.fixture
def running_watchdog(watchdog):
    """A started watchdog ready for testing."""
    watchdog.start()
    yield watchdog
    if watchdog._state != SystemState.STOPPED:
        watchdog.stop()


# ── Lifecycle Tests ────────────────────────────────────────────────────

class TestWatchdogLifecycle:
    def test_initial_state_is_stopped(self, watchdog):
        assert watchdog._state == SystemState.STOPPED

    def test_start_sets_running(self, watchdog):
        watchdog.start()
        assert watchdog._state == SystemState.RUNNING
        assert watchdog._started_at is not None
        watchdog.stop()

    def test_stop_sets_stopped(self, running_watchdog):
        running_watchdog.stop()
        assert running_watchdog._state == SystemState.STOPPED

    def test_start_records_event(self, watchdog):
        watchdog.start()
        events = watchdog.get_events()
        assert len(events) >= 1
        assert events[-1]["event_type"] == "watchdog_start"
        watchdog.stop()

    def test_stop_records_event(self, running_watchdog):
        running_watchdog.stop()
        events = running_watchdog.get_events()
        assert events[-1]["event_type"] == "watchdog_stop"


# ── Heartbeat Tests ───────────────────────────────────────────────────

class TestHeartbeat:
    def test_heartbeat_updates_timestamp(self, running_watchdog):
        old_hb = running_watchdog._last_heartbeat
        time.sleep(0.01)
        running_watchdog.heartbeat()
        assert running_watchdog._last_heartbeat > old_hb

    def test_not_stalled_when_running(self, running_watchdog):
        running_watchdog.heartbeat()
        assert running_watchdog.is_stalled() is False

    def test_stalled_after_timeout(self, running_watchdog, monkeypatch):
        # Simulate a very old heartbeat
        running_watchdog._last_heartbeat = time.monotonic() - HEARTBEAT_TIMEOUT_SECONDS - 1
        assert running_watchdog.is_stalled() is True

    def test_not_stalled_when_stopped(self, watchdog):
        assert watchdog.is_stalled() is False

    def test_not_stalled_when_paused(self, running_watchdog):
        running_watchdog.pause("test")
        running_watchdog._last_heartbeat = time.monotonic() - HEARTBEAT_TIMEOUT_SECONDS - 1
        assert running_watchdog.is_stalled() is False

    def test_heartbeat_age(self, running_watchdog):
        running_watchdog.heartbeat()
        age = running_watchdog.get_heartbeat_age()
        assert 0 <= age < 1.0  # Should be very recent

    def test_heartbeat_age_zero_when_never_started(self, watchdog):
        assert watchdog.get_heartbeat_age() == 0


# ── Pre-Cycle Checks ─────────────────────────────────────────────────

class TestPreCycleChecks:
    def test_stopped_cannot_proceed(self, watchdog):
        can, reason = watchdog.check_before_cycle()
        assert can is False
        assert "stopped" in reason.lower()

    def test_running_can_proceed(self, running_watchdog):
        with patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0}):
            can, reason = running_watchdog.check_before_cycle()
            assert can is True
            assert reason == "OK"

    def test_circuit_open_cannot_proceed(self, running_watchdog):
        running_watchdog._state = SystemState.CIRCUIT_OPEN
        running_watchdog._consecutive_critical_alerts = 5
        can, reason = running_watchdog.check_before_cycle()
        assert can is False
        assert "circuit breaker" in reason.lower()

    def test_budget_halt_cannot_proceed(self, running_watchdog):
        running_watchdog._state = SystemState.BUDGET_HALT
        can, reason = running_watchdog.check_before_cycle()
        assert can is False
        assert "cost ceiling" in reason.lower()

    def test_cooldown_blocks_until_expired(self, running_watchdog):
        running_watchdog._state = SystemState.COOLDOWN
        running_watchdog._cooldown_until = time.monotonic() + 3600
        can, reason = running_watchdog.check_before_cycle()
        assert can is False
        assert "cooling down" in reason.lower()

    def test_cooldown_resumes_after_expiry(self, running_watchdog):
        running_watchdog._state = SystemState.COOLDOWN
        running_watchdog._cooldown_until = time.monotonic() - 1  # Already expired
        with patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0}):
            can, reason = running_watchdog.check_before_cycle()
            assert can is True
            assert running_watchdog._state == SystemState.RUNNING

    def test_hard_cost_ceiling_triggers_halt(self, running_watchdog):
        with patch("cost_tracker.get_daily_spend",
                    return_value={"total_usd": HARD_COST_CEILING_USD + 1}):
            can, reason = running_watchdog.check_before_cycle()
            assert can is False
            assert running_watchdog._state == SystemState.BUDGET_HALT

    def test_cost_check_failure_allows_proceed(self, running_watchdog):
        """If cost check fails, proceed with caution (don't block on monitoring error)."""
        with patch("cost_tracker.get_daily_spend", side_effect=Exception("db error")):
            can, reason = running_watchdog.check_before_cycle()
            assert can is True

    def test_paused_resumes_on_check(self, running_watchdog):
        running_watchdog.pause("test pause")
        assert running_watchdog._state == SystemState.PAUSED
        with patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0}):
            can, reason = running_watchdog.check_before_cycle()
            assert can is True
            assert running_watchdog._state == SystemState.RUNNING


# ── Cycle Recording ──────────────────────────────────────────────────

class TestCycleRecording:
    def test_success_resets_failure_counter(self, running_watchdog):
        running_watchdog._consecutive_failures = 3
        running_watchdog.record_cycle_success(5, 7.5, 0.10)
        assert running_watchdog._consecutive_failures == 0

    def test_success_resets_critical_counter(self, running_watchdog):
        running_watchdog._consecutive_critical_alerts = 2
        running_watchdog.record_cycle_success(5, 7.5, 0.10)
        assert running_watchdog._consecutive_critical_alerts == 0

    def test_success_increments_cycle_count(self, running_watchdog):
        initial = running_watchdog._cycle_count
        running_watchdog.record_cycle_success(3, 7.0, 0.05)
        assert running_watchdog._cycle_count == initial + 1

    def test_success_tracks_total_rounds(self, running_watchdog):
        running_watchdog.record_cycle_success(3, 7.0, 0.05)
        running_watchdog.record_cycle_success(5, 7.5, 0.08)
        assert running_watchdog._total_rounds == 8

    def test_failure_increments_counter(self, running_watchdog):
        running_watchdog.record_cycle_failure("test error")
        assert running_watchdog._consecutive_failures == 1

    def test_max_failures_triggers_cooldown(self, running_watchdog):
        for i in range(MAX_CONSECUTIVE_FAILURES):
            running_watchdog.record_cycle_failure(f"error {i}")
        assert running_watchdog._state == SystemState.COOLDOWN
        assert running_watchdog._cooldown_until > time.monotonic()

    def test_failure_records_event(self, running_watchdog):
        running_watchdog.record_cycle_failure("test fail")
        events = running_watchdog.get_events()
        assert any(e["event_type"] == "cycle_failure" for e in events)

    def test_success_records_event(self, running_watchdog):
        running_watchdog.record_cycle_success(1, 8.0, 0.02)
        events = running_watchdog.get_events()
        assert any(e["event_type"] == "cycle_success" for e in events)


# ── Health Check Integration ─────────────────────────────────────────

class TestHealthCheckIntegration:
    def test_healthy_result_resets_critical(self, running_watchdog):
        running_watchdog._consecutive_critical_alerts = 2
        with patch("monitoring.run_health_check",
                    return_value={"status": "healthy", "checks": [],
                                  "alerts_generated": 0, "domains_checked": 1}):
            result = running_watchdog.run_health_check()
            assert result["status"] == "healthy"
            assert running_watchdog._consecutive_critical_alerts == 0

    def test_critical_increments_counter(self, running_watchdog):
        with patch("monitoring.run_health_check",
                    return_value={"status": "critical", "checks": [],
                                  "alerts_generated": 2, "domains_checked": 1}):
            running_watchdog.run_health_check()
            assert running_watchdog._consecutive_critical_alerts == 1

    def test_critical_trips_circuit_breaker(self, running_watchdog):
        mock_result = {"status": "critical", "checks": [],
                       "alerts_generated": 1, "domains_checked": 1}
        with patch("monitoring.run_health_check", return_value=mock_result):
            for _ in range(CIRCUIT_BREAKER_THRESHOLD):
                running_watchdog.run_health_check()
            assert running_watchdog._state == SystemState.CIRCUIT_OPEN

    def test_warning_does_not_reset_critical(self, running_watchdog):
        running_watchdog._consecutive_critical_alerts = 1
        with patch("monitoring.run_health_check",
                    return_value={"status": "warning", "checks": [],
                                  "alerts_generated": 1, "domains_checked": 1}):
            running_watchdog.run_health_check()
            assert running_watchdog._consecutive_critical_alerts == 1

    def test_health_check_error_handled(self, running_watchdog):
        with patch("monitoring.run_health_check",
                    side_effect=Exception("monitoring broken")):
            result = running_watchdog.run_health_check()
            assert "error" in result


# ── Manual Controls ──────────────────────────────────────────────────

class TestManualControls:
    def test_pause(self, running_watchdog):
        running_watchdog.pause("maintenance")
        assert running_watchdog._state == SystemState.PAUSED
        assert running_watchdog._paused_reason == "maintenance"

    def test_resume_from_pause(self, running_watchdog):
        running_watchdog.pause("test")
        running_watchdog.resume()
        assert running_watchdog._state == SystemState.RUNNING
        assert running_watchdog._paused_reason is None

    def test_resume_from_circuit_breaker(self, running_watchdog):
        running_watchdog._state = SystemState.CIRCUIT_OPEN
        running_watchdog._consecutive_critical_alerts = 5
        running_watchdog.resume()
        assert running_watchdog._state == SystemState.RUNNING
        assert running_watchdog._consecutive_critical_alerts == 0

    def test_resume_resets_failures(self, running_watchdog):
        running_watchdog._consecutive_failures = 10
        running_watchdog.resume()
        assert running_watchdog._consecutive_failures == 0

    def test_kill_switch(self, running_watchdog):
        running_watchdog.kill("emergency")
        assert running_watchdog._state == SystemState.STOPPED
        events = running_watchdog.get_events()
        assert events[-1]["event_type"] == "kill_switch"

    def test_kill_records_critical_event(self, running_watchdog):
        running_watchdog.kill("test kill")
        events = running_watchdog.get_events()
        kill_events = [e for e in events if e["event_type"] == "kill_switch"]
        assert len(kill_events) == 1
        assert kill_events[0]["severity"] == "critical"


# ── State Persistence ────────────────────────────────────────────────

class TestStatePersistence:
    def test_state_saved_on_event(self, watchdog, tmp_path, monkeypatch):
        state_file = str(tmp_path / "watchdog_state.json")
        monkeypatch.setattr("watchdog.WATCHDOG_STATE_FILE", state_file)
        watchdog.start()
        assert os.path.exists(state_file)
        with open(state_file) as f:
            data = json.load(f)
        assert data["state"] == "running"
        watchdog.stop()

    def test_state_restored_on_init(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / "watchdog_state.json")
        monkeypatch.setattr("watchdog.WATCHDOG_STATE_FILE", state_file)
        monkeypatch.setattr("watchdog.LOG_DIR", str(tmp_path))

        # Save state with some history
        state = {
            "consecutive_failures": 3,
            "consecutive_critical_alerts": 1,
            "events": [{"event_type": "test", "message": "restored",
                        "timestamp": "2026-01-01T00:00:00", "severity": "info",
                        "details": {}}],
            "cycle_count": 10,
            "total_rounds": 42,
        }
        with open(state_file, "w") as f:
            json.dump(state, f)

        w = Watchdog()
        assert w._consecutive_failures == 3
        assert w._consecutive_critical_alerts == 1
        assert w._cycle_count == 10
        assert w._total_rounds == 42
        assert len(w._events) == 1

    def test_corrupt_state_starts_fresh(self, tmp_path, monkeypatch):
        state_file = str(tmp_path / "watchdog_state.json")
        monkeypatch.setattr("watchdog.WATCHDOG_STATE_FILE", state_file)
        monkeypatch.setattr("watchdog.LOG_DIR", str(tmp_path))

        with open(state_file, "w") as f:
            f.write("not json")

        w = Watchdog()
        assert w._consecutive_failures == 0
        assert w._state == SystemState.STOPPED


# ── Status Reporting ─────────────────────────────────────────────────

class TestStatusReporting:
    def test_status_includes_state(self, running_watchdog):
        with patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0.50}):
            with patch("cost_tracker.check_budget", return_value={
                "within_budget": True, "remaining": 1.50
            }):
                with patch("agents.orchestrator.get_system_health", return_value={
                    "health_score": 85
                }):
                    status = running_watchdog.get_status()
        assert status["state"] == "running"
        assert status["started_at"] is not None

    def test_status_includes_budget(self, running_watchdog):
        with patch("cost_tracker.get_daily_spend", return_value={"total_usd": 1.00}):
            with patch("cost_tracker.check_budget", return_value={
                "within_budget": True, "remaining": 1.00
            }):
                with patch("agents.orchestrator.get_system_health", return_value={
                    "health_score": 80
                }):
                    status = running_watchdog.get_status()
        assert "budget" in status
        assert status["budget"]["spent_today"] == 1.00

    def test_events_limited_to_count(self, running_watchdog):
        events = running_watchdog.get_events(count=5)
        assert len(events) <= 5

    def test_status_handles_import_errors(self, running_watchdog):
        """Status should not crash even if subsystems fail."""
        with patch("cost_tracker.get_daily_spend", side_effect=Exception("db error")):
            with patch("agents.orchestrator.get_system_health", side_effect=Exception("err")):
                status = running_watchdog.get_status()
        assert status["state"] == "running"
        assert "error" in status["budget"]


# ── WatchdogEvent ────────────────────────────────────────────────────

class TestWatchdogEvent:
    def test_to_dict(self):
        evt = WatchdogEvent("test_type", "test message", "warning", {"key": "val"})
        d = evt.to_dict()
        assert d["event_type"] == "test_type"
        assert d["message"] == "test message"
        assert d["severity"] == "warning"
        assert d["details"]["key"] == "val"
        assert "timestamp" in d

    def test_default_severity(self):
        evt = WatchdogEvent("test", "msg")
        assert evt.severity == "info"

    def test_default_details(self):
        evt = WatchdogEvent("test", "msg")
        assert evt.details == {}


# ── Singleton ────────────────────────────────────────────────────────

class TestSingleton:
    def test_get_watchdog_returns_same_instance(self, monkeypatch):
        import watchdog as wd_mod
        monkeypatch.setattr(wd_mod, "_watchdog", None)
        w1 = get_watchdog()
        w2 = get_watchdog()
        assert w1 is w2

    def test_get_watchdog_status_returns_dict(self, monkeypatch):
        import watchdog as wd_mod
        monkeypatch.setattr(wd_mod, "_watchdog", None)
        with patch.object(Watchdog, "get_status", return_value={"state": "stopped"}):
            status = get_watchdog_status()
            assert isinstance(status, dict)
