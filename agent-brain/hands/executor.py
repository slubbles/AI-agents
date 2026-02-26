"""
Executor Agent — Executes a plan step-by-step using tools.

Takes:
- A structured execution plan (from planner)
- A tool registry (code, terminal, etc.)

Produces:
- Step-by-step execution results
- Final execution report with all artifacts

Uses Claude Haiku for cheap execution — the plan has already been made by Sonnet.
The executor just follows instructions and uses tools.

Features:
- Multi-turn conversational loop with tool feedback
- Step-level retry on failures (up to 2 retries per step)
- Context window management (summarizes old steps to stay within limits)
- Tracks cost, artifacts, and execution timeline
"""

import json
import os
import sys
import traceback
from datetime import date, datetime, timezone

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, EXEC_MAX_STEPS, EXEC_STEP_TIMEOUT
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json
from hands.tools.registry import ToolRegistry, ToolResult
from hands.error_analyzer import analyze_error, format_retry_guidance
from hands.tool_health import ToolHealthMonitor
from hands.timeout_adapter import TimeoutAdapter
from hands.mid_validator import MidExecutionValidator


client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Context window management
MAX_CONVERSATION_TOKENS_ESTIMATE = 150_000  # Stay well under limit
CHARS_PER_TOKEN_ESTIMATE = 4
MAX_CONVERSATION_CHARS = MAX_CONVERSATION_TOKENS_ESTIMATE * CHARS_PER_TOKEN_ESTIMATE
STEP_RETRY_LIMIT = 2  # Retries per individual step
MAX_EXECUTION_COST = 0.50  # Hard cost ceiling per execution ($0.50)


def _estimate_conversation_size(conversation: list[dict]) -> int:
    """Estimate the total character count of a conversation."""
    total = 0
    for msg in conversation:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            # Native tool_use/tool_result blocks
            for block in content:
                if isinstance(block, dict):
                    total += len(str(block.get("content", ""))) + len(str(block.get("text", "")))
                else:
                    # Anthropic SDK objects (TextBlock, ToolUseBlock, etc.)
                    total += len(getattr(block, "text", "")) + len(str(getattr(block, "input", "")))
    return total


def _summarize_old_steps(conversation: list[dict], keep_recent: int = 6) -> list[dict]:
    """
    Compress old conversation turns into a summary to manage context window.
    Keeps the first message (plan) and the last N messages.
    """
    if len(conversation) <= keep_recent + 1:
        return conversation

    # Keep first (plan) and last N messages
    first = conversation[0]
    recent = conversation[-keep_recent:]
    middle = conversation[1:-keep_recent]

    # Extract string content from a message (handles both str and list formats)
    def _content_str(msg: dict) -> str:
        c = msg.get("content", "")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            parts = []
            for block in c:
                if isinstance(block, dict):
                    parts.append(str(block.get("content", "")))
                elif hasattr(block, "text"):
                    parts.append(block.text)
            return " ".join(parts)
        return str(c)

    # Summarize middle messages
    summary_parts = []
    step_num = 0
    for msg in middle:
        content = _content_str(msg)
        if msg["role"] == "user" and "TOOL RESULT" in content:
            step_num += 1
            # Extract just success/failure and truncated output
            success_idx = content.find("SUCCESS:")
            failed_idx = content.find("FAILED:")
            if success_idx >= 0:
                brief = content[success_idx:success_idx + 200]
                summary_parts.append(f"Step {step_num}: ✓ {brief[:150]}")
            elif failed_idx >= 0:
                brief = content[failed_idx:failed_idx + 200]
                summary_parts.append(f"Step {step_num}: ✗ {brief[:150]}")
            else:
                summary_parts.append(f"Step {step_num}: {content[:150]}")

    summary = {
        "role": "user",
        "content": (
            f"[CONTEXT SUMMARY — {len(middle)} messages compressed]\n"
            f"Previous step results:\n" + "\n".join(summary_parts) +
            f"\n\nContinue with the current step."
        ),
    }

    return [first, summary] + recent


