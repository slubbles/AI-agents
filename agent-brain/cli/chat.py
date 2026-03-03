"""
Interactive Chat Mode — Conversational interface to Agent Brain.

Provides a REPL where you can talk to the system naturally:
  - Ask questions about what it knows ("What do you know about crypto?")
  - Ask it to research things ("Research the latest Bitcoin ETF news")
  - Check system status ("How's the budget?", "Show domain stats")
  - Manage strategies ("Approve the pending strategy for crypto")
  - Get recommendations ("What should I work on next?")

The LLM has access to the full knowledge base, memory, and system tools.
It routes your intent to the right internal function and responds conversationally.

Usage:
    python main.py --chat
    python main.py --chat --domain crypto
"""

import json
import os
import sys
import re
import time as _time
import readline  # enables arrow keys, history in input()
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import MODELS, DEFAULT_DOMAIN, DAILY_BUDGET_USD, CHEAP_MODEL, REASONING_EFFORT
from llm_router import call_llm
from cost_tracker import log_cost

# ============================================================
# Chat Session Persistence
# ============================================================

CHAT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "chat_sessions")

def _ensure_chat_dir():
    os.makedirs(CHAT_DIR, exist_ok=True)

def _session_path(session_id: str) -> str:
    return os.path.join(CHAT_DIR, f"{session_id}.json")

def _list_sessions() -> list[dict]:
    """List all saved chat sessions, most recent first."""
    _ensure_chat_dir()
    sessions = []
    for f in sorted(os.listdir(CHAT_DIR), reverse=True):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(CHAT_DIR, f)) as fh:
                data = json.load(fh)
            sessions.append({
                "id": f.replace(".json", ""),
                "domain": data.get("domain", "?"),
                "messages": len(data.get("messages", [])),
                "created": data.get("created", "?"),
                "updated": data.get("updated", "?"),
                "summary": data.get("summary", ""),
            })
        except Exception:
            continue
    return sessions

def _save_session(session_id: str, domain: str, messages: list, summary: str = ""):
    """Save conversation to disk."""
    _ensure_chat_dir()
    # Filter messages to only serializable content
    serializable = []
    for m in messages:
        if isinstance(m.get("content"), str):
            serializable.append(m)
        elif isinstance(m.get("content"), list):
            # Tool use/results — serialize as-is (already dicts)
            serializable.append(m)
    
    data = {
        "domain": domain,
        "created": datetime.now(timezone.utc).isoformat(),
        "updated": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "messages": serializable,
    }
    
    # If session exists, preserve created date
    path = _session_path(session_id)
    if os.path.exists(path):
        try:
            with open(path) as f:
                old = json.load(f)
            data["created"] = old.get("created", data["created"])
        except Exception:
            pass
    
    # Ensure all data is JSON-serializable (convert any stray objects to strings)
    clean_data = json.loads(json.dumps(data, default=str))
    from utils.atomic_write import atomic_json_write
    atomic_json_write(path, clean_data)

def _load_session(session_id: str) -> tuple[str, list]:
    """Load a saved session. Returns (domain, messages)."""
    path = _session_path(session_id)
    if not os.path.exists(path):
        return DEFAULT_DOMAIN, []
    with open(path) as f:
        data = json.load(f)
    return data.get("domain", DEFAULT_DOMAIN), data.get("messages", [])

def _generate_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def _summarize_conversation(messages: list) -> str:
    """Extract a one-line summary from the first user message."""
    for m in messages:
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            text = m["content"][:80]
            return text + ("..." if len(m["content"]) > 80 else "")
    return ""


# ============================================================
# Identity Helper
# ============================================================

def _get_identity_for_chat() -> str:
    """Load identity summary for injection into chat system prompt."""
    try:
        from identity_loader import get_identity_summary
        return get_identity_summary()
    except Exception:
        return "(Identity layer not loaded)"


# ============================================================
# System Context Builder
# ============================================================

