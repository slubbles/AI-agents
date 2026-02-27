# Agent Brain — Hands Subsystem: Complete Code Inventory

> **37 files** | ~10,000+ lines of Python | Generated from full source read

---

## Architecture Overview

The Hands subsystem is an autonomous code-execution engine built on a **Plan → Execute → Validate** loop with self-improvement via pattern learning and strategy evolution. It uses Anthropic Claude (Sonnet for planning/validation, Haiku for execution) with a tool-use architecture.

**Key execution patterns:**
- Budget-aware strategy assembly (planner gets 4K chars, executor gets 3K)
- Dependency-aware fail-fast with `DependencyResolver`
- Multi-tier retry: file_repair → surgical plan_repair → full replan
- Zero-cost static checks at 3 stages: preflight, mid-execution gates, pre-validation polish
- Sliding context window (600K char cap) with progressive plan trimming
- Per-tool timeout adaptation, health monitoring, and error classification
- Crash recovery via persistent checkpoints
- Cross-domain principle transfer and code exemplar injection

---

## 1. Core Pipeline (6 files)

### hands/planner.py (547 lines)
Planning agent — generates structured execution plans via Claude Sonnet.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_scan_workspace` | `(workspace_dir: str) -> dict` | Scans workspace; returns tree, key_files, stats |
| `_build_system_prompt` | `(tools_description, domain_knowledge, execution_strategy, workspace_context) -> str` | Builds planner system prompt with tool awareness and full context |
| `plan` | `(goal, tools_description, domain, domain_knowledge, execution_strategy, context, workspace_dir, available_tools, max_retries) -> dict \| None` | Generates execution plan for a goal; validates JSON, tool names, dependencies |
| `plan_repair` | `(original_plan, failing_steps, feedback, tools_description, completed_steps, domain, workspace_dir) -> dict \| None` | Generates surgical repair plan for partially-failed executions (re-does only failing + dependent steps) |
| `_validate_dependencies` | `(steps: list[dict]) -> None` | Sanitizes dependency graph — fixes circular deps, self-refs, forward refs via DFS cycle detection |

**Plan output structure:** `{task_summary, steps[], success_criteria, estimated_complexity, risks}`
**Step structure:** `{step_number, description, tool, params, depends_on, expected_output, criticality ("required"|"optional")}`

---

### hands/executor.py (832 lines)
Execution engine — runs plans step-by-step via Claude Haiku with native tool_use API.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_estimate_conversation_size` | `(conversation) -> int` | Estimates character count of conversation for window management |
| `_summarize_old_steps` | `(conversation, keep_recent=6) -> list[dict]` | Compresses old turns into summary for context window |
| `_build_state_accumulator` | `(step_results, artifacts) -> str` | Builds compact state summary from completed steps (replaces full history) |
| `_apply_sliding_window` | `(conversation, step_results, artifacts) -> list[dict]` | Proactive sliding window: [plan_msg, state_accumulator, last_N_messages] |
| `_trim_completed_steps_from_plan` | `(plan_msg, completed_steps) -> dict` | Progressive plan trimming: removes completed step details from plan message |
| `DependencyResolver` | class | Resolves step dependencies for fail-fast execution |
| `.can_execute` | `(self, step_num, step_results) -> tuple[bool, list[int]]` | Checks if dependencies satisfied; returns blockers list |
| `.all_remaining_blocked` | `(self, completed_step_count, step_results) -> bool` | True if all remaining required steps are blocked |
| `_build_system_prompt` | `(tools_description, execution_strategy) -> str` | Executor system prompt |
| `execute_plan` | `(plan, registry, domain, execution_strategy, workspace_dir, resume_from, enable_mid_gates) -> dict` | Main execution loop with all subsystems integrated |

**Key constants:** `MAX_CONVERSATION_CHARS=600K`, `STEP_RETRY_LIMIT=2`, `MAX_EXECUTION_COST=$0.50`, `SLIDING_WINDOW_KEEP_RECENT=4`

**Special behaviors:**
- Batch-skips all blocked steps in one message (not N round-trips)
- Always-on static file validation after every write
- Mid-execution quality gates at strategic breakpoints
- Step-directed prompting: tells LLM exactly what tool/params to use next
- Auto-injects `workspace_dir` as `cwd` for terminal commands
- Prevents premature `_complete` without any tool use

