"""
Tests for Production Hardening:
1. SQLite database layer (db.py)
2. Persistent TF-IDF vector cache
3. Graceful error recovery
4. Score trend monitoring + alerts
5. Health check endpoint
6. Integration test (mock-LLM full loop)

No API calls — all tests use temp directories and mocked agents.
"""

import json
import os
import sys
import sqlite3
import pickle
from datetime import datetime, timezone, timedelta, date
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Shared Fixtures
# ============================================================

@pytest.fixture
def tmp_dirs(tmp_path):
    """Create temporary directories for all stores."""
    mem_dir = str(tmp_path / "memory")
    strat_dir = str(tmp_path / "strategies")
    log_dir = str(tmp_path / "logs")
    os.makedirs(mem_dir)
    os.makedirs(strat_dir)
    os.makedirs(log_dir)
    return {"memory": mem_dir, "strategies": strat_dir, "logs": log_dir}


@pytest.fixture
def tmp_db(tmp_path):
    """Create a fresh temp database."""
    db_path = str(tmp_path / "test.db")
    with patch("db.DB_PATH", db_path), patch("db._initialized", False):
        import db
        db._initialized = False
        db.DB_PATH = db_path
        db.init_db()
        yield db_path


def _make_output(question, score, accepted=True, timestamp=None, findings=None, 
                 domain="test", strategy_version="default"):
    """Helper to create mock output."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": timestamp,
        "domain": domain,
        "question": question,
        "attempt": 1,
        "strategy_version": strategy_version,
        "overall_score": score,
        "accepted": accepted,
        "verdict": "accept" if accepted else "reject",
        "research": {
            "summary": f"Summary for: {question}",
            "findings": findings or [{"claim": f"Finding about {question}", "confidence": "high"}],
            "key_insights": [f"Insight about {question}"],
            "knowledge_gaps": [],
        },
        "critique": {
            "overall_score": score,
            "verdict": "accept" if accepted else "reject",
            "scores": {"accuracy": score, "depth": score},
            "strengths": ["Good coverage"],
            "weaknesses": [],
        },
    }


# ============================================================
# 1. SQLite Database Tests
# ============================================================

class TestDatabase:
    """Tests for db.py."""

    def test_init_creates_tables(self, tmp_path):
        """init_db creates all required tables."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            conn = sqlite3.connect(db_path)
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            conn.close()

            assert "outputs" in tables
            assert "costs" in tables
            assert "alerts" in tables
            assert "health_snapshots" in tables
            assert "run_log" in tables
            assert "_schema_version" in tables

    def test_init_idempotent(self, tmp_path):
        """init_db can be called multiple times safely."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()
            db._initialized = False  # Force re-init
            db.init_db()  # Should not fail

    def test_insert_and_query_output(self, tmp_path):
        """Insert an output and query it back."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            record = _make_output("What is AI?", 7.5)
            row_id = db.insert_output("test", record)
            assert row_id >= 1

            results = db.query_outputs("test")
            assert len(results) == 1
            assert results[0]["question"] == "What is AI?"
            assert results[0]["overall_score"] == 7.5

    def test_query_outputs_min_score(self, tmp_path):
        """query_outputs filters by minimum score."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_output("test", _make_output("Q1", 3.0, accepted=False))
            db.insert_output("test", _make_output("Q2", 7.0))
            db.insert_output("test", _make_output("Q3", 9.0))

            all_results = db.query_outputs("test", min_score=0)
            assert len(all_results) == 3

            high_only = db.query_outputs("test", min_score=6)
            assert len(high_only) == 2

    def test_count_outputs(self, tmp_path):
        """count_outputs returns correct count."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_output("test", _make_output("Q1", 5.0))
            db.insert_output("test", _make_output("Q2", 8.0))
            db.insert_output("other", _make_output("Q3", 7.0, domain="other"))

            assert db.count_outputs("test") == 2
            assert db.count_outputs("other") == 1
            assert db.count_outputs("missing") == 0

    def test_domain_stats_db(self, tmp_path):
        """get_domain_stats_db returns correct aggregates."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_output("test", _make_output("Q1", 6.0))
            db.insert_output("test", _make_output("Q2", 8.0))
            db.insert_output("test", _make_output("Q3", 4.0, accepted=False))

            stats = db.get_domain_stats_db("test")
            assert stats["count"] == 3
            assert 5.5 < stats["avg_score"] < 6.5
            assert stats["accepted"] == 2
            assert stats["rejected"] == 1

    def test_list_domains_db(self, tmp_path):
        """list_domains_db returns all domains with data."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_output("crypto", _make_output("Q1", 7.0, domain="crypto"))
            db.insert_output("ai", _make_output("Q2", 8.0, domain="ai"))
            db.insert_output("crypto", _make_output("Q3", 6.0, domain="crypto"))

            domains = db.list_domains_db()
            assert "ai" in domains
            assert "crypto" in domains
            assert len(domains) == 2

    def test_insert_and_query_cost(self, tmp_path):
        """Cost logging works in DB."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "date": date.today().isoformat(),
                "model": "claude-haiku-4-5-20251001",
                "agent_role": "researcher",
                "domain": "test",
                "input_tokens": 1000,
                "output_tokens": 500,
                "estimated_cost_usd": 0.0035,
            }
            db.insert_cost(entry)

            result = db.get_daily_spend_db()
            assert result["total_usd"] == 0.0035
            assert result["calls"] == 1
            assert "researcher" in result["by_agent"]

    def test_all_time_spend_db(self, tmp_path):
        """All-time spend aggregation works."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            for i in range(3):
                db.insert_cost({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "date": f"2025-02-{20+i:02d}",
                    "model": "test-model",
                    "agent_role": "researcher",
                    "domain": "test",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "estimated_cost_usd": 0.01,
                })

            result = db.get_all_time_spend_db()
            assert result["total_usd"] == 0.03
            assert result["calls"] == 3
            assert result["days"] == 3

    def test_insert_and_query_alerts(self, tmp_path):
        """Alert CRUD operations work."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            alert_id = db.insert_alert(
                alert_type="declining_scores",
                message="Scores are declining",
                severity="warning",
                domain="test",
                details={"trend": -0.5},
            )
            assert alert_id >= 1

            alerts = db.get_alerts()
            assert len(alerts) == 1
            assert alerts[0]["alert_type"] == "declining_scores"
            assert alerts[0]["acknowledged"] == 0
            assert alerts[0]["details"]["trend"] == -0.5

            # Acknowledge
            db.acknowledge_alert(alert_id)
            unacked = db.get_alerts(acknowledged=False)
            assert len(unacked) == 0
            acked = db.get_alerts(acknowledged=True)
            assert len(acked) == 1

    def test_alert_summary(self, tmp_path):
        """Alert summary aggregation works."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_alert("declining_scores", "Test1", severity="warning")
            db.insert_alert("sudden_drop", "Test2", severity="critical")
            db.insert_alert("budget_warning", "Test3", severity="warning")

            summary = db.get_alert_summary()
            assert summary["total"] == 3
            assert summary["unacknowledged"] == 3
            assert summary["by_severity"]["warning"] == 2
            assert summary["by_severity"]["critical"] == 1

    def test_health_snapshot(self, tmp_path):
        """Health snapshot insert and retrieve."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_health_snapshot("healthy", {"checks": 6, "alerts": 0})
            latest = db.get_latest_health()
            assert latest is not None
            assert latest["status"] == "healthy"
            assert latest["details"]["checks"] == 6

    def test_run_log(self, tmp_path):
        """Run log insert and query."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_run_log({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "domain": "test",
                "question": "What is X?",
                "attempts": 2,
                "score": 7.5,
                "verdict": "accept",
                "strategy_version": "v002",
            })

            history = db.get_run_history("test")
            assert len(history) == 1
            assert history[0]["score"] == 7.5
            assert history[0]["strategy_version"] == "v002"

    def test_recent_scores(self, tmp_path):
        """get_recent_scores returns most recent N scores in order."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            for i, s in enumerate([5, 6, 7, 8, 9]):
                ts = f"2025-02-{20+i:02d}T12:00:00+00:00"
                db.insert_output("test", _make_output(f"Q{i}", s, timestamp=ts))

            recent = db.get_recent_scores("test", n=3)
            assert recent == [7.0, 8.0, 9.0]  # Last 3 in chronological order

    def test_strategy_scores(self, tmp_path):
        """get_strategy_scores filters by strategy version."""
        db_path = str(tmp_path / "test.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            db.insert_output("test", _make_output("Q1", 5.0, strategy_version="v001"))
            db.insert_output("test", _make_output("Q2", 7.0, strategy_version="v002"))
            db.insert_output("test", _make_output("Q3", 8.0, strategy_version="v002"))

            v2_scores = db.get_strategy_scores("test", "v002")
            assert len(v2_scores) == 2
            assert all(s >= 7.0 for s in v2_scores)

    def test_migrate_from_json(self, tmp_dirs):
        """Migration imports JSON files into SQLite."""
        mem_dir = tmp_dirs["memory"]
        log_dir = tmp_dirs["logs"]

        # Create a memory output file
        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)
        record = _make_output("What is AI?", 7.5)
        with open(os.path.join(domain_dir, "20250223_120000_000000_1_score8.json"), "w") as f:
            json.dump(record, f)

        # Create a cost log
        with open(os.path.join(log_dir, "costs.jsonl"), "w") as f:
            f.write(json.dumps({
                "timestamp": "2025-02-23T12:00:00+00:00",
                "date": "2025-02-23",
                "model": "test",
                "agent_role": "researcher",
                "domain": "test",
                "input_tokens": 100,
                "output_tokens": 50,
                "estimated_cost_usd": 0.001,
            }) + "\n")

        # Create a run log
        with open(os.path.join(log_dir, "test.jsonl"), "w") as f:
            f.write(json.dumps({
                "timestamp": "2025-02-23T12:00:00+00:00",
                "question": "What is AI?",
                "attempts": 1,
                "score": 7.5,
                "verdict": "accept",
                "strategy_version": "default",
            }) + "\n")

        db_path = os.path.join(log_dir, "test_migrate.db")
        with patch("db.DB_PATH", db_path), patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path

            result = db.migrate_from_json(mem_dir, log_dir, verbose=False)
            assert result["outputs_imported"] == 1
            assert result["costs_imported"] == 1
            assert result["runs_imported"] == 1

            # Second run should skip (idempotent)
            db._initialized = True
            result2 = db.migrate_from_json(mem_dir, log_dir, verbose=False)
            assert result2["outputs_imported"] == 0
            assert result2["skipped"] >= 1


# ============================================================
# 2. Persistent TF-IDF Cache Tests
# ============================================================

class TestTFIDFCache:
    """Tests for persistent TF-IDF vector cache in memory_store.py."""

    def test_cache_created_on_retrieve(self, tmp_path):
        """TF-IDF cache is created on disk after first retrieve_relevant call."""
        mem_dir = str(tmp_path / "memory")
        os.makedirs(mem_dir)
        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)

        # Create enough outputs for TF-IDF (need >= 2)
        for i in range(3):
            record = _make_output(f"Question about topic {i}", 7.0 + i,
                                  findings=[{"claim": f"Finding {i} about AI and machine learning", "confidence": "high"}])
            filename = f"2025022{i}_120000_000000_1_score{7+i}.json"
            with open(os.path.join(domain_dir, filename), "w") as f:
                json.dump(record, f)

        with patch("memory_store.MEMORY_DIR", mem_dir):
            import memory_store
            memory_store._tfidf_cache.clear()  # Clear in-memory cache

            results = memory_store.retrieve_relevant("test", "What about AI?")

            # Check that cache was created on disk
            cache_file = os.path.join(domain_dir, "_cache", "tfidf_cache.pkl")
            assert os.path.exists(cache_file)

    def test_cache_used_on_second_call(self, tmp_path):
        """Second retrieve_relevant uses cached vectorizer instead of rebuilding."""
        mem_dir = str(tmp_path / "memory")
        os.makedirs(mem_dir)
        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)

        for i in range(3):
            record = _make_output(f"Question about topic {i}", 7.0,
                                  findings=[{"claim": f"Claim {i} about technology", "confidence": "high"}])
            filename = f"2025022{i}_120000_000000_1_score7.json"
            with open(os.path.join(domain_dir, filename), "w") as f:
                json.dump(record, f)

        with patch("memory_store.MEMORY_DIR", mem_dir):
            import memory_store
            memory_store._tfidf_cache.clear()

            # First call — builds cache
            memory_store.retrieve_relevant("test", "technology")

            # Check in-memory cache is populated
            assert "test" in memory_store._tfidf_cache
            fingerprint1 = memory_store._tfidf_cache["test"]["fingerprint"]

            # Second call — should use cache (same fingerprint)
            memory_store.retrieve_relevant("test", "AI advancements")
            fingerprint2 = memory_store._tfidf_cache["test"]["fingerprint"]
            assert fingerprint1 == fingerprint2

    def test_cache_invalidated_on_new_output(self, tmp_path):
        """Cache is invalidated when a new output is saved."""
        mem_dir = str(tmp_path / "memory")
        os.makedirs(mem_dir)
        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)

        for i in range(2):
            record = _make_output(f"Q{i}", 7.0, 
                                  findings=[{"claim": f"Claim {i}", "confidence": "high"}])
            filename = f"2025022{i}_120000_000000_1_score7.json"
            with open(os.path.join(domain_dir, filename), "w") as f:
                json.dump(record, f)

        with patch("memory_store.MEMORY_DIR", mem_dir):
            import memory_store

            # Build cache
            memory_store._tfidf_cache.clear()
            memory_store.retrieve_relevant("test", "query")
            assert "test" in memory_store._tfidf_cache

            # Invalidate
            memory_store.invalidate_tfidf_cache("test")
            assert "test" not in memory_store._tfidf_cache

    def test_fingerprint_changes_with_new_data(self, tmp_path):
        """Fingerprint changes when output count changes, forcing rebuild."""
        from memory_store import _compute_fingerprint

        outputs1 = [_make_output("Q1", 7.0, timestamp="2025-01-01T12:00:00+00:00")]
        outputs2 = outputs1 + [_make_output("Q2", 8.0, timestamp="2025-01-02T12:00:00+00:00")]

        fp1 = _compute_fingerprint(outputs1)
        fp2 = _compute_fingerprint(outputs2)
        assert fp1 != fp2

    def test_disk_cache_loads(self, tmp_path):
        """Cache saved to disk can be loaded back."""
        mem_dir = str(tmp_path / "memory")
        os.makedirs(mem_dir)
        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)

        for i in range(3):
            record = _make_output(f"Q{i}", 7.0,
                                  findings=[{"claim": f"Claim about subject {i}", "confidence": "high"}])
            filename = f"2025022{i}_120000_000000_1_score7.json"
            with open(os.path.join(domain_dir, filename), "w") as f:
                json.dump(record, f)

        with patch("memory_store.MEMORY_DIR", mem_dir):
            import memory_store

            # First call — builds and saves cache
            memory_store._tfidf_cache.clear()
            memory_store.retrieve_relevant("test", "subject")

            # Get fingerprint from in-memory cache
            fp = memory_store._tfidf_cache["test"]["fingerprint"]

            # Clear in-memory, should load from disk
            memory_store._tfidf_cache.clear()
            results = memory_store.retrieve_relevant("test", "subject")
            assert "test" in memory_store._tfidf_cache
            assert memory_store._tfidf_cache["test"]["fingerprint"] == fp


# ============================================================
# 3. Graceful Error Recovery Tests
# ============================================================

class TestErrorRecovery:
    """Tests for graceful error recovery in main.py."""

    def test_run_loop_catches_researcher_crash(self, tmp_path):
        """run_loop handles researcher API crash gracefully."""
        mem_dir = str(tmp_path / "memory")
        log_dir = str(tmp_path / "logs")
        os.makedirs(mem_dir)
        os.makedirs(log_dir)

        with patch("main.research", side_effect=Exception("API overloaded")), \
             patch("main.check_budget", return_value={"within_budget": True, "remaining": 5.0, "spent": 0}), \
             patch("main.get_strategy", return_value=(None, "default")), \
             patch("main.get_strategy_status", return_value="active"), \
             patch("main.load_principles", return_value=None), \
             patch("main.LOG_DIR", log_dir), \
             patch("main.CONSENSUS_ENABLED", False):

            from main import run_loop
            result = run_loop("Test question", "test")

            # Should return error dict instead of crashing
            assert "error" in result
            assert "API overloaded" in result["error"]

    def test_error_logged_to_file(self, tmp_path):
        """Errors are logged to errors.jsonl."""
        log_dir = str(tmp_path / "logs")
        os.makedirs(log_dir)

        with patch("main.LOG_DIR", log_dir):
            from main import _log_error
            _log_error("test", "What is X?", "TestError: something broke")

            error_log = os.path.join(log_dir, "errors.jsonl")
            assert os.path.exists(error_log)
            with open(error_log) as f:
                entry = json.loads(f.readline())
            assert entry["domain"] == "test"
            assert "TestError" in entry["error"]


# ============================================================
# 4. Score Trend Monitoring Tests
# ============================================================

class TestMonitoring:
    """Tests for monitoring.py — automated alerts."""

    def test_check_score_trends_declining(self, tmp_path):
        """Declining scores trigger an alert."""
        mem_dir = str(tmp_path / "memory")
        log_dir = str(tmp_path / "logs")
        db_path = str(tmp_path / "test.db")
        os.makedirs(mem_dir)
        os.makedirs(log_dir)

        # Create domain with declining scores
        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)
        scores = [9, 8, 7, 6, 5, 4, 3, 3, 2, 2]
        for i, s in enumerate(scores):
            record = _make_output(f"Q{i}", s, accepted=s >= 6,
                                  timestamp=f"2025-02-{10+i:02d}T12:00:00+00:00")
            filename = f"202502{10+i}_120000_{i:06d}_1_score{s}.json"
            with open(os.path.join(domain_dir, filename), "w") as f:
                json.dump(record, f)

        with patch("monitoring.MEMORY_DIR", mem_dir), \
             patch("db.DB_PATH", db_path), \
             patch("db._initialized", False), \
             patch("analytics.MEMORY_DIR", mem_dir), \
             patch("memory_store.MEMORY_DIR", mem_dir):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            from monitoring import check_score_trends
            alerts = check_score_trends(verbose=False)
            assert len(alerts) >= 1
            assert alerts[0]["type"] == "declining_scores"

    def test_check_budget_warning(self, tmp_path):
        """Budget usage >80% triggers warning."""
        db_path = str(tmp_path / "test.db")

        with patch("db.DB_PATH", db_path), \
             patch("db._initialized", False), \
             patch("monitoring.get_daily_spend", return_value={"total_usd": 4.5}), \
             patch("monitoring.DAILY_BUDGET_USD", 5.0):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            from monitoring import check_budget_warnings
            alerts = check_budget_warnings(verbose=False)
            assert len(alerts) == 1
            assert alerts[0]["type"] == "budget_warning"

    def test_check_rejection_rate(self, tmp_path):
        """High rejection rate triggers alert."""
        mem_dir = str(tmp_path / "memory")
        db_path = str(tmp_path / "test.db")
        os.makedirs(mem_dir)

        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)

        # 8/10 rejected = 80% rejection rate
        for i in range(10):
            accepted = i >= 8  # Only last 2 accepted
            score = 7.0 if accepted else 3.0
            record = _make_output(f"Q{i}", score, accepted=accepted,
                                  timestamp=f"2025-02-{10+i:02d}T12:00:00+00:00")
            filename = f"202502{10+i}_120000_{i:06d}_1_score{int(score)}.json"
            with open(os.path.join(domain_dir, filename), "w") as f:
                json.dump(record, f)

        with patch("monitoring.MEMORY_DIR", mem_dir), \
             patch("db.DB_PATH", db_path), \
             patch("db._initialized", False), \
             patch("memory_store.MEMORY_DIR", mem_dir):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            from monitoring import check_rejection_rate
            alerts = check_rejection_rate(verbose=False)
            assert len(alerts) >= 1
            assert alerts[0]["type"] == "high_rejection_rate"

    def test_check_error_rate_healthy(self, tmp_path):
        """No error log = no error alerts."""
        db_path = str(tmp_path / "test.db")
        log_dir = str(tmp_path / "logs")
        os.makedirs(log_dir)

        with patch("db.DB_PATH", db_path), \
             patch("db._initialized", False), \
             patch("monitoring.LOG_DIR", log_dir):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            from monitoring import check_error_rate
            alerts = check_error_rate(verbose=False)
            assert len(alerts) == 0

    def test_run_health_check_aggregates(self, tmp_path):
        """run_health_check runs all checks and produces snapshot."""
        mem_dir = str(tmp_path / "memory")
        log_dir = str(tmp_path / "logs")
        db_path = str(tmp_path / "test.db")
        os.makedirs(mem_dir)
        os.makedirs(log_dir)

        with patch("monitoring.MEMORY_DIR", mem_dir), \
             patch("monitoring.LOG_DIR", log_dir), \
             patch("db.DB_PATH", db_path), \
             patch("db._initialized", False), \
             patch("monitoring.get_daily_spend", return_value={"total_usd": 0.5}), \
             patch("monitoring.DAILY_BUDGET_USD", 5.0), \
             patch("memory_store.MEMORY_DIR", mem_dir), \
             patch("analytics.MEMORY_DIR", mem_dir):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            from monitoring import run_health_check
            result = run_health_check(verbose=False)

            assert "status" in result
            assert result["status"] in ("healthy", "warning", "critical")
            assert "checks" in result

    def test_stale_domain_detection(self, tmp_path):
        """Domains with old outputs generate stale alerts."""
        mem_dir = str(tmp_path / "memory")
        db_path = str(tmp_path / "test.db")
        os.makedirs(mem_dir)

        domain_dir = os.path.join(mem_dir, "test")
        os.makedirs(domain_dir)

        # Create output from 30 days ago
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        record = _make_output("Old question", 7.0, timestamp=old_ts)
        with open(os.path.join(domain_dir, "20250101_120000_000000_1_score7.json"), "w") as f:
            json.dump(record, f)

        with patch("monitoring.MEMORY_DIR", mem_dir), \
             patch("db.DB_PATH", db_path), \
             patch("db._initialized", False), \
             patch("memory_store.MEMORY_DIR", mem_dir):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            from monitoring import check_stale_domains
            alerts = check_stale_domains(verbose=False)
            assert len(alerts) >= 1
            assert alerts[0]["type"] == "stale_domain"


# ============================================================
# 5. Cost Tracker Dual-Write Tests
# ============================================================

class TestCostTrackerDualWrite:
    """Tests for dual-write in cost_tracker.py."""

    def test_log_cost_writes_jsonl(self, tmp_path):
        """log_cost still writes JSONL file."""
        log_dir = str(tmp_path / "logs")
        db_path = str(tmp_path / "test.db")
        os.makedirs(log_dir)

        with patch("cost_tracker.LOG_DIR", log_dir), \
             patch("cost_tracker.COST_LOG", os.path.join(log_dir, "costs.jsonl")), \
             patch("db.DB_PATH", db_path), \
             patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path

            from cost_tracker import log_cost
            cost = log_cost("test-model", 100, 50, "researcher", "test")
            assert cost > 0

            jsonl_path = os.path.join(log_dir, "costs.jsonl")
            assert os.path.exists(jsonl_path)
            with open(jsonl_path) as f:
                entry = json.loads(f.readline())
            assert entry["model"] == "test-model"


# ============================================================
# 6. Integration Test (Mock LLM Full Loop)
# ============================================================

class TestIntegration:
    """Integration tests running the full loop with mocked LLM calls."""

    def test_full_loop_with_mock_agents(self, tmp_path):
        """Full run_loop executes end-to-end with mocked agent calls."""
        mem_dir = str(tmp_path / "memory")
        log_dir = str(tmp_path / "logs")
        strat_dir = str(tmp_path / "strategies")
        db_path = str(tmp_path / "test.db")
        os.makedirs(mem_dir)
        os.makedirs(log_dir)
        os.makedirs(strat_dir)

        mock_research = {
            "summary": "Bitcoin ETFs approved in January 2024",
            "findings": [
                {"claim": "11 spot Bitcoin ETFs approved by SEC", "confidence": "high", "source": "SEC.gov"},
                {"claim": "BlackRock iShares Bitcoin Trust (IBIT) leads inflows", "confidence": "high"},
            ],
            "key_insights": ["ETF approval drove institutional adoption"],
            "knowledge_gaps": ["Long-term impact on crypto prices"],
        }

        mock_critique = {
            "overall_score": 7.5,
            "verdict": "accept",
            "scores": {"accuracy": 8, "depth": 7, "completeness": 7, "specificity": 8, "intellectual_honesty": 7},
            "strengths": ["Specific data points", "Verified sources"],
            "weaknesses": ["Missing fee comparison"],
            "actionable_feedback": "Add fee structures",
        }

        with patch("main.research", return_value=mock_research), \
             patch("main.critique", return_value=mock_critique), \
             patch("main.check_budget", return_value={"within_budget": True, "remaining": 5.0, "spent": 0}), \
             patch("main.get_strategy", return_value=(None, "default")), \
             patch("main.get_strategy_status", return_value="active"), \
             patch("main.load_principles", return_value=None), \
             patch("main.evaluate_trial", return_value={"action": "no_trial", "reason": "N/A"}), \
             patch("main.LOG_DIR", log_dir), \
             patch("main.CONSENSUS_ENABLED", False), \
             patch("memory_store.MEMORY_DIR", mem_dir), \
             patch("db.DB_PATH", db_path), \
             patch("db._initialized", False):

            import db
            db._initialized = False
            db.DB_PATH = db_path

            from main import run_loop
            result = run_loop("What are Bitcoin ETF developments?", "crypto")

            # Verify result
            assert "error" not in result
            assert result["critique"]["overall_score"] == 7.5
            assert result["attempts"] == 1

            # Verify output was saved to memory
            outputs = os.listdir(os.path.join(mem_dir, "crypto"))
            json_files = [f for f in outputs if f.endswith(".json") and not f.startswith("_")]
            assert len(json_files) >= 1

    def test_full_loop_with_retry(self, tmp_path):
        """Loop retries on low score and succeeds on second attempt."""
        mem_dir = str(tmp_path / "memory")
        log_dir = str(tmp_path / "logs")
        os.makedirs(mem_dir)
        os.makedirs(log_dir)

        call_count = [0]

        def mock_research_fn(**kwargs):
            call_count[0] += 1
            return {
                "summary": f"Attempt {call_count[0]} findings",
                "findings": [{"claim": f"Finding from attempt {call_count[0]}", "confidence": "high"}],
                "key_insights": ["Insight"],
                "knowledge_gaps": [],
            }

        def mock_critique_fn(research_output, domain=None):
            # First attempt gets low score, second gets high
            if call_count[0] <= 1:
                return {
                    "overall_score": 4.0,
                    "verdict": "reject",
                    "scores": {"accuracy": 4},
                    "strengths": [],
                    "weaknesses": ["Insufficient depth"],
                    "actionable_feedback": "Add more specific data",
                }
            return {
                "overall_score": 7.5,
                "verdict": "accept",
                "scores": {"accuracy": 8},
                "strengths": ["Improved depth"],
                "weaknesses": [],
                "actionable_feedback": "Good",
            }

        with patch("main.research", side_effect=mock_research_fn), \
             patch("main.critique", side_effect=mock_critique_fn), \
             patch("main.check_budget", return_value={"within_budget": True, "remaining": 5.0, "spent": 0}), \
             patch("main.get_strategy", return_value=(None, "default")), \
             patch("main.get_strategy_status", return_value="active"), \
             patch("main.load_principles", return_value=None), \
             patch("main.evaluate_trial", return_value={"action": "no_trial", "reason": "N/A"}), \
             patch("main.LOG_DIR", log_dir), \
             patch("main.CONSENSUS_ENABLED", False), \
             patch("memory_store.MEMORY_DIR", mem_dir):

            from main import run_loop
            result = run_loop("Test retry", "test")

            assert result["attempts"] == 2
            assert result["critique"]["overall_score"] == 7.5


# ============================================================
# 7. Memory Store Dual-Write Tests
# ============================================================

class TestMemoryStoreDualWrite:
    """Tests for memory_store dual-write to SQLite."""

    def test_save_output_writes_both(self, tmp_path):
        """save_output writes to both JSON file and SQLite."""
        mem_dir = str(tmp_path / "memory")
        db_path = str(tmp_path / "test.db")
        os.makedirs(mem_dir)

        with patch("memory_store.MEMORY_DIR", mem_dir), \
             patch("db.DB_PATH", db_path), \
             patch("db._initialized", False):
            import db
            db._initialized = False
            db.DB_PATH = db_path
            db.init_db()

            from memory_store import save_output
            filepath = save_output(
                domain="test",
                question="What is X?",
                research={"summary": "X is Y", "findings": []},
                critique={"overall_score": 7, "verdict": "accept"},
                attempt=1,
                strategy_version="default",
            )

            # JSON file exists
            assert os.path.exists(filepath)

            # SQLite has the record
            results = db.query_outputs("test")
            assert len(results) >= 1
