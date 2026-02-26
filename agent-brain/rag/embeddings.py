"""
Embedding Model Management

Lazy-loaded singleton for the sentence-transformers embedding model.
Uses all-MiniLM-L6-v2 (384 dimensions, ~80MB, fast inference).
Runs 100% locally — no API calls, no cost.

Usage:
    from rag.embeddings import get_embedding_fn, embed_texts
    
    # Get the raw function (for ChromaDB)
    fn = get_embedding_fn()
    
    # Or embed directly
    vectors = embed_texts(["text1", "text2"])  # -> list[list[float]]
"""

import os
from typing import Callable

# Lazy-loaded model singleton
_model = None
_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _get_model():
    """Lazy-load the sentence-transformers model (one-time cost ~2s)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts into dense vectors.
    
    Args:
        texts: List of strings to embed.
    
    Returns:
        List of float vectors, each of dimension _EMBEDDING_DIM.
    """
    if not texts:
        return []
    model = _get_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()


def embed_single(text: str) -> list[float]:
    """Embed a single text string."""
    return embed_texts([text])[0]


class SentenceTransformerEmbeddingFunction:
    """
    ChromaDB-compatible embedding function.
    
    ChromaDB expects:
    - __call__(input: Documents) -> Embeddings  (for indexing)
    - embed_query(input: Documents) -> Embeddings  (for querying)
    - name() -> str  (for serialization)
    """
    
    def name(self) -> str:
        return "sentence-transformer-minilm"
    
    def __call__(self, input: list[str]) -> list[list[float]]:
        return embed_texts(input)
    
    def embed_query(self, input: list[str]) -> list[list[float]]:
        """ChromaDB calls this for query-time embeddings."""
        return embed_texts(input)


def get_embedding_fn() -> SentenceTransformerEmbeddingFunction:
    """Get a ChromaDB-compatible embedding function."""
    return SentenceTransformerEmbeddingFunction()


def get_embedding_dim() -> int:
    """Return the embedding dimension."""
    return _EMBEDDING_DIM
