"""
Watchdog — Continuous Health Monitoring & Circuit Breaker

The load-bearing safety layer for 24/7 autonomous operation.
Runs alongside the daemon to ensure the system stays healthy,
detects problems before they compound, and kills runaway loops.

Responsibilities:
  1. Heartbeat monitoring — detect stalled/frozen processes
  2. Health checks — run monitoring.run_health_check() each cycle
  3. Circuit breaker — pause/kill on critical alerts
  4. Crash counter — track consecutive failures, trigger cooldown
  5. Cost ceiling — hard stop independent of daily budget
  6. Recovery logic — automatic restart after transient failures
  7. Consolidated status — single source of truth for system state

Design:
  - Pure logic, no LLM calls (cheap + reliable)
  - Thread-safe for daemon integration
  - All state persisted to disk for crash recovery
  - Every decision logged with reason

Usage:
  Integrated into scheduler.run_daemon() — not called directly.
  Status available via get_watchdog_status().
"""

import glob
import json
import os
import time
import threading
from datetime import datetime, timezone, timedelta
from enum import Enum
from config import LOG_DIR, DAILY_BUDGET_USD, EXEC_MEMORY_DIR
from utils.atomic_write import atomic_json_write


# ── Configuration ──────────────────────────────────────────────────────────

# Heartbeat: if no heartbeat received in this many seconds, system is "stalled"
HEARTBEAT_TIMEOUT_SECONDS = 600  # 10 minutes (a single round can take ~3-5 min)

# Circuit breaker: consecutive critical alerts before hard pause
CIRCUIT_BREAKER_THRESHOLD = 3

# Crash recovery: consecutive cycle failures before cooldown
MAX_CONSECUTIVE_FAILURES = 5

# Cooldown: how long to wait after hitting failure limit (seconds)
FAILURE_COOLDOWN_SECONDS = 1800  # 30 minutes

# Cost ceiling: absolute max spend per day (independent of DAILY_BUDGET_USD)
# This is the "never exceed" hard ceiling — a safety net above the normal budget
HARD_COST_CEILING_USD = DAILY_BUDGET_USD * 1.5

# HEARTBEAT-style periodic checks
LOG_RETENTION_DAYS = 7        # Delete log files older than this
STALE_CHECKPOINT_HOURS = 24   # Flag exec_memory checkpoints older than this
CONFIG_SNAPSHOT_KEYS = [       # Config keys to monitor for unexpected changes
    "DAILY_BUDGET_USD", "EXEC_MAX_STEPS", "MAX_EXECUTION_COST",
    "BUILD_BUDGET_CAP", "HARD_COST_CEILING_USD",
]

# Stall detection: max time for a single research round (seconds)
# Includes research + scoring + synthesis + verification + meta-analysis.
# 300s was too tight — synthesis alone can take 60-120s on top of research.
MAX_ROUND_DURATION_SECONDS = 600  # 10 minutes

# State file
WATCHDOG_STATE_FILE = os.path.join(LOG_DIR, "watchdog_state.json")


class SystemState(str, Enum):
    """System operational states."""
    RUNNING = "running"         # Normal operation
    PAUSED = "paused"           # Temporarily paused (will auto-resume)
    COOLDOWN = "cooldown"       # Cooling down after failures (auto-resumes)
    CIRCUIT_OPEN = "circuit_open"  # Circuit breaker tripped — needs human review
    BUDGET_HALT = "budget_halt"    # Hard cost ceiling hit
    STOPPED = "stopped"         # Gracefully stopped


class WatchdogEvent:
    """A recorded watchdog event for the audit trail."""

    def __init__(self, event_type: str, message: str, severity: str = "info",
                 details: dict | None = None):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.event_type = event_type
        self.message = message
        self.severity = severity  # info, warning, critical
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


