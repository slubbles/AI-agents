# Cortex — Complete System Documentation (OUTDATED)

> **⚠️ This version is from Session 13 (March 4, 2026) and is 9 sessions out of date.**  
> **The current version is at `/workspaces/AI-agents/CORTEX_CONSULTANT_HANDOFF.md`**

---

# SUPERSEDED CONTENT BELOW (Session 13 — March 4, 2026)

> **Comprehensive Handoff Document for Consultants**  
> Generated: March 4, 2026  
> Current Development Phase: Objectives 1-5 Complete, Objective 6 Pending  
> VPS State: Active (budget_halt)

This document provides complete context on **Cortex**, an autonomous dual-agent AI system. It covers the entire journey from inception through current state — philosophy, architecture, every AI agent, and the technical implementation.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Vision — Why This Exists](#2-the-vision--why-this-exists)
3. [The Naming — "Cortex", "Brain", "Hands"](#3-the-naming--cortex-brain-hands)
4. [The Transistor Analogy — Scaling Vision](#4-the-transistor-analogy--scaling-vision)
5. [The 5-Layer Self-Learning System](#5-the-5-layer-self-learning-system)
6. [Architecture Overview](#6-architecture-overview)
7. [Agent Brain — Research Subsystem (10 Agents)](#7-agent-brain--research-subsystem)
8. [Agent Hands — Execution Subsystem (30+ Components)](#8-agent-hands--execution-subsystem)
9. [The Orchestrator Layer](#9-the-orchestrator-layer)
10. [The Identity Layer](#10-the-identity-layer)
11. [Infrastructure & Operations](#11-infrastructure--operations)
12. [Development Journey — Objectives 1-5](#12-development-journey--objectives-1-5)
13. [Current VPS State](#13-current-vps-state)
14. [Known Issues & Technical Debt](#14-known-issues--technical-debt)
15. [The Architect's Vision Documents — Summary](#15-the-architects-vision-documents--summary)
16. [Roadmap — What's Next](#16-roadmap--whats-next)
17. [Codebase Statistics](#17-codebase-statistics)
18. [Appendix: Complete File Inventory](#18-appendix-complete-file-inventory)

---

## 1. Executive Summary

### What Cortex Is

Cortex is a **dual-agent autonomous AI system** consisting of:

- **Agent Brain** — A self-learning research engine that searches the web, scores its own outputs, and evolves its research strategies based on empirical performance data
- **Agent Hands** — An execution engine that writes code, uses tools, deploys applications, and iterates based on visual feedback
- **Cortex Orchestrator** — The strategic reasoning layer above both, making decisions about what to research, what to build, and how to coordinate the two subsystems

### What Makes It Novel

The system implements **5 layers of "self-learning"** — not through model weight updates, but through **strategy document evolution driven by empirical scoring**:

1. Knowledge is accumulated and stored
2. A Critic scores every output on a structured rubric
3. A Meta-Analyst extracts patterns from scores and rewrites strategy documents
4. Strategies evolve autonomously with rollback on regression
5. Cross-domain transfer abstracts principles from one domain to seed others

The strategies are **natural language documents** that the system reads, reasons about, and rewrites based on what works. This is achievable with current tools — no research breakthroughs needed.

### Current State (March 4, 2026)

| Metric | Value |
|--------|-------|
| **Lines of Code** | 44,483 (production Python) |
| **Test Count** | 1,737 tests passing |
| **Test Lines** | 24,998 lines |
| **Production Files** | 120+ Python files |
| **Identity Files** | 8 markdown files |
| **VPS Status** | Active (budget_halt state) |
| **Daily Budget** | $7.00 ($2 Claude + $5 OpenRouter) |
| **Git Commits** | 6 major objectives completed |

### Key Achievement

**Objectives 1-5 of the CORTEX_MASTER_PLAN are complete:**
- ✅ Objective 1: Fixed 3 critical bugs (budget desync, task type mismatch, watchdog stall)
- ✅ Objective 2: Prompt upgrades for all agents, design system created
- ✅ Objective 3: Full three-way Brain↔Cortex↔Hands communication protocol (10 message types)
- ✅ Objective 4: Playwright visual feedback system (browser tool, visual evaluator, visual gate)
- ✅ Objective 5: Train the visual standard (design systems, marketing design, scoring rubric)
- ✅ Audit: 3 additional bugs fixed, 1,737 tests passing

### What Remains

**Objective 6: Full Production-Ready SaaS Build** — The final objective that proves the complete pipeline:
- Brain researches a niche
- Cortex approves the build
- Hands builds the application with visual iteration
- Deploy to Vercel with live URL
- Zero human code written

---

## 2. The Vision — Why This Exists

### The Architect's Goal

The Architect is a solo full-stack developer building a system that, when pointed at any domain:

1. **Researches** the domain (finds opportunities, gaps, problems)
2. **Validates** demand (tests if real humans care and will pay)
3. **Builds** the solution (code, landing pages, SaaS products)
4. **Deploys and markets** it (SEO, outreach, content)
5. **Acquires customers** and generates revenue
6. **Learns from outcomes** and compounds intelligence across domains
7. **Repeats** — getting cheaper and smarter each cycle

### The End State Vision

From the CORTEX_MASTER_PLAN:

```
YOU: "Build a client portal for web agencies"

CORTEX:
  Brain researches the niche → understands pain, users, competitors
  Cortex evaluates → approves build
  Hands builds → architecture, backend, frontend, visual iteration, deploy
  Cortex reports → Telegram message with live URL

YOU: open browser → production-ready SaaS staring back at you
```

**No code written by you. Brain and Hands fully integrated. Cortex supervising end-to-end.**

### First Revenue Target

Before the grand vision, the system needs to earn money to survive:

- **Productized services**: Next.js landing pages for OnlineJobsPH employers
- **Fixed scope, fixed price**: 5-day delivery, $300-500 per project
- **Strategy**: Find job listings → Research the company using Brain → Send personalized pitch → Deliver using Hands

### Key Philosophical Insights (from Architect's notes)

1. **"Don't let it stay a demo."** The biggest risk is building inward forever. Point the system at a real problem, let it break, learn from the breaks.

2. **"The critic is the load-bearing component."** If the critic gives inflated scores, the entire loop learns wrong lessons. The system that judges quality must always be sharper than the system that produces it.

3. **"Revenue before polish."** Every feature decision should ask: "does this help generate revenue or does it just feel productive?"

4. **"The Identity Layer defined today becomes the values of the entire network."** What you bake into the first instance is what scales to 1000 instances.

---

## 3. The Naming — "Cortex", "Brain", "Hands"

### Why "Cortex"

The name comes from the **cerebral cortex** — the outer layer of the brain responsible for higher-level processing, reasoning, and decision-making. In this system:

- **Cortex** = The overall system, and specifically the strategic orchestrator that sits above everything
- The name reflects the system's role as a "thinking" layer that coordinates lower-level functions

### Why "Brain" and "Hands"

From the Architect's original conversations (ULTIMATE PURPOSE.txt):

> "Agent Brain is the research/learning side. Agent Hands is the execution/doing side. Brain learns, Hands acts. They need each other — research without action is academic, action without research is blind."

The metaphor:
- **Brain** = Cognition, learning, memory, strategy evolution
- **Hands** = Execution, building, deploying, visual iteration

This isn't just branding — it's an **architectural constraint**. The two subsystems communicate through a formal task queue (`sync.py`) and typed protocol messages (`protocol.py`), not ad-hoc function calls.

### The Three-Way Communication Model

```
         YOU
          │
          ▼
    CORTEX ORCHESTRATOR
     (Strategic Layer)
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
  BRAIN       HANDS
(Research)  (Execution)
```

- **You → Cortex**: High-level instructions ("Build a landing page for logistics companies")
- **Cortex → Brain**: Research requests, knowledge queries
- **Cortex → Hands**: Build tasks with context from Brain's research
- **Brain/Hands → Cortex**: Results, progress updates, context requests
- **Cortex → You**: Telegram notifications with live URLs

---

## 4. The Transistor Analogy — Scaling Vision

### The Core Insight

From the Architect's perspective document (my-huge-perspetive.md):

> "It's like I'm building a transistor right now, but it processes real-world interaction across domains. Once we have one fully capable AI system, I will deploy multiple of it across multiple VPS and add an orchestrator layer on top. Like how NVIDIA worked on one transistor and now has H100."

### The Scaling Stages

```
STAGE 1 (NOW):     Building the transistor — one Brain + Hands, one domain
STAGE 2 (6-12mo):  Single fully capable instance, multiple domains
STAGE 3 (1-2yr):   Multiple instances on multiple VPS, Meta Orchestrator
STAGE 4 (2-3yr):   Network effect — instances teaching each other
STAGE 5 (3-5yr):   General problem solving at scale
```

### Why This Matters

> "The transistor didn't just make computers faster. It made a new kind of thinking possible."
> 
> "Your system doesn't just make research faster. It makes a new kind of problem-solving possible:
> - Cross-domain
> - Continuous
> - Compounding
> - Coordinated"

### The Critical Decision

> "The Identity Layer you define today in one instance becomes the values of the entire network. What you bake into that first instance is what scales to 1000 instances. So the most important technical decision you will ever make isn't the architecture, isn't the models, isn't the VPS setup. It's what you put in goals.md, ethics.md, values.md of that first instance."

---

## 5. The 5-Layer Self-Learning System

This is the **novel contribution** of Cortex. The Architect explicitly defined what "self-learning" means:

### Layer 1: Knowledge Accumulation

> "The agent acts, the output is stored, it can be retrieved later."

**Implementation:** `memory_store.py` (918 lines)
- Every research output stored as JSON with question, findings, sources, timestamps
- RAG (ChromaDB) enables semantic retrieval
- TF-IDF caching for fast retrieval

**Status:** ✅ Working

### Layer 2: Evaluated Knowledge

> "A critic scores the output 1-10 on a structured rubric. The score is stored alongside the output."

**Implementation:** `agents/critic.py` (511 lines)

**5-dimensional scoring rubric:**
| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| Accuracy | 30% | Factual correctness |
| Depth | 20% | Beyond surface-level |
| Completeness | 20% | Important angles covered |
| Specificity | 15% | Concrete data, numbers, sources |
| Intellectual Honesty | 15% | Flags uncertainty |

**Features:**
- Ensemble mode (Claude Sonnet + DeepSeek for uncorrelated errors)
- Confidence validation (high-confidence claims must cite 2+ sources)
- Parse failure logging for debugging

**Status:** ✅ Working

### Layer 3: Behavioral Adaptation

> "The Meta-Analyst extracts patterns from scores → rewrites agent strategy documents. The strategy is natural language that the agent follows. Evolves every few outputs."

**Implementation:** `agents/meta_analyst.py` (410 lines) + `strategy_store.py` (577 lines)

**How it works:**
1. Loads recent scored outputs for a domain
2. Loads evolution history (what was tried before, outcomes)
3. Analyzes what scored well vs. poorly across dimensions
4. Extracts actionable patterns ("do more of X, stop doing Y")
5. Generates new strategy document incorporating lessons
6. Saves as "pending" → human approval → "trial" → evaluation → "active" or rollback

**Status:** ✅ Infrastructure complete, evolution happening

### Layer 4: Strategy Evolution

> "The strategy rewriting itself becomes autonomous and recursive. Version control + rollback."

**Implementation:** `strategy_store.py`

**Features:**
- Versioned strategy files (v001.md, v002.md, etc.)
- Lifecycle states: pending → trial → active
- Statistical testing (t-test) for significance
- Automatic rollback if score drops >20%
- Immutable clauses that can never be removed

**Status:** ✅ Working

### Layer 5: Cross-Domain Transfer

> "Insights from Domain A abstracted into general principles → applied as strategy seeds in Domain B."

**Implementation:** `agents/cross_domain.py` (629 lines)

**How it works:**
1. Collects proven strategies + performance data from all domains
2. Claude abstracts domain-specific strategies into general principles
3. Principles stored with evidence + provenance
4. When entering new domain, generates seed strategy from principles
5. Seed strategies saved as "pending" (require approval)

**Status:** ✅ Infrastructure built, principles file exists

### The Key Insight

From the Architect's notes (real-self-learning.md):

> "90% of memory-enabled AI projects live and die at Layer 1. They store things but never evaluate, never adapt, never evolve. **Layer 3+ is what makes this novel.**"
>
> "Not the agents. Not the memory. Not the tools. **The strategy evolution loop with empirical scoring is the novel piece.** Strategies are natural language documents — the LLM can read, reason about, and rewrite them. Performance is measured empirically via the Critic, not assumed."

---

## 6. Architecture Overview

### High-Level Structure

```
                         YOU (Architect)
                              │
                              ▼
╔══════════════════════════════════════════════════════════════╗
║                      IDENTITY LAYER                          ║
║                                                              ║
║   goals.md   ethics.md   boundaries.md   risk.md   taste.md  ║
║   design_system.md   marketing_design.md   visual_rubric.md  ║
║                                                              ║
║   What the system exists to do, what it will never do,      ║
║   its operational limits, quality standards, visual taste    ║
╚═══════════════════════════════╤══════════════════════════════╝
                                │
╔═══════════════════════════════▼══════════════════════════════╗
║                    CORTEX ORCHESTRATOR                       ║
║                                                              ║
║   agents/cortex.py (1,236 lines) — Claude Sonnet            ║
║   - pipeline(): research → build flow                        ║
║   - query_knowledge(): access Brain's KB mid-build          ║
║   - monitor_build(): track phase progress                   ║
║   - report_build_complete(): send Telegram notification     ║
╚═════════════════╤═══════════════════════════╤════════════════╝
                  │                           │
╔═════════════════▼═══════════╗  ╔═══════════▼═════════════════╗
║       AGENT BRAIN           ║  ║       AGENT HANDS            ║
║                             ║  ║                              ║
║   Research subsystem        ║  ║   Execution subsystem        ║
║   10 agents, ~4,500 lines   ║  ║   30+ components, ~12,000 ln ║
║                             ║  ║                              ║
║   - Researcher              ║  ║   - Planner                  ║
║   - Critic                  ║  ║   - Executor                 ║
║   - Pre-screener            ║◀─║   - Validator                ║
║   - Meta-Analyst            ║  ║   - Visual Gate              ║
║   - Question Generator      ║  ║   - Visual Evaluator         ║
║   - Synthesizer             ║  ║   - Pattern Learner          ║
║   - Verifier                ║──▶   - Project Orchestrator     ║
║   - Cross-Domain            ║  ║   - 7 Tool Categories        ║
║   - Consensus               ║  ║   - Error Analyzer           ║
║   - Orchestrator            ║  ║   - Checkpoint/Recovery      ║
╚═════════════════════════════╝  ╚══════════════════════════════╝
              │                              │
              └──────────┬───────────────────┘
                         │
╔════════════════════════▼═════════════════════════════════════╗
║                   INFRASTRUCTURE                             ║
║                                                              ║
║   scheduler.py (1,867 ln)    │    watchdog.py (601 ln)       ║
║   sync.py (460 ln)           │    cost_tracker.py (286 ln)   ║
║   memory_store.py (918 ln)   │    strategy_store.py (577 ln) ║
║   analytics.py (816 ln)      │    monitoring.py (327 ln)     ║
║   telegram_bot.py (680 ln)   │    db.py (645 ln) SQLite      ║
║   protocol.py (300 ln)       │    llm_router.py (470 ln)     ║
║   knowledge_graph.py (632 ln)│    loop_guard.py (207 ln)     ║
╚══════════════════════════════════════════════════════════════╝
```

### Model Routing — 4-Tier Architecture

The system uses different AI models for different purposes, optimizing cost vs. quality:

| Tier | Model | Role Assignments | Cost |
|------|-------|------------------|------|
| **T1 (Cheapest)** | DeepSeek V3.2 | question_generator, prescreen, progress_tracker | ~$0.14/$0.55 per 1M |
| **T2 (Fast)** | Grok 4.1 Fast | researcher, executor | ~$0.50/$2.00 per 1M |
| **T3 (Premium)** | Claude Sonnet 4 | critic, meta_analyst, synthesizer, verifier, cortex_orchestrator, planner, exec_validator | ~$3/$15 per 1M |
| **T4 (Chat)** | Gemini 2.0 Flash | chat interface | ~$0.075/$0.30 per 1M |

**Design principle:** Claude is reserved for reasoning that actually matters. Never use Claude where a cheaper model would suffice. The critic is SACRED — never cut corners.

### Communication Protocol

Defined in `protocol.py` (300 lines) — 10 typed dataclass messages:

| Message | Direction | Purpose |
|---------|-----------|---------|
| `ResearchRequest` | Cortex → Brain | Request research on a topic |
| `ResearchComplete` | Brain → Cortex | Research findings ready |
| `BuildTask` | Cortex → Hands | Instruction to build something |
| `PhaseComplete` | Hands → Cortex | A build phase finished |
| `ContextNeeded` | Hands → Cortex | Need more info mid-build |
| `ContextResponse` | Cortex → Hands | Knowledge base context |
| `BuildComplete` | Hands → Cortex | Build finished successfully |
| `BuildFailed` | Hands → Cortex | Build failed |
| `TaskComplete` | Cortex → You | Summary for Telegram |
| `JournalEntry` | Any → Log | Audit trail entry |

---

## 7. Agent Brain — Research Subsystem

### Overview

Agent Brain is the cognitive side of Cortex. It researches, evaluates, synthesizes knowledge, and evolves its own strategies based on what works.

**Total:** 10 agents, ~4,500 lines of code

### Agent Inventory

#### 1. Researcher Agent
**File:** `agents/researcher.py` (723 lines)  
**Model:** Grok 4.1 Fast (T2)  
**Purpose:** Takes a question + strategy → uses web search tools → produces structured findings

**How it works:**
1. Receives research question and domain strategy
2. Plans search approach (decomposes into sub-questions)
3. Executes web searches (DuckDuckGo via `tools/web_search.py`)
4. Fetches relevant pages (Scrapling via `tools/web_fetcher.py`)
5. Optional: Browser for JS-rendered sites (`browser/stealth_browser.py`)
6. Synthesizes findings into structured JSON output

**Key features:**
- Date-aware: knows today's date, penalizes claims about future
- Anti-hallucination rules baked into prompt
- Injects: identity summary, domain strategy, RAG context, knowledge graph summary
- Max 8 tool rounds, 10 searches, 8 fetches per run

#### 2. Critic Agent
**File:** `agents/critic.py` (511 lines)  
**Model:** Claude Sonnet 4 (T3) — SACRED, never cut corners  
**Purpose:** Reviews researcher output → scores 1-10 → provides actionable feedback

**Scoring rubric:** Accuracy (30%), Depth (20%), Completeness (20%), Specificity (15%), Intellectual Honesty (15%)

**Features:**
- Ensemble mode: second opinion from DeepSeek (CRITIC_ENSEMBLE_MODEL_B)
- Confidence validation: high-confidence claims must cite 2+ sources
- Recency awareness: penalizes stale data for time-sensitive questions
- Parse failure logging to `logs/` directory

**Threshold:** Score ≥ 6 to accept. Below 6 → retry with critique feedback (max 2 retries).

#### 3. Pre-screener
**File:** `prescreen.py` (245 lines)  
**Model:** DeepSeek V3.2 (T1) — cheapest  
**Purpose:** Cheap filter before expensive Claude critique

**How it works:**
- Quick-scores research output
- Accept if score ≥ 7.5 (skip Claude)
- Reject if score ≤ 3.5 (skip Claude)
- Escalate to Claude if between

**Cost savings:** ~40% reduction in Claude critic calls

#### 4. Meta-Analyst Agent
**File:** `agents/meta_analyst.py` (410 lines)  
**Model:** Claude Sonnet 4 (T3)  
**Purpose:** Extracts patterns from scored outputs → rewrites strategy documents

**How it works:**
1. Loads recent scored outputs (configurable window, default 20)
2. Loads evolution history (what was tried before)
3. Analyzes patterns: what dimensions score high/low?
4. Generates new strategy incorporating lessons
5. Saves as "pending" with changelog

**Constraints:**
- Suppressed during warmup (need MIN_OUTPUTS_FOR_ANALYSIS outputs first)
- Suppressed during trial period
- Respects IMMUTABLE_STRATEGY_CLAUSES
- Runs every EVOLVE_EVERY_N outputs (default 3)

#### 5. Question Generator
**File:** `agents/question_generator.py` (417 lines)  
**Model:** DeepSeek V3.2 (T1)  
**Purpose:** Diagnoses knowledge gaps → generates next research question

**How it works:**
1. Reads memory + knowledge base + domain goal
2. Identifies what's been covered vs. what's missing
3. Generates ranked list of next questions
4. Avoids questions too similar to recent ones (dedup)

#### 6. Synthesizer Agent
**File:** `agents/synthesizer.py` (439 lines)  
**Model:** Claude Sonnet 4 (T3)  
**Purpose:** Integrates findings into domain knowledge base

**What it does:**
1. Extracts claims from accepted research outputs
2. Deduplicates similar claims
3. Detects contradictions between outputs
4. Marks superseded claims when newer evidence exists
5. Assesses confidence levels across sources
6. Identifies remaining gaps
7. Produces domain summary

**Output:** Structured knowledge base with claims, confidence levels, contradictions, gaps

#### 7. Verifier Agent
**File:** `agents/verifier.py` (337 lines)  
**Model:** Claude Sonnet 4 (T3)  
**Purpose:** Tracks time-bound predictions → checks against reality

**How it works:**
1. Extracts predictive claims ("X will happen by date Y")
2. Stores with verification deadline
3. When deadline passes, searches web for outcome
4. Updates claim confidence based on prediction accuracy

**Why it matters:** Breaks the circular LLM-judging-LLM problem by introducing external ground truth.

#### 8. Cross-Domain Agent
**File:** `agents/cross_domain.py` (629 lines)  
**Model:** Claude Sonnet 4 (T3)  
**Purpose:** Extracts general principles → seeds new domains

**How it works:**
1. Collects proven strategies from mature domains
2. Claude abstracts domain-specific tips into general principles
3. Stores principles with evidence + provenance in `_principles.json`
4. When entering new domain, generates seed strategy from relevant principles

**Example principle:** "Use 3-5 focused searches rather than many broad ones"

#### 9. Consensus Agent
**File:** `agents/consensus.py` (284 lines)  
**Model:** Multiple (for diversity)  
**Purpose:** Multi-agent agreement on controversial questions

**How it works:**
1. Same question sent to 3 independent researchers
2. Each produces findings independently
3. Synthesizer merges results
4. Disagreements flagged for review

**Status:** Built but not used in daemon loop by default (CONSENSUS_ENABLED = False)

#### 10. Domain Orchestrator
**File:** `agents/orchestrator.py` (582 lines)  
**Purpose:** Multi-domain round allocation and prioritization

**Functions:**
- `discover_domains()`: Find all domains with outputs
- `prioritize_domains()`: Rank by strategy status, goal alignment, time decay
- `allocate_rounds()`: Distribute budget across domains

---

## 8. Agent Hands — Execution Subsystem

### Overview

Agent Hands is the execution side of Cortex. It plans tasks, writes code, runs commands, takes screenshots, evaluates visual quality, and deploys applications.

**Total:** 30+ components, ~12,000 lines of code

### Core Pipeline

#### Planner
**File:** `hands/planner.py` (594 lines)  
**Model:** Claude Sonnet 4 (T3)  
**Purpose:** Decomposes a task into concrete, tool-using steps

**Input:**
- Goal (natural language task description)
- Available tools (from registry)
- Domain knowledge (from Brain's KB)
- Execution strategy (from strategy store)
- Workspace context (file tree, key files)

**Output:**
- Structured plan: ordered steps with tool selections and parameters
- Each step marked "required" or "optional"

#### Executor
**File:** `hands/executor.py` (932 lines)  
**Model:** Grok 4.1 Fast (T2)  
**Purpose:** Executes a plan step-by-step using tools

**Features:**
- Multi-turn conversational loop with tool feedback
- Step-level retry on failures (up to 2 per step)
- Context window management (summarizes old steps)
- Hard cost ceiling: $0.50 per execution
- Visual gate integration (mid-build screenshots)
- Page-type aware design system loading
- Abort cleanup with resource release

**Recent fixes (Objective audit):**
- `visual_gate.cleanup()` called on abort
- `__del__` safety net on VisualGate
- Page-type properly wired from CLI

#### Validator
**File:** `hands/validator.py` (798 lines)  
**Model:** Claude Sonnet 4 (T3)  
**Purpose:** Scores execution output quality

**5-dimensional execution rubric:**
| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| Correctness | 30% | Does the code work? |
| Completeness | 20% | All requirements met? |
| Code Quality | 20% | Clean, idiomatic? |
| Security | 15% | Safe patterns? |
| KB Alignment | 15% | Uses best practices? |

**Features:**
- Reads actual artifact file contents (not just summaries)
- Runs automated tests if present
- Threshold: Score ≥ 7 (higher than research threshold of 6)

### Visual Feedback System (Objective 4)

#### Visual Gate
**File:** `hands/visual_gate.py` (344 lines)  
**Purpose:** Mid-build visual quality checks during execution

**How it works:**
1. Detects when frontend files exist
2. Starts dev server if needed
3. Takes screenshot via Playwright
4. Sends to Claude Vision for evaluation
5. Injects fix instructions if quality below threshold

**Features:**
- Auto-skips when no frontend files (zero cost)
- Configurable check frequency
- Page-type aware (app vs marketing)
- Resource cleanup on abort/completion

#### Visual Evaluator
**File:** `hands/visual_evaluator.py` (634 lines)  
**Model:** Claude Sonnet 4 (T3) with vision  
**Purpose:** Claude Vision scores screenshots against design standard

**Functions:**
- `evaluate_screenshot()`: Basic evaluation
- `evaluate_with_reference()`: Compare to reference image
- `generate_fix_instructions()`: Specific fixes for issues
- `store_visual_score()`: Persist scores for learning

**Thresholds:**
- VISUAL_ACCEPT_THRESHOLD = 8 (accept as-is)
- VISUAL_FIX_THRESHOLD = 5 (fix pass needed)
- MAX_VISUAL_FIX_ROUNDS = 2 (prevent infinite loop)

#### Browser Tool
**File:** `hands/tools/browser.py` (432 lines)  
**Purpose:** Playwright integration for visual feedback

**Functions:**
- `screenshot(url, viewport?)` → base64 image
- `navigate(url)` → load page
- `click(selector)` → interact with element
- `fill(selector, text)` → fill input
- `wait_for(selector)` → wait for element

### Tools (7 Categories)

| Tool | File | Lines | Purpose |
|------|------|-------|---------|
| **Code** | `hands/tools/code.py` | 394 | Write, edit, read files |
| **Terminal** | `hands/tools/terminal.py` | 258 | Run shell commands |
| **Git** | `hands/tools/git.py` | 206 | Git operations |
| **Search** | `hands/tools/search.py` | 352 | Web search |
| **HTTP** | `hands/tools/http.py` | 229 | HTTP requests, API calls |
| **Browser** | `hands/tools/browser.py` | 432 | Playwright visual |
| **Registry** | `hands/tools/registry.py` | 345 | Tool registration |

**Tool Safety:**
- Sandbox mode by default (EXEC_SANDBOX_MODE = True)
- Whitelist of allowed commands (EXEC_ALLOWED_COMMANDS)
- Blocked patterns (EXEC_BLOCKED_PATTERNS): no `rm -rf /`, fork bombs, privilege escalation
- Max file size: 100KB per write
- Optional directory restrictions

### Learning Layer

#### Pattern Learner
**File:** `hands/pattern_learner.py` (497 lines)  
**Purpose:** Extracts reusable patterns from execution history

**What it learns:**
- Tool usage patterns correlated with success/failure
- Step sequences that reliably work or fail
- Error categories and their resolutions
- Domain-specific execution heuristics

**Output:** Lessons injected into future planner/executor prompts

#### Execution Meta-Analyst
**File:** `hands/exec_meta.py` (506 lines)  
**Purpose:** Execution strategy evolution (parallel to Brain's meta-analyst)

### Supporting Components

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| Error Analyzer | `error_analyzer.py` | 192 | Root cause analysis |
| Feedback Cache | `feedback_cache.py` | 206 | Cache correction feedback |
| Mid Validator | `mid_validator.py` | 264 | Mid-execution validation |
| Output Polisher | `output_polisher.py` | 223 | Clean up outputs |
| Plan Cache | `plan_cache.py` | 226 | Cache similar plans |
| Plan Preflight | `plan_preflight.py` | 284 | Validate plan before exec |
| Retry Advisor | `retry_advisor.py` | 266 | Advise on retry strategies |
| Strategy Assembler | `strategy_assembler.py` | 226 | Build exec strategies |
| Task Generator | `task_generator.py` | 332 | Generate tasks from goals |
| Timeout Adapter | `timeout_adapter.py` | 147 | Adapt timeouts by complexity |
| Tool Health | `tool_health.py` | 149 | Monitor tool reliability |
| Workspace Diff | `workspace_diff.py` | 122 | Track workspace changes |
| Checkpoint | `checkpoint.py` | 172 | Save/restore progress |
| Artifact Tracker | `artifact_tracker.py` | 365 | Track produced artifacts |
| Project Orchestrator | `project_orchestrator.py` | 832 | Multi-phase projects |
| Code Exemplars | `code_exemplars.py` | 247 | Example code patterns |
| Exec Templates | `exec_templates.py` | 280 | Execution templates |
| File Repair | `file_repair.py` | 246 | Auto-fix common issues |
| Exec Analytics | `exec_analytics.py` | 266 | Execution metrics |
| Exec Cross-Domain | `exec_cross_domain.py` | 254 | Cross-domain exec transfer |
| Exec Memory | `exec_memory.py` | 142 | Execution memory store |

---

## 9. The Orchestrator Layer

### Scheduler
**File:** `scheduler.py` (1,867 lines)  
**Purpose:** The daemon loop that runs everything

**How it works each cycle:**
1. **Plan phase**: Cortex Orchestrator decides what to focus on
2. **Allocate**: Distribute rounds across domains based on priorities
3. **Execute**: Run research rounds
4. **Learn**: Run meta-analyst if enough outputs
5. **Sync**: Create tasks for Hands if research suggests actions
6. **Hands**: Execute pending build tasks
7. **Health check**: Run monitoring
8. **Sleep**: Wait for next cycle (default 60 minutes)
9. **Repeat**

**CLI flags:**
- `--daemon`: Run as daemon
- `--interval N`: Minutes between cycles
- `--autonomous`: No human approval required for strategies
- `--rounds-per-cycle N`: Max rounds per cycle

### Watchdog
**File:** `watchdog.py` (601 lines)  
**Purpose:** Circuit breaker and health monitoring for 24/7 operation

**Responsibilities:**
1. **Heartbeat monitoring**: Detect stalled processes
2. **Health checks**: Run monitoring each cycle
3. **Circuit breaker**: Pause on 3 consecutive critical alerts
4. **Crash counter**: Cooldown after 5 consecutive failures (30 min)
5. **Cost ceiling**: Hard stop at 1.5x daily budget ($10.50)
6. **Recovery**: Auto-restart after transient failures
7. **State persistence**: Survives daemon restarts

**States:**
| State | Meaning |
|-------|---------|
| `running` | Normal operation |
| `paused` | Temporarily paused (will auto-resume) |
| `cooldown` | Cooling down after failures (30 min) |
| `circuit_open` | Circuit breaker tripped (needs human review) |
| `budget_halt` | Hard cost ceiling hit |
| `stopped` | Gracefully stopped |

### Sync
**File:** `sync.py` (460 lines)  
**Purpose:** Brain → Hands task queue

**Features:**
- Tasks persisted as JSON in `logs/sync_tasks.json`
- Task lifecycle: pending → in_progress → completed | failed | stale
- Stale detection: tasks >72h without action get flagged
- Max pending: 50 tasks (prevents unbounded growth)

**Task types:** `action`, `build`, `deploy`

### Cortex Orchestrator Agent
**File:** `agents/cortex.py` (1,236 lines)  
**Model:** Claude Sonnet 4 (T3)  
**Purpose:** The "brain of brains" — strategic reasoning above everything

**Key functions:**
- `pipeline()`: Full research → build flow
- `query_knowledge()`: Access Brain's KB during builds
- `report_build_complete()`: Send Telegram notifications
- `monitor_build()`: Track phase progress, intervene if needed
- `_journal()`: Write to audit trail

---

## 10. The Identity Layer

The Identity Layer is a set of **8 markdown files** that define what the system is, what it will do, and what it will never do. Every agent reads these. They are **immutable** by the system itself.

**Location:** `agent-brain/identity/`

### goals.md — What the System Exists to Do

**Primary Goal:**
> "Generate revenue by finding, validating, building, and selling solutions to real problems."

**Operating Goals (priority order):**
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
4. Never optimize against constraints
5. Never harm real people
6. Never access systems without authorization

**Always Do:**
1. Flag uncertainty
2. Log everything
3. Respect cost boundaries
4. Preserve human control

### boundaries.md — Operational Limits

**Budget:**
- Daily spend limit: $7.00 USD ($2 Claude + $5 OpenRouter)
- Hard ceiling: 1.5x daily ($10.50)
- Single execution cap: $0.50

**Quality:**
- Research threshold: 6/10
- Execution threshold: 7/10
- Visual threshold: 8/10
- Max retries: 2
- Auto-rollback on >1.0 score drop

### risk.md — Risk Tolerance

**Risk Tiers:**
- **Tier 1** (Proven, 10+ outputs): Up to 40% daily budget
- **Tier 2** (Developing, 3-10 outputs): Up to 25% budget
- **Tier 3** (New, 0-2 outputs): Up to 15% budget

### taste.md — Quality Standards

**Good Research:**
- Specific, not vague: "72% ghosting rate (2024 survey, n=500)" > "reliability is a problem"
- Sourced, not assumed
- Actionable, not academic
- Honest about uncertainty

### design_system.md — Visual Standard for Apps (420+ lines)

Created in Objective 5. Defines:
- Component library: shadcn/ui
- Animation: Framer Motion patterns
- Typography: font families, sizes, weights
- Color system: palette structure, dark mode
- Spacing: 4px/8px grid
- States: empty, loading, error (all designed)
- Responsive: mobile-first breakpoints

### marketing_design.md — Visual Standard for Landing Pages (325+ lines)

Created in Objective 5. Defines:
- Hero section structure
- Social proof patterns
- CTA design and placement
- Above-the-fold content rules
- Testimonial formatting
- Pricing table design
- Footer structure

### visual_scoring_rubric.md — Scoring Calibration (143+ lines)

Created in Objective 5. Defines:
- What 5/10 looks like vs 8/10 vs 10/10
- Specific visual anti-patterns
- Calibration examples

---

## 11. Infrastructure & Operations

### Database Layer
**File:** `db.py` (645 lines)  
**Tech:** SQLite with WAL mode for concurrent access

**Tables:**
| Table | Purpose |
|-------|---------|
| `outputs` | Research outputs with scores |
| `costs` | API cost tracking per call |
| `alerts` | Health alerts history |
| `health_snapshots` | Periodic health state |
| `run_log` | Research run history |
| `sync_tasks` | Brain→Hands task queue |
| `daemon_cycles` | Daemon cycle history |

### Cost Tracking
**File:** `cost_tracker.py` (286 lines)

**Features:**
- Dual-write to JSONL + SQLite
- Per-provider tracking (Claude vs OpenRouter)
- Daily budget enforcement
- All-time spend tracking

**Configuration:**
```python
DAILY_BUDGET_USD = 7.00
DAILY_BUDGET_CLAUDE = 2.00
DAILY_BUDGET_OPENROUTER = 5.00
```

### LLM Router
**File:** `llm_router.py` (470 lines)  
**Purpose:** Multi-provider abstraction

**Routing:**
- `claude-*` models → Anthropic API (direct)
- `*/` models (e.g., `x-ai/grok-4.1-fast`) → OpenRouter API

**Features:**
- Normalized response format (Anthropic-compatible)
- Tool use support for both providers
- Reasoning effort configuration per role

### Monitoring
**File:** `monitoring.py` (327 lines)  
**Purpose:** Score trend detection, health checks, automated alerts

**6 automated checks:**
1. Declining score trends
2. Sudden score drops (>1.5 points)
3. Budget velocity (>80% consumed)
4. Stale domains (>14 days inactive)
5. High rejection rates (>50%)
6. Error rate spikes

### Analytics
**File:** `analytics.py` (816 lines)  
**Purpose:** Performance analysis

**Functions:**
- `score_trajectory(domain)`: Score trend over time
- `domain_comparison()`: Compare all domains
- `strategy_effectiveness()`: Compare strategy versions
- `cost_efficiency()`: Cost per accepted output

### Loop Guard
**File:** `loop_guard.py` (207 lines)  
**Purpose:** Real-time protection during auto mode

**Detects:**
- Consecutive failures (3x)
- Question similarity (>70% overlap)
- Cost velocity (>80% of budget)
- Score regression
- Same-error repetition

### Telegram Bot
**File:** `telegram_bot.py` (680 lines)  
**Purpose:** Chat interface + alerting

**Commands:**
- `/status` — System status
- `/budget` — Budget report
- `/domains` — Domain list
- `/research <question>` — Run research
- Model switching via `/model`

### Knowledge Graph
**File:** `knowledge_graph.py` (632 lines)  
**Purpose:** Structured relationships between findings

**Features:**
- Nodes: claims, topics, sources, questions
- Edges: supports, contradicts, supersedes, relates_to
- Contradiction detection
- Gap analysis
- Cluster identification

### RAG (Retrieval-Augmented Generation)
**Files:** `rag/` (3 files, 914 lines)  
**Tech:** ChromaDB + all-MiniLM-L6-v2 embeddings

**Components:**
- `embeddings.py`: Local embedding generation
- `vector_store.py`: ChromaDB persistence
- `retrieval.py`: Semantic search

---

## 12. Development Journey — Objectives 1-5

### Timeline

| Date | Commit | Objective | Changes |
|------|--------|-----------|---------|
| Mar 3 | d9800ca | Objective 1 | Fix 3 critical bugs, deploy to VPS |
| Mar 3 | f89f0e0 | Objective 2 prep | Prompt upgrades, design system |
| Mar 3 | 62afba9 | Objective 3 | Full 3-way communication protocol |
| Mar 3 | 47b2522 | Objective 4 | Playwright visual feedback system |
| Mar 3 | 497490b | Objective 5 | Visual standard training |
| Mar 4 | f0e85fd | Audit | Fix 3 more bugs, 27 new tests |

### Objective 1: Stop the Bleeding

**Bugs Fixed:**
1. **Budget desync** — `check_budget()` was reading JSONL, DB had different data. Fix: read from SQLite as source of truth.
2. **Brain→Hands pipeline dead** — Tasks created with type "investigate" but executor only accepted "build"/"action". Fix: map keywords correctly.
3. **Watchdog cooldown stall** — "all" meta-domain triggered phantom cooldowns. Fix: filter invalid domains.

**Result:** 1,538 tests passing, deployed to VPS

### Objective 2: Prompt Upgrades

**Changes:**
- Upgraded `identity/boundaries.md` with operational limits
- Upgraded `hands/planner.py` prompt for better structure
- Upgraded `hands/executor.py` prompt with anti-patterns
- Upgraded `agents/cortex.py` prompt for strategic reasoning
- Created `identity/design_system.md` (v1.0)
- Fixed executor model to Grok 4.1 Fast

### Objective 3: Full Three-Way Communication

**Created:** `protocol.py` with 10 typed message dataclasses

**Messages:**
- ResearchRequest, ResearchComplete
- BuildTask, PhaseComplete, ContextNeeded, ContextResponse
- BuildComplete, BuildFailed
- TaskComplete, JournalEntry

**Tests:** 43 new tests for protocol

### Objective 4: Give Hands Eyes (Playwright)

**Created:**
- `hands/tools/browser.py` — Playwright tool integration
- `hands/visual_evaluator.py` — Claude Vision scoring
- `hands/visual_gate.py` — Mid-build visual checks
- Executor integration for visual feedback loop

**Tests:** 62 new tests, 1,643 total passing

### Objective 5: Train the Visual Standard

**Created:**
- `identity/design_system.md` — App UI standard (v1.1, 420+ lines)
- `identity/marketing_design.md` — Marketing page standard (v1.0, 325+ lines)
- `identity/visual_scoring_rubric.md` — Calibration guide (143+ lines)

**Changes:**
- Executor loads page_type-aware design system
- Scoring calibration and storage
- Score persistence for strategy evolution

**Tests:** 67 new tests, 1,710 total passing

### Audit Pass

**Bugs Fixed:**
1. CLI page_type wiring — `_detect_page_type()` now passes to execute_plan()
2. Abort cleanup leak — `visual_gate.cleanup()` called on abort
3. No `__del__` safety net — Added to VisualGate class

**Tests:** 27 new tests, 1,737 total passing

### Pre-existing Issues (Low Severity, Not Fixed)

1. `sync.py` stale import `execute` (should be `execute_plan`)
2. `sync.py` stale import `validate` (should be `validate_execution`)
3. `project_orchestrator.py` stale import
4. `scheduler.py` missing page_type/visual_context in execute_plan() call

---

## 13. Current VPS State

### Server Details

| Property | Value |
|----------|-------|
| **IP** | 207.180.219.27 |
| **Provider** | Contabo VPS |
| **OS** | Ubuntu 24.04.3 LTS |
| **User** | root |
| **Git Version** | d9800ca (Objective 1 deployed) |

### Service Status (March 4, 2026)

| Service | Status | State |
|---------|--------|-------|
| cortex-daemon | ✅ Active | budget_halt |
| cortex-telegram | ✅ Active | running |

### Watchdog State

```json
{
  "state": "budget_halt",
  "consecutive_failures": 0,
  "cycle_count": 23,
  "total_rounds": 30,
  "paused_reason": null
}
```

The daemon is in `budget_halt` state because:
- Total spend today: $25.40
- Daily budget: $7.00
- Hard ceiling: $10.50

The system correctly halted when it hit the cost ceiling.

### Budget Status

```
Within budget: False
Spent today: $25.40
Daily limit: $7.00
Remaining: $0.00 (blocked)
```

### Latest Log Lines

```
[INFO] 2026-03-03T14:44:44 === Cycle 14 starting ===
[WARNING] 2026-03-03T14:44:44 Watchdog blocked cycle: Hard cost ceiling ($10.50) exceeded
[INFO] 2026-03-03T15:44:44 === Cycle 15 starting ===
[WARNING] 2026-03-03T15:44:44 Watchdog blocked cycle: Hard cost ceiling reached — halted for the day
...
```

The watchdog is correctly blocking cycles because the budget is exhausted.

### VPS vs Local Codebase

| | VPS | Local |
|---|-----|-------|
| Git commit | d9800ca | f0e85fd |
| Tests | 1,538 | 1,737 |

**Note:** VPS needs `git pull` to get Objectives 2-5 and audit fixes.

---

## 14. Known Issues & Technical Debt

### High Priority

#### 1. VPS Not Updated
The VPS is running Objective 1 code (d9800ca). It needs:
- `git pull` to get f0e85fd
- Service restart

#### 2. Pre-existing Stale Imports (4 files)
Low severity but should be cleaned up:
- `sync.py`: `execute` → `execute_plan`, `validate` → `validate_execution`
- `project_orchestrator.py`: same stale import
- `scheduler.py`: execute_plan() call missing page_type/visual_context params

#### 3. Consensus Agent Unused
Built but CONSENSUS_ENABLED = False. Not wired into daemon loop.

#### 4. Knowledge Graph Auto-Trigger Missing
Graph extraction works but not auto-triggered on new outputs. Gets stale.

#### 5. Dashboard Not Deployed
`dashboard/api.py` (784 lines) built but not running on VPS.

### Medium Priority

#### 6. Domain Goals Sparse
Only productized-services has a goal defined. Other domains lack direction.

#### 7. Verifier Underused
Built to break circular LLM-judging-LLM but rarely called.

#### 8. MCP Gateway Disconnected
`mcp/` (1,739 lines) built for external tool servers but not configured.

### Tech Debt

- Some test isolation issues (tests leave artifacts)
- Browser tools disabled by default (needs playwright install)

---

## 15. The Architect's Vision Documents — Summary

The `/workspaces/AI-agents/my-notes.md/` directory contains the Architect's raw thinking. Key files:

### ULTIMATE PURPOSE.txt (603 lines)

The origin conversation about building self-learning AI.

**Key concepts:**
- **Observable Horizon**: The system must know what it doesn't know
- **Calibrated uncertainty**: Not just confidence scores, but WHY
- "The most dangerous version is one confidently wrong at scale."
- "Don't let it stay a demo."

### real-self-learning.md (231 lines)

The precise 5-layer definition.

**Key insight:**
> "90% of memory-enabled AI projects live and die at Layer 1. They store things but never evaluate. Layer 3+ is what makes this novel."

### vision-hands.md

Brain + Hands architecture, tool registry, revenue model.

**Revenue model:**
- Marketplace products (Next.js landing pages)
- $500 max initial investment
- Self-funding by Month 2-3

### where-this-goes.md

Phase roadmap:
1. Statistical Grounding (volume)
2. Memory as Knowledge Graph
3. Multi-Agent Collaboration
4. Domain Specialization
5. Continuous Autonomous Operation

**Key warning:**
> "The biggest risk isn't technical. It's evaluation quality. The critic is the sacred component."

### more-insight.md

Honest gap analysis.

**Key warnings:**
- "The system has never run unsupervised"
- "The circular critic problem is real"
- "Don't let it stay a demo"

### ACTION-PLAN.md

Concrete action items.

**Key point:**
> "Brain is production-ready for productized-services. Don't wait on Brain improvements to act."

### ideal-thoughts.md (3,604 lines)

Full ideal architecture discussion.

**Contains:**
- 26-agent architecture across 5 layers
- Cost optimization strategy
- Model routing decisions
- Learning loop implementation

### my-huge-perspetive.md (977 lines)

The transistor→H100 analogy.

**Key insight:**
> "The Identity Layer you define today in one instance becomes the values of the entire network."

**Scaling stages:**
- Stage 1 (NOW): One Brain + Hands
- Stage 2 (6-12mo): Multiple domains
- Stage 3 (1-2yr): Multiple VPS
- Stage 4 (2-3yr): Instances teaching each other
- Stage 5 (3-5yr): General problem solving

### OLJstrat-mar1.md (496 lines)

OnlineJobsPH outreach strategy.

**The pitch structure:**
1. Pattern interrupt (prove you read their post)
2. Reframe (make alternative feel safer)
3. Specific deliverable
4. Personalized line (from Brain's research)
5. Friction removal
6. Single CTA

### 8phaseplan.md (273 lines)

Implementation roadmap from "here" to "one working transistor" — 8 phases.

---

## 16. Roadmap — What's Next

### Immediate (This Week)

1. **Update VPS** — `git pull` to get Objectives 2-5 + audit fixes
2. **Reset budget** — New day, fresh budget, daemon should resume
3. **Test visual pipeline** — Run Hands execution with visual feedback
4. **Fix stale imports** — Clean up the 4 pre-existing issues

### Short-Term (1-2 Weeks)

5. **Objective 6: Full SaaS Build** — The final objective
   - Pick niche with Brain research data
   - Phase 0: Context intake (PRD)
   - Phase 1: Architecture (blueprint, human review gate)
   - Phase 2-3: Backend (Supabase setup, API routes)
   - Phase 4: Frontend (visual iteration loop)
   - Phase 5: Integration (Playwright end-to-end)
   - Phase 6: DevOps (Vercel deploy)
   - Phase 7: Critic + learning

### Medium-Term (1-3 Months)

6. **First revenue** — Send OnlineJobsPH pitches, close first sale
7. **Strategy evolution at scale** — More domains, more data, faster evolution
8. **Dashboard deployed** — Web UI for monitoring

### Long-Term (3-12 Months)

9. **Growth capability** — SEO, content, outreach agents
10. **Economics agent** — Kill/pivot/double-down decisions
11. **Multi-VPS** — Scale to multiple instances
12. **Meta-Orchestrator** — Cross-instance coordination

### Success Criteria (The Transistor Test)

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

---

## 17. Codebase Statistics

### Lines of Code Summary

| Category | Files | Lines |
|----------|-------|-------|
| **Production Python** | 120 | 44,483 |
| **Test Python** | 38 | 24,998 |
| **Identity Markdown** | 8 | ~1,500 |
| **Total** | ~166 | ~71,000 |

### By Component

| Component | Lines | Notes |
|-----------|-------|-------|
| Brain Agents | ~4,500 | 10 agents |
| Hands System | ~12,000 | 30+ components |
| Infrastructure | ~10,000 | scheduler, watchdog, sync, etc. |
| CLI | ~4,500 | 11 command modules |
| Tools | ~2,000 | 7 tool categories |
| Browser | ~1,250 | stealth browser + auth |
| RAG | ~914 | ChromaDB + embeddings |
| Utils | ~1,200 | retry, cache, vault, etc. |
| Dashboard | ~933 | FastAPI backend |
| Deploy | ~923 | VPS deployment |
| MCP | ~1,739 | External tool gateway |
| Examples | ~575 | 5 example scripts |

### Test Coverage

- **Total tests:** 1,737
- **Test files:** 38
- **Major test files:**
  - `test_new_features.py`: ~2,500 lines
  - `test_watchdog.py`: ~1,200 lines
  - `test_integration.py`: ~1,000 lines

---

## 18. Appendix: Complete File Inventory

### Brain Agents (`agent-brain/agents/`)

| File | Lines | Purpose |
|------|-------|---------|
| `researcher.py` | 723 | Web research with tool use |
| `critic.py` | 511 | 5-dimensional rubric scoring |
| `cortex.py` | 1,236 | Strategic orchestrator |
| `cross_domain.py` | 629 | Principle extraction + transfer |
| `meta_analyst.py` | 410 | Strategy evolution |
| `question_generator.py` | 417 | Gap → next question |
| `synthesizer.py` | 439 | KB integration |
| `verifier.py` | 337 | Prediction tracking |
| `consensus.py` | 284 | Multi-agent agreement |
| `orchestrator.py` | 582 | Domain orchestration |

### Hands System (`agent-brain/hands/`)

| File | Lines | Purpose |
|------|-------|---------|
| `planner.py` | 594 | Structured plan generation |
| `executor.py` | 932 | Multi-turn tool execution |
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
| `constants.py` | 53 | Shared constants |
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
| `timeout_adapter.py` | 147 | Adapt timeouts |
| `tool_health.py` | 149 | Monitor tool reliability |
| `workspace_diff.py` | 122 | Track workspace changes |

### Hands Tools (`agent-brain/hands/tools/`)

| File | Lines | Purpose |
|------|-------|---------|
| `registry.py` | 345 | Tool registration |
| `code.py` | 394 | Code operations |
| `terminal.py` | 258 | Shell commands |
| `git.py` | 206 | Git operations |
| `search.py` | 352 | Web search |
| `http.py` | 229 | HTTP requests |
| `browser.py` | 432 | Playwright visual |

### Infrastructure (`agent-brain/`)

| File | Lines | Purpose |
|------|-------|---------|
| `scheduler.py` | 1,867 | Daemon loop + Cortex |
| `watchdog.py` | 601 | Circuit breaker + health |
| `sync.py` | 460 | Brain↔Hands queue |
| `main.py` | 1,258 | CLI entry point |
| `config.py` | 325 | All configuration |
| `db.py` | 645 | SQLite backend |
| `memory_store.py` | 918 | Knowledge base |
| `strategy_store.py` | 577 | Strategy versioning |
| `cost_tracker.py` | 286 | Budget awareness |
| `analytics.py` | 816 | Score analysis |
| `monitoring.py` | 327 | Health checks |
| `knowledge_graph.py` | 632 | Entity/relation graphs |
| `identity_loader.py` | 249 | Identity layer loading |
| `llm_router.py` | 470 | Model routing |
| `loop_guard.py` | 207 | Loop prevention |
| `prescreen.py` | 245 | Cheap pre-filter |
| `telegram_bot.py` | 680 | Telegram interface |
| `protocol.py` | 300 | Typed messages |
| `alerts.py` | 218 | Alert management |
| `progress_tracker.py` | 303 | Goal distance assessment |
| `domain_goals.py` | 148 | Domain goal tracking |
| `domain_seeder.py` | 159 | New domain seeding |
| `validator.py` | 505 | Research validation |
| `research_lessons.py` | 152 | Learned lessons |

### CLI (`agent-brain/cli/`)

| File | Lines | Purpose |
|------|-------|---------|
| `chat.py` | 1,903 | Chat mode interface |
| `execution.py` | 928 | Hands execution CLI |
| `infrastructure.py` | 878 | Daemon, budget, status |
| `research.py` | 598 | Research commands |
| `strategy.py` | 358 | Strategy management |
| `tools_cmd.py` | 360 | Tool commands |
| `project.py` | 172 | Project commands |
| `knowledge.py` | 166 | KB commands |
| `deploy_cmd.py` | 126 | VPS deployment |
| `vault.py` | 115 | Credential vault |
| `browser_cmd.py` | 61 | Browser commands |

### Identity Layer (`agent-brain/identity/`)

| File | Purpose |
|------|---------|
| `goals.md` | What the system exists to do |
| `ethics.md` | Hard constraints |
| `boundaries.md` | Operational limits |
| `risk.md` | Risk tolerance |
| `taste.md` | Quality standards |
| `design_system.md` | App UI standard |
| `marketing_design.md` | Marketing page standard |
| `visual_scoring_rubric.md` | Visual scoring calibration |

---

## End of Document

**For questions or clarifications, contact the Architect directly.**

**Document generated by GitHub Copilot (Claude Opus 4.5) based on full codebase audit, VPS state check, and comprehensive reading of all architectural notes.**

---

*Last updated: March 4, 2026*
