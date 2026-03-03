"""
Agent Brain — Configuration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

# --- LLM Providers ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# ── 3-Tier Model Architecture ──────────────────────────────────────────
# Tier 1 (CHEAPEST): DeepSeek V3.2 — high-volume, low-stakes tasks
# Tier 2 (FAST):     Grok 4.1 Fast — latency-sensitive, tool-use loops
# Tier 3 (PREMIUM):  Claude Sonnet  — sacred quality tasks, reasoning
#
# Zero overlap: each model serves a distinct purpose based on task profile.

_FALLBACK = "claude-haiku-4-5-20251001"  # when OpenRouter not configured

CHEAPEST_MODEL = (
    "deepseek/deepseek-chat"  # DeepSeek V3.2 — cheapest, strong reasoning
    if OPENROUTER_API_KEY
    else _FALLBACK
)

FAST_MODEL = (
    "x-ai/grok-4.1-fast"  # Grok 4.1 — low latency, tool-use loops
    if OPENROUTER_API_KEY
    else _FALLBACK
)

PREMIUM_MODEL = "claude-sonnet-4-20250514"  # Sacred — never cut corners

# Tier 4 (CHAT): Google Gemini 2.0 Flash — cheap, fast, reasoning support
# Human chat interface: 40x cheaper than Sonnet, good quality, tool use.
# Claude stays as orchestrator voice (orchestrator tools route through Sonnet).
CHAT_MODEL = (
    "google/gemini-2.0-flash-001"  # $0.075/M input, $0.30/M output
    if OPENROUTER_API_KEY
    else _FALLBACK
)

# Available models for /model switching (chat interface only)
AVAILABLE_CHAT_MODELS = {
    "gemini-flash": {
        "id": "google/gemini-2.0-flash-001",
        "label": "Gemini 2.0 Flash",
        "cost": "$0.075/$0.30 per 1M",
        "reasoning": True,
        "notes": "Default. Cheapest + fast + reasoning.",
    },
    "grok": {
        "id": "x-ai/grok-4.1-fast",
        "label": "Grok 4.1 Fast",
        "cost": "$0.50/$2.00 per 1M",
        "reasoning": True,
        "notes": "Powerful reasoning, higher cost.",
    },
    "deepseek": {
        "id": "deepseek/deepseek-chat",
        "label": "DeepSeek V3.2",
        "cost": "$0.27/$1.10 per 1M",
        "reasoning": True,
        "notes": "Strong reasoning, cheap.",
    },
    "sonnet": {
        "id": "claude-sonnet-4-20250514",
        "label": "Claude Sonnet 4",
        "cost": "$3.00/$15.00 per 1M",
        "reasoning": False,
        "notes": "Best quality. Expensive — use sparingly.",
    },
}

# Backward compat alias (some tests/modules reference CHEAP_MODEL)
CHEAP_MODEL = FAST_MODEL

# Model assignments per agent role
# Tier 1 = cheapest (synthesis/routing), Tier 2 = fast (interactive/tools),
# Tier 3 = premium (quality-critical judgment), Tier 4 = chat (cheap + capable)
MODELS = {
    # Tier 1 — DeepSeek V3.2 (cheapest, high volume)
    "question_generator": CHEAPEST_MODEL,          # synthesis task — cheapest wins
    "prescreen": CHEAPEST_MODEL,                    # pre-filter before Claude critic
    "progress_tracker": CHEAPEST_MODEL,             # periodic assessment
    # Tier 2 — Grok 4.1 Fast (low latency, tool-use loops)
    "researcher": FAST_MODEL,                       # many tool-use round trips, speed matters
    # Tier 4 — Gemini Flash (chat interface — cheap but capable)
    # Claude stays as orchestrator voice via orchestrator tools.
    "chat": CHAT_MODEL,                             # human interface — cheap + reasoning
    # Tier 3 — Claude Sonnet (sacred quality tasks)
    "critic": PREMIUM_MODEL,                        # quality signal — NEVER cut corners
    "meta_analyst": PREMIUM_MODEL,                  # pattern extraction needs reasoning
    "synthesizer": PREMIUM_MODEL,                   # contradiction detection + integration
    "cross_domain": PREMIUM_MODEL,                  # principle abstraction
    "verifier": PREMIUM_MODEL,                      # reality checking is sacred
    "cortex_orchestrator": PREMIUM_MODEL,           # strategic reasoning above Brain+Hands
}

# --- Quality Gate ---
QUALITY_THRESHOLD = 6  # minimum score (1-10) to accept output
MAX_RETRIES = 2  # how many times researcher retries after rejection

# --- Critic Enhancements ---
CRITIC_ENSEMBLE = True            # cross-model ensemble: Claude Sonnet + DeepSeek V3.2
CRITIC_ENSEMBLE_MODEL_B = CHEAPEST_MODEL  # second critic voice (different architecture = less correlated errors)
CRITIC_LOG_PARSE_FAILURES = True  # write raw critic response to logs/ on parse failure
CONFIDENCE_VALIDATION = True      # post-hoc check: "high" claims must cite 2+ sources
CONFIDENCE_PENALTY = 1.0          # accuracy deduction for invalid high-confidence claims

# --- Memory ---
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory")
STRATEGY_DIR = os.path.join(os.path.dirname(__file__), "strategies")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
DB_PATH = os.path.join(os.path.dirname(__file__), "logs", "agent_brain.db")

# --- Budget ---
# Estimated cost per 1K tokens (input/output) for tracking
# These are approximations used for budget awareness, not billing
COST_PER_1K = {
    # Claude models (Anthropic direct)
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    # Grok via OpenRouter
    "x-ai/grok-4.1-fast": {"input": 0.0005, "output": 0.002},
    # DeepSeek V3.2 via OpenRouter (cheapest)
    "deepseek/deepseek-chat": {"input": 0.00027, "output": 0.0011},
    # Gemini 2.0 Flash via OpenRouter
    "google/gemini-2.0-flash-001": {"input": 0.000075, "output": 0.0003},
}
DAILY_BUDGET_USD = 7.00  # Combined daily budget (sum of per-provider limits)

# Per-provider daily budget limits
DAILY_BUDGET_CLAUDE = float(os.environ.get("DAILY_BUDGET_CLAUDE", "2.00"))
DAILY_BUDGET_OPENROUTER = float(os.environ.get("DAILY_BUDGET_OPENROUTER", "5.00"))

# Display-only: approximate API credit balances. Not gates — just shown in status.
# Update with: python main.py --sync-balance (or manually from provider consoles)
TOTAL_BALANCE_USD = float(os.environ.get("TOTAL_BALANCE_USD", "13.31"))
BALANCE_CLAUDE = float(os.environ.get("BALANCE_CLAUDE", "3.90"))
BALANCE_OPENROUTER = float(os.environ.get("BALANCE_OPENROUTER", "9.41"))

# Model → provider mapping (for per-provider budget tracking)
MODEL_PROVIDER = {
    "claude-haiku-4-5-20251001": "claude",
    "claude-sonnet-4-20250514": "claude",
    "x-ai/grok-4.1-fast": "openrouter",
    "deepseek/deepseek-chat": "openrouter",
    "google/gemini-2.0-flash-001": "openrouter",
}

# --- Loop ---
DEFAULT_DOMAIN = "general"

# --- Research ---
MAX_TOOL_ROUNDS = 8   # max rounds of tool-use before forcing output
MAX_SEARCHES = 10     # hard cap on total web searches per run
MAX_FETCHES = 8       # hard cap on total page fetches per run

# --- Reasoning (OpenRouter models with reasoning support) ---
# Grok 4.1:    reasoning.effort via extra_body ("low", "medium", "high")
# DeepSeek V3.2: reasoning_enabled boolean via extra_body
# Claude:      N/A (reasoning is native, no toggle)
#
# Per-role override: set reasoning where it helps most.
REASONING_EFFORT = {
    # Tier 1 — DeepSeek (reasoning_enabled boolean)
    "question_generator": None,    # keep cheap — synthesis task
    "prescreen": None,             # keep cheap — pre-filter
    "progress_tracker": None,      # keep cheap — assessment
    "critic_ensemble_b": True,     # ENABLE reasoning for DeepSeek critic (quality matters)
    # Tier 2 — Grok (reasoning.effort: low/medium/high)
    "researcher": None,            # keep fast — tool-use loops, reasoning slows down
    # Chat uses Gemini Flash — enable reasoning for better quality
    "chat": "high",               # Gemini Flash reasoning (thinking tokens)
    # Tier 3 — Claude (N/A — reasoning is native)
    "critic": None,
    "meta_analyst": None,
    "synthesizer": None,
    "cross_domain": None,
    "verifier": None,
    "cortex_orchestrator": None,
}

# --- RAG (Retrieval-Augmented Generation) ---
RAG_ENABLED = True                # use vector embeddings for semantic retrieval
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # local, free, 384 dimensions
VECTORDB_DIR = os.path.join(os.path.dirname(__file__), "memory", "_vectordb")

# --- Browser (Playwright Stealth) ---
BROWSER_ENABLED = True            # enable stealth browser for JS-rendered/auth-required sites
BROWSER_HEADLESS = True           # run browser headless (True for server, False for debugging)
BROWSER_MAX_FETCHES = 3           # max browser fetches per research run (browser is slower)

# --- Credential Vault ---
VAULT_PASSPHRASE_ENV = "VAULT_PASSPHRASE"  # env var name for vault master passphrase

# --- VPS Deploy ---
DEPLOY_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "deploy", "vps_config.json")

# --- LLM Response Cache ---
LLM_CACHE_ENABLED = True
LLM_CACHE_TTL = 3600             # seconds before cached response expires (1 hour)
LLM_CACHE_DIR = os.path.join(os.path.dirname(__file__), "logs", "_llm_cache")

# --- MCP (Model Context Protocol) Gateway ---
MCP_ENABLED = True                # enable Docker MCP server integration
MCP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "mcp_servers.json")
MCP_MAX_TOOLS_PER_CALL = 15      # max MCP tools surfaced in a single Claude call
MCP_DEFAULT_TIMEOUT = 30.0       # seconds before MCP request times out
MCP_AUTO_START = False            # start MCP servers on agent-brain boot

# --- Strategy Evolution ---
SAFETY_DROP_THRESHOLD = 0.20  # block if new strategy avg drops >20%
TRIAL_PERIOD = 5              # outputs under trial before evaluation
TRIAL_EXTEND_LIMIT = 3        # max extensions when evidence is inconclusive
TRIAL_P_VALUE_THRESHOLD = 0.10  # p-value threshold for t-test significance

# --- Meta-Analysis ---
MIN_OUTPUTS_FOR_ANALYSIS = 3   # min outputs before meta-analysis runs
MAX_OUTPUTS_TO_ANALYZE = 20    # max recent outputs fed into meta-analyst
EVOLVE_EVERY_N = 3             # evolve every N new outputs

# --- Synthesis ---
MIN_OUTPUTS_FOR_SYNTHESIS = 3   # min accepted outputs to trigger synthesis
MAX_OUTPUTS_TO_SYNTHESIZE = 25  # max outputs in one synthesis call
SYNTHESIZE_EVERY_N = 5          # synthesize every N new accepted outputs

# --- Cross-Domain Transfer ---
MIN_OUTPUTS_FOR_TRANSFER = 10   # min outputs for a domain to be a transfer source
MIN_AVG_SCORE_FOR_TRANSFER = 6.0

# --- Claim Expiry ---
CLAIM_EXPIRY_DAYS = 30           # claims older than this without re-verification get flagged
CLAIM_MAX_AGE_DAYS = 90          # claims older than this are auto-expired

# --- Warmup Mode ---
WARMUP_OUTPUTS = 5               # first N outputs in a new domain require manual review
WARMUP_APPROVAL_REQUIRED = True  # if True, warmup outputs need --approve before entering KB

# --- Prompt Drift ---
MAX_EVOLUTION_HISTORY = 10       # past evolution entries to show meta-analyst (was 5)
IMMUTABLE_STRATEGY_CLAUSES = [   # these rules can never be removed from strategies
    "Always cite sources with URLs",
    "Flag uncertainty and distinguish fact from speculation",
    "Include TODAY'S DATE awareness", 
]
DRIFT_WARNING_THRESHOLD = 0.6    # warn when strategy has <60% overlap with v001

# --- Multi-Researcher Consensus ---
CONSENSUS_ENABLED = False       # disabled by default — run N researchers in parallel
CONSENSUS_RESEARCHERS = 3       # number of parallel researchers (max 5)

# --- Orchestrator Tuning ---
ORCH_MAX_PER_DOMAIN = 5          # max rounds per domain in orchestrate mode
ORCH_SCORE_PLATEAU_WINDOW = 5    # check last N scores for plateau detection
ORCH_SCORE_PLATEAU_RANGE = 0.5   # scores within ±this are considered plateau
ORCH_TIME_DECAY_DAYS = 7         # domains not researched in N days get priority boost
ORCH_TIME_DECAY_BOOST = 15       # priority boost for stale domains
AUTO_DEDUP_RETRIES = 2           # retry question generation when dedup skips

# --- Memory Hygiene ---
MAX_OUTPUTS_PER_DOMAIN = 100          # archive overflow beyond this
ARCHIVE_REJECTED_AFTER_DAYS = 7       # archive rejected outputs after N days
ARCHIVE_SCORE_THRESHOLD = 5           # archive outputs below this score after N days
AUTO_PRUNE_ENABLED = True             # auto-prune after every Nth accepted output
AUTO_PRUNE_EVERY_N = 10               # prune frequency (every N accepted outputs)

# --- Dashboard API ---
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "")  # empty = no auth
DASHBOARD_CORS_ORIGINS = os.environ.get("DASHBOARD_CORS_ORIGINS", "*")

# --- Global Rate Limiter ---
RATE_LIMIT_SEARCHES_PER_MINUTE = 15   # max web searches per minute
RATE_LIMIT_FETCHES_PER_MINUTE = 20    # max page fetches per minute

# ============================================================
# Agent Hands — Execution Layer
# ============================================================

# Model assignments for execution agents
MODELS.update({
    "planner": PREMIUM_MODEL,                    # strong — plan decomposition needs reasoning
    "executor": FAST_MODEL,                      # fast — builds full apps, needs tool-use capability
    "exec_validator": PREMIUM_MODEL,             # strong — quality judgment is sacred
    "exec_meta_analyst": PREMIUM_MODEL,          # strong — pattern extraction
})

# --- Execution Quality Gate ---
EXEC_QUALITY_THRESHOLD = 7      # higher bar than research — execution must be reliable
EXEC_MAX_RETRIES = 2            # retries with validator feedback before giving up
EXEC_MAX_STEPS = 20             # max steps in a single execution plan
EXEC_STEP_TIMEOUT = 120         # seconds before a single execution step times out

# --- Execution Memory ---
EXEC_MEMORY_DIR = os.path.join(os.path.dirname(__file__), "exec_memory")

# --- Execution Strategy Evolution ---
EXEC_EVOLVE_EVERY_N = 3        # evolve execution strategy every N completed tasks
EXEC_TRIAL_PERIOD = 3          # execution outputs under trial before evaluation
EXEC_SAFETY_DROP = 0.20        # block if exec strategy drops >20%

# --- Execution Safety ---
EXEC_SANDBOX_MODE = True        # run commands in restricted mode by default
EXEC_ALLOWED_COMMANDS = [       # whitelist of allowed shell commands
    "python", "python3", "pip", "pip3", "node", "npm", "npx",
    "git", "curl", "wget", "cat", "ls", "mkdir", "cp", "mv", "rm",
    "echo", "touch", "head", "tail", "grep", "find", "wc",
    "pytest", "eslint", "prettier", "tsc", "docker",
    "cd", "pwd", "vercel", "chmod", "sed", "awk", "sort", "uniq",
    "tar", "zip", "unzip", "env", "which", "tree",
]
EXEC_BLOCKED_PATTERNS = [       # patterns that are NEVER allowed in commands
    "rm -rf /", "rm -rf /*", ":(){ :|:& };:",  # fork bomb
    "dd if=", "mkfs", "fdisk",                   # disk destruction
    "sudo", "su ",                                # privilege escalation
    "> /dev/sd", "chmod 777",                     # dangerous ops
]
EXEC_MAX_FILE_SIZE = 100_000    # max bytes for a single file write (100KB)
EXEC_ALLOWED_DIRS = None        # if set, restrict file writes to these dirs only (list of paths)
