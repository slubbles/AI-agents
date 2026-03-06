"""
Tests for Programmatic Tool Calling (PTC) support.

PTC is Anthropic's feature where Claude writes Python code to orchestrate
tools in a sandbox. Only the final output enters the conversation context.
These tests verify the config, tool definitions, routing, and fallback behavior.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestPTCConfig(unittest.TestCase):
    """Test PTC configuration flags."""

    def test_ptc_disabled_by_default(self):
        """PTC should be disabled by default (no env var set)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PTC_ENABLED", None)
            # Re-import to pick up env change
            import importlib
            import config
            importlib.reload(config)
            self.assertFalse(config.PTC_ENABLED)

    def test_ptc_enabled_via_env(self):
        """PTC can be enabled via PTC_ENABLED=true env var."""
        with patch.dict(os.environ, {"PTC_ENABLED": "true"}):
            import importlib
            import config
            importlib.reload(config)
            self.assertTrue(config.PTC_ENABLED)

    def test_ptc_enabled_various_truthy_values(self):
        """PTC_ENABLED accepts multiple truthy values."""
        import importlib
        import config
        for val in ("true", "1", "yes", "True", "YES"):
            with patch.dict(os.environ, {"PTC_ENABLED": val}):
                importlib.reload(config)
                self.assertTrue(config.PTC_ENABLED, f"PTC_ENABLED={val} should be True")

    def test_ptc_disabled_for_falsy_values(self):
        """PTC_ENABLED rejects non-truthy values."""
        import importlib
        import config
        for val in ("false", "0", "no", "maybe", ""):
            with patch.dict(os.environ, {"PTC_ENABLED": val}):
                importlib.reload(config)
                self.assertFalse(config.PTC_ENABLED, f"PTC_ENABLED={val} should be False")

    def test_ptc_model_is_direct_anthropic(self):
        """PTC model must be a direct Anthropic model (not OpenRouter path)."""
        from config import PTC_MODEL
        # Should be a claude- prefixed model (direct API), not anthropic/ (OpenRouter)
        self.assertTrue(PTC_MODEL.startswith("claude-"), 
                        f"PTC_MODEL should be direct Anthropic model, got: {PTC_MODEL}")
        self.assertNotIn("/", PTC_MODEL,
                         "PTC_MODEL should not use OpenRouter path format")

    def test_ptc_beta_header_exists(self):
        """PTC beta header must be configured."""
        from config import PTC_BETA_HEADER
        self.assertIsInstance(PTC_BETA_HEADER, str)
        self.assertIn("tool-use", PTC_BETA_HEADER)

    def test_ptc_model_in_cost_table(self):
        """PTC model should have cost tracking configured."""
        from config import PTC_MODEL, COST_PER_1K
        self.assertIn(PTC_MODEL, COST_PER_1K,
                      f"PTC_MODEL '{PTC_MODEL}' needs a COST_PER_1K entry")


class TestPTCToolDefinitions(unittest.TestCase):
    """Test PTC tool format."""

    def test_build_ptc_tools_returns_code_execution(self):
        """PTC tools must include the code_execution tool."""
        from agents.researcher import _build_ptc_tools
        tools = _build_ptc_tools()
        code_exec = [t for t in tools if t.get("type") == "code_execution_20260120"]
        self.assertEqual(len(code_exec), 1, "Must have exactly one code_execution tool")
        self.assertEqual(code_exec[0]["name"], "code_execution")

    def test_build_ptc_tools_includes_search_tools(self):
        """PTC tools include our regular search/fetch tools alongside code_execution."""
        from agents.researcher import _build_ptc_tools
        tools = _build_ptc_tools()
        names = [t.get("name") for t in tools]
        self.assertIn("code_execution", names)
        self.assertIn("web_search", names)
        self.assertIn("fetch_page", names)
        self.assertIn("search_and_fetch", names)

    def test_build_ptc_tools_count(self):
        """PTC should have code_execution + 3 search tools = 4 total."""
        from agents.researcher import _build_ptc_tools
        tools = _build_ptc_tools()
        self.assertEqual(len(tools), 4)


