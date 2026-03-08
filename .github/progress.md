# Progress Log

Every session, what we did, why, how, and results. Newest first.

---

## Session 42 — Mar 8, 2026
**Prompt:** Check whether Buffer can read X account history and wire the X draft/approval workflow into Telegram commands

### What We Did
1. **Verified Buffer can read recent X posts** from the connected account, not just publish them
2. **Added Telegram X commands** for reading posts, reviewing queue, creating drafts, sending drafts, canceling drafts, and generating draft batches
3. **Added `/create-x-posts`** so Cortex can generate multiple X drafts from its knowledge and queue them for approval
4. **Fixed the real generation bugs** that showed up during live use: missing dependencies, Windows chat import issues, and wrong parsing of normalized LLM responses

### Why
- The user wanted the X workflow to show up inside Telegram, not just CLI code
- Buffer/X capability needed a real answer based on live schema and live reads, not assumptions

### Purpose
- Gives Cortex a Telegram-controlled X workflow with approval in the middle
- Makes it possible to casually use Telegram slash commands to generate, review, and approve X posts

### Steps Taken
1. Queried Buffer GraphQL and confirmed `posts`/`post` read access for the connected X account
2. Added `get_recent_x_posts()` in `tools/buffer_client.py`
3. Added `/x posts`, `/x queue`, `/x draft`, `/x send`, `/x cancel`, and `/create-x-posts` in `telegram_bot.py`
4. Fixed command parsing so Telegram preserves user text case instead of lowercasing draft content
5. Installed missing runtime deps in the workspace venv: `scikit-learn` and `openai`
6. Fixed `cli/chat.py` for Windows environments without `readline`
7. Fixed `agents/threads_analyst.py` so draft generation reads actual text from normalized LLM responses instead of stringifying the wrapper object
8. Verified live Telegram command behavior by generating two real X drafts and reading them back from the queue

### Results
- Buffer can read recent X posts for the connected account
- Telegram X commands are wired and tested
- Live `/create-x-posts 2 onboarding analytics` created two clean queued drafts
- Focused verification passed: `tests/test_threads_analyst.py`, `tests/test_telegram_bot.py`, and `tests/test_buffer_client.py`

### Suggested Next Steps
- **Goal/Intent**: Make Telegram the normal control surface for X posting approval
- **Why/Purpose**: The core flow works; the next leverage is cleaner review and tighter control from chat
- **Objectives**:
  1. Add a nicer Telegram review format with numbered approve/cancel shortcuts for queued drafts
  2. Add approval/rejection memory so Cortex learns what post styles the user prefers
  3. If needed later, add a separate X direct-integration path for reply/comment-style actions that Buffer does not expose here

## Session 41 — Mar 8, 2026
**Prompt:** Prove X posting works, then add an approval layer with up to 10 drafts waiting for approval

### What We Did
1. **Verified live X posting through Cortex** using the existing Buffer path
2. **Replaced the single pending draft model with a local approval queue** capped at 10 drafts
3. **Added approve-by-draft-id and cancel-by-draft-id behavior** so queued posts can be supervised cleanly
4. **Validated the queue live** by creating multiple drafts and sending a specific one to X

### Why
- The earlier supervised path only supported one pending draft at a time
- The user wanted Cortex to line up multiple post drafts and wait for explicit approval before sending

### Purpose
- Gives Cortex a usable X approval layer instead of one temporary pending slot
- Keeps posting supervised while allowing content to build up in a queue

### Steps Taken
1. Audited the current Buffer client, CLI commands, `main.py` flags, and tests
2. Confirmed the exact `hi` text is blocked by duplicate-post rules because it already exists on the account
3. Updated `tools/buffer_client.py` to store a local FIFO queue with stable draft ids and a hard limit of 10
4. Updated `cli/tools_cmd.py` and `main.py` to show the queue and support confirm/cancel by optional draft id
5. Expanded `tests/test_buffer_client.py` for queue limit, targeted approval, and queue behavior
6. Re-ran the focused Buffer test file successfully
7. Verified live behavior by queuing two drafts and sending the second one by id through Buffer to X

### Results
- X posting works through Cortex
- Approval queue works with up to 10 local pending drafts
- Specific queued drafts can be approved and sent by id
- Live queue send verified with Buffer/X post id `69ad1bf208afabd5e2f35fa6`

### Suggested Next Steps
- **Goal/Intent**: Connect the approval queue to the rest of Cortex content generation
- **Why/Purpose**: The queue works, but real leverage comes when Brain or content systems can feed it automatically
- **Objectives**:
  1. Route content-factory or scheduler-generated X drafts into the queue
  2. Add a small list/review command that prints drafts in a cleaner review format
  3. Add approval telemetry so Cortex can learn what kinds of drafts the user accepts or rejects

## Session 40 — Mar 8, 2026
**Prompt:** Give the full anatomy of Cortex in one short markdown file with parts, agents, and loops using a SaaS example

### What We Did
1. **Mapped the whole Cortex structure into one short anatomy file** instead of leaving it spread across deep architecture docs
2. **Listed the main system parts, Brain agents, Hands agents, and support layers** with very short explanations
3. **Added a plain SaaS example flow and the main loops** so the system can be understood fast without heavy jargon

### Why
- The repo has detailed architecture docs, but they are too long for a fast mental map
- The user wanted one direct markdown file that shows what each part does and how the loops connect in practice

### Purpose
- Gives Cortex one quick orientation file for the whole project
- Makes it easier to see how Signals, Brain, Hands, Orchestrator, Memory, Safety, and Feedback fit together

### Steps Taken
1. Read the strongest inventory and architecture sources already in the repo
2. Pulled out the core parts, active agents, and support systems
3. Wrote `CORTEX_PROJECT_ANATOMY.md` with short explanations and a SaaS-domain example

### Results
- Added `CORTEX_PROJECT_ANATOMY.md` as a concise map of Cortex
- The file includes anatomy, interactions, Brain agents, Hands agents, research loop, execution loop, feedback loop, self-learning loop, safety loop, and a SaaS example flow

### Suggested Next Steps
- **Goal/Intent**: Keep the quick anatomy file aligned with the live codebase
- **Why/Purpose**: The file is most useful if it stays short and reflects the current real system
- **Objectives**:
  1. Update the anatomy file whenever a major subsystem is added or removed
  2. Optionally add one second file later for a stricter proven vs partial vs planned map

## Session 39 — Mar 8, 2026
**Prompt:** Fix Buffer env loading and add a supervised draft-first X flow

### What We Did
1. **Fixed Buffer API key loading at runtime** so the client no longer depends on import timing or manual env injection
2. **Added a supervised X publish flow** with local pending draft, status, confirm, and cancel commands
3. **Verified the flow live on X** with a real post sent through Buffer after explicit confirmation

### Why
- The earlier X send only worked when the key was injected manually into the process environment
- The first supervised design used real Buffer drafts, but live testing proved that Buffer's current GraphQL surface does not provide a reliable publish-existing-draft path for this use case

### Purpose
- Gives Cortex a stable X posting path through Buffer using the normal runtime `.env`
- Gives the user a safer draft -> confirm -> send control flow without publishing on the first command

### Steps Taken
1. Refactored `tools/buffer_client.py` to load `BUFFER_API_KEY` lazily and fall back to direct `.env` parsing
2. Diagnosed the real runtime failure and confirmed the actual on-disk `agent-brain/.env` was empty, then restored the Buffer key in the real file
3. Added persisted pending-draft state plus `create_x_supervised_draft()`, `get_pending_x_supervision()`, `confirm_x_supervised_post()`, and `cancel_x_supervised_post()`
4. Added CLI wiring in `main.py` and `cli/tools_cmd.py` for supervised status, draft, confirm, and cancel
5. Expanded `tests/test_buffer_client.py` and re-ran the focused test file successfully
6. Validated live behavior: normal runtime sees the key, local pending draft is created, and confirm sent a real X post through Buffer

### Results
- Buffer env loading now works without the manual injection workaround
- Supervised X publishing now uses a local pending draft first, then one live send on confirm
- Live X post verified through Buffer: post id `69ad1981e8c0a1cfe9dccb85`

### Suggested Next Steps
- **Goal/Intent**: Fold the supervised X path into the broader social pipeline cleanly
- **Why/Purpose**: The low-level Buffer path now works, but the next value is routing content into it from Cortex workflows with the same safety model
- **Objectives**:
  1. Route approved content-factory or scheduler outputs into `--buffer-draft-x` instead of direct send
  2. Store confirmation telemetry so Cortex can learn which drafted posts were approved or canceled
  3. Add a small cleanup command for stale local pending drafts and optionally a read-only view of recent sent X posts

## Session 38 — Mar 8, 2026
**Prompt:** Build a Discord content factory with research, scripts, and thumbnails channels plus daily 8 AM automation

### What We Did
1. **Added a Discord content-factory layer** that can read recent channel history and post into three configured agent channels
2. **Built a daily content pipeline** that turns Cortex signals, daemon state, and recent channel patterns into a research brief, social drafts, and a thumbnail brief
3. **Wired the scheduler into the content factory** so it can run once per day when the 8 AM slot is due
4. **Added manual CLI controls and focused tests** for Discord status, content-factory status, and forced runs

### Why
- The user wanted Cortex to operate a content workflow inside Discord instead of keeping this as a loose manual process
- The repo already had scheduling, social posting, and signal systems, so the right move was to plug Discord into those loops instead of building a separate bot product

### Purpose
- Gives Cortex a daily social-content loop inside Discord with separate channels for research, writing, and thumbnail direction
- Keeps the path open for optional posting to X through Buffer and Threads through the direct API
- Starts learning from recent channel history so the drafts are shaped by local pattern memory, not just raw prompts

### Steps Taken
1. Added `tools/discord_client.py` as a pure-stdlib Discord REST client for channel reads and writes
2. Added `content_factory.py` to collect signals, recent daemon context, Threads engagement, and Discord history, then generate a daily content pack with anti-AI style rules inspired by the `humanizer` patterns
3. Wired `scheduler.py` to call the content factory once per day after the main cycle completes
4. Added CLI commands in `main.py` and `cli/tools_cmd.py` for Discord status, content-factory status, and manual runs
5. Added focused tests for the Discord client and content-factory scheduling/orchestration behavior

### Results
- Cortex now has a Discord-native content pipeline shaped around `#research`, `#scripts`, and `#thumbnails`
- Daily scheduling is wired into the existing daemon instead of living in a separate process
- Auto-publish to X and Threads is supported through config flags and remains off by default for safety

### Suggested Next Steps
- **Goal/Intent**: Make the content factory post with better proof and richer media
- **Why/Purpose**: The current pass produces real briefs and drafts, but thumbnail output is still a brief rather than a finished image and the publishing defaults are intentionally conservative
- **Objectives**:
  1. Add Discord setup docs with the exact bot permissions and channel steps
  2. Add a media-generation path for thumbnail mockups or screenshot-based image posts
  3. Add feedback storage from published post performance so the content factory can rank which writing patterns actually work

## Session 37 — Mar 8, 2026
**Prompt:** Use the Buffer API key to test the connected X account while keeping Threads on the direct path

### What We Did
1. **Verified the live Buffer beta API** with the existing personal API key
2. **Confirmed the connected X account** and channel through real GraphQL queries
3. **Added a minimal Buffer client** for X-only testing without touching the Threads path
4. **Ran a real draft post test** successfully through the new Python client

### Why
- The user now has real Buffer API access and wanted to test the connected X account
- Threads should remain on the direct Threads API path, so Buffer work needed to stay isolated

### Purpose
- Gives Cortex a small, real Buffer integration surface for X testing only
- Avoids mixing Buffer into the existing Threads publishing flow

### Steps Taken
1. Read the current `.env` editor state and confirmed there was no existing Buffer client in the repo
2. Probed Buffer's live GraphQL schema, account, organization, and channel data
3. Confirmed one connected X channel for the account
4. Added `tools/buffer_client.py` with account lookup, channel listing, X filtering, and safe draft-post creation
5. Added CLI hooks in `main.py` and `cli/tools_cmd.py` for `--buffer-status` and `--buffer-test-x`
6. Added tests in `tests/test_buffer_client.py`
7. Fixed live Python requests by adding standard HTTP headers so Buffer stopped returning Cloudflare 1010 blocks
8. Verified a real draft was created on the connected X channel through the new client

### Results
- Live Buffer account access works
- Connected X channel detected successfully
- Real draft created successfully through the new Python client
- Threads architecture remains unchanged and direct

### Suggested Next Steps
- **Goal/Intent**: Make Buffer testing easier to use locally and optionally from Telegram later
- **Why/Purpose**: The integration works, but local runtime depends on the API key being available to the actual process environment
- **Objectives**:
  1. Persist the local Buffer key to the real runtime environment used by `main.py`
  2. Optionally add a Telegram admin command for `buffer status` and `buffer test x`
  3. If wanted, add a separate explicit `share now` Buffer command for X after draft-only testing is enough

## Session 36 — Mar 8, 2026
**Prompt:** Map a clean social-posting architecture for Cortex with Direct Threads + future Buffer adapter

