#!/usr/bin/env python3
"""
Example: Crawl Website to Knowledge Base

Demonstrates the crawl-to-KB pipeline:
1. Crawl a documentation site
2. Extract claims from pages
3. Inject claims into the KB
4. Index in RAG for semantic search

Run:
    python examples/03_crawl_to_kb.py

Cost: FREE (no API calls - just web scraping)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def example_crawl_docs():
    """Crawl a docs site and store locally."""
    print("\n=== STEP 1: Crawl Documentation ===\n")
    
    print("  CLI command:")
    print("  python main.py --crawl 'https://playwright.dev/python/docs/intro' \\")
    print("                 --domain playwright-docs \\")
    print("                 --crawl-max 5")
    print("")
    print("  This will:")
    print("    1. Fetch up to 5 pages from playwright.dev")
    print("    2. Extract content and headings")
    print("    3. Save to crawl_data/playwright-docs/")


def example_inject_to_kb():
    """Inject crawled content into KB."""
    print("\n=== STEP 2: Inject to KB ===\n")
    
    print("  CLI command:")
    print("  python main.py --crawl-inject --domain playwright-docs")
    print("")
    print("  This will:")
    print("    1. Read crawled pages from crawl_data/playwright-docs/")
    print("    2. Extract claims using heuristics (no LLM)")
    print("    3. Add claims to the KB for this domain")
    print("    4. Index in RAG vector store")


def example_search_rag():
    """Search the RAG vector store."""
    print("\n=== STEP 3: Search RAG ===\n")
    
    print("  CLI command:")
    print("  python main.py --rag-search 'browser testing automation'")
    print("")
    print("  Python API:")
    print("    from rag.vector_store import search_claims")
    print("    results = search_claims('browser testing', max_results=5)")
    print("    for r in results:")
    print("        print(r['text'][:100])")


def example_full_pipeline():
    """Show the full pipeline."""
    print("\n=== FULL PIPELINE ===\n")
    
    print("  # 1. Crawl competitor docs")
    print("  python main.py --crawl 'https://superside.com/landing-pages' \\")
    print("                 --domain productized-services --crawl-max 10")
    print("")
    print("  # 2. Inject to KB")
    print("  python main.py --crawl-inject --domain productized-services")
    print("")
    print("  # 3. Verify KB updated")
    print("  python main.py --kb --domain productized-services")
    print("")
    print("  # 4. Search across all domains")
    print("  python main.py --rag-search 'landing page pricing'")


def main():
    print("\n" + "="*60)
    print("  CRAWL-TO-KB PIPELINE EXAMPLE")
    print("="*60)
    
    example_crawl_docs()
    example_inject_to_kb()
    example_search_rag()
    example_full_pipeline()
    
    print("\n" + "="*60)
    print("  RAG Stats")
    print("="*60 + "\n")
    
    try:
        from rag.vector_store import get_collection_stats
        stats = get_collection_stats()
        print(f"  Total claims indexed: {stats['claims_count']}")
        print(f"  Questions indexed: {stats['questions_count']}")
        print(f"  Vector DB path: {stats['vectordb_path']}")
    except Exception as e:
        print(f"  Error getting stats: {e}")


if __name__ == "__main__":
    main()
