# CORTEX MASTER PLAN v2.0

> **Goal:** Tell Cortex a niche → get back a live, beautiful, production-ready full-stack web application — with zero human code written in between.

**Created:** March 3, 2026  
**Last Updated:** March 4, 2026  
**Status:** Active — Objectives 1-9 Complete, Phase 2 In Progress  
**Codebase:** 44,483+ lines production, 1,805 tests passing

---

## The End State

```
YOU: "Build a client portal for web agencies"

CORTEX:
  Brain researches the niche → understands pain, users, competitors
  Cortex evaluates → approves build
  Hands builds → architecture, backend, frontend, visual iteration, deploy
  Cortex reports → Telegram message with live URL

YOU: open browser → production-ready SaaS staring back at you
```

No code written by you. Brain and Hands fully integrated. Cortex supervising end-to-end.

---

## Architecture (Current Implementation)

```
YOU
 ↓
CORTEX ORCHESTRATOR (agents/cortex.py + scheduler.py)
 │  Receives your instruction
 │  Supervises Brain and Hands
 │  Routes context between them
 │  Makes strategic decisions mid-build
 │  Reports results to you via Telegram
 │
 ├──→ AGENT BRAIN (self-coordinating)
 │      Researcher → Critic → Meta-Analyst → Synthesizer
 │      Produces: niche brief, user pain, competitor gaps,
 │                copy, design direction, success criteria
 │
 └──→ AGENT HANDS (self-coordinating)
        Planner → Executor → Validator → Visual Gate
        Project Orchestrator coordinates phases
        Visual Evaluator scores screenshots via Claude Vision
        7 tool categories (code, terminal, git, search, http, browser)
```

**Communication Protocol (protocol.py — 10 message types):**
```
Brain → Cortex:     ResearchComplete
Cortex → Brain:     ResearchRequest
Cortex → Hands:     BuildTask
Hands → Cortex:     PhaseComplete, ContextNeeded, BuildComplete, BuildFailed
Cortex → Brain:     ContextResponse (KB query)
Cortex → You:       TaskComplete (Telegram summary)
Internal:           JournalEntry (audit trail)
```

---

## Current State (March 4, 2026)

### What's Built & Working ✅

| Component | Status | Notes |
|-----------|--------|-------|
| Agent Brain 5-layer self-learning | ✅ Complete | All layers proven |
| Communication Protocol | ✅ Complete | 10 typed dataclass messages |
| Playwright Visual System | ✅ Complete | Browser tool, evaluator, gate |
| Design Standards | ✅ Complete | design_system.md, marketing_design.md, visual_rubric |
| Identity Layer | ✅ Complete | 8 files (boundaries, ethics, goals, design, etc.) |
| Hands Pipeline | ✅ Built | Planner, Executor, Validator, Visual Gate |
| 4-Tier Model Routing | ✅ Working | DeepSeek → Grok → Claude → Gemini |
| Daemon + Watchdog | ✅ Running | VPS active (budget_halt state) |
| Telegram Bot | ✅ Active | Alerts + chat interface |

### Statistics

| Metric | Value |
|--------|-------|
| Production Python | 44,483 lines |
| Test Python | 24,998 lines |
| Tests Passing | 1,737 |
| Agent Brain Files | ~25 files |
| Agent Hands Files | ~30 files |
| Git Commits (Phase 1) | 6 objectives completed |

### VPS State

| Property | Value |
|----------|-------|
| IP | 207.180.219.27 |
| Git Version | d9800ca (5 commits behind main) |
| Services | Active (budget_halt state) |
| Daily Budget | $7.00 ($2 Claude + $5 OpenRouter) |

### Known Issues

None — all stale imports fixed in Obj 6, pipeline bugs fixed in Obj 7.

---

## COMPLETED OBJECTIVES (Phase 1)

### ✅ OBJECTIVE 1: Stop the Bleeding (Commit: d9800ca)

**Fixed 3 critical bugs:**
1. ✅ Budget desync — now reads from SQLite as source of truth
2. ✅ Brain→Hands task type mismatch — keywords mapped correctly
3. ✅ Watchdog cooldown stall — filters invalid domains

**Result:** Deployed to VPS, daemon running, 1,538 tests passing

---

### ✅ OBJECTIVE 2: Prompt Upgrades (Commit: f89f0e0)

**Completed:**
- ✅ `identity/boundaries.md` — operational limits defined
- ✅ `hands/planner.py` — structured plan generation prompt
- ✅ `hands/executor.py` — anti-patterns, tool constraints
- ✅ `agents/cortex.py` — strategic reasoning prompt
- ✅ `identity/design_system.md` v1.0 — app UI standard

---

### ✅ OBJECTIVE 3: Full Three-Way Communication (Commit: 62afba9)

