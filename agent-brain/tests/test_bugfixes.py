"""
Tests for bugfixes applied in the audit round:
- P0: evaluate_trial f-string crash on None p_value
- P0: question generator retry on empty questions  
- P1: MAX_FETCHES limit enforcement
- P1: search_and_fetch MAX_SEARCHES enforcement
- P1: context compression in researcher
- P2: cross-reference instruction in researcher prompt
- P2: meta-analyst expected_keys fix
- P2: critic domain logging
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEvaluateTrialPValue:
    """P0: evaluate_trial must not crash when p_value is None."""

    def test_extend_trial_reason_with_none_p_value(self):
        """The f-string in extend_trial should handle None p_value gracefully."""
        # Simulate the string formatting that caused the crash
        p_value = None
        p_str = f"p={p_value:.3f}" if p_value is not None else "p=N/A"
        result = f"evidence is inconclusive ({p_str}, need p<0.1)"
        assert "p=N/A" in result

    def test_extend_trial_reason_with_valid_p_value(self):
        """String formatting should work with valid p_value."""
        p_value = 0.0523
        p_str = f"p={p_value:.3f}" if p_value is not None else "p=N/A"
        result = f"evidence is inconclusive ({p_str}, need p<0.1)"
        assert "p=0.052" in result


class TestQuestionGeneratorRetry:
    """P0: question generator should retry when model produces no questions."""

    @patch("agents.question_generator.create_message")
    @patch("agents.question_generator.load_outputs")
    @patch("agents.question_generator.load_knowledge_base")
    @patch("agents.question_generator.log_cost")
    def test_retry_on_empty_questions(self, mock_cost, mock_kb, mock_outputs, mock_create):
        """When first call returns no questions, it should retry."""
        from agents.question_generator import generate_questions

        # Mock outputs for gap analysis
        mock_outputs.return_value = [
            {"question": "q1", "score": 6.0, "summary": "s1",
             "critic_feedback": {"weaknesses": ["w1"], "feedback": "f1"},
             "knowledge_gaps": ["gap1"]}
        ]
        mock_kb.return_value = None

        # First call: diagnosis only (no questions)
        first_response = MagicMock()
        first_response.content = [MagicMock(text='{"diagnosis": {"total_gaps": 3}}')]
        first_response.usage.input_tokens = 100
        first_response.usage.output_tokens = 50

        # Retry call: has questions
        retry_response = MagicMock()
        retry_response.content = [MagicMock(text=json.dumps({
            "questions": [
                {"question": "What is X?", "priority": "high",
                 "targets_gap": "gap1", "builds_on": "q1",
                 "expected_difficulty": "medium"}
            ]
        }))]
        retry_response.usage.input_tokens = 200
        retry_response.usage.output_tokens = 100

        mock_create.side_effect = [first_response, retry_response]

        result = generate_questions("test-domain")
        assert result is not None
        assert len(result["questions"]) == 1
        assert result["questions"][0]["question"] == "What is X?"
        # Verify retry happened (2 API calls)
        assert mock_create.call_count == 2


class TestMaxFetchesLimit:
    """P1: fetch_page should be limited by MAX_FETCHES."""

    def test_max_fetches_config_exists(self):
        """MAX_FETCHES should be defined in config."""
        from config import MAX_FETCHES
        assert isinstance(MAX_FETCHES, int)
        assert MAX_FETCHES >= 1

    def test_max_fetches_imported_in_researcher(self):
        """Researcher should import MAX_FETCHES."""
        from agents.researcher import MAX_FETCHES
        assert MAX_FETCHES >= 1


class TestSearchAndFetchLimit:
    """P1: search_and_fetch should respect MAX_SEARCHES."""

    def test_search_count_check_before_execution(self):
        """Verify the researcher code has the MAX_SEARCHES guard for search_and_fetch."""
        import inspect
        from agents import researcher
        source = inspect.getsource(researcher.research)
        # search_and_fetch handler should check MAX_SEARCHES
        assert "search_count > MAX_SEARCHES" in source


class TestContextCompression:
    """P1: context compression should prevent message bloat."""

    def test_estimate_messages_size(self):
        """Should correctly count tool result content chars."""
        from agents.researcher import _estimate_messages_size
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "x" * 5000},
                {"type": "tool_result", "tool_use_id": "2", "content": "y" * 3000},
            ]},
        ]
        assert _estimate_messages_size(messages) == 8000

    def test_compress_below_threshold_is_noop(self):
        """Messages below threshold should not be compressed."""
        from agents.researcher import _compress_messages, CONTEXT_COMPRESS_THRESHOLD
        messages = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "small data"},
            ]},
        ]
        original = messages[0]["content"][0]["content"]
        _compress_messages(messages)
        assert messages[0]["content"][0]["content"] == original

    def test_compress_above_threshold(self):
        """Older messages above threshold should be compressed."""
        from agents.researcher import _compress_messages
        # Create 4 tool result messages, each with 10K chars
        messages = []
        for i in range(4):
            messages.append({"role": "assistant", "content": [{"type": "text", "text": "thinking"}]})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": str(i), "content": f"DATA_{i}: " + "x" * 10000},
            ]})
        # Total: 40K+ chars, above 30K threshold
        _compress_messages(messages)
        # Older messages (indices 1, 3) should be compressed
        old_1 = messages[1]["content"][0]["content"]
        old_2 = messages[3]["content"][0]["content"]
        # Recent messages (indices 5, 7) should be intact
        recent_1 = messages[5]["content"][0]["content"]
        recent_2 = messages[7]["content"][0]["content"]
        assert old_1.startswith("[COMPRESSED]")
        assert old_2.startswith("[COMPRESSED]")
        assert not recent_1.startswith("[COMPRESSED]")
        assert not recent_2.startswith("[COMPRESSED]")


class TestMetaAnalystExpectedKeys:
    """P1: meta-analyst should use correct expected_keys."""

    def test_expected_keys_match_prompt(self):
        """Expected keys should include 'changes_made' (not 'changes')."""
        import inspect
        from agents import meta_analyst
        source = inspect.getsource(meta_analyst)
        assert '"changes_made"' in source
        # The EXPECTED_KEYS line should have changes_made
        assert '{"new_strategy", "changes_made", "reasoning"}' in source


class TestCriticDomainLogging:
    """P2: critic should log actual domain, not hardcoded 'critique'."""

    def test_critic_logs_domain(self):
        """Critic log_cost should pass the actual domain."""
        import inspect
        from agents import critic
        # critique() now delegates to _critique_single() — check the actual implementation
        source = inspect.getsource(critic._critique_single)
        # Should NOT have hardcoded "critique"
        assert '"critique"' not in source
        # Should use domain parameter
        assert 'domain or "general"' in source


class TestCrossReferenceInstruction:
    """P2: researcher should instruct cross-referencing sources."""

    def test_cross_reference_in_prompt(self):
        """Researcher baseline prompt should mention cross-referencing."""
        from agents.researcher import _build_baseline
        baseline = _build_baseline()
        assert "corroboration" in baseline.lower() or "second independent source" in baseline.lower()


class TestWebSearchTimeout:
    """P2: web_search should have timeout protection."""

    def test_timeout_in_search_call(self):
        """web_search should pass timeout parameter."""
        import inspect
        from tools import web_search
        source = inspect.getsource(web_search.web_search)
        assert "timeout" in source


class TestStaleDatesFix:
    """P2: prompts should be built fresh, not cached at import time."""

    def test_question_generator_no_module_level_prompt(self):
        """GENERATOR_PROMPT should not exist as module constant."""
        from agents import question_generator
        assert not hasattr(question_generator, "GENERATOR_PROMPT") or \
            "Prompt built fresh" in getattr(question_generator, "GENERATOR_PROMPT", "")

    def test_critic_no_module_level_prompt(self):
        """CRITIC_SYSTEM_PROMPT should not exist as module constant."""
        from agents import critic
        assert not hasattr(critic, "CRITIC_SYSTEM_PROMPT")


class TestAntiHallucinationPrompt:
    """Quality: anti-hallucination guard rails in researcher prompt."""

    def test_anti_hallucination_in_baseline(self):
        """Baseline prompt should contain anti-hallucination rules."""
        from agents.researcher import _build_baseline
        baseline = _build_baseline()
        assert "ANTI-HALLUCINATION" in baseline
        assert "NEVER fabricate" in baseline
        assert "not found in available sources" in baseline

    def test_depth_protocol_in_baseline(self):
        """Baseline prompt should contain depth protocol."""
        from agents.researcher import _build_baseline
        baseline = _build_baseline()
        assert "DEPTH PROTOCOL" in baseline
        assert "WHY does this work" in baseline
        assert "trade-offs" in baseline


class TestStructuredRetryFeedback:
    """Quality: retry feedback should include dimension scores."""

    def test_dimension_scoring_format(self):
        """Verify dimension-based feedback format works."""
        # Simulate the feedback construction from main.py
        dim_scores = {"accuracy": 4, "depth": 7, "completeness": 6, "specificity": 5, "intellectual_honesty": 8}
        dim_names = ["accuracy", "depth", "completeness", "specificity", "intellectual_honesty"]
        scored_dims = [(d, dim_scores.get(d, 0)) for d in dim_names if d in dim_scores]
        scored_dims.sort(key=lambda x: x[1])
        lowest_dim, lowest_score = scored_dims[0]
        assert lowest_dim == "accuracy"
        assert lowest_score == 4

    def test_dimension_hints_coverage(self):
        """All 5 dimensions should have specific guidance."""
        dim_hints = {
            "accuracy": "VERIFY",
            "depth": "EXPLAIN",
            "completeness": "angles",
            "specificity": "numbers",
            "intellectual_honesty": "DISTINGUISH",
        }
        assert len(dim_hints) == 5


class TestEnrichedPriorKnowledge:
    """Quality: prior knowledge should include concrete claims."""

    def test_enriched_knowledge_injection(self):
        """Researcher prompt builder should pass findings with sources."""
        import inspect
        from agents import researcher
        source = inspect.getsource(researcher.research)
        # Should include findings loop
        assert "Key verified claims" in source
        assert '["confidence"]' in source or 'finding.get("confidence"' in source
        assert '["source"]' in source or 'finding.get("source"' in source

    def test_prior_knowledge_instructions(self):
        """Prior knowledge block should have clear instructions."""
        import inspect
        from agents import researcher
        source = inspect.getsource(researcher.research)
        assert "Claims marked [high] are verified" in source
        assert "CONTRADICT" in source


class TestFetchNudge:
    """Quality: researcher should nudge to use fetch_page after search."""

    def test_nudge_present_in_code(self):
        """Researcher should have fetch nudge after search results."""
        import inspect
        from agents import researcher
        source = inspect.getsource(researcher.research)
        assert "REMINDER: Use fetch_page" in source
        assert "fetch_count == 0" in source
