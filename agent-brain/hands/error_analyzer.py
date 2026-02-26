"""
Error Analyzer — Categorizes execution errors for smarter retry guidance.

When a step fails, the error message is analyzed to provide the executor
with targeted advice instead of generic "try again" messages.
"""

import re

# Error patterns with categories and retry advice
_ERROR_PATTERNS = [
    # Module/import errors
    {
        "pattern": r"ModuleNotFoundError|ImportError|No module named",
        "category": "missing_dependency",
        "advice": (
            "A required package is missing. Add a step BEFORE this one to install it: "
            "use the terminal tool with 'pip install <package>' or 'npm install <package>'. "
            "Then retry this step."
        ),
        "retryable": True,
    },
    # Command not found
    {
        "pattern": r"command not found|not recognized as|No such file or directory.*bin",
        "category": "missing_tool",
        "advice": (
            "A command-line tool is not installed. Install it first using the terminal tool "
            "(e.g., 'npm install -g <tool>' or 'apt-get install <tool>'). Then retry."
        ),
        "retryable": True,
    },
    # File not found
    {
        "pattern": r"FileNotFoundError|ENOENT|No such file or directory",
        "category": "missing_file",
        "advice": (
            "A required file does not exist. Check the file path — it may have a typo, "
            "or a previous step may have created it at a different path. "
            "Create the missing file first, then retry."
        ),
        "retryable": True,
    },
    # Permission denied
    {
        "pattern": r"PermissionError|EACCES|Permission denied",
        "category": "permission",
        "advice": (
            "Permission denied. Try using a different directory within the workspace, "
            "or check that you're not writing to a protected system path."
        ),
        "retryable": True,
    },
    # Syntax errors
    {
        "pattern": r"SyntaxError|Unexpected token|Parse error",
        "category": "syntax_error",
        "advice": (
            "There is a syntax error in the code. Review the file content carefully, "
            "fix the syntax issue, and rewrite the file with corrected code."
        ),
        "retryable": True,
    },
    # Type errors
    {
        "pattern": r"TypeError|is not a function|is not callable|is not iterable",
        "category": "type_error",
        "advice": (
            "A type error occurred — a value is being used incorrectly. "
            "Check the types of variables, function arguments, and return values. "
            "Fix the code logic and retry."
        ),
        "retryable": True,
    },
    # Network/connection errors
    {
        "pattern": r"ConnectionError|ECONNREFUSED|timeout|ETIMEDOUT|network",
        "category": "network",
        "advice": (
            "A network error occurred. If this was an HTTP request, check the URL. "
            "If this was package installation, check internet connectivity. "
            "You may want to retry once — network issues can be transient."
        ),
        "retryable": True,
    },
    # Out of memory
    {
        "pattern": r"MemoryError|ENOMEM|JavaScript heap out of memory|killed",
        "category": "resource",
        "advice": (
            "The system ran out of memory. Try reducing the scope of the operation, "
            "processing data in smaller chunks, or using a more memory-efficient approach."
        ),
        "retryable": False,
    },
    # Port already in use
    {
        "pattern": r"EADDRINUSE|address already in use",
        "category": "port_conflict",
        "advice": (
            "The port is already in use. Choose a different port number "
            "(e.g., 3001, 8081) and update the configuration accordingly."
        ),
        "retryable": True,
    },
    # Git conflicts
    {
        "pattern": r"CONFLICT|merge conflict|cannot pull with rebase",
        "category": "git_conflict",
        "advice": (
            "A git conflict occurred. Resolve the conflict by choosing the correct version, "
            "or reset the file to a known good state before retrying."
        ),
        "retryable": True,
    },
    # JSON parse errors
    {
        "pattern": r"JSONDecodeError|Unexpected token.*JSON|is not valid JSON",
        "category": "json_error",
        "advice": (
            "A JSON file has invalid syntax. Check for trailing commas, missing quotes, "
            "or unescaped characters. Rewrite the file with valid JSON."
        ),
        "retryable": True,
    },
    # Disk space
    {
        "pattern": r"ENOSPC|No space left on device|disk quota exceeded",
        "category": "disk_full",
        "advice": (
            "The disk is full. This execution cannot continue. "
            "Clean up unnecessary files before retrying."
        ),
        "retryable": False,
    },
]


def analyze_error(error_text: str, output_text: str = "") -> dict:
    """
    Analyze an error to categorize it and provide retry guidance.
    
    Args:
        error_text: The error message from the tool
        output_text: Additional output context
        
    Returns:
        {
            "category": str,
            "advice": str,
            "retryable": bool,
            "matched_pattern": str | None,
        }
    """
    combined = f"{error_text}\n{output_text}"
    
    for pattern_info in _ERROR_PATTERNS:
        if re.search(pattern_info["pattern"], combined, re.IGNORECASE):
            return {
                "category": pattern_info["category"],
                "advice": pattern_info["advice"],
                "retryable": pattern_info["retryable"],
                "matched_pattern": pattern_info["pattern"],
            }
    
    # Generic fallback
    return {
        "category": "unknown",
        "advice": (
            "An unexpected error occurred. Analyze the error message carefully, "
            "adjust your approach, and try again with different parameters."
        ),
        "retryable": True,
        "matched_pattern": None,
    }


def format_retry_guidance(error_analysis: dict, retries_left: int) -> str:
    """Format error analysis into a retry message for the executor."""
    parts = [
        f"\n[ERROR ANALYSIS] Category: {error_analysis['category']}",
        f"Advice: {error_analysis['advice']}",
    ]
    
    if retries_left > 0 and error_analysis["retryable"]:
        parts.append(f"You have {retries_left} retries. Apply the fix and try again.")
    elif not error_analysis["retryable"]:
        parts.append("This error type is unlikely to be fixed by retrying. Skip to the next step or abort.")
    else:
        parts.append("No retries left. Move to the next step or abort.")
    
    return "\n".join(parts)
