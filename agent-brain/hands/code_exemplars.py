"""
Code Exemplar Memory — Show, don't tell.

Problem: The executor (Haiku) follows examples far better than abstract
instructions like "include error handling." The system has scored execution
outputs with real code that scored 7+/10, but this code is never shown
to future executions.

Solution: After accepted executions (score >= threshold), extract the
best-scoring files per archetype as "exemplars." In future executions,
inject matching exemplars into the executor/planner context.

The result is "show, don't tell" — instead of "always add proper error
handling," the system shows a concrete, high-scoring example.

Used by:
- main.py (extraction after accepted executions, injection before planning)
- executor.py (receives exemplars in execution_strategy)
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional


MAX_EXEMPLARS_PER_DOMAIN = 20   # Cap total stored exemplars per domain
MAX_EXEMPLAR_SIZE = 3000        # Max content size per exemplar (chars)
MIN_SCORE_TO_STORE = 6.5       # Minimum file quality for exemplar storage


class CodeExemplarStore:
    """
    Stores the best-scoring code examples per archetype/domain.
    
    Usage:
        store = CodeExemplarStore("/path/to/exemplars.json")
        
        # After accepted execution
        store.extract_and_store(domain, scored_artifacts, threshold=7.0)
        
        # Before next execution  
        exemplars = store.get_exemplars(domain, archetypes=["config/tsconfig", "source/typescript"])
        prompt_text = store.format_for_prompt(exemplars)
    """

    def __init__(self, store_path: str):
        self.store_path = store_path
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path) as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def extract_and_store(
        self,
        domain: str,
        scored_artifacts: list[dict],
        min_score: float = MIN_SCORE_TO_STORE,
    ) -> int:
        """
        Extract high-scoring artifacts and store as exemplars.
        
        Args:
            domain: Domain context
            scored_artifacts: From artifact_tracker.score_artifacts()
            min_score: Minimum quality to be exemplar-worthy
            
        Returns:
            Number of exemplars stored/updated
        """
        stored = 0
        
        for sa in scored_artifacts:
            if sa["inferred_score"] < min_score:
                continue
            if not sa.get("step_success", True):
                continue
            
            filepath = sa["filepath"]
            archetype = sa["archetype"]
            score = sa["inferred_score"]
            
            # Read file content
            if not os.path.isfile(filepath):
                continue
            try:
                with open(filepath, "r", errors="replace") as f:
                    content = f.read(MAX_EXEMPLAR_SIZE + 100)
                if len(content) > MAX_EXEMPLAR_SIZE:
                    content = content[:MAX_EXEMPLAR_SIZE] + "\n... (truncated)"
                if not content.strip():
                    continue
            except (OSError, UnicodeDecodeError):
                continue
            
            # Store if better than existing exemplar for this archetype
            if domain not in self._data:
                self._data[domain] = {}
            
            domain_data = self._data[domain]
            existing = domain_data.get(archetype)
            
            if existing and existing.get("score", 0) >= score:
                continue  # Already have a better example
            
            domain_data[archetype] = {
                "content": content,
                "score": score,
                "filepath": filepath,
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }
            stored += 1
        
        # Enforce per-domain limit (keep highest-scoring)
        if domain in self._data and len(self._data[domain]) > MAX_EXEMPLARS_PER_DOMAIN:
            items = sorted(
                self._data[domain].items(),
                key=lambda x: x[1].get("score", 0),
                reverse=True,
            )
            self._data[domain] = dict(items[:MAX_EXEMPLARS_PER_DOMAIN])
        
        if stored > 0:
            self._save()
        
        return stored

    def get_exemplars(
        self,
        domain: str,
        archetypes: Optional[list[str]] = None,
        max_chars: int = 4000,
    ) -> list[dict]:
        """
        Get exemplars for a domain, optionally filtered by archetype.
        
        Args:
            domain: Domain context
            archetypes: If given, return only matching archetypes
            max_chars: Total character budget across all exemplars
            
        Returns:
            List of {archetype, content, score, filepath}
        """
        domain_data = self._data.get(domain, {})
        if not domain_data:
            return []
        
        # Sort by score descending
        candidates = []
        for archetype, data in domain_data.items():
            if archetypes and archetype not in archetypes:
                continue
            candidates.append({
                "archetype": archetype,
                "content": data["content"],
                "score": data["score"],
                "filepath": data.get("filepath", ""),
            })
        
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # Fit within character budget
        result = []
        total_chars = 0
        for c in candidates:
            content_len = len(c["content"])
            if total_chars + content_len > max_chars:
                # Try truncating
                remaining = max_chars - total_chars
                if remaining > 200:
                    c["content"] = c["content"][:remaining] + "\n... (truncated)"
                    result.append(c)
                break
            result.append(c)
            total_chars += content_len
        
        return result

    def predict_archetypes(self, plan: dict) -> list[str]:
        """
        Predict which archetypes a plan will produce, based on step params.
        Used to pre-select relevant exemplars.
        """
        from hands.artifact_tracker import classify_archetype
        
        predicted = set()
        for step in plan.get("steps", []):
            params = step.get("params", {})
            path = params.get("path", "") or params.get("file_path", "")
            if path:
                predicted.add(classify_archetype(path))
        
        return list(predicted)

    def format_for_prompt(self, exemplars: list[dict], max_chars: int = 4000) -> str:
        """
        Format exemplars for injection into executor/planner prompt.
        """
        if not exemplars:
            return ""
        
        lines = [
            "=== HIGH-SCORING CODE EXAMPLES ===",
            "These files scored well in previous executions. Use them as reference for quality.",
            "",
        ]
        
        total = 0
        for ex in exemplars:
            header = f"--- {os.path.basename(ex.get('filepath', ex['archetype']))} (scored {ex['score']}/10, type: {ex['archetype']}) ---"
            entry = f"{header}\n{ex['content']}\n"
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)
        
        lines.append("=== END EXAMPLES ===")
        return "\n".join(lines)

    def stats(self, domain: Optional[str] = None) -> dict:
        """Return store statistics."""
        if domain:
            data = self._data.get(domain, {})
            return {
                "total_exemplars": len(data),
                "archetypes": list(data.keys()),
                "avg_score": round(
                    sum(v.get("score", 0) for v in data.values()) / max(1, len(data)), 2
                ),
            }
        return {
            "domains": len(self._data),
            "total_exemplars": sum(len(v) for v in self._data.values()),
        }
