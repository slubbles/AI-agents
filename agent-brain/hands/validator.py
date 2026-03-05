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
    "weaknesses": [
        {{"issue": "what was done poorly", "confidence": 85}},
        {{"issue": "another issue", "confidence": 45}}
    ],
    "actionable_feedback": "specific instructions for how to improve if re-executed",
    "verdict": "accept|reject",
    "critical_issues": [
        {{"issue": "any blocking issues that must be fixed", "confidence": 92}}
    ]
}}

CONFIDENCE SCORING (0-100 per issue):
- Each weakness and critical_issue MUST include a "confidence" score (0-100).
- 90-100: Certain — you verified this in the code. Treat as error.
- 70-89: Likely — strong evidence but not 100% verified. Treat as warning.
- Below 70: Possible — speculative or based on incomplete info. Logged only.
- Be honest about your confidence. If you haven't seen the file, don't guess high.

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


def _read_artifact_files(artifacts: list[str], suspect_files: set[str] | None = None) -> dict[str, str]:
    """
    Read actual file contents from artifact paths.
    
    For suspect files (static check failures, failed step outputs): full content.
    For clean files: digest (first 20 + last 20 lines) to save ~40-60% tokens.
    
    Prioritizes key files (package.json, entry points, configs, tests).
    Skips binary files. Caps total size to stay within context limits.

    Args:
        artifacts: List of artifact file paths
        suspect_files: Set of file paths that deserve full content (have issues)

    Returns:
        Dict mapping file path to content string
    """
    if not artifacts:
        return {}

    suspect = suspect_files or set()
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
    DIGEST_LINES = 20  # First/last N lines for clean file digests
    for path in priority_files + other_files:
        if total_chars >= _MAX_ARTIFACT_CHARS:
            break
        try:
            with open(path, "r", errors="replace") as f:
                content = f.read(_MAX_FILE_CHARS + 100)
            if len(content) > _MAX_FILE_CHARS:
                content = content[:_MAX_FILE_CHARS] + f"\n... (truncated at {_MAX_FILE_CHARS} chars)"

            # Digest mode: only first/last N lines for clean (non-suspect) files
            is_suspect = path in suspect
            if not is_suspect and content.count("\n") > DIGEST_LINES * 3:
                lines = content.split("\n")
                head = lines[:DIGEST_LINES]
                tail = lines[-DIGEST_LINES:]
                omitted = len(lines) - DIGEST_LINES * 2
                content = (
                    "\n".join(head)
                    + f"\n\n... ({omitted} lines omitted — file passed static checks) ...\n\n"
                    + "\n".join(tail)
                )

            contents[path] = content
            total_chars += len(content)
        except (OSError, UnicodeDecodeError):
            contents[path] = "(unable to read file)"

    return contents


_MAX_SYNTAX_CHECK_CHARS = 500_000  # Cap file reads for syntax checks


