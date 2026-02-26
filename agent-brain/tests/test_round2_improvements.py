"""
Tests for Round 2 improvements:
- DuckDuckGo retry on transient failures
- Strategy store JSON error handling
- Fetch-count accounting for search_and_fetch
- Critic source verification
- Tool usage log collection
- Prior knowledge in user message (not system prompt)
- Single-variable evolution prompt
"""

import json
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── DuckDuckGo Retry ────────────────────────────────────────────────

class TestWebSearchRetry:
    """web_search should retry on transient failures."""

    def test_retries_on_rate_limit(self):
        """Should retry when DuckDuckGo returns a rate limit error."""
        from tools.web_search import web_search

        call_count = [0]
        
        def mock_text(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("429 Too Many Requests")
            return [{"title": "Result", "href": "http://example.com", "body": "Snippet"}]
        
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text = mock_text

        with patch("tools.web_search.DDGS", return_value=mock_ddgs), \
             patch("tools.web_search.time.sleep"):  # Skip actual delays
            results = web_search("test query")
        
        assert len(results) == 1
        assert results[0]["title"] == "Result"
        assert call_count[0] == 3  # 2 failures + 1 success

    def test_returns_error_after_max_retries(self):
        """Should return error marker after exhausting retries."""
        from tools.web_search import web_search

        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text = MagicMock(side_effect=Exception("timeout error"))

        with patch("tools.web_search.DDGS", return_value=mock_ddgs), \
             patch("tools.web_search.time.sleep"):
            results = web_search("test query")
        
        assert len(results) == 1
        assert results[0].get("error") is True
        assert "timeout" in results[0]["snippet"]

    def test_no_retry_on_non_retryable_error(self):
        """Should not retry on non-transient errors (e.g. invalid query)."""
        from tools.web_search import web_search

        call_count = [0]
        
        def mock_text(*args, **kwargs):
            call_count[0] += 1
            raise ValueError("Invalid query parameter")
        
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text = mock_text

        with patch("tools.web_search.DDGS", return_value=mock_ddgs), \
             patch("tools.web_search.time.sleep"):
            results = web_search("test query")
        
        assert call_count[0] == 1  # No retry — error is not retryable
        assert results[0].get("error") is True


# ── Strategy Store JSON Safety ───────────────────────────────────────

class TestStrategyStoreJsonSafety:
    """Strategy store should handle corrupt JSON gracefully."""

    def test_load_meta_corrupt_json(self, tmp_path):
        """_load_meta should return {} on corrupt JSON."""
        from strategy_store import _load_meta, _meta_path
        
        domain_dir = tmp_path / "test_domain"
        domain_dir.mkdir()
        meta_path = domain_dir / "_meta.json"
        meta_path.write_text("{invalid json content")
        
        with patch("strategy_store.STRATEGY_DIR", str(tmp_path)):
            result = _load_meta("test_domain")
        
        assert result == {}

    def test_load_strategy_file_corrupt_json(self, tmp_path):
        """_load_strategy_file should return None on corrupt JSON."""
        from strategy_store import _load_strategy_file
        
        domain_dir = tmp_path / "test_domain"
        domain_dir.mkdir()
        strategy_file = domain_dir / "researcher_v001.json"
        strategy_file.write_text("not valid json {{{")
        
        with patch("strategy_store.STRATEGY_DIR", str(tmp_path)):
            result = _load_strategy_file("researcher", "test_domain", "v001")
        
        assert result is None

    def test_load_strategy_file_valid_json(self, tmp_path):
        """Normal operation should still work."""
        from strategy_store import _load_strategy_file
        
        domain_dir = tmp_path / "test_domain"
        domain_dir.mkdir()
        data = {"strategy": "test strategy content", "version": "v001"}
        strategy_file = domain_dir / "researcher_v001.json"
        strategy_file.write_text(json.dumps(data))
        
        with patch("strategy_store.STRATEGY_DIR", str(tmp_path)):
            result = _load_strategy_file("researcher", "test_domain", "v001")
        
        assert result == data


# ── Fetch-Count Accounting ────────────────────────────────────────────

class TestFetchCountAccounting:
    """search_and_fetch should correctly account for actual pages fetched."""

    def test_search_and_fetch_increments_by_max_fetch(self):
        """fetch_count should increase by max_fetch, not 1."""
        # Read the researcher source and verify the logic
        import agents.researcher as researcher_module
        import inspect
        
        source = inspect.getsource(researcher_module.research)
        
        # The code should increment fetch_count by max_fetch before the check
        assert "fetch_count += max_fetch" in source, "search_and_fetch should increment fetch_count by actual pages"
        # And it should check BOTH limits
        assert "fetch_count > MAX_FETCHES" in source, "search_and_fetch should check fetch limit"


# ── Critic Source Verification ────────────────────────────────────────

class TestCriticSourceVerification:
    """Critic should accept and use source verification data."""

    def test_critique_accepts_sources_summary(self):
        """critique() should accept sources_summary parameter."""
        from agents.critic import critique
        import inspect
        
        sig = inspect.signature(critique)
        assert "sources_summary" in sig.parameters

    def test_critique_includes_source_block(self):
        """When sources_summary is provided, critic should receive source data."""
        from agents.critic import critique
        
        research_output = {
            "question": "Test question",
            "findings": [{"claim": "Test claim", "confidence": "high", "source": "http://example.com"}],
            "summary": "Test summary",
        }
        sources = [
            {"tool": "web_search", "query": "test query", "success": True, "results": 5},
            {"tool": "fetch_page", "url": "http://example.com", "success": True, "chars": 5000, "title": "Example"},
        ]
        
        # Mock the API call and capture what was sent
        captured_messages = []
        
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "scores": {"accuracy": 8, "depth": 7, "completeness": 7, "specificity": 7, "intellectual_honesty": 8},
            "overall_score": 7.5,
            "strengths": ["Good sources"],
            "weaknesses": [],
            "actionable_feedback": "None needed",
            "verdict": "accept",
        }))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        
        def capture_create_message(client, **kwargs):
            captured_messages.append(kwargs.get("messages", []))
            return mock_response
        
        with patch("agents.critic.create_message", side_effect=capture_create_message), \
             patch("agents.critic.log_cost"):
            result = critique(research_output, domain="test", sources_summary=sources)
        
        assert len(captured_messages) == 1
        user_msg = captured_messages[0][0]["content"]
        assert "SOURCE VERIFICATION DATA" in user_msg
        assert "http://example.com" in user_msg
        assert "test query" in user_msg

    def test_critique_without_sources_works(self):
        """critique() should still work when sources_summary is None."""
        from agents.critic import critique
        
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "scores": {"accuracy": 7, "depth": 7, "completeness": 7, "specificity": 7, "intellectual_honesty": 7},
            "overall_score": 7.0,
            "strengths": [],
            "weaknesses": [],
            "actionable_feedback": "",
            "verdict": "accept",
        }))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        
        with patch("agents.critic.create_message", return_value=mock_response), \
             patch("agents.critic.log_cost"):
            result = critique({"question": "Q", "findings": [], "summary": "S"}, sources_summary=None)
        
        assert result["verdict"] == "accept"


