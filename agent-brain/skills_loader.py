"""
Skills Loader — Dynamic category-based skill loading for agent prompts.

Replaces hardcoded identity file paths in executor.py and planner.py with
a scalable system that loads .md skill files from identity/skills/{category}/.

Skills are plain markdown files. Optional YAML frontmatter for metadata:
    ---
    name: React Best Practices
    description: Patterns for performant React/Next.js apps
    tags: [react, nextjs, performance]
    priority: 10
    ---

Usage:
    from skills_loader import load_skills, list_skills, lookup_design_data

    # Load skills for a task (respects token budget)
    skills_text = load_skills(["coding", "design"], max_chars=8000)

    # List available skills
    skills = list_skills("coding")

    # Query design data for an industry
    design_rec = lookup_design_data("healthcare")
"""

import csv
import io
import logging
import os
import re
from typing import Optional

logger = logging.getLogger("skills_loader")

# ── Configuration ────────────────────────────────────────────────────────

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "identity", "skills")
DESIGN_DATA_DIR = os.path.join(SKILLS_DIR, "design", "data")

# Category priority for loading order when budget is tight
CATEGORY_PRIORITY = {
    "writing": 0,
    "workflow": 1,
    "coding": 2,
    "design": 3,
    "marketing": 4,
    "research": 5,
    "product": 6,
    "sales": 7,
    "validation": 8,
}

# Keyword patterns for auto-detecting relevant categories from task text
CATEGORY_KEYWORDS = {
    "coding": re.compile(
        r"\b(code|coding|typescript|react|next\.?js|api|backend|frontend|component|"
        r"database|deploy|vercel|npm|build|refactor|debug|test|security)\b",
        re.IGNORECASE,
    ),
    "design": re.compile(
        r"\b(design|ui|ux|visual|layout|color|font|typography|style|theme|"
        r"responsive|mobile|css|tailwind|animation|landing.?page)\b",
        re.IGNORECASE,
    ),
    "marketing": re.compile(
        r"\b(marketing|content|copy|seo|blog|article|brand|campaign|social.?media|"
        r"headline|newsletter|email.?marketing|outreach|landing.?page|press.?release)\b",
        re.IGNORECASE,
    ),
    "sales": re.compile(
        r"\b(sales|outreach|prospect|pitch|cold.?email|client|lead|crm|"
        r"investor|fundrais)\b",
        re.IGNORECASE,
    ),
    "product": re.compile(
        r"\b(product|feature|spec|roadmap|user.?research|stakeholder|prd|"
        r"requirement|prioriti[sz]|backlog|sprint)\b",
        re.IGNORECASE,
    ),
    "research": re.compile(
        r"\b(research|market|competitor|competitive|analysis|survey|data|"
        r"trend|opportunity|gap|landscape)\b",
        re.IGNORECASE,
    ),
    "validation": re.compile(
        r"\b(validat|reality.?check|idea.?check|competition|existing|"
        r"already.?exists|saturated|demand)\b",
        re.IGNORECASE,
    ),
    "workflow": re.compile(
        r"\b(workflow|process|methodology|search.?first|verification|"
        r"loop|pipeline|cost.?aware|architecture)\b",
        re.IGNORECASE,
    ),
    "writing": re.compile(
        r"\b(writ|voice|tone|human|reddit|post|content|article|"
        r"copy|humaniz|natural|style|prose)\b",
        re.IGNORECASE,
    ),
}


# ── Frontmatter parsing ─────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown content.

    Returns (metadata_dict, body_without_frontmatter).
    If no frontmatter, returns ({}, original_content).
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter_text = content[3:end].strip()
    body = content[end + 3:].strip()

    # Simple key: value parsing (no full YAML dependency)
    metadata = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Handle list values: [a, b, c]
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip("'\"") for v in value[1:-1].split(",")]
            # Handle numeric values
            elif value.isdigit():
                value = int(value)
            else:
                value = value.strip("'\"")
            metadata[key] = value

    return metadata, body


# ── Core loading ─────────────────────────────────────────────────────────

def _get_skill_files(category: str) -> list[dict]:
    """Get all skill files in a category directory with metadata.

    Returns list of dicts: {path, name, category, size, priority, metadata}
    """
    category_dir = os.path.join(SKILLS_DIR, category)
    if not os.path.isdir(category_dir):
        return []

    skills = []
    for filename in sorted(os.listdir(category_dir)):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(category_dir, filename)
        if not os.path.isfile(filepath):
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except (IOError, OSError) as e:
            logger.warning(f"Failed to read skill file {filepath}: {e}")
            continue

        metadata, body = _parse_frontmatter(content)

        skills.append({
            "path": filepath,
            "filename": filename,
            "name": metadata.get("name", filename.replace(".md", "").replace("_", " ").title()),
            "category": category,
            "size": len(body),
            "priority": metadata.get("priority", 50),
            "metadata": metadata,
            "body": body,
        })

    return skills


