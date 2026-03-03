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

from config import MODELS, DAILY_BUDGET_USD, LOG_DIR
from llm_router import call_llm
from cost_tracker import log_cost
from utils.json_parser import extract_json


# ── Configuration ────────────────────────────────────────────────────────

ORCHESTRATOR_MODEL = MODELS.get("cortex_orchestrator", "claude-sonnet-4-20250514")
MAX_CONTEXT_CHARS = 12000  # Cap context to avoid blowing up token costs
CORTEX_JOURNAL_FILE = os.path.join(LOG_DIR, "cortex_journal.jsonl")
BUILD_BUDGET_CAP = 0.50  # Max cost per build execution in USD
MAX_BUILD_PHASE_FAILURES = 3  # Escalate after this many failures in same phase


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


# ── Cortex Journal ───────────────────────────────────────────────────────

def _journal(event: str, domain: str, task_id: str = "", details: dict | None = None, cost: float = 0.0):
    """
    Append an entry to cortex_journal.jsonl.
    
    Every significant pipeline event is logged here for observability.
    This is the audit trail for the entire Brain → Cortex → Hands pipeline.
    """
    from protocol import JournalEntry
    
    entry = JournalEntry(
        event=event,
        domain=domain,
        task_id=task_id,
        details=details or {},
        cost_so_far=cost,
    )
    
    try:
        os.makedirs(os.path.dirname(CORTEX_JOURNAL_FILE), exist_ok=True)
        with open(CORTEX_JOURNAL_FILE, "a") as f:
            f.write(entry.to_jsonl() + "\n")
    except Exception:
        pass  # Journal failure should never crash the pipeline


