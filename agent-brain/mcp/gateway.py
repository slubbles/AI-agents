"""
MCP Gateway — Multi-server manager with tool discovery.

The gateway is the central coordinator for all MCP servers:
  - Starts/stops multiple MCP server containers
  - Aggregates tool definitions across all servers
  - Routes tool calls to the correct server
  - Handles server failures gracefully
  - Provides a unified API for the rest of Agent Brain

Usage:
    gateway = McpGateway()
    gateway.load_config()     # Load server configs
    gateway.start_all()       # Start all enabled servers

    # Get all available tools (Claude format)
    tools = gateway.get_all_tools()

    # Call a tool (routed to correct server)
    result = gateway.call_tool("read_file", {"path": "/tmp/test.txt"})

    gateway.stop_all()
"""

import json
import logging
import os
import threading
from typing import Any

from mcp.docker_manager import McpContainer, McpServerConfig

logger = logging.getLogger("mcp.gateway")


class McpGateway:
    """
    Central gateway for managing multiple MCP servers.

    Responsibilities:
      - Load server configurations
      - Manage container lifecycles
      - Aggregate and route tool calls
      - Health monitoring
    """

    def __init__(self):
        self._containers: dict[str, McpContainer] = {}
        self._tool_to_server: dict[str, str] = {}  # tool_name → server_name
        self._all_tools: list[dict] = []  # Cached aggregated tool list
        self._lock = threading.Lock()
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    # -------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------

    def add_server(self, config: McpServerConfig) -> None:
        """Add an MCP server configuration."""
        if config.name in self._containers:
            raise ValueError(f"Server '{config.name}' already registered")
        self._containers[config.name] = McpContainer(config)

    def load_config(self, config_path: str | None = None) -> int:
        """
        Load server configurations from a JSON file.

        Config format:
        {
            "servers": {
                "filesystem": {
                    "image": "mcp/filesystem:latest",
                    "env": {"ALLOWED_DIRS": "/workspace"},
                    "volumes": {"/workspace": "/workspace"},
                    "categories": ["filesystem", "code"],
                    "description": "File system operations"
                },
                "github": {
                    "image": "mcp/github:latest",
                    "env": {"GITHUB_TOKEN": "..."},
                    "categories": ["git", "code"],
                    "description": "GitHub API operations"
                }
            }
        }

        Returns number of servers loaded.
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "mcp_servers.json",
            )

        if not os.path.exists(config_path):
            logger.warning(f"MCP config not found: {config_path}")
            return 0

        try:
            with open(config_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load MCP config: {e}")
            return 0

        servers = data.get("servers", {})
        count = 0

        for name, srv_data in servers.items():
            try:
                config = McpServerConfig(
                    name=name,
                    image=srv_data.get("image", ""),
                    command=srv_data.get("command", []),
                    env=srv_data.get("env", {}),
                    volumes=srv_data.get("volumes", {}),
                    network=srv_data.get("network", ""),
                    args=srv_data.get("args", []),
                    enabled=srv_data.get("enabled", True),
                    auto_pull=srv_data.get("auto_pull", True),
                    restart_on_failure=srv_data.get("restart_on_failure", True),
                    max_restarts=srv_data.get("max_restarts", 3),
                    timeout_seconds=srv_data.get("timeout_seconds", 30.0),
                    description=srv_data.get("description", ""),
                    categories=srv_data.get("categories", []),
                )
                self.add_server(config)
                count += 1
                logger.info(f"Loaded MCP server config: {name}")
            except Exception as e:
                logger.error(f"Failed to load server '{name}': {e}")

        return count

    def save_config(self, config_path: str | None = None) -> None:
        """Save current server configurations to JSON."""
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "mcp_servers.json",
            )

        servers = {}
        for name, container in self._containers.items():
            cfg = container.config
            servers[name] = {
                "image": cfg.image,
                "command": cfg.command,
                "env": cfg.env,
                "volumes": cfg.volumes,
                "network": cfg.network,
                "args": cfg.args,
                "enabled": cfg.enabled,
                "auto_pull": cfg.auto_pull,
                "restart_on_failure": cfg.restart_on_failure,
                "max_restarts": cfg.max_restarts,
                "timeout_seconds": cfg.timeout_seconds,
                "description": cfg.description,
                "categories": cfg.categories,
            }

        with open(config_path, "w") as f:
            json.dump({"servers": servers}, f, indent=2)

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    def start_all(self) -> dict[str, bool]:
        """
        Start all enabled MCP servers.
        Returns {server_name: success} dict.
        """
        results = {}

        for name, container in self._containers.items():
            if not container.config.enabled:
                logger.info(f"Skipping disabled server: {name}")
                results[name] = False
                continue

            success = container.start()
            results[name] = success

            if success:
                logger.info(
                    f"Started '{name}' with {len(container.tools)} tools"
                )
            else:
                logger.error(f"Failed to start '{name}'")

        # Build aggregated tool index
        self._rebuild_tool_index()
        self._started = True

        logger.info(
            f"MCP Gateway ready: {sum(results.values())}/{len(results)} "
            f"servers running, {len(self._all_tools)} tools available"
        )
        return results

    def start_server(self, name: str) -> bool:
        """Start a specific server by name."""
        container = self._containers.get(name)
        if not container:
            logger.error(f"Unknown server: {name}")
            return False

        success = container.start()
        if success:
            self._rebuild_tool_index()
        return success

    def stop_all(self) -> None:
        """Stop all running MCP servers."""
        for name, container in self._containers.items():
            if container.is_running:
                logger.info(f"Stopping MCP server: {name}")
                container.stop()

        self._tool_to_server.clear()
        self._all_tools.clear()
        self._started = False

    def stop_server(self, name: str) -> None:
        """Stop a specific server by name."""
        container = self._containers.get(name)
        if container:
            container.stop()
            self._rebuild_tool_index()

    # -------------------------------------------------------------------
    # Tool discovery and routing
    # -------------------------------------------------------------------

    def get_all_tools(self) -> list[dict]:
        """
        Get all tools from all running servers (Claude tool_use format).

        Tool names are prefixed with the server name to avoid collisions:
            e.g., "filesystem__read_file", "github__create_issue"
        """
        return self._all_tools.copy()

    def get_tools_for_server(self, server_name: str) -> list[dict]:
        """Get tools from a specific server."""
        container = self._containers.get(server_name)
        if not container or not container.is_running:
            return []
        return container.tools

    def get_tools_by_category(self, category: str) -> list[dict]:
        """Get tools from servers that have the given category."""
        tools = []
        for name, container in self._containers.items():
            if not container.is_running:
                continue
            if category in container.config.categories:
                for tool in container.tools:
                    prefixed = self._prefix_tool(name, tool)
                    tools.append(prefixed)
        return tools

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> str:
        """
        Call a tool by its (possibly prefixed) name.

        Routes to the correct MCP server automatically.
        Returns the tool result as a string.
        """
        # Resolve server for this tool
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            # Try without prefix (for direct tool names)
            for name, container in self._containers.items():
                for tool in container.tools:
                    if tool["name"] == tool_name:
                        server_name = name
                        break
                if server_name:
                    break

        if not server_name:
            return f"[MCP Error] Unknown tool: {tool_name}. Available: {list(self._tool_to_server.keys())}"

        container = self._containers.get(server_name)
        if not container or not container.is_running:
            return f"[MCP Error] Server '{server_name}' is not running"

        # Strip the server prefix from the tool name for the actual call
        actual_name = tool_name
        prefix = f"{server_name}__"
        if tool_name.startswith(prefix):
            actual_name = tool_name[len(prefix):]

        try:
            return container.call_tool(actual_name, arguments)
        except RuntimeError as e:
            # Try restart on communication failure
            if container.config.restart_on_failure:
                logger.warning(f"Tool call failed, attempting restart: {e}")
                if container.restart():
                    try:
                        return container.call_tool(actual_name, arguments)
                    except Exception as e2:
                        return f"[MCP Error] Tool call failed after restart: {e2}"
            return f"[MCP Error] {e}"

    # -------------------------------------------------------------------
    # Health monitoring
    # -------------------------------------------------------------------

    def health_check(self) -> dict[str, dict]:
        """
        Run health checks on all servers.
        Returns {server_name: status_dict}.
        """
        results = {}
        for name, container in self._containers.items():
            status = container.get_status()
            status["responsive"] = container.ping() if container.is_running else False
            results[name] = status
        return results

    def get_status(self) -> dict:
        """Get a summary of gateway status."""
        running = sum(1 for c in self._containers.values() if c.is_running)
        return {
            "started": self._started,
            "total_servers": len(self._containers),
            "running_servers": running,
            "total_tools": len(self._all_tools),
            "tool_index": dict(self._tool_to_server),
            "servers": {
                name: container.get_status()
                for name, container in self._containers.items()
            },
        }

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    def _rebuild_tool_index(self) -> None:
        """Rebuild the tool-to-server mapping from all running containers."""
        with self._lock:
            self._tool_to_server.clear()
            self._all_tools.clear()

            for name, container in self._containers.items():
                if not container.is_running:
                    continue

                for tool in container.tools:
                    prefixed = self._prefix_tool(name, tool)
                    self._all_tools.append(prefixed)
                    self._tool_to_server[prefixed["name"]] = name

    @staticmethod
    def _prefix_tool(server_name: str, tool: dict) -> dict:
        """
        Create a copy of a tool definition with server-prefixed name.

        This prevents collisions when multiple servers have tools with
        the same name (e.g., both filesystem and docker have "read_file").
        """
        prefixed = tool.copy()
        prefixed["name"] = f"{server_name}__{tool['name']}"
        prefixed["description"] = (
            f"[{server_name}] {tool.get('description', '')}"
        )
        return prefixed


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_gateway: McpGateway | None = None


def get_gateway() -> McpGateway:
    """Get or create the global MCP gateway singleton."""
    global _gateway
    if _gateway is None:
        _gateway = McpGateway()
    return _gateway


def reset_gateway() -> None:
    """Reset the global gateway (for tests)."""
    global _gateway
    if _gateway and _gateway.is_started:
        _gateway.stop_all()
    _gateway = None