def load_skills(categories: list[str], max_chars: int = 8000) -> str:
    """Load skill files from specified categories, respecting token budget.

    Args:
        categories: List of category names to load from (e.g., ["coding", "design"])
        max_chars: Maximum total characters to include (default 8000)

    Returns:
        Formatted string with skill content, ready for prompt injection.
        Includes section headers per skill for clarity.
    """
    if not categories:
        return ""

    # Gather all skill files from requested categories
    all_skills = []
    seen_paths = set()
    for category in categories:
        for skill in _get_skill_files(category):
            if skill["path"] not in seen_paths:
                seen_paths.add(skill["path"])
                all_skills.append(skill)

    if not all_skills:
        return ""

    # Sort by: category priority first, then individual skill priority (lower = higher priority)
    all_skills.sort(key=lambda s: (
        CATEGORY_PRIORITY.get(s["category"], 99),
        s["priority"],
        s["size"],  # Prefer smaller files when priority is equal
    ))

    # Build output respecting character budget
    parts = []
    chars_used = 0

    for skill in all_skills:
        body = skill["body"]

        # Section header
        header = f"\n=== SKILL: {skill['name']} ({skill['category']}) ===\n"
        footer = f"\n=== END SKILL: {skill['name']} ===\n"
        overhead = len(header) + len(footer)

        available = max_chars - chars_used - overhead
        if available <= 100:
            # Not enough room for meaningful content
            break

        if len(body) > available:
            body = body[:available - 3] + "..."

        parts.append(header + body + footer)
        chars_used += len(parts[-1])

    result = "".join(parts)

    loaded_names = [s["name"] for s in all_skills[:len(parts)]]
    if loaded_names:
        logger.info(f"Loaded {len(loaded_names)} skills: {', '.join(loaded_names)}")

    return result


def list_skills(category: str | None = None) -> list[dict]:
    """List available skills with metadata.

    Args:
        category: If provided, list skills in that category only.
                  If None, list all skills across all categories.

    Returns:
        List of dicts with: name, category, filename, size, priority
    """
    categories = [category] if category else list(CATEGORY_PRIORITY.keys())
    result = []

    for cat in categories:
        for skill in _get_skill_files(cat):
            result.append({
                "name": skill["name"],
                "category": skill["category"],
                "filename": skill["filename"],
                "size": skill["size"],
                "priority": skill["priority"],
            })

    return result


def detect_categories(task_text: str) -> list[str]:
    """Auto-detect relevant skill categories from task text.

    Scans the text for keyword patterns and returns matching categories,
    sorted by priority.

    Args:
        task_text: The task description or goal text

    Returns:
        List of category names that match (e.g., ["coding", "design"])
    """
    if not task_text:
        return []

    matched = []
    for category, pattern in CATEGORY_KEYWORDS.items():
        if pattern.search(task_text):
            matched.append(category)

    # Sort by category priority
    matched.sort(key=lambda c: CATEGORY_PRIORITY.get(c, 99))

    return matched


# ── Design data lookup ───────────────────────────────────────────────────

def _load_csv_data(filename: str) -> list[dict]:
    """Load a CSV file from the design data directory."""
    filepath = os.path.join(DESIGN_DATA_DIR, filename)
    if not os.path.isfile(filepath):
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except (IOError, OSError, csv.Error) as e:
        logger.warning(f"Failed to load design data {filepath}: {e}")
        return []


def lookup_design_data(industry: str, data_type: str | None = None) -> str:
    """Query design databases for industry-specific recommendations.

    Searches CSV databases for rows matching the industry keyword.
    Returns formatted recommendations string.

    Args:
        industry: Industry name or keyword (e.g., "healthcare", "fintech", "ecommerce")
        data_type: Optional filter: "rules", "styles", "palettes", "fonts", "ux"
                   If None, searches all databases.

    Returns:
        Formatted string with design recommendations, or empty string if no matches.
    """
    if not industry:
        return ""

    industry_lower = industry.lower()
    results = []

    databases = {
        "rules": ("industry_rules.csv", "Industry Rules"),
        "styles": ("ui_styles.csv", "UI Styles"),
        "palettes": ("color_palettes.csv", "Color Palettes"),
        "fonts": ("font_pairings.csv", "Font Pairings"),
        "ux": ("ux_guidelines.csv", "UX Guidelines"),
    }

    targets = {data_type: databases[data_type]} if data_type and data_type in databases else databases

    for dtype, (filename, label) in targets.items():
        rows = _load_csv_data(filename)
        if not rows:
            continue

        # Search all string fields for industry match
        matching = []
        for row in rows:
            row_text = " ".join(str(v) for v in row.values()).lower()
            if industry_lower in row_text:
                matching.append(row)

        if matching:
            results.append(f"\n--- {label} for '{industry}' ---")
            for row in matching[:5]:  # Cap at 5 per type
                results.append("  " + " | ".join(f"{k}: {v}" for k, v in row.items()))

    return "\n".join(results) if results else ""
