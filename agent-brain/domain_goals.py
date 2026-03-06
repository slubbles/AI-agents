"""
Domain Goals — Structured Goal Record (Lifebook-inspired Framework)

The system's biggest failure mode: researching academically interesting things
that don't serve the user's actual purpose. This module stores per-domain goals
so every question generated and every research cycle is DIRECTED at what matters.

Goal structure (mirrors the architect's personal goal-setting methodology):
  what_i_want      — Desired outcome + success state
  what_i_dont_want — Constraints, anti-patterns to avoid, failure modes
  solution         — The strategic approach to get there
  goal             — Single measurable target sentence ("the goal")
  objectives       — Numbered sub-goals that, when all done, = goal achieved
  monthly_priority — The one thing to focus on this month
  task_queue       — Specific next research tasks aligned to current objective

Backward compatible: get_goal() still returns a plain string (the "goal" field).
New: get_goal_record() returns the full structured record.

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
    Set or update the plain-text goal for a domain (backward-compat API).
    Preserves any existing structured fields (objectives, priorities, etc.).
    """
    existing = get_goal_record(domain) or {}
    return set_goal_structured(
        domain=domain,
        goal=goal,
        what_i_want=existing.get("what_i_want", ""),
        what_i_dont_want=existing.get("what_i_dont_want", ""),
        solution=existing.get("solution", ""),
        objectives=existing.get("objectives", []),
        monthly_priority=existing.get("monthly_priority", ""),
        task_queue=existing.get("task_queue", []),
    )


def set_goal_structured(
    domain: str,
    goal: str,
    what_i_want: str = "",
    what_i_dont_want: str = "",
    solution: str = "",
    objectives: list[str] | None = None,
    monthly_priority: str = "",
    task_queue: list[str] | None = None,
) -> dict:
    """
    Set or update the full structured goal record for a domain.

    The structured format mirrors the architect's goal-setting methodology:
      what_i_want      → desired outcome ("I want to sell productized services...")
      what_i_dont_want → failure modes to avoid ("I don't want generic research...")
      solution         → the strategic approach ("Build landing pages for OLJ employers")
      goal             → measurable 1-sentence target ("3 clients at $500/mo by Q2")
      objectives       → numbered sub-goals that together = goal achieved
      monthly_priority → the ONE thing to focus on this month
      task_queue       → specific next research tasks, ordered by priority
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
        "domain": domain,
        # Core goal fields
        "goal": goal.strip(),
        "what_i_want": what_i_want.strip(),
        "what_i_dont_want": what_i_dont_want.strip(),
        "solution": solution.strip(),
        # Execution breakdown
        "objectives": objectives or [],
        "monthly_priority": monthly_priority.strip(),
        "task_queue": task_queue or [],
        # Metadata
        "set_at": existing["set_at"] if existing else now,
        "updated_at": now,
    }

    # Track goal history when the goal sentence itself changes
    if existing and existing.get("goal") != goal.strip():
        history = existing.get("previous_goals", [])
        history.append({
            "goal": existing["goal"],
            "what_i_wanted": existing.get("what_i_want", ""),
            "replaced_at": now,
        })
        record["previous_goals"] = history[-5:]
    elif existing:
        record["previous_goals"] = existing.get("previous_goals", [])

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


# ── Objective helpers ────────────────────────────────────────────────

def add_objective(domain: str, objective: str) -> dict:
    """Append an objective to the domain's goal record."""
    record = get_goal_record(domain) or {}
    objs = record.get("objectives", [])
    if objective.strip() and objective.strip() not in objs:
        objs.append(objective.strip())
    return set_goal_structured(domain, goal=record.get("goal", ""),
                               objectives=objs,
                               what_i_want=record.get("what_i_want", ""),
                               what_i_dont_want=record.get("what_i_dont_want", ""),
                               solution=record.get("solution", ""),
                               monthly_priority=record.get("monthly_priority", ""),
                               task_queue=record.get("task_queue", []))


def complete_objective(domain: str, index: int) -> dict:
    """Mark objective at index as completed (prefix '✅ ')."""
    record = get_goal_record(domain) or {}
    objs = record.get("objectives", [])
    if 0 <= index < len(objs) and not objs[index].startswith("✅"):
        objs[index] = "✅ " + objs[index]
    return set_goal_structured(domain, goal=record.get("goal", ""),
                               objectives=objs,
                               what_i_want=record.get("what_i_want", ""),
                               what_i_dont_want=record.get("what_i_dont_want", ""),
                               solution=record.get("solution", ""),
                               monthly_priority=record.get("monthly_priority", ""),
                               task_queue=record.get("task_queue", []))


