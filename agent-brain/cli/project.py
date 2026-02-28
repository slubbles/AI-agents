"""Project orchestrator CLI commands."""


def run(description: str, domain: str, workspace_dir: str = ""):
    """Decompose and start executing a large project."""
    print(f"\n{'='*60}")
    print(f"  PROJECT ORCHESTRATOR")
    print(f"{'='*60}\n")
    print(f"  Description: {description}")
    print(f"  Domain: {domain}")

    try:
        from hands.project_orchestrator import decompose_project, execute_project

        print("\n  Phase 1: Decomposing project...")
        project = decompose_project(description)

        if not project:
            print("  ERROR: Failed to decompose project")
            return

        project_id = project.get("id", "unknown")
        phases = project.get("phases", [])
        total_tasks = sum(len(p.get("tasks", [])) for p in phases)

        print(f"  Project ID: {project_id}")
        print(f"  Phases: {len(phases)}")
        print(f"  Total tasks: {total_tasks}")
        print()

        for i, phase in enumerate(phases):
            name = phase.get("name", f"Phase {i+1}")
            tasks = phase.get("tasks", [])
            review = phase.get("requires_review", False)
            print(f"    {i+1}. {name} ({len(tasks)} tasks){' [REVIEW NEEDED]' if review else ''}")

        print(f"\n  Phase 2: Executing project...")
        result = execute_project(project, workspace_dir=workspace_dir or None)

        status = result.get("status", "unknown")
        completed_phases = sum(1 for p in result.get("phases", []) if p.get("status") == "completed")
        print(f"\n  Result: {status}")
        print(f"  Completed phases: {completed_phases}/{len(phases)}")

        if status == "paused":
            print(f"  Project paused (review needed). Resume with: --project-resume {project_id}")

    except ImportError as e:
        print(f"  ERROR: Missing dependency: {e}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def status(project_id: str):
    """Show status of a project."""
    print(f"\n{'='*60}")
    print(f"  PROJECT STATUS")
    print(f"{'='*60}\n")

    try:
        from hands.project_orchestrator import load_project, list_projects

        if project_id == "latest":
            projects = list_projects()
            if not projects:
                print("  No projects found.")
                return
            project_id = projects[-1]["id"]

        project = load_project(project_id)
        if not project:
            print(f"  Project '{project_id}' not found.")
            return

        print(f"  ID: {project.get('id')}")
        print(f"  Description: {project.get('description', 'N/A')[:80]}")
        print(f"  Status: {project.get('status', 'unknown')}")
        print(f"  Created: {project.get('created_at', 'N/A')[:19]}")
        print()

        for i, phase in enumerate(project.get("phases", [])):
            name = phase.get("name", f"Phase {i+1}")
            phase_status = phase.get("status", "pending")
            tasks_done = sum(1 for t in phase.get("tasks", []) if t.get("completed"))
            total = len(phase.get("tasks", []))
            icon = {"completed": "\u2713", "in_progress": "\u25b6", "failed": "\u2717", "review_needed": "\u26a0", "skipped": "\u25cb"}.get(phase_status, "\u00b7")
            print(f"    {icon} {name}: {phase_status} ({tasks_done}/{total} tasks)")

    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def resume(project_id: str):
    """Resume a paused project."""
    print(f"\n  Resuming project: {project_id}")

    try:
        from hands.project_orchestrator import load_project, execute_project, list_projects

        if project_id == "latest":
            projects = list_projects()
            if not projects:
                print("  No projects found.")
                return
            project_id = projects[-1]["id"]

        project = load_project(project_id)
        if not project:
            print(f"  Project '{project_id}' not found.")
            return

        result = execute_project(project)
        print(f"  Result: {result.get('status', 'unknown')}")

    except Exception as e:
        print(f"  ERROR: {e}")


def approve_phase(project_id: str):
    """Approve the current phase of a project needing review."""
    try:
        from hands.project_orchestrator import load_project, approve_phase as _approve, list_projects

        if project_id == "latest":
            projects = list_projects()
            if not projects:
                print("  No projects found.")
                return
            project_id = projects[-1]["id"]

        project = load_project(project_id)
        if not project:
            print(f"  Project '{project_id}' not found.")
            return

        for i, phase in enumerate(project.get("phases", [])):
            if phase.get("status") == "review_needed":
                _approve(project, i)
                print(f"  Approved phase {i+1}: {phase.get('name', 'unknown')}")
                return

        print("  No phases are waiting for review.")

    except Exception as e:
        print(f"  ERROR: {e}")


def list_all():
    """List all projects."""
    print(f"\n{'='*60}")
    print(f"  PROJECTS")
    print(f"{'='*60}\n")

    try:
        from hands.project_orchestrator import list_projects

        projects = list_projects()
        if not projects:
            print("  No projects found.")
            return

        for p in projects:
            p_status = p.get("status", "unknown")
            desc = p.get("description", "N/A")[:60]
            phases = len(p.get("phases", []))
            icon = {"completed": "\u2713", "in_progress": "\u25b6", "paused": "\u23f8", "failed": "\u2717"}.get(p_status, "\u00b7")
            print(f"  {icon} {p['id'][:12]}  {p_status:12s}  {phases} phases  {desc}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
