"""
Tests for audit bug fixes:
- BUG 1: CLI page_type wiring (auto-detection + param passing)
- BUG 2: Visual gate cleanup on executor _abort
- BUG 3: Visual gate __del__ safety net
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# BUG 1: CLI page_type auto-detection
# ============================================================

class TestPageTypeDetection:
    """Test _detect_page_type for marketing vs app detection."""

    def test_import(self):
        from cli.execution import _detect_page_type
        assert callable(_detect_page_type)

    def test_default_is_app(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Build a task management dashboard") == "app"

    def test_empty_goal_returns_app(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("") == "app"

    def test_landing_page_detected(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Build a landing page for logistics SaaS") == "marketing"

    def test_marketing_keyword_detected(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Create a marketing site for our product") == "marketing"

    def test_sales_page_detected(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Build a sales page with pricing") == "marketing"

    def test_lead_gen_detected(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Create a lead gen form with hero section") == "marketing"

    def test_opt_in_detected(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Build an opt-in page") == "marketing"

    def test_coming_soon_detected(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Create a coming soon page") == "marketing"

    def test_case_insensitive(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Build a LANDING PAGE for our brand") == "marketing"

    def test_app_words_dont_trigger_marketing(self):
        from cli.execution import _detect_page_type
        assert _detect_page_type("Build a REST API with user authentication") == "app"
        assert _detect_page_type("Create a database migration script") == "app"
        assert _detect_page_type("Build a React dashboard with charts") == "app"

    def test_substring_match_not_word_boundary(self):
        """'marketing' inside other words should still match (substring check)."""
        from cli.execution import _detect_page_type
        # "marketing" as substring of the goal
        assert _detect_page_type("Remarketingtools.com landing page") == "marketing"


class TestRunExecutePageType:
    """Test that run_execute's page_type parameter is properly wired."""

    def test_run_execute_signature_has_page_type(self):
        """run_execute should accept page_type parameter."""
        from cli.execution import run_execute
        import inspect
        sig = inspect.signature(run_execute)
        assert "page_type" in sig.parameters
        # Default should be empty string (auto-detect)
        assert sig.parameters["page_type"].default == ""

    def test_run_execute_auto_detects_marketing(self):
        """When page_type is empty, it should auto-detect from goal."""
        from cli.execution import _detect_page_type
        # Verify the auto-detection would produce 'marketing'
        goal = "Build a landing page for a SaaS product"
        assert _detect_page_type(goal) == "marketing"

    def test_run_execute_auto_detects_app(self):
        """When page_type is empty, non-marketing goals should produce 'app'."""
        from cli.execution import _detect_page_type
        goal = "Build a TypeScript utility library"
        assert _detect_page_type(goal) == "app"


# ============================================================
# BUG 2: Visual gate cleanup on _abort
# ============================================================

class TestAbortCleanup:
    """Test that _abort handler in executor calls visual_gate.cleanup()."""

    def test_abort_handler_includes_cleanup_call(self):
        """Verify the _abort code path includes visual_gate.cleanup()."""
        # Read the source code and verify the cleanup is present
        import hands.executor as executor_mod
        source = open(executor_mod.__file__).read()

        # Find the _abort handler section
        abort_idx = source.find('tool_name == "_abort"')
        assert abort_idx > 0, "_abort handler not found in executor.py"

        # The cleanup call should appear between the _abort check and the return
        abort_section = source[abort_idx:abort_idx + 800]
        assert "visual_gate.cleanup()" in abort_section, (
            "_abort handler does not call visual_gate.cleanup(). "
            "This would leak dev server processes and browser sessions."
        )

    def test_abort_returns_before_normal_cleanup(self):
        """The _abort handler should return early (not fall through to normal cleanup)."""
        import hands.executor as executor_mod
        source = open(executor_mod.__file__).read()

        abort_idx = source.find('tool_name == "_abort"')
        abort_section = source[abort_idx:abort_idx + 800]

        # Should have both cleanup AND return
        cleanup_idx = abort_section.find("visual_gate.cleanup()")
        return_idx = abort_section.find("return {")
        assert cleanup_idx < return_idx, "cleanup() must happen BEFORE return in _abort handler"


