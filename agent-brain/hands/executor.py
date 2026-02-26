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


client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Context window management
MAX_CONVERSATION_TOKENS_ESTIMATE = 150_000  # Stay well under limit
CHARS_PER_TOKEN_ESTIMATE = 4
MAX_CONVERSATION_CHARS = MAX_CONVERSATION_TOKENS_ESTIMATE * CHARS_PER_TOKEN_ESTIMATE
STEP_RETRY_LIMIT = 2  # Retries per individual step


def _estimate_conversation_size(conversation: list[dict]) -> int:
    """Estimate the total character count of a conversation."""
    return sum(len(msg.get("content", "")) for msg in conversation)


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

    # Summarize middle messages
    summary_parts = []
    step_num = 0
    for msg in middle:
        content = msg.get("content", "")
        if msg["role"] == "user" and "TOOL RESULT" in content:
            step_num += 1
            # Extract just success/failure and truncated output
            if "SUCCESS:" in content:
                brief = content[content.index("SUCCESS:"):content.index("SUCCESS:") + 200]
                summary_parts.append(f"Step {step_num}: ✓ {brief[:150]}")
            elif "FAILED:" in content:
                brief = content[content.index("FAILED:"):content.index("FAILED:") + 200]
                summary_parts.append(f"Step {step_num}: ✗ {brief[:150]}")

    summary = {
        "role": "user",
        "content": (
            f"[CONTEXT SUMMARY — {len(middle)} messages compressed]\n"
            f"Previous step results:\n" + "\n".join(summary_parts) +
            f"\n\nContinue with the current step."
        ),
    }

    return [first, summary] + recent


