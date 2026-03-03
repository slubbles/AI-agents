"""
Vector Store — ChromaDB-backed semantic memory for Agent Brain.

Provides claim-level indexing and retrieval across all domains.
Each research finding/claim is stored as a separate vector, enabling
fine-grained semantic search.

Architecture:
- ChromaDB persistent storage in memory/_vectordb/
- Two collections:
  1. "claims" — individual research findings at claim granularity
  2. "questions" — past research questions for deduplication
- Embeddings via local sentence-transformers (all-MiniLM-L6-v2, 384d)
- No API calls, no cost — runs entirely locally

Integration points:
- save_output()      → auto-index new claims + question
- save_knowledge_base() → index synthesized KB claims
- retrieve_relevant() → semantic retrieval (replaces TF-IDF)
- is_duplicate_question() → semantic dedup (replaces TF-IDF)
"""

import json
import os
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional

# Disable ChromaDB telemetry — prevents recursion in serialization
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_TELEMETRY", "false")

import chromadb

from rag.embeddings import get_embedding_fn, embed_texts


# ── Configuration ─────────────────────────────────────────────────────

# Where ChromaDB stores its persistent data
_VECTORDB_DIR = os.path.join(
    os.environ.get("MEMORY_DIR", os.path.join(os.path.dirname(__file__), "..", "memory")),
    "_vectordb"
)

# Collection names
CLAIMS_COLLECTION = "claims"
QUESTIONS_COLLECTION = "questions"

# Retrieval defaults
DEFAULT_MAX_RESULTS = 10
RELEVANCE_THRESHOLD = 0.3  # Minimum similarity to include

# ── Client Singleton ──────────────────────────────────────────────────

_client: Optional[chromadb.ClientAPI] = None
_embedding_fn = None


def _get_client() -> chromadb.ClientAPI:
    """Get or create the ChromaDB persistent client."""
    global _client
    if _client is None:
        os.makedirs(_VECTORDB_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=_VECTORDB_DIR)
    return _client


def _get_embedding_fn():
    """Lazy singleton for embedding function."""
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = get_embedding_fn()
    return _embedding_fn


def _get_claims_collection():
    """Get or create the claims collection."""
    client = _get_client()
    return client.get_or_create_collection(
        name=CLAIMS_COLLECTION,
        embedding_function=_get_embedding_fn(),
        metadata={"description": "Individual research findings at claim granularity"},
    )


def _get_questions_collection():
    """Get or create the questions collection."""
    client = _get_client()
    return client.get_or_create_collection(
        name=QUESTIONS_COLLECTION,
        embedding_function=_get_embedding_fn(),
        metadata={"description": "Past research questions for deduplication"},
    )


# ── Claim ID Generation ──────────────────────────────────────────────

def _claim_id(domain: str, output_ts: str, claim_index: int) -> str:
    """Generate a deterministic claim ID from domain + output timestamp + index."""
    raw = f"{domain}:{output_ts}:{claim_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _question_id(domain: str, question: str) -> str:
    """Generate a deterministic ID for a question."""
    raw = f"{domain}:{question.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _kb_claim_id(domain: str, claim_text: str) -> str:
    """Generate a deterministic ID for a KB claim."""
    raw = f"kb:{domain}:{claim_text[:200].lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Indexing ──────────────────────────────────────────────────────────

def index_output(domain: str, output: dict) -> int:
    """
    Index a research output's claims and question into the vector store.
    
    Each finding = one vector in the claims collection.
    The question = one vector in the questions collection.
    
    Args:
        domain: Domain name
        output: Full output dict (with research, critique, timestamp, etc.)
    
    Returns:
        Number of claims indexed.
    """
    timestamp = output.get("timestamp", datetime.now(timezone.utc).isoformat())
    question = output.get("question", "")
    research = output.get("research", {})
    overall_score = output.get("overall_score", 0)
    accepted = output.get("accepted", output.get("verdict") == "accept")
    
    claims_col = _get_claims_collection()
    indexed = 0
    
    # Index each finding as a separate claim
    findings = research.get("findings", [])
    if findings:
        ids = []
        documents = []
        metadatas = []
        
        for i, finding in enumerate(findings):
            claim_text = finding.get("claim", "")
            if not claim_text or len(claim_text) < 10:
                continue
                
            cid = _claim_id(domain, timestamp, i)
            
            # Build rich text for embedding: claim + reasoning + source context
            embed_text = claim_text
            if finding.get("reasoning"):
                embed_text += f" | {finding['reasoning'][:200]}"
            
            ids.append(cid)
            documents.append(embed_text)
            metadatas.append({
                "domain": domain,
                "question": question[:200],
                "timestamp": timestamp,
                "confidence": finding.get("confidence", "low"),
                "source": finding.get("source", "")[:500],
                "overall_score": overall_score,
                "accepted": accepted,
                "claim_index": i,
                "type": "finding",
            })
        
        if ids:
            claims_col.upsert(ids=ids, documents=documents, metadatas=metadatas)
            indexed = len(ids)
    
    # Also index key insights
    insights = research.get("key_insights", [])
    if insights:
        insight_ids = []
        insight_docs = []
        insight_metas = []
        
        for i, insight in enumerate(insights):
            if not insight or len(insight) < 10:
                continue
            iid = _claim_id(domain, timestamp, 1000 + i)  # Offset to avoid collision
            insight_ids.append(iid)
            insight_docs.append(insight)
            insight_metas.append({
                "domain": domain,
                "question": question[:200],
                "timestamp": timestamp,
                "overall_score": overall_score,
                "accepted": accepted,
                "type": "insight",
            })
        
        if insight_ids:
            claims_col.upsert(ids=insight_ids, documents=insight_docs, metadatas=insight_metas)
            indexed += len(insight_ids)
    
    # Index the question for dedup
    if question and len(question) > 5:
        questions_col = _get_questions_collection()
        qid = _question_id(domain, question)
        questions_col.upsert(
            ids=[qid],
            documents=[question],
            metadatas=[{
                "domain": domain,
                "timestamp": timestamp,
                "overall_score": overall_score,
                "accepted": accepted,
            }],
        )
    
    return indexed