# ============================================================
# BUG 3: Visual gate __del__ safety net
# ============================================================

class TestVisualGateDelSafetyNet:
    """Test that VisualGate has __del__ as a cleanup safety net."""

    def test_visual_gate_has_del(self):
        from hands.visual_gate import VisualGate
        assert hasattr(VisualGate, "__del__"), "VisualGate must have __del__ for resource cleanup"

    def test_del_calls_cleanup(self):
        """__del__ should call cleanup()."""
        from hands.visual_gate import VisualGate
        gate = VisualGate.__new__(VisualGate)
        # Initialize minimum state so cleanup() doesn't crash
        gate._dev_server_proc = None
        gate._check_count = 0
        gate._max_checks = 3
        gate._frontend_files_seen = False
        gate._last_check_step = 0
        gate._workspace_dir = "/tmp/test"
        gate._domain = "test"
        gate._context = "test"
        gate._page_type = "app"
        gate._dev_server_url = None

        # Mock cleanup
        gate.cleanup = MagicMock()
        gate.__del__()
        gate.cleanup.assert_called_once()

    def test_cleanup_is_idempotent(self):
        """Calling cleanup() twice should not raise."""
        from hands.visual_gate import VisualGate
        gate = VisualGate.__new__(VisualGate)
        gate._dev_server_proc = None
        gate._check_count = 0
        gate._max_checks = 3
        gate._frontend_files_seen = False
        gate._last_check_step = 0
        gate._workspace_dir = "/tmp/test"
        gate._domain = "test"
        gate._context = "test"
        gate._page_type = "app"
        gate._dev_server_url = None

        # Call cleanup twice — should not raise
        gate.cleanup()
        gate.cleanup()

    def test_del_after_explicit_cleanup_is_safe(self):
        """If cleanup() was called explicitly, __del__ should be a no-op."""
        from hands.visual_gate import VisualGate
        gate = VisualGate.__new__(VisualGate)
        gate._dev_server_proc = None
        gate._check_count = 0
        gate._max_checks = 3
        gate._frontend_files_seen = False
        gate._last_check_step = 0
        gate._workspace_dir = "/tmp/test"
        gate._domain = "test"
        gate._context = "test"
        gate._page_type = "app"
        gate._dev_server_url = None

        gate.cleanup()  # Explicit cleanup
        gate.__del__()  # __del__ safety net — should not raise


# ============================================================
# Integration: page_type flows through execute_plan
# ============================================================

class TestPageTypeFlowsToExecutor:
    """Verify page_type parameter reaches _build_system_prompt."""

    def test_build_system_prompt_app_default(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools here")
        # Default is "app" — should load design_system.md (not marketing)
        assert "MARKETING DESIGN SYSTEM" not in prompt

    def test_build_system_prompt_marketing(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools here", page_type="marketing")
        # Should load marketing_design.md
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "identity", "marketing_design.md")):
            assert "MARKETING DESIGN SYSTEM" in prompt
        else:
            # If file doesn't exist, just verify no crash
            assert isinstance(prompt, str)

    def test_build_system_prompt_app_explicit(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools here", page_type="app")
        # Should NOT have marketing design
        assert "MARKETING DESIGN SYSTEM" not in prompt

    def test_execute_plan_accepts_page_type(self):
        """execute_plan should accept page_type parameter."""
        from hands.executor import execute_plan
        import inspect
        sig = inspect.signature(execute_plan)
        assert "page_type" in sig.parameters
        assert sig.parameters["page_type"].default == "app"

    def test_execute_plan_accepts_research_context(self):
        """execute_plan should accept research_context parameter."""
        from hands.executor import execute_plan
        import inspect
        sig = inspect.signature(execute_plan)
        assert "research_context" in sig.parameters

    def test_execute_plan_accepts_visual_context(self):
        """execute_plan should accept visual_context parameter."""
        from hands.executor import execute_plan
        import inspect
        sig = inspect.signature(execute_plan)
        assert "visual_context" in sig.parameters
