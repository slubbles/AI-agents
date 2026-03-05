# Resource Integration Masterplan

> Structured series of objectives to integrate all HIGH VALUE and USEFUL LATER resources from RESOURCE_CATALOG.md into Cortex. Each objective is self-contained, testable, and builds on the previous one.

**Created:** March 5, 2026
**Strategy:** Don't build from scratch. Pull proven open-source skills as identity files and wire them into the right injection points.

**Architecture principle:** All external knowledge enters Cortex as markdown files in `identity/` (or a new `identity/skills/` subdirectory). The system prompt builders in `executor.py`, `planner.py`, and `identity_loader.py` load them based on task context. No code dependencies on external repos -- we extract the knowledge, not the infrastructure.

---

## Current State

**Identity files (10):** boundaries.md, design_system.md, ethics.md, goals.md, marketing_design.md, react_best_practices.md, risk.md, taste.md, visual_scoring_rubric.md, web_interface_guidelines.md

**Injection points:**
- `identity_loader.py` -- loads goals/ethics/boundaries/risk/taste into Brain agents (researcher, critic, cortex)
- `executor.py._build_system_prompt()` -- loads design_system/marketing_design + react_best_practices + web_interface_guidelines (hardcoded file paths, 3KB cap per file)
- `planner.py._build_system_prompt()` -- loads design_system + react_best_practices + web_interface_guidelines (hardcoded, 3KB cap)

**Problem with current approach:** Every new identity file requires hardcoded path additions in executor.py and planner.py. This doesn't scale to 20+ skill files. We need a skills loader.

---

## Objective 11: Skills Loader Infrastructure

> Build the foundation that all subsequent objectives depend on. A dynamic skills loader that replaces hardcoded file paths with category-based skill loading.

### What "done" looks like
- New directory: `identity/skills/` with subdirectories by category
- New module: `skills_loader.py` that loads skills by category/tag
- Planner and executor use `skills_loader.load_skills(categories)` instead of hardcoded file paths
- Existing identity files untouched (they stay in `identity/`)
- All existing tests pass

### Deliverables

**11.1 -- Create `identity/skills/` directory structure**
```
identity/skills/
  design/          -- visual design, typography, color, layout skills
  coding/          -- code quality, patterns, best practices
  marketing/       -- content creation, brand voice, outreach
  sales/           -- outreach, prospecting, pitching
  product/         -- feature specs, user research, roadmapping
  research/        -- market research, competitive analysis
  validation/      -- idea validation, reality checks
  workflow/        -- process skills (search-first, verification loops)
```

**11.2 -- Create `skills_loader.py`**
- `load_skills(categories: list[str], max_chars: int = 8000) -> str`
  - Scans `identity/skills/{category}/` for .md files
  - Concatenates them with section headers
  - Respects max_chars budget (prioritizes shorter files first, or alphabetical)
  - Returns formatted string ready for prompt injection
- `list_skills(category: str = None) -> list[dict]`
  - Returns metadata about available skills (name, category, size)
- Skills are plain .md files with optional YAML frontmatter for metadata (name, description, tags)

