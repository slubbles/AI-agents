# Cortex Codebase Findings

Generated: March 8, 2026

## Purpose

This document consolidates the main findings from a broad scan of the Cortex repository.

It is meant to answer four questions:

1. What Cortex is trying to become
2. How the current system actually works
3. Which AI agents and control layers exist today
4. What looks proven, partial, or still mostly aspirational

This is a high-confidence architectural scan of the repo, not a line-by-line implementation audit of every file.

## Executive Summary

Cortex is a layered autonomous system aimed at becoming a bounded, self-improving operator rather than a chatbot.

Its real architecture is:

1. Signal collection and opportunity discovery
2. Agent Brain for research, scoring, memory, synthesis, and strategy evolution
3. Agent Hands for planning, execution, validation, and execution learning
4. Cortex and scheduler layers for strategic routing, daemon cycles, and coordination
5. Identity, safety, and watchdog layers for constraints and operational reliability
6. Verification and outcome feedback layers for external grounding

The most important technical thesis is not "multi-agent" by itself. It is behavioral adaptation through scored outputs, versioned strategy documents, and closed-loop improvement.

The repo already contains substantial machinery for this. The main unresolved question is not whether the architecture exists. It does. The main unresolved question is whether the full loop is grounded strongly enough in external outcomes and business reality to justify the larger autonomy claims.

## Best Sources Of Truth

These files best capture the current doctrine:

1. `README.md`
2. `agent-brain/README.md`
3. `my-notes.md/CORTEX_UNIFIED_CONTEXT.md`
4. `my-notes.md/real-self-learning.md`
5. `my-notes.md/vision-hands.md`
6. `my-notes.md/NEXT-STEPS-TO-GOAL.md`

These files are useful but more snapshot-like and time-sensitive:

1. `my-notes.md/CORTEX_MASTER_PLAN.md`
2. `CORTEX_CONSULTANT_HANDOFF.md`
3. `agent-brain/ARCHITECTURE.md`
4. `agent-brain/HANDS_INVENTORY.md`
5. `agent-brain/DEEP_SCAN_REPORT.md`

They contain valuable context, but counts, line totals, and implementation status should be treated as historical snapshots rather than guaranteed current truth.

## Vision

Across the docs, Cortex is trying to become an autonomous operator that can:

1. Find opportunities
2. Judge whether they are worth pursuing
3. Build and deploy solutions
4. Learn from outcomes
5. Improve future behavior

The near-term path is pragmatic, not mystical.

The repo repeatedly converges on a revenue-first proving ground:

1. Use Brain to identify and refine commercially viable opportunities
2. Use Hands to execute delivery work or product builds
3. Feed results back into future decision-making

The large civilizational-scale ambition remains in the notes, but the mature planning documents are explicit that first proof must come from small, economically real loops.

## Core Architecture

### 1. Signal Layer

The system can ingest market pain from public sources.

Key files:

1. `agent-brain/signal_collector.py`
2. `agent-brain/opportunity_scorer.py`
3. `agent-brain/signal_bridge.py`

What it does:

1. Scrapes Reddit RSS feeds without auth
2. Stores posts in SQLite
3. Uses a low-cost model to score pain points and opportunities
4. Converts top opportunities into Brain research questions

This makes Cortex more than a generic research bot. It already has an intake path for market pain.

### 2. Brain Layer

Agent Brain is the research and learning engine.

Core files:

1. `agent-brain/main.py`
2. `agent-brain/agents/researcher.py`
3. `agent-brain/agents/critic.py`
4. `agent-brain/memory_store.py`
5. `agent-brain/agents/synthesizer.py`
6. `agent-brain/agents/question_generator.py`
7. `agent-brain/agents/meta_analyst.py`
8. `agent-brain/strategy_store.py`
9. `agent-brain/agents/cross_domain.py`

Operational loop:

1. Research question enters the system
2. Researcher searches, fetches, and synthesizes
3. Critic scores quality
4. Low-quality outputs retry
5. Accepted outputs are stored with metadata
6. Outputs are synthesized into a knowledge base
7. Question generator proposes the next research targets
8. Meta-analyst rewrites strategies from score patterns
9. Strategy store versions and governs those strategies
10. Cross-domain transfer distills reusable principles

This is the most mature subsystem in the repo.

### 3. Hands Layer

Agent Hands is the execution system.

Core files:

1. `agent-brain/hands/planner.py`
2. `agent-brain/hands/executor.py`
3. `agent-brain/hands/validator.py`
4. `agent-brain/hands/project_orchestrator.py`
5. `agent-brain/hands/checkpoint.py`
6. `agent-brain/hands/pattern_learner.py`
7. `agent-brain/hands/exec_meta.py`
8. `agent-brain/hands/exec_cross_domain.py`
9. `agent-brain/hands/visual_gate.py`
10. `agent-brain/hands/visual_evaluator.py`

Operational loop:

1. Planner decomposes a goal into steps
2. Executor runs steps with tools
3. Validator scores correctness and quality
4. Failing steps can trigger repair or replan logic
5. Checkpoints support recovery
6. Pattern learner extracts execution lessons
7. Exec meta evolves execution strategy

Hands is much more than a toy agent wrapper. It is a full execution stack with retries, context management, repair logic, and learning scaffolding.

### 4. Orchestration Layer

There are multiple orchestration layers.

Key files:

1. `agent-brain/agents/orchestrator.py`
2. `agent-brain/agents/cortex.py`
3. `agent-brain/scheduler.py`
4. `agent-brain/protocol.py`
5. `agent-brain/sync.py`

Roles:

1. Domain orchestrator allocates research rounds across domains
2. Cortex orchestrator reasons over Brain and Hands strategically
3. Scheduler runs plans, daemon cycles, and recurring operations
4. Protocol defines typed Brain-Cortex-Hands messages
5. Sync acts as the handoff queue and alignment layer between research and execution

The architecture is intentionally layered rather than putting all coordination into one file.

### 5. Identity And Goal Layer

Key files:

1. `agent-brain/identity_loader.py`
2. `agent-brain/domain_goals.py`
3. `agent-brain/identity/goals.md`
4. `agent-brain/identity/ethics.md`
5. `agent-brain/identity/boundaries.md`
6. `agent-brain/identity/risk.md`
7. `agent-brain/identity/taste.md`

What it does:

1. Loads and compresses system identity into prompt-ready summaries
2. Provides explicit values, boundaries, and operating preferences
3. Stores per-domain structured goals so research aligns to real objectives

This is not just documentary fluff. Identity summaries are injected into live agent prompts.

### 6. Safety, Stability, And Cost Control

Key files:

1. `agent-brain/watchdog.py`
2. `agent-brain/loop_guard.py`
3. `agent-brain/monitoring.py`
4. `agent-brain/cost_tracker.py`
5. `agent-brain/alerts.py`

What it does:

1. Heartbeat monitoring
2. Circuit breaking
3. Cooldowns after repeated failures
4. Hard cost ceilings
5. Alerts and health checks
6. Loop protection against stuck or regressing behavior

This layer is central to the claim that Cortex aims for bounded autonomy, not blind autonomy.

### 7. Verification And Reality Grounding

Key files:

1. `agent-brain/agents/verifier.py`
2. `agent-brain/agents/claim_verifier.py`
3. `agent-brain/outcome_feedback.py`

What it does:

1. Verifies time-bound predictions
2. Checks high-confidence claims against external evidence
3. Converts completed and failed Hands tasks into lessons for Brain

This is the repo's answer to the LLM-judging-LLM problem, though it does not yet appear to be the dominant evaluation mechanism in every loop.

## Agent Inventory

### Brain Agents

#### `researcher.py`

Purpose:

1. Executes web research with search and page-fetch tools
2. Builds structured findings
3. Injects identity, goals, lessons, and knowledge context into prompts

Notable characteristics:

1. Strong anti-hallucination instructions
2. Date awareness
3. Optional browser escalation
4. Build-mode guidance for pre-build research

