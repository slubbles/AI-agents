"""
Domain Goals — What The User Actually Wants

The system's biggest failure mode: researching academically interesting things
that don't serve the user's actual purpose. This module stores per-domain goals
so every question generated and every research cycle is DIRECTED at what matters.

A goal answers: "Why do you care about this domain? What are you trying to achieve?"

Example:
  Domain: productized-services
  Goal: "I want to sell productized Next.js landing page services to employers
         on OnlineJobsPH. I need intelligence about pricing, pain points,
         competitor gaps, and pitch angles."

Without this, the question generator produces generic academic research.
With this, every question serves the user's actual objective.

Storage: strategies/{domain}/_goal.json
"""

import json
import os
from datetime import datetime, timezone

from utils.atomic_write import atomic_json_write

STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")


def _goal_path(domain: str) -> str:
    """Path to a domain's goal file."""
    return os.path.join(STRATEGIES_DIR, domain, "_goal.json")


def set_goal(domain: str, goal: str) -> dict:
    """
    Set or update the goal/intent for a domain.
    
    Args:
        domain: The research domain
        goal: Free-text description of what the user wants to achieve
        
    Returns:
        The saved goal record
    """
    path = _goal_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Load existing to preserve history
    existing = None
    if os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    
    record = {
        "goal": goal.strip(),
        "domain": domain,
        "set_at": existing["set_at"] if existing else now,
        "updated_at": now,
    }
    
    # Track previous goals if updated
    if existing and existing.get("goal") != goal.strip():
        history = existing.get("previous_goals", [])
        history.append({
            "goal": existing["goal"],
            "replaced_at": now,
        })
        # Keep last 5 previous goals
        record["previous_goals"] = history[-5:]
    
    atomic_json_write(path, record)
    
    return record


def get_goal(domain: str) -> str | None:
    """
    Get the current goal for a domain.
    
    Returns:
        The goal text, or None if no goal is set.
    """
    path = _goal_path(domain)
    if not os.path.exists(path):
        return None
    
    try:
        with open(path) as f:
            data = json.load(f)
        return data.get("goal")
    except (json.JSONDecodeError, OSError):
        return None


def get_goal_record(domain: str) -> dict | None:
    """
    Get the full goal record including metadata.
    
    Returns:
        Full record dict, or None if no goal is set.
    """
    path = _goal_path(domain)
    if not os.path.exists(path):
        return None
    
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_goals() -> dict[str, str]:
    """
    List all domain goals.
    
    Returns:
        Dict mapping domain name → goal text
    """
    goals = {}
    if not os.path.exists(STRATEGIES_DIR):
        return goals
    
    for domain_dir in sorted(os.listdir(STRATEGIES_DIR)):
        domain_path = os.path.join(STRATEGIES_DIR, domain_dir)
        if not os.path.isdir(domain_path):
            continue
        goal = get_goal(domain_dir)
        if goal:
            goals[domain_dir] = goal
    
    return goals


def clear_goal(domain: str) -> bool:
    """Remove a domain's goal. Returns True if a goal was removed."""
    path = _goal_path(domain)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
