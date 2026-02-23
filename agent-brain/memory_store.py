"""
Memory Store
Handles reading/writing scored research outputs to disk.
"""

import json
import os
from datetime import datetime, timezone
from config import MEMORY_DIR


def save_output(domain: str, question: str, research: dict, critique: dict, attempt: int, strategy_version: str) -> str:
    """
    Save a scored research output to the memory store.
    
    Returns:
        Path to the saved file
    """
    domain_dir = os.path.join(MEMORY_DIR, domain)
    os.makedirs(domain_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_score{critique.get('overall_score', 0):.0f}.json"
    filepath = os.path.join(domain_dir, filename)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "question": question,
        "attempt": attempt,
        "strategy_version": strategy_version,
        "research": research,
        "critique": critique,
        "overall_score": critique.get("overall_score", 0),
        "verdict": critique.get("verdict", "unknown"),
    }

    with open(filepath, "w") as f:
        json.dump(record, f, indent=2)

    return filepath


def load_outputs(domain: str, min_score: float = 0) -> list[dict]:
    """
    Load all stored outputs for a domain, optionally filtered by minimum score.
    """
    domain_dir = os.path.join(MEMORY_DIR, domain)
    if not os.path.exists(domain_dir):
        return []

    outputs = []
    for filename in sorted(os.listdir(domain_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(domain_dir, filename)
        with open(filepath) as f:
            record = json.load(f)
        if record.get("overall_score", 0) >= min_score:
            outputs.append(record)

    return outputs


def get_stats(domain: str) -> dict:
    """
    Get aggregate stats for a domain's memory.
    """
    outputs = load_outputs(domain)
    if not outputs:
        return {"count": 0, "avg_score": 0, "accepted": 0, "rejected": 0}

    scores = [o.get("overall_score", 0) for o in outputs]
    return {
        "count": len(outputs),
        "avg_score": sum(scores) / len(scores),
        "accepted": sum(1 for o in outputs if o.get("verdict") == "accept"),
        "rejected": sum(1 for o in outputs if o.get("verdict") == "reject"),
    }
