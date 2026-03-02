"""
Identity Loader — Loads and caches the Identity Layer documents.

The Identity Layer defines WHO the system is: its goals, ethics, boundaries,
risk tolerance, and taste. These documents are the most important configuration
in the entire system — they determine the values that every agent decision
is filtered through.

Usage:
    from identity_loader import load_identity, get_identity_summary, get_identity_section

    # Full identity (all sections, cached)
    identity = load_identity()

    # Compact summary for injection into agent prompts (token-efficient)
    summary = get_identity_summary()

    # Single section
    ethics = get_identity_section("ethics")
"""

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("identity")

# ── Configuration ────────────────────────────────────────────────────────

IDENTITY_DIR = os.path.join(os.path.dirname(__file__), "identity")

IDENTITY_FILES = {
    "goals": "goals.md",
    "ethics": "ethics.md",
    "boundaries": "boundaries.md",
    "risk": "risk.md",
    "taste": "taste.md",
}

# Sections that are REQUIRED — system should warn loudly if missing
REQUIRED_SECTIONS = {"goals", "ethics", "boundaries"}


# ── Loader ───────────────────────────────────────────────────────────────

def _load_file(section: str) -> Optional[str]:
    """Load a single identity file. Returns None if missing."""
    filename = IDENTITY_FILES.get(section)
    if not filename:
        return None
    path = os.path.join(IDENTITY_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (IOError, OSError) as e:
        logger.error(f"Failed to read identity file {path}: {e}")
        return None


@lru_cache(maxsize=1)
def load_identity() -> dict[str, Optional[str]]:
    """
    Load all identity sections. Returns dict keyed by section name.

    Warns for missing REQUIRED sections. Caches result (call
    reload_identity() to clear cache after file changes).
    """
    identity = {}
    missing_required = []

    for section in IDENTITY_FILES:
        content = _load_file(section)
        identity[section] = content
        if content is None and section in REQUIRED_SECTIONS:
            missing_required.append(section)

    if missing_required:
        logger.warning(
            f"MISSING REQUIRED IDENTITY FILES: {', '.join(missing_required)}. "
            f"System operating without core identity constraints. "
            f"Expected files in: {IDENTITY_DIR}"
        )

    loaded = [s for s, c in identity.items() if c is not None]
    if loaded:
        logger.info(f"Identity loaded: {', '.join(loaded)}")

    return identity


def reload_identity() -> dict[str, Optional[str]]:
    """Clear cache and reload all identity files."""
    load_identity.cache_clear()
    _get_summary_cached.cache_clear()
    return load_identity()


def get_identity_section(section: str) -> Optional[str]:
    """Get a single identity section by name."""
    identity = load_identity()
    return identity.get(section)


# ── Summary for Prompts ──────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_summary_cached() -> str:
    """Build a compact summary from identity files. Cached."""
    identity = load_identity()

    parts = []

    # Goals — extract just the primary goal and operating priorities
    if identity.get("goals"):
        lines = identity["goals"].split("\n")
        goal_lines = []
        in_primary = False
        in_operating = False
        for line in lines:
            if "Primary Goal" in line or "primary goal" in line:
                in_primary = True
                continue
            if "Operating Goals" in line or "operating goals" in line:
                in_primary = False
                in_operating = True
                continue
            if line.startswith("## ") and in_operating:
                in_operating = False
                continue
            if in_primary and line.strip():
                goal_lines.append(line.strip())
                in_primary = False  # Just the first meaningful line
            if in_operating and line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
                # Extract just the priority name
                goal_lines.append(line.strip())
        if goal_lines:
            parts.append("GOALS: " + " | ".join(goal_lines[:6]))

    # Ethics — extract the "Never Do" rules as the most critical
    if identity.get("ethics"):
        lines = identity["ethics"].split("\n")
        never_rules = []
        in_never = False
        for line in lines:
            if "Never Do" in line or "never do" in line:
                in_never = True
                continue
            if line.startswith("## ") and in_never:
                in_never = False
                continue
            if in_never and line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.")):
                # Extract just the rule title (bold part)
                text = line.strip()
                # Try to get the bold part
                if "**" in text:
                    start = text.index("**") + 2
                    end = text.index("**", start) if "**" in text[start:] else len(text)
                    rule = text[start:end].rstrip(".")
                else:
                    rule = text.split("—")[0].strip() if "—" in text else text[:60]
                never_rules.append(rule)
        if never_rules:
            parts.append("ETHICS (never do): " + " | ".join(never_rules))

    # Boundaries — extract budget and autonomy limits (most operationally relevant)
    if identity.get("boundaries"):
        lines = identity["boundaries"].split("\n")
        budget_lines = []
        in_budget = False
        for line in lines:
            if "Budget" in line and line.startswith("#"):
                in_budget = True
                continue
            if line.startswith("## ") and in_budget:
                in_budget = False
                continue
            if in_budget and line.strip().startswith("- **"):
                budget_lines.append(line.strip().lstrip("- "))
        if budget_lines:
            parts.append("BOUNDARIES: " + " | ".join(budget_lines[:3]))

    # Risk — just the exploration ratio and cost limits
    if identity.get("risk"):
        lines = identity["risk"].split("\n")
        risk_lines = []
        for line in lines:
            if "exploration" in line.lower() and ("ratio" in line.lower() or "default" in line.lower()):
                risk_lines.append(line.strip().lstrip("- "))
            if "never" in line.lower() and "$" in line:
                risk_lines.append(line.strip().lstrip("- "))
        if risk_lines:
            parts.append("RISK: " + " | ".join(risk_lines[:2]))

    # Taste — just the core principles
    if identity.get("taste"):
        parts.append(
            "TASTE: Specific > vague. Sourced > assumed. Actionable > academic. "
            "Honest about uncertainty. Working > clever."
        )

    if not parts:
        return (
            "IDENTITY: No identity files loaded. Operating without constraints. "
            "This is dangerous — identity files should be created in identity/"
        )

    return "\n".join(parts)


def get_identity_summary() -> str:
    """
    Get a compact identity summary suitable for injection into agent prompts.

    This is token-efficient — distills the full identity documents into
    key constraints and priorities that fit in ~200-400 tokens.
    """
    return _get_summary_cached()


def validate_identity() -> dict:
    """
    Check that identity files are healthy.

    Returns:
        {"valid": bool, "loaded": [...], "missing": [...], "warnings": [...]}
    """
    identity = load_identity()
    loaded = [s for s, c in identity.items() if c is not None]
    missing = [s for s, c in identity.items() if c is None]
    warnings = []

    for section in REQUIRED_SECTIONS:
        if section not in loaded:
            warnings.append(f"REQUIRED section '{section}' is missing")

    for section in loaded:
        content = identity[section]
        if content and len(content) < 50:
            warnings.append(f"Section '{section}' is suspiciously short ({len(content)} chars)")

    return {
        "valid": len(warnings) == 0,
        "loaded": loaded,
        "missing": missing,
        "warnings": warnings,
    }