**Created `protocol.py` with 10 typed message dataclasses:**
- ResearchRequest, ResearchComplete
- BuildTask, PhaseComplete, ContextNeeded, ContextResponse
- BuildComplete, BuildFailed
- TaskComplete, JournalEntry

**Result:** 43 new tests, 1,581 total passing

---

### ✅ OBJECTIVE 4: Give Hands Eyes (Commit: 47b2522)

**Built Playwright visual feedback system:**
- ✅ `hands/tools/browser.py` — screenshot, navigate, click, fill, wait_for
- ✅ `hands/visual_evaluator.py` — Claude Vision scoring
- ✅ `hands/visual_gate.py` — mid-build visual checks
- ✅ Executor integration with visual feedback loop

**Result:** 62 new tests, 1,643 total passing

---

### ✅ OBJECTIVE 5: Train the Visual Standard (Commit: 497490b)

**Created comprehensive design standards:**
- ✅ `identity/design_system.md` v1.1 — app UI (420+ lines)
- ✅ `identity/marketing_design.md` — marketing pages (325+ lines)
- ✅ `identity/visual_scoring_rubric.md` — calibration guide (143+ lines)
- ✅ Page-type aware loading (app vs marketing)
- ✅ Score persistence for strategy evolution

**Result:** 67 new tests, 1,710 total passing

---

### ✅ AUDIT PASS (Commit: f0e85fd)

**Fixed 3 additional bugs:**
- ✅ CLI page_type wiring — `_detect_page_type()` now passes correctly
- ✅ Abort cleanup leak — `visual_gate.cleanup()` called on abort
- ✅ No `__del__` safety — added to VisualGate class

**Result:** 27 new tests, 1,737 total passing

---

## PHASE 2: PROVE THE PIPELINE

> **Purpose:** Test what we built. One instruction → one live URL. Fix what breaks.

---

## OBJECTIVE 6: Fix Remaining Foundation ✅ COMPLETE

> **Purpose:** Clean up stale imports and broken call signatures.
> **Completed:** 2026-03-04 | Commit: `412fdc2` + `f0abebf` (audit fixes)

### Fixed:
- [x] `sync.py`: `execute` → `execute_plan`, `validate` → `validate_execution`
- [x] `project_orchestrator.py`: same import fixes
- [x] `scheduler.py`: `execute_plan()` — added `page_type`, `visual_context`, `research_context`
- [x] `scheduler.py`: `save_exec_output()` — fixed wrong param names (`task`→`goal`, `result`→`execution_report`), added missing `validation`, `attempt`, `strategy_version` params, wired `validate_execution()` call
- [x] `scheduler.py`: `get_strategy()` — now captures `strategy_version` for exec memory
- [x] 1,737 tests passing

### VPS Update: Deferred
- VPS is in `budget_halt` state, will update when next needed

---

## OBJECTIVE 7: Prove End-to-End Pipeline ✅ COMPLETE

> **Purpose:** One manual build test to prove everything works together.
> **Completed:** 2026-03-04 | **Score:** 8.2/10 on first attempt

### What was proven:
- [x] **Planner** (Claude Sonnet via OpenRouter) produces valid step-by-step plans
- [x] **Executor** (Grok 4.1 Fast) writes real files to workspace via tool_use loop
- [x] **Validator** (Claude Sonnet via OpenRouter) scores execution and accepts/rejects
- [x] **Full Pipeline** via CLI: `python main.py --execute --goal "..." --workspace output/test`
- [x] **Pattern Learner** extracts execution patterns + stores exemplars
- [x] **Quality Gate** accepted output (8.2/10 >= threshold 7)

### Bugs found and fixed:
1. **Anthropic credit balance $0** — Routed PREMIUM_MODEL through OpenRouter (`anthropic/claude-sonnet-4`)
2. **OpenRouter message converter dropped tool_use blocks** — `_convert_messages_to_openai_format()` only handled dict/str blocks, not our `ToolUseBlock`/`TextBlock` dataclasses. Fixed to handle both + properly emit OpenAI `tool_calls` format for assistant messages.
3. **Code tool path resolution** — Executor didn't resolve relative paths against `workspace_dir` for code tool. Path `test/index.html` resolved against process cwd instead of workspace. Fixed executor to auto-prepend `workspace_dir` for relative code paths.
4. **`get_daily_spend()` returns dict not float** — Summary line `${daily:.4f}` crashed. Fixed to extract `total_usd` from dict.

### Test result:
```
Goal: "Create a single-page HTML landing page: hero section, blue gradient, CTA button, footer"
Plan: 2 steps (code write + browser screenshot)
Execution: 1/2 steps succeeded (browser failed on file:// URL — non-critical)
Score: 8.2/10 — Accepted
Artifacts: index.html (2,658 bytes, complete production HTML)
```

