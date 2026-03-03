"""
Phase 2 — Integration Tests for the Daemon

These tests prove that the daemon's components work together correctly:
  - Full daemon cycle: plan → execute → record → health check
  - Watchdog circuit breaker: critical alerts → circuit open → daemon halts
  - Crash recovery: state persisted → counters survive restart
  - Budget ceiling: hard cost ceiling → watchdog halts
  - Round timeout: slow round → killed → daemon continues

Mocking strategy:
  - MOCK the LLM boundary: main.run_loop(), get_next_question(), get_seed_question()
  - MOCK monitoring.run_health_check() (needs real DB otherwise)
  - LET EVERYTHING ELSE RUN REAL: watchdog, scheduler, budget, allocation, state I/O

Each test creates its own tmpdir for MEMORY_DIR/STRATEGY_DIR/LOG_DIR so tests
are isolated and leave no artifacts.
"""

import contextlib
import json
import os
import signal
import sys
import time
import threading
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

# Ensure agent-brain is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_daemon_globals():
    """Reset scheduler's module-level daemon state between tests."""
    import scheduler
    scheduler._daemon_running = False
    scheduler._daemon_stop_event.clear()
    scheduler._daemon_log.clear()
    yield
    scheduler._daemon_running = False
    scheduler._daemon_stop_event.clear()


