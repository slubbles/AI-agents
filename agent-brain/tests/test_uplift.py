"""
Tests for Orchestrator + Critic Quality Uplift

Covers:
  - Critic ensemble mode (score averaging, divergence tracking, parse-error fallback)
  - Confidence validation (penalty for under-sourced high-confidence claims)
  - Parse failure logging (JSONL output)
  - Recency awareness in critic prompt
  - Orchestrator plateau detection (deprioritize stagnant domains)
  - Orchestrator time decay (boost stale domains)
  - Orchestrator config-driven max_per_domain
  - Auto mode dedup retry logic
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_logs(tmp_path):
    log_dir = str(tmp_path / "logs")
    os.makedirs(log_dir)
    return log_dir


@pytest.fixture
def tmp_memory(tmp_path):
    mem_dir = str(tmp_path / "memory")
    os.makedirs(mem_dir)
    with patch("memory_store.MEMORY_DIR", mem_dir):
        yield mem_dir


@pytest.fixture
def tmp_strategy(tmp_path):
    strat_dir = str(tmp_path / "strategies")
    os.makedirs(strat_dir)
    with patch("strategy_store.STRATEGY_DIR", strat_dir):
        yield strat_dir


# ============================================================
# Critic: Recency Awareness
# ============================================================

class TestCriticRecency:
    """Ensure the critic prompt includes recency awareness language."""

    def test_recency_in_prompt(self):
        from agents.critic import _build_critic_prompt, DEFAULT_RUBRIC_WEIGHTS
        prompt = _build_critic_prompt(DEFAULT_RUBRIC_WEIGHTS)
        assert "RECENCY AWARENESS" in prompt
        assert "stale" in prompt.lower() or "outdated" in prompt.lower()
        assert "6 months" in prompt

    def test_recency_includes_current_year(self):
        from agents.critic import _build_critic_prompt, DEFAULT_RUBRIC_WEIGHTS
        from datetime import date
        prompt = _build_critic_prompt(DEFAULT_RUBRIC_WEIGHTS)
        assert str(date.today().year) in prompt

    def test_source_verification_in_prompt(self):
        from agents.critic import _build_critic_prompt, DEFAULT_RUBRIC_WEIGHTS
        prompt = _build_critic_prompt(DEFAULT_RUBRIC_WEIGHTS)
        assert "cited sources real" in prompt.lower() or "actually accessed" in prompt.lower()


# ============================================================
# Critic: Build User Message
# ============================================================

class TestBuildUserMessage:
    """Test the _build_user_message helper."""

    def test_basic_message(self):
        from agents.critic import _build_user_message
        output = {"question": "test?", "findings": []}
        msg = _build_user_message(output, None)
        assert "test?" in msg
        assert "SOURCE VERIFICATION" not in msg

    def test_with_sources(self):
        from agents.critic import _build_user_message
        output = {"question": "test?", "findings": []}
        sources = [
            {"tool": "web_search", "query": "test query", "success": True, "results": 5},
            {"tool": "fetch_page", "url": "https://example.com", "success": True, "chars": 1000},
        ]
        msg = _build_user_message(output, sources)
        assert "SOURCE VERIFICATION DATA" in msg
        assert "test query" in msg
        assert "https://example.com" in msg
        assert "ACCURACY CHECK" in msg

    def test_failed_sources_marked(self):
        from agents.critic import _build_user_message
        sources = [
            {"tool": "fetch_page", "url": "https://broken.com", "success": False, "chars": 0},
        ]
        msg = _build_user_message({"findings": []}, sources)
        assert "[FAILED]" in msg


# ============================================================
# Critic: Confidence Validation
# ============================================================

class TestConfidenceValidation:
    """Test post-hoc confidence claim checking."""

    def test_high_confidence_single_source_gets_penalty(self):
        from agents.critic import _validate_confidence_claims
        research = {
            "findings": [
                {"claim": "Bitcoin hit 100K", "confidence": "high", "source": "https://example.com"},
            ]
        }
        critique_result = {
            "scores": {"accuracy": 8, "depth": 7, "completeness": 7, "specificity": 7, "intellectual_honesty": 7},
            "overall_score": 7.35,
            "weaknesses": [],
            "verdict": "accept",
        }
        with patch("config.CONFIDENCE_VALIDATION", True), \
             patch("config.CONFIDENCE_PENALTY", 1.0):
            result = _validate_confidence_claims(research, critique_result, None)
        
        assert result["scores"]["accuracy"] == 7  # was 8, penalty -1
        assert result["_confidence_penalty"]["count"] == 1
        assert any("CONFIDENCE CHECK" in w for w in result["weaknesses"])

    def test_high_confidence_multi_source_no_penalty(self):
        from agents.critic import _validate_confidence_claims
        research = {
            "findings": [
                {"claim": "ETH 2.0 merged", "confidence": "high", "source": "https://a.com, https://b.com"},
            ]
        }
        critique_result = {
            "scores": {"accuracy": 8, "depth": 7, "completeness": 7, "specificity": 7, "intellectual_honesty": 7},
            "overall_score": 7.35,
            "weaknesses": [],
            "verdict": "accept",
        }
        with patch("config.CONFIDENCE_VALIDATION", True), \
             patch("config.CONFIDENCE_PENALTY", 1.0):
            result = _validate_confidence_claims(research, critique_result, None)
        
        assert result["scores"]["accuracy"] == 8  # no penalty
        assert "_confidence_penalty" not in result

    def test_medium_confidence_ignored(self):
        from agents.critic import _validate_confidence_claims
        research = {
            "findings": [
                {"claim": "Maybe true", "confidence": "medium", "source": "https://a.com"},
            ]
        }
        critique_result = {
            "scores": {"accuracy": 8, "depth": 7, "completeness": 7, "specificity": 7, "intellectual_honesty": 7},
            "overall_score": 7.35,
            "weaknesses": [],
            "verdict": "accept",
        }
        with patch("config.CONFIDENCE_VALIDATION", True):
            result = _validate_confidence_claims(research, critique_result, None)
        
        assert result["scores"]["accuracy"] == 8

    def test_penalty_never_below_1(self):
        from agents.critic import _validate_confidence_claims
        research = {
            "findings": [
                {"claim": "Claim", "confidence": "high", "source": ""},
            ]
        }
        critique_result = {
            "scores": {"accuracy": 1, "depth": 5, "completeness": 5, "specificity": 5, "intellectual_honesty": 5},
            "overall_score": 3.6,
            "weaknesses": [],
            "verdict": "reject",
        }
        with patch("config.CONFIDENCE_VALIDATION", True), \
             patch("config.CONFIDENCE_PENALTY", 2.0):
            result = _validate_confidence_claims(research, critique_result, None)
        
        assert result["scores"]["accuracy"] == 1  # clamped at 1, not -1

    def test_verdict_flips_after_penalty(self):
        """Confidence penalty can change accept → reject."""
        from agents.critic import _validate_confidence_claims
        research = {
            "findings": [
                {"claim": "Strong claim", "confidence": "high", "source": "one"},
            ]
        }
        # Overall is exactly 6.0 — barely accepting
        critique_result = {
            "scores": {"accuracy": 6, "depth": 6, "completeness": 6, "specificity": 6, "intellectual_honesty": 6},
            "overall_score": 6.0,
            "weaknesses": [],
            "verdict": "accept",
        }
        with patch("config.CONFIDENCE_VALIDATION", True), \
             patch("config.CONFIDENCE_PENALTY", 1.0):
            result = _validate_confidence_claims(research, critique_result, None)
        
        # Accuracy dropped from 6→5, overall drops below 6
        assert result["verdict"] == "reject"

    def test_no_findings_no_penalty(self):
        from agents.critic import _validate_confidence_claims
        research = {"findings": []}
        critique_result = {
            "scores": {"accuracy": 8}, "overall_score": 7.0, "weaknesses": [],
        }
        with patch("config.CONFIDENCE_VALIDATION", True):
            result = _validate_confidence_claims(research, critique_result, None)
        assert result["scores"]["accuracy"] == 8


# ============================================================
# Critic: Parse Failure Logging
# ============================================================

class TestParseFailureLogging:
    """Test that parse failures get logged to JSONL."""

    def test_log_written_on_parse_failure(self, tmp_logs):
        from agents.critic import _log_parse_failure
        with patch("agents.critic.LOG_DIR", tmp_logs):
            _log_parse_failure("test-domain", "this is not json at all {...")
        
        log_path = os.path.join(tmp_logs, "critic_parse_failures.jsonl")
        assert os.path.exists(log_path)
        with open(log_path) as f:
            entry = json.loads(f.readline())
        assert entry["domain"] == "test-domain"
        assert "this is not json" in entry["raw_text"]
        assert "timestamp" in entry

    def test_truncates_long_raw_text(self, tmp_logs):
        from agents.critic import _log_parse_failure
        long_text = "x" * 10000
        with patch("agents.critic.LOG_DIR", tmp_logs):
            _log_parse_failure("test-domain", long_text)
        
        log_path = os.path.join(tmp_logs, "critic_parse_failures.jsonl")
        with open(log_path) as f:
            entry = json.loads(f.readline())
        assert len(entry["raw_text"]) == 5000

    def test_multiple_failures_appended(self, tmp_logs):
        from agents.critic import _log_parse_failure
        with patch("agents.critic.LOG_DIR", tmp_logs):
            _log_parse_failure("domain-a", "fail 1")
            _log_parse_failure("domain-b", "fail 2")
        
        log_path = os.path.join(tmp_logs, "critic_parse_failures.jsonl")
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["domain"] == "domain-a"
        assert json.loads(lines[1])["domain"] == "domain-b"


# ============================================================
# Critic: Ensemble Mode
# ============================================================

class TestCriticEnsemble:
    """Test the dual-critic ensemble scoring."""

    def _make_critique_result(self, accuracy=7, depth=6, completeness=6,
                              specificity=5, honesty=7, overall=6.2):
        return {
            "scores": {
                "accuracy": accuracy, "depth": depth, "completeness": completeness,
                "specificity": specificity, "intellectual_honesty": honesty,
            },
            "overall_score": overall,
            "strengths": ["good research"],
            "weaknesses": ["could be better"],
            "actionable_feedback": "try harder next time",
            "verdict": "accept" if overall >= 6 else "reject",
        }

    @patch("config.CRITIC_ENSEMBLE_MODEL_B", None)
    @patch("agents.critic._critique_single")
    def test_ensemble_averages_scores(self, mock_single):
        from agents.critic import _critique_ensemble, DEFAULT_RUBRIC_WEIGHTS
        
        result_a = self._make_critique_result(accuracy=8, depth=6, overall=7.0)
        result_b = self._make_critique_result(accuracy=6, depth=8, overall=7.0)
        mock_single.side_effect = [result_a, result_b]
        
        result = _critique_ensemble({}, "test", DEFAULT_RUBRIC_WEIGHTS, None)
        
        assert result["scores"]["accuracy"] == 7.0  # (8+6)/2
        assert result["scores"]["depth"] == 7.0  # (6+8)/2
        assert result["_ensemble"] is True
        assert result["_ensemble_scores"] == [7.0, 7.0]
        assert mock_single.call_count == 2

    @patch("config.CRITIC_ENSEMBLE_MODEL_B", None)
    @patch("agents.critic._critique_single")
    def test_ensemble_parse_error_fallback_a(self, mock_single):
        from agents.critic import _critique_ensemble, DEFAULT_RUBRIC_WEIGHTS
        
        result_a = {"_parse_error": True, "overall_score": 0}
        result_b = self._make_critique_result(accuracy=7, overall=6.5)
        mock_single.side_effect = [result_a, result_b]
        
        result = _critique_ensemble({}, "test", DEFAULT_RUBRIC_WEIGHTS, None)
        assert result["scores"]["accuracy"] == 7
        assert result["_ensemble"] == "fallback_b"

    @patch("config.CRITIC_ENSEMBLE_MODEL_B", None)
    @patch("agents.critic._critique_single")
    def test_ensemble_parse_error_fallback_b(self, mock_single):
        from agents.critic import _critique_ensemble, DEFAULT_RUBRIC_WEIGHTS
        
        result_a = self._make_critique_result(accuracy=7, overall=6.5)
        result_b = {"_parse_error": True, "overall_score": 0}
        mock_single.side_effect = [result_a, result_b]
        
        result = _critique_ensemble({}, "test", DEFAULT_RUBRIC_WEIGHTS, None)
        assert result["scores"]["accuracy"] == 7
        assert result["_ensemble"] == "fallback_a"

    @patch("config.CRITIC_ENSEMBLE_MODEL_B", None)
    @patch("agents.critic._critique_single")
    def test_ensemble_divergence_warning(self, mock_single):
        from agents.critic import _critique_ensemble, DEFAULT_RUBRIC_WEIGHTS
        
        result_a = self._make_critique_result(overall=9.0)
        result_b = self._make_critique_result(overall=5.0)
        mock_single.side_effect = [result_a, result_b]
        
        result = _critique_ensemble({}, "test", DEFAULT_RUBRIC_WEIGHTS, None)
        assert result["_ensemble_divergence"] == 4.0
        assert any("ENSEMBLE WARNING" in w for w in result["weaknesses"])

    @patch("config.CRITIC_ENSEMBLE_MODEL_B", None)
    @patch("agents.critic._critique_single")
    def test_ensemble_no_divergence_warning_when_close(self, mock_single):
        from agents.critic import _critique_ensemble, DEFAULT_RUBRIC_WEIGHTS
        
        result_a = self._make_critique_result(overall=7.0)
        result_b = self._make_critique_result(overall=7.5)
        mock_single.side_effect = [result_a, result_b]
        
        result = _critique_ensemble({}, "test", DEFAULT_RUBRIC_WEIGHTS, None)
        assert result["_ensemble_divergence"] == 0.5
        assert not any("ENSEMBLE WARNING" in w for w in result["weaknesses"])

    @patch("config.CRITIC_ENSEMBLE_MODEL_B", None)
    @patch("agents.critic._critique_single")
    def test_ensemble_deduplicates_strengths(self, mock_single):
        from agents.critic import _critique_ensemble, DEFAULT_RUBRIC_WEIGHTS
        
        result_a = self._make_critique_result()
        result_a["strengths"] = ["thorough", "well-sourced"]
        result_b = self._make_critique_result()
        result_b["strengths"] = ["thorough", "detailed"]
        mock_single.side_effect = [result_a, result_b]
        
        result = _critique_ensemble({}, "test", DEFAULT_RUBRIC_WEIGHTS, None)
        # "thorough" should appear only once
        assert result["strengths"].count("thorough") == 1
        assert "well-sourced" in result["strengths"]
        assert "detailed" in result["strengths"]


# ============================================================
# Critic: Dispatch (critique function)
# ============================================================

class TestCritiqueDispatch:
    """Test that critique() dispatches to single or ensemble based on config."""

    @patch("agents.critic._validate_confidence_claims", side_effect=lambda r, c, s: c)
    @patch("agents.critic._critique_single")
    def test_dispatch_single_by_default(self, mock_single, mock_validate):
        from agents.critic import critique
        mock_single.return_value = {"overall_score": 7.0, "verdict": "accept", "scores": {}}
        
        with patch("config.CRITIC_ENSEMBLE", False):
            critique({"findings": []}, "test")
        
        mock_single.assert_called_once()

    @patch("agents.critic._validate_confidence_claims", side_effect=lambda r, c, s: c)
    @patch("agents.critic._critique_ensemble")
    def test_dispatch_ensemble_when_enabled(self, mock_ensemble, mock_validate):
        from agents.critic import critique
        mock_ensemble.return_value = {"overall_score": 7.0, "verdict": "accept", "scores": {}}
        
        with patch("config.CRITIC_ENSEMBLE", True):
            critique({"findings": []}, "test")
        
        mock_ensemble.assert_called_once()


# ============================================================
# Orchestrator: Score Plateau Detection
# ============================================================

class TestPlateauDetection:
    """Test that plateau scoring deprioritizes stagnant domains."""

    def _make_outputs_with_scores(self, scores):
        """Build a list of mock outputs with given scores."""
        return [
            {"critique": {"overall_score": s}, "timestamp": datetime.now(timezone.utc).isoformat()}
            for s in scores
        ]

    @patch("agents.orchestrator.load_knowledge_base", return_value=None)
    @patch("agents.orchestrator.list_pending", return_value=[])
    @patch("agents.orchestrator.get_strategy_status", return_value="active")
    @patch("agents.orchestrator.get_active_version", return_value="v002")
    @patch("agents.orchestrator.load_outputs")
    def test_plateau_deprioritizes(self, mock_outputs, *mocks):
        from agents.orchestrator import _score_domain_priority
        
        # 5 scores all within 0.5 range → plateau
        mock_outputs.return_value = self._make_outputs_with_scores([7.0, 7.1, 7.2, 7.0, 7.3])
        
        stats = {"count": 5, "accepted": 4, "rejected": 1, "avg_score": 7.12}
        result = _score_domain_priority("test", stats, "v002", "active", 0, False)
        
        assert any("plateau" in r for r in result["reasons"])
        # The -10 penalty should be reflected
        # Without plateau, a domain with 5 outputs would get some base score
        # With plateau it should be lower

    @patch("agents.orchestrator.load_knowledge_base", return_value=None)
    @patch("agents.orchestrator.list_pending", return_value=[])
    @patch("agents.orchestrator.get_strategy_status", return_value="active")
    @patch("agents.orchestrator.get_active_version", return_value="v002")
    @patch("agents.orchestrator.load_outputs")
    def test_no_plateau_with_variance(self, mock_outputs, *mocks):
        from agents.orchestrator import _score_domain_priority
        
        # Wide range of scores → no plateau
        mock_outputs.return_value = self._make_outputs_with_scores([5.0, 6.0, 7.0, 8.0, 9.0])
        
        stats = {"count": 5, "accepted": 4, "rejected": 1, "avg_score": 7.0}
        result = _score_domain_priority("test", stats, "v002", "active", 0, False)
        
        assert not any("plateau" in r for r in result["reasons"])

    @patch("agents.orchestrator.load_knowledge_base", return_value=None)
    @patch("agents.orchestrator.list_pending", return_value=[])
    @patch("agents.orchestrator.get_strategy_status", return_value="active")
    @patch("agents.orchestrator.get_active_version", return_value="v002")
    def test_no_plateau_with_few_outputs(self, *mocks):
        from agents.orchestrator import _score_domain_priority
        
        # Only 3 outputs — below plateau window
        stats = {"count": 3, "accepted": 2, "rejected": 1, "avg_score": 6.0}
        result = _score_domain_priority("test", stats, "v002", "active", 0, False)
        
        assert not any("plateau" in r for r in result["reasons"])


# ============================================================
# Orchestrator: Time Decay
# ============================================================

class TestTimeDecay:
    """Test that stale domains get a priority boost."""

    def _make_old_output(self, days_ago):
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        return {"critique": {"overall_score": 7.0}, "timestamp": ts}

    @patch("agents.orchestrator.load_knowledge_base", return_value=None)
    @patch("agents.orchestrator.list_pending", return_value=[])
    @patch("agents.orchestrator.get_strategy_status", return_value="active")
    @patch("agents.orchestrator.get_active_version", return_value="v002")
    @patch("agents.orchestrator.load_outputs")
    def test_stale_domain_boosted(self, mock_outputs, *mocks):
        from agents.orchestrator import _score_domain_priority
        
        # Last research was 10 days ago (>7 day threshold)
        mock_outputs.return_value = [self._make_old_output(10)]
        
        stats = {"count": 1, "accepted": 1, "rejected": 0, "avg_score": 7.0}
        result = _score_domain_priority("test", stats, "v002", "active", 0, False)
        
        assert any("stale" in r for r in result["reasons"])

    @patch("agents.orchestrator.load_knowledge_base", return_value=None)
    @patch("agents.orchestrator.list_pending", return_value=[])
    @patch("agents.orchestrator.get_strategy_status", return_value="active")
    @patch("agents.orchestrator.get_active_version", return_value="v002")
    @patch("agents.orchestrator.load_outputs")
    def test_recent_domain_not_boosted(self, mock_outputs, *mocks):
        from agents.orchestrator import _score_domain_priority
        
        # Last research was 2 days ago (<7 day threshold)
        mock_outputs.return_value = [self._make_old_output(2)]
        
        stats = {"count": 1, "accepted": 1, "rejected": 0, "avg_score": 7.0}
        result = _score_domain_priority("test", stats, "v002", "active", 0, False)
        
        assert not any("stale" in r for r in result["reasons"])


# ============================================================
# Orchestrator: Config-driven max_per_domain
# ============================================================

class TestAllocateRoundsConfig:
    """Test that allocate_rounds uses ORCH_MAX_PER_DOMAIN from config."""

    def test_default_uses_config(self):
        from agents.orchestrator import allocate_rounds
        
        priorities = [{
            "domain": "test",
            "priority": 50.0,
            "reasons": ["needs data"],
            "action": "auto",
            "skip": False,
            "stats": {"count": 2, "accepted": 1, "rejected": 1, "avg_score": 5.0},
            "strategy": "v001",
            "strategy_status": "active",
        }]
        
        with patch("agents.orchestrator.ORCH_MAX_PER_DOMAIN", 3):
            result = allocate_rounds(priorities, total_rounds=10)
        
        # Should cap at 3 (from config), not default 5
        assert result[0]["rounds"] <= 3

    def test_explicit_override_still_works(self):
        from agents.orchestrator import allocate_rounds
        
        priorities = [{
            "domain": "test",
            "priority": 50.0,
            "reasons": [],
            "action": "auto",
            "skip": False,
            "stats": {"count": 2, "accepted": 1, "rejected": 1, "avg_score": 5.0},
            "strategy": "v001",
            "strategy_status": "active",
        }]
        
        # Explicit override should take precedence
        result = allocate_rounds(priorities, total_rounds=10, max_per_domain=2)
        assert result[0]["rounds"] <= 2


# ============================================================
# Critic: Rubric Loading
# ============================================================

class TestRubricLoading:
    """Test adaptive rubric weight loading."""

    def test_default_rubric(self):
        from agents.critic import load_rubric, DEFAULT_RUBRIC_WEIGHTS
        # Non-existent domain → default
        rubric = load_rubric("nonexistent-domain-xyz")
        assert rubric == DEFAULT_RUBRIC_WEIGHTS

    def test_custom_rubric(self, tmp_path):
        from agents.critic import load_rubric
        domain = "custom-test"
        rubric_dir = tmp_path / "strategies" / domain
        rubric_dir.mkdir(parents=True)
        rubric_data = {
            "weights": {
                "accuracy": 0.40,
                "depth": 0.15,
                "completeness": 0.15,
                "specificity": 0.15,
                "intellectual_honesty": 0.15,
            },
            "reason": "boost accuracy"
        }
        (rubric_dir / "_rubric.json").write_text(json.dumps(rubric_data))
        
        with patch("agents.critic.STRATEGY_DIR", str(tmp_path / "strategies")):
            rubric = load_rubric(domain)
        
        assert rubric["accuracy"] == 0.40

    def test_invalid_rubric_falls_back(self, tmp_path):
        from agents.critic import load_rubric, DEFAULT_RUBRIC_WEIGHTS
        domain = "bad-rubric"
        rubric_dir = tmp_path / "strategies" / domain
        rubric_dir.mkdir(parents=True)
        # Weights don't sum to 1.0
        rubric_data = {"weights": {"accuracy": 0.9, "depth": 0.9, "completeness": 0.9, "specificity": 0.9, "intellectual_honesty": 0.9}}
        (rubric_dir / "_rubric.json").write_text(json.dumps(rubric_data))
        
        with patch("agents.critic.STRATEGY_DIR", str(tmp_path / "strategies")):
            rubric = load_rubric(domain)
        
        assert rubric == DEFAULT_RUBRIC_WEIGHTS


# ============================================================
# Config: New Constants Exist
# ============================================================

class TestUpliftConfig:
    """Verify all new config constants are present with expected types."""

    def test_critic_config(self):
        import config
        assert isinstance(config.CRITIC_ENSEMBLE, bool)
        assert isinstance(config.CRITIC_LOG_PARSE_FAILURES, bool)
        assert isinstance(config.CONFIDENCE_VALIDATION, bool)
        assert isinstance(config.CONFIDENCE_PENALTY, (int, float))
        assert config.CONFIDENCE_PENALTY > 0

    def test_orchestrator_config(self):
        import config
        assert isinstance(config.ORCH_MAX_PER_DOMAIN, int)
        assert isinstance(config.ORCH_SCORE_PLATEAU_WINDOW, int)
        assert isinstance(config.ORCH_SCORE_PLATEAU_RANGE, (int, float))
        assert isinstance(config.ORCH_TIME_DECAY_DAYS, int)
        assert isinstance(config.ORCH_TIME_DECAY_BOOST, (int, float))
        assert isinstance(config.AUTO_DEDUP_RETRIES, int)
        assert config.ORCH_MAX_PER_DOMAIN > 0
        assert config.ORCH_SCORE_PLATEAU_WINDOW >= 3
        assert config.AUTO_DEDUP_RETRIES >= 0
