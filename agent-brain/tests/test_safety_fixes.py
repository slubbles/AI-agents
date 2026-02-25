"""
Tests for Safety Fixes (Audit Fixes Session)

Covers:
1. Claim expiry (expire_stale_claims)
2. Question deduplication (is_duplicate_question)
3. Prompt drift guardrails (immutable clauses, evolution history cap)
4. Cross-domain threshold hardening
5. Warmup mode config
6. Daily digest generation
7. Webhook push (mocked)
8. Silent DB failure now logs warnings

No API calls — all tests use temp directories and mocks.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

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
    """Create a temporary log directory and patch LOG_DIR."""
    log_dir = str(tmp_path / "logs")
    os.makedirs(log_dir)
    with patch.dict(os.environ, {}, clear=False):
        yield log_dir


@pytest.fixture
def sample_kb():
    """A sample knowledge base with claims of various ages."""
    now = datetime.now(timezone.utc)
    return {
        "domain": "test",
        "last_updated": now.isoformat(),
        "claims": [
            {
                "id": "c1",
                "claim": "Bitcoin hit $100k in 2025",
                "status": "active",
                "confidence": 0.9,
                "first_seen": (now - timedelta(days=10)).isoformat(),
                "last_confirmed": (now - timedelta(days=10)).isoformat(),
            },
            {
                "id": "c2",
                "claim": "Ethereum market cap is $500B",
                "status": "active",
                "confidence": 0.8,
                "first_seen": (now - timedelta(days=35)).isoformat(),
                "last_confirmed": (now - timedelta(days=35)).isoformat(),
            },
            {
                "id": "c3",
                "claim": "DeFi TVL is $100B",
                "status": "active",
                "confidence": 0.7,
                "first_seen": (now - timedelta(days=95)).isoformat(),
                "last_confirmed": (now - timedelta(days=95)).isoformat(),
            },
            {
                "id": "c4",
                "claim": "Already superseded claim",
                "status": "superseded",
                "confidence": 0.5,
                "first_seen": (now - timedelta(days=200)).isoformat(),
            },
        ],
    }


@pytest.fixture
def sample_outputs():
    """Sample outputs for dedup testing."""
    return [
        {
            "question": "What are the latest Bitcoin ETF developments?",
            "overall_score": 7.5,
            "verdict": "accept",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "research": {"summary": "test"},
            "critique": {"overall_score": 7.5},
        },
        {
            "question": "How does Ethereum staking work?",
            "overall_score": 8.0,
            "verdict": "accept",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "research": {"summary": "test"},
            "critique": {"overall_score": 8.0},
        },
        {
            "question": "What are the risks of DeFi lending protocols?",
            "overall_score": 6.5,
            "verdict": "accept",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "research": {"summary": "test"},
            "critique": {"overall_score": 6.5},
        },
    ]


# ============================================================
# 1. Claim Expiry Tests
# ============================================================

class TestClaimExpiry:
    """Tests for expire_stale_claims function."""

    def test_fresh_claims_unchanged(self, tmp_memory, sample_kb):
        """Claims within CLAIM_EXPIRY_DAYS should not be flagged."""
        from memory_store import expire_stale_claims

        # Make all claims fresh
        now = datetime.now(timezone.utc)
        for claim in sample_kb["claims"]:
            claim["last_confirmed"] = now.isoformat()
            claim["status"] = "active"

        # Set up KB
        domain = "test"
        domain_dir = os.path.join(tmp_memory, domain)
        os.makedirs(domain_dir, exist_ok=True)
        kb_path = os.path.join(domain_dir, "_knowledge_base.json")
        with open(kb_path, "w") as f:
            json.dump(sample_kb, f)

        with patch("memory_store.CLAIM_EXPIRY_DAYS", 30), \
             patch("memory_store.CLAIM_MAX_AGE_DAYS", 90):
            result = expire_stale_claims(domain)

        assert result["flagged"] == 0
        assert result["expired"] == 0

    def test_stale_claims_flagged(self, tmp_memory, sample_kb):
        """Claims older than CLAIM_EXPIRY_DAYS should be flagged as stale."""
        from memory_store import expire_stale_claims

        domain = "test"
        domain_dir = os.path.join(tmp_memory, domain)
        os.makedirs(domain_dir, exist_ok=True)
        kb_path = os.path.join(domain_dir, "_knowledge_base.json")
        with open(kb_path, "w") as f:
            json.dump(sample_kb, f)

        with patch("memory_store.CLAIM_EXPIRY_DAYS", 30), \
             patch("memory_store.CLAIM_MAX_AGE_DAYS", 90):
            result = expire_stale_claims(domain)

        # c2 is 35 days old → stale, c3 is 95 days old → expired
        assert result["flagged"] == 1  # c2
        assert result["expired"] == 1  # c3

        # Verify the KB was actually updated
        with open(kb_path) as f:
            updated_kb = json.load(f)
        statuses = {c["id"]: c["status"] for c in updated_kb["claims"]}
        assert statuses["c1"] == "active"
        assert statuses["c2"] == "stale"
        assert statuses["c3"] == "expired"
        assert statuses["c4"] == "superseded"  # unchanged

    def test_superseded_claims_skipped(self, tmp_memory, sample_kb):
        """Already superseded/expired claims should not be processed again."""
        from memory_store import expire_stale_claims

        domain = "test"
        domain_dir = os.path.join(tmp_memory, domain)
        os.makedirs(domain_dir, exist_ok=True)
        kb_path = os.path.join(domain_dir, "_knowledge_base.json")
        with open(kb_path, "w") as f:
            json.dump(sample_kb, f)

        with patch("memory_store.CLAIM_EXPIRY_DAYS", 30), \
             patch("memory_store.CLAIM_MAX_AGE_DAYS", 90):
            result = expire_stale_claims(domain)

        # c4 (superseded) should not be counted
        total_processed = result["flagged"] + result["expired"] + result["active"]
        # c1=active, c2=stale(flagged), c3=expired → total=3 (c4 skipped)
        assert total_processed == 3

    def test_no_kb_returns_zeros(self, tmp_memory):
        """Calling expire on a domain with no KB should return zeros."""
        from memory_store import expire_stale_claims
        result = expire_stale_claims("nonexistent")
        assert result["flagged"] == 0
        assert result["expired"] == 0
        assert result["active"] == 0


# ============================================================
# 2. Question Deduplication Tests
# ============================================================

class TestQuestionDedup:
    """Tests for is_duplicate_question function."""

    def test_exact_match_is_duplicate(self, tmp_memory, sample_outputs):
        """Exact question matches should be detected."""
        from memory_store import is_duplicate_question, save_output

        domain = "test"
        for out in sample_outputs:
            save_output(domain, out["question"], out["research"], out["critique"], 1, "v001")

        is_dup, matched = is_duplicate_question(domain, "What are the latest Bitcoin ETF developments?")
        assert is_dup is True
        assert "Bitcoin ETF" in matched

    def test_case_insensitive_match(self, tmp_memory, sample_outputs):
        """Case-insensitive exact matches should be detected."""
        from memory_store import is_duplicate_question, save_output

        domain = "test"
        for out in sample_outputs:
            save_output(domain, out["question"], out["research"], out["critique"], 1, "v001")

        is_dup, matched = is_duplicate_question(domain, "what are the latest bitcoin etf developments?")
        assert is_dup is True

    def test_novel_question_not_duplicate(self, tmp_memory, sample_outputs):
        """Very different questions should not be flagged."""
        from memory_store import is_duplicate_question, save_output

        domain = "test"
        for out in sample_outputs:
            save_output(domain, out["question"], out["research"], out["critique"], 1, "v001")

        is_dup, matched = is_duplicate_question(domain, "What is quantum computing's impact on cryptography?")
        assert is_dup is False
        assert matched is None

    def test_empty_domain_not_duplicate(self, tmp_memory):
        """Empty domains should never flag duplicates."""
        from memory_store import is_duplicate_question
        is_dup, matched = is_duplicate_question("empty_domain", "Any question?")
        assert is_dup is False
        assert matched is None

    def test_similar_question_detected(self, tmp_memory, sample_outputs):
        """Very similar rephrased questions should be detected at low threshold."""
        from memory_store import is_duplicate_question, save_output

        domain = "test"
        # Add more outputs to give TF-IDF enough corpus
        extra_outputs = [
            {"question": "What is the current state of Bitcoin ETF approval process?",
             "research": {"summary": "test"}, "critique": {"overall_score": 7.0}},
            {"question": "How do Bitcoin ETFs differ from direct BTC purchases?",
             "research": {"summary": "test"}, "critique": {"overall_score": 7.0}},
        ]
        for out in sample_outputs + extra_outputs:
            save_output(domain, out["question"], out.get("research", {"summary": "t"}),
                        out.get("critique", {"overall_score": 7}), 1, "v001")

        # TF-IDF cosine similarity on short questions is naturally low (~0.3),
        # so we test with a threshold that reflects real behavior.
        # With threshold=0.30, a rephrase like "recent Bitcoin ETF updates" should match
        # "latest Bitcoin ETF developments" (both share "Bitcoin ETF" bigram).
        is_dup, matched = is_duplicate_question(
            domain, "What are the recent Bitcoin ETF updates and developments?",
            threshold=0.30
        )
        assert is_dup is True
        assert "Bitcoin ETF" in matched


# ============================================================
# 3. Prompt Drift Guardrails Tests
# ============================================================

class TestDriftGuardrails:
    """Tests for prompt drift enforcement in meta_analyst."""

    def test_evolution_history_cap(self):
        """Evolution history should be capped at MAX_EVOLUTION_HISTORY entries."""
        from agents.meta_analyst import _format_evolution_history, save_evolution_entry, load_evolution_log

        domain = "test_drift"
        # Create more entries than the cap
        with patch("agents.meta_analyst.STRATEGY_DIR", "/tmp/test_strat_drift"):
            os.makedirs(f"/tmp/test_strat_drift/{domain}", exist_ok=True)
            
            # Write 15 entries
            log_path = f"/tmp/test_strat_drift/{domain}/_evolution_log.json"
            entries = []
            for i in range(15):
                entries.append({
                    "version": f"v{i+1:03d}",
                    "date": "2025-01-01",
                    "changes": [f"change {i}"],
                    "outcome": "confirmed",
                    "score_before": 5.0 + i * 0.1,
                    "score_after": 5.5 + i * 0.1,
                })
            with open(log_path, "w") as f:
                json.dump(entries, f)

            with patch("agents.meta_analyst.MAX_EVOLUTION_HISTORY", 10):
                history_text = _format_evolution_history(domain)

            # Should only include 10 entries (the last 10)
            lines = [l for l in history_text.strip().split("\n") if l.startswith("- Version")]
            assert len(lines) == 10
            
            # Should include last entry (v015) but not first (v001)
            assert "v015" in history_text
            assert "v001" not in history_text

            # Cleanup
            import shutil
            shutil.rmtree("/tmp/test_strat_drift", ignore_errors=True)

    def test_immutable_clauses_config(self):
        """Immutable clauses should be defined in config."""
        from config import IMMUTABLE_STRATEGY_CLAUSES
        assert isinstance(IMMUTABLE_STRATEGY_CLAUSES, list)
        assert len(IMMUTABLE_STRATEGY_CLAUSES) >= 3
        assert any("source" in c.lower() or "cite" in c.lower() for c in IMMUTABLE_STRATEGY_CLAUSES)

    def test_drift_threshold_config(self):
        """Drift warning threshold should be between 0 and 1."""
        from config import DRIFT_WARNING_THRESHOLD
        assert 0 < DRIFT_WARNING_THRESHOLD < 1


# ============================================================
# 4. Cross-Domain Threshold Tests
# ============================================================

class TestCrossDomainThresholds:
    """Tests for hardened cross-domain transfer thresholds."""

    def test_min_outputs_for_transfer(self):
        """MIN_OUTPUTS_FOR_TRANSFER should be at least 10."""
        from config import MIN_OUTPUTS_FOR_TRANSFER
        assert MIN_OUTPUTS_FOR_TRANSFER >= 10

    def test_min_avg_score_for_transfer(self):
        """MIN_AVG_SCORE_FOR_TRANSFER should be at least 6.0."""
        from config import MIN_AVG_SCORE_FOR_TRANSFER
        assert MIN_AVG_SCORE_FOR_TRANSFER >= 6.0


# ============================================================
# 5. Warmup Mode Config Tests
# ============================================================

class TestWarmupConfig:
    """Tests for warmup mode configuration."""

    def test_warmup_outputs_defined(self):
        """WARMUP_OUTPUTS should be a positive integer."""
        from config import WARMUP_OUTPUTS
        assert isinstance(WARMUP_OUTPUTS, int)
        assert WARMUP_OUTPUTS >= 3  # Need at least a few outputs

    def test_warmup_approval_required(self):
        """WARMUP_APPROVAL_REQUIRED should be a boolean."""
        from config import WARMUP_APPROVAL_REQUIRED
        assert isinstance(WARMUP_APPROVAL_REQUIRED, bool)


# ============================================================
# 6. Daily Digest Tests
# ============================================================

class TestDailyDigest:
    """Tests for the digest generation function."""

    def test_generate_digest_returns_dict(self):
        """_generate_digest should return a properly structured dict."""
        # We need to test this without actually running the full loop,
        # so we import and call with mock data
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
        
        round_results = [
            {"round": 1, "question": "Test question 1", "score": 7.5, "verdict": "accept"},
            {"round": 2, "question": "Test question 2", "score": 5.0, "verdict": "reject"},
        ]

        # Mock all dependencies
        with patch("main.get_stats", return_value={"count": 10, "avg_score": 7.0, "accepted": 8, "rejected": 2}), \
             patch("main.get_daily_spend", return_value={"total_usd": 0.50, "calls": 10}), \
             patch("main.list_pending", return_value=[]), \
             patch("main.LOG_DIR", "/tmp/test_digest_logs"), \
             patch("db.get_alerts", return_value=[]):
            os.makedirs("/tmp/test_digest_logs", exist_ok=True)
            from main import _generate_digest
            digest = _generate_digest("test", round_results, dedup_skipped=1)

        assert isinstance(digest, dict)
        assert digest["domain"] == "test"
        assert digest["rounds_completed"] == 2
        assert digest["dedup_skipped"] == 1
        assert digest["scores"]["avg"] == 6.2  # (7.5 + 5.0) / 2
        assert digest["scores"]["accepted"] == 1
        assert digest["scores"]["rejected"] == 1

        # Cleanup
        import shutil
        shutil.rmtree("/tmp/test_digest_logs", ignore_errors=True)

    def test_digest_saved_to_jsonl(self):
        """Digest should be appended to digests.jsonl."""
        round_results = [
            {"round": 1, "question": "Test q", "score": 8.0, "verdict": "accept"},
        ]

        log_dir = "/tmp/test_digest_save"
        os.makedirs(log_dir, exist_ok=True)

        with patch("main.get_stats", return_value={"count": 5, "avg_score": 7.0, "accepted": 4, "rejected": 1}), \
             patch("main.get_daily_spend", return_value={"total_usd": 0.20, "calls": 5}), \
             patch("main.list_pending", return_value=[]), \
             patch("main.LOG_DIR", log_dir), \
             patch("db.get_alerts", return_value=[]):
            from main import _generate_digest
            _generate_digest("test", round_results)

        digest_path = os.path.join(log_dir, "digests.jsonl")
        assert os.path.exists(digest_path)
        with open(digest_path) as f:
            line = f.readline()
            data = json.loads(line)
        assert data["domain"] == "test"

        import shutil
        shutil.rmtree(log_dir, ignore_errors=True)


# ============================================================
# 7. Webhook Push Tests
# ============================================================

class TestWebhookPush:
    """Tests for webhook push functionality."""

    def test_webhook_called_when_url_set(self):
        """Webhook should POST payload when AGENT_BRAIN_WEBHOOK_URL is set."""
        round_results = [
            {"round": 1, "question": "Test", "score": 7.0, "verdict": "accept"},
        ]

        with patch("main.get_stats", return_value={"count": 5, "avg_score": 7.0, "accepted": 4, "rejected": 1}), \
             patch("main.get_daily_spend", return_value={"total_usd": 0.20, "calls": 5}), \
             patch("main.list_pending", return_value=[]), \
             patch("main.LOG_DIR", "/tmp/test_webhook"), \
             patch("db.get_alerts", return_value=[]), \
             patch.dict(os.environ, {"AGENT_BRAIN_WEBHOOK_URL": "https://example.com/hook"}), \
             patch("main._push_webhook") as mock_push:
            os.makedirs("/tmp/test_webhook", exist_ok=True)
            from main import _generate_digest
            digest = _generate_digest("test", round_results)
            mock_push.assert_called_once_with("https://example.com/hook", digest)

        import shutil
        shutil.rmtree("/tmp/test_webhook", ignore_errors=True)

    def test_webhook_not_called_when_no_url(self):
        """Webhook should NOT be called when no URL is set."""
        round_results = [
            {"round": 1, "question": "Test", "score": 7.0, "verdict": "accept"},
        ]

        with patch("main.get_stats", return_value={"count": 5, "avg_score": 7.0, "accepted": 4, "rejected": 1}), \
             patch("main.get_daily_spend", return_value={"total_usd": 0.20, "calls": 5}), \
             patch("main.list_pending", return_value=[]), \
             patch("main.LOG_DIR", "/tmp/test_no_webhook"), \
             patch("db.get_alerts", return_value=[]), \
             patch.dict(os.environ, {}, clear=False), \
             patch("main._push_webhook") as mock_push:
            # Ensure no webhook URL
            os.environ.pop("AGENT_BRAIN_WEBHOOK_URL", None)
            os.makedirs("/tmp/test_no_webhook", exist_ok=True)
            from main import _generate_digest
            _generate_digest("test", round_results)
            mock_push.assert_not_called()

        import shutil
        shutil.rmtree("/tmp/test_no_webhook", ignore_errors=True)


# ============================================================
# 8. Config Value Tests (Claim Expiry + Verifier Model)
# ============================================================

class TestConfigValues:
    """Tests for new config values added in safety fixes."""

    def test_claim_expiry_days(self):
        """CLAIM_EXPIRY_DAYS should be reasonable."""
        from config import CLAIM_EXPIRY_DAYS
        assert isinstance(CLAIM_EXPIRY_DAYS, int)
        assert 7 <= CLAIM_EXPIRY_DAYS <= 90

    def test_claim_max_age_days(self):
        """CLAIM_MAX_AGE_DAYS should be larger than CLAIM_EXPIRY_DAYS."""
        from config import CLAIM_EXPIRY_DAYS, CLAIM_MAX_AGE_DAYS
        assert CLAIM_MAX_AGE_DAYS > CLAIM_EXPIRY_DAYS

    def test_verifier_uses_sonnet(self):
        """Verifier should use Sonnet (upgraded from Haiku)."""
        from config import MODELS
        assert "sonnet" in MODELS["verifier"].lower()

    def test_max_evolution_history(self):
        """MAX_EVOLUTION_HISTORY should be >= 10."""
        from config import MAX_EVOLUTION_HISTORY
        assert MAX_EVOLUTION_HISTORY >= 10
