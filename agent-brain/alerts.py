"""
Telegram Alerting — Lightweight push notifications for the daemon.

Sends alerts to your Telegram chat when critical events happen:
  - Daemon started / stopped
  - Cycle completed (summary)
  - Circuit breaker tripped
  - Budget halt (hard ceiling)
  - Stall detected
  - Error / crash
  - Daily assessment summary

Setup:
  1. Message @BotFather on Telegram → /newbot → get token
  2. Message your bot, then visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     to find your chat_id
  3. Set env vars:
     export TELEGRAM_BOT_TOKEN="123456:ABC..."
     export TELEGRAM_CHAT_ID="987654321"

Zero cost. No dependencies beyond urllib (stdlib).
If env vars are missing, all functions are silent no-ops.
"""

import os
import json
import urllib.request
import urllib.error
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Throttle: max messages per minute to avoid Telegram rate limits
_MAX_PER_MINUTE = 20
_recent_sends: list[float] = []


def _is_configured() -> bool:
    """Check if Telegram alerting is configured."""
    return TELEGRAM_ENABLED


def _throttle_ok() -> bool:
    """Simple rate limiter: max _MAX_PER_MINUTE messages per 60s window."""
    import time
    now = time.time()
    # Prune old entries
    _recent_sends[:] = [t for t in _recent_sends if now - t < 60]
    if len(_recent_sends) >= _MAX_PER_MINUTE:
        return False
    _recent_sends.append(now)
    return True


def _send_telegram(text: str, parse_mode: str = "HTML") -> bool:
    """
    Send a message via Telegram Bot API. Returns True on success.
    Uses only stdlib (urllib) — no extra dependencies.
    """
    if not _is_configured():
        return False
    if not _throttle_ok():
        logger.warning("Telegram rate limit — message dropped")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning(f"Telegram send failed: {e}")
        return False


# ── High-Level Alert Functions ─────────────────────────────────────────

def alert_daemon_started(interval_minutes: int, rounds_per_cycle: int,
                         max_cycles: int, budget_remaining: float):
    """Daemon has started running."""
    _send_telegram(
        f"🟢 <b>Daemon Started</b>\n"
        f"Interval: {interval_minutes}m\n"
        f"Rounds/cycle: {rounds_per_cycle}\n"
        f"Max cycles: {max_cycles or '∞'}\n"
        f"Budget remaining: ${budget_remaining:.2f}"
    )


def alert_daemon_stopped(total_cycles: int, reason: str = "clean shutdown"):
    """Daemon has stopped."""
    _send_telegram(
        f"🔴 <b>Daemon Stopped</b>\n"
        f"Cycles completed: {total_cycles}\n"
        f"Reason: {reason}"
    )


def alert_cycle_complete(cycle: int, rounds: int, avg_score: float,
                         cost: float, duration_s: float,
                         domain_results: list[dict]):
    """A full cycle completed successfully."""
    domains_summary = "\n".join(
        f"  • {d['domain']}: {d['rounds_completed']}r, avg {d['avg_score']}"
        for d in domain_results
    ) if domain_results else "  (no domains)"

    _send_telegram(
        f"✅ <b>Cycle {cycle} Complete</b>\n"
        f"Rounds: {rounds} | Avg: {avg_score:.1f} | "
        f"Cost: ${cost:.4f} | {duration_s:.0f}s\n"
        f"{domains_summary}"
    )


def alert_circuit_breaker(reason: str):
    """Circuit breaker tripped — daemon halted."""
    _send_telegram(
        f"🚨 <b>CIRCUIT BREAKER TRIPPED</b>\n"
        f"{reason}\n"
        f"Daemon is halting. Manual intervention needed."
    )


def alert_budget_halt(spent: float, ceiling: float):
    """Hard cost ceiling hit."""
    _send_telegram(
        f"💰 <b>BUDGET HALT</b>\n"
        f"Spent: ${spent:.4f}\n"
        f"Ceiling: ${ceiling:.2f}\n"
        f"All operations stopped."
    )


def alert_budget_warning(spent: float, limit: float):
    """Budget > 80% consumed."""
    pct = (spent / limit * 100) if limit > 0 else 0
    _send_telegram(
        f"⚠️ <b>Budget Warning</b>\n"
        f"${spent:.2f} / ${limit:.2f} ({pct:.0f}%)"
    )


def alert_stall_detected(domain: str, reason: str):
    """Stall detected in a domain."""
    _send_telegram(
        f"⏸️ <b>Stall Detected</b>\n"
        f"Domain: {domain}\n"
        f"Reason: {reason}"
    )


def alert_error(cycle: int, error: str):
    """Cycle failed with an error."""
    # Truncate long errors
    if len(error) > 500:
        error = error[:500] + "..."
    _send_telegram(
        f"❌ <b>Cycle {cycle} Failed</b>\n"
        f"<code>{error}</code>"
    )


def alert_daily_summary(cycles_today: int, total_cost: float,
                        avg_score: float, domains_active: int,
                        cortex_insight: str = ""):
    """End-of-day or periodic summary."""
    msg = (
        f"📊 <b>Daily Summary</b>\n"
        f"Cycles: {cycles_today}\n"
        f"Total cost: ${total_cost:.4f}\n"
        f"Avg score: {avg_score:.1f}\n"
        f"Active domains: {domains_active}"
    )
    if cortex_insight:
        msg += f"\n\n💡 <i>{cortex_insight[:300]}</i>"
    _send_telegram(msg)


def alert_watchdog_event(event_type: str, details: str):
    """Generic watchdog event worth reporting."""
    emoji = {
        "circuit_breaker_tripped": "🚨",
        "budget_halt": "💰",
        "stall_recovery": "⏸️",
        "score_regression": "📉",
        "consecutive_failures": "❌",
    }.get(event_type, "⚡")

    _send_telegram(
        f"{emoji} <b>Watchdog: {event_type}</b>\n"
        f"{details[:500]}"
    )


def alert_custom(title: str, message: str, emoji: str = "📢"):
    """Send a custom alert."""
    _send_telegram(f"{emoji} <b>{title}</b>\n{message[:800]}")


def alert_signal_collection(collected: int, scored: int, top_score: int,
                            new_questions: int):
    """Alert after a signal intelligence cycle completes."""
    _send_telegram(
        f"📡 <b>Signal Intelligence Cycle</b>\n"
        f"Collected: {collected} new posts\n"
        f"Scored: {scored} opportunities\n"
        f"Top score: {top_score}/100\n"
        f"Research questions queued: {new_questions}"
    )
