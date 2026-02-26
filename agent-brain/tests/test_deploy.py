"""Tests for deploy/ module — VPS config, SSH manager, deployer."""

import json
import os
import subprocess
import tempfile
from dataclasses import asdict
from unittest.mock import patch, MagicMock, call

import pytest

from deploy.vps_config import VPSConfig, load_config, save_config, CONFIG_PATH
from deploy.ssh_manager import SSHManager, SSHError, SSH_CONNECT_TIMEOUT
from deploy.deployer import (
    create_archive,
    deploy,
    setup_schedule,
    remove_schedule,
    health_check,
    get_remote_logs,
    _build_cron_entry,
    DeployError,
    DEPLOY_EXCLUDE,
)


# ── VPSConfig Tests ─────────────────────────────────────────

class TestVPSConfig:
    """Test VPS configuration dataclass."""

    def test_defaults(self):
        c = VPSConfig()
        assert c.host == ""
        assert c.port == 22
        assert c.user == "agent-brain"
        assert c.schedule_cron == "0 */6 * * *"
        assert c.daily_budget_usd == 5.0
        assert c.is_deployed is False
        assert c.rounds_per_run == 3
        assert c.auto_evolve is True

    def test_custom_values(self):
        c = VPSConfig(host="1.2.3.4", port=2222, user="deploy", daily_budget_usd=10.0)
        assert c.host == "1.2.3.4"
        assert c.port == 2222
        assert c.user == "deploy"
        assert c.daily_budget_usd == 10.0

    def test_to_dict(self):
        c = VPSConfig(host="example.com")
        d = c.to_dict()
        assert isinstance(d, dict)
        assert d["host"] == "example.com"
        assert d["port"] == 22

    def test_from_dict(self):
        data = {"host": "test.com", "port": 3333, "unknown_field": "ignored"}
        c = VPSConfig.from_dict(data)
        assert c.host == "test.com"
        assert c.port == 3333

    def test_from_dict_ignores_unknown_fields(self):
        data = {"host": "a.com", "bogus": True}
        c = VPSConfig.from_dict(data)
        assert c.host == "a.com"
        assert not hasattr(c, "bogus")

    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "vps_config.json"
        c = VPSConfig(host="save-test.com", port=9999)

        with patch("deploy.vps_config.CONFIG_PATH", str(config_file)):
            save_config(c)
            assert config_file.exists()

            loaded = load_config()
            assert loaded.host == "save-test.com"
            assert loaded.port == 9999

    def test_load_returns_defaults_when_no_file(self, tmp_path):
        with patch("deploy.vps_config.CONFIG_PATH", str(tmp_path / "nope.json")):
            c = load_config()
            assert c.host == ""
            assert c.port == 22


# ── SSHManager Tests ─────────────────────────────────────────