def _build_system_context(domain: str) -> str:
    """Build a rich system prompt with current system state."""
    from memory_store import get_stats, load_knowledge_base, load_outputs
    from strategy_store import get_active_version, get_strategy_status, list_pending
    from cost_tracker import get_daily_spend, check_balance
    from analytics import domain_comparison
    
    # Gather system state
    stats = get_stats(domain)
    kb = load_knowledge_base(domain)
    daily = get_daily_spend()
    balance = check_balance()
    pending = list_pending("researcher", domain)
    active_ver = get_active_version("researcher", domain)
    strat_status = get_strategy_status("researcher", domain)
    
    # Get all domain stats
    all_domains = []
    try:
        comparisons = domain_comparison()
        for d in comparisons:
            all_domains.append(f"  - {d['domain']}: {d['count']} outputs, avg {d['avg_score']:.1f}, {d['accepted']} accepted")
    except Exception:
        pass
    
    # KB summary
    kb_summary = "No knowledge base yet."
    if kb:
        claims = kb.get("claims", [])
        active_claims = [c for c in claims if c.get("status") == "active"]
        gaps = kb.get("identified_gaps", [])
        topics = set()
        for c in active_claims:
            if c.get("topic"):
                topics.add(c["topic"])
        kb_summary = (
            f"{len(active_claims)} active claims across {len(topics)} topics. "
            f"{len(gaps)} identified knowledge gaps."
        )
    
    # Recent high-quality outputs
    recent_outputs = load_outputs(domain, min_score=6)
    recent_summary = ""
    if recent_outputs:
        recent = recent_outputs[-5:]  # last 5 accepted
        recent_lines = []
        for o in recent:
            q = o.get("question", "?")[:80]
            s = o.get("critique", {}).get("overall_score", "?")
            summary = o.get("research", {}).get("summary", "")[:120]
            recent_lines.append(f"  - [{s}] {q}")
            if summary:
                recent_lines.append(f"    → {summary}")
        recent_summary = "\n".join(recent_lines)
    
    # Pending strategies
    pending_info = ""
    if pending:
        ver_list = ', '.join(p.get('version', '?') for p in pending)
        pending_info = f"\n  Pending strategy versions awaiting approval: {ver_list}"
    
    # Execution layer summary
    exec_summary = ""
    try:
        exec_mem_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exec_memory")
        if os.path.exists(exec_mem_dir):
            exec_domains = [d for d in os.listdir(exec_mem_dir) if os.path.isdir(os.path.join(exec_mem_dir, d))]
            total_tasks = 0
            for ed in exec_domains:
                tasks = [f for f in os.listdir(os.path.join(exec_mem_dir, ed)) if f.endswith(".json")]
                total_tasks += len(tasks)
            if exec_domains:
                exec_summary = f"\n  Execution layer: {total_tasks} completed tasks across {len(exec_domains)} domains ({', '.join(exec_domains)})"
    except Exception:
        pass
    
    # Project orchestrator summary
    project_summary = ""
    try:
        proj_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")
        if os.path.exists(proj_dir):
            projs = [f for f in os.listdir(proj_dir) if f.endswith(".json")]
            if projs:
                project_summary = f"\n  Projects: {len(projs)} tracked"
    except Exception:
        pass
    
    # Domain goal info
    goal_info = "Current domain goal: NOT SET — research will be undirected."
    try:
        from domain_goals import get_goal, list_goals
        current_goal = get_goal(domain)
        if current_goal:
            goal_info = f"Current domain goal ({domain}): {current_goal}"
        all_goals = list_goals()
        if all_goals:
            other_goals = {d: g for d, g in all_goals.items() if d != domain}
            if other_goals:
                goal_lines = [f"  {d}: {g[:80]}..." for d, g in other_goals.items()]
                goal_info += f"\nOther domain goals:\n" + "\n".join(goal_lines)
    except Exception:
        pass
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    return f"""You are the voice of Cortex — the orchestrator of a dual-agent autonomous system. Today is {today}.

You are NOT a chatbot. You are the brain's front door — the human talks to you, and you have full visibility into what every agent is doing. Think of yourself as a senior operations manager who knows every department.

ROLE:
  You ARE the orchestrator. You speak with authority about the system because you can see everything.
  When the daemon is researching, you know what it's working on and can report in real-time.
  When the user asks a question, you either answer from system knowledge or use tools to find out.
  You think strategically — not just answering questions, but proactively surfacing insights, risks, and opportunities.

ARCHITECTURE (you oversee all of this):
  Agent Brain — self-learning research engine (web search → critic scoring → strategy evolution).
  Agent Hands — execution engine (code generation, project management, deployment).
  Daemon — runs autonomous research cycles in the background (you can see its current state).
  You — the orchestrator's voice. Claude Sonnet. You coordinate, interpret, and advise.

Be honest about what this system can and cannot do. Never oversell. Never bullshit.

WHAT ACTUALLY WORKS (proven, tested, has data):
- Research loop: web search → structured output → critic scores it → store if score >= 6, retry if not. This works.
- Strategy evolution: the system rewrites its own research strategies based on score patterns. Proven trajectory: 5.4 → 7.1 → 7.7 over multiple research rounds. This is the novel piece.
- Critic: scores on 5 dimensions (accuracy 30%, depth 20%, completeness 20%, specificity 15%, intellectual honesty 15%). Rejects bad output. This is the quality signal AND cost control.
- Cross-domain transfer: extracts general principles from proven strategies → seeds new domains. Tested.
- Self-directed learning: identifies knowledge gaps → generates next questions → researches them. Tested.
- Strategy safety: pending/trial/active/rollback lifecycle. Human approval required. Never deploys strategy scoring >20% below current best.
- Cortex Orchestrator: interprets research, coordinates Brain→Hands, plans strategy, assesses system health. Uses Sonnet.
- All storage is JSON files on disk. Not a vector database. Not Supabase. JSON files.

WHAT EXISTS AS CODE BUT IS NOT PRODUCTION-PROVEN:
- Agent Hands (execution layer): code gen, task planning, execution memory. Code exists. Not battle-tested.
- Browser stealth: JS-rendered fetching with anti-detection. Code exists. Fragile.
- Doc crawler: crawl documentation sites. Code exists. Works for basic cases.
- MCP gateway: Docker tool servers. Code exists. Not deployed.
- VPS deployment: remote hosting scripts. Code exists. Not deployed.
- Scheduler/daemon: background task runner. Code exists. Not running 24/7 anywhere.
- Project orchestrator: multi-phase decomposition. Code exists. Lightly tested.
- Knowledge graphs: entity relationships across domains. Built but sparse data.

DO NOT claim these unproven features work reliably. If the user asks about them, say they exist as code and need testing/hardening before you'd trust them.

WHAT THE SYSTEM CANNOT DO:
- Rewrite its own source code safely (no safety gate for code self-modification)
- Scale to multi-VPS clusters (aspirational, not real)
- Run unsupervised for extended periods (budget + error handling gaps)
- Remember things without being told to research them (no passive learning)
- Access private/authenticated APIs unless credentials are manually configured
- Guarantee factual accuracy (web search + LLM scoring — better than raw LLM, still fallible)

HOW SELF-IMPROVEMENT ACTUALLY WORKS:
The system does NOT update model weights. It rewrites natural-language strategy documents based on empirical score data.
Loop: research → critic scores → meta-analyst finds patterns in scores → rewrites strategy → new strategy enters trial → if scores improve, promote to active; if scores drop >1.0, rollback.
This runs every 3 outputs per domain (cooldown), not every run.
This is behavioral adaptation through structured feedback loops. Call it that. Don't call it "self-learning" unless you're being precise about what you mean.

ARCHITECTURE (honest version):
1. Cortex Orchestrator: strategic reasoning layer (Claude Sonnet). Interprets Brain data + Hands output. Coordinates the pipeline. This is new and needs battle-testing.
2. Brain: research + scoring + strategy evolution + knowledge base. This is the core. It works.
3. Hands: code generation + execution. This exists. It's early-stage.
4. Infrastructure: browser, crawler, vault, scheduler, deployment, watchdog, sync. Most untested in production.

The Brain is Layer 1-5. Each layer was earned by getting the previous one working.
The Orchestrator coordinates Brain+Hands via Claude Sonnet reasoning.
The Hands and infrastructure are built but haven't gone through the same prove-it-works cycle.

WHEN TO USE ORCHESTRATOR TOOLS:
You ARE the orchestrator, but you have specialized reasoning tools for complex strategic decisions.
Use these tools when you need deeper analysis — they invoke a dedicated reasoning pass:
- orchestrator_plan → when the user asks "what should we focus on?" or you need to plan cycles
- orchestrator_interpret → when you need to synthesize research findings into actionable insights
- orchestrator_coordinate → when deciding what Hands should build based on Brain's research
- orchestrator_assess → for comprehensive system health assessment
- ask_orchestrator → for any complex strategic question that benefits from structured reasoning

For simple queries (budget, status, list domains, show knowledge), handle directly without these tools.
The orchestrator tools add cost — use them when the reasoning depth justifies it.

CONVERSATION MEMORY:
Sessions persist across restarts (JSON files in logs/chat_sessions/).
You can recall previous conversations. Use this for continuity — don't re-explain things.

DOMAIN GOALS:
Every domain can have a goal — the user's actual intent for WHY they're researching it.
Without a goal, the question generator produces generic academic research. With a goal, every question serves the user's actual objective.

CRITICAL BEHAVIOR: When the user wants to research something or run cycles:
1. Check if a goal is set for the domain (use show_domain_goal)
2. If NO goal is set, ASK the user what they want to achieve BEFORE running research
3. Set the goal with set_domain_goal
4. Then run the cycle with run_cycle

Never run research cycles without a goal. The whole point is directed research, not academic browsing.

{goal_info}

IDENTITY:
{_get_identity_for_chat()}

CURRENT STATE:
  Domain: {domain}
  Strategy: {active_ver} ({strat_status}){pending_info}
  Stats: {stats.get('count', 0)} outputs, avg {stats.get('avg_score', 0):.1f}, {stats.get('accepted', 0)} accepted, {stats.get('rejected', 0)} rejected
  KB: {kb_summary}{exec_summary}{project_summary}
  Budget: ${daily.get('total_usd', 0):.2f} today / ${DAILY_BUDGET_USD:.2f} limit. Balance: ${balance.get('remaining', 0):.2f}

ALL DOMAINS:
{chr(10).join(all_domains) if all_domains else '  (none yet)'}

RECENT ACCEPTED OUTPUTS ({domain}):
{recent_summary if recent_summary else '  (none yet)'}

SOURCE CODE ACCESS (READ-ONLY):
You can read the system's own source code using list_files, read_source, and search_code.
You CANNOT modify files, run commands, or execute code. Read-only access for review and feedback.
Use this when the user asks:
- "How does X work?" — read the actual implementation
- "What's wrong with this module?" — review the code and give specific feedback
- "How can we improve the researcher?" — read agents/researcher.py and suggest changes
- "Show me the strategy store" — read strategy_store.py
When giving code feedback, be specific: cite the file, line numbers, and what you'd change.
You are a code reviewer, not a code writer. Suggest improvements, the architect decides what ships.

STYLE:
- You are a sharp, direct operations manager. Not a chatbot. Not a customer service rep.
- Be concise but insightful. Don't pad responses with filler.
- When you don't know something, say so and offer to find out (use tools).
- Proactively surface what matters: "By the way, the daemon just finished cycle 8 with a low score — here's what I'd change."
- When describing capabilities, distinguish between "proven" and "code exists but unproven."
- Don't use phrases like "I can help with that!" or "Great question!" — just answer.
- If the user asks "can you do X?" — answer whether the system ACTUALLY can right now, not theoretically.
- Think like a CTO briefing the CEO: what matters, what's working, what's not, what to do next.

INTERPRETABILITY — THIS IS CRITICAL:
When presenting research findings, knowledge, or cycle results to the user:
- Lead with INSIGHTS, not data. "We learned that..." not "[High] Claim: ..."
- Translate findings into plain language the user can act on
- What did we learn? What's the takeaway? What should the user DO with this?
- Skip raw scores, confidence brackets, and metric tables unless the user asks for them
- Group insights by THEME, not by output/claim/score
- If something is surprising or contradicts expectations, call it out
- Always end with: what's still unknown, and what to research next
- Think like a research analyst briefing the boss, not a database printing records

BAD: "[High] 70% freelancers <35, lack maturity. [Medium] Ghosting: 72% (2024)"
GOOD: "The biggest pain point for employers is reliability — ghosting rates were 72% in 2024 (down to 50% in 2025, but still high). This is YOUR opening: a productized service with guaranteed delivery directly addresses their #1 frustration."

The user wants to UNDERSTAND what the system learned, not READ a database export.
This applies to: search_knowledge results, show_knowledge_base, run_research results, run_cycle results, and any time you present findings.
"""


