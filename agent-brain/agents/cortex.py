"""
Cortex Orchestrator — The reasoning layer above Agent Brain + Agent Hands.

This is the "brain of brains" — the unified orchestrator that sits on top
of both subsystems and provides:

  1. Strategic interpretation of Brain's research data, memory, knowledge bases
  2. Strategic interpretation of Hands' execution results, projects, artifacts
  3. Coordinated decision-making about what to research and build next
  4. Brain→Hands pipeline — turning research insights into actionable tasks
  5. Unified system health assessment across all subsystems

Model: Claude Sonnet (strongest available) — orchestration decisions are sacred.
The chat interface uses a cheap model for conversation; the Cortex Orchestrator
uses the best model for decisions that matter.

Architecture:
  User ↔ Chat (Grok 4.1, cheap) → Cortex Orchestrator (Sonnet, reasoning) → Brain + Hands

The Orchestrator does NOT replace the existing domain orchestrator (agents/orchestrator.py)
which handles multi-domain round allocation. The Cortex Orchestrator sits ABOVE it,
providing strategic reasoning and cross-subsystem coordination.

Usage:
  from agents.cortex import query_orchestrator, plan_next_actions, assess_system

  # Ask the orchestrator to reason about anything
  result = query_orchestrator("What should we focus on next?", domain="productized-services")

  # Get strategic plan
  plan = plan_next_actions()

  # Get unified system assessment
  health = assess_system()
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import MODELS, DAILY_BUDGET_USD
from llm_router import call_llm
from cost_tracker import log_cost
from utils.json_parser import extract_json


# ── Configuration ────────────────────────────────────────────────────────

ORCHESTRATOR_MODEL = MODELS.get("cortex_orchestrator", "claude-sonnet-4-20250514")
MAX_CONTEXT_CHARS = 12000  # Cap context to avoid blowing up token costs


# ── System State Gathering ───────────────────────────────────────────────

def _gather_brain_state(domain: str | None = None) -> dict:
    """
    Gather current state from Agent Brain subsystems.

    Collects: domain stats, score trajectories, knowledge base summaries,
    strategy status, pending approvals, recent outputs, goals.
    """
    from memory_store import get_stats, load_knowledge_base, load_outputs
    from strategy_store import (
        get_active_version, get_strategy_status, list_pending,
    )
    from analytics import domain_comparison, score_trajectory
    from domain_goals import get_goal, list_goals

    state = {
        "goals": {},
        "domains": [],
    }

    try:
        state["goals"] = list_goals() or {}
    except Exception:
        pass

    # Get domain data
    try:
        comparisons = domain_comparison()
    except Exception:
        comparisons = []

    for d in comparisons:
        domain_name = d["domain"]

        # If a specific domain is requested, skip others for cost efficiency
        if domain and domain_name != domain:
            continue

        try:
            stats = get_stats(domain_name)
            traj = score_trajectory(domain_name) or {}
            goal = get_goal(domain_name)
            kb = load_knowledge_base(domain_name)
            active_ver = get_active_version("researcher", domain_name)
            strat_status = get_strategy_status("researcher", domain_name)
            pending = list_pending("researcher", domain_name)

            # Recent outputs — last 5
            recent_raw = load_outputs(domain_name, min_score=0)[-5:]
            recent = []
            for o in recent_raw:
                research = o.get("research", {})
                recent.append({
                    "question": o.get("question", "?")[:100],
                    "score": o.get("overall_score",
                                   o.get("critique", {}).get("overall_score", "?")),
                    "accepted": o.get("accepted", False),
                    "summary": research.get("summary", "")[:150],
                })

            # KB summary
            kb_summary = None
            if kb:
                claims = kb.get("claims", [])
                active_claims = [c for c in claims if c.get("status") == "active"]
                gaps = kb.get("identified_gaps", [])
                topics = list({c.get("topic", "?") for c in active_claims})
                kb_summary = {
                    "claims": len(active_claims),
                    "topics": topics[:10],
                    "gaps": [str(g)[:80] for g in gaps[:5]],
                    "domain_summary": kb.get("domain_summary", "")[:200],
                }

            state["domains"].append({
                "name": domain_name,
                "goal": goal[:200] if goal else None,
                "stats": {
                    "count": stats.get("count", 0),
                    "accepted": stats.get("accepted", 0),
                    "rejected": stats.get("rejected", 0),
                    "avg_score": round(stats.get("avg_score", 0), 1),
                },
                "trajectory": {
                    "trend": traj.get("trend", "unknown"),
                    "improvement": round(traj.get("improvement", 0), 2),
                },
                "strategy": {
                    "version": active_ver,
                    "status": strat_status,
                },
                "pending_strategies": [p.get("version", "?") for p in pending],
                "kb": kb_summary,
                "recent_outputs": recent,
            })
        except Exception as e:
            state["domains"].append({
                "name": domain_name,
                "error": str(e)[:100],
            })

    return state


def _gather_hands_state() -> dict:
    """
    Gather current state from Agent Hands subsystems.

    Collects: execution task history, project status, artifact counts.
    """
    state = {"execution_domains": [], "projects": []}

    # Execution memory
    exec_mem_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "exec_memory"
    )
    if os.path.exists(exec_mem_dir):
        for domain_name in sorted(os.listdir(exec_mem_dir)):
            domain_path = os.path.join(exec_mem_dir, domain_name)
            if not os.path.isdir(domain_path):
                continue
            tasks = []
            for f in sorted(os.listdir(domain_path)):
                if not f.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(domain_path, f)) as fh:
                        task = json.load(fh)
                    tasks.append({
                        "goal": task.get("goal", "?")[:100],
                        "status": task.get("status", "?"),
                        "score": task.get("overall_score",
                                          task.get("validation", {}).get(
                                              "overall_score")),
                        "accepted": task.get("accepted", False),
                    })
                except Exception:
                    continue
            state["execution_domains"].append({
                "domain": domain_name,
                "task_count": len(tasks),
                "recent_tasks": tasks[-5:],
            })

    # Projects
    projects_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "projects"
    )
    if os.path.exists(projects_dir):
        for f in sorted(os.listdir(projects_dir)):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(projects_dir, f)) as fh:
                    proj = json.load(fh)
                phases = proj.get("phases", [])
                state["projects"].append({
                    "id": proj.get("id", f.replace(".json", "")),
                    "name": proj.get("name", "?")[:100],
                    "status": proj.get("status", "?"),
                    "total_phases": len(phases),
                    "completed_phases": sum(
                        1 for p in phases if p.get("status") == "completed"
                    ),
                })
            except Exception:
                continue

    return state


def _gather_infra_state() -> dict:
    """
    Gather infrastructure state.

    Collects: budget, watchdog status, sync status.
    """
    state = {}

    # Budget
    try:
        from cost_tracker import get_daily_spend, check_budget, check_balance
        daily = get_daily_spend()
        budget = check_budget()
        balance = check_balance()
        state["budget"] = {
            "spent_today": round(daily.get("total_usd", 0), 4),
            "daily_limit": DAILY_BUDGET_USD,
            "remaining_today": round(budget.get("remaining", 0), 2),
            "within_budget": budget.get("within_budget", True),
            "balance": round(balance.get("remaining", 0), 2),
        }
    except Exception as e:
        state["budget"] = {"error": str(e)[:80]}

    # Watchdog
    try:
        from watchdog import get_watchdog_status
        wd = get_watchdog_status()
        state["watchdog"] = {
            "state": wd.get("state", "unknown"),
            "cycles_completed": wd.get("cycles_completed", 0),
            "consecutive_failures": wd.get("consecutive_failures", 0),
        }
    except Exception:
        state["watchdog"] = {"state": "not_initialized"}

    # Sync
    try:
        from sync import check_sync, get_task_stats
        sync = check_sync()
        task_stats = get_task_stats()
        state["sync"] = {
            "aligned": sync.get("aligned", True),
            "issues": sync.get("issues", [])[:3],
        }
        state["task_queue"] = task_stats
    except Exception:
        state["sync"] = {"aligned": True}

    return state


def gather_full_state(domain: str | None = None) -> dict:
    """
    Gather unified system state from all subsystems.

    Returns a dict summarizing Brain, Hands, and Infrastructure state.
    Used as context for the Orchestrator's reasoning.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "brain": _gather_brain_state(domain),
        "hands": _gather_hands_state(),
        "infrastructure": _gather_infra_state(),
    }