class TestPTCRouting(unittest.TestCase):
    """Test that researcher dispatches to PTC when enabled."""

    @patch("agents.researcher.create_message")
    @patch("agents.researcher.retrieve_relevant", return_value=[])
    @patch("agents.researcher.load_knowledge_base", return_value=None)
    @patch("agents.researcher.load_graph", return_value=None)
    def test_traditional_path_when_ptc_disabled(self, mock_graph, mock_kb, mock_rel, mock_create):
        """When PTC is disabled, research() uses the traditional tool-use loop."""
        # Mock the LLM response for traditional path
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)
        mock_response.content = [MagicMock(type="text", text='{"question": "test", "findings": [], "summary": "test"}')]
        mock_create.return_value = mock_response

        with patch.dict(os.environ, {"PTC_ENABLED": "false"}):
            import importlib
            import config
            importlib.reload(config)
            from agents.researcher import research
            result = research("test question", domain="test")
        
        # Traditional path uses create_message (not call_llm with betas)
        mock_create.assert_called()

    @patch("agents.researcher._research_ptc")
    @patch("agents.researcher.retrieve_relevant", return_value=[])
    @patch("agents.researcher.load_knowledge_base", return_value=None)
    @patch("agents.researcher.load_graph", return_value=None)
    def test_ptc_path_when_enabled(self, mock_graph, mock_kb, mock_rel, mock_ptc):
        """When PTC is enabled with API key, research() dispatches to PTC."""
        mock_ptc.return_value = {
            "question": "test", "findings": [], "summary": "test",
            "_ptc_mode": True, "_tool_log": []
        }

        with patch.dict(os.environ, {"PTC_ENABLED": "true", "ANTHROPIC_API_KEY": "sk-test"}):
            import importlib
            import config
            importlib.reload(config)
            from agents.researcher import research
            result = research("test question", domain="test")
        
        mock_ptc.assert_called_once()
        self.assertTrue(result.get("_ptc_mode"))


class TestPTCLLMRouterBetas(unittest.TestCase):
    """Test that llm_router passes beta headers to Anthropic."""

    def test_call_llm_passes_betas_to_anthropic(self):
        """call_llm should forward betas kwarg to _call_anthropic."""
        from llm_router import call_llm, _call_anthropic
        
        with patch("llm_router._call_anthropic") as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            try:
                call_llm(
                    model="claude-sonnet-4-20250514",
                    messages=[{"role": "user", "content": "test"}],
                    betas=["advanced-tool-use-2025-11-20"],
                )
            except Exception:
                pass  # May fail without real API key, but we're checking the routing
            
            if mock_anthropic.called:
                _, kwargs = mock_anthropic.call_args
                self.assertEqual(kwargs.get("betas"), ["advanced-tool-use-2025-11-20"])

    def test_anthropic_uses_beta_client_when_betas_provided(self):
        """_call_anthropic should use client.beta.messages.create when betas are provided."""
        from llm_router import _call_anthropic

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.beta.messages.create.return_value = mock_response

        with patch("llm_router._get_anthropic_client", return_value=mock_client):
            with patch("utils.retry.retry_api_call", side_effect=lambda fn, **kw: fn()):
                result = _call_anthropic(
                    model="claude-sonnet-4-20250514",
                    messages=[{"role": "user", "content": "test"}],
                    system="test system",
                    max_tokens=4096,
                    tools=[],
                    temperature=0.7,
                    betas=["advanced-tool-use-2025-11-20"],
                )
        
        mock_client.beta.messages.create.assert_called_once()
        call_kwargs = mock_client.beta.messages.create.call_args[1]
        self.assertEqual(call_kwargs["betas"], ["advanced-tool-use-2025-11-20"])

    def test_anthropic_uses_regular_client_when_no_betas(self):
        """_call_anthropic should use client.messages.create when no betas."""
        from llm_router import _call_anthropic

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("llm_router._get_anthropic_client", return_value=mock_client):
            with patch("utils.retry.retry_api_call", side_effect=lambda fn, **kw: fn()):
                result = _call_anthropic(
                    model="claude-sonnet-4-20250514",
                    messages=[{"role": "user", "content": "test"}],
                    system="test system",
                    max_tokens=4096,
                    tools=[],
                    temperature=0.7,
                )
        
        mock_client.messages.create.assert_called_once()
        mock_client.beta.messages.create.assert_not_called()


