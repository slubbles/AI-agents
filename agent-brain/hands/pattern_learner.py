"""
Execution Pattern Learner — Extracts reusable patterns from execution history.

The core self-improvement mechanism for Agent Hands. Analyzes past executions
to identify:
1. Tool usage patterns that correlate with high/low scores
2. Step sequences that reliably succeed or fail
3. Error categories and their resolutions
4. Domain-specific execution heuristics

These patterns are distilled into structured "execution lessons" that get
injected into future planner and executor prompts.

Lessons are more granular than strategies — they're specific observations like:
- "npm install fails without --prefix when cwd doesn't have package.json"
- "TypeScript projects need tsconfig.json created before src/ files"
- "Writing test files before source files causes import errors"
"""

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Optional


MAX_LESSONS = 50  # Keep top N lessons
MIN_EVIDENCE = 2  # Minimum occurrences before creating a lesson


class ExecutionLesson:
    """A single learned lesson from execution history."""

    def __init__(
        self,
        pattern: str,
        lesson: str,
        category: str,
        evidence_count: int = 0,
        success_impact: float = 0.0,
        domain: str = "",
        examples: list[str] | None = None,
    ):
        self.pattern = pattern  # What was observed
        self.lesson = lesson  # What to do about it
        self.category = category  # tool_usage, step_order, error_handling, etc.
        self.evidence_count = evidence_count
        self.success_impact = success_impact  # Score delta when pattern appears
        self.domain = domain
        self.examples = examples or []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.last_used = self.created_at

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "lesson": self.lesson,
            "category": self.category,
            "evidence_count": self.evidence_count,
            "success_impact": self.success_impact,
            "domain": self.domain,
            "examples": self.examples[:3],
            "created_at": self.created_at,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionLesson":
        lesson = cls(
            pattern=data.get("pattern", ""),
            lesson=data.get("lesson", ""),
            category=data.get("category", "general"),
            evidence_count=data.get("evidence_count", 0),
            success_impact=data.get("success_impact", 0.0),
            domain=data.get("domain", ""),
            examples=data.get("examples", []),
        )
        lesson.created_at = data.get("created_at", lesson.created_at)
        lesson.last_used = data.get("last_used", lesson.last_used)
        return lesson


