# Deep Scan Report — Agent Brain Packages

**Scanned**: `hands/`, `browser/`, `deploy/`, `mcp/`, `rag/`, `dashboard/`, `cli/`  
**Total**: 60 Python files, 17,342 lines  
**Generated**: 2025-02-24

---

## 1. `hands/` — Agent Hands Execution Engine (33 files, 8,095 lines)

The code-execution layer. Decomposes coding tasks into tool-using plans, executes them step-by-step, validates output, and learns from the results.

### `hands/__init__.py` (0 lines)
Empty init.

---

### `hands/executor.py` (831 lines)

**Purpose**: Step-by-step plan execution via Claude Haiku with tool dispatch.

| Name | Lines | Purpose |
|------|-------|---------|
| `_estimate_conversation_size()` | 52–64 | Estimate char count of all conversation messages |
| `_summarize_old_steps()` | 67–113 | Compress old conversation turns (legacy path) |
| `_build_state_accumulator()` | 122–156 | Build compact state summary from completed steps |
| `_apply_sliding_window()` | 159–188 | Proactive sliding context window — replaces full history with plan+state+recent |
| `_trim_completed_steps_from_plan()` | 191–228 | Remove completed step details to save tokens |
| `DependencyResolver` (class) | 196–250 | Resolves step dependency graph, marks downstream steps as skipped on failure |
| `_build_system_prompt()` | 262–292 | Build executor system prompt |
| `execute_plan()` | 295–831 | **MAIN**: iterates plan steps, dispatches to ToolRegistry, handles retry (2 per step), mid-execution validation gates, dependency resolution, cost ceiling ($0.50), sliding window |

**Imports**: json, os, sys, traceback, datetime, Anthropic, config (ANTHROPIC_API_KEY, MODELS, EXEC_MAX_STEPS, EXEC_STEP_TIMEOUT), cost_tracker, utils.retry, utils.json_parser, hands.tools.registry (ToolRegistry, ToolResult), hands.error_analyzer, hands.tool_health, hands.timeout_adapter, hands.mid_validator

**Constants**: `MAX_CONVERSATION_TOKENS_ESTIMATE` = 150,000 · `STEP_RETRY_LIMIT` = 2 · `MAX_EXECUTION_COST` = $0.50 · `SLIDING_WINDOW_KEEP_RECENT` = 4

**Issues**: Uses `sys.path.insert(0, ...)` for imports. Hardcoded Haiku pricing in cost calculation (`0.25/1.25 per M tokens`).

---

### `hands/project_orchestrator.py` (832 lines)

**Purpose**: Multi-phase project lifecycle (decompose → plan → execute → checkpoint → review).

| Name | Lines | Purpose |
|------|-------|---------|
| `PhaseStatus` (Enum) | — | pending/in_progress/completed/failed/review_needed/skipped |
| `ProjectStatus` (Enum) | — | pending/in_progress/completed/failed/paused |
| `decompose_project()` | 137–175 | Breaks project description into phases/tasks via Claude Sonnet |
| `save_project()` / `load_project()` / `list_projects()` | 185–222 | JSON persistence in `projects/` dir |
| `create_project()` | 228–290 | Create new project from description |
| `execute_phase()` | 293–404 | Execute single phase (plan each task, execute, validate) |
| `execute_project()` | 407–452 | Execute all remaining phases with review gates |
| `retry_phase()` / `skip_phase()` / `approve_phase()` | 458–492 | Phase lifecycle operations |
| `project_status()` / `project_report()` | 498–580 | Status reporting |
| `cli_main()` | 586–832 | CLI interface (argparse) |

**Constants**: `MAX_PHASES` = 12 · `MAX_TASKS_PER_PHASE` = 15 · `MAX_TOTAL_TASKS` = 100 · `HUMAN_REVIEW_PHASES` = {"architecture","deployment","security"}

**Issues**: `log_cost(response, ...)` in `decompose_project` passes the full response object rather than model string + token counts (inconsistent with other callsites). Lazy imports may mask import errors.

---

### `hands/validator.py` (798 lines)

**Purpose**: Scores execution quality across 5 dimensions (correctness 30%, completeness 20%, code quality 20%, security 15%, KB alignment 15%).

| Name | Lines | Purpose |
|------|-------|---------|
| `_build_validator_prompt()` | 43–92 | System prompt with rubric |
| `_read_artifact_files()` | 119–180 | Read file contents — digest mode for clean files, full for suspect |
| `_check_js_ts_syntax()` | 185–270 | Heuristic JS/TS syntax checks (bracket balance, import syntax, node -c) |
| `_run_static_checks()` | 273–392 | exists, not_empty, json_valid, python_syntax, yaml_valid, js_ts_syntax, html_structure, no_hardcoded_secrets |
| `identify_failing_steps()` | 395–455 | Cross-reference validation feedback with step results for surgical retry |
| `_should_fast_reject()` | 462–525 | Skip LLM if >50% artifacts have blocker issues (saves ~$0.03) |
| `validate_execution()` | 528–798 | **MAIN**: static checks → fast-reject → LLM validation |

**Constants**: `_MAX_ARTIFACT_CHARS` = 40,000 · `_MAX_FILE_CHARS` defined twice (8,000 at L117, **then overwritten to 500,000 at L183**) · `_BLOCKER_CHECKS` · `DEFAULT_EXEC_RUBRIC` weights

⚠ **Bug**: `_MAX_FILE_CHARS` is defined at 8,000 then overwritten to 500,000. The 500K value was likely intended only for the syntax check section but overwrites the module-level constant.

---

### `hands/planner.py` (546 lines)

**Purpose**: Decomposes tasks into concrete tool-using steps via Claude Sonnet.

| Name | Lines | Purpose |
|------|-------|---------|
| `_scan_workspace()` | 47–103 | Scan workspace directory for context (tree + key file contents) |
| `_build_system_prompt()` | 106–182 | Builds planner prompt with tools, KB, strategy, workspace context |
| `plan()` | 185–370 | **MAIN**: generates execution plan with retry on parse failure, tool name validation/remapping |
| `plan_repair()` | 373–494 | Surgical repair plan for partially failed executions |
| `_validate_dependencies()` | 497–546 | Validate/sanitize dependency graph (remove cycles, forward refs) |

