"""
Progress Tracker — Are we actually getting closer to the domain goal?

Individual output scores tell you "was this research good?" but NOT
"are we making progress toward what the user actually wants?"

This module periodically assesses goal-distance: given everything
we've learned so far, how close are we to being able to act on the goal?

Uses grok (cheap) for assessment — not Claude. Runs every N accepted outputs.

Output is a progress report stored in strategies/{domain}/_progress.json
with a simple 0-100 readiness score and specific gaps still remaining.
"""

import json
import logging
import os
from datetime import date, datetime, timezone

from config import MODELS, OPENROUTER_API_KEY
from cost_tracker import log_cost
from domain_goals import get_goal
from memory_store import load_outputs
from utils.json_parser import extract_json
from utils.atomic_write import atomic_json_write

logger = logging.getLogger("progress_tracker")

STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")

# How often to assess progress (every N accepted outputs)
ASSESS_EVERY_N = 5

# Model for progress assessment (must be cheap)
PROGRESS_MODEL = MODELS.get("researcher")  # grok-4.1-fast


def _progress_path(domain: str) -> str:
    return os.path.join(STRATEGIES_DIR, domain, "_progress.json")


def should_assess(domain: str) -> bool:
    """
    Check if it's time for a progress assessment.
    
    Returns True if:
    - A domain goal is set, AND
    - The number of accepted outputs since last assessment >= ASSESS_EVERY_N
    """
    goal = get_goal(domain)
    if not goal:
        return False

    # Check last assessment
    path = _progress_path(domain)
    last_count = 0
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            last_count = data.get("assessed_at_count", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # Count current accepted outputs
    outputs = load_outputs(domain)
    accepted = [o for o in outputs if o.get("critique", {}).get("verdict") == "accept"]
    current_count = len(accepted)

    return (current_count - last_count) >= ASSESS_EVERY_N


def assess_progress(domain: str, force: bool = False) -> dict | None:
    """
    Assess how close we are to the domain goal.
    
    Args:
        domain: The research domain
        force: If True, assess even if it's not time yet
        
    Returns:
        Progress report dict, or None if assessment not needed/possible
    """
    if not force and not should_assess(domain):
        return None

    goal = get_goal(domain)
    if not goal:
        logger.info(f"No goal set for '{domain}' — skipping progress assessment")
        return None

    if not OPENROUTER_API_KEY:
        logger.warning("No OpenRouter key — cannot assess progress")
        return None

    from llm_router import call_llm

    # Gather accepted outputs — summaries only (compact)
    outputs = load_outputs(domain)
    accepted = [o for o in outputs if o.get("critique", {}).get("verdict") == "accept"]
    accepted = accepted[-20:]  # Last 20 max

    # Build compact knowledge summary
    knowledge_items = []
    for o in accepted:
        research = o.get("research", {})
        q = research.get("question", o.get("question", ""))[:80]
        summary = research.get("summary", "")[:200]
        score = o.get("critique", {}).get("overall_score", 0)
        knowledge_items.append(f"- [{score}/10] Q: {q}\n  Summary: {summary}")

    knowledge_block = "\n".join(knowledge_items[-15:])  # Last 15

    # Load knowledge base if exists
    kb_summary = ""
    kb_path = os.path.join(STRATEGIES_DIR, domain, "_knowledge_base.json")
    if os.path.exists(kb_path):
        try:
            with open(kb_path) as f:
                kb = json.load(f)
            claims = kb.get("claims", [])
            active_claims = [c for c in claims if c.get("status") == "active"]
            if active_claims:
                kb_summary = f"\nKnowledge Base: {len(active_claims)} verified claims"
                for c in active_claims[:10]:
                    claim_text = c.get("claim", "")[:100]
                    kb_summary += f"\n  • {claim_text}"
        except (json.JSONDecodeError, OSError):
            pass

    prompt = f"""\
Assess research progress toward a specific goal.

GOAL: {goal}

DOMAIN: {domain}
ACCEPTED OUTPUTS: {len(accepted)} total
{kb_summary}

RECENT RESEARCH (newest first):
{knowledge_block}

Assess:
1. READINESS (0-100): How ready is the user to ACT on their goal based on what's been learned?
   - 0-20: Just started, barely any useful intel
   - 20-40: Some useful data but major gaps remain
   - 40-60: Decent foundation, specific gaps still need filling
   - 60-80: Strong knowledge base, minor gaps only
   - 80-100: Ready to act — enough intelligence to move forward
   
2. GAPS: What specific information is still MISSING to achieve the goal?

3. STRENGTHS: What do we now know well enough?

4. RECOMMENDATION: Should we keep researching, or switch to action?

Respond with ONLY valid JSON:
{{"readiness": 45, "gaps": ["gap1", "gap2"], "strengths": ["strength1"], "recommendation": "keep_researching|ready_to_act|pivot_approach", "reasoning": "brief explanation"}}
"""

    try:
        response = call_llm(
            model=PROGRESS_MODEL,
            system="You are a progress assessor. Be honest and specific. Respond only with JSON.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )

        log_cost(
            PROGRESS_MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
            "progress_tracker",
            domain,
        )

        raw = response.content[0].text.strip()
        result = extract_json(raw, expected_keys={"readiness", "recommendation"})

        if result is None:
            logger.warning("Progress assessment parse failure")
            return None

        # Build and save the progress report
        report = {
            "domain": domain,
            "goal": goal,
            "assessed_at": datetime.now(timezone.utc).isoformat(),
            "assessed_at_count": len(accepted),
            "readiness": min(100, max(0, int(result.get("readiness", 0)))),
            "gaps": result.get("gaps", []),
            "strengths": result.get("strengths", []),
            "recommendation": result.get("recommendation", "keep_researching"),
            "reasoning": result.get("reasoning", ""),
        }

        # Load previous assessments for trend tracking
        path = _progress_path(domain)
        history = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    old = json.load(f)
                history = old.get("history", [])
                # Add previous assessment to history
                if "readiness" in old:
                    history.append({
                        "readiness": old["readiness"],
                        "assessed_at": old["assessed_at"],
                        "assessed_at_count": old.get("assessed_at_count", 0),
                    })
            except (json.JSONDecodeError, OSError):
                pass

        # Keep last 10 assessments in history
        report["history"] = history[-10:]

        # Calculate trend
        if history:
            prev_readiness = history[-1].get("readiness", 0)
            report["readiness_change"] = report["readiness"] - prev_readiness
        else:
            report["readiness_change"] = report["readiness"]  # First assessment

        # Save
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_json_write(path, report)

        logger.info(
            f"Progress for '{domain}': {report['readiness']}% ready "
            f"({report['recommendation']}), {len(report['gaps'])} gaps remaining"
        )

        return report

    except Exception as e:
        logger.warning(f"Progress assessment error: {e}")
        return None


def get_progress(domain: str) -> dict | None:
    """Load the latest progress report for a domain."""
    path = _progress_path(domain)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def display_progress(domain: str) -> None:
    """Print progress report to console."""
    report = get_progress(domain)
    if not report:
        print(f"\n  No progress assessment for '{domain}'.")
        goal = get_goal(domain)
        if not goal:
            print(f"  Set a goal first: python main.py --set-goal --domain {domain}")
        else:
            print(f"  Run more research cycles — assessment happens every {ASSESS_EVERY_N} accepted outputs.")
        return

    readiness = report["readiness"]
    bar_len = 20
    filled = int(readiness / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    print(f"\n  ── Progress: {domain} ──")
    print(f"  Goal: {report['goal'][:80]}")
    print(f"  Readiness: [{bar}] {readiness}%")

    change = report.get("readiness_change", 0)
    if change != 0:
        arrow = "↑" if change > 0 else "↓"
        print(f"  Trend: {arrow} {change:+d}% since last check")

    rec = report.get("recommendation", "")
    rec_labels = {
        "keep_researching": "🔍 Keep researching — gaps remain",
        "ready_to_act": "🚀 Ready to act — enough intelligence to move forward",
        "pivot_approach": "🔄 Pivot — current approach isn't filling the gaps",
    }
    print(f"  Recommendation: {rec_labels.get(rec, rec)}")

    gaps = report.get("gaps", [])
    if gaps:
        print(f"\n  Gaps ({len(gaps)}):")
        for g in gaps[:5]:
            print(f"    • {g}")

    strengths = report.get("strengths", [])
    if strengths:
        print(f"\n  Strengths ({len(strengths)}):")
        for s in strengths[:5]:
            print(f"    ✓ {s}")

    if report.get("reasoning"):
        print(f"\n  Reasoning: {report['reasoning']}")

    print(f"\n  Assessed at: {report.get('assessed_at', '?')[:19]} ({report.get('assessed_at_count', '?')} outputs)")
