"""
Tests for research cycle improvements:
1. Goal validation (domain_goals.py)
2. Source quality tracking (source_quality.py)
3. Proven patterns in meta-analyst (agents/meta_analyst.py)
"""

import json
import os
import pytest
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# 1. Goal Validation Tests
# ============================================================

class TestGoalValidation:
    """Test validate_goal() quality scoring and feedback."""

    def test_valid_goal_passes(self):
        from domain_goals import validate_goal
        result = validate_goal("Identify the top 5 competitors in the CRM SaaS market and analyze their pricing models")
        assert result["valid"] is True
        assert result["score"] > 0.5

    def test_too_short_goal_fails(self):
        from domain_goals import validate_goal
        result = validate_goal("learn stuff")
        assert result["valid"] is False
        assert any("short" in i.lower() or "length" in i.lower() for i in result["issues"])

    def test_empty_goal_fails(self):
        from domain_goals import validate_goal
        result = validate_goal("")
        assert result["valid"] is False

    def test_vague_goal_no_specifics(self):
        from domain_goals import validate_goal
        # Has action keywords but no domain specifics and is shortish
        result = validate_goal("look at things")
        assert result["valid"] is False  # Too short

    def test_specific_goal_high_score(self):
        from domain_goals import validate_goal
        result = validate_goal("Compare pricing tiers of 3 competitors and identify gaps where we can undercut by 20%")
        assert result["score"] >= 0.5

    def test_action_keywords_boost_score(self):
        from domain_goals import validate_goal
        result_with = validate_goal("Identify and analyze top 5 competitor pricing strategies in SaaS CRM market")
        result_without = validate_goal("something about competitor pricing strategies in SaaS CRM market area")
        assert result_with["score"] >= result_without["score"]

    def test_suggestions_provided_for_weak_goals(self):
        from domain_goals import validate_goal
        result = validate_goal("look at the market for me please")
        assert len(result["suggestions"]) > 0

    def test_numbers_boost_specificity(self):
        from domain_goals import validate_goal
        result = validate_goal("Find 10 companies in the B2B SaaS space with revenue above $1M")
        assert result["score"] >= 0.5


class TestRequireGoal:
    """Test require_goal() — returns goal or None with warning."""

    @pytest.fixture
    def goal_dir(self, tmp_path):
        d = tmp_path / "strategies" / "test-domain"
        d.mkdir(parents=True)
        with patch("domain_goals.STRATEGIES_DIR", str(tmp_path / "strategies")):
            yield str(d)

    def test_returns_goal_when_set(self, goal_dir):
        from domain_goals import set_goal, require_goal
        set_goal("test-domain", "A real research goal with action words to analyze competitors")
        goal = require_goal("test-domain")
        assert goal is not None
        assert "analyze" in goal.lower()

    def test_returns_none_when_no_goal(self, goal_dir):
        from domain_goals import require_goal
        goal = require_goal("test-domain")
        assert goal is None


# ============================================================
# 2. Source Quality Tracking Tests
# ============================================================

class TestSourceQuality:
    """Test source_quality.py — recording and retrieving source rankings."""

    @pytest.fixture
    def sq_dir(self, tmp_path):
        d = tmp_path / "_source_quality"
        d.mkdir(parents=True)
        with patch("source_quality.SOURCE_DIR", str(d)):
            yield str(d)

    def test_record_and_retrieve(self, sq_dir):
        from source_quality import record_source_quality, get_source_rankings
        record_source_quality(
            domain="test",
            sources_used=["https://example.com/page", "https://docs.python.org/3/"],
            score=8.0,
            verdict="accept",
            tool_log=[
                {"tool": "fetch_page", "url": "https://example.com/page", "success": True, "chars": 5000},
                {"tool": "fetch_page", "url": "https://docs.python.org/3/", "success": True, "chars": 8000},
            ],
        )
        # One recording isn't enough for ranking (min_count=2)
        rankings = get_source_rankings("test", min_count=1)
        assert len(rankings["high_quality"]) > 0 or len(rankings["low_quality"]) > 0

    def test_high_quality_classification(self, sq_dir):
        from source_quality import record_source_quality, get_source_rankings
        # Record 3 high-scoring results for same source
        for _ in range(3):
            record_source_quality("test", ["https://arxiv.org/paper"], 8.5, "accept",
                                  [{"tool": "fetch_page", "url": "https://arxiv.org/paper", "success": True, "chars": 3000}])
        rankings = get_source_rankings("test", min_count=2)
        high_domains = [s["domain"] for s in rankings["high_quality"]]
        assert "arxiv.org" in high_domains

    def test_low_quality_classification(self, sq_dir):
        from source_quality import record_source_quality, get_source_rankings
        for _ in range(3):
            record_source_quality("test", ["https://clickbait.com/x"], 3.0, "reject",
                                  [{"tool": "fetch_page", "url": "https://clickbait.com/x", "success": True, "chars": 200}])
        rankings = get_source_rankings("test", min_count=2)
        low_domains = [s["domain"] for s in rankings["low_quality"]]
        assert "clickbait.com" in low_domains

    def test_unreliable_fetch_classification(self, sq_dir):
        from source_quality import record_source_quality, get_source_rankings
        for _ in range(3):
            record_source_quality("test", ["https://blocked.com/page"], 5.0, "accept",
                                  [{"tool": "fetch_page", "url": "https://blocked.com/page", "success": False, "chars": 0}])
        rankings = get_source_rankings("test", min_count=2)
        unreliable_domains = [s["domain"] for s in rankings["unreliable_fetch"]]
        assert "blocked.com" in unreliable_domains

    def test_format_source_hints(self, sq_dir):
        from source_quality import record_source_quality, format_source_hints_for_prompt
        for _ in range(3):
            record_source_quality("test", ["https://goodsite.com/a"], 8.0, "accept",
                                  [{"tool": "fetch_page", "url": "https://goodsite.com/a", "success": True, "chars": 5000}])
        hints = format_source_hints_for_prompt("test")
        assert "goodsite.com" in hints
        assert "HIGH-QUALITY" in hints

    def test_empty_domain_returns_empty(self, sq_dir):
        from source_quality import get_source_rankings, format_source_hints_for_prompt
        rankings = get_source_rankings("nonexistent")
        assert rankings == {"high_quality": [], "low_quality": [], "unreliable_fetch": []}
        assert format_source_hints_for_prompt("nonexistent") == ""

    def test_record_without_tool_log(self, sq_dir):
        from source_quality import record_source_quality, get_source_rankings
        # Should handle None/empty tool_log gracefully
        record_source_quality("test", ["https://site.com/page"], 7.0, "accept", None)
        record_source_quality("test", ["https://site.com/page"], 7.0, "accept", [])
        rankings = get_source_rankings("test", min_count=2)
        # Should not crash
        assert isinstance(rankings, dict)


