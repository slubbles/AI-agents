"""
Question Generator (Self-Directed Learning — Stages 1+2)

This is the piece that closes the self-learning loop. It reads the system's own
knowledge gaps and generates the next question to research.

Knowles' framework:
  Stage 1 — Diagnose needs: read knowledge_gaps, weaknesses, actionable_feedback
  Stage 2 — Set goals: generate the next question that fills the biggest gap

Pipeline:
1. Load all outputs for a domain → extract knowledge_gaps + critic weaknesses
2. Collect all previously asked questions (to avoid repeats)
3. Ask Claude to synthesize: what's the most valuable thing to learn next?
4. Return a ranked list of candidate questions

The question generator uses Haiku (cheap) because it's a routing/synthesis task,
not a quality-critical judgment.
"""

import json
import os
import re
import sys
from datetime import date

from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import ANTHROPIC_API_KEY, MODELS
from memory_store import load_outputs, get_stats, load_knowledge_base
from cost_tracker import log_cost
from domain_goals import get_goal
from utils.retry import create_message
from utils.json_parser import extract_json


client = Anthropic(api_key=ANTHROPIC_API_KEY)

# How many past outputs to analyze for gap extraction
MAX_OUTPUTS_TO_SCAN = 30

# Maximum questions to generate per call
MAX_QUESTIONS = 5


def _build_generator_prompt(goal: str | None = None) -> str:
    today = date.today().isoformat()
    
    goal_section = ""
    if goal:
        goal_section = f"""

USER'S GOAL FOR THIS DOMAIN:
{goal}

This is WHY the user cares about this domain. Every question you generate MUST
directly serve this goal. Do NOT generate generic academic questions. Do NOT
research market statistics, industry reports, or theoretical frameworks unless
they directly help the user achieve their stated goal.

Ask yourself for each question: "Does answering this question move the user
closer to their goal?" If not, discard it.
"""
    
    return f"""\
You are a learning strategist for an autonomous research system. TODAY'S DATE: {today}.

Your job: analyze what the system has already researched, identify the biggest knowledge gaps,
and generate the NEXT BEST QUESTION to research in this domain.
{goal_section}
You receive:
1. A list of all questions previously asked (to avoid duplicates)
2. Knowledge gaps identified by the researcher in past outputs
3. Weaknesses identified by the critic in past outputs
4. Actionable feedback from the critic
5. The domain context
6. The user's goal/intent for this domain (if set)

You must:
1. DIAGNOSE: What are the most important gaps in the system's knowledge?
2. PRIORITIZE: Which gap, if filled, would most help the user achieve their goal?
3. GENERATE: Write specific, researchable questions that target those gaps AND serve the goal

QUESTION QUALITY RULES:
- Questions must be SPECIFIC and ANSWERABLE via web search
- Don't repeat or trivially rephrase previously asked questions
- Questions MUST serve the user's stated goal — no academic tangents
- Prefer questions that produce ACTIONABLE intelligence over general knowledge
- Each question should target a clear knowledge gap with evidence from the data
- Questions should be timely (leverage today's date: {today})
- Good: "What are the most common pain points OnlineJobsPH employers report when hiring freelance web developers?"
- Bad: "What is the global freelance market size according to Gartner?" (academic, not actionable)

CRITICAL: You MUST always generate at least 3 questions. The domain is large — there are always more gaps to explore.
If you've exhausted deep questions on current subtopics, BRANCH OUT to related subtopics within the domain.
Never return an empty questions list.

OUTPUT FORMAT — respond with ONLY this JSON, no markdown fencing:
{{
    "diagnosis": {{
        "total_gaps_found": 0,
        "most_critical_gaps": ["gap1", "gap2", "gap3"],
        "recurring_weaknesses": ["weakness1", "weakness2"],
        "coverage_assessment": "Brief assessment of what the system knows vs doesn't know"
    }},
    "questions": [
        {{
            "question": "The specific research question",
            "targets_gap": "Which knowledge gap this addresses",
            "priority": "high|medium|low",
            "reasoning": "Why this is the best next question to ask",
            "builds_on": "Which previous question/output this extends (or 'new_topic')"
        }}
    ]
}}
"""


# Prompt built fresh per call to avoid stale dates in long-running processes


def _extract_gaps_from_outputs(outputs: list[dict]) -> dict:
    """
    Extract all knowledge gaps, weaknesses, and feedback from stored outputs.
    
    Returns a structured summary of what the system doesn't know.
    """
    all_gaps = []
    all_weaknesses = []
    all_feedback = []
    all_questions = []
    questions_with_scores = []

    for out in outputs:
        question = out.get("question", "")
        score = out.get("overall_score", 0)
        all_questions.append(question)
        questions_with_scores.append({"question": question, "score": score})

        research = out.get("research", {})
        gaps = research.get("knowledge_gaps", [])
        all_gaps.extend(gaps)

        critique = out.get("critique", {})
        weaknesses = critique.get("weaknesses", [])
        all_weaknesses.extend(weaknesses)

        feedback = critique.get("actionable_feedback", "")
        if feedback:
            all_feedback.append(feedback)

    return {
        "questions_asked": list(set(all_questions)),
        "questions_with_scores": questions_with_scores,
        "knowledge_gaps": all_gaps,
        "weaknesses": all_weaknesses,
        "actionable_feedback": all_feedback,
    }


