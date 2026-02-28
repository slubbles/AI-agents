"""Crawl, fetch, RAG, and MCP CLI commands."""

import os


# ============================================================
# Web Crawl / Fetch Commands
# ============================================================

def crawl(url: str, domain: str, max_pages: int, url_pattern: str):
    """Crawl a documentation site and store content locally."""
    from tools.web_fetcher import crawl_docs_site

    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "crawl_data", domain or "general")

    print(f"\n{'='*60}")
    print(f"CRAWLING: {url}")
    print(f"  Domain: {domain or 'general'}")
    print(f"  Max pages: {max_pages}")
    if url_pattern:
        print(f"  URL pattern: {url_pattern}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")

    pages = crawl_docs_site(
        start_url=url,
        max_pages=max_pages,
        url_pattern=url_pattern or None,
        output_dir=output_dir,
    )

    total_chars = sum(p.get("content_length", 0) for p in pages)
    print(f"\n{'='*60}")
    print(f"CRAWL COMPLETE")
    print(f"  Pages crawled: {len(pages)}")
    print(f"  Total content: {total_chars:,} chars")
    print(f"  Saved to: {output_dir}")
    print(f"{'='*60}")


def fetch(url: str):
    """Fetch a single URL and display content."""
    from tools.web_fetcher import fetch_page

    print(f"\nFetching: {url}")
    result = fetch_page(url)

    if not result:
        print("  FAILED — could not fetch page")
        return

    print(f"  Title: {result['title']}")
    print(f"  Content: {result['content_length']} chars")
    print(f"  Headings: {len(result['headings'])}")
    print(f"  Code blocks: {len(result['code_blocks'])}")
    print(f"\n--- Content Preview (first 1000 chars) ---")
    print(result['content'][:1000])
    if result['headings']:
        print(f"\n--- Headings ---")
        for h in result['headings'][:15]:
            print(f"  - {h}")


def crawl_inject(domain: str):
    """Inject crawled documentation into knowledge base."""
    from tools.crawl_to_kb import inject_crawl_claims_into_kb

    print(f"\n{'='*60}")
    print(f"INJECTING CRAWL DATA \u2192 KB")
    print(f"  Domain: {domain}")
    print(f"{'='*60}\n")

    result = inject_crawl_claims_into_kb(domain)

    print(f"\nResult:")
    print(f"  Total claims extracted: {result['total_claims']}")
    print(f"  Injected into KB: {result['injected']}")
    print(f"  Skipped (duplicates): {result['skipped']}")

    if result['injected'] > 0:
        print(f"\n  \u2713 KB updated. Run: python main.py --status --domain {domain}")
    else:
        print(f"\n  No new claims to inject. Run --crawl first to gather docs.")


# ============================================================
# RAG — Vector Store Commands
# ============================================================

def rag_status():
    """Show RAG vector store statistics."""
    print(f"\n{'='*60}")
    print(f"  RAG VECTOR STORE STATUS")
    print(f"{'='*60}\n")

    try:
        from rag.vector_store import get_collection_stats
        s = get_collection_stats()

        if "error" in s:
            print(f"  Error: {s['error']}")
            return

        print(f"  Claims indexed:    {s['claims_count']}")
        print(f"  Questions indexed: {s['questions_count']}")
        print(f"  Storage:           {s['vectordb_path']}")

        from config import RAG_ENABLED, EMBEDDING_MODEL
        print(f"\n  RAG enabled:       {RAG_ENABLED}")
        print(f"  Embedding model:   {EMBEDDING_MODEL}")

    except ImportError as e:
        print(f"  RAG not available: {e}")
        print(f"  Install: pip install chromadb sentence-transformers")


def rag_rebuild(domain: str):
    """Rebuild RAG index for a domain (or all domains)."""
    print(f"\n{'='*60}")
    print(f"  RAG INDEX REBUILD")
    print(f"  Domain: {domain if domain != 'general' else 'ALL'}")
    print(f"{'='*60}\n")

    try:
        from rag.vector_store import rebuild_index
        from memory_store import load_outputs, load_knowledge_base, MEMORY_DIR
    except ImportError as e:
        print(f"  Error: {e}")
        return

    # Determine which domains to rebuild
    if domain == "general":
        domains = []
        if os.path.exists(MEMORY_DIR):
            for d in os.listdir(MEMORY_DIR):
                dpath = os.path.join(MEMORY_DIR, d)
                if os.path.isdir(dpath) and not d.startswith("_"):
                    domains.append(d)
        domains.sort()
    else:
        domains = [domain]

    if not domains:
        print("  No domains found in memory.")
        return

    total_claims = 0
    total_kb = 0

    for d in domains:
        outputs = load_outputs(d, min_score=0)
        kb = load_knowledge_base(d)

        print(f"  Rebuilding {d}... ({len(outputs)} outputs)", end=" ")
        result = rebuild_index(d, outputs, kb)
        print(f"\u2192 {result['claims_indexed']} claims + {result['kb_claims_indexed']} KB claims")

        total_claims += result['claims_indexed']
        total_kb += result['kb_claims_indexed']

    print(f"\n  \u2713 Total: {total_claims} claims + {total_kb} KB claims indexed across {len(domains)} domain(s)")