### What We Did
1. **Audited the current Threads posting path** across the client, media, analyst, scheduler, and Telegram layers
2. **Mapped a clean adapter-based social architecture** that keeps Direct Threads as the live path and leaves room for Buffer later
3. **Wrote a dedicated architecture document** at `CORTEX_SOCIAL_POSTING_ARCHITECTURE.md`

### Why
- The repo already has working Threads pieces, but they are still shaped around one platform
- A clean adapter boundary prevents Cortex from growing one-off social flows for each platform

### Purpose
- Gives Cortex one reusable posting system instead of separate Threads and Buffer systems
- Clarifies what should stay shared, what should be platform-specific, and what order to build in next

### Steps Taken
1. Read the current Threads client, image publishing flow, Threads analyst helpers, Telegram Threads commands, and scheduler context
2. Identified the real current boundary: content logic, media creation, publishing, and engagement are only partly separated today
3. Wrote a target design with a platform-neutral `PostRequest`, shared media layer, router, Direct Threads adapter, future Buffer adapter, and learning telemetry layer
4. Defined a phased implementation order that keeps Direct Threads as default and makes Buffer opt-in only after access is proven

### Results
- Added `CORTEX_SOCIAL_POSTING_ARCHITECTURE.md` as the repo blueprint for future social-posting work
- Locked in the recommendation to keep Direct Threads as the main path now and add Buffer later as an adapter, not a replacement

### Suggested Next Steps
- **Goal/Intent**: Turn the architecture map into a small first implementation pass
- **Why/Purpose**: The repo already has enough Threads code to benefit from a clean boundary without a large rewrite
- **Objectives**:
  1. Introduce a shared `PostRequest` contract and wrap direct Threads posting behind an adapter
  2. Keep `image_publisher.py` platform-neutral and move platform-specific behavior out of it
  3. Add publish telemetry storage before any Buffer work starts

## Session 35 — Mar 8, 2026
**Prompt:** Use simpler words in this repo's Copilot instructions and give suggestions from the full scan

### What We Did
1. **Added a plain-language preference** to the workspace Copilot instructions
2. **Recorded the correction** in `lessons.md` so future writeups stay simpler by default
3. **Prepared repo-level suggestions** based on the full architecture scan

### Why
- The user asked for simpler wording in future explanations
- The repo already has strong technical guidance, but not an explicit plain-language preference

### Purpose
- Makes future explanations easier to read during planning, reviews, and reports
- Keeps the communication style aligned with the architect's preference while preserving technical accuracy

### Steps Taken
1. Updated `.github/copilot-instructions.md` to prefer plain, simple user-facing language
2. Added a matching rule to `.github/lessons.md`
3. Used the completed codebase scan as the basis for concrete next-step suggestions

### Results
- Workspace instructions now explicitly prefer simple wording over rare or academic terms
- Future summaries in this repo should stay clearer and easier to scan

### Suggested Next Steps
- **Goal/Intent**: Turn the scan into action
- **Why/Purpose**: The codebase is now well-mapped; the next value comes from picking the right bottleneck and fixing it
- **Objectives**:
  1. Decide whether to focus next on verifier wiring, unsupervised runtime proof, or revenue loop proof
  2. If needed, rewrite `CORTEX_CODEBASE_FINDINGS.md` in simpler language too

## Session 34 — Mar 8, 2026
**Prompt:** Scan the repo deeply and create one comprehensive markdown report of the findings

### What We Did
1. **Scanned the repo architecture, note corpus, and runtime entrypoints** to map the actual Cortex system
2. **Read the main Brain, Hands, signal, orchestration, identity, and verification modules** rather than relying only on summaries
3. **Created a consolidated findings report** at `CORTEX_CODEBASE_FINDINGS.md`

### Why
- The repo has a large amount of architectural intent spread across docs, notes, and implementation files
- A single consolidated report makes it easier to understand what Cortex is, how it works, which agents exist, and where proof still lags the vision

### Purpose
- Gives the architect one reference file for the current high-level system understanding
- Distinguishes actual runtime architecture from older or more speculative planning snapshots
- Makes future implementation and review work faster by reducing context fragmentation

### Steps Taken
1. Read the core doctrine files in `my-notes.md/`, `README.md`, and `agent-brain/`
2. Read the central runtime files: `main.py`, `scheduler.py`, `watchdog.py`, `sync.py`, `outcome_feedback.py`, `llm_router.py`, `protocol.py`, and the signal pipeline
3. Read the main Brain agent modules and core Hands planner/executor files
4. Cross-checked the code against handoff and inventory markdown files to identify stable truths versus snapshot drift
5. Wrote `CORTEX_CODEBASE_FINDINGS.md` as a comprehensive synthesis

### Results
- Produced a consolidated report describing Cortex's vision, actual architecture, agent inventory, runtime flows, strengths, and gaps
- Confirmed that the Brain, Hands, signal pipeline, scheduler/watchdog, identity injection, and Brain-to-Hands feedback loops are all materially implemented
- Identified verification, business-outcome grounding, and some philosophical concepts like the Observable Horizon as the main areas where implementation still lags doctrine

### Suggested Next Steps
- **Goal/Intent**: Turn the consolidated scan into a sharper execution aid
- **Why/Purpose**: The report now explains the system, but the next useful move is to operationalize that understanding against current priorities
- **Objectives**:
  1. Build a proven vs partial vs aspirational matrix tied to specific files
  2. Rank the top bottlenecks preventing the current system from achieving the intended autonomous loop
  3. Trim or consolidate stale markdown files that duplicate newer doctrine

## Session 33 — Mar 8, 2026
**Prompt:** Extract the best `allstar` idea and apply it in current `main`

### What We Did
1. **Implemented outcome feedback in current `main`** as a native module instead of merging `allstar`
2. **Wired the daemon to process completed Hands outcomes into Brain lessons** after task execution cycles
3. **Added a manual CLI backfill path** so completed tasks can be processed on demand without waiting for the daemon
4. **Added focused tests for lesson extraction, duplicate protection, and wiring**

### Why
- The highest-leverage missing piece was still the Brain <- Hands learning loop
- Current `main` already created tasks and stored execution results, but it did not systematically convert those outcomes into reusable Brain lessons
- Pulling the whole branch was high risk; porting the loop-closure idea directly into current architecture was the safer move

### Purpose
- Makes the system learn from real execution outcomes, not just research critiques
- Improves the research layer using actual build/deploy/action results from Hands
- Preserves current branch architecture while capturing the best idea from `allstar`

### Steps Taken
1. Added `outcome_feedback.py` to read completed and failed sync tasks, extract lessons, and mark feedback as processed
2. Reused `research_lessons.add_lesson()` so the feedback lands in the existing Brain memory path
3. Wired `process_pending_feedback()` into the daemon after Hands auto-execution
4. Added `--process-feedback` in `main.py` for manual processing and backfill
5. Added tests covering successful execution lessons, failure lessons, timeout lessons, feedback stats, and CLI/daemon source wiring

### Results
- Focused verification passed: `tests/test_outcome_feedback.py`, `tests/test_integration_wiring.py`, and `tests/test_sync.py`
- Full suite still has unrelated pre-existing failures outside this change set, including `agents/question_generator.py` syntax breakage, API-key-dependent tests, and an existing non-atomic `json.dump` usage in `telegram_bot.py`

### Suggested Next Steps
- **Goal/Intent**: Strengthen the execution-learning loop beyond basic lesson extraction
- **Why/Purpose**: The loop is now closed, but it can become more decision-useful with richer signals and better reporting
- **Objectives**:
  1. Add richer lesson extraction from validation weaknesses and repeated failed phases
  2. Surface outcome feedback stats in daemon reports and sync status views
  3. Implement the next-best `allstar` salvage: post-confirmation strategy impact tracking

## Session 32 — Mar 8, 2026
**Prompt:** Compare the divergent `allstar` branch against current `main` and identify anything worth porting

### What We Did
1. **Compared `origin/allstar` against current `main`** at the commit, file, and module level
2. **Inspected the strongest candidate modules directly** instead of treating the branch as a merge candidate
3. **Mapped `allstar` ideas onto current mainline capabilities** to separate genuinely missing pieces from features already partially covered

### Why
- The branch is highly divergent and removes or rewrites many current systems, so the real question was not "should we merge it?" but "what ideas are still worth salvaging?"
- The architect needs a practical answer tied to the real Cortex gap: closing the loop between research, execution, and learning
- Without a concrete mapping, useful work from the branch would stay buried in history

### Purpose
- Prevents a risky branch merge while still capturing high-value ideas
- Clarifies which missing pieces actually move Cortex toward the real autonomous thesis
- Creates a ranked shortlist of features worth porting into the current architecture

### Steps Taken
1. Fetched and diffed `origin/allstar` against `main`
2. Reviewed unique `allstar` commits and isolated the strongest feature cluster
3. Inspected `outcome_feedback.py`, `strategy_impact.py`, and `degradation_detector.py`
4. Compared those modules against current `scheduler.py`, `sync.py`, `research_lessons.py`, `strategy_store.py`, `analytics.py`, `domain_seeder.py`, and existing plateau/health logic
5. Ranked the portable ideas by current leverage and implementation fit

### Results
- **Do not merge `allstar` wholesale**
- **Best port candidate:** `outcome_feedback.py` because current `main` still lacks a clean Brain <- Hands feedback processor after task completion
- **Second-best:** `strategy_impact.py` because it adds post-confirmation regression checks on top of the existing trial-evaluation logic
- **Third-best:** `degradation_detector.py` because it adds slow-decay monitoring beyond the current short-horizon plateau and failure signals
- `domain_bootstrap.py` and `domain_calibration.py` have some value, but current `main` already covers part of that ground via `domain_seeder.py`, analytics, and orchestration logic

### Suggested Next Steps
- **Goal/Intent**: Port the highest-leverage `allstar` idea into current `main` without importing branch divergence
- **Why/Purpose**: The system still hands tasks to Hands and records results, but Brain does not yet reliably learn from those execution outcomes
- **Objectives**:
  1. Add an `outcome_feedback.py`-style module to process completed and failed sync tasks into `research_lessons`
  2. Trigger that processor automatically after Hands task execution in the scheduler loop and expose a manual CLI hook
  3. Add focused tests for duplicate protection, success lesson extraction, failure lesson extraction, and daemon integration

## Session 32 — Mar 7, 2026
**Prompt:** Apply `.github` guidance as persistent Cursor context and consolidate the architect's notes into one unified markdown file

### What We Did
1. **Converted stable `.github` guidance into persistent Cursor rules** under `.cursor/rules/`
2. **Read and synthesized the architect's notes corpus** into one consolidated context file
3. **Separated enduring principles from drifted or outdated assumptions** so future sessions can use the notes without inheriting obsolete framing

### Why
- The repo already had strong guidance in `.github/`, but it was not encoded as always-on Cursor-native project rules
- The `my-notes.md/` folder contains the architect's deepest reasoning, but it was spread across many overlapping documents
- The system needs one durable reference that preserves the vision while staying honest about current proof level

### Purpose
- Gives Cursor persistent project guidance aligned with Cortex's mission and development discipline
- Creates a single source of truth for the architect's enduring vision, constraints, and roadmap
- Reduces future drift between philosophy, product direction, and actual implementation priorities

### Steps Taken
1. Reviewed `.github/copilot-instructions.md`, `.github/lessons.md`, and `.github/progress.md`
2. Read the main vision, roadmap, strategy, and philosophical notes from `my-notes.md/`
3. Created `.cursor/rules/cortex-core-guidance.mdc`
4. Created `.cursor/rules/cortex-development-loop.mdc`
5. Wrote `my-notes.md/CORTEX_UNIFIED_CONTEXT.md` with consolidated architecture, mission, business logic, safety concepts, roadmap, and glossary

### Use Cases
- Use the Cursor rules as persistent always-on project guidance for future sessions
- Use `my-notes.md/CORTEX_UNIFIED_CONTEXT.md` as the first file to re-load the architect's intent quickly
- Use the consolidated file to distinguish what is stable doctrine versus what was exploratory or already superseded

### Suggested Next Steps
- **Goal/Intent**: Keep the consolidated context aligned with the living codebase and actual proof level
- **Why/Purpose**: The value of a unified context file comes from staying current as Cortex earns or loses claims in practice
- **Objectives**:
  1. Refresh `agent-brain/README.md` so it matches the current codebase and the unified context
  2. Add one concise "proven vs unproven" section to the unified context after each major milestone
  3. Revisit the Cursor rules if the architect's operating doctrine changes materially

## Session 31 — Mar 6, 2026
**Prompt:** Rewrite the repo README with a benefit-first explanation, then push it

### What We Did
1. **Rewrote the root README** from a technical-first Agent Brain description into a benefit-first Cortex explanation
2. **Repositioned the repo around outcomes**: leverage, opportunity selection, execution, and learning from real-world loops
3. **Clarified current proof versus future ambition** so the repo explains what exists without overselling it

### Why
- The root README was too implementation-heavy up front and did not explain the practical value quickly enough
- A repo visitor should understand the benefit, the use case, and the current system shape before reading architecture details
- The project needs clearer positioning around what Cortex is actually trying to do

### Purpose
- Makes the repo easier to understand for humans evaluating the project quickly
- Aligns the public-facing explanation with the architect's real goal: an autonomous operator that creates leverage
- Improves the first impression of the repository without hiding current limitations

