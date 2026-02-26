"""
Plan Cache — Caches successful execution plans for reuse.

When the system encounters a goal similar to a previously successful one,
it can reuse the plan (adjusting parameters) instead of re-planning from scratch.

This saves:
- One planner API call (Sonnet) per cache hit
- Planning latency (3-5 seconds)
- Improves reliability (proven plans succeed more often)

Cache keys are normalized goal strings. Similarity is checked via:
1. Exact match (after normalization)
2. Keyword overlap scoring (Jaccard similarity)

Eviction: LRU with max entries. Entries also expire after 7 days
to account for strategy evolution making old plans stale.
"""

import json
import hashlib
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from utils.atomic_write import atomic_json_write


# Cache config
MAX_CACHE_ENTRIES = 50
CACHE_EXPIRY_DAYS = 7
MIN_SIMILARITY_THRESHOLD = 0.6  # Jaccard similarity for keyword match


def _normalize_goal(goal: str) -> str:
    """Normalize a goal string for comparison."""
    # Lowercase, strip extra whitespace, remove punctuation
    goal = goal.lower().strip()
    goal = re.sub(r'[^\w\s]', ' ', goal)
    goal = re.sub(r'\s+', ' ', goal)
    return goal


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text."""
    stopwords = {
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
        'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were',
        'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'could', 'should', 'may', 'might', 'can',
        'that', 'this', 'these', 'those', 'it', 'its',
        'build', 'create', 'make', 'write', 'implement', 'add',  # too generic
    }
    words = set(_normalize_goal(text).split())
    return words - stopwords


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _goal_hash(goal: str) -> str:
    """Create a hash key for a normalized goal."""
    return hashlib.sha256(_normalize_goal(goal).encode()).hexdigest()[:16]


class PlanCache:
    """
    LRU cache for execution plans with similarity matching.

    Usage:
        cache = PlanCache("/path/to/cache.json")
        
        # Check for cached plan
        cached = cache.get(goal="Build a TypeScript REST API", domain="nextjs-react")
        if cached:
            plan = cached["plan"]
        
        # Store successful plan
        cache.put(goal="Build a TypeScript REST API", domain="nextjs-react",
                  plan=plan_dict, score=7.5)
    """

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._cache = data
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save(self) -> None:
        """Save cache to disk."""
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        atomic_json_write(self.cache_path, self._cache)

    def _evict_expired(self) -> None:
        """Remove expired entries."""
        now = datetime.now(timezone.utc)
        expired_keys = []
        for key, entry in self._cache.items():
            try:
                cached_at = datetime.fromisoformat(entry["cached_at"])
                if now - cached_at > timedelta(days=CACHE_EXPIRY_DAYS):
                    expired_keys.append(key)
            except (KeyError, ValueError):
                expired_keys.append(key)
        for key in expired_keys:
            del self._cache[key]

    def _evict_lru(self) -> None:
        """Remove least recently used entries if over capacity."""
        if len(self._cache) <= MAX_CACHE_ENTRIES:
            return
        # Sort by last_used timestamp, remove oldest
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].get("last_used", "2000-01-01"),
        )
        to_remove = len(self._cache) - MAX_CACHE_ENTRIES
        for key, _ in sorted_entries[:to_remove]:
            del self._cache[key]

    def get(self, goal: str, domain: str = "") -> Optional[dict]:
        """
        Look up a cached plan for a goal.

        First tries exact match, then similarity match.
        Returns the cached entry dict (with 'plan', 'score', etc.) or None.
        """
        self._evict_expired()

        # Exact match
        key = _goal_hash(goal)
        if key in self._cache:
            entry = self._cache[key]
            if not domain or entry.get("domain", "") == domain:
                entry["last_used"] = datetime.now(timezone.utc).isoformat()
                entry["hits"] = entry.get("hits", 0) + 1
                self._save()
                return entry

        # Similarity match — find the best match above threshold
        goal_keywords = _extract_keywords(goal)
        best_match = None
        best_score = 0.0

        for key, entry in self._cache.items():
            if domain and entry.get("domain", "") != domain:
                continue
            cached_keywords = set(entry.get("keywords", []))
            sim = _jaccard_similarity(goal_keywords, cached_keywords)
            if sim > best_score and sim >= MIN_SIMILARITY_THRESHOLD:
                best_score = sim
                best_match = entry

        if best_match:
            best_match["last_used"] = datetime.now(timezone.utc).isoformat()
            best_match["hits"] = best_match.get("hits", 0) + 1
            best_match["similarity_score"] = best_score
            self._save()
            return best_match

        return None

    def put(self, goal: str, domain: str, plan: dict, score: float) -> None:
        """
        Store a successful plan in the cache.

        Only caches plans with score >= 6 (accepted plans).
        """
        if score < 6.0:
            return  # Don't cache rejected plans

        key = _goal_hash(goal)
        self._cache[key] = {
            "goal": goal,
            "domain": domain,
            "plan": plan,
            "score": score,
            "keywords": list(_extract_keywords(goal)),
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "last_used": datetime.now(timezone.utc).isoformat(),
            "hits": 0,
        }

        self._evict_lru()
        self._save()

    def stats(self) -> dict:
        """Get cache statistics."""
        self._evict_expired()
        total_hits = sum(e.get("hits", 0) for e in self._cache.values())
        return {
            "entries": len(self._cache),
            "max_entries": MAX_CACHE_ENTRIES,
            "total_hits": total_hits,
            "domains": list(set(e.get("domain", "") for e in self._cache.values())),
        }

    def clear(self, domain: str = "") -> int:
        """Clear cache entries. If domain specified, only clear that domain."""
        if not domain:
            count = len(self._cache)
            self._cache.clear()
        else:
            keys = [k for k, v in self._cache.items() if v.get("domain") == domain]
            count = len(keys)
            for k in keys:
                del self._cache[k]
        self._save()
        return count