def _truncate_state(state: dict, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Serialize state to JSON, truncating if too large."""
    raw = json.dumps(state, indent=2, default=str)
    if len(raw) <= max_chars:
        return raw
    # Truncate and note it
    return raw[:max_chars] + "\n... (truncated for cost control)"


# ── Orchestrator System Prompt ───────────────────────────────────────────

def _build_orchestrator_system() -> str:
    """Build orchestrator system prompt with identity layer."""
    identity_block = ""
    try:
        from identity_loader import get_identity_summary
        summary = get_identity_summary()
        if summary:
            identity_block = "\nSYSTEM IDENTITY (your values — these override everything):\n" + summary + "\n"
    except Exception:
        pass

    header = ("You are the Cortex Orchestrator — the strategic reasoning layer\n"
              "above Agent Brain (research) and Agent Hands (execution).\n"
              + identity_block + "\n")

    return header + """Your role:
1. INTERPRET — What does the system's data mean? What are the insights?
2. DECIDE — What should Brain research next? What should Hands build?
3. COORDINATE — How should research findings become actionable build tasks?
4. ASSESS — Is the system healthy? On track? Where are the risks?

THE PIPELINE (this is how value is created):
  Brain researches a niche → understands pain, users, competitors
  Cortex evaluates research → decides if findings are build-ready
  Cortex creates a BuildTask → goal, brief, constraints, tech stack
  Hands builds → scaffold, backend, frontend, integration, deploy
  Hands deploys → live URL on Vercel
  Cortex reports → Telegram message with URL, cost, confidence

Your job is to DRIVE this pipeline forward. Every recommendation should ask:
"Does this move us closer to a live URL?"

RESEARCH-TO-BUILD READINESS:
A domain is build-ready when:
- At least 5 accepted outputs (score ≥ 6) exist
- Knowledge base has active claims about user pain, competitors, and opportunity
- A clear "who is the user and what is their #1 pain" can be articulated
- You can write a 1-paragraph brief that Hands could act on

When a domain IS build-ready, create a BuildTask with:
- type: "hands_build"
- A specific goal: "Build a [type] for [user] that solves [pain]"
- A brief from the knowledge base: user persona, core feature, design direction
- Constraints: tech stack, budget cap, timeline

When a domain is NOT yet build-ready, recommend specific Brain research to fill the gaps.

CRITICAL PRINCIPLES:
- Lead with INSIGHTS, not data recitation. "The research shows X, which means Y" not "Domain has 5 outputs."
- Be brutally honest about what's proven vs. what's aspirational.
- Every recommendation must be actionable — specify what to do and why.
- Distinguish between "we know" (KB data) vs "we think" (inference) vs "we don't know" (gaps).
- Cost is real. Don't recommend expensive actions without justification.
- The system generates revenue by: research → build → deploy → acquire customers.
  Every recommendation should serve this pipeline.
- Prefer BUILDING over MORE RESEARCH when the knowledge base has enough to act on.
  The biggest risk is researching forever and never shipping.

RESPONSE FORMAT (always JSON):
{
  "interpretation": "Your analysis of the current situation — what the data means",
  "key_insights": ["Insight 1", "Insight 2", ...],
  "recommended_actions": [
    {
      "type": "brain_research" | "hands_build" | "hands_deploy" | "strategy_change" | "system_maintenance",
      "priority": "critical" | "high" | "medium" | "low",
      "description": "What to do",
      "rationale": "Why this matters",
      "domain": "target domain (if applicable)",
      "brief": "For hands_build: the build brief from research (optional)"
    }
  ],
  "build_readiness": {
    "ready_domains": ["domains that have enough research to build"],
    "almost_ready": ["domains that need 1-2 more research rounds"],
    "not_ready": ["domains that need significant more research"]
  },
  "risks": ["Risk 1", "Risk 2", ...],
  "system_health": "healthy" | "warning" | "critical",
  "next_question": "What should the system investigate next to make better decisions?"
}

Be concise. Don't pad. Every word should add value.
"""

ORCHESTRATOR_SYSTEM = _build_orchestrator_system()


# ── Core Functions ───────────────────────────────────────────────────────

def query_orchestrator(
    question: str,
    domain: str | None = None,
    include_brain: bool = True,
    include_hands: bool = True,
    include_infra: bool = True,
    extra_context: str = "",
) -> dict:
    """
    Ask the Cortex Orchestrator to reason about the system state.

    This is the main entry point. The Orchestrator:
    1. Gathers relevant system state
    2. Sends it to Claude Sonnet with the question
    3. Returns structured reasoning + recommended actions

    Args:
        question: What to reason about
        domain: Focus domain (optional, gathers all if None)
        include_brain: Include Brain state in context
        include_hands: Include Hands state in context
        include_infra: Include infra state in context
        extra_context: Additional context from the chat layer

    Returns:
        Dict with interpretation, key_insights, recommended_actions, risks,
        system_health, next_question. Returns {"error": ...} on failure.
    """
    # Gather state
    state = {}
    if include_brain:
        state["brain"] = _gather_brain_state(domain)
    if include_hands:
        state["hands"] = _gather_hands_state()
    if include_infra:
        state["infrastructure"] = _gather_infra_state()

    state_json = _truncate_state(state)

    # Build the user message
    user_msg = f"SYSTEM STATE:\n{state_json}\n\n"
    if extra_context:
        user_msg += f"ADDITIONAL CONTEXT:\n{extra_context}\n\n"
    user_msg += f"QUESTION:\n{question}"

    try:
        response = call_llm(
            model=ORCHESTRATOR_MODEL,
            system=ORCHESTRATOR_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=2048,
            temperature=0.3,  # Low temp for strategic reasoning
        )

        # Track cost
        if response.usage:
            log_cost(
                model=ORCHESTRATOR_MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                agent_role="cortex_orchestrator",
                domain=domain or "system",
            )

        # Extract text
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        # Parse JSON response
        parsed = extract_json(text)
        if parsed:
            return parsed

        # If JSON extraction failed, return raw text as interpretation
        return {
            "interpretation": text,
            "key_insights": [],
            "recommended_actions": [],
            "risks": [],
            "system_health": "unknown",
            "next_question": None,
            "_raw": True,
        }

    except Exception as e:
        return {
            "error": str(e),
            "interpretation": f"Orchestrator query failed: {e}",
            "key_insights": [],
            "recommended_actions": [],
            "risks": [f"Orchestrator error: {e}"],
            "system_health": "unknown",
            "next_question": None,
        }


def plan_next_actions(domain: str | None = None) -> dict:
    """
    Ask the Orchestrator to create a strategic plan.

    Gathers full system state and asks: "What should the system focus on next?"

    Returns:
        Orchestrator response with prioritized recommended_actions.
    """
    question = (
        "Based on the current system state, what should the system focus on next? "
        "Consider: Which domains need more research? What findings are ready to be "
        "acted on (built/deployed)? Are there knowledge gaps blocking progress? "
        "Are there pending strategy approvals that need attention? "
        "What's the most efficient use of the remaining budget today?"
    )
    if domain:
        question += f"\n\nFocus primarily on the '{domain}' domain."

    return query_orchestrator(question, domain=domain)


def coordinate_brain_to_hands(domain: str) -> dict:
    """
    Ask the Orchestrator to identify actionable tasks from Brain's research.

    Looks at what Brain has learned and recommends specific things
    for Hands to build/deploy/execute.

    Returns:
        Orchestrator response with hands-focused recommended_actions.
    """
    question = (
        f"Review the research findings and knowledge base for domain '{domain}'. "
        f"What specific, concrete tasks should Agent Hands execute based on what "
        f"Brain has learned? Be very specific — include goals, requirements, and "
        f"expected outcomes for each task. Only recommend tasks where the research "
        f"provides enough information to act confidently."
    )
    return query_orchestrator(
        question,
        domain=domain,
        include_hands=True,
        include_brain=True,
    )


def assess_system() -> dict:
    """
    Ask the Orchestrator for a unified system health assessment.

    Checks all subsystems and provides an honest evaluation of
    what's working, what's not, and what needs attention.

    Returns:
        Orchestrator response focused on system_health and risks.
    """
    question = (
        "Give me an honest assessment of the system's current state. "
        "What's working well? What's broken or underperforming? "
        "What are the biggest risks? Is the system on track to generate "
        "revenue? What would you prioritize fixing right now?"
    )
    return query_orchestrator(question)


def interpret_findings(domain: str, question: str = "") -> dict:
    """
    Ask the Orchestrator to interpret Brain's research findings.

    Instead of dumping raw knowledge base data, the Orchestrator
    provides a strategic interpretation: what does the data mean,
    what are the actionable takeaways, what's still unknown.

    Returns:
        Orchestrator response with interpretation and key_insights.
    """
    base_question = (
        f"Interpret the research findings for domain '{domain}'. "
        f"What has the system learned? What are the key insights? "
        f"What's actionable? What's still unknown?"
    )
    if question:
        base_question += f"\n\nSpecific focus: {question}"

    return query_orchestrator(
        base_question,
        domain=domain,
        include_hands=False,
        include_infra=False,
    )


# ── Response Formatting ─────────────────────────────────────────────────

def format_orchestrator_response(result: dict) -> str:
    """
    Format an orchestrator response for human-readable display.

    Used by the chat layer to present orchestrator reasoning
    in a clear, actionable format.
    """
    if "error" in result and not result.get("interpretation"):
        return f"Orchestrator error: {result['error']}"

    lines = []

    # Interpretation — the main insight
    interpretation = result.get("interpretation", "")
    if interpretation:
        lines.append(f"**Analysis:**\n{interpretation}")
        lines.append("")

    # Key insights
    insights = result.get("key_insights", [])
    if insights:
        lines.append("**Key Insights:**")
        for ins in insights:
            lines.append(f"  • {ins}")
        lines.append("")

    # Recommended actions
    actions = result.get("recommended_actions", [])
    if actions:
        lines.append("**Recommended Actions:**")
        priority_icons = {
            "critical": "🚨",
            "high": "⚠",
            "medium": "📌",
            "low": "💡",
        }
        for a in actions:
            icon = priority_icons.get(a.get("priority", "medium"), "•")
            desc = a.get("description", "?")
            rationale = a.get("rationale", "")
            action_type = a.get("type", "?")
            domain_tag = f" [{a['domain']}]" if a.get("domain") else ""
            lines.append(f"  {icon} [{a.get('priority', '?').upper()}]{domain_tag} {desc}")
            if rationale:
                lines.append(f"     → {rationale}")
        lines.append("")

    # Risks
    risks = result.get("risks", [])
    if risks:
        lines.append("**Risks:**")
        for r in risks:
            lines.append(f"  ⚡ {r}")
        lines.append("")

    # System health
    health = result.get("system_health", "")
    if health:
        health_icons = {
            "healthy": "✓ Healthy",
            "warning": "⚠ Warning",
            "critical": "🚨 Critical",
        }
        lines.append(f"**System Health:** {health_icons.get(health, health)}")

    # Next question
    next_q = result.get("next_question")
    if next_q:
        lines.append(f"\n**Next to investigate:** {next_q}")

    return "\n".join(lines) if lines else "No orchestrator response."
