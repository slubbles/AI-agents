# Cortex — Complete System Documentation

> **Handoff Document for Consultants**  
> Generated: March 3, 2026  
> Last VPS State Check: March 3, 2026 07:47 CET

This document provides complete context on **Cortex**, an autonomous dual-agent AI system built by a solo developer (the "Architect") over approximately 2 weeks of intensive development. The system is designed to research, build, and sell solutions autonomously — learning and improving from every cycle.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Vision — Why This Exists](#2-the-vision--why-this-exists)
3. [The Naming — "Cortex", "Brain", "Hands"](#3-the-naming--cortex-brain-hands)
4. [Architecture Overview](#4-architecture-overview)
5. [The 5-Layer Self-Learning System](#5-the-5-layer-self-learning-system)
6. [Agent Brain — Research Subsystem](#6-agent-brain--research-subsystem)
7. [Agent Hands — Execution Subsystem](#7-agent-hands--execution-subsystem)
8. [The Orchestrator Layer](#8-the-orchestrator-layer)
9. [The Identity Layer](#9-the-identity-layer)
10. [Infrastructure & Operations](#10-infrastructure--operations)
11. [Current VPS State](#11-current-vps-state)
12. [Known Issues & Technical Debt](#12-known-issues--technical-debt)
13. [The Architect's Vision Documents — Summary](#13-the-architects-vision-documents--summary)
14. [Roadmap](#14-roadmap)
15. [Codebase Statistics](#15-codebase-statistics)
16. [Appendix: File Inventory](#16-appendix-file-inventory)

---

## 1. Executive Summary

**What Cortex Is:**
Cortex is a dual-agent autonomous AI system consisting of:
- **Agent Brain** — A self-learning research engine that searches the web, scores its own outputs, and evolves its strategies based on empirical performance data
- **Agent Hands** — An execution engine that writes code, uses tools, and deploys solutions
- **Cortex Orchestrator** — The reasoning layer above both, making strategic decisions about what to research and build

**What Makes It Novel:**
The system implements 5 layers of "self-learning" — not through model weight updates, but through **strategy document evolution driven by empirical scoring**. The strategies are natural language documents that the system reads, reasons about, and rewrites based on what works.

**Current State:**
- Deployed on VPS (207.180.219.27), running as systemd services
- 4,053 research outputs in database, 2,344 cost entries, 37 pending Hands tasks
- Daemon is active but in "cooldown" state
- ~41,600 lines of Python code, 1,538 tests passing
- Daily budget: $7.00 USD ($2 Claude + $5 OpenRouter)

**Key Challenge:**
The Brain→Hands pipeline is broken (0 tasks executed). The system researches effectively but doesn't act on what it learns. This is the highest-priority fix.

---

## 2. The Vision — Why This Exists

### The Architect's Goal

The Architect is a full-stack developer building a system that, when pointed at any domain:

1. **Researches** the domain (finds opportunities, gaps, problems)
2. **Validates** demand (tests if real humans care and will pay)
3. **Builds** the solution (code, landing pages, SaaS products)
4. **Deploys and markets** it (SEO, outreach, content)
5. **Acquires customers** and generates revenue
6. **Learns from outcomes** and compounds intelligence across domains
7. **Repeats** — getting cheaper and smarter each cycle

### The Analogy: Transistor → H100

The Architect's perspective (from their notes):

> "It's like I'm building a transistor right now, but it processes real-world interaction across domains. Once we have one fully capable AI system, I will deploy multiple of it across multiple VPS and add an orchestrator layer on top. Like how NVIDIA worked on one transistor and now has H100."

**The scaling vision:**
```
STAGE 1 (NOW):     Building the transistor — one Brain + Hands, one domain
STAGE 2 (6-12mo):  Single fully capable instance, multiple domains
STAGE 3 (1-2yr):   Multiple instances on multiple VPS, Meta Orchestrator
STAGE 4 (2-3yr):   Network effect — instances teaching each other
STAGE 5 (3-5yr):   General problem solving at scale
```

### First Revenue Target

Before the grand vision, the system needs to earn money to survive. The immediate target:

- **Productized services**: Next.js landing pages for OnlineJobsPH employers
- **Fixed scope, fixed price**: 5-day delivery, $300-500 per project
- **Strategy**: Find job listings → Research the company using Brain → Send personalized pitch → Deliver using Hands

This is why the "productized-services" and "onlinejobsph-employers" domains exist in the system.

---

## 3. The Naming — "Cortex", "Brain", "Hands"

### Why "Cortex"

The name comes from the cerebral cortex — the outer layer of the brain responsible for higher-level processing, reasoning, and decision-making. In this system:

- **Cortex** = The overall system, and specifically the strategic orchestrator that sits above everything
- The name reflects the system's role as a "thinking" layer that coordinates lower-level functions

### Why "Brain" and "Hands"

From the Architect's original conversations (ULTIMATE PURPOSE.txt):

> "Agent Brain is the research/learning side. Agent Hands is the execution/doing side. Brain learns, Hands acts. They need each other — research without action is academic, action without research is blind."

The metaphor:
- **Brain** = Cognition, learning, memory, strategy
- **Hands** = Execution, building, deploying, doing

This isn't just branding — it's an architectural constraint. The two subsystems are built to communicate through a formal task queue (sync.py), not ad-hoc function calls.

---

## 4. Architecture Overview

### High-Level Structure

```
                         YOU (Architect)
                              │
                              ▼
╔══════════════════════════════════════════════════════════════╗
║                      IDENTITY LAYER                          ║
║                                                              ║
║   goals.md    ethics.md    boundaries.md    risk.md    taste.md   ║
║                                                              ║
║   What the system exists to do, what it will never do,      ║
║   its operational limits, risk tolerance, quality standards  ║
╚═══════════════════════════════╤══════════════════════════════╝
                                │
╔═══════════════════════════════▼══════════════════════════════╗
║                    CORTEX ORCHESTRATOR                       ║
║                                                              ║
║   Strategic reasoning layer (Claude Sonnet)                  ║
║   - plan_next_actions(): What to focus on next              ║
║   - assess_system(): Unified health check                   ║
║   - interpret_findings(): Learn from each cycle             ║
╚═════════════════╤═══════════════════════════╤════════════════╝
                  │                           │
╔═════════════════▼═══════════╗  ╔═══════════▼═════════════════╗
║       AGENT BRAIN           ║  ║       AGENT HANDS            ║
║                             ║  ║                              ║
║   Research subsystem        ║  ║   Execution subsystem        ║
║   - Researcher Agent        ║  ║   - Planner Agent            ║
║   - Critic Agent            ║  ║   - Executor Agent           ║
║   - Meta-Analyst            ║◀─║   - Validator Agent          ║
║   - Question Generator      ║  ║   - Pattern Learner          ║
║   - Synthesizer             ║  ║   - Project Orchestrator     ║
║   - Verifier                ║──▶   - 5 Tool Categories        ║
║   - Pre-screener            ║  ║                              ║
╚═════════════════════════════╝  ╚══════════════════════════════╝
              │                              │
              └──────────┬───────────────────┘
                         │
╔════════════════════════▼═════════════════════════════════════╗
║                   INFRASTRUCTURE                             ║
║                                                              ║
║   Scheduler (daemon loop)    │    Watchdog (circuit breaker) ║
║   Sync (Brain↔Hands queue)   │    Cost Tracker (budget)      ║
║   Memory Store (knowledge)   │    Strategy Store (versions)  ║
║   Analytics (score trends)   │    Monitoring (health checks) ║
║   Telegram Bot (alerts/chat) │    DB (SQLite WAL mode)       ║
╚══════════════════════════════════════════════════════════════╝
```

### Model Routing — 4-Tier Architecture

The system uses different AI models for different purposes, optimizing cost vs. quality:

| Tier | Model | Use Case | Cost |
|------|-------|----------|------|
| **T1 (Cheapest)** | DeepSeek V3.2 | High-volume tasks: question generation, pre-screening | ~$0.14/1M tokens |
| **T2 (Fast)** | Grok 4.1 Fast | Latency-sensitive: researcher tool loops | ~$0.50/$2.00/1M |
| **T3 (Premium)** | Claude Sonnet 4 | Sacred tasks: critic, meta-analyst, orchestrator | ~$3/$15/1M |
| **T4 (Chat)** | Gemini 2.0 Flash | Human chat interface | ~$0.075/$0.30/1M |

**Design principle:** Claude is reserved for reasoning that actually matters. Never use Claude where a cheaper model would suffice.

---

## 5. The 5-Layer Self-Learning System

This is the novel contribution. The Architect explicitly defined what "self-learning" means for this system:

### Layer 1: Knowledge Accumulation
> "The agent acts, the output is stored, it can be retrieved later."

**Implementation:** `memory_store.py` — Every research output is stored as JSON with the question, findings, sources, timestamps. RAG (ChromaDB) enables semantic retrieval.

**Status:** ✅ Working (4,053 outputs in database)

### Layer 2: Evaluated Knowledge
> "A critic scores the output 1-10 on a structured rubric. The score is stored alongside the output."

**Implementation:** `agents/critic.py` — 5-dimensional scoring rubric:
- Accuracy (30%) — Factual correctness
- Depth (20%) — Beyond surface-level
- Completeness (20%) — Important angles covered
- Specificity (15%) — Concrete data, numbers, sources
- Intellectual Honesty (15%) — Flags uncertainty

**Status:** ✅ Working (ensemble mode with DeepSeek as second voice, confidence validation)

### Layer 3: Behavioral Adaptation
> "The Meta-Analyst extracts patterns from scores → rewrites agent strategy documents. The strategy is natural language that the agent follows. Evolves every few outputs."

**Implementation:** `agents/meta_analyst.py` + `strategy_store.py`

The meta-analyst:
1. Loads recent scored outputs for a domain
2. Analyzes what scored well vs. poorly
3. Extracts actionable patterns
4. Generates a NEW strategy document
5. New strategy is saved as "pending" → requires human approval → promoted to "trial" → evaluated → promoted to "active" or rolled back

**Status:** ⚠️ Partially working (strategies exist but most domains stuck in "trial" without promotion)

### Layer 4: Strategy Evolution
> "The strategy rewriting itself becomes autonomous and recursive. Version control + rollback."

**Implementation:** `strategy_store.py` manages:
- Versioned strategy files (v001.md, v002.md, etc.)
- Lifecycle states: pending → trial → active
- Automatic rollback if new strategy causes score drops >1.0
- Safety: never deploy strategy scoring >20% below current best without human review

**Status:** ⚠️ Infrastructure built, but evolution is stalled (most domains never reached "active")

### Layer 5: Cross-Domain Transfer
> "Insights from Domain A abstracted into general principles → applied as strategy seeds in Domain B."

**Implementation:** `agents/cross_domain.py` + `strategies/_principles.json`

The system:
1. Extracts domain-agnostic lessons from successful strategies
2. Stores them as "principles" (e.g., "cite specific numbers, not vague claims")
3. When seeding a new domain, injects relevant principles as starting strategy

**Status:** ✅ Infrastructure built, cross-domain extraction done, principles file exists

### The Key Insight

From the Architect's notes:

> "Not the agents. Not the memory. Not the tools. **The strategy evolution loop with empirical scoring is the novel piece.** Strategies are natural language documents — the LLM can read, reason about, and rewrite them. Performance is measured empirically via the Critic, not assumed."

This is genuinely achievable with current tools — no research breakthroughs needed, just careful engineering.

---

## 6. Agent Brain — Research Subsystem

### Agents in Brain

#### Researcher Agent (`agents/researcher.py`, 682 lines)
**Purpose:** Takes a question + strategy → uses web search tools → produces structured findings.

**How it works:**
1. Receives a research question and domain strategy
2. Plans search approach (decomposes into sub-questions)
3. Executes web searches (DuckDuckGo via `tools/web_search.py`)
4. Fetches relevant pages (Scrapling via `tools/web_fetcher.py`)
5. Synthesizes findings into structured JSON output

**Model:** Grok 4.1 Fast (T2) — needs good tool-use capability at reasonable cost

**Key features:**
- Date-aware: knows today's date, penalizes claims about future
- Anti-hallucination rules: "An honest 'I could not find X' scores HIGHER than a fabricated answer"
- Injects: identity summary, domain strategy, RAG context, knowledge graph summary, rejection lessons

#### Critic Agent (`agents/critic.py`, 511 lines)
**Purpose:** Reviews researcher output → scores 1-10 → provides actionable feedback.

**How it works:**
1. Receives the research output and original question
2. Evaluates against 5-dimensional rubric
3. Produces scores, verdict (accept/reject), and specific feedback
4. Optionally runs ensemble mode (second opinion from DeepSeek)
5. Post-hoc confidence validation (high-confidence claims must cite 2+ sources)

**Model:** Claude Sonnet 4 (T3) — this is SACRED, never cut corners

**Threshold:** Score ≥ 6 to accept. Below 6 → retry with critique feedback (max 2 retries).

#### Pre-screener (`prescreen.py`, 245 lines)
**Purpose:** Cheap filter before expensive Claude critique.

**How it works:**
- Quick-scores using DeepSeek (T1)
- Accept if score ≥ 7.5 (skip Claude)
- Reject if score ≤ 3.5 (skip Claude)
- Escalate to Claude if between

**Cost savings:** ~40% reduction in Claude critic calls

#### Meta-Analyst (`agents/meta_analyst.py`, 410 lines)
**Purpose:** Extracts patterns from scored outputs → rewrites strategy documents.

**How it works:**
1. Loads recent scored outputs for domain (configurable window)
2. Loads evolution history (what was tried before, what worked)
3. Analyzes patterns: what dimensions scored high/low?
4. Generates new strategy document incorporating lessons
5. Saves as "pending" with changelog

**Model:** Claude Sonnet (T3) — strategy quality determines research quality

**Constraints:**
- Suppressed during warmup (need minimum outputs before evolving)
- Suppressed during trial period (let trial run before changing again)
- Respects `IMMUTABLE_STRATEGY_CLAUSES` — some rules can't be changed

#### Question Generator (`agents/question_generator.py`, 417 lines)
**Purpose:** Diagnoses knowledge gaps → generates next research question.

**How it works:**
1. Reads memory + knowledge base + domain goal
2. Identifies what's been covered vs. what's missing
3. Generates ranked list of next questions
4. Top question becomes next research round

**Model:** DeepSeek V3.2 (T1) — synthesis task, doesn't need premium reasoning

#### Synthesizer (`agents/synthesizer.py`, 439 lines)
**Purpose:** Integrates new findings into the domain knowledge base.

**How it works:**
1. Takes accepted research output
2. Extracts claims from findings
3. Checks for contradictions with existing KB
4. Integrates non-contradicting claims
5. Flags contradictions for human review

**Model:** Claude Sonnet (T3) — knowledge integration affects downstream quality

#### Verifier (`agents/verifier.py`, 337 lines)
**Purpose:** Tracks time-bound predictions → checks against reality.

**How it works:**
1. Extracts predictive claims from research (e.g., "X will happen by Q2 2026")
2. Stores with verification deadline
3. When deadline passes, checks web for outcome
4. Updates claim confidence based on prediction accuracy

**Status:** ⚠️ Infrastructure built but underused — this is the key to breaking self-referential scoring

#### Consensus Agent (`agents/consensus.py`, 284 lines)
**Purpose:** Multi-agent agreement on controversial questions.

**How it works:**
1. Same question sent to 3 independent researchers
2. Each produces findings independently
3. Synthesizer merges results
4. Disagreements flagged for review

**Status:** ⚠️ Built but not used in daemon loop

### Memory & Knowledge

- **Memory Store** (`memory_store.py`, 907 lines): CRUD for outputs, KB claims, knowledge gaps
- **RAG** (`rag/vector_store.py`): ChromaDB semantic search, 217 claims indexed
- **Knowledge Graph** (`knowledge_graph.py`, 632 lines): Entity/relation extraction from claims

---

## 7. Agent Hands — Execution Subsystem

### Core Execution Pipeline

#### Planner (`hands/planner.py`, 546 lines)
**Purpose:** Decomposes a task into concrete, tool-using steps.

**Input:**
- Goal (natural language task description)
- Available tools (from registry)
- Domain knowledge (from Brain's KB)
- Execution strategy (from strategy store)
- Workspace context (file tree, key files)

**Output:**
- Structured plan: ordered steps with tool selections and parameters
- Each step marked "required" or "optional" for criticality handling

**Model:** Claude Sonnet (T3) — plan quality determines execution quality

#### Executor (`hands/executor.py`, 832 lines)
**Purpose:** Executes a plan step-by-step using tools.

**How it works:**
1. Receives structured plan from Planner
2. For each step:
   - Calls appropriate tool
   - Handles tool response
   - Retries on failure (up to 2 per step)
   - Tracks cost, artifacts, timeline
3. Manages context window (summarizes old steps to stay within limits)
4. Hard cost ceiling: $0.50 per execution

**Model:** Claude Haiku (cheaper) — just following instructions

#### Validator (`hands/validator.py`, 798 lines)
**Purpose:** Validates execution outputs against expectations.

**How it works:**
1. Receives execution results
2. Checks: Did the goal get accomplished?
3. Runs any automated tests
4. Scores execution quality
5. Provides feedback for learning

### Tools (5 Categories)

| Tool | File | Purpose |
|------|------|---------|
| **Code** | `hands/tools/code.py` (394 lines) | Write, edit, read files |
| **Terminal** | `hands/tools/terminal.py` (258 lines) | Run shell commands |
| **Git** | `hands/tools/git.py` (206 lines) | Git operations |
| **Search** | `hands/tools/search.py` (352 lines) | Web search |
| **HTTP** | `hands/tools/http.py` (229 lines) | HTTP requests, API calls |

### Learning Layer

#### Pattern Learner (`hands/pattern_learner.py`, 497 lines)
**Purpose:** Extracts reusable patterns from execution history.

**What it learns:**
- Tool usage patterns that correlate with high/low scores
- Step sequences that reliably succeed or fail
- Error categories and their resolutions
- Domain-specific execution heuristics

**Output:** "Execution lessons" injected into future planner/executor prompts

Example lesson:
> "npm install fails without --prefix when cwd doesn't have package.json"

#### Project Orchestrator (`hands/project_orchestrator.py`, 833 lines)
**Purpose:** Manages multi-phase projects end-to-end.

For "build me a SaaS app":
1. **DECOMPOSE**: Break into phases (architecture, setup, features, tests, deploy)
2. **PLAN**: Each phase planned with Planner
3. **EXECUTE**: Phases run sequentially with validation gates
4. **CHECKPOINT**: Progress saved after each phase
5. **REVIEW**: Human review at critical phases (architecture, deploy)

### Additional Hands Components

- `error_analyzer.py` — Root cause analysis for failures
- `exec_meta.py` — Execution strategy evolution (parallel to Brain's meta-analyst)
- `feedback_cache.py` — Caches correction feedback
- `mid_validator.py` — Mid-execution validation
- `output_polisher.py` — Cleans up execution outputs
- `plan_cache.py` — Caches similar plans
- `plan_preflight.py` — Validates plan before execution
- `retry_advisor.py` — Advises on retry strategies
- `strategy_assembler.py` — Builds execution strategies
- `task_generator.py` — Generates tasks from goals
- `timeout_adapter.py` — Adapts timeouts based on task complexity
- `tool_health.py` — Monitors tool reliability
- `workspace_diff.py` — Tracks changes to workspace

---

## 8. The Orchestrator Layer

### Scheduler (`scheduler.py`, 1,812 lines)
**Purpose:** The daemon loop that runs everything.

**How it works:**
1. **Plan phase**: Cortex Orchestrator decides what to focus on
2. **Allocate**: Distribute rounds across domains based on priorities
3. **Execute**: Run research rounds
4. **Learn**: Run meta-analyst if enough outputs
5. **Sync**: Create tasks for Hands if research suggests actions
6. **Health check**: Run monitoring
7. **Sleep**: Wait for next cycle
8. **Repeat**

**Configuration:**
- `--daemon`: Run as daemon
- `--interval N`: Minutes between cycles (default 60)
- `--autonomous`: No human approval required for trials
- `--rounds-per-cycle N`: Max rounds per cycle (default 5)

### Watchdog (`watchdog.py`, 601 lines)
**Purpose:** Circuit breaker and health monitoring for 24/7 operation.

**Responsibilities:**
1. **Heartbeat monitoring**: Detect stalled processes
2. **Health checks**: Run `monitoring.run_health_check()` each cycle
3. **Circuit breaker**: Pause on 3 consecutive critical alerts
4. **Crash counter**: Track consecutive failures, trigger cooldown after 5
5. **Cost ceiling**: Hard stop at 1.5x daily budget
6. **Recovery**: Auto-restart after transient failures

**States:**
- `running` — Normal operation
- `paused` — Temporarily paused (will auto-resume)
- `cooldown` — Cooling down after failures (30 minutes)
- `circuit_open` — Circuit breaker tripped (needs human review)
- `budget_halt` — Hard cost ceiling hit
- `stopped` — Gracefully stopped

### Sync (`sync.py`, 461 lines)
**Purpose:** Brain → Hands task queue.

**How it works:**
1. Brain research suggests an action (e.g., "We should build X")
2. Scheduler creates a task via `create_task()`
3. Task enters queue as "pending"
4. Hands picks up pending tasks
5. Task moves to "in_progress" → "completed" or "failed"
6. Stale tasks (>72h without action) get flagged

**Task types:** `action`, `build`, `deploy`, `investigate`

**Current issue:** Tasks are created as "investigate" but Hands only accepts "build"/"action" — **this is why 0 tasks have executed**.

### Cortex Orchestrator (`agents/cortex.py`, 628 lines)
**Purpose:** The "brain of brains" — strategic reasoning above everything.

**Key functions:**
- `plan_next_actions()`: Analyzes all domain stats, budget, goals → recommends what to focus on
- `assess_system()`: Unified health assessment across Brain + Hands
- `interpret_findings()`: After each cycle, extract strategic insights
- `query_orchestrator()`: Ad-hoc strategic questions

**Model:** Claude Sonnet (T3) — orchestration decisions are sacred

---

## 9. The Identity Layer

The Identity Layer is a set of 5 markdown files that define what the system is, what it will do, and what it will never do. Every agent reads these. They are **immutable** by the system itself.

### goals.md — What the System Exists to Do

**Primary Goal:**
> "Generate revenue by finding, validating, building, and selling solutions to real problems."

**Operating Goals (in priority order):**
1. **Stay alive.** Don't blow the budget. Don't crash.
2. **Learn things that lead to action.** Research only valuable if it changes what we build.
3. **Ship revenue-generating work.** Productized services first, SaaS second.
4. **Compound intelligence.** Cross-domain transfer is the multiplier.
5. **Increase autonomy.** Earn trust through reliability.

### ethics.md — Hard Constraints

**Never Do:**
1. Never falsify research
2. Never deceive users
3. Never make irreversible decisions without human approval
4. Never optimize against constraints (budget, circuit breaker, quality threshold)
5. Never harm real people
6. Never access systems without authorization

**Always Do:**
1. Flag uncertainty
2. Log everything
3. Respect cost boundaries
4. Preserve human control

### boundaries.md — Operational Limits

**Budget:**
- Daily spend limit: $7.00 USD
- Hard ceiling: 1.5x daily ($10.50)
- Per-round cost awareness: Skip if >25% of remaining budget

**Autonomy:**
- Strategy changes require human approval (unless `--autonomous`)
- No self-modification of safety code
- No external deployments without approval

**Quality:**
- Minimum threshold: 6/10
- Maximum retries: 2
- Auto-rollback on >1.0 score drop

### risk.md — Risk Tolerance

**Risk Tiers:**
- **Tier 1 (Proven domains, 10+ outputs):** Up to 40% of daily budget, may trial new strategies freely
- **Tier 2 (Developing, 3-10 outputs):** Up to 25% of budget, new strategies must beat baseline by ≥0.5
- **Tier 3 (New domains, 0-2 outputs):** Up to 15% of budget, use seed strategy first

**Cost Risk:**
- Never spend >$0.50 on a single round
- At 80% of daily limit → minimum-cost operations only

### taste.md — Quality Standards

**Good Research:**
- Specific, not vague: "72% ghosting rate (2024 survey, n=500)" > "reliability is a problem"
- Sourced, not assumed
- Actionable, not academic
- Honest about uncertainty

**Bad Research:**
- Generic summaries
- Claims without sources
- Restates question as answer
- Adds no new information

---

## 10. Infrastructure & Operations

### Database (`db.py`, 646 lines)

SQLite with WAL mode for concurrent access.

**Tables:**
| Table | Records | Purpose |
|-------|---------|---------|
| `outputs` | 4,053 | Research outputs with scores and metadata |
| `costs` | 2,344 | API cost tracking per call |
| `alerts` | 183 | Health alerts history |
| `health_snapshots` | 124 | Periodic health state |
| `run_log` | 212 | Research run history |

### Cost Tracking (`cost_tracker.py`, 243 lines)

Dual-write to JSONL + SQLite database.

**Budget configuration:**
- `DAILY_BUDGET_USD = 7.00` ($2 Claude + $5 OpenRouter)
- `HARD_COST_CEILING_USD = 10.50` (1.5x daily)
- Per-provider tracking (Claude separate from OpenRouter)

**Known issue:** `check_budget()` reads from JSONL which doesn't always sync with DB.

### Monitoring (`monitoring.py`, 327 lines)

6 automated health checks:
1. **Score trends**: Detect declining quality
2. **Sudden drops**: Alert on >1.5 point score drops
3. **Budget velocity**: Alert if spending too fast
4. **Stale domains**: Flag domains with no activity >7 days
5. **Rejection rates**: Alert if >50% rejections
6. **Error rates**: Alert on high error counts

### Analytics (`analytics.py`, 816 lines)

- `score_trajectory(domain)`: Score trend over time
- `domain_comparison()`: Compare all domains
- `recommendations()`: Suggest focus areas

### Telegram Bot (`telegram_bot.py`, 680 lines)

Full chat interface + alerting.

**Features:**
- `/status` — System status
- `/budget` — Budget report
- `/domains` — Domain list
- `/research <question>` — Run research
- Alert forwarding from monitoring

**Status:** ✅ Running on VPS (3h 26min uptime as of last check)

### VPS Deployment

**Server:** 207.180.219.27 (Contabo VPS)
**OS:** Ubuntu 24.04.3 LTS
**Services:**
- `cortex-daemon.service` — Main daemon loop
- `cortex-telegram.service` — Telegram bot

**Systemd configuration:**
```ini
[Service]
ExecStart=/root/AI-agents/agent-brain/venv/bin/python3 main.py --daemon --interval 60 --autonomous
MemoryMax=2G
Restart=on-failure
RestartSec=30
```

---

## 11. Current VPS State

*Checked: March 3, 2026 07:47 CET*

### Service Status

| Service | Status | Uptime | Memory |
|---------|--------|--------|--------|
| cortex-daemon | ✅ Active (running) | 31 min | 587 MB / 2 GB |
| cortex-telegram | ✅ Active (running) | 3h 26min | 117 MB / 1 GB |

### Database Statistics

| Table | Count |
|-------|-------|
| outputs | 4,053 |
| costs | 2,344 |
| alerts | 183 |
| health_snapshots | 124 |
| run_log | 212 |

### Domain Breakdown (from outputs table)

| Domain | Output Count | Notes |
|--------|--------------|-------|
| test | 3,809 | Testing data |
| economics | 174 | Active research |
| productized-services | 29 | Revenue-focused |
| nextjs-react | 26 | Tech domain |
| general | 6 | Catch-all |
| geopolitics | 2 | — |
| onlinejobsph-employers | 2 | Revenue target |
| physics | 2 | — |
| ai | 1 | — |
| crypto | 1 | — |
| cybersecurity | 1 | — |

### Sync Tasks (Brain → Hands Queue)

```
Total: 37 tasks
By type: {'investigate': 36, 'deploy': 1}
By status: {'pending': 37}
```

**🚨 Critical:** All 37 tasks are pending. Zero executed. The pipeline is broken.

### Strategy Status

All domains show `unknown` status with 0 versions — likely a data sync issue with VPS strategies directory.

### Budget

```
Spent today: $0.63
Limit: $7.00
Remaining: $6.37
Within budget: True
```

### Watchdog State

```
State: cooldown
Consecutive failures: 0
Cooldowns: 0
```

The "cooldown" state indicates the system paused after hitting some threshold.

### Latest Commits (on VPS)

```
86a2e2b fix: eliminate ChromaDB recursion by removing embedding_function from collections
2a438e9 fix: domain alignment ordering, rounds_per_cycle=5, total_planned cap, RAG recursion 10k
b526a5a Fix 5 critical gaps: RAG recursion, domain alignment, circuit breaker, DB init, scrapling
ec35c9a Fix round timeout + smart sync task priorities for Hands auto-exec
9a4ad82 Fix 6 critical gaps: autonomous mode, Hands in daemon, Cortex enforcement, cycle persistence, DB init, test isolation
```

---

## 12. Known Issues & Technical Debt

### Critical (Blocks Core Functionality)

#### 1. Brain→Hands Pipeline Broken
**Symptom:** 37 sync tasks created, 0 executed
**Root cause:** `_create_tasks_from_research()` creates tasks with type "investigate" (36/37) and "deploy" (1/37). But `_execute_hands_tasks()` only accepts "build" or "action" types.
**Impact:** The system learns but never acts on what it learns.
**Fix:** Either expand accepted types in executor OR change task creation types.

#### 2. Budget Tracking Desync
**Symptom:** JSONL shows different spend than SQLite database
**Root cause:** `check_budget()` reads from `costs.jsonl` but some cost entries only go to DB
**Impact:** System may think it has budget when it doesn't (or vice versa)
**Fix:** Make `check_budget()` read from DB as source of truth

#### 3. Watchdog in Cooldown State
**Symptom:** Daemon stuck in "cooldown" state
**Root cause:** Likely triggered by circuit breaker from repeated domain failures
**Impact:** System not actively researching
**Fix:** Investigate what caused cooldown, possibly reset state manually

### High Priority

#### 4. Strategy Evolution Stalled
**Symptom:** Most domains show "unknown" status, no active strategies
**Root cause:** Strategies exist on VPS but `_status.json` files may be missing or malformed
**Impact:** Research uses generic strategies instead of evolved ones
**Fix:** Audit strategy directories, rebuild status files

#### 5. Domain Goals Missing
**Symptom:** Only productized-services has a goal defined
**Root cause:** `domain_goals.py` wasn't populated for other domains
**Impact:** Question generator produces generic queries instead of goal-aligned ones
**Fix:** Define goals for revenue domains (onlinejobsph-employers especially)

### Medium Priority

#### 6. Consensus Agent Not Used
The consensus agent infrastructure exists but isn't called in the daemon loop. For high-stakes decisions, having 3 independent researchers would improve reliability.

#### 7. Knowledge Graph Not Auto-Triggered
The graph extraction works but isn't automatically run on new outputs. The graph data exists but gets stale.

#### 8. Dashboard Not Deployed
`dashboard/api.py` (784 lines) is built but not running on VPS. Would provide visibility without SSH.

#### 9. MCP Gateway Disconnected
`mcp/` (1,739 lines) was built for external tool servers but isn't configured.

### Low Priority / Tech Debt

- Orphaned `rag/chroma_store` directory (old RAG implementation)
- `TOTAL_BALANCE_USD` in config is hardcoded from Feb 28
- Some test isolation issues (tests leave artifacts)

---

## 13. The Architect's Vision Documents — Summary

The `/workspaces/AI-agents/my-notes.md/` directory contains the Architect's raw thinking and strategic context. Here are the key insights from each:

### ULTIMATE PURPOSE.txt (603 lines)
The origin conversation about building self-learning AI.

**Key concepts:**
- **Observable Horizon**: The system must know what it doesn't know. Three states: (1) not enough data, (2) capability gap, (3) genuine frontier of knowledge.
- **Calibrated uncertainty**: Not just confidence scores, but understanding WHY confidence is low.
- **Recursive self-improvement as a separate layer**: The thing that improves the system must be separate from the system itself.

**Memorable quote:**
> "The most dangerous version is one confidently wrong at scale."

### real-self-learning.md (231 lines)
Precise definition of the 5-layer self-learning architecture.

**Key insight:**
> "90% of memory-enabled AI projects live and die at Layer 1. They store things but never evaluate, never adapt, never evolve. Layer 3+ is what makes this novel."

### vision-hands.md
Full architecture of Brain + Hands execution vision.

**Domains planned:**
- market-research, saas-building, growth-hacking, copywriting, customer-support

**Revenue model:** Marketplace products (Shopify apps, VS Code extensions, SaaS)

### where-this-goes.md
Phase roadmap:
1. Statistical Grounding (volume of outputs)
2. Memory as Knowledge Graph
3. Multi-Agent Collaboration
4. Domain Specialization
5. Continuous Autonomous Operation

### more-insight.md
Honest gap analysis from a conversation with Claude.

**Key warnings:**
- "The system has never run unsupervised"
- "The circular critic problem is still unsolved"
- "Don't let it stay a demo"

### ACTION-PLAN.md
Concrete action items for immediate execution.

**Key point:**
> "Brain is production-ready for productized-services. Don't wait on Brain improvements to act."

### ideal-thoughts.md (3,604 lines)
The longest document — full ideal architecture discussion.

**Contains:**
- 26-agent architecture across 5 layers
- Cost optimization strategy (4-tier models)
- Model routing decisions
- HuggingFace dataset usage for local training
- Learning loop implementation details

### my-huge-perspetive.md (977 lines)
The transistor→H100 analogy and scaling vision.

**Key insight:**
> "The Identity Layer you define today in one instance becomes the values of the entire network. What you bake into that first instance is what scales to 1000 instances."

### OLJstrat-mar1.md (496 lines)
OnlineJobsPH outreach strategy for first revenue.

**The pitch structure:**
1. Pattern interrupt (prove you read their post)
2. Reframe (make alternative feel safer)
3. Specific deliverable (the list that builds trust)
4. Personalized line (from Brain's research)
5. Friction removal (payment terms)
6. Single CTA

### 8phaseplan.md
The 8-phase implementation plan from "here" to "one working transistor."

**Phases:**
1. Fix Safety Gaps
2. Integration Tests
3. Identity Layer
4. Supervised Dry Runs
5. Stability Hardening
6. Extended Unsupervised Run
7. Cortex Orchestrator in Loop
8. Confidence Gate

---

## 14. Roadmap

### Immediate (This Week)

1. **Fix Brain→Hands pipeline** — Change task types or expand accepted types
2. **Fix budget tracking desync** — Make check_budget() read from DB
3. **Reset watchdog state** — Investigate cooldown cause, reset
4. **Define domain goals** — Add goals for onlinejobsph-employers

### Short-Term (2-4 Weeks)

5. **Stabilize daemon 24/7** — Run full 72h unsupervised test
6. **Wire Cortex into daemon** — Use Sonnet reasoning for domain prioritization
7. **First Hands execution** — Get one sync task to complete successfully
8. **First revenue attempt** — Send personalized pitch to OnlineJobsPH listing

### Medium-Term (1-3 Months)

9. **Strategy evolution working** — Domains reaching "active" status automatically
10. **Dashboard deployed** — Web UI for monitoring without SSH
11. **Expand Hands tools** — Add design, deployment, outreach capabilities
12. **Verifier working** — Reality-grounded quality signal

### Long-Term (3-12 Months)

13. **Signal Agent** — Automated demand detection (Reddit, Twitter, forums)
14. **Validation Agent** — Pre-sell before building ($50 ad test)
15. **Economics Agent** — Kill/pivot/double-down decisions
16. **Multi-VPS deployment** — Second instance, meta-orchestrator

---

## 15. Codebase Statistics

### Lines of Code

| Component | Files | Lines |
|-----------|-------|-------|
| Brain Agents | 10 | ~4,200 |
| Hands System | 25+ | ~8,500 |
| Infrastructure | 15+ | ~10,000 |
| CLI | 8 | ~2,500 |
| Tools | 10 | ~2,000 |
| Browser | 4 | ~870 |
| RAG | 3 | ~914 |
| Utils | 6 | ~1,208 |
| Tests | ~40 | ~11,000 |
| **Total** | **~120** | **~41,600** |

### Test Coverage

- **Total tests:** 1,538
- **Status:** All passing
- **Key test files:**
  - `test_watchdog.py`: 52 tests
  - `test_new_features.py`: 68 tests
  - `test_integration.py`: 45 tests

### Dependencies

**Core:**
- `anthropic` — Claude API
- `openai` — OpenRouter compatibility
- `chromadb` — Vector database
- `sentence-transformers` — Embeddings
- `playwright` — Browser automation (disabled)

**Utilities:**
- `python-dotenv` — Environment config
- `httpx` — HTTP client
- `pydantic` — Data validation

---

## 16. Appendix: File Inventory

### Brain Agents (`agent-brain/agents/`)

| File | Lines | Purpose |
|------|-------|---------|
| `researcher.py` | 682 | Web research with tool use |
| `critic.py` | 511 | 5-dimensional rubric scoring |
| `cortex.py` | 628 | Strategic orchestrator |
| `cross_domain.py` | 629 | Principle extraction + transfer |
| `meta_analyst.py` | 410 | Strategy evolution |
| `question_generator.py` | 417 | Gap diagnosis → next question |
| `synthesizer.py` | 439 | KB integration |
| `verifier.py` | 337 | Prediction tracking |
| `consensus.py` | 284 | Multi-agent agreement |
| `orchestrator.py` | — | Domain orchestration |

### Hands System (`agent-brain/hands/`)

| File | Lines | Purpose |
|------|-------|---------|
| `planner.py` | 546 | Structured plan generation |
| `executor.py` | 832 | Multi-turn tool execution |
| `validator.py` | 798 | Output verification |
| `pattern_learner.py` | 497 | Learning from executions |
| `project_orchestrator.py` | 832 | Multi-phase projects |
| `exec_meta.py` | 506 | Execution strategy evolution |
| `tools/registry.py` | 343 | Tool registration |
| `tools/code.py` | 394 | Code operations |
| `tools/terminal.py` | 258 | Shell commands |
| `tools/search.py` | 352 | Web search |
| `tools/http.py` | 229 | HTTP requests |
| `tools/git.py` | 206 | Git operations |

### Infrastructure (`agent-brain/`)

| File | Lines | Purpose |
|------|-------|---------|
| `scheduler.py` | 1,812 | Daemon loop + Cortex integration |
| `watchdog.py` | 601 | Circuit breaker + health |
| `sync.py` | 461 | Brain↔Hands queue |
| `main.py` | 1,223 | CLI entry point |
| `config.py` | 324 | All configuration |
| `db.py` | 646 | SQLite backend |
| `memory_store.py` | 907 | Knowledge base management |
| `strategy_store.py` | 577 | Strategy versioning |
| `cost_tracker.py` | 243 | Budget awareness |
| `analytics.py` | 816 | Score analysis |
| `monitoring.py` | 327 | Health checks |
| `knowledge_graph.py` | 632 | Entity/relation graphs |
| `identity_loader.py` | 250 | Identity layer loading |
| `llm_router.py` | 470 | Model routing |
| `loop_guard.py` | 207 | Infinite loop prevention |
| `prescreen.py` | 245 | Cheap pre-filter |
| `telegram_bot.py` | 680 | Telegram interface |

### Identity Layer (`agent-brain/identity/`)

| File | Purpose |
|------|---------|
| `goals.md` | What the system exists to do |
| `ethics.md` | Hard constraints (never do list) |
| `boundaries.md` | Operational limits |
| `risk.md` | Risk tolerance calibration |
| `taste.md` | Quality standards |

---

## End of Document

**For questions or clarifications, contact the Architect directly.**

**Document generated by GitHub Copilot (Claude Opus 4.5) based on full codebase and VPS audit.**


---

More context:

Summarized conversation history

  

Created 6 todos

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== SERVICE STATUS ===" && systemctl is-active cortex-daemon && echo "=== UPTIME ===" && systemctl show cortex-daemon --property=ActiveEnterTimestamp && echo "=== GIT COMMIT ===" && git log --oneline -1 && echo "=== LAST 80 LINES STDOUT ===" && tail -80 logs/daemon-stdout.log && echo "=== LAST 30 LINES STDERR ===" && tail -30 logs/daemon-stderr.log'

Read [](file:///home/codespace/.vscode-remote/data/User/workspaceStorage/23b51e06/GitHub.copilot-chat/chat-session-resources/85767f3f-989d-4d3a-a95c-a12559f10226/toolu_bdrk_013FSD15ECUYxRHenFVxXp6P__vscode-1772501470942/content.txt)

Now let me get a comprehensive picture of the VPS state - cycles completed, domains, memory, strategies, sync tasks, and errors. 

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== MEMORY DOMAINS ===" && ls memory/ && echo "=== MEMORY COUNTS ===" && for d in memory/*/; do echo "$(basename $d): $(ls "$d"*.json 2>/dev/null | wc -l) outputs"; done && echo "=== STRATEGY STATUS ===" && python3 -c "
from strategy_store import StrategyStore
s = StrategyStore()
import os
for d in sorted(os.listdir(\"strategies\")):
    if os.path.isdir(f\"strategies/{d}\") and not d.startswith(\"_\"):
        info = s.get_active(d)
        status = info.get(\"status\",\"none\") if info else \"none\"
        ver = info.get(\"version\",\"?\") if info else \"?\"
        print(f\"  {d}: status={status} version={ver}\")
" 2>/dev/null && echo "=== SYNC TASKS ===" && python3 -c "
from db import get_db
db = get_db()
tasks = db.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
for t in tasks:
    print(f\"  [{t[4]}] {t[3]} | {t[2]} | {t[1]} | {t[5][:16]}\")
print(f\"  Total: {db.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]}\")
print(f\"  Pending: {db.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]}\")
print(f\"  Done: {db.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"completed\\\"\").fetchone()[0]}\")
" 2>/dev/null && echo "=== CYCLE HISTORY ===" && python3 -c "
from db import get_db
db = get_db()
rows = db.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
for r in rows:
    print(f\"  Cycle {r[0]}: {r[3]} | planned={r[4]} completed={r[5]} rounds={r[6]} cost=\${r[7]:.4f} | {(r[1] or \"\")[:16]}\")
" 2>/dev/null && echo "=== COST ===" && python3 -c "
from cost_tracker import CostTracker
c = CostTracker()
print(f\"  Daily: \${c.get_daily_spend().get(\"total_usd\", 0):.4f}\")
print(f\"  All-time: \${c.get_all_time_spend():.4f}\")
" 2>/dev/null && echo "=== ERROR COUNT IN LOGS ===" && grep -c "ERROR\|Traceback\|Exception" logs/daemon-stdout.log 2>/dev/null || echo "  0" && echo "=== RAG STATUS ===" && python3 -c "
import chromadb
client = chromadb.PersistentClient(path=\"rag/chroma_store\")
for col in client.list_collections():
    print(f\"  {col.name}: {col.count()} items\")
" 2>/dev/null'
Completed with input:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== MEMORY DOMAINS ===" && ls memory/ && echo "=== MEMORY COUNTS ===" && for d in memory/*/; do echo "$(basename $d): $(ls "$d"*.json 2>/dev/null | wc -l) outputs"; done && echo "=== STRATEGY STATUS ===" && python3 -c "
from strategy_store import StrategyStore
s = StrategyStore()
import os
for d in sorted(os.listdir(\"strategies\")):
    if os.path.isdir(f\"strategies/{d}\") and not d.startswith(\"_\"):
        info = s.get_active(d)
        status = info.get(\"status\",\"none\") if info else \"none\"
        ver = info.get(\"version\",\"?\") if info else \"?\"
        print(f\"  {d}: status={status} version={ver}\")
" 2>/dev/null && echo "=== SYNC TASKS ===" && python3 -c "
from db import get_db
db = get_db()
tasks = db.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
for t in tasks:
    print(f\"  [{t[4]}] {t[3]} | {t[2]} | {t[1]} | {t[5][:16]}\")
print(f\"  Total: {db.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]}\")
print(f\"  Pending: {db.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]}\")
print(f\"  Done: {db.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"completed\\\"\").fetchone()[0]}\")
" 2>/dev/null && echo "=== CYCLE HISTORY ===" && python3 -c "
from db import get_db
db = get_db()
rows = db.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
for r in rows:
    print(f\"  Cycle {r[0]}: {r[3]} | planned={r[4]} completed={r[5]} rounds={r[6]} cost=\${r[7]:.4f} | {(r[1] or \"\")[:16]}\")
" 2>/dev/null && echo "=== COST ===" && python3 -c "
from cost_tracker import CostTracker
c = CostTracker()
print(f\"  Daily: \${c.get_daily_spend().get(\"total_usd\", 0):.4f}\")
print(f\"  All-time: \${c.get_all_time_spend():.4f}\")
" 2>/dev/null && echo "=== ERROR COUNT IN LOGS ===" && grep -c "ERROR\|Traceback\|Exception" logs/daemon-stdout.log 2>/dev/null || echo "  0" && echo "=== RAG STATUS ===" && python3 -c "
import chromadb
client = chromadb.PersistentClient(path=\"rag/chroma_store\")
for col in client.list_collections():
    print(f\"  {col.name}: {col.count()} items\")
" 2>/dev/null'

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== STRATEGY DIRS ===" && ls strategies/ && echo "=== STRATEGY FILES ===" && for d in strategies/*/; do bn=$(basename "$d"); echo "$bn: $(ls "$d" 2>/dev/null | head -5)"; done && echo "=== SYNC TASKS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_db
db = get_db()
tasks = db.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
for t in tasks:
    print(f\"  [{t[4]}] {t[3]} | {t[2]} | {t[1]} | {t[5][:16]}\")
total = db.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]
pending = db.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]
print(f\"  Total: {total}, Pending: {pending}\")
" 2>&1 && echo "=== CYCLE HISTORY ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_db
db = get_db()
rows = db.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
for r in rows:
    end = r[2][:16] if r[2] else \"running\"
    print(f\"  Cycle {r[0]}: {r[3]} | planned={r[4]} done={r[5]} rounds={r[6]} cost=\${r[7]:.4f} | {(r[1] or \"\")[:16]} → {end}\")
" 2>&1 && echo "=== COST ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from cost_tracker import CostTracker
c = CostTracker()
d = c.get_daily_spend()
a = c.get_all_time_spend()
print(f\"  Daily: \${d.get(\"total_usd\",0):.4f}\")
print(f\"  All-time: \${a:.4f}\")
" 2>&1'
Completed with input:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== STRATEGY DIRS ===" && ls strategies/ && echo "=== STRATEGY FILES ===" && for d in strategies/*/; do bn=$(basename "$d"); echo "$bn: $(ls "$d" 2>/dev/null | head -5)"; done && echo "=== SYNC TASKS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_db
db = get_db()
tasks = db.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
for t in tasks:
    print(f\"  [{t[4]}] {t[3]} | {t[2]} | {t[1]} | {t[5][:16]}\")
total = db.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]
pending = db.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]
print(f\"  Total: {total}, Pending: {pending}\")
" 2>&1 && echo "=== CYCLE HISTORY ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_db
db = get_db()
rows = db.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
for r in rows:
    end = r[2][:16] if r[2] else \"running\"
    print(f\"  Cycle {r[0]}: {r[3]} | planned={r[4]} done={r[5]} rounds={r[6]} cost=\${r[7]:.4f} | {(r[1] or \"\")[:16]} → {end}\")
" 2>&1 && echo "=== COST ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from cost_tracker import CostTracker
c = CostTracker()
d = c.get_daily_spend()
a = c.get_all_time_spend()
print(f\"  Daily: \${d.get(\"total_usd\",0):.4f}\")
print(f\"  All-time: \${a:.4f}\")
" 2>&1'

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== DB EXPORTS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
import db as dbmod
# Find available functions
fns = [x for x in dir(dbmod) if not x.startswith(\"_\")]
print(\"DB exports:\", fns)
" 2>&1'

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_connection, get_daily_spend_db, get_all_time_spend_db, get_domain_stats_db, get_recent_scores, get_run_history, get_alert_summary

conn = get_connection()
c = conn.cursor()

print(\"=== SYNC TASKS ===\")
try:
    tasks = c.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
    for t in tasks:
        print(f\"  [{t[4]}] {t[3]} | {t[2]} | {t[1]} | {t[5][:16]}\")
    total = c.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]
    pending = c.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]
    print(f\"  Total: {total}, Pending: {pending}\")
except Exception as e:
    print(f\"  sync_tasks table: {e}\")

print(\"=== CYCLE HISTORY ===\")
try:
    rows = c.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
    for r in rows:
        end = r[2][:16] if r[2] else \"running\"
        print(f\"  Cycle {r[0]}: {r[3]} | planned={r[4]} done={r[5]} rounds={r[6]} cost=\${r[7]:.4f} | {(r[1] or \"\")[:16]} -> {end}\")
except Exception as e:
    print(f\"  daemon_cycles table: {e}\")

print(\"=== DB TABLES ===\")
tables = c.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\"\").fetchall()
for t in tables:
    count = c.execute(f\"SELECT count(*) FROM {t[0]}\").fetchone()[0]
    print(f\"  {t[0]}: {count} rows\")

print(\"=== DAILY COST ===\")
d = get_daily_spend_db()
print(f\"  {d}\")

print(\"=== ALL-TIME COST ===\")
a = get_all_time_spend_db()
print(f\"  {a}\")

print(\"=== ACTIVE ALERTS ===\")
s = get_alert_summary()
print(f\"  {s}\")

conn.close()
" 2>&1'
Completed with input:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_connection, get_daily_spend_db, get_all_time_spend_db, get_domain_stats_db, get_recent_scores, get_run_history, get_alert_summary

conn = get_connection()
c = conn.cursor()

print(\"=== SYNC TASKS ===\")
try:
    tasks = c.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
    for t in tasks:
        print(f\"  [{t[4]}] {t[3]} | {t[2]} | {t[1]} | {t[5][:16]}\")
    total = c.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]
    pending = c.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]
    print(f\"  Total: {total}, Pending: {pending}\")
except Exception as e:
    print(f\"  sync_tasks table: {e}\")

print(\"=== CYCLE HISTORY ===\")
try:
    rows = c.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
    for r in rows:
        end = r[2][:16] if r[2] else \"running\"
        print(f\"  Cycle {r[0]}: {r[3]} | planned={r[4]} done={r[5]} rounds={r[6]} cost=\${r[7]:.4f} | {(r[1] or \"\")[:16]} -> {end}\")
except Exception as e:
    print(f\"  daemon_cycles table: {e}\")

print(\"=== DB TABLES ===\")
tables = c.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\"\").fetchall()
for t in tables:
    count = c.execute(f\"SELECT count(*) FROM {t[0]}\").fetchone()[0]
    print(f\"  {t[0]}: {count} rows\")

print(\"=== DAILY COST ===\")
d = get_daily_spend_db()
print(f\"  {d}\")

print(\"=== ALL-TIME COST ===\")
a = get_all_time_spend_db()
print(f\"  {a}\")

print(\"=== ACTIVE ALERTS ===\")
s = get_alert_summary()
print(f\"  {s}\")

conn.close()
" 2>&1'

Read [](file:///workspaces/AI-agents/agent-brain/db.py#1-1), lines 1 to 60

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_connection, get_daily_spend_db, get_all_time_spend_db, get_alert_summary

with get_connection() as conn:
    c = conn.cursor()

    print(\"=== SYNC TASKS ===\")
    try:
        tasks = c.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
        for t in tasks:
            print(f\"  [{t[\"status\"]}] {t[\"priority\"]} | {t[\"task_type\"]} | {t[\"domain\"]} | {str(t[\"created_at\"])[:16]}\")
        total = c.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]
        pending = c.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]
        print(f\"  Total: {total}, Pending: {pending}\")
    except Exception as e:
        print(f\"  sync_tasks: {e}\")

    print(\"=== CYCLE HISTORY ===\")
    try:
        rows = c.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
        for r in rows:
            end = str(r[\"ended_at\"])[:16] if r[\"ended_at\"] else \"running\"
            print(f\"  Cycle {r[\"id\"]}: {r[\"status\"]} | plan={r[\"domains_planned\"]} done={r[\"domains_completed\"]} rnd={r[\"rounds_completed\"]} cost=\${r[\"total_cost_usd\"]:.4f} | {str(r[\"started_at\"])[:16]} -> {end}\")
    except Exception as e:
        print(f\"  daemon_cycles: {e}\")

    print(\"=== DB TABLES ===\")
    tables = c.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\"\").fetchall()
    for t in tables:
        count = c.execute(f\"SELECT count(*) FROM [{t[0]}]\").fetchone()[0]
        print(f\"  {t[0]}: {count} rows\")

print(\"=== DAILY COST ===\")
d = get_daily_spend_db()
print(f\"  {d}\")

print(\"=== ALL-TIME COST ===\")
a = get_all_time_spend_db()
print(f\"  \${a:.4f}\")

print(\"=== ACTIVE ALERTS ===\")
s = get_alert_summary()
print(f\"  {s}\")
" 2>&1'
Completed with input:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_connection, get_daily_spend_db, get_all_time_spend_db, get_alert_summary

with get_connection() as conn:
    c = conn.cursor()

    print(\"=== SYNC TASKS ===\")
    try:
        tasks = c.execute(\"SELECT id, domain, task_type, priority, status, created_at FROM sync_tasks ORDER BY created_at DESC LIMIT 20\").fetchall()
        for t in tasks:
            print(f\"  [{t[\"status\"]}] {t[\"priority\"]} | {t[\"task_type\"]} | {t[\"domain\"]} | {str(t[\"created_at\"])[:16]}\")
        total = c.execute(\"SELECT count(*) FROM sync_tasks\").fetchone()[0]
        pending = c.execute(\"SELECT count(*) FROM sync_tasks WHERE status=\\\"pending\\\"\").fetchone()[0]
        print(f\"  Total: {total}, Pending: {pending}\")
    except Exception as e:
        print(f\"  sync_tasks: {e}\")

    print(\"=== CYCLE HISTORY ===\")
    try:
        rows = c.execute(\"SELECT id, started_at, ended_at, status, domains_planned, domains_completed, rounds_completed, total_cost_usd FROM daemon_cycles ORDER BY id DESC LIMIT 10\").fetchall()
        for r in rows:
            end = str(r[\"ended_at\"])[:16] if r[\"ended_at\"] else \"running\"
            print(f\"  Cycle {r[\"id\"]}: {r[\"status\"]} | plan={r[\"domains_planned\"]} done={r[\"domains_completed\"]} rnd={r[\"rounds_completed\"]} cost=\${r[\"total_cost_usd\"]:.4f} | {str(r[\"started_at\"])[:16]} -> {end}\")
    except Exception as e:
        print(f\"  daemon_cycles: {e}\")

    print(\"=== DB TABLES ===\")
    tables = c.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\"\").fetchall()
    for t in tables:
        count = c.execute(f\"SELECT count(*) FROM [{t[0]}]\").fetchone()[0]
        print(f\"  {t[0]}: {count} rows\")

print(\"=== DAILY COST ===\")
d = get_daily_spend_db()
print(f\"  {d}\")

print(\"=== ALL-TIME COST ===\")
a = get_all_time_spend_db()
print(f\"  \${a:.4f}\")

print(\"=== ACTIVE ALERTS ===\")
s = get_alert_summary()
print(f\"  {s}\")
" 2>&1'

Critical findings already. Let me now do a deep codebase audit in parallel. 

Searched for regex `sync_tasks|daemon_cycles` (`**/agent-brain/**/*.py`), 12 results

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== SYNC TASKS FILE ===" && wc -l logs/sync_tasks.json 2>/dev/null && python3 -c "import json; d=json.load(open(\"logs/sync_tasks.json\")); print(f\"Total: {len(d)}\"); sc={t.get(\"status\",\"?\") for t in d}; print(f\"Statuses: {sc}\"); [print(f\"  [{t.get(\"status\")}] {t.get(\"priority\",\"?\")} | {t.get(\"task_type\",\"?\")} | {t.get(\"domain\",\"?\")} | {str(t.get(\"created_at\",\"\"))[:16]}\") for t in d[-15:]]" 2>&1 && echo "=== DAEMON CYCLE TRACKING ===" && ls -la logs/daemon_cycle* logs/cycle* 2>&1 && echo "=== ERRORS IN CURRENT LOG ===" && grep -c "ERROR\|Traceback\|Exception" logs/daemon-stdout.log 2>/dev/null && echo "=== SPECIFIC ERRORS ===" && grep -i "error\|traceback\|exception\|failed" logs/daemon-stdout.log 2>/dev/null | grep -vi "fetch.*failed\|rate.*error\|confidence.*check\|no.*error\|0.*error" | tail -20 && echo "=== RAG STORE ===" && ls -la rag/chroma_store/ 2>/dev/null && echo "=== HANDS STATUS ===" && ls hands/ 2>/dev/null && echo "=== EXEC MEMORY ===" && ls exec_memory/ 2>/dev/null'
Completed with input:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== SYNC TASKS FILE ===" && wc -l logs/sync_tasks.json 2>/dev/null && python3 -c "import json; d=json.load(open(\"logs/sync_tasks.json\")); print(f\"Total: {len(d)}\"); sc={t.get(\"status\",\"?\") for t in d}; print(f\"Statuses: {sc}\"); [print(f\"  [{t.get(\"status\")}] {t.get(\"priority\",\"?\")} | {t.get(\"task_type\",\"?\")} | {t.get(\"domain\",\"?\")} | {str(t.get(\"created_at\",\"\"))[:16]}\") for t in d[-15:]]" 2>&1 && echo "=== DAEMON CYCLE TRACKING ===" && ls -la logs/daemon_cycle* logs/cycle* 2>&1 && echo "=== ERRORS IN CURRENT LOG ===" && grep -c "ERROR\|Traceback\|Exception" logs/daemon-stdout.log 2>/dev/null && echo "=== SPECIFIC ERRORS ===" && grep -i "error\|traceback\|exception\|failed" logs/daemon-stdout.log 2>/dev/null | grep -vi "fetch.*failed\|rate.*error\|confidence.*check\|no.*error\|0.*error" | tail -20 && echo "=== RAG STORE ===" && ls -la rag/chroma_store/ 2>/dev/null && echo "=== HANDS STATUS ===" && ls hands/ 2>/dev/null && echo "=== EXEC MEMORY ===" && ls exec_memory/ 2>/dev/null'

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== CYCLE HISTORY ===" && cat logs/cycle_history.jsonl && echo "=== CYCLE COUNTER ===" && cat logs/cycle_counter.json && echo "=== BUDGET CONFIG ===" && venv/bin/python3 -c "import sys; sys.path.insert(0,\".\"); from config import DAILY_BUDGET_USD; print(f\"DAILY_BUDGET_USD={DAILY_BUDGET_USD}\")" 2>&1 && echo "=== SYNC TASK DETAILS ===" && venv/bin/python3 -c "
import json
d = json.load(open(\"logs/sync_tasks.json\"))
# Show full structure of one task
print(\"Sample task:\")
print(json.dumps(d[-4], indent=2))
# Count by task_type
from collections import Counter
types = Counter(t.get(\"task_type\",\"unknown\") for t in d)
print(f\"By type: {dict(types)}\")
priorities = Counter(t.get(\"priority\",\"unknown\") for t in d)
print(f\"By priority: {dict(priorities)}\")
has_domain = sum(1 for t in d if t.get(\"domain\"))
print(f\"Has domain: {has_domain}/{len(d)}\")
" 2>&1'

Now let me audit the full codebase architecture. Let me check all major modules systematically. 

Ran terminal command:  cd /workspaces/AI-agents/agent-brain && echo "=== PRODUCTION FILES ===" && find . -name "*.py" -not -path "./tests/*" -not -path "./__pycache__/*" -not -path "./venv/*" -not -path "./browser/node_modules/*" | sort | while read f; do lines=$(wc -l < "$f"); echo "  $lines $f"; done && echo "=== TOTAL ===" && find . -name "*.py" -not -path "./tests/*" -not -path "./__pycache__/*" -not -path "./venv/*" -not -path "./browser/node_modules/*" | xargs wc -l 2>/dev/null | tail -1

Now let me read the key architectural files and check how the components wire together: 

Searched for regex `DAILY_BUDGET_USD|budget.*enforce|check_budget|over_budget` (`**/agent-brain/**/*.py`), 20 results

Read [](file:///workspaces/AI-agents/agent-brain/cost_tracker.py#100-100), lines 100 to 160

Read [](file:///workspaces/AI-agents/agent-brain/cost_tracker.py#1-1), lines 1 to 30

Read [](file:///workspaces/AI-agents/agent-brain/config.py#1-1), lines 1 to 60

Read [](file:///workspaces/AI-agents/agent-brain/config.py#60-60), lines 60 to 170

Now let me check the budget enforcement in the daemon loop and the broader integration issues: 

Read [](file:///workspaces/AI-agents/agent-brain/scheduler.py#1340-1340), lines 1340 to 1430

Read [](file:///workspaces/AI-agents/agent-brain/scheduler.py#1430-1430), lines 1430 to 1570

Read [](file:///workspaces/AI-agents/agent-brain/scheduler.py#1570-1570), lines 1570 to 1700

Now let me check the sync task creation and hands execution:  

Read [](file:///workspaces/AI-agents/agent-brain/sync.py#1-1), lines 1 to 200

Now let me check how tasks are created from research output (the `create_tasks_from_output` function in main.py): 

Searched for regex `create_task|sync.*task|SYNC|sync\.create` (`**/agent-brain/main.py`), 19 results

Read [](file:///workspaces/AI-agents/agent-brain/main.py#118-118), lines 118 to 175

Now let me check how the daemon's `_execute_hands_tasks` works: 

Searched for regex `_execute_hands_tasks` (`**/agent-brain/scheduler.py`), 2 results

Read [](file:///workspaces/AI-agents/agent-brain/scheduler.py#1066-1066), lines 1066 to 1180

Read [](file:///workspaces/AI-agents/agent-brain/scheduler.py#1180-1180), lines 1180 to 1240

Now let me check all the agents and hands modules to understand integration gaps: 

Searched for regex `cortex_plan_cycle|cortex_interpret_cycle` (`**/agent-brain/scheduler.py`), 4 results

Read [](file:///workspaces/AI-agents/agent-brain/scheduler.py#600-600), lines 600 to 750

Now let me audit the Hands, Identity, and other key modules:  

Read [](file:///workspaces/AI-agents/agent-brain/hands/executor.py#1-1), lines 1 to 60

Read [](file:///workspaces/AI-agents/agent-brain/identity_loader.py#1-1), lines 1 to 50

Read [](file:///workspaces/AI-agents/agent-brain/identity)

Ran terminal command:  cd /workspaces/AI-agents/agent-brain && echo "=== IDENTITY FILES ===" && for f in identity/*.md; do echo "--- $f ---"; head -5 "$f"; done && echo "=== WHO IMPORTS IDENTITY ===" && grep -rn "identity_loader\|load_identity\|get_identity" --include="*.py" | grep -v test | grep -v __pycache__

Ran terminal command:  cd /workspaces/AI-agents/agent-brain && echo "=== MCP INTEGRATION ===" && grep -rn "from mcp\|import mcp" --include="*.py" | grep -v test | grep -v __pycache__ && echo "=== KNOWLEDGE GRAPH USAGE ===" && grep -rn "knowledge_graph\|from knowledge" --include="*.py" | grep -v test | grep -v __pycache__ && echo "=== ANALYTICS USAGE ===" && grep -rn "from analytics\|import analytics" --include="*.py" | grep -v test | grep -v __pycache__ && echo "=== VALIDATOR USAGE ===" && grep -rn "from validator\|import validator" --include="*.py" | grep -v test | grep -v __pycache__ && echo "=== MONITORING USAGE ===" && grep -rn "from monitoring\|import monitoring" --include="*.py" | grep -v test | grep -v __pycache__ && echo "=== CONSENSUS USAGE ===" && grep -rn "from agents.consensus\|agents.consensus\|consensus\." --include="*.py" | grep -v test | grep -v __pycache__

Ran terminal command:  cd /workspaces/AI-agents/agent-brain && echo "=== DOMAIN GOALS ===" && ls memory/*/  2>/dev/null | head -30 && echo "=== GOAL FILES ===" && find strategies/ -name "_goal.json" 2>/dev/null && echo "=== DOMAIN SEEDER ===" && grep -rn "domain_seeder\|get_seed" --include="*.py" | grep -v test | grep -v __pycache__ | head -15 && echo "=== RESEARCH_LESSONS ===" && grep -rn "research_lessons" --include="*.py" | grep -v test | grep -v __pycache__ && echo "=== TELEGRAM BOT ===" && grep -rn "telegram_bot\|from telegram" --include="*.py" | grep -v test | grep -v __pycache__ | head -10 && echo "=== DASHBOARD ===" && grep -rn "dashboard\|from dashboard" --include="*.py" | grep -v test | grep -v __pycache__ | head -10

Now let me check the VPS for deeper issues — the actual budget being hit but daemon still running: 

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== IS DAEMON STILL RUNNING ===" && systemctl is-active cortex-daemon && echo "=== FULL LOG LINE COUNT ===" && wc -l logs/daemon-stdout.log && echo "=== BUDGET CHECKS IN LOG ===" && grep -i "budget\|within_budget\|waiting.*budget\|budget.*exceeded\|budget.*hit" logs/daemon-stdout.log | tail -15 && echo "=== WATCHDOG BLOCKS ===" && grep -i "watchdog.*block\|circuit.*break\|cost.*ceil" logs/daemon-stdout.log | tail -10 && echo "=== HANDS AUTO-EXEC ===" && grep -i "hands.*auto\|hands.*exec\|hands.*skip\|hands.*task" logs/daemon-stdout.log | tail -10 && echo "=== CORTEX PLAN DETAILS ===" && grep -i "cortex.*plan\|cortex.*focus\|cortex.*inject\|cortex.*priorities" logs/daemon-stdout.log | tail -10 && echo "=== CYCLE STARTS SINCE DEPLOY ===" && grep "Cycle.*starting" logs/daemon-stdout.log && echo "=== DOMAIN GOAL WARNINGS ===" && grep -i "no goal\|goal.*set\|goal.*missing" logs/daemon-stdout.log | head -5'

Read [](file:///workspaces/AI-agents/agent-brain/cost_tracker.py#30-30), lines 30 to 100

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== COSTS JSONL SIZE ===" && ls -la logs/costs.jsonl* 2>/dev/null && echo "=== TODAY ENTRIES ===" && grep "2026-03-03" logs/costs.jsonl 2>/dev/null | wc -l && echo "=== TODAY TOTAL FROM JSONL ===" && python3 -c "
import json
total = 0
with open(\"logs/costs.jsonl\") as f:
    for line in f:
        e = json.loads(line.strip())
        if e.get(\"date\") == \"2026-03-03\":
            total += e.get(\"estimated_cost_usd\", 0)
print(f\"JSONL today total: \${total:.4f}\")
" 2>&1 && echo "=== DB TODAY TOTAL ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from db import get_daily_spend_db
d = get_daily_spend_db()
print(f\"DB today total: \${d.get(\"total_usd\", 0):.4f}\")
print(f\"DB calls: {d.get(\"calls\", 0)}\")
" 2>&1 && echo "=== CHECK_BUDGET RESULT ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from cost_tracker import check_budget
b = check_budget()
print(f\"within_budget: {b[\"within_budget\"]}\")
print(f\"spent: \${b[\"spent\"]:.4f}\")
print(f\"limit: \${b[\"limit\"]:.4f}\")
print(f\"remaining: \${b[\"remaining\"]:.4f}\")
print(f\"claude: spent=\${b[\"by_provider\"][\"claude\"][\"spent\"]:.4f} limit=\${b[\"by_provider\"][\"claude\"][\"limit\"]:.4f}\")
print(f\"openrouter: spent=\${b[\"by_provider\"][\"openrouter\"][\"spent\"]:.4f} limit=\${b[\"by_provider\"][\"openrouter\"][\"limit\"]:.4f}\")
" 2>&1'

Starting: *Audit all agent modules* (2/6)

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== SCORES BY DOMAIN ===" && venv/bin/python3 -c "
import sys, json, os, glob; sys.path.insert(0,\".\")
from config import MEMORY_DIR
for d in sorted(os.listdir(MEMORY_DIR)):
    dp = os.path.join(MEMORY_DIR, d)
    if not os.path.isdir(dp) or d.startswith(\"_\"): continue
    files = glob.glob(os.path.join(dp, \"*.json\"))
    files = [f for f in files if not os.path.basename(f).startswith(\"_\")]
    scores = []
    for f in files:
        try:
            data = json.load(open(f))
            s = data.get(\"critique\",{}).get(\"overall_score\",0)
            if s > 0: scores.append(s)
        except: pass
    if scores:
        avg = sum(scores)/len(scores)
        acc = sum(1 for s in scores if s >= 6)
        last3 = scores[-3:]
        print(f\"  {d}: {len(scores)} outputs, avg={avg:.1f}, accepted={acc}/{len(scores)}, last3={last3}\")
    else:
        print(f\"  {d}: 0 scored outputs\")
" && echo "=== STRATEGY DETAILS ===" && venv/bin/python3 -c "
import sys, json, os; sys.path.insert(0,\".\")
from strategy_store import StrategyStore
s = StrategyStore()
for d in sorted(os.listdir(\"strategies\")):
    if os.path.isdir(f\"strategies/{d}\") and not d.startswith(\"_\"):
        meta_path = f\"strategies/{d}/_meta.json\"
        if os.path.exists(meta_path):
            meta = json.load(open(meta_path))
            active = meta.get(\"active_version\")
            latest = meta.get(\"latest_version\")
            status = \"unknown\"
            if active:
                vf = f\"strategies/{d}/researcher_{active}.json\"
                if os.path.exists(vf):
                    vdata = json.load(open(vf))
                    status = vdata.get(\"status\",\"?\")
            print(f\"  {d}: active={active} latest={latest} status={status}\")
        else:
            print(f\"  {d}: no _meta.json\")
" 2>&1 && echo "=== RAG CHROMA STATUS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
try:
    import chromadb
    client = chromadb.PersistentClient(path=\"rag/chroma_store\")
    cols = client.list_collections()
    for c in cols:
        print(f\"  {c.name}: {c.count()} items\")
    if not cols:
        print(\"  No collections\")
except Exception as e:
    print(f\"  Error: {e}\")
" 2>&1 && echo "=== EXEC_MEMORY ===" && find output/ -type f 2>/dev/null | wc -l && echo "=== HANDS TOOLS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from hands.tools.registry import create_default_registry
r = create_default_registry()
descs = r.get_tool_descriptions()
print(f\"  {len(descs)} tools registered\")
for name in sorted(r._tools.keys()):
    print(f\"    - {name}\")
" 2>&1'
Completed with input:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== SCORES BY DOMAIN ===" && venv/bin/python3 -c "
import sys, json, os, glob; sys.path.insert(0,\".\")
from config import MEMORY_DIR
for d in sorted(os.listdir(MEMORY_DIR)):
    dp = os.path.join(MEMORY_DIR, d)
    if not os.path.isdir(dp) or d.startswith(\"_\"): continue
    files = glob.glob(os.path.join(dp, \"*.json\"))
    files = [f for f in files if not os.path.basename(f).startswith(\"_\")]
    scores = []
    for f in files:
        try:
            data = json.load(open(f))
            s = data.get(\"critique\",{}).get(\"overall_score\",0)
            if s > 0: scores.append(s)
        except: pass
    if scores:
        avg = sum(scores)/len(scores)
        acc = sum(1 for s in scores if s >= 6)
        last3 = scores[-3:]
        print(f\"  {d}: {len(scores)} outputs, avg={avg:.1f}, accepted={acc}/{len(scores)}, last3={last3}\")
    else:
        print(f\"  {d}: 0 scored outputs\")
" && echo "=== STRATEGY DETAILS ===" && venv/bin/python3 -c "
import sys, json, os; sys.path.insert(0,\".\")
from strategy_store import StrategyStore
s = StrategyStore()
for d in sorted(os.listdir(\"strategies\")):
    if os.path.isdir(f\"strategies/{d}\") and not d.startswith(\"_\"):
        meta_path = f\"strategies/{d}/_meta.json\"
        if os.path.exists(meta_path):
            meta = json.load(open(meta_path))
            active = meta.get(\"active_version\")
            latest = meta.get(\"latest_version\")
            status = \"unknown\"
            if active:
                vf = f\"strategies/{d}/researcher_{active}.json\"
                if os.path.exists(vf):
                    vdata = json.load(open(vf))
                    status = vdata.get(\"status\",\"?\")
            print(f\"  {d}: active={active} latest={latest} status={status}\")
        else:
            print(f\"  {d}: no _meta.json\")
" 2>&1 && echo "=== RAG CHROMA STATUS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
try:
    import chromadb
    client = chromadb.PersistentClient(path=\"rag/chroma_store\")
    cols = client.list_collections()
    for c in cols:
        print(f\"  {c.name}: {c.count()} items\")
    if not cols:
        print(\"  No collections\")
except Exception as e:
    print(f\"  Error: {e}\")
" 2>&1 && echo "=== EXEC_MEMORY ===" && find output/ -type f 2>/dev/null | wc -l && echo "=== HANDS TOOLS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from hands.tools.registry import create_default_registry
r = create_default_registry()
descs = r.get_tool_descriptions()
print(f\"  {len(descs)} tools registered\")
for name in sorted(r._tools.keys()):
    print(f\"    - {name}\")
" 2>&1'

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== STRATEGY META FILES ===" && for d in strategies/*/; do bn=$(basename "$d"); meta="$d/_meta.json"; if [ -f "$meta" ]; then echo "$bn: $(cat "$meta")"; fi; done && echo "=== RAG CHROMA STATUS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
try:
    import chromadb
    client = chromadb.PersistentClient(path=\"rag/chroma_store\")
    cols = client.list_collections()
    for c in cols:
        print(f\"  {c.name}: {c.count()} items\")
    if not cols:
        print(\"  No collections\")
except Exception as e:
    print(f\"  Error: {e}\")
" 2>&1 && echo "=== EXEC_MEMORY FILES ===" && find output/ -type f 2>/dev/null | wc -l && find exec_memory/ -type f 2>/dev/null | wc -l && echo "=== HANDS TOOLS ===" && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
from hands.tools.registry import create_default_registry
r = create_default_registry()
descs = r.get_tool_descriptions()
print(f\"  {len(descs)} tools registered\")
for name in sorted(r._tools.keys()):
    print(f\"    - {name}\")
" 2>&1'

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== RAG CHROMA STORE ===" && ls -la rag/chroma_store/ 2>/dev/null && echo "=== RAG VECTORDB IN MEMORY ===" && ls -la memory/_vectordb/ 2>/dev/null && echo "=== RAG INDEX IN LOG ===" && grep -i "RAG.*index\|RAG.*claim\|RAG.*error\|vector.*store" logs/daemon-stdout.log | tail -10 && echo "=== EXEC MEMORY DIR ===" && find exec_memory/ -type f && echo "=== LOGS LIST ===" && ls -la logs/*.jsonl logs/*.json logs/*.log 2>/dev/null && echo "=== COSTS JSONL DATES ===" && python3 -c "
import json; dates = {}
with open(\"logs/costs.jsonl\") as f:
    for line in f:
        e = json.loads(line.strip())
        d = e.get(\"date\",\"?\")
        dates[d] = dates.get(d,0) + 1
for d in sorted(dates.keys()): print(f\"  {d}: {dates[d]} entries\")
" 2>&1 && echo "=== LOG ROTATION FILES ===" && ls -la logs/costs.jsonl* logs/run-log.jsonl* 2>/dev/null'
Completed with input:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== RAG CHROMA STORE ===" && ls -la rag/chroma_store/ 2>/dev/null && echo "=== RAG VECTORDB IN MEMORY ===" && ls -la memory/_vectordb/ 2>/dev/null && echo "=== RAG INDEX IN LOG ===" && grep -i "RAG.*index\|RAG.*claim\|RAG.*error\|vector.*store" logs/daemon-stdout.log | tail -10 && echo "=== EXEC MEMORY DIR ===" && find exec_memory/ -type f && echo "=== LOGS LIST ===" && ls -la logs/*.jsonl logs/*.json logs/*.log 2>/dev/null && echo "=== COSTS JSONL DATES ===" && python3 -c "
import json; dates = {}
with open(\"logs/costs.jsonl\") as f:
    for line in f:
        e = json.loads(line.strip())
        d = e.get(\"date\",\"?\")
        dates[d] = dates.get(d,0) + 1
for d in sorted(dates.keys()): print(f\"  {d}: {dates[d]} entries\")
" 2>&1 && echo "=== LOG ROTATION FILES ===" && ls -la logs/costs.jsonl* logs/run-log.jsonl* 2>/dev/null'

Searched for regex `migrate_from_json|def init_db` (`**/agent-brain/db.py`), 2 results

Read [](file:///workspaces/AI-agents/agent-brain/db.py#51-51), lines 51 to 115

Read [](file:///workspaces/AI-agents/agent-brain/db.py#538-538), lines 538 to 646

Starting: *Map architecture vs vision* (5/6)

Let me check a few more integration details to round out the audit: 

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== WATCHDOG STATE ===" && python3 -c "import json; print(json.dumps(json.load(open(\"logs/watchdog_state.json\")), indent=2))" 2>&1 | head -40 && echo "=== DAEMON STATE ===" && cat logs/daemon_state.json && echo "=== TELEGRAM BOT STATUS ===" && systemctl is-active cortex-telegram 2>/dev/null || echo "no service" && echo "=== ALL SERVICES ===" && systemctl list-units --type=service --state=active 2>/dev/null | grep cortex'

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && echo "=== RAG TWO STORES CHECK ===" && echo "rag/chroma_store:" && ls rag/chroma_store/ 2>/dev/null && echo "memory/_vectordb:" && ls memory/_vectordb/ 2>/dev/null && echo "=== WHO REFERENCES WHICH STORE ===" && grep -rn "chroma_store\|_vectordb\|PersistentClient" --include="*.py" | grep -v test | grep -v __pycache__ | grep -v venv'

Read [](file:///home/codespace/.vscode-remote/data/User/workspaceStorage/23b51e06/GitHub.copilot-chat/chat-session-resources/85767f3f-989d-4d3a-a95c-a12559f10226/toolu_bdrk_01SQXMc86coUy874jn4ZUFco__vscode-1772501470988/content.txt#1-1), lines 1 to 40

Searched for regex `PersistentClient|chroma_store|_vectordb` (`**/agent-brain/rag/vector_store.py`), 10 results

Ran terminal command:  sshpass -p '[REDACTED_VPS_PASS]' ssh -o StrictHostKeyChecking=no root@207.180.219.27 'cd /root/AI-agents/agent-brain && venv/bin/python3 -c "
import sys; sys.path.insert(0,\".\")
import chromadb
client = chromadb.PersistentClient(path=\"memory/_vectordb\")
cols = client.list_collections()
for c in cols:
    print(f\"  {c.name}: {c.count()} items\")
if not cols:
    print(\"  No collections\")
" 2>&1'

Good — RAG is working. 217 claims and 24 questions indexed. Now let me compile the full audit report. 

Starting: *Produce full audit report* (6/6)

---

# CORTEX SYSTEM — FULL ARCHITECTURE AUDIT

**Date**: March 3, 2026
**VPS**: 207.180.219.27 (active, commit `86a2e2b`)
**Codebase**: 41,596 lines across 120 production Python files, 1,538 tests

---

## 1. WHERE WE ARE ON THE BIG PICTURE

### Target Architecture (from vision docs)
```
                    IDENTITY LAYER
            (goals, values, risk tolerance)
                        │
                   ORCHESTRATOR
        Watchdog │ Sync │ Progress │ Economics
                   /           \
              BRAIN             HANDS
         7 agents              10 agents
                        │
                SENSOR LAYER
         Signal │ Validation │ Behavior │ Analytics
                        │
                LEARNING LAYER
         Local Judge │ Preference Store │ Re-trainer
```

### What Actually Exists

| Layer | Status | Detail |
|-------|--------|--------|
| **Identity** | **COMPLETE** | 5 files (goals, ethics, boundaries, risk, taste). Injected into Cortex, Critic, Researcher, Chat. |
| **Orchestrator** | **70%** | Watchdog, Sync, Scheduler, Cortex planner — all built and running. Missing: Economics Agent. |
| **Brain** | **95%** | All 10 agents built. 5 self-learning layers proven. Consensus not used in daemon. |
| **Hands** | **30%** | Executor + Planner + Validator + 5 tools. Missing 6 expansion agents (Design, DevOps, SEO, Outreach, Debugger, Hands Critic). **Pipeline to Hands is broken** (see below). |
| **Sensor Layer** | **10%** | Analytics module exists. Signal, Validation, Behavior agents not built. |
| **Learning Layer** | **15%** | research_lessons.py + strategy evolution fill partial role. Local Judge, Re-trainer not built. |

### Build Order Progress

| Step | Target | Status |
|------|--------|--------|
| 1 | Brain self-learning loop | **DONE** — 5 layers proven |
| 2 | Hands coding execution | **DONE** — executor + 5 tools |
| 3 | Prescreen + Loop Guard + Progress | **DONE** |
| 4 | Orchestrator (24/7 stability) | **70%** — running on VPS, but integration gaps |
| 5 | Signal Agent | **NOT STARTED** |
| 6 | Validation Agent | **NOT STARTED** |
| 7 | Expand Hands beyond coding | **NOT STARTED** |
| 8 | Economics Agent | **NOT STARTED** |
| 9 | Behavior + Analytics agents | **NOT STARTED** |
| 10 | Learning Layer upgrade | **NOT STARTED** |

---

## 2. COMPONENT-BY-COMPONENT AUDIT

### BRAIN AGENTS

| Agent | File | Lines | Integration | VPS Status |
|-------|------|-------|-------------|------------|
| Researcher | agents/researcher.py | 681 | Identity + Strategy + RAG + Lessons | **WORKING** — producing 7.0+ avg scores |
| Critic | agents/critic.py | 511 | Identity + Ensemble + Confidence check | **WORKING** — Claude Sonnet, 5-dim rubric |
| Pre-screener | prescreen.py | 245 | DeepSeek → Claude escalation | **WORKING** — saves ~40% critic cost |
| Meta-Analyst | agents/meta_analyst.py | 410 | Strategy evolution from scored outputs | **SUPPRESSED** — domains in warmup/trial |
| Question Generator | agents/question_generator.py | 417 | Gap diagnosis → next question | **WORKING** |
| Cross-Domain | agents/cross_domain.py | 629 | Principle extraction + transfer | **PASSIVE** — principles from 3 domains available |
| Synthesizer | agents/synthesizer.py | 439 | KB integration + contradiction detection | Built, called in loop |
| Verifier | agents/verifier.py | 337 | Prediction tracking + reality check | Built, called in loop |
| Consensus | agents/consensus.py | 284 | Multi-agent agreement | **NOT USED IN DAEMON** — CLI only |
| Cortex | agents/cortex.py | 628 | Strategic planning + cycle interpretation | **WORKING** — focus domains, health monitoring |

### HANDS AGENTS

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Planner | hands/planner.py | 546 | Built — generates structured plans |
| Executor | hands/executor.py | 832 | Built — multi-turn tool use |
| Validator | hands/validator.py | 798 | Built — output verification |
| Pattern Learner | hands/pattern_learner.py | 497 | Built — learns from execution patterns |
| Tools (5) | hands/tools/ | 1,582 | code, git, http, search, terminal |
| Error Analyzer | hands/error_analyzer.py | 192 | Built |
| **Design Agent** | — | — | **NOT BUILT** |
| **DevOps Agent** | — | — | **NOT BUILT** |
| **SEO Agent** | — | — | **NOT BUILT** |
| **Outreach Agent** | — | — | **NOT BUILT** |
| **Hands Critic** | — | — | **NOT BUILT** |

### INFRASTRUCTURE

| Component | File | Lines | VPS Status |
|-----------|------|-------|------------|
| Scheduler | scheduler.py | 1,812 | **RUNNING** — cycle 7, 5 rounds/cycle |
| Watchdog | watchdog.py | 601 | **ACTIVE** — currently in cooldown after 5 failures |
| Sync | sync.py | 461 | **BROKEN** — 37 tasks, all pending, never consumed |
| Cost Tracker | cost_tracker.py | 243 | **BUG** — JSONL/DB desync (see critical issues) |
| DB | db.py | 646 | **WORKING** — 4,053 outputs, 2,338 costs, 180 alerts |
| RAG | rag/vector_store.py | 589 | **WORKING** — 217 claims, 24 questions |
| Knowledge Graph | knowledge_graph.py | 632 | Built but **NOT triggered in daemon** |
| Analytics | analytics.py | 816 | Built, used by Cortex + monitoring |
| Monitoring | monitoring.py | 327 | **WORKING** — health checks run post-cycle |
| Telegram Bot | telegram_bot.py | 680 | **RUNNING** as `cortex-telegram` service |
| Dashboard API | dashboard/api.py | 784 | Built but **NOT deployed** |
| MCP Gateway | mcp/ | 1,739 | Built but **NOT connected** to daemon |
| Identity Loader | identity_loader.py | 250 | **WORKING** — cached, injected into 4 agents |

---

## 3. CRITICAL ISSUES (Bugs breaking the system)

### CRITICAL 1: Budget Tracking Desync — Unlimited Spending Risk

`check_budget()` reads from cost_tracker.py which parses `costs.jsonl`.
The DB shows **$25.46 spent today** but the JSONL shows only **$0.60**.
The daemon thinks budget is fine (`within_budget: True`, remaining $6.40) when it's actually 3.6x over the $7 daily limit.

**Root cause**: `get_daily_spend()` reads JSONL, not DB. When JSONL entries are lost (rotation, corruption), the budget check silently under-reports.

**Impact**: The system can spend unlimited money. Budget enforcement is bypassed.

**Fix**: Make `get_daily_spend()` read from DB (authoritative source) with JSONL fallback.

---

### CRITICAL 2: Brain → Hands Pipeline Completely Broken

The daemon creates sync tasks from research, but Hands **never executes any of them**.

**Three compounding failures:**

1. **Task type mismatch**: `_create_tasks_from_research()` in [main.py](agent-brain/main.py#L118) creates `"investigate"` (36/37) and `"deploy"` (1/37) tasks. But `_execute_hands_tasks()` in [scheduler.py](agent-brain/scheduler.py#L1109) only accepts `"build"` and `"action"` types.

2. **Priority mismatch**: Hands only picks up `"critical"` and `"high"` priority tasks. But 36/37 tasks are `"low"` priority investigate tasks.

3. **The one high-priority task** (type=`"deploy"`) was **skipped** because deploy is not in the allowed types `("build", "action")`.

**VPS evidence**: `"Hands skipping task task_20260303_062033_283890: type=deploy"` — the ONLY actionable task, skipped.

**Impact**: Zero exec_memory outputs. Hands has never auto-executed a single task from research. The Brain→Hands feedback loop is completely disconnected.

**Fix**: Either expand accepted task_types to include `"deploy"` and `"investigate"`, or fix `_create_tasks_from_research()` to generate `"build"` and `"action"` type tasks.

---

### CRITICAL 3: Watchdog Cooldown After 5 Stall Failures

The watchdog is currently in **cooldown state** (1800s/30min cooldown after 5 consecutive failures). The daemon is alive but blocked from running cycles.

**Root cause**: The `all` meta-domain stalled — Cortex injected it as a focus domain but it consistently produces 0 rounds because it's a catch-all domain with no clear research direction.

**Impact**: Daemon is idle whenever the cooldown is active. Research progress stops.

**Fix**: Either remove `all` from Cortex's focus candidates, or add logic to skip meta-domains that consistently stall.

---

## 4. HIGH-SEVERITY ISSUES

### HIGH 1: Domain Goals Missing for Revenue Domains

Only `productized-services` has a goal file. The primary revenue domain `onlinejobsph-employers` has **no goal set**.

VPS log: `"⚠ No goal set for domain 'onlinejobsph-employers' — questions may not be actionable"`

**Impact**: Question generator produces generic questions instead of targeted revenue-aligned research.

---

### HIGH 2: Strategy Evolution Stalled

| Domain | Status | Active Version | Last Updated |
|--------|--------|---------------|-------------|
| ai | trial | v002 | Feb 28 |
| crypto | trial | v004 | Feb 23 |
| cybersecurity | **active** | v003 | Feb 23 |
| general | trial | v001 | Mar 2 |
| geopolitics | trial | v002 | Mar 2 |
| nextjs-react | trial | v002 | Feb 25 |
| physics | trial | v001 | Mar 2 |
| productized-services | trial | v002 | Mar 1 |
| saas-fullstack-apps | trial | v001 | Mar 3 |
| **onlinejobsph-employers** | **NO STRATEGY** | default | — |

8/9 domains stuck in "trial" status. Trial evaluation requires `TRIAL_PERIOD=5` outputs under the trial strategy, but most domains haven't accumulated enough. Only cybersecurity has reached "active" (v003).

The revenue domain has **no strategy at all** — using defaults.

---

### HIGH 3: Cybersecurity 50% Rejection Rate

cybersecurity: 10 outputs, only 5 accepted (50% rejection). The last 3 scores are 7.4, 8.1, 7.9 (improving), but the historical rejection rate is alarming. The strategy (v003) is the only "active" one — it may need re-evaluation.

---

### HIGH 4: productized-services Declining Quality

productized-services: 29 outputs, last 3 scores: 8.25, 4.8, **2.9**. This is a severe quality regression. The domain has the most outputs but is degrading rapidly.

---

## 5. MEDIUM-SEVERITY ISSUES

### MED 1: Consensus Agent Idle

`consensus_research()` is never called in the daemon loop. Only available via CLI `--consensus` flag. Could improve research quality by adding multi-agent agreement scoring.

### MED 2: Knowledge Graph Not Triggered in Daemon

Knowledge graph building exists ([knowledge_graph.py](agent-brain/knowledge_graph.py)) but is only triggered via CLI `--graph`. The daemon never builds/updates knowledge graphs from accumulated research.

### MED 3: Dashboard Not Deployed

[dashboard/api.py](agent-brain/dashboard/api.py) (784 lines FastAPI) is fully built but has no systemd service. No web interface for monitoring.

### MED 4: MCP Gateway Disconnected

5 MCP modules ([mcp/](agent-brain/mcp/)) totaling 1,739 lines. Docker-based architecture. Only accessible via CLI flags. Not integrated into daemon or research pipeline.

### MED 5: Two ChromaDB Stores

`rag/chroma_store/` (188KB, 0 collections) and `memory/_vectordb/` (1.7MB, 217 claims + 24 questions). The `rag/chroma_store` directory is orphaned/unused — only `memory/_vectordb` is the active path.

### MED 6: Sync Tasks Have No "domain" Field

Tasks use `source_domain` instead of `domain`. While `get_pending_tasks()` correctly filters on `source_domain`, any external tooling or dashboard expecting a `domain` field will see empty data.

---

## 6. VPS LIVE STATE SUMMARY

| Metric | Value |
|--------|-------|
| **Daemon** | Active, cycle 7 completed, next run ~07:30 UTC |
| **Watchdog** | Cooldown (5 failures, 30min cooldown) |
| **Telegram Bot** | Active |
| **Commit** | `86a2e2b` |
| **Daily Budget** | $7.00 ($2 Claude + $5 OpenRouter) |
| **Reported Spend** | $0.60 (JSONL) — **actual $25.46 (DB)** |
| **Total Memory** | 155 research outputs across 11 domains |
| **RAG** | 217 claims, 24 questions (working) |
| **Sync Tasks** | 37 pending, 0 executed, 0 completed |
| **Exec Memory** | 1 file (from Feb 25 manual run) |
| **Strategies** | 8/9 in trial, 1 active, 1 using default |

### Domain Health

| Domain | Outputs | Avg Score | Acceptance | Trend |
|--------|---------|-----------|------------|-------|
| onlinejobsph-employers | 3 | 7.2 | 100% | Warmup (3/5) |
| geopolitics | 6 | 7.4 | 100% | Stable |
| physics | 7 | 7.2 | 100% | Stable |
| ai | 11 | 7.0 | 100% | Declining (-0.55) |
| general | 8 | 6.9 | 88% | Declining (-1.74) |
| nextjs-react | 27 | 6.7 | 81% | Stable |
| crypto | 17 | 6.3 | 76% | Mixed |
| productized-services | 29 | 6.3 | 72% | **CRITICAL** — last score 2.9 |
| saas-fullstack-apps | 15 | 5.9 | 47% | Struggling |
| cybersecurity | 10 | 5.8 | 50% | Improving (last 3: 7.4, 8.1, 7.9) |

---

## 7. ARCHITECTURE GAPS — WHAT'S MISSING

### Missing Agents (from vision)

| Agent | Layer | Priority | Impact |
|-------|-------|----------|--------|
| **Economics Agent** | Orchestrator | HIGH | Kill/pivot/double-down decisions. Currently Cortex fills partial role. |
| **Signal Agent** | Sensor | MEDIUM | Replaces human "is this worth pursuing?" judgment |
| **Validation Agent** | Sensor | MEDIUM | Replaces human "will people pay?" judgment |
| **Design Agent** | Hands | LOW | Needed for landing pages (productized services) |
| **DevOps Agent** | Hands | LOW | Auto-deploy, infra management |
| **SEO Agent** | Hands | LOW | Content optimization |
| **Outreach Agent** | Hands | LOW | Customer acquisition |
| **Hands Critic** | Hands | MEDIUM | Judge execution quality (validator is partial) |
| **Local Judge** | Learning | LOW | Replace Claude with local model for scoring |
| **Re-trainer** | Learning | LOW | Strategy evolution from feedback data |

### Missing Integrations (things built but not connected)

1. **Consensus → Daemon**: Agent exists, not called in auto-mode
2. **Knowledge Graph → Daemon**: Builder exists, never auto-triggered
3. **Dashboard → VPS**: API built, no systemd service
4. **MCP → Research**: Gateway built, not used in pipeline
5. **Cost DB → Budget Check**: DB is authoritative, but budget reads stale JSONL

---

## 8. THE HONEST ASSESSMENT

**What's working well:**
- Brain's core loop (research → critique → store → evolve) is solid
- Identity layer is complete and injected
- Cortex strategic planning is making smart decisions (prioritizing revenue domains)
- RAG semantic memory is indexing and queryable (217 claims)
- Watchdog is doing its job (catching failures, enforcing cooldowns)
- Telegram bot provides real-time monitoring

**What's broken:**
- Budget tracking is unreliable (JSONL vs DB desync)
- Brain→Hands pipeline is completely disconnected (0 executions)
- Strategy evolution is stalled (most domains stuck in trial)
- Revenue domain (onlinejobsph-employers) has no goal or strategy
- Watchdog cooldowns are triggered by meta-domain stalls

**The gap between vision and reality:**
The vision describes a system that researches → builds → deploys → markets → acquires customers. What actually runs on the VPS is a system that researches → stores research → creates tasks that nobody picks up. The Brain is working. Hands exists but the wiring between them is broken. Everything downstream of Hands (deploy, market, acquire) doesn't exist yet.

**Revenue-generating readiness: ~20%**
The research is accumulating knowledge about onlinejobsph-employers, but there's no mechanism to turn that research into a landing page, a pitch, or a deployed service. That pipeline (research → Hands execution → deployment → outreach) has 3 broken links.

---

## 9. PRIORITY FIX ORDER

| # | Issue | Severity | Effort | Impact |
|---|-------|----------|--------|--------|
| 1 | Budget: read from DB not JSONL | CRITICAL | Small | Prevent unlimited spending |
| 2 | Hands pipeline: fix task types | CRITICAL | Small | Unblock Brain→Hands flow |
| 3 | Domain goal for onlinejobsph-employers | HIGH | Small | Targeted revenue research |
| 4 | Skip `all` meta-domain in Cortex focus | HIGH | Small | Stop watchdog cooldowns |
| 5 | Strategy: auto-promote trials with enough data | HIGH | Medium | Unblock evolution |
| 6 | productized-services: investigate 2.9 score | HIGH | Medium | Stop quality regression |
| 7 | Clean orphaned rag/chroma_store | LOW | Tiny | Hygiene |
| 8 | Deploy dashboard API | MEDIUM | Medium | Monitoring visibility | 

Completed: *Produce full audit report* (6/6)

That's the complete picture. Three critical issues need immediate attention:

1. **Budget is blind** — `check_budget()` reads JSONL ($0.60) while DB shows the real spend ($25.46). The daemon thinks it has $6.40 remaining when it's actually 3.6x over budget.

2. **Hands never executes** — Research creates "investigate"/"deploy" tasks but Hands only accepts "build"/"action". The 1 high-priority deploy task was explicitly skipped. Zero executions in the entire system's lifetime (on VPS).

3. **Watchdog blocked by meta-domain stalls** — Cortex injects `all` as a focus domain, it consistently stalls, triggers the circuit breaker, and blocks all research for 30 minutes.

The architecture is ~50% built toward the full vision. Brain is 95% complete. Hands exists (30%) but is completely disconnected from Brain. Sensor and Learning layers are barely started. The system researches well but can't act on what it learns.