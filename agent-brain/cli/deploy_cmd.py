"""VPS deployment CLI commands."""

from config import DEFAULT_DOMAIN


def deploy(dry_run: bool = False):
    """Deploy Agent Brain to VPS, then auto-setup cron schedule."""
    print(f"\n{'='*60}")
    print(f"  VPS DEPLOYMENT {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}\n")

    try:
        from deploy.deployer import deploy as _deploy, setup_schedule
        from deploy.vps_config import load_config
        from cli.vault import get_vault
        vault = get_vault()

        result = _deploy(vault=vault, dry_run=dry_run)
        for step in result.get("steps", []):
            icon = "\u2713" if step["status"] == "done" else "\u25cb" if step["status"] == "dry_run" else "\u2717"
            extra = f" ({step['archive_size_mb']} MB)" if "archive_size_mb" in step else ""
            print(f"  {icon} {step['name']}{extra}")

        print(f"\n  Deployment: {result['status']}")
        if result.get("error"):
            print(f"  Error: {result['error']}")

        # Auto-setup cron schedule after successful deploy
        if result.get("status") == "success" and not dry_run:
            config = load_config()
            if config.host and config.schedule_cron:
                print(f"\n  Setting up cron schedule on VPS...")
                sched = setup_schedule(config=config, vault=vault)
                if sched.get("status") == "success":
                    print(f"  \u2713 Schedule configured: {sched.get('cron_entry', '')[:60]}")
                else:
                    print(f"  \u2717 Schedule failed: {sched.get('error', 'unknown')}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def health():
    """Run health check on remote VPS."""
    print(f"\n{'='*60}")
    print(f"  VPS HEALTH CHECK")
    print(f"{'='*60}\n")

    try:
        from deploy.deployer import health_check
        from cli.vault import get_vault
        vault = get_vault()

        checks = health_check(vault=vault)
        for key, val in checks.items():
            print(f"  {key}: {val}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def logs(domain: str = ""):
    """View remote VPS logs."""
    try:
        from deploy.deployer import get_remote_logs
        from cli.vault import get_vault
        vault = get_vault()

        log_output = get_remote_logs(vault=vault, domain=domain if domain != DEFAULT_DOMAIN else None)
        print(log_output)
    except Exception as e:
        print(f"  ERROR: {e}")


def schedule():
    """Setup cron schedule on VPS."""
    try:
        from deploy.deployer import setup_schedule
        from cli.vault import get_vault
        vault = get_vault()

        result = setup_schedule(vault=vault)
        print(f"  Schedule: {result.get('status')}")
        if result.get("cron_entry"):
            print(f"  Entry: {result['cron_entry']}")
    except Exception as e:
        print(f"  ERROR: {e}")


def unschedule():
    """Remove cron schedule from VPS."""
    try:
        from deploy.deployer import remove_schedule
        from cli.vault import get_vault
        vault = get_vault()

        result = remove_schedule(vault=vault)
        print(f"  {result.get('message', result.get('error'))}")
    except Exception as e:
        print(f"  ERROR: {e}")


def configure(host: str = "", user: str = ""):
    """Configure VPS connection."""
    print(f"\n{'='*60}")
    print(f"  VPS CONFIGURATION")
    print(f"{'='*60}\n")

    try:
        from deploy.vps_config import load_config, save_config

        config = load_config()
        if host:
            config.host = host
        if user:
            config.user = user

        save_config(config)
        print(f"  Host: {config.host or '(not set)'}")
        print(f"  User: {config.user}")
        print(f"  Port: {config.port}")
        print(f"  Schedule: {config.schedule_cron}")
        print(f"  Remote dir: {config.remote_dir}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
