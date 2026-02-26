"""
RAG (Retrieval-Augmented Generation) Module

Provides semantic vector search for Agent Brain's memory system.
Replaces TF-IDF bag-of-words retrieval with dense embeddings
via sentence-transformers + ChromaDB.

Components:
- vector_store.py — ChromaDB-backed vector store with auto-indexing
- embeddings.py  — Embedding model management (local sentence-transformers)
"""