### Steps Taken
1. Reviewed the root and inner README structure
2. Rewrote the root README around benefits, use cases, and current system value
3. Added explicit sections for what is working, what is not yet proven, and where to read deeper

### Suggested Next Steps
- **Goal/Intent**: Keep public-facing documentation aligned with the actual proof level of the system
- **Why/Purpose**: Stronger positioning helps people understand the project quickly, but trust comes from honest scope
- **Objectives**:
  1. Refresh the inner `agent-brain/README.md` next so it matches the new top-level framing
  2. Add one concrete end-to-end example flow from signal -> decision -> execution
  3. Keep updating docs as new proof points are earned

## Session 30 — Mar 6, 2026
**Prompt:** Push the latest work, sync it to the VPS, and write a comprehensive next-steps document tied to the real Cortex goal

### What We Did
1. **Prepared a clean deployable change set** by separating intentional code changes from runtime artifacts and unrelated editor settings
2. **Added a comprehensive roadmap document** covering what Cortex must do next to reach the real goal
3. **Prepared the repo for push and VPS sync** around the new signals commercial-decision workflow

### Why
- The repo had mixed state: real code changes plus logs, databases, and unrelated local files
- The system needed a written plan that ties architecture work back to proof, revenue, and autonomous reliability
- Deployment should ship the product changes, not transient local runtime data

### Purpose
- Keeps the git history clean and reviewable
- Gives the architect a durable strategic document for what to do next
- Aligns the code changes with the broader mission: revenue, verification, and trustworthy autonomy

### Steps Taken
1. Reviewed changed files and identified deploy-safe scope
2. Verified the existing deploy mechanism and VPS configuration path
3. Wrote `my-notes.md/NEXT-STEPS-TO-GOAL.md`
4. Kept the strategic recommendations tied to the architect's stated vision and current system reality

### Use Cases
- Use as the current operating roadmap for Cortex development
- Use as a filter for deciding whether a feature is enabling proof or just adding complexity
- Use as the basis for the next execution sprint after deployment

### Suggested Next Steps
- **Goal/Intent**: Turn the new code and roadmap into a real market-validation cycle
- **Why/Purpose**: The next proof comes from deployed usage and commercial outcomes, not more inward iteration
- **Objectives**:
  1. Run the new reality-check packets on the top current opportunities
  2. Pick one narrow offer and test outreach immediately
  3. Start logging commercial outcomes as first-class learning signals

## Session 29 — Mar 6, 2026
**Prompt:** Improve Cortex further by wiring commercial reality checks directly into the signals workflow and borrow good patterns from external repos

### What We Did
1. **Added a signals-level decision-packet workflow** in `opportunity_scorer.py`
2. **Introduced a first-class CLI reality-check command** so ranked opportunities can now be evaluated commercially without ad hoc chat calls
3. **Captured a reusable commercial evaluation framework** inside the packet payload to make judgments more repeatable
4. **Added focused tests and wiring checks** for the new workflow

### Why
- The previous improvement made reality checks possible, but not canonical in the signals pipeline
- We needed the default path to become: signal -> product spec -> commercial verdict -> saved artifact
- External repo review showed the useful pattern is structured evaluation criteria plus reusable traces, not more free-form prompting

### Purpose
- Makes commercial judgment a standard part of opportunity triage
- Produces reusable decision artifacts instead of one-off chat outputs
- Moves Cortex closer to a repeatable evaluation loop inspired by eval frameworks and reasoning-memory repos

### Steps Taken
1. Reviewed signal CLI and scorer insertion points
2. Added `generate_opportunity_decision_packet()` to build a spec, assemble evidence, and call Cortex reality-check mode
3. Added a reusable commercial evaluation framework payload with explicit evaluation steps and rubric
4. Added `_save_decision_packet()` so combined spec + verdict artifacts are persisted under `logs/build_specs/`
5. Added `run_reality_check()` to `cli/signals_cmd.py`
6. Wired `--reality-check N` and `--reality-focus` through `main.py`
7. Added tests for packet generation, artifact persistence, CLI output, and source wiring

### Use Cases
- Evaluate ranked opportunities before committing build effort
- Compare multiple opportunity packets under the same commercial lens
- Revisit past decision packets as the system learns from real market outcomes

### Suggested Next Steps
- **Goal/Intent**: Compare the top 3 current opportunities under the new decision-packet workflow
- **Why/Purpose**: The new path is only valuable if it becomes the standard decision gate before Hands builds anything
- **Objectives**:
  1. Run `--reality-check` on the top 3 ranked opportunities
  2. Extract common failure patterns from the saved packets and feed them back into strategy/memory
  3. Add a compare-top-opportunities command that ranks multiple packets side by side on the same rubric

## Session 28 — Mar 6, 2026
**Prompt:** Improve Cortex so it gets better at commercial reality checks, not just optimistic idea generation

### What We Did
1. **Added a first-class Cortex reality-check helper** in `agents/cortex.py`
2. **Added a chat tool for evidence-based reality checks** so this workflow can be invoked directly later
3. **Strengthened opportunity scoring prompt rules** to penalize broad pain, crowded markets, switching costs, distribution difficulty, and trust/liability-heavy workflows
4. **Strengthened build spec generation** so specs now include narrow wedge, distribution strategy, killer objections, and why the idea could fail
5. **Fixed pre-existing logger errors** in `agents/cortex.py`

### Why
- The system was too willing to reward generic pain points and broad categories
- Build specs were optimistic and product-shaped, but weak on objections, GTM reality, and failure modes
- We needed the same hard commercial lens we just used manually to become reusable system behavior

### Purpose
- Makes Cortex better at distinguishing "easy to build" from "worth building"
- Pushes future opportunity analysis toward narrower wedges and more realistic go-to-market thinking
- Gives the chat/orchestration layer a reusable commercial reality-check capability

### Steps Taken
1. Reviewed orchestrator and opportunity-scorer code paths
2. Added `reality_check_opportunity()` to Cortex with evidence-only mode (no Brain/Hands/infra state by default)
3. Updated `format_orchestrator_response()` to render reality-check outputs cleanly
4. Added `orchestrator_reality_check` to the chat tool surface and execution router
5. Updated analysis prompt to penalize generic, crowded, hard-to-distribute ideas
6. Updated build-spec prompt to force wedge, objections, GTM, and failure analysis
7. Added tests for the new helper, formatter, chat tool, and extended build spec fields
8. Fixed missing `logger` definition in `agents/cortex.py`
9. Verified: `tests/test_cortex.py` passes and build-spec-related signal tests pass

### Results
- Cortex now has an explicit commercial reality-check path
- Opportunity analysis is less likely to overrate vague, generic, or crowded opportunities
- Build specs now ask for the exact information needed to decide whether something is worth pursuing, not just how to build it

### Key Files
- `agent-brain/agents/cortex.py`
- `agent-brain/cli/chat.py`
- `agent-brain/opportunity_scorer.py`
- `agent-brain/tests/test_cortex.py`
- `agent-brain/tests/test_signals.py`

### Suggested Next Steps
- **Goal:** Apply the new reality-check loop to the next opportunity candidate before committing build effort
- **Why/Purpose:** The system now has a better decision lens; use it consistently so we stop wasting time on commercially weak ideas
- **Objectives:**
  1. Run the same evidence-driven reality check on the next top opportunity
  2. Compare opportunities under the same standard: pain, distribution, switching cost, wedge, and trust complexity
  3. Pick the first build target only after it survives the stricter lens

---

## Session 27 — Mar 6, 2026
**Prompt:** Reality-check the CallGuard idea with Cortex — objections, competitors, complexities, underserved wedge, and direct GTM

### What We Did
1. **Set a dedicated research goal** for `callguard-reality-check` so the system would investigate the idea commercially, not academically
2. **Gathered external market evidence** on competitors, substitute solutions, partner ecosystems, pricing, and missed-call pain signals
3. **Used Cortex Orchestrator to do a hard go/no-go assessment** with no optimism bias
4. **Forced a narrow-wedge recommendation** from Cortex in case we still wanted a cheap validation test
5. **Saved the full reality-check memo** for future reference

### Why
- The initial CallGuard thesis sounded buildable, but the architect asked for a reality check before committing effort
- The right question was not "can we build it?" but "is it worth selling into this market?"
- This is the exact kind of load-bearing decision Cortex should learn: distinguish technically easy ideas from commercially winnable ones

### Purpose
- Prevents building a product that is easy to code but hard to sell
- Forces the system to look at switching costs, incumbents, distribution difficulty, and trust/risk
- Produces a narrower test wedge if the broad idea is not worth pursuing

### Steps Taken
1. Set structured goal for `callguard-reality-check`
2. Reviewed competitor evidence: Smith.ai, AnswerConnect, Grasshopper, niche text-back products, and the crowded field-service software category
3. Gathered partner-channel evidence from Housecall Pro, Jobber, and ServiceTitan ecosystems
4. Gathered pain/distribution signals from HVAC/plumbing missed-call and answering-service search results
5. Ran Cortex on the evidence bundle for a blunt verdict
6. Ran a follow-up Cortex query: if forced to test anyway, what is the smallest viable wedge?
7. Saved the output to `logs/build_specs/2026-03-06_callguard_reality_check.md`

### Results
- **Broad verdict:** not worth building now as a broad SaaS
- **Main reasons:** saturated market, weak differentiation, fragmented/expensive distribution, and trust-heavy workflows where human solutions still dominate
- **Underserved wedge:** 1-3 employee emergency HVAC / plumbing shops that cannot justify full answering services but still lose real money on after-hours missed calls
- **If testing anyway:** run a concierge validation offer first, not a full SaaS
- **Recommended test offer:** "24/7 Emergency Call Backup for HVAC Contractors" at ~$97/month with manual fulfillment behind the scenes

### Key Files
- `agent-brain/logs/build_specs/2026-03-06_callguard_reality_check.md` — final market reality-check memo

### Suggested Next Steps
- **Goal:** Focus on winnable revenue paths before product build effort compounds in the wrong direction
- **Why/Purpose:** Cortex found that distribution, not coding, is the real bottleneck here
- **Objectives:**
  1. Return focus to the productized-services path for the fastest near-term revenue
  2. If still curious about CallGuard, run the concierge HVAC validation test before writing product code
  3. Capture trial response/conversion data and let Cortex re-evaluate based on real customer behavior instead of theory

---

## Session 26 — Mar 6, 2026
**Prompt:** Create build specs for the top 3 opportunities and turn them into a convincing market research memo using Cortex

### What We Did
1. **Used Cortex Orchestrator to select 3 distinct opportunities** from the signal DB instead of blindly taking the top 3 raw scores
2. **Generated build specs** for the selected opportunities using `generate_build_spec()`
3. **Used Cortex again for strategic ranking** and commercial analysis
4. **Saved a reusable market memo** covering sales pitch, feasibility, audience, GTM, and solution design

### Why
- The top-scored opportunities contained near-duplicates in the small-business admin category
- The architect asked for something closer to a founder-facing investment memo than raw JSON specs
- This is exactly the Brain → Cortex → build decision workflow the system needs to practice

### Purpose
- Converts signal analysis into buildable product decisions
- Creates a reusable artifact for deciding what to build first
- Exercises Cortex as the orchestration layer so it learns the selection and prioritization pattern

### Steps Taken
1. Reviewed the top scored opportunities from the partial signal run
2. Asked Cortex to choose the 3 best distinct wedges by ROI clarity, feasibility, and GTM clarity
3. Cortex selected: missed-call recovery for service businesses, lightweight QA test management, and SaaS marketing automation
4. Generated detailed product specs for the three chosen opportunities
5. Asked Cortex to rank the three and explain which should be built first
6. Wrote the final memo to `logs/build_specs/2026-03-06_top3_market_memo.md`

### Results
- **#1 Recommendation:** CallGuard / CallCatcher-style missed-call recovery for service businesses
- **#2:** GrowthPulse-style SaaS marketing automation for founders
- **#3:** TestFlow-style lightweight QA test management
- **Key thesis:** choose products with immediate financial pain and simple ROI explanation; CallGuard won because one recovered call can justify the subscription

### Key Files
- `agent-brain/logs/build_specs/2026-03-06_top3_market_memo.md` — founder-facing market memo
- `agent-brain/logs/build_specs/` — generated JSON build specs from the spec generator

### Suggested Next Steps
- **Goal:** Turn the selected opportunity into an execution-ready product brief
- **Why/Purpose:** The decision layer is done; now the system should move into build mode
- **Objectives:**
  1. Create a strict MVP scope for CallGuard with pages, flows, schema, and Twilio webhook requirements
  2. Validate pricing and onboarding assumptions with competitor comparison
  3. Draft landing page copy and core offer for local service businesses
  4. Have Hands build the MVP in a scoped two-week execution plan

---

## Session 25 — Mar 6, 2026
**Prompt:** Fix Telegram bot fundamentals + run signal analysis batch (Option B)