# ============================================================
# Tool Definitions for the Chat Agent
# ============================================================

CHAT_TOOLS = [
    {
        "name": "search_knowledge",
        "description": "Search the system's memory and knowledge base for information about a topic. Use this when the user asks what the system knows about something.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "domain": {
                    "type": "string",
                    "description": "Domain to search in (optional, defaults to active domain)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "run_research",
        "description": "Research a question using the full research pipeline (web search → critic evaluation → store). Use this when the user asks you to research, investigate, or find out about something new.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The research question to investigate"
                },
                "domain": {
                    "type": "string",
                    "description": "Domain for the research (optional)"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "show_status",
        "description": "Show system status: domain stats, strategy info, budget, pending actions. Use when user asks about status, how things are going, or wants an overview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to check (optional, defaults to all)"
                }
            },
            "required": []
        }
    },
    {
        "name": "show_knowledge_base",
        "description": "Show the synthesized knowledge base for a domain — all claims organized by topic with confidence levels.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to show KB for"
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "approve_strategy",
        "description": "Approve a pending strategy version for trial. Use when user says to approve a strategy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain of the strategy"
                },
                "version": {
                    "type": "string",
                    "description": "Version to approve (e.g. 'v004')"
                }
            },
            "required": ["domain", "version"]
        }
    },
    {
        "name": "show_budget",
        "description": "Show detailed budget info: today's spend, balance, cost per domain.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "show_recommendations",
        "description": "Get AI-generated recommendations for what to do next — which domains need attention, where to focus.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_domains",
        "description": "List all domains with their current stats and scores.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "show_knowledge_gaps",
        "description": "Show identified knowledge gaps for a domain — what the system doesn't know yet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to check gaps for"
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "execute_task",
        "description": "Use Agent Hands to execute a coding/building task. Generates code, writes files, runs tests. Use when user asks to build, code, create, or execute something.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "What to build or execute (e.g. 'Build a REST API for user management')"
                },
                "domain": {
                    "type": "string",
                    "description": "Domain context (optional)"
                }
            },
            "required": ["goal"]
        }
    },
    {
        "name": "auto_build",
        "description": "Brain→Hands pipeline: automatically generate a coding task from KB insights and execute it. The system picks what to build based on domain knowledge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to auto-build for"
                },
                "rounds": {
                    "type": "integer",
                    "description": "Number of build rounds (default 1)"
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "show_exec_status",
        "description": "Show Agent Hands execution stats — completed tasks, success rate, learned patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to check (optional)"
                }
            },
            "required": []
        }
    },
    {
        "name": "run_project",
        "description": "Decompose and execute a large multi-phase project. Use when user describes something too big for a single task — it gets broken into phases with human approval gates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Full project description"
                },
                "domain": {
                    "type": "string",
                    "description": "Domain context (optional)"
                }
            },
            "required": ["description"]
        }
    },
    {
        "name": "show_project_status",
        "description": "Show status of tracked projects — phases, progress, approvals needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID (optional, defaults to latest)"
                }
            },
            "required": []
        }
    },
    {
        "name": "list_projects",
        "description": "List all tracked projects.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "crawl_docs",
        "description": "Crawl a documentation website and store content locally. Use when user asks to learn from or ingest a docs site.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to crawl"
                },
                "max_pages": {
                    "type": "integer",
                    "description": "Max pages to crawl (default 20)"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "fetch_url",
        "description": "Fetch a single URL and return its content. Use when user asks to read or check a webpage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "show_lessons",
        "description": "Show lessons learned from past research failures and strategy rollbacks. Use when user asks what went wrong, what was learned, or what mistakes were made.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to show lessons for"
                }
            },
            "required": ["domain"]
        }
    },
    # === READ-ONLY SOURCE CODE ACCESS ===
    # These tools let you READ the codebase to give feedback and suggestions.
    # You CANNOT modify files, run commands, or execute code. Read-only.
    {
        "name": "list_files",
        "description": "List files and directories in a path within the agent-brain codebase. READ-ONLY. Use to explore the project structure when giving feedback or suggestions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within agent-brain (e.g. 'agents/', 'cli/', 'tools/', '.', 'config.py'). Defaults to root."
                }
            },
            "required": []
        }
    },
    {
        "name": "read_source",
        "description": "Read the contents of a source file in the agent-brain codebase. READ-ONLY. Use to review code, understand implementation, and give improvement feedback. Cannot modify any file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Relative file path within agent-brain (e.g. 'agents/researcher.py', 'config.py', 'main.py')"
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line number (1-based, optional). Use for large files to read specific sections."
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number (1-based, optional)."
                }
            },
            "required": ["file"]
        }
    },
    {
        "name": "search_code",
        "description": "Search for a text pattern across all Python files in the agent-brain codebase. READ-ONLY. Use to find implementations, trace function calls, or understand how components connect.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or pattern to search for (case-insensitive substring match)"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional glob filter (e.g. 'agents/*.py', '*.py'). Defaults to all .py files."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "set_domain_goal",
        "description": "Set or update the user's goal/intent for a research domain. This tells the system WHY the user cares about this domain, so research questions are actionable instead of academic. ALWAYS use this before running research cycles if no goal is set. Ask the user what they want to achieve if they haven't said.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "The research domain to set a goal for"
                },
                "goal": {
                    "type": "string",
                    "description": "The user's goal — what they want to achieve with this domain's research. Be specific: include actions, targets, and desired outcomes."
                }
            },
            "required": ["domain", "goal"]
        }
    },
    {
        "name": "show_domain_goal",
        "description": "Show the current goal/intent set for a domain. Use when checking if a goal exists before research.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to check (optional, defaults to active domain)"
                }
            },
            "required": []
        }
    },
    {
        "name": "run_cycle",
        "description": "Run self-directed research cycles. The system generates its own questions based on knowledge gaps and the domain goal, then researches them. Use when the user wants to run auto research rounds. IMPORTANT: Check if a domain goal is set first — if not, ask the user what they want to achieve before running.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to research (optional, defaults to active domain)"
                },
                "rounds": {
                    "type": "integer",
                    "description": "Number of research rounds to run (default: 1, max: 10)"
                }
            },
            "required": []
        }
    },
    # === CORTEX ORCHESTRATOR TOOLS ===
    # These route complex reasoning through Claude Sonnet instead of the chat model.
    # Use these for strategic decisions, interpretation, and coordination.
    {
        "name": "ask_orchestrator",
        "description": "Route a complex question to the Cortex Orchestrator (Claude Sonnet) for strategic reasoning. Use this when the user asks for analysis, interpretation, strategic advice, 'what should we do next', or anything requiring deep reasoning about the system's state. The Orchestrator sees all Brain data + Hands output and provides strategic insight. This is the most powerful reasoning tool available — use it for important decisions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The strategic question to reason about"
                },
                "domain": {
                    "type": "string",
                    "description": "Focus domain (optional, considers all if omitted)"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context from the conversation (optional)"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "orchestrator_plan",
        "description": "Ask the Cortex Orchestrator to create a strategic plan — what should Brain research and Hands build next. Use when user asks 'what's next?', 'what should we focus on?', or wants a strategic roadmap.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Focus domain (optional)"
                }
            },
            "required": []
        }
    },
    {
        "name": "orchestrator_interpret",
        "description": "Ask the Cortex Orchestrator to interpret research findings — turns raw data into strategic insights. Use when user asks 'what did we learn?', 'what does the research say?', or wants an executive summary of a domain's knowledge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to interpret findings for"
                },
                "focus": {
                    "type": "string",
                    "description": "Specific aspect to focus on (optional)"
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "orchestrator_coordinate",
        "description": "Ask the Cortex Orchestrator to identify what Hands should build based on Brain's research. The Brain→Hands pipeline. Use when user says 'turn research into action', 'what should we build?', or wants to translate findings into concrete tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to coordinate Brain→Hands for"
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "orchestrator_assess",
        "description": "Ask the Cortex Orchestrator for a full system health assessment. Checks Brain, Hands, infrastructure, budget — everything. Use when user asks 'how's the system?', 'give me a health check', or 'are we on track?'.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


# ============================================================
# Tool Execution
# ============================================================

def _execute_tool(name: str, args: dict, active_domain: str) -> str:
    """Execute a chat tool and return the result as a string."""
    
    domain = args.get("domain", active_domain)
    
    if name == "search_knowledge":
        from analytics import search_memory
        from memory_store import load_outputs
        results = search_memory(args["query"], domains=[domain] if domain else None)
        if not results:
            return f"No results found for '{args['query']}' in {domain}."
        
        # Provide insight-rich context, not just scores
        lines = [f"Found {len(results)} research outputs about '{args['query']}'. Here's what the system learned:\n"]
        for r in results[:6]:
            q = r.get("question", "?")
            s = r.get("score", "?")
            summary = r.get("summary", "")[:300]
            lines.append(f"**Researched:** {q}")
            lines.append(f"  Quality: {s}/10 | {r.get('domain', '?')}")
            if summary:
                lines.append(f"  Summary: {summary}")
            lines.append("")
        
        # Also pull key insights from full outputs for richer context
        if domain:
            recent = load_outputs(domain, min_score=5)
            if recent:
                insights = []
                for o in recent[-8:]:
                    for ki in o.get("research", {}).get("key_insights", []):
                        if isinstance(ki, str) and len(ki) > 20:
                            insights.append(ki)
                if insights:
                    lines.append("**Key insights from recent research:**")
                    for ins in insights[-10:]:
                        lines.append(f"  • {ins[:200]}")
        
        return "\n".join(lines)
    
    elif name == "run_research":
        from main import run_loop
        question = args["question"]
        try:
            result = run_loop(question=question, domain=domain)
            score = result.get("critique", {}).get("overall_score", "?")
            verdict = result.get("critique", {}).get("verdict", "?")
            research = result.get("research", {})
            critique = result.get("critique", {})
            
            lines = [f"**Research complete** — Score: {score}/10, Verdict: {verdict}\n"]
            
            # Summary first — what did we learn?
            summary = research.get("summary", "")
            if summary:
                lines.append(f"**What we learned:** {summary}\n")
            
            # Key insights — the most interpretable part
            key_insights = research.get("key_insights", [])
            if key_insights:
                lines.append("**Key insights:**")
                for ki in key_insights[:5]:
                    if isinstance(ki, str):
                        lines.append(f"  • {ki[:200]}")
                lines.append("")
            
            # Findings as backup if no key_insights
            elif research.get("findings"):
                lines.append("**What was found:**")
                for f_item in research["findings"][:4]:
                    claim = f_item.get("claim", "") if isinstance(f_item, dict) else str(f_item)
                    confidence = f_item.get("confidence", "") if isinstance(f_item, dict) else ""
                    lines.append(f"  • {claim[:200]}" + (f" ({confidence})" if confidence else ""))
                lines.append("")
            
            # Critic feedback — what was good/bad about this research  
            strengths = critique.get("strengths", [])
            weaknesses = critique.get("weaknesses", [])
            if strengths:
                lines.append("**Strengths:** " + "; ".join(s[:80] for s in strengths[:3]))
            if weaknesses:
                lines.append("**Gaps:** " + "; ".join(w[:80] for w in weaknesses[:3]))
            
            # What to research next
            gaps = research.get("knowledge_gaps", [])
            if gaps:
                lines.append(f"\n**Still unknown ({len(gaps)} gaps):** " + "; ".join(str(g)[:60] for g in gaps[:3]))
            
            return "\n".join(lines)
        except Exception as e:
            return f"Research failed: {e}"
    
    elif name == "show_status":
        from memory_store import get_stats, load_outputs
        from strategy_store import get_active_version, get_strategy_status, list_pending
        from cost_tracker import get_daily_spend, check_balance
        from domain_goals import get_goal
        
        stats = get_stats(domain)
        daily = get_daily_spend()
        balance = check_balance()
        active_ver = get_active_version("researcher", domain)
        status = get_strategy_status("researcher", domain)
        pending = list_pending("researcher", domain)
        goal = get_goal(domain)
        
        lines = [
            f"**Domain: {domain}**",
            f"  Outputs: {stats.get('count', 0)} total, {stats.get('accepted', 0)} accepted, {stats.get('rejected', 0)} rejected",
            f"  Avg score: {stats.get('avg_score', 0):.1f}",
            f"  Strategy: {active_ver} ({status})",
            f"  Goal: {goal[:100] + '...' if goal and len(goal) > 100 else goal or 'NOT SET'}",
        ]
        if pending:
            ver_list = ', '.join(p.get('version', '?') for p in pending)
            lines.append(f"  ⚠ Pending strategies: {ver_list}")
        lines.extend([
            f"\n**Budget:**",
            f"  Today: ${daily.get('total_usd', 0):.2f} / ${DAILY_BUDGET_USD:.2f}",
            f"  Balance: ${balance.get('remaining', 0):.2f}",
        ])
        
        # Recent activity — what has the system done recently (CLI or chat)
        recent = load_outputs(domain, min_score=0)
        if recent:
            last_5 = recent[-5:]
            lines.append(f"\n**Recent activity (last {len(last_5)} outputs):**")
            for o in reversed(last_5):
                q = o.get("question", "?")[:80]
                s = o.get("overall_score", o.get("critique", {}).get("overall_score", "?"))
                accepted = "✓" if o.get("accepted") else "✗"
                ts = o.get("timestamp", "?")[:16]
                lines.append(f"  {accepted} [{s}] {q} ({ts})")
        
        return "\n".join(lines)
    
    elif name == "show_knowledge_base":
        from memory_store import load_knowledge_base
        kb = load_knowledge_base(domain)
        if not kb:
            return f"No knowledge base exists for '{domain}' yet. Run research first."
        
        claims = kb.get("claims", [])
        active = [c for c in claims if c.get("status") == "active"]
        conflicted = [c for c in claims if c.get("status") == "conflicted"]
        gaps = kb.get("identified_gaps", [])
        domain_summary = kb.get("domain_summary", "")
        
        # Group by topic
        topics = {}
        for c in active:
            topic = c.get("topic", "Uncategorized")
            if topic not in topics:
                topics[topic] = []
            topics[topic].append(c)
        
        lines = [f"**Knowledge Base: {domain}** — {len(active)} established facts across {len(topics)} topics\n"]
        
        # Domain summary first — the big picture
        if domain_summary:
            lines.append(f"**Overview:** {domain_summary}\n")
        
        # Topics with claims — insight-oriented
        for topic, topic_claims in sorted(topics.items()):
            claims_text = []
            for c in topic_claims[:6]:
                claim_str = c.get('claim', '?')[:150]
                conf = c.get('confidence', '')
                if conf and conf.lower() not in ('high', 'established'):
                    claim_str += f" ({conf})"
                claims_text.append(claim_str)
            lines.append(f"**{topic}** ({len(topic_claims)} facts):")
            for ct in claims_text:
                lines.append(f"  • {ct}")
            if len(topic_claims) > 6:
                lines.append(f"  ... and {len(topic_claims) - 6} more")
            lines.append("")
        
        # Disputed/conflicting info — worth highlighting
        if conflicted:
            lines.append(f"**⚠ Conflicting information ({len(conflicted)}):**")
            for c in conflicted[:3]:
                lines.append(f"  • {c.get('claim', '?')[:120]}")
            lines.append("")
        
        if gaps:
            lines.append(f"**Still unknown ({len(gaps)} gaps):**")
            for g in gaps[:5]:
                gap_text = g if isinstance(g, str) else g.get("gap", str(g))
                lines.append(f"  • {gap_text[:120]}")
        
        return "\n".join(lines)
    
    elif name == "approve_strategy":
        from strategy_store import approve_strategy
        version = args["version"]
        result = approve_strategy("researcher", domain, version)
        if result.get("action") == "approved":
            return f"✓ {result.get('reason', f'Strategy {version} approved for trial in {domain}.')}"
        else:
            return f"Failed to approve: {result.get('reason', 'unknown error')}"
    
    elif name == "show_budget":
        from cost_tracker import get_daily_spend, check_balance, get_all_time_spend
        daily = get_daily_spend()
        balance = check_balance()
        all_time = get_all_time_spend()
        
        lines = [
            "**Budget Status:**",
            f"  Today: ${daily.get('total_usd', 0):.2f} spent ({daily.get('calls', 0)} API calls)",
            f"  Daily limit: ${DAILY_BUDGET_USD:.2f}",
            f"  Remaining today: ${max(0, DAILY_BUDGET_USD - daily.get('total_usd', 0)):.2f}",
            f"  Balance: ${balance.get('remaining', 0):.2f}",
            f"  All-time spend: ${all_time.get('total_usd', 0):.2f}",
        ]
        return "\n".join(lines)
    
    elif name == "show_recommendations":
        from scheduler import get_recommendations
        recs = get_recommendations()
        
        if not recs:
            return "No recommendations available right now."
        
        lines = ["**Recommendations:**"]
        for r in recs:
            priority = r.get("priority", "info")
            msg = r.get("message", "")
            action = r.get("action", "")
            lines.append(f"  [{priority}] {msg}")
            if action:
                lines.append(f"    → {action}")
        
        return "\n".join(lines)
    
    elif name == "list_domains":
        from analytics import domain_comparison
        comparisons = domain_comparison()
        if not comparisons:
            return "No domains have data yet."
        
        lines = ["**All Domains:**"]
        for d in comparisons:
            lines.append(
                f"  - **{d['domain']}**: {d['count']} outputs, "
                f"avg {d['avg_score']:.1f}, {d['accepted']} accepted"
            )
        return "\n".join(lines)
    
    elif name == "show_knowledge_gaps":
        from memory_store import load_knowledge_base
        kb = load_knowledge_base(domain)
        if not kb:
            return f"No knowledge base for '{domain}'. Can't show gaps."
        
        gaps = kb.get("identified_gaps", [])
        if not gaps:
            return f"No identified knowledge gaps in '{domain}'."
        
        lines = [f"**What we don't know yet about {domain}** ({len(gaps)} gaps):"]
        for i, g in enumerate(gaps, 1):
            gap_text = g if isinstance(g, str) else g.get("gap", str(g))
            lines.append(f"  {i}. {gap_text}")
        return "\n".join(lines)
    
    elif name == "execute_task":
        goal = args["goal"]
        try:
            from cli.execution import run_execute
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run_execute(domain=domain, goal=goal)
            output = buf.getvalue()
            # Extract key info from output
            if output:
                return f"**Execution complete.**\n\n{output[-2000:]}"
            return "**Execution complete.** Check the workspace for generated files."
        except Exception as e:
            return f"Execution failed: {e}"
    
    elif name == "auto_build":
        rounds = args.get("rounds", 1)
        try:
            from cli.execution import run_auto_build
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run_auto_build(domain=domain, rounds=rounds)
            output = buf.getvalue()
            if output:
                return f"**Auto-build complete ({rounds} round(s)).**\n\n{output[-2000:]}"
            return f"**Auto-build complete ({rounds} round(s)).** Check workspace for artifacts."
        except Exception as e:
            return f"Auto-build failed: {e}"
    
    elif name == "show_exec_status":
        try:
            from cli.execution import show_exec_status
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                show_exec_status(domain=domain)
            return buf.getvalue() or "No execution data yet."
        except Exception as e:
            return f"Error getting exec status: {e}"
    
    elif name == "run_project":
        description = args["description"]
        try:
            from cli.project import run as run_project_fn
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run_project_fn(description=description, domain=domain)
            output = buf.getvalue()
            if output:
                return f"**Project started.**\n\n{output[-2000:]}"
            return "**Project created.** Use show_project_status to track progress."
        except Exception as e:
            return f"Project creation failed: {e}"
    
    elif name == "show_project_status":
        project_id = args.get("project_id", "latest")
        try:
            from cli.project import status as project_status
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                project_status(project_id=project_id)
            return buf.getvalue() or "No project data found."
        except Exception as e:
            return f"Error getting project status: {e}"
    
    elif name == "list_projects":
        try:
            from cli.project import list_all
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                list_all()
            return buf.getvalue() or "No projects yet."
        except Exception as e:
            return f"Error listing projects: {e}"
    
    elif name == "crawl_docs":
        url = args["url"]
        max_pages = args.get("max_pages", 20)
        try:
            from cli.tools_cmd import crawl
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                crawl(url=url, domain=domain, max_pages=max_pages, url_pattern="")
            output = buf.getvalue()
            return output[-2000:] if output else f"Crawled {url} (up to {max_pages} pages)."
        except Exception as e:
            return f"Crawl failed: {e}"
    
    elif name == "fetch_url":
        url = args["url"]
        try:
            from cli.tools_cmd import fetch
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                fetch(url=url)
            output = buf.getvalue()
            return output[-3000:] if output else f"Fetched {url} (no content returned)."
        except Exception as e:
            return f"Fetch failed: {e}"
    
    elif name == "show_lessons":
        try:
            from research_lessons import get_lessons
            lessons = get_lessons(domain)
            if not lessons:
                return f"No research lessons for '{domain}' yet. Lessons are captured from critic rejections (score < 5) and strategy rollbacks."
            lines = [f"Research lessons for '{domain}' ({len(lessons)} total):"]
            for l in lessons:
                hits = f" (seen {l['hit_count']}x)" if l.get('hit_count', 1) > 1 else ""
                lines.append(f"- [{l.get('source', '?')}] {l['lesson']}{hits}")
            return "\n".join(lines)
        except Exception as e:
            return f"Failed to load lessons: {e}"
    
    # === READ-ONLY SOURCE CODE TOOLS ===
    elif name == "list_files":
        try:
            base = os.path.dirname(os.path.dirname(__file__))  # agent-brain/
            rel_path = args.get("path", ".") or "."
            # Security: prevent path traversal outside agent-brain
            target = os.path.normpath(os.path.join(base, rel_path))
            if not target.startswith(base):
                return "Access denied: cannot navigate outside agent-brain/"
            if not os.path.exists(target):
                return f"Path not found: {rel_path}"
            if os.path.isfile(target):
                size = os.path.getsize(target)
                return f"{rel_path} — file, {size} bytes"
            entries = sorted(os.listdir(target))
            dirs = [e + "/" for e in entries if os.path.isdir(os.path.join(target, e)) and not e.startswith("__pycache")]
            files = [e for e in entries if os.path.isfile(os.path.join(target, e)) and not e.endswith(".pyc")]
            lines = [f"Contents of {rel_path}/ ({len(dirs)} dirs, {len(files)} files):"]
            for d in dirs:
                lines.append(f"  📁 {d}")
            for f_name in files:
                size = os.path.getsize(os.path.join(target, f_name))
                lines.append(f"  📄 {f_name} ({size:,} bytes)")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing files: {e}"
    
    elif name == "read_source":
        try:
            base = os.path.dirname(os.path.dirname(__file__))  # agent-brain/
            rel_path = args["file"]
            target = os.path.normpath(os.path.join(base, rel_path))
            # Security: prevent path traversal outside agent-brain
            if not target.startswith(base):
                return "Access denied: cannot read files outside agent-brain/"
            if not os.path.exists(target):
                return f"File not found: {rel_path}"
            if not os.path.isfile(target):
                return f"Not a file: {rel_path} (use list_files to browse directories)"
            
            with open(target, "r", errors="replace") as f:
                all_lines = f.readlines()
            
            total = len(all_lines)
            start = max(1, args.get("start_line", 1)) - 1  # 0-indexed
            end = min(total, args.get("end_line", total))
            selected = all_lines[start:end]
            
            # Cap output to avoid blowing up context
            content = "".join(selected)
            if len(content) > 8000:
                content = content[:8000] + f"\n... (truncated at 8000 chars, file has {total} lines total)"
            
            header = f"📄 {rel_path} — lines {start+1}-{end} of {total}:\n"
            return header + "```\n" + content + "\n```"
        except Exception as e:
            return f"Error reading file: {e}"
    
    elif name == "search_code":
        try:
            import fnmatch
            base = os.path.dirname(os.path.dirname(__file__))  # agent-brain/
            pattern = args["pattern"].lower()
            file_glob = args.get("file_pattern", "*.py") or "*.py"
            
            matches = []
            for root, dirs, files in os.walk(base):
                # Skip hidden dirs, __pycache__, node_modules, crawl_data
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "crawl_data", ".git")]
                for fname in files:
                    if not fnmatch.fnmatch(fname, file_glob):
                        continue
                    filepath = os.path.join(root, fname)
                    rel = os.path.relpath(filepath, base)
                    try:
                        with open(filepath, "r", errors="replace") as f:
                            for i, line in enumerate(f, 1):
                                if pattern in line.lower():
                                    matches.append(f"  {rel}:{i}: {line.rstrip()[:120]}")
                                    if len(matches) >= 50:
                                        break
                    except Exception:
                        continue
                    if len(matches) >= 50:
                        break
                if len(matches) >= 50:
                    break
            
            if not matches:
                return f"No matches for '{args['pattern']}' in {file_glob}"
            
            truncated = " (showing first 50)" if len(matches) >= 50 else ""
            return f"Found {len(matches)} matches for '{args['pattern']}'{truncated}:\n" + "\n".join(matches)
        except Exception as e:
            return f"Error searching: {e}"
    
    elif name == "set_domain_goal":
        try:
            from domain_goals import set_goal
            goal_domain = args["domain"]
            goal_text = args["goal"]
            if not goal_text.strip():
                return "Goal text is empty — cannot set an empty goal."
            record = set_goal(goal_domain, goal_text)
            return (
                f"Goal set for domain '{goal_domain}'.\n"
                f"Goal: {record['goal']}\n"
                f"Now when research cycles run, questions will be directed at this goal."
            )
        except Exception as e:
            return f"Error setting goal: {e}"
    
    elif name == "show_domain_goal":
        try:
            from domain_goals import get_goal_record, list_goals
            if domain:
                record = get_goal_record(domain)
                if not record:
                    return f"No goal set for domain '{domain}'. Set one with set_domain_goal before running research."
                lines = [
                    f"**Domain: {domain}**",
                    f"Goal: {record['goal']}",
                    f"Set: {record.get('set_at', '?')[:10]}",
                ]
                if record.get('previous_goals'):
                    lines.append(f"Previous goals: {len(record['previous_goals'])}")
                return "\n".join(lines)
            else:
                goals = list_goals()
                if not goals:
                    return "No domain goals set yet."
                lines = ["**Domain Goals:**"]
                for d, g in goals.items():
                    lines.append(f"  **{d}**: {g[:100]}{'...' if len(g) > 100 else ''}")
                return "\n".join(lines)
        except Exception as e:
            return f"Error showing goal: {e}"
    
    elif name == "run_cycle":
        try:
            from domain_goals import get_goal
            from cli.research import run_auto
            from memory_store import load_outputs
            import io
            import contextlib
            
            rounds = min(args.get("rounds", 1), 10)  # Cap at 10
            goal = get_goal(domain)
            
            if not goal:
                return (
                    f"No goal set for domain '{domain}'.\n"
                    f"Before running research cycles, set a goal so questions are actionable.\n"
                    f"Use set_domain_goal to define what you want to achieve with this domain."
                )
            
            # Snapshot outputs before cycle to identify what's new
            before_count = len(load_outputs(domain, min_score=0))
            
            # Run the cycle (capture stdout for diagnostics)
            output_buffer = io.StringIO()
            with contextlib.redirect_stdout(output_buffer):
                run_auto(domain, rounds)
            
            # Get new outputs — what the system actually learned
            all_outputs = load_outputs(domain, min_score=0)
            new_outputs = all_outputs[before_count:]
            
            lines = [f"**Research cycle complete** — {rounds} round(s) in domain '{domain}'\n"]
            
            if not new_outputs:
                lines.append("No new outputs produced (budget limit, dedup, or generation failure).")
                return "\n".join(lines)
            
            lines.append(f"**{len(new_outputs)} new research output(s):**\n")
            
            for i, o in enumerate(new_outputs, 1):
                score = o.get("overall_score", o.get("critique", {}).get("overall_score", "?"))
                accepted = "✓ Accepted" if o.get("accepted") else "✗ Rejected"
                question = o.get("question", "?")
                research = o.get("research", {})
                critique = o.get("critique", {})
                
                lines.append(f"**Round {i}: {question}**")
                lines.append(f"  Score: {score}/10 ({accepted})")
                
                # Summary — what was learned
                summary = research.get("summary", "")
                if summary:
                    lines.append(f"  Summary: {summary[:300]}")
                
                # Key insights
                key_insights = research.get("key_insights", [])
                if key_insights:
                    for ki in key_insights[:3]:
                        if isinstance(ki, str):
                            lines.append(f"    • {ki[:200]}")
                
                # Critic feedback
                weaknesses = critique.get("weaknesses", [])
                if weaknesses:
                    lines.append(f"  Gaps: {'; '.join(w[:60] for w in weaknesses[:2])}")
                
                lines.append("")
            
            # Overall what's still unknown
            all_gaps = []
            for o in new_outputs:
                all_gaps.extend(o.get("research", {}).get("knowledge_gaps", []))
            if all_gaps:
                unique_gaps = list(dict.fromkeys(str(g)[:80] for g in all_gaps))[:5]
                lines.append(f"**Still unknown:** {'; '.join(unique_gaps)}")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Research cycle failed: {e}"
    
    # === CORTEX ORCHESTRATOR TOOLS ===
    elif name == "ask_orchestrator":
        try:
            from agents.cortex import query_orchestrator, format_orchestrator_response
            result = query_orchestrator(
                question=args["question"],
                domain=args.get("domain", domain),
                extra_context=args.get("context", ""),
            )
            return format_orchestrator_response(result)
        except Exception as e:
            return f"Orchestrator query failed: {e}"
    
    elif name == "orchestrator_plan":
        try:
            from agents.cortex import plan_next_actions, format_orchestrator_response
            result = plan_next_actions(domain=args.get("domain", domain))
            return format_orchestrator_response(result)
        except Exception as e:
            return f"Orchestrator planning failed: {e}"
    
    elif name == "orchestrator_interpret":
        try:
            from agents.cortex import interpret_findings, format_orchestrator_response
            result = interpret_findings(
                domain=args["domain"],
                question=args.get("focus", ""),
            )
            return format_orchestrator_response(result)
        except Exception as e:
            return f"Orchestrator interpretation failed: {e}"
    
    elif name == "orchestrator_coordinate":
        try:
            from agents.cortex import coordinate_brain_to_hands, format_orchestrator_response
            result = coordinate_brain_to_hands(domain=args["domain"])
            return format_orchestrator_response(result)
        except Exception as e:
            return f"Brain→Hands coordination failed: {e}"
    
    elif name == "orchestrator_assess":
        try:
            from agents.cortex import assess_system, format_orchestrator_response
            result = assess_system()
            return format_orchestrator_response(result)
        except Exception as e:
            return f"System assessment failed: {e}"
    
    return f"Unknown tool: {name}"


