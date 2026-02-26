"""
Plan Pre-Flight Validator — Structural checks before burning execution cost.

Problem: A bad plan burns the full execution budget before the validator catches it.
A 15-step execution that fails validation wastes ~$0.15–0.30. With retries, up to 3×.

Solution: Zero-cost structural pre-check between planning and execution.
Catches violations of known patterns, bad tool ordering, missing test steps,
and plans that will blow the cost ceiling — before any LLM execution happens.

Used by: main.py (after create_plan_hands, before execute_plan)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PreflightIssue:
    """A single pre-flight check result."""
    severity: str  # "blocker" or "warning"
    category: str
    message: str


@dataclass
class PreflightResult:
    """Result of pre-flight validation."""
    issues: list[PreflightIssue] = field(default_factory=list)
    
    @property
    def blockers(self) -> list[PreflightIssue]:
        return [i for i in self.issues if i.severity == "blocker"]
    
    @property
    def warnings(self) -> list[PreflightIssue]:
        return [i for i in self.issues if i.severity == "warning"]
    
    @property
    def passed(self) -> bool:
        return len(self.blockers) == 0
    
    def format(self) -> str:
        """Format issues for feedback to planner."""
        lines = []
        for i in self.blockers:
            lines.append(f"BLOCKER [{i.category}]: {i.message}")
        for i in self.warnings:
            lines.append(f"WARNING [{i.category}]: {i.message}")
        return "\n".join(lines)


def preflight_check(
    plan: dict,
    domain: str = "general",
    pattern_learner: Optional[object] = None,
    artifact_quality_db: Optional[object] = None,
    cost_ceiling: float = 0.50,
) -> PreflightResult:
    """
    Run structural pre-flight checks on a plan.
    
    Zero LLM cost. Pure structural validation.

    Args:
        plan: Structured plan from planner
        domain: Domain context
        pattern_learner: PatternLearner instance (optional, for lesson checks)
        artifact_quality_db: ArtifactQualityDB instance (optional)
        cost_ceiling: Max execution cost ($)
    
    Returns:
        PreflightResult with blockers/warnings
    """
    result = PreflightResult()
    steps = plan.get("steps", [])
    
    if not steps:
        result.issues.append(PreflightIssue("blocker", "empty_plan", "Plan has no steps"))
        return result
    
    _check_step_ordering(steps, result)
    _check_completeness(steps, plan, result)
    _check_cost_estimate(steps, cost_ceiling, result)
    
    if pattern_learner:
        _check_lesson_violations(steps, domain, pattern_learner, result)
    
    if artifact_quality_db:
        _check_weak_archetypes(steps, domain, artifact_quality_db, result)
    
    return result


def _check_step_ordering(steps: list[dict], result: PreflightResult) -> None:
    """Check for bad step ordering patterns."""
    
    # Check: dependencies reference future steps
    step_nums = {s.get("step_number", i + 1) for i, s in enumerate(steps)}
    for step in steps:
        sn = step.get("step_number", 0)
        for dep in step.get("depends_on", []):
            if dep >= sn:
                result.issues.append(PreflightIssue(
                    "blocker", "ordering",
                    f"Step {sn} depends on future step {dep}",
                ))
            if dep not in step_nums:
                result.issues.append(PreflightIssue(
                    "warning", "ordering",
                    f"Step {sn} depends on non-existent step {dep}",
                ))
    
    # Check: code write before config setup
    # If a config file (package.json, tsconfig) exists in the plan,
    # it should come before source code writes
    config_step = None
    source_step = None
    for step in steps:
        params = step.get("params", {})
        path = (params.get("path", "") or params.get("file_path", "")).lower()
        basename = os.path.basename(path)
        sn = step.get("step_number", 0)
        
        if basename in ("package.json", "tsconfig.json", "pyproject.toml", "requirements.txt", "cargo.toml"):
            if config_step is None:
                config_step = sn
        elif path.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs")):
            if source_step is None:
                source_step = sn
    
    if config_step and source_step and config_step > source_step:
        result.issues.append(PreflightIssue(
            "warning", "ordering",
            f"Config file at step {config_step} comes after source code at step {source_step} — "
            f"config should be created first",
        ))
    
    # Check: all steps use the same tool (suspicious — likely bad plan)
    tools_used = set(s.get("tool", "") for s in steps)
    if len(steps) > 3 and len(tools_used) == 1 and "code" in tools_used:
        result.issues.append(PreflightIssue(
            "warning", "diversity",
            "All steps use only 'code' tool — consider adding terminal steps for install/test",
        ))


def _check_completeness(steps: list[dict], plan: dict, result: PreflightResult) -> None:
    """Check for missing essential steps."""
    
    has_test_step = False
    has_verify_step = False
    tools_used = set()
    
    for step in steps:
        tool = step.get("tool", "")
        desc = step.get("description", "").lower()
        tools_used.add(tool)
        
        if "test" in desc or "verify" in desc or "check" in desc:
            has_test_step = True
        if tool == "terminal" and ("test" in desc or "run" in desc or "verify" in desc):
            has_verify_step = True
    
    # Warn if no verification step exists
    if len(steps) >= 4 and not has_test_step and not has_verify_step:
        result.issues.append(PreflightIssue(
            "warning", "completeness",
            "No test/verification step found — add a step to verify the output works",
        ))
    
    # Check: plan has steps that duplicate each other (same tool + same path)
    seen_actions = set()
    for step in steps:
        tool = step.get("tool", "")
        params = step.get("params", {})
        path = params.get("path", "") or params.get("file_path", "")
        action = params.get("action", "write")
        key = f"{tool}:{action}:{path}"
        if path and key in seen_actions:
            result.issues.append(PreflightIssue(
                "warning", "duplicate",
                f"Step {step.get('step_number', '?')} duplicates action on {os.path.basename(path)}",
            ))
        if path:
            seen_actions.add(key)


def _check_cost_estimate(steps: list[dict], ceiling: float, result: PreflightResult) -> None:
    """Estimate if the plan will exceed the cost ceiling."""
    # Rough estimation: each step costs ~2 turns of Haiku conversation
    # Average: ~1K input + 0.5K output per turn
    estimated_turns = len(steps) * 2.5
    estimated_input_tokens = estimated_turns * 2000  # Growing conversation
    estimated_output_tokens = estimated_turns * 500
    
    # Haiku pricing: $0.25/M input, $1.25/M output
    estimated_cost = (estimated_input_tokens * 0.25 + estimated_output_tokens * 1.25) / 1_000_000
    
    if estimated_cost > ceiling * 0.8:
        result.issues.append(PreflightIssue(
            "warning", "cost",
            f"Estimated execution cost ~${estimated_cost:.3f} approaches ceiling ${ceiling:.2f}",
        ))
    
    if estimated_cost > ceiling:
        result.issues.append(PreflightIssue(
            "blocker", "cost",
            f"Estimated execution cost ~${estimated_cost:.3f} exceeds ceiling ${ceiling:.2f} — simplify the plan",
        ))


def _check_lesson_violations(
    steps: list[dict],
    domain: str,
    pattern_learner: object,
    result: PreflightResult,
) -> None:
    """Check if the plan violates known execution lessons."""
    try:
        lessons = pattern_learner.get_lessons(domain=domain)  # type: ignore
    except Exception:
        return
    
    if not lessons:
        return
    
    # Check for lessons about specific tools or patterns
    for lesson in lessons:
        pattern = getattr(lesson, "pattern", "") or ""
        recommendation = getattr(lesson, "recommendation", "") or ""
        evidence = getattr(lesson, "evidence_count", 0) or 0
        
        if evidence < 2:
            continue  # Not enough evidence
        
        # Check: plan uses a tool that has reliability warnings
        if "consecutive" in pattern.lower() and "failure" in pattern.lower():
            # Extract tool name from pattern if possible
            for step in steps:
                tool = step.get("tool", "")
                if tool.lower() in pattern.lower():
                    result.issues.append(PreflightIssue(
                        "warning", "lesson",
                        f"Step {step.get('step_number', '?')} uses '{tool}' which has known issues: {recommendation[:100]}",
                    ))
                    break


def _check_weak_archetypes(
    steps: list[dict],
    domain: str,
    quality_db: object,
    result: PreflightResult,
) -> None:
    """Warn about steps that will produce historically weak file types."""
    try:
        from hands.artifact_tracker import classify_archetype
        weak = quality_db.get_weak_archetypes(domain)  # type: ignore
    except Exception:
        return
    
    if not weak:
        return
    
    weak_types = {w["archetype"] for w in weak}
    
    for step in steps:
        params = step.get("params", {})
        path = params.get("path", "") or params.get("file_path", "")
        if not path:
            continue
        archetype = classify_archetype(path)
        if archetype in weak_types:
            match = next((w for w in weak if w["archetype"] == archetype), None)
            if match:
                result.issues.append(PreflightIssue(
                    "warning", "weak_archetype",
                    f"Step {step.get('step_number', '?')} creates {archetype} "
                    f"(avg {match['avg_score']}/10) — pay extra attention to quality",
                ))
