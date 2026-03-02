"""
Tests for the Cortex Orchestrator — agents/cortex.py

Covers:
  - System state gathering (Brain, Hands, Infrastructure)
  - query_orchestrator with mocked LLM
  - plan_next_actions
  - coordinate_brain_to_hands
  - assess_system
  - interpret_findings
  - format_orchestrator_response
  - Error handling and edge cases
  - Config integration (MODELS has cortex_orchestrator)
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_memory(tmp_path, monkeypatch):
    """Set up temporary dirs for Brain memory."""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    strat_dir = tmp_path / "strategies"
    strat_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    exec_dir = tmp_path / "exec_memory"
    exec_dir.mkdir()
    proj_dir = tmp_path / "projects"
    proj_dir.mkdir()

    monkeypatch.setattr("config.MEMORY_DIR", str(mem_dir))
    monkeypatch.setattr("config.STRATEGY_DIR", str(strat_dir))
    monkeypatch.setattr("config.LOG_DIR", str(log_dir))
    monkeypatch.setattr("config.EXEC_MEMORY_DIR", str(exec_dir))

    return tmp_path


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response with proper structure."""
    def _make(text: str, input_tokens: int = 500, output_tokens: int = 300):
        mock_resp = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = text
        mock_resp.content = [mock_block]
        mock_resp.stop_reason = "end_turn"
        mock_resp.usage = MagicMock()
        mock_resp.usage.input_tokens = input_tokens
        mock_resp.usage.output_tokens = output_tokens
        return mock_resp
    return _make


SAMPLE_ORCHESTRATOR_RESPONSE = json.dumps({
    "interpretation": "The system is making progress in productized-services.",
    "key_insights": [
        "Employer pain points are well-researched",
        "Ghosting rates decreased but still high",
    ],
    "recommended_actions": [
        {
            "type": "hands_build",
            "priority": "high",
            "description": "Build a landing page targeting OLJ employers",
            "rationale": "Research shows high demand for reliable services",
            "domain": "productized-services",
        }
    ],
    "risks": ["No revenue generated yet"],
    "system_health": "healthy",
    "next_question": "What pricing model would convert best?",
})


# ── Config Integration ───────────────────────────────────────────────────

class TestCortexConfig:
    """Verify cortex_orchestrator is in the MODELS config."""

    def test_model_in_config(self):
        from config import MODELS
        assert "cortex_orchestrator" in MODELS
        assert "sonnet" in MODELS["cortex_orchestrator"].lower() or "claude" in MODELS["cortex_orchestrator"].lower()

    def test_orchestrator_model_matches_config(self):
        from agents.cortex import ORCHESTRATOR_MODEL
        from config import MODELS
        assert ORCHESTRATOR_MODEL == MODELS["cortex_orchestrator"]


# ── State Gathering ──────────────────────────────────────────────────────

class TestGatherBrainState:
    """Test _gather_brain_state collects Brain subsystem data."""

    def test_empty_brain_state(self, tmp_memory):
        from agents.cortex import _gather_brain_state
        state = _gather_brain_state()
        assert "goals" in state
        assert "domains" in state
        assert isinstance(state["domains"], list)

    def test_brain_state_with_domain_filter(self, tmp_memory):
        from agents.cortex import _gather_brain_state
        state = _gather_brain_state(domain="nonexistent-domain")
        assert isinstance(state["domains"], list)

    def test_brain_state_structure(self, tmp_memory):
        """Verify domain data structure when domains exist."""
        from agents.cortex import _gather_brain_state

        # Mock domain_comparison to return a domain
        mock_comparison = [{"domain": "test-domain", "count": 5, "avg_score": 7.0, "accepted": 3}]
        mock_stats = {"count": 5, "accepted": 3, "rejected": 2, "avg_score": 7.0}
        mock_traj = {"trend": "improving", "improvement": 1.5, "total_outputs": 5}

        with patch("analytics.domain_comparison", return_value=mock_comparison), \
             patch("memory_store.get_stats", return_value=mock_stats), \
             patch("analytics.score_trajectory", return_value=mock_traj), \
             patch("domain_goals.get_goal", return_value="Test goal"), \
             patch("memory_store.load_knowledge_base", return_value=None), \
             patch("strategy_store.get_active_version", return_value="v001"), \
             patch("strategy_store.get_strategy_status", return_value="active"), \
             patch("strategy_store.list_pending", return_value=[]), \
             patch("memory_store.load_outputs", return_value=[]):
            state = _gather_brain_state()

        assert len(state["domains"]) == 1
        d = state["domains"][0]
        assert d["name"] == "test-domain"
        assert d["stats"]["count"] == 5
        assert d["trajectory"]["trend"] == "improving"
        assert d["strategy"]["version"] == "v001"


