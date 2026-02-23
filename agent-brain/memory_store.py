"""
Memory Store
Handles reading/writing scored research outputs to disk.
Includes relevance retrieval for memory-informed research.
Includes memory hygiene: pruning rejected outputs, archiving old data, domain caps.
"""

import json
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from config import MEMORY_DIR, QUALITY_THRESHOLD, MAX_OUTPUTS_PER_DOMAIN, ARCHIVE_REJECTED_AFTER_DAYS, ARCHIVE_SCORE_THRESHOLD

# Stop words to exclude from keyword matching
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "about", "what",
    "which", "who", "whom", "this", "that", "these", "those", "it", "its",
}


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

    score = critique.get("overall_score", 0)
    accepted = score >= QUALITY_THRESHOLD

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "question": question,
        "attempt": attempt,
        "strategy_version": strategy_version,
        "research": research,
        "critique": critique,
        "overall_score": score,
        "accepted": accepted,
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
        "accepted": sum(1 for o in outputs if o.get("accepted", o.get("verdict") == "accept")),
        "rejected": sum(1 for o in outputs if not o.get("accepted", o.get("verdict") == "accept")),
    }


def _tokenize(text: str) -> list[str]:
    """Extract meaningful tokens from text (lowercase, no stop words, no short tokens)."""
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 2]


