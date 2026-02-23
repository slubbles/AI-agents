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


client = Anthropic(api_key=ANTHROPIC_API_KEY)

# How many past outputs to analyze for gap extraction
MAX_OUTPUTS_TO_SCAN = 30

# Maximum questions to generate per call
MAX_QUESTIONS = 5


def _build_generator_prompt() -> str:
    today = date.today().isoformat()
    return f"""\
You are a learning strategist for an autonomous research system. TODAY'S DATE: {today}.

Your job: analyze what the system has already researched, identify the biggest knowledge gaps,
and generate the NEXT BEST QUESTION to research in this domain.

You receive:
1. A list of all questions previously asked (to avoid duplicates)
2. Knowledge gaps identified by the researcher in past outputs
3. Weaknesses identified by the critic in past outputs
4. Actionable feedback from the critic
5. The domain context

You must:
1. DIAGNOSE: What are the most important gaps in the system's knowledge?
2. PRIORITIZE: Which gap, if filled, would most improve the system's understanding?
3. GENERATE: Write specific, researachable questions that target those gaps

QUESTION QUALITY RULES:
- Questions must be SPECIFIC and ANSWERABLE via web search
- Don't repeat or trivially rephrase previously asked questions
- Prefer questions that DEEPEN existing knowledge over questions that add breadth
- Each question should target a clear knowledge gap with evidence from the data
- Questions should be timely (leverage today's date: {today})
- Good: "What specific mechanisms drive institutional Bitcoin ETF outflows during market corrections?"
- Bad: "Tell me about crypto" (too vague, not targeted at a gap)

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


GENERATOR_PROMPT = _build_generator_prompt()


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

    # Take recent outputs
    recent = all_outputs[-MAX_OUTPUTS_TO_SCAN:]
    stats = get_stats(domain)

    print(f"[QUESTION-GEN] Scanning {len(recent)} outputs in domain '{domain}'...")
    print(f"  Domain stats: {stats['count']} outputs, avg {stats['avg_score']:.1f}")

    # Extract gaps
    gap_data = _extract_gaps_from_outputs(recent)

    print(f"  Found {len(gap_data['knowledge_gaps'])} knowledge gaps, "
          f"{len(gap_data['weaknesses'])} weaknesses, "
          f"{len(gap_data['actionable_feedback'])} feedback items")
    print(f"  Previously asked: {len(gap_data['questions_asked'])} unique questions")

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
        "knowledge_gaps": gap_data["knowledge_gaps"],
        "critic_weaknesses": gap_data["weaknesses"],
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

    user_message = (
        f"Analyze the knowledge gaps for domain '{domain}' and generate "
        f"the next {MAX_QUESTIONS} best questions to research.\n\n"
        f"DATA:\n{json.dumps(payload, indent=2)}"
    )

    response = client.messages.create(
        model=MODELS["researcher"],  # Use Haiku — it's a synthesis task
        max_tokens=2048,
        system=GENERATOR_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    log_cost(
        MODELS["researcher"],
        response.usage.input_tokens,
        response.usage.output_tokens,
        "question_generator",
        domain,
    )

    raw_text = response.content[0].text.strip()

    # Strip ALL markdown fences
    raw_text = re.sub(r'```(?:json)?\s*\n?', '', raw_text).strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try to find JSON object in text (model may add preamble)
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                print("[QUESTION-GEN] ⚠ Failed to parse question generator output")
                return None
        else:
            print("[QUESTION-GEN] ⚠ Failed to parse question generator output")
            return None

    questions = result.get("questions", [])
    if not questions:
        print("[QUESTION-GEN] ⚠ No questions generated")
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


def get_next_question(domain: str) -> str | None:
    """
    Convenience function: generate questions and return the top-priority one.
    
    Returns:
        The top question string, or None if generation failed.
    """
    result = generate_questions(domain)
    if not result or not result.get("questions"):
        return None

    top = result["questions"][0]
    return top.get("question")
