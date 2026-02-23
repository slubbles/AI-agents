"""
Strategy Store (Layer 4 — Strategy Evolution)

Manages versioned strategy documents per agent per domain.
Supports:
- Version tracking with status (active, trial, pending, rolled_back)
- Active version pointer per agent+domain
- Performance tracking per strategy version
- Rollback to previous version
- Approval gate: new strategies start as 'pending' (human must approve)
- Safety: blocks strategies that score >20% below current best
"""

import json
import os
from datetime import datetime, timezone
from config import STRATEGY_DIR

# Safety threshold: block if new strategy avg score drops more than this fraction
SAFETY_DROP_THRESHOLD = 0.20  # 20%

# Minimum outputs under a trial strategy before evaluating it
TRIAL_PERIOD = 3


def _meta_path(domain: str) -> str:
    """Path to the domain's strategy metadata file."""
    return os.path.join(STRATEGY_DIR, domain, "_meta.json")


def _load_meta(domain: str) -> dict:
    """Load strategy metadata for a domain."""
    path = _meta_path(domain)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _save_meta(domain: str, meta: dict):
    """Save strategy metadata for a domain."""
    strategy_dir = os.path.join(STRATEGY_DIR, domain)
    os.makedirs(strategy_dir, exist_ok=True)
    path = _meta_path(domain)
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)


