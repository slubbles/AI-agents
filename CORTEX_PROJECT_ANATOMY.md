# Cortex Project Anatomy

Short map of the whole Cortex system.

## 1. Big Picture

`Cortex = Signals + Brain + Hands + Orchestrator + Memory + Safety + Feedback`

- `Signals` find pain, demand, and trends.
- `Brain` researches, scores, remembers, and chooses what to learn next.
- `Hands` plans work, executes work, checks work, and learns from execution.
- `Orchestrator` decides what runs, when it runs, and in what order.
- `Memory` keeps what Cortex learned.
- `Safety` stops bad loops, cost blowups, and drift.
- `Feedback` turns real results into better future behavior.

## 2. Core Parts

### Signal Layer

- `signal_collector.py`: collects public pain signals and posts.
- `opportunity_scorer.py`: scores which signals look worth chasing.
- `signal_bridge.py`: turns strong signals into Brain questions or build ideas.

Interaction:
`signals -> score -> Brain questions`

### Brain Layer

- `main.py`: main research loop and CLI entry.
- `memory_store.py`: stores scored outputs and retrieves useful old knowledge.
- `strategy_store.py`: saves research strategies, trial strategies, and rollbacks.
- `knowledge_graph.py`: maps claim-to-claim connections.
- `domain_goals.py`: stores what each domain is trying to achieve.
- `domain_seeder.py`: gives starter questions for a new domain.
- `domain_bootstrap.py`: helps a cold domain start with better first steps.
- `domain_calibration.py`: tunes how a domain should be judged.
- `prescreen.py`: cheap first filter before expensive judging.
- `progress_tracker.py`: checks if a domain is actually moving forward.
- `research_lessons.py`: stores lessons Brain should reuse.
- `memory_lifecycle.py`: prunes, archives, and keeps memory cleaner.

Interaction:
`question -> research -> score -> store -> synthesize -> next question`

### Hands Layer

- `hands/planner.py`: breaks a goal into steps.
- `hands/executor.py`: does the steps with tools.
- `hands/validator.py`: checks if the result is good enough.
- `hands/project_orchestrator.py`: runs multi-phase projects.
- `hands/checkpoint.py`: saves progress so work can resume after failure.
- `hands/pattern_learner.py`: finds execution lessons.
- `hands/exec_meta.py`: improves execution strategy over time.
- `hands/exec_cross_domain.py`: moves execution lessons across domains.
- `hands/code_exemplars.py`: stores strong code examples for reuse.
- `hands/artifact_tracker.py`: tracks quality by file type.
- `hands/feedback_cache.py`: remembers recent weak spots.
- `hands/strategy_assembler.py`: builds the final execution guidance bundle.
- `hands/visual_gate.py`: blocks weak visual output.
- `hands/visual_evaluator.py`: judges visual quality.

Interaction:
`goal -> plan -> execute -> validate -> repair or pass`

### Orchestration Layer

- `agents/orchestrator.py`: picks what domain or research path matters most.
- `agents/cortex.py`: higher-level coordinator over Brain and Hands.
- `scheduler.py`: runs timed cycles, daemon mode, and recurring jobs.
- `sync.py`: handoff queue between Brain discoveries and Hands tasks.
- `protocol.py`: message structure between system parts.

Interaction:
`signals/brain/hands -> scheduler/orchestrator -> next action`

### Identity Layer

- `identity_loader.py`: loads system identity into prompt-ready form.
- `identity/goals.md`: what Cortex wants.
- `identity/ethics.md`: what Cortex should not do.
- `identity/boundaries.md`: operating limits.
- `identity/risk.md`: risk tolerance.
- `identity/taste.md`: style and quality preference.

Interaction:
`identity -> shapes Brain and Hands behavior`

### Safety And Reliability Layer

- `watchdog.py`: checks if the system is alive and behaving.
- `loop_guard.py`: catches stuck loops, repeats, regressions, and cost spikes.
- `monitoring.py`: system health checks.
- `cost_tracker.py`: spend tracking and limits.
- `alerts.py`: creates alerts for bad states.
- `validator.py`: checks data integrity across stores.

Interaction:
`all loops -> safety checks -> allow / warn / stop`

### Verification And Grounding Layer

- `agents/verifier.py`: checks predictions against reality.
- `agents/claim_verifier.py`: checks specific claims.
- `outcome_feedback.py`: turns finished work into lessons.
- `source_quality.py`: judges how trustworthy a source is.

Interaction:
`research or execution output -> verify -> confidence up/down`

### Social / Market Layer

- `tools/threads_client.py`: direct Threads posting path.
- `tools/buffer_client.py`: X posting path through Buffer.
- `tools/image_publisher.py`: media publishing support.
- `agents/threads_analyst.py`: reads Threads performance and patterns.
- `content_factory.py`: makes content drafts from recent system context.

Interaction:
`content idea -> draft -> publish -> engagement feedback`

### Interface Layer

- `cli/`: command-line commands for research, tools, deploy, signals, and knowledge.
- `telegram_bot.py`: Telegram control surface.
- `dashboard/`: web UI and API layer.

Interaction:
`human -> CLI/Telegram/dashboard -> Cortex`

## 3. Brain Agents

