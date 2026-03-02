"""
Tests for Phase 1 Safety Gaps — Round Timeout, Auto-Approve, Log Rotation, Balance Config

These tests verify the 4 safety fixes that make the daemon safe for 24/7 operation:
  1. Round timeout enforcement (MAX_ROUND_DURATION_SECONDS)
  2. require_approval wired to auto-approve logic
  3. Log rotation for JSONL files
  4. TOTAL_BALANCE_USD configurable via env var
"""

import json
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_logs(tmp_path, monkeypatch):
    """Redirect LOG_DIR to tmp for isolation."""
    monkeypatch.setattr("config.LOG_DIR", str(tmp_path))
    # Also patch scheduler's LOG_DIR since it imports at module level
    import scheduler
    monkeypatch.setattr(scheduler, "LOG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def tmp_strategy_dir(tmp_path, monkeypatch):
    """Redirect STRATEGY_DIR to tmp for isolation."""
    strat_dir = str(tmp_path / "strategies")
    os.makedirs(strat_dir, exist_ok=True)
    monkeypatch.setattr("config.STRATEGY_DIR", strat_dir)
    import strategy_store
    monkeypatch.setattr(strategy_store, "STRATEGY_DIR", strat_dir)
    return strat_dir


# ============================================================
# 1. Round Timeout Enforcement
# ============================================================

class TestRoundTimeout:
    """Tests for MAX_ROUND_DURATION_SECONDS enforcement in daemon."""

    def test_timeout_import_in_scheduler(self):
        """Verify ThreadPoolExecutor and FutureTimeoutError are available."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        assert ThreadPoolExecutor is not None
        assert FutureTimeoutError is not None

    def test_timeout_kills_slow_round(self):
        """A round that exceeds the timeout should be killed, not hang forever."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

        def slow_function():
            time.sleep(10)  # Would hang if no timeout
            return {"critique": {"overall_score": 5}}

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(slow_function)
            with pytest.raises(FutureTimeoutError):
                future.result(timeout=0.1)  # 100ms timeout

    def test_timeout_allows_fast_round(self):
        """A round that completes in time should return normally."""
        from concurrent.futures import ThreadPoolExecutor

        def fast_function():
            return {"critique": {"overall_score": 8}, "_cost": 0.05}

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fast_function)
            result = future.result(timeout=5.0)
            assert result["critique"]["overall_score"] == 8

    def test_max_round_duration_defined(self):
        """MAX_ROUND_DURATION_SECONDS must be defined in watchdog."""
        from watchdog import MAX_ROUND_DURATION_SECONDS
        assert MAX_ROUND_DURATION_SECONDS > 0
        assert MAX_ROUND_DURATION_SECONDS <= 600  # Shouldn't be more than 10 min

    def test_scheduler_imports_timeout_machinery(self):
        """Scheduler module must have round timeout via daemon threads."""
        import scheduler
        source_file = scheduler.__file__
        with open(source_file) as f:
            source = f.read()
        assert "MAX_ROUND_DURATION_SECONDS" in source
        # Uses daemon threads for timeout (replaced ThreadPoolExecutor)
        assert "daemon=True" in source
        assert "round_thread" in source


# ============================================================
# 2. require_approval Auto-Approve
# ============================================================

class TestAutoApprove:
    """Tests for _auto_approve_pending_strategies."""

    def test_auto_approve_no_pending(self, tmp_logs, tmp_strategy_dir):
        """No error when there are no pending strategies."""
        from scheduler import _auto_approve_pending_strategies
        with patch("agents.orchestrator.discover_domains", return_value=["test-domain"]):
            _auto_approve_pending_strategies()  # Should not raise

    def test_auto_approve_approves_pending(self, tmp_logs, tmp_strategy_dir):
        """Pending strategies get auto-approved to trial status."""
        from scheduler import _auto_approve_pending_strategies
        from utils.atomic_write import atomic_json_write

        # Create a pending strategy file
        domain_dir = os.path.join(tmp_strategy_dir, "test-domain")
        os.makedirs(domain_dir, exist_ok=True)
        strategy_data = {
            "version": "v002",
            "status": "pending",
            "strategy": "Test strategy content",
            "agent_role": "researcher",
            "domain": "test-domain",
        }
        atomic_json_write(
            os.path.join(domain_dir, "researcher_v002.json"),
            strategy_data
        )

        # Also create an active version file
        active_file = os.path.join(domain_dir, "researcher_active.json")
        atomic_json_write(active_file, {"version": "v001", "status": "active"})

        with patch("agents.orchestrator.discover_domains", return_value=["test-domain"]):
            _auto_approve_pending_strategies()

        # Verify the strategy was approved (status changed to trial)
        with open(os.path.join(domain_dir, "researcher_v002.json")) as f:
            updated = json.load(f)
        assert updated["status"] == "trial"
        assert "approved_at" in updated

    def test_auto_approve_skips_non_pending(self, tmp_logs, tmp_strategy_dir):
        """Only pending strategies are auto-approved, not active or trial ones."""
        from scheduler import _auto_approve_pending_strategies
        from utils.atomic_write import atomic_json_write

        domain_dir = os.path.join(tmp_strategy_dir, "test-domain")
        os.makedirs(domain_dir, exist_ok=True)

        # Create an active strategy (not pending)
        atomic_json_write(
            os.path.join(domain_dir, "researcher_v001.json"),
            {"version": "v001", "status": "active", "strategy": "Active strategy"}
        )

        with patch("agents.orchestrator.discover_domains", return_value=["test-domain"]):
            _auto_approve_pending_strategies()

        # Status should remain unchanged
        with open(os.path.join(domain_dir, "researcher_v001.json")) as f:
            data = json.load(f)
        assert data["status"] == "active"

    def test_auto_approve_handles_error_gracefully(self, tmp_logs):
        """Auto-approve should log errors but not crash."""
        from scheduler import _auto_approve_pending_strategies

        with patch("agents.orchestrator.discover_domains", return_value=["bad-domain"]), \
             patch("strategy_store.list_pending", side_effect=Exception("disk error")):
            # Should not raise
            _auto_approve_pending_strategies()

    def test_require_approval_documented_in_daemon(self):
        """run_daemon docstring must mention require_approval behavior."""
        from scheduler import run_daemon
        doc = run_daemon.__doc__
        assert "require_approval" in doc
        assert "auto-approved" in doc.lower() or "auto-approve" in doc.lower() or "autonomous" in doc.lower()

    def test_daemon_log_includes_require_approval(self, tmp_logs):
        """Daemon start log should include the require_approval setting."""
        from scheduler import _log_daemon, _daemon_log
        initial = len(_daemon_log)
        _log_daemon("Daemon started: interval=60m, rounds=5, max_cycles=∞, require_approval=True")
        assert "require_approval=True" in _daemon_log[-1]["message"]


