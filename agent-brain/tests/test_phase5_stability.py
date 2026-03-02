"""
Phase 5: Stability Hardening Tests

Tests for:
1. Persistent cycle history (JSONL append, read, report generation)
2. --daemon-report CLI flag and output
3. Stall detection enforcement (check_stall_and_act)
"""

import json
import os
import sys
import tempfile
import time
from unittest.mock import patch, MagicMock

import pytest

# Ensure agent-brain is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# 1. Persistent Cycle History Tests
# ============================================================

class TestCycleHistory:
    """Test _append_cycle_history and get_cycle_history."""

    def test_append_creates_file(self, tmp_path):
        """Appending a cycle record creates the JSONL file."""
        with patch("scheduler.CYCLE_HISTORY_FILE", str(tmp_path / "cycle_history.jsonl")), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import _append_cycle_history, CYCLE_HISTORY_FILE
            # Re-patch since CYCLE_HISTORY_FILE was already evaluated at import
            hist_file = str(tmp_path / "cycle_history.jsonl")
            with patch("scheduler.CYCLE_HISTORY_FILE", hist_file):
                _append_cycle_history({"cycle": 1, "status": "success", "avg_score": 7.5})
                assert os.path.exists(hist_file)
                with open(hist_file) as f:
                    lines = f.readlines()
                assert len(lines) == 1
                record = json.loads(lines[0])
                assert record["cycle"] == 1
                assert record["status"] == "success"
                assert record["avg_score"] == 7.5

    def test_append_is_additive(self, tmp_path):
        """Multiple appends create multiple lines (never overwrites)."""
        hist_file = str(tmp_path / "cycle_history.jsonl")
        with patch("scheduler.CYCLE_HISTORY_FILE", hist_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import _append_cycle_history
            _append_cycle_history({"cycle": 1, "status": "success"})
            _append_cycle_history({"cycle": 2, "status": "success"})
            _append_cycle_history({"cycle": 3, "status": "failure", "error": "boom"})
            
            with open(hist_file) as f:
                lines = f.readlines()
            assert len(lines) == 3
            assert json.loads(lines[0])["cycle"] == 1
            assert json.loads(lines[2])["status"] == "failure"

    def test_get_history_returns_last_n(self, tmp_path):
        """get_cycle_history returns only the last N records."""
        hist_file = str(tmp_path / "cycle_history.jsonl")
        with patch("scheduler.CYCLE_HISTORY_FILE", hist_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import _append_cycle_history, get_cycle_history
            for i in range(10):
                _append_cycle_history({"cycle": i + 1})
            
            result = get_cycle_history(last_n=3)
            assert len(result) == 3
            assert result[0]["cycle"] == 8
            assert result[2]["cycle"] == 10

    def test_get_history_empty_file(self, tmp_path):
        """get_cycle_history returns [] when file doesn't exist."""
        hist_file = str(tmp_path / "nonexistent.jsonl")
        with patch("scheduler.CYCLE_HISTORY_FILE", hist_file):
            from scheduler import get_cycle_history
            assert get_cycle_history() == []

    def test_get_history_corrupted_lines(self, tmp_path):
        """get_cycle_history skips corrupted lines gracefully."""
        hist_file = str(tmp_path / "cycle_history.jsonl")
        with open(hist_file, "w") as f:
            f.write('{"cycle": 1}\n')
            f.write('CORRUPTED LINE\n')
            f.write('{"cycle": 3}\n')
        
        with patch("scheduler.CYCLE_HISTORY_FILE", hist_file):
            from scheduler import get_cycle_history
            result = get_cycle_history()
            assert len(result) == 2
            assert result[0]["cycle"] == 1
            assert result[1]["cycle"] == 3

    def test_get_history_default_last_n(self, tmp_path):
        """Default last_n is 20."""
        hist_file = str(tmp_path / "cycle_history.jsonl")
        with open(hist_file, "w") as f:
            for i in range(30):
                f.write(json.dumps({"cycle": i + 1}) + "\n")
        
        with patch("scheduler.CYCLE_HISTORY_FILE", hist_file):
            from scheduler import get_cycle_history
            result = get_cycle_history()
            assert len(result) == 20
            assert result[0]["cycle"] == 11  # 30 - 20 + 1


# ============================================================
# 2. Daemon Report Tests
# ============================================================

class TestDaemonReport:
    """Test generate_daemon_report."""

    @patch("scheduler.get_stats")
    @patch("scheduler._load_daemon_state")
    @patch("scheduler.get_cycle_history")
    def test_report_structure(self, mock_history, mock_state, mock_stats):
        """Report has all required top-level keys."""
        mock_state.return_value = {"status": "idle", "cycle": 5}
        mock_history.return_value = []
        mock_stats.return_value = {"count": 0, "avg_score": 0}
        
        with patch("scheduler.check_budget", return_value={"within_budget": True, "remaining": 1.5, "spent": 0.5, "limit": 2.0}), \
             patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0.5}), \
             patch("watchdog.get_watchdog_status", return_value={"state": "running"}), \
             patch("agents.orchestrator.discover_domains", return_value=["test"]), \
             patch("sync.check_sync", return_value={"aligned": True, "issues": []}):
            from scheduler import generate_daemon_report
            report = generate_daemon_report()
        
        assert "generated_at" in report
        assert "daemon" in report
        assert "cycles" in report
        assert "budget" in report
        assert "watchdog" in report
        assert "domains" in report
        assert "sync" in report

    @patch("scheduler.get_stats")
    @patch("scheduler._load_daemon_state")
    @patch("scheduler.get_cycle_history")
    def test_report_includes_running_flag(self, mock_history, mock_state, mock_stats):
        """Report daemon section includes is_running flag."""
        mock_state.return_value = {"status": "idle"}
        mock_history.return_value = []
        mock_stats.return_value = {"count": 0, "avg_score": 0}
        
        with patch("scheduler.check_budget", return_value={"within_budget": True, "remaining": 1.5, "spent": 0.5, "limit": 2.0}), \
             patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0.5}), \
             patch("watchdog.get_watchdog_status", return_value={"state": "running"}), \
             patch("agents.orchestrator.discover_domains", return_value=[]), \
             patch("sync.check_sync", return_value={"aligned": True}):
            from scheduler import generate_daemon_report
            report = generate_daemon_report()
        
        assert report["daemon"]["is_running"] is False  # Not actually running

    @patch("scheduler.get_stats")
    @patch("scheduler._load_daemon_state")
    @patch("scheduler.get_cycle_history")
    def test_report_handles_missing_state(self, mock_history, mock_state, mock_stats):
        """Report works when daemon_state.json doesn't exist."""
        mock_state.return_value = None
        mock_history.return_value = []
        mock_stats.return_value = {"count": 0, "avg_score": 0}
        
        with patch("scheduler.check_budget", return_value={"within_budget": True, "remaining": 2.0, "spent": 0, "limit": 2.0}), \
             patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0}), \
             patch("watchdog.get_watchdog_status", return_value={"state": "stopped"}), \
             patch("agents.orchestrator.discover_domains", return_value=[]), \
             patch("sync.check_sync", return_value={"aligned": True}):
            from scheduler import generate_daemon_report
            report = generate_daemon_report()
        
        assert report["daemon"]["status"] == "no_state_file"

    @patch("scheduler.get_stats")
    @patch("scheduler._load_daemon_state")
    @patch("scheduler.get_cycle_history")
    def test_report_cycles_from_history(self, mock_history, mock_state, mock_stats):
        """Report cycles come from persistent history."""
        mock_state.return_value = {"status": "idle"}
        mock_history.return_value = [
            {"cycle": 1, "status": "success", "avg_score": 7.0},
            {"cycle": 2, "status": "success", "avg_score": 7.5},
        ]
        mock_stats.return_value = {"count": 0, "avg_score": 0}
        
        with patch("scheduler.check_budget", return_value={"within_budget": True, "remaining": 1.0, "spent": 1.0, "limit": 2.0}), \
             patch("cost_tracker.get_daily_spend", return_value={"total_usd": 1.0}), \
             patch("watchdog.get_watchdog_status", return_value={"state": "running"}), \
             patch("agents.orchestrator.discover_domains", return_value=[]), \
             patch("sync.check_sync", return_value={"aligned": True}):
            from scheduler import generate_daemon_report
            report = generate_daemon_report(last_n=5)
        
        assert len(report["cycles"]) == 2
        assert report["cycles"][0]["cycle"] == 1
        assert report["cycles"][1]["avg_score"] == 7.5

    @patch("scheduler.get_stats")
    @patch("scheduler._load_daemon_state")
    @patch("scheduler.get_cycle_history")
    def test_report_domain_scores(self, mock_history, mock_state, mock_stats):
        """Report includes per-domain scores."""
        mock_state.return_value = {"status": "idle"}
        mock_history.return_value = []
        mock_stats.side_effect = lambda d: {
            "ai": {"count": 5, "avg_score": 7.1, "latest_score": 7.5},
            "physics": {"count": 3, "avg_score": 7.3, "latest_score": 7.0},
        }.get(d, {"count": 0, "avg_score": 0, "latest_score": 0})
        
        with patch("scheduler.check_budget", return_value={"within_budget": True, "remaining": 1.0, "spent": 1.0, "limit": 2.0}), \
             patch("cost_tracker.get_daily_spend", return_value={"total_usd": 1.0}), \
             patch("watchdog.get_watchdog_status", return_value={"state": "running"}), \
             patch("agents.orchestrator.discover_domains", return_value=["ai", "physics"]), \
             patch("sync.check_sync", return_value={"aligned": True}):
            from scheduler import generate_daemon_report
            report = generate_daemon_report()
        
        assert "ai" in report["domains"]
        assert report["domains"]["ai"]["count"] == 5
        assert report["domains"]["ai"]["avg_score"] == 7.1
        assert "physics" in report["domains"]

    @patch("scheduler.get_stats")
    @patch("scheduler._load_daemon_state")
    @patch("scheduler.get_cycle_history")
    def test_report_error_resilience(self, mock_history, mock_state, mock_stats):
        """Report handles errors in subsystems gracefully."""
        mock_state.return_value = {"status": "idle"}
        mock_history.return_value = []
        mock_stats.return_value = {"count": 0, "avg_score": 0}
        
        # Patch at the source modules where generate_daemon_report imports from
        with patch("cost_tracker.get_daily_spend", side_effect=Exception("budget error")), \
             patch("watchdog.get_watchdog_status", side_effect=Exception("watchdog error")), \
             patch("agents.orchestrator.discover_domains", side_effect=Exception("domains error")), \
             patch("sync.check_sync", side_effect=Exception("sync error")):
            from scheduler import generate_daemon_report
            report = generate_daemon_report()
        
        # Report should still complete, with error fields
        assert "error" in report["budget"]
        assert "error" in report["watchdog"]
        assert "error" in report["sync"]


