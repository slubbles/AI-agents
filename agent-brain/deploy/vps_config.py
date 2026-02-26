"""
VPS Configuration — Defines VPS connection and deployment settings.

Stored in deploy/vps_config.json (encrypted fields in vault).
This module handles config loading/saving with sensible defaults.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

from utils.atomic_write import atomic_json_write

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "vps_config.json")

# Default values
DEFAULT_REMOTE_DIR = "/opt/agent-brain"
DEFAULT_PYTHON = "python3.12"
DEFAULT_SCHEDULE = "0 */6 * * *"  # Every 6 hours
DEFAULT_MAX_DAILY_RUNS = 8
DEFAULT_LOG_RETENTION_DAYS = 30


@dataclass
class VPSConfig:
    """VPS connection and deployment configuration."""
    
    # Connection
    host: str = ""
    port: int = 22
    user: str = "agent-brain"
    
    # SSH auth — actual keys stored in vault, these are just references
    ssh_key_vault_ref: str = "vps_ssh_key"  # Vault key for SSH private key
    
    # Deployment paths
    remote_dir: str = DEFAULT_REMOTE_DIR
    python_cmd: str = DEFAULT_PYTHON
    venv_dir: str = "/opt/agent-brain/venv"
    
    # Scheduling
    schedule_cron: str = DEFAULT_SCHEDULE
    max_daily_runs: int = DEFAULT_MAX_DAILY_RUNS
    auto_evolve: bool = True  # Run with --evolve flag
    default_domain: str = "general"
    domains: list[str] = field(default_factory=lambda: ["general"])
    rounds_per_run: int = 3
    
    # Monitoring
    health_check_url: Optional[str] = None
    alert_on_failure: bool = True
    log_retention_days: int = DEFAULT_LOG_RETENTION_DAYS
    
    # Safety
    daily_budget_usd: float = 5.0
    require_approval: bool = True  # Require --approve for strategy changes
    
    # State
    is_deployed: bool = False
    last_deployed_at: Optional[str] = None
    last_health_check: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VPSConfig":
        # Filter to only known fields
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def load_config() -> VPSConfig:
    """Load VPS config from disk, or return defaults."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        return VPSConfig.from_dict(data)
    return VPSConfig()


def save_config(config: VPSConfig) -> None:
    """Save VPS config to disk."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    atomic_json_write(CONFIG_PATH, config.to_dict())
