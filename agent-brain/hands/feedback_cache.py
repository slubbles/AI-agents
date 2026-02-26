"""
Feedback Cache — Persistent per-dimension failure signals for the planner.

Problem: The same validation failures recur across executions ("no error handling",
"missing input validation"). The planner only learns from these through slow paths
(pattern learner needs 2+ occurrences, meta-analyst runs every 3 executions).

Solution: Direct, fast feedback loop. After each validation, store which dimensions
scored below threshold along with specific failure reasons. Before each planning
cycle, inject targeted reminders for persistently weak dimensions.

Used by: main.py (after validation → record, before planning → inject)
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Optional

from utils.atomic_write import atomic_json_write

MAX_RECENT_ISSUES = 5  # Rolling buffer per dimension
WEAK_THRESHOLD = 7.0  # Dimensions scoring below this get recorded
CLEAR_THRESHOLD = 7.5  # Auto-clear when dimension improves above this


class FeedbackCache:
    """Persistent per-dimension failure signals."""

    def __init__(self, path: str):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        atomic_json_write(self._path, self._data)

    def record(
        self,
        domain: str,
        validation: dict,
        threshold: float = WEAK_THRESHOLD,
    ) -> list[str]:
        """
        Extract low-scoring dimensions + reasons from validation, store in rolling buffer.
        
        Returns list of dimensions that were recorded as weak.
        """
        scores = validation.get("scores", {})
        weaknesses = validation.get("weaknesses", [])
        critical_issues = validation.get("critical_issues", [])
        
        if not scores:
            return []

        domain_data = self._data.setdefault(domain, {})
        recorded = []

        for dim, score in scores.items():
            if not isinstance(score, (int, float)):
                continue
            if score >= threshold:
                continue

            # This dimension is weak — extract relevant issues
            dim_lower = dim.lower().replace("_", " ")
            relevant_issues = []
            
            for w in weaknesses:
                if isinstance(w, str) and (dim_lower in w.lower() or len(weaknesses) <= 3):
                    relevant_issues.append(w)
            for ci in critical_issues:
                if isinstance(ci, str):
                    relevant_issues.append(f"CRITICAL: {ci}")

            # If no matching issues found, add a generic one
            if not relevant_issues:
                relevant_issues.append(f"{dim} scored {score}/10")

            dim_entry = domain_data.setdefault(dim, {
                "recent_issues": [],
                "occurrences": 0,
                "avg_score": 0.0,
            })

            # Update rolling buffer
            dim_entry["occurrences"] = dim_entry.get("occurrences", 0) + 1
            existing = dim_entry.get("recent_issues", [])
            for issue in relevant_issues:
                if issue not in existing:  # Avoid exact duplicates
                    existing.append(issue)
            dim_entry["recent_issues"] = existing[-MAX_RECENT_ISSUES:]

            # Update running average
            prev_avg = dim_entry.get("avg_score", 0.0)
            n = dim_entry["occurrences"]
            dim_entry["avg_score"] = round(prev_avg + (score - prev_avg) / n, 2)
            dim_entry["last_seen"] = date.today().isoformat()

            recorded.append(dim)

        if recorded:
            self._save()

        return recorded

    def auto_clear(
        self,
        domain: str,
        validation: dict,
        clear_threshold: float = CLEAR_THRESHOLD,
    ) -> list[str]:
        """
        Remove dimension feedback when scores improve above threshold.
        Returns list of cleared dimensions.
        """
        scores = validation.get("scores", {})
        domain_data = self._data.get(domain, {})
        if not domain_data or not scores:
            return []

        cleared = []
        for dim, score in scores.items():
            if not isinstance(score, (int, float)):
                continue
            if dim in domain_data and score >= clear_threshold:
                del domain_data[dim]
                cleared.append(dim)

        if cleared:
            if domain_data:
                self._data[domain] = domain_data
            else:
                self._data.pop(domain, None)
            self._save()

        return cleared

    def get_for_planner(self, domain: str, max_items: int = 5) -> str:
        """
        Format cached feedback as planner-ready text.
        Returns '' if no weak dimensions.
        """
        domain_data = self._data.get(domain, {})
        if not domain_data:
            return ""

        lines = ["=== RECURRING QUALITY ISSUES (address these in your plan) ==="]
        count = 0

        # Sort by lowest avg_score
        sorted_dims = sorted(
            domain_data.items(),
            key=lambda x: x[1].get("avg_score", 10),
        )

        for dim, info in sorted_dims:
            if count >= max_items:
                break
            avg = info.get("avg_score", 0)
            occurrences = info.get("occurrences", 0)
            issues = info.get("recent_issues", [])

            lines.append(
                f"\n{dim.upper()} (avg {avg}/10, seen {occurrences}x):"
            )
            for issue in issues[-3:]:  # Show last 3
                lines.append(f"  - {issue}")
            count += 1

        lines.append("=== END RECURRING ISSUES ===")
        return "\n".join(lines)

    def stats(self, domain: str) -> dict:
        """Summary stats for a domain."""
        domain_data = self._data.get(domain, {})
        if not domain_data:
            return {"weak_dimensions": 0, "dimensions": {}}

        dims = {}
        for dim, info in domain_data.items():
            dims[dim] = {
                "avg_score": info.get("avg_score", 0),
                "occurrences": info.get("occurrences", 0),
                "issue_count": len(info.get("recent_issues", [])),
            }

        return {
            "weak_dimensions": len(dims),
            "dimensions": dims,
        }

    def get_all_domains(self) -> list[str]:
        """List domains with cached feedback."""
        return list(self._data.keys())