### Not tested yet (deferred to Obj 8-10):
- Visual Gate (needs dev server running)
- Vercel deploy
- Telegram notification
- Next.js/full SaaS builds

---

## OBJECTIVE 8: Wire Cortex Pipeline Method ✅ COMPLETE

> **Purpose:** Full Brain → Cortex → Hands flow with approval gate, not just Hands alone.
> **Completed:** March 4, 2026

### Implemented:
- [x] `pipeline()` in `agents/cortex.py` — full Brain→Approve→Build flow
  - Research phase: calls `run_loop()` if domain not build-ready
  - Approval gate: `request_approval()` sends Telegram notification, blocks on `threading.Event`
  - Build phase: `_execute_build()` runs plan→execute→validate→retry→store
  - Completion: Telegram notification with score, artifacts, cost
  - Status tracking: `get_pipeline_status()` for live monitoring
- [x] Thread-safe approval mechanism (`request_approval` / `resolve_approval`)
  - `_pending_approvals` dict with `threading.Event` per domain
  - 1-hour timeout, auto-reject on timeout
- [x] Telegram commands: `/build`, `/approve`, `/reject`, `/pipeline`
  - `/build <instruction>` — starts pipeline in background thread
  - `/approve [domain]` — approves pending build
  - `/reject [domain]` — rejects pending build  
  - `/pipeline` — shows active pipelines and pending approvals
- [x] CLI entry point updated: `run_pipeline()` calls `pipeline(require_approval=False)`
- [x] `_execute_build()` — simplified Hands execution for programmatic use
  - plan → execute → validate → retry → save_exec_output
  - Auto-detects page_type from goal keywords
  - Injects build brief into strategy context
- [x] 27 new tests (1,764 total), all passing
- [x] Updated `/start` help text with pipeline commands

### Architecture:
```
/build <instruction>
  → pipeline() in background thread
    → Brain research (or skip if build-ready)
    → Extract build brief from KB
    → Telegram: "Approve?" → blocks on Event
    → /approve → resolve_approval(True) → Event.set()
    → _execute_build(plan→execute→validate→store)
    → Telegram: "Complete! Score X/10"
```

---

## OBJECTIVE 9: Threads Pipeline ✅ COMPLETE

> **Purpose:** Brain + Growth use Threads API for research (pain points) and distribution (posting).
> **Completed:** March 4, 2026
> **Pivoted from Reddit:** Reddit API access too complicated. Will scrape Reddit separately for learning human posting style.

### Implemented:

**tools/threads_client.py — Full Meta Graph API client (pure stdlib, no deps):**
- [x] `publish_post(text, image_url, reply_to_id, link_attachment)` — two-step container→publish
- [x] `reply_to_thread(thread_id, text)` — reply wrapper
- [x] `search_threads(query, limit, fields)` — keyword search across Threads
- [x] `get_user_threads(limit)` — own posts
- [x] `get_thread(thread_id)` / `get_thread_replies()` / `get_conversation()` — reading
- [x] `get_thread_insights(thread_id)` — per-post views, likes, replies, reposts, shares
- [x] `get_profile_insights()` — profile-level analytics
- [x] `get_recent_engagement(limit)` — quick engagement summary with top post
- [x] Rate limiting (250 calls/hour), publish cooldown (90s anti-spam)
- [x] LLM tool definitions: `THREADS_SEARCH_TOOL`, `THREADS_POST_TOOL`, `THREADS_INSIGHTS_TOOL`
- [x] `execute_threads_tool()` — tool_use executor for all 3 tools

**agents/threads_analyst.py — Content analysis agent:**
- [x] `analyze_pain_points(domain, query, threads_data, goal)` — extract pain points, user language, market signals
- [x] `analyze_content_strategy(domain, threads_data)` — extract patterns, hooks, formats, write drafts
- [x] `generate_post(domain, topic, style, knowledge_context)` — AI-written post using Brain KB

**Brain integration (researcher.py):**
- [x] `threads_search` tool auto-loaded when `THREADS_ACCESS_TOKEN` configured
- [x] Researcher can search Threads alongside web search during research loops
- [x] Handler in tool-use loop formats results as numbered posts for LLM

**Telegram commands:**
- [x] `/threads search <query>` — search Threads posts
- [x] `/threads post <text>` — publish to Threads
- [x] `/threads draft <topic>` — AI-generated post draft using Brain KB
- [x] `/threads analyze <query>` — search + pain point analysis
- [x] `/threads insights` — recent engagement stats
- [x] `/threads analytics` — profile-level metrics
- [x] Updated `/start` help with Threads section

