"""
Research Lessons — persistent corrections from critic rejections and strategy rollbacks.

The Brain-side equivalent of hands/pattern_learner.py.
Captures specific "don't do this again" rules from:
1. Critic rejections (what went wrong + the actionable feedback)
2. Strategy rollbacks (which strategy change hurt scores)
3. Manual corrections from the operator

These get injected into the researcher prompt so it doesn't repeat mistakes.
Lessons are domain-scoped. Stored as JSON, one file per domain.

This is NOT the strategy. The strategy says what TO do.
Lessons say what NOT to do — based on actual failures.
"""

import json
import os
from datetime import datetime, timezone

from utils.atomic_write import atomic_json_write

LESSONS_DIR = os.path.join(os.path.dirname(__file__), "memory", "_lessons")
MAX_LESSONS_PER_DOMAIN = 30  # Keep it tight. Noise kills agent performance.


def _lessons_path(domain: str) -> str:
    return os.path.join(LESSONS_DIR, f"{domain}.json")


def _load_lessons(domain: str) -> list[dict]:
    path = _lessons_path(domain)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_lessons(domain: str, lessons: list[dict]) -> None:
    os.makedirs(LESSONS_DIR, exist_ok=True)
    # Keep only the most recent MAX_LESSONS_PER_DOMAIN
    if len(lessons) > MAX_LESSONS_PER_DOMAIN:
        lessons = lessons[-MAX_LESSONS_PER_DOMAIN:]
    atomic_json_write(_lessons_path(domain), lessons)


def add_lesson(domain: str, lesson: str, source: str, details: str = "") -> None:
    """
    Add a lesson from a failure.
    
    Args:
        domain: Which domain this applies to
        lesson: The specific rule (e.g., "Don't search for future-dated events as facts")
        source: Where this came from ("critic_rejection", "strategy_rollback", "manual")
        details: Optional context (e.g., the critique feedback that triggered this)
    """
    lessons = _load_lessons(domain)
    
    # Deduplicate — don't add the same lesson twice
    for existing in lessons:
        if existing.get("lesson") == lesson:
            existing["hit_count"] = existing.get("hit_count", 1) + 1
            existing["last_seen"] = datetime.now(timezone.utc).isoformat()
            _save_lessons(domain, lessons)
            return
    
    lessons.append({
        "lesson": lesson,
        "source": source,
        "details": details[:500],  # Cap detail length
        "hit_count": 1,
        "created": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
    })
    _save_lessons(domain, lessons)


def add_rejection_lesson(domain: str, score: float, weakest_dim: str, feedback: str) -> None:
    """
    Extract a lesson from a critic rejection.
    Only captures lessons from genuinely bad outputs (score < 5) to avoid noise.
    """
    if score >= 5:
        return  # Not bad enough to warrant a lesson — might just be mediocre
    
    # Build a specific lesson from the weakest dimension
    dim_lessons = {
        "accuracy": f"Accuracy failure (scored {score}): verify claims against fetched content before including them",
        "depth": f"Depth failure (scored {score}): explain WHY and HOW, not just list facts",
        "completeness": f"Completeness failure (scored {score}): cover multiple angles, don't tunnel on one aspect",
        "specificity": f"Specificity failure (scored {score}): include concrete numbers, dates, URLs — vague claims get rejected",
        "intellectual_honesty": f"Honesty failure (scored {score}): distinguish facts from speculation, flag uncertainty",
    }
    
    lesson = dim_lessons.get(weakest_dim, f"Low score ({score}): {feedback[:200]}")
    add_lesson(domain, lesson, "critic_rejection", details=feedback[:500])


def add_rollback_lesson(domain: str, strategy_version: str, reason: str) -> None:
    """Capture a lesson when a strategy gets rolled back."""
    lesson = f"Strategy {strategy_version} was rolled back: {reason[:200]}"
    add_lesson(domain, lesson, "strategy_rollback", details=reason)


def get_lessons(domain: str) -> list[dict]:
    """Get all lessons for a domain, sorted by hit_count (most repeated first)."""
    lessons = _load_lessons(domain)
    return sorted(lessons, key=lambda l: l.get("hit_count", 1), reverse=True)


def format_lessons_for_prompt(domain: str, max_items: int = 10) -> str:
    """
    Format lessons as a block to inject into the researcher's system prompt.
    Returns empty string if no lessons exist.
    """
    lessons = get_lessons(domain)[:max_items]
    if not lessons:
        return ""
    
    lines = ["LESSONS FROM PAST FAILURES (do NOT repeat these mistakes):"]
    for l in lessons:
        hit = f" (seen {l['hit_count']}x)" if l.get("hit_count", 1) > 1 else ""
        lines.append(f"- {l['lesson']}{hit}")
    
    return "\n".join(lines)


def show_lessons(domain: str) -> None:
    """Print lessons for a domain (CLI display)."""
    lessons = get_lessons(domain)
    print(f"\n{'='*60}")
    print(f"  RESEARCH LESSONS — Domain: {domain or 'all'}")
    print(f"{'='*60}\n")
    
    if not lessons:
        print("  No lessons yet. Lessons are captured from critic rejections (score < 5)")
        print("  and strategy rollbacks.")
        return
    
    for l in lessons:
        source = l.get("source", "?")
        hits = l.get("hit_count", 1)
        print(f"  [{source}] {l['lesson']}")
        print(f"    Seen: {hits}x | First: {l.get('created', '?')[:10]}")
        if l.get("details"):
            print(f"    Context: {l['details'][:120]}...")
        print()
    
    print(f"  Total: {len(lessons)} lessons")