# ============================================================
# Chat REPL
# ============================================================

WELCOME = """
\033[1;36m╔══════════════════════════════════════════════════════════════╗
║                       CORTEX                                 ║
║          Autonomous Research & Execution System              ║
╠══════════════════════════════════════════════════════════════╣\033[0m
  \033[1mArchitecture:\033[0m Chat (Grok) → Orchestrator (Sonnet) → Brain + Hands

  \033[1;33mResearch:\033[0m  "Research the latest React 19 features"
  \033[1;33mStrategic:\033[0m "What should we focus on next?"  →  Orchestrator
  \033[1;33mBuild:\033[0m     "Build a REST API for user management"
  \033[1;33mStatus:\033[0m    "How is the system performing?"

  \033[2mCommands:\033[0m
    /domain <name>  Switch domain       /sessions  List conversations
    /clear          Reset history        /load <id> Resume conversation
    /new            Fresh session         /context  Show current state
    /reasoning      Toggle Grok reasoning (off by default)
    /help           Show this message    quit/exit  Leave
\033[1;36m╚══════════════════════════════════════════════════════════════╝\033[0m
"""


def _format_markdown(text: str) -> str:
    """Convert markdown formatting to ANSI terminal codes."""
    # Bold: **text** → \033[1mtext\033[0m
    text = re.sub(r'\*\*(.+?)\*\*', r'\033[1m\1\033[0m', text)
    # Italic: *text* → \033[3mtext\033[0m (but not ** or list items)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\033[3m\1\033[0m', text)
    # Inline code: `text` → \033[33mtext\033[0m (yellow)
    text = re.sub(r'`([^`]+)`', r'\033[33m\1\033[0m', text)
    # Headers: ## text → bold + underline
    text = re.sub(r'^(#{1,3})\s+(.+)$', r'\033[1;4m\2\033[0m', text, flags=re.MULTILINE)
    # Bullet points: - text or • text → colored bullet
    text = re.sub(r'^(\s*)[-•]\s', r'\1\033[36m•\033[0m ', text, flags=re.MULTILINE)
    # Score formatting: [7.0] or [8.5] → colored
    text = re.sub(r'\[(\d+\.\d+)\]', r'\033[1;33m[\1]\033[0m', text)
    # Checkmarks
    text = text.replace('✓', '\033[32m✓\033[0m')
    text = text.replace('✗', '\033[31m✗\033[0m')
    return text