def generate_questions(domain: str) -> dict | None:
    """
    Generate the next best questions for a domain based on knowledge gap analysis.
    
    This is Stage 1 (Diagnose Needs) + Stage 2 (Set Goals) of self-directed learning.
    
    Returns:
        Dict with diagnosis and ranked questions, or None if not enough data.
    """
    # Load all outputs for this domain
    all_outputs = load_outputs(domain, min_score=0)

    if len(all_outputs) < 1:
        print(f"[QUESTION-GEN] No outputs in domain '{domain}' — cannot diagnose gaps yet.")
        print(f"  Run at least one manual question first to seed the domain.")
        return None

    # Take recent outputs, filtering out stale ones beyond claim expiry
    recent = all_outputs[-MAX_OUTPUTS_TO_SCAN:]
    try:
        from datetime import datetime, timezone, timedelta
        from config import CLAIM_EXPIRY_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=CLAIM_EXPIRY_DAYS)
        recent = [
            o for o in recent
            if datetime.fromisoformat(
                o.get("timestamp", "2099-01-01T00:00:00+00:00")
            ).replace(tzinfo=timezone.utc) >= cutoff
        ]
    except Exception:
        pass  # If date parsing fails, keep all outputs
    stats = get_stats(domain)

    print(f"[QUESTION-GEN] Scanning {len(recent)} outputs in domain '{domain}'...")
    print(f"  Domain stats: {stats['count']} outputs, avg {stats['avg_score']:.1f}")

    # Extract gaps
    gap_data = _extract_gaps_from_outputs(recent)

    print(f"  Found {len(gap_data['knowledge_gaps'])} knowledge gaps, "
          f"{len(gap_data['weaknesses'])} weaknesses, "
          f"{len(gap_data['actionable_feedback'])} feedback items")
    print(f"  Previously asked: {len(gap_data['questions_asked'])} unique questions")

    # Cap payload size to prevent overwhelming Haiku with huge context
    # Deduplicate and limit gaps/weaknesses to most recent/unique
    unique_gaps = list(dict.fromkeys(gap_data["knowledge_gaps"]))[:20]
    unique_weaknesses = list(dict.fromkeys(gap_data["weaknesses"]))[:15]

    # Build the analysis payload
    payload = {
        "domain": domain,
        "stats": {
            "total_outputs": stats["count"],
            "avg_score": stats["avg_score"],
            "accepted": stats["accepted"],
            "rejected": stats["rejected"],
        },
        "previously_asked_questions": gap_data["questions_asked"],
        "questions_with_scores": gap_data["questions_with_scores"][-10:],  # last 10
        "knowledge_gaps": unique_gaps,
        "critic_weaknesses": unique_weaknesses,
        "critic_feedback": gap_data["actionable_feedback"][-5:],  # last 5
    }

    # Include synthesized knowledge base if available (for smarter gap targeting)
    kb = load_knowledge_base(domain)
    if kb:
        kb_context = {
            "domain_summary": kb.get("domain_summary", ""),
            "topics_covered": [t.get("name", "") for t in kb.get("topics", [])],
            "active_claims_count": len([c for c in kb.get("claims", []) if c.get("status") == "active"]),
            "disputed_claims": [
                c.get("claim", "") for c in kb.get("claims", [])
                if c.get("status") == "conflicted"
            ],
            "kb_knowledge_gaps": [
                {"gap": g.get("gap", ""), "priority": g.get("priority", "")}
                for g in kb.get("knowledge_gaps", [])
            ],
        }
        payload["synthesized_knowledge"] = kb_context
        print(f"  Knowledge base available: {kb_context['active_claims_count']} active claims, "
              f"{len(kb_context['kb_knowledge_gaps'])} identified gaps")

    # Load the user's goal for this domain — the WHY behind the research
    goal = get_goal(domain)
    if goal:
        payload["user_goal"] = goal
        print(f"  Goal: {goal[:100]}{'...' if len(goal) > 100 else ''}")
    else:
        print(f"  ⚠ No goal set for domain '{domain}' — questions may not be actionable")
        print(f"    Set one with: --set-goal or chat: set_domain_goal")

    user_message = (
        f"Analyze the knowledge gaps for domain '{domain}' and generate "
        f"the next {MAX_QUESTIONS} best questions to research.\n\n"
        f"DATA:\n{json.dumps(payload, indent=2)}"
    )

    generator_prompt = _build_generator_prompt(goal=goal)  # Fresh per call (avoids stale dates)
    response = create_message(
        client,
        model=MODELS["question_generator"],  # Haiku — it's a synthesis task
        max_tokens=2048,
        system=generator_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    log_cost(
        MODELS["question_generator"],
        response.usage.input_tokens,
        response.usage.output_tokens,
        "question_generator",
        domain,
    )

    raw_text = response.content[0].text.strip()

    # Robust JSON extraction — only require "questions" key
    EXPECTED_KEYS = {"questions"}
    result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)

    # Retry once on parse failure or empty questions
    needs_retry = result is None or not result.get("questions")
    if needs_retry:
        if result is None:
            print("[QUESTION-GEN] ⚠ Failed to parse output, retrying with simplified prompt...")
        else:
            print("[QUESTION-GEN] ⚠ No questions generated by model")
        print(f"  Raw output (first 300 chars): {raw_text[:300]}")
        
        retry_msg = (
            f"Your previous response did not contain a valid 'questions' array. "
            f"You MUST respond with a JSON object containing a 'questions' array with "
            f"at least 3 question objects. Each question object must have: "
            f"'question', 'priority', 'targets_gap', 'builds_on', 'expected_difficulty'. "
            f"Generate questions for domain '{domain}' based on the gaps data above."
        )
        retry_response = create_message(
            client,
            model=MODELS["question_generator"],
            max_tokens=2048,
            system=generator_prompt,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": raw_text},
                {"role": "user", "content": retry_msg},
            ],
        )
        log_cost(
            MODELS["question_generator"],
            retry_response.usage.input_tokens,
            retry_response.usage.output_tokens,
            "question_generator",
            domain,
        )
        raw_text = retry_response.content[0].text.strip()
        result = extract_json(raw_text, expected_keys=EXPECTED_KEYS)
        
        if result is None:
            print("[QUESTION-GEN] ⚠ Retry also failed to parse")
            return None

    questions = result.get("questions", [])
    if not questions:
        print("[QUESTION-GEN] ⚠ No questions generated after retry")
        print(f"  Raw output (first 300 chars): {raw_text[:300]}")
        return None

    diagnosis = result.get("diagnosis", {})

    print(f"\n[QUESTION-GEN] ✓ Generated {len(questions)} candidate questions")
    print(f"  Coverage: {diagnosis.get('coverage_assessment', 'N/A')}")
    print(f"\n  Candidates (ranked by priority):")

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    questions.sort(key=lambda q: priority_order.get(q.get("priority", "low"), 3))

    for i, q in enumerate(questions, 1):
        pri = q.get("priority", "?").upper()
        print(f"\n    {i}. [{pri}] {q.get('question', '?')}")
        print(f"       Gap: {q.get('targets_gap', 'N/A')}")
        print(f"       Builds on: {q.get('builds_on', 'N/A')}")

    return {
        "diagnosis": diagnosis,
        "questions": questions,
        "domain": domain,
    }