def _check_js_ts_syntax(content: str, path: str) -> list[str]:
    """
    Heuristic syntax checks for JS/TS files.
    Returns list of issues found (empty = OK).
    
    Checks:
      1. Bracket/paren/brace balance
      2. Common import/export syntax errors
      3. Unterminated template literals
      4. node -c validation for .js/.jsx (if node available)
    """
    issues: list[str] = []
    ext = os.path.splitext(path)[1].lower()

    # --- Bracket balance ---
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    in_string = False
    string_char = ""
    in_template = False
    in_line_comment = False
    in_block_comment = False
    prev_ch = ""

    for ch in content:
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            prev_ch = ch
            continue
        if in_block_comment:
            if prev_ch == "*" and ch == "/":
                in_block_comment = False
            prev_ch = ch
            continue
        if not in_string and not in_template:
            if prev_ch == "/" and ch == "/":
                in_line_comment = True
                if stack and stack[-1] == "/":
                    stack.pop()
                prev_ch = ch
                continue
            if prev_ch == "/" and ch == "*":
                in_block_comment = True
                if stack and stack[-1] == "/":
                    stack.pop()
                prev_ch = ch
                continue
        if in_string:
            if ch == string_char and prev_ch != "\\":
                in_string = False
            prev_ch = ch
            continue
        if in_template:
            if ch == "`" and prev_ch != "\\":
                in_template = False
            prev_ch = ch
            continue
        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            prev_ch = ch
            continue
        if ch == "`":
            in_template = True
            prev_ch = ch
            continue
        if ch in ("(", "[", "{"):
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack[-1] != pairs[ch]:
                issues.append(f"Unmatched '{ch}' in {os.path.basename(path)}")
                break
            stack.pop()
        prev_ch = ch

    if in_template:
        issues.append("Unterminated template literal")
    if stack:
        openers = "".join(stack[-3:])
        issues.append(f"Unclosed brackets: {openers}")

    # --- Import/export syntax ---
    for i, line in enumerate(content.split("\n")[:200], 1):
        stripped = line.strip()
        # Catch 'import from' without braces/default: import "module"
        if re.match(r'^import\s+from\s', stripped):
            issues.append(f"Line {i}: 'import from' missing specifier")
        # Catch missing from: import { X }  (no 'from')
        if re.match(r'^import\s*\{[^}]*\}\s*$', stripped):
            issues.append(f"Line {i}: import statement missing 'from'")
        # Catch export default followed by nothing meaningful
        if re.match(r'^export\s+default\s*$', stripped):
            issues.append(f"Line {i}: empty 'export default'")

    # --- Node -c for JS files (fast, authoritative) ---
    if ext in (".js", ".jsx") and not issues and os.path.isfile(path):
        try:
            proc = subprocess.run(
                ["node", "-c", path],
                capture_output=True, text=True, timeout=5,
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").strip().split("\n")[0][:120]
                issues.append(f"node -c: {err}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # node not available — heuristic results stand

    return issues


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

        # Check: TypeScript/JavaScript syntax (heuristic + node fallback)
        if ext in (".ts", ".tsx", ".js", ".jsx"):
            results["checks_run"] += 1
            try:
                with open(path, "r", errors="replace") as f:
                    content = f.read(_MAX_SYNTAX_CHECK_CHARS)
                issues = _check_js_ts_syntax(content, path)
                if issues:
                    results["issues"].append({
                        "file": path, "check": "js_ts_syntax",
                        "detail": "; ".join(issues[:3]),
                    })
                else:
                    results["passes"].append({"file": path, "check": "js_ts_syntax"})
            except OSError:
                pass
        
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


def identify_failing_steps(
    validation: dict,
    step_results: list[dict],
    plan_steps: list[dict],
) -> list[int]:
    """
    Cross-reference validation feedback with step results to identify
    which specific steps produced the issues.

    Used for surgical retry — only re-execute failing steps + dependents
    instead of starting from scratch.

    Args:
        validation: Validation result dict (from validate_execution)
        step_results: List of step result dicts from execution report
        plan_steps: Original plan steps

    Returns:
        List of step numbers (1-based) that need re-doing.
    """
    failing_steps: set[int] = set()

    # 1. Steps that explicitly failed
    for sr in step_results:
        if not sr.get("success", False) and sr.get("criticality", "required") == "required":
            failing_steps.add(sr.get("step", 0))

    # 2. Cross-reference critical_issues + weaknesses with artifacts
    problem_text = " ".join(
        validation.get("critical_issues", []) +
        validation.get("weaknesses", [])
    ).lower()

    for sr in step_results:
        step_num = sr.get("step", 0)
        # Check if any artifact from this step is mentioned in issues
        for artifact in sr.get("artifacts", []):
            basename = os.path.basename(artifact).lower()
            if basename in problem_text:
                failing_steps.add(step_num)
                break

        # Check if the tool type matches issue categories
        tool = sr.get("tool", "").lower()
        if tool == "code" and any(
            kw in problem_text
            for kw in ["syntax", "import", "missing file", "empty file", "invalid json"]
        ):
            # Code step that created a file mentioned in issues
            if sr.get("artifacts"):
                failing_steps.add(step_num)

    # 3. Static check failures — map file to the step that created it
    static_issues = validation.get("static_checks", {}).get("issues", [])
    artifact_to_step: dict[str, int] = {}
    for sr in step_results:
        for art in sr.get("artifacts", []):
            artifact_to_step[art] = sr.get("step", 0)

    for issue in static_issues:
        file_path = issue.get("file", "")
        if file_path in artifact_to_step:
            failing_steps.add(artifact_to_step[file_path])

    # 4. Add dependent steps (steps that depend on failing steps)
    failing_deps: set[int] = set()
    for ps in plan_steps:
        sn = ps.get("step_number", 0)
        deps = ps.get("depends_on", [])
        if any(d in failing_steps for d in deps):
            failing_deps.add(sn)

    failing_steps |= failing_deps

    # Remove step 0 if present (invalid)
    failing_steps.discard(0)

    return sorted(failing_steps)


# ---- Fast-Reject for Blocker-Level Static Issues ----

# Checks that indicate definitively broken output (no need for LLM eval)
_BLOCKER_CHECKS = {"python_syntax", "json_valid", "js_ts_syntax", "exists", "not_empty"}


def _should_fast_reject(
    static_results: dict,
    artifacts: list[str],
    completed_steps: int,
    total_steps: int,
) -> dict | None:
    """
    Check whether static analysis results are bad enough to skip the LLM validator.

    Returns a synthetic validation result if fast-reject applies, None otherwise.
    This saves one Sonnet call (~$0.03) when artifacts are definitively broken.

    Criteria for fast-reject:
    - >=50% of EXISTING artifacts have blocker-level issues, OR
    - Any required config file (package.json, etc.) has a blocker
    - AND at least 2 artifacts exist (no fast-rejecting single-file tasks)
    - Only counts files that exist on disk (non-existent files are a separate concern)
    """
    if not artifacts or not static_results.get("issues"):
        return None

    # Only consider blocker issues on files that actually exist
    # (non-existent files are a planning/execution issue, not a content quality issue)
    blocker_issues = [
        i for i in static_results["issues"]
        if i.get("check") in _BLOCKER_CHECKS and i.get("check") != "exists"
    ]

    if not blocker_issues:
        return None

    # Count existing artifacts (only those we can actually evaluate)
    existing_artifacts = [a for a in artifacts if os.path.isfile(a)]
    if len(existing_artifacts) < 2:
        return None  # Too few files to confidently fast-reject

    # Count unique files with blockers
    blocker_files = set(i["file"] for i in blocker_issues)
    blocker_ratio = len(blocker_files) / max(len(existing_artifacts), 1)

    # Check for critical config file failures
    critical_configs = {"package.json", "tsconfig.json", "pyproject.toml"}
    has_critical_config_failure = any(
        os.path.basename(f).lower() in critical_configs for f in blocker_files
    )

    # Trigger fast-reject if >50% of files broken OR critical config broken
    if blocker_ratio <= 0.5 and not has_critical_config_failure:
        return None

    # Build synthetic validation result
    issue_details = [
        f"{os.path.basename(i['file'])}: {i['detail']}"
        for i in blocker_issues[:10]
    ]

    return {
        "overall_score": 2,
        "dimensions": {
            "correctness": 2,
            "completeness": 3,
            "code_quality": 2,
            "best_practices": 3,
            "goal_alignment": 4,
        },
        "verdict": "reject",
        "strengths": [f"{completed_steps}/{total_steps} steps completed"],
        "weaknesses": issue_details,
        "critical_issues": [f"Static analysis found {len(blocker_issues)} blocker(s): " +
                           "; ".join(issue_details[:3])],
        "fast_rejected": True,
        "static_blocker_count": len(blocker_issues),
        "static_blocker_ratio": round(blocker_ratio, 2),
    }


# Confidence thresholds for issue filtering
CONFIDENCE_ERROR_THRESHOLD = 90   # 90-100: reported as errors
CONFIDENCE_WARNING_THRESHOLD = 70  # 70-89: reported as warnings
# Below 70: logged only, not reported as failures


def _normalize_issue(item) -> dict:
    """Normalize an issue entry to {issue: str, confidence: int} format.

    The LLM may return plain strings (old format) or dicts with confidence.
    Plain strings are treated as high-confidence (95) for backward compatibility.
    """
    if isinstance(item, dict):
        return {
            "issue": str(item.get("issue", "")),
            "confidence": int(item.get("confidence", 95)),
        }
    return {"issue": str(item), "confidence": 95}


def _filter_by_confidence(result: dict) -> dict:
    """Filter weaknesses and critical_issues by confidence score.

    - confidence >= 90: error (kept in list)
    - confidence 70-89: warning (kept, marked as warning)
    - confidence < 70: removed from list, stored in _low_confidence_issues
    """
    low_confidence = []

    for key in ("weaknesses", "critical_issues"):
        raw = result.get(key, [])
        filtered = []
        for item in raw:
            entry = _normalize_issue(item)
            if entry["confidence"] < CONFIDENCE_WARNING_THRESHOLD:
                low_confidence.append(entry)
            else:
                filtered.append(entry)
        result[key] = filtered

    if low_confidence:
        result["_low_confidence_issues"] = low_confidence

    return result


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

    # Fast-reject path: skip LLM call if artifacts are definitively broken
    fast_reject = _should_fast_reject(
        static_results,
        execution_report.get("artifacts", []),
        execution_report.get("completed_steps", 0),
        execution_report.get("total_steps", 0),
    )
    if fast_reject:
        print(f"  [VALIDATOR] Fast-reject: {fast_reject['static_blocker_count']} blocker(s), "
              f"ratio={fast_reject['static_blocker_ratio']:.0%} — skipping LLM evaluation")
        return fast_reject

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
    # Compact format: successful steps get 1-line summary, failed steps get full detail
    step_details = []
    for step in execution_report.get("step_results", [])[:20]:
        if step.get("success"):
            step_details.append({
                "step": step.get("step", 0),
                "tool": step.get("tool", ""),
                "success": True,
                "output": step.get("output", "")[:200],  # 200 chars for successes (was 500)
            })
        else:
            step_details.append({
                "step": step.get("step", 0),
                "tool": step.get("tool", ""),
                "success": False,
                "output": step.get("output", "")[:500],
                "error": step.get("error", ""),
            })
    eval_context["step_details"] = step_details

    # Identify suspect files: those with static check issues + failed step artifacts
    suspect_files = set()
    for issue in static_results.get("issues", []):
        suspect_files.add(issue.get("file", ""))
    for step in execution_report.get("step_results", []):
        if not step.get("success") and step.get("artifacts"):
            suspect_files.update(step["artifacts"])

    # Read actual artifact file contents for accurate evaluation
    # Suspect files get full content; clean files get digest (first/last 20 lines)
    artifact_contents = _read_artifact_files(
        execution_report.get("artifacts", []),
        suspect_files=suspect_files,
    )
    if artifact_contents:
        eval_context["file_contents"] = artifact_contents

    # Compact JSON: no indentation, minimal separators (~25-35% smaller)
    user_message = f"Evaluate this execution:\n\n{json.dumps(eval_context, separators=(',', ':'))}"

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

    # Apply confidence filtering to weaknesses and critical_issues
    result = _filter_by_confidence(result)

    # Attach static check results for downstream consumers
    result["static_checks"] = static_results

    return result