class TestGatherHandsState:
    """Test _gather_hands_state collects Hands subsystem data."""

    def test_empty_hands_state(self, tmp_memory):
        from agents.cortex import _gather_hands_state
        # Patch the exec_memory and projects paths
        with patch("agents.cortex.os.path.dirname") as mock_dir:
            mock_dir.return_value = str(tmp_memory)
            state = _gather_hands_state()
        assert "execution_domains" in state
        assert "projects" in state

    def test_hands_state_with_exec_data(self, tmp_memory):
        from agents.cortex import _gather_hands_state

        # Create exec memory data at temp path
        exec_dir = tmp_memory / "exec_memory" / "test-domain"
        exec_dir.mkdir(parents=True, exist_ok=True)
        task = {
            "goal": "Build a landing page",
            "status": "completed",
            "overall_score": 8.0,
            "accepted": True,
        }
        with open(str(exec_dir / "task_001.json"), "w") as f:
            json.dump(task, f)

        # Also create empty projects dir
        (tmp_memory / "projects").mkdir(exist_ok=True)

        # Patch __file__ equivalent by patching os.path.join for known paths
        real_join = os.path.join
        def patched_join(*args):
            joined = real_join(*args)
            if "exec_memory" in joined and "agents" in joined:
                return str(tmp_memory / "exec_memory")
            if "projects" in joined and "agents" in joined:
                return str(tmp_memory / "projects")
            return joined

        with patch("agents.cortex.os.path.join", side_effect=patched_join):
            state = _gather_hands_state()

        assert len(state["execution_domains"]) == 1
        assert state["execution_domains"][0]["domain"] == "test-domain"
        assert state["execution_domains"][0]["task_count"] == 1

    def test_hands_state_with_projects(self, tmp_memory):
        from agents.cortex import _gather_hands_state

        # Create project data
        proj_dir = tmp_memory / "projects"
        proj_dir.mkdir(exist_ok=True)
        (tmp_memory / "exec_memory").mkdir(exist_ok=True)
        project = {
            "id": "proj_001",
            "name": "Landing page project",
            "status": "in_progress",
            "phases": [
                {"name": "setup", "status": "completed"},
                {"name": "build", "status": "in_progress"},
            ],
        }
        with open(str(proj_dir / "proj_001.json"), "w") as f:
            json.dump(project, f)

        real_join = os.path.join
        def patched_join(*args):
            joined = real_join(*args)
            if "exec_memory" in joined and "agents" in joined:
                return str(tmp_memory / "exec_memory")
            if "projects" in joined and "agents" in joined:
                return str(tmp_memory / "projects")
            return joined

        with patch("agents.cortex.os.path.join", side_effect=patched_join):
            state = _gather_hands_state()

        assert len(state["projects"]) == 1
        assert state["projects"][0]["id"] == "proj_001"
        assert state["projects"][0]["completed_phases"] == 1