@pytest.fixture
def integration_dirs(tmp_path):
    """
    Create real filesystem dirs for an integration test.
    Returns a dict of paths.
    """
    memory_dir = str(tmp_path / "memory")
    log_dir = str(tmp_path / "logs")
    strategy_dir = str(tmp_path / "strategies")

    os.makedirs(memory_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(strategy_dir, exist_ok=True)

    # Create a test domain with scored outputs so discover_domains finds it
    domain_dir = os.path.join(memory_dir, "test-domain")
    os.makedirs(domain_dir, exist_ok=True)

    for i in range(3):
        output = {
            "question": f"Test question {i}?",
            "domain": "test-domain",
            "overall_score": 6 + i,
            "accepted": True,
            "verdict": "accept",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "research": {
                "summary": f"Test finding {i}",
                "findings": [{"claim": f"Test claim {i}"}],
                "key_insights": [f"Insight {i}"],
            },
            "critique": {
                "overall_score": 6 + i,
                "accuracy": 7, "depth": 6, "completeness": 7,
                "specificity": 6, "intellectual_honesty": 7,
            },
            "_cost": 0.05,
        }
        with open(os.path.join(domain_dir, f"output_{i}.json"), "w") as f:
            json.dump(output, f)

    os.makedirs(os.path.join(strategy_dir, "test-domain"), exist_ok=True)

    return {
        "memory_dir": memory_dir,
        "log_dir": log_dir,
        "strategy_dir": strategy_dir,
        "domain_dir": domain_dir,
    }


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _enter_dir_patches(stack: contextlib.ExitStack, dirs: dict):
    """Enter all dir-config patches into an ExitStack."""
    for target, val in [
        ("config.MEMORY_DIR", dirs["memory_dir"]),
        ("config.LOG_DIR", dirs["log_dir"]),
        ("config.STRATEGY_DIR", dirs["strategy_dir"]),
        ("scheduler.MEMORY_DIR", dirs["memory_dir"]),
        ("scheduler.LOG_DIR", dirs["log_dir"]),
        ("memory_store.MEMORY_DIR", dirs["memory_dir"]),
        ("agents.orchestrator.MEMORY_DIR", dirs["memory_dir"]),
        ("strategy_store.STRATEGY_DIR", dirs["strategy_dir"]),
    ]:
        stack.enter_context(patch(target, val))


def _enter_standard_mocks(
    stack: contextlib.ExitStack,
    dirs: dict,
    *,
    run_loop_side_effect=None,
    run_loop_return=None,
    health_side_effect=None,
    budget_within=True,
    budget_spent=0.10,
    daily_spend=0.10,
):
    """Enter all standard mock patches (LLM boundary + health + budget + sync)."""
    # Dirs
    _enter_dir_patches(stack, dirs)

    # Watchdog state file → tmp dir
    stack.enter_context(
        patch("watchdog.WATCHDOG_STATE_FILE",
              os.path.join(dirs["log_dir"], "watchdog_state.json"))
    )

    # Cycle counter file → tmp dir (prevent cross-test contamination)
    stack.enter_context(
        patch("scheduler.CYCLE_COUNTER_FILE",
              os.path.join(dirs["log_dir"], "cycle_counter.json"))
    )

    # run_loop
    if run_loop_side_effect is not None:
        stack.enter_context(patch("main.run_loop", side_effect=run_loop_side_effect))
    else:
        rv = run_loop_return or _canned_result()
        stack.enter_context(patch("main.run_loop", return_value=rv))

    # Question generation (LLM)
    stack.enter_context(
        patch("agents.question_generator.get_next_question", return_value="Test Q?"))
    stack.enter_context(
        patch("domain_seeder.get_seed_question", return_value="Seed Q?"))

    # Health check
    if health_side_effect is not None:
        stack.enter_context(
            patch("monitoring.run_health_check", side_effect=health_side_effect))
    else:
        stack.enter_context(
            patch("monitoring.run_health_check",
                  return_value={"status": "healthy", "alerts_generated": 0,
                                "domains_checked": 1}))

    # Sync
    stack.enter_context(
        patch("sync.check_sync", return_value={"aligned": True, "issues": []}))

    # Budget
    budget_ret = {
        "within_budget": budget_within,
        "spent": budget_spent,
        "limit": 2.00,
        "remaining": 2.00 - budget_spent if budget_within else -0.10,
    }
    stack.enter_context(patch("cost_tracker.check_budget", return_value=budget_ret))
    stack.enter_context(patch("scheduler.check_budget", return_value=budget_ret))

    # Daily spend (for hard ceiling check)
    stack.enter_context(
        patch("cost_tracker.get_daily_spend",
              return_value={"total_usd": daily_spend}))

    # Cortex orchestrator — prevent real LLM calls from Phase 7 wiring
    stack.enter_context(
        patch("scheduler.cortex_plan_cycle", return_value=None))
    stack.enter_context(
        patch("scheduler.cortex_interpret_cycle", return_value=None))
    stack.enter_context(
        patch("scheduler.cortex_daily_assessment", return_value=None))

    # Signal handlers — can't register from non-main thread
    # Mock signal.signal to be a no-op so run_daemon() works in threads
    stack.enter_context(
        patch("scheduler.signal.signal", return_value=signal.SIG_DFL))


def _canned_result(score=7.0, cost=0.05):
    """Return a canned run_loop() result."""
    return {
        "question": "Test question?",
        "domain": "test-domain",
        "research": {
            "summary": "Integration test finding",
            "findings": [{"claim": "Test claim", "confidence": "high"}],
            "key_insights": ["Test insight"],
        },
        "critique": {
            "overall_score": score,
            "accuracy": score, "depth": score - 1,
            "completeness": score, "specificity": score - 1,
            "intellectual_honesty": score,
        },
        "overall_score": score,
        "accepted": True,
        "_cost": cost,
    }


def _run_daemon_threaded(kwargs: dict, timeout: float = 30.0):
    """Run run_daemon() in a thread and wait for it."""
    import scheduler

    result = {"error": None}

    def _target():
        try:
            scheduler.run_daemon(**kwargs)
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        scheduler._daemon_stop_event.set()
        t.join(timeout=5)

    return result


@contextlib.contextmanager
def _fresh_watchdog():
    """Reset watchdog singleton for test isolation, restore on exit."""
    import watchdog as wd_mod
    old = wd_mod._watchdog
    wd_mod._watchdog = None
    try:
        yield
    finally:
        wd_mod._watchdog = old


# ────────────────────────────────────────────────────────────────
# 2.1 — Full Daemon Cycle Integration Test
# ────────────────────────────────────────────────────────────────

class TestFullDaemonCycle:
    """
    Prove: daemon wakes up → creates plan → runs research → records success
           → runs health check → saves state → shuts down cleanly.
    """

    def test_single_cycle_completes(self, integration_dirs):
        """Full single cycle: plan → execute → record → health check → stop."""
        calls = []

        def mock_run_loop(question, domain="test-domain"):
            calls.append({"question": question, "domain": domain})
            return _canned_result(score=7.0, cost=0.03)

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs,
                                  run_loop_side_effect=mock_run_loop)
            with _fresh_watchdog():
                result = _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 2,
                    "max_cycles": 1,
                    "require_approval": True,
                })

                assert result["error"] is None, f"Daemon crashed: {result['error']}"
                assert len(calls) >= 1, "run_loop never called"

                # Daemon state persisted
                state_file = os.path.join(integration_dirs["log_dir"],
                                          "daemon_state.json")
                assert os.path.exists(state_file)
                with open(state_file) as f:
                    state = json.load(f)
                assert state["status"] == "stopped"
                # Daemon increments cycle counter before checking max_cycles,
                # so total_cycles is max_cycles + 1 when it exits the loop
                assert state["total_cycles"] >= 1

                # Watchdog state persisted
                wd_file = os.path.join(integration_dirs["log_dir"],
                                       "watchdog_state.json")
                assert os.path.exists(wd_file)
                with open(wd_file) as f:
                    ws = json.load(f)
                assert ws["state"] == "stopped"
                assert ws["cycle_count"] >= 1

    def test_daemon_produces_domain_results(self, integration_dirs):
        """Verify cycle_success events contain domain results."""
        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs,
                                  run_loop_return=_canned_result(7.5, 0.04))
            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 2,
                    "max_cycles": 1,
                })

                wd_file = os.path.join(integration_dirs["log_dir"],
                                       "watchdog_state.json")
                with open(wd_file) as f:
                    ws = json.load(f)

                success = [e for e in ws.get("events", [])
                           if e["event_type"] == "cycle_success"]
                assert len(success) >= 1, "No cycle_success events"

                d = success[0]["details"]
                assert d["rounds"] >= 1
                assert d["avg_score"] > 0
                assert d["cost"] >= 0