**Imports**: constants from hands.constants

**Issues**: Tool name validation has hardcoded fallback to "terminal" for unknown tools (silent coercion).

---

### `hands/exec_meta.py` (506 lines)

**Purpose**: Execution Meta-Analyst — evolves HOW the system writes code.

| Name | Lines | Purpose |
|------|-------|---------|
| `load_exec_evolution_log()` / `_save_exec_evolution_entry()` | 39–60 | Evolution log persistence |
| `_build_exec_meta_prompt()` / `_build_targeted_evolution_prompt()` | 63–130 | General vs. targeted dimension prompts |
| `_evaluate_last_evolution()` | 133–194 | Before/after score comparison for last strategy change |
| `_prepare_exec_analysis_data()` | 197–283 | Format outputs + analytics for meta-analyst |
| `analyze_and_evolve_exec()` | 286–438 | **MAIN**: targeted dimension evolution — finds weakest dimension, generates surgical strategy patch |
| `_identify_weakest_dimension()` | 441–506 | Finds single weakest dimension (needs >0.5 gap from best) |

**Constants**: `MIN_EXEC_OUTPUTS_FOR_ANALYSIS` = 3 · `MAX_EXEC_OUTPUTS_TO_ANALYZE` = 10

---

### `hands/pattern_learner.py` (497 lines)

**Purpose**: Extracts reusable patterns ("lessons") from execution history.

| Name | Lines | Purpose |
|------|-------|---------|
| `ExecutionLesson` (class) | 39–80 | Dataclass: pattern, lesson, category, evidence_count, success_impact |
| `PatternLearner` (class) | 83–497 | Analyzes executions, extracts 6 pattern types |
| `.analyze_execution()` | 157–310 | Extracts patterns: consecutive failures, first-step failures, reliable tools, error patterns, plan explosion, validator feedback |
| `.analyze_plan_structure()` | 312–426 | Plan-level patterns from successful executions |
| `.get_lessons()` / `.format_lessons_for_prompt()` | 428–480 | Retrieve and format |

**Constants**: `MAX_LESSONS` = 50 · `MIN_EVIDENCE` = 2

---

### `hands/artifact_tracker.py` (365 lines)

**Purpose**: Per-file quality scoring by archetype (e.g., config/tsconfig, test/jest, component/react).

| Name | Lines | Purpose |
|------|-------|---------|
| `classify_archetype()` | 82–118 | Map filepath to archetype string |
| `score_artifacts()` | 125–190 | Cross-reference validator feedback with artifacts |
| `ArtifactQualityDB` (class) | 196–365 | Persists per-archetype quality stats, rolling window of 30, weak/strong detection |

---

### `hands/checkpoint.py` (172 lines)

**Purpose**: Save and resume execution progress for crash recovery.

| Name | Lines | Purpose |
|------|-------|---------|
| `ExecutionCheckpoint` (class) | all | create/update/load/clear/mark_complete checkpoints per domain (JSON) |

---

### `hands/code_exemplars.py` (247 lines)

**Purpose**: "Show, don't tell" — stores best-scoring code files as exemplars for future prompts.

| Name | Lines | Purpose |
|------|-------|---------|
| `CodeExemplarStore` (class) | all | extract_and_store, get_exemplars, predict_archetypes, format_for_prompt |

**Constants**: `MAX_EXEMPLARS_PER_DOMAIN` = 20 · `MAX_EXEMPLAR_SIZE` = 3,000 · `MIN_SCORE_TO_STORE` = 6.5

---

### `hands/constants.py` (53 lines)

**Purpose**: Shared constants for workspace scanning.

**Constants**: `SKIP_DIRS` (22 entries) · `KEY_FILENAMES` (22 entries) · `BINARY_EXTENSIONS` · `PRIORITY_EXTENSIONS` · `MAX_TREE_CHARS` = 3,000 · `MAX_KEY_FILE_CHARS` = 4,000 · `MAX_WORKSPACE_FILES` = 2,000

---

### `hands/error_analyzer.py` (192 lines)

**Purpose**: Categorizes execution errors into 12 types for smarter retry.

| Name | Lines | Purpose |
|------|-------|---------|
| `analyze_error()` | 151–175 | Match error text against 12 patterns |
| `format_retry_guidance()` | 178–192 | Human-readable guidance for the executor |

**Patterns**: missing_dependency, missing_tool, missing_file, permission, syntax_error, type_error, network, resource, port_conflict, git_conflict, json_error, disk_full

---

### `hands/exec_analytics.py` (266 lines)

**Purpose**: Deep execution performance insights (tool usage, error trends, score trajectory, efficiency).

| Name | Lines | Purpose |
|------|-------|---------|
| `analyze_executions()` | 22–185 | Comprehensive analysis dict |
| `format_analytics_report()` | 188–266 | Rich CLI output |

---

### `hands/exec_cross_domain.py` (254 lines)

**Purpose**: Transfers execution patterns across domains as "principles".

| Name | Lines | Purpose |
|------|-------|---------|
| `extract_exec_principles()` | 72–168 | Extract from high-scoring executions via Claude |
| `get_principles_for_domain()` | 183–224 | Returns relevant principles for a domain |

**Constants**: `MIN_SCORE_FOR_PRINCIPLES` = 7.0 · `MAX_PRINCIPLES` = 50

---

### `hands/exec_memory.py` (142 lines)

**Purpose**: Scored execution output storage per domain (JSON files).

| Name | Lines | Purpose |
|------|-------|---------|
| `save_exec_output()` | 17–85 | Saves with atomic_json_write |
| `load_exec_outputs()` | 88–113 | Load from domain directory |
| `get_exec_stats()` | 116–138 | Summary stats |
| `get_recent_exec_outputs()` | 141–143 | Convenience wrapper |

---

### `hands/exec_templates.py` (163 lines)

**Purpose**: Default strategy templates for common domains.

Templates: default, nextjs-react, python, saas-building, growth-hacking.