# ── Tool Usage Log ────────────────────────────────────────────────────

class TestToolUsageLog:
    """Researcher should emit _tool_log with tool usage details."""

    def test_tool_log_included_in_result(self):
        """Research result should include _tool_log field."""
        from agents.researcher import research
        
        # Mock a simple response with no tool use
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text=json.dumps({
            "question": "Test",
            "findings": [{"claim": "test", "confidence": "low", "source": ""}],
            "summary": "test",
        }))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=100)
        
        with patch("agents.researcher.create_message", return_value=mock_response), \
             patch("agents.researcher.log_cost"), \
             patch("agents.researcher.retrieve_relevant", return_value=[]), \
             patch("agents.researcher.load_knowledge_base", return_value=None):
            result = research("Test question")
        
        assert "_tool_log" in result
        assert isinstance(result["_tool_log"], list)

    def test_meta_analyst_includes_tool_usage(self):
        """Meta-analyst _prepare_analysis_data should include tool_usage when available."""
        from agents.meta_analyst import _prepare_analysis_data
        
        outputs = [{
            "question": "Q1",
            "overall_score": 7,
            "verdict": "accept",
            "critique": {"scores": {"accuracy": 7}, "strengths": [], "weaknesses": [], "actionable_feedback": ""},
            "research": {
                "summary": "Test",
                "knowledge_gaps": [],
                "findings": [{"claim": "C1"}],
                "_searches_made": 2,
                "_empty_searches": 0,
                "_tool_log": [
                    {"tool": "web_search", "query": "test query", "success": True, "results": 5},
                    {"tool": "fetch_page", "url": "http://example.com", "success": True, "chars": 3000},
                ],
            },
        }]
        
        data_str = _prepare_analysis_data(outputs, "test strategy", "")
        data = json.loads(data_str)
        
        output_data = data["outputs"][0]
        assert "tool_usage" in output_data
        assert output_data["tool_usage"]["search_queries"] == ["test query"]
        assert output_data["tool_usage"]["total_chars_retrieved"] == 3000
        assert output_data["tool_usage"]["fetch_success_rate"] == 1.0


