"""
Strategy Assembler — Budget-aware, deduplicated strategy context.

Problem: The planner and executor receive strategy text built by blindly
concatenating 4-5 sources (base strategy, principles, lessons, quality warnings,
exemplars). The combined text often exceeds the 3000-char truncation in the
prompt builders, silently dropping critical guidance.

Solution: Assemble strategy text within a hard character budget, prioritizing
the most impactful sources and deduplicating overlapping advice.

Priority order (highest first):
  1. Feedback cache — recurring quality issues (most actionable)
  2. Lessons — patterns learned from past executions
  3. Base strategy — evolved execution strategy from meta-analyst
  4. Quality warnings — per-archetype degradation signals
  5. Exemplars — high-scoring code examples
  6. Principles — cross-domain general patterns (lowest priority)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Default budgets (chars). Planner gets more because it sees the full context.
PLANNER_BUDGET = 4000
EXECUTOR_BUDGET = 3000


@dataclass
class StrategySection:
    """A single section of strategy context."""
    label: str
    content: str
    priority: int  # lower = higher priority


@dataclass
class AssemblyResult:
    """Result of budget-aware strategy assembly."""
    text: str
    included: list[str]  # labels of included sections
    dropped: list[str]   # labels of dropped sections (budget exceeded)
    budget: int
    used: int
    was_deduped: bool = False


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for deduplication comparison."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _extract_sentences(text: str) -> list[str]:
    """Split text into rough sentence-level chunks for dedup."""
    # Split on sentence-ending punctuation or newlines
    chunks = re.split(r"[.\n]+", text)
    return [c.strip() for c in chunks if len(c.strip()) > 20]


def _deduplicate_sections(sections: list[StrategySection]) -> list[StrategySection]:
    """
    Remove duplicate advice across sections.

    If a sentence in a lower-priority section is semantically similar to one
    in a higher-priority section, remove it from the lower-priority section.
    Uses simple normalized string overlap (not embeddings — zero cost).
    """
    if len(sections) <= 1:
        return sections

    # Sort by priority (ascending = highest priority first)
    sorted_sections = sorted(sections, key=lambda s: s.priority)

    # Collect "seen" sentence fingerprints from higher-priority sections
    seen_fingerprints: set[str] = set()
    result = []

    for section in sorted_sections:
        sentences = _extract_sentences(section.content)

        # If content is too short for sentence-level dedup, keep it whole
        if not sentences:
            result.append(section)
            seen_fingerprints.add(_normalize_for_dedup(section.content))
            continue

        unique_sentences = []

        for sentence in sentences:
            fingerprint = _normalize_for_dedup(sentence)
            # Check if any existing fingerprint is a substantial substring
            is_dup = False
            for seen in seen_fingerprints:
                # If >60% of words overlap, consider it a duplicate
                words_new = set(fingerprint.split())
                words_seen = set(seen.split())
                if not words_new:
                    is_dup = True
                    break
                overlap = len(words_new & words_seen) / len(words_new)
                if overlap > 0.6:
                    is_dup = True
                    break
            if not is_dup:
                unique_sentences.append(sentence)
                seen_fingerprints.add(fingerprint)

        # Rebuild section content from unique sentences only
        if unique_sentences:
            new_content = ". ".join(unique_sentences)
            if not new_content.endswith("."):
                new_content += "."
            result.append(StrategySection(
                label=section.label,
                content=new_content,
                priority=section.priority,
            ))
        # If all sentences were duplicates, drop the section entirely

    return result


def assemble(
    budget: int = PLANNER_BUDGET,
    base_strategy: str = "",
    principles: str = "",
    lessons: str = "",
    quality_warnings: str = "",
    exemplars: str = "",
    feedback: str = "",
    deduplicate: bool = True,
) -> AssemblyResult:
    """
    Assemble strategy context within a character budget.

    Prioritizes the most actionable sources and deduplicates overlapping advice.
    Each source is assigned a priority tier (lower = higher priority):
      1. feedback — recurring quality issues
      2. lessons — execution patterns
      3. base_strategy — evolved strategy
      4. quality_warnings — archetype degradation
      5. exemplars — code examples
      6. principles — cross-domain patterns

    Args:
        budget: Maximum characters for the assembled text
        base_strategy: Evolved execution strategy text
        principles: Cross-domain general principles
        lessons: Learned patterns from pattern_learner
        quality_warnings: Per-archetype quality warnings
        exemplars: High-scoring code examples
        feedback: Recurring quality issue warnings from feedback_cache
        deduplicate: Whether to remove overlapping advice

    Returns:
        AssemblyResult with the assembled text and metadata
    """
    # Build sections with priority
    sections: list[StrategySection] = []
    if feedback.strip():
        sections.append(StrategySection("feedback", feedback.strip(), priority=1))
    if lessons.strip():
        sections.append(StrategySection("lessons", lessons.strip(), priority=2))
    if base_strategy.strip():
        sections.append(StrategySection("strategy", base_strategy.strip(), priority=3))
    if quality_warnings.strip():
        sections.append(StrategySection("quality", quality_warnings.strip(), priority=4))
    if exemplars.strip():
        sections.append(StrategySection("exemplars", exemplars.strip(), priority=5))
    if principles.strip():
        sections.append(StrategySection("principles", principles.strip(), priority=6))

    if not sections:
        return AssemblyResult(text="", included=[], dropped=[], budget=budget, used=0)

    # Deduplicate across sections
    was_deduped = False
    if deduplicate and len(sections) > 1:
        original_count = sum(len(s.content) for s in sections)
        sections = _deduplicate_sections(sections)
        deduped_count = sum(len(s.content) for s in sections)
        was_deduped = deduped_count < original_count * 0.95  # >5% reduction

    # Sort by priority (ascending)
    sections.sort(key=lambda s: s.priority)

    # Pack within budget
    parts: list[str] = []
    included: list[str] = []
    dropped: list[str] = []
    used = 0
    separator_cost = 4  # "\n\n" between sections + label overhead

    for section in sections:
        # Calculate cost of adding this section
        header = f"[{section.label.upper()}]\n"
        section_text = header + section.content
        cost = len(section_text) + separator_cost

        if used + cost <= budget:
            parts.append(section_text)
            included.append(section.label)
            used += cost
        else:
            # Try to fit a truncated version (at least 200 chars useful)
            remaining = budget - used - len(header) - separator_cost
            if remaining >= 200:
                truncated = section.content[:remaining - 20] + "... (truncated)"
                parts.append(header + truncated)
                included.append(f"{section.label}*")  # asterisk = truncated
                used += len(header) + len(truncated) + separator_cost
            else:
                dropped.append(section.label)

    text = "\n\n".join(parts)
    return AssemblyResult(
        text=text,
        included=included,
        dropped=dropped,
        budget=budget,
        used=used,
        was_deduped=was_deduped,
    )