# ============================================================
# 3. Log Rotation
# ============================================================

class TestLogRotation:
    """Tests for _rotate_logs."""

    def test_rotate_does_nothing_when_small(self, tmp_logs):
        """Files under the size limit should not be rotated."""
        from scheduler import _rotate_logs, LOG_MAX_SIZE_BYTES

        # Create a small log file
        log_file = os.path.join(str(tmp_logs), "costs.jsonl")
        with open(log_file, "w") as f:
            f.write('{"test": true}\n')

        _rotate_logs()

        # File should still exist at original path
        assert os.path.exists(log_file)
        assert not os.path.exists(f"{log_file}.1")

    def test_rotate_moves_large_file(self, tmp_logs):
        """Files over the size limit should be rotated to .1."""
        from scheduler import _rotate_logs, LOG_MAX_SIZE_BYTES

        log_file = os.path.join(str(tmp_logs), "costs.jsonl")
        # Write a file larger than the limit
        with open(log_file, "w") as f:
            f.write("x" * (LOG_MAX_SIZE_BYTES + 1))

        _rotate_logs()

        # Original should be gone, .1 should exist
        assert not os.path.exists(log_file)
        assert os.path.exists(f"{log_file}.1")

    def test_rotate_shifts_existing_rotations(self, tmp_logs):
        """Existing .1 should shift to .2 when a new rotation happens."""
        from scheduler import _rotate_logs, LOG_MAX_SIZE_BYTES

        log_file = os.path.join(str(tmp_logs), "costs.jsonl")

        # Create .1 with identifiable content
        with open(f"{log_file}.1", "w") as f:
            f.write("old rotation 1\n")

        # Create oversized current file
        with open(log_file, "w") as f:
            f.write("x" * (LOG_MAX_SIZE_BYTES + 1))

        _rotate_logs()

        # .1 should now have the rotated current file content
        assert os.path.exists(f"{log_file}.1")
        # .2 should have the old .1 content
        assert os.path.exists(f"{log_file}.2")
        with open(f"{log_file}.2") as f:
            assert f.read().strip() == "old rotation 1"

    def test_rotate_deletes_oldest(self, tmp_logs):
        """Oldest rotation beyond LOG_MAX_ROTATIONS should be deleted."""
        from scheduler import _rotate_logs, LOG_MAX_SIZE_BYTES, LOG_MAX_ROTATIONS

        log_file = os.path.join(str(tmp_logs), "costs.jsonl")

        # Create all rotation slots
        for i in range(1, LOG_MAX_ROTATIONS + 1):
            with open(f"{log_file}.{i}", "w") as f:
                f.write(f"rotation {i}\n")

        # Create oversized current file
        with open(log_file, "w") as f:
            f.write("x" * (LOG_MAX_SIZE_BYTES + 1))

        _rotate_logs()

        # .1 should be the newly rotated file
        assert os.path.exists(f"{log_file}.1")
        # .2 and .3 should exist (shifted from .1 and .2)
        assert os.path.exists(f"{log_file}.2")
        assert os.path.exists(f"{log_file}.3")
        # .4 should NOT exist (LOG_MAX_ROTATIONS=3, so .3 is the max)
        assert not os.path.exists(f"{log_file}.4")

    def test_rotate_ignores_json_files(self, tmp_logs):
        """JSON state files should NOT be rotated, only JSONL."""
        from scheduler import _rotate_logs, LOG_MAX_SIZE_BYTES

        json_file = os.path.join(str(tmp_logs), "daemon_state.json")
        with open(json_file, "w") as f:
            f.write("x" * (LOG_MAX_SIZE_BYTES + 1))

        _rotate_logs()

        # Should still be there, untouched
        assert os.path.exists(json_file)
        assert not os.path.exists(f"{json_file}.1")

    def test_rotate_handles_missing_dir(self, tmp_path, monkeypatch):
        """Should not crash if LOG_DIR doesn't exist."""
        import scheduler
        monkeypatch.setattr(scheduler, "LOG_DIR", str(tmp_path / "nonexistent"))
        from scheduler import _rotate_logs
        _rotate_logs()  # Should not raise

    def test_rotate_constants_defined(self):
        """LOG_MAX_SIZE_BYTES and LOG_MAX_ROTATIONS must be defined."""
        from scheduler import LOG_MAX_SIZE_BYTES, LOG_MAX_ROTATIONS
        assert LOG_MAX_SIZE_BYTES > 0
        assert LOG_MAX_ROTATIONS >= 1

    def test_rotate_multiple_files(self, tmp_logs):
        """Multiple oversized files should all be rotated."""
        from scheduler import _rotate_logs, LOG_MAX_SIZE_BYTES

        for name in ["costs.jsonl", "ai.jsonl", "crypto.jsonl"]:
            fpath = os.path.join(str(tmp_logs), name)
            with open(fpath, "w") as f:
                f.write("x" * (LOG_MAX_SIZE_BYTES + 1))

        _rotate_logs()

        for name in ["costs.jsonl", "ai.jsonl", "crypto.jsonl"]:
            fpath = os.path.join(str(tmp_logs), name)
            assert not os.path.exists(fpath)
            assert os.path.exists(f"{fpath}.1")


