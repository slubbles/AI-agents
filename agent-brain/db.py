"""
Database Layer — SQLite Backend for Agent Brain

Replaces flat JSON/JSONL files with a proper database for:
- Research outputs (memory)
- Cost tracking (API spend)
- Alerts (monitoring)
- System health snapshots

Design:
- Thread-safe via per-call connections (SQLite handles locking)
- Automatic schema migration on init
- Backward compatible: JSON files still work, DB is an acceleration layer
- All writes go through this module; reads fall back to JSON if DB is empty

Schema version tracked in _schema_version table for future migrations.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone, date
from contextlib import contextmanager
from config import LOG_DIR

DB_PATH = os.path.join(LOG_DIR, "agent_brain.db")
SCHEMA_VERSION = 1

_init_lock = threading.Lock()
_initialized = False


@contextmanager
def get_connection():
    """Thread-safe database connection context manager."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

        with get_connection() as conn:
            # Schema version tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)

            # Check current schema version
            cur = conn.execute("SELECT MAX(version) FROM _schema_version")
            current = cur.fetchone()[0] or 0

            if current < 1:
                _apply_v1(conn)

        _initialized = True


def _apply_v1(conn: sqlite3.Connection):
    """Schema v1 — initial tables."""

    # Research outputs (replaces memory/*.json)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            question TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            attempt INTEGER DEFAULT 1,
            strategy_version TEXT DEFAULT 'default',
            overall_score REAL DEFAULT 0,
            accepted INTEGER DEFAULT 0,
            verdict TEXT DEFAULT 'unknown',
            research_json TEXT,
            critique_json TEXT,
            full_record_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outputs_domain ON outputs(domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outputs_score ON outputs(domain, overall_score)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outputs_timestamp ON outputs(domain, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outputs_strategy ON outputs(domain, strategy_version)")

    # Cost log (replaces logs/costs.jsonl)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            date TEXT NOT NULL,
            model TEXT NOT NULL,
            agent_role TEXT NOT NULL,
            domain TEXT DEFAULT '',
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_costs_date ON costs(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_costs_agent ON costs(agent_role)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_costs_model ON costs(model)")

    # Alerts (new — monitoring)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            domain TEXT DEFAULT '',
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            message TEXT NOT NULL,
            details_json TEXT,
            acknowledged INTEGER DEFAULT 0,
            acknowledged_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(acknowledged)")

    # Health snapshots (new — periodic system state)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'healthy',
            details_json TEXT NOT NULL
        )
    """)

    # Run log (replaces logs/{domain}.jsonl)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            domain TEXT NOT NULL,
            question TEXT NOT NULL,
            attempts INTEGER DEFAULT 1,
            score REAL DEFAULT 0,
            verdict TEXT DEFAULT 'unknown',
            strategy_version TEXT DEFAULT 'default',
            consensus INTEGER DEFAULT 0,
            consensus_level TEXT,
            researchers_used INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runlog_domain ON run_log(domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runlog_timestamp ON run_log(timestamp)")

    # Mark schema version
    conn.execute(
        "INSERT INTO _schema_version (version, applied_at) VALUES (?, ?)",
        (1, datetime.now(timezone.utc).isoformat()),
    )


# ── Output Operations ─────────────────────────────────────────────────────

def insert_output(domain: str, record: dict) -> int:
    """Insert a research output. Returns the row ID."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO outputs
               (domain, question, timestamp, attempt, strategy_version,
                overall_score, accepted, verdict, research_json, critique_json,
                full_record_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                domain,
                record.get("question", ""),
                record.get("timestamp", datetime.now(timezone.utc).isoformat()),
                record.get("attempt", 1),
                record.get("strategy_version", "default"),
                record.get("overall_score", 0),
                1 if record.get("accepted", False) else 0,
                record.get("verdict", "unknown"),
                json.dumps(record.get("research", {})),
                json.dumps(record.get("critique", {})),
                json.dumps(record),
            ),
        )
        return cur.lastrowid


def query_outputs(domain: str, min_score: float = 0, limit: int = 0) -> list[dict]:
    """Query outputs for a domain, optionally filtered by minimum score."""
    init_db()
    with get_connection() as conn:
        sql = "SELECT full_record_json FROM outputs WHERE domain = ? AND overall_score >= ?"
        params = [domain, min_score]
        sql += " ORDER BY timestamp ASC"
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["full_record_json"]) for row in rows]


