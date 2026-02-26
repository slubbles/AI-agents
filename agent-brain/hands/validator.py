"""
Execution Validator — Scores execution output quality.

Parallel to Brain's critic.py but for code/execution output.
Evaluates on different dimensions suited to execution quality.

Now reads actual artifact file contents for accurate evaluation,
not just step output summaries.

Scoring Rubric (5 dimensions):
- Correctness (30%) — Does the code work? Does it do what was asked?
- Completeness (20%) — All requirements met? No missing pieces?
- Code Quality (20%) — Clean, idiomatic, well-structured?
- Security (15%) — Safe patterns? No vulnerabilities?
- KB Alignment (15%) — Uses best practices from Brain's knowledge?
"""

import json
import os
import re
import subprocess
import sys
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS, EXEC_QUALITY_THRESHOLD
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json

client = Anthropic(api_key=ANTHROPIC_API_KEY)

DEFAULT_EXEC_RUBRIC = {
    "correctness": 0.30,
    "completeness": 0.20,
    "code_quality": 0.20,
    "security": 0.15,
    "kb_alignment": 0.15,
}


def _build_validator_prompt(rubric: dict | None = None) -> str:
    """Build the validator's system prompt."""
    today = date.today().isoformat()
    w = rubric or DEFAULT_EXEC_RUBRIC

    cor = int(w["correctness"] * 100)
    com = int(w["completeness"] * 100)
    qual = int(w["code_quality"] * 100)
    sec = int(w["security"] * 100)
    kb = int(w["kb_alignment"] * 100)

    return f"""\
You are a strict execution validator. Your job is to evaluate code and execution output
for quality, correctness, and adherence to best practices.

TODAY'S DATE: {today}

You score on 5 dimensions (each 1-10):
1. **Correctness** — Does the code work? Does it accomplish the stated task? Are there bugs?
2. **Completeness** — Are all requirements met? All files created? All features implemented?
3. **Code Quality** — Is the code clean, idiomatic, well-structured? Proper error handling? Types?
4. **Security** — Safe patterns? No vulnerabilities (XSS, injection, exposed secrets)?
5. **KB Alignment** — Does it follow best practices from the domain knowledge base?

Overall score = weighted average (Correctness {cor}%, Completeness {com}%, Quality {qual}%, Security {sec}%, KB {kb}%)

EVALUATION RULES:
- A file with just placeholders or TODO comments is NOT complete — score 1-2.
- Working code with minor issues = 6-7. Production-quality = 8+.
- If tests exist and pass, that's a strong correctness signal.
- If tests exist and fail, that's a strong correctness penalty.
- Code without ANY error handling = max 5 on quality.
- Hardcoded secrets = max 3 on security.
- IMPORTANT: You will receive the actual file contents of produced artifacts.
  Read the code carefully — verify imports, types, logic flow, and completeness.
  Do NOT just trust step summaries — the code itself is the ground truth.

Output ONLY valid JSON:
{{
    "scores": {{
        "correctness": 7,
        "completeness": 6,
        "code_quality": 5,
        "security": 8,
        "kb_alignment": 6
    }},
    "overall_score": 6.4,
    "strengths": ["what was done well"],
    "weaknesses": ["what was done poorly"],
    "actionable_feedback": "specific instructions for how to improve if re-executed",
    "verdict": "accept|reject",
    "critical_issues": ["any blocking issues that must be fixed"]
}}

Threshold for accept: overall_score >= {EXEC_QUALITY_THRESHOLD}.
Be harsh but fair. The system depends on honest evaluation.
"""


# Binary/non-text file extensions to skip when reading artifacts
_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".wasm",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".pyc", ".pyo", ".class", ".o",
    ".db", ".sqlite", ".sqlite3",
}

# File extensions to prioritize reading (most informative for validation)
_PRIORITY_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".md", ".html", ".css", ".sql",
    ".sh", ".bash", ".dockerfile", ".env.example",
}

# Max total chars of artifact content we'll send to the validator
_MAX_ARTIFACT_CHARS = 40_000
# Max chars per individual file
_MAX_FILE_CHARS = 8_000