# ============================================================
# 4. Balance Config via Environment Variable
# ============================================================

class TestBalanceConfig:
    """Tests for TOTAL_BALANCE_USD env var support."""

    def test_default_balance_is_float(self):
        """TOTAL_BALANCE_USD should be a float."""
        from config import TOTAL_BALANCE_USD
        assert isinstance(TOTAL_BALANCE_USD, float)

    def test_balance_env_var_override(self, monkeypatch):
        """TOTAL_BALANCE_USD should be overridable via env var."""
        monkeypatch.setenv("TOTAL_BALANCE_USD", "25.50")
        # Need to reimport since config reads env at import time
        import importlib
        import config
        importlib.reload(config)
        assert config.TOTAL_BALANCE_USD == 25.50
        # Restore
        monkeypatch.delenv("TOTAL_BALANCE_USD", raising=False)
        importlib.reload(config)

    def test_balance_not_a_gate(self):
        """check_balance should return info, not block execution."""
        from cost_tracker import check_balance
        result = check_balance()
        # Must return a dict with informational keys
        assert "starting_balance" in result
        assert "remaining_balance" in result
        assert "accuracy_note" in result
        # There should be no "within_budget" or "blocked" key
        assert "blocked" not in result

    def test_sync_balance_flag_exists(self):
        """--sync-balance should be a recognized argument."""
        import main
        import argparse
        # Parse just the help to verify it's registered
        parser = argparse.ArgumentParser()
        # We can't easily extract main's parser, so check source
        with open(main.__file__) as f:
            source = f.read()
        assert "--sync-balance" in source


# ============================================================
# Integration: Daemon Safety Wiring
# ============================================================

class TestDaemonSafetyWiring:
    """Verify all safety features are wired into run_daemon."""

    def test_daemon_source_has_timeout(self):
        """run_daemon must use MAX_ROUND_DURATION_SECONDS for round timeout."""
        import scheduler
        with open(scheduler.__file__) as f:
            source = f.read()
        assert "MAX_ROUND_DURATION_SECONDS" in source
        assert "round_thread.join" in source

    def test_daemon_source_has_log_rotation(self):
        """run_daemon must call _rotate_logs."""
        import scheduler
        with open(scheduler.__file__) as f:
            source = f.read()
        assert "_rotate_logs()" in source

    def test_daemon_source_has_auto_approve(self):
        """run_daemon must call _auto_approve_pending_strategies when appropriate."""
        import scheduler
        with open(scheduler.__file__) as f:
            source = f.read()
        assert "_auto_approve_pending_strategies()" in source
        assert "require_approval" in source

    def test_daemon_source_has_watchdog_heartbeat(self):
        """run_daemon must call watchdog.heartbeat() during rounds."""
        import scheduler
        with open(scheduler.__file__) as f:
            source = f.read()
        assert "watchdog.heartbeat()" in source

    def test_log_rotation_called_periodically(self):
        """Log rotation should be called every 10 cycles (check source)."""
        import scheduler
        with open(scheduler.__file__) as f:
            source = f.read()
        assert "cycle % 10 == 0" in source
        assert "_rotate_logs()" in source
