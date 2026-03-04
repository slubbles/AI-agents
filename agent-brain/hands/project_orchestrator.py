"""
Large Project Orchestrator — Manages multi-phase projects end-to-end.

When the user says "build me a SaaS app" or "create a Next.js blog",
this orchestrator:

1. DECOMPOSE: Breaks the project into phases (architecture, setup, features, tests, deploy)
2. PLAN: Each phase is planned with the existing planner
3. EXECUTE: Phases execute sequentially, with validation gates between them
4. CHECKPOINT: Progress saved after each phase so work can resume
5. REVIEW: Human review points at critical phases (architecture, deploy)

This sits ABOVE hands/planner.py + hands/executor.py — it orchestrates them.

Key Design:
- Projects are persisted as JSON in projects/<project_id>/
- Each phase has: plan, execution results, validation results, status
- Failed phases can be retried without restarting the whole project
- Human review gates at phase boundaries (configurable)
"""

import json
import os
import re
import sys
import time
import hashlib
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json
from utils.atomic_write import atomic_json_write

from anthropic import Anthropic

logger = logging.getLogger(__name__)
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Lazy imports for testability (allows mocking)
_plan_task = None
_execute_task = None
_validate = None

def _get_plan_task():
    global _plan_task
    if _plan_task is None:
        from hands.planner import plan
        _plan_task = plan
    return _plan_task

def _get_execute_task():
    global _execute_task
    if _execute_task is None:
        from hands.executor import execute_plan
        _execute_task = execute_plan
    return _execute_task

def _get_validate():
    global _validate
    if _validate is None:
        from hands.validator import validate_execution
        _validate = validate_execution
    return _validate

# Directories
PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Constraints
MAX_PHASES = 12
MAX_TASKS_PER_PHASE = 15
MAX_TOTAL_TASKS = 100
HUMAN_REVIEW_PHASES = {"architecture", "deployment", "security"}


class PhaseStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REVIEW_NEEDED = "review_needed"


class ProjectStatus(str, Enum):
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================
# Project Decomposition
# ============================================================

DECOMPOSE_SYSTEM_PROMPT = """You are an expert software architect and project manager.
Your job is to decompose a large project into concrete phases and tasks.

Each phase should be independently executable and testable.
Order phases by dependency (foundations first, features second, polish last).

RULES:
1. Maximum {max_phases} phases
2. Maximum {max_tasks} tasks per phase
3. Each phase has a clear GATE CONDITION — what must be true before moving to next phase
4. Mark phases that need human review: architecture decisions, security config, deployment
5. Be specific — "create authentication" is too vague, "implement JWT auth with refresh tokens using Next-Auth" is correct
6. Include test tasks in each phase, not just at the end
7. Estimate hours realistically (for an automated coding agent, not a human)

OUTPUT FORMAT (strict JSON):
{{
    "project_name": "short-kebab-case-name",
    "summary": "1-2 sentence project description",
    "tech_stack": ["Next.js", "TypeScript", "Prisma", ...],
    "total_estimated_hours": 15,
    "phases": [
        {{
            "id": "phase-01-setup",
            "name": "Project Setup & Configuration",
            "description": "Initialize project, install dependencies, configure tooling",
            "order": 1,
            "estimated_hours": 2,
            "requires_human_review": false,
            "gate_condition": "Project runs with npm run dev, TypeScript compiles, ESLint passes",
            "tasks": [
                {{
                    "id": "task-01",
                    "description": "Create Next.js 14 project with TypeScript and Tailwind CSS",
                    "type": "execute",
                    "estimated_minutes": 10,
                    "depends_on": []
                }},
                {{
                    "id": "task-02",
                    "description": "Configure ESLint, Prettier, and TypeScript strict mode",
                    "type": "execute",
                    "depends_on": ["task-01"]
                }},
                {{
                    "id": "task-03",
                    "description": "Verify: npm run dev starts without errors, npm run lint passes",
                    "type": "validate",
                    "depends_on": ["task-02"]
                }}
            ]
        }}
    ]
}}

Task types:
- "execute": Create/modify files, run commands
- "validate": Run tests, check outputs
- "research": Look up documentation, find patterns
- "review": Needs human approval before proceeding
"""

