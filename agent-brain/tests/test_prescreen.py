"""Tests for the pre-screen critic module."""

import pytest
from unittest.mock import patch, MagicMock
from prescreen import (
    prescreen, build_prescreen_critique, _structural_precheck,
    PRESCREEN_ACCEPT_THRESHOLD, PRESCREEN_REJECT_THRESHOLD,
)


class TestStructuralPrecheck:
    """Zero-cost structural checks (no LLM)."""

    def test_zero_findings_rejects(self):
        result = _structural_precheck({"findings": [], "_zero_findings": True})
        assert result is not None
        assert result["decision"] == "reject"
        assert result["skip_claude"] is True
        assert result["prescreen_score"] == 1.0

    def test_empty_findings_list_rejects(self):
        result = _structural_precheck({"findings": []})
        assert result is not None
        assert result["decision"] == "reject"

    def test_parse_error_rejects(self):
        result = _structural_precheck({
            "findings": [{"claim": "something"}],
            "_parse_error": True,
        })
        assert result is not None
        assert result["decision"] == "reject"
        assert result["prescreen_score"] == 2.0

    def test_single_finding_no_summary_rejects(self):
        result = _structural_precheck({
            "findings": [{"claim": "one thing"}],
            "summary": "",
        })
        assert result is not None
        assert result["decision"] == "reject"
        assert result["prescreen_score"] == 2.5

    def test_mostly_empty_searches_rejects(self):
        result = _structural_precheck({
            "findings": [{"claim": "a"}, {"claim": "b"}],
            "summary": "ok",
            "_empty_searches": 9,
            "_searches_made": 10,
        })
        assert result is not None
        assert result["decision"] == "reject"
        assert result["prescreen_score"] == 3.0

    def test_normal_output_returns_none(self):
        """Good-looking output should pass structural checks."""
        result = _structural_precheck({
            "findings": [
                {"claim": "finding 1", "source": "url1"},
                {"claim": "finding 2", "source": "url2"},
                {"claim": "finding 3", "source": "url3"},
            ],
            "summary": "A relevant summary",
            "_empty_searches": 1,
            "_searches_made": 5,
        })
        assert result is None  # passes structural checks


class TestPrescreen:
    """Full pre-screen with mocked LLM."""

    def test_no_openrouter_key_escalates(self):
        with patch("prescreen.OPENROUTER_API_KEY", ""):
            result = prescreen({"findings": [{"claim": "x"}, {"claim": "y"}], "summary": "ok"})
            assert result["decision"] == "escalate"
            assert result["skip_claude"] is False

    def test_structural_reject_skips_llm(self):
        """If structural precheck rejects, LLM is never called."""
        with patch("prescreen.OPENROUTER_API_KEY", "fake-key"):
            result = prescreen({"findings": [], "_zero_findings": True})
            assert result["decision"] == "reject"
            assert result["skip_claude"] is True

    def test_high_score_accepts(self):
        """Score >= ACCEPT_THRESHOLD → accept, skip Claude."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"score": 8.5, "decision": "accept", "reason": "good"}')]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

        with patch("prescreen.OPENROUTER_API_KEY", "fake-key"), \
             patch("llm_router.call_llm", return_value=mock_response), \
             patch("prescreen.log_cost"):
            result = prescreen({
                "findings": [{"claim": "a"}, {"claim": "b"}],
                "summary": "ok",
                "question": "test?",
            })
            assert result["decision"] == "accept"
            assert result["skip_claude"] is True
            assert result["prescreen_score"] == 8.5

    def test_low_score_rejects(self):
        """Score <= REJECT_THRESHOLD → reject, skip Claude."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"score": 2.0, "decision": "reject", "reason": "terrible"}')]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

        with patch("prescreen.OPENROUTER_API_KEY", "fake-key"), \
             patch("llm_router.call_llm", return_value=mock_response), \
             patch("prescreen.log_cost"):
            result = prescreen({
                "findings": [{"claim": "a"}, {"claim": "b"}],
                "summary": "ok",
                "question": "test?",
            })
            assert result["decision"] == "reject"
            assert result["skip_claude"] is True

    def test_mid_score_escalates(self):
        """Score between thresholds → escalate to Claude."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"score": 5.5, "decision": "escalate", "reason": "uncertain"}')]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

        with patch("prescreen.OPENROUTER_API_KEY", "fake-key"), \
             patch("llm_router.call_llm", return_value=mock_response), \
             patch("prescreen.log_cost"):
            result = prescreen({
                "findings": [{"claim": "a"}, {"claim": "b"}],
                "summary": "ok",
                "question": "test?",
            })
            assert result["decision"] == "escalate"
            assert result["skip_claude"] is False

    def test_llm_error_escalates(self):
        """LLM failure → escalate (safe fallback)."""
        with patch("prescreen.OPENROUTER_API_KEY", "fake-key"), \
             patch("llm_router.call_llm", side_effect=Exception("API down")):
            result = prescreen({
                "findings": [{"claim": "a"}, {"claim": "b"}],
                "summary": "ok",
                "question": "test?",
            })
            assert result["decision"] == "escalate"
            assert result["skip_claude"] is False

    def test_parse_failure_escalates(self):
        """Unparseable LLM response → escalate."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not JSON at all")]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

        with patch("prescreen.OPENROUTER_API_KEY", "fake-key"), \
             patch("llm_router.call_llm", return_value=mock_response), \
             patch("prescreen.log_cost"):
            result = prescreen({
                "findings": [{"claim": "a"}, {"claim": "b"}],
                "summary": "ok",
                "question": "test?",
            })
            assert result["decision"] == "escalate"
            assert result["skip_claude"] is False


class TestBuildPrescreenCritique:
    """Converting prescreen results to critique-compatible dicts."""

    def test_accept_produces_valid_critique(self):
        result = build_prescreen_critique({
            "prescreen_score": 8.0,
            "decision": "accept",
            "reason": "looks good",
        })
        assert result["verdict"] == "accept"
        assert result["overall_score"] == 8.0
        assert result["_prescreened"] is True
        assert "scores" in result

    def test_reject_produces_valid_critique(self):
        result = build_prescreen_critique({
            "prescreen_score": 2.0,
            "decision": "reject",
            "reason": "terrible output",
        })
        assert result["verdict"] == "reject"
        assert result["overall_score"] == 2.0
        assert result["_prescreened"] is True
        assert "terrible output" in result["weaknesses"]

    def test_critique_has_all_dimensions(self):
        result = build_prescreen_critique({
            "prescreen_score": 6.0,
            "decision": "accept",
            "reason": "ok",
        })
        expected_dims = {"accuracy", "depth", "completeness", "specificity", "intellectual_honesty"}
        assert set(result["scores"].keys()) == expected_dims
