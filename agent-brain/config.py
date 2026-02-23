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
}

# --- Quality Gate ---
QUALITY_THRESHOLD = 6  # minimum score (1-10) to accept output
MAX_RETRIES = 2  # how many times researcher retries after rejection

# --- Memory ---
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory")
STRATEGY_DIR = os.path.join(os.path.dirname(__file__), "strategies")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

# --- Loop ---
DEFAULT_DOMAIN = "general"