class TestGatherInfraState:
    """Test _gather_infra_state collects infrastructure data."""

    def test_infra_state_structure(self):
        from agents.cortex import _gather_infra_state
        # Patch at source modules since imports are lazy (inside function body)
        with patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0.5}), \
             patch("cost_tracker.check_budget", return_value={"remaining": 1.5, "within_budget": True}), \
             patch("cost_tracker.check_balance", return_value={"remaining": 10.0}):
            state = _gather_infra_state()

        assert "budget" in state
        assert state["budget"]["spent_today"] == 0.5

    def test_infra_state_budget_error(self):
        from agents.cortex import _gather_infra_state
        with patch("cost_tracker.get_daily_spend", side_effect=Exception("DB error")):
            state = _gather_infra_state()
        assert "error" in state.get("budget", {})

    def test_infra_state_watchdog(self):
        from agents.cortex import _gather_infra_state
        mock_wd = {"state": "running", "cycles_completed": 5, "consecutive_failures": 0}
        with patch("cost_tracker.get_daily_spend", return_value={"total_usd": 0}), \
             patch("cost_tracker.check_budget", return_value={"remaining": 2, "within_budget": True}), \
             patch("cost_tracker.check_balance", return_value={"remaining": 10}), \
             patch("watchdog.get_watchdog_status", return_value=mock_wd):
            state = _gather_infra_state()
        assert state["watchdog"]["state"] == "running"


class TestGatherFullState:
    """Test the unified state gathering."""

    def test_full_state_has_all_sections(self, tmp_memory):
        from agents.cortex import gather_full_state
        with patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            state = gather_full_state()
        assert "timestamp" in state
        assert "brain" in state
        assert "hands" in state
        assert "infrastructure" in state


# ── Truncation ───────────────────────────────────────────────────────────

class TestTruncation:
    """Test state truncation for cost control."""

    def test_small_state_not_truncated(self):
        from agents.cortex import _truncate_state
        state = {"key": "value"}
        result = _truncate_state(state, max_chars=1000)
        assert "truncated" not in result

    def test_large_state_gets_truncated(self):
        from agents.cortex import _truncate_state
        state = {"key": "x" * 20000}
        result = _truncate_state(state, max_chars=5000)
        assert "truncated" in result
        assert len(result) <= 5100  # 5000 + truncation message


# ── Query Orchestrator ───────────────────────────────────────────────────

class TestQueryOrchestrator:
    """Test the main query_orchestrator function."""

    def test_successful_query(self, tmp_memory, mock_llm_response):
        from agents.cortex import query_orchestrator

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = query_orchestrator("What should we do next?")

        assert result["interpretation"] is not None
        assert "key_insights" in result
        assert "recommended_actions" in result
        assert result["system_health"] == "healthy"

    def test_query_with_domain_filter(self, tmp_memory, mock_llm_response):
        from agents.cortex import query_orchestrator

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = query_orchestrator(
                "Focus on this domain",
                domain="productized-services",
            )

        assert "error" not in result or result.get("interpretation")

    def test_query_with_extra_context(self, tmp_memory, mock_llm_response):
        from agents.cortex import query_orchestrator

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp) as mock_call, \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = query_orchestrator(
                "What next?",
                extra_context="User is focused on revenue generation",
            )

        # Verify extra context was included in the LLM call
        call_args = mock_call.call_args
        user_msg = call_args.kwargs.get("messages", call_args[1]["messages"]
                                        if len(call_args[1]) > 1 else
                                        call_args.kwargs["messages"])[0]["content"]
        assert "revenue generation" in user_msg

    def test_query_handles_llm_error(self, tmp_memory):
        from agents.cortex import query_orchestrator

        with patch("agents.cortex.call_llm", side_effect=Exception("API down")), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = query_orchestrator("Test question")

        assert "error" in result
        assert "API down" in result["error"]

    def test_query_handles_non_json_response(self, tmp_memory, mock_llm_response):
        from agents.cortex import query_orchestrator

        mock_resp = mock_llm_response("This is a plain text response without JSON.")

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = query_orchestrator("Test question")

        # Should fallback to raw text interpretation
        assert result.get("_raw") is True or result.get("interpretation")

    def test_query_selective_state(self, tmp_memory, mock_llm_response):
        """Test include_brain/include_hands/include_infra flags."""
        from agents.cortex import query_orchestrator

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp) as mock_call, \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_brain_state") as mock_brain, \
             patch("agents.cortex._gather_hands_state") as mock_hands, \
             patch("agents.cortex._gather_infra_state") as mock_infra:
            mock_brain.return_value = {}
            mock_hands.return_value = {}
            mock_infra.return_value = {}

            query_orchestrator(
                "Test",
                include_brain=True,
                include_hands=False,
                include_infra=False,
            )

        mock_brain.assert_called_once()
        mock_hands.assert_not_called()
        mock_infra.assert_not_called()

    def test_query_logs_cost(self, tmp_memory, mock_llm_response):
        from agents.cortex import query_orchestrator

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost") as mock_log, \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            query_orchestrator("Test", domain="test-domain")

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs.kwargs.get("agent_role") == "cortex_orchestrator" or \
               "cortex_orchestrator" in str(call_kwargs)


