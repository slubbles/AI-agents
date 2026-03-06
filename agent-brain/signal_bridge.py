"""
Signal Bridge — Converts top signal opportunities into Brain research questions.

This is the connective tissue between Signal Intelligence (what real people
complain about) and Brain's self-learning loop (deep research + scoring).

Pipeline:
    1. Read top-scored opportunities from signals DB
    2. Generate research questions that Brain can answer
    3. Tag questions with source="signal" for tracking
    4. Integrate into question_generator's candidate pool

No LLM calls — pure template-based question generation.
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from signal_collector import get_top_opportunities, init_signals_db

logger = logging.getLogger(__name__)

# Question templates — filled from opportunity data
_VALIDATION_TEMPLATES = [
    "Who is already solving '{pain}' for {audience}? What tools exist, what do they charge, and what's missing?",
    "How many {audience} experience '{pain}'? What data exists on market size and willingness to pay?",
    "What would a 2-week MVP look like for solving '{pain}'? What's the minimum feature set for first 10 users?",
]

_COMPETITOR_TEMPLATES = [
    "What are the top 5 competitors solving '{pain}' and what are their pricing models, weaknesses, and review scores?",
]

_TECHNICAL_TEMPLATES = [
    "What APIs, data sources, or integrations would be needed to build a product solving '{pain}' for {audience}?",
]


def generate_signal_questions(limit: int = 3, min_score: int = 60) -> list[dict]:
    """
    Generate Brain research questions from top signal opportunities.

    Reads the highest-scored opportunities and converts them into
    specific, researchable questions for Brain's question_generator.

    Args:
        limit: Max questions to generate
        min_score: Minimum opportunity score to consider

    Returns:
        List of question dicts:
        [
            {
                "question": "The research question",
                "source": "signal",
                "source_post_id": int,
                "opportunity_score": int,
                "pain_point": str,
                "category": str,
                "priority": "high"|"medium",
                "targets_gap": str,
            }
        ]
    """
    init_signals_db()

    opportunities = get_top_opportunities(limit=limit * 2)

    if not opportunities:
        return []

    # Filter by minimum score
    qualified = [o for o in opportunities if o.get("opportunity_score", 0) >= min_score]

    if not qualified:
        logger.info(f"[BRIDGE] No opportunities above score {min_score}")
        return []

    questions = []
    seen_pains = set()

    for opp in qualified:
        if len(questions) >= limit:
            break

        pain = opp.get("pain_point_summary", "")
        if not pain or pain.lower() in seen_pains:
            continue
        seen_pains.add(pain.lower())

        audience = opp.get("affected_audience", "users")
        score = opp.get("opportunity_score", 0)
        category = opp.get("category", "Other")
        post_id = opp.get("post_id")
        severity = opp.get("severity", 3)

        # Pick template based on what we know
        existing = opp.get("existing_solutions", [])
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                existing = []

        # If there are known competitors, ask about competitive gaps
        if existing and len(existing) > 0:
            templates = _COMPETITOR_TEMPLATES + _VALIDATION_TEMPLATES[:1]
        else:
            templates = _VALIDATION_TEMPLATES[:2]

        # Add technical question for high-severity
        if severity >= 4:
            templates.append(_TECHNICAL_TEMPLATES[0])

        # Generate one question per opportunity (most impactful template)
        template = templates[0]
        question_text = template.format(pain=pain, audience=audience)

        questions.append({
            "question": question_text,
            "source": "signal",
            "source_post_id": post_id,
            "opportunity_score": score,
            "pain_point": pain,
            "category": category,
            "priority": "high" if score >= 80 else "medium",
            "targets_gap": f"Signal-sourced: {pain[:80]}",
        })

    logger.info(f"[BRIDGE] Generated {len(questions)} research questions from signals")
    return questions


def get_signal_domain_for_category(category: str) -> str:
    """
    Map a signal category to the most appropriate Brain research domain.

    Brain uses domains like 'productized-services', 'crypto', etc.
    Signal categories are broader ('Marketing', 'Finance', etc.).
    This maps them so research goes to the right domain.
    """
    category_to_domain = {
        "Productivity": "micro-saas",
        "Developer Tools": "dev-tools",
        "Business": "micro-saas",
        "Communication": "micro-saas",
        "Finance": "fintech",
        "Health": "health-tech",
        "Education": "edu-tech",
        "Marketing": "marketing-tools",
        "Design": "design-tools",
        "Data & Analytics": "analytics",
        "Automation": "automation",
        "Other": "micro-saas",
    }
    return category_to_domain.get(category, "micro-saas")