DECOMPOSE_USER_PROMPT = """Decompose this project into phases and tasks:

PROJECT: {description}

Additional context:
- Working directory: {workspace_dir}
- Existing files: {existing_files}
- Constraints: {constraints}

Create a detailed, actionable phase breakdown."""


def decompose_project(
    description: str,
    workspace_dir: str = ".",
    constraints: str = "None",
    existing_files: str = "Empty project",
) -> dict:
    """Decompose a project description into phases and tasks.
    
    Returns the full project plan as a dict.
    """
    system = DECOMPOSE_SYSTEM_PROMPT.format(
        max_phases=MAX_PHASES,
        max_tasks=MAX_TASKS_PER_PHASE,
    )
    user = DECOMPOSE_USER_PROMPT.format(
        description=description,
        workspace_dir=workspace_dir,
        constraints=constraints,
        existing_files=existing_files,
    )

    _model = MODELS.get("planner", "claude-sonnet-4-20250514")
    response = create_message(
        client=client,
        model=_model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    text = response.content[0].text
    log_cost(
        model=_model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        agent_role="project_orchestrator",
        domain="system",
    )

    plan = extract_json(text)
    if not plan:
        raise ValueError("Failed to parse project decomposition from Claude response")

    # Validate constraints
    phases = plan.get("phases", [])
    if len(phases) > MAX_PHASES:
        plan["phases"] = phases[:MAX_PHASES]
        logger.warning(f"Truncated phases from {len(phases)} to {MAX_PHASES}")

    total_tasks = sum(len(p.get("tasks", [])) for p in plan["phases"])
    if total_tasks > MAX_TOTAL_TASKS:
        logger.warning(f"Project has {total_tasks} tasks (limit: {MAX_TOTAL_TASKS})")

    return plan


# ============================================================
# Project State Management
# ============================================================

def _project_id(name: str) -> str:
    """Generate a project ID from name + timestamp."""
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower())[:40]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{slug}-{ts}"


def _project_dir(project_id: str) -> str:
    """Get the directory for a project."""
    return os.path.join(PROJECTS_DIR, project_id)


def save_project(project: dict) -> None:
    """Save project state to disk."""
    project_id = project["project_id"]
    pdir = _project_dir(project_id)
    os.makedirs(pdir, exist_ok=True)
    
    filepath = os.path.join(pdir, "project.json")
    atomic_json_write(filepath, project, indent=2)
    logger.info(f"Project saved: {project_id}")