def index_knowledge_base(domain: str, kb: dict) -> int:
    """
    Index synthesized knowledge base claims into the vector store.
    
    KB claims are indexed with type="kb_claim" so they can be distinguished
    from raw findings.
    
    Args:
        domain: Domain name
        kb: Knowledge base dict with "claims" list
    
    Returns:
        Number of KB claims indexed.
    """
    claims = kb.get("claims", [])
    if not claims:
        return 0
    
    claims_col = _get_claims_collection()
    ids = []
    documents = []
    metadatas = []
    
    for claim in claims:
        claim_text = claim.get("claim", "")
        if not claim_text or len(claim_text) < 10:
            continue
        if claim.get("status") in ("expired", "superseded"):
            continue
            
        cid = _kb_claim_id(domain, claim_text)
        
        ids.append(cid)
        documents.append(claim_text)
        metadatas.append({
            "domain": domain,
            "confidence": claim.get("confidence", "low"),
            "status": claim.get("status", "active"),
            "topic": claim.get("topic", "")[:100],
            "type": "kb_claim",
            "timestamp": claim.get("first_seen", datetime.now(timezone.utc).isoformat()),
        })
    
    if ids:
        claims_col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    
    return len(ids)


def index_all_outputs(domain: str, outputs: list[dict]) -> int:
    """
    Bulk index all outputs for a domain. Used for initial migration
    from TF-IDF to vector store.
    
    Args:
        domain: Domain name
        outputs: List of output dicts
    
    Returns:
        Total claims indexed.
    """
    total = 0
    for output in outputs:
        total += index_output(domain, output)
    return total


# ── Retrieval ─────────────────────────────────────────────────────────