def _load_strategy_file(agent_role: str, domain: str, version: str) -> dict | None:
    """Load a specific strategy version file."""
    strategy_dir = os.path.join(STRATEGY_DIR, domain)
    filepath = os.path.join(strategy_dir, f"{agent_role}_{version}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath) as f:
        return json.load(f)


def get_active_version(agent_role: str, domain: str) -> str:
    """Get the active strategy version for an agent+domain. Returns 'default' if none."""
    meta = _load_meta(domain)
    key = f"{agent_role}_active"
    return meta.get(key, "default")


def set_active_version(agent_role: str, domain: str, version: str, status: str = "active"):
    """
    Set the active strategy version and its status.
    
    Status: 'active' (proven), 'trial' (being evaluated)
    """
    meta = _load_meta(domain)
    key = f"{agent_role}_active"
    status_key = f"{agent_role}_status"
    history_key = f"{agent_role}_history"

    # Track version history
    if history_key not in meta:
        meta[history_key] = []
    
    old_version = meta.get(key, "default")
    old_status = meta.get(status_key, "active")
    if old_version != version:
        meta[history_key].append({
            "version": old_version,
            "status": old_status,
            "replaced_at": datetime.now(timezone.utc).isoformat(),
        })

    meta[key] = version
    meta[status_key] = status
    meta[f"{agent_role}_updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_meta(domain, meta)


def get_strategy_status(agent_role: str, domain: str) -> str:
    """Get the status of the current active strategy. Returns 'active' or 'trial'."""
    meta = _load_meta(domain)
    return meta.get(f"{agent_role}_status", "active")


def get_strategy(agent_role: str, domain: str) -> tuple[str | None, str]:
    """
    Load the current active strategy for an agent+domain combo.
    
    Returns:
        (strategy_text or None, version_string)
    """
    active = get_active_version(agent_role, domain)

    if active == "default":
        # Check if there are any strategy files (backwards compat with Layer 3)
        strategy_dir = os.path.join(STRATEGY_DIR, domain)
        if not os.path.exists(strategy_dir):
            return None, "default"

        files = sorted([
            f for f in os.listdir(strategy_dir)
            if f.startswith(f"{agent_role}_v") and f.endswith(".json")
        ])

        if not files:
            return None, "default"

        # Migrate: set the latest as active
        latest = files[-1]
        filepath = os.path.join(strategy_dir, latest)
        with open(filepath) as f:
            data = json.load(f)
        version = data.get("version", "unknown")
        set_active_version(agent_role, domain, version, "active")
        return data.get("strategy"), version

    data = _load_strategy_file(agent_role, domain, active)
    if data is None:
        return None, "default"
    return data.get("strategy"), data.get("version", active)


def save_strategy(agent_role: str, domain: str, strategy_text: str, version: str,
                  reason: str = "", status: str = "trial") -> str:
    """
    Save a new strategy version. New strategies start as 'trial' by default.
    
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
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(filepath, "w") as f:
        json.dump(record, f, indent=2)

    # Set as active with trial status
    set_active_version(agent_role, domain, version, status)

    return filepath


def rollback(agent_role: str, domain: str) -> str | None:
    """
    Roll back to the previous strategy version.
    
    Returns:
        The version rolled back to, or None if no previous version exists.
    """
    meta = _load_meta(domain)
    history_key = f"{agent_role}_history"
    history = meta.get(history_key, [])

    if not history:
        return None

    # Pop the most recent previous version
    previous = history[-1]
    prev_version = previous["version"]

    if prev_version == "default":
        # Roll back to no custom strategy
        set_active_version(agent_role, domain, "default", "active")
        return "default"

    # Verify the strategy file exists
    data = _load_strategy_file(agent_role, domain, prev_version)
    if data is None:
        return None

    # Mark current as rolled_back in its file
    current_version = get_active_version(agent_role, domain)
    current_data = _load_strategy_file(agent_role, domain, current_version)
    if current_data:
        current_data["status"] = "rolled_back"
        current_data["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
        filepath = os.path.join(STRATEGY_DIR, domain, f"{agent_role}_{current_version}.json")
        with open(filepath, "w") as f:
            json.dump(current_data, f, indent=2)

    set_active_version(agent_role, domain, prev_version, "active")
    return prev_version


def get_strategy_performance(domain: str, strategy_version: str) -> dict:
    """
    Get performance stats for outputs produced under a specific strategy version.
    
    Returns:
        {count, avg_score, scores[], accepted, rejected}
    """
    # Import here to avoid circular imports
    from memory_store import load_outputs

    all_outputs = load_outputs(domain, min_score=0)
    matching = [
        o for o in all_outputs
        if o.get("strategy_version") == strategy_version
    ]

    if not matching:
        return {"count": 0, "avg_score": 0, "scores": [], "accepted": 0, "rejected": 0}

    scores = [o.get("overall_score", 0) for o in matching]
    return {
        "count": len(matching),
        "avg_score": sum(scores) / len(scores),
        "scores": scores,
        "accepted": sum(1 for o in matching if o.get("verdict") == "accept"),
        "rejected": sum(1 for o in matching if o.get("verdict") == "reject"),
    }


def evaluate_trial(agent_role: str, domain: str) -> dict:
    """
    Evaluate a trial strategy against the previous one.
    
    Returns:
        {
            "action": "confirm" | "rollback" | "continue_trial",
            "trial_version": str,
            "trial_performance": dict,
            "previous_version": str,
            "previous_performance": dict,
            "drop_pct": float | None,
            "reason": str,
        }
    """
    status = get_strategy_status(agent_role, domain)
    current = get_active_version(agent_role, domain)

    if status != "trial":
        return {
            "action": "no_trial",
            "reason": f"Strategy {current} is already confirmed (status: {status})",
        }

    # Get trial performance
    trial_perf = get_strategy_performance(domain, current)

    if trial_perf["count"] < TRIAL_PERIOD:
        return {
            "action": "continue_trial",
            "trial_version": current,
            "trial_performance": trial_perf,
            "reason": f"Trial needs {TRIAL_PERIOD - trial_perf['count']} more output(s) before evaluation",
        }

    # Find previous version
    meta = _load_meta(domain)
    history = meta.get(f"{agent_role}_history", [])
    prev_version = history[-1]["version"] if history else "default"
    prev_perf = get_strategy_performance(domain, prev_version)

    result = {
        "trial_version": current,
        "trial_performance": trial_perf,
        "previous_version": prev_version,
        "previous_performance": prev_perf,
        "drop_pct": None,
    }

    # If no previous data, confirm the trial (nothing to compare against)
    if prev_perf["count"] == 0:
        set_active_version(agent_role, domain, current, "active")
        result["action"] = "confirm"
        result["reason"] = "No previous strategy data — confirming trial as active"
        return result

    # Compare performance
    prev_avg = prev_perf["avg_score"]
    trial_avg = trial_perf["avg_score"]

    if prev_avg > 0:
        drop_pct = (prev_avg - trial_avg) / prev_avg
    else:
        drop_pct = 0

    result["drop_pct"] = drop_pct

    if drop_pct > SAFETY_DROP_THRESHOLD:
        # SAFETY: strategy is performing significantly worse → rollback
        rolled_to = rollback(agent_role, domain)
        result["action"] = "rollback"
        result["reason"] = (
            f"SAFETY ROLLBACK: Trial {current} avg {trial_avg:.1f} is {drop_pct:.0%} below "
            f"previous {prev_version} avg {prev_avg:.1f} (threshold: {SAFETY_DROP_THRESHOLD:.0%}). "
            f"Rolled back to {rolled_to}."
        )
    else:
        # Strategy is performing OK → confirm
        set_active_version(agent_role, domain, current, "active")
        result["action"] = "confirm"
        if drop_pct <= 0:
            result["reason"] = (
                f"Trial {current} avg {trial_avg:.1f} ≥ previous {prev_version} avg {prev_avg:.1f}. "
                f"Improvement: {abs(drop_pct):.0%}. Confirmed as active."
            )
        else:
            result["reason"] = (
                f"Trial {current} avg {trial_avg:.1f} is {drop_pct:.0%} below "
                f"previous {prev_version} avg {prev_avg:.1f} — within safety threshold. Confirmed."
            )

    return result


def get_version_history(agent_role: str, domain: str) -> list[dict]:
    """Get the full version history for an agent+domain."""
    meta = _load_meta(domain)
    history = meta.get(f"{agent_role}_history", [])
    current = {
        "version": get_active_version(agent_role, domain),
        "status": get_strategy_status(agent_role, domain),
    }
    return history + [current]


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


def list_pending(agent_role: str, domain: str) -> list[dict]:
    """List all pending (unapproved) strategies for an agent+domain."""
    strategy_dir = os.path.join(STRATEGY_DIR, domain)
    if not os.path.exists(strategy_dir):
        return []

    pending = []
    for fname in sorted(os.listdir(strategy_dir)):
        if not fname.startswith(f"{agent_role}_v") or not fname.endswith(".json"):
            continue
        filepath = os.path.join(strategy_dir, fname)
        with open(filepath) as f:
            data = json.load(f)
        if data.get("status") == "pending":
            pending.append(data)
    return pending


def approve_strategy(agent_role: str, domain: str, version: str) -> dict:
    """
    Approve a pending strategy — promotes it to 'trial' status.
    The system will then run it for TRIAL_PERIOD outputs before auto-confirming or rolling back.

    Returns:
        {"action": "approved"/"error", "reason": str}
    """
    data = _load_strategy_file(agent_role, domain, version)
    if data is None:
        return {"action": "error", "reason": f"Strategy {version} not found"}

    if data.get("status") != "pending":
        return {"action": "error", "reason": f"Strategy {version} is '{data.get('status')}', not 'pending'"}

    # Update the strategy file status
    data["status"] = "trial"
    data["approved_at"] = datetime.now(timezone.utc).isoformat()
    filepath = os.path.join(STRATEGY_DIR, domain, f"{agent_role}_{version}.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    # Set as active trial
    set_active_version(agent_role, domain, version, "trial")

    return {
        "action": "approved",
        "reason": f"Strategy {version} approved → now in trial (needs {TRIAL_PERIOD} outputs to confirm)",
    }


def reject_strategy(agent_role: str, domain: str, version: str) -> dict:
    """
    Reject a pending strategy — marks it as 'rejected', does not deploy.

    Returns:
        {"action": "rejected"/"error", "reason": str}
    """
    data = _load_strategy_file(agent_role, domain, version)
    if data is None:
        return {"action": "error", "reason": f"Strategy {version} not found"}

    if data.get("status") != "pending":
        return {"action": "error", "reason": f"Strategy {version} is '{data.get('status')}', not 'pending'"}

    data["status"] = "rejected"
    data["rejected_at"] = datetime.now(timezone.utc).isoformat()
    filepath = os.path.join(STRATEGY_DIR, domain, f"{agent_role}_{version}.json")
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return {"action": "rejected", "reason": f"Strategy {version} rejected — will not be deployed"}


def get_strategy_diff(agent_role: str, domain: str, version_a: str, version_b: str) -> dict:
    """
    Compare two strategy versions. Returns the strategy text of each for diffing.

    Returns:
        {"version_a": {version, strategy, created_at, status, reason},
         "version_b": {version, strategy, created_at, status, reason},
         "error": str or None}
    """
    data_a = _load_strategy_file(agent_role, domain, version_a)
    data_b = _load_strategy_file(agent_role, domain, version_b)

    if data_a is None and version_a != "default":
        return {"error": f"Version {version_a} not found"}
    if data_b is None and version_b != "default":
        return {"error": f"Version {version_b} not found"}

    def _extract(data, version):
        if data is None:
            return {"version": version, "strategy": "(default — built-in prompt)", "created_at": "N/A", "status": "active", "reason": "Original default strategy"}
        return {
            "version": data.get("version", version),
            "strategy": data.get("strategy", ""),
            "created_at": data.get("created_at", "?"),
            "status": data.get("status", "?"),
            "reason": data.get("reason", ""),
        }

    return {
        "version_a": _extract(data_a, version_a),
        "version_b": _extract(data_b, version_b),
        "error": None,
    }