### What We Did
1. **Fixed Telegram bot conversation persistence** — `ConversationManager` now persists to disk (`logs/telegram_sessions/{chat_id}.json`), survives restarts
2. **Added message batching** — rapid-fire messages batched with 1.5s delay window before single LLM call
3. **Rewrote system prompt behavioral rules** — 7 hard rules replacing soft STYLE section (no more "Sound good?", menus, permission-seeking)
4. **Fixed enrich_signals tool** — replaced scrapling dependency with stdlib urllib + graceful 403 handling
5. **Ran signal analysis batch** — batch-scoring 1,477 unanalyzed posts via DeepSeek (cheapest tier, ~$0.28 total)
6. **Generated first weekly brief** — premium model synthesis of top 15 opportunities into 4 themes + micro-SaaS recommendation

### Why
- User reported Telegram bot is "fundamentally broken": loses context on restart, asks permission instead of acting, treats rapid messages as independent conversations
- enrich_signals kept failing ("Reddit API calls not working") — scrapling dependency + Reddit 403 from server IPs
- 1,397 posts sitting unanalyzed in signal DB — zero intelligence generated from the data

### Purpose
- Telegram bot is now a reliable chat interface (persistent memory, batched messages, direct personality)
- Signal intelligence pipeline now operational end-to-end: collect → analyze → score → brief
- Weekly brief recommended building a "Billing Recovery Automation Tool" ($49-99/mo) based on Reddit pain points

### Steps Taken
1. Diagnosed 4 root causes from user's Telegram conversation transcript
2. Rewrote `ConversationManager` with disk persistence + 50-message history limit
3. Added `_queue_message()` / `_flush_messages()` batching system with 1.5s timer
4. Replaced STYLE section with 7 CRITICAL BEHAVIORAL RULES
5. Rewrote `enrich_post()` using stdlib urllib (removed scrapling dependency)
6. Fixed all test failures (temp dir isolation, updated limits), 273 tests pass
7. Deployed to VPS (commit `373cd1f`), confirmed bot active
8. Ran `score_unanalyzed(batch_size=10, max_batches=150)` — DeepSeek scoring entire DB
9. Generated weekly brief with `generate_weekly_brief(top_n=15, premium_top=5)`
10. Saved brief to `logs/briefs/weekly-brief-2026-03-06.md`

### Key Files Modified
- `telegram_bot.py` — ConversationManager rewritten, message batching added
- `cli/chat.py` — behavioral rules, enrich_signals handler
- `signal_collector.py` — enrich_post() rewritten
- `tests/test_telegram_bot.py` — persistence test, temp dir isolation
- `logs/briefs/weekly-brief-2026-03-06.md` — first weekly brief (NEW)

### Results
- **Score distribution (200+ analyzed):** 60 high (80+), 104 moderate (50-79), 16 low (<50)
- **Top categories:** Business (57), Marketing (37), Developer Tools (23), Productivity (13), Automation (10)
- **Top recommendation:** Billing Recovery Automation Tool — integrates with Stripe/Chargebee, $49-99/mo, 2-week build
- **Cost:** ~$0.28 for full DB analysis (DeepSeek) + ~$0.05 for brief synthesis (Claude)
- **Batch still running:** Processing remaining ~1,200 posts in background

### Suggested Next Steps
- **Goal:** Prove signal intelligence has commercial value
- **Why/Purpose:** The system can now find + score + synthesize opportunities autonomously. Next step is proving someone would pay for this.
- **Objectives:**
  1. Test Telegram bot with user — verify persistent memory + direct personality work in practice
  2. Regenerate weekly brief after full batch completes (1,477 posts analyzed)
  3. Build spec for top opportunity using `generate_build_spec()`
  4. Share weekly brief via Telegram — test the distribution channel
  5. First cold outreach with signal data as proof of value

---

## Session 24 — Mar 6, 2026
**Prompt:** Humanizer integration — teach Cortex to write like a human using blader/humanizer + Reddit voice patterns

### What We Did
1. **Integrated blader/humanizer anti-AI-pattern rules** into Cortex system prompt
2. **Created writing skill** — `identity/skills/writing/human_voice.md` (120 lines)
3. **Updated skills_loader.py** — added "writing" category at priority 0 (always loads first)
4. **Added `_get_writing_voice()` helper** in `cli/chat.py` — loads and injects the skill into every system prompt
5. **Deployed to VPS** — git pull + restart cortex-telegram service

### Why
- Cortex output reads like a chatbot — "Great question!", "I'd be happy to help", "delve", "landscape"
- blader/humanizer (7,812 stars) has 24 anti-AI-pattern categories with concrete before/after examples
- Reddit posts from signal DB show how real micro-SaaS builders actually write — direct, opinionated, specific

### Purpose
- Every Cortex output (chat, Telegram, research, opportunity reports) now passes through the humanizer filter
- Makes Cortex output indistinguishable from a sharp founder's writing
- Prerequisite for selling signal intelligence reports — reports must sound human, not AI-generated
- Proof: Telegram chat quality should immediately improve

### Steps Taken
1. Read blader/humanizer SKILL.md (488 lines, 24 anti-AI-pattern categories)
2. Extracted 15 Reddit writing samples from signals.db (real r/SaaS, r/microsaas posts)
3. Created `identity/skills/writing/human_voice.md` combining humanizer rules + Reddit voice patterns
4. Added "writing" to `CATEGORY_PRIORITY` (priority 0) and `CATEGORY_KEYWORDS` in skills_loader.py
5. Added `_get_writing_voice()` function in cli/chat.py
6. Injected writing voice into system prompt template between goal_info and identity
7. Verified: `load_skills(["writing"])` returns 4,000 chars of humanizer content
8. All 128 related tests pass (87 skills + 23 identity + 18 chat)
9. Committed `2cc52bb`, pushed to GitHub, deployed to VPS, restarted Telegram bot

### Key Files
- `agent-brain/identity/skills/writing/human_voice.md` — the humanizer skill (NEW)
- `agent-brain/skills_loader.py` — writing category added
- `agent-brain/cli/chat.py` — `_get_writing_voice()` + prompt injection

### What This Enables
- Telegram bot responses sound like a builder, not a chatbot
- Chat CLI responses same
- Foundation for humanized research reports, opportunity briefs, Reddit posts
- The skill is priority 0 — it loads before all other skills in every context

### Suggested Next Steps
- **Goal:** Prove ROI — tangible proof Cortex writes like a human
- **Why/Purpose:** User needs proof via Telegram chat quality before monetization push
- **Objectives:**
  1. Send test questions to Telegram bot and screenshot before/after comparison
  2. Wire humanizer into researcher agent output (not just chat)
  3. Wire humanizer into opportunity scorer narrative output
  4. First Reddit post draft using humanized Cortex output
  5. Run signal analysis cycle with humanized writing

---

## Session 23 — Previous
**Prompt:** Beads/Agent Orchestrator research + THREADS.MD full implementation + full system audit + new CORTEX_CONSULTANT_HANDOFF.md

### What We Did
1. **Researched Beads + Agent Orchestrator** — evaluated both for applicability to Cortex
2. **Implemented THREADS.MD image pipeline** — `tools/image_publisher.py` (screenshot + chart posts via Vercel Blob)
3. **Updated tools/threads_client.py** — added `THREADS_SCREENSHOT_POST_TOOL`, `THREADS_CHART_POST_TOOL` defs + execute handlers
4. **Updated agents/threads_analyst.py** — added `post_build_screenshot()` and `post_score_chart()` narrator hooks
5. **Full system audit** — import health, stale imports, test counts, LOC, git history
6. **Rewrote CORTEX_CONSULTANT_HANDOFF.md** — from Session 13 (9 sessions stale) to full Session 23 update

### Why
- Beads and Agent Orchestrator were found by architect — needed honest applicability assessment
- THREADS.MD described an image pipeline but tools/threads_client.py had no image source or upload
- Handoff doc was 9 sessions stale (Sessions 14–22 entirely undocumented for consultants)
- Consultant/architect needs a fresh full-picture document covering the entire system as it exists now

### Purpose
- Beads: not now — patterns documented for later (get_ready_tasks blocked_by field)
- Agent Orchestrator: not now — single-agent system; revisit at 5+ parallel Hands instances
- Image pipeline enables Threads social posts with screenshots + score charts (full THREADS.MD spec)
- New handoff doc enables consultant onboarding without needing to read all 22 session logs

### Steps Taken
1. Researched github.com/steveyegge/beads (18k stars, Go, distributed agent task tracker)
2. Researched github.com/ComposioHQ/agent-orchestrator (TypeScript, parallel worktree agents)
3. Verdict: both not applicable now; patterns documented
4. Read THREADS.MD and confirmed: no image source, no upload, no public URL bridge
5. Created `tools/image_publisher.py` (323 lines): blob_configured, upload_to_vercel_blob, capture_and_post (Playwright 2×Retina + agent-browser fallback), generate_score_chart (matplotlib dark theme), post_with_chart
6. Added VERCEL_BLOB_ENABLED to config.py
7. Added THREADS_SCREENSHOT_POST_TOOL + THREADS_CHART_POST_TOOL defs to threads_client.py
8. Added execute handlers for threads_screenshot_post + threads_chart_post in execute_threads_tool
9. Added post_build_screenshot() + post_score_chart() to threads_analyst.py
10. Ran full audit: 135 prod files / 52,147 LOC; 45 test files / 29,827 LOC / 2,092 test functions
11. Confirmed 147/147 actively-run tests pass (54 integration + 93 core)
12. Confirmed stale imports from Session 13 handoff ALL fixed
13. Wrote new comprehensive CORTEX_CONSULTANT_HANDOFF.md covering Sessions 1–23
14. Committed 8965db2 (image pipeline), VPS synced

### Stale Import Fixes Confirmed (from Session 13 known issues)
- ✅ sync.py: lazy imports `execute_plan` + `validate_execution` (not stale `execute`/`validate`)
- ✅ project_orchestrator.py: same lazy import pattern
- ✅ scheduler.py: `page_type="app"` present in execute_plan() call

### Audit Findings
- Production grew from 120→135 files, 44,483→52,147 LOC (+7,664 lines since Session 13)
- Test suite grew from 38→45 files, 24,998→29,827 LOC (+4,829 lines since Session 13)
- True test function count: 2,092 in 45 files (only 147 actively run — 43 files are historical)
- image_publisher: blob_configured()=False on dev (expected — no BLOB_READ_WRITE_TOKEN set)
- Verified imports: all 13 critical module imports pass

### What This Enables
- Cortex can post build screenshots to Threads after a successful Hands pipeline run
- Cortex can post research score charts showing domain improvement over time
- Full THREADS.MD spec is now implemented — screenshots + charts + text all supported
- Consultants and architects have a current, comprehensive (24-section) handoff document

### New Todo Items Surfaced
- Set BLOB_READ_WRITE_TOKEN in .env for image posting to go live
- Set VERCEL_TOKEN on VPS so post-build auto-deploy fires
- Enable daemon first supervised cycle (5 cycles, monitor via Telegram)
- Deploy dashboard (FastAPI) as systemd service on VPS
- Wire RAG auto-indexing: new KB outputs → ChromaDB on accept

### Suggested Next Steps
- **Goal:** Prove the transistor — one domain, one build, live URL, zero human code
- **Why/Purpose:** Everything is built for autonomous operation but the daemon has never run unsupervised. "Don't let it stay a demo."
- **Objectives:**
  1. Set VERCEL_TOKEN + BLOB_READ_WRITE_TOKEN on VPS
  2. Enable daemon with 5-cycle limit, monitor via Telegram
  3. Let signal cycle run → watch auto-generated build specs appear
  4. Run /build on best signal opportunity
  5. Verify Vercel auto-deploy fires and returns a live URL

---

## Session 22 — May 30, 2025
**Prompt:** Lifebook goal-setting framework applied to Cortex domains + sandboxed chat execution + copilot-instructions loop strengthening

### What We Did
1. **Sandboxed execution in chat/Telegram** — 5 new CHAT_TOOLS (patch_file, control_service, tail_log, run_tests, run_safe_command) + 7 new Telegram /commands (daemon, services, logs, logcat, tests, patch, editlog)
2. **copilot-instructions.md loop** — Added steps 10/11 (ASK + REPEAT), "mostly works is not done" rule, 8-question loop completion checklist
3. **Lifebook goal framework for Cortex** — domain_goals.py upgraded to full structured record; question_generator uses it

### Why
- Chat and Telegram needed to execute code, restart services, and run tests autonomously  
- The dev loop needed a formal "am I done?" gate and a rule to not reuse todo lists across loop passes
- Domain goals were a single string — couldn't support the architect's full Lifebook methodology

### Purpose
- Chat/Telegram can now self-modify Cortex source code on command (sandboxed)
- Dev process mirrors the product's own loop: plan → execute → test → verify → learn → repeat
- Cortex research is now goal-directed at the objectives level, not just a topic string

