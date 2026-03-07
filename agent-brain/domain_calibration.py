"""
Domain Calibration — Cross-Domain Score Consistency

Solves the problem: a 7 in "crypto" and a 7 in "quantum physics" should
mean comparable quality, but domain difficulty makes raw scores unreliable
across domains.

This module:
1. Tracks per-domain score distributions (mean, stddev, count)
2. Computes a domain difficulty signal
3. Provides calibration context for the critic prompt
4. Offers a normalized score for cross-domain comparison

The calibration is descriptive, not prescriptive — it informs the critic
about the domain's baseline so it can judge relative quality, but does NOT
alter scores after the fact. The critic makes better judgments when it
knows the landscape.
"""

import json
import math
import os
from datetime import datetime, timezone

from config import MEMORY_DIR, CALIBRATION_ENABLED, CALIBRATION_MIN_OUTPUTS, CALIBRATION_FILE
from memory_store import load_outputs, get_stats
from utils.atomic_write import atomic_json_write


def _load_calibration() -> dict:
    """Load the calibration data file."""
    if not os.path.exists(CALIBRATION_FILE):
        return {"domains": {}, "updated_at": None}
    try:
        with open(CALIBRATION_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"domains": {}, "updated_at": None}


def _save_calibration(data: dict) -> None:
    os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json_write(CALIBRATION_FILE, data)


