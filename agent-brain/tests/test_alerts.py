"""
Tests for alerts.py — Telegram alerting module.

Validates:
  - All alert functions exist and are callable
  - Functions are silent no-ops when TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID unset
  - _send_telegram makes correct HTTP request when configured
  - Rate limiter (throttle) works
  - Error truncation in alert_error
"""

import os
import json
import time
from unittest.mock import patch, MagicMock

import pytest

# Ensure alerts module is importable from agent-brain/
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import alerts


# ── Unconfigured (default) — all functions are no-ops ─────────────────

class TestUnconfigured:
    """When TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set, all functions
    should be silent no-ops that don't raise."""

    def test_is_configured_false(self):
        """Without env vars, _is_configured returns False."""
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            assert alerts._is_configured() is False

    def test_send_telegram_noop(self):
        """_send_telegram returns False immediately when unconfigured."""
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            result = alerts._send_telegram("test")
            assert result is False

    def test_alert_daemon_started_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_daemon_started(15, 3, 0, 1.90)  # no exception

    def test_alert_daemon_stopped_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_daemon_stopped(5, "test")

    def test_alert_cycle_complete_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_cycle_complete(1, 3, 7.5, 0.05, 120.0, [])

    def test_alert_circuit_breaker_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_circuit_breaker("test reason")

    def test_alert_budget_halt_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_budget_halt(2.50, 2.00)

    def test_alert_budget_warning_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_budget_warning(1.80, 2.00)

    def test_alert_stall_detected_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_stall_detected("ai-safety", "score stalled")

    def test_alert_error_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_error(3, "some error")

    def test_alert_daily_summary_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_daily_summary(10, 0.50, 7.2, 3, "insight")

    def test_alert_watchdog_event_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_watchdog_event("circuit_breaker_tripped", "details")

    def test_alert_custom_noop(self):
        with patch.object(alerts, "TELEGRAM_ENABLED", False):
            alerts.alert_custom("Title", "Message")


# ── Configured — verify HTTP calls ────────────────────────────────────

class TestConfigured:
    """When configured, verify _send_telegram makes the right HTTP call."""

    def _mock_configured(self):
        """Return patches that make alerts think it's configured."""
        return [
            patch.object(alerts, "TELEGRAM_ENABLED", True),
            patch.object(alerts, "TELEGRAM_BOT_TOKEN", "123:FAKE"),
            patch.object(alerts, "TELEGRAM_CHAT_ID", "99999"),
        ]

    def test_send_telegram_http_call(self):
        """_send_telegram sends POST to Telegram API with correct payload."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        # Clear rate limiter
        alerts._recent_sends.clear()

        with patch.object(alerts, "TELEGRAM_ENABLED", True), \
             patch.object(alerts, "TELEGRAM_BOT_TOKEN", "123:FAKE"), \
             patch.object(alerts, "TELEGRAM_CHAT_ID", "99999"), \
             patch("alerts.urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = alerts._send_telegram("Hello World")
            assert result is True
            mock_urlopen.assert_called_once()

            # Verify URL
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            assert "123:FAKE" in req.full_url
            assert "sendMessage" in req.full_url

            # Verify payload
            payload = json.loads(req.data.decode("utf-8"))
            assert payload["chat_id"] == "99999"
            assert payload["text"] == "Hello World"
            assert payload["parse_mode"] == "HTML"

    def test_send_telegram_handles_network_error(self):
        """Network errors are caught and logged, return False."""
        import urllib.error

        alerts._recent_sends.clear()

        with patch.object(alerts, "TELEGRAM_ENABLED", True), \
             patch.object(alerts, "TELEGRAM_BOT_TOKEN", "123:FAKE"), \
             patch.object(alerts, "TELEGRAM_CHAT_ID", "99999"), \
             patch("alerts.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("timeout")):
            result = alerts._send_telegram("test")
            assert result is False

    def test_alert_daemon_started_sends(self):
        """alert_daemon_started calls _send_telegram with correct content."""
        alerts._recent_sends.clear()
        with patch.object(alerts, "_send_telegram", return_value=True) as mock:
            with patch.object(alerts, "TELEGRAM_ENABLED", True):
                alerts.alert_daemon_started(15, 3, 0, 1.90)
                mock.assert_called_once()
                msg = mock.call_args[0][0]
                assert "Daemon Started" in msg
                assert "15m" in msg
                assert "$1.90" in msg

    def test_alert_cycle_complete_sends(self):
        """alert_cycle_complete formats domain results correctly."""
        alerts._recent_sends.clear()
        results = [
            {"domain": "ai-safety", "rounds_completed": 2, "avg_score": 7.5},
            {"domain": "quantum", "rounds_completed": 1, "avg_score": 6.3},
        ]
        with patch.object(alerts, "_send_telegram", return_value=True) as mock:
            alerts.alert_cycle_complete(1, 3, 7.0, 0.05, 120.0, results)
            mock.assert_called_once()
            msg = mock.call_args[0][0]
            assert "Cycle 1" in msg
            assert "ai-safety" in msg
            assert "quantum" in msg

    def test_alert_error_truncates_long_errors(self):
        """alert_error truncates messages longer than 500 chars."""
        alerts._recent_sends.clear()
        long_error = "x" * 1000
        with patch.object(alerts, "_send_telegram", return_value=True) as mock:
            alerts.alert_error(5, long_error)
            mock.assert_called_once()
            msg = mock.call_args[0][0]
            assert "..." in msg
            assert len(msg) < 600  # 500 + HTML tags + "..."


# ── Throttle / Rate Limiter ───────────────────────────────────────────

class TestThrottle:
    """Rate limiter prevents more than _MAX_PER_MINUTE messages."""

    def test_throttle_allows_under_limit(self):
        alerts._recent_sends.clear()
        for _ in range(19):
            assert alerts._throttle_ok() is True

    def test_throttle_blocks_at_limit(self):
        alerts._recent_sends.clear()
        for _ in range(20):
            alerts._throttle_ok()
        assert alerts._throttle_ok() is False

    def test_throttle_resets_after_window(self):
        alerts._recent_sends.clear()
        # Fill with old timestamps
        old = time.time() - 61  # >60s ago
        alerts._recent_sends.extend([old] * 20)
        assert alerts._throttle_ok() is True  # old entries pruned


# ── Function Existence (all 11 alert functions) ──────────────────────

class TestFunctionExistence:
    """Verify all expected alert functions exist as callables."""

    EXPECTED = [
        "alert_daemon_started",
        "alert_daemon_stopped",
        "alert_cycle_complete",
        "alert_circuit_breaker",
        "alert_budget_halt",
        "alert_budget_warning",
        "alert_stall_detected",
        "alert_error",
        "alert_daily_summary",
        "alert_watchdog_event",
        "alert_custom",
    ]

    @pytest.mark.parametrize("name", EXPECTED)
    def test_function_exists(self, name):
        assert hasattr(alerts, name)
        assert callable(getattr(alerts, name))