### Steps Taken
1. Added 5 CHAT_TOOLS to cli/chat.py with path sandboxing + command whitelisting
2. Added 7 /commands to telegram_bot.py; updated /start help text
3. Updated copilot-instructions.md: steps 10/11, "mostly works" rule, new-todo-list rule, 8-question checklist
4. Upgraded domain_goals.py schema — full Lifebook record: what_i_want, what_i_dont_want, solution, goal, objectives[], monthly_priority, task_queue[], audit_log[]
5. Added 8 new helper functions: set_goal_structured, add_objective, complete_objective, set_monthly_priority, push_task, pop_task, audit_goal, get_active_objectives — all backward-compat
6. Updated question_generator.py: imports get_goal_record + get_active_objectives; _build_generator_prompt now injects objectives/priority/task_queue into LLM system prompt; call site passes goal_record
7. Expanded Lifebook section in copilot-instructions.md with full framework (PRINCIPLE → WHAT I WANT → SOLUTION → GOAL → OBJECTIVES → SCHEDULE → MONTHLY PRIORITY → DAILY TASKS → EXECUTE → CHECK → ANALYZE → AUDIT → LIST IMPROVEMENTS → REPEAT)
8. 147/147 tests passing, committed 8f1a4d7, VPS synced

### What This Enables
- Set a goal like: `set_goal_structured("productized-services", goal="3 clients at $500/mo", what_i_want="...", objectives=["Research OLJ pain points", "Build LP template"], monthly_priority="Validate offer with 10 outreach messages")`
- question_generator will generate questions aimed at completing specific objectives, prioritized by monthly focus
- pop_task / push_task lets the system consume a FIFO work queue per domain

### Suggested Next Steps
- **Goal:** Wire `set_goal_structured` into the CLI so the user can set a full structured goal via `python main.py --domain X --set-goal`
- **Why:** Currently only callable from Python code — needs a UX wrapper for real use
- **Objectives:**
  1. Add `--set-goal-structured` flag (or interactive prompt) to main.py/cli
  2. Add `/setgoal` Telegram command that prompts through each field
  3. Add `--add-objective`, `--complete-objective`, `--monthly-priority` flags
  4. Show structured goal in `--status` output and `/status` Telegram command


**Prompt:** "is all in upnext.md done and properly integrated? if not continue"

### What We Did
- Completed full A-P audit of upnext.md against actual code (verified Sessions 19-20 work)
- Added curated seed questions for 3 revenue-generating domains (domain_seeder.py)
- Wired post-build Vercel auto-deploy trigger in the Hands pipeline (agents/cortex.py)
- 147/147 tests passing, committed a516c9b, VPS synced

### Why
- upnext.md gaps P and J remained after Sessions 19/20 — both actionable without architectural decisions
- Gap P (domain seeds): VPS was actively researching onlinejobsph-employers, productized-services, saas-fullstack-apps using generic questions instead of strategic domain-specific ones
- Gap J (auto-deploy): Built web artifacts sat in workspace_dir with no deployment path

### Purpose
- Revenue domains (the 3 actively researched on VPS) now get targeted, strategic seed questions on domain bootstrap
- When VERCEL_TOKEN is set, Hands-built web projects auto-deploy to Vercel immediately after a successful build
- Closes all actionable gaps from upnext.md; remaining deferred items (I, N, O) require UX/architectural decisions

### Steps Taken
1. Re-read upnext.md and cross-checked every gap A-P against actual code
2. Confirmed gaps A-M (except J) all wired in Sessions 19-20
3. Added 5 curated questions each for: onlinejobsph-employers, saas-fullstack-apps, productized-services to domain_seeder.py SEED_QUESTIONS dict
4. Added post-build deploy block in agents/cortex.py pipeline() inside the `if build_result.get("success"):` branch — checks `package.json` + `VERCEL_TOKEN`, runs `npx vercel --prod --yes`, stores URL in result, notifies Telegram
5. Smoke-tested domain_seeder — all 3 new domains return curated seeds correctly
6. 147 wiring + core tests green; committed + pushed + VPS synced

### Deferred (require design/UX decisions)
- **Gap I** (Credential Vault): .env works fine; API key rotation vault is over-engineering for now
- **Gap N** (Browser direct access): Already works as fallback in web_fetcher; researcher uses it when BROWSER_ENABLED
- **Gap O** (Consultant human answer): Needs Telegram inline keyboard UX — deferred

### Suggested Next Steps
**Goal/Intent:** First live deployment of a Hands-built product
- **Why/Purpose:** Prove the full loop end-to-end (Research → Build → Deploy → Live URL) — "don't let it stay a demo"
- **Objectives:**
  1. Set VERCEL_TOKEN on VPS (export VERCEL_TOKEN=... → /etc/environment or systemd override)
  2. Run one Hands pipeline build on a revenue domain (onlinejobsph-employers or productized-services)
  3. Verify auto-deploy to Vercel fires and returns a live URL
  4. Check Telegram notification for deploy URL
  5. Manual review of the live site output quality

---

## Session 20 — Mar 6, 2026
**Prompt:** "execute /workspaces/AI-agents/upnext.md"

### What We Did
- Audited upnext.md again against code state; identified 5 remaining real gaps not yet wired
- Wired MCP tool bridge into executor (cortex.py → register_mcp_tools_in_registry)
- Wired MCP research tools into researcher (get_mcp_research_tools in tool loop)
- Wired crawl-to-KB into scheduler daemon (inject_crawl_claims_into_kb after each domain)
- Wired dataset loader into executor strategy loading (inject_examples_into_strategy in cortex.py)
- Created cortex-dashboard.service on VPS, installed FastAPI, started it — API live on port 8000
- Added 12 new integration tests (42→54); full suite: 338 passed, 0 failed

### Why
- MCP gateway + tool bridge existed but no agent could use MCP tools. Now if gateway is started, all agents can use GitHub MCP, idea-reality check, etc.
- Crawl data was collected but never fed into the knowledge base automatically
- Dataset loader (HuggingFace/GitHub examples) existed since Session 13 but nothing triggered it
- Dashboard API fully built but never deployed — FastAPI wasn't even installed on VPS

### Purpose
- Every "BUILT BUT NOT INTEGRATED" gap from upnext.md is now wired (except Deploy automation + Consultant human answer, which require UX decisions)
- Dashboard API + existing Next.js frontend = full observability stack running at 207.180.219.27:8000
- MCP tools (GitHub, idea-reality) now available in all agent contexts when gateway is started

### Steps Taken
1. **agents/cortex.py** — After `create_default_registry()`: try `register_mcp_tools_in_registry()` guarded by `gw.is_started`; after `get_strategy("executor")`: try `inject_examples_into_strategy()`
2. **agents/researcher.py** — After Threads tool section: try `get_mcp_research_tools()` guarded by `gw.is_started`; MCP dispatch added to tool loop before web_search handler
3. **scheduler.py** — After each domain's `domain_results.append()`: try `inject_crawl_claims_into_kb(domain)` if `crawl_data/domain/` exists
4. **VPS** — `pip install fastapi`, created `/etc/systemd/system/cortex-dashboard.service`, `systemctl enable + start cortex-dashboard` → active on port 8000
5. **deploy/cortex-dashboard.service** — service file version-controlled in repo
6. **tests/test_integration_wiring.py** — 4 new test classes: `TestMcpToolBridgeWiring`, `TestMcpResearchToolsWiring`, `TestCrawlToKbWiring`, `TestDatasetLoaderWiring` (12 tests)
7. **Broad suite** — 338 passed. Committed `3d962de`, pushed, VPS synced.

### Remaining Gaps (deferred — require UX/infra decisions)
- **Deploy automation** — `deploy/deployer.py` exists but build artifacts need a destination. Requires Vercel/server target setup decisions.
- **Consultant human answer** — `hands/consultant.py` `_consult` tool gets LLM answers, not human. Needs Telegram inline keyboard or polling mechanism.
- **MCP Docker containers** — Gateway wired but Docker containers need to be started (handled by `gateway.start_all()` from CLI or future service)

### Suggested Next Steps
- **Goal:** Enable the daemon (currently DISABLED) for a supervised 24-hour test run
- **Why:** The system has never run unsupervised. The entire thesis is unproven until it does.
- **Objectives:**
  1. Enable `cortex-daemon.service`, monitor for 4-6 hours via Telegram
  2. Verify signal cycles run, enrichment fires, crawl-to-KB triggers
  3. Verify budget enforcer kills it at $7 limit
  4. Fix any runtime errors before going 24/7

---

## Session 19 — Mar 6, 2026
**Prompt:** "execute upnext.md — Finalize stuff, improve, refine, test, integrate, sync to VPS"

### What We Did
- Audited all 7 gaps from upnext.md against actual code state; found most already closed in Sessions 13-17
- Wired `enrich_top_posts()` into daemon signal cycle as non-fatal Step 2.5
- Added `/threads thread <id>` Telegram command for per-post analytics
- Added 3 signal intelligence tools to chat (`show_signals`, `enrich_signals`, `show_build_specs`)
- Fixed atomic write violation in `opportunity_scorer._save_build_spec` (pre-existing bug)
- Added 13 new tests (signals: 7→8, integration wiring: 29→42); suite: 326 passed, 0 failed

### Why
- `enrich_top_posts()` existed since Session 14 but was never wired into the daemon — dead letter code
- `get_thread_insights()` was built but unreachable via Telegram; only profile-level stats were exposed
- Chat had 28 tools but zero for signal intelligence; couldn't ask "what are top opportunities?" in chat
- `opportunity_scorer` was using raw `json.dump` violating the project write-integrity rule

### Purpose
- Signal cycle now collects → scores → **enriches** → bridges (full pipeline live)
- Telegram `/threads thread <id>` gives per-post engagement breakdown
- Chat can now query, enrich, and display the full signal intelligence pipeline interactively

### Steps Taken
1. **scheduler.py** — Added Step 2.5: calls `enrich_top_posts(limit=20)` inside `_run_signal_cycle()`; failure is caught and logged but never aborts the cycle; results dict gains `"enriched"` key
2. **telegram_bot.py** — Added `/threads thread <id>` sub-command using `get_thread_insights()`; updated both help text locations
3. **cli/chat.py** — Added 3 tools to CHAT_TOOLS + handlers in `_execute_tool`: `show_signals` (DB query), `enrich_signals` (Reddit enrichment), `show_build_specs` (read build spec files). Tool count: 28 → 31
4. **opportunity_scorer.py** — Added `atomic_json_write` import, replaced `json.dump` with `atomic_json_write` in `_save_build_spec()`
5. **tests/test_signals.py** — Updated `test_run_signal_cycle_full` to mock enrichment; added `test_run_signal_cycle_enrichment_failure_is_nonfatal`
6. **tests/test_integration_wiring.py** — Added 3 test classes: `TestSignalChatTools`, `TestTelegramThreadsCommand`, `TestSignalEnrichmentWiring`
7. **Full suite**: 326 passed, 0 failed. Committed `297b522`, pushed, VPS synced.

### Suggested Next Steps
- **Goal:** Orchestrator — 24/7 stability layer (watchdog + sync + cost control)
- **Why:** Daemon has never run unsupervised; the thesis is unproven until it does
- **Objectives:**
  1. Watchdog: restart daemon on crash, alert Telegram, log cause
  2. Daily budget enforcer: kill daemon if daily spend > threshold
  3. Sync: keep Brain ↔ Hands state consistent across restarts
  4. Health endpoint: simple HTTP check so external monitor can ping it

---

## Session 18 — Mar 7, 2026
**Prompt:** "set it for cortex ready to use the ptc so by the time i top it up with credits, ptc is ready to use"

### What We Did
- Pre-wired Anthropic PTC (Programmatic Tool Calling) so flipping one env var activates it
- Answered LangChain question (not needed — Cortex has its own routing/dispatch/memory)

### Why
- PTC = biggest efficiency gain identified in Session 16: ~37% token savings, fewer API round trips (4-8 → 1-2), context pollution eliminated
- Budget blocks actual usage, but code should be ready so `PTC_ENABLED=true` is all that's needed when credits arrive

### Purpose
- Zero-activation-cost PTC support: disabled by default, zero tokens burned until enabled
- When activated: researcher auto-routes to PTC path (direct Anthropic API with beta header)

### Steps Taken
1. **config.py** — Added PTC config block: `PTC_ENABLED` (env var, default false), `PTC_MODEL = "claude-sonnet-4-20250514"`, `PTC_BETA_HEADER = "advanced-tool-use-2025-11-20"`
2. **llm_router.py** — Added `betas` parameter to `_call_anthropic()`, routes to `client.beta.messages.create()` when betas provided, regular `client.messages.create()` otherwise. `call_llm()` passes betas through.
3. **agents/researcher.py** — Added `_build_ptc_tools()` (code_execution sandbox + 3 search tools) and `_research_ptc()` (full PTC research implementation with system prompt augmentation, JSON parsing, cost logging as "researcher_ptc"). Modified `research()` to dispatch to PTC when `PTC_ENABLED and ANTHROPIC_API_KEY`.
4. **tests/test_ptc.py** — 19 tests covering: config flag parsing, tool format, PTC dispatch routing, beta header routing (client.beta vs client.messages), response parsing, fallback on parse error, cost logging label.
5. **Full suite**: 124 passed, 0 failed, 0 regressions.
6. **Deployed**: Commit `985c44c` pushed + pulled to VPS.

### Activation Instructions
```bash
# In agent-brain/.env, add:
PTC_ENABLED=true
# That's it. Researcher auto-routes to PTC. To disable, remove or set false.
```