| Name | Lines | Purpose |
|------|-------|---------|
| `get_template()` | 140–155 | Exact + partial match |
| `list_templates()` | 157–163 | List available templates |

---

### `hands/feedback_cache.py` (206 lines)

**Purpose**: Persistent per-dimension failure signals for fast planner feedback loop.

| Name | Lines | Purpose |
|------|-------|---------|
| `FeedbackCache` (class) | all | record weak dimensions, auto_clear when improved, get_for_planner output |

**Constants**: `MAX_RECENT_ISSUES` = 5 · `WEAK_THRESHOLD` = 7.0 · `CLEAR_THRESHOLD` = 7.5

---

### `hands/file_repair.py` (246 lines)

**Purpose**: Fix specific files via single Haiku call (~$0.003) instead of full retry ($0.15–$0.40).

| Name | Lines | Purpose |
|------|-------|---------|
| `identify_weak_artifacts()` | 37–84 | Find which artifacts are weak |
| `repair_files()` | 87–246 | Reads current content, sends issues to Haiku, applies fixes |

---

### `hands/mid_validator.py` (264 lines)

**Purpose**: Zero-cost static validation checkpoints during execution.

| Name | Lines | Purpose |
|------|-------|---------|
| `MidExecutionValidator` (class) | all | Identifies gate points (after setup, midpoint, fan-out, pre-last), runs quick_validate (JSON/Python/JS/TS/YAML/HTML checks), generates correction prompts |

---

### `hands/output_polisher.py` (223 lines)

**Purpose**: Zero-cost rule-based quality fixes before validation.

| Name | Lines | Purpose |
|------|-------|---------|
| `polish_artifacts()` | 42–108 | Orchestrates all fixes |
| `_fix_json()` / `_fix_python()` / `_fix_general()` | various | JSON reformatting, trailing newlines, etc. |

---

### `hands/plan_cache.py` (226 lines)

**Purpose**: LRU cache for successful plans with Jaccard similarity matching.

| Name | Lines | Purpose |
|------|-------|---------|
| `PlanCache` (class) | all | get (exact + similarity match), put (score≥6 only), LRU eviction |

**Constants**: `MAX_CACHE_ENTRIES` = 50 · `CACHE_EXPIRY_DAYS` = 7 · `MIN_SIMILARITY_THRESHOLD` = 0.6

---

### `hands/plan_preflight.py` (284 lines)

**Purpose**: Zero-cost structural pre-checks before execution.

| Name | Lines | Purpose |
|------|-------|---------|
| `PreflightIssue` / `PreflightResult` (classes) | — | Typed result containers |
| `preflight_check()` | main | Checks step ordering, completeness, cost estimates, lesson violations, weak archetypes |

---

### `hands/retry_advisor.py` (266 lines)

**Purpose**: Classifies failure severity and routes to optimal retry strategy.

| Name | Lines | Purpose |
|------|-------|---------|
| `FailureClass` (Enum) | — | COSMETIC / STRUCTURAL / FUNDAMENTAL / MIXED |
| `RetryRecommendation` (Enum) | — | FILE_REPAIR / SURGICAL / FULL_REPLAN / SKIP_RETRY |
| `classify_failure()` | — | Classify by score + error signals |
| `recommend_strategy()` | — | Route to cheapest effective retry path |

**Constants**: `COSMETIC_FLOOR` = 5.5 · `STRUCTURAL_FLOOR` = 3.0

---

### `hands/strategy_assembler.py` (226 lines)

**Purpose**: Budget-aware, deduplicated strategy context assembly from 6 sources.

| Name | Lines | Purpose |
|------|-------|---------|
| `assemble()` | main | Prioritizes: feedback > lessons > strategy > quality > exemplars > principles |

**Constants**: `PLANNER_BUDGET` = 4,000 · `EXECUTOR_BUDGET` = 3,000

---

### `hands/task_generator.py` (332 lines)

**Purpose**: Converts Brain knowledge into coding tasks using complexity adaptation.

| Name | Lines | Purpose |
|------|-------|---------|
| `_get_max_allowed_complexity()` | — | Caps complexity based on historical success rates |
| `generate_tasks()` | — | Generates 3 ranked candidates via Claude |
| `get_next_task()` | — | Convenience wrapper |

**Constants**: `MIN_ACCEPT_RATE_FOR_COMPLEXITY` = 0.40 · `MIN_ATTEMPTS_FOR_GATING` = 3

---

### `hands/timeout_adapter.py` (147 lines)

**Purpose**: Adaptive per-tool timeouts based on historical execution durations.

| Name | Lines | Purpose |
|------|-------|---------|
| `TimeoutAdapter` (class) | all | load_history, record, suggest (priority: slow patterns > historical > defaults > global) |

**Constants**: `_DEFAULT_TIMEOUTS` per tool · `_SLOW_COMMAND_PATTERNS` (16 patterns) · `MIN_TIMEOUT` = 10 · `MAX_TIMEOUT` = 600 · `MULTIPLIER` = 2.5

---

### `hands/tool_health.py` (149 lines)

**Purpose**: Tracks tool reliability during execution, suggests alternatives when degraded.

| Name | Lines | Purpose |
|------|-------|---------|
| `ToolHealthMonitor` (class) | all | record, is_degraded, get_alternatives, get_health_context |

**Constants**: `DEGRADATION_THRESHOLD` = 0.7 · `MIN_ATTEMPTS_FOR_DEGRADATION` = 3

---

### `hands/workspace_diff.py` (122 lines)

**Purpose**: Tracks file changes during execution (before/after snapshots).

| Name | Lines | Purpose |
|------|-------|---------|
| `snapshot_workspace()` | — | Lightweight mtime+size fingerprints |
| `compute_diff()` | — | Created/modified/deleted lists |
| `format_diff_summary()` | — | Human-readable diff output |

---

### `hands/tools/registry.py` (343 lines)

**Purpose**: Pluggable tool selection, routing, and execution metrics middleware.