# ────────────────────────────────────────────────────────────────
# 2.2 — Watchdog Circuit Breaker Integration Test
# ────────────────────────────────────────────────────────────────

class TestCircuitBreakerIntegration:
    """
    Prove: repeated 'critical' health checks → circuit breaker trips.
    """

    def test_circuit_breaker_trips(self, integration_dirs):
        """After CIRCUIT_BREAKER_THRESHOLD criticals, watchdog blocks.

        The circuit breaker trips when run_health_check() returns 'critical'
        enough consecutive times. But record_cycle_success() resets the counter.
        To test the breaker, we need cycles to FAIL (not succeed) so
        record_cycle_failure() is called (doesn't reset critical counter),
        AND health checks return critical.

        We make run_loop() raise so every round fails → completed=0 →
        the daemon records it as a cycle failure.
        """
        from watchdog import CIRCUIT_BREAKER_THRESHOLD

        def always_critical(verbose=False):
            return {"status": "critical", "alerts_generated": 2,
                    "domains_checked": 1}

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(
                stack, integration_dirs,
                health_side_effect=always_critical,
                run_loop_side_effect=RuntimeError("Simulated round failure"),
            )
            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 1,
                    "max_cycles": CIRCUIT_BREAKER_THRESHOLD + 5,
                })

                wd_file = os.path.join(integration_dirs["log_dir"],
                                       "watchdog_state.json")
                with open(wd_file) as f:
                    ws = json.load(f)

                tripped = [e for e in ws.get("events", [])
                           if e["event_type"] == "circuit_breaker_tripped"]
                assert len(tripped) >= 1, (
                    f"Circuit breaker never tripped. Events: "
                    f"{[e['event_type'] for e in ws.get('events', [])]}"
                )
                assert ws["state"] in ("circuit_open", "stopped")

    def test_healthy_resets_critical_counter(self, integration_dirs):
        """Alternating critical/healthy never trips the breaker."""
        n = {"i": 0}

        def alternating(verbose=False):
            n["i"] += 1
            if n["i"] % 2 == 1:
                return {"status": "critical", "alerts_generated": 1,
                        "domains_checked": 1}
            return {"status": "healthy", "alerts_generated": 0,
                    "domains_checked": 1}

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs,
                                  health_side_effect=alternating)
            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 1,
                    "max_cycles": 6,
                })

                wd_file = os.path.join(integration_dirs["log_dir"],
                                       "watchdog_state.json")
                with open(wd_file) as f:
                    ws = json.load(f)

                tripped = [e for e in ws.get("events", [])
                           if e["event_type"] == "circuit_breaker_tripped"]
                assert len(tripped) == 0, "Should NOT trip with alternating"
                assert ws["cycle_count"] >= 6


# ────────────────────────────────────────────────────────────────
# 2.3 — Crash Recovery Test
# ────────────────────────────────────────────────────────────────

