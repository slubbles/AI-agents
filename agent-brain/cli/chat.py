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

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import MODELS, DEFAULT_DOMAIN, DAILY_BUDGET_USD, CHEAP_MODEL
from llm_router import call_llm
from cost_tracker import log_cost


# ============================================================
# System Context Builder
# ============================================================

def _build_system_context(domain: str) -> str:
    """Build a rich system prompt with current system state."""
    from memory_store import get_stats, load_knowledge_base, load_outputs
    from strategy_store import get_active_version, get_strategy_status, list_pending
    from cost_tracker import get_daily_spend, check_balance
    from analytics import domain_comparison, cost_efficiency
    
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
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    return f"""You are Agent Brain's conversational interface. Today is {today}.

You are an autonomous, self-improving research system. You have a knowledge base, scored research outputs, strategy evolution, and multi-domain research capabilities.

CURRENT STATE:
  Active domain: {domain}
  Strategy: {active_ver} ({strat_status}){pending_info}
  Domain stats: {stats.get('count', 0)} outputs, avg score {stats.get('avg_score', 0):.1f}, {stats.get('accepted', 0)} accepted, {stats.get('rejected', 0)} rejected
  Knowledge base: {kb_summary}
  Budget: ${daily.get('total_usd', 0):.2f} spent today / ${DAILY_BUDGET_USD:.2f} limit. Balance: ${balance.get('remaining', 0):.2f}

ALL DOMAINS:
{chr(10).join(all_domains) if all_domains else '  (none loaded)'}

RECENT HIGH-QUALITY OUTPUTS ({domain}):
{recent_summary if recent_summary else '  (none yet)'}

AVAILABLE TOOLS:
You have tools to interact with the system. Use them when the user asks you to do something.
When users ask conversational questions about what you know, answer from your knowledge base context.
When they ask you to take actions (research, approve, check status), use the appropriate tool.

STYLE:
- Be direct, concise, and helpful
- When sharing knowledge, cite the confidence level and source if available
- If you don't know something, say so — suggest researching it
- Use plain language, not jargon
- Format with markdown when helpful
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
    
    return f"Unknown tool: {name}"


# ============================================================
# Chat REPL
# ============================================================

WELCOME = """
╔══════════════════════════════════════════════════════════════╗
║                    AGENT BRAIN — Chat Mode                  ║
╠══════════════════════════════════════════════════════════════╣
║  Talk to the system naturally. Ask questions, give commands.║
║                                                             ║
║  Examples:                                                  ║
║    "What do you know about crypto?"                         ║
║    "Research the latest React 19 features"                  ║
║    "How's the budget looking?"                              ║
║    "What are the knowledge gaps in productized-services?"   ║
║    "Approve strategy v004 for crypto"                       ║
║    "What should I work on next?"                            ║
║                                                             ║
║  Type 'quit' or 'exit' to leave. Ctrl+C also works.        ║
║  Type '/domain <name>' to switch domains.                   ║
║  Type '/clear' to reset conversation history.               ║
╚══════════════════════════════════════════════════════════════╝
"""


def run_chat(domain: str = DEFAULT_DOMAIN):
    """Run the interactive chat REPL."""
    
    print(WELCOME)
    print(f"  Active domain: {domain}")
    print(f"  Model: {CHEAP_MODEL} (chat) / Sonnet (research)\n")
    
    conversation: list[dict] = []
    system_prompt = _build_system_context(domain)
    
    # Use the cheap model for conversation (fast + affordable)
    chat_model = CHEAP_MODEL
    
    while True:
        try:
            user_input = input("\033[1;36m You:\033[0m ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Goodbye.\n")
            break
        
        if not user_input:
            continue
        
        # Meta-commands
        if user_input.lower() in ("quit", "exit", "/quit", "/exit"):
            print("\n  Goodbye.\n")
            break
        
        if user_input.lower() == "/clear":
            conversation.clear()
            print("  Conversation cleared.\n")
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
            print(f"  History: {len(conversation)} messages")
            print(f"  Model: {chat_model}\n")
            continue
        
        # Add user message
        conversation.append({"role": "user", "content": user_input})
        
        # Keep conversation manageable (last 20 messages)
        if len(conversation) > 20:
            conversation = conversation[-20:]
        
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
