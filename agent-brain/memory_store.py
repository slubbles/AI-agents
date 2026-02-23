"""
Memory Store
Handles reading/writing scored research outputs to disk.
Includes relevance retrieval for memory-informed research.
"""

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from config import MEMORY_DIR

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
    
    # Quality score (normalized to 0-1)
    quality = output.get("overall_score", 0) / 10.0
    
    # Recency (outputs from today = 1.0, decays over time)
    try:
        ts = datetime.fromisoformat(output.get("timestamp", "2000-01-01"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - ts).days
        recency = max(0.0, 1.0 - (age_days / 90.0))  # Decays to 0 over 90 days
    except (ValueError, TypeError):
        recency = 0.5
    
    return (keyword_score * 0.60) + (quality * 0.25) + (recency * 0.15)


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
    
    # Only include accepted outputs
    accepted = [o for o in outputs if o.get("verdict") == "accept"]
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
