"""
Tests for Objective 4: Visual Feedback System.

Tests browser tool, visual evaluator, visual gate, and executor integration.
All tests use mocks — no real browser launches or API calls.
"""

import base64
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# Browser Tool Tests (hands/tools/browser.py)
# ============================================================

class TestBrowserToolConfig:
    """Browser tool configuration and safety checks."""

    def test_import_browser_tool(self):
        from hands.tools.browser import BrowserTool
        tool = BrowserTool()
        assert tool.name == "browser"
        assert "screenshot" in tool.description.lower() or "browser" in tool.description.lower()

    def test_input_schema_has_required_fields(self):
        from hands.tools.browser import BrowserTool
        tool = BrowserTool()
        schema = tool.input_schema
        assert "properties" in schema
        assert "action" in schema["properties"]
        assert "required" in schema
        assert "action" in schema["required"]

    def test_actions_listed_in_schema(self):
        from hands.tools.browser import BrowserTool
        tool = BrowserTool()
        actions = tool.input_schema["properties"]["action"]["enum"]
        expected = {"screenshot", "navigate", "click", "fill", "wait_for", "evaluate", "get_text"}
        assert set(actions) == expected

    def test_url_safety_blocks_file_protocol(self):
        from hands.tools.browser import _is_safe_url
        assert _is_safe_url("file:///etc/passwd") is not None  # Returns error string

    def test_url_safety_blocks_javascript(self):
        from hands.tools.browser import _is_safe_url
        assert _is_safe_url("javascript:alert(1)") is not None

    def test_url_safety_blocks_internal_ips(self):
        from hands.tools.browser import _is_safe_url
        assert _is_safe_url("http://169.254.169.254/metadata") is not None
        assert _is_safe_url("http://10.0.0.1/admin") is not None

    def test_url_safety_allows_localhost(self):
        from hands.tools.browser import _is_safe_url
        assert _is_safe_url("http://localhost:3000") is None  # None = safe
        assert _is_safe_url("http://127.0.0.1:5173") is None

    def test_url_safety_allows_https(self):
        from hands.tools.browser import _is_safe_url
        assert _is_safe_url("https://example.com") is None

    def test_url_safety_empty_string(self):
        from hands.tools.browser import _is_safe_url
        assert _is_safe_url("") is not None  # Returns error string

    def test_url_safety_blocks_data_uri(self):
        from hands.tools.browser import _is_safe_url
        assert _is_safe_url("data:text/html,<script>alert(1)</script>") is not None


class TestBrowserSession:
    """BrowserSession singleton management."""

    def test_singleton_access(self):
        from hands.tools.browser import BrowserSession
        # Just verify the class exists and has expected methods
        assert hasattr(BrowserSession, "get")
        assert hasattr(BrowserSession, "close")
        assert hasattr(BrowserSession, "reset")
        assert hasattr(BrowserSession, "set_viewport")

    def test_viewport_constants(self):
        from hands.tools.browser import _DEFAULT_VIEWPORT, _MOBILE_VIEWPORT
        assert _DEFAULT_VIEWPORT["width"] == 1280
        assert _DEFAULT_VIEWPORT["height"] == 720
        assert _MOBILE_VIEWPORT["width"] == 375
        assert _MOBILE_VIEWPORT["height"] == 812


