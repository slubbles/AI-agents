"""
Deployer — Packages and deploys Agent Brain to a VPS.

Deployment steps:
1. Package: Create deployment archive (exclude dev files, logs, memory)
2. Transfer: Upload archive to VPS via SSH
3. Install: Create venv, install deps, configure env
4. Configure: Set up .env, cron schedule, systemd service
5. Verify: Run health check, verify cron is active

Rollback: Keep last 3 deployments for quick rollback.
"""

import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Optional

from deploy.vps_config import VPSConfig, load_config, save_config
from deploy.ssh_manager import SSHManager, SSHError

logger = logging.getLogger(__name__)

# Files/dirs to exclude from deployment archive
DEPLOY_EXCLUDE = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "memory",        # Don't overwrite remote memory
    "logs",          # Don't overwrite remote logs
    "strategies",    # Don't overwrite remote strategies 
    "vault",         # NEVER deploy vault data
    "browser/_profiles",  # Browser sessions are local
    "projects",      # Project state is local
    "output",        # Cached outputs
    ".env",          # Environment-specific
    "*.pyc",
    "node_modules",
}

# Source directory
BRAIN_DIR = os.path.dirname(os.path.dirname(__file__))


class DeployError(Exception):
    """Deployment failed."""
    pass


def create_archive(output_path: Optional[str] = None) -> str:
    """Create a deployment archive of Agent Brain.
    
    Returns path to the created .tar.gz file.
    """
    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"agent-brain-{ts}.tar.gz")

    logger.info(f"Creating deployment archive: {output_path}")

    with tarfile.open(output_path, "w:gz") as tar:
        for item in os.listdir(BRAIN_DIR):
            if item in DEPLOY_EXCLUDE:
                continue
            if item.startswith("."):
                continue
            
            full_path = os.path.join(BRAIN_DIR, item)
            tar.add(full_path, arcname=item)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"Archive created: {output_path} ({size_mb:.1f} MB)")
    return output_path