# ============================================================
# 3. Proven Patterns Tests (meta-analyst)
# ============================================================

class TestProvenPatterns:
    """Test get_proven_patterns() and _format_proven_patterns()."""

    @pytest.fixture
    def evo_dir(self, tmp_path):
        d = tmp_path / "strategies" / "test"
        d.mkdir(parents=True)
        with patch("agents.meta_analyst.STRATEGY_DIR", str(tmp_path / "strategies")):
            yield str(d)

    def _write_evolution_log(self, evo_dir, entries):
        path = os.path.join(evo_dir, "_evolution_log.json")
        with open(path, "w") as f:
            json.dump(entries, f)

    def test_effective_pattern_extracted(self, evo_dir):
        from agents.meta_analyst import get_proven_patterns
        self._write_evolution_log(evo_dir, [
            {"version": "v002", "changes": ["Added source verification"], "primary_change": "Added source verification",
             "outcome": "confirmed", "score_before": 6.0, "score_after": 7.5},
        ])
        patterns = get_proven_patterns("test")
        assert len(patterns["effective"]) == 1
        assert patterns["effective"][0]["change"] == "Added source verification"
        assert patterns["effective"][0]["score_delta"] == 1.5

    def test_harmful_pattern_extracted(self, evo_dir):
        from agents.meta_analyst import get_proven_patterns
        self._write_evolution_log(evo_dir, [
            {"version": "v003", "changes": ["Removed depth requirement"], "primary_change": "Removed depth requirement",
             "outcome": "rollback", "score_before": 7.0, "score_after": 5.5},
        ])
        patterns = get_proven_patterns("test")
        assert len(patterns["harmful"]) == 1
        assert patterns["harmful"][0]["score_delta"] == -1.5

    def test_inconclusive_when_no_scores(self, evo_dir):
        from agents.meta_analyst import get_proven_patterns
        self._write_evolution_log(evo_dir, [
            {"version": "v001", "changes": ["Initial strategy"], "outcome": "pending",
             "score_before": None, "score_after": None},
        ])
        patterns = get_proven_patterns("test")
        assert len(patterns["inconclusive"]) == 1

    def test_empty_log_returns_empty(self, evo_dir):
        from agents.meta_analyst import get_proven_patterns
        patterns = get_proven_patterns("test")
        assert patterns == {"effective": [], "harmful": [], "inconclusive": []}

    def test_format_proven_patterns_text(self, evo_dir):
        from agents.meta_analyst import _format_proven_patterns
        self._write_evolution_log(evo_dir, [
            {"version": "v002", "changes": ["Better sources"], "primary_change": "Better sources",
             "outcome": "confirmed", "score_before": 5.0, "score_after": 7.0},
            {"version": "v003", "changes": ["Less depth"], "primary_change": "Less depth",
             "outcome": "rollback", "score_before": 7.0, "score_after": 5.0},
        ])
        text = _format_proven_patterns("test")
        assert "PROVEN EFFECTIVE" in text
        assert "Better sources" in text
        assert "PROVEN HARMFUL" in text
        assert "Less depth" in text

    def test_format_returns_empty_when_no_data(self, evo_dir):
        from agents.meta_analyst import _format_proven_patterns
        text = _format_proven_patterns("test")
        assert text == ""

    def test_mixed_evolution_entries(self, evo_dir):
        from agents.meta_analyst import get_proven_patterns
        self._write_evolution_log(evo_dir, [
            {"version": "v001", "changes": ["Initial"], "outcome": "pending",
             "score_before": None, "score_after": None},
            {"version": "v002", "changes": ["Good change"], "primary_change": "Good change",
             "outcome": "confirmed", "score_before": 5.0, "score_after": 7.0},
            {"version": "v003", "changes": ["Bad change"], "primary_change": "Bad change",
             "outcome": "rollback", "score_before": 7.0, "score_after": 4.0},
            {"version": "v004", "changes": ["Neutral"], "primary_change": "Neutral",
             "outcome": "confirmed", "score_before": 6.0, "score_after": 6.0},
        ])
        patterns = get_proven_patterns("test")
        assert len(patterns["effective"]) == 1  # v002
        assert len(patterns["harmful"]) == 1    # v003
        assert len(patterns["inconclusive"]) >= 2  # v001 + v004 (confirmed but delta=0)