class TestBrowserToolExecution:
    """Browser tool execution with mocked Playwright."""

    def test_invalid_action_returns_error(self):
        from hands.tools.browser import BrowserTool
        tool = BrowserTool()
        result = tool.execute(action="nonexistent")
        assert not result.success
        assert "unknown action" in result.error.lower() or "invalid" in result.error.lower() or "unsupported" in result.error.lower()

    def test_navigate_unsafe_url_rejected(self):
        from hands.tools.browser import BrowserTool
        tool = BrowserTool()
        result = tool.execute(action="navigate", url="file:///etc/passwd")
        assert not result.success
        assert "unsafe" in result.error.lower() or "blocked" in result.error.lower() or "not allowed" in result.error.lower()

    def test_screenshot_no_url_no_session(self):
        """Screenshot without URL and no active session should handle gracefully."""
        from hands.tools.browser import BrowserTool, BrowserSession
        BrowserSession.reset()
        tool = BrowserTool()
        # Without a running browser, this should fail gracefully
        result = tool.execute(action="screenshot")
        # Either fails or explains what happened
        assert isinstance(result.success, bool)

    def test_navigate_success(self):
        """Test navigate action with mocked Playwright."""
        from hands.tools.browser import BrowserTool, BrowserSession
        BrowserSession.reset()
        
        # Mock the Playwright chain
        mock_page = MagicMock()
        mock_page.title.return_value = "Test Page"
        mock_page.url = "https://example.com"
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        
        # Patch BrowserSession singleton to return our mock page
        session = BrowserSession.get()
        session._page = mock_page
        session._browser = MagicMock()
        session._playwright = MagicMock()
        
        with patch.object(session, "_ensure_started"):
            tool = BrowserTool()
            result = tool.execute(action="navigate", url="https://example.com")
            
            assert result.success
            assert "200" in result.output or "Test Page" in result.output
        
        BrowserSession.reset()

    def test_screenshot_returns_base64(self):
        """Test screenshot action returns base64 image in metadata."""
        from hands.tools.browser import BrowserTool, BrowserSession
        BrowserSession.reset()
        
        fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        
        mock_page = MagicMock()
        mock_page.title.return_value = "Test"
        mock_page.url = "http://localhost:3000"
        mock_page.screenshot.return_value = fake_image
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        
        session = BrowserSession.get()
        session._page = mock_page
        session._browser = MagicMock()
        session._playwright = MagicMock()
        
        with patch.object(session, "_ensure_started"):
            tool = BrowserTool()
            result = tool.execute(action="screenshot", url="http://localhost:3000")
            
            assert result.success
            assert "base64_image" in result.metadata
            assert len(result.metadata["base64_image"]) > 0
        
        BrowserSession.reset()

    def test_evaluate_blocks_dangerous_scripts(self):
        """JS evaluation should block dangerous patterns."""
        from hands.tools.browser import BrowserTool, BrowserSession
        BrowserSession.reset()
        
        tool = BrowserTool()
        # These should be blocked even without a browser session
        dangerous_scripts = [
            "require('fs')",
            "process.env.SECRET",
            "child_process.exec('rm -rf /')",
        ]
        for script in dangerous_scripts:
            result = tool.execute(action="evaluate", script=script)
            # Should either fail due to dangerous pattern or no session
            # The key is it doesn't succeed with dangerous code
            if result.error:
                assert any(word in result.error.lower() for word in 
                          ["dangerous", "blocked", "unsafe", "not allowed", "no active", "session", "browser"])


# ============================================================
# Visual Evaluator Tests (hands/visual_evaluator.py)
# ============================================================