def _build_system_prompt(tools_description: str, execution_strategy: str = "") -> str:
    """Build the executor's system prompt."""
    today = date.today().isoformat()

    base = f"""\
You are an execution agent. You receive a plan with ordered steps and execute them
using the available tools. You are precise, careful, and follow the plan exactly.

TODAY'S DATE: {today}

AVAILABLE TOOLS:
{tools_description}

EXECUTION RULES:
1. Execute each step using the specified tool with the specified parameters.
2. If a step fails, describe the error and decide whether to:
   a) Retry with adjusted parameters
   b) Skip and note the failure
   c) Abort if the failure blocks subsequent steps
3. You may adapt parameters based on earlier step results (e.g., using generated file paths).
4. NEVER deviate from the plan's intent — you can adjust HOW but not WHAT.
5. After each step, report the result clearly.
6. Write COMPLETE file contents — never use placeholders like "// rest of code here".
7. Include proper error handling, imports, and types in all generated code.
8. For config files (package.json, tsconfig.json, etc.) use the right format for the ecosystem.
9. IMPORTANT: You MUST execute tools one at a time. Do NOT describe what you would do — actually DO it by outputting the JSON action.
10. You are NOT allowed to use the "complete" action until you have executed at least one tool.

When you need to execute a tool, respond with ONLY this JSON:
{{
  "action": "execute_tool",
  "tool": "tool_name",
  "params": {{"param1": "value1"}},
  "reasoning": "Why this action"
}}

When you are done with all steps, respond with:
{{
  "action": "complete",
  "summary": "What was accomplished",
  "artifacts": ["list", "of", "created", "files"]
}}

If you need to abort, respond with:
{{
  "action": "abort",
  "reason": "Why execution cannot continue",
  "completed_steps": 3
}}
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
) -> dict:
    """
    Execute a plan step-by-step using tools.

    Args:
        plan: Structured plan from planner (task_summary, steps, success_criteria)
        registry: Tool registry with available tools
        domain: Domain context
        execution_strategy: Execution strategy text
        workspace_dir: Base directory for file operations

    Returns:
        Execution report dict with step results, artifacts, and summary
    """
    tools_desc = registry.get_tool_descriptions()
    system = _build_system_prompt(tools_desc, execution_strategy)

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

    # Build initial context with the full plan
    plan_text = json.dumps(plan, indent=2)
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

    step_results = []
    all_artifacts = []
    total_input_tokens = 0
    total_output_tokens = 0
    max_turns = EXEC_MAX_STEPS * 3  # Allow some retries per step
    step_failures = {}  # Track retries per step: {step_num: retry_count}

    for turn in range(max_turns):
        # Context window management — compress old turns if conversation grows large
        conv_size = _estimate_conversation_size(conversation)
        if conv_size > MAX_CONVERSATION_CHARS * 0.7:
            conversation = _summarize_old_steps(conversation)
            print(f"  [EXECUTOR] Context compressed ({conv_size // 1000}K chars → {_estimate_conversation_size(conversation) // 1000}K)")

        # Call the model
        response = create_message(
            client,
            model=MODELS["executor"],
            max_tokens=4096,
            system=system,
            messages=conversation,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Extract response text
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        # Parse the action
        action_data = extract_json(text, expected_keys={"action"})

        if not action_data:
            # Model didn't return valid JSON — try to recover
            conversation.append({"role": "assistant", "content": text})
            conversation.append({
                "role": "user",
                "content": (
                    "Your response was not valid JSON. Please respond with the exact JSON format "
                    "specified in your instructions. Execute the next step."
                ),
            })
            continue

        action = action_data.get("action", "")

        if action == "complete":
            # Prevent premature completion without any tool use
            if not step_results:
                conversation.append({"role": "assistant", "content": text})
                conversation.append({
                    "role": "user",
                    "content": (
                        "You cannot mark as complete without executing any tools. "
                        "You MUST use the tools to create files, run commands, etc. "
                        "Start with Step 1 from the plan."
                    ),
                })
                continue

            # Execution finished
            print(f"  [EXECUTOR] ✓ Complete: {action_data.get('summary', 'done')}")
            all_artifacts.extend(action_data.get("artifacts", []))
            break

        elif action == "abort":
            # Execution aborted
            reason = action_data.get("reason", "unknown")
            print(f"  [EXECUTOR] ✗ Aborted: {reason}")
            # Log cost before returning
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
                "completed_steps": action_data.get("completed_steps", len(step_results)),
                "total_steps": len(steps),
            }

        elif action == "execute_tool":
            # Execute a tool
            tool_name = action_data.get("tool", "")
            params = action_data.get("params", {})
            reasoning = action_data.get("reasoning", "")
            step_num = len(step_results) + 1

            print(f"  [STEP {step_num}] {tool_name}: {reasoning[:80]}")

            # Execute the tool through the registry
            result = registry.execute(tool_name, **params)

            step_result = {
                "step": step_num,
                "tool": tool_name,
                "params": {k: (v[:200] if isinstance(v, str) and len(v) > 200 else v) for k, v in params.items()},
                "reasoning": reasoning,
                "success": result.success,
                "output": result.output[:2000],
                "error": result.error,
                "artifacts": result.artifacts,
            }
            step_results.append(step_result)
            all_artifacts.extend(result.artifacts)

            status = "✓" if result.success else "✗"
            print(f"           {status} {result.output[:100] if result.success else result.error[:100]}")

            # Step-level retry tracking
            retry_msg = ""
            if not result.success:
                step_failures[step_num] = step_failures.get(step_num, 0) + 1
                retries_left = STEP_RETRY_LIMIT - step_failures[step_num]
                if retries_left > 0:
                    retry_msg = (
                        f"\nThis step failed. You have {retries_left} retries left for this step. "
                        f"Analyze the error and try again with corrected parameters, "
                        f"or skip to the next step if the error is not recoverable."
                    )
                    print(f"           [RETRY] {retries_left} retries remaining for step {step_num}")
                else:
                    retry_msg = (
                        f"\nThis step has failed {STEP_RETRY_LIMIT} times. "
                        f"Move on to the next step or abort if this blocks progress."
                    )

            # Feed result back into conversation
            conversation.append({"role": "assistant", "content": text})
            result_msg = f"TOOL RESULT (step {step_num}):\n"
            if result.success:
                result_msg += f"SUCCESS: {result.output[:3000]}"
            else:
                result_msg += f"FAILED: {result.error}\nOutput: {result.output[:1000]}"

            if result.artifacts:
                result_msg += f"\nArtifacts: {result.artifacts}"

            result_msg += retry_msg
            result_msg += "\n\nProceed to the next step (or 'complete' if all steps are done)."
            conversation.append({"role": "user", "content": result_msg})

        else:
            # Unknown action
            conversation.append({"role": "assistant", "content": text})
            conversation.append({
                "role": "user",
                "content": f"Unknown action '{action}'. Use 'execute_tool', 'complete', or 'abort'.",
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
    retried_steps = sum(1 for v in step_failures.values() if v > 0)

    report = {
        "success": failed_steps == 0 and successful_steps > 0,
        "task_summary": plan.get("task_summary", ""),
        "step_results": step_results,
        "artifacts": list(set(all_artifacts)),  # deduplicate
        "completed_steps": successful_steps,
        "failed_steps": failed_steps,
        "retried_steps": retried_steps,
        "total_steps": len(steps),
        "total_turns": turn + 1 if 'turn' in dir() else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return report