| Name | Lines | Purpose |
|------|-------|---------|
| `ToolResult` (class) | 28–60 | Standardized result from any tool |
| `BaseTool` (ABC) | 63–127 | Abstract base — name, description, input_schema, execute(), safe_execute(), to_claude_tool() |
| `ToolMetrics` (class) | 130–195 | Per-tool invocation count, success rate, avg duration, last N errors |
| `ToolRegistry` (class) | 198–310 | Central registry: register, get, execute (with metrics), get_claude_tools(), get_execution_tools() (adds `_complete`/`_abort` synthetic tools) |
| `create_default_registry()` | 313–343 | Factory — registers CodeTool, TerminalTool, GitTool, HttpTool, SearchTool |

---

### `hands/tools/search.py` (352 lines)

**Purpose**: Code and text search tool (grep, find, count_lines, tree).

| Name | Lines | Purpose |
|------|-------|---------|
| `SearchTool(BaseTool)` | all | 4 actions: grep (regex/literal), find (glob), count_lines (wc -l), tree (ASCII tree) |

Uses `SKIP_DIRS` from constants. Max tree depth 4, max tree lines 200.

---

### `hands/tools/terminal.py` (258 lines)

**Purpose**: Shell command execution with safety sandboxing.

| Name | Lines | Purpose |
|------|-------|---------|
| `_build_safe_env()` | 73–93 | Sanitize env vars — strip API keys, only pass safe vars |
| `_check_command_safety()` | 96–146 | Blocked patterns + sandbox whitelist check |
| `_validate_cwd()` | 149–160 | Working directory within allowed dirs |
| `TerminalTool(BaseTool)` | 163–258 | Runs commands via `subprocess.run(shell=True)` with sanitized env and timeout |

**Constants**: `_SAFE_ENV_VARS` (~40 names) · `_SECRET_NAME_PATTERNS` (9 patterns)

**Issues**: Uses `shell=True` (necessary for piped commands but increases surface area). Stdout capped at 10,000 chars, stderr at 5,000.

---

### `hands/tools/code.py` (394 lines)

**Purpose**: File I/O tool (write, read, edit, insert_at_line, append, delete, list_dir).

| Name | Lines | Purpose |
|------|-------|---------|
| `CodeTool(BaseTool)` | all | All file operations with safety (`_is_safe_path`), automatic backups, `rollback_session()`, `get_session_backups()` |

**Constants**: `_SYSTEM_DIRS` · `_BACKUP_DIR_NAME` = ".agent-backups" · `_MAX_BACKUPS` = 200

---

### `hands/tools/git.py` (206 lines)

**Purpose**: Git VCS operations (init, status, add, commit, log, branch, checkout, diff, clone).

| Name | Lines | Purpose |
|------|-------|---------|
| `GitTool(BaseTool)` | all | Uses subprocess with `shell=False`. Blocks: force push, rebase, reset --hard, clean -fd |

---

### `hands/tools/http.py` (229 lines)

**Purpose**: HTTP requests for testing APIs and fetching docs.

| Name | Lines | Purpose |
|------|-------|---------|
| `HttpTool(BaseTool)` | all | GET/POST/PUT/PATCH/DELETE/HEAD with SSRF protection |
| `_SafeRedirectHandler` | — | Validates redirect targets against blocked hosts |

**Constants**: `_BLOCKED_HOSTS` regex (private IP ranges) · `_MAX_RESPONSE_SIZE` = 50,000

---

## 2. `browser/` — Stealth Browser Engine (5 files, 1,241 lines)

Playwright-based browser with anti-detection for sites requiring JS/login.

### `browser/__init__.py` (21 lines)
Docstring describing module capabilities (stealth patches, persistent contexts, proxy, vault integration).

---

### `browser/stealth_browser.py` (373 lines)

**Purpose**: Core browser engine — launch, configure stealth, manage contexts.

| Name | Lines | Purpose |
|------|-------|---------|
| `StealthBrowser` (class) | 87–373 | Async context manager for Playwright + stealth |
| `.launch()` | 117–166 | Launch Chromium with anti-detection flags, persistent context, resource blocking |
| `.close()` | 168–178 | Save state and close |
| `.save_session()` | 180–185 | Save cookies/localStorage to JSON |
| `.new_page()` | 189–194 | Create stealth page (applies `playwright_stealth`) |
| `.navigate()` | 196–212 | Navigate with human-like wait |
| `.human_type()` / `.human_click()` / `.human_scroll()` / `.random_mouse_movement()` | 216–254 | Human-mimicking interaction methods |
| `.extract_text()` / `.extract_html()` / `.extract_links()` / `.extract_structured()` | 258–316 | Content extraction methods |
| `.screenshot()` | 318–322 | Debug screenshots |
| `.wait_for_selector()` / `.wait_for_navigation()` | 326–341 | Wait utilities |
| `.get_cookies()` / `.add_cookies()` / `.clear_cookies()` | 345–361 | Cookie management |
| `.check_detection()` | 363–373 | Run bot-detection test vectors |

**Constants**: `TYPING_DELAY_*`, `CLICK_DELAY_*`, `SCROLL_DELAY_*`, `PAGE_LOAD_WAIT_*` · 6 viewport presets · 5 user agents · 4 locale/timezone pairs

**Imports**: playwright.async_api, playwright_stealth

---

### `browser/auth.py` (313 lines)

**Purpose**: Site-specific login flows. Credentials from vault.

| Name | Lines | Purpose |
|------|-------|---------|
| `SiteAuthenticator` (class) | 57–155 | Generic email/password login — finds inputs by attribute scanning |
| `LinkedInAuth(SiteAuthenticator)` | 158–219 | LinkedIn-specific selectors + challenge detection |
| `IndeedAuth(SiteAuthenticator)` | 222–252 | Indeed multi-step login |
| `GitHubAuth(SiteAuthenticator)` | 255–297 | GitHub login with optional TOTP 2FA (pyotp) |
| `get_authenticator()` | 308–313 | Factory — returns site-specific or generic authenticator |

**Constants**: `LOGIN_SUCCESS_INDICATORS` dict per domain · `AUTHENTICATORS` registry

---

### `browser/session_manager.py` (352 lines)