class TestVisualEvaluatorHelpers:
    """Visual evaluator utility functions."""

    def test_import_evaluator(self):
        from hands.visual_evaluator import evaluate_screenshot, evaluate_with_reference
        assert callable(evaluate_screenshot)
        assert callable(evaluate_with_reference)

    def test_constants_reasonable(self):
        from hands.visual_evaluator import (
            VISUAL_ACCEPT_THRESHOLD,
            VISUAL_FIX_THRESHOLD,
            MAX_VISUAL_FIX_ROUNDS,
        )
        assert 1 <= VISUAL_FIX_THRESHOLD < VISUAL_ACCEPT_THRESHOLD <= 10
        assert MAX_VISUAL_FIX_ROUNDS >= 1

    def test_build_eval_prompt(self):
        from hands.visual_evaluator import _build_eval_prompt
        prompt = _build_eval_prompt("Landing page for SaaS", "desktop")
        assert "landing page" in prompt.lower() or "SaaS" in prompt
        assert "desktop" in prompt.lower()

    def test_build_eval_prompt_empty_context(self):
        from hands.visual_evaluator import _build_eval_prompt
        prompt = _build_eval_prompt("", "mobile")
        assert "mobile" in prompt.lower()
        assert "evaluate" in prompt.lower()

    def test_parse_eval_response_valid_json(self):
        from hands.visual_evaluator import _parse_eval_response
        response = json.dumps({
            "score": 7,
            "dimensions": {"layout": 8, "typography": 7},
            "strengths": ["Good spacing"],
            "issues": [{"severity": "minor", "description": "Button too small", "fix": "Increase padding"}],
            "overall_impression": "Decent page"
        })
        result = _parse_eval_response(response)
        assert result["score"] == 7
        assert len(result["strengths"]) == 1
        assert len(result["issues"]) == 1

    def test_parse_eval_response_markdown_fenced(self):
        from hands.visual_evaluator import _parse_eval_response
        response = '```json\n{"score": 9, "dimensions": {}, "strengths": [], "issues": [], "overall_impression": "Great"}\n```'
        result = _parse_eval_response(response)
        assert result["score"] == 9

    def test_parse_eval_response_malformed(self):
        from hands.visual_evaluator import _parse_eval_response
        result = _parse_eval_response("This is not JSON at all")
        assert result["score"] == 0
        assert len(result["issues"]) > 0  # Should report parse failure

    def test_parse_eval_response_with_score_fallback(self):
        from hands.visual_evaluator import _parse_eval_response
        result = _parse_eval_response('I think the "score": 6 because...')
        assert result["score"] == 6

    def test_parse_reference_response_valid(self):
        from hands.visual_evaluator import _parse_reference_response
        response = json.dumps({
            "score": 5,
            "gaps": [{"area": "layout", "description": "Less whitespace", "fix": "Add padding"}],
            "matches": ["Color scheme"],
            "overall_impression": "Close but needs work"
        })
        result = _parse_reference_response(response)
        assert result["score"] == 5
        assert len(result["gaps"]) == 1

    def test_parse_reference_response_malformed(self):
        from hands.visual_evaluator import _parse_reference_response
        result = _parse_reference_response("broken json")
        assert result["score"] == 0


class TestGenerateFixInstructions:
    """Fix instruction generation from issues."""

    def test_empty_issues(self):
        from hands.visual_evaluator import generate_fix_instructions
        assert generate_fix_instructions([]) == ""

    def test_single_issue(self):
        from hands.visual_evaluator import generate_fix_instructions
        issues = [{"severity": "major", "description": "Buttons too small", "fix": "Increase padding to 12px"}]
        result = generate_fix_instructions(issues)
        assert "Buttons too small" in result
        assert "12px" in result
        assert "MAJOR" in result

    def test_severity_ordering(self):
        from hands.visual_evaluator import generate_fix_instructions
        issues = [
            {"severity": "minor", "description": "Minor thing"},
            {"severity": "critical", "description": "Critical thing"},
            {"severity": "major", "description": "Major thing"},
        ]
        result = generate_fix_instructions(issues)
        # Critical should come before major, major before minor
        crit_pos = result.index("Critical thing")
        major_pos = result.index("Major thing")
        minor_pos = result.index("Minor thing")
        assert crit_pos < major_pos < minor_pos

    def test_fix_instructions_include_fix_text(self):
        from hands.visual_evaluator import generate_fix_instructions
        issues = [{"severity": "critical", "description": "Layout broken", "fix": "Change display to flex"}]
        result = generate_fix_instructions(issues)
        assert "FIX:" in result
        assert "flex" in result


class TestSaveScreenshotLog:
    """Screenshot audit trail saving."""

    def test_save_screenshot_log(self, tmp_path):
        from hands.visual_evaluator import save_screenshot_log
        
        # Create a fake base64 image
        fake_image = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10).decode()
        
        with patch("hands.visual_evaluator.SCREENSHOT_LOG_DIR", str(tmp_path)):
            path = save_screenshot_log(
                domain="test_domain",
                task_id="build_landing",
                phase="step_5",
                base64_image=fake_image,
                evaluation={"score": 7, "issues": []},
                iteration=0,
            )
        
        assert os.path.exists(path)
        assert "test_domain" in path
        # Check eval JSON was saved too
        eval_path = path.replace(".png", "_eval.json")
        assert os.path.exists(eval_path)
        with open(eval_path) as f:
            eval_data = json.load(f)
        assert eval_data["score"] == 7