class TestCrashRecovery:
    """
    Prove: watchdog state survives process restart (crash recovery).
    """

    def test_state_survives_restart(self, integration_dirs):
        """Counters persisted by wd1 are loaded by wd2."""
        from watchdog import Watchdog

        wd_file = os.path.join(integration_dirs["log_dir"],
                               "watchdog_state.json")
        with patch("watchdog.WATCHDOG_STATE_FILE", wd_file):
            wd1 = Watchdog()
            wd1.start()
            wd1.record_cycle_success(2, 7.0, 0.06)
            wd1.record_cycle_success(3, 7.5, 0.08)
            wd1.record_cycle_failure("err1")
            wd1.record_cycle_failure("err2")
            wd1.record_cycle_success(1, 6.0, 0.03)
            wd1.stop()

            assert os.path.exists(wd_file)
            with open(wd_file) as f:
                saved = json.load(f)
            assert saved["cycle_count"] == 5
            assert saved["total_rounds"] == 6

            wd2 = Watchdog()
            s = wd2.get_status()
            assert s["cycles_completed"] == 5
            assert s["total_rounds"] == 6
            assert s["consecutive_failures"] == 0  # last was success

    def test_failure_counter_persisted(self, integration_dirs):
        """Consecutive failure counter survives a crash (no stop())."""
        from watchdog import Watchdog

        wd_file = os.path.join(integration_dirs["log_dir"],
                               "watchdog_state.json")
        with patch("watchdog.WATCHDOG_STATE_FILE", wd_file):
            wd1 = Watchdog()
            wd1.start()
            wd1.record_cycle_failure("A")
            wd1.record_cycle_failure("B")
            wd1.record_cycle_failure("C")
            del wd1  # crash — no stop()

            wd2 = Watchdog()
            s = wd2.get_status()
            assert s["consecutive_failures"] == 3
            assert s["cycles_completed"] == 3

    def test_corrupt_state_starts_fresh(self, integration_dirs):
        """Corrupt state file → watchdog starts with zero counters."""
        from watchdog import Watchdog

        wd_file = os.path.join(integration_dirs["log_dir"],
                               "watchdog_state.json")
        os.makedirs(os.path.dirname(wd_file), exist_ok=True)
        with open(wd_file, "w") as f:
            f.write("{corrupt json!!")

        with patch("watchdog.WATCHDOG_STATE_FILE", wd_file):
            wd = Watchdog()
            s = wd.get_status()
            assert s["cycles_completed"] == 0
            assert s["consecutive_failures"] == 0

    def test_daemon_state_persisted_each_cycle(self, integration_dirs):
        """daemon_state.json is written multiple times during one cycle."""
        import scheduler
        original_save = scheduler._save_daemon_state
        saves = []

        def capture(state):
            saves.append(dict(state))
            original_save(state)

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs)
            stack.enter_context(
                patch("scheduler._save_daemon_state", side_effect=capture))
            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 1,
                    "max_cycles": 1,
                })

                assert len(saves) >= 2, (
                    f"Expected >=2 state saves, got {len(saves)}: "
                    f"{[s.get('status') for s in saves]}"
                )
                assert saves[-1]["status"] == "stopped"


# ────────────────────────────────────────────────────────────────
# 2.4 — Budget Ceiling Integration Test
# ────────────────────────────────────────────────────────────────

class TestBudgetCeilingIntegration:
    """
    Prove: hard cost ceiling → watchdog halts, run_loop never called.
    """

    def test_hard_ceiling_blocks(self, integration_dirs):
        """Daily spend >= HARD_COST_CEILING → no research runs."""
        from watchdog import HARD_COST_CEILING_USD

        run_loop_mock = MagicMock(return_value=_canned_result())

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(
                stack, integration_dirs,
                daily_spend=HARD_COST_CEILING_USD + 0.50,
            )
            # Override run_loop with a trackable mock
            stack.enter_context(patch("main.run_loop", run_loop_mock))

            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 2,
                    "max_cycles": 3,
                })

                assert run_loop_mock.call_count == 0, (
                    f"run_loop called {run_loop_mock.call_count}x "
                    f"despite budget ceiling"
                )

                wd_file = os.path.join(integration_dirs["log_dir"],
                                       "watchdog_state.json")
                with open(wd_file) as f:
                    ws = json.load(f)

                halts = [e for e in ws.get("events", [])
                         if e["event_type"] == "budget_halt"]
                assert len(halts) >= 1, (
                    f"No budget_halt event. Events: "
                    f"{[e['event_type'] for e in ws.get('events', [])]}"
                )

    def test_daily_budget_exceeded_skips(self, integration_dirs):
        """Normal daily budget exceeded (not hard ceiling) → cycle skipped."""
        run_loop_mock = MagicMock(return_value=_canned_result())

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(
                stack, integration_dirs,
                budget_within=False,
                budget_spent=2.10,
                daily_spend=2.10,  # below hard ceiling (3.00)
            )
            stack.enter_context(patch("main.run_loop", run_loop_mock))

            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 2,
                    "max_cycles": 1,
                })

                assert run_loop_mock.call_count == 0

                state_file = os.path.join(integration_dirs["log_dir"],
                                          "daemon_state.json")
                if os.path.exists(state_file):
                    with open(state_file) as f:
                        state = json.load(f)
                    assert state["status"] in ("waiting_budget", "stopped")


