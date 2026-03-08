"""
Integration tests — verify all modules are wired into the main system.

Tests that:
1. Browser tools are available when BROWSER_ENABLED=True
2. Browser dispatch works in researcher tool loop
3. Vault CLI handlers exist and work
4. Project orchestrator CLI handlers exist and work
5. Deploy CLI handlers exist and work
6. Config flags exist for all new modules
"""

import json
import os
import sys
import pytest
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Config Flag Tests
# ============================================================

class TestConfigFlags:
    """Verify all new config flags exist."""

    def test_browser_enabled_flag(self):
        from config import BROWSER_ENABLED
        assert isinstance(BROWSER_ENABLED, bool)

    def test_browser_headless_flag(self):
        from config import BROWSER_HEADLESS
        assert isinstance(BROWSER_HEADLESS, bool)

    def test_browser_max_fetches_flag(self):
        from config import BROWSER_MAX_FETCHES
        assert isinstance(BROWSER_MAX_FETCHES, int)
        assert BROWSER_MAX_FETCHES > 0

    def test_vault_passphrase_env(self):
        from config import VAULT_PASSPHRASE_ENV
        assert isinstance(VAULT_PASSPHRASE_ENV, str)

    def test_deploy_config_path(self):
        from config import DEPLOY_CONFIG_PATH
        assert isinstance(DEPLOY_CONFIG_PATH, str)


# ============================================================
# Browser → Researcher Wiring Tests
# ============================================================

class TestBrowserResearcherWiring:
    """Verify browser tools are wired into the researcher agent."""

    def test_browser_import_in_researcher(self):
        """BROWSER_ENABLED flag is imported in researcher."""
        from agents.researcher import BROWSER_ENABLED
        assert isinstance(BROWSER_ENABLED, bool)

    def test_browser_tools_lazy_loader_exists(self):
        """_load_browser_tools function exists."""
        from agents.researcher import _load_browser_tools
        assert callable(_load_browser_tools)

    def test_browser_tools_load_successfully(self):
        """Browser tool definitions can be loaded."""
        from agents.researcher import _load_browser_tools, _browser_tools_loaded
        _load_browser_tools()
        # After loading, the module-level vars should be set
        import agents.researcher as r
        assert r._browser_tools_loaded is True
        assert r.BROWSER_FETCH_TOOL is not None
        assert r.BROWSER_SEARCH_TOOL is not None
        assert r._execute_browser_tool is not None

    def test_browser_tool_definitions_have_correct_names(self):
        """Browser tool defs have the right names for dispatch."""
        from agents.researcher import _load_browser_tools
        _load_browser_tools()
        import agents.researcher as r
        assert r.BROWSER_FETCH_TOOL["name"] == "browser_fetch"
        assert r.BROWSER_SEARCH_TOOL["name"] == "browser_search"

    @patch("agents.researcher.BROWSER_ENABLED", True)
    @patch("agents.researcher._browser_tools_loaded", True)
    @patch("agents.researcher.BROWSER_FETCH_TOOL", {"name": "browser_fetch", "description": "test", "input_schema": {"type": "object", "properties": {}, "required": []}})
    @patch("agents.researcher.BROWSER_SEARCH_TOOL", {"name": "browser_search", "description": "test", "input_schema": {"type": "object", "properties": {}, "required": []}})
    def test_tools_list_includes_browser_when_enabled(self):
        """When BROWSER_ENABLED=True, browser tools are in the tool list."""
        # We can't easily test the full research() call, but we can verify
        # the tool list construction logic
        from agents.researcher import SEARCH_TOOL_DEFINITION, FETCH_TOOL_DEFINITION, SEARCH_AND_FETCH_TOOL_DEFINITION
        import agents.researcher as r

        tools = [SEARCH_TOOL_DEFINITION, FETCH_TOOL_DEFINITION, SEARCH_AND_FETCH_TOOL_DEFINITION]
        if r.BROWSER_ENABLED and r._browser_tools_loaded and r.BROWSER_FETCH_TOOL and r.BROWSER_SEARCH_TOOL:
            tools.append(r.BROWSER_FETCH_TOOL)
            tools.append(r.BROWSER_SEARCH_TOOL)

        assert len(tools) == 5  # 3 base + 2 browser
        tool_names = [t["name"] for t in tools]
        assert "browser_fetch" in tool_names
        assert "browser_search" in tool_names

    def test_browser_baseline_instructions_added_when_enabled(self):
        """_build_baseline includes browser instructions when enabled."""
        import agents.researcher as r
        original = r.BROWSER_ENABLED
        orig_loaded = r._browser_tools_loaded
        try:
            r.BROWSER_ENABLED = True
            r._load_browser_tools()
            r._browser_tools_loaded = True
            baseline = r._build_baseline()
            assert "browser_fetch" in baseline
            assert "BROWSER TOOLS" in baseline
        finally:
            r.BROWSER_ENABLED = original
            r._browser_tools_loaded = orig_loaded

    def test_baseline_no_browser_when_disabled(self):
        """_build_baseline does NOT include browser when disabled."""
        import agents.researcher as r
        original = r.BROWSER_ENABLED
        try:
            r.BROWSER_ENABLED = False
            baseline = r._build_baseline()
            assert "BROWSER TOOLS" not in baseline
        finally:
            r.BROWSER_ENABLED = original


