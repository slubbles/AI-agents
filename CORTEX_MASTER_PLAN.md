# CORTEX MASTER PLAN

> **Goal:** Tell Cortex a niche → get back a live, beautiful, production-ready full-stack web application — with zero human code written in between.

**Created:** March 3, 2026
**Status:** Active
**Estimated timeline:** 4–8 weeks of focused work

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

## Architecture (what we're building toward)

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
        Phase 0: Context Intake (brief → PRD)
        Phase 1: Architecture (spec → blueprint)
        Phase 2: Workspace (scaffold + Supabase setup)
        Phase 3: Backend (API + auth + DB)
        Phase 4: Frontend (UI + visual feedback loop)
        Phase 5: Integration (Playwright end-to-end testing)
        Phase 6: DevOps (deploy to Vercel, live URL)
        Phase 7: Critic (score output, extract lessons)
```

**Communication protocol:**
- Cortex → Brain: `research_request`, `query_knowledge`, `store_lessons`
- Cortex → Hands: `build_task`, `inject_context`, `pause_build`, `abort_build`
- Brain → Cortex: `research_complete`, `knowledge_query_result`
- Hands → Cortex: `phase_complete`, `context_needed`, `build_complete`, `build_failed`
- Cortex → You: `task_complete`, `decision_needed` (rare), `status_update`

---

## Current State (March 3, 2026)

**What works:**
- Agent Brain 5-layer self-learning loop (research → critique → strategy evolution)
- 4,053 outputs in DB, 1,538 tests passing, 41,600 lines of code
- Daemon running on VPS (207.180.219.27), Telegram bot active
- 4-tier model routing, pre-screener saving ~40% Claude costs
- Identity layer (5 files), RAG memory (ChromaDB), knowledge graphs
- Cortex strategic planning (recommends focus domains each cycle)

**What's broken (3 critical bugs):**
1. **Budget desync** — `check_budget()` reads JSONL ($0.60) while DB has $25.46
2. **Brain→Hands pipeline dead** — 37 tasks pending, 0 ever executed (type mismatch)
3. **Watchdog stuck in cooldown** — "all" meta-domain triggers phantom cooldowns

**What's partial:**
- Strategy evolution stalled (domains stuck in trial, need volume)
- productized-services quality regression (8.25 → 2.9)
- Hands has never completed a single execution
- No visual feedback loop (no Playwright)
- No Supabase MCP, no Vercel MCP
- Dashboard built but not deployed

---

## OBJECTIVE 1: Stop the Bleeding

> **Purpose:** Unblock the entire system. Three bugs prevent everything downstream.

### Task 1.1: Fix budget tracking desync
- [ ] Make `get_daily_spend()` in `cost_tracker.py` read from SQLite DB instead of JSONL
- [ ] Keep JSONL write for backward compat, but DB is source of truth for reads
- [ ] Make `get_all_time_spend()` also read from DB
- [ ] Update `check_budget()` — it calls `get_daily_spend()` so it auto-fixes
- [ ] Update `check_balance()` — it calls `get_all_time_spend()` so it auto-fixes
- [ ] Verify: `check_budget()` returns numbers matching DB, not JSONL
- [ ] Run existing cost_tracker tests, ensure all pass

**Where the bug is:** [cost_tracker.py](agent-brain/cost_tracker.py#L57-L107) — `get_daily_spend()` and `get_all_time_spend()` both parse `costs.jsonl` line-by-line. Should query `db.py` instead.

**Why it matters:** The daemon thinks it has $6.40 remaining when it actually has $0. It will keep spending past budget because it's reading the wrong file.

### Task 1.2: Fix Brain→Hands task type mismatch
- [ ] In `main.py` `_ACTION_KEYWORDS`, change keywords that map to `"investigate"` to either `"action"` or remove them from task creation
- [ ] OR: In `scheduler.py` line 1105, expand the filter to also accept `"investigate"` and `"deploy"` task types
- [ ] Better fix: In `main.py` `_create_tasks_from_research()`, map `knowledge_gaps` to `task_type="action"` with `priority="low"` instead of `"investigate"`
- [ ] Clean up 37 stale `"investigate"` tasks in VPS sync_tasks.json (mark as dropped or convert type)
- [ ] Verify: create a test task with type `"build"` → confirm Hands picks it up in daemon
- [ ] Run sync tests, ensure all pass

**Where the bug is:**
- [main.py](agent-brain/main.py#L85-L100) creates tasks with `task_type="investigate"` and `"deploy"`
- [scheduler.py](agent-brain/scheduler.py#L1105) only executes `"build"` and `"action"` types
- Result: 36 `"investigate"` tasks + 1 `"deploy"` task sitting forever in pending

**Why it matters:** Brain has been creating tasks for Hands for weeks. Hands has never seen a single one. This is the #1 blocker for the entire Brain→Hands pipeline.

### Task 1.3: Fix watchdog cooldown stall
- [ ] Investigate what domain value is causing phantom cooldowns on VPS
- [ ] In `scheduler.py`, filter out meta-domains like `"all"` from Cortex focus_domains before applying priorities
- [ ] In `_apply_cortex_priorities()`, skip any domain that doesn't exist in the actual memory directory
- [ ] Reset watchdog state on VPS: clear `watchdog_state.json` cooldown_until and set state to "running"
- [ ] Verify: daemon runs multiple consecutive cycles without entering cooldown spuriously
- [ ] Run watchdog tests, ensure all pass

**Where the bug is:** [scheduler.py](agent-brain/scheduler.py#L570-L610) — `_apply_cortex_priorities()` injects focus_domains into the plan. If Cortex recommends `"all"` as a domain (from its LLM response), the scheduler tries to allocate rounds to a domain called `"all"` which doesn't exist, causing downstream failures → watchdog trips → 30min cooldown.

**Why it matters:** The daemon stalls every cycle. It runs one cycle, hits cooldown, waits 30 minutes, runs one cycle, hits cooldown again. Should be running continuously.

### Task 1.4: Deploy fixes to VPS
- [ ] Commit all Objective 1 fixes
- [ ] Push to GitHub
- [ ] SSH to VPS, `git pull`, restart `cortex-daemon.service`
- [ ] Monitor via Telegram: budget numbers correct, cycles running, no phantom cooldowns
- [ ] Verify at least one research cycle completes end-to-end without issues

**Done when:** Daemon runs full cycles without cooldown. Budget numbers match reality. Sync queue has at least one `"build"` or `"action"` task.

---

## OBJECTIVE 2: First Hands Execution

> **Purpose:** Prove the pipeline works. One task in → one live URL out.

### Task 2.1: Hardcode one test task
- [ ] Create a manual sync task: `task_type="build"`, `priority="high"`
- [ ] Task description: "Build a Next.js landing page for [one OLJ company Brain already researched]"
- [ ] Pull company info from Brain's existing knowledge base for the domain
- [ ] Insert task into sync_tasks.json

### Task 2.2: Verify Hands planner works
- [ ] Run `hands/planner.py` with the test task's goal and description
- [ ] Confirm it produces a valid step-by-step plan
- [ ] Confirm the plan uses tools that exist in the registry (code, terminal, git, search, http)
- [ ] Debug any import errors, model config issues, or missing dependencies

### Task 2.3: Verify Hands executor works
- [ ] Run `hands/executor.py` with the planner's output
- [ ] Confirm it writes actual files to the workspace
- [ ] Confirm terminal commands execute (npx create-next-app, npm install, etc.)
- [ ] Debug any tool execution failures, timeout issues, or workspace path problems

### Task 2.4: Verify build passes
- [ ] After executor completes, run `npm run build` in the generated project
- [ ] If build fails: feed error back to executor for one retry
- [ ] Confirm: a clean Next.js build with zero errors

### Task 2.5: Deploy to Vercel
- [ ] Install Vercel CLI in the workspace/VPS if not present
- [ ] Configure Vercel project (or use --yes flag for auto-setup)
- [ ] Run `vercel --prod` from the generated project directory
- [ ] Capture the live URL from Vercel's output
- [ ] Verify: URL loads a real page in the browser

### Task 2.6: Report result back through the pipeline
- [ ] Hands stores execution result in exec_memory
- [ ] Sync task updated to `"completed"` with result URL
- [ ] Telegram notification sent with the live URL
- [ ] Confirm the full pipeline: task created → Hands executes → URL returned → Telegram notified

### Task 2.7: Run in daemon mode
- [ ] Once manual test works, let the daemon pick up a `"build"` task autonomously
- [ ] Confirm: daemon finds task → Hands executes → URL returned → no human intervention
- [ ] Monitor cost: how much did one Hands execution cost?

**Done when:** You receive a Telegram message with a live Vercel URL that you can open in your browser. You wrote zero code for that page.

---

## OBJECTIVE 3: Full Three-Way Communication

> **Purpose:** Brain feeds Hands through Cortex. Cortex supervises. You talk only to Cortex.

### Task 3.1: Define message protocol as Python dataclasses
- [ ] Create `agent-brain/protocol.py` with typed message classes:
  - `ResearchRequest(domain, question, depth, urgency)`
  - `ResearchComplete(findings, confidence, cost)`
  - `BuildTask(spec, brief, constraints, budget_cap)`
  - `PhaseComplete(phase, artifact_path, cost)`
  - `ContextNeeded(phase, question)`
  - `BuildComplete(url, test_results, total_cost)`
  - `BuildFailed(phase, reason, retry_count)`
  - `TaskComplete(result, cost, confidence, summary)` → for Telegram
- [ ] All messages are JSON-serializable dicts (simple, no over-engineering)

### Task 3.2: Cortex → Brain → Cortex → Hands flow
- [ ] In `agents/cortex.py`, add `research_and_build(domain, instruction)`:
  1. Calls Brain's research loop (existing `run_loop()`)
  2. If research accepted (score ≥ 6): extract brief
  3. Create a `BuildTask` with the brief
  4. Insert into sync queue with `task_type="build"`, `priority="high"`
- [ ] Test: call `research_and_build("productized-services", "Build a landing page for a logistics company")`
- [ ] Verify: Brain researches → task created → Hands picks it up → URL returned

### Task 3.3: Hands → Cortex mid-build context requests
- [ ] In Hands executor, add ability to query Brain's knowledge base mid-execution
- [ ] When Hands hits a "need more context" situation (e.g., writing copy), it:
  1. Sends `ContextNeeded(phase="frontend", question="What words do users use to describe their pain?")`
  2. Cortex routes to Brain's RAG/knowledge base
  3. Brain returns specific context
  4. Hands injects context into the current prompt
- [ ] Start simple: Hands can call `query_knowledge(domain, question)` directly
- [ ] Later: route through Cortex for supervision

### Task 3.4: Cortex status monitoring during builds
- [ ] Cortex tracks which build phase Hands is in
- [ ] After each phase, Cortex evaluates: continue or intervene?
- [ ] If cost exceeds budget_cap → Cortex aborts
- [ ] If same phase fails 3x → Cortex escalates (Telegram alert + pause)
- [ ] Progress updates logged to cortex_journal.jsonl

### Task 3.5: End-to-end integration test
- [ ] You send one message to Cortex (via Telegram or CLI): "Research web agencies and build a landing page"
- [ ] Cortex → Brain researches → Cortex evaluates → Cortex → Hands builds → Hands deploys
- [ ] You receive: Telegram message with URL, cost summary, confidence score
- [ ] No human intervention between instruction and result

**Done when:** You type one sentence to Cortex and receive a live URL without touching anything in between. Brain's research is visibly reflected in the output (correct industry, correct copy, correct pain points).

---

## OBJECTIVE 4: Give Hands Eyes (Playwright Visual Feedback)

> **Purpose:** Hands can see what it built. Fixes visual problems autonomously.

### Task 4.1: Add Playwright to the stack
- [ ] Add `playwright` to requirements.txt
- [ ] Install browser binaries (`playwright install chromium`)
- [ ] Create `hands/tools/browser_tool.py`:
  - `screenshot(url, viewport?)` → returns base64 image
  - `navigate(url)` → loads page
  - `click(selector)` → clicks element
  - `fill(selector, text)` → fills input
  - `wait_for(selector)` → waits for element
- [ ] Register browser tool in `hands/tools/registry.py`
- [ ] Test: screenshot a known URL, verify image is captured

### Task 4.2: Visual evaluation after build
- [ ] After Hands deploys (Phase 6), take screenshot of live URL
- [ ] Pass screenshot to Claude with prompt: "Evaluate this web page. Does it look production-ready? What specific visual issues do you see?"
- [ ] Claude returns structured feedback: `{score: 7, issues: ["navbar too cramped", "no mobile responsiveness"]}`
- [ ] If score ≥ 8: accept
- [ ] If score < 8: one fix pass with specific issues, redeploy, screenshot again
- [ ] Max 2 visual iteration rounds (prevent infinite loop)

### Task 4.3: Mid-build visual checks (Frontend Phase)
- [ ] During Phase 4 (Frontend), after each major component group:
  - Start dev server (`npm run dev`)
  - Screenshot localhost
  - Claude evaluates component-by-component
  - Fix issues before moving to next component group
- [ ] This catches problems early — don't wait until deploy to see the UI is broken

### Task 4.4: Reference image comparison
- [ ] Brain's research can include reference screenshots (from competitor sites)
- [ ] During visual evaluation, inject reference: "The target aesthetic is similar to [reference]. Compare."
- [ ] Claude vision compares: current output vs reference → specific gap analysis
- [ ] Hands fixes gaps

**Done when:** Hands autonomously fixes something it saw was wrong in a screenshot, without you telling it what to fix. The fix is visible in the next screenshot.

---

## OBJECTIVE 5: Train the Visual Standard

> **Purpose:** Every app Cortex builds looks intentional, consistent, and beautiful.

### Task 5.1: Brain researches design quality
- [ ] Run Brain research on: "What makes a web app look production-ready?"
- [ ] Topics: shadcn/ui best practices, Tailwind patterns, Framer Motion, modern SaaS aesthetics
- [ ] Brain scores and synthesizes into structured knowledge
- [ ] Extract: specific rules, patterns, anti-patterns

### Task 5.2: Write the design system prompt
- [ ] Create `identity/design_system.md` — the visual standard Brain researched
- [ ] Include:
  - Component library: shadcn/ui
  - Animation library: Framer Motion (specific animation patterns)
  - Typography: font families, sizes, weights, line heights
  - Color system: palette structure, dark mode, accent usage
  - Spacing: 4px/8px grid, padding/margin rules
  - Shadows, borders, hover states, focus rings
  - Empty states, loading states, error states (all must be designed)
  - Mobile-first responsive breakpoints
  - What "good" looks like (with descriptions)
  - What "bad" looks like (anti-patterns)
- [ ] Version it in strategy store so it can evolve

### Task 5.3: Write the marketing page prompt
- [ ] Create `identity/marketing_design.md` — separate standard for landing/marketing pages
- [ ] Include:
  - Hero section structure
  - Social proof patterns
  - CTA design and placement
  - Above-the-fold content rules
  - Testimonial formatting
  - Pricing table design
  - Footer structure
- [ ] These are conversion-optimized, not app-UX-optimized (different aesthetic)

### Task 5.4: Inject into Hands pipeline
- [ ] Hands frontend phase loads `identity/design_system.md` as system prompt prefix
- [ ] Hands marketing builds load `identity/marketing_design.md` instead
- [ ] The prompt is injected at the API call level — Hands doesn't think about design, it just executes Brain's standard
- [ ] Test: build two different apps → both should look like they came from the same design team

### Task 5.5: Visual scoring calibration
- [ ] Define the visual scoring rubric (what 5/10 looks like vs 8/10 vs 10/10)
- [ ] Critic uses this rubric when evaluating screenshots
- [ ] Store visual scores alongside execution scores
- [ ] Strategy evolution can now improve the design prompt based on visual scores

**Done when:** Two different apps built by Hands look like they came from the same design team. A human looking at them would assume one designer made both.

---

## OBJECTIVE 6: Full Production-Ready SaaS Build

> **Purpose:** The end goal. One niche → one complete, beautiful, working web application.

### Task 6.1: Pick one specific niche and lock it in
- [ ] Choose a niche with enough Brain research data (e.g., productized-services or a new targeted one)
- [ ] Define precisely: who is the user, what is their pain, what is the core feature
- [ ] Example: "Client portal for web agencies — freelancers share project status with clients"
- [ ] Brain researches this niche deeply (at least 5 accepted outputs, score ≥ 7 average)

### Task 6.2: Phase 0 — Context Intake
- [ ] Brain's research → PRD (Product Requirements Document)
- [ ] PRD includes: user persona, core feature, success criteria, tech stack, UI direction
- [ ] One Claude Sonnet call with full research context
- [ ] Output stored as `projects/{niche}/prd.md`

### Task 6.3: Phase 1 — Architecture Agent
- [ ] Takes PRD → produces blueprint
- [ ] Outputs:
  - File/folder structure
  - API contract (endpoints, request/response shapes)
  - Supabase schema (tables, relationships, RLS)
  - Component hierarchy
  - Environment variables list
- [ ] **HUMAN REVIEW GATE** — you approve the blueprint before any code is written
- [ ] Stored as `projects/{niche}/architecture.md`

### Task 6.4: Phase 2 — Workspace Setup
- [ ] Scaffold Next.js project with App Router
- [ ] Install dependencies: Tailwind, shadcn/ui, Framer Motion, Supabase client
- [ ] Set up Supabase project (via MCP or manual for now)
- [ ] Create database schema via SQL migration
- [ ] Initialize Git repo
- [ ] Verify: `npm run dev` starts without errors
- [ ] Screenshot: blank slate confirmed

### Task 6.5: Phase 3 — Backend Agent
- [ ] Build API routes one feature at a time
- [ ] Auth flow: sign up, login, session management, logout
- [ ] Core feature CRUD operations
- [ ] Supabase RLS policies
- [ ] Test each endpoint via HTTP tool before moving on
- [ ] Verify: all endpoints return correct response shapes
- [ ] Verify: auth works (can sign up, login, get session)
- [ ] Verify: data persists correctly in Supabase

### Task 6.6: Phase 4 — Frontend Agent
- [ ] Design system prompt injected from `identity/design_system.md`
- [ ] Build order: layout shell → auth pages → core feature pages → settings → empty/loading/error states
- [ ] For each component group:
  - Write components
  - Screenshot via Playwright
  - Claude vision evaluates against design standard
  - Fix visual issues
  - Screenshot again (max 2 iterations per group)
- [ ] Mobile responsive verification (viewport 375px screenshot)

### Task 6.7: Phase 5 — Integration Agent
- [ ] Playwright acts as a real user:
  - Navigate to /signup
  - Fill form, submit
  - Verify redirect to dashboard
  - Use the core feature (create/read/update/delete)
  - Check Supabase: data persisted correctly
  - Logout, login again — session restored
  - Test error states (bad input, empty states)
- [ ] `npm run build` passes clean
- [ ] Fix anything that breaks

### Task 6.8: Phase 6 — DevOps Agent
- [ ] Push to GitHub
- [ ] Deploy to Vercel via CLI
- [ ] Set production environment variables
- [ ] Screenshot live URL (not localhost)
- [ ] Run integration test suite against live URL
- [ ] Verify: app works in production exactly as it did locally

### Task 6.9: Phase 7 — Critic + Learning
- [ ] Score the full output against the PRD
- [ ] Visual quality score from screenshot evaluation
- [ ] Integration test pass rate
- [ ] Total cost and time per phase
- [ ] What failed and was retried
- [ ] Store all lessons in exec_memory and Brain's knowledge base
- [ ] Feed back to strategy store for next build

### Task 6.10: Final delivery
- [ ] Live URL sent to you via Telegram
- [ ] Summary: what was built, for whom, cost, time, confidence score
- [ ] GitHub repo link
- [ ] Screenshot gallery of the live app
- [ ] You open the URL and see a production-ready, beautiful web application

**Done when:** Cortex returns a live SaaS URL with working auth and one core feature. Playwright tested end-to-end. Looks beautiful. You didn't write a single line of code for it.

---

## Dependency Map

```
OBJECTIVE 1 (Fix Bugs)
    │
    ▼
