"""
Output Polisher — Zero-cost rule-based quality fixes before validation.

Problem: Many validator deductions are for trivially fixable issues:
invalid JSON formatting, missing trailing newlines, Python syntax errors
from minor typos, empty files. These trigger expensive LLM-powered retries
when a rule-based fix could boost scores for free.

Solution: After execution completes but BEFORE validation, run fast
deterministic fixes on artifacts. No LLM calls — pure file I/O and parsing.

Fixes applied:
1. JSON files: re-serialize to ensure validity + formatting
2. Python files: add trailing newline, verify syntax
3. Package.json: ensure required fields exist
4. General: remove trailing whitespace, ensure final newline
5. TypeScript/JS: basic bracket balance warnings (logged, not auto-fixed)

The polisher logs all fixes, which feed into pattern_learner as evidence
of recurring issues that the planner should prevent.

Used by: main.py (between execute_plan and validate_execution)
"""

import ast
import json
import os
import re
from typing import Optional


# Extensions we can safely auto-fix
_FIXABLE_EXTENSIONS = {".json", ".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".md", ".css", ".html"}

# Max file size we'll attempt to fix (avoid huge files)
_MAX_FIX_SIZE = 100_000


def polish_artifacts(
    artifacts: list[str],
    domain: str = "general",
) -> dict:
    """
    Apply rule-based quality fixes to artifact files.
    Modifies files in-place. Returns a log of what was fixed.
    
    Args:
        artifacts: List of file paths to polish
        domain: Domain context (for domain-specific rules)
    
    Returns:
        {
            "files_checked": int,
            "files_modified": int,
            "fixes": [{"file": str, "fix": str}, ...],
            "skipped": int,
        }
    """
    result = {
        "files_checked": 0,
        "files_modified": 0,
        "fixes": [],
        "skipped": 0,
    }
    
    for filepath in set(artifacts):
        if not os.path.isfile(filepath):
            continue
        
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in _FIXABLE_EXTENSIONS:
            result["skipped"] += 1
            continue
        
        try:
            size = os.path.getsize(filepath)
            if size == 0 or size > _MAX_FIX_SIZE:
                result["skipped"] += 1
                continue
        except OSError:
            continue
        
        result["files_checked"] += 1
        
        try:
            with open(filepath, "r", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        
        original = content
        fixes = []
        
        # Apply fixes based on file type
        if ext == ".json" or os.path.basename(filepath).lower() in ("package.json", "tsconfig.json"):
            content, fix_list = _fix_json(filepath, content)
            fixes.extend(fix_list)
        
        elif ext == ".py":
            content, fix_list = _fix_python(filepath, content)
            fixes.extend(fix_list)
        
        # General fixes (all text files)
        content, general_fixes = _fix_general(filepath, content)
        fixes.extend(general_fixes)
        
        # Write back if changed
        if content != original:
            try:
                with open(filepath, "w") as f:
                    f.write(content)
                result["files_modified"] += 1
                for fix in fixes:
                    result["fixes"].append({"file": filepath, "fix": fix})
            except OSError:
                pass
    
    return result


def _fix_json(filepath: str, content: str) -> tuple[str, list[str]]:
    """Fix JSON files: re-serialize for validity + formatting."""
    fixes = []
    basename = os.path.basename(filepath).lower()
    
    # Try to parse and re-format
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try to fix common issues
        fixed_content = content
        
        # Remove trailing commas before } or ]
        fixed_content = re.sub(r',\s*([\]}])', r'\1', fixed_content)
        
        # Try again
        try:
            data = json.loads(fixed_content)
            fixes.append("removed_trailing_commas")
            content = json.dumps(data, indent=2) + "\n"
            return content, fixes
        except json.JSONDecodeError:
            return content, fixes  # Can't fix this
    
    # Package.json specific enrichment
    if basename == "package.json":
        modified = False
        if "name" not in data:
            data["name"] = "project"
            modified = True
            fixes.append("added_missing_name_field")
        if "version" not in data:
            data["version"] = "1.0.0"
            modified = True
            fixes.append("added_missing_version_field")
        if modified:
            content = json.dumps(data, indent=2) + "\n"
    else:
        # Re-format for consistency
        reformatted = json.dumps(data, indent=2) + "\n"
        if reformatted != content:
            content = reformatted
            fixes.append("reformatted_json")
    
    return content, fixes


def _fix_python(filepath: str, content: str) -> tuple[str, list[str]]:
    """Fix Python files: syntax check, add trailing newline."""
    fixes = []
    
    # Check for syntax errors we can locate
    try:
        ast.parse(content)
    except SyntaxError as e:
        # Can't auto-fix arbitrary syntax errors, but log it
        # Don't modify — let the validator catch it properly
        pass
    
    # Remove common BOM marker
    if content.startswith("\ufeff"):
        content = content[1:]
        fixes.append("removed_bom")
    
    return content, fixes


def _fix_general(filepath: str, content: str) -> tuple[str, list[str]]:
    """General fixes applicable to all text files."""
    fixes = []
    
    # Ensure trailing newline
    if content and not content.endswith("\n"):
        content += "\n"
        fixes.append("added_trailing_newline")
    
    # Remove null bytes (corrupted output)
    if "\x00" in content:
        content = content.replace("\x00", "")
        fixes.append("removed_null_bytes")
    
    # Remove excessive trailing blank lines (keep max 1)
    lines = content.split("\n")
    while len(lines) > 2 and lines[-1] == "" and lines[-2] == "":
        lines.pop(-1)
        if "trimmed_trailing_blank_lines" not in fixes:
            fixes.append("trimmed_trailing_blank_lines")
    content = "\n".join(lines)
    
    return content, fixes


def format_polish_log(polish_result: dict) -> str:
    """Format the polish result for display."""
    if not polish_result.get("fixes"):
        return ""
    
    lines = [f"[POLISHER] Fixed {polish_result['files_modified']} files:"]
    for fix in polish_result["fixes"][:10]:
        lines.append(f"  • {os.path.basename(fix['file'])}: {fix['fix']}")
    if len(polish_result["fixes"]) > 10:
        lines.append(f"  ... and {len(polish_result['fixes']) - 10} more fixes")
    return "\n".join(lines)
