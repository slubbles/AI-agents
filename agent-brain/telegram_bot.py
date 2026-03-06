"""
Telegram Chat Bot — Cortex AI System interface via Telegram.

Bridges the CLI chat mode to Telegram so you can interact with
Agent Brain from your phone. Same LLM + tools + system prompt
as the terminal chat, just over Telegram messages.

Usage:
    python telegram_bot.py          # Run the bot (foreground)
    python main.py --telegram       # Run via CLI

Setup:
    TELEGRAM_BOT_TOKEN=... in .env
    TELEGRAM_CHAT_ID=... in .env (only this chat ID can use the bot)

Architecture:
    Long-polling (getUpdates) → process message → call_llm w/ tools → 
    execute tools → send response via sendMessage.

No external dependencies — uses only stdlib urllib (same as alerts.py).
"""

import json
import logging
import os
import sys
import time
import signal
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Ensure agent-brain is on the path
sys.path.insert(0, os.path.dirname(__file__))

# Load .env before anything else
from config import (
    DEFAULT_DOMAIN, DAILY_BUDGET_USD, MODELS, REASONING_EFFORT, LOG_DIR,
    AVAILABLE_CHAT_MODELS, CHAT_MODEL
)
from llm_router import call_llm
from cost_tracker import log_cost

logger = logging.getLogger(__name__)

# ── Telegram API (pure stdlib) ─────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Telegram message length limit
MAX_MSG_LEN = 4096