**Purpose**: Orchestrates stealth browser + auth + vault. High-level interface.

| Name | Lines | Purpose |
|------|-------|---------|
| `BrowserSession` (class) | 50–305 | Main session: fetch, fetch_multiple, search_and_fetch, auto-auth |
| `.fetch()` | 67–131 | Fetch URL with auto-detection of auth/JS needs |
| `.fetch_multiple()` | 133–144 | Concurrent fetch with semaphore |
| `.search_and_fetch()` | 146–179 | Google site-search + fetch results |
| `._ensure_logged_in()` | 193–240 | Check session → login via vault credentials |
| `._extract()` | 242–265 | Content extraction by mode (text/html/structured/links) |
| `fetch_with_browser()` | 269–331 | **Sync wrapper** for non-async code (used by researcher) |
| `fetch_multiple_with_browser()` | 334–352 | Sync wrapper for batch fetches |

**Constants**: `AUTH_REQUIRED_DOMAINS` = {linkedin, indeed, glassdoor, github} · `JS_REQUIRED_DOMAINS` = {medium, substack, bloomberg, ft}

**Issues**: `_extract()` iterates `self._browsers.values()` to get "any" browser rather than the one that owns the page — fragile if multiple profiles are active.

---

### `browser/tools.py` (182 lines)

**Purpose**: Claude `tool_use` integration for stealth browser.

| Name | Lines | Purpose |
|------|-------|---------|
| `BROWSER_FETCH_TOOL` / `BROWSER_SEARCH_TOOL` | 15–90 | Tool definitions (Claude format) |
| `execute_browser_tool()` | 93–141 | Async dispatcher for browser_fetch / browser_search |
| `_format_fetch_result()` / `_format_search_results()` | 144–182 | Format results for Claude tool_result |

**Constants**: Content truncated at 15,000 chars (fetch) / 5,000 chars (search results).

---

## 3. `deploy/` — VPS Deployment & Scheduling (4 files, 939 lines)

SSH-based deployment tooling for running Agent Brain on a remote VPS.

### `deploy/__init__.py` (16 lines)
Docstring describing deploy/schedule/monitor/manage capabilities.

---

### `deploy/vps_config.py` (87 lines)

**Purpose**: VPS connection and deployment settings (dataclass + JSON persistence).

| Name | Lines | Purpose |
|------|-------|---------|
| `VPSConfig` (dataclass) | 25–69 | Connection (host, port, user), paths, scheduling, monitoring, safety, state |
| `load_config()` / `save_config()` | 72–87 | JSON load/save with `atomic_json_write` |

**Constants**: `DEFAULT_REMOTE_DIR` = /opt/agent-brain · `DEFAULT_PYTHON` = python3.12 · `DEFAULT_SCHEDULE` = "0 */6 * * *" (every 6h) · `DEFAULT_MAX_DAILY_RUNS` = 8 · `DEFAULT_LOG_RETENTION_DAYS` = 30

---

### `deploy/ssh_manager.py` (265 lines)

**Purpose**: Remote command execution via system ssh/scp (no paramiko).

| Name | Lines | Purpose |
|------|-------|---------|
| `SSHManager` (class) | 39–265 | SSH connection manager |
| `.run()` | 117–152 | Execute remote command via subprocess ssh |
| `.run_script()` | 154–158 | Multi-line script via heredoc |
| `.upload_file()` | 162–178 | SCP single file |
| `.upload_dir()` | 180–209 | rsync (falls back to scp -r) |
| `.download_file()` | 211–215 | SCP download |
| `.test_connection()` | 219–225 | Connectivity test |
| `.get_system_info()` | 227–247 | Remote OS/uptime/disk/memory/python info |
| `.cleanup()` | 251–256 | Remove temp key files |

**Constants**: `SSH_CONNECT_TIMEOUT` = 10 · `SSH_COMMAND_TIMEOUT` = 300 · `SCP_TIMEOUT` = 600

**Issues**: Temp key file uses `tempfile.mkstemp` but the destructor (`__del__`) is unreliable in Python — `cleanup()` should be called explicitly (which it is in deployer.py via `finally`).

---

### `deploy/deployer.py` (571 lines)

**Purpose**: Full deployment pipeline + scheduling + health monitoring.

| Name | Lines | Purpose |
|------|-------|---------|
| `create_archive()` | 55–74 | Create .tar.gz deployment archive |
| `deploy()` | 77–224 | **MAIN**: 8-step pipeline (connect → archive → prepare → upload → extract → install → cron → verify) with dry_run support |
| `_build_cron_entry()` | 230–244 | Build cron entry from config |
| `setup_schedule()` / `remove_schedule()` | 247–307 | Manage cron on VPS |
| `health_check()` | 312–395 | Check SSH, process, cron, disk, last logs, recent outputs, budget |
| `get_remote_logs()` | 398–427 | Tail remote logs |
| `cli_main()` | 433–571 | CLI (configure, deploy, health, logs, schedule, unschedule, status) |

**Constants**: `DEPLOY_EXCLUDE` set (13 entries: __pycache__, .git, memory, logs, strategies, vault, browser/_profiles, etc.)

---

## 4. `mcp/` — Model Context Protocol Gateway (6 files, 1,759 lines)

Manages MCP servers running in Docker containers, bridges their tools into Agent Brain.

### `mcp/__init__.py` (20 lines)
Module docstring + `MCP_AVAILABLE = True` flag.

---

### `mcp/protocol.py` (235 lines)

**Purpose**: JSON-RPC 2.0 message encoding/decoding for MCP.

| Name | Lines | Purpose |
|------|-------|---------|
| `build_request()` | 35–48 | Build JSON-RPC 2.0 request as newline-terminated bytes |
| `build_notification()` | 51–59 | Notification (no id) |
| `parse_response()` | 62–88 | Parse JSON-RPC response, validate jsonrpc:"2.0" |
| `is_error_response()` / `get_result()` | 91–106 | Error checking + result extraction |
| `build_initialize()` | 114–129 | MCP initialize request |
| `build_initialized_notification()` | 132–134 | Post-init notification |
| `build_tools_list()` / `build_tools_call()` / `build_resources_list()` / `build_prompts_list()` / `build_ping()` | 137–165 | MCP-specific request builders |
| `parse_tool_definition()` | 175–188 | MCP inputSchema → Claude input_schema (camelCase→snake_case) |
| `parse_tools_list_result()` | 191–202 | Parse tools/list response |
| `parse_tool_call_result()` | 205–235 | Parse tools/call response content blocks (text, image, resource) |

