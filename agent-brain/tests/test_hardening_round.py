"""
Tests for hardening round: atomic writes, MCP fixes, deploy→scheduler wiring.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# Atomic Write Tests
# ============================================================

class TestAtomicWriteUsage(unittest.TestCase):
    """Verify all JSON-writing modules use atomic_json_write."""

    def test_no_raw_json_dump_in_production(self):
        """Scan production code for non-atomic json.dump (excluding allowed sites)."""
        import re
        brain_dir = os.path.join(os.path.dirname(__file__), "..")
        
        # Files allowed to have raw json.dump
        ALLOWED = {
            "utils/atomic_write.py",   # The implementation itself
            "memory_store.py",         # Line 142: intentionally append-only
        }
        
        violations = []
        for root, dirs, files in os.walk(brain_dir):
            # Skip test dirs and caches
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", "tests", "node_modules")]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(root, fname), brain_dir)
                if rel in ALLOWED:
                    continue
                
                filepath = os.path.join(root, fname)
                with open(filepath) as f:
                    for i, line in enumerate(f, 1):
                        # Match json.dump( but not json.dumps(
                        if re.search(r'json\.dump\(', line) and 'json.dumps(' not in line:
                            violations.append(f"{rel}:{i}: {line.strip()}")
        
        self.assertEqual(violations, [],
                         f"Found {len(violations)} non-atomic json.dump calls:\n" +
                         "\n".join(violations))


# ============================================================
# MCP Docker Manager Tests
# ============================================================

class TestMcpDockerManager(unittest.TestCase):
    """Test MCP Docker manager fixes."""

    def test_rlock_used(self):
        """Verify McpContainer uses RLock (not Lock) to prevent deadlocks."""
        from mcp.docker_manager import McpContainer, McpServerConfig
        
        cfg = McpServerConfig(name="test", image="test:latest")
        container = McpContainer(cfg)
        self.assertIsInstance(container._lock, type(threading.RLock()))

    def test_env_var_resolution(self):
        """Verify ${VAR} references are resolved from host environment."""
        from mcp.docker_manager import McpContainer
        
        with patch.dict(os.environ, {"MY_TOKEN": "secret123"}):
            result = McpContainer._resolve_env_value("Bearer ${MY_TOKEN}")
            self.assertEqual(result, "Bearer secret123")

    def test_env_var_missing(self):
        """Missing env vars resolve to empty string."""
        from mcp.docker_manager import McpContainer
        
        env_backup = os.environ.pop("NONEXISTENT_VAR_XYZ", None)
        try:
            result = McpContainer._resolve_env_value("${NONEXISTENT_VAR_XYZ}")
            self.assertEqual(result, "")
        finally:
            if env_backup is not None:
                os.environ["NONEXISTENT_VAR_XYZ"] = env_backup

    def test_notification_skipping(self):
        """Verify send_request skips MCP notifications and finds the real response."""
        from mcp.docker_manager import McpContainer, McpServerConfig
        from mcp.protocol import parse_response
        
        cfg = McpServerConfig(name="test", image="test:latest", timeout_seconds=5)
        container = McpContainer(cfg)
        container.process = MagicMock()
        container.process.poll.return_value = None  # Running
        container.process.stdin = MagicMock()
        container.process.stdout = MagicMock()
        
        # Simulate: notification, notification, then actual response
        lines = [
            b'{"jsonrpc":"2.0","method":"notifications/tools/list_changed","params":{}}\n',
            b'{"jsonrpc":"2.0","method":"notifications/resources/list_changed","params":{}}\n',
            b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n',
        ]
        call_count = [0]
        
        def fake_readline():
            idx = call_count[0]
            call_count[0] += 1
            return lines[idx] if idx < len(lines) else b''
        
        container.process.stdout.readline = fake_readline
        
        # Mock select to always return ready
        with patch('select.select', return_value=([container.process.stdout], [], [])):
            response = container.send_request(b'{"test":true}\n', timeout=5)
        
        self.assertEqual(response["id"], 1)
        self.assertTrue(response["result"]["ok"])


# ============================================================
# Deploy → Schedule Wiring Tests
# ============================================================

class TestDeployScheduleWiring(unittest.TestCase):
    """Test that deploy auto-triggers schedule setup."""

    @patch("cli.vault.get_vault")
    def test_deploy_calls_schedule_on_success(self, mock_vault_fn):
        """After successful deploy, setup_schedule is called."""
        mock_vault_fn.return_value = MagicMock()
        
        with patch("deploy.deployer.deploy", return_value={"status": "success", "steps": []}) as mock_deploy, \
             patch("deploy.deployer.setup_schedule", return_value={"status": "success", "cron_entry": "test"}) as mock_sched, \
             patch("deploy.vps_config.load_config") as mock_cfg:
            
            cfg = MagicMock()
            cfg.host = "1.2.3.4"
            cfg.schedule_cron = "0 */6 * * *"
            mock_cfg.return_value = cfg
            
            # Import and call  
            from cli.deploy_cmd import deploy
            deploy(dry_run=False)
            
            mock_deploy.assert_called_once()
            mock_sched.assert_called_once()

    @patch("cli.vault.get_vault")
    def test_deploy_skips_schedule_on_dry_run(self, mock_vault_fn):
        """Dry run should not trigger schedule setup."""
        mock_vault_fn.return_value = MagicMock()
        
        with patch("deploy.deployer.deploy", return_value={"status": "success", "steps": []}) as mock_deploy, \
             patch("deploy.deployer.setup_schedule") as mock_sched:
            
            from cli.deploy_cmd import deploy
            deploy(dry_run=True)
            
            mock_deploy.assert_called_once()
            mock_sched.assert_not_called()


# ============================================================
# Warning Suppression Test
# ============================================================

class TestWarningSuppression(unittest.TestCase):
    """Verify pyproject.toml warning filters exist."""

    def test_pyproject_exists(self):
        """pyproject.toml with pytest config should exist."""
        pyproject = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        self.assertTrue(os.path.exists(pyproject))

    def test_chromadb_filter(self):
        """ChromaDB deprecation filter should be configured."""
        pyproject = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(pyproject) as f:
            content = f.read()
        self.assertIn("chromadb", content)
        self.assertIn("DeprecationWarning", content)


if __name__ == "__main__":
    unittest.main()
