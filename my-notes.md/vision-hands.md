# Vision: Agent Brain + Agent Hands — Autonomous Business Operator

## The Goal

A system that handles the full business lifecycle autonomously:

```
Find pain point → Validate demand → Build solution → Deploy → Market → Acquire customers → Support → Iterate
```

Not a tool. Not an assistant. An autonomous operator that self-improves at every stage.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        YOU (Director)                        │
│  Set priorities. Approve key outputs. Own legal/financial.   │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │     ORCHESTRATOR      │  Routes work between brain & hands
              └───────┬───────┬───────┘
                      │       │
         ┌────────────▼┐  ┌──▼────────────┐
         │  AGENT BRAIN │  │  AGENT HANDS  │
         │  (research)  │  │  (execution)  │
         │              │  │               │
         │  Question    │  │  Planner      │
         │  Researcher  │  │  Executor     │
         │  Critic      │  │  Validator    │
         │  Synthesizer │  │  Exec Meta    │
         │  Meta-Analyst│  │               │
         └──────┬───────┘  │  TOOLS:       │
                │          │  ├ code.py     │
                │ writes   │  ├ terminal.py │
                ▼          │  ├ browser.py  │
         ┌──────────┐     │  ├ file.py     │
         │    KB    │◄────┤  └ api.py      │
         │ (claims, │reads│               │
         │  graph,  │     └───────┬───────┘
         │  gaps)   │             │
         └──────────┘             ▼
                           ┌──────────┐
                           │ OUTPUTS  │  Code, content, posts, emails
                           │ (scored, │  Parked for approval or auto-shipped
                           │ versioned│  based on confidence threshold
                           └──────────┘
```

## Domain Coverage (Brain learns each, Hands executes each)

| Domain | Brain Learns | Hands Executes |
|---|---|---|
| market-research | Reddit pain points, demand signals, competitor gaps | Scrape Reddit, analyze trends, rank opportunities |
| saas-building | Architecture, deployment, testing, security | Write code, deploy, run tests, fix bugs |
| growth-hacking | What content gets traction, where to post, messaging | Post to Reddit/Twitter/HN, write content, SEO |
| copywriting | Conversion patterns, landing page psychology, email | Write landing pages, email sequences, social posts |
| customer-support | Response patterns, triage, retention tactics | Respond to emails, handle support, escalate edge cases |
| [product-domain] | Whatever niche the product serves | Domain-specific execution |

## The Self-Improvement Loops

**Brain loop** (proven, working):
```
Research → Critic scores → Strategy evolves → Research improves → Repeat
```

**Hands loop** (building now):
```
Plan → Execute → Validator scores → Exec strategy evolves → Execution improves → Repeat
```

**Cross-loop feedback:**
```
Hands fails at X → Brain adds X to research queue → Brain learns X → Hands uses it → Scores improve
```

## Tool Registry (Pluggable)

```
hands/tools/
├── registry.py    — Tool selection + routing
├── code.py        — Write/edit code, generate projects
├── terminal.py    — Run shell commands, deploy, test, lint
├── browser.py     — Playwright headless: post, comment, scrape, screenshot
├── file.py        — Write docs, reports, copy, configs
└── api.py         — Call external APIs (Stripe, email, social, analytics)
```

Adding a new capability = adding a new tool file. The planner automatically selects tools based on the task.

## The 100% Autonomous Mode

The system handles everything except:
- Being legally/financially you (Stripe KYC, legal entity)
- Checking the dashboard occasionally
- Setting high-level priorities

Everything else — research, build, deploy, market, support, iterate — runs autonomously.

## Revenue Model

The system doesn't make money. Products the system builds make money.

Target: marketplace products (Shopify apps, VS Code extensions, templates, Chrome extensions) where the marketplace handles distribution. The system builds, markets, and iterates. Revenue covers API costs. Surplus is profit.

## Budget

- $500 max investment before self-sustaining
- Target: self-funding by Month 2-3
- API cost optimized: Haiku for 90% of calls, Sonnet for judgment calls only

## Build Order

1. ✅ Agent Brain (complete, 5 layers, proven)
2. 🔨 Agent Hands core (planner, executor, validator, tools)
3. 🔨 Exec Meta-Analyst (execution strategy evolution)
4. 🔨 Browser tool (web interaction, posting, scraping)
5. 🔨 Marketing domains (brain training on growth, copy, support)
6. 🔨 Orchestrator upgrade (brain + hands coordination)
7. 🔨 First autonomous product run (end-to-end proof)