def load_project(project_id: str) -> Optional[dict]:
    """Load a project from disk."""
    filepath = os.path.join(_project_dir(project_id), "project.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath) as f:
        return json.load(f)


def list_projects() -> list[dict]:
    """List all projects with summary info."""
    projects = []
    if not os.path.exists(PROJECTS_DIR):
        return projects
    
    for name in sorted(os.listdir(PROJECTS_DIR)):
        pfile = os.path.join(PROJECTS_DIR, name, "project.json")
        if os.path.exists(pfile):
            try:
                with open(pfile) as f:
                    p = json.load(f)
                projects.append({
                    "project_id": p["project_id"],
                    "name": p.get("project_name", name),
                    "status": p.get("status", "unknown"),
                    "phases_completed": sum(
                        1 for ph in p.get("phases", [])
                        if ph.get("status") == PhaseStatus.COMPLETED
                    ),
                    "phases_total": len(p.get("phases", [])),
                    "created_at": p.get("created_at"),
                })
            except Exception as e:
                logger.warning(f"Failed to load project {name}: {e}")
    
    return projects


# ============================================================
# Project Execution Engine
# ============================================================

def create_project(description: str, workspace_dir: str = ".") -> dict:
    """Create a new project from a description.
    
    Steps:
    1. Decompose into phases/tasks
    2. Initialize project state
    3. Save to disk
    
    Returns the project dict.
    """
    # Scan existing files
    existing = "Empty project"
    if os.path.isdir(workspace_dir):
        from hands.constants import SKIP_DIRS as _SKIP_DIRS
        files = []
        for root, dirs, fnames in os.walk(workspace_dir):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in fnames[:50]:
                rel = os.path.relpath(os.path.join(root, fname), workspace_dir)
                files.append(rel)
        if files:
            existing = "\n".join(files[:100])

    # Decompose
    plan = decompose_project(
        description=description,
        workspace_dir=workspace_dir,
        existing_files=existing,
    )

    # Initialize project state
    project_id = _project_id(plan.get("project_name", "project"))
    project = {
        "project_id": project_id,
        "project_name": plan.get("project_name", "unnamed"),
        "description": description,
        "summary": plan.get("summary", ""),
        "tech_stack": plan.get("tech_stack", []),
        "total_estimated_hours": plan.get("total_estimated_hours", 0),
        "status": ProjectStatus.PLANNING,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": os.path.abspath(workspace_dir),
        "current_phase_index": 0,
        "phases": [],
        "execution_log": [],
    }

    # Initialize phases with status tracking
    for phase in plan.get("phases", []):
        phase["status"] = PhaseStatus.PENDING
        phase["started_at"] = None
        phase["completed_at"] = None
        phase["execution_results"] = []
        phase["validation_results"] = []
        phase["retry_count"] = 0
        
        # Initialize tasks
        for task in phase.get("tasks", []):
            task["status"] = PhaseStatus.PENDING
            task["result"] = None
            task["error"] = None
        
        project["phases"].append(phase)

    save_project(project)
    logger.info(f"Project created: {project_id} ({len(project['phases'])} phases)")
    return project


def execute_phase(
    project: dict,
    phase_index: int,
    workspace_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Execute a single phase of the project.
    
    1. Plans each task using hands/planner
    2. Executes using hands/executor
    3. Validates with hands/validator
    4. Updates project state
    
    Returns the updated phase dict.
    """
    phases = project.get("phases", [])
    if phase_index >= len(phases):
        raise ValueError(f"Phase index {phase_index} out of range ({len(phases)} phases)")

    phase = phases[phase_index]
    ws = workspace_dir or project.get("workspace_dir", ".")

    # Check if previous phases are done
    for i in range(phase_index):
        prev_status = phases[i].get("status")
        if prev_status not in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED):
            raise ValueError(
                f"Cannot execute phase {phase_index} — phase {i} ({phases[i]['name']}) "
                f"is {prev_status}"
            )

    # Check if human review is needed
    if phase.get("requires_human_review") and phase["status"] != PhaseStatus.REVIEW_NEEDED:
        phase["status"] = PhaseStatus.REVIEW_NEEDED
        save_project(project)
        return phase

    phase["status"] = PhaseStatus.IN_PROGRESS
    phase["started_at"] = datetime.now(timezone.utc).isoformat()
    project["current_phase_index"] = phase_index
    project["status"] = ProjectStatus.IN_PROGRESS
    save_project(project)

    logger.info(f"Executing phase {phase_index}: {phase['name']}")

    # Execute each task in order
    tasks = phase.get("tasks", [])
    for task in tasks:
        if task.get("status") == PhaseStatus.COMPLETED:
            continue  # Skip already completed tasks (resume support)

        if task["type"] == "review":
            task["status"] = PhaseStatus.REVIEW_NEEDED
            save_project(project)
            continue

        # Check task dependencies
        deps_met = True
        for dep_id in task.get("depends_on", []):
            dep_task = next((t for t in tasks if t["id"] == dep_id), None)
            if dep_task and dep_task.get("status") != PhaseStatus.COMPLETED:
                deps_met = False
                break

        if not deps_met:
            task["status"] = PhaseStatus.SKIPPED
            task["error"] = "Dependencies not met"
            continue

        task["status"] = PhaseStatus.IN_PROGRESS
        save_project(project)

        try:
            if dry_run:
                task["result"] = {"dry_run": True, "description": task["description"]}
                task["status"] = PhaseStatus.COMPLETED
                continue

            if task["type"] == "validate":
                # Run validation — needs a plan + execution report.
                # For standalone validate tasks, build a minimal report
                # from the workspace state.
                from hands.tools.registry import create_default_registry
                _registry = create_default_registry()
                _artifacts = []
                for _root, _dirs, _files in os.walk(ws):
                    _dirs[:] = [d for d in _dirs if d not in {
                        "node_modules", ".git", "__pycache__", ".next", "venv",
                    }]
                    for _f in _files:
                        _artifacts.append(os.path.join(_root, _f))
                _dummy_report = {
                    "step_results": [],
                    "artifacts": _artifacts[:50],
                    "completed_steps": 0,
                    "failed_steps": 0,
                    "total_steps": 0,
                }
                _dummy_plan = {
                    "task_summary": task["description"],
                    "steps": [],
                    "success_criteria": task["description"],
                }
                result = _get_validate()(
                    goal=task["description"],
                    plan=_dummy_plan,
                    execution_report=_dummy_report,
                    domain=project.get("project_name", "general"),
                )
                task["result"] = result
                task["status"] = (
                    PhaseStatus.COMPLETED
                    if result.get("verdict") == "accept"
                    else PhaseStatus.FAILED
                )
            else:
                # Plan + execute
                from hands.tools.registry import create_default_registry
                _registry = create_default_registry()
                _tools_desc = _registry.get_tool_descriptions()
                task_plan = _get_plan_task()(
                    goal=task["description"],
                    tools_description=_tools_desc,
                    domain=project.get("project_name", "general"),
                    workspace_dir=ws,
                    available_tools=_registry.list_tools(),
                )
                if not task_plan:
                    raise ValueError(f"Planning failed for task: {task['description']}")
                exec_result = _get_execute_task()(
                    plan=task_plan,
                    registry=_registry,
                    domain=project.get("project_name", "general"),
                    workspace_dir=ws,
                )
                task["result"] = {
                    "plan_steps": len(task_plan.get("steps", [])),
                    "executed": True,
                    "success": exec_result.get("success", False),
                    "summary": exec_result.get("task_summary", ""),
                }
                task["status"] = (
                    PhaseStatus.COMPLETED
                    if exec_result.get("success", False)
                    else PhaseStatus.FAILED
                )

        except Exception as e:
            logger.error(f"Task {task['id']} failed: {e}")
            task["status"] = PhaseStatus.FAILED
            task["error"] = str(e)

        save_project(project)

        # Log execution
        project.setdefault("execution_log", []).append({
            "phase": phase["id"],
            "task": task["id"],
            "status": task["status"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Check phase completion
    all_tasks_done = all(
        t.get("status") in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED)
        for t in tasks
    )
    any_failed = any(t.get("status") == PhaseStatus.FAILED for t in tasks)

    if all_tasks_done and not any_failed:
        phase["status"] = PhaseStatus.COMPLETED
        phase["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Phase {phase_index} completed: {phase['name']}")
    elif any_failed:
        phase["status"] = PhaseStatus.FAILED
        phase["retry_count"] = phase.get("retry_count", 0) + 1
        logger.warning(f"Phase {phase_index} failed: {phase['name']}")
    
    # Check if all phases complete
    if all(p.get("status") == PhaseStatus.COMPLETED for p in phases):
        project["status"] = ProjectStatus.COMPLETED
        project["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Project COMPLETED: {project['project_id']}")

    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_project(project)
    return phase


def execute_project(
    project: dict,
    workspace_dir: Optional[str] = None,
    auto_approve: bool = False,
    max_phases: Optional[int] = None,
) -> dict:
    """Execute all remaining phases of a project.
    
    Args:
        project: Project dict
        workspace_dir: Override workspace directory
        auto_approve: Skip human review gates
        max_phases: Stop after N phases (for incremental execution)
    
    Returns:
        Updated project dict
    """
    phases = project.get("phases", [])
    executed = 0

    for i, phase in enumerate(phases):
        if max_phases and executed >= max_phases:
            logger.info(f"Stopping after {executed} phases (max_phases={max_phases})")
            break

        status = phase.get("status")
        
        if status == PhaseStatus.COMPLETED:
            continue
        
        if status == PhaseStatus.REVIEW_NEEDED:
            if auto_approve:
                logger.info(f"Auto-approving phase {i}: {phase['name']}")
                phase["status"] = PhaseStatus.PENDING
            else:
                logger.info(f"Phase {i} needs human review: {phase['name']}")
                project["status"] = ProjectStatus.PAUSED
                save_project(project)
                return project

        execute_phase(project, i, workspace_dir)
        executed += 1

        # Stop on failure or review gate
        if phase.get("status") == PhaseStatus.FAILED:
            logger.warning(f"Stopping project — phase {i} failed")
            project["status"] = ProjectStatus.PAUSED
            save_project(project)
            return project
        
        if phase.get("status") == PhaseStatus.REVIEW_NEEDED:
            logger.info(f"Phase {i} needs human review: {phase['name']}")
            project["status"] = ProjectStatus.PAUSED
            save_project(project)
            return project

    return project


# ============================================================
# Phase Operations
# ============================================================

def retry_phase(project: dict, phase_index: int) -> dict:
    """Retry a failed phase."""
    phases = project.get("phases", [])
    if phase_index >= len(phases):
        raise ValueError(f"Phase index {phase_index} out of range")
    
    phase = phases[phase_index]
    if phase.get("status") != PhaseStatus.FAILED:
        raise ValueError(f"Phase {phase_index} is {phase['status']}, not FAILED")

    # Reset failed tasks
    for task in phase.get("tasks", []):
        if task.get("status") == PhaseStatus.FAILED:
            task["status"] = PhaseStatus.PENDING
            task["result"] = None
            task["error"] = None

    phase["status"] = PhaseStatus.PENDING
    save_project(project)
    
    return execute_phase(project, phase_index)


def skip_phase(project: dict, phase_index: int) -> None:
    """Skip a phase (mark as skipped)."""
    phases = project.get("phases", [])
    if phase_index >= len(phases):
        raise ValueError(f"Phase index {phase_index} out of range")
    
    phases[phase_index]["status"] = PhaseStatus.SKIPPED
    phases[phase_index]["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_project(project)


def approve_phase(project: dict, phase_index: int) -> None:
    """Approve a phase that's waiting for human review."""
    phases = project.get("phases", [])
    if phase_index >= len(phases):
        raise ValueError(f"Phase index {phase_index} out of range")
    
    phase = phases[phase_index]
    if phase.get("status") != PhaseStatus.REVIEW_NEEDED:
        raise ValueError(f"Phase {phase_index} is {phase['status']}, not REVIEW_NEEDED")
    
    phase["status"] = PhaseStatus.PENDING
    phase["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    save_project(project)


# ============================================================
# Project Status & Reporting
# ============================================================

def project_status(project: dict) -> dict:
    """Get a summary of project status."""
    phases = project.get("phases", [])
    
    completed = sum(1 for p in phases if p.get("status") == PhaseStatus.COMPLETED)
    failed = sum(1 for p in phases if p.get("status") == PhaseStatus.FAILED)
    pending = sum(1 for p in phases if p.get("status") == PhaseStatus.PENDING)
    review = sum(1 for p in phases if p.get("status") == PhaseStatus.REVIEW_NEEDED)
    
    total_tasks = sum(len(p.get("tasks", [])) for p in phases)
    completed_tasks = sum(
        sum(1 for t in p.get("tasks", []) if t.get("status") == PhaseStatus.COMPLETED)
        for p in phases
    )

    current = None
    for i, p in enumerate(phases):
        if p.get("status") in (PhaseStatus.PENDING, PhaseStatus.IN_PROGRESS, 
                                PhaseStatus.REVIEW_NEEDED, PhaseStatus.FAILED):
            current = {"index": i, "name": p["name"], "status": p["status"]}
            break

    return {
        "project_id": project["project_id"],
        "project_name": project.get("project_name"),
        "status": project.get("status"),
        "phases": {
            "total": len(phases),
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "review_needed": review,
        },
        "tasks": {
            "total": total_tasks,
            "completed": completed_tasks,
            "progress_pct": round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0,
        },
        "current_phase": current,
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
    }


def project_report(project: dict) -> str:
    """Generate a human-readable project report."""
    status = project_status(project)
    
    lines = [
        f"# Project: {status['project_name']}",
        f"Status: {status['status']}",
        f"Progress: {status['tasks']['progress_pct']}% ({status['tasks']['completed']}/{status['tasks']['total']} tasks)",
        "",
        "## Phases:",
    ]

    for i, phase in enumerate(project.get("phases", [])):
        icon = {
            PhaseStatus.COMPLETED: "✓",
            PhaseStatus.FAILED: "✗",
            PhaseStatus.IN_PROGRESS: "→",
            PhaseStatus.REVIEW_NEEDED: "⏸",
            PhaseStatus.PENDING: "○",
            PhaseStatus.SKIPPED: "⊘",
        }.get(phase.get("status", ""), "?")
        
        tasks_done = sum(1 for t in phase.get("tasks", []) 
                        if t.get("status") == PhaseStatus.COMPLETED)
        tasks_total = len(phase.get("tasks", []))
        
        lines.append(f"  {icon} Phase {i}: {phase['name']} [{tasks_done}/{tasks_total} tasks]")
        
        if phase.get("status") == PhaseStatus.FAILED:
            failed_tasks = [t for t in phase.get("tasks", []) 
                          if t.get("status") == PhaseStatus.FAILED]
            for ft in failed_tasks:
                lines.append(f"      FAILED: {ft['description']}")
                if ft.get("error"):
                    lines.append(f"        Error: {ft['error'][:200]}")

    if status.get("current_phase"):
        lines.extend([
            "",
            f"## Next Action:",
            f"  Phase {status['current_phase']['index']}: {status['current_phase']['name']}",
            f"  Status: {status['current_phase']['status']}",
        ])

    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================

def cli_main():
    """CLI interface for project orchestrator."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Brain Project Orchestrator")
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a new project")
    p_create.add_argument("description", help="Project description")
    p_create.add_argument("--workspace", default=".", help="Workspace directory")

    # list
    sub.add_parser("list", help="List all projects")

    # status
    p_status = sub.add_parser("status", help="Show project status")
    p_status.add_argument("project_id", help="Project ID")

    # run
    p_run = sub.add_parser("run", help="Execute project phases")
    p_run.add_argument("project_id", help="Project ID")
    p_run.add_argument("--phases", type=int, default=None, help="Max phases to execute")
    p_run.add_argument("--auto-approve", action="store_true", help="Skip human review")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a phase for execution")
    p_approve.add_argument("project_id", help="Project ID")
    p_approve.add_argument("phase", type=int, help="Phase index to approve")

    # retry
    p_retry = sub.add_parser("retry", help="Retry a failed phase")
    p_retry.add_argument("project_id", help="Project ID")
    p_retry.add_argument("phase", type=int, help="Phase index to retry")

    # report
    p_report = sub.add_parser("report", help="Show detailed project report")
    p_report.add_argument("project_id", help="Project ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "create":
        project = create_project(args.description, args.workspace)
        print(f"Project created: {project['project_id']}")
        print(f"Phases: {len(project['phases'])}")
        for i, p in enumerate(project['phases']):
            review = " [REVIEW]" if p.get("requires_human_review") else ""
            print(f"  {i}: {p['name']}{review} ({len(p.get('tasks', []))} tasks)")

    elif args.command == "list":
        projects = list_projects()
        if not projects:
            print("No projects found")
        for p in projects:
            print(f"  {p['project_id']}  [{p['status']}]  {p['phases_completed']}/{p['phases_total']} phases")

    elif args.command == "status":
        project = load_project(args.project_id)
        if not project:
            print(f"Project not found: {args.project_id}")
            return
        s = project_status(project)
        print(json.dumps(s, indent=2))

    elif args.command == "run":
        project = load_project(args.project_id)
        if not project:
            print(f"Project not found: {args.project_id}")
            return
        execute_project(project, max_phases=args.phases, auto_approve=args.auto_approve)
        print(project_report(project))

    elif args.command == "approve":
        project = load_project(args.project_id)
        if not project:
            print(f"Project not found: {args.project_id}")
            return
        approve_phase(project, args.phase)
        print(f"Phase {args.phase} approved")

    elif args.command == "retry":
        project = load_project(args.project_id)
        if not project:
            print(f"Project not found: {args.project_id}")
            return
        retry_phase(project, args.phase)
        print(project_report(project))

    elif args.command == "report":
        project = load_project(args.project_id)
        if not project:
            print(f"Project not found: {args.project_id}")
            return
        print(project_report(project))


if __name__ == "__main__":
    cli_main()