# ── Prior Knowledge in User Message ──────────────────────────────────

class TestPriorKnowledgeInUserMessage:
    """Prior knowledge should be in user message, not system prompt."""

    def test_prior_knowledge_not_in_system_prompt(self):
        """System prompt should NOT contain prior knowledge."""
        from agents.researcher import research
        
        captured_kwargs = []
        
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(text=json.dumps({
            "question": "Test",
            "findings": [],
            "summary": "test",
        }))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=100)
        
        def capture_create(client, **kwargs):
            captured_kwargs.append(kwargs)
            return mock_response
        
        # Return some prior knowledge
        kb = {"claims": [{"claim": "KB claim 1", "confidence": "high", "status": "active"}], "domain_summary": "Test domain"}
        relevant = [{"question": "Past Q", "score": 8, "summary": "Past summary", "key_insights": ["Insight 1"], "knowledge_gaps": ["Gap 1"], "findings": []}]
        
        with patch("agents.researcher.create_message", side_effect=capture_create), \
             patch("agents.researcher.log_cost"), \
             patch("agents.researcher.retrieve_relevant", return_value=relevant), \
             patch("agents.researcher.load_knowledge_base", return_value=kb):
            research("Test question", domain="test")
        
        assert len(captured_kwargs) > 0
        system = captured_kwargs[0].get("system", "")
        messages = captured_kwargs[0].get("messages", [])
        user_msg = messages[0]["content"] if messages else ""
        
        # Prior knowledge should be in user message
        assert "PRIOR KNOWLEDGE" in user_msg
        assert "KB claim 1" in user_msg
        # System prompt should NOT have prior knowledge
        assert "PRIOR KNOWLEDGE" not in system


# ── Single-Variable Evolution ────────────────────────────────────────

class TestSingleVariableEvolution:
    """Meta-analyst prompt should enforce limited changes per evolution."""

    def test_prompt_limits_changes(self):
        """Meta-analyst prompt should instruct max 2 changes."""
        from agents.meta_analyst import _build_meta_prompt
        
        prompt = _build_meta_prompt()
        assert "at most 2 changes" in prompt
        assert "primary_change" in prompt

    def test_prompt_includes_tool_usage_framework(self):
        """Meta-analyst prompt should mention tool usage analysis."""
        from agents.meta_analyst import _build_meta_prompt
        
        prompt = _build_meta_prompt()
        assert "tool_usage" in prompt.lower() or "tool usage" in prompt.lower()
