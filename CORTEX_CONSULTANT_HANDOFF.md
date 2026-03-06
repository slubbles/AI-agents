# Cortex — Complete System Documentation

> **Comprehensive Handoff Document for Consultants**  
> **Version:** March 2026 (Session 23 — Full Audit Revision)  
> **Prior Version:** Session 13 / March 4, 2026 (9 sessions stale — this replaces it)  
> **Author:** GitHub Copilot (AI co-builder)  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Vision & Goals](#2-vision--goals)
3. [Naming — Brain & Hands](#3-naming--brain--hands)
4. [The Transistor Analogy](#4-the-transistor-analogy)
5. [5 Self-Learning Layers (Brain)](#5-5-self-learning-layers-brain)
6. [Architecture — Full Diagram](#6-architecture--full-diagram)
7. [Brain Agent Inventory](#7-brain-agent-inventory)
8. [Hands System Inventory](#8-hands-system-inventory)
9. [Signal Intelligence Pipeline](#9-signal-intelligence-pipeline-new-since-session-13)
10. [Orchestrator Layer](#10-orchestrator-layer)
11. [Identity Layer](#11-identity-layer)
12. [MCP Integration](#12-mcp-integration-new-since-session-13)
13. [Threads + Social Pipeline](#13-threads--social-pipeline-new-this-session)
14. [Sandboxed Execution (Chat + Telegram)](#14-sandboxed-execution-new-session-22)
15. [Lifebook Goal Framework](#15-lifebook-goal-framework-new-session-22)
16. [CLI & Telegram Interface](#16-cli--telegram-interface)
17. [Infrastructure](#17-infrastructure)
18. [Development Journey — Sessions 1–23](#18-development-journey--sessions-1-23)
19. [VPS State](#19-vps-state)
20. [Known Issues & Technical Debt](#20-known-issues--technical-debt)
21. [Pending Integrations (upnext.md Audit)](#21-pending-integrations-upnextmd-audit)
22. [Codebase Statistics](#22-codebase-statistics)
23. [Roadmap — What's Next](#23-roadmap--whats-next)
24. [Appendix: File Inventory](#24-appendix-file-inventory)

---

## 1. Executive Summary

Cortex is a dual-agent autonomous system — **Agent Brain** (self-learning research engine) + **Agent Hands** (coding execution engine) — being built toward fully autonomous business operation: research a domain → validate demand → build a product → deploy → market → acquire customers → learn → repeat.

| Metric | Value |
|--------|-------|
| **Git HEAD** | `8965db2` |
| **Sessions** | 23 (Sessions 1–22 documented; current = 23) |
| **Production Python** | 135 files / 52,147 lines |
| **Test Python** | 45 files / 29,827 lines / 2,092 test functions |
| **Actively Run Tests** | 147 (test_core: 93, test_integration_wiring: 54) |
| **VPS** | 207.180.219.27 (Contabo Ubuntu 24.04.3) |
| **Active Services (VPS)** | cortex-telegram.service (running) |
| **Daily Budget** | $7.00 ($2 Claude + $5 OpenRouter) |
| **Models** | T1=DeepSeek V3.2, T2=Grok 4.1 Fast, T3=Claude Sonnet 4, T4=Gemini 2.0 Flash |
| **5 Self-Learning Layers** | All proven and operational |

**What changed since last handoff (Session 13, March 4, 2026):**
- Signal Intelligence pipeline (Sessions 14–15) — pain point discovery → opportunity scoring → build specs → Brain bridge
- Signal enrichment + chat tools (Session 19) — auto-enrichment wired into daemon cycle
- PTC pre-wired (Session 18) — flip one env var when Anthropic credits available
- MCP tools wired into researcher + executor (Session 20)
- Crawl-to-KB pipeline wired into daemon (Session 20)
- Dataset loader added to Hands planner (Session 20)
- Dashboard API live (Session 20 — FastAPI running, not yet deployed to VPS)
- Revenue domain seeds + Vercel auto-deploy (Session 21)
- Sandboxed execution in Chat + Telegram (Session 22)
- Lifebook goal framework in domain_goals (Session 22)
- THREADS.MD image pipeline — screenshot + chart posts (Session 23)
- **Fixed:** 3 stale import issues from Session 13 (sync.py, project_orchestrator.py, scheduler.py page_type)

---

## 2. Vision & Goals

Cortex is not a chatbot. Not a wrapper around an LLM. Not a personal assistant.

It is an **autonomous system that researches, builds, markets, and makes money** — learning from every cycle.

**The pipeline it will eventually run without human input:**
1. Research the domain (finds opportunities, gaps, problems from Reddit/forums/Twitter)
2. Validate demand (tests if real humans care and will pay)
3. Build the solution (code, landing pages, SaaS products)
4. Deploy and market (SEO, outreach, content, Threads posts)
5. Acquire customers and generate revenue
6. Learn from outcomes and compound intelligence across domains
7. Repeat — getting cheaper and smarter each cycle

**First target:** Productized Next.js services on OnlineJobsPH ($250–$500 per page, turn-key)  
**Next:** SaaS factory running parallel products, kill losers fast, double down on winners  
**End state:** Point at any domain → system handles 100% autonomously

---

## 3. Naming — Brain & Hands

**Agent Brain** = self-learning research engine
- Researches markets, scores outputs, remembers, plans, evolves strategies
- Layers 1–5 of self-learning all proven

**Agent Hands** = execution engine
- Codes, builds, deploys, debugs, verifies
- Currently: coding domain (web/full-stack)
- Future: design, devops, SEO, outreach

**Why these names:**
- Brain thinks and accumulates knowledge
- Hands execute and produce artifacts
- The Brain tells the Hands what to build; the Hands tell the Brain what worked

---

## 4. The Transistor Analogy

"One autonomous thing that does one job reliably is more powerful than 26 half-built agents."

The architect's vision: one system that, given a domain name, produces a live URL with real auth, real database, core feature working, beautiful design, tested end-to-end — with zero lines of code written by the human.

**That is the transistor.** Everything else follows from having one that works.

**Scaling stages:**
- Stage 1 (NOW): One Brain + Hands, one domain at a time
- Stage 2 (3–6mo): Multiple domains running in parallel, each in isolation
- Stage 3 (6–12mo): Multiple VPS instances, each running one domain
- Stage 4 (1–2yr): Instances teaching each other cross-domain patterns
- Stage 5 (2–5yr): Meta-Orchestrator finding connections across instances

The identity layer defined today becomes the values of the entire network at Stage 5. **Build the transistor right first.**

---

## 5. 5 Self-Learning Layers (Brain)

All 5 layers are **fully implemented and proven.**

### Layer 1: Knowledge Accumulation
- Agent acts → output stored → retrieved on next run
- Files: `memory_store.py`, `memory/` directory (per-domain JSON)
- All outputs scored, stored with metadata (question, domain, strategy version, timestamp)

### Layer 2: Evaluated Knowledge
- Critic scores every output on 5 dimensions (rubric below)
- Score stored alongside output — retrieval is score-weighted
- Files: `agents/critic.py` (511 lines), `prescreen.py` (cheap pre-filter)

**Scoring rubric:**
| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Accuracy | 30% | Factual correctness |
| Depth | 20% | Beyond surface-level |
| Completeness | 20% | All important angles |
| Specificity | 15% | Concrete data, numbers, sources |
| Intellectual Honesty | 15% | Flags uncertainty, separates fact from speculation |

Threshold: ≥ 6.0 to accept. Below 6 → retry with critique feedback (max 2 retries). Prescreen: accept ≥ 7.5, reject ≤ 3.5, escalate 3.5–7.5 to Claude critic.

### Layer 3: Behavioral Adaptation
- Meta-Analyst extracts patterns from scored outputs → rewrites strategy documents
- Strategy = natural language instructions the agent reads and follows on next run
- Runs every 3 accepted outputs (evolve cooldown). `--evolve` flag forces it.
- Files: `agents/meta_analyst.py` (410 lines), `strategies/` directory

### Layer 4: Strategy Evolution
- Strategies version-controlled: `pending → trial → active` lifecycle
- New strategies saved as "pending" — must be human-approved before trial
- Rollback if trial strategy scores >20% below current best
- Files: `strategy_store.py`, strategies stored per-domain

### Layer 5: Cross-Domain Transfer
- Insights from Domain A abstracted into general principles → seeds Domain B
- The system compounds intelligence across domains, not just within them
- Files: `agents/cross_domain.py` (629 lines), `strategies/_principles.json`

---

## 6. Architecture — Full Diagram

```
╔══════════════════════════════════════════════════════════════╗
║                     IDENTITY LAYER                           ║
║  goals.md | ethics.md | boundaries.md | risk.md | taste.md   ║
║  design_system.md | visual_rubric.md | skills/ (10 files)    ║
╚══════════════════════╦═══════════════════════════════════════╝
                       ║
           ╔═══════════╩══════════╗
           ║      ORCHESTRATOR    ║
           ║ scheduler.py (1867L) ║
           ║ watchdog.py (700L)   ║
           ║ sync.py (400L)       ║
           ║ cost_tracker.py      ║
           ║ monitoring.py        ║
           ╚════╦═══════╦═════════╝
                ║       ║
        ╔═══════╩╗     ╔╩════════════╗
        ║  BRAIN ║     ║    HANDS    ║
        ╠════════╣     ╠═════════════╣
        ║researcher    ║planner      ║
        ║critic        ║executor     ║
        ║meta_analyst  ║validator    ║  
        ║cross_domain  ║visual_gate  ║
        ║question_gen  ║visual_eval  ║
        ║synthesizer   ║project_orch ║
        ║verifier      ║pattern_learn║
        ║consensus     ║exec_meta    ║
        ║threads_analyst║30+ support ║
        ║orchestrator  ║modules      ║
        ╚═══════╦═══════╩═════════════╝
                ║
        ╔═══════╩══════════╗
        ║   SIGNAL LAYER   ║
        ║signal_collector  ║
        ║opportunity_scorer║
        ║signal_bridge     ║
        ╚═══════╦══════════╝
                ║
        ╔═══════╩══════════╗
        ║  LEARNING LAYER  ║
        ║memory_store      ║
        ║strategy_store    ║
        ║knowledge_graph   ║
        ║research_lessons  ║
        ║rag/ (ChromaDB)   ║
        ╚══════════════════╝
```

**Model routing (4 tiers):**
| Tier | Model | Use Case |
|------|-------|----------|
| T1 | DeepSeek V3.2 (OpenRouter) | Cheapest bulk work |
| T2 | Grok 4.1 Fast (OpenRouter) | Research, prescreen, progress |
| T3 | Claude Sonnet 4 (Anthropic) | Critic, meta-analyst, reasoning |
| T4 | Gemini 2.0 Flash (OpenRouter) | Visual tasks, fallback |

**Protocol layer:** `protocol.py` — 10 message types (TASK_REQUEST, TASK_RESULT, CRITIQUE_REQUEST, CRITIQUE_RESULT, STRATEGY_UPDATE, STRATEGY_BROADCAST, HEALTH_CHECK, HEALTH_RESPONSE, ALERT, SYNC)

---

## 7. Brain Agent Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `agents/researcher.py` | 723 | Web search + structured findings (date-aware, tool use loop, PTC-ready) |
| `agents/critic.py` | 511 | 5-dimension rubric scoring; accepts/rejects outputs |
| `agents/meta_analyst.py` | 410 | Analyzes scored outputs → rewrites strategy documents (Layer 3) |
| `agents/cross_domain.py` | 629 | Extracts general principles → seeds new domains (Layer 5) |
| `agents/question_generator.py` | 417 | Reads knowledge gaps + objectives → generates next research questions |
| `agents/synthesizer.py` | 439 | Integrates findings into domain knowledge base |
| `agents/verifier.py` | 337 | Prediction tracking + output verification |
| `agents/consensus.py` | 284 | Multi-agent agreement (built, disabled — CONSENSUS_ENABLED=False) |
| `agents/orchestrator.py` | 582 | Domain routing + agent coordination |
| `agents/cortex.py` | 1,236 | Strategic orchestrator + full pipeline (Brain→approve→Hands→deploy) |
| `agents/threads_analyst.py` | ~600 | Threads content strategy, post generation, screenshot/chart posts |

**Prescreen layer:**
- `prescreen.py` — cheap Grok-4.1 pre-filter before Claude critic
- Accept threshold: ≥ 7.5 (skip Claude altogether)
- Reject threshold: ≤ 3.5 (reject without Claude)
- Escalate: 3.5–7.5 (Claude makes final call)
- Estimated savings: ~40% Claude critic cost

---

## 8. Hands System Inventory

The Hands system gives the Brain the ability to write code, run commands, deploy projects, and learn from execution outcomes. 30+ components.

**Core execution pipeline:**
```
cortex.py:pipeline()
  → hands/planner.py:plan()         — Structured build plan (JSON)
  → [Human approval gate]           — Review plan before execution
  → hands/executor.py:execute_plan() — Multi-turn tool execution (24 tools)
  → hands/visual_gate.py             — Mid-build screenshot → Claude Vision → fix
  → hands/validator.py:validate_execution() — Output verification
  → [agents/cortex.py post-build]    — Vercel auto-deploy if VERCEL_TOKEN set
```

**24 Hands tools (executor):**
write_file, read_file, append_to_file, delete_file, create_directory, move_file, copy_file, list_directory, run_command, run_test_command, search_codebase, find_and_replace, patch_file, web_search, fetch_url, screenshot_page, check_build_quality, get_project_state, read_portfolio, apply_identity_skills, consult_architect, check_visual_standard, wait, no_op

**Key Hands modules:**

| File | Lines | Purpose |
|------|-------|---------|
| `hands/planner.py` | 594 | Structured plan generation with reality check |
| `hands/executor.py` | 932 | Multi-turn tool execution loop |
| `hands/validator.py` | 798 | Output verification + test running |
| `hands/visual_gate.py` | 344 | Mid-build screenshot → Vision → fix cycle |
| `hands/visual_evaluator.py` | 634 | Claude Vision scoring of UI outputs |
| `hands/pattern_learner.py` | 497 | Learning from execution outcomes |
| `hands/project_orchestrator.py` | 832 | Multi-phase decomposition (plan → build → validate) |
| `hands/exec_meta.py` | 506 | Execution strategy evolution |
| `hands/error_analyzer.py` | 192 | Root cause analysis on failures |
| `hands/task_generator.py` | 332 | Generate tasks from domain goals |
| `hands/artifact_tracker.py` | 365 | Track produced artifacts |
| `hands/checkpoint.py` | 172 | Save/restore mid-build progress |
| `hands/code_exemplars.py` | 247 | Example patterns injected into prompts |
| `hands/exec_cross_domain.py` | 254 | Cross-domain execution pattern transfer |
| `hands/exec_memory.py` | 142 | Execution memory store |
| `hands/exec_templates.py` | 280 | Reusable execution templates |
| `hands/feedback_cache.py` | 206 | Cache mid-build corrections |
| `hands/file_repair.py` | 246 | Auto-fix common file issues |
| `hands/mid_validator.py` | 264 | Mid-execution quality gates |
| `hands/output_polisher.py` | 223 | Clean up output artifacts |
| `hands/plan_cache.py` | 226 | Cache similar build plans |
| `hands/plan_preflight.py` | 284 | Validate plans before execution |
| `hands/retry_advisor.py` | 266 | Retry strategies for failed steps |
| `hands/strategy_assembler.py` | 226 | Assemble execution strategies |
| `hands/consultant.py` | ~100 | `_consult` tool — agent asks human mid-build |
| `hands/exec_analytics.py` | 266 | Execution metrics |
| `hands/constants.py` | 53 | Shared constants |

**Visual feedback loop:**
- During frontend builds, `visual_gate.py` takes Playwright screenshot → encodes as base64 → sends to Claude Vision → gets structured critique → injects feedback into executor → agent self-corrects
- `visual_evaluator.py` scores against identity/visual_scoring_rubric.md
- Confirmed working in Objective 5 (Session 10)

**Post-build auto-deploy (Session 21):**
- After successful Hands build, `agents/cortex.py:pipeline()` checks for `package.json` + `VERCEL_TOKEN`
- If both present: runs `npx vercel --prod --yes`, stores deploy URL in result, sends Telegram notification
- **Setup needed:** `export VERCEL_TOKEN=<token>` on VPS

---

## 9. Signal Intelligence Pipeline (NEW since Session 13)

The Signal Intelligence pipeline transforms Reddit/forum pain points into actionable build specs and research questions — connecting external signals to both Brain (research) and Hands (build).

**Full pipeline:**
```
signal_collector.py
  → RSS/Atom feeds (Reddit, HN, forums)
  → parse_post() → store to SQLite
  → enrich_top_posts() → Scrapling re-checks engagement (upvotes, comments)
  → check_engagement_changes() → tracks growing vs dying opportunities
        ↓
opportunity_scorer.py
  → score_opportunity() → weighted scoring (pain severity, urgency, market size...)
  → generate_build_spec() → DeepSeek generates product spec (features, MVP scope, competitors, gap)
  → _save_build_spec() → saves to logs/build_specs/ (JSON, atomic write)
        ↓
signal_bridge.py
  → generate_signal_questions() → converts top opportunities into Brain research questions
  → get_signal_domain_for_category() → maps signal category to Brain domain
        ↓
scheduler.py:_run_signal_cycle()
  → Step 1: collect() — RSS to DB
  → Step 2: score_all() — score unanalyzed posts
  → Step 2.5: enrich_top_posts() — Scrapling enrichment on top 20 (non-fatal if fails)
  → Step 3: generate_signal_questions() — bridge to Brain
  → Step 4: check_engagement_changes() — every 3rd cycle
  → Step 5: alert on top opportunities
  → Step 6: auto-generate build specs for score ≥ 70
  → Step 7: create_task() — Hands can pick up build specs
        ↓
sync.py:create_task()
  → type="build", priority="high"
  → Hands executor can pick up and build
```

**Current VPS state:** 493+ posts collected, 50+ analyzed, top score 90/100. Daemon DISABLED (daemon = disabled as of last VPS check).

**Files:**
- `signal_collector.py` — RSS collection, Scrapling enrichment, engagement tracking
- `opportunity_scorer.py` — Scoring algorithm, build spec generation
- `signal_bridge.py` — Signal → Brain research question bridge
- `cli/signals_cmd.py` — Manual CLI access to the full pipeline

---

## 10. Orchestrator Layer

The Orchestrator keeps the system stable and on-track for 24/7 operation.

**Scheduler (`scheduler.py`, 1,867 lines):**
- Multi-domain loop: iterates active domains, runs research cycle per domain
- Signal cycle: `_run_signal_cycle()` every 6 hours
- Build spec auto-generation: for signals scoring ≥ 70
- Exponential backoff on failures: `min(base_sleep × 2^(failures-1), 300s)` (Symphony formula)
- `page_type="app"` set on execute_plan() calls (fixes Session 13 known issue)

**Watchdog (`watchdog.py`, ~700 lines):**
- States: running, paused, budget_halt, error_halt, cooldown, disabled
- Circuit breaker: 3 consecutive failures → halt
- Daily budget enforcer: halts at $7.00 daily spend ($10.50 hard ceiling)
- Logs full state to watchdog.json

**Sync (`sync.py`, ~400 lines):**
- `create_task(domain, task)` — Brain creates task for Hands
- `get_pending_tasks(domain)` — Hands polls for work
- `complete_task(task_id)` — Hands marks done
- Stale imports **fixed** (Session 13 issue resolved): now uses `execute_plan`, `validate_execution` via lazy imports

**Monitoring (`monitoring.py`):**
- Score trend detection (drop alerts)
- Domain staleness detection
- Health checks between cycles

**Loop Guard (`loop_guard.py`):**
- Consecutive failure detection (3× → halt)
- Question similarity detection (> 70% similarity → flag)
- Cost velocity detection (> 80% of budget in < 20% of time → slow down)
- Score regression detection
- Same-error repetition detection
- **Pure logic — no LLM calls**

**Progress Tracker (`progress_tracker.py`):**
- Runs every 5 accepted outputs
- Goal-distance assessment via Grok 4.1 (cheap)
- Returns: distance score, verdict, key gaps, momentum

---

## 11. Identity Layer

The Identity Layer is what makes Cortex produce outputs aligned to the architect's taste and standards — not just "working" but *good*.

**Files in `identity/`:**

| File | Size | Purpose |
|------|------|---------|
| `goals.md` | 2,341 lines | What Cortex is trying to achieve |
| `ethics.md` | 2,111 lines | What Cortex will never do |
| `boundaries.md` | 3,950 lines | Operational constraints |
| `risk.md` | 2,346 lines | Risk tolerance and budget rules |
| `taste.md` | 2,853 lines | Aesthetic preferences, copy standards |
| `design_system.md` | 13,926 lines | Full design language (colors, typography, components) |
| `marketing_design.md` | 13,575 lines | Marketing page patterns |
| `visual_scoring_rubric.md` | 6,510 lines | How to score a UI screenshot |
| `react_best_practices.md` | 2,931 lines | React/Next.js coding standards |
| `web_interface_guidelines.md` | 5,000 lines | Web interface standards |

**Skills system (`identity/skills/`):**
- 10 skill domains (not all listed — varies by session additions)
- `skills_loader.py` — lazy-loads skills into agent prompts based on task type
- `identity_loader.py` — loads identity files into planner/executor system prompts

---

## 12. MCP Integration (NEW since Session 13)

The MCP (Model Context Protocol) gateway allows Cortex to call external tool servers via Docker containers.

**Gateway files:**
- `mcp/gateway.py` — MCP client: start containers, list tools, call tools
- `mcp/docker_manager.py` — Docker container lifecycle management
- `mcp/protocol.py` — MCP protocol implementation
- `mcp/tool_bridge.py` — `register_mcp_tools_in_registry()` — injects MCP tools into Hands tool registry
- `mcp/context_router.py` — `select_tools(task)` — picks most relevant MCP tools for a task
- Total: ~1,739 lines

**Configured servers (`mcp_servers.json`):**
| Server | Status | Purpose |
|--------|--------|---------|
| `filesystem` | disabled | File read/write (redundant with Hands tools) |
| `github` | enabled | GitHub API — repos, issues, PRs, search |
| `fetch` | disabled | URL fetching (redundant with Scrapling) |
| `postgres` | disabled | PostgreSQL queries |
| `puppeteer` | disabled | Browser automation (redundant with stealth browser) |
| `idea-reality` | enabled | Pre-build reality check — scans GitHub/HN/npm/PyPI/ProductHunt |

**Wired (Session 20):**
- `agents/cortex.py` calls `register_mcp_tools_in_registry()` before builds
- `agents/researcher.py` calls `get_mcp_research_tools()` in tool loop
- Only `github` and `idea-reality` are enabled — others disabled to avoid Docker dependency

**Gap remaining:** MCP servers start via Docker. Docker must be running on VPS and containers must be pulled. Until that's done, MCP tools fail gracefully (researchers fall back to web_search).

---

## 13. Threads + Social Pipeline (NEW this session)

The Threads pipeline enables Cortex to post research insights, build screenshots, and score charts to the architect's Threads account.

**Files:**
- `tools/threads_client.py` — Full Threads API client + tool definitions
- `tools/image_publisher.py` — Image pipeline (screenshot → Vercel Blob → Threads)  *(NEW Session 23)*
- `agents/threads_analyst.py` — Content strategy, post generation, narrator hooks

### threads_client.py capabilities:
```python
# Text post
publish_post(text)

# Reply to thread
reply_to_thread(thread_id, text)

# Search Threads for topic
search_threads(keyword, limit)

# Get post analytics
get_thread_insights(thread_id)

# Get profile metrics
get_profile_insights()

# Get recent engagement summary
get_recent_engagement()
```

**Tool definitions (for LLM tool-use):**
- `THREADS_POST_TOOL` — post text
- `THREADS_SEARCH_TOOL` — search
- `THREADS_INSIGHTS_TOOL` — analytics
- `THREADS_SCREENSHOT_POST_TOOL` — screenshot URL + post text  *(NEW)*
- `THREADS_CHART_POST_TOOL` — score chart + post text  *(NEW)*

### image_publisher.py capabilities (NEW Session 23):
The missing piece from THREADS.MD — images require a public HTTPS URL, so local bytes need Vercel Blob as a bridge.

```python
# Check if Vercel Blob is configured
blob_configured() → bool  # True when BLOB_READ_WRITE_TOKEN is set

# Upload image bytes → get public URL
upload_to_vercel_blob(image_bytes, filename) → "https://blob.vercel-storage.com/..."

# Screenshot a page → upload → post to Threads
capture_and_post(
    page_url,        # URL to screenshot
    post_text,       # Text for the Threads post  
    full_page=False, # Full-page vs viewport screenshot
    retina=True      # 2× DPR = 2800×1800px
) → {success, url, threads_post_id}
# Primary: Playwright 2× Retina; Fallback: agent-browser CLI

# Generate score chart → upload → post
generate_score_chart(dates, scores, title) → bytes | None  # None if matplotlib missing
post_with_chart(post_text, dates, scores, title) → {success, url, threads_post_id}
```

**Design details:**
- Pure stdlib for Vercel Blob upload (no httpx/requests dependency)
- Playwright primary (2800×1800px retina); agent-browser fallback
- matplotlib dark theme (#1a1a2e background, #e94560 line) for score charts
- Graceful degradation: if `blob_configured()=False`, falls back to text-only post

### threads_analyst.py narrator hooks (NEW Session 23):
```python
# Called after a successful Hands build
post_build_screenshot(page_url, post_text, full_page=False)
→ tries screenshot post; falls back to text if Blob not configured

# Called after enough research outputs accumulate
post_score_chart(domain, post_text)
→ loads KB outputs → extracts dates + scores → calls post_with_chart
→ falls back to text if matplotlib or Blob missing
```

**Setup needed:** `BLOB_READ_WRITE_TOKEN=<token>` in `.env` (Vercel Blob write token from dashboard.vercel.com)

---

## 14. Sandboxed Execution (NEW Session 22)

Both CLI chat mode and Telegram can now execute code, restart services, run tests, and patch files — with security sandboxing.

### New CHAT_TOOLS (in `cli/chat.py`):

| Tool | What it does | Sandbox constraint |
|------|--------------|-------------------|
| `patch_file` | Edit a file in-place (old→new string replacement) | Path must be under `agent-brain/` |
| `control_service` | Start/stop/restart/status a systemd service | Only `cortex-*` services |
| `tail_log` | Read last N lines of a log file | Only `logs/` directory |
| `run_tests` | Run pytest on a test file pattern | Only tests/ directory; env whitelist |
| `run_safe_command` | Run a shell command | Prefix whitelist only (git status/log/diff, python -m pytest, etc.) |

Total CHAT_TOOLS: 37

### New Telegram /commands (in `telegram_bot.py`):

| Command | What it does |
|---------|-------------|
| `/daemon [start|stop|restart|status]` | Control cortex-daemon.service |
| `/services` | List all cortex-* service states |
| `/logs [n]` | Read last N lines from daemon log |
| `/logcat [daemon|telegram|dashboard] [n]` | Tail a specific service log |
| `/tests` | Run test_core.py + test_integration_wiring.py in background |
| `/patch <file>` | Patch a file (prompts for old/new string) |
| `/editlog` | Show recent AI self-edits |

---

## 15. Lifebook Goal Framework (NEW Session 22)

Domain goals upgraded from a single string to a full structured record aligned to the architect's Lifebook methodology.

### New schema in `domain_goals.py`:

```python
{
    "goal": str,                    # One-sentence measurable target
    "what_i_want": str,             # Desired end state
    "what_i_dont_want": str,        # Failure modes to avoid
    "solution": str,                # Strategic approach
    "objectives": [                 # Numbered sub-goals
        {"id": 1, "text": str, "done": bool}
    ],
    "monthly_priority": str,        # One focus for the current 30-day window
    "task_queue": [str],            # FIFO work queue
    "audit_log": [                  # History of audits
        {"date": str, "verdict": str, "notes": str}
    ]
}
```

### New helper functions:
- `set_goal_structured(domain, goal, what_i_want, what_i_dont_want, solution, monthly_priority)`
- `add_objective(domain, text)` / `complete_objective(domain, obj_id)`
- `set_monthly_priority(domain, priority)`
- `push_task(domain, task)` / `pop_task(domain) → str | None`
- `audit_goal(domain, verdict, notes)`
- `get_active_objectives(domain) → [{"id": int, "text": str}]`
- `get_goal_record(domain) → full dict`
- Backward compat: `set_goal(domain, goal_str)` / `get_goal(domain)` still work

### question_generator.py integration:
- `_build_generator_prompt()` now injects objectives, monthly_priority, task_queue into LLM system prompt
- Researcher generates questions aimed at completing specific objectives
- Questions prioritized by monthly focus area

---

## 16. CLI & Telegram Interface

### CLI commands (`python main.py [flags]`):

| Flag | Purpose |
|------|---------|
| `--domain X` | Set active domain |
| `--status` | Show domain status, scores, strategy version |
| `--evolve` | Force meta-analyst run now |
| `--rollback` | Rollback to previous strategy |
| `--approve VERSION` / `--reject VERSION` | Approve/reject pending strategy |
| `--diff V1 V2` | Diff two strategy versions |
| `--audit` | Full audit log |
| `--budget` | Budget status |
| `--principles` | Show cross-domain principles |
| `--principles --extract` | Extract + save new principles |
| `--transfer DOMAIN [--hint Q]` | Transfer principles to new domain |
| `--next` | Generate next research question |
| `--auto [--rounds N]` | Auto research loop |
| `--progress` | Goal-distance assessment |

### CLI subcommands (`cli/` modules):
- `research.py` — research loop
- `chat.py` — interactive chat mode (37 tools)
- `execution.py` — run a build task
- `project.py` — multi-phase project orchestration
- `knowledge.py` — KB queries, graph visualization
- `signals_cmd.py` — signal intelligence pipeline
- `strategy.py` — strategy management
- `browser_cmd.py` — browser automation
- `deploy_cmd.py` — VPS deployment
- `infrastructure.py` — service management
- `tools_cmd.py` — tool registry, MCP tools
- `vault.py` — credential vault

### Telegram commands (`telegram_bot.py`):

| Command | Purpose |
|---------|---------|
| `/start` | Help text, all commands |
| `/status` | Domain status + budget |
| `/research [domain] [question]` | Manual research trigger |
| `/build [spec]` | Trigger a Hands build |
| `/threads [sub]` | Threads analytics, post, draft, analyze, search, thread |
| `/signals` | Signal intelligence status |
| `/daemon [action]` | Control daemon service |
| `/services` | List cortex-* service states |
| `/logs [n]` | Tail daemon log |
| `/logcat [svc] [n]` | Tail specific log |
| `/tests` | Run test suite |
| `/patch <file>` | Edit a file |
| `/editlog` | Recent AI self-edits |

---

## 17. Infrastructure

**Database (`db.py` — SQLite):**
- Tables: research_outputs, costs, alerts, health_checks, signal_posts, build_specs
- All writes use `atomic_json_write()` for corruption-safe updates
- Dashboard API reads from same DB

**Cost tracking (`cost_tracker.py`):**
- Per-provider budgets: Anthropic $2/day, OpenRouter $5/day
- Hard ceiling: $10.50/day (watchdog blocks on this)
- Full audit trail: every LLM call logged with model, tokens, cost, domain

**LLM Router (`llm_router.py`):**
- `call_llm(model, system, messages, ...)` — unified interface
- Routes to Anthropic (T3) or OpenRouter (T1/T2/T4) based on model prefix
- PTC-ready: `betas` param → `client.beta.messages.create()` when provided
- LLM cache: `utils/llm_cache.py` (configurable via `LLM_CACHE_ENABLED`)

**Browser (`browser/stealth_browser.py`):**
- Playwright with fingerprint spoofing, human-like behavior, session persistence
- Used as fallback in `tools/web_fetcher.py` when Scrapling fails
- Also: `agent-browser` CLI wrapper (for environments without Playwright Python)

**RAG / Vector Search (`rag/`):**
- `rag/embeddings.py` — sentence-transformers embeddings
- `rag/vector_store.py` — ChromaDB vector store
- `rag/retrieval.py` — semantic search, cross-domain search, duplicate detection
- Integrated: `memory_store.retrieve_relevant()` calls RAG when `RAG_ENABLED=true`
- Gap: RAG index not auto-updated — new outputs not auto-indexed (needs `--rebuild-index`)

**Dashboard (`dashboard/`):**
- `dashboard/api.py` (784 lines) — FastAPI backend
- Routes: `/api/overview`, `/api/budget`, `/api/domains`, `/api/signals`, `/api/exec`, SSE events
- `dashboard/frontend/` — Next.js frontend
- **Status: Built but not deployed.** Not running on VPS. Not accessible externally.

**Utilities (`utils/`):**
- `retry.py` — exponential backoff with jitter
- `rate_limiter.py` — per-provider rate limiting
- `llm_cache.py` — response caching
- `credential_vault.py` — Fernet-encrypted secret storage
- `atomic_write.py` — corruption-safe file writes

---

## 18. Development Journey — Sessions 1–23

### Session Timeline

| Session | Date | Key Deliverable | Commit |
|---------|------|-----------------|--------|
| 1 | Feb 28 | Initial architecture, memory_store, strategy_store | — |
| 2 | Mar 1 | Critic + prescreen + loop_guard | — |
| 3 | Mar 1 | Meta-analyst (Layer 3) | — |
| 4 | Mar 1 | Cross-domain transfer (Layer 5) | — |
| 5 | Mar 1 | Question generator + auto mode | — |
| 6 | Mar 1 | Strategy evolution (Layer 4) | — |
| 7 | Mar 1 | Agent Hands framework | — |
| 8 | Mar 1 | Planner + Executor (24 tools) | — |
| 9 | Mar 1 | Validator + progress tracker | — |
| 10 | Mar 1 pm | Visual gate + visual evaluator | — |
| 11 | Mar 1 eve | Protocol layer + cost tracking | — |
| 12 | Mar 2 | ideal-thoughts.md analysis, gap audit | — |
| 13 | Mar 4 | **Signal Intelligence masterplan; last handoff doc** | `f0e85fd` |
| 14 | Mar 5 | Signal Intelligence pipeline (9 objectives) | `a698872` |
| 15 | Mar 6 | Progress logging convention established | — |
| 16 | Mar 6 | 12 external resources evaluated (PTC, Symphony) | — |
| 17 | Mar 6 | Tool input_examples; Symphony backoff in scheduler | `08016aa` |
| 18 | Mar 7 | PTC pre-wired (flip PTC_ENABLED when credits available) | `985c44c` |
| 19 | Mar 6 | Signal enrichment → daemon; /threads thread cmd; 3 chat tools | `297b522` |
| 20 | Mar 6 | MCP wired; crawl-to-KB; dataset loader; dashboard API live | `3d962de` |
| 21 | Mar 6 | Revenue domain seeds; post-build Vercel auto-deploy | `a516c9b` |
| 22 | May 30 | Sandboxed execution (5 tools + 7 Telegram cmds); Lifebook goals | `8f1a4d7` + `964347a` |
| 23 | Current | Beads/Orchestrator research; THREADS.MD image pipeline | `8965db2` |

### Objectives Completed (Hands hardening arc, Sessions 7–13)
1. ✅ Bug sweep — 22 test failures fixed
2. ✅ Prompt quality — identity + skills injection
3. ✅ Protocol layer — 10 message types
4. ✅ Playwright integration — agent-browser CLI wrapper
5. ✅ Visual standard — vision-based scoring in validator

### Key Milestones
- **Score trajectory proven:** 5.4 → 7.1 → 7.7 via strategy evolution (Layer 3 working)
- **Signal Intelligence:** 493+ posts, 50+ analyzed, top score 90/100
- **Visual pipeline:** confirmations of screenshot → Vision fix working in test
- **PTC:** Pre-wired, zero activation cost, activates with `PTC_ENABLED=true`
- **MCP:** Wired to researcher + executor, 2 servers enabled (github, idea-reality)
- **Threads:** Full social posting pipeline including images and charts
- **Sandboxed execution:** CLI chat and Telegram can both self-modify Cortex
- **Lifebook goals:** Research is now objective-directed, not topic-driven

---

## 19. VPS State

| Property | Value |
|----------|-------|
| **IP** | 207.180.219.27 |
| **Provider** | Contabo VPS |
| **OS** | Ubuntu 24.04.3 LTS |
| **User** | root |
| **Last confirmed sync** | `8965db2` (set as of session end) |

### Service Status

| Service | Status |
|---------|--------|
| cortex-daemon | **DISABLED** (budget_halt as of March 3; needs re-enable after budget reset) |
| cortex-telegram | ✅ Active (receiving commands) |
| cortex-dashboard | Not running (not deployed) |

### What Needs to Run First

Before enabling the daemon, verify:
```bash
# 1. Check VPS is on latest commit
git log --oneline -3

# 2. Check environment variables
cat /etc/environment | grep -E "ANTHROPIC|OPENROUTER|THREADS|VERCEL|BLOB"

# 3. Verify Python deps
source venv/bin/activate && python -c "import scrapling; print('OK')"

# 4. Reset budget (new day)
python -c "from cost_tracker import reset_daily; reset_daily()"

# 5. Enable daemon with conservative settings (1 cycle first)
systemctl start cortex-daemon
```

### Environment Variables Needed

| Var | Where | Status |
|-----|-------|--------|
| `ANTHROPIC_API_KEY` | VPS + local | ✅ Set |
| `OPENROUTER_API_KEY` | VPS + local | ✅ Set |
| `TELEGRAM_BOT_TOKEN` | VPS | ✅ Set |
| `THREADS_ACCESS_TOKEN` | Local | ✅ Set |
| `VERCEL_TOKEN` | VPS | ❌ Needed for auto-deploy |
| `BLOB_READ_WRITE_TOKEN` | Local + VPS | ❌ Needed for image posts |
| `PTC_ENABLED` | Optional | Set `=true` when Anthropic credits loaded |

---

## 20. Known Issues & Technical Debt

### FIXED since Session 13

| Issue | Fix |
|-------|-----|
| `sync.py` stale imports (`execute`, `validate`) | Fixed — now uses lazy `execute_plan`/`validate_execution` |
| `project_orchestrator.py` stale imports | Fixed — lazy import pattern |
| `scheduler.py` missing `page_type` in `execute_plan()` | Fixed — `page_type="app"` added |

### High Priority (active)

#### 1. Daemon Never Run Unsupervised
**The biggest gap.** Every improvement happened in supervised sessions. The autonomous thesis is unproven until the daemon runs for 24+ hours without human intervention.
- **Action:** Enable daemon with `--max-cycles 5`, monitor via Telegram

#### 2. VERCEL_TOKEN Not Set on VPS
Post-build auto-deploy (Session 21) will silently skip if `VERCEL_TOKEN` is missing.  
- **Action:** `export VERCEL_TOKEN=<token>` in VPS `/etc/environment`

#### 3. BLOB_READ_WRITE_TOKEN Not Set
Image posts (Session 23) will fall back to text-only if token isn't configured.  
- **Action:** Get token from vercel.com/dashboard → Blob storage → create store → copy token

#### 4. Knowledge Graph Auto-Trigger Missing
`knowledge_graph.py` works but isn't auto-triggered on new outputs — gets stale.  
- **Action:** Add call to graph extraction in memory_store after new accepts

#### 5. RAG Index Not Auto-Updated
New research outputs go to JSON memory but not ChromaDB. Semantic search gets staler over time.  
- **Action:** Add `rag/embeddings.py:index_document()` call in `memory_store.store()`

### Medium Priority

#### 6. Dashboard Not Deployed
`dashboard/api.py` (784 lines) built and tested but not running on VPS.  
- **Action:** Add `cortex-dashboard.service` systemd file; `uvicorn dashboard.api:app`

#### 7. Consensus Agent Unused
Built but `CONSENSUS_ENABLED = False`. Not wired into daemon loop.
- **Action:** Enable when running 2+ domains simultaneously to validate research quality

#### 8. Verifier Underused
Built to break circular LLM-judging-LLM — rarely called. Only in explicit verification flows.

#### 9. MCP Docker Dependency
MCP servers need Docker running on VPS + containers pulled. `github` and `idea-reality` will fail gracefully if Docker not available.

#### 10. Test Suite Fragmentation
2,092 test functions in 45 test files but only 147 actively run (`test_core.py` + `test_integration_wiring.py`). The remaining 43 test files contain ~1,945 additional test functions. Many are historical integration tests that may have import issues or test approaches that are now outdated.  
- **Action:** Audit the 43 idle test files — identify which are still valid and re-enable them, archive the rest

#### 11. `get_ready_tasks()` Not Implemented
Pattern from Beads analysis (Session 23) — adding `blocked_by` field to task_queue items + `get_ready_tasks()` query (unblocked tasks only). Not yet implemented.

### Low Priority / Accepted Tech Debt

- `hands/consultant.py` `_consult` tool gives LLM-generated answers, not actual human input (Telegram mid-build Q&A would fix this)
- Some test isolation issues (test artifacts left in `memory/`, `strategies/`)
- Browser tools disabled by default (need `playwright install` on fresh VPS)
- `CONSENSUS_ENABLED=False` permanently until multi-domain run justifies it

---

## 21. Pending Integrations (upnext.md Audit)

### Still Not Integrated (from upnext.md — all 16 gaps re-audited)

| Gap | Status | Notes |
|-----|--------|-------|
| A — MCP during research | ✅ Wired (Session 20) | `get_mcp_research_tools()` in researcher |
| B — MCP context router | ✅ Wired (Session 20) | `select_tools()` called before researcher run |
| C — MCP tool bridge | ✅ Wired (Session 20) | `register_mcp_tools_in_registry()` in cortex |
| D — Threads insights not exposed | ⚠️ Partial | `/threads thread <id>` added (Session 19); `get_profile_insights()`, `get_recent_engagement()` still not in chat tools |
| E — Signal enrichment never auto-runs | ✅ Wired (Session 19) | `enrich_top_posts()` in `_run_signal_cycle()` step 2.5 |
| F — Signal → Build spec | ✅ Wired (Session 14) | `generate_build_spec()` runs on score ≥ 70 |
| G — Signal bridge daemon | ✅ Wired (Session 14) | `_run_signal_cycle()` calls `generate_signal_questions()` |
| H — Dashboard not started | ❌ Still not deployed | API built, no systemd service file |
| I — Credential vault for API keys | Deferred | .env works fine; over-engineering for now |
| J — Post-build Vercel deploy | ✅ Wired (Session 21) | Runs if VERCEL_TOKEN set |
| K — RAG not auto-indexed | ❌ Still not wired | New outputs don't auto-index into ChromaDB |
| L — Dataset loader | ✅ Wired (Session 20) | Injected into planner system prompt |
| M — Crawl-to-KB | ✅ Wired (Session 20) | `inject_crawl_claims_into_kb()` in scheduler |
| N — Browser direct access | Deferred | Works as fallback in web_fetcher; researcher uses when BROWSER_ENABLED |
| O — Consultant human answer | Deferred | Needs Telegram inline keyboard UX |
| P — Domain seeds stale | ✅ Fixed (Session 21) | `domain_seeder.py` has 5 curated questions for 3 revenue domains |

### New gaps identified in Session 23:
- `get_ready_tasks()` (Beads pattern) — not implemented, worth adding for multi-agent task claiming
- `BLOB_READ_WRITE_TOKEN` — Vercel Blob image pipeline won't activate without it
- Dashboard deployment — still the biggest unblocker for monitoring without SSH

---

## 22. Codebase Statistics

### Lines of Code (as of Session 23)

| Category | Files | Lines |
|----------|-------|-------|
| **Production Python** | 135 | 52,147 |
| **Test Python** | 45 | 29,827 |
| **Identity Markdown** | 10 | ~55,000 |
| **Strategies (per domain)** | varies | varies |
| **Total (Python only)** | 180 | ~82,000 |

*Growth since Session 13 handoff: +15 production files (+7,664 LOC), +7 test files (+4,829 LOC)*

### Component Breakdown

| Component | Approx Lines | Notes |
|-----------|-------------|-------|
| Brain Agents | ~5,500 | 11 agents |
| Hands System | ~12,000 | 30+ components |
| Signal Intelligence | ~2,500 | collector, scorer, bridge |
| Infrastructure | ~10,000 | scheduler, watchdog, sync, DB, monitoring, loop_guard |
| CLI | ~5,000 | 12 command modules |
| Tools | ~2,800 | 8 tool files (+ image_publisher NEW) |
| Browser | ~1,250 | stealth browser + auth |
| RAG | ~914 | ChromaDB + embeddings |
| Utils | ~1,200 | retry, cache, vault, rate limiter |
| Dashboard | ~933 | FastAPI backend |
| Deploy | ~923 | VPS deployment |
| MCP | ~1,739 | External tool gateway |
| Identity / Skills | ~55,000 | Markdown docs |

### Test Coverage

- **Total test functions:** 2,092 (across all 45 test files)
- **Actively run:** 147 (`test_core.py`: 93 + `test_integration_wiring.py`: 54)
- **All pass:** ✅ 147/147

**Why only 147 actively run:**  
The 43 other test files are historical — they test specific features, refactors, and hardening rounds from Sessions 1–13. Many have import assumptions or test setups that are now outdated. `test_hardening_round.py` is explicitly noted as a "known skip." The two actively maintained files cover all critical wiring points and core functionality.

---

## 23. Roadmap — What's Next

### Immediate (This Week)

1. **Set VERCEL_TOKEN on VPS** — `export VERCEL_TOKEN=<token>` in `/etc/environment` — unlocks auto-deploy
2. **Set BLOB_READ_WRITE_TOKEN** — enables image posts to Threads
3. **Enable daemon (supervised first cycle)** — start with `--max-cycles 3 --rounds 5`
4. **Watch first autonomous signal cycle** via Telegram alerts
5. **First end-to-end: Research → Build → Auto-deploy → Live URL** — the transistor proof

### Short-Term (1–2 Weeks)

6. **Deploy dashboard** — add systemd service; `uvicorn dashboard.api:app --port 8000`
7. **Auto-index RAG** — wire `index_document()` call in `memory_store.store()` on new accepts
8. **Audit idle test files** — identify valid tests in the 43 dormant files; re-enable or archive
9. **Wire domain goals CLI** — `--set-goal-structured` + `/setgoal` Telegram command
10. **Objective 6: Full SaaS Build** — pick niche from signal data, run full pipeline

### Medium-Term (1–3 Months)

11. **First revenue** — deliver one OnlineJobsPH landing page, collect testimonial
12. **Enable daemon 24/7** — prove the loop runs autonomously for a week straight
13. **Portfolio flywheel** — 3 delivered pages → testimonials → conversion compounds
14. **Economics agent** — cost vs revenue tracking, kill/pivot/double-down decisions

### Long-Term (3–12 Months)

15. **Multi-domain parallel** — 5+ domains researching simultaneously
16. **Growth capability** — SEO, content, outreach agents
17. **Multi-VPS** — Scale to multiple instances
18. **Meta-Orchestrator** — Cross-instance signal coordination

### The Transistor Test (success criteria)

```
INPUT:  One sentence describing a niche.

OUTPUT: A live Vercel URL.
        Real auth (sign-up, login, session, logout).
        Real database (Supabase, data persists).
        Core feature working end-to-end.
        Beautiful design (matches identity/design_system.md).
        Playwright end-to-end tests passing.
        Production-ready.
        Built from Brain's research on real user pain (signal data).
        You wrote zero lines of code.
```

That is a working transistor. When that works once, everything else compounds.

---

## 24. Appendix: File Inventory

### Brain Agents (`agent-brain/agents/`)

| File | Lines | Purpose |
|------|-------|---------|
| `researcher.py` | 723 | Web research, tool use loop, PTC-ready |
| `critic.py` | 511 | 5-dimension rubric scoring |
| `cortex.py` | 1,236 | Strategic orchestrator + pipeline |
| `cross_domain.py` | 629 | Principle extraction + domain transfer |
| `meta_analyst.py` | 410 | Strategy evolution (Layer 3) |
| `question_generator.py` | 417 | Gap → next question (Lifebook-aware) |
| `synthesizer.py` | 439 | KB integration |
| `verifier.py` | 337 | Prediction tracking |
| `consensus.py` | 284 | Multi-agent agreement (disabled) |
| `orchestrator.py` | 582 | Domain routing |
| `threads_analyst.py` | ~600 | Threads content strategy + narrator |

### Hands System (`agent-brain/hands/`)

| File | Lines | Purpose |
|------|-------|---------|
| `planner.py` | 594 | Structured plan generation |
| `executor.py` | 932 | Multi-turn tool execution (24 tools) |
| `validator.py` | 798 | Output verification |
| `visual_gate.py` | 344 | Mid-build visual checks |
| `visual_evaluator.py` | 634 | Claude Vision scoring |
| `pattern_learner.py` | 497 | Learning from executions |
| `project_orchestrator.py` | 832 | Multi-phase projects |
| `exec_meta.py` | 506 | Execution strategy evolution |
| `error_analyzer.py` | 192 | Root cause analysis |
| `task_generator.py` | 332 | Generate tasks from goals |
| `artifact_tracker.py` | 365 | Track produced artifacts |
| `checkpoint.py` | 172 | Save/restore progress |
| `code_exemplars.py` | 247 | Example code patterns |
| `exec_analytics.py` | 266 | Execution metrics |
| `exec_cross_domain.py` | 254 | Cross-domain exec transfer |
| `exec_memory.py` | 142 | Execution memory store |
| `exec_templates.py` | 280 | Execution templates |
| `feedback_cache.py` | 206 | Cache corrections |
| `file_repair.py` | 246 | Auto-fix common issues |
| `mid_validator.py` | 264 | Mid-execution validation |
| `output_polisher.py` | 223 | Clean up outputs |
| `plan_cache.py` | 226 | Cache similar plans |
| `plan_preflight.py` | 284 | Validate plans |
| `retry_advisor.py` | 266 | Retry strategies |
| `strategy_assembler.py` | 226 | Build exec strategies |
| `consultant.py` | ~100 | `_consult` tool |
| `constants.py` | 53 | Shared constants |

### Tools (`agent-brain/tools/`)

| File | Lines | Purpose |
|------|-------|---------|
| `web_search.py` | ~300 | DuckDuckGo search (tool def + execute) |
| `web_fetcher.py` | ~400 | Scrapling + browser fallback |
| `threads_client.py` | ~500 | Full Threads API client |
| `image_publisher.py` | ~323 | Vercel Blob upload + screenshot + chart |
| `crawl_to_kb.py` | ~250 | Crawl page → inject into KB |
| `dataset_loader.py` | ~200 | HuggingFace + GitHub code examples |

### Infrastructure

| File | Lines | Purpose |
|------|-------|---------|
| `scheduler.py` | 1,867 | Multi-domain daemon loop |
| `watchdog.py` | ~700 | Circuit breaker + budget gate |
| `sync.py` | ~400 | Brain ↔ Hands task handoff |
| `cost_tracker.py` | ~300 | Per-provider budget tracking |
| `monitoring.py` | ~400 | Score trends, health checks |
| `loop_guard.py` | ~300 | Pure-logic stuck detection |
| `progress_tracker.py` | ~200 | Goal-distance assessment |
| `prescreen.py` | ~200 | Cheap pre-filter before critic |
| `memory_store.py` | ~400 | Scored output storage |
| `strategy_store.py` | ~350 | Versioned strategy management |
| `domain_goals.py` | ~300 | Full Lifebook goal records |
| `knowledge_graph.py` | ~400 | Entity-relationship extraction |
| `db.py` | ~300 | SQLite wrapper |
| `analytics.py` | ~400 | Score trajectories, distributions |
| `protocol.py` | ~300 | 10-message protocol layer |
| `signal_collector.py` | ~500 | RSS + Scrapling enrichment |
| `opportunity_scorer.py` | ~400 | Scoring + build spec generation |
| `signal_bridge.py` | ~160 | Signal → research question bridge |
| `config.py` | ~200 | All config (models, budgets, flags) |
| `llm_router.py` | ~250 | 4-tier model routing |

### CLI (`agent-brain/cli/`)

| File | Purpose |
|------|---------|
| `research.py` | Research loop commands |
| `chat.py` | Interactive chat (37 tools) |
| `execution.py` | Build task runner |
| `project.py` | Multi-phase projects |
| `knowledge.py` | KB queries |
| `signals_cmd.py` | Signal pipeline |
| `strategy.py` | Strategy management |
| `browser_cmd.py` | Browser automation |
| `deploy_cmd.py` | VPS deployment |
| `infrastructure.py` | Service management |
| `tools_cmd.py` | Tool registry + MCP |
| `vault.py` | Credential vault |

---

*Document generated: Session 23 (current)*  
*Previous version: Session 13 / March 4, 2026*  
*Replaces: `my-notes.md/CORTEX_CONSULTANT_HANDOFF.md` (now superseded)*
