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
import readline  # enables arrow keys, history in input()
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import MODELS, DEFAULT_DOMAIN, DAILY_BUDGET_USD, CHEAP_MODEL
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
            recent_lines.append(f"  - [{s}] {q}")
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
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    return f"""You are the chat interface for Agent Brain. Today is {today}.

Be honest about what this system can and cannot do. Never oversell. Never bullshit.

WHAT ACTUALLY WORKS (proven, tested, has data):
- Research loop: web search → structured output → critic scores it → store if score >= 6, retry if not. This works.
- Strategy evolution: the system rewrites its own research strategies based on score patterns. Proven trajectory: 5.4 → 7.1 → 7.7 over multiple research rounds. This is the novel piece.
- Critic: scores on 5 dimensions (accuracy 30%, depth 20%, completeness 20%, specificity 15%, intellectual honesty 15%). Rejects bad output. This is the quality signal AND cost control.
- Cross-domain transfer: extracts general principles from proven strategies → seeds new domains. Tested.
- Self-directed learning: identifies knowledge gaps → generates next questions → researches them. Tested.
- Strategy safety: pending/trial/active/rollback lifecycle. Human approval required. Never deploys strategy scoring >20% below current best.
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
1. Brain: research + scoring + strategy evolution + knowledge base. This is the core. It works.
2. Hands: code generation + execution. This exists. It's early-stage.
3. Infrastructure: browser, crawler, vault, scheduler, deployment. This exists. Most of it is untested in production.

The Brain is Layer 1-5. Each layer was earned by getting the previous one working.
The Hands and infrastructure are built but haven't gone through the same prove-it-works cycle.

CONVERSATION MEMORY:
Sessions persist across restarts (JSON files in logs/chat_sessions/).
You can recall previous conversations. Use this for continuity — don't re-explain things.

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

STYLE:
- Be direct. Be honest. No hype.
- When you don't know something, say so. Offer to research it.
- When describing capabilities, distinguish between "proven" and "code exists but unproven."
- Cite confidence levels and sources when sharing from the KB.
- If the user asks "can you do X?" — answer whether you ACTUALLY can right now, not theoretically.
- Don't use phrases like "I can scale to clusters" or "vector DB" — that's not what this is yet.
- Format with markdown when it helps readability, not for decoration.
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
]


# ============================================================
# Tool Execution
# ============================================================

def _execute_tool(name: str, args: dict, active_domain: str) -> str:
    """Execute a chat tool and return the result as a string."""
    
    domain = args.get("domain", active_domain)
    
    if name == "search_knowledge":
        from analytics import search_memory
        results = search_memory(args["query"], domains=[domain] if domain else None)
        if not results:
            return f"No results found for '{args['query']}' in {domain}."
        
        lines = [f"Found {len(results)} results for '{args['query']}':"]
        for r in results[:8]:
            q = r.get("question", "?")[:80]
            s = r.get("score", "?")
            d = r.get("domain", "?")
            findings = r.get("findings", "")[:200]
            lines.append(f"\n**[{s}] {q}** ({d})")
            if findings:
                lines.append(f"  {findings}")
        return "\n".join(lines)
    
    elif name == "run_research":
        from main import run_loop
        question = args["question"]
        try:
            result = run_loop(question=question, domain=domain)
            score = result.get("critique", {}).get("overall_score", "?")
            verdict = result.get("critique", {}).get("verdict", "?")
            findings = result.get("research", {}).get("findings", [])
            
            lines = [f"**Research complete** — Score: {score}/10, Verdict: {verdict}"]
            if findings:
                lines.append("\nKey findings:")
                for f_item in findings[:5]:
                    claim = f_item.get("claim", "") if isinstance(f_item, dict) else str(f_item)
                    lines.append(f"  - {claim[:150]}")
            
            gaps = result.get("research", {}).get("knowledge_gaps", [])
            if gaps:
                lines.append(f"\nKnowledge gaps identified: {len(gaps)}")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Research failed: {e}"
    
    elif name == "show_status":
        from memory_store import get_stats
        from strategy_store import get_active_version, get_strategy_status, list_pending
        from cost_tracker import get_daily_spend, check_balance
        
        stats = get_stats(domain)
        daily = get_daily_spend()
        balance = check_balance()
        active_ver = get_active_version("researcher", domain)
        status = get_strategy_status("researcher", domain)
        pending = list_pending("researcher", domain)
        
        lines = [
            f"**Domain: {domain}**",
            f"  Outputs: {stats.get('count', 0)} total, {stats.get('accepted', 0)} accepted, {stats.get('rejected', 0)} rejected",
            f"  Avg score: {stats.get('avg_score', 0):.1f}",
            f"  Strategy: {active_ver} ({status})",
        ]
        if pending:
            ver_list = ', '.join(p.get('version', '?') for p in pending)
            lines.append(f"  ⚠ Pending strategies: {ver_list}")
        lines.extend([
            f"\n**Budget:**",
            f"  Today: ${daily.get('total_usd', 0):.2f} / ${DAILY_BUDGET_USD:.2f}",
            f"  Balance: ${balance.get('remaining', 0):.2f}",
        ])
        return "\n".join(lines)
    
    elif name == "show_knowledge_base":
        from memory_store import load_knowledge_base
        kb = load_knowledge_base(domain)
        if not kb:
            return f"No knowledge base exists for '{domain}' yet. Run research first."
        
        claims = kb.get("claims", [])
        active = [c for c in claims if c.get("status") == "active"]
        gaps = kb.get("identified_gaps", [])
        
        # Group by topic
        topics = {}
        for c in active:
            topic = c.get("topic", "Uncategorized")
            if topic not in topics:
                topics[topic] = []
            topics[topic].append(c)
        
        lines = [f"**Knowledge Base: {domain}** — {len(active)} active claims\n"]
        for topic, topic_claims in sorted(topics.items()):
            lines.append(f"### {topic} ({len(topic_claims)} claims)")
            for c in topic_claims[:5]:
                conf = c.get("confidence", "?")
                lines.append(f"  - [{conf}] {c.get('claim', '?')[:120]}")
            if len(topic_claims) > 5:
                lines.append(f"  ... and {len(topic_claims) - 5} more")
            lines.append("")
        
        if gaps:
            lines.append(f"**Knowledge Gaps ({len(gaps)}):**")
            for g in gaps[:5]:
                gap_text = g if isinstance(g, str) else g.get("gap", str(g))
                lines.append(f"  - {gap_text[:120]}")
        
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
        
        lines = [f"**Knowledge Gaps in {domain}** ({len(gaps)}):"]
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
    
    return f"Unknown tool: {name}"


# ============================================================
# Chat REPL
# ============================================================

WELCOME = """
╔══════════════════════════════════════════════════════════════╗
║              AGENT BRAIN + HANDS — Chat Mode                ║
╠══════════════════════════════════════════════════════════════╣
║  Talk to the full system naturally. Research, build, manage.║
║  Conversations are saved and remembered across sessions.    ║
║                                                             ║
║  Research:                                                  ║
║    "What do you know about crypto?"                         ║
║    "Research the latest React 19 features"                  ║
║    "What are the knowledge gaps in productized-services?"   ║
║                                                             ║
║  Build:                                                     ║
║    "Build a REST API for user management"                   ║
║    "Auto-build something for the nextjs-react domain"       ║
║    "Start a project: build a SaaS dashboard"                ║
║                                                             ║
║  System feedback:                                           ║
║    "How is the system performing?"                          ║
║    "What have we built so far?"                             ║
║    "Give me feedback on the architecture"                   ║
║                                                             ║
║  Type 'quit' or 'exit' to leave. Ctrl+C also works.        ║
║  Type '/domain <name>' to switch domains.                   ║
║  Type '/clear' to reset conversation history.               ║
║  Type '/sessions' to list saved conversations.              ║
║  Type '/load <id>' to resume a previous conversation.       ║
║  Type '/new' to start a fresh conversation.                 ║
╚══════════════════════════════════════════════════════════════╝
"""


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
    print(f"  Model: {CHEAP_MODEL} (chat) / Sonnet (research)\n")
    
    system_prompt = _build_system_context(domain)
    
    # Use the cheap model for conversation (fast + affordable)
    chat_model = CHEAP_MODEL
    
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
        
        if user_input.lower() == "/context":
            print(f"\n  Domain: {domain}")
            print(f"  Session: {session_id}")
            print(f"  History: {len(conversation)} messages")
            print(f"  Model: {chat_model}\n")
            continue
        
        # Add user message
        conversation.append({"role": "user", "content": user_input})
        
        # Keep conversation manageable (last 40 messages sent to LLM)
        if len(conversation) > 40:
            conversation = conversation[-40:]
        
        # Call LLM with tools
        try:
            response = call_llm(
                model=chat_model,
                system=system_prompt,
                messages=conversation,
                tools=CHAT_TOOLS,
                max_tokens=2048,
                temperature=0.7,
            )
            
            # Track cost
            if response.usage:
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
                        print(f"\033[1;33m  [{block.name}]\033[0m ", end="", flush=True)
                        result = _execute_tool(block.name, block.input, domain)
                        print("done")
                        
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
                )
                
                if response.usage:
                    log_cost(
                        model=chat_model,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        agent_role="chat",
                        domain=domain,
                    )
            
            # Extract final text response
            text_parts = []
            for block in response.content:
                if block.type == "text" and block.text:
                    text_parts.append(block.text)
            
            assistant_text = "\n".join(text_parts) if text_parts else "(no response)"
            
            # Add to conversation history
            conversation.append({"role": "assistant", "content": assistant_text})
            
            # Print response
            print(f"\n\033[1;32m Agent:\033[0m {assistant_text}\n")
            
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