OBJECTIVE 2 (First Hands Execution)
    │
    ├──────────────────┐
    ▼                  ▼
OBJECTIVE 3         OBJECTIVE 4
(Three-Way Comm)    (Playwright Eyes)
    │                  │
    ▼                  ▼
    └────────┬─────────┘
             │
             ▼
      OBJECTIVE 5
      (Visual Standard)
             │
             ▼
      OBJECTIVE 6
      (Full SaaS Build)
```

Objectives 3 and 4 can be worked in parallel after Objective 2 is complete.
Objective 5 requires both 3 (Brain researches design) and 4 (Playwright to verify visual output).
Objective 6 requires everything above it.

---

## Timeline (Honest)

| Objective | Estimated Time | Cumulative |
|-----------|---------------|------------|
| 1. Fix Bugs | 1–2 days | Day 2 |
| 2. First Hands Execution | 1–2 weeks | Week 2 |
| 3. Three-Way Communication | 1–2 weeks | Week 3 |
| 4. Playwright Visual Loop | 1 week | Week 3 (parallel with 3) |
| 5. Visual Standard | 1 week | Week 4 |
| 6. Full SaaS Build | 2–4 weeks | Week 6–8 |

**Total: 6–8 weeks of focused work.**

---

## What This Plan Does NOT Include (Deferred)

These are all real and valid — but they come AFTER Objective 6 is proven:

- **Growth Capability** (content, SEO, outreach, Reddit marketing)
- **Reddit research pipeline** (PRAW integration, subreddit scraping)
- **Outreach Agent** (posting to Reddit/Twitter)
- **Analytics Agent** (monitoring signups, churn, activation)
- **Economics Agent** (kill/pivot/double-down decisions)
- **Multi-instance scaling** (new VPS per new Cortex)
- **Docker sandbox isolation** (each build in its own container)
- **Supabase MCP** (using CLI/API directly for now)
- **Dashboard deployment** (CLI is fine for now)

Each of these becomes its own Objective after the first beautiful webapp ships.

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