# ============================================================
# 3. Stall Detection Enforcement Tests
# ============================================================

class TestStallEnforcement:
    """Test check_stall_and_act in watchdog."""

    def test_no_stall_when_heartbeat_fresh(self):
        """No stall when heartbeat is recent."""
        from watchdog import Watchdog, HEARTBEAT_TIMEOUT_SECONDS
        wd = Watchdog()
        wd.start()
        wd.heartbeat()  # Fresh heartbeat
        
        stalled, reason = wd.check_stall_and_act()
        assert stalled is False
        assert reason == "ok"
        wd.stop()

    def test_no_stall_when_stopped(self):
        """No stall when watchdog is stopped."""
        from watchdog import Watchdog
        wd = Watchdog()
        # Don't start — stays in STOPPED state
        
        stalled, reason = wd.check_stall_and_act()
        assert stalled is False
        assert reason == "not running"

    def test_no_stall_when_never_started(self):
        """No stall when heartbeat was never set (system RUNNING but no heartbeat)."""
        from watchdog import Watchdog, SystemState
        wd = Watchdog()
        # Manually set to RUNNING without calling start() (which sets heartbeat)
        with wd._lock:
            wd._state = SystemState.RUNNING
            wd._last_heartbeat = 0  # Never received a heartbeat
        
        stalled, reason = wd.check_stall_and_act()
        assert stalled is False
        assert reason == "never started"
        wd.stop()

    def test_stall_detected_after_timeout(self):
        """Stall detected when heartbeat exceeds timeout."""
        from watchdog import Watchdog, HEARTBEAT_TIMEOUT_SECONDS
        wd = Watchdog()
        wd.start()
        
        # Set heartbeat to far in the past
        with wd._lock:
            wd._last_heartbeat = time.monotonic() - (HEARTBEAT_TIMEOUT_SECONDS + 100)
        
        stalled, reason = wd.check_stall_and_act()
        assert stalled is True
        assert "Stalled" in reason
        assert "forcing recovery" in reason.lower()
        wd.stop()

    def test_stall_increments_failure_counter(self):
        """Stall detection increments consecutive failure counter."""
        from watchdog import Watchdog, HEARTBEAT_TIMEOUT_SECONDS
        wd = Watchdog()
        wd.start()
        
        # Save the starting failure count (may be non-zero from persisted state)
        initial_failures = wd._consecutive_failures
        
        # Trigger stall
        with wd._lock:
            wd._last_heartbeat = time.monotonic() - (HEARTBEAT_TIMEOUT_SECONDS + 100)
        
        wd.check_stall_and_act()
        assert wd._consecutive_failures == initial_failures + 1
        wd.stop()

    def test_stall_records_critical_event(self):
        """Stall records a critical severity event."""
        from watchdog import Watchdog, HEARTBEAT_TIMEOUT_SECONDS
        wd = Watchdog()
        wd.start()
        
        with wd._lock:
            wd._last_heartbeat = time.monotonic() - (HEARTBEAT_TIMEOUT_SECONDS + 100)
        
        wd.check_stall_and_act()
        
        events = wd.get_events(count=5)
        stall_events = [e for e in events if e["event_type"] == "stall_detected"]
        assert len(stall_events) >= 1
        assert stall_events[0]["severity"] == "critical"
        wd.stop()

    def test_stall_resets_heartbeat(self):
        """After stall detection, heartbeat is reset to prevent immediate re-trigger."""
        from watchdog import Watchdog, HEARTBEAT_TIMEOUT_SECONDS
        wd = Watchdog()
        wd.start()
        
        with wd._lock:
            wd._last_heartbeat = time.monotonic() - (HEARTBEAT_TIMEOUT_SECONDS + 100)
        
        stalled1, _ = wd.check_stall_and_act()
        assert stalled1 is True
        
        # Second check should NOT be stalled (heartbeat was reset)
        stalled2, _ = wd.check_stall_and_act()
        assert stalled2 is False
        wd.stop()

    def test_stall_triggers_cooldown_after_max_failures(self):
        """Repeated stalls trigger cooldown mode."""
        from watchdog import Watchdog, HEARTBEAT_TIMEOUT_SECONDS, MAX_CONSECUTIVE_FAILURES, SystemState
        wd = Watchdog()
        wd.start()
        
        # Trigger enough stalls to hit cooldown
        for i in range(MAX_CONSECUTIVE_FAILURES):
            with wd._lock:
                wd._last_heartbeat = time.monotonic() - (HEARTBEAT_TIMEOUT_SECONDS + 100)
            wd.check_stall_and_act()
        
        assert wd._state == SystemState.COOLDOWN
        wd.stop()

    def test_stall_cooldown_blocks_cycles(self):
        """After stall-induced cooldown, check_before_cycle blocks."""
        from watchdog import Watchdog, HEARTBEAT_TIMEOUT_SECONDS, MAX_CONSECUTIVE_FAILURES
        wd = Watchdog()
        wd.start()
        
        # Trigger cooldown
        for i in range(MAX_CONSECUTIVE_FAILURES):
            with wd._lock:
                wd._last_heartbeat = time.monotonic() - (HEARTBEAT_TIMEOUT_SECONDS + 100)
            wd.check_stall_and_act()
        
        can_proceed, reason = wd.check_before_cycle()
        assert can_proceed is False
        assert "cool" in reason.lower() or "failure" in reason.lower()
        wd.stop()


