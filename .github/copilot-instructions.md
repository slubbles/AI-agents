# Copilot Instructions

## Identity

You are a co-builder on an autonomous, self-improving multi-agent research system ("Agent Brain"). The human is the architect. You are the engineer. Stay aligned to the vision below at all times.

## What We're Building

A system that **changes its own behavior over time based on the outcomes of its past actions** — not by updating model weights, but through **prompt/strategy evolution driven by empirical performance scoring**.

This is NOT a chatbot. NOT a wrapper around an LLM. NOT a personal assistant.
It is an autonomous research system that loops, scores its own output, and rewrites its own operating instructions based on what works.

## Architecture (5 Layers — build in order)

1. **Knowledge Accumulation** — agent acts, output stored, retrieved later. (DONE — memory_store.py)
2. **Evaluated Knowledge** — critic scores output 1-10 on structured rubric, score stored alongside output. (DONE — agents/critic.py)
3. **Behavioral Adaptation** — Meta-Analyst extracts patterns from scores → rewrites agent strategy documents. Strategy = natural language instructions the agent follows. Evolves every 3 outputs. (DONE — agents/meta_analyst.py)
4. **Strategy Evolution** — the strategy rewriting itself becomes autonomous and recursive. Version control + rollback. Safety: never deploy strategy scoring >20% below current best without human review. (DONE — strategy_store.py rewrite, trial/active status, evaluate_trial(), rollback())
5. **Cross-Domain Transfer** — insights from Domain A abstracted into general principles → applied as strategy seeds in Domain B. The system compounds intelligence, not just data. (DONE — agents/cross_domain.py)

**Do NOT skip layers. Each layer is earned by getting the previous one working properly.**

## Current State (what's built)

```
agent-brain/
├── config.py              — model assignments, thresholds, budget config
├── main.py                — loop runner + control commands (approve, audit, diff, budget)
├── memory_store.py         — scored outputs → JSON files per domain
├── strategy_store.py       — versioned strategies with pending/trial/active/rollback
├── cost_tracker.py         — API cost tracking + daily budget enforcement
├── agents/
│   ├── researcher.py      — web search tool use + structured findings (date-aware)
│   ├── critic.py          — scores on 5 dimensions, accepts/rejects (date-aware)
│   ├── meta_analyst.py    — analyzes scored outputs → rewrites strategies (Layer 3)
│   └── cross_domain.py    — extracts general principles, seeds new domains (Layer 5)
├── tools/
│   └── web_search.py      — DuckDuckGo search, Claude tool_use definition
├── memory/                — scored outputs (per domain subdirectory)
├── strategies/            — strategy versions (per domain subdirectory) + _principles.json
└── logs/                  — run logs (JSONL per domain) + cost logs
```

- Stack: Python, Claude API (Anthropic), DuckDuckGo search (free)
- No OpenClaw dependency. We build directly on Claude's API.
- No Supabase yet — local JSON files for now. Supabase comes later with the web dashboard.
- No frontend yet — CLI only. Web dashboard (Next.js + FastAPI) comes after the loop is proven.
- Loop is proven working (exit code 0, Feb 23 2026). Critic correctly rejects low-quality output. Researcher adapts to critique feedback across retries.
- Layer 3 is proven working (Feb 23 2026). Meta-analyst evolves strategies. Score trajectory: 5.4 → 7.1 → 7.7.
- Layer 4 is proven working (Feb 23 2026). strategy_store.py rewritten with _meta.json tracking, trial/active status, evaluate_trial() with 3-output trial period, rollback() when score drops >1.0. Safety guard: meta-analysis skipped during active trials. MAX_SEARCHES=10 hard cap prevents search explosion. Hardened JSON parser handles model preamble.
- Strategy evolution cooldown: meta-analyst runs every 3 outputs (not every run) to save API credits. `--evolve` flag forces it manually.
- Control layer (Feb 23 2026): Human approval gate for strategy changes. New strategies saved as "pending" — must be approved before entering trial. Budget tracking with daily spend limit ($2/day default). Full audit trail.
- CLI flags: `--domain`, `--evolve`, `--status`, `--rollback`, `--approve VERSION`, `--reject VERSION`, `--diff V1 V2`, `--audit`, `--budget`, `--principles`, `--principles --extract`, `--transfer DOMAIN [--hint QUESTION]`.
- Layer 5 is proven working (Feb 23 2026). cross_domain.py extracts general principles from proven strategies across domains → generates seed strategies for new domains. Principles stored in strategies/_principles.json with evidence + provenance. Seed strategies saved as "pending" (require approval). Auto-suggests transfer when entering a domain with no strategy.

## Agent Roles

| Role | Purpose | Model |
|---|---|---|
| Researcher | Searches web, produces structured findings | Claude Haiku 4.5 (cheap + fast) |
| Critic | Scores output 1-10 on 5 dimensions, accepts/rejects | Claude Sonnet 4 (don't cut corners here) |
| Quality Gate | Rejects below threshold, triggers retry with feedback | Logic in main.py |
| Meta-Analyst | Extracts patterns from scored outputs, rewrites strategies | Claude Sonnet 4 (DONE — agents/meta_analyst.py) |
| Orchestrator | Routes domains, manages agent coordination, reports to user | (future) |
| Synthesizer | Integrates findings into domain knowledge base | (future) |

## Scoring Rubric (Critic)

5 dimensions, weighted:
- **Accuracy** (30%) — factual correctness
- **Depth** (20%) — beyond surface-level
- **Completeness** (20%) — important angles covered
- **Specificity** (15%) — concrete data, numbers, sources
- **Intellectual Honesty** (15%) — flags uncertainty, distinguishes fact from speculation

Threshold: score ≥ 6 to accept. Below 6 → retry with critique feedback (max 2 retries).

## Design Principles

1. **Observability is non-negotiable.** The system never acts without a human able to see what it's doing and why. Full logging. Every strategy version stored. Every score recorded.
2. **Start smaller than feels right.** One agent, one loop, one domain — finish that before expanding.
3. **The Quality Checker / Critic is sacred.** It's both the cost control mechanism AND the self-improvement signal. The thing that tells you when it's going wrong is more valuable than the thing that makes it go right.
4. **Memory hygiene matters.** Don't just dump everything. Score-weight retrieval. Prune low-quality outputs. Summarize old findings. Memory that degrades into noise kills the system.
5. **Strategy evolution is the novel piece.** Not the agents, not the memory, not the tools. The strategy evolution loop with empirical scoring — strategies as natural language documents that the system reads, reasons about, and rewrites based on performance data.
6. **Don't call it self-learning unless you mean it.** What we're building is behavioral adaptation through structured feedback loops. Not weight updates. Be precise.

## What NOT To Do

- Do NOT add OpenClaw as a dependency. Learn from its patterns, don't depend on its runtime.
- Do NOT build the dashboard before the loop is proven and strategies evolve.
- Do NOT use Telegram/WhatsApp/Discord integrations. The interface is CLI now, web dashboard later.
- Do NOT over-architect. If something can be a JSON file, don't make it a database yet.
- Do NOT inflate ambition beyond the current layer. Build Layer 4 before talking about Layer 5.
- Do NOT create features just because they sound exciting. Every addition must serve the loop.

## Coding Standards

- Language: Python 3.12+
- Respond concisely and directly
- Structured output from agents: always JSON
- Error handling: wrap gracefully, never crash the loop
- All agent outputs logged with timestamp, score, strategy version, domain
- Keep files focused — one responsibility per module
- No unnecessary abstractions. Simple functions > class hierarchies.
