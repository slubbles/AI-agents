"""
Memory Store
Handles reading/writing scored research outputs to disk.
Includes relevance retrieval for memory-informed research.
Includes memory hygiene: pruning rejected outputs, archiving old data, domain caps.
Includes persistent TF-IDF cache for fast retrieval without per-call rebuilds.
"""

import json
import os
import pickle
import hashlib
import re
import shutil
from collections import Counter
from datetime import datetime, timezone

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from config import MEMORY_DIR, QUALITY_THRESHOLD, MAX_OUTPUTS_PER_DOMAIN, ARCHIVE_REJECTED_AFTER_DAYS, ARCHIVE_SCORE_THRESHOLD, CLAIM_EXPIRY_DAYS, CLAIM_MAX_AGE_DAYS

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


# ============================================================
# Persistent TF-IDF Cache
# ============================================================

# In-memory cache: {domain: {"vectorizer": obj, "matrix": sparse, "fingerprint": str, "outputs": list}}
_tfidf_cache: dict[str, dict] = {}


def _cache_dir(domain: str) -> str:
    """Directory for storing TF-IDF cache files."""
    return os.path.join(MEMORY_DIR, domain, "_cache")


def _compute_fingerprint(accepted_outputs: list[dict]) -> str:
    """
    Compute a fingerprint for a set of outputs to detect cache invalidation.
    Uses count + hash of timestamps (fast, avoids reading full content).
    """
    if not accepted_outputs:
        return "empty"
    timestamps = sorted(o.get("timestamp", "") for o in accepted_outputs)
    content = f"{len(timestamps)}:{','.join(timestamps)}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def _load_tfidf_cache(domain: str, fingerprint: str) -> dict | None:
    """Load cached TF-IDF vectorizer + matrix from disk if fingerprint matches."""
    cache_path = os.path.join(_cache_dir(domain), "tfidf_cache.pkl")
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        if cached.get("fingerprint") == fingerprint:
            return cached
    except Exception:
        pass
    return None


def _save_tfidf_cache(domain: str, vectorizer, matrix, fingerprint: str):
    """Save TF-IDF vectorizer + matrix to disk."""
    cache_d = _cache_dir(domain)
    os.makedirs(cache_d, exist_ok=True)
    cache_path = os.path.join(cache_d, "tfidf_cache.pkl")
    try:
        with open(cache_path, "wb") as f:
            pickle.dump({
                "vectorizer": vectorizer,
                "matrix": matrix,
                "fingerprint": fingerprint,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }, f)
    except Exception:
        pass  # Cache write failure is non-fatal


def invalidate_tfidf_cache(domain: str):
    """Invalidate TF-IDF cache for a domain (call after new outputs are added)."""
    _tfidf_cache.pop(domain, None)
    cache_path = os.path.join(_cache_dir(domain), "tfidf_cache.pkl")
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
        except OSError:
            pass