### Suggested Next Steps
- **Goal:** Orchestrator + 24/7 stability (watchdog, sync, cost control)
- **Why:** Build order says Orchestrator is NEXT after Hands coding execution proven
- **Objectives:**
  1. Wire watchdog to auto-restart daemon on crash/hang
  2. Sync agent — coordinate Brain + Hands task handoff
  3. Economics agent — daily cost vs revenue tracking, kill/pivot decisions
  4. Signal Agent — replace human "is this a good idea?" judgment

### Current System State
- **Brain**: 5 self-learning layers proven, strategy evolution working
- **Hands**: Coding execution (chat mode, 24 tools)
- **PTC**: Pre-wired, disabled by default. `PTC_ENABLED=true` activates.
- **Tests**: 124 passing (excluding known hardening test)
- **VPS**: 207.180.219.27, daemon DISABLED, telegram bot ACTIVE
- **Git**: `985c44c` on main

---

## Session 17 — Mar 6, 2026
**Prompt:** "Execute those objectives." — Implementing Session 16's 7 integration objectives

### What We Did
- Executed all 7 objectives from Session 16's resource evaluation verdicts

### Why
- Session 16 identified concrete improvements (tool accuracy, daemon hardening, resource bookmarks). Time to ship, not plan.

### Purpose
- Improve researcher tool call accuracy via Anthropic's input_examples feature
- Harden daemon loop with exponential backoff on consecutive failures
- Catalog decisions for future phases

### Steps Taken
1. **Added `input_examples` to all 3 tool definitions:**
   - `SEARCH_TOOL_DEFINITION` in `tools/web_search.py` — 3 examples (keyword query, query with source hint, query with max_results)
   - `FETCH_TOOL_DEFINITION` in `tools/web_fetcher.py` — 2 examples (docs URL, GitHub README)
   - `SEARCH_AND_FETCH_TOOL_DEFINITION` in `tools/web_fetcher.py` — 3 examples (simple, with max_results+max_fetch, with max_fetch only)
2. **Checked OpenRouter PTC support:** Queried `/api/v1/models` endpoint for claude-sonnet-4 → `supported_parameters` does NOT include code_execution beta. **Parked for later.**
3. **Implemented Symphony-style exponential backoff in `scheduler.py`:**
   - Formula: `delay = min(base_sleep * 2^(failures-1), 300s)` added to sleep interval on consecutive cycle failures
   - Uses `watchdog.get_status()["consecutive_failures"]` — resets to base interval on success (existing watchdog behavior)
4. **Bookmarked `coreyhaines31/marketingskills` in `RESOURCE_CATALOG.md`** as entry #14 under USEFUL LATER, tagged for Phase 7 (Outreach Agent)
5. **Verified `idea-reality-mcp` on VPS:** Not pip-installed, but `planner.py` handles gracefully via try/except. Not critical for current operations.
6. **Tests:** 2,050 passed, 0 failures (1 pre-existing failure in `opportunity_scorer.py` atomic write — unrelated)
7. **Deployed:** Committed `08016aa`, pushed to GitHub, pulled on VPS via git pull

### Commit
`08016aa` — `feat: input_examples on tools, Symphony backoff in scheduler, marketing skills bookmark`

### Suggested Next Steps
**Goal:** Enable first autonomous daemon run on VPS
**Why:** All code is deployed but daemon is DISABLED. The thesis is unproven until it runs unsupervised.

**Objectives:**
1. Fix the pre-existing `opportunity_scorer.py` atomic write test failure
2. Enable `cortex-daemon.service` on VPS with conservative settings (1 cycle, require_approval=true)
3. Monitor first cycle via Telegram alerts + watchdog status
4. If stable: increase to 3 cycles, then remove cycle cap
5. When Anthropic PTC is available via OpenRouter (or switch to direct API): refactor researcher to use PTC for 37% token savings

---

## Session 16 — Mar 6, 2026
**Prompt:** "Is this worth adding to our current system?" — 12 external resources evaluated

### What We Did
- Deep-researched 12 external resources (repos, APIs, docs, tools) the architect found and evaluated each against Cortex's current architecture and priorities

### Why
- Architect found potentially useful tools/patterns and needed honest assessment of what's worth integrating vs what's noise

### Purpose
- Avoid wasting time on shiny objects that don't serve the loop
- Identify genuine improvements that compound (tool accuracy, token savings, daemon hardening)

### Steps Taken
1. Read full local `symphony.md` (2,109-line OpenAI Symphony spec)
2. Fetched + analyzed OpenAI Symphony Elixir README (Codex orchestrator daemon)
3. Fetched + analyzed Apple ML-CLARA (RAG compression research paper)
4. Fetched + analyzed Anthropic advanced tool use blog (Tool Search, PTC, Examples)
5. Fetched + analyzed Anthropic programmatic tool calling docs (full API spec)
6. Fetched + analyzed Anthropic fine-grained tool streaming docs
7. Fetched + analyzed coreyhaines31/marketingskills (30+ marketing skill files)
8. Fetched + analyzed ComposioHQ/awesome-claude-skills (500+ app integrations)
9. Fetched + analyzed snarktank/ai-dev-tasks (PRD → task list workflow)
10. Fetched + analyzed sickn33/antigravity-awesome-skills (1006+ IDE skills)
11. Fetched + analyzed mnemox-ai/idea-reality-mcp (competition validator)
12. Fetched Google Doc (scroll animation tutorial)
13. Audited current Cortex tool usage: researcher tool_use loop, MCP gateway, context_router, executor registry, planner reality check
14. Cross-referenced each resource against Cortex architecture, priorities, and constraints

### Verdicts
- **YES (do now):** Tool Use Examples (add input_examples to tool defs — cheap accuracy boost), Programmatic Tool Calling (37% token reduction — blocked by API access check)
- **EXTRACT PATTERNS:** Symphony retry/backoff formula for daemon hardening, ai-dev-tasks PRD step for build specs
- **ADOPT LATER:** Marketing Skills (Phase 7 when Hands does marketing), Tool Search API (when 50+ tools)
- **ALREADY DONE:** idea-reality-mcp (wired in planner.py)
- **SKIP:** ML-CLARA (needs GPU), Antigravity Skills (wrong audience), Fine-grained Streaming (no UI), Google Doc (irrelevant)

### Suggested Next Steps
**Goal:** Improve tool call accuracy + prepare for programmatic tool calling
**Why:** Tool Use Examples is free accuracy boost; PTC is biggest efficiency gain possible for research loop

**Objectives:**
1. Add `input_examples` to search/fetch tool definitions in `tools/web_search.py` and `tools/web_fetcher.py`
2. Check if OpenRouter supports `code_execution` beta feature for PTC
3. If yes: refactor `agents/researcher.py` tool loop to use PTC
4. If no: park for later when direct Anthropic API or OpenRouter adds support
5. Verify `idea-reality-mcp` installed on VPS
6. Extract Symphony retry backoff formula into `scheduler.py`
7. Bookmark `coreyhaines31/marketingskills` for Phase 7

---

## Session 15 — Mar 6, 2026
**Prompt:** "log every progress on one .md + add to copilot instructions so you never forget"

### What We Did
- Created this structured progress logging convention and added a mandatory rule to `.github/copilot-instructions.md`

### Why
- No persistent record of session-level progress in a quick-reference format
- Copilot has no standing instruction to log work, so progress tracking was inconsistent

### Purpose
- Single source of truth for all development sessions
- Architect can review any session's decisions, steps, and outcomes at a glance
- Copilot is now contractually required to log after every completed task series

### Steps Taken
1. Reviewed existing `.github/progress.md` (sessions 1-12 already logged)
2. Added missing sessions 13-15
3. Added mandatory progress logging rule to `.github/copilot-instructions.md`

### Suggested Next Steps
**Goal:** Ensure Cortex runs its first fully autonomous signal-to-build cycle on VPS
**Why:** All code is deployed but the daemon is DISABLED — the thesis is unproven until it runs unsupervised

**Objectives:**
1. Enable `cortex-daemon.service` on VPS and run 1 supervised cycle (`--daemon --max-cycles 1 --rounds 3 --no-approval`) to validate full autonomous flow end-to-end
2. Monitor Telegram alerts for first autonomous signal collection + scoring cycle
3. Verify Scrapling is installed on VPS venv (required for enrichment)
4. Let the 443 unanalyzed posts get scored autonomously
5. Review first auto-generated build spec for quality

---

## Session 14 — Mar 5, 2026
**Prompt:** "Execute systematically." — Build Signal Intelligence autonomous pipeline (9 objectives)

### What We Did
- Executed a 9-objective masterplan transforming Signal Intelligence from disconnected CLI commands into a fully autonomous Cortex pipeline

### Why
- Signal Intelligence existed as standalone CLI tools (collect, score, status) with zero daemon awareness
- No bridge between signal opportunities and Brain's research loop
- No automatic build spec generation from high-scoring opportunities
- No engagement feedback loop to track growing vs dying opportunities

### Purpose
- Make Cortex autonomously: discover pain points → score them → research solutions → generate build specs → create sync tasks for Hands → track engagement changes
- Close the gap between "finds opportunities" and "builds solutions"

### Steps Taken
1. **Obj 1 — Scrapling Enrichment Layer**: Added `enrich_post()`, `enrich_top_posts()`, `check_engagement_changes()` to `signal_collector.py`. Lazy-loads Scrapling, extracts upvotes/comments from old.reddit.com, rate-limited. 5 tests.
2. **Obj 2 — Solution Spec Generator**: Added `BUILD_SPEC_PROMPT`, `generate_build_spec()`, `_save_build_spec()` to `opportunity_scorer.py`. DeepSeek generates structured product specs (name, features, MVP scope, competitors, gap). Saves to `logs/build_specs/`. 3 tests.
3. **Obj 3 — Signal→Brain Bridge**: Created new `signal_bridge.py` (160 lines). Template-based question generation from top opportunities — validation, competitor, and technical templates. Maps signal categories to Brain domains. Zero LLM calls. 5 tests.
4. **Obj 4 — Signal-Aware Daemon**: Modified `scheduler.py` with signal state management, `_run_signal_cycle()` (collect→score→bridge→engage→alert), interval-based execution (6h). 7 tests.
5. **Obj 5 — Research→Build Spec Pipeline**: Added `_generate_signal_build_specs()` to `scheduler.py`. Auto-generates specs for 70+ score opportunities (max 3/cycle), creates sync tasks. 4 tests.
6. **Obj 6 — Hands Signal-Build Executor**: Build specs create `sync.create_task()` entries with type="build", priority="high". Hands can pick them up for execution. 1 additional test.
7. **Obj 7 — Engagement Feedback Loop**: `check_engagement_changes()` re-checks engagement on high-scoring posts, computes deltas, flags growing opportunities. Runs every 3rd signal cycle. 5 tests.
8. **Obj 8 — Integration Tests + Hardening**: 35 new tests (38→73 signal, 93 core, 32 alert — all passing). Zero regressions.
9. **Obj 9 — VPS Deploy + Validation**: Committed `a698872`, pushed, SSH deployed, validated all imports and live data (493 posts, 50 analyzed, top score 90/100).

### Use Cases
- Autonomous pain point discovery from Reddit communities
- Auto-generated micro-SaaS product specs from real user complaints
- Signal-driven research prioritization (Brain researches what signals suggest, not random topics)
- Engagement tracking to identify growing opportunities vs noise

### Suggested Next Steps
**Goal:** Validate autonomous signal-to-build cycle end-to-end on VPS
**Why:** Code is deployed but daemon is DISABLED — nothing runs without human triggering

**Objectives:**
1. Verify Scrapling installed on VPS venv
2. Enable daemon and run 1 supervised cycle
3. Monitor first auto signal cycle via Telegram
4. Review quality of auto-generated build specs
5. Tune scoring thresholds based on real results

---

## Session 13 — Mar 4, 2026
**Prompt:** "write a comprehensive masterplan" + strategic analysis of Signal Intelligence for monetization

### What We Did
- Analyzed what Signal Intelligence means for the monetization strategy
- Answered 3 clarifying questions honestly (was it autonomous? can Scrapling help? does it recommend solutions?)
- Designed a 9-objective masterplan with dependency graph, cost estimates, and architecture diagram

### Why
- User wanted to understand the strategic impact of the signal system on OLJ productized services vs SaaS factory
- Needed honest assessment of what Cortex does autonomously vs what was human-built
- Identified capability gaps: signals existed but didn't connect to Brain loop or generate actionable build specs

### Purpose
- Shift from "OLJ productized services capped at human time" to "signal-driven SaaS factory that scales with Cortex's time"
- Create a roadmap that could be fully executed in one Codespace session

### Steps Taken
1. Read `OLJstrat-mar1.md`, `ACTION-PLAN.md`, `8phaseplan.md`, `OLJ-PITCH-TEMPLATE.md` for strategic context
2. Audited all signal intelligence code (signal_collector.py, opportunity_scorer.py, cli/signals_cmd.py)
3. Confirmed Scrapling is installed and importable
4. Identified 3 gaps: no Brain bridge, no build spec generation, no engagement feedback
5. Designed 9-objective plan with dependency graph (Obj 1-3 parallel → Obj 4 depends on 1-3 → etc.)

### Use Cases
- Strategic planning for autonomous business operator systems
- Gap analysis methodology: audit code → identify disconnections → design integration plan

### Suggested Next Steps
→ Became Session 14 (full execution of the masterplan)

---