def _read_artifact_files(artifacts: list[str]) -> dict[str, str]:
    """
    Read actual file contents from artifact paths.
    Prioritizes key files (package.json, entry points, configs, tests).
    Skips binary files. Caps total size to stay within context limits.

    Returns:
        Dict mapping file path to content string
    """
    if not artifacts:
        return {}

    contents = {}
    total_chars = 0

    # Deduplicate and filter
    unique_paths = list(dict.fromkeys(artifacts))  # preserve order, dedupe

    # Separate into priority and non-priority files
    priority_files = []
    other_files = []
    for path in unique_paths:
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext in _BINARY_EXTENSIONS:
            continue
        basename = os.path.basename(path).lower()
        # Boost config files and tests
        if (ext in _PRIORITY_EXTENSIONS
                or basename in ("package.json", "tsconfig.json", "pyproject.toml",
                                "readme.md", "dockerfile", ".gitignore",
                                "requirements.txt", "setup.py", "setup.cfg")):
            priority_files.append(path)
        else:
            other_files.append(path)

    # Read priority files first, then others
    for path in priority_files + other_files:
        if total_chars >= _MAX_ARTIFACT_CHARS:
            break
        try:
            with open(path, "r", errors="replace") as f:
                content = f.read(_MAX_FILE_CHARS + 100)
            if len(content) > _MAX_FILE_CHARS:
                content = content[:_MAX_FILE_CHARS] + f"\n... (truncated at {_MAX_FILE_CHARS} chars)"
            contents[path] = content
            total_chars += len(content)
        except (OSError, UnicodeDecodeError):
            contents[path] = "(unable to read file)"

    return contents


def _run_static_checks(artifacts: list[str]) -> dict:
    """
    Run basic static checks on artifact files before LLM validation.
    
    Returns dict with:
        - checks_run: int
        - issues: list of {file, check, detail}
        - passes: list of {file, check}
    """
    results = {"checks_run": 0, "issues": [], "passes": []}
    
    for path in artifacts:
        if not os.path.isfile(path):
            results["checks_run"] += 1
            results["issues"].append({
                "file": path, "check": "exists",
                "detail": "File does not exist"
            })
            continue
        
        ext = os.path.splitext(path)[1].lower()
        basename = os.path.basename(path).lower()
        
        # Check: file is not empty
        try:
            size = os.path.getsize(path)
            results["checks_run"] += 1
            if size == 0:
                results["issues"].append({
                    "file": path, "check": "not_empty",
                    "detail": "File is empty (0 bytes)"
                })
            else:
                results["passes"].append({"file": path, "check": "not_empty"})
        except OSError:
            pass
        
        # Check: JSON files are valid JSON
        if ext == ".json" or basename in ("package.json", "tsconfig.json"):
            results["checks_run"] += 1
            try:
                with open(path, "r") as f:
                    json.load(f)
                results["passes"].append({"file": path, "check": "json_valid"})
            except (json.JSONDecodeError, OSError) as e:
                results["issues"].append({
                    "file": path, "check": "json_valid",
                    "detail": f"Invalid JSON: {str(e)[:100]}"
                })
        
        # Check: Python files compile
        if ext == ".py":
            results["checks_run"] += 1
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", path],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    results["passes"].append({"file": path, "check": "python_syntax"})
                else:
                    detail = result.stderr.strip()[:200] or "Syntax error"
                    results["issues"].append({
                        "file": path, "check": "python_syntax",
                        "detail": detail
                    })
            except (subprocess.TimeoutExpired, OSError):
                pass  # Skip if we can't run py_compile
        
        # Check: YAML files parse (if pyyaml available)
        if ext in (".yaml", ".yml"):
            results["checks_run"] += 1
            try:
                import yaml
                with open(path, "r") as f:
                    yaml.safe_load(f)
                results["passes"].append({"file": path, "check": "yaml_valid"})
            except ImportError:
                results["checks_run"] -= 1  # Don't count if yaml not installed
            except Exception as e:
                results["issues"].append({
                    "file": path, "check": "yaml_valid",
                    "detail": f"Invalid YAML: {str(e)[:100]}"
                })
        
        # Check: HTML files have basic structure
        if ext in (".html", ".htm"):
            results["checks_run"] += 1
            try:
                with open(path, "r", errors="replace") as f:
                    content = f.read(10000)
                if "<html" in content.lower() or "<!doctype" in content.lower():
                    results["passes"].append({"file": path, "check": "html_structure"})
                else:
                    results["issues"].append({
                        "file": path, "check": "html_structure",
                        "detail": "Missing <html> or <!DOCTYPE> tag"
                    })
            except OSError:
                pass

        # Check: no hardcoded secrets patterns
        if ext in _PRIORITY_EXTENSIONS and ext not in (".md",):
            results["checks_run"] += 1
            try:
                with open(path, "r", errors="replace") as f:
                    content = f.read(20000)
                # Look for common secret patterns
                secret_patterns = [
                    r'(?:api_key|apikey|secret|password|token)\s*=\s*["\'][a-zA-Z0-9_\-]{20,}["\']',
                    r'sk-[a-zA-Z0-9_\-]{20,}',  # OpenAI/Anthropic-style keys
                    r'ghp_[a-zA-Z0-9]{36}',  # GitHub PATs
                ]
                found_secrets = False
                for pat in secret_patterns:
                    if re.search(pat, content, re.IGNORECASE):
                        found_secrets = True
                        break
                if found_secrets:
                    results["issues"].append({
                        "file": path, "check": "no_hardcoded_secrets",
                        "detail": "Possible hardcoded secret/API key detected"
                    })
                else:
                    results["passes"].append({"file": path, "check": "no_hardcoded_secrets"})
            except OSError:
                pass
    
    return results