---

### hands/validator.py (799 lines)
Quality evaluator — scores execution output on 5 dimensions via Claude Sonnet.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_build_validator_prompt` | `(rubric) -> str` | Builds validator system prompt with scoring rubric |
| `_read_artifact_files` | `(artifacts, suspect_files) -> dict[str, str]` | Reads file contents; digest mode (first/last 20 lines) for clean files, full content for suspect files |
| `_check_js_ts_syntax` | `(content, path) -> list[str]` | Heuristic JS/TS checker: bracket balance, imports, templates, `node -c` fallback |
| `_run_static_checks` | `(artifacts) -> dict` | Pre-LLM static checks: file exists, not empty, JSON valid, Python syntax, YAML valid, JS/TS syntax, HTML structure, hardcoded secrets detection |
| `identify_failing_steps` | `(validation, step_results, plan_steps) -> list[int]` | Cross-references validation feedback with step results to find which steps to redo |
| `_should_fast_reject` | `(static_results, artifacts, completed_steps, total_steps) -> dict \| None` | Fast-reject path: skips LLM call (~$0.03 saved) when ≥50% of artifacts have blockers or critical config broken |
| `validate_execution` | `(goal, plan, execution_report, domain, domain_knowledge) -> dict` | Full validation: static checks → fast-reject check → LLM evaluation → score normalization |

**Scoring rubric:** correctness(30%), completeness(20%), code_quality(20%), security(15%), kb_alignment(15%)
**Threshold:** score ≥ 6 to accept

---

### hands/checkpoint.py (155 lines)
Crash recovery — persists execution progress for resume after failure.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `ExecutionCheckpoint` | class | Manages execution progress persistence |
| `.create` | `(self, domain, goal, plan)` | Creates new checkpoint |
| `.update_step` | `(self, domain, step_result)` | Records completed step |
| `.load` | `(self, domain) -> Optional[dict]` | Loads active checkpoint |
| `.clear` | `(self, domain) -> bool` | Removes checkpoint (execution complete) |
| `.mark_complete` | `(self, domain, success)` | Marks completed/failed |
| `.list_active` | `(self) -> list[dict]` | Lists all active checkpoints |
| `.get_resume_info` | `(self, domain) -> Optional[dict]` | Gets plan/steps/artifacts needed to resume |

---

### hands/constants.py (~50 lines)
Shared constants for workspace scanning and file handling.

| Symbol | Type | Description |
|--------|------|-------------|
| `SKIP_DIRS` | `set` | 20+ directories to skip when scanning (node_modules, .git, __pycache__, etc.) |
| `KEY_FILENAMES` | `set` | ~25 config/manifest filenames to read into planner context |
| `BINARY_EXTENSIONS` | `set` | Binary file extensions to skip |
| `PRIORITY_EXTENSIONS` | `set` | Source code extensions to prioritize |
| `MAX_TREE_CHARS` | `int` | 3000 — max chars for directory tree |
| `MAX_KEY_FILE_CHARS` | `int` | 4000 — max chars for key file contents |
| `MAX_WORKSPACE_FILES` | `int` | 2000 — max files to enumerate |

---

### hands/project_orchestrator.py (833 lines)
Multi-phase project execution — decomposes large projects into phases/tasks with human review gates.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `PhaseStatus` | `Enum` | PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED, REVIEW_NEEDED |
| `ProjectStatus` | `Enum` | PLANNING, IN_PROGRESS, PAUSED, COMPLETED, FAILED |
| `decompose_project` | `(description, workspace_dir, constraints, existing_files) -> dict` | Uses Claude to break project into phases/tasks |
| `save_project` | `(project)` | Persists project state to JSON |
| `load_project` | `(project_id) -> Optional[dict]` | Loads project by ID |
| `list_projects` | `() -> list[dict]` | Lists all projects with summary info |
| `create_project` | `(description, workspace_dir) -> dict` | Full project creation: decompose + initialize state |
| `execute_phase` | `(project, phase_index, workspace_dir, dry_run) -> dict` | Executes single phase: plan → execute → validate per task |
| `execute_project` | `(project, workspace_dir, auto_approve, max_phases) -> dict` | Executes all remaining phases with review gates |
| `retry_phase` | `(project, phase_index) -> dict` | Retries a failed phase (resets status) |
| `skip_phase` | `(project, phase_index) -> None` | Marks phase as skipped |
| `approve_phase` | `(project, phase_index) -> None` | Approves a REVIEW_NEEDED phase |
| `project_status` | `(project) -> dict` | Summary: completion %, current phase, task counts |
| `project_report` | `(project) -> str` | Human-readable report with phase icons and failure details |
| `cli_main` | `()` | CLI with subcommands: create, list, status, run, approve, retry, report |

**Limits:** `MAX_PHASES=12`, `MAX_TASKS_PER_PHASE=15`, `MAX_TOTAL_TASKS=100`
**Human review required for:** architecture, deployment, security phases

---

## 2. Self-Improvement (7 files)

### hands/pattern_learner.py (~460 lines)
Learns execution patterns from history — distills into reusable lessons.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `ExecutionLesson` | class | Single lesson: pattern, lesson text, category, evidence_count, success_impact, domain, examples |
| `.to_dict` | `() -> dict` | Serialize |
| `.from_dict` | `(cls, data) -> ExecutionLesson` | Deserialize |
| `PatternLearner` | class | Core learning engine |
| `.analyze_execution` | `(self, exec_output) -> list[str]` | Extracts patterns: consecutive failures, first-step failures, reliable tools, error patterns, plan explosion, validator feedback |
| `.analyze_plan_structure` | `(self, exec_output) -> list[str]` | Plan archetypes from successes: setup-first, config placement, optimal size, tool diversity |
| `.get_lessons` | `(self, domain, category, top_n) -> list[ExecutionLesson]` | Gets top lessons filtered by domain/category |
| `.format_lessons_for_prompt` | `(self, lessons, domain, max_chars) -> str` | Formats lessons for prompt injection |
| `.stats` | `(self) -> dict` | Learner statistics |

**Limits:** `MAX_LESSONS=50`, `MIN_EVIDENCE=2`

---

### hands/exec_meta.py (507 lines)
Meta-analyst — analyzes scored outputs and evolves execution strategies.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `load_exec_evolution_log` | `(domain) -> list[dict]` | Loads evolution history |
| `_save_exec_evolution_entry` | `(domain, entry)` | Appends to evolution log |
| `_build_exec_meta_prompt` | `() -> str` | General meta-analyst prompt |
| `_build_targeted_evolution_prompt` | `(weakest_dimension) -> str` | Focused prompt targeting single weakest scoring dimension |
| `_evaluate_last_evolution` | `(domain, outputs) -> dict \| None` | Checks if last strategy evolution helped (before/after comparison) |
| `_prepare_exec_analysis_data` | `(outputs, current_strategy) -> str` | Formats execution outputs + analytics for meta-analyst |
| `analyze_and_evolve_exec` | `(domain) -> dict \| None` | Main entry: targeted dimension evolution with last-evolution evaluation |
| `_identify_weakest_dimension` | `(outputs) -> str \| None` | Finds single weakest dimension (requires ≥0.5 gap from strongest) |

---

### hands/exec_cross_domain.py (~240 lines)
Cross-domain principle transfer — extracts reusable patterns from high-scoring executions.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `load_exec_principles` | `() -> list[dict]` | Load stored cross-domain execution principles |
| `extract_exec_principles` | `(domain, min_outputs=3) -> list[dict] \| None` | Extracts principles from high-scoring executions via LLM |
| `_principles_similar` | `(a, b) -> bool` | Dedup check: word overlap >60% |
| `get_principles_for_domain` | `(domain, max_principles=10) -> str` | Gets relevant principles scored by relevance, formatted for injection |
| `suggest_principles_in_strategy` | `(domain) -> str \| None` | Generates strategy seed for new domain using principles + template |

---

### hands/code_exemplars.py (~220 lines)
"Show, don't tell" — stores best-scoring code files per archetype for prompt injection.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `CodeExemplarStore` | class | Stores best-scoring code files per archetype/domain |
| `.extract_and_store` | `(self, domain, scored_artifacts, min_score=6.5) -> int` | Extracts high-scoring artifacts as exemplars |
| `.get_exemplars` | `(self, domain, archetypes, max_chars=4000) -> list[dict]` | Gets exemplars filtered by archetype |
| `.predict_archetypes` | `(self, plan) -> list[str]` | Predicts which archetypes a plan will produce |
| `.format_for_prompt` | `(self, exemplars, max_chars=4000) -> str` | Formats for prompt injection |
| `.stats` | `(self, domain) -> dict` | Store statistics |

**Limits:** `MAX_EXEMPLARS_PER_DOMAIN=20`, `MAX_EXEMPLAR_SIZE=3000`, `MIN_SCORE_TO_STORE=6.5`

---

### hands/artifact_tracker.py (~330 lines)
Per-file quality tracking — infers per-artifact scores from validation feedback.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `classify_archetype` | `(filepath: str) -> str` | Maps file path to archetype (e.g., "config/tsconfig", "test/python", "component/react") |
| `score_artifacts` | `(validation, step_results, artifacts) -> list[dict]` | Infers per-file quality from validation; returns [{filepath, archetype, inferred_score, issues, step_success}] |
| `ArtifactQualityDB` | class | Persists per-archetype quality stats over time |
| `.update` | `(self, domain, scored_artifacts)` | Updates quality records (rolling window of 30 scores per archetype) |
| `.get_weak_archetypes` | `(self, domain, threshold=6.5)` | Returns historically weak file types |
| `.get_strong_archetypes` | `(self, domain, threshold=7.5)` | Returns historically strong file types |
| `.get_domain_summary` | `(self, domain) -> dict` | Returns per-archetype avg scores, counts |
| `.format_for_prompt` | `(self, domain, max_chars=800) -> str` | Formats archetype warnings for prompt injection |

**Archetype maps:** _ARCHETYPE_MAP (exact filenames), _EXT_ARCHETYPE_MAP (test file patterns), _GENERAL_EXT_MAP (by extension)

---

### hands/feedback_cache.py (~170 lines)
Persistent per-dimension failure signals for fast feedback loop.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `FeedbackCache` | class | Tracks per-dimension weaknesses |
| `.record` | `(self, domain, validation, threshold=7.0) -> list[str]` | Records weak dimensions + reasons in rolling buffer |
| `.auto_clear` | `(self, domain, validation, clear_threshold=7.5) -> list[str]` | Auto-clears when dimension improves above threshold |
| `.get_for_planner` | `(self, domain, max_items=5) -> str` | Formats as planner-ready text |
| `.stats` | `(self, domain) -> dict` | Cache statistics |
| `.get_all_domains` | `(self) -> list[str]` | Lists all tracked domains |

**Constants:** `MAX_RECENT_ISSUES=5`, `WEAK_THRESHOLD=7.0`, `CLEAR_THRESHOLD=7.5`

---

### hands/strategy_assembler.py (~220 lines)
Budget-aware strategy assembly — combines multiple context sources with deduplication.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `StrategySection` | dataclass | label, content, priority |
| `AssemblyResult` | dataclass | text, included, dropped, budget, used, was_deduped |
| `_normalize_for_dedup` | `(text) -> str` | Normalize text for dedup comparison |
| `_extract_sentences` | `(text) -> list[str]` | Extract sentences for dedup |
| `_deduplicate_sections` | `(sections) -> list[StrategySection]` | Removes duplicate advice across sections using word overlap |
| `assemble` | `(budget, base_strategy, principles, lessons, quality_warnings, exemplars, feedback, deduplicate=True) -> AssemblyResult` | Budget-aware assembly with priority ordering |

**Priority order:** feedback(1) > lessons(2) > strategy(3) > quality_warnings(4) > exemplars(5) > principles(6)
**Budgets:** `PLANNER_BUDGET=4000`, `EXECUTOR_BUDGET=3000`

---

## 3. Quality & Retry Infrastructure (7 files)

### hands/error_analyzer.py (~180 lines)
Categorizes errors into 12 types with retryable flag and advice.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `analyze_error` | `(error_text, output_text="") -> dict` | Categorizes into 12 types: missing_dependency, missing_tool, missing_file, permission, syntax_error, type_error, network, resource, port_conflict, git_conflict, json_error, disk_full |
| `format_retry_guidance` | `(error_analysis, retries_left) -> str` | Formats error analysis into retry message for executor |

---

### hands/retry_advisor.py (~270 lines)
Routes to optimal retry strategy based on failure severity.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `FailureClass` | Enum | COSMETIC, STRUCTURAL, FUNDAMENTAL, MIXED |
| `RetryRecommendation` | class | strategy, failure_class, confidence, reason, skip_strategies |
| `classify_failure` | `(validation) -> str` | Classifies failure severity from scores and dimension breakdowns |
| `recommend_strategy` | `(validation, attempt, max_retries, has_weak_artifacts, has_failing_steps) -> RetryRecommendation` | Routes to: FILE_REPAIR, SURGICAL, FULL_REPLAN, or SKIP_RETRY |
| `should_skip_strategy` | `(recommendation, strategy) -> bool` | Whether a strategy should be skipped for this failure |

**Thresholds:** `COSMETIC_FLOOR=5.5`, `STRUCTURAL_FLOOR=3.0`

---

### hands/file_repair.py (~210 lines)
Targeted file repair — fixes 1-5 specific files in a single Haiku call (~$0.003).

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `identify_weak_artifacts` | `(validation, all_artifacts, threshold=6.0) -> list[dict]` | Identifies files needing repair from validation results |
| `repair_files` | `(files_to_fix, goal, plan, domain, workspace_dir) -> dict` | Reads current content, sends issues, gets corrected content, writes back |

---

### hands/mid_validator.py (~260 lines)
Zero-cost static quality checks at strategic breakpoints during execution.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `MidExecutionValidator` | class | Runs static checks at gate points |
| `.__init__` | `(self, plan, min_steps_for_midpoint=8)` | Identifies gate points: after setup, midpoint of large plans, fan-out steps, before last step |
| `.should_gate` | `(self, step_num, step_result) -> bool` | Whether to gate after this step |
| `.quick_validate` | `(self, artifacts) -> list[dict]` | Fast static checks (JSON, Python, JS/TS, YAML, HTML) on new artifacts |
| `.get_correction_prompt` | `(self, issues) -> str` | Generates correction message for executor |
| `.get_gate_summary` | `(self) -> dict` | Summary of gate results |

---

### hands/output_polisher.py (~200 lines)
Zero-cost rule-based fixes before validation.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `polish_artifacts` | `(artifacts, domain="general") -> dict` | Pre-validation fixes: JSON re-serialization, trailing newlines, null byte removal, trailing comma removal, package.json enrichment |
| `_fix_json` | `(filepath, content) -> tuple[str, list[str]]` | JSON-specific fixes |
| `_fix_python` | `(filepath, content) -> tuple[str, list[str]]` | Python-specific fixes (BOM removal) |
| `_fix_general` | `(filepath, content) -> tuple[str, list[str]]` | General fixes (trailing newline, null bytes, blank lines) |
| `format_polish_log` | `(polish_result) -> str` | Human-readable polish summary |

---

### hands/plan_preflight.py (~270 lines)
Zero-cost structural validation before execution begins.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `PreflightIssue` | dataclass | severity ("blocker"\|"warning"), category, message |
| `PreflightResult` | class | `.blockers`, `.warnings`, `.passed`, `.format()` properties |
| `preflight_check` | `(plan, domain, pattern_learner, artifact_quality_db, cost_ceiling=0.50) -> PreflightResult` | Full structural validation before execution |
| `_check_step_ordering` | `(steps, result)` | Forward deps, config before source, tool diversity |
| `_check_completeness` | `(steps, plan, result)` | Test/verify steps present, duplicate actions |
| `_check_cost_estimate` | `(steps, ceiling, result)` | Blocks if estimated cost exceeds ceiling |
| `_check_lesson_violations` | `(steps, domain, pattern_learner, result)` | Checks against learned lessons |
| `_check_weak_archetypes` | `(steps, domain, quality_db, result)` | Warns about historically weak file types |

---

### hands/exec_analytics.py (~210 lines)
Comprehensive execution analytics.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `analyze_executions` | `(domain) -> dict` | Full analysis: summary, tool_stats (per-tool success rates), error_patterns, score_trajectory (rolling avg, trend), efficiency (steps/task, failure rate), complexity_breakdown, dimension_averages |
| `format_analytics_report` | `(analytics) -> str` | Rich CLI report with ASCII bar charts and statistics |

---

## 4. Caching & Persistence (3 files)

### hands/exec_memory.py (~100 lines)
Scored execution output storage.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `save_exec_output` | `(domain, goal, plan, execution_report, validation, attempt, strategy_version) -> str` | Saves scored output to per-domain JSON files |
| `load_exec_outputs` | `(domain, min_score=0) -> list[dict]` | Loads all outputs for a domain |
| `get_exec_stats` | `(domain) -> dict` | Aggregate stats: count, avg_score, accepted, rejected, total_artifacts |
| `get_recent_exec_outputs` | `(domain, n=5) -> list[dict]` | N most recent outputs |

---

### hands/plan_cache.py (~200 lines)
LRU plan cache with similarity matching.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_normalize_goal` | `(goal) -> str` | Text normalization for matching |
| `_extract_keywords` | `(text) -> set[str]` | Keyword extraction for Jaccard similarity |
| `_jaccard_similarity` | `(set_a, set_b) -> float` | Set similarity metric |
| `_goal_hash` | `(goal) -> str` | SHA256 hash for exact match |
| `PlanCache` | class | LRU cache with similarity |
| `.get` | `(self, goal, domain) -> Optional[dict]` | Exact match then Jaccard similarity (threshold 0.6) |
| `.put` | `(self, goal, domain, plan, score)` | Stores plans with score ≥ 6.0 |
| `.stats` | `(self) -> dict` | Cache statistics |
| `.clear` | `(self, domain) -> int` | Clears cache for domain |