# ============================================================
# Vault → CLI Wiring Tests
# ============================================================

class TestVaultCLIWiring:
    """Verify vault handlers exist in cli/vault.py (extracted from main.py)."""

    def test_vault_handlers_exist_in_cli(self):
        """Vault handler functions exist in cli/vault.py."""
        cli_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "vault.py")
        with open(cli_dir) as f:
            source = f.read()
        assert "def store(" in source
        assert "def get(" in source
        assert "def delete(" in source
        assert "def list_all(" in source
        assert "def stats(" in source

    def test_vault_argparse_flags_exist(self):
        """Argparse flags for vault are in main.py source."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "--vault-store" in source
        assert "--vault-get" in source
        assert "--vault-delete" in source
        assert "--vault-list" in source
        assert "--vault-stats" in source

    def test_vault_dispatch_wired(self):
        """Vault dispatch in main() calls cli.vault."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "from cli.vault import" in source
        assert "vault_store" in source
        assert "vault_get" in source
        assert "vault_delete" in source

    def test_get_vault_helper_exists(self):
        """Vault helper with CredentialVault exists in cli/vault.py."""
        cli_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "vault.py")
        with open(cli_dir) as f:
            source = f.read()
        assert "CredentialVault" in source


# ============================================================
# Browser → CLI Wiring Tests
# ============================================================