# ---- Sliding Context Window ----
# Instead of grow-then-compress, proactively keep the conversation small.
# The state accumulator maintains a running summary of all completed steps,
# so the executor always has full context in a compact form.

SLIDING_WINDOW_KEEP_RECENT = 4  # Keep last N messages (2 turns)


def _build_state_accumulator(step_results: list[dict], artifacts: list[str]) -> str:
    """
    Build a compact state summary from all completed steps.
    
    This replaces the old conversation history with a structured status block.
    The executor sees: plan + state accumulator + last 2 turns. That's it.
    Cuts context by ~70% on multi-step executions.
    """
    if not step_results:
        return ""
    
    parts = [f"EXECUTION STATE — {len(step_results)} step(s) completed:"]
    
    for sr in step_results:
        status = "✓" if sr.get("success") else "✗"
        tool = sr.get("tool", "?")
        step_num = sr.get("step", "?")
        output = sr.get("output", "")[:200]
        error = sr.get("error", "")
        
        line = f"  Step {step_num} [{tool}] {status}"
        if sr.get("success"):
            # Only include output summary for successful steps
            if output:
                line += f": {output}"
        else:
            if error:
                line += f": ERROR — {error[:200]}"
        
        parts.append(line)
    
    if artifacts:
        # List unique artifacts
        unique = sorted(set(artifacts))
        parts.append(f"\nArtifacts created: {', '.join(unique[:20])}")
    
    parts.append(f"\nProceed with Step {len(step_results) + 1}.")
    return "\n".join(parts)


def _apply_sliding_window(
    conversation: list[dict],
    step_results: list[dict],
    artifacts: list[str],
) -> list[dict]:
    """
    Apply the sliding context window strategy.
    
    Replaces the full conversation with:
    [plan_message, state_accumulator, last_N_messages]
    
    This is called proactively every turn (not just when nearing limits),
    keeping the conversation consistently small.
    """
    if len(conversation) <= SLIDING_WINDOW_KEEP_RECENT + 1:
        return conversation  # Not enough messages to compress yet
    
    plan_msg = conversation[0]
    recent = conversation[-SLIDING_WINDOW_KEEP_RECENT:]
    
    state = _build_state_accumulator(step_results, artifacts)
    
    if state:
        state_msg = {"role": "user", "content": state}
        # Ensure conversation alternation: plan(user), state(user) won't work
        # So we merge state into the last assistant message before recent, or inject as context
        return [plan_msg, {"role": "assistant", "content": "Understood. Continuing execution."}, state_msg] + recent
    
    return [plan_msg] + recent


# ---- Dependency-Aware Fail-Fast ----
# Check the dependency graph BEFORE dispatching each step to the LLM.
# Skip steps whose dependencies have already failed — no LLM cost spent.

class DependencyResolver:
    """Resolves step dependencies to enable fail-fast execution."""

    def __init__(self, steps: list[dict]):
        """Build adjacency map from plan steps."""
        self._deps: dict[int, list[int]] = {}
        self._criticality: dict[int, str] = {}
        self._total_steps = len(steps)
        
        for step in steps:
            sn = step.get("step_number", 0)
            self._deps[sn] = step.get("depends_on", [])
            self._criticality[sn] = step.get("criticality", "required")

    def can_execute(self, step_num: int, step_results: list[dict]) -> tuple[bool, list[int]]:
        """
        Check if a step's dependencies are all satisfied.
        
        Returns: (can_run, [failed_dependency_step_nums])
        A step can run if all depends_on steps succeeded.
        """
        deps = self._deps.get(step_num, [])
        if not deps:
            return True, []
        
        # Build lookup of completed step results
        result_map = {}
        for sr in step_results:
            result_map[sr.get("step", 0)] = sr
        
        blockers = []
        for dep in deps:
            dep_result = result_map.get(dep)
            if dep_result is None:
                continue  # Not yet executed — might still succeed
            if not dep_result.get("success") and dep_result.get("status") != "blocked_by_dependency":
                blockers.append(dep)
            elif dep_result.get("status") == "blocked_by_dependency":
                blockers.append(dep)  # Transitively blocked
        
        return len(blockers) == 0, blockers

    def all_remaining_blocked(self, completed_step_count: int, step_results: list[dict]) -> bool:
        """
        True if every unexecuted required step is blocked by a failed dependency.
        Used for early termination.
        """
        for sn in range(completed_step_count + 1, self._total_steps + 1):
            if self._criticality.get(sn) != "required":
                continue
            can_run, blockers = self.can_execute(sn, step_results)
            if can_run:
                return False
        return True


