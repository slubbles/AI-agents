# CORTEX MASTER PLAN v2.0

> **Goal:** Tell Cortex a niche → get back a live, beautiful, production-ready full-stack web application — with zero human code written in between.

**Created:** March 3, 2026  
**Last Updated:** March 4, 2026  
**Status:** Active — Objectives 1-5 Complete, Phase 2 Beginning  
**Codebase:** 44,483 lines production, 1,737 tests passing

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

### Known Issues (Low Severity)

4 stale imports that will cause runtime failures if those code paths execute:
1. `sync.py`: imports `execute` (should be `execute_plan`)
2. `sync.py`: imports `validate` (should be `validate_execution`)
3. `project_orchestrator.py`: same stale import
4. `scheduler.py`: `execute_plan()` call missing `page_type` param

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

## OBJECTIVE 6: Fix Remaining Foundation

> **Purpose:** Clean up 4 stale imports that will cause runtime failures.

### Task 6.1: Fix sync.py stale imports
- [ ] Change `from hands.executor import execute` → `from hands.executor import execute_plan`
- [ ] Change `from hands.validator import validate` → `from hands.validator import validate_execution`
- [ ] Run tests to verify imports work

### Task 6.2: Fix project_orchestrator.py stale import
- [ ] Same `execute` → `execute_plan` fix
- [ ] Run tests to verify

### Task 6.3: Fix scheduler.py execute_plan call
- [ ] Add `page_type` parameter to `execute_plan()` call
- [ ] Add `visual_context` parameter if needed
- [ ] Run tests to verify

### Task 6.4: Update VPS
- [ ] Commit all fixes
- [ ] Push to GitHub
- [ ] SSH to VPS: `git pull`
- [ ] Restart services: `systemctl restart cortex-daemon cortex-telegram`
- [ ] Verify services start clean

### Task 6.5: Verify tests pass
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Confirm 1,737+ tests still passing
- [ ] Fix any regressions

**Done when:** All imports correct, VPS updated, tests green.

**Estimated time:** 2-4 hours

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

## OBJECTIVE 8: Wire Cortex Pipeline Method

> **Purpose:** Full Brain → Cortex → Hands flow, not just Hands alone.

### Task 8.1: Complete cortex.py pipeline() method
- [ ] Implement research phase:
  ```python
  research_req = ResearchRequest(domain=niche, question=f"Find opportunity in {niche}")
  brain_result = self._send_to_brain(research_req)
  ```
- [ ] Implement approval gate:
  ```python
  self._send_telegram(f"Brain found: {summary}. Approve? /yes /no")
  approval = self._wait_for_approval(timeout=3600)
  ```
- [ ] Implement build phase:
  ```python
  build_task = BuildTask(spec=product_brief, budget=budget_cap)
  build_result = self._send_to_hands(build_task)
  ```
- [ ] Implement completion:
  ```python
  self._send_telegram(f"Build complete: {url}")
  ```

### Task 8.2: Add Telegram /build command
- [ ] In `telegram_bot.py`, add handler for `/build <niche>`
- [ ] Triggers `cortex.pipeline(niche)`
- [ ] Shows progress updates per phase
- [ ] Final message: live URL

### Task 8.3: Test end-to-end via Telegram
- [ ] Send: `/build contact form`
- [ ] Watch: Brain researches (or uses existing KB)
- [ ] Watch: Cortex asks for approval
- [ ] Reply: `/yes`
- [ ] Watch: Hands builds
- [ ] Receive: live URL

**Done when:** `/build <niche>` in Telegram produces a live URL.

**Estimated time:** 2-3 days

---

## OBJECTIVE 9: Reddit Research Pipeline

> **Purpose:** Brain finds real pain points from Reddit, not just web search.

### Task 9.1: Add PRAW client
- [ ] Add `praw` to requirements.txt
- [ ] Create `tools/reddit_client.py`:
  - `search_posts(subreddit, query, limit, time_filter)`
  - `get_top_posts(subreddit, limit)`
  - `get_comments(post_id, limit)`
- [ ] Test: can fetch posts from r/freelance

### Task 9.2: Create Reddit Analyst Agent
- [ ] Create `agents/reddit_analyst.py`:
  - Takes raw Reddit posts
  - Extracts pain points with user's exact language
  - Scores each: specificity, frequency, buildability
  - Returns top 3 opportunities with evidence
- [ ] Test with real subreddit data

### Task 9.3: Wire into Brain's research loop
- [ ] In `question_generator.py`, add `reddit_research` question type
- [ ] Route opportunity-finding questions to Reddit analyst
- [ ] Combine with web search for fuller picture

### Task 9.4: Dual output format
- [ ] Reddit research produces two outputs:
  1. `product_brief.md` — what to build
  2. `marketing_brief.md` — user language for copy
- [ ] Both passed to Cortex for downstream use

**Done when:** Brain can research a domain using Reddit + web, producing actionable briefs.

**Estimated time:** 3-5 days

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
| Threads API | Marketing comes after product ships |
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
OBJECTIVE 9 (Reddit Research)
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
| 9. Reddit Pipeline | 3-5 days | Day 11 |
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