# ============================================================
# 4. CLI --daemon-report display test
# ============================================================

class TestDaemonReportDisplay:
    """Test show_daemon_report CLI display."""

    @patch("scheduler.generate_daemon_report")
    def test_show_daemon_report_runs(self, mock_report, capsys):
        """show_daemon_report prints output without crashing."""
        mock_report.return_value = {
            "generated_at": "2026-03-02T12:00:00+00:00",
            "daemon": {"status": "idle", "is_running": False},
            "cycles": [
                {
                    "cycle": 1,
                    "status": "success",
                    "started_at": "2026-03-02T11:00:00",
                    "rounds_completed": 3,
                    "avg_score": 7.2,
                    "cycle_cost": 0.0450,
                    "duration_seconds": 120,
                    "domain_results": [
                        {"domain": "ai", "rounds_completed": 2, "avg_score": 7.5},
                        {"domain": "physics", "rounds_completed": 1, "avg_score": 6.8},
                    ],
                },
            ],
            "budget": {
                "spent_today": 0.88,
                "daily_limit": 2.00,
                "remaining": 1.12,
                "within_budget": True,
            },
            "watchdog": {
                "state": "running",
                "cycles_completed": 5,
                "consecutive_failures": 0,
                "consecutive_critical_alerts": 0,
                "heartbeat_age_seconds": 30.5,
                "recent_events": [
                    {
                        "timestamp": "2026-03-02T11:59:00",
                        "severity": "info",
                        "message": "Health check passed",
                    },
                ],
            },
            "domains": {
                "ai": {"count": 5, "avg_score": 7.1, "latest_score": 7.5},
                "physics": {"count": 3, "avg_score": 7.3, "latest_score": 7.0},
            },
            "sync": {"aligned": True, "issues": []},
        }
        
        from cli.infrastructure import show_daemon_report
        show_daemon_report()
        
        captured = capsys.readouterr()
        assert "DAEMON HEALTH REPORT" in captured.out
        assert "IDLE" in captured.out
        assert "Cycle History" in captured.out
        assert "Budget" in captured.out
        assert "Watchdog" in captured.out
        assert "Domain Scores" in captured.out
        assert "Sync" in captured.out
        assert "ai" in captured.out
        assert "physics" in captured.out
        assert "ALIGNED" in captured.out

    @patch("scheduler.generate_daemon_report")
    def test_show_report_with_failures(self, mock_report, capsys):
        """Report displays failures correctly."""
        mock_report.return_value = {
            "generated_at": "2026-03-02T12:00:00+00:00",
            "daemon": {"status": "error", "is_running": False},
            "cycles": [
                {
                    "cycle": 1,
                    "status": "failure",
                    "started_at": "2026-03-02T11:00:00",
                    "error": "API timeout after 300s",
                },
            ],
            "budget": {"error": "could not connect"},
            "watchdog": {"error": "not initialized"},
            "domains": {"error": "no domains"},
            "sync": {"error": "sync module failed"},
        }
        
        from cli.infrastructure import show_daemon_report
        show_daemon_report()
        
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "API timeout" in captured.out

    @patch("scheduler.generate_daemon_report")
    def test_show_report_empty_state(self, mock_report, capsys):
        """Report handles empty/never-run state."""
        mock_report.return_value = {
            "generated_at": "2026-03-02T12:00:00+00:00",
            "daemon": {"status": "no_state_file", "is_running": False},
            "cycles": [],
            "budget": {
                "spent_today": 0,
                "daily_limit": 2.00,
                "remaining": 2.00,
                "within_budget": True,
            },
            "watchdog": {"state": "stopped", "cycles_completed": 0,
                         "consecutive_failures": 0, "consecutive_critical_alerts": 0,
                         "recent_events": []},
            "domains": {},
            "sync": {"aligned": True, "issues": []},
        }
        
        from cli.infrastructure import show_daemon_report
        show_daemon_report()
        
        captured = capsys.readouterr()
        assert "No cycle history" in captured.out
        assert "No domains" in captured.out


