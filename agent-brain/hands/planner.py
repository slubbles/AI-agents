"""
Execution Planner — Decomposes a task into concrete, tool-using steps.

Takes:
- A goal (natural language task description)
- Available tools (from registry)
- Domain knowledge (from Brain's KB)
- Execution strategy (from strategy store, evolves over time)
- Workspace context (existing file tree, key file contents)

Produces:
- A structured execution plan: ordered steps with tool selections and parameters
  Each step can be marked as "required" or "optional" for criticality handling.

Uses Claude Sonnet for reasoning — plan quality directly determines execution quality.
"""

import json
import os
import sys
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, EXEC_MAX_STEPS
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json

client = Anthropic(api_key=ANTHROPIC_API_KEY)


# File extensions considered "key files" that get their content injected
_KEY_FILENAMES = {
    "package.json", "tsconfig.json", "pyproject.toml", "requirements.txt",
    "setup.py", "setup.cfg", "cargo.toml", "go.mod", "dockerfile",
    ".gitignore", "readme.md", "readme.rst", ".env.example",
    "next.config.js", "next.config.mjs", "next.config.ts",
    "vite.config.ts", "vite.config.js", "tailwind.config.js",
    "eslint.config.js", ".eslintrc.json", "jest.config.js",
}

# Extensions to skip in file tree
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".next", ".cache",
              "dist", "build", ".turbo", "coverage", ".venv", "venv"}

# Max chars for workspace context section
_MAX_TREE_CHARS = 3000
_MAX_KEY_FILE_CHARS = 4000


def _scan_workspace(workspace_dir: str) -> dict:
    """
    Scan a workspace directory and return structured context.

    Returns:
        {
            "tree": "ASCII file tree string",
            "key_files": {"path": "content", ...},
            "stats": {"files": int, "dirs": int}
        }
    """
    if not workspace_dir or not os.path.isdir(workspace_dir):
        return {"tree": "", "key_files": {}, "stats": {"files": 0, "dirs": 0}}

    tree_lines = []
    key_files = {}
    file_count = 0
    dir_count = 0
    total_tree_chars = 0

    for root, dirs, files in os.walk(workspace_dir):
        # Skip ignored directories
        dirs[:] = [d for d in sorted(dirs) if d not in _SKIP_DIRS]

        depth = root.replace(workspace_dir, "").count(os.sep)
        if depth > 4:  # Max depth for tree display
            dirs.clear()
            continue

        indent = "  " * depth
        dirname = os.path.basename(root) or os.path.basename(workspace_dir)

        line = f"{indent}{dirname}/"
        if total_tree_chars + len(line) < _MAX_TREE_CHARS:
            tree_lines.append(line)
            total_tree_chars += len(line) + 1
        dir_count += 1

        for f in sorted(files):
            file_count += 1
            file_line = f"{indent}  {f}"
            if total_tree_chars + len(file_line) < _MAX_TREE_CHARS:
                tree_lines.append(file_line)
                total_tree_chars += len(file_line) + 1

            # Check if this is a key file to read
            if f.lower() in _KEY_FILENAMES:
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, "r", errors="replace") as fh:
                        content = fh.read(2000)
                    if len(content) >= 2000:
                        content = content[:2000] + "\n... (truncated)"
                    key_files[os.path.relpath(filepath, workspace_dir)] = content
                except (OSError, UnicodeDecodeError):
                    pass

    # Cap key files total size
    total_kf_chars = 0
    trimmed_key_files = {}
    for path, content in key_files.items():
        if total_kf_chars + len(content) > _MAX_KEY_FILE_CHARS:
            break
        trimmed_key_files[path] = content
        total_kf_chars += len(content)

    return {
        "tree": "\n".join(tree_lines) if tree_lines else "(empty directory)",
        "key_files": trimmed_key_files,
        "stats": {"files": file_count, "dirs": dir_count},
    }