def _relevance_score(query_tokens: list[str], output: dict) -> float:
    """
    Score how relevant a stored output is to a new query.
    
    Combines:
    - Keyword overlap between query and output question/findings/insights (60%)
    - Output quality score (25%) — higher-quality outputs preferred
    - Recency bonus (15%) — more recent outputs slightly preferred
    """
    # Build output text for matching
    parts = [
        output.get("question", ""),
        output.get("research", {}).get("summary", ""),
    ]
    for f in output.get("research", {}).get("findings", []):
        parts.append(f.get("claim", ""))
    for insight in output.get("research", {}).get("key_insights", []):
        parts.append(insight)
    
    output_text = " ".join(parts)
    output_tokens = _tokenize(output_text)
    
    if not output_tokens or not query_tokens:
        return 0.0
    
    # Keyword overlap (Jaccard-like but weighted by frequency)
    query_set = set(query_tokens)
    output_counter = Counter(output_tokens)
    overlap = sum(output_counter[t] for t in query_set if t in output_counter)
    max_possible = max(len(query_tokens), 1)
    keyword_score = min(overlap / max_possible, 1.0)
    
    # Quality score (normalized to 0-1, with penalty for rejected outputs)
    quality = output.get("overall_score", 0) / 10.0
    if not output.get("accepted", output.get("verdict") == "accept"):
        quality *= 0.3  # Heavy penalty — rejected outputs are much less useful
    
    # Recency (outputs from today = 1.0, decays over time)
    try:
        ts = datetime.fromisoformat(output.get("timestamp", "2000-01-01"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - ts).days
        recency = max(0.0, 1.0 - (age_days / 90.0))  # Decays to 0 over 90 days
    except (ValueError, TypeError):
        recency = 0.5
    
    return (keyword_score * 0.50) + (quality * 0.35) + (recency * 0.15)


def retrieve_relevant(domain: str, question: str, max_results: int = 5, min_score: float = 4.0) -> list[dict]:
    """
    Retrieve the most relevant past findings for a new research question.
    
    Only returns accepted outputs (score >= min_score) to avoid feeding the
    researcher bad information from its own rejected outputs.
    
    Returns a list of condensed output summaries, ranked by relevance.
    """
    outputs = load_outputs(domain, min_score=min_score)
    if not outputs:
        return []
    
    # Only include accepted outputs (use 'accepted' field with verdict fallback)
    accepted = [o for o in outputs if o.get("accepted", o.get("verdict") == "accept")]
    if not accepted:
        return []
    
    query_tokens = _tokenize(question)
    
    # Score all outputs
    scored = []
    for output in accepted:
        rel_score = _relevance_score(query_tokens, output)
        if rel_score > 0.05:  # Minimum relevance threshold
            scored.append((rel_score, output))
    
    # Sort by relevance (descending)
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Return condensed summaries
    results = []
    for rel_score, output in scored[:max_results]:
        research = output.get("research", {})
        results.append({
            "question": output.get("question", ""),
            "summary": research.get("summary", ""),
            "key_insights": research.get("key_insights", []),
            "findings": [
                {"claim": f.get("claim", ""), "confidence": f.get("confidence", "low")}
                for f in research.get("findings", [])[:5]  # Top 5 findings only
            ],
            "knowledge_gaps": research.get("knowledge_gaps", []),
            "score": output.get("overall_score", 0),
            "timestamp": output.get("timestamp", ""),
            "_relevance": round(rel_score, 3),
        })
    
    return results


def get_knowledge_base_path(domain: str) -> str:
    """Return path to the synthesized knowledge base for a domain."""
    return os.path.join(MEMORY_DIR, domain, "_knowledge_base.json")


def load_knowledge_base(domain: str) -> dict | None:
    """Load the synthesized knowledge base for a domain, if it exists."""
    path = get_knowledge_base_path(domain)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save_knowledge_base(domain: str, knowledge_base: dict) -> str:
    """Save a synthesized knowledge base for a domain."""
    path = get_knowledge_base_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(knowledge_base, f, indent=2)
    return path


# ============================================================
# Memory Hygiene — Pruning, Archival, Domain Caps
# ============================================================

# MAX_OUTPUTS_PER_DOMAIN, ARCHIVE_REJECTED_AFTER_DAYS, ARCHIVE_SCORE_THRESHOLD imported from config


def _get_archive_dir(domain: str) -> str:
    """Return the archive directory path for a domain."""
    return os.path.join(MEMORY_DIR, domain, "_archive")


def _get_output_filepath(domain: str, filename: str) -> str:
    """Return full path for an output file."""
    return os.path.join(MEMORY_DIR, domain, filename)


def _output_age_days(record: dict) -> int:
    """Calculate the age of an output in days."""
    try:
        ts = datetime.fromisoformat(record.get("timestamp", "2000-01-01"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).days
    except (ValueError, TypeError):
        return 999


def prune_domain(domain: str, dry_run: bool = False) -> dict:
    """
    Run memory hygiene on a domain:
    
    1. Archive rejected outputs older than ARCHIVE_REJECTED_AFTER_DAYS
    2. Archive low-score outputs when domain exceeds MAX_OUTPUTS_PER_DOMAIN
    3. Never archive the knowledge base or other underscore-prefixed files
    
    Args:
        domain: The domain to prune
        dry_run: If True, report what would be done without doing it
    
    Returns:
        Dict with statistics about what was pruned/archived
    """
    domain_dir = os.path.join(MEMORY_DIR, domain)
    if not os.path.exists(domain_dir):
        return {"archived": 0, "kept": 0, "reason": "domain not found"}

    archive_dir = _get_archive_dir(domain)
    
    # Load all output files (skip underscore-prefixed files like _knowledge_base.json)
    output_files = []
    for filename in sorted(os.listdir(domain_dir)):
        if not filename.endswith(".json") or filename.startswith("_"):
            continue
        filepath = os.path.join(domain_dir, filename)
        try:
            with open(filepath) as f:
                record = json.load(f)
            record["_filename"] = filename
            record["_filepath"] = filepath
            output_files.append(record)
        except (json.JSONDecodeError, IOError):
            continue

    if not output_files:
        return {"archived": 0, "kept": len(output_files), "reason": "no outputs"}

    to_archive = []
    to_keep = []

    for record in output_files:
        age = _output_age_days(record)
        score = record.get("overall_score", 0)
        verdict = record.get("verdict", "unknown")

        # Rule 1: Archive old rejected outputs
        if verdict == "reject" and age >= ARCHIVE_REJECTED_AFTER_DAYS:
            to_archive.append((record, "rejected + old"))
            continue

        # Rule 2: Archive old low-score outputs (even if "accepted" at threshold)
        if score < ARCHIVE_SCORE_THRESHOLD and age >= ARCHIVE_REJECTED_AFTER_DAYS:
            to_archive.append((record, f"low score ({score}) + old"))
            continue

        to_keep.append(record)

    # Rule 3: If still over cap, archive lowest-scored outputs (keep newest)
    if len(to_keep) > MAX_OUTPUTS_PER_DOMAIN:
        # Sort by score (ascending), then age (oldest first) — archive the worst+oldest
        to_keep.sort(key=lambda r: (r.get("overall_score", 0), -_output_age_days(r)))
        overflow = len(to_keep) - MAX_OUTPUTS_PER_DOMAIN
        for record in to_keep[:overflow]:
            to_archive.append((record, "domain cap exceeded"))
        to_keep = to_keep[overflow:]

    # Execute archival
    if not dry_run and to_archive:
        os.makedirs(archive_dir, exist_ok=True)

    archived_details = []
    for record, reason in to_archive:
        filename = record["_filename"]
        src = record["_filepath"]
        dst = os.path.join(archive_dir, filename)

        archived_details.append({
            "filename": filename,
            "score": record.get("overall_score", 0),
            "verdict": record.get("verdict", "?"),
            "age_days": _output_age_days(record),
            "reason": reason,
        })

        if not dry_run:
            shutil.move(src, dst)

    return {
        "archived": len(to_archive),
        "kept": len(to_keep),
        "total_before": len(output_files),
        "details": archived_details,
        "dry_run": dry_run,
    }


def restore_from_archive(domain: str, filename: str) -> bool:
    """Restore a specific output from archive back to active memory."""
    archive_dir = _get_archive_dir(domain)
    src = os.path.join(archive_dir, filename)
    dst = os.path.join(MEMORY_DIR, domain, filename)

    if not os.path.exists(src):
        return False

    shutil.move(src, dst)
    return True


def get_archive_stats(domain: str) -> dict:
    """Get statistics about archived outputs for a domain."""
    archive_dir = _get_archive_dir(domain)
    if not os.path.exists(archive_dir):
        return {"count": 0, "files": []}

    files = []
    for filename in sorted(os.listdir(archive_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(archive_dir, filename)
        try:
            with open(filepath) as f:
                record = json.load(f)
            files.append({
                "filename": filename,
                "score": record.get("overall_score", 0),
                "verdict": record.get("verdict", "?"),
                "question": record.get("question", "?")[:60],
            })
        except (json.JSONDecodeError, IOError):
            continue

    return {"count": len(files), "files": files}