- `agents/researcher.py`: researches the topic.
- `agents/critic.py`: scores research quality.
- `agents/question_generator.py`: decides the next useful questions.
- `agents/synthesizer.py`: merges findings into a cleaner knowledge base.
- `agents/meta_analyst.py`: rewrites research strategy from score patterns.
- `agents/cross_domain.py`: extracts reusable principles for other domains.
- `agents/consensus.py`: runs multi-researcher agreement checks.
- `agents/orchestrator.py`: chooses what to focus on.
- `agents/verifier.py`: checks if claims or predictions held up.
- `agents/claim_verifier.py`: checks single claims more directly.
- `agents/cortex.py`: top-level thinker over the whole system.
- `agents/threads_analyst.py`: studies Threads results and patterns.

## 4. Hands Agents

- `hands/planner.py`: makes the execution plan.
- `hands/executor.py`: performs the plan.
- `hands/validator.py`: checks execution quality.
- `hands/project_orchestrator.py`: manages bigger builds by phase.
- `hands/pattern_learner.py`: learns from execution history.
- `hands/exec_meta.py`: improves how Hands works.
- `hands/exec_cross_domain.py`: reuses execution lessons in new domains.
- `hands/visual_gate.py`: catches weak-looking outputs.
- `hands/visual_evaluator.py`: rates visual quality.

## 5. What Interacts With What

- `Signals` feed `Brain`.
- `Brain` feeds `Sync`.
- `Sync` feeds `Hands`.
- `Hands` feeds `Outcome Feedback`.
- `Outcome Feedback` feeds `Brain lessons`.
- `Meta agents` update `strategy stores`.
- `Scheduler` decides when loops run.
- `Safety` watches all layers.
- `Identity` shapes all prompt-driven agents.
- `Social tools` push market-facing output and send engagement back in.

## 6. SaaS Domain Example

Example domain:
`SaaS for teams that want better customer onboarding analytics`

### What Cortex would do

1. `signal_collector.py` finds pain posts like: "we lose users in onboarding and don't know why."
2. `opportunity_scorer.py` scores that pain as worth chasing.
3. `signal_bridge.py` turns it into questions like:
   - who has this problem?
   - how painful is it?
   - what tools already exist?
   - what gap is still open?
4. `researcher.py` studies the market, competitors, pricing, user pain, and use cases.
5. `critic.py` scores the research.
6. Good research goes into `memory_store.py`.
7. `synthesizer.py` updates the SaaS domain knowledge base.
8. `question_generator.py` picks the next gap, like pricing or buyer type.
9. `orchestrator.py` or `scheduler.py` decides if it is ready for build work.
10. `sync.py` creates a Hands task like: "build MVP onboarding funnel tracker landing page and app shell."
11. `hands/planner.py` makes the build steps.
12. `hands/executor.py` writes code, edits files, runs tests, and fixes issues.
13. `hands/validator.py` checks if the build is acceptable.
14. If weak, Hands repairs or replans.
15. If good, result can move to deploy, publish, or outreach.
16. `outcome_feedback.py` turns success or failure into lessons.
17. `meta_analyst.py` and `exec_meta.py` improve future research and build behavior.

## 7. Main Loops Cortex Runs

### Research Loop

`goal/question -> researcher -> critic -> accept/retry -> memory`

What it does:
- learns the domain
- builds knowledge
- improves question quality

### Execution Loop

`task -> planner -> executor -> validator -> repair/replan -> done`

What it does:
- turns an idea into a real artifact
- keeps retrying until quality passes or it fails cleanly

### Feedback Loop

`real output -> result -> lesson -> future better output`

What it does:
- turns success and failure into reusable lessons
- helps Brain and Hands stop repeating mistakes

### Self-Learning Loop

`scores/history -> meta analysis -> strategy rewrite -> next runs use new strategy`

What it does:
- changes system behavior without changing model weights
- improves prompts, rules, and tactics from evidence

### Cross-Domain Loop

`good lessons in one domain -> abstract principle -> seed another domain`

What it does:
- lets Cortex start faster in a new space

### Verification Loop

`claim or prediction -> verifier -> confidence update -> memory update`

What it does:
- grounds the system in reality
- reduces fake confidence

### Safety Loop

`run -> watchdog/loop_guard/cost_tracker -> continue or stop`

What it does:
- prevents runaway loops
- controls cost and repeated failure

### Market Loop

`signal -> research -> build -> publish/outreach -> engagement -> new signal`

What it does:
- connects the system to real market response
- is the path toward revenue

## 8. SaaS Domain End-to-End Flow

### Phase 1: Find a SaaS idea

`signals -> score -> research`

Output:
- user pain
- buyer type
- competitor map
- pricing ideas

### Phase 2: Decide if it is worth building

`research -> critic -> verifier -> progress check`

Output:
- keep going
- change angle
- kill the idea

### Phase 3: Build the SaaS

`Brain task -> sync -> Hands plan -> Hands execute -> validate`

Output:
- landing page
- app shell
- feature MVP
- deploy steps

### Phase 4: Put it in front of people

`content_factory/social tools -> X or Threads -> engagement`

Output:
- posts
- traffic signal
- interest signal

### Phase 5: Learn from reality

`usage/outreach/build result -> outcome_feedback + verifier + meta agents`

Output:
- better strategy
- better prompts
- better next build

## 9. The Shortest Possible Summary

- `Brain` learns what to do.
- `Hands` does the work.
- `Orchestrator` decides what runs next.
- `Memory` keeps what worked.
- `Safety` stops bad loops.
- `Feedback` makes the next run better.
- `Signals and market response` keep Cortex tied to the real world.