def rag_search(query: str, domain: str):
    """Semantic search across the vector store."""
    print(f"\n{'='*60}")
    print(f"  RAG SEMANTIC SEARCH")
    print(f"  Query: {query}")
    print(f"  Domain: {domain}")
    print(f"{'='*60}\n")

    try:
        from rag.vector_store import search_claims
    except ImportError as e:
        print(f"  Error: {e}")
        return

    target_domain = domain if domain != "general" else None
    results = search_claims(
        query=query,
        domain=target_domain,
        max_results=10,
        accepted_only=True,
    )

    if not results:
        print("  No results found. Try --rag-rebuild first to index existing data.")
        return

    for i, r in enumerate(results):
        sim = r['similarity']
        sim_bar = "\u2588" * int(sim * 20) + "\u2591" * (20 - int(sim * 20))
        print(f"  {i+1}. [{r['domain']}] (sim: {sim:.3f}) {sim_bar}")
        print(f"     {r['text'][:120]}")
        if r.get('source'):
            print(f"     Source: {r['source'][:80]}")
        print()


# ============================================================
# MCP — Docker Tool Gateway Commands
# ============================================================

def mcp_status():
    """Display MCP gateway status and connected servers."""
    print(f"\n{'='*60}")
    print(f"  MCP GATEWAY STATUS")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        s = gw.get_status()

        print(f"  Started: {s['started']}")
        print(f"  Servers: {s['running_servers']}/{s['total_servers']} running")
        print(f"  Total tools: {s['total_tools']}")
        print()

        for name, srv in s.get("servers", {}).items():
            icon = "\u25cf" if srv.get("running") else "\u25cb"
            init = "\u2713" if srv.get("initialized") else "\u2717"
            print(f"  {icon} {name} (init: {init}, tools: {srv.get('tools_count', 0)})")
            if srv.get("tool_names"):
                for tn in srv["tool_names"][:10]:
                    print(f"      - {tn}")
                if len(srv.get("tool_names", [])) > 10:
                    print(f"      ... and {len(srv['tool_names']) - 10} more")
            print()

    except Exception as e:
        print(f"  Error: {e}")


def mcp_start_all():
    """Start all configured MCP servers."""
    print(f"\n{'='*60}")
    print(f"  MCP \u2014 STARTING ALL SERVERS")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()

        if not gw._containers:
            count = gw.load_config(_cfg.MCP_CONFIG_PATH)
            print(f"  Loaded {count} server configurations")

        results = gw.start_all()
        for name, success in results.items():
            icon = "\u2713" if success else "\u2717"
            print(f"  {icon} {name}")

        total_tools = len(gw.get_all_tools())
        print(f"\n  Total tools available: {total_tools}")

    except Exception as e:
        print(f"  Error: {e}")


def mcp_stop_all():
    """Stop all running MCP servers."""
    print(f"\n{'='*60}")
    print(f"  MCP \u2014 STOPPING ALL SERVERS")
    print(f"{'='*60}\n")

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        gw.stop_all()
        print("  All MCP servers stopped.")
    except Exception as e:
        print(f"  Error: {e}")


def mcp_tools():
    """List all available MCP tools across all servers."""
    print(f"\n{'='*60}")
    print(f"  MCP TOOLS")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        tools = gw.get_all_tools()

        if not tools:
            print("  No tools available. Start MCP servers with --mcp-start first.")
            return

        by_server: dict[str, list] = {}
        for tool in tools:
            server = tool["name"].split("__")[0] if "__" in tool["name"] else "unknown"
            by_server.setdefault(server, []).append(tool)

        for server, server_tools in sorted(by_server.items()):
            print(f"  [{server}] ({len(server_tools)} tools)")
            for t in server_tools:
                short_name = t["name"].split("__", 1)[-1] if "__" in t["name"] else t["name"]
                desc = t.get("description", "").replace(f"[{server}] ", "")[:80]
                print(f"    - {short_name}: {desc}")
            print()

    except Exception as e:
        print(f"  Error: {e}")


def mcp_health():
    """Run health checks on all MCP servers."""
    print(f"\n{'='*60}")
    print(f"  MCP HEALTH CHECK")
    print(f"{'='*60}\n")

    import config as _cfg
    if not _cfg.MCP_ENABLED:
        print("  MCP is disabled. Set MCP_ENABLED=True in config.py to enable.")
        return

    try:
        from mcp.gateway import get_gateway
        gw = get_gateway()
        health_data = gw.health_check()

        if not health_data:
            print("  No servers configured.")
            return

        for name, s in health_data.items():
            running = s.get("running", False)
            responsive = s.get("responsive", False)
            if running and responsive:
                icon = "\u25cf"
                state = "healthy"
            elif running and not responsive:
                icon = "\u25d0"
                state = "unresponsive"
            else:
                icon = "\u25cb"
                state = "stopped"
            restarts = s.get("restart_count", 0)
            tools_count = s.get("tools_count", 0)
            print(f"  {icon} {name}: {state} (tools: {tools_count}, restarts: {restarts})")

    except Exception as e:
        print(f"  Error: {e}")