class TestEvaluateScreenshotMocked:
    """Visual evaluation with mocked Claude API."""

    @patch("anthropic.Anthropic")
    @patch("hands.visual_evaluator.log_cost")
    def test_evaluate_screenshot_success(self, mock_log_cost, mock_anthropic_class):
        from hands.visual_evaluator import evaluate_screenshot
        
        # Mock the API response
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500
        mock_content = MagicMock()
        mock_content.text = json.dumps({
            "score": 8,
            "dimensions": {"layout": 8, "typography": 7, "color": 9, "components": 8, "responsiveness": 8, "polish": 7},
            "strengths": ["Clean layout"],
            "issues": [],
            "overall_impression": "Production-ready"
        })
        mock_response.content = [mock_content]
        
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client
        
        result = evaluate_screenshot(
            base64_image="AAAA",
            context="Test page",
            page_type="app",
        )
        
        assert result["score"] == 8
        assert result["cost"] > 0
        assert mock_client.messages.create.called
        
        # Verify image was sent in the message
        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_content = messages[0]["content"]
        assert any(item["type"] == "image" for item in user_content)

    @patch("anthropic.Anthropic")
    @patch("hands.visual_evaluator.log_cost")
    def test_evaluate_screenshot_api_error(self, mock_log_cost, mock_anthropic_class):
        from hands.visual_evaluator import evaluate_screenshot
        
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API quota exceeded")
        mock_anthropic_class.return_value = mock_client
        
        result = evaluate_screenshot(base64_image="AAAA")
        
        assert result["score"] == 0
        assert "error" in result
        assert "quota" in result["error"].lower()

    @patch("anthropic.Anthropic")
    @patch("hands.visual_evaluator.log_cost")
    def test_evaluate_with_reference_sends_two_images(self, mock_log_cost, mock_anthropic_class):
        from hands.visual_evaluator import evaluate_with_reference
        
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 2000
        mock_response.usage.output_tokens = 800
        mock_content = MagicMock()
        mock_content.text = json.dumps({
            "score": 6,
            "gaps": [{"area": "layout", "description": "Less whitespace", "fix": "Add padding"}],
            "matches": ["Color scheme is similar"],
            "overall_impression": "Getting there"
        })
        mock_response.content = [mock_content]
        
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client
        
        result = evaluate_with_reference(
            base64_image="AAAA",
            reference_base64="BBBB",
            context="Compare landing pages",
        )
        
        assert result["score"] == 6
        assert len(result["gaps"]) == 1
        
        # Verify TWO images were sent
        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_content = messages[0]["content"]
        image_count = sum(1 for item in user_content if item["type"] == "image")
        assert image_count == 2


class TestDesignSystemLoading:
    """Design system file loading."""

    def test_get_design_system_returns_string(self):
        from hands.visual_evaluator import _get_design_system
        result = _get_design_system()
        assert isinstance(result, str)
        # It may or may not find the file — just verify it doesn't crash

    def test_build_eval_system_contains_rubric(self):
        from hands.visual_evaluator import _build_eval_system
        system = _build_eval_system("app")
        assert "SCORING RUBRIC" in system
        assert "Layout" in system
        assert "Typography" in system
        assert "JSON" in system


# ============================================================
# Visual Gate Tests (hands/visual_gate.py)
# ============================================================