def update_domain_stats(domain: str) -> dict:
    """
    Recompute score distribution stats for a domain from its outputs.

    Returns the domain's calibration entry.
    """
    outputs = load_outputs(domain, min_score=0)
    if not outputs:
        return {}

    scores = [o.get("overall_score", 0) for o in outputs if o.get("overall_score", 0) > 0]
    if len(scores) < 3:
        return {}

    accepted_scores = [o.get("overall_score", 0) for o in outputs
                       if o.get("accepted", o.get("verdict") == "accept")]
    rejected_scores = [o.get("overall_score", 0) for o in outputs
                       if not o.get("accepted", o.get("verdict") == "accept")]

    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    stddev = math.sqrt(variance)

    accept_rate = len(accepted_scores) / len(scores) if scores else 0

    dim_stats = {}
    for dim in ("accuracy", "depth", "completeness", "specificity", "intellectual_honesty"):
        dim_scores = []
        for o in outputs:
            critique = o.get("critique", {})
            scores_dict = critique.get("scores", {})
            if dim in scores_dict:
                dim_scores.append(scores_dict[dim])
        if dim_scores:
            dim_stats[dim] = {
                "mean": round(sum(dim_scores) / len(dim_scores), 2),
                "min": min(dim_scores),
                "max": max(dim_scores),
            }

    entry = {
        "count": len(scores),
        "mean": round(mean, 2),
        "stddev": round(stddev, 2),
        "median": round(sorted(scores)[len(scores) // 2] if len(scores) % 2 == 1
                       else (sorted(scores)[len(scores) // 2 - 1] + sorted(scores)[len(scores) // 2]) / 2, 1),
        "min": min(scores),
        "max": max(scores),
        "accept_rate": round(accept_rate, 3),
        "accepted_count": len(accepted_scores),
        "rejected_count": len(rejected_scores),
        "dimension_stats": dim_stats,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    cal = _load_calibration()
    cal["domains"][domain] = entry
    _save_calibration(cal)

    return entry


def get_domain_difficulty(domain: str) -> dict:
    """
    Compute a difficulty signal for a domain.

    Difficulty is inferred from:
    - Accept rate (lower = harder)
    - Score distribution (lower mean = harder)
    - Score variance (higher variance = less predictable)

    Returns:
        {difficulty: "easy"|"medium"|"hard"|"unknown", stats: {...}}
    """
    cal = _load_calibration()
    entry = cal.get("domains", {}).get(domain, {})

    if not entry or entry.get("count", 0) < CALIBRATION_MIN_OUTPUTS:
        return {"difficulty": "unknown", "reason": "insufficient data"}

    mean = entry.get("mean", 5)
    accept_rate = entry.get("accept_rate", 0.5)
    stddev = entry.get("stddev", 1.5)

    if accept_rate >= 0.75 and mean >= 7.0:
        difficulty = "easy"
    elif accept_rate <= 0.40 or mean < 5.5:
        difficulty = "hard"
    else:
        difficulty = "medium"

    return {
        "difficulty": difficulty,
        "mean_score": mean,
        "accept_rate": accept_rate,
        "stddev": stddev,
        "count": entry.get("count", 0),
    }


def get_calibration_context(domain: str) -> str:
    """
    Build a text block for the critic prompt that provides cross-domain context.

    This helps the critic understand where this domain sits relative to others,
    enabling more calibrated scoring. A tough domain getting consistently lower
    scores doesn't mean the critic should be lenient — it means the critic should
    recognize and reward relative excellence.
    """
    if not CALIBRATION_ENABLED:
        return ""

    cal = _load_calibration()
    domain_entry = cal.get("domains", {}).get(domain, {})

    if not domain_entry or domain_entry.get("count", 0) < CALIBRATION_MIN_OUTPUTS:
        return ""

    all_domains = cal.get("domains", {})
    global_scores = []
    for d, entry in all_domains.items():
        if entry.get("count", 0) >= CALIBRATION_MIN_OUTPUTS:
            global_scores.append(entry.get("mean", 0))

    if not global_scores:
        return ""

    global_mean = sum(global_scores) / len(global_scores)
    domain_mean = domain_entry.get("mean", 0)
    domain_accept_rate = domain_entry.get("accept_rate", 0)
    difficulty_info = get_domain_difficulty(domain)
    difficulty = difficulty_info.get("difficulty", "unknown")

    weakest_dim = ""
    dim_stats = domain_entry.get("dimension_stats", {})
    if dim_stats:
        weakest = min(dim_stats.items(), key=lambda x: x[1].get("mean", 10))
        weakest_dim = f"Historically weakest dimension: {weakest[0]} (avg {weakest[1]['mean']})."

    context = (
        f"\nDOMAIN CALIBRATION ({domain}):\n"
        f"- Domain difficulty: {difficulty} (accept rate {domain_accept_rate:.0%}, "
        f"avg score {domain_mean:.1f})\n"
        f"- System-wide average across all domains: {global_mean:.1f}\n"
        f"- {weakest_dim}\n"
        f"- Score relative to context: do NOT inflate scores for difficult domains. "
        f"Maintain the same absolute standard. A 7 means the same quality everywhere. "
        f"But recognize genuine improvement relative to past performance.\n"
    )
    return context


def get_normalized_score(raw_score: float, domain: str) -> float:
    """
    Normalize a raw score relative to domain difficulty for cross-domain comparison.

    Uses z-score normalization mapped back to 1-10 scale.
    Only used for analytics/comparison — the stored score is always raw.
    """
    cal = _load_calibration()
    entry = cal.get("domains", {}).get(domain, {})

    if not entry or entry.get("count", 0) < CALIBRATION_MIN_OUTPUTS:
        return raw_score

    mean = entry.get("mean", 5)
    stddev = entry.get("stddev", 1.5)

    if stddev < 0.1:
        return raw_score

    z = (raw_score - mean) / stddev
    normalized = 5 + (z * 1.5)
    return round(max(1, min(10, normalized)), 2)


def update_all_domains() -> dict:
    """Recompute calibration stats for all domains with outputs."""
    if not os.path.exists(MEMORY_DIR):
        return {}

    updated = {}
    for name in sorted(os.listdir(MEMORY_DIR)):
        domain_dir = os.path.join(MEMORY_DIR, name)
        if not os.path.isdir(domain_dir) or name.startswith("_"):
            continue
        stats = get_stats(name)
        if stats.get("count", 0) >= 3:
            entry = update_domain_stats(name)
            if entry:
                updated[name] = entry

    return updated
