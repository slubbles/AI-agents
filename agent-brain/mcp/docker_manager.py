"""
Docker Container Manager for MCP Servers.

Handles the lifecycle of MCP servers running in Docker containers:
  - Pull images on demand
  - Start containers with correct stdin/stdout configuration
  - Communicate via subprocess pipes (JSON-RPC over stdio)
  - Health checks and automatic restart
  - Graceful shutdown

Each MCP server runs in its own Docker container as a subprocess:
    docker run -i --rm <image> [args...]

The -i flag keeps stdin open for JSON-RPC communication.
Stdout carries JSON-RPC responses. Stderr carries logs.
"""

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from mcp.protocol import (
    build_initialize,
    build_initialized_notification,
    build_ping,
    build_tools_list,
    get_result,
    is_error_response,
    parse_response,
    parse_tools_list_result,
)

logger = logging.getLogger("mcp.docker")


# ---------------------------------------------------------------------------
# Server configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class McpServerConfig:
    """Configuration for a single MCP server."""

    name: str
    """Unique identifier for this server (e.g., 'filesystem', 'github')."""

    image: str
    """Docker image (e.g., 'mcp/filesystem:latest')."""

    command: list[str] = field(default_factory=list)
    """Optional command override for the container."""

    env: dict[str, str] = field(default_factory=dict)
    """Environment variables to pass to the container."""

    volumes: dict[str, str] = field(default_factory=dict)
    """Host:container volume mounts."""

    network: str = ""
    """Docker network to attach to."""

    args: list[str] = field(default_factory=list)
    """Additional docker run arguments."""

    enabled: bool = True
    """Whether this server should be started."""

    auto_pull: bool = True
    """Pull image if not found locally."""

    restart_on_failure: bool = True
    """Automatically restart if the process dies."""

    max_restarts: int = 3
    """Maximum restart attempts before giving up."""

    timeout_seconds: float = 30.0
    """Timeout for individual MCP requests."""

    description: str = ""
    """Human-readable description of what this server provides."""

    categories: list[str] = field(default_factory=list)
    """Tool categories this server provides (for context routing)."""


# ---------------------------------------------------------------------------
# Container process wrapper
# ---------------------------------------------------------------------------

