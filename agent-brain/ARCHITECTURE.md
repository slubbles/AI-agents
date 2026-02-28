# Agent Brain — Technical Architecture Document

> **Version:** 2.0 (Hardened)  
> **Last Updated:** February 2026  
> **Total Codebase:** 15,302 lines Python | 229 tests | 34 modules  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Layers](#2-architecture-layers)
3. [Module Reference](#3-module-reference)
4. [Data Flow](#4-data-flow)
5. [Agent Roles](#5-agent-roles)
6. [Scoring & Quality Gate](#6-scoring--quality-gate)
7. [Strategy Evolution Pipeline](#7-strategy-evolution-pipeline)
8. [Database Layer](#8-database-layer)
9. [Monitoring & Alerts](#9-monitoring--alerts)
10. [Memory System](#10-memory-system)
11. [Dashboard & API](#11-dashboard--api)
12. [Configuration Reference](#12-configuration-reference)
13. [CLI Reference](#13-cli-reference)
14. [Testing](#14-testing)
15. [Deployment](#15-deployment)
16. [Design Decisions](#16-design-decisions)

---

## 1. System Overview

Agent Brain is an **autonomous, self-improving multi-agent research system**. It does not update model weights — instead, it evolves its behavior through **natural language strategy documents** that are empirically scored and rewritten based on performance data.

### What It Does

1. **Researches** topics using web search + LLM synthesis
2. **Evaluates** its own output quality on a 5-dimension rubric
3. **Stores** scored outputs in structured memory
4. **Evolves** its research strategies based on score patterns
5. **Transfers** learned principles across knowledge domains
6. **Monitors** its own health and generates alerts on degradation

### What It Is NOT

- Not a chatbot or personal assistant
- Not a wrapper around an LLM API
- Not a RAG system (it generates knowledge, not just retrieves it)
- Not dependent on any framework (pure Python + Claude API)

### Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| LLM | Claude API (Anthropic) — Haiku for cheap tasks, Sonnet for quality-critical |
| Search | DuckDuckGo (free, no API key needed) |
| Database | SQLite (WAL mode) + JSON files (backward compat) |
| Dashboard Backend | FastAPI + uvicorn (port 8000) |
| Dashboard Frontend | Next.js 16 + TypeScript + Tailwind CSS (port 3000) |
| Testing | pytest (229 tests) |

---

## 2. Architecture Layers

The system is built in 5 layers, each earning the right to exist by proving the previous layer works.

### Layer 1: Knowledge Accumulation
**Module:** `memory_store.py`

Every research output is stored as a scored JSON file with full provenance: question, findings, critique scores, strategy version, timestamp. This is the raw material for everything above.

### Layer 2: Evaluated Knowledge  
**Modules:** `agents/critic.py`, quality gate in `main.py`

The Critic agent scores every output on 5 dimensions (accuracy, depth, completeness, specificity, intellectual honesty). Outputs below threshold 6/10 are rejected and retried with feedback. The Critic uses an **adaptive rubric** that adjusts dimension weights per domain based on historical patterns.

### Layer 3: Behavioral Adaptation
**Module:** `agents/meta_analyst.py`

The Meta-Analyst examines scored outputs every N runs, identifies patterns (what works, what doesn't), and rewrites the researcher's strategy document. It maintains an **evolution log** tracking every change, its reasoning, and the score trajectory that motivated it.

### Layer 4: Strategy Evolution
**Module:** `strategy_store.py`

Strategies are versioned documents with a lifecycle: `pending → trial → active` or `rolled_back`. New strategies require human approval before entering trial. Trial evaluation uses **Welch's t-test** (minimum 5 outputs, p ≤ 0.10) to determine statistical significance. Safety guard: strategies scoring >20% below current best trigger automatic rollback.

### Layer 5: Cross-Domain Transfer
**Module:** `agents/cross_domain.py`

General principles are extracted from high-performing strategies across domains, abstracted into domain-agnostic insights, and applied as seed strategies in new domains. Transfer effectiveness is tracked via **lift measurement** (score improvement vs. baseline).

---

## 3. Module Reference

### Core Modules (10)

| Module | Lines | Purpose |
|--------|-------|---------|
| `main.py` | 1,918 | CLI entry point, research loop, command dispatch |
| `config.py` | 87 | All configuration: models, thresholds, paths, budget |
| `memory_store.py` | 562 | Scored output storage, TF-IDF retrieval, memory hygiene |
| `strategy_store.py` | 556 | Versioned strategies, trial evaluation, rollback |
| `cost_tracker.py` | 148 | API cost logging, budget enforcement |
| `analytics.py` | 815 | Score trends, strategy comparison, cost efficiency |
| `db.py` | 645 | SQLite database layer (outputs, costs, alerts, runs) |
| `monitoring.py` | 327 | Health checks, trend detection, automated alerts |
| `validator.py` | 505 | Data integrity checks across all stores |
| `knowledge_graph.py` | 550 | Typed-edge knowledge graph from synthesized claims |

### Agent Modules (9)

| Module | Lines | Model | Purpose |
|--------|-------|-------|---------|
| `agents/researcher.py` | 243 | Haiku | Web search + structured findings |
| `agents/critic.py` | 287 | Sonnet | Score on 5 dimensions, adaptive rubric |
| `agents/meta_analyst.py` | 347 | Sonnet | Pattern extraction, strategy rewriting |
| `agents/synthesizer.py` | 439 | Sonnet | Knowledge base integration, incremental merge |
| `agents/cross_domain.py` | 631 | Sonnet | Principle extraction, domain seeding, transfer tracking |
| `agents/verifier.py` | 337 | Haiku | Prediction extraction + web verification |
| `agents/question_generator.py` | 246 | Haiku | Knowledge gap analysis → next questions |
| `agents/consensus.py` | 273 | Haiku ×N | Multi-researcher parallel findings |
| `agents/orchestrator.py` | 538 | Sonnet | LLM-powered domain prioritization |

### Infrastructure

| Module | Lines | Purpose |
|--------|-------|---------|
| `scheduler.py` | 716 | Research plans, daemon mode, time-based scheduling |
| `domain_seeder.py` | ~200 | Curated seed questions per domain |
| `dashboard/api.py` | 749 | FastAPI REST API + SSE streaming |
| `utils/retry.py` | 149 | Exponential backoff for API calls |
| `utils/json_parser.py` | ~80 | Robust JSON extraction from LLM output |
| `tools/web_search.py` | ~100 | DuckDuckGo search wrapper |

### Test Suites (4)

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_core.py` | 146 | Memory, strategy, cost, analytics, validator, CLI |
| `tests/test_new_features.py` | 53 | Consensus, knowledge graph, orchestrator, scheduler |
| `tests/test_improvements.py` | 50 | TF-IDF, adaptive rubric, t-test, synthesis, verifier |
| `tests/test_hardening.py` | 33 | SQLite, caching, error recovery, monitoring, integration |

**Total: 229 tests, all passing.**

---

## 4. Data Flow

### Research Loop (Single Run)

```
User Question
    │
    ▼
[Budget Check] ──── Over limit? → BLOCKED
    │
    ▼
[Load Strategy] ──── Domain-specific strategy document
    │
    ▼
[Researcher Agent] ──── Web search → LLM synthesis → Structured findings
    │                    (with memory context from TF-IDF retrieval)
    ▼
[Critic Agent] ──── Score on 5 dimensions (adaptive rubric)
    │
    ▼
[Quality Gate] ──── Score ≥ 6? 
    │                YES → Accept     NO → Retry with feedback (max 2)
    ▼
[Memory Store] ──── Save to JSON + SQLite (dual-write)
    │
    ▼
[Trial Evaluation] ──── If trial strategy active: t-test check
    │
    ▼
[Auto-Synthesize] ──── Every 5 accepted outputs: merge into knowledge base
    │
    ▼
[Auto-Graph] ──── Build knowledge graph from claims
    │
    ▼
[Meta-Analysis] ──── Every 3 outputs: analyze patterns → evolve strategy
```

### Strategy Evolution Cycle

```
Scored Outputs (3+ new)
    │
    ▼
[Meta-Analyst] ──── Read scores, weaknesses, strengths
    │                Read evolution log (what changed before, what worked)
    │                Read adaptive rubric weights
    ▼
[New Strategy] ──── Natural language document → saved as "pending"
    │
    ▼
[Human Approval] ──── --approve v004 → enters trial
    │
    ▼
[Trial Period] ──── 5 outputs under new strategy
    │
    ▼
[Statistical Test] ──── Welch's t-test: is new strategy better?
    │                     p ≤ 0.10 and mean higher → CONFIRM
    │                     p ≤ 0.10 and mean lower → ROLLBACK
    │                     p > 0.10 → EXTEND trial (up to 3×)
    ▼
[Active/Rollback] ──── Strategy becomes active or rolled back
```

### Cross-Domain Transfer

```
Domain A (mature, avg score 7.5+)
    │
    ▼
[Principle Extraction] ──── What made strategies work? Abstract into general truths.
    │                        Store in strategies/_principles.json
    ▼
Domain B (new, no data)
    │
    ▼
[Seed Strategy] ──── Apply general principles → domain-specific initial strategy
    │                 Track transfer in _transfer_log.json
    ▼
[Lift Measurement] ──── Compare Domain B scores with/without transferred principles
```

---

## 5. Agent Roles

### Researcher (Haiku — cheap + fast)
- **Input:** Question, strategy document, previous critique feedback, memory context
- **Process:** Up to 10 web searches via DuckDuckGo, synthesizes into structured findings
- **Output:** `{summary, findings: [{claim, confidence, source}], key_insights, knowledge_gaps}`
- **Error handling:** Wrapped in retry with exponential backoff; crash triggers retry with error context

### Critic (Sonnet — quality is sacred)
- **Input:** Research output, domain-specific adaptive rubric
- **Scoring dimensions:**
  - **Accuracy** (default 30%) — Factual correctness
  - **Depth** (default 20%) — Beyond surface-level analysis
  - **Completeness** (default 20%) — Important angles covered
  - **Specificity** (default 15%) — Concrete data, numbers, sources
  - **Intellectual Honesty** (default 15%) — Flags uncertainty, fact vs. speculation
- **Output:** `{overall_score, verdict, scores: {}, strengths, weaknesses, actionable_feedback}`
- **Adaptive rubric:** Weights adjust per domain via `_rubric.json`. Domains with historically low accuracy get boosted accuracy weight.

### Meta-Analyst (Sonnet — needs reasoning)
- **Trigger:** Every `EVOLVE_EVERY_N` (3) new outputs, only when no trial is active
- **Input:** Recent scored outputs (up to 20), current strategy, evolution log
- **Process:** Identifies patterns in scores → writes improved strategy
- **Output:** New strategy document saved as "pending"
- **Safety:** Skipped during active trials; skipped when pending strategies await approval

### Synthesizer (Sonnet — contradiction detection)
- **Trigger:** Every `SYNTHESIZE_EVERY_N` (5) accepted outputs
- **Modes:**
  - **Full synthesis:** Builds complete knowledge base from all outputs
  - **Incremental merge:** For ≤10 new outputs, merges into existing KB
- **Output:** `{domain, claims: [{claim, confidence, status, sources, topics}], contradictions, knowledge_gaps, summary}`

### Verifier (Haiku — cheap fact-checking)
- **Process:** Extracts predictions from past outputs → searches web for evidence → updates prediction status
- **Output:** `{predictions: [{prediction, extracted_from, verification_status, evidence}]}`

### Question Generator (Haiku — synthesis task)
- **Input:** Domain knowledge gaps, critic weaknesses, coverage patterns
- **Output:** Ranked list of next research questions

### Orchestrator (Sonnet — strategic reasoning)
- **Input:** All domain stats, budget remaining, system health
- **Output:** Prioritized domain allocation for multi-round auto mode

---

## 6. Scoring & Quality Gate

### Score Computation
The Critic produces a weighted overall score:

```
overall = Σ (dimension_weight × dimension_score) / Σ dimension_weight
```

Default weights: `{accuracy: 0.30, depth: 0.20, completeness: 0.20, specificity: 0.15, intellectual_honesty: 0.15}`

Adaptive rubric adjusts these per domain based on historical performance patterns.

### Quality Gate Logic
```python
if score >= QUALITY_THRESHOLD (6):  # ACCEPT
    store output, continue to meta-analysis
elif attempt <= MAX_RETRIES (2):     # RETRY
    feed critique back to researcher with enhanced guidance
    # Smart recovery for search failures:
    #   - Zero findings → broader search advice
    #   - Empty searches → simpler query advice  
else:                                 # MAX RETRIES REACHED
    store output anyway (for learning), mark as rejected
```

### Score Trajectory
The system tracks score improvement over time:
- **Rolling average** (window=3) smooths noise
- **Trend detection:** first third avg vs. last third avg
  - Improvement > 0.5 → "improving"
  - Drop > 0.5 → "declining" (triggers monitoring alert)
  - Otherwise → "stable"

---

## 7. Strategy Evolution Pipeline

### Strategy Lifecycle

```
[Created by Meta-Analyst]
        │
        ▼
    PENDING ──── Requires human --approve
        │
        ▼
     TRIAL ──── 5 outputs evaluated with t-test
        │
    ┌───┴───┐
    ▼       ▼
 ACTIVE   ROLLED_BACK
```

### Trial Evaluation (Welch's T-Test)

```python
# Collect scores under trial strategy vs. previous active
trial_scores = [outputs under trial version]
baseline_scores = [outputs under previous version]

# Welch's t-test (unequal variances)
t_stat, p_value = ttest_ind(trial_scores, baseline_scores, equal_var=False)

if p_value <= 0.10:  # Statistically significant
    if mean(trial) > mean(baseline):
        CONFIRM → promote to active
    else:
        ROLLBACK → revert to previous
elif extensions < TRIAL_EXTEND_LIMIT (3):
    EXTEND → collect more data
else:
    CONFIRM → not enough evidence to reject, keep trial
```

### Safety Guards
- **20% drop threshold:** If new strategy mean is >20% below current best, auto-rollback
- **Human approval gate:** All new strategies start as "pending" — must be explicitly approved
- **Cooldown:** Meta-analysis only runs every 3 outputs (saves API credits)
- **Trial lock:** No strategy evolution during active trial (prevents interference)

---

## 8. Database Layer

### Architecture
**Module:** `db.py` — SQLite with WAL journal mode for concurrent reads.

The system uses **dual-write**: all data is written to both JSON files (backward compatibility) and SQLite (fast queries). Reads still use JSON files for most operations; SQLite is used for:
- Alert storage and querying
- Health snapshots
- Aggregated analytics queries
- Cost trend analysis

### Schema (v1)

```sql
-- Research outputs
CREATE TABLE outputs (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL,
    question TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    attempt INTEGER DEFAULT 1,
    strategy_version TEXT DEFAULT 'default',
    overall_score REAL DEFAULT 0,
    accepted INTEGER DEFAULT 0,
    verdict TEXT DEFAULT 'unknown',
    research_json TEXT,
    critique_json TEXT,
    full_record_json TEXT NOT NULL
);

-- Cost tracking
CREATE TABLE costs (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    domain TEXT DEFAULT '',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0
);

-- Monitoring alerts
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    domain TEXT DEFAULT '',
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    message TEXT NOT NULL,
    details_json TEXT,
    acknowledged INTEGER DEFAULT 0,
    acknowledged_at TEXT
);

-- Health snapshots
CREATE TABLE health_snapshots (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'healthy',
    details_json TEXT NOT NULL
);

-- Run log
CREATE TABLE run_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    domain TEXT NOT NULL,
    question TEXT NOT NULL,
    attempts INTEGER DEFAULT 1,
    score REAL DEFAULT 0,
    verdict TEXT DEFAULT 'unknown',
    strategy_version TEXT DEFAULT 'default',
    consensus INTEGER DEFAULT 0,
    consensus_level TEXT,
    researchers_used INTEGER
);
```

### Migration
Existing JSON/JSONL data can be imported into SQLite:
```bash
python main.py --migrate
```
Migration is idempotent — duplicate records (matched by timestamp) are skipped.

---

## 9. Monitoring & Alerts

### Module: `monitoring.py`

Six automated health checks run on demand via `--check-health` or the `/api/health/deep` endpoint:

| Check | Trigger | Severity |
|-------|---------|----------|
| **Declining Scores** | Rolling avg drops >0.5 | warning |
| **Sudden Drop** | Latest score >2.0 below rolling avg | critical |
| **Budget Warning** | Daily spend >80% of limit | warning/critical |
| **Stale Domain** | No outputs in 14+ days | info |
| **High Rejection** | >50% rejected in last 10 outputs | warning |
| **Error Rate Spike** | >5 errors in 24 hours | critical |

### Alert Lifecycle
```
Generated → Unacknowledged → Acknowledged
```

Alerts are stored in SQLite and queryable via:
- CLI: `python main.py --alerts`
- API: `GET /api/alerts`
- API: `POST /api/alerts/{id}/acknowledge`

### Error Recovery
The research loop (`run_loop`) is wrapped in structured error handling:
- **Researcher crash:** Retries with error context as feedback
- **Critic crash:** Uses minimal fallback critique (score 3, reject)
- **Loop crash:** Catches all exceptions, logs to `errors.jsonl`, generates DB alert, returns error dict
- **Keyboard interrupt:** Propagated cleanly
- **Budget block:** `sys.exit(1)` propagated

---

## 10. Memory System

### Storage Structure
```
memory/
├── crypto/
│   ├── 20250223_120000_000001_1_score8.json   ← individual outputs
│   ├── _knowledge_base.json                    ← synthesized knowledge
│   ├── _predictions.json                       ← verifier predictions
│   ├── _rubric.json                            ← adaptive critic weights
│   ├── _cache/
│   │   └── tfidf_cache.pkl                     ← persistent TF-IDF cache
│   └── _archive/                               ← pruned/rejected outputs
├── ai/
│   └── ...
└── ...
```

### TF-IDF Retrieval (Persistent Cache)
When the researcher starts, it queries memory for relevant past findings:

1. **Load accepted outputs** for the domain (score ≥ 4.0)
2. **Compute fingerprint** (MD5 of output count + timestamps)
3. **Check in-memory cache** → hit? Use cached vectorizer
4. **Check disk cache** (`_cache/tfidf_cache.pkl`) → hit? Load vectorizer
5. **Miss?** Build TF-IDF matrix from scratch, save to both caches
6. **Query:** Transform question → cosine similarity against corpus
7. **Score:** 55% semantic + 30% quality + 15% recency
8. **Return** top 5 most relevant past findings

Cache invalidation: automatically cleared when `save_output()` adds new data.

### Memory Hygiene
```bash
python main.py --prune --domain crypto    # Archive rejected/low-score outputs
python main.py --prune-dry --domain crypto # Preview without acting
```

Rules:
1. Archive rejected outputs older than 7 days
2. Archive outputs with score < 5 after 7 days
3. If domain exceeds 100 outputs, archive lowest-scored

---

## 11. Dashboard & API

### Backend: FastAPI (`dashboard/api.py`)

**Base URL:** `http://localhost:8000`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API status |
| `/api/health` | GET | Basic system health |
| `/api/health/deep` | GET | Full monitoring check with alert generation |
| `/api/overview` | GET | Complete analytics report |
| `/api/budget` | GET | Budget and cost data |
| `/api/domains` | GET | List all domains |
| `/api/domains/{domain}` | GET | Domain detail (outputs, stats, strategy) |
| `/api/domains/{domain}/outputs` | GET | Paginated outputs |
| `/api/domains/{domain}/trajectory` | GET | Score trajectory |
| `/api/domains/{domain}/graph` | GET | Knowledge graph |
| `/api/strategies/{domain}` | GET | Strategy versions and status |
| `/api/strategies/{domain}/approve/{version}` | POST | Approve pending strategy |
| `/api/strategies/{domain}/reject/{version}` | POST | Reject pending strategy |
| `/api/strategies/{domain}/rollback` | POST | Rollback to previous |
| `/api/alerts` | GET | Query alerts (filter by severity, acknowledged) |
| `/api/alerts/{id}/acknowledge` | POST | Acknowledge alert |
| `/api/db/stats` | GET | Database statistics |
| `/api/events` | GET | SSE stream (real-time loop events) |
| `/api/validate` | GET | Data integrity validation |

### Frontend: Next.js

**Pages:**
| Route | Description |
|-------|-------------|
| `/` | Overview dashboard — all domains, score chart, budget |
| `/live` | Live Loop — SSE-connected real-time research monitoring |
| `/domains/[domain]` | Domain detail — outputs, strategy, graph |
| `/scheduler` | Scheduler — plans, recommendations, daemon control |

### SSE Event Types
The `/api/events` endpoint streams real-time events:
- `research_start` — New research question starting
- `research_complete` — Research finished with score
- `critique_result` — Critic evaluation result
- `strategy_evolved` — New strategy generated
- `trial_result` — Trial evaluation outcome
- `error` — Error occurred

---

## 12. Configuration Reference

**File:** `config.py`

### Models
```python
MODELS = {
    "researcher": "claude-haiku-4-5-20251001",     # cheap — searches + compiles
    "critic": "claude-sonnet-4-20250514",           # strong — quality is sacred
    "meta_analyst": "claude-sonnet-4-20250514",     # strong — pattern extraction
    "synthesizer": "claude-sonnet-4-20250514",      # strong — contradiction detection
    "cross_domain": "claude-sonnet-4-20250514",     # strong — principle abstraction
    "question_generator": "claude-haiku-4-5-20251001", # cheap — synthesis task
    "verifier": "claude-haiku-4-5-20251001",        # cheap — web search + fact checking
}
```

### Thresholds
| Setting | Value | Description |
|---------|-------|-------------|
| `QUALITY_THRESHOLD` | 6 | Minimum score to accept output |
| `MAX_RETRIES` | 2 | Retry attempts after rejection |
| `DAILY_BUDGET_USD` | 5.00 | Hard budget cap per day |
| `MAX_SEARCHES` | 10 | Max web searches per research run |
| `TRIAL_PERIOD` | 5 | Outputs before trial evaluation |
| `TRIAL_EXTEND_LIMIT` | 3 | Max trial extensions |
| `TRIAL_P_VALUE_THRESHOLD` | 0.10 | T-test significance level |
| `SAFETY_DROP_THRESHOLD` | 0.20 | Max allowed score drop for strategies |
| `EVOLVE_EVERY_N` | 3 | Meta-analysis frequency |
| `SYNTHESIZE_EVERY_N` | 5 | Auto-synthesis frequency |
| `MAX_OUTPUTS_PER_DOMAIN` | 100 | Archive threshold |
| `CONSENSUS_RESEARCHERS` | 3 | Parallel researchers in consensus mode |

### Paths
```python
MEMORY_DIR = agent-brain/memory/
STRATEGY_DIR = agent-brain/strategies/
LOG_DIR = agent-brain/logs/
DB_PATH = agent-brain/logs/agent_brain.db
```

---

## 13. CLI Reference

### Research
```bash
# Single question
python main.py "What is quantum computing?" --domain physics

# Self-directed mode (generates its own question)
python main.py --auto --domain crypto

# Multi-round self-directed
python main.py --auto --rounds 5 --domain ai

# Multi-domain orchestrated
python main.py --orchestrate --rounds 10

# LLM-powered smart orchestration
python main.py --smart-orchestrate --rounds 5

# Consensus mode (multiple researchers)
python main.py "question" --consensus --domain crypto
```

### Strategy Management
```bash
python main.py --status --domain crypto         # Strategy status
python main.py --approve v004 --domain crypto   # Approve pending strategy
python main.py --reject v004 --domain crypto    # Reject pending strategy
python main.py --rollback --domain crypto       # Rollback to previous
python main.py --diff v001 v003 --domain crypto # Compare versions
python main.py --evolve --domain crypto         # Force evolution
```

### Knowledge
```bash
python main.py --synthesize --domain crypto     # Force synthesis
python main.py --kb --domain crypto             # Show knowledge base
python main.py --graph --domain crypto          # Show knowledge graph
python main.py --search "Bitcoin ETF"           # Search all memory
python main.py --next --domain crypto           # Next research questions
```

### Cross-Domain
```bash
python main.py --principles                     # Show general principles
python main.py --principles --extract           # Force re-extraction
python main.py --transfer ai --hint "What is AGI?"  # Seed new domain
```

### System Operations
```bash
python main.py --budget                         # Budget status
python main.py --dashboard                      # Full system dashboard
python main.py --analytics --domain crypto      # Deep analytics
python main.py --validate                       # Data integrity check
python main.py --prune --domain crypto          # Archive old outputs
python main.py --export                         # Export as JSON
python main.py --export-md                      # Export as Markdown
```

### Hardened Operations
```bash
python main.py --migrate                        # JSON → SQLite migration
python main.py --alerts                         # Show monitoring alerts
python main.py --check-health                   # Run full health check
```

### Scheduler
```bash
python main.py --plan                           # Show research plan
python main.py --run-plan                       # Execute research plan
python main.py --recommend                      # Get recommendations
python main.py --daemon --interval 60           # Start daemon (60min cycles)
python main.py --daemon-stop                    # Stop daemon
python main.py --daemon-status                  # Check daemon status
python main.py --seed --domain crypto           # Show seed questions
```

---

## 14. Testing

### Running Tests
```bash
# Full suite (229 tests)
python -m pytest tests/ -v

# By category
python -m pytest tests/test_core.py -v          # 146 core tests
python -m pytest tests/test_new_features.py -v   # 53 feature tests
python -m pytest tests/test_improvements.py -v   # 50 improvement tests
python -m pytest tests/test_hardening.py -v      # 33 hardening tests

# With coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

### Test Categories

| Suite | Tests | What It Covers |
|-------|-------|----------------|
| `test_core.py` | 146 | Memory CRUD, strategy versioning, cost tracking, analytics, validator, CLI args, edge cases |
| `test_new_features.py` | 53 | Consensus research, knowledge graph, smart orchestrator, scheduler daemon |
| `test_improvements.py` | 50 | TF-IDF retrieval, adaptive rubric, evolution log, t-test trials, incremental synthesis, verifier, transfer tracking |
| `test_hardening.py` | 33 | SQLite ops (16 tests), TF-IDF cache (5), error recovery (2), monitoring (6), dual-write (1), integration (2), memory save (1) |

### Integration Tests
`test_hardening.py::TestIntegration` runs the full `run_loop()` with mocked LLM calls:
- `test_full_loop_with_mock_agents` — Single attempt, score 7.5, full pipeline
- `test_full_loop_with_retry` — First attempt rejected (4.0), retry succeeds (7.5)

Both verify outputs are saved to memory and the complete pipeline executes.

---

## 15. Deployment

### Prerequisites
```bash
# Python 3.12+
python --version

# Install dependencies
pip install anthropic ddgs python-dotenv scikit-learn scipy fastapi uvicorn

# Set API key
export ANTHROPIC_API_KEY=sk-ant-...
```

### Quick Start
```bash
# Single research question
python main.py "What are the latest developments in quantum computing?" --domain physics

# Self-directed exploration
python main.py --auto --rounds 3 --domain crypto

# Start dashboard
cd dashboard && uvicorn api:app --reload --port 8000 &
cd dashboard/frontend && npm run dev &
```

### First-Time Setup
```bash
# 1. Run your first research
python main.py "What is the current state of AI?" --domain ai

# 2. Run a few more to build data
python main.py --auto --rounds 5 --domain ai

# 3. Migrate data to SQLite for fast queries
python main.py --migrate

# 4. Check system health
python main.py --check-health

# 5. View analytics
python main.py --analytics --domain ai

# 6. Start the dashboard
cd dashboard && uvicorn api:app --port 8000
```

### Production Checklist
- [ ] Set `ANTHROPIC_API_KEY` environment variable
- [ ] Adjust `DAILY_BUDGET_USD` in config.py for your budget
- [ ] Run `--migrate` to initialize SQLite database
- [ ] Run `--validate` to check data integrity
- [ ] Run `--check-health` to verify monitoring works
- [ ] Set up periodic `--check-health` (cron or daemon mode)
- [ ] Review and approve pending strategies before they enter trial

---

## 16. Design Decisions

### Why JSON + SQLite Dual-Write?
JSON files provide human-readable, git-friendly storage. SQLite provides fast aggregation queries. Dual-write ensures backward compatibility — if the DB is lost, JSON files are the source of truth. Migration can rebuild the DB at any time.

### Why Welch's T-Test for Strategy Evaluation?
Sample sizes are small (5-15 outputs). Welch's t-test handles unequal variances and small samples better than alternatives. The p ≤ 0.10 threshold balances false positives (wrong strategy promoted) against false negatives (good strategy rejected). Extensions up to 3× allow evidence accumulation.

### Why Natural Language Strategies?
Model weights can't be updated at runtime. But system prompts can. A "strategy" is a natural language document that tells the researcher how to behave — what to focus on, what to avoid, how to search. This is the behavioral lever the system can pull.

### Why Adaptive Rubric Weights?
Different domains need different evaluation emphasis. A domain about breaking news needs high accuracy weight. A domain about fundamental research needs high depth weight. The adaptive rubric learns these differences from historical score patterns.

### Why Persistent TF-IDF Cache?
With 100+ outputs per domain, rebuilding the TF-IDF matrix on every retrieval is O(n). The fingerprint-based cache makes subsequent retrievals O(1) for the vectorizer (only the query transform runs). Invalidation is automatic on new data.

### Why Not a Vector Database?
The current scale (hundreds of outputs, not millions) doesn't justify the complexity. TF-IDF with cosine similarity works well for structured research summaries. When scale demands it, the cache layer is designed to be swapped for a proper vector store.

### Why Error Recovery Instead of Crash?
In autonomous mode (daemon, orchestrate), a single API failure shouldn't kill a multi-hour research session. The error recovery wrapper catches crashes, logs them, generates alerts, and allows the loop to continue with the next question.

---

## Appendix: Score Evolution History

| Date | Event | Score |
|------|-------|-------|
| Session 1 | First research outputs | 5.4 avg |
| Session 2 | Quality gate active | 7.1 avg |
| Session 3 | Strategy evolution (Layer 3) | 7.7 avg |
| Session 4 | Cross-domain transfer (Layer 5) | 8.0 avg |
| Current | Hardened + monitored | Tracked per domain |

---

## 17. Agent Hands (Execution Layer)

> **Added:** February 2026  
> **Purpose:** Code generation and execution capabilities

### Overview

Agent Hands is the execution layer — it turns KB knowledge into working code:

```
KB Claims → Task Generator → Planner → Executor → Artifacts
```

### Components

| Component | Model | Purpose |
|-----------|-------|---------|
| **Task Generator** | Haiku 4.5 | Generate coding tasks from KB claims |
| **Planner** | Sonnet 4 | Goal → step-by-step plan |
| **Executor** | Haiku 4.5 | Plan → tool calls → artifacts |
| **Validator** | Sonnet 4 | Score execution quality |

### Execution Tools

| Tool | Operations |
|------|------------|
| `code` | write, read, edit, append, delete, list_dir |
| `terminal` | npm, pip, pytest, git, curl, docker (whitelisted) |
| `git` | init, commit, push, branch, merge |
| `http` | GET/POST for API testing |
| `search` | find files/code in workspace |

### Execution Templates

Domain-specific execution guidance:

- `nextjs-react`: create-next-app, TypeScript, App Router
- `python`: venv, pytest, type hints, PEP 8
- `saas-building`: REST API, auth, database patterns
- `productized-services`: risk calculators, comparison tools (KB-aware)
- `cli-tools`: argparse, Unix conventions, JSON output
- `web-dashboard`: Next.js 14, server components, Tailwind

### CLI Commands

```bash
python main.py --next-task --domain D         # Generate coding tasks
python main.py --auto-build --domain D        # Brain→Hands pipeline
python main.py --execute --goal "..."         # Direct execution
python main.py --exec-status --domain D       # Execution history
```

---

## 18. Tool Integrations

> **Added:** February 2026  
> **Purpose:** Enhanced web scraping, credential management, semantic search

### Stealth Browser

Playwright-based browser with anti-detection:

- Human-like timing (typing, clicking, scrolling)
- Fingerprint randomization (viewport, user-agent, locale)
- Session persistence (cookies, localStorage)
- Auto-auth via vault credentials

**Browser-Required Domains** (auto-detected):
```
reddit, linkedin, twitter/x, medium, bloomberg, ft, wsj, nytimes,
indeed, glassdoor, angel.co, wellfound, notion, airtable, figma,
stackoverflow, amazon, shopify
```

### Credential Vault

Encrypted credential storage (Fernet encryption):

- Passphrase-protected (`VAULT_PASSPHRASE` env var)
- Key format: `domain_com` (dots → underscores)
- Auto-retrieved for browser auth

```bash
# Store credential
python main.py --vault-store linkedin_com '{"email":"x","password":"y"}'

# Browser automatically uses vault
python main.py --browser-fetch 'https://linkedin.com/in/someone'
```

### RAG Vector Store

ChromaDB + sentence-transformers for semantic search:

- Model: `all-MiniLM-L6-v2` (384 dimensions, local, free)
- Claims indexed per domain
- Cross-domain semantic search
- Currently: ~1,900+ claims indexed

```bash
python main.py --rag-search "landing page pricing"
python main.py --rag-status
```

### Crawl-to-KB Pipeline

Web scraping → claim extraction → KB injection:

```bash
# Crawl documentation site
python main.py --crawl 'https://docs.example.com' --domain D --crawl-max 10

# Inject extracted claims to KB
python main.py --crawl-inject --domain D
```

Flow:
```
URL → Scrapling (HTTP) or Browser (JS sites) → Pages → 
Extract Claims (heuristics) → KB → RAG Index
```

---

## 19. Cortex System Naming

> **Established:** February 2026

**Cortex** is the name for the complete system:

| Component | Purpose |
|-----------|---------|
| **Brain** | Research, scoring, strategy evolution |
| **Hands** | Planning, execution, code generation |
| **Tools** | Browser, vault, RAG, crawl |

A **cycle** is one complete research or execution run.

---

*Document updated February 2026. Total codebase: ~20,000 lines Python across 40+ modules.*