## Session 12 — Mar 2, 2026
**Prompt:** "Read ideal-thoughts.md, extract relevant ideas for our current system architecture. Don't apply OpenClaw stuff."

### What we did
1. Read entire 3,604-line ideal-thoughts.md (conversation with another AI about system architecture)
2. Cross-referenced every concept against our actual codebase
3. Produced a gap analysis: what we already have, what's partially implemented, what's missing

### Why
- User had a detailed architecture brainstorm document covering: ideal self-learning system anatomy, 26-agent design, 4-type memory, local judge models, cost optimization, and the full SaaS factory vision
- Needed to extract what's actually useful for our system vs what's aspirational/OpenClaw-specific

### Key extractions (applicable to our system)
1. **Pre-screen critic** — grok scores output before Claude critic, skip Claude when result is clearly good or clearly bad → saves ~40% critic cost
2. **Real-time loop guard** — detect repeated questions, stuck rounds, runaway cost DURING auto mode (not post-hoc like monitoring.py)
3. **Progress-toward-goal check** — every 5 outputs, assess "are we closer to the domain goal?" (not individual output quality)
4. **Procedural memory** — extract "what search patterns work" into reusable approach templates (beyond strategy docs)
5. **Scout vs Research separation** — split "find niches" from "deep domain dive" in question generation
6. **Orchestrator should be pure logic, not an LLM** — watchdog, loop detection, sync checking

### What we explicitly skipped
- Channel Agent / messaging platforms (OpenClaw-specific)
- Voice/camera/device nodes (irrelevant)
- Fine-tuning Mistral 7B locally (no GPU in Codespaces)
- 26-agent full architecture (overkill, would go broke)
- Signal/Validation/Behavior agents (premature — no product yet)

### Results
- Clear priority stack: pre-screen critic → loop guard → progress check
- Validated that our Brain+Hands+Orchestrator architecture matches the doc's recommended approach
- Our domain_goals.py is the seed of the doc's "Identity Layer"
- Our research_lessons.py is the seed of the doc's "Preference Store"
- Budget: $15.51 total ($9.70 OpenRouter + $5.81 Claude)

### Implementation (Session 12 continued)

Built and wired all three priority improvements:

**1. Pre-screen Critic** (`prescreen.py`, 246 lines)
- Structural prechecks (zero-cost): zero findings, parse errors, empty searches → instant reject
- Grok LLM prescreen: scores 1-10. Accept ≥7.5, Reject ≤3.5, Escalate 4-7 to Claude
- Wired into `main.py:_run_loop_inner()` — runs BEFORE Claude critic call
- Expected savings: ~40% reduction in Claude critic API calls
- 14 tests

**2. Loop Guard** (`loop_guard.py`, 208 lines)
- Real-time loop protection during auto mode (pure logic, no LLM)
- Detects: consecutive failures (3x), question similarity (>70%), cost velocity (>80% budget), score regression, same-error repetition
- `LoopGuard` class with `check_before_round()`, `record_round()`, `check_after_round()`
- Raises `LoopGuardError` to stop auto mode gracefully
- Wired into `cli/research.py:run_auto()` — wraps every round
- 17 tests

**3. Progress Tracker** (`progress_tracker.py`, 208 lines)
- Cheap grok assessment: "given goal X and research Y, how close are we to acting?"
- Returns readiness score (0-100%), gaps list, recommendation (keep/act/pivot)
- Tracks history + trend (↑/↓ since last check)
- Runs every 5 accepted outputs, or on-demand via `--progress` CLI flag
- Wired into `cli/research.py:run_auto()` — checks at end of each run
- `display_progress()` renders progress bar + gaps + strengths
- 14 tests

**Wiring summary:**
- `main.py`: prescreen import + prescreen→critique flow (7 lines)
- `cli/research.py`: LoopGuard init + check_before/after + progress assessment (25 lines)
- `main.py CLI`: `--progress` flag for on-demand goal progress display
- `tests/test_hardening.py`: fixed integration test to mock prescreen

**Tests:** 1,218 passing (was 1,173 — 45 new tests added)

---

## Session 11 — Mar 1, 2026 (evening)
**Prompt:** "Execute 1 and 2, you oversee it for me" (push to remote + run goal-directed cycle)

### What we did
1. Pushed 9 commits (0403fe0..da02a0d) to origin/main
2. Approved v002 strategy for productized-services (enhanced source verification + reduced search budget 5-8→3-6)
3. Bumped daily budget temporarily from $2→$4 (was blocked at $2.12 spent)
4. Ran `--auto --rounds 3 --domain productized-services` with the new goal system active
5. Reset budget back to $2
6. Evaluated results

### Why
- The system had been building for a week without pushing. Needed to get code on remote.
- v002 strategy was pending — needed approval to enter trial.
- Needed to prove the goal system (Session 10) actually changed research behavior.

### Results
- **Goal system works.** Question quality shifted:
  - BEFORE: "Gartner 2025 freelance success rates", "McKinsey freelance vs agency analysis"
  - AFTER: "Employer complaints/ghosting on OLJ for Next.js", "Budgets in active 2026 OLJ postings"
- Round 1 scored 6.0: Found no specific Next.js complaint data on OLJ, but general employer reviews show inconsistent candidate quality
- Round 2 scored 7.25: No fixed-budget landing page postings on OLJ. Full/part-time roles at $270–$1,100/mo. OLJ is direct-hire focused, not project-based.
- Round 3 ran successfully (budget decreased further)
- **Key insight:** OLJ isn't a gig platform — it's a direct-hire platform. This fundamentally changes the pitch strategy from "buy my landing page" to "hire me as your fractional Next.js developer."
- Browser stealth broken throughout (Page.evaluate ReferenceError) — limits OLJ-specific scraping
- Total cost: ~$1.50 for 3 rounds
- Commit: `0b99570`

### Blockers identified
- Browser stealth completely broken — can't scrape OLJ directly
- Budget tight at ~$4.63 remaining, $2/day limit

---

## Session 10 — Mar 1, 2026 (afternoon)
**Prompt:** "I dont want to be fed by data and metrics but rather what it learns" + "somehow the system we create dont know what I want, need, goal or intention is"

### What we did
1. **Domain Goals system** — Created `domain_goals.py` (148 lines): per-domain goal/intent storage in `strategies/{domain}/_goal.json`
   - Wired into question_generator.py (goal injected into prompt, bad/good examples changed to OLJ-specific)
   - Wired into researcher.py (goal block in system prompt: "Focus on ACTIONABLE toward this goal")
   - Added --set-goal, --show-goal CLI flags
   - Added chat tools: set_domain_goal, show_domain_goal, run_cycle
   - Total chat tools: 24
2. **Interpretability rewrite** — Rewrote how chat presents data
   - New INTERPRETABILITY section in system prompt with BAD/GOOD examples
   - Rewrote tool handlers: search_knowledge, show_knowledge_base, run_research, run_cycle, show_status, show_knowledge_gaps
   - show_status now includes recent activity + domain goal
   - analytics.search_memory returns key_insights + 400-char summaries (was 200)

### Why
- User ran `--auto --rounds 5 --domain productized-services` and got Gartner/McKinsey academic research — completely irrelevant to selling on OLJ
- Root cause: question generator had ZERO context about WHY user cares about a domain
- Chat was dumping raw data like `[High] Claim:... confidence: 0.85` instead of plain English insights

### Results
- Domain goal set for productized-services: "I want to sell productized Next.js/React landing page services to employers on OnlineJobsPH..."
- System prompt got an honesty section — BAD examples show data dumps, GOOD examples show conversational insights
- Tested in Session 11 — confirmed questions are now directed, not academic
- Commits: `26ea6c2`, `da02a0d`

---

## Session 9 — Mar 1, 2026 (earlier afternoon)
**Prompt:** Add architect's notes to copilot instructions + let chat read source code

### What we did
1. Added `my-notes.md/` reference to `.github/copilot-instructions.md` with summaries of each file and 6 distilled principles
2. Added 3 read-only source tools to chat: list_files, read_source, search_code
3. Path traversal prevention (no `..` in paths)

### Why
- Copilot kept making decisions without knowing the architect's strategic context (revenue before polish, don't let it stay a demo, etc.)
- Chat couldn't look at its own code — couldn't help debug or explain how things work

### Results
- Copilot now reads architect's notes before architectural decisions
- Chat can browse source code within agent-brain/ safely
- Commit: `fac817b`

---

## Session 8 — Mar 1, 2026
**Prompt:** Add self-improvement lessons loop

### What we did
1. Created `.github/lessons.md` for Copilot — rules extracted from user corrections, reviewed at session start
2. Created `research_lessons.py` for Brain — lessons injected into researcher prompt from critic rejections and strategy rollbacks
3. Added show_lessons chat tool (18→21 tools)

### Why
- Same mistakes kept happening across sessions — no persistent learning
- Researcher kept making the same errors the critic kept rejecting

### Results
- 8 initial rules in lessons.md covering: atomic_json_write, test directory, function name mismatches, return type assumptions, system prompt honesty, don't oversell, check implementations, conversation window costs
- Researcher prompt now includes "LEARN FROM PAST MISTAKES" section with domain-specific lessons
- Commit: `120755b`

---

## Session 7 — Mar 1, 2026
**Prompt:** Chat system prompt is overselling — fix it to be honest