def count_outputs(domain: str, min_score: float = 0) -> int:
    """Count outputs for a domain."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM outputs WHERE domain = ? AND overall_score >= ?",
            (domain, min_score),
        ).fetchone()
        return row["cnt"]


def get_domain_stats_db(domain: str) -> dict:
    """Get aggregate stats from DB."""
    init_db()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as cnt,
                   COALESCE(AVG(overall_score), 0) as avg_score,
                   SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END) as accepted,
                   SUM(CASE WHEN accepted = 0 THEN 1 ELSE 0 END) as rejected
            FROM outputs WHERE domain = ?
        """, (domain,)).fetchone()
        return {
            "count": row["cnt"],
            "avg_score": round(row["avg_score"], 2),
            "accepted": row["accepted"] or 0,
            "rejected": row["rejected"] or 0,
        }


def list_domains_db() -> list[str]:
    """List all domains that have outputs."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT domain FROM outputs ORDER BY domain"
        ).fetchall()
        return [row["domain"] for row in rows]


def get_recent_scores(domain: str, n: int = 10) -> list[float]:
    """Get the N most recent scores for a domain."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT overall_score FROM outputs WHERE domain = ? ORDER BY timestamp DESC LIMIT ?",
            (domain, n),
        ).fetchall()
        return [row["overall_score"] for row in reversed(rows)]


def get_strategy_scores(domain: str, strategy_version: str) -> list[float]:
    """Get all scores produced under a specific strategy version."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT overall_score FROM outputs WHERE domain = ? AND strategy_version = ? ORDER BY timestamp",
            (domain, strategy_version),
        ).fetchall()
        return [row["overall_score"] for row in rows]


# ── Cost Operations ────────────────────────────────────────────────────────

def insert_cost(entry: dict):
    """Insert a cost log entry."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO costs
               (timestamp, date, model, agent_role, domain,
                input_tokens, output_tokens, estimated_cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.get("timestamp", datetime.now(timezone.utc).isoformat()),
                entry.get("date", date.today().isoformat()),
                entry.get("model", "unknown"),
                entry.get("agent_role", "unknown"),
                entry.get("domain", ""),
                entry.get("input_tokens", 0),
                entry.get("output_tokens", 0),
                entry.get("estimated_cost_usd", 0),
            ),
        )


def get_daily_spend_db(target_date: str | None = None) -> dict:
    """Get total spend for a date from DB."""
    init_db()
    if target_date is None:
        target_date = date.today().isoformat()

    with get_connection() as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(estimated_cost_usd), 0) as total,
                   COUNT(*) as calls
            FROM costs WHERE date = ?
        """, (target_date,)).fetchone()

        by_agent = {}
        for r in conn.execute(
            "SELECT agent_role, SUM(estimated_cost_usd) as s FROM costs WHERE date = ? GROUP BY agent_role",
            (target_date,),
        ).fetchall():
            by_agent[r["agent_role"]] = round(r["s"], 4)

        by_model = {}
        for r in conn.execute(
            "SELECT model, SUM(estimated_cost_usd) as s FROM costs WHERE date = ? GROUP BY model",
            (target_date,),
        ).fetchall():
            by_model[r["model"]] = round(r["s"], 4)

        return {
            "date": target_date,
            "total_usd": round(row["total"], 4),
            "calls": row["calls"],
            "by_agent": by_agent,
            "by_model": by_model,
        }


def get_all_time_spend_db() -> dict:
    """Get total all-time spend from DB."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) as total, COUNT(*) as calls FROM costs"
        ).fetchone()

        by_date = {}
        for r in conn.execute(
            "SELECT date, SUM(estimated_cost_usd) as s FROM costs GROUP BY date ORDER BY date"
        ).fetchall():
            by_date[r["date"]] = round(r["s"], 4)

        return {
            "total_usd": round(row["total"], 4),
            "calls": row["calls"],
            "days": len(by_date),
            "by_date": by_date,
        }


