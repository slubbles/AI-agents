# Agent Brain

An autonomous, self-improving multi-agent research system that **changes its own behavior over time** based on empirical performance scoring — not by updating model weights, but through **prompt/strategy evolution driven by structured feedback loops**.

This is not a chatbot. Not a wrapper around an LLM. Not a personal assistant. It is an autonomous research system that loops, scores its own output, and rewrites its own operating instructions based on what works.

## How It Works

```
Question → Researcher (web search) → Critic (scores 1-10) → Quality Gate
                                                                  ↓
                                                            Score ≥ 6? → Accept → Memory
                                                            Score < 6? → Retry with feedback (up to 2x)
                                                                  ↓
                                                      Every 3 outputs → Meta-Analyst rewrites strategy
                                                                  ↓
                                                      Strategy trial → Evaluate → Confirm or rollback
```

The system learns through 5 layers:

1. **Knowledge Accumulation** — agent acts, output stored with full provenance
2. **Evaluated Knowledge** — critic scores on 5 dimensions (accuracy, depth, completeness, specificity, intellectual honesty)
3. **Behavioral Adaptation** — meta-analyst extracts patterns from scores, rewrites agent strategy documents
4. **Strategy Evolution** — strategies version-controlled with trial periods, safety rollbacks, human approval gates
5. **Cross-Domain Transfer** — insights from proven domains abstracted into general principles, applied as seeds in new domains

## Architecture

```
agent-brain/
├── config.py              — central configuration (models, thresholds, budget)
├── main.py                — loop runner + CLI (19 commands)
├── memory_store.py         — scored outputs, relevance retrieval, pruning
├── strategy_store.py       — versioned strategies with trial/active/rollback
├── cost_tracker.py         — API cost tracking + daily budget enforcement
├── agents/
│   ├── researcher.py      — web search + structured findings (Claude Haiku)
│   ├── critic.py          — 5-dimension scoring, accepts/rejects (Claude Sonnet)
│   ├── meta_analyst.py    — pattern extraction → strategy rewriting (Claude Sonnet)
│   ├── synthesizer.py     — knowledge base integration + claim tracking
│   ├── cross_domain.py    — principle extraction + domain seeding
│   └── question_generator.py — self-directed learning: gap diagnosis → question generation
├── tools/
│   └── web_search.py      — DuckDuckGo search (free, no API key)
├── tests/
│   └── test_core.py       — 42 unit tests (config, memory, strategy, cost, pruning)
├── memory/                — scored outputs (JSON, per domain)
├── strategies/            — strategy versions (JSON, per domain) + principles
└── logs/                  — run logs (JSONL) + cost logs
```

## Quick Start

```bash
# 1. Clone
git clone https://github.com/slubbles/AI-agents.git
cd AI-agents/agent-brain

# 2. Set up
pip install anthropic python-dotenv duckduckgo-search
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Run a research question
python main.py --domain crypto "What are the latest Bitcoin ETF developments?"

# 4. Self-directed mode (system picks its own questions)
python main.py --domain crypto --auto --rounds 3

# 5. See everything at a glance
python main.py --dashboard
```

## CLI Commands

### Research
```bash
python main.py "Your question here"                    # Research a question
python main.py --domain crypto "Bitcoin ETFs?"         # Research in a specific domain
python main.py --auto                                  # Self-directed: system picks the question
python main.py --auto --rounds 5                       # Run 5 self-directed rounds
```

### Strategy Management
```bash
python main.py --status                                # Strategy status + version performance
python main.py --approve v004                          # Approve a pending strategy for trial
python main.py --reject v004                           # Reject a pending strategy
python main.py --diff v001 v003                        # Compare two strategy versions
python main.py --rollback                              # Roll back to previous strategy
python main.py --evolve                                # Force strategy evolution now
```

### Knowledge & Memory
```bash
python main.py --kb                                    # Show synthesized knowledge base
python main.py --synthesize                            # Force knowledge synthesis
python main.py --prune                                 # Archive rejected/low-score outputs
python main.py --prune-dry                             # Preview what --prune would archive
python main.py --next                                  # Show self-generated next questions
```

### Cross-Domain & System
```bash
python main.py --principles                            # Show general principles
python main.py --principles --extract                  # Re-extract principles from all domains
python main.py --transfer ai --hint "AI safety"        # Seed a new domain
python main.py --budget                                # Cost tracking / budget status
python main.py --audit                                 # Full audit trail
python main.py --dashboard                             # Full system dashboard
```

## Scoring Rubric

The Critic scores every research output on 5 dimensions (weighted):

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Accuracy | 30% | Factual correctness |
| Depth | 20% | Beyond surface-level analysis |
| Completeness | 20% | Important angles covered |
| Specificity | 15% | Concrete data, numbers, sources |
| Intellectual Honesty | 15% | Flags uncertainty, fact vs speculation |

**Threshold: score ≥ 6/10 to accept.** Below 6 → retry with critique feedback (max 2 retries).

## Safety & Control

- **Human approval gate**: new strategies saved as "pending" — must be approved before trial
- **Trial period**: strategies run for 3 outputs before confirming or rolling back
- **Safety rollback**: auto-rolls back if trial strategy scores >20% below previous best
- **Budget enforcement**: daily spend limit ($2/day default), hard-stops when exceeded
- **Full observability**: every output scored, every strategy versioned, every run logged

## Stack

- **Python 3.12+** — ~3,800 lines across 13 modules
- **Claude API** (Anthropic) — Haiku for cheap research, Sonnet for quality-critical scoring
- **DuckDuckGo Search** — free web search, no API key needed
- **Local JSON storage** — memory, strategies, logs all in versioned JSON files

## Design Principles

1. **Observability is non-negotiable.** The system never acts without a human able to see what it's doing and why.
2. **Start smaller than feels right.** One agent, one loop, one domain — finish before expanding.
3. **The Critic is sacred.** It's both the cost control and the self-improvement signal.
4. **Memory hygiene matters.** Score-weighted retrieval. Prune rejected outputs. Summarize old findings.
5. **Strategy evolution is the novel piece.** Strategies as natural language documents that the system reads, reasons about, and rewrites based on performance data.

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

42 unit tests covering config validation, memory save/load/retrieve/prune, cost tracking, strategy versioning/approval/rollback, and CLI integration.

## Current Performance

Score trajectory over strategy evolution: **5.4 → 7.1 → 7.7 → 8.0**

5 active domains: crypto (14 outputs), cybersecurity (4), geopolitics (2), AI (1), physics (1). 9 cross-domain principles extracted. 73% acceptance rate overall.