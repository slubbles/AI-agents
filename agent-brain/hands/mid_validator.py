"""
Mid-Execution Quality Gates — Static validation checkpoints during execution.

Problem: Without mid-execution gates, a broken file written at step 3 propagates
through 17 more steps before the final validator catches it. This wastes ~75% of
execution cost building on a broken foundation.

Solution: Insert zero-cost static checks at natural breakpoints during execution.
No LLM calls — only syntax/structure validation (JSON parse, Python compile, etc).
If issues are found, inject a correction prompt into the executor's conversation
so the LLM can self-correct before proceeding.

Gate points are identified from the plan:
1. After setup steps (package.json, tsconfig, etc.)
2. After core logic steps (before optional/styling steps)
3. At the midpoint of any plan > 8 steps
4. After any step that creates a file used by 2+ later steps (fan-out)

Used by: executor.py (checks gates after each successful step)
"""

import json
import os
import re
import subprocess
import sys
from typing import Optional


# Extensions that can be statically checked
_CHECKABLE_EXTENSIONS = {
    ".json", ".py", ".yaml", ".yml", ".html", ".htm",
    ".js", ".ts", ".jsx", ".tsx", ".css",
}

# Setup file patterns (gate after these)
_SETUP_PATTERNS = {
    "package.json", "tsconfig.json", "pyproject.toml", "setup.py",
    "requirements.txt", "Cargo.toml", "go.mod", "Makefile",
    "docker-compose.yml", "Dockerfile", ".env",
}