**Constants**: `MCP_PROTOCOL_VERSION` = "2024-11-05"

---

### `mcp/docker_manager.py` (478 lines)

**Purpose**: Docker container lifecycle for MCP servers (start/stop/communicate via stdio JSON-RPC).

| Name | Lines | Purpose |
|------|-------|---------|
| `McpServerConfig` (dataclass) | 43–89 | Server config: image, command, env, volumes, network, categories, timeouts, etc. |
| `McpContainer` (class) | 95–478 | Full container lifecycle |
| `.start()` | 121–168 | Build docker command, launch subprocess, initialize MCP, discover tools |
| `.stop()` | 170–187 | Terminate gracefully (5s term → kill) |
| `.restart()` | 189–209 | Restart with max_restarts guard |
| `.send_request()` | 211–260 | Send JSON-RPC request, read response (skipping notifications), with timeout |
| `.call_tool()` | 262–278 | Call MCP tool and return string result |
| `.ping()` | 280–286 | Health check |
| `._build_docker_command()` | 292–327 | Build `docker run -i --rm` command with env/volumes/network |
| `._resolve_env_value()` | 330–335 | Resolve `${VAR}` references from host env |
| `._pull_image()` | 337–362 | Pull Docker image if not present |
| `._mcp_initialize()` | 364–392 | MCP initialize handshake |
| `._mcp_list_tools()` | 394–414 | Fetch tool definitions |
| `._read_line_with_timeout()` | 416–427 | Read stdout line using `select()` |
| `._capture_stderr()` | 429–445 | Background thread for stderr capture |
| `.get_status()` | 447–460 | Status dict for monitoring |

---

### `mcp/gateway.py` (399 lines)

**Purpose**: Multi-server gateway — aggregates tools, routes calls, manages lifecycles.

| Name | Lines | Purpose |
|------|-------|---------|
| `McpGateway` (class) | 41–380 | Central MCP coordinator |
| `.load_config()` | 70–139 | Load from `mcp_servers.json` |
| `.save_config()` | 141–168 | Save back to JSON |
| `.start_all()` / `.start_server()` | 174–210 | Start all/one enabled servers |
| `.stop_all()` / `.stop_server()` | 212–227 | Stop servers |
| `.get_all_tools()` | 233–239 | Aggregated tool list (prefixed names: `server__tool`) |
| `.get_tools_by_category()` | 248–259 | Filter by server category |
| `.call_tool()` | 261–305 | Route tool call to correct server (with auto-restart on failure) |
| `.health_check()` / `.get_status()` | 311–348 | Monitoring endpoints |
| `._rebuild_tool_index()` | 354–365 | Rebuild tool→server mapping |
| `._prefix_tool()` | 368–380 | Namespace tools to prevent collisions |
| `get_gateway()` / `reset_gateway()` | 387–399 | Module-level singleton |

---

### `mcp/context_router.py` (344 lines)

**Purpose**: Intelligent tool filtering — selects only relevant tools per task to avoid context waste.

| Name | Lines | Purpose |
|------|-------|---------|
| `ContextRouter` (class) | 68–324 | Routes tasks to relevant MCP tools |
| `.select_tools()` | 101–140 | Score all tools against task, return top N |
| `.record_usage()` | 142–159 | Record tool usage for history-based routing |
| `.get_categories_for_task()` | 161–172 | Keyword→category mapping |
| `._score_tool()` | 178–229 | Scoring: category match (0.4) + keyword match (0.3) + history (0.2) + base (0.1) |
| `._keyword_score()` | 231–268 | Jaccard-ish keyword overlap |
| `._history_score()` | 270–297 | Historical success of tool on similar tasks |
| `._extract_keywords()` | 307–324 | Stop-word filtered keyword extraction |
| `.get_routing_stats()` | 326–344 | Routing analytics |

**Constants**: `DEFAULT_MAX_MCP_TOOLS` = 15 · `KEYWORD_CATEGORIES` — 11 pattern→category mappings

---

### `mcp/tool_bridge.py` (283 lines)

**Purpose**: Bridges MCP tools into both Agent Brain tool systems (research + execution).

| Name | Lines | Purpose |
|------|-------|---------|
| `McpProxyTool` (class) | 38–125 | BaseTool-compatible proxy for MCP tools (execution layer) |
| `get_mcp_research_tools()` | 133–184 | Get filtered tool defs + dispatch function for researcher agent |
| `get_mcp_tool_names()` | 187–189 | Extract tool name set |
| `route_mcp_tool_call()` | 196–206 | Universal one-off dispatcher |
| `register_mcp_tools_in_registry()` | 213–283 | Register all MCP tools in ToolRegistry with `mcp_` prefix |

**Issues**: `McpProxyTool` duck-types `BaseTool` instead of inheriting (avoids circular import) — works but fragile if BaseTool interface changes.

---

## 5. `rag/` — Vector Search (4 files, 901 lines)

Semantic retrieval via ChromaDB + sentence-transformers. Replaces TF-IDF.

### `rag/__init__.py` (11 lines)
Module docstring.

---

### `rag/embeddings.py` (86 lines)

**Purpose**: Embedding model management (lazy singleton).

| Name | Lines | Purpose |
|------|-------|---------|
| `_get_model()` | 29–33 | Lazy-load SentenceTransformer (all-MiniLM-L6-v2) |
| `embed_texts()` | 36–49 | Batch embed → list[list[float]] |
| `embed_single()` | 52–54 | Single text embed |
| `SentenceTransformerEmbeddingFunction` (class) | 57–74 | ChromaDB-compatible embedding function |
| `get_embedding_fn()` | 77–79 | Factory |
| `get_embedding_dim()` | 82–84 | Returns 384 |