# ────────────────────────────────────────────────────────────────
# 2.5 — Round Timeout Integration Test
# ────────────────────────────────────────────────────────────────

class TestRoundTimeoutIntegration:
    """
    Prove: hung rounds are killed, daemon continues.
    """

    def test_slow_round_killed_fast_succeeds(self, integration_dirs):
        """First round hangs → killed. Second round completes normally."""
        n = {"i": 0}

        def slow_then_fast(question, domain="test-domain"):
            n["i"] += 1
            if n["i"] == 1:
                time.sleep(999)  # Will be killed
                return _canned_result()
            return _canned_result(score=8.0, cost=0.04)

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs,
                                  run_loop_side_effect=slow_then_fast)
            stack.enter_context(
                patch("watchdog.MAX_ROUND_DURATION_SECONDS", 2))

            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 2,
                    "max_cycles": 1,
                }, timeout=30)

                import scheduler
                log_text = "\n".join(
                    e["message"] if isinstance(e, dict) else str(e)
                    for e in scheduler._daemon_log
                )
                assert "TIMEOUT" in log_text or "timeout" in log_text.lower(), (
                    f"No timeout in log: {log_text}"
                )
                assert n["i"] >= 1

    def test_all_rounds_timeout_cycle_completes(self, integration_dirs):
        """Even with all rounds timing out, the cycle finishes cleanly."""
        def always_hang(question, domain="test-domain"):
            time.sleep(999)
            return _canned_result()

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs,
                                  run_loop_side_effect=always_hang)
            stack.enter_context(
                patch("watchdog.MAX_ROUND_DURATION_SECONDS", 1))

            with _fresh_watchdog():
                _run_daemon_threaded({
                    "interval_minutes": 0,
                    "rounds_per_cycle": 2,
                    "max_cycles": 1,
                }, timeout=30)

                state_file = os.path.join(integration_dirs["log_dir"],
                                          "daemon_state.json")
                assert os.path.exists(state_file)
                with open(state_file) as f:
                    state = json.load(f)
                # After timeout kills all rounds, daemon completes cycle
                # (0 successful rounds) then exits via max_cycles.
                # Status may be 'idle' (cycle completed) or 'stopped'.
                assert state["status"] in ("idle", "stopped"), (
                    f"Unexpected status: {state['status']}")

                wd_file = os.path.join(integration_dirs["log_dir"],
                                       "watchdog_state.json")
                with open(wd_file) as f:
                    ws = json.load(f)
                assert ws["cycle_count"] >= 1


# ────────────────────────────────────────────────────────────────
# 2.6 — Graceful Shutdown Test
# ────────────────────────────────────────────────────────────────

class TestGracefulShutdown:
    """
    Prove: stop signal → clean shutdown mid-cycle.
    """

    def test_stop_event_during_cycle(self, integration_dirs):
        """Setting stop event mid-round → daemon exits cleanly."""
        import scheduler

        def run_loop_then_stop(question, domain="test-domain"):
            scheduler._daemon_stop_event.set()
            return _canned_result(score=7.0, cost=0.03)

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs,
                                  run_loop_side_effect=run_loop_then_stop)
            with _fresh_watchdog():
                result = _run_daemon_threaded({
                    "interval_minutes": 60,
                    "rounds_per_cycle": 10,
                    "max_cycles": 100,
                }, timeout=15)

                assert result["error"] is None
                state_file = os.path.join(integration_dirs["log_dir"],
                                          "daemon_state.json")
                with open(state_file) as f:
                    state = json.load(f)
                assert state["status"] == "stopped"
                assert state["total_cycles"] <= 2

    def test_stop_daemon_function(self, integration_dirs):
        """stop_daemon() triggers graceful shutdown."""
        import scheduler

        def slow_loop(question, domain="test-domain"):
            time.sleep(0.5)
            return _canned_result()

        with contextlib.ExitStack() as stack:
            _enter_standard_mocks(stack, integration_dirs,
                                  run_loop_side_effect=slow_loop)
            with _fresh_watchdog():
                t = threading.Thread(
                    target=scheduler.run_daemon,
                    kwargs={
                        "interval_minutes": 0,
                        "rounds_per_cycle": 5,
                        "max_cycles": 0,
                    },
                    daemon=True,
                )
                t.start()
                time.sleep(1)

                assert scheduler.stop_daemon() is True

                t.join(timeout=10)
                assert not t.is_alive(), "Daemon hung after stop_daemon()"