class PatternLearner:
    """
    Learns execution patterns and distills them into lessons.
    
    Usage:
        learner = PatternLearner("exec_memory/_patterns.json")
        
        # After each execution
        learner.analyze_execution(exec_output)
        
        # Before planning
        lessons = learner.get_lessons(domain="nextjs-react", top_n=10)
        prompt_context = learner.format_lessons_for_prompt(lessons)
    """

    def __init__(self, lessons_path: str):
        self.lessons_path = lessons_path
        self._lessons: list[ExecutionLesson] = []
        self._load()

    def _load(self) -> None:
        """Load lessons from disk."""
        if os.path.exists(self.lessons_path):
            try:
                with open(self.lessons_path) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._lessons = [ExecutionLesson.from_dict(d) for d in data]
            except (json.JSONDecodeError, OSError):
                self._lessons = []

    def _save(self) -> None:
        """Save lessons to disk."""
        os.makedirs(os.path.dirname(self.lessons_path) or ".", exist_ok=True)
        # Sort by evidence count * success_impact (most impactful first)
        self._lessons.sort(
            key=lambda l: l.evidence_count * abs(l.success_impact),
            reverse=True,
        )
        # Keep only top N
        self._lessons = self._lessons[:MAX_LESSONS]
        with open(self.lessons_path, "w") as f:
            json.dump([l.to_dict() for l in self._lessons], f, indent=2)

    def _find_lesson(self, pattern: str) -> Optional[ExecutionLesson]:
        """Find an existing lesson by pattern."""
        for lesson in self._lessons:
            if lesson.pattern == pattern:
                return lesson
        return None

    def _add_or_update(self, pattern: str, lesson_text: str, category: str,
                       success_impact: float, domain: str, example: str = "") -> None:
        """Add a new lesson or reinforce an existing one."""
        existing = self._find_lesson(pattern)
        if existing:
            existing.evidence_count += 1
            # Smooth the success impact
            existing.success_impact = (
                existing.success_impact * 0.7 + success_impact * 0.3
            )
            if example and example not in existing.examples:
                existing.examples.append(example)
                existing.examples = existing.examples[-3:]  # Keep last 3
            existing.last_used = datetime.now(timezone.utc).isoformat()
        else:
            new_lesson = ExecutionLesson(
                pattern=pattern,
                lesson=lesson_text,
                category=category,
                evidence_count=1,
                success_impact=success_impact,
                domain=domain,
                examples=[example] if example else [],
            )
            self._lessons.append(new_lesson)

    def analyze_execution(self, exec_output: dict) -> list[str]:
        """
        Analyze a completed execution and extract patterns/lessons.
        
        Args:
            exec_output: Full execution output dict from exec_memory
            
        Returns:
            List of new lesson descriptions added
        """
        new_lessons = []
        domain = exec_output.get("domain", "general")
        score = exec_output.get("overall_score", 0)
        accepted = exec_output.get("accepted", False)
        report = exec_output.get("execution_report", {})
        plan = exec_output.get("plan", {})
        validation = exec_output.get("validation", {})

        step_results = report.get("step_results", [])
        if not step_results:
            return new_lessons

        # Score impact: positive for accepted, negative for rejected
        score_impact = score - 7.0  # 7 is the accept threshold

        # Pattern 1: Tool usage sequences that succeed/fail
        tool_sequence = [s.get("tool", "?") for s in step_results]
        success_sequence = [s.get("success", False) for s in step_results]

        # Find consecutive failures
        consecutive_fails = 0
        max_consecutive_fails = 0
        fail_tool = ""
        for i, (tool, success) in enumerate(zip(tool_sequence, success_sequence)):
            if not success:
                consecutive_fails += 1
                if consecutive_fails > max_consecutive_fails:
                    max_consecutive_fails = consecutive_fails
                    fail_tool = tool
            else:
                consecutive_fails = 0

        if max_consecutive_fails >= 2:
            pattern = f"consecutive_failures_{fail_tool}"
            lesson = (
                f"Tool '{fail_tool}' had {max_consecutive_fails} consecutive failures. "
                f"Consider breaking complex {fail_tool} operations into smaller steps."
            )
            self._add_or_update(pattern, lesson, "tool_usage", score_impact, domain,
                              f"Score: {score}, {max_consecutive_fails} consecutive fails")
            new_lessons.append(lesson)

        # Pattern 2: First step failures
        if step_results and not step_results[0].get("success", False):
            first_tool = step_results[0].get("tool", "?")
            first_error = step_results[0].get("error", "")[:100]
            pattern = f"first_step_failure_{first_tool}"
            lesson = (
                f"First step using '{first_tool}' often fails. "
                f"Common error: {first_error}. "
                f"Consider adding a setup/validation step before the main work."
            )
            self._add_or_update(pattern, lesson, "step_order", score_impact, domain,
                              f"Error: {first_error}")
            new_lessons.append(lesson)

        # Pattern 3: Tool that always succeeds (positive reinforcement)
        tool_success = defaultdict(lambda: {"success": 0, "total": 0})
        for sr in step_results:
            tool = sr.get("tool", "?")
            tool_success[tool]["total"] += 1
            if sr.get("success", False):
                tool_success[tool]["success"] += 1

        for tool, counts in tool_success.items():
            if counts["total"] >= 3 and counts["success"] == counts["total"]:
                pattern = f"reliable_tool_{tool}"
                lesson = f"Tool '{tool}' is highly reliable ({counts['total']}/{counts['total']} success)."
                self._add_or_update(pattern, lesson, "tool_usage", abs(score_impact), domain)

        # Pattern 4: Specific error patterns
        error_patterns = {
            "ENOENT": ("missing_file_error", "Ensure directories exist before writing files. Use mkdir -p or code tool's write (which auto-creates dirs)."),
            "ModuleNotFoundError": ("missing_module", "Install dependencies before importing. Add an explicit npm install/pip install step early in the plan."),
            "SyntaxError": ("syntax_error", "Validate code syntax before proceeding. Consider writing smaller functions and testing incrementally."),
            "permission denied": ("permission_error", "Check file permissions. The sandbox may block certain operations."),
            "not in allowed": ("sandbox_violation", "Command or path not in the sandbox allowlist. Use allowed alternatives."),
            "timed out": ("timeout_error", "Operation timed out. Break into smaller operations or increase timeout."),
        }

        for sr in step_results:
            error = sr.get("error", "")
            for error_key, (pattern, lesson) in error_patterns.items():
                if error_key.lower() in error.lower():
                    self._add_or_update(pattern, lesson, "error_handling", score_impact, domain,
                                      f"Seen in: {sr.get('tool', '?')} step")
                    if lesson not in new_lessons:
                        new_lessons.append(lesson)

        # Pattern 5: Score correlation with step count
        planned_steps = len(plan.get("steps", []))
        actual_steps = len(step_results)
        if actual_steps > planned_steps * 2:
            pattern = "plan_explosion"
            lesson = (
                f"Execution used {actual_steps} steps for a {planned_steps}-step plan. "
                f"Plans that explode in step count tend to score lower. "
                f"Create more detailed plans with explicit sub-steps."
            )
            self._add_or_update(pattern, lesson, "planning", score_impact, domain,
                              f"Planned: {planned_steps}, Actual: {actual_steps}")
            new_lessons.append(lesson)

        # Pattern 6: Validator feedback patterns
        weaknesses = validation.get("weaknesses", [])
        for w in weaknesses:
            w_lower = str(w).lower()
            if "test" in w_lower and "fail" in w_lower:
                self._add_or_update("test_failures", 
                    "Tests frequently fail on first run. Write simpler initial tests and iterate.",
                    "code_quality", score_impact, domain, str(w)[:100])
            elif "error handling" in w_lower:
                self._add_or_update("missing_error_handling",
                    "Add explicit error handling (try/catch) in generated code.",
                    "code_quality", score_impact, domain, str(w)[:100])

        self._save()
        return new_lessons

    def get_lessons(self, domain: str = "", category: str = "", top_n: int = 10) -> list[ExecutionLesson]:
        """
        Get top lessons, optionally filtered by domain and category.
        
        Lessons are ranked by evidence_count * |success_impact|.
        """
        filtered = self._lessons
        if domain:
            # Include domain-specific and general lessons
            filtered = [l for l in filtered if l.domain == domain or l.domain == "general" or not l.domain]
        if category:
            filtered = [l for l in filtered if l.category == category]

        # Only return lessons with sufficient evidence
        filtered = [l for l in filtered if l.evidence_count >= MIN_EVIDENCE]

        # Sort by impact
        filtered.sort(
            key=lambda l: l.evidence_count * abs(l.success_impact),
            reverse=True,
        )

        return filtered[:top_n]

    def format_lessons_for_prompt(self, lessons: list[ExecutionLesson] | None = None,
                                  domain: str = "", max_chars: int = 2000) -> str:
        """
        Format lessons as a string suitable for injection into planner/executor prompts.
        """
        if lessons is None:
            lessons = self.get_lessons(domain=domain)

        if not lessons:
            return ""

        parts = ["=== LEARNED EXECUTION LESSONS ==="]
        total_chars = len(parts[0])

        for i, lesson in enumerate(lessons):
            line = f"{i+1}. [{lesson.category}] {lesson.lesson}"
            if lesson.evidence_count > 2:
                line += f" (seen {lesson.evidence_count}x)"
            if total_chars + len(line) > max_chars:
                break
            parts.append(line)
            total_chars += len(line)

        parts.append("Apply these lessons to improve execution quality.")
        return "\n".join(parts)

    def stats(self) -> dict:
        """Get learner statistics."""
        categories = Counter(l.category for l in self._lessons)
        domains = Counter(l.domain for l in self._lessons)
        return {
            "total_lessons": len(self._lessons),
            "categories": dict(categories),
            "domains": dict(domains),
            "high_evidence": sum(1 for l in self._lessons if l.evidence_count >= 3),
            "avg_evidence": (
                sum(l.evidence_count for l in self._lessons) / len(self._lessons)
                if self._lessons else 0
            ),
        }