def save_output(domain: str, question: str, research: dict, critique: dict, attempt: int, strategy_version: str) -> str:
    """
    Save a scored research output to the memory store.
    
    Returns:
        Path to the saved file
    """
    domain_dir = os.path.join(MEMORY_DIR, domain)
    os.makedirs(domain_dir, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    # Add full microseconds + process ID to prevent filename collisions
    micro = now.strftime("%f")  # full 6 digits of microseconds
    pid = os.getpid()
    filename = f"{timestamp}_{micro}_{pid}_score{critique.get('overall_score', 0):.0f}.json"
    filepath = os.path.join(domain_dir, filename)

    score = critique.get("overall_score", 0)
    accepted = score >= QUALITY_THRESHOLD

    record = {
        "timestamp": now.isoformat(),
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

    # NOTE: save_output uses non-atomic write intentionally.
    # Individual output files are append-only (never overwritten), so corruption
    # risk is minimal. The file either exists or doesn't.
    # Invalidate TF-IDF cache for this domain (new data available)
    invalidate_tfidf_cache(domain)
    
    # Invalidate output cache
    _invalidate_output_cache(domain)

    # Dual-write to SQLite
    try:
        from db import insert_output
        insert_output(domain, record)
    except Exception as e:
        print(f"[DB] \u26a0 Output write failed (non-blocking): {e}")

    # Auto-index in RAG vector store (non-blocking)
    try:
        from config import RAG_ENABLED
        if RAG_ENABLED:
            from rag.vector_store import index_output
            indexed = index_output(domain, record)
            if indexed > 0:
                print(f"[RAG] Indexed {indexed} claims from output")
    except Exception as e:
        # RAG indexing is non-blocking — don't crash the loop
        pass

    return filepath


# --- Output cache ---
# In-memory cache for load_outputs to avoid repeated disk I/O.
# Keyed by full domain_dir path so different MEMORY_DIR values don't collide.
_output_cache: dict[str, tuple[float, list[dict]]] = {}  # domain_dir -> (timestamp, outputs)
_OUTPUT_CACHE_TTL = 60  # seconds


def _invalidate_output_cache(domain: str) -> None:
    """Remove cached outputs for a domain."""
    domain_dir = os.path.join(MEMORY_DIR, domain)
    _output_cache.pop(domain_dir, None)


def load_outputs(domain: str, min_score: float = 0) -> list[dict]:
    """
    Load all stored outputs for a domain, optionally filtered by minimum score.
    Uses in-memory cache to avoid repeated disk I/O within the same loop run.
    """
    import time
    
    domain_dir = os.path.join(MEMORY_DIR, domain)
    if not os.path.exists(domain_dir):
        return []

    # Check cache keyed by full path (all outputs cached, filter applied after)
    now = time.time()
    if domain_dir in _output_cache:
        cached_time, cached_outputs = _output_cache[domain_dir]
        if now - cached_time < _OUTPUT_CACHE_TTL:
            if min_score > 0:
                return [o for o in cached_outputs if o.get("overall_score", 0) >= min_score]
            return list(cached_outputs)  # Return copy

    outputs = []
    for filename in sorted(os.listdir(domain_dir)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(domain_dir, filename)
        try:
            with open(filepath) as f:
                record = json.load(f)
            outputs.append(record)
        except (json.JSONDecodeError, OSError):
            continue

    # Cache all outputs keyed by full path (filter applied on retrieval)
    _output_cache[domain_dir] = (now, outputs)
    
    if min_score > 0:
        return [o for o in outputs if o.get("overall_score", 0) >= min_score]
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


def _build_output_text(output: dict) -> str:
    """Build a text representation of an output for TF-IDF indexing."""
    parts = [
        output.get("question", ""),
        output.get("research", {}).get("summary", ""),
    ]
    for f in output.get("research", {}).get("findings", []):
        parts.append(f.get("claim", ""))
    for insight in output.get("research", {}).get("key_insights", []):
        parts.append(insight)
    return " ".join(parts)


def _quality_score(output: dict) -> float:
    """Compute quality score (0-1), with penalty for rejected outputs."""
    quality = output.get("overall_score", 0) / 10.0
    if not output.get("accepted", output.get("verdict") == "accept"):
        quality *= 0.3  # Heavy penalty — rejected outputs are much less useful
    return quality


def _recency_score(output: dict) -> float:
    """Compute recency score (0-1), decays to 0 over 90 days."""
    try:
        ts = datetime.fromisoformat(output.get("timestamp", "2000-01-01"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - ts).days
        return max(0.0, 1.0 - (age_days / 90.0))
    except (ValueError, TypeError):
        return 0.5


def _relevance_score(query_tokens: list[str], output: dict) -> float:
    """
    Fallback keyword relevance score for when TF-IDF can't be used (< 2 docs).
    
    Combines:
    - Keyword overlap between query and output question/findings/insights (50%)
    - Output quality score (35%) — higher-quality outputs preferred
    - Recency bonus (15%) — more recent outputs slightly preferred
    """
    output_text = _build_output_text(output)
    output_tokens = _tokenize(output_text)
    
    if not output_tokens or not query_tokens:
        return 0.0
    
    # Keyword overlap (Jaccard-like but weighted by frequency)
    query_set = set(query_tokens)
    output_counter = Counter(output_tokens)
    overlap = sum(output_counter[t] for t in query_set if t in output_counter)
    max_possible = max(len(query_tokens), 1)
    keyword_score = min(overlap / max_possible, 1.0)
    
    quality = _quality_score(output)
    recency = _recency_score(output)
    
    return (keyword_score * 0.50) + (quality * 0.35) + (recency * 0.15)


def retrieve_relevant(domain: str, question: str, max_results: int = 5, min_score: float = 4.0) -> list[dict]:
    """
    Retrieve the most relevant past findings for a new research question.
    
    Uses RAG vector embeddings when available (semantic search), with automatic
    fallback to TF-IDF cosine similarity for backward compatibility.
    
    Only returns accepted outputs (score >= min_score) to avoid feeding the
    researcher bad information from its own rejected outputs.
    
    Returns a list of condensed output summaries, ranked by relevance.
    """
    # Try RAG first — semantic embeddings are much more accurate
    try:
        from config import RAG_ENABLED
        if RAG_ENABLED:
            from rag.retrieval import retrieve_relevant_rag, RAG_ENABLED as _rag_deps
            if _rag_deps:
                from rag.vector_store import get_collection_stats
                stats = get_collection_stats()
                if stats.get("claims_count", 0) > 0:
                    return retrieve_relevant_rag(domain, question, max_results, min_score)
    except Exception:
        pass  # Fall through to TF-IDF
    
    # Fallback: TF-IDF retrieval (original implementation)
    outputs = load_outputs(domain, min_score=min_score)
    if not outputs:
        return []
    
    # Only include accepted outputs (use 'accepted' field with verdict fallback)
    accepted = [o for o in outputs if o.get("accepted", o.get("verdict") == "accept")]
    if not accepted:
        return []
    
    # Build text corpus for TF-IDF
    corpus_texts = [_build_output_text(o) for o in accepted]
    
    # Need at least 2 documents for TF-IDF to work meaningfully
    if len(accepted) < 2:
        # Fallback to keyword matching
        query_tokens = _tokenize(question)
        scored = []
        for output in accepted:
            rel_score = _relevance_score(query_tokens, output)
            if rel_score > 0.05:
                scored.append((rel_score, output))
    else:
        # TF-IDF cosine similarity — with persistent caching
        try:
            fingerprint = _compute_fingerprint(accepted)
            
            # Check in-memory cache first
            cached = _tfidf_cache.get(domain)
            if cached and cached.get("fingerprint") == fingerprint:
                vectorizer = cached["vectorizer"]
                tfidf_matrix = cached["matrix"]
            else:
                # Check disk cache
                disk_cache = _load_tfidf_cache(domain, fingerprint)
                if disk_cache:
                    vectorizer = disk_cache["vectorizer"]
                    tfidf_matrix = disk_cache["matrix"]
                else:
                    # Rebuild from scratch
                    vectorizer = TfidfVectorizer(
                        stop_words='english',
                        max_features=5000,
                        ngram_range=(1, 2),
                        min_df=1,
                        sublinear_tf=True,
                    )
                    tfidf_matrix = vectorizer.fit_transform(corpus_texts)
                    # Save to disk
                    _save_tfidf_cache(domain, vectorizer, tfidf_matrix, fingerprint)
                
                # Update in-memory cache
                _tfidf_cache[domain] = {
                    "vectorizer": vectorizer,
                    "matrix": tfidf_matrix,
                    "fingerprint": fingerprint,
                }
            
            query_vec = vectorizer.transform([question])
            similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()
            
            scored = []
            for i, output in enumerate(accepted):
                semantic = float(similarities[i])
                quality = _quality_score(output)
                recency = _recency_score(output)
                
                # Combined: 55% semantic + 30% quality + 15% recency
                combined = (semantic * 0.55) + (quality * 0.30) + (recency * 0.15)
                if combined > 0.02:
                    scored.append((combined, output))
        except Exception:
            # Fallback to keyword matching on any sklearn error
            query_tokens = _tokenize(question)
            scored = []
            for output in accepted:
                rel_score = _relevance_score(query_tokens, output)
                if rel_score > 0.05:
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
    from utils.atomic_write import atomic_json_write
    path = get_knowledge_base_path(domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_json_write(path, knowledge_base)
    
    # Auto-index KB claims in RAG vector store (non-blocking)
    try:
        from config import RAG_ENABLED
        if RAG_ENABLED:
            from rag.vector_store import index_knowledge_base
            indexed = index_knowledge_base(domain, knowledge_base)
            if indexed > 0:
                print(f"[RAG] Indexed {indexed} KB claims")
    except Exception:
        pass
    
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


# ============================================================
# Claim Expiry — Flag or expire stale KB claims
# ============================================================

def expire_stale_claims(domain: str) -> dict:
    """
    Check knowledge base claims for staleness and mark them.
    
    - Claims older than CLAIM_EXPIRY_DAYS without re-verification -> status='stale'
    - Claims older than CLAIM_MAX_AGE_DAYS -> status='expired'
    
    Returns:
        Dict with counts of flagged/expired claims.
    """
    kb = load_knowledge_base(domain)
    if not kb:
        return {"flagged": 0, "expired": 0, "active": 0}
    
    claims = kb.get("claims", [])
    now = datetime.now(timezone.utc)
    flagged = 0
    expired = 0
    active = 0
    
    for claim in claims:
        if claim.get("status") in ("superseded", "expired"):
            continue
            
        # Use last_confirmed if available, fall back to first_seen
        last_date_str = claim.get("last_confirmed") or claim.get("first_seen", "")
        if not last_date_str:
            continue
            
        try:
            last_date = datetime.fromisoformat(last_date_str)
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        
        age_days = (now - last_date).days
        
        if age_days >= CLAIM_MAX_AGE_DAYS and claim.get("status") != "expired":
            claim["status"] = "expired"
            claim["notes"] = (claim.get("notes", "") + f" [AUTO-EXPIRED: {age_days}d old, no re-verification]").strip()
            expired += 1
        elif age_days >= CLAIM_EXPIRY_DAYS and claim.get("status") not in ("stale", "expired"):
            claim["status"] = "stale"
            claim["notes"] = (claim.get("notes", "") + f" [STALE: {age_days}d since last verification]").strip()
            flagged += 1
        elif claim.get("status") == "active":
            active += 1
    
    if flagged > 0 or expired > 0:
        save_knowledge_base(domain, kb)
    
    return {"flagged": flagged, "expired": expired, "active": active}


# ============================================================
# Question Deduplication
# ============================================================

def is_duplicate_question(domain: str, question: str, threshold: float = 0.80) -> tuple[bool, str | None]:
    """
    Check if a question has already been researched (or is very similar to one).
    
    Uses RAG vector embeddings when available for accurate semantic matching
    (catches paraphrases). Falls back to TF-IDF cosine similarity.
    
    Args:
        domain: Domain to check
        question: The candidate question
        threshold: Similarity threshold above which we consider it a duplicate
    
    Returns:
        (is_duplicate, matched_question_or_None)
    """
    # Try RAG first
    try:
        from config import RAG_ENABLED
        if RAG_ENABLED:
            from rag.retrieval import is_duplicate_question_rag, RAG_ENABLED as _rag_deps
            if _rag_deps:
                from rag.vector_store import get_collection_stats
                stats = get_collection_stats()
                if stats.get("questions_count", 0) > 0:
                    return is_duplicate_question_rag(domain, question, threshold)
    except Exception:
        pass  # Fall through to TF-IDF
    
    # Fallback: TF-IDF dedup (original implementation)
    outputs = load_outputs(domain, min_score=0)
    if not outputs:
        return False, None
    
    past_questions = [o.get("question", "") for o in outputs if o.get("question")]
    if not past_questions:
        return False, None
    
    # Quick exact match
    question_lower = question.lower().strip()
    for pq in past_questions:
        if pq.lower().strip() == question_lower:
            return True, pq
    
    # TF-IDF similarity
    if len(past_questions) < 2:
        # Not enough data for TF-IDF — use token overlap
        q_tokens = set(_tokenize(question))
        for pq in past_questions:
            pq_tokens = set(_tokenize(pq))
            if not q_tokens or not pq_tokens:
                continue
            overlap = len(q_tokens & pq_tokens) / max(len(q_tokens | pq_tokens), 1)
            if overlap >= threshold:
                return True, pq
        return False, None
    
    try:
        corpus = past_questions + [question]
        vectorizer = TfidfVectorizer(
            stop_words='english',
            max_features=2000,
            ngram_range=(1, 2),
            min_df=1,
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)
        
        # Compare the last vector (our question) against all others
        query_vec = tfidf_matrix[-1]
        past_matrix = tfidf_matrix[:-1]
        similarities = cosine_similarity(query_vec, past_matrix).flatten()
        
        max_idx = int(np.argmax(similarities))
        max_sim = float(similarities[max_idx])
        
        if max_sim >= threshold:
            return True, past_questions[max_idx]
    except Exception:
        pass
    
    return False, None