class MidExecutionValidator:
    """
    Runs static quality checks at strategic points during execution.
    
    Usage:
        mid_val = MidExecutionValidator(plan_data)
        
        # After each step completes:
        if mid_val.should_gate(step_num, step_result):
            issues = mid_val.quick_validate(all_artifacts_so_far)
            if issues:
                correction = mid_val.get_correction_prompt(issues)
                # Inject into executor conversation
    """

    def __init__(self, plan: dict, min_steps_for_midpoint: int = 8):
        self.plan = plan
        self.steps = plan.get("steps", [])
        self.gate_points = self._identify_gate_points(min_steps_for_midpoint)
        self._checked_artifacts: set[str] = set()  # Avoid re-checking

    def _identify_gate_points(self, min_steps_for_midpoint: int) -> set[int]:
        """
        Identify step numbers after which to run quality gates.
        """
        gates = set()
        n = len(self.steps)
        if n == 0:
            return gates

        # 1. After setup steps (package.json, config files, etc.)
        for step in self.steps:
            sn = step.get("step_number", 0)
            params = step.get("params", {})
            path = params.get("path", "") or params.get("file_path", "")
            basename = os.path.basename(path).lower() if path else ""

            if basename in _SETUP_PATTERNS:
                gates.add(sn)

            # Detect setup from description
            desc = step.get("description", "").lower()
            if any(kw in desc for kw in ["setup", "initialize", "configure", "install"]):
                gates.add(sn)

        # 2. Midpoint gate for large plans
        if n >= min_steps_for_midpoint:
            gates.add(n // 2)

        # 3. Fan-out detection: steps whose output is used by 2+ others
        usage_count: dict[int, int] = {}
        for step in self.steps:
            for dep in step.get("depends_on", []):
                usage_count[dep] = usage_count.get(dep, 0) + 1

        for step_num, count in usage_count.items():
            if count >= 2:
                gates.add(step_num)

        # 4. Gate before the last step (catch issues before "done")
        if n > 3:
            gates.add(n - 1)

        return gates

    def should_gate(self, step_num: int, step_result: Optional[dict] = None) -> bool:
        """
        Check if a quality gate should run after this step.
        
        Only gates on successful steps (no point checking artifacts from failures).
        """
        if step_result and not step_result.get("success", False):
            return False
        return step_num in self.gate_points

    def quick_validate(self, artifacts: list[str]) -> list[dict]:
        """
        Run fast static checks on all new artifacts since last gate.
        
        Returns list of issues: [{file, check, detail}, ...]
        Zero LLM cost — only file I/O and basic parsing.
        """
        issues = []
        new_artifacts = [a for a in artifacts if a not in self._checked_artifacts]
        
        for path in new_artifacts:
            self._checked_artifacts.add(path)
            
            if not os.path.isfile(path):
                # File referenced as artifact but doesn't exist
                issues.append({
                    "file": path,
                    "check": "exists",
                    "detail": "Artifact file does not exist",
                })
                continue

            ext = os.path.splitext(path)[1].lower()
            basename = os.path.basename(path).lower()

            # Check: file is not empty
            try:
                size = os.path.getsize(path)
                if size == 0:
                    issues.append({
                        "file": path,
                        "check": "not_empty",
                        "detail": "File is empty (0 bytes)",
                    })
                    continue
            except OSError:
                continue

            # Check: JSON valid
            if ext == ".json" or basename in ("package.json", "tsconfig.json"):
                try:
                    with open(path, "r") as f:
                        json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    issues.append({
                        "file": path,
                        "check": "json_valid",
                        "detail": f"Invalid JSON: {str(e)[:150]}",
                    })

            # Check: Python syntax
            elif ext == ".py":
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "py_compile", path],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode != 0:
                        detail = result.stderr.strip()[:200] or "Syntax error"
                        issues.append({
                            "file": path,
                            "check": "python_syntax",
                            "detail": detail,
                        })
                except (subprocess.TimeoutExpired, OSError):
                    pass

            # Check: JS/TS basic syntax (look for obvious broken patterns)
            elif ext in (".js", ".ts", ".jsx", ".tsx"):
                try:
                    with open(path, "r", errors="replace") as f:
                        content = f.read(20000)
                    # Check for unmatched braces (simple heuristic)
                    opens = content.count("{") + content.count("[") + content.count("(")
                    closes = content.count("}") + content.count("]") + content.count(")")
                    if abs(opens - closes) > 3:
                        issues.append({
                            "file": path,
                            "check": "bracket_balance",
                            "detail": f"Potentially unmatched brackets: {opens} opens vs {closes} closes",
                        })
                except OSError:
                    pass

            # Check: YAML valid
            elif ext in (".yaml", ".yml"):
                try:
                    import yaml
                    with open(path, "r") as f:
                        yaml.safe_load(f)
                except ImportError:
                    pass
                except Exception as e:
                    issues.append({
                        "file": path,
                        "check": "yaml_valid",
                        "detail": f"Invalid YAML: {str(e)[:150]}",
                    })

            # Check: HTML basic structure
            elif ext in (".html", ".htm"):
                try:
                    with open(path, "r", errors="replace") as f:
                        content = f.read(10000)
                    if ("<html" not in content.lower() and 
                        "<!doctype" not in content.lower() and
                        len(content) > 50):
                        issues.append({
                            "file": path,
                            "check": "html_structure",
                            "detail": "Missing <html> or <!DOCTYPE> tag",
                        })
                except OSError:
                    pass

        return issues

    def get_correction_prompt(self, issues: list[dict]) -> str:
        """
        Generate a correction message for the executor based on found issues.
        """
        if not issues:
            return ""

        lines = [
            "⚠️ MID-EXECUTION QUALITY CHECK — Issues detected:",
            "",
        ]
        for issue in issues:
            lines.append(f"  • {os.path.basename(issue['file'])} [{issue['check']}]: {issue['detail']}")

        lines.extend([
            "",
            "FIX these issues before proceeding to the next step.",
            "Rewrite the problematic file(s) with correct content.",
            "Then continue with the remaining plan steps.",
        ])

        return "\n".join(lines)

    def get_gate_summary(self) -> dict:
        """Returns summary of gate points for diagnostics."""
        return {
            "total_steps": len(self.steps),
            "gate_points": sorted(self.gate_points),
            "artifacts_checked": len(self._checked_artifacts),
        }