# ── Convenience Functions ────────────────────────────────────────────────

class TestPlanNextActions:
    """Test plan_next_actions."""

    def test_plan_calls_query(self, tmp_memory, mock_llm_response):
        from agents.cortex import plan_next_actions

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = plan_next_actions()

        assert "recommended_actions" in result

    def test_plan_with_domain(self, tmp_memory, mock_llm_response):
        from agents.cortex import plan_next_actions

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp) as mock_call, \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            plan_next_actions(domain="crypto")

        # Verify domain is mentioned in the question
        call_args = mock_call.call_args
        msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", [])
        user_msg = msgs[0]["content"] if msgs else ""
        assert "crypto" in user_msg


class TestCoordinateBrainToHands:
    """Test coordinate_brain_to_hands."""

    def test_coordinate_calls_query(self, tmp_memory, mock_llm_response):
        from agents.cortex import coordinate_brain_to_hands

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = coordinate_brain_to_hands("productized-services")

        assert "recommended_actions" in result


class TestAssessSystem:
    """Test assess_system."""

    def test_assess_calls_query(self, tmp_memory, mock_llm_response):
        from agents.cortex import assess_system

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_infra_state", return_value={"budget": {}}):
            result = assess_system()

        assert "system_health" in result


class TestInterpretFindings:
    """Test interpret_findings."""

    def test_interpret_no_hands_or_infra(self, tmp_memory, mock_llm_response):
        from agents.cortex import interpret_findings

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp), \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_brain_state") as mock_brain, \
             patch("agents.cortex._gather_hands_state") as mock_hands, \
             patch("agents.cortex._gather_infra_state") as mock_infra:
            mock_brain.return_value = {}
            interpret_findings("productized-services")

        # interpret_findings should NOT gather hands or infra
        mock_hands.assert_not_called()
        mock_infra.assert_not_called()

    def test_interpret_with_focus(self, tmp_memory, mock_llm_response):
        from agents.cortex import interpret_findings

        mock_resp = mock_llm_response(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.call_llm", return_value=mock_resp) as mock_call, \
             patch("agents.cortex.log_cost"), \
             patch("agents.cortex._gather_brain_state", return_value={}):
            interpret_findings("crypto", question="pricing models")

        call_args = mock_call.call_args
        msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", [])
        user_msg = msgs[0]["content"] if msgs else ""
        assert "pricing models" in user_msg


# ── Response Formatting ──────────────────────────────────────────────────

class TestFormatOrchestratorResponse:
    """Test format_orchestrator_response."""

    def test_format_full_response(self):
        from agents.cortex import format_orchestrator_response
        result = json.loads(SAMPLE_ORCHESTRATOR_RESPONSE)
        formatted = format_orchestrator_response(result)

        assert "Analysis" in formatted
        assert "Key Insights" in formatted
        assert "Recommended Actions" in formatted
        assert "Risks" in formatted
        assert "System Health" in formatted
        assert "landing page" in formatted

    def test_format_error_response(self):
        from agents.cortex import format_orchestrator_response
        result = {"error": "API failed", "interpretation": ""}
        formatted = format_orchestrator_response(result)
        assert "error" in formatted.lower() or "Error" in formatted

    def test_format_empty_response(self):
        from agents.cortex import format_orchestrator_response
        result = {}
        formatted = format_orchestrator_response(result)
        assert formatted  # Should return something, not crash

    def test_format_partial_response(self):
        from agents.cortex import format_orchestrator_response
        result = {
            "interpretation": "System needs more research data.",
            "key_insights": [],
            "recommended_actions": [],
            "risks": [],
            "system_health": "warning",
        }
        formatted = format_orchestrator_response(result)
        assert "more research data" in formatted
        assert "Warning" in formatted

    def test_format_priority_icons(self):
        from agents.cortex import format_orchestrator_response
        result = {
            "interpretation": "OK",
            "recommended_actions": [
                {"type": "brain_research", "priority": "critical",
                 "description": "Critical action", "rationale": "Urgent"},
                {"type": "hands_build", "priority": "low",
                 "description": "Low action", "rationale": "Nice to have"},
            ],
        }
        formatted = format_orchestrator_response(result)
        assert "🚨" in formatted  # Critical
        assert "💡" in formatted  # Low
        assert "CRITICAL" in formatted
        assert "LOW" in formatted


# ── Chat Integration ─────────────────────────────────────────────────────

class TestChatToolDefinitions:
    """Verify orchestrator tools are defined in the chat tool list."""

    def test_orchestrator_tools_exist(self):
        from cli.chat import CHAT_TOOLS
        tool_names = [t["name"] for t in CHAT_TOOLS]

        assert "ask_orchestrator" in tool_names
        assert "orchestrator_plan" in tool_names
        assert "orchestrator_interpret" in tool_names
        assert "orchestrator_coordinate" in tool_names
        assert "orchestrator_assess" in tool_names

    def test_ask_orchestrator_schema(self):
        from cli.chat import CHAT_TOOLS
        tool = next(t for t in CHAT_TOOLS if t["name"] == "ask_orchestrator")
        props = tool["input_schema"]["properties"]
        assert "question" in props
        assert "domain" in props
        assert "context" in props

    def test_orchestrator_tools_have_descriptions(self):
        from cli.chat import CHAT_TOOLS
        orchestrator_tools = [
            t for t in CHAT_TOOLS
            if t["name"].startswith("orchestrator_") or t["name"] == "ask_orchestrator"
        ]
        for tool in orchestrator_tools:
            assert tool.get("description"), f"{tool['name']} has no description"
            assert len(tool["description"]) > 20, f"{tool['name']} description too short"


class TestChatToolExecution:
    """Test that chat tool execution routes to cortex correctly."""

    def test_execute_ask_orchestrator(self):
        from cli.chat import _execute_tool
        mock_result = json.loads(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.query_orchestrator", return_value=mock_result):
            result = _execute_tool(
                "ask_orchestrator",
                {"question": "What should we do?"},
                "test-domain",
            )

        assert "Analysis" in result or "progress" in result

    def test_execute_orchestrator_plan(self):
        from cli.chat import _execute_tool
        mock_result = json.loads(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.plan_next_actions", return_value=mock_result):
            result = _execute_tool(
                "orchestrator_plan",
                {},
                "test-domain",
            )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_orchestrator_interpret(self):
        from cli.chat import _execute_tool
        mock_result = json.loads(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.interpret_findings", return_value=mock_result):
            result = _execute_tool(
                "orchestrator_interpret",
                {"domain": "crypto"},
                "test-domain",
            )

        assert isinstance(result, str)

    def test_execute_orchestrator_coordinate(self):
        from cli.chat import _execute_tool
        mock_result = json.loads(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.coordinate_brain_to_hands", return_value=mock_result):
            result = _execute_tool(
                "orchestrator_coordinate",
                {"domain": "productized-services"},
                "test-domain",
            )

        assert isinstance(result, str)

    def test_execute_orchestrator_assess(self):
        from cli.chat import _execute_tool
        mock_result = json.loads(SAMPLE_ORCHESTRATOR_RESPONSE)

        with patch("agents.cortex.assess_system", return_value=mock_result):
            result = _execute_tool(
                "orchestrator_assess",
                {},
                "test-domain",
            )

        assert isinstance(result, str)
        assert "Health" in result

    def test_execute_orchestrator_error_handling(self):
        from cli.chat import _execute_tool

        with patch("agents.cortex.query_orchestrator", side_effect=Exception("Sonnet unavailable")):
            result = _execute_tool(
                "ask_orchestrator",
                {"question": "Test"},
                "test-domain",
            )

        assert "failed" in result.lower()
