"""
Artifact Quality Tracker — Per-file quality scoring by archetype.

Problem: The system scores entire executions as one number (e.g., 7.4/10),
but never tracks which FILE TYPES consistently cause problems. Tests might
average 5.2 while configs average 8.5 — the system can't see this.

Solution: Map each artifact file to an "archetype" (config/tsconfig, test/jest,
component/react, etc.), infer per-file quality from validator feedback, and
track archetype-level quality over time.

This gives the meta-analyst file-level signal: "test files are your weakness"
instead of just "completeness is low."

Used by:
- main.py (called after save_exec_output to update quality DB)
- exec_meta.py (reads weak/strong archetypes for strategy evolution)
- planner.py (warns about historically weak archetypes)
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from utils.atomic_write import atomic_json_write


# =====================================================
# Archetype classification
# =====================================================

_ARCHETYPE_MAP: dict[str, str] = {
    # Config files
    "package.json": "config/package-json",
    "tsconfig.json": "config/tsconfig",
    "jest.config.js": "config/jest",
    "jest.config.ts": "config/jest",
    ".eslintrc.json": "config/eslint",
    ".eslintrc.js": "config/eslint",
    "pyproject.toml": "config/pyproject",
    "setup.py": "config/setup-py",
    "requirements.txt": "config/requirements",
    "dockerfile": "config/docker",
    "docker-compose.yml": "config/docker-compose",
    ".gitignore": "config/gitignore",
    ".env": "config/env",
    ".env.example": "config/env",
    "makefile": "config/makefile",
    "cargo.toml": "config/cargo",
    "go.mod": "config/go-mod",
}

_EXT_ARCHETYPE_MAP: dict[str, str] = {
    ".test.ts": "test/typescript",
    ".test.tsx": "test/react",
    ".test.js": "test/javascript",
    ".test.jsx": "test/react",
    ".spec.ts": "test/typescript",
    ".spec.tsx": "test/react",
    ".spec.js": "test/javascript",
    "_test.py": "test/python",
    "_test.go": "test/go",
}

_GENERAL_EXT_MAP: dict[str, str] = {
    ".py": "source/python",
    ".ts": "source/typescript",
    ".tsx": "component/react",
    ".js": "source/javascript",
    ".jsx": "component/react",
    ".css": "style/css",
    ".scss": "style/scss",
    ".html": "markup/html",
    ".md": "docs/markdown",
    ".sql": "source/sql",
    ".sh": "script/shell",
    ".yaml": "config/yaml",
    ".yml": "config/yaml",
    ".json": "data/json",
    ".go": "source/go",
    ".rs": "source/rust",
}


def classify_archetype(filepath: str) -> str:
    """
    Map a file path to its archetype string.
    
    Examples:
        "src/components/Button.tsx" -> "component/react"
        "package.json" -> "config/package-json"
        "tests/test_api.py" -> "test/python"
    """
    basename = os.path.basename(filepath).lower()
    
    # Exact filename match
    if basename in _ARCHETYPE_MAP:
        return _ARCHETYPE_MAP[basename]
    
    # Test file pattern match (check multi-part extensions)
    for pattern, archetype in _EXT_ARCHETYPE_MAP.items():
        if basename.endswith(pattern):
            return archetype
    
    # Test file pattern: test_*.py, test_*.go, etc.
    if basename.startswith("test_") or basename.startswith("test-"):
        ext = os.path.splitext(filepath)[1].lower()
        test_map = {
            ".py": "test/python",
            ".ts": "test/typescript",
            ".tsx": "test/react",
            ".js": "test/javascript",
            ".jsx": "test/react",
            ".go": "test/go",
        }
        if ext in test_map:
            return test_map[ext]
    
    # Path-based test detection (files in test/ or tests/ directories)
    path_lower = filepath.lower().replace("\\", "/")
    if "/test/" in path_lower or "/tests/" in path_lower or "/__tests__/" in path_lower:
        ext = os.path.splitext(filepath)[1].lower()
        test_ext_map = {
            ".py": "test/python", ".ts": "test/typescript",
            ".tsx": "test/react", ".js": "test/javascript",
            ".jsx": "test/react", ".go": "test/go",
        }
        if ext in test_ext_map:
            return test_ext_map[ext]
    
    # General extension match
    ext = os.path.splitext(filepath)[1].lower()
    if ext in _GENERAL_EXT_MAP:
        return _GENERAL_EXT_MAP[ext]
    
    return "other/unknown"


# =====================================================
# Per-file quality scoring
# =====================================================

def score_artifacts(
    validation: dict,
    step_results: list[dict],
    artifacts: list[str],
) -> list[dict]:
    """
    Cross-reference validator feedback with artifacts to infer per-file quality.
    
    Returns list of {filepath, archetype, inferred_score, issues, step_success}.
    """
    overall = validation.get("overall_score", 5.0)
    weaknesses = validation.get("weaknesses", [])
    strengths = validation.get("strengths", [])
    critical = validation.get("critical_issues", [])
    static_issues = validation.get("static_checks", {}).get("issues", [])
    
    # Build step success map: artifact -> step success status
    artifact_step_success: dict[str, bool] = {}
    for sr in step_results:
        for art in sr.get("artifacts", []):
            artifact_step_success[art] = sr.get("success", False)
    
    # Build static issues map: file -> list of issues
    static_issue_map: dict[str, list[str]] = {}
    for issue in static_issues:
        f = issue.get("file", "")
        static_issue_map.setdefault(f, []).append(issue.get("detail", ""))
    
    # Combine all negative feedback text
    negative_text = " ".join(weaknesses + critical).lower()
    positive_text = " ".join(strengths).lower()
    
    scored = []
    for filepath in set(artifacts):
        basename = os.path.basename(filepath).lower()
        archetype = classify_archetype(filepath)
        
        # Start with overall score as baseline
        score = overall
        issues = []
        
        # Adjust based on step success
        if filepath in artifact_step_success:
            if not artifact_step_success[filepath]:
                score = max(1.0, score - 2.0)
                issues.append("step_failed")
        
        # Adjust based on static check failures
        if filepath in static_issue_map:
            penalty = min(2.0, len(static_issue_map[filepath]) * 0.5)
            score = max(1.0, score - penalty)
            issues.extend(static_issue_map[filepath])
        
        # Check if file is mentioned in weaknesses/critical issues
        if basename in negative_text:
            score = max(1.0, score - 1.0)
            issues.append("mentioned_in_weaknesses")
        
        # Bonus if mentioned in strengths
        if basename in positive_text:
            score = min(10.0, score + 0.5)
        
        scored.append({
            "filepath": filepath,
            "archetype": archetype,
            "inferred_score": round(score, 1),
            "issues": issues,
            "step_success": artifact_step_success.get(filepath, True),
        })
    
    return scored


# =====================================================
# Quality database persistence
# =====================================================

class ArtifactQualityDB:
    """
    Persists per-archetype quality statistics over time.
    
    Stored in exec_memory/_artifact_quality.json:
    {
        "nextjs-react": {
            "config/tsconfig": {
                "scores": [8.0, 7.5, 9.0],
                "avg_score": 8.17,
                "issues": {"json_valid": 1, "mentioned_in_weaknesses": 0},
                "total_artifacts": 3,
                "last_updated": "2026-02-25T..."
            },
            ...
        }
    }
    """

    MAX_SCORES_PER_ARCHETYPE = 30  # Keep rolling window

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path) as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        atomic_json_write(self.db_path, self._data)

    def update(self, domain: str, scored_artifacts: list[dict]) -> None:
        """Record new artifact scores into the DB."""
        if domain not in self._data:
            self._data[domain] = {}
        
        domain_data = self._data[domain]
        
        for sa in scored_artifacts:
            archetype = sa["archetype"]
            score = sa["inferred_score"]
            
            if archetype not in domain_data:
                domain_data[archetype] = {
                    "scores": [],
                    "avg_score": 0.0,
                    "issues": {},
                    "total_artifacts": 0,
                    "last_updated": "",
                }
            
            entry = domain_data[archetype]
            entry["scores"].append(score)
            
            # Keep rolling window
            if len(entry["scores"]) > self.MAX_SCORES_PER_ARCHETYPE:
                entry["scores"] = entry["scores"][-self.MAX_SCORES_PER_ARCHETYPE:]
            
            entry["avg_score"] = round(
                sum(entry["scores"]) / len(entry["scores"]), 2
            )
            entry["total_artifacts"] += 1
            entry["last_updated"] = datetime.now(timezone.utc).isoformat()
            
            for issue in sa.get("issues", []):
                entry["issues"][issue] = entry["issues"].get(issue, 0) + 1
        
        self._save()

    def get_weak_archetypes(self, domain: str, threshold: float = 6.5) -> list[dict]:
        """Get archetypes that consistently score below threshold."""
        domain_data = self._data.get(domain, {})
        weak = []
        for archetype, entry in domain_data.items():
            if (entry["avg_score"] < threshold and 
                entry["total_artifacts"] >= 2):  # Need at least 2 samples
                weak.append({
                    "archetype": archetype,
                    "avg_score": entry["avg_score"],
                    "samples": entry["total_artifacts"],
                    "top_issues": sorted(
                        entry["issues"].items(),
                        key=lambda x: x[1], reverse=True
                    )[:3],
                })
        return sorted(weak, key=lambda x: x["avg_score"])

    def get_strong_archetypes(self, domain: str, threshold: float = 7.5) -> list[dict]:
        """Get archetypes that consistently score well."""
        domain_data = self._data.get(domain, {})
        strong = []
        for archetype, entry in domain_data.items():
            if (entry["avg_score"] >= threshold and
                entry["total_artifacts"] >= 2):
                strong.append({
                    "archetype": archetype,
                    "avg_score": entry["avg_score"],
                    "samples": entry["total_artifacts"],
                })
        return sorted(strong, key=lambda x: x["avg_score"], reverse=True)

    def get_domain_summary(self, domain: str) -> dict:
        """Full quality summary for a domain."""
        domain_data = self._data.get(domain, {})
        if not domain_data:
            return {"archetypes": 0}
        
        all_scores = []
        for entry in domain_data.values():
            all_scores.extend(entry["scores"])
        
        return {
            "archetypes": len(domain_data),
            "total_artifacts_tracked": sum(e["total_artifacts"] for e in domain_data.values()),
            "overall_avg": round(sum(all_scores) / len(all_scores), 2) if all_scores else 0,
            "weakest": min(domain_data.items(), key=lambda x: x[1]["avg_score"])[0] if domain_data else None,
            "strongest": max(domain_data.items(), key=lambda x: x[1]["avg_score"])[0] if domain_data else None,
        }

    def format_for_prompt(self, domain: str, max_chars: int = 800) -> str:
        """Format quality warnings for injection into planner/strategy."""
        weak = self.get_weak_archetypes(domain)
        if not weak:
            return ""
        
        lines = ["=== ARTIFACT QUALITY WARNINGS ==="]
        for w in weak[:5]:
            issues_str = ", ".join(f"{k}({v})" for k, v in w["top_issues"]) if w["top_issues"] else "various"
            lines.append(
                f"⚠ {w['archetype']}: avg {w['avg_score']}/10 over {w['samples']} files — "
                f"common issues: {issues_str}"
            )
        lines.append("Pay extra attention to these file types. Write complete, valid content.")
        lines.append("=== END QUALITY WARNINGS ===")
        
        text = "\n".join(lines)
        return text[:max_chars]