def load_journal(domain: str | None = None, last_n: int = 50) -> list[dict]:
    """
    Load recent journal entries, optionally filtered by domain.
    
    Args:
        domain: Filter to this domain (None = all)
        last_n: Number of recent entries to return
    
    Returns:
        List of journal entry dicts, most recent last.
    """
    if not os.path.exists(CORTEX_JOURNAL_FILE):
        return []
    
    entries = []
    try:
        with open(CORTEX_JOURNAL_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if domain is None or entry.get("domain") == domain:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    
    return entries[-last_n:]


# ── Knowledge Query (Brain → Hands Context Bridge) ──────────────────────

def query_knowledge(domain: str, question: str, max_results: int = 5) -> str:
    """
    Query Brain's knowledge base for context relevant to a build task.
    
    This is the bridge that lets Hands access Brain's research mid-build.
    Returns a formatted text block suitable for injecting into an LLM prompt.
    
    Used by:
    - Hands executor (mid-build context requests)
    - Cortex (to evaluate build-readiness)
    
    Args:
        domain: Domain to query
        question: What context is needed
        max_results: Max number of relevant findings to return
    
    Returns:
        Formatted context string (empty string if nothing found)
    """
    from memory_store import load_knowledge_base, retrieve_relevant
    
    context_parts = []
    
    # 1. Knowledge base claims (highest quality — synthesized + verified)
    kb = load_knowledge_base(domain)
    if kb:
        active_claims = [c for c in kb.get("claims", []) if c.get("status") == "active"]
        if active_claims:
            # Filter claims relevant to the question (simple keyword match)
            question_lower = question.lower()
            question_words = set(question_lower.split())
            
            scored_claims = []
            for claim in active_claims:
                claim_text = claim.get("claim", "").lower()
                # Count word overlap
                claim_words = set(claim_text.split())
                overlap = len(question_words & claim_words)
                if overlap > 0:
                    scored_claims.append((overlap, claim))
            
            scored_claims.sort(key=lambda x: x[0], reverse=True)
            top_claims = [c for _, c in scored_claims[:10]]
            
            if top_claims:
                kb_block = "KNOWLEDGE BASE (verified claims):\n"
                for claim in top_claims:
                    conf = claim.get("confidence", "?")
                    kb_block += f"  [{conf}] {claim.get('claim', '')}\n"
                context_parts.append(kb_block)
        
        # Domain summary is always useful
        if kb.get("domain_summary"):
            context_parts.insert(0, f"DOMAIN SUMMARY: {kb['domain_summary']}\n")
    
    # 2. Relevant past findings (raw research data)
    relevant = retrieve_relevant(domain, question, max_results=max_results)
    if relevant:
        findings_block = "RELEVANT RESEARCH FINDINGS:\n"
        for r in relevant:
            findings_block += f"\n  Q: {r.get('question', '?')} (score: {r.get('score', 0)}/10)\n"
            findings_block += f"  Summary: {r.get('summary', 'N/A')}\n"
            insights = r.get("key_insights", [])
            if insights:
                for ins in insights[:3]:
                    findings_block += f"    • {ins}\n"
        context_parts.append(findings_block)
    
    return "\n".join(context_parts) if context_parts else ""


def is_build_ready(domain: str) -> dict:
    """
    Evaluate whether a domain has enough research to support a build.
    
    Criteria:
    - At least 5 accepted outputs (score ≥ 6)
    - Knowledge base has active claims about user pain, competitors, opportunity
    - A clear user persona can be articulated
    
    Returns:
        {
            "ready": bool,
            "reason": str,
            "accepted_count": int,
            "claim_count": int,
            "has_user_pain": bool,
            "has_competitors": bool,
            "domain_summary": str,
        }
    """
    from memory_store import load_knowledge_base, get_stats
    
    stats = get_stats(domain)
    accepted_count = stats.get("accepted", 0)
    
    kb = load_knowledge_base(domain)
    claim_count = 0
    has_user_pain = False
    has_competitors = False
    domain_summary = ""
    
    if kb:
        active_claims = [c for c in kb.get("claims", []) if c.get("status") == "active"]
        claim_count = len(active_claims)
        domain_summary = kb.get("domain_summary", "")
        
        # Check claim topics for build-readiness signals
        pain_keywords = {"pain", "problem", "frustrat", "complain", "issue", "struggle", "challenge"}
        competitor_keywords = {"competitor", "alternative", "existing", "platform", "service", "pricing"}
        
        for claim in active_claims:
            text = claim.get("claim", "").lower()
            topic = claim.get("topic", "").lower()
            
            if any(k in text or k in topic for k in pain_keywords):
                has_user_pain = True
            if any(k in text or k in topic for k in competitor_keywords):
                has_competitors = True
    
    # Build readiness decision
    reasons = []
    if accepted_count < 5:
        reasons.append(f"Only {accepted_count}/5 accepted outputs")
    if claim_count < 3:
        reasons.append(f"Only {claim_count} active claims in knowledge base")
    if not has_user_pain:
        reasons.append("No claims about user pain/problems found")
    if not has_competitors:
        reasons.append("No claims about competitors/alternatives found")
    
    ready = accepted_count >= 5 and claim_count >= 3 and has_user_pain
    
    return {
        "ready": ready,
        "reason": "Build-ready" if ready else "; ".join(reasons),
        "accepted_count": accepted_count,
        "claim_count": claim_count,
        "has_user_pain": has_user_pain,
        "has_competitors": has_competitors,
        "domain_summary": domain_summary,
    }


def extract_build_brief(domain: str, instruction: str = "") -> str:
    """
    Extract a build brief from Brain's knowledge base for a domain.
    
    Compiles user pain, competitors, and opportunity into a structured
    brief that Hands can use to build a product.
    
    Args:
        domain: Domain to extract brief from
        instruction: Optional specific instruction ("Build a landing page for X")
    
    Returns:
        Build brief text string
    """
    from memory_store import load_knowledge_base
    
    kb = load_knowledge_base(domain)
    if not kb:
        return f"No knowledge base found for domain '{domain}'. Research needed first."
    
    active_claims = [c for c in kb.get("claims", []) if c.get("status") == "active"]
    if not active_claims:
        return f"Knowledge base for '{domain}' has no active claims. More research needed."
    
    # Organize claims by topic
    by_topic: dict[str, list[str]] = {}
    for claim in active_claims:
        topic = claim.get("topic", "General")
        text = claim.get("claim", "")
        conf = claim.get("confidence", "?")
        if text:
            by_topic.setdefault(topic, []).append(f"[{conf}] {text}")
    
    # Build the brief
    brief_parts = []
    
    if instruction:
        brief_parts.append(f"INSTRUCTION: {instruction}\n")
    
    brief_parts.append(f"DOMAIN: {domain}")
    
    if kb.get("domain_summary"):
        brief_parts.append(f"DOMAIN SUMMARY: {kb['domain_summary']}\n")
    
    for topic, claims in by_topic.items():
        brief_parts.append(f"\n{topic.upper()}:")
        for claim in claims[:5]:  # Top 5 per topic
            brief_parts.append(f"  {claim}")
    
    brief_parts.append(f"\nBased on this research, build a solution that addresses the core user pain points.")
    brief_parts.append(f"Use specific language and data from the research in the copy.")
    
    return "\n".join(brief_parts)


# ── Research and Build Pipeline ──────────────────────────────────────────

def research_and_build(
    domain: str,
    instruction: str,
    skip_research: bool = False,
    budget_cap: float = BUILD_BUDGET_CAP,
) -> dict:
    """
    Full pipeline: Cortex → Brain researches → Cortex evaluates → Hands builds.
    
    This is the core pipeline function that turns a domain + instruction into
    a live deployed product.
    
    Args:
        domain: Domain to research and build for
        instruction: What to build ("Build a landing page for a logistics company")
        skip_research: If True, skip Brain research and use existing KB
        budget_cap: Max cost for the Hands build execution
    
    Returns:
        {
            "success": bool,
            "stage": str,  # Where it got to: "research" | "brief" | "task_created" | "complete"
            "research": dict | None,  # Research results
            "build_task": dict | None,  # The BuildTask that was created
            "task_id": str,  # Sync task ID
            "error": str,  # Error message if failed
        }
    """
    from protocol import BuildTask, ResearchComplete, JournalEntry
    from sync import create_task
    
    result = {
        "success": False,
        "stage": "init",
        "research": None,
        "build_task": None,
        "task_id": "",
        "error": "",
    }
    
    _journal("pipeline_start", domain, details={
        "instruction": instruction,
        "skip_research": skip_research,
        "budget_cap": budget_cap,
    })
    
    # Stage 1: Check build readiness or run research
    if not skip_research:
        readiness = is_build_ready(domain)
        
        if not readiness["ready"]:
            print(f"[CORTEX] Domain '{domain}' not build-ready: {readiness['reason']}")
            print(f"[CORTEX] Running Brain research first...")
            
            _journal("research_start", domain, details={
                "reason": readiness["reason"],
                "instruction": instruction,
            })
            
            # Run Brain research loop
            try:
                from main import run_loop
                
                # Frame the research question for build intelligence
                research_question = (
                    f"Research for building: {instruction}. "
                    f"Focus on: Who is the user? What's their #1 pain? "
                    f"Who are the competitors? What do they charge? "
                    f"What would make this product compelling?"
                )
                
                loop_result = run_loop(research_question, domain=domain)
                result["research"] = loop_result
                
                score = loop_result.get("critique", {}).get("overall_score", 0)
                accepted = loop_result.get("critique", {}).get("verdict") == "accept"
                
                _journal("research_complete", domain, details={
                    "score": score,
                    "accepted": accepted,
                    "stored_at": loop_result.get("stored_at", ""),
                })
                
                if not accepted:
                    result["stage"] = "research"
                    result["error"] = f"Research rejected (score: {score}/10). Need better research before building."
                    _journal("pipeline_blocked", domain, details={
                        "reason": "research_rejected",
                        "score": score,
                    })
                    return result
                    
            except SystemExit:
                result["stage"] = "research"
                result["error"] = "Budget exceeded — cannot run research"
                _journal("pipeline_blocked", domain, details={"reason": "budget_exceeded"})
                return result
            except Exception as e:
                result["stage"] = "research"
                result["error"] = f"Research failed: {e}"
                _journal("pipeline_error", domain, details={"error": str(e)})
                return result
        else:
            print(f"[CORTEX] Domain '{domain}' is build-ready ({readiness['accepted_count']} outputs, {readiness['claim_count']} claims)")
    else:
        print(f"[CORTEX] Skipping research (skip_research=True)")
    
    # Stage 2: Extract build brief from knowledge base
    result["stage"] = "brief"
    brief = extract_build_brief(domain, instruction)
    
    if brief.startswith("No knowledge base") or brief.startswith("Knowledge base for"):
        result["error"] = brief
        _journal("pipeline_blocked", domain, details={"reason": "no_knowledge_base", "brief": brief})
        return result
    
    print(f"[CORTEX] Build brief extracted ({len(brief)} chars)")
    
    # Stage 3: Create BuildTask and insert into sync queue
    result["stage"] = "task_created"
    
    build_task = BuildTask(
        domain=domain,
        goal=instruction,
        brief=brief,
        constraints={
            "tech_stack": ["nextjs", "tailwind", "shadcn-ui", "framer-motion"],
            "deploy_to": "vercel",
            "design_system": "identity/design_system.md",
        },
        budget_cap=budget_cap,
        priority="high",
    )
    
    # Insert into sync queue
    sync_task = create_task(**build_task.to_sync_task())
    task_id = sync_task["id"]
    result["task_id"] = task_id
    result["build_task"] = build_task.to_dict()
    
    _journal("build_task_created", domain, task_id=task_id, details={
        "goal": instruction,
        "brief_length": len(brief),
        "budget_cap": budget_cap,
    })
    
    print(f"[CORTEX] Build task created: {task_id}")
    print(f"[CORTEX] Task queued for Hands execution (priority: high)")
    print(f"[CORTEX] The daemon will pick this up, or run manually:")
    print(f"  python -m cli.execution run {task_id}")
    
    result["success"] = True
    return result


# ── Build Monitor ────────────────────────────────────────────────────────

def monitor_build(task_id: str, domain: str) -> dict:
    """
    Monitor an active build's progress. Called periodically during execution.
    
    Checks:
    - Cost vs budget cap
    - Phase progress
    - Repeated failures in same phase
    
    Returns:
        {
            "status": "continue" | "warn" | "abort",
            "reason": str,
            "phase_failures": int,
            "cost_so_far": float,
        }
    """
    # Read journal entries for this task
    entries = load_journal(domain)
    task_entries = [e for e in entries if e.get("task_id") == task_id]
    
    if not task_entries:
        return {"status": "continue", "reason": "No journal entries yet", "phase_failures": 0, "cost_so_far": 0}
    
    # Calculate cost
    cost_so_far = max((e.get("cost_so_far", 0) for e in task_entries), default=0)
    
    # Count phase failures
    phase_failures: dict[str, int] = {}
    for entry in task_entries:
        if entry.get("event") == "phase_failed":
            phase = entry.get("details", {}).get("phase", "unknown")
            phase_failures[phase] = phase_failures.get(phase, 0) + 1
    
    max_failures = max(phase_failures.values(), default=0)
    
    # Decision
    if cost_so_far > BUILD_BUDGET_CAP:
        _journal("cost_alert", domain, task_id=task_id, cost=cost_so_far, details={
            "budget_cap": BUILD_BUDGET_CAP,
        })
        return {
            "status": "abort",
            "reason": f"Cost ${cost_so_far:.4f} exceeds budget cap ${BUILD_BUDGET_CAP}",
            "phase_failures": max_failures,
            "cost_so_far": cost_so_far,
        }
    
    if max_failures >= MAX_BUILD_PHASE_FAILURES:
        failed_phase = max(phase_failures, key=phase_failures.get)
        _journal("intervention", domain, task_id=task_id, details={
            "reason": "repeated_phase_failure",
            "phase": failed_phase,
            "failure_count": max_failures,
        })
        return {
            "status": "abort",
            "reason": f"Phase '{failed_phase}' failed {max_failures}x — escalating",
            "phase_failures": max_failures,
            "cost_so_far": cost_so_far,
        }
    
    if cost_so_far > BUILD_BUDGET_CAP * 0.8:
        return {
            "status": "warn",
            "reason": f"Cost ${cost_so_far:.4f} approaching budget cap ${BUILD_BUDGET_CAP}",
            "phase_failures": max_failures,
            "cost_so_far": cost_so_far,
        }
    
    return {
        "status": "continue",
        "reason": "Within budget, no repeated failures",
        "phase_failures": max_failures,
        "cost_so_far": cost_so_far,
    }


def report_build_complete(
    domain: str,
    task_id: str,
    success: bool,
    url: str = "",
    total_cost: float = 0.0,
    total_steps: int = 0,
    error: str = "",
) -> dict:
    """
    Report a build completion through the pipeline.
    
    Logs to journal, updates sync task, and formats a Telegram notification.
    
    Returns:
        TaskComplete message dict
    """
    from protocol import TaskComplete, BuildComplete, BuildFailed
    from sync import update_task
    
    if success:
        msg = BuildComplete(
            domain=domain,
            task_id=task_id,
            url=url,
            total_cost=total_cost,
            total_steps=total_steps,
        )
        _journal("build_complete", domain, task_id=task_id, cost=total_cost, details={
            "url": url,
            "total_steps": total_steps,
        })
        update_task(task_id, "completed", {"url": url, "cost": total_cost})
    else:
        msg = BuildFailed(
            domain=domain,
            task_id=task_id,
            phase="unknown",
            reason=error,
            cost_so_far=total_cost,
        )
        _journal("build_failed", domain, task_id=task_id, cost=total_cost, details={
            "error": error,
        })
        update_task(task_id, "failed", {"error": error, "cost": total_cost})
    
    # Create summary for Telegram
    task_complete = TaskComplete(
        domain=domain,
        task_id=task_id,
        result="success" if success else "failed",
        url=url,
        cost=total_cost,
        summary=f"{'Built and deployed' if success else 'Build failed'}: {domain}",
    )
    
    # Try to send Telegram notification
    try:
        _send_telegram_notification(task_complete)
    except Exception:
        pass  # Don't crash on notification failure
    
    return task_complete.to_dict()


def _send_telegram_notification(task_complete):
    """Send a pipeline completion notification via Telegram."""
    try:
        from alerts import alert_custom
        message = task_complete.to_telegram_message()
        emoji = "✅" if task_complete.result == "success" else "❌"
        alert_custom(f"Build {task_complete.result.upper()}", message, emoji=emoji)
    except Exception:
        pass