class McpContainer:
    """
    Manages a single MCP server running as a Docker container subprocess.

    Communication flows:
        Agent Brain → container stdin  (JSON-RPC requests)
        container stdout → Agent Brain (JSON-RPC responses)
        container stderr → log capture
    """

    def __init__(self, config: McpServerConfig):
        self.config = config
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._restart_count = 0
        self._tools: list[dict] = []  # Cached tool definitions
        self._server_info: dict = {}  # From initialize response
        self._initialized = False

    @property
    def is_running(self) -> bool:
        """Check if the container process is alive."""
        return self.process is not None and self.process.poll() is None

    @property
    def tools(self) -> list[dict]:
        """Return cached tool definitions (Claude tool_use format)."""
        return self._tools

    def start(self) -> bool:
        """
        Start the Docker container and initialize the MCP connection.

        Returns True on success, False on failure.
        """
        with self._lock:
            if self.is_running:
                return True

            try:
                # Build docker run command
                cmd = self._build_docker_command()
                logger.info(f"Starting MCP server '{self.config.name}': {' '.join(cmd)}")

                # Optionally pull the image first
                if self.config.auto_pull:
                    self._pull_image()

                # Start the container as a subprocess
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,  # Unbuffered for real-time communication
                )

                # Start stderr capture thread
                self._stderr_thread = threading.Thread(
                    target=self._capture_stderr,
                    daemon=True,
                    name=f"mcp-stderr-{self.config.name}",
                )
                self._stderr_thread.start()

                # Give the process a moment to start
                time.sleep(0.5)

                if not self.is_running:
                    exit_code = self.process.poll()
                    stderr = self._get_stderr_tail()
                    logger.error(
                        f"MCP server '{self.config.name}' exited immediately "
                        f"(code {exit_code}): {stderr}"
                    )
                    return False

                # Initialize MCP connection
                if not self._mcp_initialize():
                    logger.error(f"MCP initialize failed for '{self.config.name}'")
                    self.stop()
                    return False

                # Discover tools
                self._tools = self._mcp_list_tools()
                logger.info(
                    f"MCP server '{self.config.name}' ready with "
                    f"{len(self._tools)} tools: "
                    f"{[t['name'] for t in self._tools]}"
                )

                self._initialized = True
                self._restart_count = 0
                return True

            except Exception as e:
                logger.error(f"Failed to start MCP server '{self.config.name}': {e}")
                self.stop()
                return False

    def stop(self) -> None:
        """Stop the Docker container gracefully."""
        with self._lock:
            self._initialized = False
            if self.process:
                try:
                    if self.process.stdin:
                        self.process.stdin.close()
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
                except Exception as e:
                    logger.warning(f"Error stopping '{self.config.name}': {e}")
                finally:
                    self.process = None

    def restart(self) -> bool:
        """
        Restart the container.
        Returns True on success. Respects max_restarts.
        """
        self._restart_count += 1
        if self._restart_count > self.config.max_restarts:
            logger.error(
                f"MCP server '{self.config.name}' exceeded max restarts "
                f"({self.config.max_restarts})"
            )
            return False

        logger.info(
            f"Restarting MCP server '{self.config.name}' "
            f"(attempt {self._restart_count}/{self.config.max_restarts})"
        )
        self.stop()
        time.sleep(1)
        return self.start()

    def send_request(self, request_bytes: bytes, timeout: float | None = None) -> dict:
        """
        Send a JSON-RPC request and wait for the response.

        Returns the parsed JSON-RPC response dict.
        Raises RuntimeError on communication failure.
        """
        timeout = timeout or self.config.timeout_seconds

        if not self.is_running:
            if self.config.restart_on_failure and self._restart_count < self.config.max_restarts:
                if not self.restart():
                    raise RuntimeError(f"MCP server '{self.config.name}' is not running and restart failed")
            else:
                raise RuntimeError(f"MCP server '{self.config.name}' is not running")

        with self._lock:
            try:
                assert self.process and self.process.stdin and self.process.stdout

                # Write request to stdin
                self.process.stdin.write(request_bytes)
                self.process.stdin.flush()

                # Read response line from stdout (with timeout)
                response_line = self._read_line_with_timeout(timeout)
                if not response_line:
                    raise RuntimeError(f"No response from '{self.config.name}' within {timeout}s")

                return parse_response(response_line)

            except (BrokenPipeError, OSError) as e:
                raise RuntimeError(
                    f"Communication error with '{self.config.name}': {e}"
                ) from e

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> str:
        """
        Call an MCP tool and return the result as a string.

        This is the main entry point for tool invocation.
        """
        from mcp.protocol import build_tools_call, parse_tool_call_result

        request = build_tools_call(tool_name, arguments)
        response = self.send_request(request)

        if is_error_response(response):
            err = response["error"]
            return f"[MCP Error] {err.get('message', 'Unknown error')}"

        result = get_result(response)
        return parse_tool_call_result(result)

    def ping(self) -> bool:
        """Send a ping to check if the server is responsive."""
        try:
            response = self.send_request(build_ping(), timeout=5.0)
            return not is_error_response(response)
        except Exception:
            return False

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    def _build_docker_command(self) -> list[str]:
        """Build the docker run command."""
        cmd = ["docker", "run", "-i", "--rm"]

        # Container name for easy identification
        cmd.extend(["--name", f"mcp-{self.config.name}"])

        # Environment variables
        for key, value in self.config.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Volume mounts
        for host_path, container_path in self.config.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])

        # Network
        if self.config.network:
            cmd.extend(["--network", self.config.network])

        # Additional args
        cmd.extend(self.config.args)

        # Image
        cmd.append(self.config.image)

        # Command override
        if self.config.command:
            cmd.extend(self.config.command)

        return cmd

    def _pull_image(self) -> None:
        """Pull the Docker image if not present locally."""
        try:
            # Check if image exists
            result = subprocess.run(
                ["docker", "image", "inspect", self.config.image],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return  # Image already exists

            logger.info(f"Pulling image '{self.config.image}'...")
            result = subprocess.run(
                ["docker", "pull", self.config.image],
                capture_output=True,
                timeout=300,  # 5 min for large images
            )
            if result.returncode != 0:
                logger.warning(
                    f"Failed to pull '{self.config.image}': "
                    f"{result.stderr.decode()[:500]}"
                )
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout pulling '{self.config.image}'")
        except Exception as e:
            logger.warning(f"Error pulling image: {e}")

    def _mcp_initialize(self) -> bool:
        """
        Perform the MCP initialize handshake.
        Returns True on success.
        """
        try:
            request = build_initialize()
            response = self.send_request(request, timeout=15.0)

            if is_error_response(response):
                logger.error(f"Initialize error: {response.get('error')}")
                return False

            self._server_info = get_result(response) or {}
            logger.debug(f"Server info for '{self.config.name}': {self._server_info}")

            # Send initialized notification
            assert self.process and self.process.stdin
            self.process.stdin.write(build_initialized_notification())
            self.process.stdin.flush()

            return True

        except Exception as e:
            logger.error(f"Initialize handshake failed: {e}")
            return False

    def _mcp_list_tools(self) -> list[dict]:
        """
        Fetch available tools from the MCP server.
        Returns list of Claude tool_use format dicts.
        """
        try:
            request = build_tools_list()
            response = self.send_request(request, timeout=15.0)

            if is_error_response(response):
                logger.error(f"tools/list error: {response.get('error')}")
                return []

            result = get_result(response)
            return parse_tools_list_result(result)

        except Exception as e:
            logger.error(f"Failed to list tools from '{self.config.name}': {e}")
            return []

    def _read_line_with_timeout(self, timeout: float) -> str:
        """Read a line from stdout with timeout."""
        assert self.process and self.process.stdout

        import select

        # Use select for timeout on the stdout file descriptor
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            return ""

        line = self.process.stdout.readline()
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        return line.strip()

    def _capture_stderr(self) -> None:
        """Background thread to capture stderr output."""
        try:
            assert self.process and self.process.stderr
            for line in self.process.stderr:
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                line = line.strip()
                if line:
                    self._stderr_lines.append(line)
                    # Keep last 100 lines
                    if len(self._stderr_lines) > 100:
                        self._stderr_lines = self._stderr_lines[-50:]
                    logger.debug(f"[{self.config.name}] {line}")
        except Exception:
            pass  # Process ended

    def _get_stderr_tail(self, n: int = 10) -> str:
        """Get the last N lines of stderr."""
        return "\n".join(self._stderr_lines[-n:])

    def get_status(self) -> dict:
        """Get container status for monitoring."""
        return {
            "name": self.config.name,
            "image": self.config.image,
            "running": self.is_running,
            "initialized": self._initialized,
            "tools_count": len(self._tools),
            "tool_names": [t["name"] for t in self._tools],
            "restart_count": self._restart_count,
            "categories": self.config.categories,
        }
