"""
Domain Bootstrap — Cold-Start Reliability

When Cortex encounters a new domain (< BOOTSTRAP_MIN_OUTPUTS), this module
orchestrates a reliable bootstrap sequence:

1. Detect cold domain (fewer than N outputs)
2. Generate a domain orientation (what is this domain, key concepts, sources)
3. Apply cross-domain principles if available (auto-transfer)
4. Generate progressive seed questions tailored to the domain
5. Track bootstrap status so the system knows where it stands

The goal: Cortex should produce passable output in ANY domain from round 1,
not just the 14 domains with curated seeds. The generic fallback must be
good enough that a completely unknown domain still bootstraps reliably.
"""

import json
import os
from datetime import datetime, timezone

from config import (
    MEMORY_DIR, MODELS, BOOTSTRAP_MIN_OUTPUTS,
    BOOTSTRAP_SEED_ROUNDS, BOOTSTRAP_AUTO_TRANSFER,
    OPENROUTER_API_KEY,
)
from memory_store import get_stats
from domain_seeder import get_seed_questions, has_curated_seeds, GENERIC_SEEDS
from utils.atomic_write import atomic_json_write
from utils.json_parser import extract_json


def _bootstrap_path(domain: str) -> str:
    return os.path.join(MEMORY_DIR, domain, "_bootstrap.json")


def is_cold(domain: str) -> bool:
    """A domain is 'cold' if it has fewer than BOOTSTRAP_MIN_OUTPUTS accepted outputs."""
    stats = get_stats(domain)
    return stats.get("accepted", 0) < BOOTSTRAP_MIN_OUTPUTS


def get_bootstrap_status(domain: str) -> dict:
    """Load bootstrap status for a domain. Returns empty dict if never bootstrapped."""
    path = _bootstrap_path(domain)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_bootstrap_status(domain: str, status: dict) -> None:
    path = _bootstrap_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_json_write(path, status)


def generate_orientation(domain: str) -> dict | None:
    """
    Generate a domain orientation: what the domain is about, key concepts,
    useful source types, and what 'good research' looks like in this space.

    This gives the system grounding before its first research round,
    so even a completely unknown domain gets a fighting chance.

    Returns dict with orientation text, or None on failure.
    """
    from llm_router import call_llm
    from cost_tracker import log_cost

    prompt = f"""\
You are helping an autonomous research system understand a new domain it has never studied before.

DOMAIN: {domain}

Provide a concise orientation covering:
1. What this domain is about (1-2 sentences)
2. Key concepts and terminology a researcher must know
3. Best types of sources (academic, news, industry, govt, forums, etc.)
4. What "good research" looks like in this domain (depth vs breadth, recency needs, quantitative vs qualitative)
5. Common pitfalls or misinformation traps in this domain
6. 3-5 foundational questions that would establish a baseline understanding

Respond with ONLY valid JSON, no markdown fencing:
{{
    "summary": "Brief domain description",
    "key_concepts": ["concept1", "concept2", ...],
    "best_sources": ["source type 1", "source type 2", ...],
    "research_profile": {{
        "recency_importance": "high|medium|low",
        "quantitative_importance": "high|medium|low",
        "depth_vs_breadth": "depth|breadth|balanced"
    }},
    "pitfalls": ["pitfall1", "pitfall2"],
    "foundational_questions": ["q1", "q2", "q3"]
}}"""

    try:
        response = call_llm(
            model=MODELS.get("question_generator", MODELS.get("prescreen")),
            system="You are a domain analysis expert. Be concise and practical.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        log_cost(
            MODELS.get("question_generator"),
            response.usage.input_tokens,
            response.usage.output_tokens,
            "bootstrap",
            domain,
        )
        raw = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw += block.text
        result = extract_json(raw.strip(), expected_keys={"summary", "foundational_questions"})
        return result
    except Exception as e:
        print(f"[BOOTSTRAP] Orientation generation failed: {e}")
        return None


def get_bootstrap_questions(domain: str, orientation: dict | None = None, count: int = None) -> list[str]:
    """
    Get bootstrap questions for a domain, progressively deeper.

    Priority:
    1. Orientation-generated foundational questions (if orientation was run)
    2. Curated seed questions (if domain has them)
    3. Generic seeds (always available for any domain)

    Returns up to `count` questions ordered from broad to specific.
    """
    if count is None:
        count = BOOTSTRAP_SEED_ROUNDS

    questions = []

    if orientation and orientation.get("foundational_questions"):
        questions.extend(orientation["foundational_questions"])

    if len(questions) < count:
        seeds = get_seed_questions(domain, count=count)
        for s in seeds:
            if s not in questions:
                questions.append(s)

    return questions[:count]


