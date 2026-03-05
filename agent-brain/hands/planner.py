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
from skills_loader import load_skills, detect_categories, lookup_design_data

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Import shared constants (single source of truth)
from hands.constants import (
    KEY_FILENAMES as _KEY_FILENAMES,
    SKIP_DIRS as _SKIP_DIRS,
    MAX_TREE_CHARS as _MAX_TREE_CHARS,
    MAX_KEY_FILE_CHARS as _MAX_KEY_FILE_CHARS,
)


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
    goal: str = "",
) -> str:
    """Build the planner's system prompt with tool awareness and domain context."""
    today = date.today().isoformat()

    # Load design system if available (large file, always loaded for frontend tasks)
    design_system = ""
    identity_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "identity")
    design_path = os.path.join(identity_dir, "design_system.md")
    if os.path.exists(design_path):
        try:
            with open(design_path, "r") as f:
                design_system = f.read()[:3000]
        except OSError:
            pass

    # Dynamic skill loading based on task context
    task_text = f"{goal} {domain_knowledge} {execution_strategy}"
    categories = detect_categories(task_text)
    # Always include coding for web builds
    if "coding" not in categories:
        categories.append("coding")
    skills_block = load_skills(categories, max_chars=8000)

    base = f"""\
You are an execution planner for an autonomous AI system that builds production-ready web applications.
Your job: decompose a task into concrete, ordered steps executable by tools.

TODAY'S DATE: {today}

AVAILABLE TOOLS:
{tools_description}

=== BUILD ARCHITECTURE ===
When building a web application, follow this phase structure:

Phase 0 — Context Intake: Read the research brief/PRD. Understand the user, their pain, and the core feature.
Phase 1 — Scaffold: Create the project (`npx create-next-app@latest --ts --tailwind --app --src-dir --eslint`).
           Install dependencies: shadcn/ui (`npx shadcn@latest init`), framer-motion.
Phase 2 — Backend: API routes, auth, database. See DATABASE and AUTH sections below.
Phase 3 — Frontend: Layout → pages → components. Mobile-first. Design system applied.
Phase 4 — Integration: Connect frontend to backend. Wire up auth flow. Test data flow.
Phase 5 — Validation: `npm run build` must pass clean. Fix any TypeScript/lint errors.
Phase 6 — Deploy: Deploy to Vercel via CLI (`npx vercel --yes --prod`). VERCEL_TOKEN is set in environment.

=== TECH STACK (always use unless task specifies otherwise) ===
- Framework: Next.js 15+ (App Router, TypeScript, src/ directory)
- Styling: Tailwind CSS + shadcn/ui components
- Animations: Framer Motion (subtle, purposeful)
- Database: Use the simplest option that fits the task:
  * Landing pages / static sites: No database needed. Use local JSON or hardcoded data.
  * MVP with data persistence: better-sqlite3 (npm install better-sqlite3) — zero cost, serverless-compatible, stores in a local .db file. Create a src/lib/db.ts with schema init.
  * Full SaaS with users: Supabase free tier (needs NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY in .env.local).
- Auth: Use the simplest option that fits the task:
  * No auth needed: Skip entirely for landing pages and static sites.
  * MVP auth: NextAuth.js v5 (Auth.js) — `npm install next-auth@beta`. Free, open source. Use credential provider (email/password) with better-sqlite3 adapter. Zero external dependencies.
  * Full auth: Supabase Auth (free tier: 50K MAU) or Clerk (free tier: 10K MAU).
- Deploy: Vercel (via CLI: `npx vercel --yes --prod`)
- Package manager: npm (not yarn, not pnpm)

=== CODE QUALITY RULES ===
- Every file must contain COMPLETE, working code. NEVER use placeholders like `// TODO`, `// rest of code`, `...`, or `/* implement */`.
- Every component must be properly typed with TypeScript. No `any` types.
- Every page must handle: loading state, empty state, error state.
- Use `"use client"` directive only on components that need interactivity.
- Server components by default. Client components only when needed (hooks, event handlers).
- All imports must be correct. Verify import paths match actual file locations.
- Include proper meta tags, viewport settings, and favicon in layout.
- Responsive: works on mobile (375px), tablet (768px), and desktop (1280px+).

=== PLANNING RULES ===
1. Each step must use exactly one tool with specific parameters.
2. Steps execute sequentially — later steps can reference earlier results.
3. Keep plans focused — fewest steps that correctly complete the task.
4. Never plan more than {EXEC_MAX_STEPS} steps. Batch related files into fewer steps when possible.
5. Include a `npm run build` validation step after all code is written.
6. If a task is ambiguous, plan for the most reasonable interpretation.
7. Be specific — "write file src/app/page.tsx with content Y", not "create the homepage".
8. Each file write must include the FULL file content — never partial.
9. Mark each step as "required" or "optional" — optional steps (like formatting) don't block.
10. Only reference tools listed in AVAILABLE TOOLS above.
11. For multi-page apps: write layout first, then shared components, then pages. Dependencies before dependents.
12. Always create `.env.local` with all required environment variables (use placeholder values).

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

    if design_system:
        base += f"""
