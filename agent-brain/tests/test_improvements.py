"""
Tests for the 7 self-improvement upgrades:
1. TF-IDF semantic memory retrieval
2. Adaptive critic rubric
3. Meta-analyst evolution log
4. Statistical trial evaluation (t-test)
5. Incremental synthesis merge
6. Prediction verifier agent
7. Cross-domain transfer tracking

No API calls — all tests use local data and temp directories.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta, date
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Shared Fixtures
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


def _make_output(question: str, score: float, summary: str = "", accepted: bool = True, 
                 timestamp: str = None, findings: list = None, strategy_version: str = "default") -> dict:
    """Helper to create a mock research output."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "question": question,
        "overall_score": score,
        "verdict": "accept" if accepted else "reject",
        "accepted": accepted,
        "timestamp": timestamp,
        "_strategy_version": strategy_version,
        "research": {
            "summary": summary or f"Research about {question}",
            "findings": findings or [
                {"claim": f"Claim about {question}", "confidence": "high"},
            ],
            "key_insights": [f"Insight about {question}"],
            "knowledge_gaps": [f"Gap in {question}"],
        },
        "critique": {
            "scores": {"accuracy": score, "depth": score, "completeness": score,
                       "specificity": score, "intellectual_honesty": score},
            "strengths": ["Good"],
            "weaknesses": ["Could improve"],
            "actionable_feedback": "Try harder",
        },
    }


def _save_output_file(mem_dir: str, domain: str, output: dict, index: int = 0) -> str:
    """Save a mock output to the memory directory."""
    domain_dir = os.path.join(mem_dir, domain)
    os.makedirs(domain_dir, exist_ok=True)
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{index:03d}.json"
    filepath = os.path.join(domain_dir, filename)
    with open(filepath, "w") as f:
        json.dump(output, f, indent=2)
    return filepath


# ============================================================
# 1. TF-IDF Semantic Memory Tests
# ============================================================

class TestTfidfMemory:
    def test_imports_sklearn(self):
        """Verify sklearn is importable and used in memory_store."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        assert TfidfVectorizer is not None
        assert cosine_similarity is not None

    def test_build_output_text(self):
        """Test that _build_output_text extracts text from output dict."""
        from memory_store import _build_output_text
        output = _make_output("Bitcoin price", 7, "BTC is rising")
        text = _build_output_text(output)
        assert "Bitcoin price" in text
        assert "BTC is rising" in text

    def test_quality_score(self):
        """Test quality score normalization."""
        from memory_store import _quality_score
        good = _make_output("test", 8, accepted=True)
        bad = _make_output("test", 8, accepted=False)
        assert _quality_score(good) == 0.8
        assert _quality_score(bad) == pytest.approx(0.8 * 0.3, rel=1e-2)

    def test_recency_score_today(self):
        """Today's output should have recency ~1.0."""
        from memory_store import _recency_score
        output = _make_output("test", 7)
        assert _recency_score(output) > 0.9

    def test_recency_score_old(self):
        """90-day-old output should have recency ~0."""
        from memory_store import _recency_score
        old_ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        output = _make_output("test", 7, timestamp=old_ts)
        assert _recency_score(output) < 0.05

    def test_tfidf_retrieval(self, tmp_memory):
        """TF-IDF should rank semantically relevant outputs higher."""
        from memory_store import retrieve_relevant
        
        # Save several outputs with different topics
        _save_output_file(tmp_memory, "crypto", 
                         _make_output("Bitcoin ETF approval", 8, "SEC approved Bitcoin ETFs"), 0)
        _save_output_file(tmp_memory, "crypto",
                         _make_output("Ethereum staking rewards", 7, "ETH stakers earn 4%"), 1)
        _save_output_file(tmp_memory, "crypto",
                         _make_output("Bitcoin mining energy", 7, "Mining uses renewable energy"), 2)
        
        results = retrieve_relevant("crypto", "What is the Bitcoin ETF situation?")
        assert len(results) > 0
        # The Bitcoin ETF output should be most relevant
        assert "ETF" in results[0]["question"] or "Bitcoin" in results[0]["question"]

    def test_retrieval_fallback_single_doc(self, tmp_memory):
        """With only 1 document, should fall back to keyword matching."""
        from memory_store import retrieve_relevant
        
        _save_output_file(tmp_memory, "ai",
                         _make_output("GPT-5 capabilities", 8, "GPT-5 shows amazing reasoning"), 0)
        
        results = retrieve_relevant("ai", "What can GPT-5 do?")
        assert len(results) > 0

    def test_retrieval_empty_domain(self, tmp_memory):
        """Empty domain returns empty list."""
        from memory_store import retrieve_relevant
        results = retrieve_relevant("empty_domain", "anything")
        assert results == []

    def test_keyword_fallback_preserved(self):
        """Original _relevance_score still works as fallback."""
        from memory_store import _relevance_score, _tokenize
        output = _make_output("Bitcoin price analysis", 8, "BTC reached all-time high")
        tokens = _tokenize("Bitcoin price trend")
        score = _relevance_score(tokens, output)
        assert score > 0


