# Agent Brain — Session Progress

## Date: February 23, 2026

---

## What Got Built Today

From zero files to a fully working autonomous research loop in one session.

### System Architecture (5 Layers)

| Layer | Name | Status |
|-------|------|--------|
| 1 | Knowledge Accumulation | ✅ DONE — researcher agent + memory store |
| 2 | Evaluated Knowledge | ✅ DONE — critic agent + scoring + quality gate |
| 3 | Behavioral Adaptation | ❌ NOT STARTED — meta-analyst + strategy evolution |
| 4 | Strategy Evolution | ❌ NOT STARTED — autonomous recursive rewriting |
| 5 | Cross-Domain Transfer | ❌ NOT STARTED — cross-domain abstraction |

### Files Created

```
agent-brain/
├── config.py              — model assignments, thresholds, dotenv loading
├── main.py                — loop runner: research → critique → quality gate → store
├── memory_store.py        — scored outputs → JSON files per domain
├── strategy_store.py      — versioned strategy docs (ready for Layer 3)
├── requirements.txt       — anthropic, ddgs, python-dotenv
├── agents/
│   ├── __init__.py
│   ├── researcher.py      — Claude tool_use + web search + JSON extraction
│   └── critic.py          — 5-dimension scoring rubric
├── tools/
│   ├── __init__.py
│   └── web_search.py      — DuckDuckGo search via ddgs package
├── memory/
│   └── crypto/            — stored outputs (1 file so far)
├── strategies/            — empty (Layer 3 will populate this)
└── logs/
    └── crypto.jsonl       — run logs
```

Also created:
- `.github/copilot-instructions.md` — comprehensive system prompt for session continuity
- `.env` — Anthropic API key (git-ignored)
- `.gitignore` — protects .env

---

## First Successful End-to-End Run

**Query:** "What are the latest Bitcoin ETF developments?"  
**Domain:** crypto  
**Result:** Exit code 0 — full loop completed

### What happened:

1. **Attempt 1** — Researcher searched 3 times, produced 6 findings. Critic scored **5.2/10** (rejected). Issues: included a future-dated claim (Feb 2026), lacked depth on regulatory mechanisms, stopped at 2024 events.

2. **Attempt 2** — Researcher adapted to critique, searched 6 times, produced 10 findings. Critic scored **5.0/10** (rejected). Issues: more comprehensive but systematically included future-dated data as fact, poor intellectual honesty on temporal claims.

3. **Attempt 3** — Researcher searched 4 times, produced 8 findings. Critic scored **5.4/10** (rejected). Better intellectual honesty (8/10) with explicit disclaimers, but still had temporal inconsistencies. Stored anyway (max retries reached).

### Key Observation

The **critic is working exactly as designed**. It correctly identified that the researcher was citing 2025-2026 data that can't be verified, and it penalized accuracy while rewarding the researcher's improving intellectual honesty across attempts. The quality gate forced 3 iterations, each one showing adaptation to the previous critique feedback. This is the core feedback loop that Layer 3 will automate.

---

## Issues Encountered & Resolved

| Problem | Solution |
|---------|----------|
| Researcher had no web search | Added DuckDuckGo via `ddgs` package + Claude tool_use API |
| Package renamed (`duckduckgo-search` → `ddgs`) | Updated import and requirements.txt |
| JSON parsing failures (model preamble before JSON) | Built `_extract_json()` with regex, markdown fence handling, truncation repair |
| Cost concerns (all models on Sonnet) | Researcher → Haiku 4.5 (~12x cheaper), Critic stays on Sonnet |
| Model ID errors (404s) | Queried `client.models.list()` API → found correct ID `claude-haiku-4-5-20251001` |
| API key management (export every session) | Created `.env` + python-dotenv auto-loading |

---

## Models Available on Account

| Model ID | Used For |
|----------|----------|
| `claude-haiku-4-5-20251001` | Researcher (cheap, fast) |
| `claude-sonnet-4-20250514` | Critic + Meta-Analyst (quality) |
| `claude-sonnet-4-6` | Available (not assigned) |
| `claude-opus-4-6` | Available (not assigned) |
| `claude-opus-4-5-20251101` | Available (not assigned) |
| `claude-sonnet-4-5-20250929` | Available (not assigned) |
| `claude-opus-4-1-20250805` | Available (not assigned) |
| `claude-opus-4-20250514` | Available (not assigned) |
| `claude-3-haiku-20240307` | Available (legacy) |

---

## What's Next (Priority Order)

### Immediate (Next Session)

1. **Improve researcher accuracy on temporal claims.** The biggest issue: the researcher cites future-dated data as fact. Options:
   - Inject current date into researcher's system prompt so it knows what's "future"
   - Add a date-validation step before critique
   - Instruct the researcher to explicitly discard sources with future dates

2. **Get a score ≥ 6 run.** The loop works but hasn't produced an accepted output yet. Tuning the researcher prompt or adding the date awareness should fix this.

3. **Run on multiple domains.** Test with different questions (AI, finance, science) to verify the loop generalizes.

### Layer 3 — Behavioral Adaptation (The Novel Piece)

Once the loop reliably produces accepted outputs:

1. **Build the Meta-Analyst agent** — reads scored outputs from `memory/<domain>/`, extracts patterns (what scored well, what got rejected and why), produces strategy recommendations.

2. **Strategy rewriting** — Meta-Analyst writes new strategy documents to `strategies/<domain>/researcher_v2.json`. The researcher reads these instead of its default prompt.

3. **A/B testing** — run the same question with old strategy vs new strategy. Keep whichever scores higher. This is prompt evolution driven by empirical data.

4. **Safety rails** — never deploy a strategy scoring >20% below the current best without human review.

### Later

- Supabase for persistent storage (replaces JSON files)
- Web dashboard (Next.js + FastAPI) for observability
- More agent roles (Orchestrator, Synthesizer)
- Cross-domain transfer (Layer 5)

---

## Design Decisions Made

1. **No OpenClaw dependency.** Studied it, learned from patterns, building directly on Claude API. Simpler, faster, fully under our control.
2. **Critic is sacred.** It's both cost control AND the self-improvement signal. Never weaken it.
3. **JSON files over databases** — for now. Supabase comes when the loop is proven and strategies evolve.
4. **Haiku for researcher, Sonnet for critic.** Cost optimization that preserves quality where it matters.
5. **Strategy evolution is the novel piece.** Not the agents, not the memory — the strategy documents that get rewritten based on performance data.

---

## Stack

- Python 3.12+
- Anthropic SDK (Claude API with tool_use)
- ddgs (DuckDuckGo search — free, no API key)
- python-dotenv
- JSON file storage (for now)

---

*This document should be updated each session to maintain continuity.*