=== DESIGN SYSTEM ===
Apply these visual standards to all frontend code. This is the system's taste — what makes outputs look production-ready.

{design_system}
=== END DESIGN SYSTEM ===
"""

    # Inject dynamically loaded skills
    if skills_block:
        base += f"""
=== LOADED SKILLS ===
Apply these skills and best practices to your planning.

{skills_block}
=== END LOADED SKILLS ===
"""

    # Design data lookup for industry-specific recommendations
    if goal:
        design_data = lookup_design_data(goal)
        if design_data:
            base += f"""
=== INDUSTRY DESIGN DATA ===
{design_data[:2000]}
=== END INDUSTRY DESIGN DATA ===
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
    available_tools: list[str] | None = None,
    max_retries: int = 2,
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
        available_tools: List of available tool names (for validation)
        max_retries: Number of retries on parse failure

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

    system = _build_system_prompt(tools_description, domain_knowledge, execution_strategy, workspace_context, goal)

    user_message = f"TASK: {goal}"
    if context:
        user_message += f"\n\nADDITIONAL CONTEXT:\n{context}"

    for attempt in range(max_retries + 1):
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
            if attempt < max_retries:
                print(f"  [PLANNER] Parse failed (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                user_message = (
                    f"TASK: {goal}\n\n"
                    f"IMPORTANT: Your previous response was not valid JSON. "
                    f"Respond with ONLY the JSON plan structure, no extra text."
                )
                if context:
                    user_message += f"\n\nADDITIONAL CONTEXT:\n{context}"
                continue
            print(f"  [PLANNER] Failed to parse plan after {max_retries + 1} attempts. Raw:\n{text[:500]}")
            return None

        # Validate plan structure
        if "steps" not in plan_data or not isinstance(plan_data["steps"], list):
            if attempt < max_retries:
                print(f"  [PLANNER] Plan missing 'steps' array (attempt {attempt + 1}), retrying...")
                continue
            print("  [PLANNER] Plan missing 'steps' array")
            return None

        if not plan_data["steps"]:
            if attempt < max_retries:
                print(f"  [PLANNER] Plan has 0 steps (attempt {attempt + 1}), retrying...")
                continue
            print("  [PLANNER] Plan has no steps")
            return None

        # Successfully parsed — break out of retry loop
        break

    if len(plan_data["steps"]) > EXEC_MAX_STEPS:
        print(f"  [PLANNER] Plan has {len(plan_data['steps'])} steps (max {EXEC_MAX_STEPS})")
        plan_data["steps"] = plan_data["steps"][:EXEC_MAX_STEPS]

    # Ensure each step has required fields + validate tool names
    for i, step in enumerate(plan_data["steps"]):
        step.setdefault("step_number", i + 1)
        step.setdefault("tool", "unknown")
        step.setdefault("params", {})
        step.setdefault("depends_on", [])
        step.setdefault("description", "")
        step.setdefault("expected_output", "")
        step.setdefault("criticality", "required")

        # Validate tool name against available tools
        if available_tools and step["tool"] not in available_tools:
            # Try to map common misspellings/aliases
            tool_map = {
                "file": "code", "fs": "code", "write": "code", "read": "code",
                "shell": "terminal", "bash": "terminal", "exec": "terminal",
                "cmd": "terminal", "run": "terminal",
                "grep": "search", "find": "search",
                "http_request": "http", "curl": "http", "fetch": "http",
                "version_control": "git", "vcs": "git",
            }
            mapped = tool_map.get(step["tool"])
            if mapped and mapped in available_tools:
                print(f"  [PLANNER] Remapped tool '{step['tool']}' → '{mapped}' (step {i+1})")
                step["tool"] = mapped
            else:
                print(f"  [PLANNER] ⚠ Unknown tool '{step['tool']}' in step {i+1} — defaulting to 'terminal'")
                step["tool"] = "terminal"

    plan_data.setdefault("task_summary", goal[:200])
    plan_data.setdefault("success_criteria", "All steps complete without errors")
    plan_data.setdefault("estimated_complexity", "medium")
    plan_data.setdefault("risks", [])

    # Validate and fix dependency graph
    _validate_dependencies(plan_data["steps"])

    return plan_data