**Limits:** `MAX_CACHE_ENTRIES=50`, `CACHE_EXPIRY_DAYS=7`

---

### hands/exec_templates.py (~160 lines)
Domain-specific execution strategy templates.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `DEFAULT_TEMPLATE` | `str` | Default execution strategy text |
| `DOMAIN_TEMPLATES` | `dict` | Templates for: "nextjs-react", "python", "saas-building", "growth-hacking" |
| `get_template` | `(domain) -> str` | Returns best template (exact → partial → default) |
| `list_templates` | `() -> list[str]` | Lists available template names |

---

## 5. Adaptive Execution (3 files)

### hands/timeout_adapter.py (~130 lines)
Learns optimal per-tool timeouts from execution history.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `TimeoutAdapter` | class | Adaptive timeout manager |
| `.load_history` | `(self, exec_outputs)` | Loads timing data from past executions |
| `.record` | `(self, tool, duration_s)` | Records actual duration |
| `.suggest` | `(self, tool, params=None) -> int` | Timeout: slow patterns → historical avg×2.5 → tool default → global default |
| `.stats` | `(self) -> dict` | Timing statistics |

**16 slow command patterns** (e.g., `npm install=180s`, `docker build=300s`, `pip install=120s`)

---

### hands/tool_health.py (~130 lines)
Per-tool reliability tracking within a session.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `ToolHealthMonitor` | class | Session-level tool health tracker |
| `.record` | `(self, tool_name, success, error="")` | Records tool invocation result |
| `.is_degraded` | `(self, tool_name) -> bool` | ≥70% failure rate with 3+ attempts |
| `.get_alternatives` | `(self, tool_name) -> list[str]` | Suggests alternatives for degraded tools |
| `.get_health_report` | `(self) -> dict` | Full health report |
| `.get_degraded_tools` | `(self) -> list[str]` | Lists degraded tools |
| `.get_health_context` | `(self) -> str` | Prompt injection for degraded tools |

