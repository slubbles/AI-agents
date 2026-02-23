# Agent Brain

Self-improving autonomous research agent system that **changes its own behavior based on the outcomes of its past actions** — through prompt/strategy evolution driven by empirical performance scoring.

## Architecture

```
Question → Researcher → Critic (scores 1-10) → Quality Gate → Memory
                ↑                                      |
                └──── retry with critique if score < 6 ─┘
                
Memory → Meta-Analyst → Strategy Evolution → Better Researcher
                |
                └──→ Cross-Domain Principles → Seed New Domains
```

**5 Learning Layers:**
1. **Knowledge Accumulation** — agent acts, output stored, retrieved later
2. **Evaluated Knowledge** — critic scores output on 5 dimensions, score stored alongside
3. **Behavioral Adaptation** — meta-analyst rewrites strategies based on score patterns
4. **Strategy Evolution** — trial/active/rollback with safety guards + human approval
5. **Cross-Domain Transfer** — principles from one domain seed strategies in new domains

## Setup

```bash
cd agent-brain
pip install -r requirements.txt
cp .env.example .env  # Add ANTHROPIC_API_KEY
python main.py "your research question here"
```

## Structure

```
agent-brain/
├── config.py              — model assignments, thresholds, budget config
├── main.py                — CLI entry point (29 commands, 1536 lines)
├── memory_store.py        — scored outputs → JSON files per domain
├── strategy_store.py      — versioned strategies with pending/trial/active/rollback
├── cost_tracker.py        — API cost tracking + daily budget enforcement
├── analytics.py           — performance analytics: trends, distributions, efficiency
├── validator.py           — data integrity checks across memory/strategies/costs
├── domain_seeder.py       — seed questions for bootstrapping new domains
├── agents/
│   ├── researcher.py      — web search + structured findings (date-aware)
│   ├── critic.py          — scores on 5 dimensions, accepts/rejects
│   ├── meta_analyst.py    — analyzes scored outputs → rewrites strategies
│   ├── cross_domain.py    — extracts general principles, seeds new domains
│   ├── question_generator.py — diagnoses gaps, generates next questions
│   ├── synthesizer.py     — integrates findings into knowledge base
│   └── orchestrator.py    — multi-domain priority routing (no API calls)
├── tools/
│   └── web_search.py      — DuckDuckGo search, Claude tool_use definition
├── utils/
│   └── retry.py           — exponential backoff retry for transient API errors
├── tests/
│   └── test_core.py       — 75 unit tests (pytest)
├── memory/                — scored outputs (per domain subdirectory)
├── strategies/            — strategy versions + _principles.json
└── logs/                  — run logs (JSONL per domain) + cost logs
```

**22 Python files, ~7,600 lines of code, 75 unit tests.**

## CLI Commands

### Research
```bash
python main.py "What is the current state of AI agents?"
python main.py --domain crypto "Bitcoin ETF developments?"
python main.py --auto                        # Self-directed: generate question + research
python main.py --auto --rounds 5             # 5 self-directed rounds
python main.py --orchestrate                 # Smart multi-domain auto mode
python main.py --orchestrate --rounds 10     # 10 rounds across all domains
python main.py --orchestrate --target-domains crypto,ai
```

### Strategy Management
```bash
python main.py --status                      # Strategy versions + performance
python main.py --evolve                      # Force strategy evolution
python main.py --approve v004                # Approve pending strategy for trial
python main.py --reject v004                 # Reject pending strategy
python main.py --diff v001 v003              # Compare strategy versions
python main.py --rollback                    # Roll back to previous version
```

### Knowledge & Analysis
```bash
python main.py --kb --domain crypto          # Show synthesized knowledge base
python main.py --synthesize --domain crypto  # Force knowledge synthesis
python main.py --analytics                   # System-wide performance analytics
python main.py --analytics --domain crypto   # Domain-specific deep dive
python main.py --search "bitcoin ETF"        # Search across all memory
```

### System Management
```bash
python main.py --dashboard                   # Full system dashboard
python main.py --budget                      # Cost tracking + budget status
python main.py --validate                    # Data integrity checks
python main.py --seed                        # Show available seed domains
python main.py --seed --domain biotech       # See seed questions for a domain
python main.py --prune                       # Archive rejected/low outputs
python main.py --prune-dry                   # Preview what prune would do
python main.py --export                      # Export system report (JSON)
python main.py --export-md                   # Export system report (Markdown)
python main.py --audit                       # Full audit trail
```

### Cross-Domain
```bash
python main.py --principles                  # Show cross-domain principles
python main.py --principles --extract        # Force re-extraction
python main.py --transfer ai                 # Seed domain with principles
python main.py --next --domain crypto        # Show next auto-generated questions
```

## Agent Roles

| Agent | Model | Purpose |
|-------|-------|---------|
| Researcher | Haiku 4.5 | Web search + structured findings |
| Critic | Sonnet 4 | Score on 5 dimensions, accept/reject |
| Meta-Analyst | Sonnet 4 | Extract patterns → rewrite strategies |
| Question Generator | Haiku 4.5 | Diagnose gaps → generate questions |
| Cross-Domain | Sonnet 4 | Extract principles, seed new domains |
| Synthesizer | Sonnet 4 | Integrate findings into knowledge base |
| Orchestrator | None (logic) | Multi-domain priority routing |

## Scoring Rubric

5 dimensions, weighted:
- **Accuracy** (30%) — factual correctness
- **Depth** (20%) — beyond surface-level
- **Completeness** (20%) — important angles covered
- **Specificity** (15%) — concrete data, numbers, sources
- **Intellectual Honesty** (15%) — flags uncertainty

Threshold: score ≥ 6/10 to accept. Below 6 → retry with critique feedback (max 2 retries).

## Budget System

- Daily budget: $5.00 (configurable in config.py)
- Per-call cost tracking with estimated token costs
- Budget gate on every API call — auto-stops when exceeded
- `--budget` shows daily/all-time breakdown by agent and model

## Retry System

All API-calling agents use exponential backoff with jitter:
- 5 attempts per call
- Retryable: 529 Overloaded, 500 Internal Server Error, 503, rate limits
- Non-retryable errors fail immediately
- `create_message()` drop-in replacement for `client.messages.create()`

## Tests

```bash
python -m pytest tests/ -v              # Run all 75 tests
python -m pytest tests/ -v --tb=short   # Compact output
```

Test coverage: Config, MemoryStore, Pruning, CostTracker, StrategyStore, Integration, Orchestrator, Retry, Analytics, DomainSeeder, Validator.

## Score Trajectory

```
5.4 → 7.1 → 7.7 → 8.0  (crypto domain, over strategy evolution)
```

## Design Principles

1. **Observability is non-negotiable** — full logging, every score recorded
2. **Start smaller than feels right** — one loop, prove it, then expand
3. **The Critic is sacred** — both cost control and self-improvement signal
4. **Memory hygiene matters** — score-weight retrieval, prune low quality
5. **Strategy evolution is the novel piece** — not the agents, not the memory