def plan_repair(
    original_plan: dict,
    failing_steps: list[int],
    feedback: str,
    tools_description: str,
    completed_steps: list[dict],
    domain: str = "general",
    workspace_dir: str = "",
) -> dict | None:
    """
    Generate a repair plan that only re-does failing steps + dependents.
    
    Instead of full re-planning from scratch, this takes the original plan,
    identifies what worked, and produces a focused repair plan that:
    1. Preserves successful steps (don't redo what's already good)
    2. Replaces failing steps with improved versions
    3. Includes dependent steps that build on the failures
    
    Args:
        original_plan: The plan that was executed (with issues)
        failing_steps: Step numbers that need re-doing (from identify_failing_steps)
        feedback: Validation feedback / actionable critique
        tools_description: Available tools description
        completed_steps: Step results from the original execution
        domain: Domain context
        workspace_dir: Workspace path for context
    
    Returns:
        Repair plan dict, or None if repair isn't feasible (falls back to full replan)
    """
    if not failing_steps:
        return None
    
    total = len(original_plan.get("steps", []))
    if not total:
        return None
    
    # If >60% of steps failed, full replan is better
    if len(failing_steps) > total * 0.6:
        return None

    # Build context: what succeeded vs what failed
    successful_summaries = []
    for sr in completed_steps:
        if sr.get("success") and sr.get("step") not in failing_steps:
            successful_summaries.append(
                f"Step {sr['step']} ({sr.get('tool', '?')}): ✓ {sr.get('output', '')[:100]}"
            )

    failing_details = []
    for sr in completed_steps:
        if sr.get("step") in failing_steps:
            failing_details.append(
                f"Step {sr['step']} ({sr.get('tool', '?')}): ✗ {sr.get('error', '')[:200]}"
            )

    repair_prompt = f"""\
You are an execution planner performing SURGICAL REPAIR on a partially-failed plan.

ORIGINAL PLAN:
{json.dumps(original_plan, indent=2)[:4000]}

STEPS THAT SUCCEEDED (DO NOT REDO):
{chr(10).join(successful_summaries) if successful_summaries else "(none)"}

STEPS THAT FAILED (MUST BE FIXED):
{chr(10).join(failing_details) if failing_details else "Steps " + str(failing_steps)}

FAILING STEP NUMBERS: {failing_steps}

VALIDATOR FEEDBACK:
{feedback[:2000]}

REPAIR INSTRUCTIONS:
1. Generate replacement steps ONLY for the failing steps and their dependents.
2. Keep the same step numbering as the original plan.
3. Use improved parameters based on the feedback.
4. Reference artifacts created by successful steps — don't recreate them.
5. If a failing step's approach was fundamentally wrong, redesign it.

AVAILABLE TOOLS:
{tools_description}

Respond with ONLY the JSON repair plan (same format as original plan, but with only the steps that need re-execution).
"""

    # Scan workspace context if available
    workspace_context = ""
    if workspace_dir and os.path.isdir(workspace_dir):
        ws = _scan_workspace(workspace_dir)
        workspace_context = f"Current workspace state:\n{ws['tree']}\n"

    if workspace_context:
        repair_prompt += f"\nWORKSPACE STATE:\n{workspace_context}"

    try:
        response = create_message(
            client,
            model=MODELS["planner"],
            max_tokens=4096,
            system="You are a precise execution planner. Output ONLY valid JSON.",
            messages=[{"role": "user", "content": repair_prompt}],
        )

        log_cost(
            model=MODELS["planner"],
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_role="planner",
            domain=domain,
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        repair_plan = extract_json(text, expected_keys={"steps"})
        if not repair_plan or not repair_plan.get("steps"):
            return None

        # Inherit metadata from original plan
        repair_plan.setdefault("task_summary", original_plan.get("task_summary", ""))
        repair_plan.setdefault("success_criteria", original_plan.get("success_criteria", ""))
        repair_plan["is_repair"] = True
        repair_plan["original_failing_steps"] = failing_steps

        return repair_plan

    except Exception as e:
        print(f"  [PLANNER] Repair plan failed: {e}")
        return None


def _validate_dependencies(steps: list[dict]) -> None:
    """
    Validate and sanitize the dependency graph of plan steps.
    
    Fixes:
    - References to non-existent step numbers
    - Circular dependencies (breaks cycles)
    - Self-references
    
    Modifies steps in-place.
    """
    valid_steps = {s.get("step_number", i + 1) for i, s in enumerate(steps)}
    
    for step in steps:
        step_num = step.get("step_number", 0)
        deps = step.get("depends_on", [])
        
        if not isinstance(deps, list):
            step["depends_on"] = []
            continue
        
        # Remove self-references and invalid step numbers
        cleaned = [d for d in deps if d != step_num and d in valid_steps]
        
        # Remove forward references (can't depend on a later step)
        cleaned = [d for d in cleaned if d < step_num]
        
        if len(cleaned) != len(deps):
            step["depends_on"] = cleaned
    
    # Detect and break circular dependencies using topological sort attempt
    # Build adjacency list
    graph = {}
    for step in steps:
        sn = step.get("step_number", 0)
        graph[sn] = step.get("depends_on", [])
    
    # Simple cycle detection via DFS
    visited = set()
    in_stack = set()
    
    def has_cycle(node: int) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in graph.get(node, []):
            if has_cycle(dep):
                return True
        in_stack.discard(node)
        return False
    
    for step in steps:
        sn = step.get("step_number", 0)
        visited.clear()
        in_stack.clear()
        if has_cycle(sn):
            # Break cycle by clearing this step's dependencies
            print(f"  [PLANNER] ⚠ Circular dependency detected at step {sn} — clearing deps")
            step["depends_on"] = []
            graph[sn] = []