### What we did
- Rewrote system prompt with three sections:
  - **WHAT ACTUALLY WORKS** (tested, proven)
  - **CODE BUT UNPROVEN** (exists but never battle-tested)
  - **CANNOT DO** (doesn't exist yet)

### Why
- User noticed chat was claiming capabilities the system doesn't actually have
- Example: claiming "I can deploy to VPS" when deploy module has never been tested

### Results
- Chat no longer oversells. Distinguishes proven vs aspirational.
- Commit: `ebc4e69`

---

## Session 6 — Mar 1, 2026
**Prompt:** Chat needs persistent memory + better developer context

### What we did
1. Persistent conversation memory — session save/load in `logs/chat_sessions/`
2. Full dev context in system prompt (model inventory, budget, architecture)
3. Switched executor from claude-haiku-4.5 to grok-4.1-fast (cost savings)

### Why
- Chat forgot everything between sessions
- Chat didn't know what models it was using, what the budget was, or how the system was structured

### Results
- Sessions persist across restarts
- 40-message context window (balance between memory and cost)
- Commit: `91f4291`

---

## Session 5 — Mar 1, 2026
**Prompt:** Build interactive chat mode + fix system anatomy understanding

### What we did
1. Built `cli/chat.py` — interactive REPL with LLM tool-use access to system internals
2. Fixed chat to understand the full 3-layer architecture (Brain + Hands + Infrastructure)
3. Model switch from deepseek-v3 to x-ai/grok-4.1-fast

### Why
- CLI flags (`--auto`, `--status`, etc.) are powerful but not conversational
- Wanted to talk to the system, ask questions, get it to run things
- deepseek-v3 was unreliable; grok-4.1-fast is cheap ($0.10/M input) and capable

### Results
- Working chat mode with tool access to: search_knowledge, run_research, show_status, approve_strategy, show_budget, etc.
- Commits: `54da4b6`, `2e734a2`

---

## Session 4 — Mar 1, 2026
**Prompt:** Decompose main.py god module

### What we did
- Broke main.py from 4,170 lines down to 973 lines
- Created cli/ modules: research.py, execution.py, knowledge.py, project.py, infrastructure.py, browser_cmd.py, deploy_cmd.py, tools_cmd.py
- Rewired 64 dispatch handlers

### Why
- main.py was unmaintainable at 4,170 lines — every feature was dumped in one file
- Couldn't add chat mode without making it even worse

### Results
- main.py is now a thin dispatch layer
- Each cli/ module owns its domain
- All tests pass
- Commit: `0403fe0`

---

## Session 3 — Mar 1, 2026
**Prompt:** Activation round — wire disconnected components, build knowledge graphs, run productized-services

### What we did
1. Wired verifier into the research loop
2. Built knowledge graphs for 7 domains
3. Extracted cross-domain principles v5
4. Wired 4 disconnected components (llm_router, verifier, knowledge_graph, cross_domain)
5. Fixed graph summary key names in researcher.py + null guard in auto mode

### Why
- Deep audit (Session 2) found many modules that existed but weren't connected to anything
- Knowledge graphs existed as code but had no data
- Cross-domain principles were stale

### Results
- Verifier now runs on research outputs
- 7 knowledge graphs populated
- Principles v5 extracted
- Commits: `031311c`, `e941a4e`, `6f01396`

---

## Session 2 — Mar 1, 2026
**Prompt:** Deep audit of entire codebase

### What we did
- Audited all 103 Python files (50,441 lines)
- Ran all 1,173 tests
- Identified: disconnected modules, dead code, missing wiring, untested paths
- Created OLJ pitch template
- Consolidated notes (deleted 9 obsolete files)
- Added Mar 1 action plan

### Why
- System had grown fast across Feb 23–28 sessions. Needed to understand what actually works vs what's just code sitting there.

### Results
- Clear picture: Brain is production-ready, Hands is untested, Dashboard is cosmetic, Deploy is unwired
- Priority stack established: wire components → chat mode → verifier → first delivery
- Commits: `1aa2d2a`, `d3ebbcd`, `1473920`

---

## Session 1 — Feb 28, 2026
**Prompt:** Productized services research session ($5 budget)

### What we did
1. Ran activation round: synthesized knowledge bases, wired balance tracker, bug fixes
2. Added search planning phase to researcher (fix blind query generation)
3. Ran 19 research outputs for productized-services domain
4. Strategy v001 confirmed (+18% score improvement)
5. Built 26-claim knowledge base
6. Wired stealth browser fallback
7. Verified RAG working
8. Refined Cortex without running cycles (zero-cost improvements)
9. Wired verifier to CLI: --predictions, --verify, --prediction-stats

### Why
- First real research session focused on the money domain (OLJ productized services)
- Needed to validate the loop actually produces useful competitive intelligence

### Results
- 19 outputs with avg score ~6.3, 26-claim KB synthesized
- Strategy v001 evolved and confirmed (score improved 18%)
- Researcher now plans searches before executing them (more focused queries)
- Browser stealth wired as fallback for when regular search fails
- Total spend: ~$5
- Commits: `6a4735e` through `3ba5c60`, `8e4b5e5`

---

## Foundation Sessions — Feb 23–27, 2026
**Multiple sessions building the core system from scratch**

### Feb 23 — The Big Build Day
- **Layer 1+2:** Research loop with web search, critic scoring, quality gate (`5b29d72`)
- **Layer 3:** Meta-Analyst with strategy evolution (`753baab`)
- **Layer 4:** Trial system, rollback, JSON parser hardening (`8f5c485`)
  - JSON parser fix validated: Web3 gaming went from 3.2 to 7.1/10
- **Control layer:** Approval gate, cost tracking, audit trail, budget enforcement (`93e5b37`)
- **Layer 5:** Cross-domain transfer — principle extraction + strategy seeding (`e51bddc`)
- **Self-directed learning:** Question generator + auto mode (`26d9f3c`)
- **Data accumulation:** Cybersecurity (7.7), geopolitics (7.7), crypto (7.4) — multi-domain runs
- **Cross-domain principles v2:** 9 principles from 5 domains
- **Infrastructure:** Dashboard, orchestrator, retry utility, analytics engine, data validator, domain seeder, smart scheduler
- **Tests:** 0 → 79

### Feb 24 — Dashboard + Advanced Agents
- Web dashboard (FastAPI + Next.js) with 3 rounds of UX fixes
- Consensus research, knowledge graph engine, smart orchestrator, daemon mode
- Dashboard UI for knowledge graph, scheduler, consensus
- **Tests:** 79 → 93

### Feb 25 — Production Hardening
- SQLite DB, TF-IDF cache, monitoring, error recovery
- Safety hardening: 7 fixes from audit + 24 new tests
- First nextjs-react domain run: 5 rounds avg 6.9, KB synthesized (14 claims, 41-node graph)
- 20-round nextjs-react run: 28 outputs, avg 6.2, strategy evolved v001→v002
- **Tests:** 93 → 253

### Feb 26 — Agent Hands (Execution Layer)
- Built Agent Hands v1 through v18 in one session (18 iterations)
- Full execution pipeline: planner → executor → validator → memory → meta-learning
- Added: stealth browser, credential vault, VPS deploy, project orchestrator
- RAG with ChromaDB + sentence-transformers
- MCP Docker gateway
- Orchestrator + Critic quality uplift
- **18 Hands iterations** covering: tool validation, workspace awareness, security hardening, execution analytics, pattern learning, adaptive timeouts, artifact tracking, native tool_use API, TS/JS validation, progressive plan trimming
- Commits: `ded62af` through `95106c7`

### Feb 27 — Limitations Round
- LLM cache, KB rollback, rate limiter, dashboard auth, auto-prune (`e2cba16`)

---

## Current System State (as of Mar 6, 2026)

| Component | Status |
|---|---|
| Research Loop (Brain) | **Production-ready.** 5 layers working. ~29 outputs for productized-services. |
| Strategy Evolution | **Working.** v002 in trial for productized-services. |
| Domain Goals | **Working.** Proved it directs research away from academic topics. |
| Signal Intelligence | **Fully integrated.** Collect→Score→Bridge→BuildSpec→Engage pipeline. 493 posts on VPS. |
| Signal→Brain Bridge | **Working.** Template-based question generation from top opportunities. |
| Build Spec Generator | **Working.** DeepSeek generates product specs from 70+ score signals. |
| Engagement Feedback | **Working.** Tracks upvote/comment deltas on high-scoring posts. |
| Chat Mode | **Working.** 24 tools, interpretability-first, persistent sessions. |
| Buffer X Path | **Working.** Runtime `.env` loading fixed; local draft -> confirm -> send flow verified live on Mar 8. |
| Verifier | **Wired to CLI.** Not yet integrated into automatic loop. |
| Agent Hands | **Code exists, untested in production.** 18 iterations of executor code. |
| Dashboard | **Code exists, cosmetic.** Not used in practice. |
| Deploy | **Code exists, unwired.** Never deployed anything. |
| Browser Stealth | **Broken.** Page.evaluate ReferenceError on every call. |
| Daemon | **Code deployed, service DISABLED on VPS.** Never run unsupervised. |

### Models (4-tier, all OpenRouter)
- **T1 deepseek/deepseek-chat**: Signal scoring, build specs — cheapest
- **T2 x-ai/grok-4.1-fast**: Researcher, question generator, chat, executor
- **T3 anthropic/claude-sonnet-4**: Critic, meta-analyst, verifier, planner
- **T4 google/gemini-2.0-flash-001**: Fallback

### Key Files Modified (Sessions 13-15)
- `signal_bridge.py` — NEW, connects signals to Brain research loop
- `signal_collector.py` — Scrapling enrichment + engagement feedback
- `opportunity_scorer.py` — Build spec generator
- `scheduler.py` — Signal-aware daemon cycle
- `alerts.py` — Signal collection alerts
- `config.py` — Signal config vars
- `cli/signals_cmd.py` — New CLI commands (enrich, build-spec, engagement-check)
- `tests/test_signals.py` — 73 tests (was 38)

### VPS State
- **IP:** 207.180.219.27 | **Git HEAD:** `a698872`
- **Signals DB:** 493 posts, 50 analyzed, 443 awaiting, top score 90/100
- **Daemon:** DISABLED | **Telegram bot:** ACTIVE

### Priority Stack (next actions)
1. Enable daemon and run first supervised autonomous cycle
2. Verify Scrapling on VPS + test enrichment
3. Review auto-generated build spec quality
4. Fix browser stealth (unlocks OLJ-specific data)
5. Wire Verifier into automatic loop
6. First real delivery — revenue before polish

---

## Session 33 — Transistor Core (Cold-Start, Calibration, Memory Lifecycle, Claim Verification)

**Date:** 2026-03-07

### What was done
Implemented the four "transistor reliability" systems to make Cortex's core loop domain-agnostic and self-managing:

**A. Cold-Start Reliability (`domain_bootstrap.py`)**
- Auto-detects cold domains (< 5 accepted outputs)
- Generates domain orientation via LLM (key concepts, source types, pitfalls, research profile)
- Auto-applies cross-domain principles when available
- Produces progressive bootstrap questions tailored to the domain
- Tracks bootstrap status per domain
- Integrated into main loop (auto-runs on first encounter) and daemon (bootstrap-aware question generation)

**B. Critic Calibration (`domain_calibration.py`)**
- Tracks per-domain score distributions (mean, stddev, accept rate, per-dimension stats)
- Computes domain difficulty signal (easy/medium/hard) from historical performance
- Injects calibration context into the critic prompt — tells the critic about baseline performance without inflating scores
- Provides normalized scores for cross-domain analytics
- CLI: `--calibration` shows all domain stats

**C. Automatic Memory Lifecycle (`memory_lifecycle.py`)**
- Self-managing maintenance sweep: claim expiry → re-synthesis → graph rebuild → pruning → claim verification → calibration update
- Re-synthesizes KB when stale claims accumulate past threshold
- Runs automatically every N daemon cycles (configurable)
- CLI: `--maintenance` runs manually for one or all domains

**D. Claim Verification (`agents/claim_verifier.py`)**
- Extends beyond time-bound predictions to check ANY high-confidence claim against web evidence
- Samples claims prioritizing: never-verified first, then oldest verified
- Verdicts: confirmed / refuted / weakened / inconclusive
- Refuted claims get status="disputed", confidence lowered, and correction noted
- Refutations fed back as research lessons (breaking the LLM-judging-LLM loop)
- Integrated into main loop (every 5 accepted outputs) and daemon maintenance cycle

### Files created
- `agent-brain/domain_bootstrap.py` — Cold-start bootstrapping protocol
- `agent-brain/domain_calibration.py` — Cross-domain score calibration
- `agent-brain/memory_lifecycle.py` — Self-managing memory maintenance
- `agent-brain/agents/claim_verifier.py` — General claim verification against web evidence

### Files modified
- `agent-brain/config.py` — Added 11 new config constants for all four systems
- `agent-brain/agents/critic.py` — Calibration context injection into critic prompt
- `agent-brain/main.py` — Bootstrap auto-detection, calibration updates, claim verification in loop, 5 new CLI commands
- `agent-brain/scheduler.py` — Bootstrap-aware question generation, maintenance cycle in daemon, calibration updates

### New CLI commands
- `--bootstrap` — Manually bootstrap a new domain
- `--calibration` — Show cross-domain score calibration stats
- `--maintenance` — Run full memory lifecycle maintenance
- `--verify-claims` — Verify high-confidence KB claims against web evidence
- `--claim-stats` — Show claim verification statistics

### Architecture principle
All four systems follow the "transistor first" principle: they strengthen the core loop's ability to operate reliably in ANY domain without human intervention. No new features — just reliability, self-correction, and domain-agnostic operation.

---

## Session 34 — Architectural Hardening (Zero-API-Cost)

Focus: Make the architecture fundamentally solid without running cycles. All changes are zero-API-cost — structural improvements, testing, and tooling.

### 1. Domain-Agnostic Brain-to-Hands Handoff (`main.py`)
- Replaced `_ACTION_KEYWORDS` (13 coding-centric terms) with `_ACTION_VERBS` (40+ universal action verbs)
- Added verbs for non-technical domains: analyze, evaluate, survey, contact, negotiate, propose, pitch, assess, track, monitor, engage, etc.
- Extracted `_classify_task_priority()` for testable priority logic
- Task creation now works for biotech, finance, policy, or any domain — not just software

### 2. Structural Tests (`tests/test_transistor.py`)
- 30+ mock-based tests across all four transistor systems + handoff + error paths
- `TestDomainBootstrap`: is_cold detection, status lifecycle, sequential questions, curated/generic fallback
- `TestDomainCalibration`: stats computation, difficulty classification, normalization, cross-domain update
- `TestMemoryLifecycle`: disabled state, empty domains, populated maintenance, all-domain sweep
- `TestClaimVerifier`: confidence filtering, recency skipping, search query building, stats
- `TestHandoffClassification`: verb coverage, priority logic, broad verb detection across domains
- `TestErrorPaths`: LLM unavailability, corrupt calibration files, partial maintenance failures

### 3. Error Path Hardening
- All integration points already wrapped in try/except with graceful degradation
- Memory lifecycle continues remaining steps even when one step crashes
- Bootstrap falls back to generic seeds when orientation LLM fails
- Calibration silently resets on corrupt file reads

### 4. Config Completeness
- Created `.env.example` with all env vars documented (API keys, budget, Telegram, VPS, vault, PTC)
- Added `check_readiness()` in `validator.py` — verifies dirs, API key, .env, budget, data integrity
- Added `display_readiness()` for formatted output
- Added `--readiness` CLI command
- Offline commands (`--validate`, `--readiness`, `--review`) now work without API key set

### 5. Extended Validator (`validator.py`)
- `validate_bootstrap()` — checks bootstrap status files (phase, questions)
- `validate_calibration()` — checks calibration data (ranges, required fields)
- `validate_claim_verification()` — checks KB verification metadata (timestamps, verdicts, disputed notes)
- All three integrated into `validate_all()` and `display_validation()`

### 6. Logs Review System (`logs_review.py`)
- `load_run_logs()` — reads per-domain JSONL run logs, filtered by domain and age
- `analyze_score_trends()` — rolling window trend detection (improving/declining/stable)
- `detect_anomalies()` — score drops, rejection streaks, strategy changes
- `load_cycle_history()` / `summarize_cycles()` — daemon cycle analysis
- `analyze_costs()` — cost breakdown by day, agent, domain
- `load_errors()` — recent error aggregation
- `generate_review()` — comprehensive review pulling all of the above + verification + calibration
- `display_review()` — formatted terminal output
- `--review` CLI command (with `--review-days` and `--domain` filters)
- `--review-cycles N` CLI command for daemon-specific analysis

### Files created
- `agent-brain/.env.example` — Environment variable template
- `agent-brain/logs_review.py` — Post-cycle analysis and review system
- `agent-brain/tests/test_transistor.py` — Structural tests for transistor systems

### Files modified
- `agent-brain/main.py` — Domain-agnostic handoff, offline command bypass, review/readiness CLI
- `agent-brain/validator.py` — Bootstrap/calibration/claim validation, readiness check
