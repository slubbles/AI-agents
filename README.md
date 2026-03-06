# Cortex

Cortex is an autonomous agent system being built to do real work, not just generate impressive outputs.

The goal is simple to describe and hard to execute:

1. find real opportunities,
2. decide which ones are worth pursuing,
3. build the solution,
4. deploy it,
5. learn from what actually happened,
6. and improve the next cycle.

The benefit is not "better chat." The benefit is leverage.

If Cortex works, it reduces the amount of founder/operator effort required to go from idea to evidence to execution. Instead of manually researching everything, guessing what to build, and burning time on weak opportunities, the system is meant to help choose better, move faster, and learn from outcomes.

## What You Get

Today, the system is strongest at these jobs:

1. researching markets and opportunities,
2. scoring and filtering ideas,
3. pressure-testing ideas commercially,
4. generating build specs and decision packets,
5. executing coding tasks through Agent Hands,
6. preserving memory, strategy evolution, and audit trails.

In plain terms, Cortex is being built to help answer questions like:

1. What should we work on next?
2. Which opportunity is real versus just emotionally appealing?
3. What is the smallest wedge worth targeting first?
4. What should we build in the next few days, not someday?
5. What did the last cycle teach us that should change the next one?

## Why This Exists

Most agent systems stop at output generation.

They can write, summarize, search, or code, but they do not reliably:

1. carry lessons forward,
2. adapt their operating behavior based on scored performance,
3. separate idea quality from commercial viability,
4. coordinate reasoning and execution as one loop.

Cortex is built around that missing layer.

It is not trying to be a generic assistant. It is trying to become an autonomous operator that can improve through repeated real-world cycles.

## The Current Shape Of The System

### Agent Brain

Agent Brain is the research and learning engine.

It accumulates findings, scores outputs, rewrites strategy documents based on performance, extracts cross-domain principles, and keeps a structured memory of what has been tried.

### Agent Hands

Agent Hands is the execution engine.

Right now it is strongest in coding and delivery work: editing code, running tools, testing, fixing, and deploying.

### Cortex

Cortex is the reasoning layer above both.

It interprets research, coordinates Brain and Hands, performs commercial reality checks, and helps turn raw opportunities into decisions.

## What Makes It Different

The core mechanism is not model fine-tuning.

The core mechanism is behavioral adaptation through structured feedback loops.

That means:

1. outputs are scored,
2. score patterns are analyzed,
3. strategy instructions are rewritten,
4. new strategies are trialed,
5. weak changes can be rolled back,
6. useful lessons can transfer across domains.

The system changes its own behavior over time by changing how it operates, not by pretending the base model itself has learned new weights.

## What Is Already Working

The following pieces exist and are usable now:

1. self-learning research loops in Agent Brain,
2. strategy evolution with trial and rollback,
3. cross-domain principle extraction,
4. cost tracking and budget enforcement,
5. signal collection and opportunity scoring,
6. build-spec generation,
7. Cortex commercial reality checks,
8. decision packets that combine a build spec with a go, test-first, or skip verdict,
9. coding execution through Agent Hands,
10. VPS deployment tooling.

## What Is Not Proven Yet

This matters because the project should not oversell itself.

These things still need proof through real operation:

1. long unsupervised autonomous runtime,
2. reliable revenue generation,
3. stronger verifier-driven truth checks,
4. repeatable market validation from live outreach and customer behavior,
5. broader non-coding execution capabilities in Hands.

The vision is larger than the proof so far. The repo is meant to close that gap, not hide it.

## The Operating Loop

At a high level, Cortex is moving toward this loop:

```text
Research signal -> score opportunity -> generate build spec -> reality check -> choose go/test/skip -> execute -> measure outcome -> adapt strategy -> repeat
```

That is the real product. Not a single model call. Not a demo. A repeatable decision-and-execution loop.

## Current Priority

The current priority is not infinite architecture expansion.

It is:

1. use the system to choose better opportunities,
2. validate them faster,
3. get to revenue sooner,
4. improve the system using real business outcomes.

The first target is productized services because it is the shortest path to real-world proof and cash flow. After that, the same loop can expand into SaaS and broader autonomous operations.

## Repository Structure

```text
AI-agents/
├── agent-brain/      # Main Cortex codebase: Brain, Hands, Cortex, deploy, tests
├── my-notes.md/      # Vision, action plans, strategy notes, architectural intent
├── openclaw/         # External reference repo used for learning from patterns, not as runtime dependency
└── zip-files/        # Supporting archive artifacts
```

Inside `agent-brain/`, the key areas are:

```text
agent-brain/
├── agents/           # Brain and Cortex reasoning modules
├── hands/            # Execution engine and tools
├── cli/              # User and system command surface
├── deploy/           # VPS deployment tooling
├── tests/            # Test suite
├── logs/             # Runtime logs and artifacts
├── memory/           # Brain output memory
├── strategies/       # Strategy versions and domain-specific operating instructions
└── main.py           # Main entry point
```

## Quick Start

```bash
git clone https://github.com/slubbles/AI-agents.git
cd AI-agents/agent-brain
pip install -r requirements.txt
cp .env.example .env
python main.py --signal-status
```

A few useful flows:

```bash
# Research loop
python main.py --domain productized-services --auto --rounds 3

# Signal intelligence
python main.py --collect-signals
python main.py --rank-opportunities
python main.py --build-spec 1
python main.py --reality-check 1

# System status
python main.py --dashboard
python main.py --budget
```

## Who This Is For

This repo is most relevant if you care about one of these problems:

1. building agent systems that learn from outcomes instead of just producing outputs,
2. creating a founder/operator copilot that can research, decide, and execute,
3. turning autonomous systems into something economically useful,
4. exploring how Brain, execution, and self-improvement loops can be separated cleanly.

## Design Principles

1. Revenue before polish.
2. Autonomous first, but with observability.
3. The critic and verifier matter more than optimistic generation.
4. Learning should change behavior, not just store data.
5. The system should become more useful through real loops, not more impressive through isolated demos.

## Read Next

If you want the technical implementation details, start here:

1. [agent-brain/README.md](agent-brain/README.md)
2. [my-notes.md/ACTION-PLAN.md](my-notes.md/ACTION-PLAN.md)
3. [my-notes.md/ULTIMATE PURPOSE.txt](my-notes.md/ULTIMATE%20PURPOSE.txt)
4. [my-notes.md/NEXT-STEPS-TO-GOAL.md](my-notes.md/NEXT-STEPS-TO-GOAL.md)

## Status

Cortex is already beyond a toy.

It is not yet the finished autonomous operator described in the long-term vision.

The work now is to keep converting architecture into proof:

1. better decisions,
2. real execution,
3. real market feedback,
4. real learning,
5. less human intervention over time.