def _fallback_question_from_kb(domain: str) -> str | None:
    """
    Fallback: generate a question from the knowledge base's own identified gaps.
    Returns a question string or None.
    """
    kb = load_knowledge_base(domain)
    if not kb:
        return None
    
    gaps = kb.get("knowledge_gaps", [])
    if not gaps:
        return None
    
    # Pick the highest priority gap not yet covered
    all_outputs = load_outputs(domain, min_score=0)
    asked = set()
    for out in all_outputs:
        q = out.get("question", "").lower().strip()
        if q:
            asked.add(q)
    
    for gap in gaps:
        gap_text = gap.get("gap", "") if isinstance(gap, dict) else str(gap)
        if not gap_text:
            continue
        # Turn the gap into a research question
        question = f"What are the specific details, evidence, and current state of: {gap_text}"
        # Simple check it's not too similar to what's been asked
        if not any(gap_text.lower()[:50] in q for q in asked):
            print(f"[QUESTION-GEN] Using KB gap fallback: {gap_text[:80]}")
            return question
    
    return None


def get_next_question(domain: str) -> str | None:
    """
    Convenience function: generate questions and return the top-priority one.
    Falls back to KB knowledge gaps if model generation fails.
    
    Returns:
        The top question string, or None if generation failed.
    """
    result = generate_questions(domain)
    if result and result.get("questions"):
        top = result["questions"][0]
        return top.get("question")
    
    # Fallback: use KB's own knowledge gaps
    print("[QUESTION-GEN] Trying KB knowledge gap fallback...")
    fallback = _fallback_question_from_kb(domain)
    if fallback:
        return fallback
    
    # Last resort: use a seed question if available
    from domain_seeder import get_seed_question, has_curated_seeds
    if has_curated_seeds(domain):
        seed = get_seed_question(domain)
        if seed:
            print(f"[QUESTION-GEN] Using seed question fallback")
            return seed
    
    return None