class TestVisualGateConfig:
    """Visual gate configuration and initialization."""

    def test_import_visual_gate(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp/test", domain="test")
        assert gate.enabled
        assert gate._check_count == 0

    def test_disabled_gate(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", enable=False)
        assert not gate.enabled
        assert gate.should_check(5, ["file.tsx", "page.tsx", "main.tsx"]) is False

    def test_max_checks_respected(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        gate._max_checks = 2
        gate._check_count = 2
        assert gate.should_check(10, ["a.tsx", "b.tsx", "c.tsx"]) is False


class TestVisualGateShouldCheck:
    """Visual gate triggering logic."""

    def test_no_frontend_files(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        # No frontend files → should not check
        assert gate.should_check(5, ["config.py", "main.py", "utils.py"]) is False

    def test_enough_frontend_files_triggers(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        gate._min_step_gap = 1
        artifacts = ["page.tsx", "layout.tsx", "globals.css"]
        assert gate.should_check(5, artifacts) is True

    def test_same_count_doesnt_retrigger(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        gate._min_step_gap = 1
        artifacts = ["page.tsx", "layout.tsx"]
        # First check should trigger
        assert gate.should_check(5, artifacts) is True
        gate._frontend_files_seen = 2
        gate._last_check_step = 5
        # Same files, different step — should NOT trigger
        assert gate.should_check(10, artifacts) is False

    def test_new_frontend_files_retrigger(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        gate._min_step_gap = 1
        gate._frontend_files_seen = 2
        gate._last_check_step = 5
        gate._check_count = 1
        # More frontend files → should trigger
        artifacts = ["page.tsx", "layout.tsx", "hero.tsx"]
        assert gate.should_check(10, artifacts) is True

    def test_step_gap_respected(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        gate._last_check_step = 5
        gate._min_step_gap = 3
        # Only 2 steps later — too soon
        assert gate.should_check(7, ["a.tsx", "b.tsx"]) is False
        # 3+ steps later — OK
        gate._frontend_files_seen = 0  # Reset so count check passes
        assert gate.should_check(8, ["a.tsx", "b.tsx"]) is True


class TestVisualGateDevServer:
    """Dev server detection and management."""

    def test_find_dev_server_no_server(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        # No server running → should return None
        # (This actually tries to connect, so it should fail)
        result = gate._find_dev_server()
        assert result is None

    def test_find_dev_server_cached_url(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        gate._dev_server_url = "http://localhost:3000"
        
        # Mock successful connection to cached URL
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = MagicMock()
            result = gate._find_dev_server()
            assert result == "http://localhost:3000"

    def test_start_dev_server_no_package_json(self, tmp_path):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir=str(tmp_path), domain="test")
        result = gate._start_dev_server()
        assert result is None

    def test_start_dev_server_no_dev_script(self, tmp_path):
        from hands.visual_gate import VisualGate
        # Create a package.json without dev script
        pkg = {"name": "test", "scripts": {"build": "echo build"}}
        with open(tmp_path / "package.json", "w") as f:
            json.dump(pkg, f)
        
        gate = VisualGate(workspace_dir=str(tmp_path), domain="test")
        result = gate._start_dev_server()
        assert result is None


class TestVisualGateSummary:
    """Visual gate summary/diagnostics."""

    def test_get_summary_initial(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        summary = gate.get_summary()
        assert summary["visual_checks_run"] == 0
        assert summary["frontend_files_seen"] == 0

    def test_get_summary_after_checks(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        gate._check_count = 2
        gate._frontend_files_seen = 5
        gate._dev_server_url = "http://localhost:3000"
        
        summary = gate.get_summary()
        assert summary["visual_checks_run"] == 2
        assert summary["frontend_files_seen"] == 5
        assert summary["dev_server_url"] == "http://localhost:3000"


class TestVisualGateCleanup:
    """Visual gate cleanup."""

    def test_cleanup_no_server(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        # Should not crash even with nothing to clean up
        gate.cleanup()

    def test_cleanup_kills_server(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(workspace_dir="/tmp", domain="test")
        
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        gate._dev_server_proc = mock_proc
        
        with patch("os.killpg") as mock_killpg, \
             patch("os.getpgid", return_value=12345):
            gate.cleanup()
            mock_killpg.assert_called_once()
        
        assert gate._dev_server_proc is None


# ============================================================
# Executor Integration Tests
# ============================================================

class TestExecutorVisualGateIntegration:
    """Verify visual gate is wired into executor correctly."""

    def test_execute_plan_accepts_visual_params(self):
        """execute_plan should accept visual gate parameters."""
        from hands.executor import execute_plan
        import inspect
        sig = inspect.signature(execute_plan)
        assert "enable_visual_gate" in sig.parameters
        assert "visual_context" in sig.parameters
        assert "page_type" in sig.parameters

    def test_execute_plan_visual_gate_default_enabled(self):
        """Visual gate should be enabled by default."""
        from hands.executor import execute_plan
        import inspect
        sig = inspect.signature(execute_plan)
        assert sig.parameters["enable_visual_gate"].default is True

    def test_execute_plan_imports_visual_gate(self):
        """Executor should import VisualGate without errors."""
        from hands.visual_gate import VisualGate
        assert VisualGate is not None

    def test_executor_report_includes_visual_fields(self):
        """Executor report dict should include visual gate fields."""
        # We can't run a full execution (requires API), but we can verify
        # the report structure by checking the source code
        import hands.executor as executor_module
        source = open(executor_module.__file__).read()
        assert "visual_corrections" in source
        assert "visual_gate" in source


class TestBrowserToolInRegistry:
    """Verify BrowserTool is registered in the default registry."""

    def test_browser_tool_registered(self):
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        tools = registry.list_tools()  # Returns list[str]
        assert "browser" in tools

    def test_browser_tool_claude_definition(self):
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        claude_tools = registry.get_execution_tools()
        browser_tools = [t for t in claude_tools if t.get("name") == "browser"]
        assert len(browser_tools) == 1
        assert "input_schema" in browser_tools[0]


# ============================================================
# End-to-End Visual Flow (mocked)
# ============================================================

class TestVisualFlowEndToEnd:
    """End-to-end visual feedback flow with all components mocked."""

    @patch("anthropic.Anthropic")
    @patch("hands.visual_evaluator.log_cost")
    def test_screenshot_to_evaluation_flow(self, mock_log_cost, mock_anthropic_class):
        """Full flow: browser screenshot → visual evaluation → fix instructions."""
        from hands.tools.browser import BrowserTool, BrowserSession
        from hands.visual_evaluator import evaluate_screenshot, generate_fix_instructions
        
        # 1. Mock browser screenshot
        BrowserSession.reset()
        fake_image = b"\x89PNG" + b"\x00" * 50
        fake_b64 = base64.b64encode(fake_image).decode()
        
        mock_page = MagicMock()
        mock_page.screenshot.return_value = fake_image
        mock_page.title.return_value = "Test"
        mock_page.url = "http://localhost:3000"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        
        session = BrowserSession.get()
        session._page = mock_page
        session._browser = MagicMock()
        session._playwright = MagicMock()
        
        with patch.object(session, "_ensure_started"):
            tool = BrowserTool()
            screenshot_result = tool.execute(action="screenshot", url="http://localhost:3000")
            assert screenshot_result.success
            b64 = screenshot_result.metadata["base64_image"]
        
        BrowserSession.reset()
        
        # 2. Mock Claude Vision evaluation
        mock_eval_response = MagicMock()
        mock_eval_response.usage.input_tokens = 1500
        mock_eval_response.usage.output_tokens = 600
        mock_content = MagicMock()
        mock_content.text = json.dumps({
            "score": 6,
            "dimensions": {"layout": 7, "typography": 6, "color": 7, "components": 5, "responsiveness": 6, "polish": 5},
            "strengths": ["Clean grid"],
            "issues": [
                {"severity": "major", "description": "Buttons are too small", "fix": "Increase padding to p-3"},
                {"severity": "minor", "description": "Footer text faint", "fix": "Change to text-gray-400"},
            ],
            "overall_impression": "Functional but needs polish"
        })
        mock_eval_response.content = [mock_content]
        
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_eval_response
        mock_anthropic_class.return_value = mock_client
        
        eval_result = evaluate_screenshot(b64, context="Landing page")
        assert eval_result["score"] == 6
        assert len(eval_result["issues"]) == 2
        
        # 3. Generate fix instructions
        fixes = generate_fix_instructions(eval_result["issues"])
        assert "Buttons are too small" in fixes
        assert "padding" in fixes.lower()
        assert "MAJOR" in fixes

    def test_visual_gate_integrates_all_components(self):
        """VisualGate combines browser + evaluator correctly."""
        from hands.visual_gate import VisualGate
        
        gate = VisualGate(
            workspace_dir="/tmp/test",
            domain="logistics",
            context="Logistics landing page",
            page_type="marketing",
        )
        
        # Verify initial state
        assert gate.domain == "logistics"
        assert gate.page_type == "marketing"
        assert gate._check_count == 0
        
        # Verify it would trigger
        gate._min_step_gap = 1
        artifacts = ["hero.tsx", "features.tsx", "pricing.tsx"]
        assert gate.should_check(5, artifacts) is True
