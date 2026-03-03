"""
Protocol — Typed message classes for Brain ↔ Cortex ↔ Hands communication.

All messages are simple dataclasses that serialize to/from JSON dicts.
No over-engineering — these are structured dicts with validation, not a message bus.

Usage:
    from protocol import BuildTask, ResearchComplete, PhaseComplete

    task = BuildTask(
        domain="productized-services",
        goal="Build a landing page for LaunchReady",
        brief="...",
        constraints={"tech_stack": ["nextjs", "tailwind"]},
        budget_cap=0.50,
    )
    
    # Serialize
    data = task.to_dict()
    
    # Deserialize
    task2 = BuildTask.from_dict(data)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    """Current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()


# ── Brain Messages ─────────────────────────────────────────────────────────

@dataclass
class ResearchRequest:
    """Request from Cortex → Brain to research a topic."""
    domain: str
    question: str
    depth: str = "standard"       # "quick" | "standard" | "deep"
    urgency: str = "medium"       # "critical" | "high" | "medium" | "low"
    build_mode: bool = False      # True = research for pre-build intelligence
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ResearchRequest:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ResearchComplete:
    """Response from Brain → Cortex: research findings are ready."""
    domain: str
    question: str
    findings: dict                # The full research output (researcher JSON)
    confidence: str = "medium"    # "high" | "medium" | "low"
    score: float = 0.0            # Critic score (1-10)
    accepted: bool = False        # Whether it passed quality gate
    cost: float = 0.0             # Cost of this research cycle in USD
    knowledge_gaps: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ResearchComplete:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Hands Messages ─────────────────────────────────────────────────────────

@dataclass
class BuildTask:
    """
    Instruction from Cortex → Hands to build something.
    
    Contains everything Hands needs: goal, brief from research,
    constraints, and budget cap.
    """
    domain: str
    goal: str                     # Human-readable goal ("Build a landing page for X")
    brief: str                    # Research-derived brief (user persona, pain, features)
    constraints: dict = field(default_factory=dict)  # tech_stack, design, etc.
    budget_cap: float = 0.50      # Max cost for this execution in USD
    priority: str = "high"        # "critical" | "high" | "medium" | "low"
    source_research_id: str = ""  # Link back to the research output that informed this
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> BuildTask:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_sync_task(self) -> dict:
        """Convert to the format expected by sync.create_task()."""
        return {
            "title": self.goal,
            "description": self.brief,
            "source_domain": self.domain,
            "task_type": "build",
            "priority": self.priority,
            "source_output_id": self.source_research_id,
            "metadata": {
                **self.metadata,
                "constraints": self.constraints,
                "budget_cap": self.budget_cap,
            },
        }


@dataclass
class PhaseComplete:
    """Notification from Hands → Cortex: a build phase finished."""
    domain: str
    task_id: str
    phase: str                    # "scaffold" | "backend" | "frontend" | "integration" | "validation" | "deploy"
    phase_number: int             # 0-6
    success: bool = True
    artifact_path: str = ""       # Path to the artifact produced
    cost: float = 0.0             # Cost of this phase in USD
    error: str = ""               # Error message if failed
    step_count: int = 0           # How many steps this phase took
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PhaseComplete:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContextNeeded:
    """
    Request from Hands → Cortex: need more information mid-build.
    
    Cortex routes this to Brain's knowledge base and returns context.
    """
    domain: str
    task_id: str
    phase: str                    # Current build phase
    question: str                 # What Hands needs to know
    context_type: str = "general" # "copy" | "design" | "technical" | "user_research" | "general"
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ContextNeeded:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ContextResponse:
    """Response from Cortex → Hands with the requested context."""
    domain: str
    task_id: str
    question: str                 # Echo back the question
    context: str                  # The knowledge base context to inject
    source: str = "knowledge_base"  # "knowledge_base" | "research" | "strategy"
    confidence: str = "medium"
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ContextResponse:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BuildComplete:
    """Notification from Hands → Cortex: build finished successfully."""
    domain: str
    task_id: str
    url: str = ""                 # Live URL (Vercel)
    test_results: dict = field(default_factory=dict)  # Build pass/fail, lint, etc.
    total_cost: float = 0.0       # Total cost of the entire build
    total_steps: int = 0          # Total steps executed
    artifacts: list[str] = field(default_factory=list)  # Files created
    phases_completed: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> BuildComplete:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BuildFailed:
    """Notification from Hands → Cortex: build failed."""
    domain: str
    task_id: str
    phase: str                    # Which phase failed
    reason: str                   # Why it failed
    retry_count: int = 0          # How many times this was retried
    cost_so_far: float = 0.0      # How much was spent before failure
    recoverable: bool = True      # Whether a retry might help
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> BuildFailed:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TaskComplete:
    """
    Summary message for Telegram / external reporting.
    
    Sent after a full pipeline run (research → build → deploy).
    """
    domain: str
    task_id: str
    result: str                   # "success" | "partial" | "failed"
    url: str = ""                 # Live URL if deployed
    cost: float = 0.0             # Total pipeline cost
    confidence: str = "medium"
    summary: str = ""             # Human-readable summary for Telegram
    research_score: float = 0.0   # Brain's research quality
    build_score: float = 0.0      # Hands' build quality (from validator)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TaskComplete:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_telegram_message(self) -> str:
        """Format for Telegram notification."""
        icons = {"success": "✅", "partial": "⚠️", "failed": "❌"}
        icon = icons.get(self.result, "📋")
        
        lines = [
            f"{icon} **Pipeline Complete: {self.domain}**",
            f"Result: {self.result.upper()}",
        ]
        if self.url:
            lines.append(f"🔗 URL: {self.url}")
        if self.summary:
            lines.append(f"📝 {self.summary}")
        lines.append(f"💰 Cost: ${self.cost:.4f}")
        if self.research_score > 0:
            lines.append(f"🔬 Research: {self.research_score}/10")
        if self.build_score > 0:
            lines.append(f"🔨 Build: {self.build_score}/10")
        
        return "\n".join(lines)


# ── Journal Entry ──────────────────────────────────────────────────────────

@dataclass
class JournalEntry:
    """
    An entry in cortex_journal.jsonl — tracks every significant event
    in the pipeline for observability and debugging.
    """
    event: str                    # "research_start" | "research_complete" | "build_start" | 
                                  # "phase_complete" | "context_request" | "build_complete" |
                                  # "build_failed" | "cost_alert" | "intervention"
    domain: str
    task_id: str = ""
    details: dict = field(default_factory=dict)
    cost_so_far: float = 0.0
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> JournalEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_jsonl(self) -> str:
        """Format for appending to cortex_journal.jsonl."""
        return json.dumps(self.to_dict())
