"""
RAG-Enhanced Retrieval

Drop-in replacement functions for memory_store's TF-IDF retrieval.
Falls back gracefully to TF-IDF if ChromaDB/sentence-transformers unavailable.

Usage:
    from rag.retrieval import retrieve_relevant_rag, is_duplicate_question_rag
    
    # Same signature as memory_store.retrieve_relevant()
    results = retrieve_relevant_rag(domain, question, max_results=5)
    
    # Same signature as memory_store.is_duplicate_question()
    is_dup, matched = is_duplicate_question_rag(domain, question)
"""

import os
import sys
from datetime import datetime, timezone

# Ensure parent is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Feature flag ──────────────────────────────────────────────────────

def _rag_available() -> bool:
    """Check if RAG dependencies are available."""
    try:
        import chromadb
        import sentence_transformers
        return True
    except ImportError:
        return False


RAG_ENABLED = _rag_available()


# ── Enhanced Retrieval ────────────────────────────────────────────────

def retrieve_relevant_rag(
    domain: str,
    question: str,
    max_results: int = 5,
    min_score: float = 4.0,
) -> list[dict]:
    """
    Semantic retrieval using vector embeddings.
    
    Replaces TF-IDF with dense embedding search. Falls back to TF-IDF
    if RAG dependencies are not installed.
    
    Returns the same format as memory_store.retrieve_relevant():
    List of dicts with: question, summary, key_insights, findings,
    knowledge_gaps, score, timestamp, _relevance
    """
    if not RAG_ENABLED:
        from memory_store import retrieve_relevant
        return retrieve_relevant(domain, question, max_results, min_score)
    
    from rag.vector_store import search_claims
    from memory_store import load_outputs
    
    # Search for semantically similar claims
    claims = search_claims(
        query=question,
        domain=domain,
        max_results=max_results * 5,  # Over-fetch; we'll group by output
        min_score=min_score,
        accepted_only=True,
        include_kb=True,
    )
    
    if not claims:
        # Fall back to TF-IDF if vector store is empty
        from memory_store import retrieve_relevant
        return retrieve_relevant(domain, question, max_results, min_score)
    
    # Group claims by source question (reconstruct output-level results)
    # This preserves the same return format as the original
    question_groups: dict[str, dict] = {}
    
    for claim in claims:
        src_question = claim.get("question", "")
        claim_type = claim.get("type", "finding")
        
        if claim_type == "kb_claim":
            # KB claims don't group by question — include as standalone
            key = f"kb:{claim['text'][:50]}"
            if key not in question_groups:
                question_groups[key] = {
                    "question": f"[KB] {claim.get('domain', domain)}",
                    "summary": "",
                    "key_insights": [],
                    "findings": [],
                    "knowledge_gaps": [],
                    "score": 10,  # KB claims are pre-verified
                    "timestamp": claim.get("timestamp", ""),
                    "_relevance": claim["similarity"],
                    "_max_similarity": claim["similarity"],
                }
            question_groups[key]["findings"].append({
                "claim": claim["text"],
                "confidence": claim.get("confidence", "high"),
            })
            continue
        
        if not src_question:
            continue
            
        if src_question not in question_groups:
            question_groups[src_question] = {
                "question": src_question,
                "summary": "",
                "key_insights": [],
                "findings": [],
                "knowledge_gaps": [],
                "score": claim.get("overall_score", 0),
                "timestamp": claim.get("timestamp", ""),
                "_relevance": claim["similarity"],
                "_max_similarity": claim["similarity"],
            }
        
        group = question_groups[src_question]
        # Track highest similarity in group
        group["_max_similarity"] = max(group["_max_similarity"], claim["similarity"])
        group["_relevance"] = group["_max_similarity"]
        
        if claim_type == "insight":
            group["key_insights"].append(claim["text"])
        else:
            group["findings"].append({
                "claim": claim["text"],
                "confidence": claim.get("confidence", "low"),
            })
    
    # Enrich with output-level data (summary, gaps) if available
    try:
        outputs = load_outputs(domain, min_score=min_score)
        output_by_question = {}
        for o in outputs:
            q = o.get("question", "")
            if q:
                output_by_question[q] = o
        
        for q, group in question_groups.items():
            if q in output_by_question:
                o = output_by_question[q]
                research = o.get("research", {})
                group["summary"] = research.get("summary", "")
                group["knowledge_gaps"] = research.get("knowledge_gaps", [])
                group["score"] = o.get("overall_score", group["score"])
    except Exception:
        pass  # Enrichment is best-effort
    
    # Sort by relevance (max similarity in group)
    result_list = sorted(
        question_groups.values(),
        key=lambda g: g["_max_similarity"],
        reverse=True,
    )
    
    # Clean up internal fields
    for r in result_list:
        r["_relevance"] = round(r.pop("_max_similarity"), 3)
    
    return result_list[:max_results]


def is_duplicate_question_rag(
    domain: str,
    question: str,
    threshold: float = 0.80,
) -> tuple[bool, str | None]:
    """
    Semantic question deduplication using vector embeddings.
    
    Much more accurate than TF-IDF — catches paraphrases and synonym variations.
    Falls back to TF-IDF if RAG is unavailable.
    
    Returns:
        (is_duplicate, matched_question_or_None)
    """
    if not RAG_ENABLED:
        from memory_store import is_duplicate_question
        return is_duplicate_question(domain, question, threshold)
    
    from rag.vector_store import search_similar_questions
    
    similar = search_similar_questions(
        question=question,
        domain=domain,
        max_results=3,
    )
    
    if not similar:
        return False, None
    
    # Check the most similar question
    best = similar[0]
    if best["similarity"] >= threshold:
        return True, best["question"]
    
    return False, None


# ── Cross-Domain Retrieval (new capability) ───────────────────────────

def retrieve_cross_domain(
    query: str,
    source_domain: str,
    max_results: int = 10,
) -> list[dict]:
    """
    Retrieve relevant claims from OTHER domains.
    
    This enables Layer 5 (cross-domain transfer) to find genuinely
    related knowledge across domain boundaries using semantic similarity,
    rather than relying on keyword matching or manual principle extraction.
    
    Args:
        query: What to search for
        source_domain: The domain making the query (excluded from results)
        max_results: Max results
    
    Returns:
        List of claim dicts from other domains.
    """
    if not RAG_ENABLED:
        return []
    
    from rag.vector_store import cross_domain_search
    
    return cross_domain_search(
        query=query,
        exclude_domain=source_domain,
        max_results=max_results,
    )