---

### hands/workspace_diff.py (~100 lines)
Lightweight workspace change detection.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `snapshot_workspace` | `(workspace_dir) -> dict[str, str]` | Fingerprint snapshot using mtime+size |
| `compute_diff` | `(before, after) -> dict` | Returns created, modified, deleted, unchanged lists |
| `format_diff_summary` | `(diff) -> str` | Human-readable diff summary |

---

## 6. Task Generation (1 file)

### hands/task_generator.py (~340 lines)
Self-directed task generation — generates coding tasks from KB + execution history.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_get_past_goals` | `(domain) -> list[str]` | Gets previously attempted goals for dedup |
| `_get_complexity_stats` | `(domain) -> dict[str, dict]` | Success rates by complexity level |
| `_get_max_allowed_complexity` | `(domain) -> str` | Caps complexity where historical success <40% with 3+ attempts |
| `generate_tasks` | `(domain, hint="") -> list[dict]` | Generates 3 ranked coding task candidates using KB + exec history |
| `get_next_task` | `(domain, hint="") -> str \| None` | Returns single best task description |

---

## 7. Tool System (7 files)

### hands/tools/registry.py (~330 lines)
Central tool registry with metrics middleware.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `ToolResult` | class | Standardized: success, output, error, artifacts, metadata, timestamp |
| `BaseTool` | ABC class | Abstract base: name, description, input_schema, execute(), validate_params(), safe_execute(), to_claude_tool() |
| `ToolMetrics` | class | Per-tool: invocation count, success rate, avg duration, errors |
| `ToolRegistry` | class | Central registry |
| `.register` | `(self, tool: BaseTool)` | Registers a tool |
| `.get` | `(self, name) -> Optional[BaseTool]` | Gets tool by name |
| `.get_required` | `(self, name) -> BaseTool` | Gets tool or raises |
| `.list_tools` | `(self) -> list[str]` | Lists registered tool names |
| `.get_claude_tools` | `(self) -> list[dict]` | Claude API tool definitions |
| `.get_execution_tools` | `(self) -> list[dict]` | Tool definitions + `_complete`/`_abort` synthetic control tools |
| `.get_tool_descriptions` | `(self) -> str` | Human-readable tool descriptions |
| `.execute` | `(self, name, **params) -> ToolResult` | Executes with metrics middleware |
| `create_default_registry` | `() -> ToolRegistry` | Creates registry with all 5 tools (code, terminal, git, http, search) |

---

### hands/tools/code.py (~350 lines)
File I/O tool with safety guards and backup/rollback.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_is_safe_path` | `(path) -> str \| None` | Safety: blocks system dirs, enforces EXEC_ALLOWED_DIRS whitelist |
| `_backup_file` | `(filepath) -> str \| None` | Timestamped backup before destructive ops; max 200 backups |
| `rollback_session` | `() -> list[dict]` | Restores all backed-up files to originals |
| `get_session_backups` | `() -> list[dict]` | Lists current session backups |
| `clear_session_backups` | `()` | Clears backup list |
| `CodeTool` | class (BaseTool) | name="code" |