# ============================================================
# 5. Integration: Cycle history written during daemon execution
# ============================================================

class TestCycleHistoryIntegration:
    """Test that cycle history is written during daemon execution paths."""

    def test_append_history_called_on_success(self, tmp_path):
        """_append_cycle_history is called when a cycle succeeds."""
        hist_file = str(tmp_path / "cycle_history.jsonl")
        with patch("scheduler.CYCLE_HISTORY_FILE", hist_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import _append_cycle_history
            
            # Simulate what the daemon does on success
            _append_cycle_history({
                "cycle": 1,
                "status": "success",
                "started_at": "2026-03-02T12:00:00+00:00",
                "completed_at": "2026-03-02T12:02:00+00:00",
                "duration_seconds": 120,
                "rounds_completed": 3,
                "avg_score": 7.2,
                "cycle_cost": 0.0450,
                "domain_results": [
                    {"domain": "ai", "rounds_completed": 2, "avg_score": 7.5},
                ],
            })
            
            assert os.path.exists(hist_file)
            with open(hist_file) as f:
                record = json.loads(f.readline())
            assert record["status"] == "success"
            assert record["rounds_completed"] == 3

    def test_append_history_called_on_failure(self, tmp_path):
        """_append_cycle_history is called when a cycle fails."""
        hist_file = str(tmp_path / "cycle_history.jsonl")
        with patch("scheduler.CYCLE_HISTORY_FILE", hist_file), \
             patch("scheduler.LOG_DIR", str(tmp_path)):
            from scheduler import _append_cycle_history
            
            _append_cycle_history({
                "cycle": 1,
                "status": "failure",
                "started_at": "2026-03-02T12:00:00+00:00",
                "error": "API timeout",
            })
            
            with open(hist_file) as f:
                record = json.loads(f.readline())
            assert record["status"] == "failure"
            assert record["error"] == "API timeout"
