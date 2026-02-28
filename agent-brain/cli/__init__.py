"""
CLI command modules — extracted from main.py for maintainability.

Each module handles a related group of CLI commands:
- vault: Credential vault operations
- browser_cmd: Stealth browser fetch/test
- project: Project orchestrator commands
- deploy_cmd: VPS deployment commands
- tools_cmd: Crawl, fetch, RAG, MCP commands
- strategy: Strategy management (status, approve, reject, diff, rollback, audit)
- knowledge: Knowledge base, synthesis, graph
- infrastructure: Dashboard, export, migrate, alerts, health, daemon, seeds, budget
- research: Auto mode, orchestrate, next questions
- execution: Agent Hands execution commands
"""

import sys
import os

# Ensure parent package is importable (agent-brain/ on sys.path)
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
