"""
Architect Consultant -- Mid-execution escalation from cheap executor to premium model.

When the executor (DeepSeek) hits an architectural decision, error it can't resolve,
or needs guidance on implementation approach, it calls _consult. This module routes
that consultation to Claude (the premium model) with full project context.

This is THE communication channel between the cheap builder and the smart architect.
Without this, DeepSeek builds blind. With this, it has a lifeline.

Design:
- Lightweight: single LLM call per consultation, max 1000 tokens response
- Context-aware: includes project plan, completed steps, workspace state
- Capped: max 3 consultations per execution run (prevent cost spiral)
- Logged: every consultation tracked for meta-analysis
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import MODELS
from cost_tracker import log_cost

logger = logging.getLogger(__name__)

# Limits
MAX_CONSULTATIONS_PER_RUN = 3
CONSULTATION_MAX_TOKENS = 1024

# Consultation log for the current run
_run_consultations: list[dict] = []


def reset_consultations():
    """Reset consultation log for a new execution run."""
    global _run_consultations
    _run_consultations.clear()


def get_consultation_count() -> int:
    """How many consultations have been used in this run."""
    return len(_run_consultations)


def get_consultation_log() -> list[dict]:
    """Get all consultations from this run (for validator/meta-analysis)."""
    return list(_run_consultations)


def consult_architect(
    question: str,
    context: str,
    category: str = "other",
    plan: dict = None,
    step_results: list[dict] = None,
    workspace_dir: str = "",
    domain: str = "general",
) -> dict:
    """
    Route a consultation from the executor to Claude.
    
    Args:
        question: What the executor is asking
        context: Executor's description of the situation
        category: Type of consultation (architecture, code_pattern, error_diagnosis, design, dependency)
        plan: The current execution plan
        step_results: Results of steps completed so far
        workspace_dir: Current workspace directory
        domain: Domain context
    
    Returns:
        {
            "success": bool,
            "answer": str,       # Claude's response
            "directive": str,    # Short action instruction for the executor
            "consultation_num": int,  # Which consultation this is (1-indexed)
            "remaining": int,    # How many consultations left
            "error": str,        # Error message if failed
        }
    """
    from llm_router import call_llm
    
    consultation_num = len(_run_consultations) + 1
    remaining = MAX_CONSULTATIONS_PER_RUN - consultation_num
    
    result = {
        "success": False,
        "answer": "",
        "directive": "",
        "consultation_num": consultation_num,
        "remaining": remaining,
        "error": "",
    }
    
    # Enforce cap
    if consultation_num > MAX_CONSULTATIONS_PER_RUN:
        result["error"] = (
            f"Consultation limit reached ({MAX_CONSULTATIONS_PER_RUN} per run). "
            f"Make your best judgment and proceed."
        )
        result["answer"] = result["error"]
        result["directive"] = "Proceed with your best judgment."
        logger.warning(f"Consultation cap reached for domain={domain}")
        return result
    
    # Build context for Claude
    plan_summary = ""
    if plan:
        plan_summary = (
            f"Project: {plan.get('task_summary', 'unknown')}\n"
            f"Total steps: {len(plan.get('steps', []))}\n"
            f"Success criteria: {plan.get('success_criteria', 'N/A')}\n"
        )
        # Include step names for context
        step_names = [
            f"  Step {s.get('step', i+1)}: [{s.get('tool', '?')}] {s.get('description', '')[:80]}"
            for i, s in enumerate(plan.get("steps", []))
        ]
        plan_summary += "Steps:\n" + "\n".join(step_names[:20])
    
    progress_summary = ""
    if step_results:
        completed = [s for s in step_results if s.get("success")]
        failed = [s for s in step_results if not s.get("success") and s.get("status") != "blocked_by_dependency"]
        progress_summary = (
            f"Progress: {len(completed)} completed, {len(failed)} failed out of {len(step_results)} attempted.\n"
        )
        # Include last 3 step results for recency
        for sr in step_results[-3:]:
            status = "OK" if sr.get("success") else "FAIL"
            progress_summary += (
                f"  Step {sr.get('step', '?')} [{sr.get('tool', '?')}]: {status} "
                f"- {sr.get('output', sr.get('error', ''))[:150]}\n"
            )
    
    workspace_note = f"Workspace: {workspace_dir}" if workspace_dir else ""
    
    system_prompt = f"""\
You are the senior architect reviewing a build in progress.
A junior execution agent (DeepSeek) is asking for your guidance.

Your job:
1. Give a CONCRETE answer. No "it depends" -- make the decision.
2. Include specific code snippets or file paths when relevant.
3. Keep it under 300 words. The executor needs to act, not read essays.
4. End with a one-line DIRECTIVE: the single most important action to take.

Category: {category}
Domain: {domain}
{workspace_note}

PROJECT PLAN:
{plan_summary}

CURRENT PROGRESS:
{progress_summary}"""

    user_message = f"""\
QUESTION FROM EXECUTOR:
{question}

EXECUTOR'S CONTEXT:
{context}

Give a concrete, actionable answer. End with "DIRECTIVE: <one-line action>"."""

    start = time.monotonic()
    try:
        model = MODELS.get("exec_validator", MODELS.get("planner"))  # Use premium model
        response = call_llm(
            model=model,
            messages=[{"role": "user", "content": user_message}],
            system=system_prompt,
            max_tokens=CONSULTATION_MAX_TOKENS,
            temperature=0.3,  # Low temperature for decisive answers
        )
        
        # Extract answer
        answer_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                answer_text += block.text
        
        # Extract directive (last line starting with DIRECTIVE:)
        directive = ""
        for line in reversed(answer_text.strip().split("\n")):
            if line.strip().upper().startswith("DIRECTIVE:"):
                directive = line.strip().split(":", 1)[1].strip()
                break
        
        if not directive:
            # If no explicit directive, use last sentence
            sentences = answer_text.strip().rstrip(".").split(". ")
            directive = sentences[-1].strip() + "." if sentences else "Proceed."
        
        result["success"] = True
        result["answer"] = answer_text
        result["directive"] = directive
        
        # Log cost
        log_cost(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_role="consultant",
            domain=domain,
        )
        
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            f"Consultation #{consultation_num} for {domain} [{category}]: "
            f"{duration_ms:.0f}ms, {response.usage.input_tokens}+{response.usage.output_tokens} tokens"
        )
        
    except Exception as e:
        result["error"] = f"Consultation failed: {e}"
        result["answer"] = f"Consultation unavailable: {e}. Use your best judgment."
        result["directive"] = "Proceed with your best judgment."
        logger.error(f"Consultation failed: {e}")
    
    # Record for this run
    _run_consultations.append({
        "num": consultation_num,
        "category": category,
        "question": question[:500],
        "answer": result["answer"][:500],
        "directive": result["directive"],
        "success": result["success"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    return result