# ── Alert Operations ───────────────────────────────────────────────────────

def insert_alert(
    alert_type: str,
    message: str,
    severity: str = "warning",
    domain: str = "",
    details: dict | None = None,
) -> int:
    """Insert a monitoring alert. Returns alert ID."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO alerts (timestamp, domain, alert_type, severity, message, details_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                domain,
                alert_type,
                severity,
                message,
                json.dumps(details) if details else None,
            ),
        )
        return cur.lastrowid


def get_alerts(
    acknowledged: bool | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query alerts with optional filters."""
    init_db()
    with get_connection() as conn:
        sql = "SELECT * FROM alerts WHERE 1=1"
        params = []

        if acknowledged is not None:
            sql += " AND acknowledged = ?"
            params.append(1 if acknowledged else 0)
        if severity:
            sql += " AND severity = ?"
            params.append(severity)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if d.get("details_json"):
                d["details"] = json.loads(d["details_json"])
            del d["details_json"]
            results.append(d)
        return results


def acknowledge_alert(alert_id: int):
    """Mark an alert as acknowledged."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            "UPDATE alerts SET acknowledged = 1, acknowledged_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), alert_id),
        )


def get_alert_summary() -> dict:
    """Get alert counts by type and severity."""
    init_db()
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM alerts").fetchone()["c"]
        unack = conn.execute(
            "SELECT COUNT(*) as c FROM alerts WHERE acknowledged = 0"
        ).fetchone()["c"]

        by_severity = {}
        for r in conn.execute(
            "SELECT severity, COUNT(*) as c FROM alerts WHERE acknowledged = 0 GROUP BY severity"
        ).fetchall():
            by_severity[r["severity"]] = r["c"]

        by_type = {}
        for r in conn.execute(
            "SELECT alert_type, COUNT(*) as c FROM alerts WHERE acknowledged = 0 GROUP BY alert_type"
        ).fetchall():
            by_type[r["alert_type"]] = r["c"]

        return {
            "total": total,
            "unacknowledged": unack,
            "by_severity": by_severity,
            "by_type": by_type,
        }


# ── Health Snapshots ───────────────────────────────────────────────────────

def insert_health_snapshot(status: str, details: dict) -> int:
    """Record a health snapshot."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO health_snapshots (timestamp, status, details_json) VALUES (?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), status, json.dumps(details)),
        )
        return cur.lastrowid


def get_latest_health() -> dict | None:
    """Get the most recent health snapshot."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM health_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["details"] = json.loads(d["details_json"])
        del d["details_json"]
        return d


# ── Run Log Operations ─────────────────────────────────────────────────────

def insert_run_log(entry: dict):
    """Insert a run log entry."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO run_log
               (timestamp, domain, question, attempts, score, verdict,
                strategy_version, consensus, consensus_level, researchers_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.get("timestamp", datetime.now(timezone.utc).isoformat()),
                entry.get("domain", ""),
                entry.get("question", ""),
                entry.get("attempts", 1),
                entry.get("score", 0),
                entry.get("verdict", "unknown"),
                entry.get("strategy_version", "default"),
                1 if entry.get("consensus", False) else 0,
                entry.get("consensus_level"),
                entry.get("researchers_used"),
            ),
        )


