"""
SSH Manager — Remote command execution via SSH.

Handles:
- SSH key-based authentication (keys from vault)
- Remote command execution
- File transfer (SCP/rsync)
- Connection pooling and reuse

Uses subprocess + ssh/scp commands (no paramiko dependency).
This keeps things simple and works on any Unix system.
"""

import logging
import os
import shlex
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Timeouts
SSH_CONNECT_TIMEOUT = 10
SSH_COMMAND_TIMEOUT = 300
SCP_TIMEOUT = 600


class SSHError(Exception):
    """SSH operation failed."""
    pass


class SSHManager:
    """SSH connection manager using system ssh/scp commands.
    
    Usage:
        ssh = SSHManager(host="1.2.3.4", user="deploy", key="/path/to/key")
        result = ssh.run("ls -la /opt/app")
        ssh.upload_file("local.py", "/opt/app/local.py")
        ssh.upload_dir("./src", "/opt/app/src")
    """

    def __init__(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        key_path: Optional[str] = None,
        key_content: Optional[str] = None,
    ):
        self.host = host
        self.user = user
        self.port = port
        self._key_path = key_path
        self._key_content = key_content
        self._temp_key_file: Optional[str] = None

    def _get_key_path(self) -> Optional[str]:
        """Get path to SSH private key. Creates temp file if key_content provided."""
        if self._key_path:
            return self._key_path
        
        if self._key_content:
            if not self._temp_key_file:
                fd, path = tempfile.mkstemp(prefix="agent_brain_ssh_", suffix=".key")
                with os.fdopen(fd, "w") as f:
                    f.write(self._key_content)
                os.chmod(path, 0o600)
                self._temp_key_file = path
            return self._temp_key_file

        return None

    def _ssh_base_args(self) -> list[str]:
        """Build base SSH command arguments."""
        args = [
            "ssh",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
            "-o", "BatchMode=yes",
            "-p", str(self.port),
        ]
        
        key_path = self._get_key_path()
        if key_path:
            args.extend(["-i", key_path])
        
        return args

    def _scp_base_args(self) -> list[str]:
        """Build base SCP command arguments."""
        args = [
            "scp",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
            "-o", "BatchMode=yes",
            "-P", str(self.port),
        ]
        
        key_path = self._get_key_path()
        if key_path:
            args.extend(["-i", key_path])
        
        return args

    def _target(self) -> str:
        """SSH target string: user@host"""
        return f"{self.user}@{self.host}"

    # ── Commands ─────────────────────────────────────────────

    def run(
        self,
        command: str,
        timeout: int = SSH_COMMAND_TIMEOUT,
        check: bool = True,
    ) -> dict:
        """Execute a command on the remote server.
        
        Returns dict with {stdout, stderr, returncode}.
        Raises SSHError if check=True and command fails.
        """
        args = self._ssh_base_args() + [self._target(), command]
        
        logger.debug(f"SSH: {self._target()} $ {command}")
        
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise SSHError(f"SSH command timed out after {timeout}s: {command}")
        except FileNotFoundError:
            raise SSHError("ssh command not found — is OpenSSH installed?")

        output = {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }

        if check and result.returncode != 0:
            raise SSHError(
                f"SSH command failed (exit {result.returncode}): {command}\n"
                f"stderr: {result.stderr.strip()}"
            )

        return output

    def run_script(self, script: str, timeout: int = SSH_COMMAND_TIMEOUT) -> dict:
        """Execute a multi-line script on the remote server."""
        # Use heredoc approach
        escaped = script.replace("'", "'\\''")
        command = f"bash -c '{escaped}'"
        return self.run(command, timeout=timeout)

    # ── File Transfer ────────────────────────────────────────

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a single file via SCP."""
        args = self._scp_base_args() + [local_path, f"{self._target()}:{remote_path}"]
        
        logger.debug(f"SCP: {local_path} → {self._target()}:{remote_path}")
        
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=SCP_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise SSHError(f"SCP timed out uploading {local_path}")
        
        if result.returncode != 0:
            raise SSHError(f"SCP failed: {result.stderr.strip()}")

    def upload_dir(self, local_dir: str, remote_dir: str) -> None:
        """Upload a directory via rsync (falls back to scp -r)."""
        # Try rsync first (better for incremental updates)
        rsync_args = [
            "rsync", "-avz", "--delete",
            "-e", f"ssh -o StrictHostKeyChecking=accept-new -p {self.port}",
        ]
        
        key_path = self._get_key_path()
        if key_path:
            rsync_args[4] = f"ssh -o StrictHostKeyChecking=accept-new -p {self.port} -i {key_path}"
        
        rsync_args.extend([
            f"{local_dir}/",
            f"{self._target()}:{remote_dir}/",
        ])

        try:
            result = subprocess.run(
                rsync_args,
                capture_output=True,
                text=True,
                timeout=SCP_TIMEOUT,
            )
            if result.returncode == 0:
                return
            logger.warning(f"rsync failed, falling back to scp: {result.stderr}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("rsync not available, falling back to scp")

        # Fallback: scp -r
        args = self._scp_base_args() + ["-r", local_dir, f"{self._target()}:{remote_dir}"]
        result = subprocess.run(args, capture_output=True, text=True, timeout=SCP_TIMEOUT)
        if result.returncode != 0:
            raise SSHError(f"SCP directory upload failed: {result.stderr.strip()}")

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from remote server."""
        args = self._scp_base_args() + [f"{self._target()}:{remote_path}", local_path]
        result = subprocess.run(args, capture_output=True, text=True, timeout=SCP_TIMEOUT)
        if result.returncode != 0:
            raise SSHError(f"SCP download failed: {result.stderr.strip()}")

    # ── Connectivity ─────────────────────────────────────────

    def test_connection(self) -> bool:
        """Test SSH connectivity. Returns True if connection works."""
        try:
            result = self.run("echo ok", check=False, timeout=15)
            return result["returncode"] == 0 and "ok" in result["stdout"]
        except SSHError:
            return False

    def get_system_info(self) -> dict:
        """Get basic system info from remote server."""
        commands = {
            "os": "cat /etc/os-release | head -3",
            "uptime": "uptime -p",
            "disk": "df -h / | tail -1",
            "memory": "free -h | grep Mem",
            "python": "python3 --version 2>&1",
            "hostname": "hostname",
        }
        
        info = {}
        for key, cmd in commands.items():
            try:
                result = self.run(cmd, check=False, timeout=10)
                info[key] = result["stdout"]
            except SSHError as e:
                info[key] = f"Error: {e}"
        
        return info

    # ── Cleanup ──────────────────────────────────────────────

    def cleanup(self) -> None:
        """Remove temporary key files."""
        if self._temp_key_file and os.path.exists(self._temp_key_file):
            os.remove(self._temp_key_file)
            self._temp_key_file = None

    def __del__(self):
        self.cleanup()
