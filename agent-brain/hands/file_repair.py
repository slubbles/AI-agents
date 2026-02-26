"""
Per-Artifact Targeted File Repair — Fix specific files instead of full re-execution.

Problem: Validation is all-or-nothing. If 7/8 files are excellent but 1 has issues,
the entire execution scores low. Full retry ($0.20-0.40) or surgical retry ($0.08-0.15)
re-executes multiple steps. But often only 1-2 files need fixing.

Solution: Single Haiku call to regenerate ONLY the low-scoring files.
Cost: ~$0.003 per repair vs ~$0.15-0.40 for full/surgical retry (10-100x cheaper).

Used by: main.py (in retry loop, before surgical retry)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json

client = Anthropic(api_key=ANTHROPIC_API_KEY)


def identify_weak_artifacts(
    validation: dict,
    all_artifacts: list[str],
    threshold: float = 6.0,
) -> list[dict]:
    """
    From validation results, identify files that likely need repair.
    
    Uses per-artifact scores if available, otherwise infers from
    weaknesses/critical_issues and artifact list.
    
    Returns: [{path, score, issues}] for files below threshold.
    """
    # Check for per-artifact scores in validation
    per_artifact = validation.get("per_artifact_scores", [])
    if per_artifact:
        return [
            a for a in per_artifact
            if isinstance(a.get("score"), (int, float)) and a["score"] < threshold
        ]
    
    # Fallback: infer from weaknesses + critical issues
    # Map issues to files by checking if filenames appear in the text
    weaknesses = validation.get("weaknesses", [])
    critical = validation.get("critical_issues", [])
    all_issues = weaknesses + [f"CRITICAL: {c}" for c in critical]
    
    if not all_issues or not all_artifacts:
        return []
    
    weak = []
    for artifact_path in all_artifacts:
        if not os.path.isfile(artifact_path):
            continue
        basename = os.path.basename(artifact_path)
        # Check if this file is mentioned in any issue
        matching_issues = []
        for issue in all_issues:
            if isinstance(issue, str) and (basename in issue or artifact_path in issue):
                matching_issues.append(issue)
        
        if matching_issues:
            weak.append({
                "path": artifact_path,
                "score": 0,  # Unknown specific score
                "issues": matching_issues,
            })
    
    return weak


def repair_files(
    files_to_fix: list[dict],
    goal: str,
    plan: dict,
    domain: str,
    workspace_dir: str = "",
) -> dict:
    """
    Fix specific files using a single Haiku call.
    
    Reads current content, sends issues, gets corrected content.
    Cost: ~$0.003 per call (1-3 files).
    
    Args:
        files_to_fix: [{path, score, issues}]
        goal: Original task goal
        plan: Original plan
        domain: Domain context
        workspace_dir: Base directory
    
    Returns: {files_fixed, files_failed, cost, details}
    """
    if not files_to_fix:
        return {"files_fixed": 0, "files_failed": 0, "cost": 0.0, "details": []}
    
    # Read current content of files needing repair
    file_contents = []
    for entry in files_to_fix[:5]:  # Cap at 5 files per repair call
        path = entry["path"]
        issues = entry.get("issues", [])
        
        if not os.path.isfile(path):
            continue
        
        try:
            with open(path, "r") as f:
                content = f.read()
        except Exception:
            continue
        
        file_contents.append({
            "path": path,
            "relative_path": os.path.relpath(path, workspace_dir) if workspace_dir else path,
            "content": content[:8000],  # Cap content size
            "issues": issues,
        })
    
    if not file_contents:
        return {"files_fixed": 0, "files_failed": 0, "cost": 0.0, "details": []}
    
    # Build repair prompt
    today = date.today().isoformat()
    system = f"""\
You are a code repair agent. You fix specific issues in files without changing their overall structure.
TODAY: {today}

RULES:
1. Fix ONLY the issues listed for each file.
2. Do NOT change code that doesn't relate to the listed issues.
3. Maintain the same coding style, imports, and structure.
4. Output COMPLETE file contents — never use placeholders.
5. If a file cannot be fixed (e.g., fundamental design issue), mark it as unfixable.

OUTPUT FORMAT — respond with ONLY valid JSON:
{{
    "repairs": [
        {{
            "path": "relative/path/to/file.ts",
            "fixed": true,
            "content": "The COMPLETE fixed file content...",
            "changes_made": ["description of change 1"]
        }}
    ]
}}
"""
    
    # Build user message with files + issues
    parts = [f"TASK GOAL: {goal}\n"]
    for fc in file_contents:
        issues_text = "\n".join(f"  - {i}" for i in fc["issues"])
        parts.append(
            f"FILE: {fc['relative_path']}\n"
            f"ISSUES:\n{issues_text}\n"
            f"CURRENT CONTENT:\n```\n{fc['content']}\n```\n"
        )
    parts.append("Fix the issues listed above. Return the complete fixed content for each file.")
    
    try:
        response = create_message(
            client,
            model=MODELS.get("executor", "claude-haiku-4-20250414"),
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": "\n".join(parts)}],
        )
    except Exception as e:
        return {"files_fixed": 0, "files_failed": len(file_contents), "cost": 0.0, "details": [], "error": str(e)}
    
    # Track cost
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    estimated_cost = (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000
    
    log_cost(
        MODELS.get("executor", "claude-haiku-4-20250414"),
        input_tokens,
        output_tokens,
        "file_repair",
        domain,
    )
    
    # Parse response
    raw = response.content[0].text.strip()
    result = extract_json(raw, expected_keys={"repairs"})
    
    if not result or not result.get("repairs"):
        return {
            "files_fixed": 0,
            "files_failed": len(file_contents),
            "cost": estimated_cost,
            "details": [],
        }
    
    # Apply repairs
    files_fixed = 0
    files_failed = 0
    details = []
    
    path_lookup = {fc["relative_path"]: fc["path"] for fc in file_contents}
    
    for repair in result["repairs"]:
        rel_path = repair.get("path", "")
        fixed = repair.get("fixed", False)
        content = repair.get("content", "")
        changes = repair.get("changes_made", [])
        
        abs_path = path_lookup.get(rel_path, "")
        if not abs_path:
            # Try matching by basename
            for rp, ap in path_lookup.items():
                if os.path.basename(rp) == os.path.basename(rel_path):
                    abs_path = ap
                    break
        
        if not fixed or not content or not abs_path:
            files_failed += 1
            details.append({"path": rel_path, "fixed": False, "reason": "unfixable or no content"})
            continue
        
        try:
            with open(abs_path, "w") as f:
                f.write(content)
            files_fixed += 1
            details.append({"path": rel_path, "fixed": True, "changes": changes})
        except Exception as e:
            files_failed += 1
            details.append({"path": rel_path, "fixed": False, "reason": str(e)})
    
    return {
        "files_fixed": files_fixed,
        "files_failed": files_failed,
        "cost": estimated_cost,
        "details": details,
    }