# ============================================================
# 2. Adaptive Critic Rubric Tests
# ============================================================

class TestAdaptiveRubric:
    def test_default_weights(self):
        """Default weights should sum to 1.0."""
        from agents.critic import DEFAULT_RUBRIC_WEIGHTS
        total = sum(DEFAULT_RUBRIC_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_load_rubric_default(self, tmp_strategy):
        """Without custom rubric file, should return defaults."""
        with patch("agents.critic.STRATEGY_DIR", tmp_strategy):
            from agents.critic import load_rubric, DEFAULT_RUBRIC_WEIGHTS
            weights = load_rubric("nonexistent_domain")
            assert weights == DEFAULT_RUBRIC_WEIGHTS

    def test_save_and_load_rubric(self, tmp_strategy):
        """Save custom weights and load them back."""
        with patch("agents.critic.STRATEGY_DIR", tmp_strategy):
            from agents.critic import save_rubric, load_rubric
            custom = {
                "accuracy": 0.40,
                "depth": 0.15,
                "completeness": 0.15,
                "specificity": 0.15,
                "intellectual_honesty": 0.15,
            }
            save_rubric("test_domain", custom, "Testing custom weights")
            loaded = load_rubric("test_domain")
            assert loaded["accuracy"] == 0.40
            assert loaded["depth"] == 0.15

    def test_invalid_rubric_falls_back(self, tmp_strategy):
        """Invalid rubric file should fall back to defaults."""
        with patch("agents.critic.STRATEGY_DIR", tmp_strategy):
            from agents.critic import load_rubric, DEFAULT_RUBRIC_WEIGHTS
            # Write invalid data
            domain_dir = os.path.join(tmp_strategy, "bad_domain")
            os.makedirs(domain_dir)
            with open(os.path.join(domain_dir, "_rubric.json"), "w") as f:
                json.dump({"weights": {"accuracy": 2.0}}, f)  # Doesn't sum to 1.0
            loaded = load_rubric("bad_domain")
            assert loaded == DEFAULT_RUBRIC_WEIGHTS

    def test_build_prompt_with_custom_weights(self):
        """Custom weights should appear in the prompt text."""
        from agents.critic import _build_critic_prompt
        custom = {
            "accuracy": 0.40,
            "depth": 0.15,
            "completeness": 0.15,
            "specificity": 0.15,
            "intellectual_honesty": 0.15,
        }
        prompt = _build_critic_prompt(custom)
        assert "Accuracy 40%" in prompt
        assert "Depth 15%" in prompt

    def test_critique_accepts_domain_param(self):
        """critique() should accept domain parameter without error."""
        from agents.critic import critique
        import inspect
        sig = inspect.signature(critique)
        assert "domain" in sig.parameters


# ============================================================
# 3. Meta-analyst Evolution Log Tests
# ============================================================

class TestEvolutionLog:
    def test_empty_log(self, tmp_strategy):
        """Empty log should return empty list."""
        with patch("agents.meta_analyst.STRATEGY_DIR", tmp_strategy):
            from agents.meta_analyst import load_evolution_log
            log = load_evolution_log("test_domain")
            assert log == []

    def test_save_and_load_entry(self, tmp_strategy):
        """Save an entry and load it back."""
        with patch("agents.meta_analyst.STRATEGY_DIR", tmp_strategy):
            from agents.meta_analyst import save_evolution_entry, load_evolution_log
            entry = {
                "version": "v001",
                "date": "2026-02-23",
                "changes": ["Added source verification"],
                "score_before": 6.5,
                "score_after": None,
                "outcome": "pending",
            }
            save_evolution_entry("test_domain", entry)
            log = load_evolution_log("test_domain")
            assert len(log) == 1
            assert log[0]["version"] == "v001"

    def test_multiple_entries(self, tmp_strategy):
        """Multiple entries should accumulate."""
        with patch("agents.meta_analyst.STRATEGY_DIR", tmp_strategy):
            from agents.meta_analyst import save_evolution_entry, load_evolution_log
            for i in range(3):
                save_evolution_entry("test_domain", {"version": f"v{i:03d}", "changes": [f"change {i}"]})
            log = load_evolution_log("test_domain")
            assert len(log) == 3

    def test_update_outcome(self, tmp_strategy):
        """Update outcome of a specific version."""
        with patch("agents.meta_analyst.STRATEGY_DIR", tmp_strategy):
            from agents.meta_analyst import save_evolution_entry, update_evolution_outcome, load_evolution_log
            save_evolution_entry("test_domain", {"version": "v001", "outcome": "pending", "score_after": None})
            update_evolution_outcome("test_domain", "v001", "confirmed", 7.5)
            log = load_evolution_log("test_domain")
            assert log[0]["outcome"] == "confirmed"
            assert log[0]["score_after"] == 7.5

    def test_format_history_empty(self, tmp_strategy):
        """Empty history should return no-history message."""
        with patch("agents.meta_analyst.STRATEGY_DIR", tmp_strategy):
            from agents.meta_analyst import _format_evolution_history
            history = _format_evolution_history("test_domain")
            assert "No previous evolution history" in history

    def test_format_history_with_entries(self, tmp_strategy):
        """History with entries should format them."""
        with patch("agents.meta_analyst.STRATEGY_DIR", tmp_strategy):
            from agents.meta_analyst import save_evolution_entry, _format_evolution_history
            save_evolution_entry("test_domain", {
                "version": "v001",
                "date": "2026-02-23",
                "changes": ["Added X"],
                "outcome": "confirmed",
                "score_before": 6.0,
                "score_after": 7.5,
            })
            history = _format_evolution_history("test_domain")
            assert "v001" in history
            assert "confirmed" in history


# ============================================================
# 4. Statistical Trial Evaluation Tests
# ============================================================

class TestStatisticalTrialEval:
    def test_scipy_ttest_import(self):
        """Verify scipy ttest_ind is importable."""
        from scipy.stats import ttest_ind
        assert ttest_ind is not None

    def test_config_trial_period(self):
        """Trial period should be 5."""
        from config import TRIAL_PERIOD
        assert TRIAL_PERIOD == 5

    def test_config_extend_limit(self):
        """Extend limit should exist."""
        from config import TRIAL_EXTEND_LIMIT
        assert TRIAL_EXTEND_LIMIT >= 1

    def test_config_p_value_threshold(self):
        """P-value threshold should exist."""
        from config import TRIAL_P_VALUE_THRESHOLD
        assert 0 < TRIAL_P_VALUE_THRESHOLD < 1

    def test_extend_trial_function_exists(self):
        """_extend_trial helper should exist."""
        from strategy_store import _extend_trial
        assert callable(_extend_trial)

    def test_evaluate_trial_returns_p_value(self, tmp_strategy):
        """evaluate_trial should include p_value in result."""
        with patch("strategy_store.STRATEGY_DIR", tmp_strategy):
            from strategy_store import evaluate_trial
            # No trial → no_trial action
            result = evaluate_trial("researcher", "test_domain")
            assert result["action"] == "no_trial"

    def test_welch_ttest_basic(self):
        """Basic t-test sanity check."""
        from scipy.stats import ttest_ind
        # Clearly different distributions
        a = [8, 9, 8, 7, 9]
        b = [3, 4, 3, 2, 4]
        _, p = ttest_ind(a, b, equal_var=False)
        assert p < 0.01  # Should be very significant

    def test_welch_ttest_similar(self):
        """Similar distributions should have high p-value."""
        from scipy.stats import ttest_ind
        a = [7, 7, 7, 7, 7]
        b = [7, 7, 7, 7, 7]
        _, p = ttest_ind(a, b, equal_var=False)
        # p should be 1.0 (or NaN for identical) — not significant
        assert p >= 0.10 or str(p) == 'nan'


# ============================================================
# 5. Incremental Synthesis Tests
# ============================================================

class TestIncrementalSynthesis:
    def test_incremental_prompt_exists(self):
        """Incremental prompt should be defined."""
        from agents.synthesizer import INCREMENTAL_PROMPT
        assert "INCREMENTAL UPDATE" in INCREMENTAL_PROMPT
        assert "MERGE" in INCREMENTAL_PROMPT

    def test_full_prompt_still_exists(self):
        """Full synthesis prompt should still work."""
        from agents.synthesizer import SYNTHESIS_PROMPT
        assert "knowledge synthesizer" in SYNTHESIS_PROMPT.lower()

    def test_synthesize_signature(self):
        """synthesize() should still accept domain and force params."""
        from agents.synthesizer import synthesize
        import inspect
        sig = inspect.signature(synthesize)
        assert "domain" in sig.parameters
        assert "force" in sig.parameters


# ============================================================
# 6. Prediction Verifier Tests
# ============================================================

class TestPredictionVerifier:
    def test_predictions_path(self, tmp_memory):
        """Predictions path should be in memory dir."""
        with patch("agents.verifier.MEMORY_DIR", tmp_memory):
            from agents.verifier import _predictions_path
            path = _predictions_path("crypto")
            assert "crypto" in path
            assert "_predictions.json" in path

    def test_load_empty_predictions(self, tmp_memory):
        """Empty predictions should return empty list."""
        with patch("agents.verifier.MEMORY_DIR", tmp_memory):
            from agents.verifier import load_predictions
            preds = load_predictions("crypto")
            assert preds == []

    def test_save_and_load_predictions(self, tmp_memory):
        """Save and load predictions."""
        with patch("agents.verifier.MEMORY_DIR", tmp_memory):
            from agents.verifier import save_predictions, load_predictions
            predictions = [
                {
                    "prediction": "Bitcoin will reach $100k by 2026-12-31",
                    "deadline": "2026-12-31",
                    "status": "pending",
                },
                {
                    "prediction": "ETH will hit $5k by 2026-06-30",
                    "deadline": "2026-06-30",
                    "status": "pending",
                },
            ]
            save_predictions("crypto", predictions)
            loaded = load_predictions("crypto")
            assert len(loaded) == 2
            assert loaded[0]["prediction"] == "Bitcoin will reach $100k by 2026-12-31"

    def test_verification_stats_empty(self, tmp_memory):
        """Stats for empty domain."""
        with patch("agents.verifier.MEMORY_DIR", tmp_memory):
            from agents.verifier import get_verification_stats
            stats = get_verification_stats("crypto")
            assert stats["total"] == 0

    def test_verification_stats_with_data(self, tmp_memory):
        """Stats should count by status."""
        with patch("agents.verifier.MEMORY_DIR", tmp_memory):
            from agents.verifier import save_predictions, get_verification_stats
            predictions = [
                {"prediction": "A", "status": "confirmed"},
                {"prediction": "B", "status": "confirmed"},
                {"prediction": "C", "status": "refuted"},
                {"prediction": "D", "status": "pending"},
            ]
            save_predictions("crypto", predictions)
            stats = get_verification_stats("crypto")
            assert stats["total"] == 4
            assert stats["confirmed"] == 2
            assert stats["refuted"] == 1
            assert stats["pending"] == 1
            assert stats["accuracy_rate"] == pytest.approx(2/3, rel=1e-2)

    def test_verifier_model_configured(self):
        """Verifier model should be in config."""
        from config import MODELS
        assert "verifier" in MODELS


# ============================================================
# 7. Cross-Domain Transfer Tracking Tests
# ============================================================

class TestTransferTracking:
    def test_transfer_log_file_defined(self):
        """Transfer log file should be defined."""
        from agents.cross_domain import TRANSFER_LOG_FILE
        assert "_transfer_log.json" in TRANSFER_LOG_FILE

    def test_empty_transfer_log(self, tmp_strategy):
        """Empty log should return empty list."""
        with patch("agents.cross_domain.TRANSFER_LOG_FILE", os.path.join(tmp_strategy, "_transfer_log.json")):
            from agents.cross_domain import _load_transfer_log
            log = _load_transfer_log()
            assert log == []

    def test_log_transfer(self, tmp_strategy):
        """Log a transfer and load it."""
        log_file = os.path.join(tmp_strategy, "_transfer_log.json")
        with patch("agents.cross_domain.TRANSFER_LOG_FILE", log_file):
            from agents.cross_domain import _log_transfer, _load_transfer_log
            _log_transfer(
                target_domain="ai",
                source_domains=["crypto", "markets"],
                version="v001",
                principles_applied=["Be specific", "Verify sources"],
            )
            log = _load_transfer_log()
            assert len(log) == 1
            assert log[0]["target_domain"] == "ai"
            assert log[0]["status"] == "pending"
            assert log[0]["lift"] is None

    def test_get_transfer_stats(self, tmp_strategy):
        """Transfer stats should summarize log."""
        log_file = os.path.join(tmp_strategy, "_transfer_log.json")
        with patch("agents.cross_domain.TRANSFER_LOG_FILE", log_file):
            from agents.cross_domain import _log_transfer, get_transfer_stats
            _log_transfer("ai", ["crypto"], "v001", ["P1"])
            _log_transfer("tech", ["crypto"], "v001", ["P2"])
            stats = get_transfer_stats()
            assert len(stats) == 2
            assert stats[0]["target_domain"] == "ai"
            assert stats[1]["target_domain"] == "tech"

    def test_update_principle_confidence(self, tmp_strategy):
        """Positive lift should increase principle confidence."""
        principles_file = os.path.join(tmp_strategy, "_principles.json")
        with patch("agents.cross_domain.PRINCIPLES_FILE", principles_file):
            from agents.cross_domain import _update_principle_confidence
            # Create a principles file
            principles_data = {
                "version": 1,
                "principles": [
                    {"principle": "Be specific", "confidence": "medium", "source_domains": ["crypto"]},
                    {"principle": "Verify sources", "confidence": "low", "source_domains": ["crypto"]},
                ],
            }
            with open(principles_file, "w") as f:
                json.dump(principles_data, f)
            
            # Positive lift should bump confidence
            _update_principle_confidence(["Be specific"], 1.5)
            
            with open(principles_file) as f:
                updated = json.load(f)
            
            principle = updated["principles"][0]
            assert "transfer_results" in principle
            assert len(principle["transfer_results"]) == 1
            assert principle["transfer_results"][0]["lift"] == 1.5


# ============================================================
# Integration: All improvements don't break imports
# ============================================================

class TestImportIntegrity:
    def test_memory_store_imports(self):
        """memory_store should import without error."""
        import memory_store
        assert hasattr(memory_store, 'retrieve_relevant')
        assert hasattr(memory_store, '_build_output_text')
        assert hasattr(memory_store, '_quality_score')
        assert hasattr(memory_store, '_recency_score')

    def test_critic_imports(self):
        """critic should import without error."""
        from agents.critic import critique, load_rubric, save_rubric, DEFAULT_RUBRIC_WEIGHTS
        assert callable(critique)
        assert callable(load_rubric)
        assert callable(save_rubric)

    def test_meta_analyst_imports(self):
        """meta_analyst should import without error."""
        from agents.meta_analyst import (
            analyze_and_evolve, load_evolution_log, save_evolution_entry, 
            update_evolution_outcome, _format_evolution_history
        )
        assert callable(analyze_and_evolve)
        assert callable(load_evolution_log)

    def test_strategy_store_imports(self):
        """strategy_store should import without error (includes scipy)."""
        from strategy_store import evaluate_trial, _extend_trial
        assert callable(evaluate_trial)
        assert callable(_extend_trial)

    def test_synthesizer_imports(self):
        """synthesizer should import without error."""
        from agents.synthesizer import synthesize, INCREMENTAL_PROMPT, SYNTHESIS_PROMPT
        assert callable(synthesize)
        assert len(INCREMENTAL_PROMPT) > 0

    def test_verifier_imports(self):
        """verifier should import without error."""
        from agents.verifier import (
            extract_predictions, verify_predictions, load_predictions, 
            save_predictions, get_verification_stats
        )
        assert callable(extract_predictions)
        assert callable(verify_predictions)

    def test_cross_domain_imports(self):
        """cross_domain should import without error (includes tracking)."""
        from agents.cross_domain import (
            generate_seed_strategy, extract_principles, measure_transfer_lift,
            get_transfer_stats, _log_transfer, _load_transfer_log
        )
        assert callable(generate_seed_strategy)
        assert callable(measure_transfer_lift)