def _build_system_prompt(tools_description: str, execution_strategy: str = "") -> str:
    """Build the executor's system prompt. Lean — tool definitions handled by Claude tools API."""
    today = date.today().isoformat()

    base = f"""\
You are an execution agent. You receive a plan with ordered steps and execute them
using the available tools. You are precise, careful, and follow the plan exactly.

TODAY'S DATE: {today}

EXECUTION RULES:
1. Execute each step using the specified tool with the specified parameters.
2. If a step fails, decide whether to retry with adjusted parameters, skip, or abort.
3. You may adapt parameters based on earlier step results (e.g., using generated file paths).
4. NEVER deviate from the plan's intent — you can adjust HOW but not WHAT.
5. Write COMPLETE file contents — never use placeholders like "// rest of code here".
6. Include proper error handling, imports, and types in all generated code.
7. For config files (package.json, tsconfig.json, etc.) use the right format for the ecosystem.
8. Execute tools one at a time. After each result, proceed to the next step.
9. Call _complete when all steps are done. Call _abort if execution cannot continue.
10. You MUST execute at least one real tool before calling _complete.
"""

    if execution_strategy:
        base += f"""
=== EXECUTION STRATEGY ===
{execution_strategy[:3000]}
=== END EXECUTION STRATEGY ===
"""

    return base