def get_run_history(domain: str | None = None, limit: int = 50) -> list[dict]:
    """Get recent run history."""
    init_db()
    with get_connection() as conn:
        if domain:
            rows = conn.execute(
                "SELECT * FROM run_log WHERE domain = ? ORDER BY timestamp DESC LIMIT ?",
                (domain, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM run_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


# ── Migration: Import from JSON files ──────────────────────────────────────

def migrate_from_json(memory_dir: str, log_dir: str, verbose: bool = True) -> dict:
    """
    Import existing JSON/JSONL files into SQLite.
    Idempotent — skips rows that already exist (by timestamp match).

    Returns:
        {outputs_imported, costs_imported, runs_imported, skipped, errors}
    """
    init_db()
    stats = {"outputs_imported": 0, "costs_imported": 0, "runs_imported": 0, "skipped": 0, "errors": []}

    # Import memory outputs
    if os.path.exists(memory_dir):
        for domain_name in sorted(os.listdir(memory_dir)):
            domain_path = os.path.join(memory_dir, domain_name)
            if not os.path.isdir(domain_path) or domain_name.startswith("_"):
                continue
            for filename in sorted(os.listdir(domain_path)):
                if not filename.endswith(".json") or filename.startswith("_"):
                    continue
                filepath = os.path.join(domain_path, filename)
                try:
                    with open(filepath) as f:
                        record = json.load(f)

                    # Check if already imported (by timestamp + domain)
                    ts = record.get("timestamp", "")
                    with get_connection() as conn:
                        existing = conn.execute(
                            "SELECT id FROM outputs WHERE domain = ? AND timestamp = ?",
                            (domain_name, ts),
                        ).fetchone()
                        if existing:
                            stats["skipped"] += 1
                            continue

                    insert_output(domain_name, record)
                    stats["outputs_imported"] += 1
                    if verbose:
                        print(f"  Imported: {domain_name}/{filename}")
                except Exception as e:
                    stats["errors"].append(f"{domain_name}/{filename}: {e}")

    # Import cost logs
    cost_log = os.path.join(log_dir, "costs.jsonl")
    if os.path.exists(cost_log):
        with open(cost_log) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Check for duplicate by timestamp
                    ts = entry.get("timestamp", "")
                    with get_connection() as conn:
                        existing = conn.execute(
                            "SELECT id FROM costs WHERE timestamp = ?", (ts,)
                        ).fetchone()
                        if existing:
                            stats["skipped"] += 1
                            continue
                    insert_cost(entry)
                    stats["costs_imported"] += 1
                except Exception as e:
                    stats["errors"].append(f"costs.jsonl line {line_num}: {e}")

    # Import run logs
    if os.path.exists(log_dir):
        for filename in sorted(os.listdir(log_dir)):
            if not filename.endswith(".jsonl") or filename == "costs.jsonl":
                continue
            domain_name = filename.replace(".jsonl", "")
            filepath = os.path.join(log_dir, filename)
            with open(filepath) as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry["domain"] = domain_name
                        ts = entry.get("timestamp", "")
                        with get_connection() as conn:
                            existing = conn.execute(
                                "SELECT id FROM run_log WHERE domain = ? AND timestamp = ?",
                                (domain_name, ts),
                            ).fetchone()
                            if existing:
                                stats["skipped"] += 1
                                continue
                        insert_run_log(entry)
                        stats["runs_imported"] += 1
                    except Exception as e:
                        stats["errors"].append(f"{filename} line {line_num}: {e}")

    if verbose:
        print(f"\n  Migration complete:")
        print(f"    Outputs: {stats['outputs_imported']}")
        print(f"    Costs:   {stats['costs_imported']}")
        print(f"    Runs:    {stats['runs_imported']}")
        print(f"    Skipped: {stats['skipped']}")
        if stats["errors"]:
            print(f"    Errors:  {len(stats['errors'])}")
            for e in stats["errors"][:5]:
                print(f"      {e}")

    return stats