class Watchdog:
    """
    Continuous health monitor and circuit breaker.

    Integrates with the daemon's research cycle to:
    - Track heartbeats and detect stalls
    - Run health checks between cycles
    - Trip circuit breaker on critical failures
    - Enforce hard cost ceilings
    - Manage crash recovery with cooldowns
    - Provide consolidated system status

    Thread-safe. All state persisted for crash recovery.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = SystemState.STOPPED
        self._last_heartbeat: float = 0
        self._consecutive_failures: int = 0
        self._consecutive_critical_alerts: int = 0
        self._cooldown_until: float = 0
        self._events: list[dict] = []
        self._cycle_count: int = 0
        self._total_rounds: int = 0
        self._started_at: str | None = None
        self._paused_reason: str | None = None

        # Load persisted state if available
        self._load_state()

    # ── State Persistence ───────────────────────────────────────────────

    def _save_state(self):
        """Persist watchdog state to disk for crash recovery."""
        os.makedirs(LOG_DIR, exist_ok=True)
        state = {
            "state": self._state.value,
            "last_heartbeat": self._last_heartbeat,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_critical_alerts": self._consecutive_critical_alerts,
            "cooldown_until": self._cooldown_until,
            "cycle_count": self._cycle_count,
            "total_rounds": self._total_rounds,
            "started_at": self._started_at,
            "paused_reason": self._paused_reason,
            "events": self._events[-50:],  # Keep last 50 events
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json_write(WATCHDOG_STATE_FILE, state)

    def _load_state(self):
        """Load persisted state from disk."""
        if not os.path.exists(WATCHDOG_STATE_FILE):
            return
        try:
            with open(WATCHDOG_STATE_FILE) as f:
                state = json.load(f)
            # Only restore counters, not running state
            # (if we crashed, we start fresh but remember history)
            self._consecutive_failures = state.get("consecutive_failures", 0)
            self._consecutive_critical_alerts = state.get(
                "consecutive_critical_alerts", 0)
            self._events = state.get("events", [])[-50:]
            self._cycle_count = state.get("cycle_count", 0)
            self._total_rounds = state.get("total_rounds", 0)
        except (json.JSONDecodeError, OSError, KeyError):
            pass  # Start fresh on corrupt state

    def _record_event(self, event_type: str, message: str,
                      severity: str = "info", details: dict | None = None):
        """Record an event in the audit trail."""
        evt = WatchdogEvent(event_type, message, severity, details)
        self._events.append(evt.to_dict())
        # Trim to last 200 events in memory
        if len(self._events) > 200:
            self._events = self._events[-200:]
        self._save_state()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self):
        """Start the watchdog. Called when daemon begins."""
        with self._lock:
            self._state = SystemState.RUNNING
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._last_heartbeat = time.monotonic()
            self._record_event(
                "watchdog_start", "Watchdog started",
                details={
                    "heartbeat_timeout": HEARTBEAT_TIMEOUT_SECONDS,
                    "circuit_breaker_threshold": CIRCUIT_BREAKER_THRESHOLD,
                    "max_consecutive_failures": MAX_CONSECUTIVE_FAILURES,
                    "hard_cost_ceiling": HARD_COST_CEILING_USD,
                }
            )

    def stop(self):
        """Stop the watchdog. Called when daemon shuts down."""
        with self._lock:
            self._state = SystemState.STOPPED
            self._record_event("watchdog_stop", "Watchdog stopped",
                               details={"cycles": self._cycle_count,
                                        "total_rounds": self._total_rounds})

    # ── Heartbeat ───────────────────────────────────────────────────────

    def heartbeat(self):
        """Record a heartbeat. Call this at least once per round."""
        with self._lock:
            self._last_heartbeat = time.monotonic()

    def is_stalled(self) -> bool:
        """Check if the system appears stalled (no heartbeat for too long)."""
        with self._lock:
            if self._state in (SystemState.STOPPED, SystemState.PAUSED,
                               SystemState.COOLDOWN, SystemState.CIRCUIT_OPEN,
                               SystemState.BUDGET_HALT):
                return False  # Not stalled if intentionally not running
            if self._last_heartbeat == 0:
                return False  # Never started
            elapsed = time.monotonic() - self._last_heartbeat
            return elapsed > HEARTBEAT_TIMEOUT_SECONDS

    def check_stall_and_act(self) -> tuple[bool, str]:
        """
        Check for stall and take corrective action.
        
        Unlike is_stalled() which is passive detection, this method:
        1. Detects the stall
        2. Records the event
        3. Increments failure counter  
        4. Returns (is_stalled, reason) so the daemon can skip/restart
        
        Returns:
            (stalled: bool, reason: str)
            If stalled=True, the caller should abort the current operation.
        """
        with self._lock:
            if self._state in (SystemState.STOPPED, SystemState.PAUSED,
                               SystemState.COOLDOWN, SystemState.CIRCUIT_OPEN,
                               SystemState.BUDGET_HALT):
                return False, "not running"
            if self._last_heartbeat == 0:
                return False, "never started"
            
            elapsed = time.monotonic() - self._last_heartbeat
            if elapsed <= HEARTBEAT_TIMEOUT_SECONDS:
                return False, "ok"
            
            # Stall detected — take action
            self._consecutive_failures += 1
            self._record_event(
                "stall_detected",
                f"System stalled: {elapsed:.0f}s since last heartbeat "
                f"(threshold: {HEARTBEAT_TIMEOUT_SECONDS}s). "
                f"Consecutive failures: {self._consecutive_failures}. "
                f"Forcing skip to next operation.",
                severity="critical",
                details={
                    "elapsed_seconds": round(elapsed),
                    "threshold_seconds": HEARTBEAT_TIMEOUT_SECONDS,
                    "consecutive_failures": self._consecutive_failures,
                }
            )
            
            # Check if we need to enter cooldown
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self._state = SystemState.COOLDOWN
                self._cooldown_until = time.monotonic() + FAILURE_COOLDOWN_SECONDS
                self._record_event(
                    "cooldown_entered",
                    f"Entering cooldown after stall + {self._consecutive_failures} "
                    f"consecutive failures.",
                    severity="critical",
                )
            
            # Reset heartbeat so we don't trigger again immediately
            self._last_heartbeat = time.monotonic()
            
            return True, (
                f"Stalled for {elapsed:.0f}s — forcing recovery "
                f"({self._consecutive_failures} consecutive failures)"
            )

    def get_heartbeat_age(self) -> float:
        """Seconds since last heartbeat."""
        with self._lock:
            if self._last_heartbeat == 0:
                return 0
            return time.monotonic() - self._last_heartbeat

    # ── Pre-Cycle Checks ───────────────────────────────────────────────

    def check_before_cycle(self) -> tuple[bool, str]:
        """
        Run all pre-cycle safety checks.

        Returns:
            (can_proceed: bool, reason: str)

        Checks (in order):
        1. System state allows execution
        2. Cooldown period has elapsed (if applicable)
        3. Hard cost ceiling not exceeded
        4. Circuit breaker not tripped
        """
        with self._lock:
            # 1. Check system state
            if self._state == SystemState.STOPPED:
                return False, "Watchdog is stopped"

            if self._state == SystemState.CIRCUIT_OPEN:
                return False, (
                    f"Circuit breaker OPEN — {self._consecutive_critical_alerts} "
                    f"consecutive critical alerts. Human review required."
                )

            if self._state == SystemState.BUDGET_HALT:
                return False, "Hard cost ceiling reached — halted for the day"

            # 2. Check cooldown
            if self._state == SystemState.COOLDOWN:
                now = time.monotonic()
                if now < self._cooldown_until:
                    remaining = int(self._cooldown_until - now)
                    return False, (
                        f"Cooling down after {self._consecutive_failures} failures. "
                        f"{remaining}s remaining."
                    )
                else:
                    # Cooldown expired — resume
                    self._state = SystemState.RUNNING
                    self._record_event(
                        "cooldown_expired", "Cooldown period ended, resuming",
                        severity="info"
                    )

            # 3. Check hard cost ceiling
            try:
                from cost_tracker import get_daily_spend
                daily = get_daily_spend()
                spent = daily.get("total_usd", 0)
                if spent >= HARD_COST_CEILING_USD:
                    self._state = SystemState.BUDGET_HALT
                    self._record_event(
                        "budget_halt",
                        f"Hard cost ceiling hit: ${spent:.4f} >= ${HARD_COST_CEILING_USD:.2f}",
                        severity="critical",
                        details={"spent": spent, "ceiling": HARD_COST_CEILING_USD}
                    )
                    return False, f"Hard cost ceiling (${HARD_COST_CEILING_USD:.2f}) exceeded"
            except Exception as e:
                # Can't check cost — proceed with caution
                self._record_event(
                    "cost_check_error", f"Cost check failed: {e}",
                    severity="warning"
                )

            # 4. All clear
            if self._state == SystemState.PAUSED:
                self._state = SystemState.RUNNING
                self._record_event(
                    "resumed", f"Resumed from pause: {self._paused_reason}",
                    severity="info"
                )
                self._paused_reason = None

            return True, "OK"

    # ── Post-Cycle Checks ──────────────────────────────────────────────

    def record_cycle_success(self, rounds_completed: int, avg_score: float,
                             cost: float, domain_results: list[dict] | None = None):
        """Record a successful cycle. Resets failure counters."""
        with self._lock:
            self._cycle_count += 1
            self._total_rounds += rounds_completed
            self._consecutive_failures = 0  # Reset on success
            self._consecutive_critical_alerts = 0  # Reset on success
            self._record_event(
                "cycle_success",
                f"Cycle {self._cycle_count}: {rounds_completed} rounds, "
                f"avg {avg_score:.1f}, ${cost:.4f}",
                details={
                    "rounds": rounds_completed,
                    "avg_score": avg_score,
                    "cost": cost,
                    "domains": domain_results or [],
                }
            )

    def record_cycle_failure(self, error: str):
        """Record a failed cycle. Increments failure counter, may trigger cooldown."""
        with self._lock:
            self._cycle_count += 1
            self._consecutive_failures += 1
            self._record_event(
                "cycle_failure",
                f"Cycle {self._cycle_count} failed ({self._consecutive_failures} "
                f"consecutive): {error}",
                severity="warning",
                details={"error": error,
                         "consecutive": self._consecutive_failures}
            )

            # Check if we need to enter cooldown
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self._state = SystemState.COOLDOWN
                self._cooldown_until = time.monotonic() + FAILURE_COOLDOWN_SECONDS
                self._record_event(
                    "cooldown_entered",
                    f"Entering cooldown: {MAX_CONSECUTIVE_FAILURES} consecutive "
                    f"failures. Will resume in {FAILURE_COOLDOWN_SECONDS}s.",
                    severity="critical",
                    details={
                        "consecutive_failures": self._consecutive_failures,
                        "cooldown_seconds": FAILURE_COOLDOWN_SECONDS,
                    }
                )

    # ── Health Check Integration ───────────────────────────────────────

    def run_health_check(self) -> dict:
        """
        Run monitoring health checks and process alerts.

        Integrates with monitoring.py to:
        - Run all 6 health checks (score trends, sudden drops, budget,
          stale domains, rejection rate, error rate)
        - Process critical alerts → may trip circuit breaker
        - Return health snapshot

        Returns:
            Health check result dict from monitoring.run_health_check()
        """
        try:
            from monitoring import run_health_check as _run_health_check
            result = _run_health_check(verbose=False)
        except Exception as e:
            self._record_event(
                "health_check_error", f"Health check failed: {e}",
                severity="warning",
                details={"error": str(e)}
            )
            return {"status": "error", "error": str(e)}

        status = result.get("status", "healthy")

        with self._lock:
            if status == "critical":
                self._consecutive_critical_alerts += 1
                self._record_event(
                    "critical_alert",
                    f"Critical health status ({self._consecutive_critical_alerts} "
                    f"consecutive)",
                    severity="critical",
                    details=result
                )

                # Trip circuit breaker if threshold exceeded
                if self._consecutive_critical_alerts >= CIRCUIT_BREAKER_THRESHOLD:
                    self._state = SystemState.CIRCUIT_OPEN
                    self._record_event(
                        "circuit_breaker_tripped",
                        f"Circuit breaker TRIPPED after "
                        f"{self._consecutive_critical_alerts} consecutive "
                        f"critical alerts. Human review required.",
                        severity="critical",
                        details={
                            "consecutive_critical": self._consecutive_critical_alerts,
                            "threshold": CIRCUIT_BREAKER_THRESHOLD,
                            "last_health": result,
                        }
                    )
            elif status == "warning":
                # Warning doesn't reset critical counter (could escalate)
                self._record_event(
                    "health_warning",
                    f"Health warning: {result.get('alerts_generated', 0)} alert(s)",
                    severity="warning",
                    details=result
                )
            else:
                # Healthy — reset critical counter
                self._consecutive_critical_alerts = 0
                self._record_event(
                    "health_ok",
                    f"Health check passed: {result.get('domains_checked', 0)} domains OK",
                    details=result
                )

        return result

    # ── HEARTBEAT-style Periodic Checks ────────────────────────────────

    def run_heartbeat_checks(self) -> dict:
        """
        HEARTBEAT-style periodic self-checks (inspired by proactive-agent).

        Runs three maintenance checks:
        1. Security integrity — detect unexpected config changes
        2. Resource cleanup — remove old log files
        3. Memory maintenance — flag stale exec_memory checkpoints

        Returns dict with results of each check.
        """
        results = {
            "security": self._check_security_integrity(),
            "cleanup": self._cleanup_old_resources(),
            "memory": self._check_stale_memory(),
        }

        issues = sum(1 for v in results.values() if v.get("issues"))
        severity = "warning" if issues else "info"
        self._record_event(
            "heartbeat_check",
            f"Heartbeat: {3 - issues}/3 checks clean"
            + (f", {issues} with issues" if issues else ""),
            severity=severity,
            details=results,
        )
        return results

    def _check_security_integrity(self) -> dict:
        """Verify critical config values haven't changed unexpectedly."""
        import config as cfg
        snapshot_path = os.path.join(LOG_DIR, "_config_snapshot.json")

        current = {}
        for key in CONFIG_SNAPSHOT_KEYS:
            current[key] = getattr(cfg, key, None)

        # Load previous snapshot
        if os.path.exists(snapshot_path):
            try:
                with open(snapshot_path) as f:
                    previous = json.load(f)
                changed = {
                    k: {"was": previous.get(k), "now": current[k]}
                    for k in current
                    if previous.get(k) is not None and previous.get(k) != current[k]
                }
                if changed:
                    self._record_event(
                        "config_drift",
                        f"Config changed since last check: {list(changed.keys())}",
                        severity="warning",
                        details=changed,
                    )
                    # Save new snapshot (the change is now acknowledged)
                    os.makedirs(LOG_DIR, exist_ok=True)
                    atomic_json_write(snapshot_path, current)
                    return {"ok": True, "issues": list(changed.keys()),
                            "changes": changed}
            except (json.JSONDecodeError, OSError):
                pass  # Corrupt snapshot — recreate

        # Save current snapshot
        os.makedirs(LOG_DIR, exist_ok=True)
        atomic_json_write(snapshot_path, current)
        return {"ok": True, "issues": []}

    def _cleanup_old_resources(self) -> dict:
        """Remove log files older than LOG_RETENTION_DAYS."""
        cleaned = 0
        errors = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)
        cutoff_ts = cutoff.timestamp()

        if not os.path.exists(LOG_DIR):
            return {"cleaned": 0, "errors": 0, "issues": []}

        for fname in os.listdir(LOG_DIR):
            fpath = os.path.join(LOG_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            # Only clean .jsonl log files, not state files
            if not fname.endswith(".jsonl"):
                continue
            try:
                if os.path.getmtime(fpath) < cutoff_ts:
                    os.remove(fpath)
                    cleaned += 1
            except OSError:
                errors += 1

        issues = [f"{errors} files failed to clean"] if errors else []
        return {"cleaned": cleaned, "errors": errors, "issues": issues}

    def _check_stale_memory(self) -> dict:
        """Flag stale exec_memory checkpoint files."""
        stale = []
        checkpoint_dir = os.path.join(EXEC_MEMORY_DIR, "_checkpoints")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_CHECKPOINT_HOURS)
        cutoff_ts = cutoff.timestamp()

        if not os.path.exists(checkpoint_dir):
            return {"stale_checkpoints": [], "issues": []}

        for fname in os.listdir(checkpoint_dir):
            fpath = os.path.join(checkpoint_dir, fname)
            if not fname.endswith(".json"):
                continue
            try:
                if os.path.getmtime(fpath) < cutoff_ts:
                    stale.append(fname)
            except OSError:
                continue

        issues = [f"{len(stale)} stale checkpoints"] if stale else []
        if stale:
            self._record_event(
                "stale_checkpoints",
                f"{len(stale)} checkpoint(s) older than {STALE_CHECKPOINT_HOURS}h",
                severity="warning",
                details={"files": stale},
            )
        return {"stale_checkpoints": stale, "issues": issues}

    # ── Manual Controls ────────────────────────────────────────────────

    def pause(self, reason: str = "manual"):
        """Pause the watchdog (daemon will wait for resume)."""
        with self._lock:
            self._state = SystemState.PAUSED
            self._paused_reason = reason
            self._record_event(
                "paused", f"Watchdog paused: {reason}",
                severity="warning"
            )

    def resume(self):
        """Resume from pause or circuit breaker (human override)."""
        with self._lock:
            old_state = self._state
            self._state = SystemState.RUNNING
            self._consecutive_critical_alerts = 0
            self._consecutive_failures = 0
            self._cooldown_until = 0
            self._paused_reason = None
            self._record_event(
                "resumed",
                f"Watchdog resumed from {old_state.value} (human override)",
                severity="info",
                details={"previous_state": old_state.value}
            )

    def kill(self, reason: str = "manual kill"):
        """Emergency kill switch — immediately stops everything."""
        with self._lock:
            self._state = SystemState.STOPPED
            self._record_event(
                "kill_switch",
                f"KILL SWITCH activated: {reason}",
                severity="critical",
                details={"reason": reason}
            )

    # ── Status ─────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """
        Get consolidated system status.

        Returns a single dict combining watchdog state, health,
        budget, and operational metrics.
        """
        with self._lock:
            # Budget info
            try:
                from cost_tracker import get_daily_spend, check_budget
                daily = get_daily_spend()
                budget = check_budget()
                budget_info = {
                    "spent_today": daily.get("total_usd", 0),
                    "daily_limit": DAILY_BUDGET_USD,
                    "hard_ceiling": HARD_COST_CEILING_USD,
                    "within_budget": budget.get("within_budget", True),
                    "remaining": budget.get("remaining", 0),
                }
            except Exception:
                budget_info = {"error": "Could not retrieve budget info"}

            # System health
            try:
                from agents.orchestrator import get_system_health
                health = get_system_health()
            except Exception:
                health = {"health_score": 0, "error": "Could not retrieve health"}

            return {
                "state": self._state.value,
                "started_at": self._started_at,
                "cycles_completed": self._cycle_count,
                "total_rounds": self._total_rounds,
                "consecutive_failures": self._consecutive_failures,
                "consecutive_critical_alerts": self._consecutive_critical_alerts,
                "heartbeat_age_seconds": round(
                    time.monotonic() - self._last_heartbeat, 1
                ) if self._last_heartbeat > 0 else None,
                "paused_reason": self._paused_reason,
                "budget": budget_info,
                "health": health,
                "recent_events": self._events[-10:],
            }

    def get_events(self, count: int = 20) -> list[dict]:
        """Get recent watchdog events."""
        with self._lock:
            return list(self._events[-count:])


# ── Module-level singleton ─────────────────────────────────────────────

_watchdog: Watchdog | None = None
_watchdog_lock = threading.Lock()


def get_watchdog() -> Watchdog:
    """Get or create the module-level Watchdog singleton."""
    global _watchdog
    if _watchdog is None:
        with _watchdog_lock:
            if _watchdog is None:
                _watchdog = Watchdog()
    return _watchdog


def get_watchdog_status() -> dict:
    """Get watchdog status (convenience function for dashboard/CLI)."""
    return get_watchdog().get_status()
