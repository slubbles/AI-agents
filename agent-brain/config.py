"""
Agent Brain — Configuration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

# --- LLM Provider ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model assignments per agent role
# Critic gets the strongest model — it's the quality signal, don't cut corners.
# Researcher uses a cheap model — it just searches and compiles.
# Meta-analyst needs reasoning for pattern extraction — uses Sonnet.
MODELS = {
    "researcher": "claude-haiku-4-5-20251001",    # cheap — searches + compiles
    "critic": "claude-sonnet-4-20250514",         # strong — quality is sacred
    "meta_analyst": "claude-sonnet-4-20250514",   # strong — pattern extraction needs reasoning
    "synthesizer": "claude-sonnet-4-20250514",    # strong — contradiction detection + integration
    "cross_domain": "claude-sonnet-4-20250514",   # strong — principle abstraction
    "question_generator": "claude-haiku-4-5-20251001",  # cheap — routing/synthesis task
    "verifier": "claude-haiku-4-5-20251001",      # cheap — web search + fact checking
}

# --- Quality Gate ---
QUALITY_THRESHOLD = 6  # minimum score (1-10) to accept output
MAX_RETRIES = 2  # how many times researcher retries after rejection

# --- Memory ---
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory")
STRATEGY_DIR = os.path.join(os.path.dirname(__file__), "strategies")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
DB_PATH = os.path.join(os.path.dirname(__file__), "logs", "agent_brain.db")

# --- Budget ---
# Estimated cost per 1K tokens (input/output) for tracking
# These are approximations used for budget awareness, not billing
COST_PER_1K = {
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
}
DAILY_BUDGET_USD = 5.00  # Hard stop — refuse to run if daily spend exceeds this

# --- Loop ---
DEFAULT_DOMAIN = "general"

# --- Research ---
MAX_TOOL_ROUNDS = 5   # max rounds of tool-use before forcing output
MAX_SEARCHES = 10     # hard cap on total web searches per run

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
MIN_OUTPUTS_FOR_TRANSFER = 5    # min outputs for a domain to be a transfer source
MIN_AVG_SCORE_FOR_TRANSFER = 5.5

# --- Multi-Researcher Consensus ---
CONSENSUS_ENABLED = False       # disabled by default — run N researchers in parallel
CONSENSUS_RESEARCHERS = 3       # number of parallel researchers (max 5)

# --- Memory Hygiene ---
MAX_OUTPUTS_PER_DOMAIN = 100          # archive overflow beyond this
ARCHIVE_REJECTED_AFTER_DAYS = 7       # archive rejected outputs after N days
ARCHIVE_SCORE_THRESHOLD = 5           # archive outputs below this score after N days