def _tg_request(method: str, payload: dict = None, timeout: int = 60) -> dict:
    """Make a request to the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    if payload:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    else:
        req = urllib.request.Request(url)
    
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _send_message(chat_id: int | str, text: str, parse_mode: str = "HTML") -> bool:
    """Send a message, splitting if > 4096 chars."""
    if not text:
        text = "(empty response)"
    
    # Split long messages
    chunks = []
    while len(text) > MAX_MSG_LEN:
        # Try to split at a newline
        split_at = text.rfind("\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)
    
    for chunk in chunks:
        try:
            _tg_request("sendMessage", {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            })
        except Exception:
            # Fallback: send without parse_mode if HTML fails
            try:
                _tg_request("sendMessage", {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                })
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                return False
    return True


def _send_typing(chat_id: int | str):
    """Send 'typing...' indicator."""
    try:
        _tg_request("sendChatAction", {
            "chat_id": chat_id,
            "action": "typing",
        }, timeout=5)
    except Exception:
        pass


# ── Conversation State ─────────────────────────────────────────────────

class ConversationManager:
    """Manages per-chat conversation history, domain state, and model preference."""
    
    def __init__(self):
        self.conversations: dict[str, list[dict]] = {}  # chat_id → messages
        self.domains: dict[str, str] = {}  # chat_id → active domain
        self.models: dict[str, str] = {}   # chat_id → active chat model
        self._lock = threading.Lock()
    
    def get_messages(self, chat_id: str) -> list[dict]:
        with self._lock:
            return self.conversations.get(chat_id, [])
    
    def add_message(self, chat_id: str, role: str, content):
        with self._lock:
            if chat_id not in self.conversations:
                self.conversations[chat_id] = []
            self.conversations[chat_id].append({"role": role, "content": content})
            # Keep last 30 messages
            if len(self.conversations[chat_id]) > 30:
                self.conversations[chat_id] = self.conversations[chat_id][-30:]
    
    def clear(self, chat_id: str):
        with self._lock:
            self.conversations[chat_id] = []
    
    def get_domain(self, chat_id: str) -> str:
        return self.domains.get(chat_id, DEFAULT_DOMAIN)
    
    def set_domain(self, chat_id: str, domain: str):
        self.domains[chat_id] = domain
    
    def get_model(self, chat_id: str) -> str:
        return self.models.get(chat_id, CHAT_MODEL)
    
    def set_model(self, chat_id: str, model: str):
        self.models[chat_id] = model


_conversations = ConversationManager()


# ── Chat Pipeline (reuses cli/chat.py components) ─────────────────────

def _get_live_daemon_state() -> str:
    """Read daemon_state.json to know what the kitchen is doing right now."""
    state_file = os.path.join(LOG_DIR, "daemon_state.json")
    if not os.path.exists(state_file):
        return "Daemon: not running (no state file)"
    try:
        with open(state_file) as f:
            state = json.load(f)
        status = state.get("status", "unknown")
        cycle = state.get("cycle", "?")
        
        if status == "idle":
            last_completed = state.get("last_completed", "")
            avg_score = state.get("avg_score", "?")
            next_run = state.get("next_run", "")
            domain_results = state.get("domain_results", [])
            domains_summary = ", ".join(
                f"{d['domain']} ({d['avg_score']})" for d in domain_results
            ) if domain_results else "none"
            return (
                f"Daemon: IDLE after cycle {cycle}. "
                f"Last cycle scored {avg_score}/10 across [{domains_summary}]. "
                f"Next run: {next_run[:16] if next_run else 'unknown'}"
            )
        elif status == "running":
            domains = state.get("domains", [])
            planned = state.get("planned_rounds", "?")
            return (
                f"Daemon: RUNNING cycle {cycle} — "
                f"{planned} rounds across {', '.join(domains)}. "
                f"Started: {state.get('started_at', '?')[:16]}"
            )
        elif status == "waiting_budget":
            return (
                f"Daemon: PAUSED (budget limit reached). "
                f"Spent ${state.get('budget_spent', 0):.2f}/${state.get('budget_limit', 0):.2f}"
            )
        elif status == "watchdog_blocked":
            return f"Daemon: BLOCKED by watchdog — {state.get('reason', '?')}"
        elif status == "stopped":
            return f"Daemon: STOPPED at cycle {cycle}. {state.get('stop_reason', '')}"
        else:
            return f"Daemon: {status} (cycle {cycle})"
    except Exception:
        return "Daemon: state unreadable"


def _process_message(chat_id: str, text: str) -> str:
    """Process a user message through the LLM + tools pipeline.
    
    Returns the assistant's text response.
    """
    from cli.chat import (
        CHAT_TOOLS, _execute_tool, _build_system_context
    )
    
    domain = _conversations.get_domain(chat_id)
    
    # Build system prompt with live daemon state injected
    base_prompt = _build_system_context(domain)
    live_state = _get_live_daemon_state()
    system_prompt = base_prompt + f"\n\nLIVE DAEMON STATUS:\n  {live_state}\n"
    
    # Add user message to history
    _conversations.add_message(chat_id, "user", text)
    conversation = _conversations.get_messages(chat_id)
    
    chat_model = _conversations.get_model(chat_id)
    chat_reasoning = REASONING_EFFORT.get("chat")
    
    # Call LLM
    response = call_llm(
        model=chat_model,
        system=system_prompt,
        messages=conversation,
        tools=CHAT_TOOLS,
        max_tokens=2048,
        temperature=0.7,
        reasoning_effort=chat_reasoning,
    )
    
    total_input = response.usage.input_tokens if response.usage else 0
    total_output = response.usage.output_tokens if response.usage else 0
    if response.usage:
        log_cost(
            model=chat_model,
            input_tokens=total_input,
            output_tokens=total_output,
            agent_role="chat",
            domain=domain,
        )
    
    # Tool execution loop (max 5 rounds)
    max_tool_rounds = 5
    tool_round = 0
    tool_names_used = []
    
    while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
        tool_round += 1
        
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
                
                # Execute tool
                tool_names_used.append(block.name)
                try:
                    result = _execute_tool(block.name, block.input, domain)
                except Exception as e:
                    result = f"Tool error: {e}"
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result if isinstance(result, str) else json.dumps(result),
                })
        
        # Add to conversation
        _conversations.add_message(chat_id, "assistant", assistant_content)
        _conversations.add_message(chat_id, "user", tool_results)
        conversation = _conversations.get_messages(chat_id)
        
        # Send typing indicator between tool calls (shows activity)
        _send_typing(int(chat_id))
        
        # Continue conversation
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
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens
            log_cost(
                model=chat_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                agent_role="chat",
                domain=domain,
            )
    
    # Extract final text
    text_parts = []
    for block in response.content:
        if block.type == "text" and block.text:
            text_parts.append(block.text)
    
    assistant_text = "\n".join(text_parts) if text_parts else "(no response)"
    
    # Store assistant response
    _conversations.add_message(chat_id, "assistant", assistant_text)
    
    # Add cost footer
    from llm_router import get_model_cost
    costs = get_model_cost(chat_model)
    est_cost = (total_input * costs["input"] + total_output * costs["output"]) / 1_000_000
    
    footer = f"\n\n💬 {total_input}+{total_output} tokens • ~${est_cost:.4f}"
    if tool_names_used:
        footer += f" • 🔧 {', '.join(tool_names_used)}"
    
    return assistant_text + footer


def _html_escape(text: str) -> str:
    """Minimal HTML escaping for Telegram."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _markdown_to_telegram(text: str) -> str:
    """Convert common markdown to Telegram HTML.
    
    Handles: **bold**, *italic*, `code`, ```code blocks```, ### headers.
    Falls back to plain text if conversion would break HTML.
    """
    import re
    
    # Code blocks first (before other conversions)
    text = re.sub(r'```(\w*)\n(.*?)```', r'<pre>\2</pre>', text, flags=re.DOTALL)
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    
    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Bold (**text**)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # Italic (*text*) — but not inside <b> tags
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
    
    # Headers (### text → bold)
    text = re.sub(r'^#{1,3}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    
    # Bullet points — keep as-is (Telegram renders them fine)
    
    return text


# ── Bot Commands ───────────────────────────────────────────────────────

def _handle_command(chat_id: str, command: str) -> str | None:
    """Handle /commands. Returns response text, or None if not a command."""
    cmd = command.strip().lower()
    parts = cmd.split(None, 1)
    cmd_name = parts[0]
    cmd_arg = parts[1] if len(parts) > 1 else ""
    
    if cmd_name == "/start":
        return (
            "🟢 <b>Cortex AI System</b>\n\n"
            "I'm the chat interface for Cortex — a self-learning research agent.\n\n"
            "<b>What I can do:</b>\n"
            "• Research any topic (web search + critic scoring)\n"
            "• Build products from research (Brain → Hands pipeline)\n"
            "• Show what the system knows (knowledge base)\n"
            "• Check budget, status, domain stats\n\n"
            "<b>Research Commands:</b>\n"
            "/research [rounds] — Run a research cycle (default: 1 round)\n"
            "/research 3 — Run 3 rounds of self-directed research\n\n"
            "<b>Pipeline Commands:</b>\n"
            "/build &lt;instruction&gt; — Full pipeline: research → approve → build\n"
            "/approve — Approve a pending build\n"
            "/reject — Reject a pending build\n"
            "/pipeline — Show active pipelines\n\n"
            "<b>Threads Commands:</b>\n"
            "/threads search &lt;query&gt; — Search Threads posts\n"
            "/threads post &lt;text&gt; — Publish to Threads\n"
            "/threads draft &lt;topic&gt; — AI-generated post draft\n"
            "/threads analyze &lt;query&gt; — Pain point analysis\n"
            "/threads insights — Engagement stats\n"
            "/threads analytics — Profile analytics\n"
            "/threads thread &lt;id&gt; — Stats for a specific post\n\n"
            "<b>System Commands:</b>\n"
            "/status — System status + budget\n"
            "/kitchen — What's cooking right now (live daemon view)\n"
            "/domains — List all research domains\n"
            "/domain &lt;name&gt; — Switch active domain\n"
            "/model — Switch chat model (gemini-flash/grok/deepseek/sonnet)\n"
            "/clear — Clear conversation history\n"
            "/daemon — Full daemon status\n"
            "/help — Show this message\n\n"
            "Or just type naturally — I understand plain English.\n"
            "Chat: Gemini Flash (cheap + reasoning). Orchestrator: Claude Sonnet."
        )
    
    if cmd_name == "/help":
        return _handle_command(chat_id, "/start")
    
    if cmd_name == "/clear":
        _conversations.clear(chat_id)
        return "🗑 Conversation cleared. Fresh start."
    
    if cmd_name == "/domain":
        if cmd_arg:
            _conversations.set_domain(chat_id, cmd_arg)
            return f"📂 Switched to domain: <b>{cmd_arg}</b>"
        else:
            domain = _conversations.get_domain(chat_id)
            return f"📂 Active domain: <b>{domain}</b>\nUse /domain &lt;name&gt; to switch."
    
    if cmd_name == "/model":
        if cmd_arg:
            target = cmd_arg.strip().lower()
            if target in AVAILABLE_CHAT_MODELS:
                info = AVAILABLE_CHAT_MODELS[target]
                _conversations.set_model(chat_id, info["id"])
                reasoning_badge = " 🧠" if info.get("reasoning") else ""
                return (
                    f"✅ Switched to <b>{info['label']}</b>{reasoning_badge}\n"
                    f"Cost: {info['cost']}\n"
                    f"{info.get('notes', '')}"
                )
            else:
                available = ", ".join(AVAILABLE_CHAT_MODELS.keys())
                return f"❌ Unknown model '{cmd_arg}'. Available: {available}"
        else:
            current_model = _conversations.get_model(chat_id)
            lines = ["🤖 <b>Available chat models:</b>\n"]
            for alias, info in AVAILABLE_CHAT_MODELS.items():
                current = " ← current" if info["id"] == current_model else ""
                reasoning_badge = " 🧠" if info.get("reasoning") else ""
                lines.append(
                    f"<b>{alias}</b> — {info['label']}{reasoning_badge}\n"
                    f"  {info['cost']}{current}\n"
                    f"  {info.get('notes', '')}"
                )
            lines.append("\nUse /model &lt;name&gt; to switch.")
            return "\n".join(lines)
    
    if cmd_name == "/domains":
        # Route through LLM for nice formatting
        return None
    
    if cmd_name == "/status":
        from cost_tracker import check_budget, get_daily_spend
        b = check_budget()
        d = get_daily_spend()
        domain = _conversations.get_domain(chat_id)
        
        claude_info = b.get("by_provider", {}).get("claude", {})
        openrouter_info = b.get("by_provider", {}).get("openrouter", {})
        
        live = _get_live_daemon_state()
        
        return (
            f"📊 <b>System Status</b>\n\n"
            f"Active domain: {domain}\n"
            f"Daily spend: ${d['total_usd']:.2f} / ${b['limit']:.2f}\n"
            f"Claude: ${claude_info.get('spent', 0):.2f} / ${claude_info.get('limit', 0):.2f}\n"
            f"OpenRouter: ${openrouter_info.get('spent', 0):.2f} / ${openrouter_info.get('limit', 0):.2f}\n"
            f"Budget OK: {'✅' if b['within_budget'] else '❌'}\n"
            f"Calls today: {d['calls']}\n\n"
            f"🔄 {live}"
        )
    
    if cmd_name == "/daemon":
        live = _get_live_daemon_state()
        # Also try the full status from scheduler
        try:
            from scheduler import get_daemon_status
            s = get_daemon_status()
            state = s.get("state", {})
            cycle = state.get("cycle", 0)
            avg = state.get("avg_score", "?")
            cost = state.get("cycle_cost", 0)
            domains = state.get("domain_results", [])
            domain_lines = "\n".join(
                f"  • {d['domain']}: {d.get('avg_score', '?')}/10 ({d.get('rounds_completed', '?')} rounds)"
                for d in domains
            ) if domains else "  (no domain results)"
            return (
                f"🤖 <b>Daemon Status</b>\n\n"
                f"{live}\n\n"
                f"<b>Last cycle results:</b>\n"
                f"{domain_lines}\n"
                f"Cost: ${cost:.4f} | Avg: {avg}/10"
            )
        except Exception:
            return f"🤖 <b>Daemon Status</b>\n\n{live}"
    
    if cmd_name == "/kitchen":
        """What's cooking right now? Live view of daemon activity."""
        live = _get_live_daemon_state()
        # Get recent cycle history
        history_file = os.path.join(LOG_DIR, "daemon_history.jsonl")
        recent_cycles = []
        if os.path.exists(history_file):
            try:
                with open(history_file) as f:
                    lines = f.readlines()
                for line in lines[-5:]:
                    entry = json.loads(line.strip())
                    c = entry.get("cycle", "?")
                    d = entry.get("domains", [])
                    s = entry.get("avg_score", "?")
                    cost = entry.get("cycle_cost", 0)
                    recent_cycles.append(f"  Cycle {c}: {s}/10 • ${cost:.3f} • {', '.join(d)}")
            except Exception:
                pass
        
        history_text = "\n".join(recent_cycles) if recent_cycles else "  (no history yet)"
        return (
            f"🍳 <b>Kitchen Status</b>\n\n"
            f"{live}\n\n"
            f"<b>Recent cycles:</b>\n{history_text}"
        )
    
    if cmd_name == "/research":
        domain = _conversations.get_domain(chat_id)
        rounds = 1
        if cmd_arg:
            try:
                rounds = max(1, min(int(cmd_arg), 10))  # clamp 1-10
            except ValueError:
                return "Usage: /research [rounds]\nExample: /research 3"

        # Run research cycle in background thread
        def _run_research():
            try:
                from cli.research import run_auto
                run_auto(domain, rounds)
                _send_message(int(chat_id),
                    f"\u2705 Research complete: {rounds} round(s) in <b>{domain}</b>.")
            except Exception as e:
                _send_message(int(chat_id), f"\u274c Research cycle failed: {e}")

        t = threading.Thread(target=_run_research, daemon=True, name=f"research-{domain}")
        t.start()

        return (
            f"\U0001f50d <b>Research Cycle Started</b>\n\n"
            f"Domain: {domain}\n"
            f"Rounds: {rounds}\n\n"
            f"I'll notify you when it's done."
        )

    if cmd_name == "/build":
        if not cmd_arg:
            return (
                "🔨 <b>Build Pipeline</b>\n\n"
                "Usage: /build &lt;instruction&gt;\n\n"
                "Examples:\n"
                "  /build Build a landing page for OLJ employers\n"
                "  /build Create a client portal for web agencies\n\n"
                "The pipeline will:\n"
                "1. Research the niche (Brain)\n"
                "2. Ask for your approval\n"
                "3. Build it (Hands)\n"
                "4. Report the result"
            )
        
        domain = _conversations.get_domain(chat_id)
        instruction = cmd_arg
        
        # Check if pipeline already running for this domain
        from agents.cortex import get_pipeline_status
        active = get_pipeline_status()
        for p in active:
            if p["domain"] == domain:
                return f"⚠️ Pipeline already running for '{domain}' (stage: {p.get('stage', '?')})"
        
        # Start pipeline in background thread
        def _run_pipeline():
            try:
                from agents.cortex import pipeline
                result = pipeline(
                    domain=domain,
                    instruction=instruction,
                    require_approval=True,
                )
                # Final summary already sent via Telegram notifications in pipeline()
                print(f"[TELEGRAM] Pipeline finished: {result.get('stage', '?')} — "
                      f"success={result.get('success')} score={result.get('build_score', 0)}")
            except Exception as e:
                _send_message(int(chat_id), f"❌ Pipeline crashed: {e}")
                print(f"[TELEGRAM] Pipeline error: {e}")
        
        t = threading.Thread(target=_run_pipeline, daemon=True, name=f"pipeline-{domain}")
        t.start()
        
        return (
            f"🚀 <b>Pipeline Started</b>\n\n"
            f"Domain: {domain}\n"
            f"Goal: {instruction}\n\n"
            f"I'll notify you when research is done and ask for approval."
        )
    
    if cmd_name == "/approve":
        from agents.cortex import resolve_approval, get_pending_approvals
        
        pending = get_pending_approvals()
        if not pending:
            return "✅ No pending approvals."
        
        # If cmd_arg specifies a domain, approve that one
        if cmd_arg:
            target_domain = cmd_arg.strip()
        else:
            # Approve the first (and usually only) pending
            target_domain = pending[0]["domain"]
        
        resolved = resolve_approval(target_domain, approved=True)
        if resolved:
            return f"✅ Approved build for <b>{target_domain}</b>. Hands will start building now."
        else:
            return f"❌ No pending approval for '{target_domain}'."
    
    if cmd_name == "/reject":
        from agents.cortex import resolve_approval, get_pending_approvals
        
        pending = get_pending_approvals()
        if not pending:
            return "🛑 No pending approvals."
        
        if cmd_arg:
            target_domain = cmd_arg.strip()
        else:
            target_domain = pending[0]["domain"]
        
        resolved = resolve_approval(target_domain, approved=False)
        if resolved:
            return f"🛑 Rejected build for <b>{target_domain}</b>. Pipeline stopped."
        else:
            return f"❌ No pending approval for '{target_domain}'."
    
    if cmd_name == "/pipeline":
        from agents.cortex import get_pipeline_status, get_pending_approvals
        
        active = get_pipeline_status()
        pending = get_pending_approvals()
        
        if not active and not pending:
            return "📋 No active pipelines or pending approvals."
        
        lines = ["📋 <b>Pipeline Status</b>\n"]
        
        if active:
            lines.append("<b>Active Pipelines:</b>")
            for p in active:
                lines.append(
                    f"  • <b>{p['domain']}</b>: {p.get('stage', '?')} "
                    f"({p.get('instruction', '')[:50]})"
                )
        
        if pending:
            lines.append("\n<b>Awaiting Approval:</b>")
            for p in pending:
                lines.append(
                    f"  • <b>{p['domain']}</b>\n"
                    f"    {p['summary'][:200]}\n"
                    f"    → /approve or /reject"
                )
        
        return "\n".join(lines)
    
    # ── Threads Commands ────────────────────────────────────────────────
    
    if cmd_name == "/threads":
        from tools.threads_client import is_configured as threads_configured
        
        if not threads_configured():
            return (
                "⚠️ <b>Threads API not configured</b>\n\n"
                "Set in .env:\n"
                "  THREADS_ACCESS_TOKEN=...\n"
                "  THREADS_USER_ID=...\n\n"
                "Get these from the Meta Developer Dashboard."
            )
        
        # Sub-commands: /threads search|post|insights|draft|analytics
        sub_parts = cmd_arg.split(None, 1) if cmd_arg else []
        sub_cmd = sub_parts[0] if sub_parts else "help"
        sub_arg = sub_parts[1] if len(sub_parts) > 1 else ""
        
        if sub_cmd == "help" or not cmd_arg:
            return (
                "🧵 <b>Threads Commands</b>\n\n"
                "/threads search &lt;query&gt; — Search for posts\n"
                "/threads post &lt;text&gt; — Publish a post\n"
                "/threads draft &lt;topic&gt; — Generate a post draft\n"
                "/threads insights — Recent engagement stats\n"
                "/threads analytics — Profile-level analytics\n"
                "/threads analyze &lt;query&gt; — Pain point analysis\n"
                "/threads thread &lt;id&gt; — Stats for a specific post\n"
            )
        
        if sub_cmd == "search":
            if not sub_arg:
                return "Usage: /threads search &lt;query&gt;"
            from tools.threads_client import search_threads, ThreadsAPIError
            try:
                results = search_threads(sub_arg, limit=10)
                if not results:
                    return f"🔍 No Threads posts found for: <b>{sub_arg}</b>"
                lines = [f"🔍 <b>Threads Search: {sub_arg}</b>\n"]
                for i, post in enumerate(results[:10], 1):
                    text = (post.get("text") or "")[:150]
                    user = post.get("username", "?")
                    lines.append(f"{i}. @{user}: {text}")
                return "\n".join(lines)
            except ThreadsAPIError as e:
                return f"❌ Search failed: {e}"
        
        if sub_cmd == "post":
            if not sub_arg:
                return "Usage: /threads post &lt;text&gt;\n(max 500 chars)"
            from tools.threads_client import publish_post, ThreadsAPIError
            try:
                result = publish_post(text=sub_arg)
                return f"✅ <b>Posted to Threads!</b>\n\nID: {result.get('id', '?')}"
            except ThreadsAPIError as e:
                return f"❌ Post failed: {e}"
        
        if sub_cmd == "draft":
            if not sub_arg:
                return "Usage: /threads draft &lt;topic&gt;\nExample: /threads draft freelance invoicing pain"
            domain = _conversations.get_domain(chat_id)
            from agents.threads_analyst import generate_post
            from memory_store import load_knowledge_base
            kb = load_knowledge_base(domain)
            kb_text = kb.get("summary", "") if kb else ""
            result = generate_post(
                domain=domain,
                topic=sub_arg,
                knowledge_context=kb_text,
            )
            post_text = result.get("text", "")
            hook = result.get("hook_type", "?")
            eng = result.get("estimated_engagement", "?")
            tags = " ".join(f"#{t}" for t in result.get("hashtags", []))
            return (
                f"📝 <b>Draft Post</b> ({hook} hook, est. {eng} engagement)\n\n"
                f"{post_text}\n\n"
                f"{tags}\n\n"
                f"To publish: /threads post {post_text[:100]}..."
            )
        
        if sub_cmd == "insights":
            from tools.threads_client import get_recent_engagement, ThreadsAPIError
            try:
                data = get_recent_engagement(limit=10)
                top = data.get("top_post")
                top_text = f"\n\n🏆 Top post: {top['text'][:100]}..." if top else ""
                return (
                    f"📊 <b>Recent Threads Engagement</b>\n\n"
                    f"Posts analyzed: {len(data.get('posts', []))}\n"
                    f"Total views: {data['total_views']:,}\n"
                    f"Total likes: {data['total_likes']:,}\n"
                    f"Total replies: {data['total_replies']:,}\n"
                    f"Avg engagement rate: {data['avg_engagement_rate']:.1f}%"
                    f"{top_text}"
                )
            except ThreadsAPIError as e:
                return f"❌ Insights failed: {e}"
        
        if sub_cmd == "analytics":
            from tools.threads_client import get_profile_insights, ThreadsAPIError
            try:
                data = get_profile_insights()
                lines = ["📈 <b>Profile Analytics</b>\n"]
                for metric, value in data.items():
                    lines.append(f"  {metric}: {value:,}" if isinstance(value, int) else f"  {metric}: {value}")
                return "\n".join(lines)
            except ThreadsAPIError as e:
                return f"❌ Analytics failed: {e}"
        
        if sub_cmd == "thread":
            if not sub_arg:
                return "Usage: /threads thread &lt;thread_id&gt;\nGet detailed stats for a specific post."
            from tools.threads_client import get_thread_insights, ThreadsAPIError
            try:
                data = get_thread_insights(sub_arg)
                text_preview = (data.get("text") or "")[:150]
                views = data.get("views", 0)
                likes = data.get("likes", 0)
                replies = data.get("replies", 0)
                reposts = data.get("reposts", 0)
                quotes = data.get("quotes", 0)
                rate = data.get("engagement_rate", 0)
                return (
                    f"🧵 <b>Thread Insights</b>\n\n"
                    f"📝 {text_preview}\n\n"
                    f"👁 Views: {views:,}\n"
                    f"❤️ Likes: {likes:,}\n"
                    f"💬 Replies: {replies:,}\n"
                    f"🔁 Reposts: {reposts:,}\n"
                    f"💭 Quotes: {quotes:,}\n"
                    f"📊 Engagement rate: {rate:.2f}%"
                )
            except ThreadsAPIError as e:
                return f"❌ Thread insights failed: {e}"

        if sub_cmd == "analyze":
            if not sub_arg:
                return "Usage: /threads analyze &lt;query&gt;\nSearches Threads and analyzes pain points."
            domain = _conversations.get_domain(chat_id)
            _send_message(int(chat_id), f"🔍 Searching Threads for '{sub_arg}' and analyzing...")
            
            from tools.threads_client import search_threads, ThreadsAPIError
            from agents.threads_analyst import analyze_pain_points
            from domain_goals import get_goal
            
            try:
                posts = search_threads(sub_arg, limit=25)
                if not posts:
                    return f"No Threads posts found for: {sub_arg}"
                
                goal = get_goal(domain)
                goal_text = goal.get("description") if goal else None
                analysis = analyze_pain_points(domain, sub_arg, posts, goal=goal_text)
                
                lines = [f"🧵 <b>Pain Point Analysis: {sub_arg}</b>\n"]
                lines.append(f"Posts analyzed: {len(posts)}\n")
                
                for pp in analysis.get("pain_points", [])[:5]:
                    lines.append(
                        f"• <b>{pp.get('pain', '?')}</b> (score: {pp.get('score', 0):.1f})\n"
                        f"  User says: \"{pp.get('user_language', '')}\"" 
                    )
                
                if analysis.get("market_signals"):
                    lines.append(f"\n📡 Signals: {', '.join(analysis['market_signals'][:3])}")
                
                lines.append(f"\n{analysis.get('summary', '')[:300]}")
                return "\n".join(lines)
            except ThreadsAPIError as e:
                return f"❌ Analysis failed: {e}"
        
        return f"Unknown sub-command: {sub_cmd}. Use /threads for help."
    
    return None  # Not a recognized command


# ── Main Bot Loop ──────────────────────────────────────────────────────

_bot_running = False
_stop_event = threading.Event()


def run_telegram_bot():
    """Run the Telegram bot with long-polling."""
    global _bot_running
    
    if not TELEGRAM_BOT_TOKEN:
        print("  ❌ TELEGRAM_BOT_TOKEN not set in .env")
        return
    if not TELEGRAM_CHAT_ID:
        print("  ❌ TELEGRAM_CHAT_ID not set in .env")
        return
    
    # Verify bot token works
    try:
        me = _tg_request("getMe")
        bot_name = me["result"]["username"]
        print(f"  🤖 Telegram bot @{bot_name} connected")
    except Exception as e:
        print(f"  ❌ Bot connection failed: {e}")
        return
    
    _bot_running = True
    offset = 0
    
    # Handle SIGINT/SIGTERM
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    
    def _shutdown(sig, frame):
        print("\n  Telegram bot shutting down...")
        _stop_event.set()
    
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    
    allowed_chat_id = str(TELEGRAM_CHAT_ID)
    
    print(f"  📱 Listening for messages from chat_id {allowed_chat_id}...")
    print(f"  Active domain: {DEFAULT_DOMAIN}")
    # Find display name for current model
    _chat_display = MODELS.get('chat', 'unknown')
    for alias, info in AVAILABLE_CHAT_MODELS.items():
        if info['id'] == _chat_display:
            _chat_display = f"{info['label']} ({alias})"
            break
    print(f"  Model: {_chat_display} / Sonnet (orchestrator)")
    print(f"  Press Ctrl+C to stop.\n")
    
    # Notify on Telegram
    _send_message(allowed_chat_id, "🟢 <b>Bot online</b>\nReady to chat.")
    
    try:
        while not _stop_event.is_set():
            try:
                # Long poll (30s timeout)
                updates = _tg_request("getUpdates", {
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": ["message"],
                }, timeout=35)
                
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    
                    msg = update.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "")
                    
                    if not text or not chat_id:
                        continue
                    
                    # Security: only respond to authorized chat
                    if chat_id != allowed_chat_id:
                        logger.warning(f"Unauthorized chat_id: {chat_id}")
                        _send_message(chat_id, "⛔ Unauthorized. This bot only responds to its owner.")
                        continue
                    
                    # Log incoming message
                    username = msg.get("from", {}).get("username", "?")
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] @{username}: {text[:80]}")
                    
                    # Check for /commands first
                    if text.startswith("/"):
                        cmd_response = _handle_command(chat_id, text)
                        if cmd_response:
                            _send_message(int(chat_id), cmd_response)
                            print(f"  [{datetime.now().strftime('%H:%M:%S')}] → Command response sent")
                            continue
                    
                    # Send typing indicator
                    _send_typing(int(chat_id))
                    
                    # Process through LLM pipeline
                    try:
                        response = _process_message(chat_id, text)
                        
                        # Convert markdown to Telegram HTML
                        formatted = _markdown_to_telegram(response)
                        
                        _send_message(int(chat_id), formatted)
                        print(f"  [{datetime.now().strftime('%H:%M:%S')}] → Response sent ({len(response)} chars)")
                        
                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=True)
                        error_msg = f"❌ Error: {str(e)[:300]}"
                        _send_message(int(chat_id), error_msg)
                        print(f"  [{datetime.now().strftime('%H:%M:%S')}] → Error: {e}")
                
            except urllib.error.URLError as e:
                # Network error — retry after brief pause
                if not _stop_event.is_set():
                    logger.warning(f"Network error: {e}")
                    time.sleep(5)
            except Exception as e:
                if not _stop_event.is_set():
                    logger.error(f"Bot loop error: {e}", exc_info=True)
                    time.sleep(5)
    
    finally:
        _bot_running = False
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
        _send_message(allowed_chat_id, "🔴 <b>Bot offline</b>")
        print("  Telegram bot stopped.")


# ── Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print(f"\n{'='*50}")
    print(f"  CORTEX — Telegram Chat Bot")
    print(f"{'='*50}\n")
    run_telegram_bot()