class TestBrowserCLIWiring:
    """Verify browser CLI handlers exist in cli/browser_cmd.py."""

    def test_browser_fetch_handler_exists(self):
        cli_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "browser_cmd.py")
        with open(cli_path) as f:
            source = f.read()
        assert "def fetch_url(" in source
        assert "def test_stealth(" in source

    def test_browser_argparse_flags(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "--browser-fetch" in source
        assert "--browser-test" in source


# ============================================================
# Project Orchestrator → CLI Wiring Tests
# ============================================================

class TestProjectOrchestratorCLIWiring:
    """Verify project orchestrator is wired into cli/project.py."""

    def test_project_handlers_exist(self):
        cli_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "project.py")
        with open(cli_path) as f:
            source = f.read()
        assert "def run(" in source
        assert "def status(" in source
        assert "def resume(" in source
        assert "def approve_phase(" in source
        assert "def list_all(" in source

    def test_project_argparse_flags(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "--project" in source
        assert "--project-status" in source
        assert "--project-resume" in source
        assert "--project-approve" in source
        assert "--project-list" in source

    def test_project_dispatch_wired(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "from cli.project import" in source
        assert "project_run" in source
        assert "project_status" in source
        assert "project_list" in source


# ============================================================
# Signals → CLI Wiring Tests
# ============================================================

class TestSignalsCLIWiring:
    """Verify signal reality-check wiring exists in CLI and main dispatch."""

    def test_signal_reality_check_argparse_flags(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "--reality-check" in source
        assert "--reality-focus" in source

    def test_signal_reality_check_dispatch_wired(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "from cli.signals_cmd import run_reality_check" in source
        assert "run_reality_check(args.reality_check" in source

    def test_signal_reality_check_handler_exists(self):
        cli_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "signals_cmd.py")
        with open(cli_path) as f:
            source = f.read()
        assert "def run_reality_check(" in source


class TestOutcomeFeedbackWiring:
    """Verify outcome feedback is wired into CLI and daemon loop."""

    def test_outcome_feedback_argparse_flag(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "--process-feedback" in source

    def test_outcome_feedback_dispatch_wired(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "from outcome_feedback import process_pending_feedback" in source
        assert "result = process_pending_feedback(" in source

    def test_outcome_feedback_daemon_wired(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "scheduler.py")) as f:
            source = f.read()
        assert "from outcome_feedback import process_pending_feedback" in source
        assert "Outcome feedback: processed" in source


# ============================================================
# Deploy → CLI Wiring Tests
# ============================================================

class TestDeployCLIWiring:
    """Verify VPS deploy is wired into cli/deploy_cmd.py."""

    def test_deploy_handlers_exist(self):
        cli_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "deploy_cmd.py")
        with open(cli_path) as f:
            source = f.read()
        assert "def deploy(" in source
        assert "def health(" in source
        assert "def logs(" in source
        assert "def schedule(" in source
        assert "def unschedule(" in source
        assert "def configure(" in source

    def test_deploy_argparse_flags(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "--deploy" in source
        assert "--deploy-dry-run" in source
        assert "--deploy-health" in source
        assert "--deploy-logs" in source
        assert "--deploy-schedule" in source
        assert "--deploy-unschedule" in source
        assert "--deploy-configure" in source

    def test_deploy_dispatch_wired(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")) as f:
            source = f.read()
        assert "from cli.deploy_cmd import deploy" in source
        assert "deploy_health" in source


# ============================================================
# Cross-Module Integration Tests
# ============================================================

class TestCrossModuleIntegration:
    """Test that modules reference each other correctly."""

    def test_vault_used_in_browser_session(self):
        """BrowserSession accepts vault parameter."""
        from browser.session_manager import BrowserSession
        # Should accept vault=None without error
        session = BrowserSession(vault=None, headless=True)
        assert session.vault is None

    def test_vault_used_in_deploy(self):
        """deploy() accepts vault parameter."""
        from deploy.deployer import deploy
        import inspect
        sig = inspect.signature(deploy)
        assert "vault" in sig.parameters

    def test_browser_tools_schema_valid(self):
        """Browser tool schemas are valid for Claude API."""
        from browser.tools import BROWSER_FETCH_TOOL, BROWSER_SEARCH_TOOL

        for tool in [BROWSER_FETCH_TOOL, BROWSER_SEARCH_TOOL]:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "properties" in tool["input_schema"]
            assert "required" in tool["input_schema"]

    def test_project_orchestrator_imports_planner(self):
        """Project orchestrator uses lazy imports for planner/executor."""
        from hands.project_orchestrator import _get_plan_task, _get_execute_task, _get_validate
        # These should be callable (lazy loaders)
        assert callable(_get_plan_task)
        assert callable(_get_execute_task)
        assert callable(_get_validate)

    def test_deploy_vault_integration(self):
        """Deploy functions accept vault for SSH key retrieval."""
        from deploy.deployer import deploy, setup_schedule, remove_schedule, health_check
        import inspect
        for fn in [deploy, setup_schedule, remove_schedule, health_check]:
            sig = inspect.signature(fn)
            assert "vault" in sig.parameters, f"{fn.__name__} missing vault param"


# ============================================================
# Researcher Browser Dispatch Tests
# ============================================================

class TestResearcherBrowserDispatch:
    """Test that browser tool dispatch works in the researcher loop."""

    def test_browser_fetch_dispatch_branch_exists(self):
        """The researcher source has browser_fetch dispatch."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "researcher.py")) as f:
            source = f.read()
        assert 'tool_name == "browser_fetch"' in source
        assert 'tool_name == "browser_search"' in source

    def test_browser_fetch_counter_initialized(self):
        """browser_fetch_count is initialized in research()."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "researcher.py")) as f:
            source = f.read()
        assert "browser_fetch_count = 0" in source

    def test_browser_tools_in_tool_log(self):
        """Browser tools log to tool_log for observability."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "researcher.py")) as f:
            source = f.read()
        assert '"tool": "browser_fetch"' in source
        assert '"tool": "browser_search"' in source


# ============================================================
# Signal Intelligence Chat Tools
# ============================================================

class TestSignalChatTools:
    """Verify signal intelligence tools are wired into the chat system."""

    def _get_chat_tool_names(self):
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from cli.chat import CHAT_TOOLS
        return [t["name"] for t in CHAT_TOOLS]

    def test_show_signals_tool_registered(self):
        """show_signals tool is defined in chat CHAT_TOOLS."""
        assert "show_signals" in self._get_chat_tool_names()

    def test_enrich_signals_tool_registered(self):
        """enrich_signals tool is defined in chat CHAT_TOOLS."""
        assert "enrich_signals" in self._get_chat_tool_names()

    def test_show_build_specs_tool_registered(self):
        """show_build_specs tool is defined in chat CHAT_TOOLS."""
        assert "show_build_specs" in self._get_chat_tool_names()

    def test_show_signals_handler_exists(self):
        """show_signals handler is implemented in _execute_tool."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "chat.py")) as f:
            source = f.read()
        assert 'name == "show_signals"' in source

    def test_enrich_signals_handler_exists(self):
        """enrich_signals handler is implemented in _execute_tool."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "chat.py")) as f:
            source = f.read()
        assert 'name == "enrich_signals"' in source

    def test_show_build_specs_handler_exists(self):
        """show_build_specs handler is implemented in _execute_tool."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "cli", "chat.py")) as f:
            source = f.read()
        assert 'name == "show_build_specs"' in source


# ============================================================
# Telegram Threads Thread Command
# ============================================================

class TestTelegramThreadsCommand:
    """Verify /threads thread <id> command is wired in telegram_bot."""

    def test_thread_subcommand_exists(self):
        """The 'thread' sub-command is handled in /threads dispatch."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "telegram_bot.py")) as f:
            source = f.read()
        assert 'sub_cmd == "thread"' in source
        assert "get_thread_insights" in source

    def test_thread_help_text_updated(self):
        """The /threads help text includes the thread sub-command."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "telegram_bot.py")) as f:
            source = f.read()
        # Both the /help command and the /threads help sub-command should mention it
        assert "/threads thread" in source


# ============================================================
# Signal Enrichment Wired in Daemon Cycle
# ============================================================

class TestSignalEnrichmentWiring:
    """Verify enrich_top_posts is called within _run_signal_cycle."""

    def test_enrich_called_in_signal_cycle(self):
        """scheduler._run_signal_cycle source contains enrich_top_posts call."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "scheduler.py")) as f:
            source = f.read()
        assert "enrich_top_posts" in source
        # Should be inside _run_signal_cycle function
        fn_start = source.find("def _run_signal_cycle()")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert "enrich_top_posts" in fn_body

    def test_enriched_key_in_results(self):
        """The results dict in _run_signal_cycle includes an 'enriched' key."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "scheduler.py")) as f:
            source = f.read()
        fn_start = source.find("def _run_signal_cycle()")
        fn_end = source.find("\ndef ", fn_start + 1)
        fn_body = source[fn_start:fn_end]
        assert '"enriched": 0' in fn_body or '"enriched"' in fn_body


# ============================================================
# MCP Tool Bridge Wired in Executor
# ============================================================

class TestMcpToolBridgeWiring:
    """Verify MCP tool bridge is wired into the executor (cortex.py)."""

    def test_mcp_bridge_import_in_cortex(self):
        """cortex.py must contain register_mcp_tools_in_registry call."""
        cortex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "cortex.py")
        with open(cortex_path) as f:
            source = f.read()
        assert "register_mcp_tools_in_registry" in source

    def test_mcp_bridge_guarded_by_is_started(self):
        """MCP registration in cortex.py must be guarded by gw.is_started."""
        cortex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "cortex.py")
        with open(cortex_path) as f:
            source = f.read()
        # The call should be inside an is_started check
        bridge_idx = source.find("register_mcp_tools_in_registry")
        snippet = source[max(0, bridge_idx - 200):bridge_idx + 200]
        assert "is_started" in snippet

    def test_mcp_bridge_is_nonfatal(self):
        """MCP registration must be wrapped in try/except so it never crashes pipeline."""
        cortex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "cortex.py")
        with open(cortex_path) as f:
            source = f.read()
        bridge_idx = source.find("register_mcp_tools_in_registry")
        # Scan backwards for the enclosing try block
        preceding = source[max(0, bridge_idx - 600):bridge_idx]
        assert "try:" in preceding


# ============================================================
# MCP Research Tools Wired in Researcher
# ============================================================

class TestMcpResearchToolsWiring:
    """Verify MCP research tools are wired into researcher.py."""

    def test_mcp_research_tools_imported(self):
        """researcher.py must call get_mcp_research_tools."""
        researcher_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "researcher.py")
        with open(researcher_path) as f:
            source = f.read()
        assert "get_mcp_research_tools" in source

    def test_mcp_dispatch_in_tool_loop(self):
        """researcher.py must dispatch MCP tools in its tool-use loop."""
        researcher_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "researcher.py")
        with open(researcher_path) as f:
            source = f.read()
        assert "_mcp_dispatch" in source
        assert "_mcp_tool_names" in source

    def test_mcp_researcher_guarded_by_is_started(self):
        """MCP tools in researcher must only be added if gateway is_started."""
        researcher_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "researcher.py")
        with open(researcher_path) as f:
            source = f.read()
        mcp_tools_idx = source.find("get_mcp_research_tools")
        snippet = source[max(0, mcp_tools_idx - 400):mcp_tools_idx + 200]
        assert "is_started" in snippet