**Actions:** write (with backup), read, edit (replace unique string, with backup), insert_at_line, append, delete (with backup), list_dir
**Input schema:** action, path, content, old_string, line_number
**Safety:** blocks `_SYSTEM_DIRS`, respects `EXEC_MAX_FILE_SIZE`, `EXEC_ALLOWED_DIRS`

---

### hands/tools/git.py (~180 lines)
Git version control with safety guards.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_check_git_safety` | `(subcommand) -> str \| None` | Blocks dangerous ops |
| `GitTool` | class (BaseTool) | name="git" |

**Actions:** init, status, add, commit, log, branch, checkout, diff, clone
**Safety:** blocks push --force, rebase, reset --hard, clean -fd; uses list args (no shell injection), `GIT_TERMINAL_PROMPT=0`, custom author name

---

### hands/tools/http.py (~230 lines)
HTTP requests with SSRF protection.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_check_url_safety` | `(url) -> str \| None` | Blocks internal/private IPs, non-http(s) schemes |
| `_SafeRedirectHandler` | class | Validates redirect targets against SSRF |
| `HttpTool` | class (BaseTool) | name="http" |

**Actions:** get, post, put, patch, delete, head
**Limits:** max response 50KB, 30s timeout, SSRF protection on redirects

---

### hands/tools/search.py (~300 lines)
Code/text search using subprocess.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `SearchTool` | class (BaseTool) | name="search" |

