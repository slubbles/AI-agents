Here's the complete honest audit after scanning every module:

FULL CAPABILITY MAP — What Exists vs What's Integrated
FULLY INTEGRATED (wired end-to-end, reachable from Telegram/CLI/Daemon)
#	Capability	Where	Reachable From
1	Web Search (DuckDuckGo)	tools/web_search.py	Researcher, Chat, Telegram
2	Web Fetching (Scrapling + browser fallback)	tools/web_fetcher.py	Researcher, Chat
3	Research Loop (search → critic → score → store)	agents/researcher.py, agents/critic.py	CLI, Telegram /research, Daemon
4	Strategy Evolution (meta-analyst rewrites strategies)	agents/meta_analyst.py, strategy_store.py	Daemon auto-evolves every 3 outputs
5	Cross-Domain Transfer	agents/cross_domain.py	CLI --transfer
6	Knowledge Base (synthesized claims)	agents/synthesizer.py, memory_store.py	Researcher reads prior knowledge
7	Knowledge Graph	knowledge_graph.py	Researcher gets graph context per question
8	Source Quality Tracking	source_quality.py	Researcher gets source hints in prompt
9	LLM Routing (4-tier: DeepSeek/Grok/Claude/Gemini)	llm_router.py	Everything
10	Cost Tracking + Per-Provider Budgets	cost_tracker.py, config.py	Daemon, CLI, Telegram /status
11	Telegram Bot (chat, commands, tool use)	telegram_bot.py	Active on VPS
12	Telegram Alerts (daemon events, budget, errors)	alerts.py	Daemon → Telegram notifications
13	Daemon Scheduler (multi-domain research cycles)	scheduler.py	cortex-daemon.service (currently DISABLED)
14	Watchdog (circuit breaker, cost ceiling, cooldown)	watchdog.py	Daemon pre-cycle check
15	Health Monitoring (score trends, drops, staleness)	monitoring.py	Daemon inter-cycle checks
16	Loop Guard (stuck detection, similarity, cost velocity)	loop_guard.py	Research loop
17	Prescreen (cheap grok filter before Claude critic)	prescreen.py	Main research loop
18	Progress Tracker (goal-distance assessment)	progress_tracker.py	Every 5 accepted outputs
19	Agent Hands — Planner	hands/planner.py	Chat execute_task, Pipeline /build
20	Agent Hands — Executor (24 tools: write_file, run_cmd, etc.)	hands/executor.py, hands/tools/	Pipeline, Chat
21	Mid-Execution Quality Gates	hands/mid_validator.py	Executor during builds
22	Visual Gate (screenshot → Claude Vision → fix)	hands/visual_gate.py, hands/visual_evaluator.py	Executor during frontend builds
23	Pipeline (Brain → Approve → Hands → Done)	agents/cortex.py → pipeline()	Telegram /build, Chat auto_build
24	Project Orchestrator (multi-phase decomposition)	hands/project_orchestrator.py	Chat run_project
25	Execution Memory (learned patterns from past builds)	hands/exec_memory.py, hands/pattern_learner.py	Planner reads for next builds
26	Identity/Skills System (design rubrics, coding standards)	identity/, skills_loader.py, identity_loader.py	Planner/Executor system prompts
27	LLM Cache	utils/llm_cache.py	Configurable via LLM_CACHE_ENABLED
28	Rate Limiter	utils/rate_limiter.py	LLM router
29	Retry with Exponential Backoff	utils/retry.py	LLM calls
30	SQLite Database (outputs, costs, alerts, health)	db.py	Daemon, analytics, dashboard API
31	Analytics (trajectories, distributions, cost efficiency)	analytics.py	CLI --analytics
32	Research Lessons (failure pattern tracking)	research_lessons.py	Question generator
33	PTC (Programmatic Tool Calling — pre-wired)	config.py, llm_router.py, researcher.py	Flip PTC_ENABLED=true (needs Anthropic credits)
BUILT BUT NOT INTEGRATED (standalone modules, no wiring to main flow)
#	Capability	Files	What It Does	What's Missing
A	MCP Gateway (Docker-based MCP servers)	mcp/gateway.py, mcp/docker_manager.py, mcp/protocol.py, mcp/tool_bridge.py, mcp/context_router.py	Full MCP client: start Docker containers, list tools, call tools, context-aware routing	Only reachable from CLI (cli/tools_cmd.py). NOT wired into researcher, executor, or daemon. MCP tools can't be used during research or builds.
B	MCP Context Router (task-aware tool selection)	mcp/context_router.py	Scores MCP tools by relevance to task, picks best subset	Same — not wired to any agent. The router exists but no agent calls select_tools()
C	MCP Tool Bridge (proxy MCP tools into Hands registry)	mcp/tool_bridge.py	register_mcp_tools_in_registry() can inject MCP tools into ToolRegistry	Never called. Hands executor only sees built-in tools, never MCP tools
D	Threads API — Post/Reply/Insights	tools/threads_client.py	publish_post(), reply_to_thread(), get_thread_insights(), get_profile_insights(), get_recent_engagement()	Telegram has /threads commands but only search/post/draft/analyze are wired. get_thread_insights(), get_profile_insights(), get_recent_engagement() exist but are not exposed anywhere — not in chat tools, not in daemon
E	Signal Intelligence — Scrapling Enrichment	signal_collector.py → enrich_post(), enrich_top_posts(), check_engagement_changes()	Fetches real Reddit upvote/comment counts via Scrapling	Built + tested but never called automatically. Only via CLI --enrich-signals. Daemon doesn't call it. No auto-enrichment in signal cycle.
F	Signal → Build Spec Pipeline	opportunity_scorer.py → generate_build_spec()	Takes scored opportunity → generates a full build specification	Built but never auto-triggered. Build specs are generated but never handed to Hands/Pipeline
G	Signal Bridge (signals → research questions)	signal_bridge.py → generate_signal_questions()	Converts top Reddit signals into research questions	Wired in daemon's signal cycle but the daemon is DISABLED, so it's never running
H	Dashboard API (FastAPI + Next.js frontend)	dashboard/api.py, dashboard/frontend/	Full REST API: /api/overview, /api/budget, /api/domains, /api/signals, /api/exec, SSE events	Never started. Not in any service file. Not accessible on VPS. Frontend is Next.js but not deployed
I	Credential Vault (encrypted secrets)	utils/credential_vault.py	Fernet-encrypted secret storage with passphrase	Only used by deploy module (deploy/deployer.py). Not used for API keys, Telegram token, or other secrets
J	Deploy Module (SSH deploy to VPS)	deploy/deployer.py, deploy/ssh_manager.py, deploy/vps_config.py	deploy(), setup_schedule(), health_check(), get_remote_logs()	Only reachable from CLI (cli/deploy_cmd.py). Not wired into any automated flow — can't auto-deploy build artifacts
K	RAG/Vector Search (ChromaDB + sentence-transformers)	rag/embeddings.py, rag/vector_store.py, rag/retrieval.py	Embeddings, vector store, semantic search, cross-domain search, duplicate detection	Partially integrated. retrieve_relevant_rag() is called from memory_store.retrieve_relevant() when RAG_ENABLED=true, but RAG index is never auto-built — only via CLI --rebuild-index. New research outputs don't auto-index.
L	Dataset Loader (HuggingFace + GitHub code examples)	tools/dataset_loader.py	Fetch code examples from HuggingFace datasets, GitHub repos, inject into strategy	Never called automatically. Only from tests. The inject_examples_into_strategy() function exists but nothing triggers it
M	Crawl-to-KB (convert crawled pages into knowledge)	tools/crawl_to_kb.py	Extracts claims from crawl_data/ → injects into knowledge base	Only reachable from CLI (cli/tools_cmd.py:crawl()). Not auto-triggered after crawling
N	Browser Stealth Module (Playwright anti-detection)	browser/stealth_browser.py	Full stealth browser: fingerprint spoofing, human-like behavior, session persistence	Only used by web_fetcher.py as browser fallback when Scrapling fails. Not directly accessible for web automation tasks
O	Hands Consultant (ask human for clarification mid-build)	hands/consultant.py	_consult tool in executor lets agent ask questions during builds	Tool exists in registry but answers come from LLM, not actual human. In Telegram builds, there's no way for the user to answer mid-build questions
P	Domain Seeder (curated seed questions)	domain_seeder.py	Pre-written starter questions for known domains	Integrated into question generator, but the curated domains list may be stale
MCP SERVERS CONFIGURED (in mcp_servers.json)
Server	Status	What It Does
filesystem	disabled	Read/write workspace files
github	enabled	GitHub API — repos, issues, PRs, search
fetch	disabled	URL fetching (redundant — we have Scrapling)
postgres	disabled	PostgreSQL queries
puppeteer	disabled	Browser automation (redundant — we have stealth browser)
idea-reality	enabled	Pre-build reality check — scans GitHub/HN/npm/PyPI/ProductHunt
Only github and idea-reality are enabled, but neither is reachable from any agent — only from CLI.

THE GAPS THAT MATTER MOST
Priority-ordered by what would unlock the most value:

MCP tools not available during research or builds — The whole MCP system (gateway, protocol, bridge, router) exists but agents can't use it. The idea-reality check should run before every /build. GitHub MCP should be available during coding tasks.

Signal enrichment never auto-runs — enrich_top_posts() exists but daemon's signal cycle doesn't call it. Engagement data stays stale.

Signal → Build pipeline broken — generate_build_spec() produces build specs but nothing hands them to the Pipeline. The full vision (detect pain → score → build spec → build) has a broken link.

RAG index never auto-updates — New research outputs go to memory but not ChromaDB. Semantic search gets staler over time.

Dashboard never started — Full API exists, Next.js frontend exists, neither is deployed or accessible.

Threads insights not exposed — get_thread_insights() and get_profile_insights() exist but aren't in chat tools or Telegram commands.

Deploy not automated — deploy() exists but build artifacts from Hands sit in output/ forever. No auto-deploy.

Now, what do you want me to wire up?