**11.3 -- Wire `skills_loader` into planner.py**
- Planner determines relevant categories from the task description (keyword matching, similar to context_router.py)
- Calls `load_skills(categories)` and appends to system prompt
- Remove hardcoded react_best_practices and web_interface_guidelines loading (they move to `identity/skills/coding/`)
- Keep design_system.md and marketing_design.md loading as-is (they're large and page-type-specific)

**11.4 -- Wire `skills_loader` into executor.py**
- Same pattern: determine categories from plan context, load relevant skills
- Remove hardcoded react_best_practices and web_interface_guidelines loading
- Keep design system loading as-is

**11.5 -- Move existing skills into new structure**
- `react_best_practices.md` -> `identity/skills/coding/react_best_practices.md`
- `web_interface_guidelines.md` -> `identity/skills/coding/web_interface_guidelines.md`
- Keep originals as symlinks for backward compatibility during transition

**11.6 -- Tests**
- Unit tests for skills_loader (load, list, max_chars budget, missing dirs)
- Integration tests that planner/executor correctly load skills
- Verify all existing tests still pass

---

## Objective 12: everything-claude-code Skills Integration

> Cherry-pick the highest-value skills from ECC (60K stars) and install them as identity skill files.

### Dependencies: Objective 11 (skills loader)

### What "done" looks like
- 8-10 ECC skill files installed in `identity/skills/`
- Skills load correctly via skills_loader when relevant task categories match
- All tests pass

### Deliverables

**12.1 -- Download and adapt ECC market-research skill**
- Source: `affaan-m/everything-claude-code/skills/market-research/SKILL.md`
- Target: `identity/skills/research/market_research.md`
- Adapt: Strip ECC-specific references, adjust for Cortex context (Brain researcher uses this)
- This gives Brain a structured market research methodology with source attribution

**12.2 -- Download and adapt ECC search-first skill**
- Source: `skills/search-first/SKILL.md`
- Target: `identity/skills/workflow/search_first.md`
- Adapt: Strip Claude Code references, make it generic for Cortex planner
- This adds a "research before code" phase to every build

**12.3 -- Download and adapt ECC content-engine + article-writing**
- Source: `skills/content-engine/SKILL.md`, `skills/article-writing/SKILL.md`
- Target: `identity/skills/marketing/content_engine.md`, `identity/skills/marketing/article_writing.md`
- Adapt: Strip ECC references, focus on landing page copy and blog content
- This gives executor marketing content capabilities without AI tone

**12.4 -- Download and adapt ECC verification-loop skill**
- Source: `skills/verification-loop/SKILL.md`
- Target: `identity/skills/workflow/verification_loop.md`
- Adapt: Map to Cortex's exec_validator flow
- Strengthens executor's self-verification during builds

**12.5 -- Download and adapt ECC cost-aware-llm-pipeline patterns**
- Source: `skills/cost-aware-llm-pipeline/SKILL.md`
- Target: `identity/skills/workflow/cost_aware_pipeline.md`
- Adapt: Reference Cortex's 4-tier model setup, validate our approach
- Documents cost optimization patterns as accessible reference

**12.6 -- Download and adapt ECC frontend-patterns + backend-patterns**
- Source: `skills/frontend-patterns/SKILL.md`, `skills/backend-patterns/SKILL.md`
- Target: `identity/skills/coding/frontend_patterns.md`, `identity/skills/coding/backend_patterns.md`
- Adapt: Filter to Next.js/React/Node relevant patterns only

**12.7 -- Download and adapt ECC security-review skill**
- Source: `skills/security-review/SKILL.md`
- Target: `identity/skills/coding/security_review.md`
- Adapt: OWASP-focused security checklist for executor to reference during builds

**12.8 -- Download and adapt ECC deployment-patterns skill**
- Source: `skills/deployment-patterns/SKILL.md`
- Target: `identity/skills/coding/deployment_patterns.md`
- Adapt: Filter to Vercel/Next.js deployment patterns

**12.9 -- Tests**
- Verify all new skills load via skills_loader
- Test category matching picks correct skills for sample tasks
- All existing tests pass

---

## Objective 13: Anthropic Marketing + Sales Skills Integration

> Install Anthropic's official marketing and sales skills -- the highest-quality prompt engineering for content and outreach.

### Dependencies: Objective 11 (skills loader)

### What "done" looks like
- 4 marketing skill files + 1 sales skill file installed
- Skills auto-load when planner/executor detects marketing/sales task context
- All tests pass

### Deliverables

**13.1 -- Download and install marketing/content-creation skill**
- Source: `anthropics/knowledge-work-plugins/marketing/skills/content-creation/SKILL.md`
- Target: `identity/skills/marketing/content_creation.md`
- Adapt: Strip YAML frontmatter, keep all templates (blog, social, email, landing page, press release, case study), SEO fundamentals, headline formulas

**13.2 -- Download and install marketing/competitive-analysis skill**
- Source: `marketing/skills/competitive-analysis/SKILL.md`
- Target: `identity/skills/research/competitive_analysis.md`
- Adapt: Keep messaging matrix, value prop comparison, narrative analysis frameworks

**13.3 -- Download and install marketing/brand-voice skill**
- Source: `marketing/skills/brand-voice/SKILL.md`
- Target: `identity/skills/marketing/brand_voice.md`
- Adapt: Keep voice definition framework, tone guidelines, consistency rules

**13.4 -- Download and install marketing/campaign-planning skill**
- Source: `marketing/skills/campaign-planning/SKILL.md`
- Target: `identity/skills/marketing/campaign_planning.md`

**13.5 -- Download and install sales/draft-outreach skill**
- Source: `sales/skills/draft-outreach/SKILL.md`
- Target: `identity/skills/sales/draft_outreach.md`
- Adapt: Keep research-first framework, personalization approach, multi-channel templates
- Critical for OLJ client outreach strategy

**13.6 -- Tests**
- Verify marketing skills load for "build a landing page" type tasks
- Verify sales skills load for "outreach" type tasks
- All existing tests pass

---

## Objective 14: Frontend Design Anti-Slop + UI/UX Pro Max

> Make Cortex produce visually distinctive sites. Two resources: the Claude frontend-design plugin (philosophy) and UI/UX Pro Max (data).

### Dependencies: Objective 11 (skills loader)

### What "done" looks like
- frontend-design anti-slop skill installed and loading for all frontend tasks
- UI/UX Pro Max CSV databases installed with a lookup function
- Planner can query industry-specific design rules, palettes, and font pairings
- Executor references the anti-slop guidelines during every build
- All tests pass

### Deliverables

**14.1 -- Download and install frontend-design SKILL.md**
- Source: `anthropics/claude-plugins-official/plugins/frontend-design/skills/frontend-design/SKILL.md`
- Target: `identity/skills/design/frontend_design.md`
- Adapt: Keep all anti-AI-slop rules, typography guidance, motion principles, spatial composition rules
- This loads automatically for ALL frontend builds via skills_loader

**14.2 -- Install UI/UX Pro Max CSV databases**
- Source: openclaw skill (extract from marketplace or local zip)
- Target: `identity/skills/design/data/` directory:
  - `industry_rules.csv` -- 100 industry reasoning rules
  - `ui_styles.csv` -- 67 style definitions
  - `color_palettes.csv` -- 96 palettes with hex codes
  - `font_pairings.csv` -- 57 font pairings
  - `ux_guidelines.csv` -- 99 UX guidelines

**14.3 -- Build design lookup function**
- New function in `skills_loader.py`: `lookup_design_data(industry: str, data_type: str) -> str`
- Queries CSV files to return industry-appropriate design recommendations
- Called by planner when building for a specific industry/domain
- Returns formatted string: "For [industry]: use [colors], pair [fonts], follow [rules]"

**14.4 -- Wire design lookup into planner.py**
- Planner extracts industry/domain from task description
- Calls `lookup_design_data(industry)` and includes in system prompt
- Falls back to generic design_system.md if no industry match

**14.5 -- Tests**
- Test CSV loading and lookup for various industries
- Test planner correctly queries design data
- Test frontend-design skill loads for frontend tasks
- Test fallback behavior when industry not found
- All existing tests pass

---

## Objective 15: Product Management + Feature Development Skills

> Structured product thinking for when Cortex validates and specs SaaS products.

### Dependencies: Objective 11 (skills loader)

### What "done" looks like
- PM skills installed for feature spec and user research
- Feature-dev workflow concepts adapted into planner enhancement
- All tests pass

### Deliverables

**15.1 -- Download and install PM feature-spec skill**
- Source: `anthropics/knowledge-work-plugins/product-management/skills/feature-spec/SKILL.md`
- Target: `identity/skills/product/feature_spec.md`
- Adapt: Feature specification writing framework for SaaS product development

**15.2 -- Download and install PM user-research-synthesis skill**
- Source: `product-management/skills/user-research-synthesis/SKILL.md`
- Target: `identity/skills/product/user_research_synthesis.md`
- Adapt: User research analysis framework for validation phase

**15.3 -- Adapt feature-dev workflow concepts into planner**
- Source: `anthropics/claude-plugins-official/plugins/feature-dev/` (7-phase workflow)
- DON'T copy the whole plugin. Extract the 7-phase structure as a planning methodology skill:
  - `identity/skills/workflow/feature_dev_methodology.md`
  - Covers: Discovery -> Codebase Exploration -> Clarifying Questions -> Architecture Design -> Implementation Planning -> Implementation -> Quality Review
- Planner can reference this when building complex features

**15.4 -- Tests**
- Verify product skills load for "build a SaaS" type tasks
- Verify workflow skills load for complex feature requests
- All existing tests pass

---

## Objective 16: idea-reality-mcp Integration (Signal Agent)

> Pre-build validation: check if an idea already exists before Cortex builds it. This is the shortest path to the Signal Agent from the build order.

### Dependencies: None (independent of skills loader)

### What "done" looks like
- idea-reality-mcp added as an MCP server in `mcp_servers.json`
- New tool exposed to planner/executor: `idea_check(description, depth)`
- Before any SaaS build, planner runs idea_check and factors the reality signal into the plan
- Reality signal >= 80 triggers a "pivot or differentiate" requirement in the plan
- All tests pass

### Deliverables

**16.1 -- Add idea-reality-mcp to mcp_servers.json**
```json
"idea-reality": {
  "command": "uvx",
  "args": ["idea-reality-mcp"],
  "categories": ["validation", "research"],
  "description": "Pre-build reality check -- scans GitHub, HN, npm, PyPI, Product Hunt for existing solutions",
  "enabled": true
}
```

**16.2 -- Add validation category to context_router.py**
- Add keyword mapping: `\b(validate|reality check|idea check|already exists|competition|competitors)\b` -> `["validation"]`
- This ensures idea-reality tools surface when relevant

**16.3 -- Add pre-build validation step to planner.py**
- Before generating the build plan, planner checks if idea_check tool is available
- If available and task is a new SaaS/product build, run idea_check first
- Include the reality signal in the plan context:
  - Signal 0-30: "Low competition. Proceed with confidence."
  - Signal 31-60: "Moderate competition. Differentiate on [aspect]."
  - Signal 61-80: "High competition. Must have clear differentiator."
  - Signal 81-100: "Saturated market. Consider pivoting or finding a niche."

**16.4 -- Install idea-reality-mcp on VPS**
- `pip install idea-reality-mcp` or `pipx install idea-reality-mcp` on VPS
- Verify `uvx idea-reality-mcp` runs

**16.5 -- Tests**
- Mock test for idea_check integration in planner
- Test context_router routes validation keywords correctly
- Test planner handles various reality signal levels
- All existing tests pass

---

## Objective 17: ECC Continuous Learning Concepts

> Enhance Cortex's self-learning with ECC's instinct-based learning model: confidence-scored atomic learnings with project scoping.

### Dependencies: None

### What "done" looks like
- `research_lessons.py` enhanced with structured entry format (timestamps, confidence scores, domain tags)
- Learning entries are project-scoped (not global soup)
- Meta-analyst considers confidence scores when extracting patterns
- All tests pass

### Deliverables

**17.1 -- Enhance learning entry format in research_lessons.py**
- Add structured fields: confidence (0.0-1.0), domain, observation_count, first_seen, last_seen
- Inspired by ECC's instinct model but adapted to our JSON-based storage
- Existing entries migrate seamlessly (missing fields get defaults)

**17.2 -- Add confidence scoring to lesson extraction**
- When meta_analyst extracts a lesson, assign initial confidence (0.5)
- Confidence increases when same pattern observed again (+0.1 per observation)
- Confidence decreases if contradicted (-0.2)
- Only lessons with confidence >= 0.6 inform strategy rewrites

**17.3 -- Add project scoping**
- Lessons tagged with domain (from current brain loop) or project (from hands build)
- Global lessons: seen in 2+ domains/projects
- Domain lessons: only apply when working in that domain

**17.4 -- Tests**
- Test entry format migration
- Test confidence scoring logic
- Test project scoping
- All existing tests pass

---

## Objective 18: Code Review Confidence Scoring

> Apply ECC's code-review confidence-scoring concept to exec_validator to reduce false positive validation failures.

### Dependencies: None

### What "done" looks like
- exec_validator scores each issue with confidence (0-100)
- Only issues with confidence >= 70 are reported as failures
- Reduces exec_validator noise without missing real problems
- All tests pass

### Deliverables

**18.1 -- Add confidence scoring to validator.py**
- When exec_validator identifies an issue, it also assigns a confidence score
- Modify the validation prompt to request confidence per issue
- Parse confidence from LLM response

**18.2 -- Filter low-confidence issues**
- Issues below 70 confidence logged but not treated as failures
- Issues 70-89 reported as warnings
- Issues 90-100 reported as errors (block deployment)

**18.3 -- Tests**
- Test confidence parsing from validator response
- Test filtering at different thresholds
- All existing tests pass

---

## Objective 19: OpenClaw Concept Integrations (Polish)

> Light-touch integrations of useful concepts from OpenClaw's proactive-agent and self-improving-agent.

### Dependencies: None

### What "done" looks like
- Watchdog enhanced with HEARTBEAT-style periodic self-checks
- Exec memory uses WAL-style write-before-respond for resilience
- Learning entries use structured format from self-improving-agent
- All tests pass

### Deliverables

**19.1 -- Enhance watchdog with HEARTBEAT-style checks**
- Add to watchdog.py's periodic check cycle:
  - Security integrity check (confirm no unexpected config changes)
  - Resource cleanup (old log files, orphaned processes)
  - Memory maintenance (flag stale exec_memory entries)
- Inspired by proactive-agent's HEARTBEAT.md but adapted for headless operation

**19.2 -- Add WAL-style persistence to exec_memory**
- Before executor starts a new step, write the current state to disk
- If executor crashes mid-step, state can be recovered on restart
- Simple: write a checkpoint JSON after each step completion

**19.3 -- Enhance lessons format with self-improving-agent structure**
- If not already done in Objective 17, add:
  - Timestamp + priority + status + area fields
  - Promotion concept: high-confidence lessons auto-surface in relevant agent prompts

**19.4 -- Tests**
- Test watchdog new checks
- Test exec_memory checkpoint write/recovery
- All existing tests pass

---

## Objective 20: Remaining Anthropic Plugin Skills

> Install the remaining useful skills from Anthropic's knowledge-work-plugins that have MEDIUM priority.

### Dependencies: Objective 11 (skills loader)

### What "done" looks like
- Data plugin skills available for data-heavy SaaS builds
- PM stakeholder-comms and roadmap skills available
- Marketing performance-analytics skill installed
- All tests pass

### Deliverables

**20.1 -- Install data plugin skills**
- `data-exploration/SKILL.md` -> `identity/skills/coding/data_exploration.md`
- `sql-queries/SKILL.md` -> `identity/skills/coding/sql_queries.md`
- `data-visualization/SKILL.md` -> `identity/skills/coding/data_visualization.md`
- These load when task involves data-heavy features

**20.2 -- Install remaining PM skills**
- `roadmap-management/SKILL.md` -> `identity/skills/product/roadmap_management.md`
- `stakeholder-comms/SKILL.md` -> `identity/skills/product/stakeholder_comms.md`
- `metrics-tracking/SKILL.md` -> `identity/skills/product/metrics_tracking.md`

**20.3 -- Install marketing performance-analytics**
- `performance-analytics/SKILL.md` -> `identity/skills/marketing/performance_analytics.md`

**20.4 -- Install remaining sales skills**
- `account-research/SKILL.md` -> `identity/skills/sales/account_research.md`
- `competitive-intelligence/SKILL.md` -> `identity/skills/sales/competitive_intelligence.md`

**20.5 -- Tests**
- Verify all new skills load via skills_loader
- Category matching works for data/product/marketing tasks
- All existing tests pass

---

## Objective 21: ECC Agent Prompts + Investor Skills

> Install ECC's well-structured agent prompt definitions and business skills for fundraising/investor work.

### Dependencies: Objective 11 (skills loader)

### What "done" looks like
- Security-reviewer and architect agent prompts adapted for Cortex's exec_validator
- Investor-outreach and investor-materials skills available
- All tests pass

### Deliverables

**21.1 -- Adapt ECC security-reviewer.md for validator**
- Source: `agents/security-reviewer.md`
- Extract the security review checklist and vulnerability patterns
- Integrate into exec_validator's system prompt (or as a skill in `identity/skills/coding/`)

**21.2 -- Adapt ECC architect.md for planner**
- Source: `agents/architect.md`
- Extract the architecture decision framework
- Install as `identity/skills/workflow/architecture_decisions.md`
- Planner references this when building complex multi-service features

**21.3 -- Install ECC investor-outreach + investor-materials**
- Source: `skills/investor-outreach/SKILL.md`, `skills/investor-materials/SKILL.md`
- Target: `identity/skills/sales/investor_outreach.md`, `identity/skills/sales/investor_materials.md`
- Available when Cortex helps with fundraising tasks

**21.4 -- Tests**
- Verify agent prompt concepts properly integrated
- All existing tests pass

---

## Objective 22: Service Integration Foundation (clihub + External MCP)

> Prepare the infrastructure for Cortex to interact with external services. Park this for when actual SaaS builds need Stripe/Supabase/etc.

### Dependencies: Successful SaaS build (Objective 10)

### What "done" looks like
- clihub evaluated and optionally installed as a tool
- External MCP server integrations (supabase, stripe, github, slack) configured in mcp_servers.json
- Context router properly routes to external service tools
- All tests pass

### Deliverables

**22.1 -- Evaluate and install clihub**
- Only if MCP tools need CLI wrappers for executor
- May not be needed if executor uses MCP tools directly

**22.2 -- Configure external MCP servers**
- Add supabase, stripe, github MCP servers to mcp_servers.json (disabled by default)
- Add appropriate category mappings to context_router.py
- Enable per-project as needed

**22.3 -- Tests**
- Test context routing for external service keywords
- All existing tests pass

---

## Execution Order & Dependencies

```
Objective 11: Skills Loader Infrastructure
    |
    +--- Objective 12: ECC Skills Integration
    +--- Objective 13: Anthropic Marketing + Sales Skills
    +--- Objective 14: Frontend Design + UI/UX Pro Max
    +--- Objective 15: PM + Feature Dev Skills
    +--- Objective 20: Remaining Anthropic Skills
    +--- Objective 21: ECC Agent Prompts + Investor Skills

Objective 16: idea-reality-mcp (independent)
Objective 17: Continuous Learning Enhancement (independent)
Objective 18: Confidence Scoring for Validator (independent)
Objective 19: OpenClaw Concept Integrations (independent)
Objective 22: Service Integration Foundation (after Obj 10)
```

### Recommended Execution Sequence

| Order | Objective | Rationale |
|-------|-----------|-----------|
| 1st | **Obj 11**: Skills Loader | Everything else depends on this. Small scope, high leverage. |
| 2nd | **Obj 14**: Frontend Design + UI/UX Pro Max | Directly improves build quality for Objective 10. |
| 3rd | **Obj 12**: ECC Skills (market-research, search-first, etc.) | Richest single source. Multiple categories at once. |
| 4th | **Obj 13**: Anthropic Marketing + Sales | Critical for landing pages and OLJ outreach. |
| 5th | **Obj 16**: idea-reality-mcp | Signal Agent shortcut. Independent, quick win. |
| 6th | **Obj 15**: PM + Feature Dev Skills | Useful for complex SaaS builds. |
| 7th | **Obj 18**: Confidence Scoring | Reduces validator noise. Small, focused. |
| 8th | **Obj 17**: Continuous Learning | Enhances self-improvement loop. |
| 9th | **Obj 19**: OpenClaw Concepts | Polish improvements. |
| 10th | **Obj 20**: Remaining Anthropic Skills | Fill in remaining gaps. |
| 11th | **Obj 21**: ECC Agent Prompts + Investor | Business expansion skills. |
| 12th | **Obj 22**: Service Integration | Only after SaaS revenue flowing. |

---

## Token Budget Considerations

Loading too many skills bloats the system prompt and wastes tokens. Guardrails:

- **Max skills per call:** 3-4 skill files (skills_loader enforces via `max_chars`)
- **Default budget:** 8,000 chars for skills (on top of existing system prompt)
- **Priority loading:** If multiple skills match, load by priority: workflow > coding > design > marketing > product
- **No skill loaded twice:** Dedup by file path
- **Monitoring:** Log which skills were loaded per call for debugging

---

## Success Criteria

After all objectives complete:
- Cortex has 25-30+ skill files organized by category
- Skills auto-load based on task context (no manual selection)
- Planner produces better plans informed by market research, design data, and PM frameworks
- Executor produces distinctive, non-generic sites with industry-appropriate design
- Pre-build validation prevents building saturated products
- Self-learning loop has confidence scoring and project scoping
- Validator has reduced false positives via confidence scoring
- Total token overhead per call stays under 10,000 chars for skills (controlled by budget)
- All 1812+ existing tests continue to pass at every objective boundary