**Config:**
- [x] `THREADS_ENABLED` flag in config.py
- [x] `threads_analyst` model assignment (CHEAPEST_MODEL — synthesis task)
- [x] 41 new tests (1,805 total), all passing

### Architecture:
```
/threads search "invoicing frustrated"
  → threads_client.search_threads() → Meta Graph API
  → Returns posts with text, username, timestamp

/threads analyze "freelance invoicing"  
  → search_threads(query, limit=25)
  → threads_analyst.analyze_pain_points(posts)
  → Structured: pain_points[], user_language[], market_signals[]

/threads draft "invoicing tool launch"
  → threads_analyst.generate_post(topic, KB context)
  → Draft post with hook type, hashtags, engagement estimate

Brain research loop:
  → researcher.py auto-adds threads_search tool when API configured
  → LLM can search Threads alongside web/browser during research
```

### Setup Required (user action):
```
# In agent-brain/.env:
THREADS_ACCESS_TOKEN=<long-lived-token>
THREADS_USER_ID=<your-threads-user-id>
```

---

## OBJECTIVE 10: Full SaaS Build (The Transistor Test)

> **Purpose:** The real test. One niche → one complete, working web application.

### Task 10.1: Pick target niche
- [ ] Choose niche with existing Brain research OR run new research
- [ ] Example: "Simple invoicing for freelancers"
- [ ] Define: user persona, core pain, MVP feature

### Task 10.2: Brain researches deeply
- [ ] Reddit + web search
- [ ] At least 5 accepted outputs
- [ ] Competitive analysis
- [ ] User language extraction

### Task 10.3: Cortex approves build
- [ ] Evaluates research confidence
- [ ] Telegram prompt for human approval
- [ ] Creates BuildTask with full brief

### Task 10.4: Hands executes 7 phases
- [ ] Phase 0: Context Intake → PRD.md
- [ ] Phase 1: Architecture → ARCHITECTURE.md (human review gate)
- [ ] Phase 2: Workspace → scaffold + Supabase
- [ ] Phase 3: Backend → API routes + auth
- [ ] Phase 4: Frontend → UI + visual iteration
- [ ] Phase 5: Integration → Playwright tests
- [ ] Phase 6: Deploy → Vercel live URL
- [ ] Phase 7: Critic → score + lessons

### Task 10.5: Verify success criteria
- [ ] Live URL works
- [ ] Auth flow works (signup, login, logout)
- [ ] Core feature works (data persists)
- [ ] Visual score ≥ 8/10
- [ ] Playwright tests pass
- [ ] You wrote zero code

**Done when:** You type one sentence to Cortex, receive a live SaaS URL with working auth and core feature.

**Estimated time:** 1-2 weeks

---

## DEFERRED (After Transistor Works)

These are valid but come AFTER Objective 10 proves the system works:

| Feature | Why Defer |
|---------|-----------|
| Reddit Scraping | Scrape for human posting style (not API) |
| Content Agent | Blog/SEO after first revenue |
| Economics Agent | Need economics to track first |
| Multi-VPS scaling | Prove one instance first |
| Docker sandbox | Overkill until builds are frequent |
| Supabase MCP | CLI/API sufficient for now |
| Dashboard deploy | CLI monitoring is fine |

---

## Dependency Map

```
✅ OBJECTIVE 1-5 (COMPLETE)
       │
       ▼
OBJECTIVE 6 (Fix Foundation)
       │
       ▼
OBJECTIVE 7 (Prove Pipeline)
       │
       ▼
OBJECTIVE 8 (Cortex Pipeline)
       │
       ▼
OBJECTIVE 9 (Threads Pipeline)
       │
       ▼
OBJECTIVE 10 (Full SaaS Build)
       │
       ▼
    SUCCESS
    (Working Transistor)
```

---

## Timeline (Honest)

| Objective | Estimated | Cumulative |
|-----------|-----------|------------|
| ✅ 1-5 Complete | Done | Done |
| 6. Fix Foundation | 2-4 hours | Day 1 |
| 7. Prove Pipeline | 1-2 days | Day 3 |
| 8. Cortex Pipeline | 2-3 days | Day 6 |
| 9. Threads Pipeline | 1 day | Day 7 |
| 10. Full SaaS Build | 1-2 weeks | Day 25 |

**Total remaining: 3-4 weeks of focused work.**

---

## Success Criteria (The Transistor Test)

The plan is complete when this is true:

```
INPUT:  You type one sentence to Cortex describing a niche.

OUTPUT: A live URL.
        Real auth (sign up, login, session, logout).
        Real database (Supabase, data persists).
        Core feature working.
        Looks beautiful (consistent design system).
        Tested end-to-end by Playwright.
        Production-ready on Vercel.
        Built from Brain's research on real user pain.
        You wrote zero lines of code.
```

That is a working transistor. Everything else follows.