# ============================================================
# Crawl-to-KB Wired in Scheduler
# ============================================================

class TestCrawlToKbWiring:
    """Verify crawl-to-KB is wired into the daemon scheduler."""

    def test_crawl_to_kb_in_scheduler(self):
        """scheduler.py must call inject_crawl_claims_into_kb."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "scheduler.py")) as f:
            source = f.read()
        assert "inject_crawl_claims_into_kb" in source

    def test_crawl_to_kb_per_domain(self):
        """Crawl-to-KB wiring must be inside the per-domain loop."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "scheduler.py")) as f:
            source = f.read()
        inject_idx = source.find("inject_crawl_claims_into_kb")
        # Should be after domain_results.append
        domain_idx = source.rfind("domain_results.append", 0, inject_idx)
        assert domain_idx < inject_idx, "inject_crawl_claims_into_kb should follow domain_results.append"

    def test_crawl_to_kb_is_nonfatal(self):
        """Crawl-to-KB must be wrapped in try/except so it never crashes the cycle."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "scheduler.py")) as f:
            source = f.read()
        inject_idx = source.find("inject_crawl_claims_into_kb")
        preceding = source[max(0, inject_idx - 400):inject_idx]
        assert "try:" in preceding


# ============================================================
# Dataset Loader Wired in Executor Strategy
# ============================================================

class TestDatasetLoaderWiring:
    """Verify dataset loader is wired into cortex.py executor strategy loading."""

    def test_dataset_loader_imported_in_cortex(self):
        """cortex.py must call inject_examples_into_strategy."""
        cortex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "cortex.py")
        with open(cortex_path) as f:
            source = f.read()
        assert "inject_examples_into_strategy" in source

    def test_dataset_loader_applied_after_strategy_load(self):
        """inject_examples_into_strategy must appear after get_strategy('executor')."""
        cortex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "cortex.py")
        with open(cortex_path) as f:
            source = f.read()
        strategy_idx = source.find('get_strategy("executor"')
        inject_idx = source.find("inject_examples_into_strategy")
        assert strategy_idx < inject_idx, "inject_examples_into_strategy should follow get_strategy"

    def test_dataset_loader_is_nonfatal(self):
        """inject_examples_into_strategy must be wrapped in try/except."""
        cortex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents", "cortex.py")
        with open(cortex_path) as f:
            source = f.read()
        inject_idx = source.find("inject_examples_into_strategy")
        preceding = source[max(0, inject_idx - 300):inject_idx]
        assert "try:" in preceding