**Constants**: `_MODEL_NAME` = "all-MiniLM-L6-v2" (overridable via `EMBEDDING_MODEL` env) · `_EMBEDDING_DIM` = 384

---

### `rag/vector_store.py` (565 lines)

**Purpose**: ChromaDB-backed claim-level indexing and retrieval.

| Name | Lines | Purpose |
|------|-------|---------|
| `_get_client()` / `_get_embedding_fn()` | 53–65 | Lazy singletons |
| `_get_claims_collection()` / `_get_questions_collection()` | 68–82 | ChromaDB collection accessors |
| `_claim_id()` / `_question_id()` / `_kb_claim_id()` | 86–98 | Deterministic SHA-256 IDs (16 char hex) |
| `index_output()` | 103–185 | Index findings + insights + question from a research output |
| `index_knowledge_base()` | 188–237 | Index synthesized KB claims (type="kb_claim") |
| `index_all_outputs()` | 240–251 | Bulk index for migration |
| `search_claims()` | 256–348 | **MAIN RETRIEVAL**: semantic search with domain/score/accepted filters, L2→cosine similarity conversion |
| `search_similar_questions()` | 351–394 | Question dedup via semantic similarity |
| `cross_domain_search()` | 399–424 | Search across all domains (Layer 5) |
| `get_collection_stats()` | 429–440 | Collection counts |
| `clear_domain()` | 443–474 | Remove all vectors for a domain |
| `rebuild_index()` | 477–502 | Full re-index: clear → index outputs → index KB |
| `reset_client()` / `set_vectordb_dir()` | 508–516 | Test helpers |

**Constants**: `CLAIMS_COLLECTION` = "claims" · `QUESTIONS_COLLECTION` = "questions" · `DEFAULT_MAX_RESULTS` = 10 · `RELEVANCE_THRESHOLD` = 0.3

**Two collections**: "claims" (individual findings at claim granularity) and "questions" (past questions for dedup).

---

### `rag/retrieval.py` (239 lines)

**Purpose**: Drop-in replacement for memory_store's TF-IDF retrieval. Falls back gracefully.

| Name | Lines | Purpose |
|------|-------|---------|
| `_rag_available()` | 24–30 | Check chromadb + sentence_transformers imports |
| `retrieve_relevant_rag()` | 42–151 | Semantic retrieval → groups claims by source question to match original return format |
| `is_duplicate_question_rag()` | 154–182 | Semantic question dedup (threshold=0.80) |
| `retrieve_cross_domain()` | 188–215 | Cross-domain claim retrieval |

**Issues**: Falls back silently to TF-IDF if deps unavailable — good behavior. Enrichment step (L130–145) wraps in bare `except Exception: pass` — should at least log.

---

## 6. `dashboard/` — FastAPI Backend (1 file, 784 lines)

### `dashboard/api.py` (784 lines)

**Purpose**: FastAPI backend exposing system data + real-time SSE loop monitoring.

| Name | Lines | Purpose |
|------|-------|---------|
| `broadcast_event()` | 34–44 | Push events to all SSE clients |
| `APIKeyMiddleware` (class) | 67–82 | X-API-Key auth (optional — open in dev mode) |
| **Health endpoints** | | |
| `GET /` | 98–100 | Root |
| `GET /api/health` | 103–105 | System health from orchestrator |
| `GET /api/health/deep` | 108–122 | Deep health: score trends, budget, rejection rates |
| `GET /api/alerts` | 125–136 | Monitoring alerts query |
| `POST /api/alerts/{id}/acknowledge` | 139–146 | Acknowledge alert |
| `GET /api/db/stats` | 149–175 | Database row counts, size |
| `GET /api/overview` | 178–180 | Full analytics report |
| `GET /api/budget` | 183–196 | Budget + cost info |
| **Domain endpoints** | | |
| `GET /api/domains` | 200–222 | List all domains with stats |
| `GET /api/domains/{domain}` | 225–240 | Detailed domain analytics |
| `GET /api/domains/{domain}/outputs` | 243–280 | Research outputs list |
| `GET /api/domains/{domain}/kb` | 283–288 | Knowledge base |
| **Strategy endpoints** | | |
| `GET /api/domains/{domain}/strategy` | 293–310 | Current strategy + history |
| `GET /api/domains/{domain}/strategy/pending` | 313–316 | Pending strategies |
| `POST /api/domains/{domain}/strategy/approve` | 319–325 | Approve |
| `POST /api/domains/{domain}/strategy/reject` | 328–334 | Reject |
| `POST /api/domains/{domain}/strategy/rollback` | 337–347 | Rollback |
| `GET /api/domains/{domain}/strategy/diff` | 350–356 | Diff two versions |
| `GET /api/cost` | 361–379 | Cost efficiency |
| `GET /api/validate` | 384–397 | Data validation |
| `GET /api/comparison` | 402–404 | Cross-domain comparison |
| **Run loop (SSE)** | | |
| `POST /api/run` | 437–461 | Start research loop → SSE stream |
| `GET /api/run/status` | 464–466 | Is a run in progress? |
| `POST /api/auto` | 504–535 | Autonomous multi-round mode → SSE |
| **Knowledge graph** | | |
| `GET /api/domains/{domain}/graph` | 541–553 | Get knowledge graph |
| `POST /api/domains/{domain}/graph/build` | 556–564 | Build/rebuild graph |
| **Daemon** | | |
| `GET /api/daemon/status` | 569–572 | Daemon status |
| `POST /api/daemon/start` | 575–595 | Start daemon thread |
| `POST /api/daemon/stop` | 598–602 | Stop daemon |
| **Consensus** | | |
| `GET /api/config/consensus` | 608–614 | Get consensus config |
| `POST /api/config/consensus` | 617–624 | Toggle consensus at runtime |

**Imports**: FastAPI, CORSMiddleware, StarlettBaseHTTPMiddleware, StreamingResponse, plus ~10 internal modules.