#### `critic.py`

Purpose:

1. Scores research outputs on five weighted dimensions
2. Supports adaptive rubrics per domain
3. Can run ensemble mode and confidence validation

The critic is treated as sacred in the notes because it defines what improvement means.

#### `meta_analyst.py`

Purpose:

1. Reads scored outputs and strategy history
2. Identifies effective and harmful changes
3. Produces new strategy candidates with limited controlled modifications

This is the core of the behavioral adaptation thesis.

#### `question_generator.py`

Purpose:

1. Reads knowledge gaps and critic weaknesses
2. Aligns next questions to domain goals and task queues
3. Drives self-directed research progression

#### `synthesizer.py`

Purpose:

1. Turns accepted outputs into a unified knowledge base
2. Deduplicates claims
3. Detects contradictions
4. Marks superseded knowledge

This is what upgrades the system from isolated outputs to compounding domain memory.

#### `verifier.py`

Purpose:

1. Extracts time-bound predictions
2. Verifies them once deadlines pass
3. Updates internal confidence based on real-world evidence

#### `claim_verifier.py`

Purpose:

1. Samples high-confidence claims
2. Searches for confirmation or contradiction
3. Prevents bad claims from calcifying into internal truth

#### `consensus.py`

Purpose:

1. Runs multiple independent researchers in parallel
2. Merges agreement and disagreement into a stronger final answer

This is a useful hedge against single-run blind spots.

#### `cross_domain.py`

Purpose:

1. Extracts general principles from strong domains
2. Seeds new domains with transferable strategies

This is Layer 5 of the self-learning thesis.

#### `orchestrator.py`

Purpose:

1. Scores domain priority
2. Allocates rounds across domains based on budget, freshness, and maturity

#### `cortex.py`

Purpose:

1. Strategic reasoning over Brain and Hands together
2. System-level planning and assessment
3. Approval management
4. Meta-level coordination

This is the repo's clearest "brain above brains" file.

#### `threads_analyst.py`

Purpose:

1. Analyzes Threads content for market pain and content opportunities
2. Supports both research-mode and growth/content-mode use cases

### Hands Core Agents And Subsystems

#### `planner.py`

Purpose:

1. Creates structured execution plans
2. Scans workspaces and key files
3. Applies skills and design context to planning
4. Adds some reality-check logic for certain build tasks

#### `executor.py`

Purpose:

1. Executes plans step by step with tools
2. Maintains sliding context windows
3. Handles retries, failures, step dependencies, and checkpoints
4. Tracks artifacts and cost ceilings

#### `validator.py`

Purpose:

1. Runs static checks
2. Scores execution outputs on quality dimensions
3. Identifies failing steps for repair loops

#### `project_orchestrator.py`

Purpose:

1. Breaks larger projects into phases and tasks
2. Adds review gates to higher-risk phases

#### `pattern_learner.py`, `exec_meta.py`, `exec_cross_domain.py`

Purpose:

1. Learn from Hands execution history
2. Evolve execution strategies
3. Transfer strong execution principles across domains

## Model Routing

Key file:

1. `agent-brain/llm_router.py`

Routing pattern:

1. Cheap and high-volume tasks use OpenRouter-backed models such as DeepSeek, Grok, or Gemini depending on config
2. Higher-stakes reasoning and judgment tasks use Claude Sonnet

This supports the recurring repo principle: cheap before smart, but do not cheap out on judgment-critical steps.

## Core Runtime Flows

### Flow 1: Signal To Research

1. Reddit posts are collected
2. Opportunities are scored
3. Top pain points are converted to research questions
4. Brain researches those questions

### Flow 2: Research To Memory

1. Researcher produces findings
2. Critic scores them
3. Accepted outputs are stored
4. Synthesizer folds them into a knowledge base

### Flow 3: Memory To Better Research

1. Question generator surfaces next gaps
2. Meta-analyst evolves strategy based on scores
3. Researcher runs again under a better strategy

### Flow 4: Research To Execution

