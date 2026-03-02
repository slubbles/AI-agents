"""Tests for the progress tracker module."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock
from progress_tracker import (
    should_assess, assess_progress, get_progress, display_progress,
    ASSESS_EVERY_N, _progress_path,
)


class TestShouldAssess:
    """Determining when to run a progress assessment."""

    def test_no_goal_returns_false(self):
        with patch("progress_tracker.get_goal", return_value=None):
            assert should_assess("test") is False

    def test_not_enough_outputs_returns_false(self):
        with patch("progress_tracker.get_goal", return_value="Learn about X"), \
             patch("progress_tracker.load_outputs", return_value=[]):
            assert should_assess("test") is False

    def test_enough_accepted_outputs_returns_true(self, tmp_path):
        accepted = [
            {"critique": {"verdict": "accept"}} for _ in range(ASSESS_EVERY_N)
        ]
        strat_dir = str(tmp_path / "strategies" / "test")
        os.makedirs(strat_dir, exist_ok=True)

        with patch("progress_tracker.get_goal", return_value="Learn about X"), \
             patch("progress_tracker.load_outputs", return_value=accepted), \
             patch("progress_tracker.STRATEGIES_DIR", str(tmp_path / "strategies")):
            assert should_assess("test") is True

    def test_already_assessed_recently_returns_false(self, tmp_path):
        accepted = [
            {"critique": {"verdict": "accept"}} for _ in range(ASSESS_EVERY_N)
        ]
        strat_dir = str(tmp_path / "strategies" / "test")
        os.makedirs(strat_dir, exist_ok=True)
        # Write a progress file showing we assessed at count=5
        progress_path = os.path.join(strat_dir, "_progress.json")
        with open(progress_path, "w") as f:
            json.dump({"assessed_at_count": ASSESS_EVERY_N, "readiness": 30}, f)

        with patch("progress_tracker.get_goal", return_value="Learn about X"), \
             patch("progress_tracker.load_outputs", return_value=accepted), \
             patch("progress_tracker.STRATEGIES_DIR", str(tmp_path / "strategies")):
            assert should_assess("test") is False


class TestAssessProgress:
    """Progress assessment with mocked LLM."""

    def test_no_goal_returns_none(self):
        with patch("progress_tracker.get_goal", return_value=None):
            result = assess_progress("test", force=True)
            assert result is None

    def test_no_api_key_returns_none(self):
        with patch("progress_tracker.get_goal", return_value="Learn X"), \
             patch("progress_tracker.OPENROUTER_API_KEY", ""):
            result = assess_progress("test", force=True)
            assert result is None

    def test_assess_with_force(self, tmp_path):
        """Force assessment produces a progress report."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "readiness": 45,
            "gaps": ["missing competitor data", "no pricing info"],
            "strengths": ["good market overview"],
            "recommendation": "keep_researching",
            "reasoning": "solid start but key gaps remain",
        }))]
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)

        strat_dir = str(tmp_path / "strategies")
        os.makedirs(os.path.join(strat_dir, "test"), exist_ok=True)

        accepted = [
            {
                "critique": {"verdict": "accept", "overall_score": 7},
                "research": {"question": f"Q{i}", "summary": f"Summary {i}"},
            }
            for i in range(5)
        ]

        with patch("progress_tracker.get_goal", return_value="Understand the market"), \
             patch("progress_tracker.OPENROUTER_API_KEY", "fake-key"), \
             patch("progress_tracker.load_outputs", return_value=accepted), \
             patch("llm_router.call_llm", return_value=mock_response), \
             patch("progress_tracker.log_cost"), \
             patch("progress_tracker.STRATEGIES_DIR", strat_dir):
            result = assess_progress("test", force=True)

        assert result is not None
        assert result["readiness"] == 45
        assert result["recommendation"] == "keep_researching"
        assert len(result["gaps"]) == 2
        assert result["domain"] == "test"

    def test_readiness_clamped(self, tmp_path):
        """Readiness is clamped to 0-100."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "readiness": 150,
            "gaps": [],
            "strengths": [],
            "recommendation": "ready_to_act",
            "reasoning": "done",
        }))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

        strat_dir = str(tmp_path / "strategies")
        os.makedirs(os.path.join(strat_dir, "test"), exist_ok=True)

        with patch("progress_tracker.get_goal", return_value="X"), \
             patch("progress_tracker.OPENROUTER_API_KEY", "fake-key"), \
             patch("progress_tracker.load_outputs", return_value=[]), \
             patch("llm_router.call_llm", return_value=mock_response), \
             patch("progress_tracker.log_cost"), \
             patch("progress_tracker.STRATEGIES_DIR", strat_dir):
            result = assess_progress("test", force=True)

        assert result["readiness"] == 100  # clamped


class TestGetProgress:
    """Loading saved progress."""

    def test_no_file_returns_none(self, tmp_path):
        with patch("progress_tracker.STRATEGIES_DIR", str(tmp_path / "strategies")):
            result = get_progress("nonexistent")
            assert result is None

    def test_loads_saved_progress(self, tmp_path):
        strat_dir = str(tmp_path / "strategies" / "test")
        os.makedirs(strat_dir, exist_ok=True)
        progress = {"readiness": 60, "domain": "test", "recommendation": "keep_researching"}
        with open(os.path.join(strat_dir, "_progress.json"), "w") as f:
            json.dump(progress, f)

        with patch("progress_tracker.STRATEGIES_DIR", str(tmp_path / "strategies")):
            result = get_progress("test")
            assert result["readiness"] == 60


class TestDisplayProgress:
    """Progress display output."""

    def test_no_progress_displays_message(self, tmp_path, capsys):
        with patch("progress_tracker.STRATEGIES_DIR", str(tmp_path / "strategies")), \
             patch("progress_tracker.get_goal", return_value=None):
            display_progress("test")
        output = capsys.readouterr().out
        assert "No progress" in output

    def test_with_progress_displays_bar(self, tmp_path, capsys):
        strat_dir = str(tmp_path / "strategies" / "test")
        os.makedirs(strat_dir, exist_ok=True)
        progress = {
            "readiness": 50,
            "domain": "test",
            "goal": "Learn about markets",
            "recommendation": "keep_researching",
            "gaps": ["pricing data"],
            "strengths": ["market overview"],
            "readiness_change": 10,
            "assessed_at": "2026-03-01T00:00:00Z",
            "assessed_at_count": 10,
            "reasoning": "Good progress",
        }
        with open(os.path.join(strat_dir, "_progress.json"), "w") as f:
            json.dump(progress, f)

        with patch("progress_tracker.STRATEGIES_DIR", str(tmp_path / "strategies")):
            display_progress("test")
        output = capsys.readouterr().out
        assert "50%" in output
        assert "█" in output
        assert "pricing data" in output