def search_claims(
    query: str,
    domain: str | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    min_score: float = 0,
    accepted_only: bool = True,
    include_kb: bool = True,
) -> list[dict]:
    """
    Semantic search for relevant claims across the vector store.
    
    Args:
        query: The search query (natural language)
        domain: Restrict to a specific domain, or None for cross-domain
        max_results: Maximum number of claims to return
        min_score: Minimum overall_score to include (0 = all)
        accepted_only: Only return claims from accepted outputs
        include_kb: Also include KB claims in results
    
    Returns:
        List of dicts with keys: text, domain, confidence, source, score,
        distance, timestamp, type
    """
    claims_col = _get_claims_collection()
    
    # Build where filter
    where_filters = []
    if domain:
        where_filters.append({"domain": {"$eq": domain}})
    if accepted_only:
        where_filters.append({
            "$or": [
                {"accepted": {"$eq": True}},
                {"type": {"$eq": "kb_claim"}},  # KB claims are always included
            ]
        })
    if not include_kb:
        where_filters.append({"type": {"$ne": "kb_claim"}})
    
    where = None
    if len(where_filters) == 1:
        where = where_filters[0]
    elif len(where_filters) > 1:
        where = {"$and": where_filters}
    
    try:
        # Pre-compute embedding ourselves to bypass ChromaDB's internal
        # embedding function callback, which triggers recursion in 1.5.x
        query_embedding = embed_texts([query])
        results = claims_col.query(
            query_embeddings=query_embedding,
            n_results=min(max_results * 2, 50),  # Over-fetch for post-filtering
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        print(f"[RAG] Search error: {e}")
        return []
    
    if not results or not results["ids"] or not results["ids"][0]:
        return []
    
    # Process results
    claims = []
    for i, doc_id in enumerate(results["ids"][0]):
        doc = results["documents"][0][i]
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        
        # ChromaDB returns L2 distance; convert to similarity (0-1)
        # For normalized embeddings: distance = 2 - 2*cos_sim, so cos_sim = 1 - distance/2
        similarity = max(0, 1 - distance / 2)
        
        # Post-filter by min_score
        output_score = meta.get("overall_score", 0)
        if min_score > 0 and meta.get("type") != "kb_claim" and output_score < min_score:
            continue
        
        claims.append({
            "id": doc_id,
            "text": doc,
            "domain": meta.get("domain", ""),
            "confidence": meta.get("confidence", "unknown"),
            "source": meta.get("source", ""),
            "overall_score": output_score,
            "question": meta.get("question", ""),
            "timestamp": meta.get("timestamp", ""),
            "type": meta.get("type", "finding"),
            "similarity": round(similarity, 4),
            "distance": round(distance, 4),
        })
    
    # Sort by similarity descending
    claims.sort(key=lambda c: c["similarity"], reverse=True)
    
    return claims[:max_results]


def search_similar_questions(
    question: str,
    domain: str | None = None,
    max_results: int = 5,
) -> list[dict]:
    """
    Find similar past questions for deduplication.
    
    Args:
        question: The candidate question
        domain: Restrict to domain, or None for cross-domain
        max_results: Max results
    
    Returns:
        List of dicts with: question, domain, similarity, timestamp, score
    """
    questions_col = _get_questions_collection()
    
    where = {"domain": {"$eq": domain}} if domain else None
    
    try:
        # Pre-compute embedding to bypass ChromaDB recursion bug
        query_embedding = embed_texts([question])
        results = questions_col.query(
            query_embeddings=query_embedding,
            n_results=max_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        print(f"[RAG] Question search error: {e}")
        return []
    
    if not results or not results["ids"] or not results["ids"][0]:
        return []
    
    similar = []
    for i, doc_id in enumerate(results["ids"][0]):
        doc = results["documents"][0][i]
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        similarity = max(0, 1 - distance / 2)
        
        similar.append({
            "question": doc,
            "domain": meta.get("domain", ""),
            "similarity": round(similarity, 4),
            "timestamp": meta.get("timestamp", ""),
            "overall_score": meta.get("overall_score", 0),
        })
    
    return similar


# ── Cross-Domain Retrieval ────────────────────────────────────────────

def cross_domain_search(
    query: str,
    exclude_domain: str | None = None,
    max_results: int = 10,
) -> list[dict]:
    """
    Search for relevant claims across ALL domains.
    
    This enables Layer 5 (cross-domain transfer) to work semantically
    rather than relying on keyword/principle matching.
    
    Args:
        query: What to search for
        exclude_domain: Domain to exclude from results (usually the target domain)
        max_results: Max results
    
    Returns:
        List of claim dicts from other domains, ranked by relevance.
    """
    results = search_claims(
        query=query,
        domain=None,  # All domains
        max_results=max_results * 2,
        accepted_only=True,
        include_kb=True,
    )
    
    if exclude_domain:
        results = [r for r in results if r["domain"] != exclude_domain]
    
    return results[:max_results]


# ── Migration & Maintenance ───────────────────────────────────────────

def get_collection_stats() -> dict:
    """Get stats about the vector store collections."""
    try:
        claims_col = _get_claims_collection()
        questions_col = _get_questions_collection()
        return {
            "claims_count": claims_col.count(),
            "questions_count": questions_col.count(),
            "vectordb_path": _VECTORDB_DIR,
        }
    except Exception as e:
        return {"error": str(e)}


def clear_domain(domain: str) -> int:
    """
    Remove all vectors for a specific domain.
    Used when re-indexing from scratch.
    
    Returns:
        Number of vectors removed.
    """
    removed = 0
    
    try:
        claims_col = _get_claims_collection()
        # Get all IDs for this domain
        existing = claims_col.get(
            where={"domain": {"$eq": domain}},
            include=[],
        )
        if existing["ids"]:
            claims_col.delete(ids=existing["ids"])
            removed += len(existing["ids"])
    except Exception:
        pass
    
    try:
        questions_col = _get_questions_collection()
        existing = questions_col.get(
            where={"domain": {"$eq": domain}},
            include=[],
        )
        if existing["ids"]:
            questions_col.delete(ids=existing["ids"])
            removed += len(existing["ids"])
    except Exception:
        pass
    
    return removed


def rebuild_index(domain: str, outputs: list[dict], kb: dict | None = None) -> dict:
    """
    Full re-index for a domain: clear existing vectors, re-index all outputs + KB.
    
    Args:
        domain: Domain to rebuild
        outputs: All output dicts for the domain
        kb: Optional knowledge base dict
    
    Returns:
        Stats dict with counts.
    """
    cleared = clear_domain(domain)
    claims_indexed = index_all_outputs(domain, outputs)
    kb_indexed = 0
    if kb:
        kb_indexed = index_knowledge_base(domain, kb)
    
    return {
        "domain": domain,
        "cleared": cleared,
        "claims_indexed": claims_indexed,
        "kb_claims_indexed": kb_indexed,
        "total": claims_indexed + kb_indexed,
    }


# ── Test/Debug Helpers ────────────────────────────────────────────────

def reset_client():
    """Reset the ChromaDB client (for testing)."""
    global _client, _embedding_fn
    _client = None
    _embedding_fn = None


def set_vectordb_dir(path: str):
    """Override the vector DB directory (for testing)."""
    global _VECTORDB_DIR, _client
    _VECTORDB_DIR = path
    _client = None  # Force re-creation