def set_monthly_priority(domain: str, priority: str) -> dict:
    """Set the current monthly focus for a domain."""
    record = get_goal_record(domain) or {}
    return set_goal_structured(domain, goal=record.get("goal", ""),
                               monthly_priority=priority,
                               what_i_want=record.get("what_i_want", ""),
                               what_i_dont_want=record.get("what_i_dont_want", ""),
                               solution=record.get("solution", ""),
                               objectives=record.get("objectives", []),
                               task_queue=record.get("task_queue", []))


def push_task(domain: str, task: str) -> dict:
    """Add a task to the domain's task queue."""
    record = get_goal_record(domain) or {}
    queue = record.get("task_queue", [])
    if task.strip() and task.strip() not in queue:
        queue.append(task.strip())
    return set_goal_structured(domain, goal=record.get("goal", ""),
                               task_queue=queue,
                               what_i_want=record.get("what_i_want", ""),
                               what_i_dont_want=record.get("what_i_dont_want", ""),
                               solution=record.get("solution", ""),
                               objectives=record.get("objectives", []),
                               monthly_priority=record.get("monthly_priority", ""))


def pop_task(domain: str) -> str | None:
    """Remove and return the first task in the queue (FIFO)."""
    record = get_goal_record(domain)
    if not record:
        return None
    queue = record.get("task_queue", [])
    if not queue:
        return None
    task = queue.pop(0)
    set_goal_structured(domain, goal=record.get("goal", ""),
                        task_queue=queue,
                        what_i_want=record.get("what_i_want", ""),
                        what_i_dont_want=record.get("what_i_dont_want", ""),
                        solution=record.get("solution", ""),
                        objectives=record.get("objectives", []),
                        monthly_priority=record.get("monthly_priority", ""))
    return task


def audit_goal(domain: str, audit_notes: str) -> dict:
    """
    Record an audit pass — what's working, what isn't, what to do next.
    Appended to an audit log inside the goal record.
    """
    record = get_goal_record(domain) or {}
    now = datetime.now(timezone.utc).isoformat()
    audit_log = record.get("audit_log", [])
    audit_log.append({"ts": now, "notes": audit_notes.strip()})
    record["audit_log"] = audit_log[-10:]  # keep last 10
    record["last_audited"] = now
    path = _goal_path(domain)
    atomic_json_write(path, record)
    return record


def get_active_objectives(domain: str) -> list[str]:
    """Return only objectives not yet marked complete."""
    record = get_goal_record(domain)
    if not record:
        return []
    return [o for o in record.get("objectives", []) if not o.startswith("✅")]


MIN_GOAL_LENGTH = 20  # Minimum chars for a meaningful goal
GOAL_QUALITY_KEYWORDS = [
    # Action-oriented words that indicate a clear goal
    "build", "sell", "launch", "create", "deploy", "find", "validate",
    "understand", "compare", "analyze", "improve", "automate", "generate",
    "acquire", "convert", "optimize", "identify", "research", "test",
]


def validate_goal(goal: str) -> dict:
    """
    Check if a goal is specific enough to direct research effectively.
    
    Returns:
        {"valid": bool, "score": float 0-1, "issues": [str], "suggestions": [str]}
    """
    issues = []
    suggestions = []

    text = goal.strip()
    if len(text) < MIN_GOAL_LENGTH:
        issues.append(f"Too short ({len(text)} chars) — needs at least {MIN_GOAL_LENGTH}")
        suggestions.append("Describe WHAT you want to achieve and WHY")

    # Check for action words
    lower = text.lower()
    has_action = any(kw in lower for kw in GOAL_QUALITY_KEYWORDS)
    if not has_action:
        issues.append("No actionable intent detected")
        suggestions.append("Start with what you want to DO: build, sell, find, validate, etc.")

    # Check for specificity signals
    has_specifics = any(marker in lower for marker in [
        "$", "%", "customer", "user", "product", "service", "market",
        "revenue", "landing page", "saas", "api", "tool", "audience",
    ])
    if not has_specifics and len(text) < 80:
        suggestions.append("Add specifics: who is the audience? what's the output? what metric matters?")

    # Score: 0-1
    score = 1.0
    if issues:
        score -= 0.3 * len(issues)
    if not has_action:
        score -= 0.2
    if not has_specifics:
        score -= 0.1
    score = max(0.0, min(1.0, score))

    return {
        "valid": len(issues) == 0,
        "score": round(score, 2),
        "issues": issues,
        "suggestions": suggestions,
    }


def require_goal(domain: str) -> str | None:
    """
    Get goal or return None with a printed warning for auto modes.
    Used by run_auto/orchestrate to enforce goal-directed research.
    """
    goal = get_goal(domain)
    if not goal:
        print(f"\n[GOAL] ⚠ No goal set for domain '{domain}'")
        print(f"  Research without a goal produces unfocused, academic results.")
        print(f"  Set one: python main.py --set-goal --domain {domain}")
        return None
    return goal


def clear_goal(domain: str) -> bool:
    """Remove a domain's goal. Returns True if a goal was removed."""
    path = _goal_path(domain)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