def execute_plan(
    plan: dict,
    registry: ToolRegistry,
    domain: str = "general",
    execution_strategy: str = "",
    workspace_dir: str = "",
    resume_from: dict | None = None,
    enable_mid_gates: bool = True,
) -> dict:
    """
    Execute a plan step-by-step using tools.

    Args:
        plan: Structured plan from planner (task_summary, steps, success_criteria)
        registry: Tool registry with available tools
        domain: Domain context
        execution_strategy: Execution strategy text
        workspace_dir: Base directory for file operations
        resume_from: Checkpoint data for partial re-execution (completed steps to skip)
        enable_mid_gates: Whether to run mid-execution quality gates

    Returns:
        Execution report dict with step results, artifacts, and summary
    """
    tools_desc = registry.get_tool_descriptions()
    system = _build_system_prompt(tools_desc, execution_strategy)

    # Get native Claude tool definitions (includes _complete and _abort)
    claude_tools = registry.get_execution_tools()

    steps = plan.get("steps", [])
    if not steps:
        return {
            "success": False,
            "error": "Plan has no steps",
            "step_results": [],
            "artifacts": [],
        }

    print(f"\n  [EXECUTOR] Executing {len(steps)} steps...")
    print(f"  [EXECUTOR] Task: {plan.get('task_summary', 'unknown')}")

    # Initialize timeout adapter with per-tool intelligent timeouts
    timeout_adapter = TimeoutAdapter(global_default=EXEC_STEP_TIMEOUT)

    # Initialize mid-execution quality gates
    mid_validator = MidExecutionValidator(plan) if enable_mid_gates else None
    if mid_validator and mid_validator.gate_points:
        print(f"  [EXECUTOR] Quality gates at steps: {sorted(mid_validator.gate_points)}")
    mid_gate_corrections = 0  # Track how many corrections were injected

    # Handle resume_from (partial re-execution)
    resumed_steps = []
    resumed_artifacts = []
    if resume_from:
        completed = resume_from.get("completed_steps", [])
        resumed_artifacts = resume_from.get("artifacts", [])
        # Build a summary of completed steps for the executor's context
        resume_summary_parts = []
        for sr in completed:
            if sr.get("success"):
                resumed_steps.append(sr)
                resume_summary_parts.append(
                    f"Step {sr.get('step', '?')} [{sr.get('tool', '?')}]: ✓ Completed — {sr.get('output', '')[:200]}"
                )
        if resumed_steps:
            print(f"  [EXECUTOR] Resuming — {len(resumed_steps)} steps already done, skipping to remaining")

    # Build initial context with the full plan
    plan_text = json.dumps(plan, indent=2)
    if resumed_steps:
        resume_context = "\n".join(
            f"Step {sr.get('step', '?')} [{sr.get('tool', '?')}]: ✓ Already completed"
            for sr in resumed_steps
        )
        conversation = [
            {
                "role": "user",
                "content": (
                    f"Execute this plan step by step. Some steps are already completed "
                    f"from a previous run — SKIP those and continue from where it left off.\n\n"
                    f"PLAN:\n{plan_text}\n\n"
                    f"ALREADY COMPLETED (DO NOT REDO):\n{resume_context}\n\n"
                    f"WORKSPACE: {workspace_dir or 'current directory'}\n\n"
                    f"Continue with the first uncompleted step."
                ),
            }
        ]
    else:
        conversation = [
            {
                "role": "user",
                "content": (
                    f"Execute this plan step by step. After each tool execution, "
                    f"I'll give you the result and you proceed to the next step.\n\n"
                    f"PLAN:\n{plan_text}\n\n"
                    f"WORKSPACE: {workspace_dir or 'current directory'}\n\n"
                    f"Begin with Step 1."
                ),
            }
        ]

    step_results = list(resumed_steps)  # Pre-populate with resumed steps
    all_artifacts = list(resumed_artifacts)
    total_input_tokens = 0
    total_output_tokens = 0
    max_turns = EXEC_MAX_STEPS * 3  # Allow some retries per step
    step_failures = {}  # Track retries per step: {step_num: retry_count}
    last_turn = 0  # Track the last turn for reporting
    health_monitor = ToolHealthMonitor()  # Track tool reliability
    dep_resolver = DependencyResolver(steps)  # Dependency-aware fail-fast
    blocked_step_count = 0  # Track skipped steps

    for turn in range(max_turns):
        last_turn = turn
        # Cost ceiling check — prevent runaway spending
        estimated_cost = (total_input_tokens * 0.25 + total_output_tokens * 1.25) / 1_000_000  # Haiku pricing
        if estimated_cost > MAX_EXECUTION_COST:
            print(f"  [EXECUTOR] ⚠ Cost ceiling reached (${estimated_cost:.4f} > ${MAX_EXECUTION_COST})")
            break

        # Sliding context window — proactively compress every turn (not just near limit)
        prev_size = _estimate_conversation_size(conversation)
        conversation = _apply_sliding_window(conversation, step_results, all_artifacts)
        new_size = _estimate_conversation_size(conversation)
        if new_size < prev_size * 0.7:
            print(f"  [EXECUTOR] Sliding window: {prev_size // 1000}K → {new_size // 1000}K chars")

        # Call model with native tool definitions (guaranteed structured output)
        response = create_message(
            client,
            model=MODELS["executor"],
            max_tokens=4096,
            system=system,
            messages=conversation,
            tools=claude_tools,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Dispatch on response content blocks (native tool_use API)
        tool_use_block = None
        text_content = ""
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use":
                tool_use_block = block
            elif hasattr(block, "text"):
                text_content += block.text

        # If no tool_use block, the model sent text — might need to handle it
        # Also try extract_json as fallback for compatibility
        if not tool_use_block:
            # Fallback: try to parse text as JSON (for backward compatibility)
            action_data = extract_json(text_content, expected_keys={"action"})
            if action_data and action_data.get("action") == "complete" and step_results:
                print(f"  [EXECUTOR] ✓ Complete: {action_data.get('summary', 'done')}")
                all_artifacts.extend(action_data.get("artifacts", []))
                break
            # Model is thinking aloud — nudge it to use tools
            conversation.append({"role": "assistant", "content": text_content or "..."})
            conversation.append({
                "role": "user",
                "content": "Please execute the next step by calling the appropriate tool.",
            })
            continue

        tool_name = tool_use_block.name
        tool_input = tool_use_block.input if hasattr(tool_use_block, "input") else {}
        tool_use_id = tool_use_block.id if hasattr(tool_use_block, "id") else "unknown"

        # --- Handle control tools ---
        if tool_name == "_complete":
            # Prevent premature completion without any tool use
            if not step_results:
                # Append the full response and reject
                conversation.append({"role": "assistant", "content": response.content})
                conversation.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                                 "content": "Cannot complete without executing any tools. Start with Step 1."}],
                })
                continue

            print(f"  [EXECUTOR] ✓ Complete: {tool_input.get('summary', 'done')}")
            all_artifacts.extend(tool_input.get("artifacts", []))
            break

        elif tool_name == "_abort":
            reason = tool_input.get("reason", "unknown")
            print(f"  [EXECUTOR] ✗ Aborted: {reason}")
            log_cost(
                model=MODELS["executor"],
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                agent_role="executor",
                domain=domain,
            )
            return {
                "success": False,
                "error": f"Execution aborted: {reason}",
                "step_results": step_results,
                "artifacts": all_artifacts,
                "completed_steps": tool_input.get("completed_steps", len(step_results)),
                "total_steps": len(steps),
            }

        # --- Handle real tool execution ---
        params = dict(tool_input) if isinstance(tool_input, dict) else {}
        reasoning = text_content[:200] if text_content else ""
        step_num = len(step_results) + 1

        # Dependency-aware fail-fast: skip blocked steps without LLM cost
        can_run, blockers = dep_resolver.can_execute(step_num, step_results)
        if not can_run:
            blocked_step_count += 1
            print(f"  [STEP {step_num}] BLOCKED by failed dependencies: {blockers}")
            step_results.append({
                "step": step_num,
                "tool": tool_name,
                "params": {},
                "reasoning": reasoning,
                "success": False,
                "output": "",
                "error": f"Blocked by failed dependency step(s): {blockers}",
                "artifacts": [],
                "status": "blocked_by_dependency",
                "blocked_by": blockers,
                "criticality": steps[step_num - 1].get("criticality", "required") if step_num <= len(steps) else "required",
            })
            conversation.append({"role": "assistant", "content": response.content})
            conversation.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                             "content": f"Step {step_num} SKIPPED — blocked by failed dependency step(s) {blockers}. Proceed to the next step."}],
            })
            if dep_resolver.all_remaining_blocked(step_num, step_results):
                print(f"  [EXECUTOR] All remaining required steps blocked — early termination")
                break
            continue

        # Look up step criticality from the plan
        criticality = "required"  # default
        if step_num <= len(steps):
            criticality = steps[step_num - 1].get("criticality", "required")

        print(f"  [STEP {step_num}] {tool_name}: {reasoning[:80]}")

        # Check tool health and inject warnings if degraded
        if health_monitor.is_degraded(tool_name):
            health_ctx = health_monitor.get_health_context()
            if health_ctx:
                print(f"           ⚠ Tool '{tool_name}' is degraded — consider alternatives")

        # Get adaptive timeout for this tool + params
        step_timeout = timeout_adapter.suggest(tool_name, params)

        # Execute the tool through the registry (with timeout for terminal)
        if tool_name == "terminal":
            params["timeout"] = step_timeout
        result = registry.execute(tool_name, **params)

        # Record duration in timeout adapter for future improvement
        duration_ms = result.metadata.get("duration_ms", 0)
        if duration_ms > 0:
            timeout_adapter.record(tool_name, duration_ms / 1000.0)

        # Record in health monitor
        health_monitor.record(tool_name, result.success, result.error)

        step_result = {
            "step": step_num,
            "tool": tool_name,
            "params": {k: (v[:200] if isinstance(v, str) and len(v) > 200 else v) for k, v in params.items()},
            "reasoning": reasoning,
            "success": result.success,
            "output": result.output[:2000],
            "error": result.error,
            "artifacts": result.artifacts,
            "criticality": criticality,
        }
        step_results.append(step_result)
        all_artifacts.extend(result.artifacts)

        status = "✓" if result.success else "✗"
        print(f"           {status} {result.output[:100] if result.success else result.error[:100]}")

        # Mid-execution quality gate check
        gate_correction = ""
        if mid_validator and result.success and mid_validator.should_gate(step_num, step_result):
            gate_issues = mid_validator.quick_validate(all_artifacts)
            if gate_issues:
                gate_correction = mid_validator.get_correction_prompt(gate_issues)
                mid_gate_corrections += 1
                print(f"           [GATE] Quality check at step {step_num}: {len(gate_issues)} issue(s) found")
                for gi in gate_issues[:3]:
                    print(f"             • {os.path.basename(gi['file'])}: {gi['detail'][:80]}")
            else:
                print(f"           [GATE] Step {step_num}: ✓ passed")

        # Step-level retry tracking with smart error analysis
        retry_msg = ""
        if not result.success:
            step_failures[step_num] = step_failures.get(step_num, 0) + 1
            retries_left = STEP_RETRY_LIMIT - step_failures[step_num]
            
            error_analysis = analyze_error(result.error, result.output)
            
            if criticality == "optional":
                retry_msg = (
                    f"\nThis optional step failed ({error_analysis['category']}). "
                    f"You may retry once or skip to the next step. "
                    f"Optional step failures do not block execution."
                )
                print(f"           [OPTIONAL] Step failed — non-blocking ({error_analysis['category']})")
            elif retries_left > 0 and error_analysis["retryable"]:
                retry_msg = format_retry_guidance(error_analysis, retries_left)
                print(f"           [RETRY] {retries_left} retries — {error_analysis['category']}")
            elif not error_analysis["retryable"]:
                retry_msg = format_retry_guidance(error_analysis, 0)
                print(f"           [SKIP] Non-retryable error: {error_analysis['category']}")
            else:
                retry_msg = (
                    f"\nThis step has failed {STEP_RETRY_LIMIT} times ({error_analysis['category']}). "
                    f"Move on to the next step or abort if this blocks progress."
                )

            health_ctx = health_monitor.get_health_context()
            if health_ctx:
                retry_msg += health_ctx

        # Build tool result message (native tool_result format)
        result_text = f"TOOL RESULT (step {step_num}):\n"
        if result.success:
            result_text += f"SUCCESS: {result.output[:3000]}"
        else:
            result_text += f"FAILED: {result.error}\nOutput: {result.output[:1000]}"

        if result.artifacts:
            result_text += f"\nArtifacts: {result.artifacts}"
        result_text += retry_msg
        if gate_correction:
            result_text += f"\n\n{gate_correction}"
        result_text += "\n\nProceed to the next step (or call _complete if all steps are done)."

        # Append assistant response + tool result in proper format
        conversation.append({"role": "assistant", "content": response.content})
        conversation.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": result_text}],
        })

    # Log total cost
    log_cost(
        model=MODELS["executor"],
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        agent_role="executor",
        domain=domain,
    )

    # Build execution report
    successful_steps = sum(1 for s in step_results if s["success"])
    failed_steps = sum(1 for s in step_results if not s["success"])
    failed_required = sum(1 for s in step_results if not s["success"] and s.get("criticality") == "required")
    failed_optional = sum(1 for s in step_results if not s["success"] and s.get("criticality") == "optional")
    retried_steps = sum(1 for v in step_failures.values() if v > 0)

    report = {
        "success": failed_required == 0 and successful_steps > 0,
        "task_summary": plan.get("task_summary", ""),
        "step_results": step_results,
        "artifacts": list(set(all_artifacts)),  # deduplicate
        "completed_steps": successful_steps,
        "failed_steps": failed_steps,
        "failed_required": failed_required,
        "failed_optional": failed_optional,
        "retried_steps": retried_steps,
        "blocked_steps": blocked_step_count,
        "total_steps": len(steps),
        "total_turns": last_turn + 1,
        "tool_health": health_monitor.get_health_report(),
        "mid_gate_corrections": mid_gate_corrections,
        "timeout_stats": timeout_adapter.stats(),
        "resumed_steps": len(resumed_steps),
        "is_repair": plan.get("is_repair", False),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return report