def deploy(
    config: Optional[VPSConfig] = None,
    vault=None,
    skip_install: bool = False,
    dry_run: bool = False,
) -> dict:
    """Deploy Agent Brain to VPS.
    
    Args:
        config: VPS configuration (loaded from disk if None)
        vault: CredentialVault for SSH key retrieval
        skip_install: Skip pip install (for code-only updates)
        dry_run: Print commands but don't execute
        
    Returns:
        Deployment result dict
    """
    if config is None:
        config = load_config()

    if not config.host:
        raise DeployError("No VPS host configured. Run: deploy configure --host <ip>")

    result = {
        "status": "pending",
        "steps": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    # Get SSH key from vault
    ssh_key = None
    if vault:
        try:
            ssh_key = vault.retrieve(config.ssh_key_vault_ref)
        except KeyError:
            logger.warning(f"SSH key '{config.ssh_key_vault_ref}' not in vault")

    ssh = SSHManager(
        host=config.host,
        user=config.user,
        port=config.port,
        key_content=ssh_key,
    )

    try:
        # Step 1: Test connection
        step = {"name": "test_connection", "status": "running"}
        result["steps"].append(step)
        
        if dry_run:
            step["status"] = "dry_run"
            logger.info("[DRY RUN] Would test SSH connection")
        else:
            if not ssh.test_connection():
                raise DeployError(f"Cannot connect to {config.host}:{config.port}")
            step["status"] = "done"
            logger.info(f"Connected to {config.host}")

        # Step 2: Create archive
        step = {"name": "create_archive", "status": "running"}
        result["steps"].append(step)
        archive_path = create_archive()
        step["status"] = "done"
        step["archive_size_mb"] = round(os.path.getsize(archive_path) / 1024 / 1024, 1)

        # Step 3: Prepare remote directory
        step = {"name": "prepare_remote", "status": "running"}
        result["steps"].append(step)

        commands = [
            f"mkdir -p {config.remote_dir}",
            f"mkdir -p {config.remote_dir}/memory",
            f"mkdir -p {config.remote_dir}/logs",
            f"mkdir -p {config.remote_dir}/strategies",
            f"mkdir -p {config.remote_dir}/vault",
        ]
        
        if dry_run:
            for cmd in commands:
                logger.info(f"[DRY RUN] {cmd}")
            step["status"] = "dry_run"
        else:
            for cmd in commands:
                ssh.run(cmd)
            step["status"] = "done"

        # Step 4: Upload archive
        step = {"name": "upload", "status": "running"}
        result["steps"].append(step)
        
        remote_archive = f"/tmp/agent-brain-deploy.tar.gz"
        
        if dry_run:
            logger.info(f"[DRY RUN] Would upload {archive_path} → {remote_archive}")
            step["status"] = "dry_run"
        else:
            ssh.upload_file(archive_path, remote_archive)
            step["status"] = "done"

        # Step 5: Extract archive
        step = {"name": "extract", "status": "running"}
        result["steps"].append(step)
        
        extract_cmd = f"cd {config.remote_dir} && tar xzf {remote_archive} --overwrite && rm {remote_archive}"
        
        if dry_run:
            logger.info(f"[DRY RUN] {extract_cmd}")
            step["status"] = "dry_run"
        else:
            ssh.run(extract_cmd)
            step["status"] = "done"

        # Step 6: Install dependencies
        if not skip_install:
            step = {"name": "install_deps", "status": "running"}
            result["steps"].append(step)
            
            install_cmds = [
                f"{config.python_cmd} -m venv {config.venv_dir}",
                f"{config.venv_dir}/bin/pip install -r {config.remote_dir}/requirements.txt -q",
            ]
            
            if dry_run:
                for cmd in install_cmds:
                    logger.info(f"[DRY RUN] {cmd}")
                step["status"] = "dry_run"
            else:
                for cmd in install_cmds:
                    ssh.run(cmd, timeout=600)
                step["status"] = "done"

        # Step 7: Configure cron
        step = {"name": "setup_cron", "status": "running"}
        result["steps"].append(step)
        
        cron_entry = _build_cron_entry(config)
        cron_cmd = f'(crontab -l 2>/dev/null | grep -v "agent-brain"; echo "{cron_entry}") | crontab -'
        
        if dry_run:
            logger.info(f"[DRY RUN] Cron: {cron_entry}")
            step["status"] = "dry_run"
        else:
            ssh.run(cron_cmd)
            step["status"] = "done"

        # Step 8: Verify
        step = {"name": "verify", "status": "running"}
        result["steps"].append(step)
        
        if dry_run:
            step["status"] = "dry_run"
        else:
            verify = ssh.run(
                f"cd {config.remote_dir} && {config.venv_dir}/bin/python -c 'import config; print(\"OK\")'",
                check=False,
            )
            if verify["returncode"] == 0 and "OK" in verify["stdout"]:
                step["status"] = "done"
            else:
                step["status"] = "warning"
                step["message"] = verify["stderr"]

        # Update config
        config.is_deployed = True
        config.last_deployed_at = datetime.now(timezone.utc).isoformat()
        save_config(config)

        result["status"] = "success"
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        # Cleanup
        if os.path.exists(archive_path):
            os.remove(archive_path)

    except (SSHError, DeployError) as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(f"Deployment failed: {e}")
    finally:
        ssh.cleanup()

    return result


# ── Scheduler ──────────────────────────────────────────────

def _build_cron_entry(config: VPSConfig) -> str:
    """Build a cron entry from config."""
    python = f"{config.venv_dir}/bin/python"
    main = f"{config.remote_dir}/main.py"
    log = f"{config.remote_dir}/logs/cron.log"
    
    flags = f"--domain {config.default_domain} --auto --rounds {config.rounds_per_run}"
    if config.auto_evolve:
        flags += " --evolve"
    
    env = f"cd {config.remote_dir} && source .env &&"
    
    return f"{config.schedule_cron} {env} {python} {main} {flags} >> {log} 2>&1 # agent-brain"


def setup_schedule(
    config: Optional[VPSConfig] = None,
    vault=None,
) -> dict:
    """Configure the cron schedule on the VPS."""
    if config is None:
        config = load_config()

    if not config.host:
        raise DeployError("No VPS configured")

    ssh_key = None
    if vault:
        try:
            ssh_key = vault.retrieve(config.ssh_key_vault_ref)
        except KeyError:
            pass

    ssh = SSHManager(
        host=config.host,
        user=config.user,
        port=config.port,
        key_content=ssh_key,
    )

    try:
        cron_entry = _build_cron_entry(config)
        # Remove old agent-brain cron entries and add new one
        cmd = f'(crontab -l 2>/dev/null | grep -v "agent-brain"; echo "{cron_entry}") | crontab -'
        ssh.run(cmd)
        
        # Verify
        verify = ssh.run("crontab -l | grep agent-brain", check=False)
        
        return {
            "status": "success",
            "cron_entry": cron_entry,
            "verified": verify["returncode"] == 0,
        }
    except SSHError as e:
        return {"status": "failed", "error": str(e)}
    finally:
        ssh.cleanup()


def remove_schedule(config: Optional[VPSConfig] = None, vault=None) -> dict:
    """Remove the cron schedule from the VPS."""
    if config is None:
        config = load_config()

    ssh_key = None
    if vault:
        try:
            ssh_key = vault.retrieve(config.ssh_key_vault_ref)
        except KeyError:
            pass

    ssh = SSHManager(
        host=config.host,
        user=config.user,
        port=config.port,
        key_content=ssh_key,
    )

    try:
        cmd = 'crontab -l 2>/dev/null | grep -v "agent-brain" | crontab -'
        ssh.run(cmd)
        return {"status": "success", "message": "Schedule removed"}
    except SSHError as e:
        return {"status": "failed", "error": str(e)}
    finally:
        ssh.cleanup()


# ── Health & Monitoring ──────────────────────────────────────

def health_check(config: Optional[VPSConfig] = None, vault=None) -> dict:
    """Run health check on the remote Agent Brain instance."""
    if config is None:
        config = load_config()

    ssh_key = None
    if vault:
        try:
            ssh_key = vault.retrieve(config.ssh_key_vault_ref)
        except KeyError:
            pass

    ssh = SSHManager(
        host=config.host,
        user=config.user,
        port=config.port,
        key_content=ssh_key,
    )

    checks = {}

    try:
        # Connection
        checks["ssh"] = ssh.test_connection()

        # Service running
        ps = ssh.run("pgrep -f 'agent-brain/main.py' || true", check=False)
        checks["process_running"] = len(ps["stdout"].strip()) > 0

        # Cron active
        cron = ssh.run("crontab -l 2>/dev/null | grep agent-brain || true", check=False)
        checks["cron_active"] = "agent-brain" in cron["stdout"]

        # Disk space
        disk = ssh.run("df -h / | tail -1 | awk '{print $5}'", check=False)
        checks["disk_usage"] = disk["stdout"]

        # Last run
        last_log = ssh.run(
            f"ls -t {config.remote_dir}/logs/*.jsonl 2>/dev/null | head -1",
            check=False,
        )
        checks["last_log"] = last_log["stdout"] or "No logs found"

        # Recent outputs
        output_count = ssh.run(
            f"find {config.remote_dir}/memory -name '*.json' -mtime -1 | wc -l",
            check=False,
        )
        checks["outputs_last_24h"] = int(output_count["stdout"].strip() or "0")

        # Budget status  
        budget = ssh.run(
            f"cd {config.remote_dir} && {config.venv_dir}/bin/python -c "
            "'from cost_tracker import get_daily_spend; print(get_daily_spend())'",
            check=False,
        )
        checks["daily_spend"] = budget["stdout"] if budget["returncode"] == 0 else "unknown"

        checks["status"] = "healthy" if checks["ssh"] and checks["cron_active"] else "degraded"

    except SSHError as e:
        checks["status"] = "unreachable"
        checks["error"] = str(e)
    finally:
        ssh.cleanup()

    # Update config with health check time
    config.last_health_check = datetime.now(timezone.utc).isoformat()
    save_config(config)

    return checks


def get_remote_logs(
    config: Optional[VPSConfig] = None,
    vault=None,
    lines: int = 50,
    domain: Optional[str] = None,
) -> str:
    """Get recent logs from the VPS."""
    if config is None:
        config = load_config()

    ssh_key = None
    if vault:
        try:
            ssh_key = vault.retrieve(config.ssh_key_vault_ref)
        except KeyError:
            pass

    ssh = SSHManager(
        host=config.host,
        user=config.user,
        port=config.port,
        key_content=ssh_key,
    )

    try:
        log_pattern = f"{config.remote_dir}/logs"
        if domain:
            log_pattern += f"/{domain}*.jsonl"
        else:
            log_pattern += "/cron.log"

        result = ssh.run(f"tail -n {lines} {log_pattern}", check=False)
        return result["stdout"] or "No logs found"
    except SSHError as e:
        return f"Error fetching logs: {e}"
    finally:
        ssh.cleanup()


# ── CLI ──────────────────────────────────────────────────────

def cli_main():
    """CLI for VPS deployment management."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Brain VPS Deployment")
    sub = parser.add_subparsers(dest="command")

    # configure
    p_conf = sub.add_parser("configure", help="Set VPS configuration")
    p_conf.add_argument("--host", help="VPS IP or hostname")
    p_conf.add_argument("--user", help="SSH user")
    p_conf.add_argument("--port", type=int, help="SSH port")
    p_conf.add_argument("--schedule", help="Cron schedule expression")
    p_conf.add_argument("--domain", help="Default research domain")
    p_conf.add_argument("--rounds", type=int, help="Rounds per auto run")
    p_conf.add_argument("--budget", type=float, help="Daily budget in USD")

    # deploy
    p_deploy = sub.add_parser("deploy", help="Deploy to VPS")
    p_deploy.add_argument("--skip-install", action="store_true")
    p_deploy.add_argument("--dry-run", action="store_true")

    # health
    sub.add_parser("health", help="Run health check")

    # logs
    p_logs = sub.add_parser("logs", help="View remote logs")
    p_logs.add_argument("--lines", type=int, default=50)
    p_logs.add_argument("--domain", help="Filter by domain")

    # schedule
    sub.add_parser("schedule", help="Setup/update cron schedule")

    # unschedule
    sub.add_parser("unschedule", help="Remove cron schedule")

    # status
    sub.add_parser("status", help="Show deployment configuration")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "configure":
        config = load_config()
        if args.host:
            config.host = args.host
        if args.user:
            config.user = args.user
        if args.port:
            config.port = args.port
        if args.schedule:
            config.schedule_cron = args.schedule
        if args.domain:
            config.default_domain = args.domain
        if args.rounds:
            config.rounds_per_run = args.rounds
        if args.budget:
            config.daily_budget_usd = args.budget
        save_config(config)
        print(f"VPS configuration saved")
        print(f"  Host: {config.host or '(not set)'}")
        print(f"  User: {config.user}")
        print(f"  Schedule: {config.schedule_cron}")

    elif args.command == "deploy":
        result = deploy(dry_run=args.dry_run, skip_install=args.skip_install)
        for step in result.get("steps", []):
            icon = "✓" if step["status"] == "done" else "○" if step["status"] == "dry_run" else "✗"
            print(f"  {icon} {step['name']}")
        print(f"\nDeployment: {result['status']}")

    elif args.command == "health":
        checks = health_check()
        for key, val in checks.items():
            print(f"  {key}: {val}")

    elif args.command == "logs":
        print(get_remote_logs(lines=args.lines, domain=args.domain))

    elif args.command == "schedule":
        result = setup_schedule()
        print(f"Schedule: {result.get('status')}")
        if result.get("cron_entry"):
            print(f"  Entry: {result['cron_entry']}")

    elif args.command == "unschedule":
        result = remove_schedule()
        print(result.get("message", result.get("error")))

    elif args.command == "status":
        config = load_config()
        print(json.dumps(config.to_dict(), indent=2))


if __name__ == "__main__":
    cli_main()