1. Accepted research can create actionable sync tasks
2. Hands planner and executor can work those tasks
3. Validation scores execution results

### Flow 5: Execution Back To Learning

1. Completed and failed tasks are processed by outcome feedback
2. Research lessons are created from execution reality
3. Brain can use those lessons in later cycles

### Flow 6: Multi-Domain Daemon Operation

1. Scheduler creates or executes domain plans
2. Domain orchestrator allocates limited rounds
3. Watchdog and monitoring enforce safety and stability
4. System health and state can be surfaced to higher layers

## What Looks Proven

High-confidence implemented subsystems:

1. Brain research, scoring, storage, and strategy machinery
2. Hands planning and execution stack
3. Signal ingestion and opportunity scoring path
4. Sync and outcome feedback bridge
5. Identity injection into prompts
6. Scheduler and watchdog infrastructure

These are not just aspirations in docs. The codebase contains real implementations for all of them.

## What Looks Partial

Important but not fully dominant yet:

1. Verification as the main quality arbiter
2. Outcome-grounded commercial learning
3. End-to-end autonomous business operation
4. Fully mature Cortex-level strategic orchestration

The code exists in pieces, but the repo still appears stronger at generating and evaluating research and execution artifacts than at proving economic success through repeated autonomous runs.

## What Looks Aspirational Or Underbuilt

### Observable Horizon

The notes describe a powerful idea: classify the boundary of reliable knowledge into not-enough-data, capability-gap, and frontier-unknown states.

This concept is philosophically central, but it does not yet appear to be a first-class runtime subsystem with explicit state transitions.

### Full Autonomous Business Operator

The repo contains the building blocks for this, but the proof standard described in the notes remains higher than what the visible runtime wiring alone proves.

### Civilizational-Scale Multi-Instance Vision

This remains a long-horizon rationale, not a current operating reality.

## Main Strengths

1. The architecture is unusually coherent across docs and code
2. The Brain subsystem is genuinely more than note-taking or RAG
3. Hands is much deeper than a thin code-agent wrapper
4. Identity, safety, and budget awareness are treated structurally
5. The system already includes a signal-to-opportunity intake path
6. The repo has a credible attempt at closing Brain-to-Hands and Hands-to-Brain loops

## Main Risks And Gaps

1. Doc drift across handoff and plan files can make status claims look more certain than current proof
2. Verification exists, but it is still not obviously the load-bearing judge of all important loops
3. The economic learning loop is not yet as mature as the research learning loop
4. The strongest philosophy in the notes is ahead of the strongest enforcement in runtime code
5. The system can still produce internally impressive artifacts faster than it can prove durable external value

## Practical Reading Order

If a new engineer needs fast context, this is the most useful order:

1. `README.md`
2. `my-notes.md/CORTEX_UNIFIED_CONTEXT.md`
3. `my-notes.md/real-self-learning.md`
4. `my-notes.md/vision-hands.md`
5. `my-notes.md/NEXT-STEPS-TO-GOAL.md`
6. `agent-brain/main.py`
7. `agent-brain/agents/cortex.py`
8. `agent-brain/scheduler.py`
9. `agent-brain/agents/researcher.py`
10. `agent-brain/agents/critic.py`
11. `agent-brain/agents/meta_analyst.py`
12. `agent-brain/agents/synthesizer.py`
13. `agent-brain/hands/planner.py`
14. `agent-brain/hands/executor.py`
15. `agent-brain/watchdog.py`

## Bottom Line

Cortex is a serious autonomous-systems codebase with a real research engine, a real execution stack, a real safety-and-budget layer, and a meaningful attempt at behavioral self-improvement.

Its strongest proven claim is not that it is already a fully autonomous operator. Its strongest proven claim is that it has implemented a layered architecture for turning scored research and execution outcomes into changed future behavior.

The most important next proof is not more philosophy. It is stronger external grounding:

1. reliable verifier influence
2. repeated unsupervised runs
3. business-outcome feedback
4. evidence that the full loop makes better decisions over time

If that proof arrives, the broader vision in the notes becomes much more credible.