def validate_execution(
    goal: str,
    plan: dict,
    execution_report: dict,
    domain: str = "general",
    domain_knowledge: str = "",
) -> dict:
    """
    Evaluate execution output quality.

    Args:
        goal: The original task description
        plan: The execution plan that was followed
        execution_report: Full execution report with step results and artifacts
        domain: Domain context
        domain_knowledge: Relevant KB claims for alignment checking

    Returns:
        Validation result dict with scores, feedback, and verdict
    """
    system = _build_validator_prompt()

    # Run static checks first (fast, no API call)
    static_results = _run_static_checks(execution_report.get("artifacts", []))

    # Build the evaluation context
    eval_context = {
        "goal": goal,
        "plan_summary": plan.get("task_summary", ""),
        "success_criteria": plan.get("success_criteria", ""),
        "steps_completed": execution_report.get("completed_steps", 0),
        "steps_failed": execution_report.get("failed_steps", 0),
        "total_steps": execution_report.get("total_steps", 0),
        "artifacts": execution_report.get("artifacts", []),
    }

    # Inject static check results so the LLM evaluator knows about them
    if static_results["checks_run"] > 0:
        eval_context["static_analysis"] = {
            "checks_run": static_results["checks_run"],
            "issues_found": len(static_results["issues"]),
            "issues": static_results["issues"][:10],  # Cap to avoid bloat
            "passes": len(static_results["passes"]),
        }

    # Include step details (capped to avoid huge payloads)
    step_details = []
    for step in execution_report.get("step_results", [])[:20]:
        step_details.append({
            "step": step.get("step", 0),
            "tool": step.get("tool", ""),
            "success": step.get("success", False),
            "output": step.get("output", "")[:500],
            "error": step.get("error", ""),
        })
    eval_context["step_details"] = step_details

    # Read actual artifact file contents for accurate evaluation
    artifact_contents = _read_artifact_files(execution_report.get("artifacts", []))
    if artifact_contents:
        eval_context["file_contents"] = artifact_contents

    user_message = f"Evaluate this execution:\n\n{json.dumps(eval_context, indent=2)}"

    if domain_knowledge:
        user_message += f"\n\nDOMAIN KNOWLEDGE (best practices):\n{domain_knowledge[:3000]}"

    try:
        response = create_message(
            client,
            model=MODELS["exec_validator"],
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

        # Track cost
        log_cost(
            model=MODELS["exec_validator"],
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            agent_role="exec_validator",
            domain=domain,
        )

        if not response.content:
            raise ValueError("Empty response from validator model")
        raw_text = response.content[0].text.strip()

    except Exception as e:
        return {
            "scores": {
                "correctness": 0, "completeness": 0,
                "code_quality": 0, "security": 0, "kb_alignment": 0,
            },
            "overall_score": 0,
            "strengths": [],
            "weaknesses": [f"Validator API error: {str(e)[:200]}"],
            "actionable_feedback": "Unable to evaluate — retry",
            "verdict": "reject",
            "critical_issues": ["Validation API error"],
            "_api_error": True,
        }

    # Parse JSON
    EXPECTED_KEYS = {"scores", "overall_score", "verdict"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    if result is None:
        result = {
            "scores": {
                "correctness": 0, "completeness": 0,
                "code_quality": 0, "security": 0, "kb_alignment": 0,
            },
            "overall_score": 0,
            "strengths": [],
            "weaknesses": ["Validator failed to produce structured output"],
            "actionable_feedback": "Unable to evaluate — retry",
            "verdict": "reject",
            "critical_issues": ["Validation parse error"],
            "_parse_error": True,
        }

    # Ensure verdict aligns with score
    if "overall_score" in result and "verdict" not in result:
        result["verdict"] = "accept" if result["overall_score"] >= EXEC_QUALITY_THRESHOLD else "reject"

    result.setdefault("critical_issues", [])
    result.setdefault("strengths", [])
    result.setdefault("weaknesses", [])
    result.setdefault("actionable_feedback", "")

    # Attach static check results for downstream consumers
    result["static_checks"] = static_results

    return result