def try_auto_transfer(domain: str) -> dict | None:
    """
    Attempt to auto-transfer cross-domain principles to a cold domain.

    Only runs if:
    - BOOTSTRAP_AUTO_TRANSFER is enabled
    - Principles exist from proven domains
    - Domain doesn't already have a custom strategy

    Returns transfer result or None.
    """
    if not BOOTSTRAP_AUTO_TRANSFER:
        return None

    from strategy_store import get_strategy
    existing, version = get_strategy("researcher", domain)
    if existing and version != "default":
        return None

    from agents.cross_domain import load_principles, generate_seed_strategy
    principles = load_principles()
    if not principles or not principles.get("principles"):
        return None

    print(f"[BOOTSTRAP] Cross-domain principles available — generating seed strategy for '{domain}'...")
    try:
        result = generate_seed_strategy(domain)
        if result:
            print(f"[BOOTSTRAP] Seed strategy {result['version']} created (pending approval)")
        return result
    except Exception as e:
        print(f"[BOOTSTRAP] Auto-transfer failed: {e}")
        return None


def bootstrap_domain(domain: str, goal: str | None = None) -> dict:
    """
    Run the full bootstrap sequence for a cold domain.

    Steps:
    1. Check if bootstrap is needed
    2. Generate domain orientation
    3. Try cross-domain transfer
    4. Generate bootstrap questions
    5. Save bootstrap status

    This does NOT run the actual research rounds — it prepares the domain
    so the next call to run_loop or the daemon will execute properly.

    Returns bootstrap status dict.
    """
    stats = get_stats(domain)
    existing_status = get_bootstrap_status(domain)

    if existing_status.get("phase") == "complete":
        return existing_status

    status = {
        "domain": domain,
        "phase": "in_progress",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "outputs_at_start": stats.get("count", 0),
        "accepted_at_start": stats.get("accepted", 0),
    }

    print(f"\n[BOOTSTRAP] Bootstrapping domain '{domain}'...")
    print(f"  Current state: {stats.get('count', 0)} outputs, {stats.get('accepted', 0)} accepted")

    orientation = generate_orientation(domain)
    if orientation:
        status["orientation"] = orientation
        print(f"[BOOTSTRAP] Orientation: {orientation.get('summary', '?')[:100]}")
        print(f"  Recency importance: {orientation.get('research_profile', {}).get('recency_importance', '?')}")
        print(f"  Key concepts: {', '.join(orientation.get('key_concepts', [])[:5])}")
    else:
        print(f"[BOOTSTRAP] Orientation failed — using generic fallback")
        status["orientation"] = None

    transfer = try_auto_transfer(domain)
    status["transfer"] = transfer

    questions = get_bootstrap_questions(domain, orientation)
    status["bootstrap_questions"] = questions
    print(f"[BOOTSTRAP] Generated {len(questions)} bootstrap questions")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q[:90]}")

    if goal:
        try:
            from domain_goals import set_goal, get_goal
            if not get_goal(domain):
                set_goal(domain, goal)
                status["goal_set"] = goal
                print(f"[BOOTSTRAP] Goal set: {goal[:80]}")
        except Exception:
            pass

    _save_bootstrap_status(domain, status)
    return status


def mark_bootstrap_complete(domain: str) -> None:
    """Mark a domain's bootstrap as complete (called when it reaches BOOTSTRAP_MIN_OUTPUTS)."""
    status = get_bootstrap_status(domain)
    if not status:
        status = {"domain": domain}

    stats = get_stats(domain)
    status["phase"] = "complete"
    status["completed_at"] = datetime.now(timezone.utc).isoformat()
    status["outputs_at_completion"] = stats.get("count", 0)
    status["accepted_at_completion"] = stats.get("accepted", 0)

    _save_bootstrap_status(domain, status)
    print(f"[BOOTSTRAP] Domain '{domain}' bootstrap complete "
          f"({stats.get('accepted', 0)} accepted outputs)")


def get_bootstrap_question(domain: str) -> str | None:
    """
    Get the next bootstrap question for a cold domain.

    Used by the scheduler/main loop as a drop-in replacement for
    get_seed_question when bootstrap status exists.

    Returns None if no more bootstrap questions are available.
    """
    status = get_bootstrap_status(domain)
    if not status or status.get("phase") == "complete":
        return None

    questions = status.get("bootstrap_questions", [])
    if not questions:
        return None

    stats = get_stats(domain)
    idx = stats.get("count", 0)

    if idx < len(questions):
        return questions[idx]

    return None