**Actions:** grep (subprocess `grep -rn`), find (subprocess `find`), count_lines (`find | wc -l`), tree (ASCII directory tree)
**Limits:** uses SKIP_DIRS, caps output at 200 lines/entries

---

### hands/tools/terminal.py (~230 lines)
Shell execution with sanitized environment.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_build_safe_env` | `() -> dict[str, str]` | Strips API keys/tokens/secrets from environment |
| `_check_command_safety` | `(command) -> str \| None` | Checks blocked patterns, secret probes, sandbox whitelist |
| `_validate_cwd` | `(cwd) -> str \| None` | Validates working directory against EXEC_ALLOWED_DIRS |
| `TerminalTool` | class (BaseTool) | name="terminal" |

**Input:** command, cwd, timeout
**Safety:** shell=True with sanitized env, EXEC_ALLOWED_COMMANDS whitelist in sandbox mode, blocks `$ANTHROPIC_API_KEY` references

---

## 8. External Tools (4 files)

### tools/web_search.py (~60 lines)
DuckDuckGo search for the Brain subsystem.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `web_search` | `(query, max_results=5, max_retries=3) -> list[dict]` | DuckDuckGo search with retry+backoff on rate limits |
| `SEARCH_TOOL_DEFINITION` | `dict` | Claude tool_use definition for web_search |

---

### tools/web_fetcher.py (435 lines)
Web page fetching via Scrapling with structured extraction.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `fetch_page` | `(url, timeout=12) -> Optional[dict]` | Fetches single page, extracts title, content, headings, code_blocks |
| `fetch_pages` | `(urls, max_pages=3) -> list[dict]` | Batch fetch with dedup and filtering |
| `search_and_fetch` | `(query, max_results=5, max_fetch=3) -> dict` | Combined DuckDuckGo search + Scrapling fetch pipeline |
| `crawl_docs_site` | `(start_url, max_pages=20, url_pattern, output_dir) -> list[dict]` | Crawls documentation site following internal links |
| `_get_selectors` | `(url) -> dict` | CSS selectors per known site (nextjs.org, react.dev, MDN, vercel.com) |
| `_should_skip` | `(url) -> bool` | Skip social media, search engines, paywalled sites |
| `_extract_content` | `(page, url) -> dict` | Structured content extraction |
| `_clean_text` | `(text) -> str` | Text normalization |
| `FETCH_PAGE_TOOL_DEFINITION` | `dict` | Claude tool_use definition |
| `SEARCH_AND_FETCH_TOOL_DEFINITION` | `dict` | Claude tool_use definition |

**Constants:** `SKIP_DOMAINS` set, `MAX_CONTENT_LENGTH=8000`, `FETCH_TIMEOUT=12`

---

### tools/crawl_to_kb.py (~160 lines)
Converts crawl data into knowledge base claims.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `_extract_claims_from_page` | `(page) -> list[dict]` | Heuristic claim extraction (no LLM): scores sentences by technical indicators, comparisons, definitions, code refs |
| `crawl_to_claims` | `(domain, max_claims_per_page=10) -> list[dict]` | Converts all crawl data for domain into deduplicated claims |
| `inject_crawl_claims_into_kb` | `(domain, max_claims=100) -> dict` | Injects claims into KB as synthetic scored entries (score=7) |

---

### tools/dataset_loader.py (~340 lines)
External data loading from HuggingFace, GitHub, and crawl data.

| Symbol | Signature | Description |
|--------|-----------|-------------|
| `fetch_hf_dataset_samples` | `(dataset_id, split, max_samples, text_field) -> list[dict]` | Fetches from HuggingFace datasets API with caching |
| `fetch_github_file` | `(repo, path, branch="main") -> Optional[dict]` | Fetches raw file from GitHub (week-long cache) |
| `load_crawl_data` | `(domain) -> list[dict]` | Loads local crawl data |
| `get_domain_examples` | `(domain, max_examples=20) -> list[dict]` | Combined: HF datasets + GitHub files + crawl data |
| `inject_examples_into_strategy` | `(domain, strategy, max_examples, max_chars_per_example) -> str` | Appends code examples to strategy text |
| `DOMAIN_DATASETS` | `dict` | Curated HuggingFace datasets per domain |
| `DOMAIN_GITHUB_REPOS` | `dict` | Curated GitHub example files per domain |

---

## Summary Statistics

| Category | Files | Total Lines (approx) |
|----------|-------|---------------------|
| Core Pipeline | 6 | ~3,200 |
| Self-Improvement | 7 | ~2,150 |
| Quality & Retry | 7 | ~1,600 |
| Caching & Persistence | 3 | ~460 |
| Adaptive Execution | 3 | ~360 |
| Task Generation | 1 | ~340 |
| Tool System (Hands) | 6 | ~1,620 |
| External Tools | 4 | ~995 |
| **Total** | **37** | **~10,725** |
