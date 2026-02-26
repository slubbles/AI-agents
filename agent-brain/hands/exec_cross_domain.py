"""
Execution Cross-Domain Learning — Transfers execution patterns across domains.

Parallel to Brain's cross_domain.py but for the execution layer.
Extracts reusable patterns from high-scoring executions and applies them
as strategy seeds in new domains.

Examples of transferable patterns:
- "Always create package.json before npm install"
- "Run tests after every file creation step"
- "Pin dependency versions to avoid breaking changes"
- "Commit working state before refactoring steps"
"""

import json
import os
import sys
from datetime import datetime, timezone

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    ANTHROPIC_API_KEY, MODELS, STRATEGY_DIR,
    EXEC_QUALITY_THRESHOLD,
)
from hands.exec_memory import load_exec_outputs
from cost_tracker import log_cost
from utils.retry import create_message
from utils.json_parser import extract_json

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# File storing extracted execution principles
_EXEC_PRINCIPLES_PATH = os.path.join(STRATEGY_DIR, "_exec_principles.json")

# Minimum score for an execution to contribute to principles
MIN_SCORE_FOR_PRINCIPLES = 7.0

# Maximum number of principles to store
MAX_PRINCIPLES = 50


def load_exec_principles() -> list[dict]:
    """Load stored execution principles."""
    if not os.path.exists(_EXEC_PRINCIPLES_PATH):
        return []
    try:
        with open(_EXEC_PRINCIPLES_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_exec_principles(principles: list[dict]) -> None:
    """Save execution principles, capping at MAX_PRINCIPLES."""
    os.makedirs(os.path.dirname(_EXEC_PRINCIPLES_PATH), exist_ok=True)
    # Keep most recent/highest-evidence principles
    principles = sorted(
        principles,
        key=lambda p: (p.get("evidence_count", 1), p.get("avg_score", 0)),
        reverse=True,
    )[:MAX_PRINCIPLES]
    with open(_EXEC_PRINCIPLES_PATH, "w") as f:
        json.dump(principles, f, indent=2)


def extract_exec_principles(domain: str, min_outputs: int = 3) -> list[dict] | None:
    """
    Extract reusable execution principles from high-scoring executions in a domain.
    
    Only runs if there are enough high-quality outputs.
    Returns new principles extracted, or None if insufficient data.
    """
    outputs = load_exec_outputs(domain, min_score=MIN_SCORE_FOR_PRINCIPLES)
    if len(outputs) < min_outputs:
        return None

    # Prepare analysis data
    successes = []
    for out in outputs[-15:]:  # Cap at 15 most recent high-scoring
        exec_data = out.get("execution", {})
        val_data = out.get("validation", {})
        successes.append({
            "goal": out.get("goal", "")[:200],
            "score": out.get("overall_score", 0),
            "steps_count": out.get("plan", {}).get("steps_count", 0),
            "tool_sequence": [
                s.get("tool", "?") for s in exec_data.get("step_results", [])
                if s.get("success")
            ],
            "strengths": val_data.get("strengths", [])[:3],
            "domain": out.get("domain", domain),
        })

    existing_principles = load_exec_principles()
    existing_texts = [p.get("principle", "") for p in existing_principles]

    prompt = f"""\
Analyze these {len(successes)} high-scoring code execution results and extract 
REUSABLE patterns that would improve execution quality in ANY coding domain.

Focus on:
- Tool usage patterns (order, combinations)  
- Planning patterns (step granularity, dependencies)
- Error prevention (what avoids failures)
- Quality drivers (what leads to high scores)

EXISTING PRINCIPLES (don't duplicate):
{json.dumps(existing_texts[:20], indent=2)}

HIGH-SCORING EXECUTIONS from '{domain}':
{json.dumps(successes, indent=2)}

Output ONLY valid JSON — an array of principle objects:
[
  {{
    "principle": "Always create project config files before installing dependencies",
    "evidence": "Observed in 8/10 high-scoring executions",
    "domains_observed": ["{domain}"],
    "category": "planning|tool_usage|error_prevention|quality"
  }}
]

Extract 3-7 principles. Be specific and actionable — avoid vague advice.
"""

    response = create_message(
        client,
        model=MODELS.get("exec_meta_analyst", MODELS.get("meta_analyst", "claude-sonnet-4-20250514")),
        max_tokens=2048,
        system="You extract reusable execution principles from coding data. Output only valid JSON.",
        messages=[{"role": "user", "content": prompt}],
    )

    log_cost(
        model=MODELS.get("exec_meta_analyst", MODELS.get("meta_analyst")),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        agent_role="exec_cross_domain",
        domain=domain,
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    new_principles = extract_json(text)
    if not isinstance(new_principles, list):
        return None

    # Enrich and merge with existing
    now = datetime.now(timezone.utc).isoformat()
    for p in new_principles:
        p.setdefault("extracted_at", now)
        p.setdefault("source_domain", domain)
        p.setdefault("evidence_count", 1)
        p.setdefault("avg_score", sum(
            s["score"] for s in successes
        ) / len(successes) if successes else 0)

    # Merge: update evidence_count for matching principles
    merged = list(existing_principles)
    for new_p in new_principles:
        found = False
        for existing_p in merged:
            # Simple similarity: check if principles are about the same thing
            if _principles_similar(new_p.get("principle", ""), existing_p.get("principle", "")):
                # Merge evidence
                existing_p["evidence_count"] = existing_p.get("evidence_count", 1) + 1
                domains = set(existing_p.get("domains_observed", []))
                domains.update(new_p.get("domains_observed", []))
                existing_p["domains_observed"] = sorted(domains)
                existing_p["last_seen"] = now
                found = True
                break
        if not found:
            merged.append(new_p)

    _save_exec_principles(merged)
    return new_principles


def _principles_similar(a: str, b: str) -> bool:
    """Check if two principle texts are about the same concept."""
    # Simple approach: significant word overlap
    a_words = set(a.lower().split()) - {"the", "a", "an", "is", "to", "and", "or", "in", "of", "for", "with", "before", "after"}
    b_words = set(b.lower().split()) - {"the", "a", "an", "is", "to", "and", "or", "in", "of", "for", "with", "before", "after"}
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words)
    min_len = min(len(a_words), len(b_words))
    return overlap / min_len > 0.6 if min_len > 0 else False


def get_principles_for_domain(domain: str, max_principles: int = 10) -> str:
    """
    Get relevant execution principles formatted for injection into strategies.
    
    Returns principles as a formatted string for strategy/prompt injection.
    Prioritizes principles observed across multiple domains and with high evidence.
    """
    principles = load_exec_principles()
    if not principles:
        return ""

    # Score principles by relevance: multi-domain > single-domain, high-evidence > low
    scored = []
    for p in principles:
        domains = p.get("domains_observed", [])
        relevance = 0
        # Boost if this domain is in the observed list
        if domain in domains:
            relevance += 3
        # Boost multi-domain principles (more general)
        relevance += min(len(domains), 5)
        # Boost high evidence count
        relevance += min(p.get("evidence_count", 1), 5)
        scored.append((relevance, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored[:max_principles]]

    if not top:
        return ""

    lines = ["## Learned Execution Principles"]
    for i, p in enumerate(top, 1):
        domains_str = ", ".join(p.get("domains_observed", ["general"]))
        evidence = p.get("evidence_count", 1)
        lines.append(
            f"{i}. {p.get('principle', '?')} "
            f"(evidence: {evidence}, domains: {domains_str})"
        )

    return "\n".join(lines)


def suggest_principles_in_strategy(domain: str) -> str | None:
    """
    Generate a strategy seed for a new domain using execution principles.
    
    Returns a strategy string combining domain template with learned principles,
    or None if no principles exist.
    """
    principles_text = get_principles_for_domain(domain)
    if not principles_text:
        return None

    from hands.exec_templates import get_template
    template = get_template(domain)
    
    return f"{template}\n\n{principles_text}\n"