def _build_system_prompt(
    tools_description: str,
    domain_knowledge: str = "",
    execution_strategy: str = "",
    workspace_context: str = "",
) -> str:
    """Build the planner's system prompt with tool awareness and domain context."""
    today = date.today().isoformat()

    base = f"""\
You are an execution planner. Your job is to decompose a task into concrete, 
ordered steps that can be executed by tools.

TODAY'S DATE: {today}

AVAILABLE TOOLS:
{tools_description}

PLANNING RULES:
1. Each step must use exactly one tool with specific parameters.
2. Steps execute sequentially — later steps can reference earlier results.
3. Keep plans minimal — fewest steps that correctly complete the task.
4. Never plan more than {EXEC_MAX_STEPS} steps.
5. Include validation steps (run tests, check output) after creation steps.
6. If a task is ambiguous, plan for the most reasonable interpretation.
7. For code tasks: always include a test/verification step at the end.
8. For content tasks: plan a review step to check quality.
9. Be specific — "write file X with content Y", not "create the project".
10. Each file must be written with complete content — never partial stubs.
11. Mark each step as "required" or "optional" — optional steps (like linting, formatting)
    should not block execution if they fail.
12. Only reference tools that are listed in AVAILABLE TOOLS above.

RESPOND WITH ONLY THIS JSON STRUCTURE:
{{
  "task_summary": "1-sentence summary of what this plan accomplishes",
  "steps": [
    {{
      "step_number": 1,
      "description": "What this step does",
      "tool": "tool_name",
      "params": {{"param1": "value1", "param2": "value2"}},
      "depends_on": [],
      "expected_output": "What success looks like",
      "criticality": "required"
    }}
  ],
  "success_criteria": "How to verify the whole task succeeded",
  "estimated_complexity": "low|medium|high",
  "risks": ["potential failure points"]
}}

criticality values: "required" (blocks execution if fails) or "optional" (nice to have, skip on failure).
"""

    if workspace_context:
        base += f"""
=== WORKSPACE STATE ===
This is the current state of the project directory. Plan your steps considering what already exists.
Do NOT recreate files that already exist unless they need to be replaced.

{workspace_context[:5000]}
=== END WORKSPACE STATE ===
"""

    if domain_knowledge:
        base += f"""
=== DOMAIN KNOWLEDGE (from Brain's KB) ===
Use this knowledge to inform your plan. These are verified claims from prior research.

{domain_knowledge[:4000]}
=== END DOMAIN KNOWLEDGE ===
"""

    if execution_strategy:
        base += f"""
=== EXECUTION STRATEGY ===
Follow this strategy for planning. It was evolved based on past execution performance.

{execution_strategy[:3000]}
=== END EXECUTION STRATEGY ===
"""

    return base


def plan(
    goal: str,
    tools_description: str,
    domain: str = "general",
    domain_knowledge: str = "",
    execution_strategy: str = "",
    context: str = "",
    workspace_dir: str = "",
) -> dict | None:
    """
    Generate an execution plan for a given goal.

    Args:
        goal: Natural language task description
        tools_description: Output of registry.get_tool_descriptions()
        domain: Domain context (e.g., "saas-building", "growth-hacking")
        domain_knowledge: Relevant KB claims from Brain
        execution_strategy: Execution strategy text (evolves over time)
        context: Additional context (e.g., prior execution feedback)
        workspace_dir: Path to workspace directory (for scanning existing files)

    Returns:
        Parsed plan dict, or None if planning failed
    """
    # Scan workspace for context injection
    workspace_context = ""
    if workspace_dir and os.path.isdir(workspace_dir):
        ws = _scan_workspace(workspace_dir)
        workspace_parts = [f"File tree ({ws['stats']['files']} files, {ws['stats']['dirs']} dirs):"]
        workspace_parts.append(ws["tree"])
        if ws["key_files"]:
            workspace_parts.append("\nKey file contents:")
            for path, content in ws["key_files"].items():
                workspace_parts.append(f"\n--- {path} ---\n{content}")
        workspace_context = "\n".join(workspace_parts)

    system = _build_system_prompt(tools_description, domain_knowledge, execution_strategy, workspace_context)

    user_message = f"TASK: {goal}"
    if context:
        user_message += f"\n\nADDITIONAL CONTEXT:\n{context}"

    response = create_message(
        client,
        model=MODELS["planner"],
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    # Track cost
    log_cost(
        model=MODELS["planner"],
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        agent_role="planner",
        domain=domain,
    )

    # Extract text
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # Parse JSON
    plan_data = extract_json(text, expected_keys={"steps", "task_summary"})

    if not plan_data:
        print(f"  [PLANNER] Failed to parse plan. Raw output:\n{text[:500]}")
        return None

    # Validate plan structure
    if "steps" not in plan_data or not isinstance(plan_data["steps"], list):
        print("  [PLANNER] Plan missing 'steps' array")
        return None

    if len(plan_data["steps"]) > EXEC_MAX_STEPS:
        print(f"  [PLANNER] Plan has {len(plan_data['steps'])} steps (max {EXEC_MAX_STEPS})")
        plan_data["steps"] = plan_data["steps"][:EXEC_MAX_STEPS]

    # Ensure each step has required fields
    for i, step in enumerate(plan_data["steps"]):
        step.setdefault("step_number", i + 1)
        step.setdefault("tool", "unknown")
        step.setdefault("params", {})
        step.setdefault("depends_on", [])
        step.setdefault("description", "")
        step.setdefault("expected_output", "")
        step.setdefault("criticality", "required")  # Default to required

    plan_data.setdefault("task_summary", goal[:200])
    plan_data.setdefault("success_criteria", "All steps complete without errors")
    plan_data.setdefault("estimated_complexity", "medium")
    plan_data.setdefault("risks", [])

    return plan_data
