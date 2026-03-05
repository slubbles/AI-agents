# Cortex Resource Catalog

> External resources evaluated for integration into Cortex. Strategy: don't build from scratch when others have perfected it. Pull open-source repos, skills, and knowledge files that boost Cortex capabilities.

**Last Updated:** Session of current date
**Total Evaluated:** 17 resources (across 3 sessions)

---

## Legend

| Status | Meaning |
|--------|---------|
| INTEGRATED | Already pulled into Cortex and wired up |
| HIGH VALUE | Worth integrating, not yet done |
| USEFUL LATER | Good resource, not needed right now |
| NOT NOW | Has value but blocked by complexity or timing |
| NOT USEFUL | Doesn't fit Cortex needs |

---

## INTEGRATED (Already In Cortex)

### 1. agent-browser (v0.16.3)
- **Source:** `nicepkg/agent-browser` (npm)
- **What it is:** AI-native browser that returns accessibility tree with @ref identifiers instead of raw HTML
- **What we took:** CLI wrapper in `hands/tools/browser.py`, replaces Playwright
- **Commit:** `ef9cb49`
- **Value:** Lets executor navigate web, fill forms, click elements with structured output

### 2. Vercel Agent Skills (react-best-practices + web-design-guidelines)
- **Source:** `vercel/agent-skills` (GitHub)
- **What it is:** 58 React rules + 100+ web interface guidelines packaged as markdown
- **What we took:** Two identity files: `identity/react_best_practices.md` (79 lines), `identity/web_interface_guidelines.md` (130 lines). Wired into `executor.py._build_system_prompt()` and `planner.py._build_system_prompt()`
- **Commit:** `e39539b`
- **Value:** Production-grade coding standards injected into every build

---

## HIGH VALUE (Should Integrate)

### 4. everything-claude-code (60K+ stars)
- **Source:** `affaan-m/everything-claude-code` (GitHub)
- **Repo:** https://github.com/affaan-m/everything-claude-code
- **What it is:** The most starred AI agent optimization system. 58 skills, 14 agents, 32 commands, 992 tests. Anthropic Hackathon winner. Covers:
  - **14 specialized agents:** planner, architect, code-reviewer, security-reviewer, tdd-guide, build-error-resolver, e2e-runner, refactor-cleaner, doc-updater, python-reviewer, database-reviewer, go-reviewer, go-build-resolver, chief-of-staff
  - **58 skills across domains:** `market-research` (source-attributed competitive analysis), `investor-outreach` (personalized fundraising), `content-engine` (multi-platform content repurposing), `article-writing` (long-form without AI tone), `search-first` (research-before-code workflow), `cost-aware-llm-pipeline` (model routing + budget tracking patterns), `continuous-learning-v2` (instinct-based learning with confidence scoring + project scoping), `frontend-patterns`, `backend-patterns`, `security-review`, `tdd-workflow`, `verification-loop`, `eval-harness`, `deployment-patterns`, `docker-patterns`, `postgres-patterns`, and 40+ more
  - **Rules system:** language-specific coding rules (TypeScript, Python, Go, Java)
  - **Hooks:** session memory persistence, continuous learning extraction
