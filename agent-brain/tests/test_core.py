"""
Unit Tests for Agent Brain — Core Logic

Tests memory_store, cost_tracker, strategy_store, and config.
No API calls — all tests use local data and temp directories.

Run:
    python -m pytest tests/ -v
    python -m pytest tests/test_core.py -v
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_memory(tmp_path):
    """Create a temporary memory directory and patch MEMORY_DIR."""
    mem_dir = str(tmp_path / "memory")
    os.makedirs(mem_dir)
    with patch("memory_store.MEMORY_DIR", mem_dir):
        yield mem_dir


@pytest.fixture
def tmp_strategy(tmp_path):
    """Create a temporary strategy directory and patch STRATEGY_DIR."""
    strat_dir = str(tmp_path / "strategies")
    os.makedirs(strat_dir)
    with patch("strategy_store.STRATEGY_DIR", strat_dir):
        yield strat_dir


@pytest.fixture
def tmp_logs(tmp_path):
    """Create a temporary log directory and patch LOG_DIR + COST_LOG."""
    log_dir = str(tmp_path / "logs")
    os.makedirs(log_dir)
    cost_log = os.path.join(log_dir, "costs.jsonl")
    with patch("cost_tracker.LOG_DIR", log_dir), \
         patch("cost_tracker.COST_LOG", cost_log):
        yield log_dir


@pytest.fixture
def sample_research():
    """A sample research output dict."""
    return {
        "summary": "Bitcoin ETFs have seen significant institutional adoption in 2026.",
        "findings": [
            {"claim": "BlackRock iShares Bitcoin Trust holds $50B AUM", "confidence": "high"},
            {"claim": "SEC approved new spot ETF rules", "confidence": "medium"},
        ],
        "key_insights": [
            "Institutional money is flowing into crypto ETFs",
            "Regulatory clarity has improved market confidence",
        ],
        "knowledge_gaps": ["Retail vs institutional ratio unclear"],
    }


@pytest.fixture
def sample_critique():
    """A sample critique output dict."""
    return {
        "overall_score": 7,
        "verdict": "accept",
        "scores": {
            "accuracy": 7,
            "depth": 7,
            "completeness": 6,
            "specificity": 8,
            "intellectual_honesty": 7,
        },
        "strengths": ["Good data", "Specific numbers"],
        "weaknesses": ["Missing retail perspective"],
        "actionable_feedback": "Add retail adoption data",
    }


@pytest.fixture
def low_score_critique():
    """A critique that should be rejected."""
    return {
        "overall_score": 3,
        "verdict": "reject",
        "scores": {"accuracy": 3, "depth": 2, "completeness": 3, "specificity": 4, "intellectual_honesty": 3},
        "strengths": [],
        "weaknesses": ["Superficial", "No data"],
        "actionable_feedback": "Start over",
    }


# ============================================================
# Config Tests
# ============================================================

class TestConfig:
    def test_quality_threshold_is_integer(self):
        from config import QUALITY_THRESHOLD
        assert isinstance(QUALITY_THRESHOLD, int)
        assert 1 <= QUALITY_THRESHOLD <= 10

    def test_models_defined(self):
        from config import MODELS
        assert "researcher" in MODELS
        assert "critic" in MODELS
        assert "meta_analyst" in MODELS

    def test_cost_rates_defined(self):
        from config import COST_PER_1K, MODELS
        for model in MODELS.values():
            assert model in COST_PER_1K, f"Missing cost rate for {model}"
            assert "input" in COST_PER_1K[model]
            assert "output" in COST_PER_1K[model]

    def test_budget_positive(self):
        from config import DAILY_BUDGET_USD
        assert DAILY_BUDGET_USD > 0

    def test_thresholds_consistent(self):
        from config import (
            QUALITY_THRESHOLD, MAX_RETRIES, MAX_TOOL_ROUNDS, MAX_SEARCHES,
            TRIAL_PERIOD, EVOLVE_EVERY_N, MIN_OUTPUTS_FOR_ANALYSIS,
        )
        assert MAX_RETRIES >= 0
        assert MAX_TOOL_ROUNDS >= 1
        assert MAX_SEARCHES >= 1
        assert TRIAL_PERIOD >= 1
        assert EVOLVE_EVERY_N >= 1
        assert MIN_OUTPUTS_FOR_ANALYSIS >= 1


# ============================================================
# Memory Store Tests
# ============================================================

class TestMemoryStore:
    def test_save_and_load(self, tmp_memory, sample_research, sample_critique):
        from memory_store import save_output, load_outputs

        path = save_output("test", "What is Bitcoin?", sample_research, sample_critique, 1, "v001")
        assert os.path.exists(path)

        outputs = load_outputs("test")
        assert len(outputs) == 1
        assert outputs[0]["question"] == "What is Bitcoin?"
        assert outputs[0]["overall_score"] == 7

    def test_accepted_field_stored(self, tmp_memory, sample_research, sample_critique, low_score_critique):
        from memory_store import save_output, load_outputs

        save_output("test", "Q1", sample_research, sample_critique, 1, "v001")  # score 7
        save_output("test", "Q2", sample_research, low_score_critique, 1, "v001")  # score 3

        outputs = load_outputs("test")
        assert len(outputs) == 2
        accepted = [o for o in outputs if o["accepted"]]
        rejected = [o for o in outputs if not o["accepted"]]
        assert len(accepted) == 1
        assert len(rejected) == 1

    def test_load_with_min_score(self, tmp_memory, sample_research, sample_critique, low_score_critique):
        from memory_store import save_output, load_outputs

        save_output("test", "Q1", sample_research, sample_critique, 1, "v001")  # score 7
        save_output("test", "Q2", sample_research, low_score_critique, 1, "v001")  # score 3

        high = load_outputs("test", min_score=5)
        assert len(high) == 1
        assert high[0]["overall_score"] == 7

    def test_get_stats(self, tmp_memory, sample_research, sample_critique, low_score_critique):
        from memory_store import save_output, get_stats

        save_output("test", "Q1", sample_research, sample_critique, 1, "v001")
        save_output("test", "Q2", sample_research, low_score_critique, 1, "v001")

        stats = get_stats("test")
        assert stats["count"] == 2
        assert stats["accepted"] == 1
        assert stats["rejected"] == 1
        assert stats["avg_score"] == 5.0  # (7+3)/2

    def test_get_stats_empty_domain(self, tmp_memory):
        from memory_store import get_stats
        stats = get_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["avg_score"] == 0

    def test_tokenize(self):
        from memory_store import _tokenize
        tokens = _tokenize("What is the current state of Bitcoin ETFs?")
        assert "bitcoin" in tokens
        assert "etfs" in tokens
        assert "the" not in tokens  # stop word
        assert "is" not in tokens  # stop word

    def test_relevance_score_high_overlap(self, sample_research, sample_critique):
        from memory_store import _relevance_score, _tokenize

        output = {
            "question": "What are Bitcoin ETF developments?",
            "research": sample_research,
            "overall_score": 8,
            "accepted": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        query_tokens = _tokenize("Bitcoin ETF institutional adoption")
        score = _relevance_score(query_tokens, output)
        assert score > 0.3  # Should have good keyword overlap

    def test_relevance_score_no_overlap(self, sample_research, sample_critique):
        from memory_store import _relevance_score, _tokenize

        output = {
            "question": "What are Bitcoin ETF developments?",
            "research": sample_research,
            "overall_score": 8,
            "accepted": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        query_tokens = _tokenize("quantum computing photon entanglement")
        score = _relevance_score(query_tokens, output)
        assert score < 0.5  # Low keyword overlap (quality+recency still contribute)

    def test_relevance_rejected_penalty(self, sample_research):
        from memory_store import _relevance_score, _tokenize

        base_output = {
            "question": "What are Bitcoin ETF developments?",
            "research": sample_research,
            "overall_score": 7,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        query_tokens = _tokenize("Bitcoin ETF institutional")

        accepted_output = {**base_output, "accepted": True}
        rejected_output = {**base_output, "accepted": False}

        score_accepted = _relevance_score(query_tokens, accepted_output)
        score_rejected = _relevance_score(query_tokens, rejected_output)

        assert score_accepted > score_rejected  # Accepted should rank higher

    def test_retrieve_relevant(self, tmp_memory, sample_research, sample_critique, low_score_critique):
        from memory_store import save_output, retrieve_relevant

        save_output("test", "Bitcoin ETF developments", sample_research, sample_critique, 1, "v001")
        save_output("test", "Ethereum gas fees", sample_research, low_score_critique, 1, "v001")

        results = retrieve_relevant("test", "What is happening with Bitcoin ETFs?")
        # Should return the accepted output, not the rejected one
        assert len(results) >= 1
        assert results[0]["question"] == "Bitcoin ETF developments"

    def test_retrieve_relevant_empty(self, tmp_memory):
        from memory_store import retrieve_relevant
        results = retrieve_relevant("empty_domain", "anything")
        assert results == []

    def test_knowledge_base_save_and_load(self, tmp_memory):
        from memory_store import save_knowledge_base, load_knowledge_base

        kb = {"claims": [{"claim": "Test", "status": "active"}], "topics": []}
        path = save_knowledge_base("test", kb)
        assert os.path.exists(path)

        loaded = load_knowledge_base("test")
        assert loaded["claims"][0]["claim"] == "Test"

    def test_knowledge_base_missing(self, tmp_memory):
        from memory_store import load_knowledge_base
        assert load_knowledge_base("nonexistent") is None


# ============================================================
# Pruning Tests
# ============================================================

class TestPruning:
    def _make_output(self, domain_dir, filename, score, verdict, days_old=0):
        """Helper: write a fake output file."""
        os.makedirs(domain_dir, exist_ok=True)
        ts = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
        record = {
            "timestamp": ts,
            "overall_score": score,
            "verdict": verdict,
            "accepted": score >= 6,
            "question": f"Test question (score={score})",
        }
        filepath = os.path.join(domain_dir, filename)
        with open(filepath, "w") as f:
            json.dump(record, f)
        return filepath

    def test_prune_old_rejected(self, tmp_memory):
        from memory_store import prune_domain

        domain_dir = os.path.join(tmp_memory, "test")
        self._make_output(domain_dir, "good.json", 8, "accept", days_old=0)
        self._make_output(domain_dir, "bad_old.json", 3, "reject", days_old=10)

        result = prune_domain("test")
        assert result["archived"] == 1
        assert result["kept"] == 1

    def test_prune_keeps_recent_rejected(self, tmp_memory):
        from memory_store import prune_domain

        domain_dir = os.path.join(tmp_memory, "test")
        self._make_output(domain_dir, "good.json", 8, "accept", days_old=0)
        self._make_output(domain_dir, "bad_new.json", 3, "reject", days_old=1)  # Only 1 day old

        result = prune_domain("test")
        assert result["archived"] == 0
        assert result["kept"] == 2  # Both kept

    def test_prune_dry_run(self, tmp_memory):
        from memory_store import prune_domain

        domain_dir = os.path.join(tmp_memory, "test")
        self._make_output(domain_dir, "bad_old.json", 2, "reject", days_old=10)

        result = prune_domain("test", dry_run=True)
        assert result["archived"] == 1
        assert result["dry_run"] is True
        # File should still exist
        assert os.path.exists(os.path.join(domain_dir, "bad_old.json"))

    def test_prune_domain_cap(self, tmp_memory):
        from memory_store import prune_domain

        domain_dir = os.path.join(tmp_memory, "test")
        # Create 105 outputs (above MAX_OUTPUTS_PER_DOMAIN=100)
        with patch("memory_store.MAX_OUTPUTS_PER_DOMAIN", 5):
            for i in range(8):
                self._make_output(domain_dir, f"output_{i:03d}.json", 6 + (i % 3), "accept", days_old=i)
            result = prune_domain("test")
            assert result["kept"] == 5
            assert result["archived"] == 3

    def test_archive_stats(self, tmp_memory):
        from memory_store import prune_domain, get_archive_stats

        domain_dir = os.path.join(tmp_memory, "test")
        self._make_output(domain_dir, "bad.json", 2, "reject", days_old=10)
        prune_domain("test")

        stats = get_archive_stats("test")
        assert stats["count"] == 1


# ============================================================
# Cost Tracker Tests
# ============================================================

class TestCostTracker:
    def test_log_cost(self, tmp_logs):
        from cost_tracker import log_cost

        cost = log_cost(
            model="claude-haiku-4-5-20251001",
            input_tokens=1000,
            output_tokens=500,
            agent_role="researcher",
            domain="test",
        )
        assert cost > 0

        # Check file was written
        cost_log = os.path.join(tmp_logs, "costs.jsonl")
        assert os.path.exists(cost_log)
        with open(cost_log) as f:
            entry = json.loads(f.readline())
        assert entry["agent_role"] == "researcher"
        assert entry["input_tokens"] == 1000

    def test_get_daily_spend(self, tmp_logs):
        from cost_tracker import log_cost, get_daily_spend

        log_cost("claude-haiku-4-5-20251001", 1000, 500, "researcher", "test")
        log_cost("claude-sonnet-4-20250514", 2000, 1000, "critic", "test")

        daily = get_daily_spend()
        assert daily["calls"] == 2
        assert daily["total_usd"] > 0
        assert "researcher" in daily["by_agent"]
        assert "critic" in daily["by_agent"]

    def test_check_budget_within(self, tmp_logs):
        from cost_tracker import log_cost, check_budget

        log_cost("claude-haiku-4-5-20251001", 100, 50, "researcher", "test")
        budget = check_budget()
        assert budget["within_budget"] is True
        assert budget["remaining"] > 0

    def test_check_budget_exceeded(self, tmp_logs):
        from cost_tracker import log_cost, check_budget

        with patch("cost_tracker.DAILY_BUDGET_USD", 0.001):
            log_cost("claude-sonnet-4-20250514", 100000, 50000, "critic", "test")
            budget = check_budget()
            assert budget["within_budget"] is False

    def test_get_all_time_spend(self, tmp_logs):
        from cost_tracker import log_cost, get_all_time_spend

        log_cost("claude-haiku-4-5-20251001", 1000, 500, "researcher", "test")
        alltime = get_all_time_spend()
        assert alltime["calls"] == 1
        assert alltime["days"] == 1
        assert alltime["total_usd"] > 0

    def test_empty_spend(self, tmp_logs):
        from cost_tracker import get_daily_spend
        daily = get_daily_spend()
        assert daily["calls"] == 0
        assert daily["total_usd"] == 0


# ============================================================
# Strategy Store Tests
# ============================================================

class TestStrategyStore:
    def test_default_version(self, tmp_strategy):
        from strategy_store import get_active_version
        assert get_active_version("researcher", "test") == "default"

    def test_set_and_get_active(self, tmp_strategy):
        from strategy_store import set_active_version, get_active_version
        set_active_version("researcher", "test", "v001", status="trial")
        assert get_active_version("researcher", "test") == "v001"

    def test_strategy_status(self, tmp_strategy):
        from strategy_store import set_active_version, get_strategy_status
        set_active_version("researcher", "test", "v001", status="trial")
        assert get_strategy_status("researcher", "test") == "trial"

    def test_version_history(self, tmp_strategy):
        from strategy_store import set_active_version, get_version_history
        set_active_version("researcher", "test", "v001", status="active")
        set_active_version("researcher", "test", "v002", status="trial")

        history = get_version_history("researcher", "test")
        assert len(history) >= 2  # history entries + current
        # Last entry is current (v002), previous entry is v001
        assert history[-1]["version"] == "v002"
        assert history[-2]["version"] == "v001"

    def test_save_and_load_strategy(self, tmp_strategy):
        from strategy_store import save_strategy, get_strategy, _load_strategy_file

        filepath = save_strategy(
            agent_role="researcher",
            domain="test",
            strategy_text="Use academic sources. Be thorough.",
            version="v001",
            reason="Test strategy",
            status="pending",
        )
        assert os.path.exists(filepath)

        # Saved as pending — not active yet
        data = _load_strategy_file("researcher", "test", "v001")
        assert data is not None
        assert data["strategy"] == "Use academic sources. Be thorough."
        assert data["status"] == "pending"

    def test_approve_strategy(self, tmp_strategy):
        from strategy_store import save_strategy, approve_strategy, get_active_version

        save_strategy("researcher", "test", "New strategy", "v001", status="pending")
        result = approve_strategy("researcher", "test", "v001")
        assert result["action"] == "approved"
        assert get_active_version("researcher", "test") == "v001"

    def test_reject_strategy(self, tmp_strategy):
        from strategy_store import save_strategy, reject_strategy, _load_strategy_file

        save_strategy("researcher", "test", "Bad strategy", "v001", status="pending")
        result = reject_strategy("researcher", "test", "v001")
        assert result["action"] == "rejected"

        data = _load_strategy_file("researcher", "test", "v001")
        assert data["status"] == "rejected"

    def test_list_pending(self, tmp_strategy):
        from strategy_store import save_strategy, list_pending

        save_strategy("researcher", "test", "Pending 1", "v001", status="pending")
        save_strategy("researcher", "test", "Pending 2", "v002", status="pending")

        pending = list_pending("researcher", "test")
        assert len(pending) == 2

    def test_rollback(self, tmp_strategy):
        from strategy_store import save_strategy, rollback, get_active_version

        # save_strategy with default status="trial" directly sets as active
        save_strategy("researcher", "test", "Strategy v1", "v001")
        save_strategy("researcher", "test", "Strategy v2", "v002")

        assert get_active_version("researcher", "test") == "v002"
        rolled_to = rollback("researcher", "test")
        assert rolled_to == "v001"

    def test_strategy_diff(self, tmp_strategy):
        from strategy_store import save_strategy, get_strategy_diff

        save_strategy("researcher", "test", "Line A\nLine B\nLine C", "v001")
        save_strategy("researcher", "test", "Line A\nLine D\nLine C", "v002")

        diff = get_strategy_diff("researcher", "test", "v001", "v002")
        assert diff.get("error") is None
        assert diff["version_a"]["version"] == "v001"
        assert diff["version_b"]["version"] == "v002"

    def test_strategy_performance(self, tmp_strategy, tmp_memory, sample_research, sample_critique):
        from strategy_store import save_strategy, get_strategy_performance
        from memory_store import save_output

        save_strategy("researcher", "test", "Strat", "v001")

        # Save an output tagged with this strategy version
        save_output("test", "Q1", sample_research, sample_critique, 1, "v001")

        perf = get_strategy_performance("test", "v001")
        assert perf["count"] == 1
        assert perf["avg_score"] == 7.0


# ============================================================
# Integration-ish Tests (no API calls)
# ============================================================

class TestIntegration:
    def test_full_memory_cycle(self, tmp_memory, sample_research, sample_critique, low_score_critique):
        """Save multiple outputs, retrieve relevant, check stats, prune."""
        import time
        from memory_store import save_output, retrieve_relevant, get_stats, prune_domain

        # Save 3 outputs (sleep to avoid timestamp collision in filenames)
        save_output("test", "Bitcoin ETFs 2026", sample_research, sample_critique, 1, "v001")
        time.sleep(1.1)
        save_output("test", "Ethereum L2 scaling", sample_research, sample_critique, 1, "v001")
        time.sleep(1.1)
        save_output("test", "Failed research", sample_research, low_score_critique, 1, "v001")

        # Stats
        stats = get_stats("test")
        assert stats["count"] == 3
        assert stats["accepted"] == 2
        assert stats["rejected"] == 1

        # Retrieval (should only return accepted)
        results = retrieve_relevant("test", "Bitcoin ETF adoption", min_score=4.0)
        for r in results:
            assert r["score"] >= 4.0

    def test_cli_dashboard_runs(self, tmp_memory, tmp_logs, tmp_strategy):
        """Verify --dashboard doesn't crash on empty data."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "main", "--dashboard"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            capture_output=True,
            text=True,
            env={**os.environ, "ANTHROPIC_API_KEY": "test-key"},
        )
        # Dashboard should run without errors
        assert result.returncode == 0
        assert "DASHBOARD" in result.stdout