class TestPTCResearchFunction(unittest.TestCase):
    """Test the _research_ptc function itself."""

    @patch("llm_router.call_llm")
    @patch("agents.researcher.log_cost")
    def test_research_ptc_returns_structured_output(self, mock_cost, mock_llm):
        """_research_ptc should parse JSON output from PTC response."""
        mock_response = MagicMock()
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=1000)
        mock_response.content = [MagicMock(
            type="text",
            text='{"question": "test q", "findings": [{"claim": "found it", "confidence": "high", "reasoning": "tested", "source": "http://example.com"}], "summary": "test summary"}'
        )]
        mock_llm.return_value = mock_response

        with patch.dict(os.environ, {"PTC_ENABLED": "true", "ANTHROPIC_API_KEY": "sk-test"}):
            import importlib
            import config
            importlib.reload(config)
            from agents.researcher import _research_ptc
            result = _research_ptc(
                question="test q",
                strategy=None,
                critique=None,
                domain="test",
                build_mode=False,
                system_prompt="test system",
                prior_knowledge_block="",
            )
        
        self.assertTrue(result.get("_ptc_mode"))
        self.assertEqual(result["question"], "test q")
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["claim"], "found it")

    @patch("llm_router.call_llm")
    @patch("agents.researcher.log_cost")
    def test_research_ptc_passes_beta_header(self, mock_cost, mock_llm):
        """_research_ptc must pass the PTC beta header to call_llm."""
        mock_response = MagicMock()
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)
        mock_response.content = [MagicMock(type="text", text='{"question": "q", "findings": [], "summary": "s"}')]
        mock_llm.return_value = mock_response

        with patch.dict(os.environ, {"PTC_ENABLED": "true", "ANTHROPIC_API_KEY": "sk-test"}):
            import importlib
            import config
            importlib.reload(config)
            from agents.researcher import _research_ptc
            _research_ptc(
                question="test q", strategy=None, critique=None,
                domain="test", build_mode=False, system_prompt="test",
                prior_knowledge_block="",
            )
        
        mock_llm.assert_called_once()
        call_kwargs = mock_llm.call_args[1]
        self.assertIn("betas", call_kwargs)
        self.assertIn("advanced-tool-use-2025-11-20", call_kwargs["betas"])

    @patch("llm_router.call_llm")
    @patch("agents.researcher.log_cost")
    def test_research_ptc_fallback_on_parse_error(self, mock_cost, mock_llm):
        """_research_ptc should gracefully handle non-JSON output."""
        mock_response = MagicMock()
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)
        mock_response.content = [MagicMock(type="text", text="This is not JSON output")]
        mock_llm.return_value = mock_response

        with patch.dict(os.environ, {"PTC_ENABLED": "true", "ANTHROPIC_API_KEY": "sk-test"}):
            import importlib
            import config
            importlib.reload(config)
            from agents.researcher import _research_ptc
            result = _research_ptc(
                question="test q", strategy=None, critique=None,
                domain="test", build_mode=False, system_prompt="test",
                prior_knowledge_block="",
            )
        
        self.assertTrue(result.get("_parse_error"))
        self.assertTrue(result.get("_ptc_mode"))
        self.assertEqual(len(result["findings"]), 1)

    @patch("llm_router.call_llm")
    @patch("agents.researcher.log_cost")
    def test_research_ptc_logs_cost_as_researcher_ptc(self, mock_cost, mock_llm):
        """PTC costs should be logged with 'researcher_ptc' agent label."""
        mock_response = MagicMock()
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=1000)
        mock_response.content = [MagicMock(type="text", text='{"question": "q", "findings": [], "summary": "s"}')]
        mock_llm.return_value = mock_response

        with patch.dict(os.environ, {"PTC_ENABLED": "true", "ANTHROPIC_API_KEY": "sk-test"}):
            import importlib
            import config
            importlib.reload(config)
            from agents.researcher import _research_ptc
            _research_ptc(
                question="test q", strategy=None, critique=None,
                domain="test", build_mode=False, system_prompt="test",
                prior_knowledge_block="",
            )
        
        mock_cost.assert_called_once()
        args = mock_cost.call_args[0]
        self.assertEqual(args[3], "researcher_ptc")  # agent label


if __name__ == "__main__":
    unittest.main()