- **What to steal:**
  - `market-research` SKILL.md -- decision-oriented research with source attribution (directly supports Brain's research loop)
  - `content-engine` + `article-writing` -- content creation without AI tone (marketing agent)
  - `investor-outreach` + `investor-materials` -- when Cortex needs to help with fundraising
  - `search-first` SKILL.md -- research-before-code workflow (could enhance planner's pre-build phase)
  - `cost-aware-llm-pipeline` patterns -- model routing + budget tracking (validates our existing approach)
  - `continuous-learning-v2` instinct model -- confidence-scored atomic learnings with project scoping (more granular than our strategy evolution)
  - `verification-loop` + `eval-harness` -- verification patterns for executor
  - Agent definitions (planner.md, architect.md, security-reviewer.md) -- well-structured agent prompts
- **Integration difficulty:** LOW -- all markdown files, no code dependencies
- **Priority:** VERY HIGH -- single richest source of agent knowledge we've found. Cherry-pick the best skills as identity files.
- **Blocked by:** Nothing. Ready to integrate.

### 4. UI/UX Pro Max Skill
- **Source:** Community skill (openclaw marketplace)
- **What it is:** Massive searchable CSV databases of design knowledge:
  - 100 industry-specific reasoning rules (e.g., healthcare = calming blues, fintech = trust signals)
  - 67 UI style definitions with descriptions
  - 96 color palettes with hex codes
  - 57 font pairings with use cases
  - 99 UX guideline rules
- **What to steal:** The CSV databases. Currently Cortex has one static `design_system.md` (408 lines). This would let Cortex pick industry-appropriate design decisions dynamically per project.
- **Integration difficulty:** MEDIUM -- need to build a lookup function in planner/executor that queries the right CSV based on project domain
- **Priority:** HIGH -- directly supports Objective 10 (SaaS builds need good design per industry)
- **Blocked by:** Nothing. Ready to integrate.

### 5. Anthropic Knowledge Work Plugins -- Marketing Plugin
- **Source:** `anthropics/knowledge-work-plugins` (GitHub)
- **Repo:** https://github.com/anthropics/knowledge-work-plugins
- **What it is:** 5 skills for marketing:
  - `brand-voice` -- brand voice definition, tone guidelines, consistency rules
  - `campaign-planning` -- campaign strategy frameworks, timeline templates
  - `competitive-analysis` -- competitor research methodology, messaging matrices, battlecard frameworks
  - `content-creation` -- blog/social/email/landing page/press release/case study templates, SEO fundamentals, headline formulas, channel-specific best practices
  - `performance-analytics` -- marketing metrics frameworks
- **What to steal:** The SKILL.md files are extremely high quality (~8-10KB each). Pure markdown, no code dependencies. Content-creation alone has complete templates for every content type Cortex would build.
- **Integration difficulty:** LOW -- just markdown files. Copy relevant ones to `identity/` or load on-demand based on task type
- **Priority:** HIGH -- marketing copy is critical for landing pages, outreach, SEO content
- **Blocked by:** Nothing. Ready to integrate.

### 6. Anthropic Knowledge Work Plugins -- Sales Plugin
- **Source:** `anthropics/knowledge-work-plugins` (GitHub)
- **What it is:** 6 skills:
  - `account-research` -- prospect research frameworks
  - `call-prep` -- meeting preparation workflows
  - `competitive-intelligence` -- competitive intel gathering
  - `create-an-asset` -- sales asset creation (decks, one-pagers)
  - `daily-briefing` -- sales activity summaries
  - `draft-outreach` -- personalized cold outreach workflow (research-first approach, multi-channel templates)
- **What to steal:** `draft-outreach` is gold for the OLJ outreach strategy. Research-first personalization framework that maps directly to what Cortex needs for client acquisition.
- **Integration difficulty:** LOW -- markdown skill files
- **Priority:** HIGH -- directly supports revenue generation through outreach
- **Blocked by:** Nothing.

### 7. Anthropic Knowledge Work Plugins -- Product Management Plugin
- **Source:** `anthropics/knowledge-work-plugins` (GitHub)
- **What it is:** 6 skills:
  - `competitive-analysis` -- market/product competitive analysis
  - `feature-spec` -- feature specification writing
  - `metrics-tracking` -- product metrics frameworks
  - `roadmap-management` -- roadmap planning
  - `stakeholder-comms` -- stakeholder communication templates
  - `user-research-synthesis` -- user research analysis
- **What to steal:** `feature-spec` and `user-research-synthesis` for when Cortex validates and specs out SaaS products
- **Integration difficulty:** LOW
- **Priority:** MEDIUM -- useful once Cortex is building SaaS products autonomously

### 8. Claude Official Plugin -- frontend-design
- **Source:** `anthropics/claude-plugins-official` (GitHub)
- **Repo:** https://github.com/anthropics/claude-plugins-official
- **What it is:** Single SKILL.md (4.3KB) focused on creating distinctive, non-generic frontend interfaces. Key principles:
  - Design thinking before coding (purpose, tone, constraints, differentiation)
  - Anti-AI-slop rules (no Inter/Roboto, no purple gradients, no cookie-cutter designs)
  - Typography: distinctive font choices, unexpected pairings
  - Color: dominant colors with sharp accents
  - Motion: CSS-only animations, scroll-triggering, staggered reveals
  - Spatial composition: asymmetry, overlap, diagonal flow, grid-breaking
  - Backgrounds: gradient meshes, noise textures, grain overlays
- **What to steal:** The anti-AI-slop guidelines and design thinking framework. Complements our existing `design_system.md` with a "make it distinctive" philosophy.
- **Integration difficulty:** LOW -- single markdown file
- **Priority:** HIGH -- directly prevents Cortex from producing generic-looking sites

### 9. Claude Official Plugin -- feature-dev
- **Source:** `anthropics/claude-plugins-official`
- **What it is:** 7-phase structured feature development workflow with specialized sub-agents:
  1. Discovery (clarify requirements)
  2. Codebase Exploration (parallel agents explore existing code)
  3. Clarifying Questions (fill gaps before design)
  4. Architecture Design (multiple approaches: minimal, clean, performant)
  5. Implementation Planning
  6. Implementation
  7. Quality Review
- **What to steal:** The 7-phase workflow structure. Cortex planner currently does plan-then-execute. This adds discovery + clarification + multi-approach architecture phases before coding.
- **Integration difficulty:** MEDIUM -- would need to adapt the workflow into planner.py phases
- **Priority:** MEDIUM -- improves build quality but requires planner refactor

### 10. Claude Official Plugin -- code-review
- **Source:** `anthropics/claude-plugins-official`
- **What it is:** Automated PR review using 4 parallel specialized agents:
  - 2 agents for guidelines compliance
  - 1 agent for obvious bugs
  - 1 agent for git history context analysis
  - Confidence scoring (0-100), only surfaces issues >= 80 confidence
- **What to steal:** The confidence-based scoring approach for filtering false positives. Could apply to Cortex's exec_validator to reduce noise.
- **Integration difficulty:** LOW-MEDIUM -- the scoring concept is simple; the agent parallelism is more complex
- **Priority:** LOW -- Cortex already has exec_validator + critic

---

## USEFUL LATER (Park for Now)

### 11. idea-reality-mcp (Pre-Build Validation)
- **Source:** `mnemox-ai/idea-reality-mcp` (GitHub, 264 stars)
- **Repo:** https://github.com/mnemox-ai/idea-reality-mcp
- **What it is:** MCP tool that checks if an idea already exists before you build it. Searches 5 sources in parallel (GitHub, Hacker News, npm, PyPI, Product Hunt) and returns a 0-100 "reality signal" with top competitors.
- **What to steal:** The validation concept maps directly to Cortex's Signal/Validation Agent (item 5-6 in build order). This tool does exactly what those agents should do: check if a SaaS idea is already saturated before building.
- **Integration approach:** Could use as an MCP server directly (`uvx idea-reality-mcp`), or extract the search logic (Python, ~6 source files) into Brain's researcher.py
- **Integration difficulty:** LOW as MCP server (just add to mcp_servers.json), MEDIUM to extract and embed
- **Priority:** HIGH -- prevents Cortex from building things that already exist with 5000 stars. Direct path to Signal Agent.
- **Blocked by:** Nothing.

### 12. clihub (MCP to CLI Converter)
- **Source:** Community tool
- **What it is:** Converts MCP server tools into standalone CLI commands
- **Why useful later:** When Cortex needs to integrate with external services (Stripe, Supabase, etc.), clihub could expose MCP tools as CLI commands the executor can call
- **Why not now:** Cortex already has `context_router.py` for MCP tool filtering. Don't need CLI wrappers until we're actually integrating external services.
- **Priority:** LOW -- revisit when building service integrations

### 13. OpenClaw Self-Improving Agent (v1.0.11)
- **Source:** `zip-files/self-improving-agent-1.0.11.zip` (extracted to `/tmp/self-improving-agent/`)
- **What it is:** 647-line SKILL.md for structured error/learning capture:
  - `LEARNINGS.md` -- corrections, knowledge gaps, best practices (with timestamps, priorities, statuses)
  - `ERRORS.md` -- command failures with structured entries
  - `FEATURE_REQUESTS.md` -- user feature requests
  - Promotion pipeline: behavioral patterns -> SOUL.md, workflow improvements -> AGENTS.md, tool gotchas -> TOOLS.md
  - Cross-session communication via sessions_list, sessions_history
- **What to steal:** The structured learning entry format (timestamp + priority + status + area + metadata). Our `research_lessons.py` + `.github/lessons.md` already do something similar but less structured.
- **Integration difficulty:** LOW -- just adopting the entry format in our learning files
- **Priority:** LOW -- our existing learning system works. This is a polish improvement.
- **Why not now:** Cortex's meta_analyst + strategy_store already handle behavioral adaptation (Layer 3). This is a less sophisticated version of what we have.

### 14. OpenClaw Proactive Agent (v3.1.0)
- **Source:** `zip-files/proactive-agent-3.1.0.zip` (extracted to `/tmp/proactive-agent/`)
- **What it is:** 632-line SKILL.md + 7 asset files for making agents proactive and persistent:
  - **WAL Protocol** -- Write-Ahead Logging: scan every message for corrections/preferences/decisions, write to SESSION-STATE.md BEFORE responding
  - **Working Buffer Protocol** -- capture every exchange at risk of being lost during context compaction (at 60% context usage)
  - **Compaction Recovery** -- detect and recover from context loss
  - **3-tier memory** -- SESSION-STATE.md (active), daily logs, MEMORY.md (curated long-term)
  - **HEARTBEAT.md** -- periodic self-checks: security scan, self-healing, proactive surprise suggestions, memory maintenance
  - **Reverse Prompting** -- agent asks human questions to surface unknown unknowns
- **What to steal:**
  - HEARTBEAT.md concept: periodic self-check routine (security, self-healing, cleanup) -- maps to our watchdog.py
  - WAL Protocol idea: always persist state before responding -- useful for exec_memory resilience
- **Integration difficulty:** MEDIUM -- concepts need adaptation to our architecture
- **Priority:** LOW -- our watchdog + orchestrator already handle most of this. WAL Protocol is interesting for exec_memory but not urgent.
- **Why not now:** Most of this targets Claude Code/desktop agents with persistent sessions. Cortex runs headless with its own persistence layer.

---

## NOT NOW (Blocked or Wrong Timing)

### 15. Google Stitch MCP Server
- **Source:** Google Labs
- **What it is:** MCP server that generates UI from screenshots/descriptions using Google's Stitch API
- **Why not now:**
  - Outputs raw HTML, not React/Next.js components
  - Requires Google Cloud auth setup (OAuth complexity)
  - Would need an HTML-to-React conversion step
- **When to revisit:** When Cortex needs screenshot-to-code capability and we've solved the React conversion pipeline

---

## NOT USEFUL (Skip)

### 16. claude-agent-sdk-python
- **Source:** `anthropics/claude-agent-sdk-python` (GitHub, 5165 stars)
- **Repo:** https://github.com/anthropics/claude-agent-sdk-python
- **What it is:** Official Anthropic Python SDK for Claude Agent (Claude Code as a library). Provides:
  - `query()` async function for programmatic Claude Code queries
  - `ClaudeSDKClient` for bidirectional interactive conversations
  - Custom tools as in-process MCP servers (no subprocess overhead)
  - Hooks system for deterministic processing at specific points in agent loop
  - Permission modes, working directory control, tool restrictions
- **What to steal:** Nothing directly. This is a wrapper around Claude Code CLI. Cortex already has its own executor loop with tool_use, and we use OpenRouter (not Claude Code). The SDK requires Claude Code CLI bundled.
- **Integration difficulty:** N/A
- **Priority:** NOT APPLICABLE -- this replaces the kind of system Cortex IS. Using it would mean replacing our executor with Claude Code, losing control over model routing, cost tracking, and the entire self-learning loop.
- **When relevant:** Only if we ever want to delegate specific sub-tasks to Claude Code as a black-box tool (e.g., "let Claude Code handle this complex refactor while Cortex orchestrates"). That's a Phase 5+ consideration.

### 17. 21st.dev
- **What it is:** Paid component marketplace for AI-generated UI components
- **Why not useful:** Costs money per component. Cortex should generate its own components using the design skills we're integrating.

### 18. claude-context-mode
- **What it is:** Custom context management strategy for Claude Code sessions
- **Why not useful:** Cortex controls its own context pipeline end-to-end via `context_router.py`, planner system prompt, and executor system prompt. This targets manual Claude Code users.

---

## ADDITIONAL RESOURCES (Not Yet Deeply Evaluated)

### Anthropic Knowledge Work Plugins -- Remaining Plugins
These exist in `anthropics/knowledge-work-plugins` but haven't been deeply read:

| Plugin | Skills | Potential Value for Cortex |
|--------|--------|--------------------------|
| customer-support | customer-research, escalation, knowledge-management, response-drafting, ticket-triage | LOW -- Cortex doesn't do support (yet) |
| productivity | memory-management, task-management | LOW -- we have our own task/memory systems |
| legal | contract-review, compliance, legal-risk-assessment, nda-triage, canned-responses, meeting-briefing | LOW -- niche, not current focus |
| finance | audit-support, close-management, financial-statements, journal-entry-prep, reconciliation, variance-analysis | LOW -- niche |
| data | data-exploration, data-validation, data-visualization, interactive-dashboard-builder, sql-queries, statistical-analysis | MEDIUM -- could help when building data-heavy SaaS |
| enterprise-search | knowledge-synthesis, search-strategy, source-management | LOW |
| bio-research | instrument-data-to-allotrope, nextflow-development, scientific-problem-selection, scvi-tools, single-cell-rna-qc | NONE -- domain-specific |

### Claude Official Plugins -- Remaining Plugins
From `anthropics/claude-plugins-official`:

| Plugin | Type | Potential Value |
|--------|------|----------------|
| skill-creator | Create new skills from patterns | MEDIUM -- meta-tool for creating Cortex skills |
| security-guidance | Hook-based security reminders during coding | MEDIUM -- could augment executor security checks |
| code-simplifier | Simplify complex code | LOW |
| ralph-loop | Agent loop patterns | MEDIUM -- worth investigating |
| hookify | Hook system for agent workflows | MEDIUM -- worth investigating |
| agent-sdk-dev | Agent SDK development | LOW |
| explanatory-output-style | Output formatting | LOW |
| learning-output-style | Learning-focused output | LOW |
| Various LSP plugins | Language server integrations (pyright, typescript, etc.) | LOW -- Cortex doesn't need IDE features |
| External: supabase, stripe, playwright, github, gitlab, linear, slack | Service integrations | USEFUL LATER when building integrations |

---

## Integration Priority Queue

**Immediate (before Objective 10):**
1. **everything-claude-code skills** -- cherry-pick market-research, content-engine, search-first, verification-loop, agent prompts
2. **idea-reality-mcp** -- add as MCP server for pre-build validation (Signal Agent shortcut)
3. **UI/UX Pro Max** -- dynamic industry-specific design decisions
4. **Marketing content-creation skill** -- landing page/content templates
5. **frontend-design plugin** -- anti-AI-slop design philosophy
6. **Sales draft-outreach skill** -- OLJ client outreach framework

**Next Sprint:**
7. **ECC continuous-learning-v2** -- instinct model concepts for strategy evolution enhancement
8. **Marketing competitive-analysis skill** -- market research for SaaS validation
9. **Marketing brand-voice skill** -- consistent brand identity per project
10. **PM feature-spec skill** -- structured feature specifications
11. **PM user-research-synthesis** -- user research analysis for validation

**Future:**
12. feature-dev workflow concepts -- enhanced planner phases
13. code-review confidence scoring -- better validation filtering
14. Proactive agent HEARTBEAT concept -- watchdog enhancement
15. Self-improving agent entry format -- learning system polish
16. clihub -- when service integrations are needed
17. Remaining anthropic plugins -- as domains require them

---

## OpenClaw Skills Inventory (52 skills in workspace)
Located at `/workspaces/AI-agents/openclaw/skills/`. Most are app-specific integrations (Apple Notes, Discord, Slack, Spotify, etc.) or platform tools. Notable ones worth checking:
- `coding-agent` -- may have useful coding patterns
- `skill-creator` -- meta-skill for creating skills
- `summarize` -- summarization skill
- `sherpa-onnx-tts` -- text-to-speech (future voice features)
- `openai-image-gen` -- image generation wrapper