class TestSSHManager:
    """Test SSH manager (mocked subprocess)."""

    def test_init(self):
        ssh = SSHManager(host="1.2.3.4", user="deploy", port=2222)
        assert ssh.host == "1.2.3.4"
        assert ssh.user == "deploy"
        assert ssh.port == 2222

    def test_target(self):
        ssh = SSHManager(host="1.2.3.4", user="deploy")
        assert ssh._target() == "deploy@1.2.3.4"

    def test_ssh_base_args_no_key(self):
        ssh = SSHManager(host="1.2.3.4")
        args = ssh._ssh_base_args()
        assert "ssh" in args
        assert "-p" in args
        assert "-i" not in args

    def test_ssh_base_args_with_key_path(self):
        ssh = SSHManager(host="1.2.3.4", key_path="/tmp/mykey")
        args = ssh._ssh_base_args()
        idx = args.index("-i")
        assert args[idx + 1] == "/tmp/mykey"

    def test_ssh_base_args_with_key_content(self, tmp_path):
        ssh = SSHManager(host="1.2.3.4", key_content="-----BEGIN FAKE KEY-----")
        args = ssh._ssh_base_args()
        assert "-i" in args
        # Temp key file should have been created
        assert ssh._temp_key_file is not None
        assert os.path.exists(ssh._temp_key_file)
        # Only readable by owner
        mode = os.stat(ssh._temp_key_file).st_mode & 0o777
        assert mode == 0o600
        ssh.cleanup()

    @patch("deploy.ssh_manager.subprocess.run")
    def test_run_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="hello\n", stderr="", returncode=0
        )
        ssh = SSHManager(host="1.2.3.4")
        result = ssh.run("echo hello")
        assert result["stdout"] == "hello"
        assert result["returncode"] == 0

    @patch("deploy.ssh_manager.subprocess.run")
    def test_run_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="Permission denied\n", returncode=255
        )
        ssh = SSHManager(host="1.2.3.4")
        with pytest.raises(SSHError, match="Permission denied"):
            ssh.run("whoami")

    @patch("deploy.ssh_manager.subprocess.run")
    def test_run_failure_no_check(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="error", returncode=1
        )
        ssh = SSHManager(host="1.2.3.4")
        result = ssh.run("false", check=False)
        assert result["returncode"] == 1

    @patch("deploy.ssh_manager.subprocess.run")
    def test_run_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=300)
        ssh = SSHManager(host="1.2.3.4")
        with pytest.raises(SSHError, match="timed out"):
            ssh.run("sleep 999")

    @patch("deploy.ssh_manager.subprocess.run")
    def test_run_ssh_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        ssh = SSHManager(host="1.2.3.4")
        with pytest.raises(SSHError, match="not found"):
            ssh.run("echo test")

    @patch("deploy.ssh_manager.subprocess.run")
    def test_run_script(self, mock_run):
        mock_run.return_value = MagicMock(stdout="done\n", stderr="", returncode=0)
        ssh = SSHManager(host="1.2.3.4")
        result = ssh.run_script("set -e\necho done")
        assert result["stdout"] == "done"
        assert mock_run.called

    @patch("deploy.ssh_manager.subprocess.run")
    def test_upload_file(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        ssh = SSHManager(host="1.2.3.4")
        ssh.upload_file("/tmp/local.py", "/opt/remote.py")
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "scp" in args

    @patch("deploy.ssh_manager.subprocess.run")
    def test_upload_file_failure(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="error\n", returncode=1)
        ssh = SSHManager(host="1.2.3.4")
        with pytest.raises(SSHError, match="SCP failed"):
            ssh.upload_file("/tmp/local.py", "/opt/remote.py")

    @patch("deploy.ssh_manager.subprocess.run")
    def test_download_file(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        ssh = SSHManager(host="1.2.3.4")
        ssh.download_file("/opt/remote.py", "/tmp/local.py")
        assert mock_run.called

    @patch("deploy.ssh_manager.subprocess.run")
    def test_test_connection_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="ok\n", stderr="", returncode=0)
        ssh = SSHManager(host="1.2.3.4")
        assert ssh.test_connection() is True

    @patch("deploy.ssh_manager.subprocess.run")
    def test_test_connection_failure(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="timeout", returncode=255)
        ssh = SSHManager(host="1.2.3.4")
        assert ssh.test_connection() is False

    @patch("deploy.ssh_manager.subprocess.run")
    def test_get_system_info(self, mock_run):
        mock_run.return_value = MagicMock(stdout="test\n", stderr="", returncode=0)
        ssh = SSHManager(host="1.2.3.4")
        info = ssh.get_system_info()
        assert "os" in info
        assert "hostname" in info

    def test_cleanup_removes_temp_key(self):
        ssh = SSHManager(host="1.2.3.4", key_content="-----BEGIN RSA-----\nfakekey")
        _ = ssh._get_key_path()
        assert ssh._temp_key_file is not None
        path = ssh._temp_key_file
        assert os.path.exists(path)
        ssh.cleanup()
        assert not os.path.exists(path)
        assert ssh._temp_key_file is None

    @patch("deploy.ssh_manager.subprocess.run")
    def test_upload_dir_rsync(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        ssh = SSHManager(host="1.2.3.4")
        ssh.upload_dir("/tmp/src", "/opt/dest")
        # First call should be rsync
        args = mock_run.call_args[0][0]
        assert "rsync" in args

    @patch("deploy.ssh_manager.subprocess.run")
    def test_upload_dir_rsync_fallback_to_scp(self, mock_run):
        # First call (rsync) fails, second call (scp) succeeds
        mock_run.side_effect = [
            MagicMock(stdout="", stderr="not found", returncode=1),
            MagicMock(stdout="", stderr="", returncode=0),
        ]
        ssh = SSHManager(host="1.2.3.4")
        ssh.upload_dir("/tmp/src", "/opt/dest")
        assert mock_run.call_count == 2


# ── Deployer Tests ───────────────────────────────────────────

class TestCreateArchive:
    """Test archive creation."""

    def test_creates_tarball(self, tmp_path):
        output = tmp_path / "test.tar.gz"
        # Create a minimal fake project structure
        with patch("deploy.deployer.BRAIN_DIR", str(tmp_path)):
            # Create some files
            (tmp_path / "main.py").write_text("print('hello')")
            (tmp_path / "config.py").write_text("x=1")
            
            result = create_archive(str(output))
            assert os.path.exists(result)
            import tarfile
            with tarfile.open(result) as tar:
                names = tar.getnames()
                assert "main.py" in names
                assert "config.py" in names

    def test_excludes_patterns(self, tmp_path):
        output = tmp_path / "test.tar.gz"
        with patch("deploy.deployer.BRAIN_DIR", str(tmp_path)):
            (tmp_path / "main.py").write_text("x=1")
            (tmp_path / "__pycache__").mkdir()
            (tmp_path / ".git").mkdir()
            (tmp_path / "vault").mkdir()
            
            result = create_archive(str(output))
            import tarfile
            with tarfile.open(result) as tar:
                names = tar.getnames()
                assert "main.py" in names
                assert "__pycache__" not in names
                assert ".git" not in names
                assert "vault" not in names


class TestBuildCronEntry:
    """Test cron entry building."""

    def test_default_config(self):
        c = VPSConfig(host="test.com")
        entry = _build_cron_entry(c)
        assert "0 */6 * * *" in entry
        assert "agent-brain" in entry
        assert "--auto" in entry
        assert "--rounds 3" in entry

    def test_custom_schedule(self):
        c = VPSConfig(host="test.com", schedule_cron="0 0 * * *", rounds_per_run=5)
        entry = _build_cron_entry(c)
        assert "0 0 * * *" in entry
        assert "--rounds 5" in entry

    def test_evolve_flag(self):
        c = VPSConfig(host="test.com", auto_evolve=True)
        entry = _build_cron_entry(c)
        assert "--evolve" in entry

    def test_no_evolve_flag(self):
        c = VPSConfig(host="test.com", auto_evolve=False)
        entry = _build_cron_entry(c)
        assert "--evolve" not in entry


class TestDeploy:
    """Test deployment orchestration."""

    def test_no_host_raises(self):
        config = VPSConfig(host="")
        with pytest.raises(DeployError, match="No VPS host"):
            deploy(config=config)

    @patch("deploy.deployer.SSHManager")
    @patch("deploy.deployer.create_archive")
    @patch("deploy.deployer.save_config")
    def test_dry_run(self, mock_save, mock_archive, mock_ssh_cls, tmp_path):
        archive = tmp_path / "test.tar.gz"
        archive.write_bytes(b"fake")
        mock_archive.return_value = str(archive)
        mock_ssh = MagicMock()
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        result = deploy(config=config, dry_run=True)

        assert result["status"] == "success"
        # SSH run should NOT have been called
        mock_ssh.run.assert_not_called()
        mock_ssh.upload_file.assert_not_called()

    @patch("deploy.deployer.SSHManager")
    @patch("deploy.deployer.create_archive")
    @patch("deploy.deployer.save_config")
    def test_full_deploy(self, mock_save, mock_archive, mock_ssh_cls, tmp_path):
        archive = tmp_path / "test.tar.gz"
        archive.write_bytes(b"fake")
        mock_archive.return_value = str(archive)

        mock_ssh = MagicMock()
        mock_ssh.test_connection.return_value = True
        mock_ssh.run.return_value = {"stdout": "OK\n", "stderr": "", "returncode": 0}
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        result = deploy(config=config)

        assert result["status"] == "success"
        assert mock_ssh.test_connection.called
        assert mock_ssh.upload_file.called
        step_names = [s["name"] for s in result["steps"]]
        assert "test_connection" in step_names
        assert "upload" in step_names
        assert "install_deps" in step_names
        assert "verify" in step_names

    @patch("deploy.deployer.SSHManager")
    @patch("deploy.deployer.create_archive")
    @patch("deploy.deployer.save_config")
    def test_deploy_skip_install(self, mock_save, mock_archive, mock_ssh_cls, tmp_path):
        archive = tmp_path / "test.tar.gz"
        archive.write_bytes(b"fake")
        mock_archive.return_value = str(archive)

        mock_ssh = MagicMock()
        mock_ssh.test_connection.return_value = True
        mock_ssh.run.return_value = {"stdout": "OK\n", "stderr": "", "returncode": 0}
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        result = deploy(config=config, skip_install=True)

        assert result["status"] == "success"
        step_names = [s["name"] for s in result["steps"]]
        assert "install_deps" not in step_names

    @patch("deploy.deployer.SSHManager")
    @patch("deploy.deployer.create_archive")
    @patch("deploy.deployer.save_config")
    def test_deploy_connection_failure(self, mock_save, mock_archive, mock_ssh_cls, tmp_path):
        archive = tmp_path / "test.tar.gz"
        archive.write_bytes(b"fake")
        mock_archive.return_value = str(archive)

        mock_ssh = MagicMock()
        mock_ssh.test_connection.return_value = False
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="unreachable.com")
        result = deploy(config=config)

        assert result["status"] == "failed"
        assert "Cannot connect" in result["error"]

    @patch("deploy.deployer.SSHManager")
    @patch("deploy.deployer.create_archive")
    @patch("deploy.deployer.save_config")
    def test_deploy_with_vault(self, mock_save, mock_archive, mock_ssh_cls, tmp_path):
        archive = tmp_path / "test.tar.gz"
        archive.write_bytes(b"fake")
        mock_archive.return_value = str(archive)

        mock_ssh = MagicMock()
        mock_ssh.test_connection.return_value = True
        mock_ssh.run.return_value = {"stdout": "OK\n", "stderr": "", "returncode": 0}
        mock_ssh_cls.return_value = mock_ssh

        mock_vault = MagicMock()
        mock_vault.retrieve.return_value = "-----BEGIN RSA-----\nfakekey"

        config = VPSConfig(host="1.2.3.4")
        result = deploy(config=config, vault=mock_vault)

        assert result["status"] == "success"
        mock_vault.retrieve.assert_called_with("vps_ssh_key")
        mock_ssh_cls.assert_called_with(
            host="1.2.3.4",
            user="agent-brain",
            port=22,
            key_content="-----BEGIN RSA-----\nfakekey",
        )


class TestSchedule:
    """Test schedule management."""

    @patch("deploy.deployer.SSHManager")
    def test_setup_schedule(self, mock_ssh_cls):
        mock_ssh = MagicMock()
        mock_ssh.run.return_value = {"stdout": "agent-brain", "stderr": "", "returncode": 0}
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        result = setup_schedule(config=config)

        assert result["status"] == "success"
        assert result["verified"] is True
        assert mock_ssh.run.called

    @patch("deploy.deployer.SSHManager")
    def test_setup_schedule_no_host(self, mock_ssh_cls):
        config = VPSConfig(host="")
        with pytest.raises(DeployError, match="No VPS configured"):
            setup_schedule(config=config)

    @patch("deploy.deployer.SSHManager")
    def test_remove_schedule(self, mock_ssh_cls):
        mock_ssh = MagicMock()
        mock_ssh.run.return_value = {"stdout": "", "stderr": "", "returncode": 0}
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        result = remove_schedule(config=config)
        assert result["status"] == "success"


class TestHealthCheck:
    """Test health checks."""

    @patch("deploy.deployer.save_config")
    @patch("deploy.deployer.SSHManager")
    def test_healthy_system(self, mock_ssh_cls, mock_save):
        mock_ssh = MagicMock()
        mock_ssh.test_connection.return_value = True
        
        # Different responses for different commands
        def run_side_effect(cmd, check=True, timeout=300):
            if "pgrep" in cmd:
                return {"stdout": "12345", "stderr": "", "returncode": 0}
            if "crontab" in cmd:
                return {"stdout": "agent-brain", "stderr": "", "returncode": 0}
            if "df" in cmd:
                return {"stdout": "45%", "stderr": "", "returncode": 0}
            if "find" in cmd:
                return {"stdout": "3", "stderr": "", "returncode": 0}
            if "cost_tracker" in cmd:
                return {"stdout": "1.23", "stderr": "", "returncode": 0}
            return {"stdout": "log.jsonl", "stderr": "", "returncode": 0}

        mock_ssh.run.side_effect = run_side_effect
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        result = health_check(config=config)

        assert result["status"] == "healthy"
        assert result["ssh"] is True
        assert result["cron_active"] is True
        assert result["process_running"] is True
        assert result["outputs_last_24h"] == 3

    @patch("deploy.deployer.save_config")
    @patch("deploy.deployer.SSHManager")
    def test_unreachable(self, mock_ssh_cls, mock_save):
        mock_ssh = MagicMock()
        mock_ssh.test_connection.side_effect = SSHError("Connection refused")
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        result = health_check(config=config)
        assert result["status"] == "unreachable"


class TestGetRemoteLogs:
    """Test remote log fetching."""

    @patch("deploy.deployer.SSHManager")
    def test_get_logs(self, mock_ssh_cls):
        mock_ssh = MagicMock()
        mock_ssh.run.return_value = {
            "stdout": '{"timestamp": "2025-01-01", "score": 7.5}',
            "stderr": "",
            "returncode": 0,
        }
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        logs = get_remote_logs(config=config, lines=20)
        assert "score" in logs

    @patch("deploy.deployer.SSHManager")
    def test_get_logs_with_domain(self, mock_ssh_cls):
        mock_ssh = MagicMock()
        mock_ssh.run.return_value = {"stdout": "data", "stderr": "", "returncode": 0}
        mock_ssh_cls.return_value = mock_ssh

        config = VPSConfig(host="1.2.3.4")
        get_remote_logs(config=config, domain="crypto")
        
        # Verify the command included domain filter
        cmd = mock_ssh.run.call_args[0][0]
        assert "crypto" in cmd

    @patch("deploy.deployer.SSHManager")
    def test_get_logs_error(self, mock_ssh_cls):
        mock_ssh = MagicMock()
        mock_ssh_cls.return_value = mock_ssh
        mock_ssh.run.side_effect = SSHError("timeout")

        config = VPSConfig(host="1.2.3.4")
        logs = get_remote_logs(config=config)
        assert "Error" in logs