**Issues**: 
- `_run_loop_thread` monkey-patches `builtins.print` for event capture — works but brittle (any exception during patching leaves print broken). Restored in `finally`.
- `_is_running` global flag is not fully atomic — two near-simultaneous requests could both see `False` before the lock is acquired.
- CORS origins loaded from config string split by comma.

---

## 7. `cli/` — CLI Command Modules (8 files, 1,381 lines)

Extracted from main.py for maintainability. Each module handles a command group.

### `cli/__init__.py` (23 lines)
Docstring + `sys.path.insert` for parent package.

---

### `cli/vault.py` (115 lines)

**Purpose**: Credential vault CLI operations.

| Name | Lines | Purpose |
|------|-------|---------|
| `get_vault()` | 8–22 | Unlock CredentialVault (env var or getpass prompt) |
| `store()` | 25–39 | Store credential (auto-detects JSON vs string) |
| `get()` | 42–62 | Retrieve with password masking |
| `delete()` | 65–72 | Delete credential |
| `list_all()` | 75–93 | List all keys with metadata |
| `stats()` | 96–115 | Vault statistics |

---

### `cli/browser_cmd.py` (61 lines)

**Purpose**: Stealth browser CLI.

| Name | Lines | Purpose |
|------|-------|---------|
| `fetch_url()` | 4–32 | Fetch URL via stealth browser |
| `test_stealth()` | 35–61 | Run bot-detection test against bot.sannysoft.com |

---

### `cli/deploy_cmd.py` (126 lines)

**Purpose**: VPS deployment CLI.

| Name | Lines | Purpose |
|------|-------|---------|
| `deploy()` | 4–38 | Deploy to VPS (with auto-cron setup) |
| `health()` | 41–57 | VPS health check |
| `logs()` | 60–70 | View remote logs |
| `schedule()` / `unschedule()` | 73–95 | Cron management |
| `configure()` | 98–126 | Set VPS connection params |

---

### `cli/knowledge.py` (166 lines)

**Purpose**: Knowledge base, synthesis, and graph CLI.

| Name | Lines | Purpose |
|------|-------|---------|
| `run_synthesize()` | 14–33 | Force KB synthesis + auto-build graph |
| `show_kb()` | 36–42 | Display KB |
| `versions()` | 45–60 | KB version history |
| `kb_rollback()` | 63–82 | Rollback KB to previous version |
| `prune()` | 85–115 | Memory hygiene (archive low-quality outputs) |
| `graph()` | 118–166 | Display knowledge graph summary + contradictions + gaps |

---

### `cli/project.py` (172 lines)

**Purpose**: Project orchestrator CLI.

| Name | Lines | Purpose |
|------|-------|---------|
| `run()` | 4–50 | Decompose and execute a project |
| `status()` | 53–93 | Show project status |
| `resume()` | 96–115 | Resume paused project |
| `approve_phase()` | 118–140 | Approve review-gated phase |
| `list_all()` | 143–172 | List all projects |

---

### `cli/strategy.py` (358 lines)

**Purpose**: Strategy management CLI (the most complex CLI module).

| Name | Lines | Purpose |
|------|-------|---------|
| `show_status()` | 22–57 | Strategy status + version performance table |
| `approve()` | 60–94 | Approve pending strategy (preview + approve) |
| `reject()` | 97–103 | Reject pending strategy |
| `diff()` | 106–139 | Line-level diff between two versions |
| `rollback()` | 142–151 | Manual rollback |
| `audit()` | 154–210 | Unified audit trail (run history, strategy changes, pending, spend) |
| `budget()` | 213–268 | Cost tracking + budget display |
| `principles()` | 271–315 | Cross-domain principles display |
| `transfer()` | 318–358 | Generate seed strategy from principles |

---

### `cli/tools_cmd.py` (360 lines)

**Purpose**: Crawl, fetch, RAG, and MCP CLI commands.

| Name | Lines | Purpose |
|------|-------|---------|
| `crawl()` | 11–39 | Crawl documentation site |
| `fetch()` | 42–62 | Fetch single URL |
| `crawl_inject()` | 65–82 | Inject crawl data into KB |
| `rag_status()` | 88–107 | RAG vector store stats |
| `rag_rebuild()` | 110–150 | Rebuild RAG index |
| `rag_search()` | 153–186 | Semantic search CLI |
| `mcp_status()` | 192–222 | MCP gateway status |
| `mcp_start_all()` | 225–253 | Start all MCP servers |
| `mcp_stop_all()` | 256–266 | Stop all MCP servers |
| `mcp_tools()` | 269–304 | List all MCP tools |
| `mcp_health()` | 307–340 | MCP server health checks |

---

## Summary of Issues Found

| # | File | Severity | Description |
|---|------|----------|-------------|
| 1 | `hands/validator.py` | **Bug** | `_MAX_FILE_CHARS` defined as 8,000 (L117) then overwritten to 500,000 (L183) — likely unintentional |
| 2 | `hands/executor.py` | Minor | `sys.path.insert` for imports (fragile in installed packages) |
| 3 | `hands/executor.py` | Minor | Hardcoded Haiku pricing (will break if rates change) |
| 4 | `hands/planner.py` | Minor | Unknown tools silently coerced to "terminal" |
| 5 | `hands/project_orchestrator.py` | Minor | `log_cost()` call signature inconsistent with other callsites |
| 6 | `hands/tools/terminal.py` | Note | `shell=True` needed but increases attack surface (mitigated by whitelist) |
| 7 | `browser/session_manager.py` | Minor | `_extract()` grabs arbitrary browser from dict — fragile with multiple profiles |
| 8 | `deploy/ssh_manager.py` | Minor | `__del__` cleanup unreliable — mitigated by explicit `cleanup()` in deployer |
| 9 | `mcp/tool_bridge.py` | Minor | `McpProxyTool` duck-types BaseTool — fragile if interface changes |
| 10 | `rag/retrieval.py` | Minor | Bare `except Exception: pass` in enrichment step (should log) |
| 11 | `dashboard/api.py` | Minor | Monkey-patches `builtins.print` for SSE capture — brittle |
| 12 | `dashboard/api.py` | Minor | `_is_running` race condition between global check and lock acquisition |
