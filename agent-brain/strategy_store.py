"""
Strategy Store
Manages versioned strategy documents per agent per domain.
"""

import json
import os
from datetime import datetime, timezone
from config import STRATEGY_DIR


def get_strategy(agent_role: str, domain: str) -> tuple[str | None, str]:
    """
    Load the current strategy for an agent+domain combo.
    
    Returns:
        (strategy_text or None, version_string)
    """
    strategy_dir = os.path.join(STRATEGY_DIR, domain)
    if not os.path.exists(strategy_dir):
        return None, "default"

    # Find the latest strategy file for this agent
    files = sorted([
        f for f in os.listdir(strategy_dir)
        if f.startswith(f"{agent_role}_v") and f.endswith(".json")
    ])

    if not files:
        return None, "default"

    latest = files[-1]
    filepath = os.path.join(strategy_dir, latest)
    with open(filepath) as f:
        data = json.load(f)

    return data.get("strategy"), data.get("version", "unknown")


def save_strategy(agent_role: str, domain: str, strategy_text: str, version: str, reason: str = "") -> str:
    """
    Save a new strategy version.
    
    Returns:
        Path to the saved file
    """
    strategy_dir = os.path.join(STRATEGY_DIR, domain)
    os.makedirs(strategy_dir, exist_ok=True)

    filename = f"{agent_role}_{version}.json"
    filepath = os.path.join(strategy_dir, filename)

    record = {
        "agent_role": agent_role,
        "domain": domain,
        "version": version,
        "strategy": strategy_text,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(filepath, "w") as f:
        json.dump(record, f, indent=2)

    return filepath


def list_versions(agent_role: str, domain: str) -> list[str]:
    """List all strategy versions for an agent+domain."""
    strategy_dir = os.path.join(STRATEGY_DIR, domain)
    if not os.path.exists(strategy_dir):
        return []

    return sorted([
        f.replace(f"{agent_role}_", "").replace(".json", "")
        for f in os.listdir(strategy_dir)
        if f.startswith(f"{agent_role}_v") and f.endswith(".json")
    ])