def run_chat(domain: str = DEFAULT_DOMAIN, session_id: str = ""):
    """Run the interactive chat REPL with persistent conversation memory."""
    
    print(WELCOME)
    
    # Session management: resume latest, load specific, or create new
    conversation: list[dict] = []
    
    if session_id:
        # Explicit session requested
        loaded_domain, loaded_msgs = _load_session(session_id)
        if loaded_msgs:
            domain = loaded_domain
            conversation = loaded_msgs
            print(f"  Resumed session: {session_id} ({len(conversation)} messages)")
        else:
            print(f"  Session '{session_id}' not found, starting fresh.")
            session_id = _generate_session_id()
    else:
        # Try to resume most recent session for this domain (if < 24h old)
        sessions = _list_sessions()
        recent = None
        for s in sessions:
            if s["domain"] == domain:
                recent = s
                break
        
        if recent:
            # Check if session is recent (within 24h)
            try:
                updated = datetime.fromisoformat(recent["updated"])
                age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
                if age_hours < 24:
                    loaded_domain, loaded_msgs = _load_session(recent["id"])
                    if loaded_msgs:
                        conversation = loaded_msgs
                        session_id = recent["id"]
                        print(f"  Resumed recent session: {session_id} ({len(conversation)} messages)")
                        summary = recent.get("summary", "")
                        if summary:
                            print(f"  Last topic: {summary}")
                else:
                    session_id = _generate_session_id()
            except Exception:
                session_id = _generate_session_id()
        else:
            session_id = _generate_session_id()
    
    if not session_id:
        session_id = _generate_session_id()
    
    print(f"  Active domain: {domain}")
    print(f"  Session: {session_id}")
    
    # Use the cheap model for conversation (fast + affordable)
    chat_model = CHEAP_MODEL
    
    # Reasoning toggle — starts based on config, togglable via /reasoning
    chat_reasoning = REASONING_EFFORT.get("chat")
    reasoning_label = f" + reasoning={chat_reasoning}" if chat_reasoning else ""
    print(f"  Model: {CHEAP_MODEL} (chat{reasoning_label}) / Sonnet (orchestrator + research)\n")
    
    system_prompt = _build_system_context(domain)
    
    while True:
        try:
            user_input = input("\033[1;36m You:\033[0m ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Saving conversation...")
            _save_session(session_id, domain, conversation, _summarize_conversation(conversation))
            print("  Goodbye.\n")
            break
        
        if not user_input:
            continue
        
        # Meta-commands
        if user_input.lower() in ("quit", "exit", "/quit", "/exit"):
            print("  Saving conversation...")
            _save_session(session_id, domain, conversation, _summarize_conversation(conversation))
            print("  Goodbye.\n")
            break
        
        if user_input.lower() == "/clear":
            conversation.clear()
            session_id = _generate_session_id()
            print(f"  Conversation cleared. New session: {session_id}\n")
            continue
        
        if user_input.lower() == "/new":
            # Save current, start fresh
            if conversation:
                _save_session(session_id, domain, conversation, _summarize_conversation(conversation))
                print(f"  Saved session {session_id}.")
            conversation = []
            session_id = _generate_session_id()
            print(f"  New session: {session_id}\n")
            continue
        
        if user_input.lower() == "/sessions":
            sessions = _list_sessions()
            if not sessions:
                print("  No saved sessions.\n")
            else:
                print(f"\n  Saved conversations ({len(sessions)}):")
                for s in sessions[:10]:
                    current = " ← current" if s["id"] == session_id else ""
                    print(f"    {s['id']}  [{s['domain']}]  {s['messages']} msgs  {s.get('summary', '')[:50]}{current}")
                print(f"\n  Use '/load <id>' to resume.\n")
            continue
        
        if user_input.lower().startswith("/load "):
            target = user_input.split(None, 1)[1].strip()
            # Save current first
            if conversation:
                _save_session(session_id, domain, conversation, _summarize_conversation(conversation))
            loaded_domain, loaded_msgs = _load_session(target)
            if loaded_msgs:
                domain = loaded_domain
                conversation = loaded_msgs
                session_id = target
                system_prompt = _build_system_context(domain)
                print(f"  Loaded session {target}: {len(conversation)} messages, domain={domain}\n")
            else:
                print(f"  Session '{target}' not found.\n")
            continue
        
        if user_input.lower().startswith("/domain "):
            domain = user_input.split(None, 1)[1].strip()
            system_prompt = _build_system_context(domain)
            print(f"  Switched to domain: {domain}\n")
            continue
        
        if user_input.lower() == "/help":
            print(WELCOME)
            continue
        
        if user_input.lower().startswith("/reasoning"):
            parts = user_input.split()
            if len(parts) == 1:
                # Toggle: off → high, or any → off
                if chat_reasoning:
                    chat_reasoning = None
                    print("  Reasoning: \033[31mOFF\033[0m (faster, cheaper)\n")
                else:
                    chat_reasoning = "high"
                    print("  Reasoning: \033[32mHIGH\033[0m (better quality, more tokens)\n")
            elif len(parts) == 2 and parts[1].lower() in ("off", "low", "medium", "high"):
                level = parts[1].lower()
                if level == "off":
                    chat_reasoning = None
                    print("  Reasoning: \033[31mOFF\033[0m\n")
                else:
                    chat_reasoning = level
                    print(f"  Reasoning: \033[32m{level.upper()}\033[0m\n")
            else:
                print("  Usage: /reasoning [off|low|medium|high]  (no arg = toggle)\n")
            continue
        
        if user_input.lower() == "/context":
            from cost_tracker import get_daily_spend
            daily = get_daily_spend()
            reasoning_str = f", reasoning={chat_reasoning}" if chat_reasoning else ""
            print(f"\n  Domain: {domain}")
            print(f"  Session: {session_id}")
            print(f"  History: {len(conversation)} messages")
            print(f"  Model: {chat_model}{reasoning_str}")
            print(f"  Budget: ${daily.get('total_usd', 0):.2f} / ${DAILY_BUDGET_USD:.2f} today\n")
            continue
        
        # Add user message
        conversation.append({"role": "user", "content": user_input})
        
        # Keep conversation manageable (last 40 messages sent to LLM)
        if len(conversation) > 40:
            conversation = conversation[-40:]
        
        # Call LLM with tools
        try:
            t_start = _time.monotonic()
            total_input_tokens = 0
            total_output_tokens = 0
            
            response = call_llm(
                model=chat_model,
                system=system_prompt,
                messages=conversation,
                tools=CHAT_TOOLS,
                max_tokens=2048,
                temperature=0.7,
                reasoning_effort=chat_reasoning,
            )
            
            # Track cost
            if response.usage:
                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens
                log_cost(
                    model=chat_model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    agent_role="chat",
                    domain=domain,
                )
            
            # Process response — handle tool calls
            max_tool_rounds = 3
            tool_round = 0
            
            while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
                tool_round += 1
                
                # Build assistant message content
                assistant_content = []
                tool_results = []
                
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                        
                        # Execute the tool
                        tool_start = _time.monotonic()
                        print(f"  \033[2m\u25B6 {block.name}\033[0m ", end="", flush=True)
                        result = _execute_tool(block.name, block.input, domain)
                        tool_elapsed = _time.monotonic() - tool_start
                        print(f"\033[2m({tool_elapsed:.1f}s)\033[0m")
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                
                # Add assistant message + tool results to conversation                
                conversation.append({"role": "assistant", "content": assistant_content})
                conversation.append({"role": "user", "content": tool_results})
                
                # Get next response
                response = call_llm(
                    model=chat_model,
                    system=system_prompt,
                    messages=conversation,
                    tools=CHAT_TOOLS,
                    max_tokens=2048,
                    temperature=0.7,
                    reasoning_effort=chat_reasoning,
                )
                
                if response.usage:
                    total_input_tokens += response.usage.input_tokens
                    total_output_tokens += response.usage.output_tokens
                    log_cost(
                        model=chat_model,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        agent_role="chat",
                        domain=domain,
                    )
            
            t_elapsed = _time.monotonic() - t_start
            
            # Extract final text response
            text_parts = []
            for block in response.content:
                if block.type == "text" and block.text:
                    text_parts.append(block.text)
            
            assistant_text = "\n".join(text_parts) if text_parts else "(no response)"
            
            # Add to conversation history
            conversation.append({"role": "assistant", "content": assistant_text})
            
            # Print response with markdown formatting
            formatted = _format_markdown(assistant_text)
            print(f"\n\033[1;32m Agent:\033[0m {formatted}")
            
            # Response metadata line (tokens, time, cost estimate)
            from llm_router import get_model_cost
            costs = get_model_cost(chat_model)
            est_cost = (total_input_tokens * costs["input"] + total_output_tokens * costs["output"]) / 1_000_000
            reasoning_tag = f" \033[35mreasoning={chat_reasoning}\033[0m" if chat_reasoning else ""
            print(f"  \033[2m{total_input_tokens}+{total_output_tokens} tokens \u2022 {t_elapsed:.1f}s \u2022 ~${est_cost:.4f}{reasoning_tag}\033[0m\n")
            
            # Auto-save after each exchange
            _save_session(session_id, domain, conversation, _summarize_conversation(conversation))
            
        except KeyboardInterrupt:
            print("\n  (interrupted)\n")
            # Remove the user message we added
            if conversation and conversation[-1]["role"] == "user":
                conversation.pop()
            continue
        except Exception as e:
            print(f"\n\033[1;31m  Error: {e}\033[0m\n")
            # Remove the user message we added
            if conversation and conversation[-1]["role"] == "user":
                conversation.pop()
            continue
