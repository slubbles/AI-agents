"""
Tests for MCP (Model Context Protocol) Gateway.

Tests the protocol layer, docker manager, gateway, context router,
and tool bridge without requiring actual Docker containers or MCP servers.
All external dependencies are mocked.
"""

import json
import os
import sys
import threading
import time
from io import BytesIO
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure agent-brain is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.protocol import (
    build_request,
    build_notification,
    parse_response,
    is_error_response,
    get_result,
    build_initialize,
    build_initialized_notification,
    build_tools_list,
    build_tools_call,
    build_ping,
    parse_tool_definition,
    parse_tools_list_result,
    parse_tool_call_result,
    reset_id_counter,
    MCP_PROTOCOL_VERSION,
)
from mcp.docker_manager import McpServerConfig, McpContainer
from mcp.gateway import McpGateway, get_gateway, reset_gateway
from mcp.context_router import ContextRouter, KEYWORD_CATEGORIES
from mcp.tool_bridge import (
    McpProxyTool,
    get_mcp_research_tools,
    get_mcp_tool_names,
    route_mcp_tool_call,
    register_mcp_tools_in_registry,
)


# ============================================================
# Protocol Tests
# ============================================================

class TestProtocol:
    """Tests for JSON-RPC 2.0 message encoding/decoding."""

    def setup_method(self):
        reset_id_counter()

    def test_build_request_basic(self):
        """Build a simple JSON-RPC request."""
        msg = build_request("tools/list")
        parsed = json.loads(msg)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "tools/list"
        assert "id" in parsed
        assert isinstance(parsed["id"], int)

    def test_build_request_with_params(self):
        """Build a request with parameters."""
        msg = build_request("tools/call", {"name": "test", "arguments": {"x": 1}})
        parsed = json.loads(msg)
        assert parsed["params"]["name"] == "test"
        assert parsed["params"]["arguments"]["x"] == 1

    def test_build_request_custom_id(self):
        """Build a request with a custom ID."""
        msg = build_request("ping", req_id=42)
        parsed = json.loads(msg)
        assert parsed["id"] == 42

    def test_build_request_increments_ids(self):
        """Request IDs auto-increment."""
        msg1 = json.loads(build_request("a"))
        msg2 = json.loads(build_request("b"))
        assert msg2["id"] == msg1["id"] + 1

    def test_build_notification(self):
        """Notifications have no id field."""
        msg = build_notification("notifications/initialized")
        parsed = json.loads(msg)
        assert "id" not in parsed
        assert parsed["method"] == "notifications/initialized"

    def test_build_request_newline_terminated(self):
        """Messages are newline-terminated bytes."""
        msg = build_request("test")
        assert isinstance(msg, bytes)
        assert msg.endswith(b"\n")

    def test_parse_response_success(self):
        """Parse a successful response."""
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
        msg = parse_response(data)
        assert msg["id"] == 1
        assert not is_error_response(msg)
        assert get_result(msg) == {"tools": []}

    def test_parse_response_error(self):
        """Parse an error response."""
        data = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32600, "message": "Invalid method"}
        })
        msg = parse_response(data)
        assert is_error_response(msg)
        with pytest.raises(ValueError, match="Invalid method"):
            get_result(msg)

    def test_parse_response_bytes(self):
        """Parse response from bytes."""
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "ok"}).encode("utf-8")
        msg = parse_response(data)
        assert get_result(msg) == "ok"

    def test_parse_response_invalid_json(self):
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_response("not json")

    def test_parse_response_empty(self):
        """Empty response raises ValueError."""
        with pytest.raises(ValueError, match="Empty response"):
            parse_response("")

    def test_parse_response_missing_jsonrpc(self):
        """Missing jsonrpc version raises ValueError."""
        with pytest.raises(ValueError, match="Expected jsonrpc 2.0"):
            parse_response(json.dumps({"id": 1, "result": "ok"}))

    # --- MCP-specific builders ---

    def test_build_initialize(self):
        """Initialize request has correct structure."""
        msg = json.loads(build_initialize())
        assert msg["method"] == "initialize"
        assert msg["params"]["protocolVersion"] == MCP_PROTOCOL_VERSION
        assert msg["params"]["clientInfo"]["name"] == "agent-brain"

    def test_build_initialized_notification(self):
        """Post-init notification has correct method."""
        msg = json.loads(build_initialized_notification())
        assert msg["method"] == "notifications/initialized"
        assert "id" not in msg

    def test_build_tools_list(self):
        """tools/list request."""
        msg = json.loads(build_tools_list())
        assert msg["method"] == "tools/list"

    def test_build_tools_call(self):
        """tools/call request with arguments."""
        msg = json.loads(build_tools_call("read_file", {"path": "/tmp/test.txt"}))
        assert msg["method"] == "tools/call"
        assert msg["params"]["name"] == "read_file"
        assert msg["params"]["arguments"]["path"] == "/tmp/test.txt"

    def test_build_ping(self):
        """Ping request."""
        msg = json.loads(build_ping())
        assert msg["method"] == "ping"

    # --- Response parsers ---

    def test_parse_tool_definition(self):
        """Convert MCP tool def to Claude format."""
        mcp_tool = {
            "name": "read_file",
            "description": "Read a file",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
        claude_tool = parse_tool_definition(mcp_tool)
        assert claude_tool["name"] == "read_file"
        assert claude_tool["input_schema"]["required"] == ["path"]

    def test_parse_tools_list_result_list(self):
        """Parse tools/list when result is a list."""
        result = [
            {"name": "a", "description": "A", "inputSchema": {"type": "object"}},
            {"name": "b", "description": "B", "inputSchema": {"type": "object"}},
        ]
        tools = parse_tools_list_result(result)
        assert len(tools) == 2
        assert tools[0]["name"] == "a"

    def test_parse_tools_list_result_dict(self):
        """Parse tools/list when result is a dict with 'tools' key."""
        result = {
            "tools": [
                {"name": "x", "description": "X", "inputSchema": {"type": "object"}},
            ]
        }
        tools = parse_tools_list_result(result)
        assert len(tools) == 1
        assert tools[0]["name"] == "x"

    def test_parse_tool_call_result_text(self):
        """Parse a text content block."""
        result = {
            "content": [{"type": "text", "text": "Hello world"}],
            "isError": False,
        }
        assert parse_tool_call_result(result) == "Hello world"

    def test_parse_tool_call_result_error(self):
        """Parse an error result."""
        result = {
            "content": [{"type": "text", "text": "File not found"}],
            "isError": True,
        }
        assert "[MCP Error]" in parse_tool_call_result(result)

    def test_parse_tool_call_result_multiple_blocks(self):
        """Parse multiple content blocks."""
        result = {
            "content": [
                {"type": "text", "text": "Line 1"},
                {"type": "text", "text": "Line 2"},
            ],
            "isError": False,
        }
        text = parse_tool_call_result(result)
        assert "Line 1" in text
        assert "Line 2" in text

    def test_parse_tool_call_result_image(self):
        """Image blocks become placeholders."""
        result = {
            "content": [{"type": "image", "mimeType": "image/png"}],
            "isError": False,
        }
        assert "image" in parse_tool_call_result(result).lower()

    def test_parse_tool_call_result_string(self):
        """String result is returned as-is."""
        assert parse_tool_call_result("raw text") == "raw text"


# ============================================================
# Server Config Tests
# ============================================================

class TestServerConfig:
    """Tests for MCP server configuration."""

    def test_default_config(self):
        """Default config has sensible values."""
        cfg = McpServerConfig(name="test", image="test:latest")
        assert cfg.name == "test"
        assert cfg.image == "test:latest"
        assert cfg.enabled is True
        assert cfg.auto_pull is True
        assert cfg.max_restarts == 3
        assert cfg.timeout_seconds == 30.0

    def test_config_with_all_fields(self):
        """Config with all fields specified."""
        cfg = McpServerConfig(
            name="github",
            image="mcp/github:latest",
            command=["--token", "abc"],
            env={"GITHUB_TOKEN": "abc"},
            volumes={"/host": "/container"},
            network="bridge",
            args=["--memory", "512m"],
            enabled=True,
            categories=["git", "github"],
            description="GitHub operations",
        )
        assert cfg.categories == ["git", "github"]
        assert cfg.env["GITHUB_TOKEN"] == "abc"
        assert cfg.volumes["/host"] == "/container"


# ============================================================
# Docker Manager Tests (mocked)
# ============================================================

class TestDockerManager:
    """Tests for McpContainer with mocked Docker subprocess."""

    def _make_container(self, **kwargs) -> McpContainer:
        """Create a container with default config."""
        config = McpServerConfig(
            name=kwargs.get("name", "test"),
            image=kwargs.get("image", "test:latest"),
            env=kwargs.get("env", {}),
            volumes=kwargs.get("volumes", {}),
            categories=kwargs.get("categories", ["test"]),
        )
        return McpContainer(config)

    def test_build_docker_command(self):
        """Docker run command is built correctly."""
        container = self._make_container(
            env={"KEY": "val"},
            volumes={"/host": "/mount"},
        )
        cmd = container._build_docker_command()
        assert "docker" in cmd
        assert "run" in cmd
        assert "-i" in cmd
        assert "--rm" in cmd
        assert "-e" in cmd
        assert "KEY=val" in cmd
        assert "-v" in cmd
        assert "/host:/mount" in cmd
        assert "test:latest" in cmd

    def test_is_running_no_process(self):
        """Not running when no process."""
        container = self._make_container()
        assert not container.is_running

    def test_stop_no_process(self):
        """Stop is safe when no process."""
        container = self._make_container()
        container.stop()  # Should not raise

    @patch("subprocess.run")
    def test_pull_image_exists(self, mock_run):
        """Skip pull if image already exists."""
        mock_run.return_value = MagicMock(returncode=0)
        container = self._make_container()
        container._pull_image()
        # inspect was called
        assert mock_run.called
        args = mock_run.call_args_list[0][0][0]
        assert "inspect" in args or "image" in args

    def test_get_status(self):
        """Status dict has correct structure."""
        container = self._make_container(categories=["git", "code"])
        status = container.get_status()
        assert status["name"] == "test"
        assert status["running"] is False
        assert status["initialized"] is False
        assert status["tools_count"] == 0
        assert status["categories"] == ["git", "code"]


# ============================================================
# Gateway Tests
# ============================================================

class TestGateway:
    """Tests for McpGateway."""

    def setup_method(self):
        reset_gateway()

    def test_add_server(self):
        """Add a server configuration."""
        gw = McpGateway()
        cfg = McpServerConfig(name="test", image="test:latest")
        gw.add_server(cfg)
        assert "test" in gw._containers

    def test_add_duplicate_server_raises(self):
        """Duplicate server names raise ValueError."""
        gw = McpGateway()
        cfg = McpServerConfig(name="test", image="test:latest")
        gw.add_server(cfg)
        with pytest.raises(ValueError, match="already registered"):
            gw.add_server(cfg)

    def test_load_config_missing_file(self):
        """Loading from missing file returns 0."""
        gw = McpGateway()
        count = gw.load_config("/nonexistent/path.json")
        assert count == 0

    def test_load_config_valid(self, tmp_path):
        """Load valid server configurations."""
        config = {
            "servers": {
                "fs": {
                    "image": "mcp/fs:latest",
                    "categories": ["filesystem"],
                    "description": "File system",
                },
                "git": {
                    "image": "mcp/git:latest",
                    "categories": ["git"],
                },
            }
        }
        config_path = str(tmp_path / "mcp_servers.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        gw = McpGateway()
        count = gw.load_config(config_path)
        assert count == 2
        assert "fs" in gw._containers
        assert "git" in gw._containers
        assert gw._containers["fs"].config.categories == ["filesystem"]

    def test_save_config(self, tmp_path):
        """Save server configs to JSON."""
        gw = McpGateway()
        gw.add_server(McpServerConfig(
            name="test", image="test:latest", categories=["code"]
        ))
        config_path = str(tmp_path / "saved.json")
        gw.save_config(config_path)

        with open(config_path) as f:
            saved = json.load(f)
        assert "test" in saved["servers"]
        assert saved["servers"]["test"]["image"] == "test:latest"

    def test_get_all_tools_empty(self):
        """No tools when no servers are running."""
        gw = McpGateway()
        assert gw.get_all_tools() == []

    def test_stop_all_safe(self):
        """Stop all is safe even when empty."""
        gw = McpGateway()
        gw.stop_all()

    def test_get_status(self):
        """Status dict has correct structure."""
        gw = McpGateway()
        gw.add_server(McpServerConfig(name="test", image="test:latest"))
        status = gw.get_status()
        assert status["total_servers"] == 1
        assert status["running_servers"] == 0
        assert "test" in status["servers"]

    def test_call_tool_unknown(self):
        """Calling an unknown tool returns error."""
        gw = McpGateway()
        gw._started = True
        result = gw.call_tool("nonexistent_tool", {})
        assert "[MCP Error]" in result

    def test_prefix_tool(self):
        """Tool names get server prefix."""
        tool = {"name": "read_file", "description": "Read a file"}
        prefixed = McpGateway._prefix_tool("filesystem", tool)
        assert prefixed["name"] == "filesystem__read_file"
        assert "[filesystem]" in prefixed["description"]

    def test_tool_routing(self):
        """Tool calls route to correct server."""
        gw = McpGateway()

        # Create mock containers with tools
        mock_fs = MagicMock()
        mock_fs.is_running = True
        mock_fs.config = McpServerConfig(name="fs", image="fs:latest", categories=["filesystem"])
        mock_fs.tools = [{"name": "read_file", "description": "Read"}]

        mock_git = MagicMock()
        mock_git.is_running = True
        mock_git.config = McpServerConfig(name="git", image="git:latest", categories=["git"])
        mock_git.tools = [{"name": "commit", "description": "Commit"}]

        gw._containers = {"fs": mock_fs, "git": mock_git}
        gw._rebuild_tool_index()

        # Verify tool index
        assert "fs__read_file" in gw._tool_to_server
        assert gw._tool_to_server["fs__read_file"] == "fs"
        assert "git__commit" in gw._tool_to_server
        assert gw._tool_to_server["git__commit"] == "git"

    def test_singleton_gateway(self):
        """Global gateway singleton works."""
        reset_gateway()
        gw1 = get_gateway()
        gw2 = get_gateway()
        assert gw1 is gw2

    def test_reset_gateway(self):
        """Reset creates a fresh gateway."""
        gw1 = get_gateway()
        reset_gateway()
        gw2 = get_gateway()
        assert gw1 is not gw2

    def test_get_tools_by_category(self):
        """Filter tools by server category."""
        gw = McpGateway()

        mock_fs = MagicMock()
        mock_fs.is_running = True
        mock_fs.config = McpServerConfig(name="fs", image="fs:latest", categories=["filesystem"])
        mock_fs.tools = [{"name": "read", "description": "Read a file"}]

        mock_db = MagicMock()
        mock_db.is_running = True
        mock_db.config = McpServerConfig(name="db", image="db:latest", categories=["database"])
        mock_db.tools = [{"name": "query", "description": "Run SQL"}]

        gw._containers = {"fs": mock_fs, "db": mock_db}

        fs_tools = gw.get_tools_by_category("filesystem")
        assert len(fs_tools) == 1
        assert "fs__read" == fs_tools[0]["name"]

        db_tools = gw.get_tools_by_category("database")
        assert len(db_tools) == 1
        assert "db__query" == db_tools[0]["name"]

        empty = gw.get_tools_by_category("nonexistent")
        assert len(empty) == 0


# ============================================================
# Context Router Tests
# ============================================================

class TestContextRouter:
    """Tests for intelligent tool filtering."""

    def _make_gateway_with_tools(self) -> McpGateway:
        """Create a mock gateway with diverse tools."""
        gw = McpGateway()

        # Filesystem server
        mock_fs = MagicMock()
        mock_fs.is_running = True
        mock_fs.config = McpServerConfig(
            name="filesystem", image="fs:latest",
            categories=["filesystem", "code"],
        )
        mock_fs.tools = [
            {"name": "read_file", "description": "Read file contents", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
            {"name": "write_file", "description": "Write file contents", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}},
            {"name": "list_directory", "description": "List directory contents", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
        ]

        # GitHub server
        mock_gh = MagicMock()
        mock_gh.is_running = True
        mock_gh.config = McpServerConfig(
            name="github", image="gh:latest",
            categories=["git", "github"],
        )
        mock_gh.tools = [
            {"name": "create_issue", "description": "Create a GitHub issue", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}}},
            {"name": "list_repos", "description": "List GitHub repositories", "input_schema": {"type": "object", "properties": {}}},
            {"name": "create_pull_request", "description": "Create a pull request", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}}},
        ]

        # Database server
        mock_db = MagicMock()
        mock_db.is_running = True
        mock_db.config = McpServerConfig(
            name="postgres", image="pg:latest",
            categories=["database"],
        )
        mock_db.tools = [
            {"name": "query", "description": "Execute SQL query", "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}}},
            {"name": "list_tables", "description": "List database tables", "input_schema": {"type": "object", "properties": {}}},
        ]

        gw._containers = {"filesystem": mock_fs, "github": mock_gh, "postgres": mock_db}
        gw._started = True
        gw._rebuild_tool_index()
        return gw

    def test_category_detection_filesystem(self):
        """Detect filesystem category from task."""
        router = ContextRouter()
        cats = router.get_categories_for_task("Read the package.json file")
        assert "filesystem" in cats

    def test_category_detection_git(self):
        """Detect git category."""
        router = ContextRouter()
        cats = router.get_categories_for_task("Create a pull request on GitHub")
        assert "git" in cats or "github" in cats

    def test_category_detection_database(self):
        """Detect database category."""
        router = ContextRouter()
        cats = router.get_categories_for_task("Query the postgres database for users")
        assert "database" in cats

    def test_category_detection_multiple(self):
        """Multiple categories from one task."""
        router = ContextRouter()
        cats = router.get_categories_for_task("Read the file and commit to git repository")
        assert "filesystem" in cats
        assert "git" in cats

    def test_select_tools_filesystem_task(self):
        """Filesystem task selects filesystem tools."""
        gw = self._make_gateway_with_tools()
        router = ContextRouter(gw)

        tools = router.select_tools("Read the configuration file from the directory")
        tool_names = [t["name"] for t in tools]

        # Filesystem tools should score high
        assert any("filesystem__" in n for n in tool_names)

    def test_select_tools_github_task(self):
        """GitHub task selects github tools."""
        gw = self._make_gateway_with_tools()
        router = ContextRouter(gw)

        tools = router.select_tools("Create a new issue on the GitHub repository")
        tool_names = [t["name"] for t in tools]

        assert any("github__" in n for n in tool_names)

    def test_select_tools_max_limit(self):
        """Max tools limit is respected."""
        gw = self._make_gateway_with_tools()
        router = ContextRouter(gw)

        tools = router.select_tools("Do everything with files and git and database", max_tools=3)
        assert len(tools) <= 3

    def test_select_tools_required_categories(self):
        """Required categories force inclusion."""
        gw = self._make_gateway_with_tools()
        router = ContextRouter(gw)

        tools = router.select_tools(
            "Some random task",
            required_categories=["database"],
        )
        tool_names = [t["name"] for t in tools]
        assert any("postgres__" in n for n in tool_names)

    def test_select_tools_excluded_categories(self):
        """Excluded categories prevent inclusion."""
        gw = self._make_gateway_with_tools()
        router = ContextRouter(gw)

        tools = router.select_tools(
            "Read files and query database",
            excluded_categories=["database"],
        )
        tool_names = [t["name"] for t in tools]
        assert not any("postgres__" in n for n in tool_names)

    def test_record_and_use_history(self):
        """Usage history influences future routing."""
        gw = self._make_gateway_with_tools()
        router = ContextRouter(gw)

        # Record successful usage
        router.record_usage("filesystem__read_file", "reading config files", True)
        router.record_usage("filesystem__read_file", "reading config files", True)
        router.record_usage("filesystem__read_file", "reading config files", True)

        # Now ask for a similar task
        tools = router.select_tools("Read the config file")
        tool_names = [t["name"] for t in tools]

        # filesystem tools should be boosted
        assert any("filesystem__" in n for n in tool_names)

    def test_extract_keywords(self):
        """Keyword extraction removes stop words."""
        keywords = ContextRouter._extract_keywords("Read the JSON file from directory")
        assert "the" not in keywords
        assert "from" not in keywords
        assert "read" in keywords
        assert "json" in keywords
        assert "file" in keywords

    def test_empty_gateway(self):
        """Empty gateway returns no tools."""
        gw = McpGateway()
        gw._started = True
        router = ContextRouter(gw)
        tools = router.select_tools("Do something")
        assert tools == []

    def test_routing_stats(self):
        """Routing stats track usage."""
        router = ContextRouter()
        router.record_usage("tool_a", "task 1", True)
        router.record_usage("tool_a", "task 2", False)
        router.record_usage("tool_b", "task 3", True)

        stats = router.get_routing_stats()
        assert stats["total_routings"] == 3
        assert stats["unique_tools_used"] == 2
        assert stats["tool_usage"]["tool_a"] == 2
        assert stats["tool_success_rates"]["tool_b"] == 1.0


# ============================================================
# Tool Bridge Tests
# ============================================================

class TestToolBridge:
    """Tests for MCP tool bridge integration."""

    def test_mcp_proxy_tool_creation(self):
        """Create a proxy tool from MCP definition."""
        tool_def = {
            "name": "fs__read_file",
            "description": "Read a file",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
        proxy = McpProxyTool(tool_def, "filesystem")
        assert proxy.name == "fs__read_file"
        assert proxy.description == "Read a file"
        assert proxy.input_schema["required"] == ["path"]

    def test_mcp_proxy_tool_to_claude(self):
        """Proxy tool converts to Claude format."""
        tool_def = {"name": "test", "description": "Test tool"}
        proxy = McpProxyTool(tool_def, "test_server")
        claude = proxy.to_claude_tool()
        assert claude["name"] == "test"
        assert claude["description"] == "Test tool"
        assert "input_schema" in claude

    def test_mcp_proxy_tool_validate_params(self):
        """Parameter validation catches missing required params."""
        tool_def = {
            "name": "test",
            "description": "Test",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
        proxy = McpProxyTool(tool_def, "server")
        assert proxy.validate_params(path="/tmp") is None
        error = proxy.validate_params()
        assert error is not None
        assert "path" in error

    def test_mcp_proxy_tool_execute_success(self):
        """Proxy tool executes via gateway."""
        mock_gw = MagicMock()
        mock_gw.call_tool.return_value = "file contents here"

        tool_def = {"name": "fs__read_file", "description": "Read"}
        proxy = McpProxyTool(tool_def, "filesystem", mock_gw)
        result = proxy.execute(path="/tmp/test.txt")

        assert result.success
        assert result.output == "file contents here"
        mock_gw.call_tool.assert_called_once_with("fs__read_file", {"path": "/tmp/test.txt"})

    def test_mcp_proxy_tool_execute_error(self):
        """Proxy tool handles MCP errors."""
        mock_gw = MagicMock()
        mock_gw.call_tool.return_value = "[MCP Error] File not found"

        tool_def = {"name": "fs__read_file", "description": "Read"}
        proxy = McpProxyTool(tool_def, "filesystem", mock_gw)
        result = proxy.execute(path="/nonexistent")

        assert not result.success
        assert "File not found" in result.error

    def test_mcp_proxy_tool_safe_execute(self):
        """Safe execute catches exceptions."""
        mock_gw = MagicMock()
        mock_gw.call_tool.side_effect = RuntimeError("Connection lost")

        tool_def = {"name": "test", "description": "Test"}
        proxy = McpProxyTool(tool_def, "server", mock_gw)
        result = proxy.safe_execute()

        assert not result.success
        assert "Connection lost" in result.error or "McpProxyTool error" in result.error

    def test_get_mcp_tool_names(self):
        """Extract tool names from definitions."""
        tools = [
            {"name": "fs__read", "description": "Read"},
            {"name": "gh__issue", "description": "Issue"},
        ]
        names = get_mcp_tool_names(tools)
        assert names == {"fs__read", "gh__issue"}

    def test_get_mcp_research_tools_gateway_not_started(self):
        """Research tools return empty when gateway not started."""
        mock_gw = MagicMock()
        mock_gw.is_started = False
        tools, dispatch = get_mcp_research_tools("test task", gateway=mock_gw)
        assert tools == []
        result = dispatch("anything", {})
        assert "[MCP Error]" in result

    def test_route_mcp_tool_call_not_started(self):
        """Route returns error when gateway not started."""
        mock_gw = MagicMock()
        mock_gw.is_started = False
        result = route_mcp_tool_call("test", {}, gateway=mock_gw)
        assert "[MCP Error]" in result

    def test_route_mcp_tool_call_success(self):
        """Route dispatches to gateway."""
        mock_gw = MagicMock()
        mock_gw.is_started = True
        mock_gw.call_tool.return_value = "success"
        result = route_mcp_tool_call("fs__read", {"path": "/tmp"}, gateway=mock_gw)
        assert result == "success"

    def test_register_mcp_tools(self):
        """Register MCP tools in a mock execution registry."""
        mock_gw = MagicMock()
        mock_gw.is_started = True

        mock_container = MagicMock()
        mock_container.is_running = True
        mock_container.config = McpServerConfig(name="fs", image="fs:latest", categories=["filesystem"])
        mock_container.tools = [
            {"name": "read", "description": "Read", "input_schema": {"type": "object", "properties": {}}},
            {"name": "write", "description": "Write", "input_schema": {"type": "object", "properties": {}}},
        ]
        mock_gw._containers = {"fs": mock_container}

        mock_registry = MagicMock()
        mock_registry.register = MagicMock()

        count = register_mcp_tools_in_registry(mock_registry, gateway=mock_gw)
        assert count == 2
        assert mock_registry.register.call_count == 2

    def test_register_mcp_tools_category_filter(self):
        """Only register tools from matching categories."""
        mock_gw = MagicMock()
        mock_gw.is_started = True

        mock_fs = MagicMock()
        mock_fs.is_running = True
        mock_fs.config = McpServerConfig(name="fs", image="fs:latest", categories=["filesystem"])
        mock_fs.tools = [{"name": "read", "description": "Read", "input_schema": {"type": "object", "properties": {}}}]

        mock_db = MagicMock()
        mock_db.is_running = True
        mock_db.config = McpServerConfig(name="db", image="db:latest", categories=["database"])
        mock_db.tools = [{"name": "query", "description": "Query", "input_schema": {"type": "object", "properties": {}}}]

        mock_gw._containers = {"fs": mock_fs, "db": mock_db}

        mock_registry = MagicMock()
        count = register_mcp_tools_in_registry(
            mock_registry, gateway=mock_gw, categories=["filesystem"]
        )
        assert count == 1  # Only filesystem tools

    def test_register_mcp_tools_gateway_not_started(self):
        """No registration when gateway not started."""
        mock_gw = MagicMock()
        mock_gw.is_started = False
        mock_registry = MagicMock()
        count = register_mcp_tools_in_registry(mock_registry, gateway=mock_gw)
        assert count == 0


# ============================================================
# Integration-style Tests (all mocked, tests component interaction)
# ============================================================

class TestMcpIntegration:
    """Tests that verify components work together correctly."""

    def test_gateway_to_router_flow(self):
        """Gateway aggregates tools → router filters them."""
        gw = McpGateway()

        mock_srv = MagicMock()
        mock_srv.is_running = True
        mock_srv.config = McpServerConfig(
            name="mixed", image="mixed:latest",
            categories=["filesystem", "git"],
        )
        mock_srv.tools = [
            {"name": "read_file", "description": "Read a file from disk"},
            {"name": "git_commit", "description": "Commit changes to git"},
            {"name": "git_log", "description": "View git log"},
        ]

        gw._containers = {"mixed": mock_srv}
        gw._started = True
        gw._rebuild_tool_index()

        router = ContextRouter(gw)

        # Filesystem task should score filesystem-related tools higher
        tools = router.select_tools("Read the README file")
        tool_names = [t["name"] for t in tools]
        assert len(tool_names) > 0

    def test_config_roundtrip(self, tmp_path):
        """Config save → load preserves all fields."""
        gw = McpGateway()
        gw.add_server(McpServerConfig(
            name="test",
            image="test:latest",
            env={"KEY": "val"},
            volumes={"/home": "/workspace"},
            categories=["testing"],
            description="Test server",
            max_restarts=5,
        ))

        config_path = str(tmp_path / "roundtrip.json")
        gw.save_config(config_path)

        gw2 = McpGateway()
        count = gw2.load_config(config_path)
        assert count == 1

        loaded = gw2._containers["test"].config
        assert loaded.image == "test:latest"
        assert loaded.env == {"KEY": "val"}
        assert loaded.volumes == {"/home": "/workspace"}
        assert loaded.categories == ["testing"]
        assert loaded.max_restarts == 5

    def test_tool_name_collision_prevention(self):
        """Tools from different servers get unique prefixed names."""
        gw = McpGateway()

        mock_a = MagicMock()
        mock_a.is_running = True
        mock_a.config = McpServerConfig(name="server_a", image="a:latest", categories=["code"])
        mock_a.tools = [{"name": "search", "description": "Search A"}]

        mock_b = MagicMock()
        mock_b.is_running = True
        mock_b.config = McpServerConfig(name="server_b", image="b:latest", categories=["code"])
        mock_b.tools = [{"name": "search", "description": "Search B"}]

        gw._containers = {"server_a": mock_a, "server_b": mock_b}
        gw._rebuild_tool_index()

        all_tools = gw.get_all_tools()
        names = [t["name"] for t in all_tools]
        assert "server_a__search" in names
        assert "server_b__search" in names
        assert len(names) == 2  # No collision


# ============================================================
# Edge Case Tests
# ============================================================

class TestEdgeCases:
    """Edge cases and error handling."""

    def test_protocol_parse_non_dict_response(self):
        """Parsing a JSON array raises ValueError."""
        with pytest.raises(ValueError, match="Expected JSON object"):
            parse_response("[1, 2, 3]")

    def test_protocol_parse_wrong_version(self):
        """Wrong jsonrpc version raises ValueError."""
        with pytest.raises(ValueError, match="Expected jsonrpc 2.0"):
            parse_response(json.dumps({"jsonrpc": "1.0", "id": 1, "result": "x"}))

    def test_empty_tools_list_parse(self):
        """Empty tools list returns empty list."""
        assert parse_tools_list_result([]) == []
        assert parse_tools_list_result({"tools": []}) == []

    def test_tool_def_missing_fields(self):
        """Tool definition with missing fields gets defaults."""
        tool = parse_tool_definition({})
        assert tool["name"] == "unknown"
        assert tool["description"] == ""
        assert "type" in tool["input_schema"]

    def test_context_router_empty_task(self):
        """Empty task returns no categories."""
        router = ContextRouter()
        cats = router.get_categories_for_task("")
        assert len(cats) == 0

    def test_gateway_start_disabled_server(self):
        """Disabled servers are skipped during start_all."""
        gw = McpGateway()
        gw.add_server(McpServerConfig(name="disabled", image="x:latest", enabled=False))
        results = gw.start_all()
        assert results["disabled"] is False

    def test_proxy_tool_no_input_schema(self):
        """Proxy tool works without input_schema."""
        tool_def = {"name": "simple", "description": "Simple tool"}
        proxy = McpProxyTool(tool_def, "server")
        assert proxy.input_schema["type"] == "object"

    def test_keyword_patterns_are_valid_regex(self):
        """All keyword category patterns are valid regex."""
        import re
        for pattern in KEYWORD_CATEGORIES.keys():
            re.compile(pattern)  # Should not raise

    def test_parse_tool_call_result_dict_no_content(self):
        """Handle dict result without content key."""
        result = parse_tool_call_result({"data": "value"})
        assert isinstance(result, str)

    def test_mcp_server_config_defaults(self):
        """McpServerConfig has correct defaults for all fields."""
        cfg = McpServerConfig(name="x", image="y:latest")
        assert cfg.command == []
        assert cfg.env == {}
        assert cfg.volumes == {}
        assert cfg.network == ""
        assert cfg.args == []
        assert cfg.restart_on_failure is True
        assert cfg.description == ""
        assert cfg.categories == []


# ============================================================
# Objective 16: idea-reality-mcp Integration Tests
# ============================================================

class TestIdeaRealityIntegration:
    """Tests for idea-reality-mcp integration in context_router and mcp_servers.json."""

    def test_validation_keywords_route_correctly(self):
        """Validation keywords should match validation/research categories."""
        router = ContextRouter()
        for task in [
            "validate this product idea",
            "do a reality check on this SaaS concept",
            "check if this already exists",
            "analyze the competition for task management",
            "pre-build check for this app idea",
        ]:
            cats = router.get_categories_for_task(task)
            assert "validation" in cats or "research" in cats, f"Failed for: {task}"

    def test_idea_reality_in_mcp_config(self):
        """idea-reality server should be in mcp_servers.json."""
        import json
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "mcp_servers.json",
        )
        with open(config_path) as f:
            config = json.load(f)
        assert "idea-reality" in config["servers"]
        ir = config["servers"]["idea-reality"]
        assert ir["enabled"] is True
        assert "validation" in ir["categories"]
        assert ir["command"] == "uvx"

    def test_non_build_tasks_dont_trigger_validation(self):
        """Non-build tasks should not match validation keywords."""
        router = ContextRouter()
        cats = router.get_categories_for_task("write a unit test for the parser")
        assert "validation" not in cats


# === Objective 22: Service Integration Foundation ===


class TestServiceIntegrationMcpConfig:
    """Verify external MCP servers are configured in mcp_servers.json."""

    @pytest.fixture(autouse=True)
    def load_config(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "mcp_servers.json",
        )
        with open(config_path) as f:
            self.config = json.load(f)
        self.servers = self.config["servers"]

    def test_supabase_server_configured(self):
        assert "supabase" in self.servers
        s = self.servers["supabase"]
        assert s["enabled"] is False  # disabled by default
        assert "database" in s["categories"]
        assert "supabase" in s["categories"]
        assert "auth" in s["categories"]
        assert "SUPABASE_ACCESS_TOKEN" in s.get("env", {})

    def test_stripe_server_configured(self):
        assert "stripe" in self.servers
        s = self.servers["stripe"]
        assert s["enabled"] is False
        assert "payments" in s["categories"]
        assert "stripe" in s["categories"]
        assert "STRIPE_SECRET_KEY" in s.get("env", {})

    def test_slack_server_configured(self):
        assert "slack" in self.servers
        s = self.servers["slack"]
        assert s["enabled"] is False
        assert "messaging" in s["categories"]
        assert "slack" in s["categories"]
        assert "SLACK_BOT_TOKEN" in s.get("env", {})

    def test_vercel_server_configured(self):
        assert "vercel" in self.servers
        s = self.servers["vercel"]
        assert s["enabled"] is False
        assert "deploy" in s["categories"]
        assert "vercel" in s["categories"]
        assert "VERCEL_TOKEN" in s.get("env", {})

    def test_all_new_servers_disabled_by_default(self):
        """New service servers should be disabled until explicitly enabled."""
        for name in ["supabase", "stripe", "slack", "vercel"]:
            assert self.servers[name]["enabled"] is False, f"{name} should be disabled"

    def test_existing_servers_unchanged(self):
        """Pre-existing servers should not be affected."""
        assert "github" in self.servers
        assert self.servers["github"]["enabled"] is True
        assert "idea-reality" in self.servers
        assert self.servers["idea-reality"]["enabled"] is True


class TestServiceIntegrationRouting:
    """Verify context router routes service keywords correctly."""

    def setup_method(self):
        self.router = ContextRouter()

    def test_payment_keywords_route_to_stripe(self):
        for task in [
            "set up stripe checkout for subscriptions",
            "create a payment flow for the SaaS",
            "handle billing and subscription management",
            "add a checkout page with pricing tiers",
        ]:
            cats = self.router.get_categories_for_task(task)
            assert "payments" in cats or "stripe" in cats, f"Failed for: {task}"

    def test_supabase_keywords_route_correctly(self):
        for task in [
            "set up supabase auth for the app",
            "create database tables with RLS policies",
            "implement signup and login flow",
            "configure storage buckets for user uploads",
        ]:
            cats = self.router.get_categories_for_task(task)
            assert any(c in cats for c in ["database", "auth", "supabase", "storage"]), \
                f"Failed for: {task}"

    def test_slack_keywords_route_correctly(self):
        for task in [
            "send a slack notification when build completes",
            "post to the #deployments channel",
        ]:
            cats = self.router.get_categories_for_task(task)
            assert "slack" in cats or "messaging" in cats, f"Failed for: {task}"

    def test_vercel_keywords_route_correctly(self):
        for task in [
            "deploy the app to vercel",
            "set up a custom domain for hosting",
            "configure production deploy environment variables",
        ]:
            cats = self.router.get_categories_for_task(task)
            assert "deploy" in cats or "vercel" in cats or "hosting" in cats, \
                f"Failed for: {task}"

    def test_mixed_service_task_routes_multiple(self):
        """A task mentioning multiple services should match multiple categories."""
        cats = self.router.get_categories_for_task(
            "deploy the supabase-backed SaaS with stripe billing to vercel"
        )
        assert "supabase" in cats or "database" in cats
        assert "stripe" in cats or "payments" in cats
        assert "vercel" in cats or "deploy" in cats

