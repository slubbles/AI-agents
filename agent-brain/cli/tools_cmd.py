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


# ============================================================
# Buffer — Personal API test commands
# ============================================================

def buffer_status():
    """Show Buffer account and connected X channels."""
    print(f"\n{'='*60}")
    print("  BUFFER API STATUS")
    print(f"{'='*60}\n")

    try:
        from tools.buffer_client import is_configured, get_account, get_x_channels
    except ImportError as exc:
        print(f"  Error: {exc}")
        return

    if not is_configured():
        print("  Buffer API not configured. Set BUFFER_API_KEY in .env")
        return

    try:
        account = get_account()
        x_channels = get_x_channels()
    except Exception as exc:
        print(f"  Error: {exc}")
        return

    print(f"  Account: {account.get('email', '?')}")
    organizations = account.get("organizations", [])
    print(f"  Organizations: {len(organizations)}")
    for org in organizations:
        print(f"    - {org.get('name', '?')} ({org.get('channelCount', 0)} channels)")

    print(f"\n  Connected X channels: {len(x_channels)}")
    for channel in x_channels:
        print(
            f"    - {channel.get('displayName') or channel.get('name')} "
            f"[id={channel.get('id')}] disconnected={channel.get('isDisconnected')} locked={channel.get('isLocked')}"
        )


def buffer_test_x(text: str = ""):
    """Create a safe draft post on the first connected X channel."""
    print(f"\n{'='*60}")
    print("  BUFFER X DRAFT TEST")
    print(f"{'='*60}\n")

    try:
        from tools.buffer_client import create_x_draft_test
        result = create_x_draft_test(text or None)
    except Exception as exc:
        print(f"  Error: {exc}")
        return

    post = result.get("post", {})
    channel = result.get("channel", {})
    print("  ✓ Draft created successfully")
    print(f"  Post ID: {post.get('id', '?')}")
    print(f"  Status: {post.get('status', '?')}")
    print(f"  Channel: {channel.get('displayName') or channel.get('name', '?')}")
    print(f"  Service: {channel.get('service', '?')}")
    print(f"  Text: {post.get('text', '')}")


def buffer_supervised_status():
    """Show the pending supervised X draft, if any."""
    print(f"\n{'='*60}")
    print("  BUFFER X SUPERVISED STATUS")
    print(f"{'='*60}\n")

    try:
        from tools.buffer_client import get_pending_x_queue, MAX_PENDING_X_DRAFTS
    except ImportError as exc:
        print(f"  Error: {exc}")
        return

    queue = get_pending_x_queue()
    if not queue:
        print("  No pending supervised X draft")
        return

    print(f"  Queue: {len(queue)}/{MAX_PENDING_X_DRAFTS}")
    for index, pending in enumerate(queue, start=1):
        print(f"\n  [{index}] {pending.get('draft_id', 'unknown')}")
        print(f"    Type: {'buffer-draft' if pending.get('draft_post_id') else 'local'}")
        print(f"    Channel: {pending.get('channel_name', '?')}")
        print(f"    Created: {pending.get('created_at', '?')}")
        print(f"    Status: {pending.get('status', '?')}")
        print(f"    Text: {pending.get('text', '')}")


def buffer_draft_x(text: str):
    """Create a supervised draft that must be confirmed before sending."""
    print(f"\n{'='*60}")
    print("  BUFFER X SUPERVISED DRAFT")
    print(f"{'='*60}\n")

    try:
        from tools.buffer_client import create_x_supervised_draft
        result = create_x_supervised_draft(text)
    except Exception as exc:
        print(f"  Error: {exc}")
        return

    pending = result.get("pending", {})
    print("  ✓ Draft created and waiting for confirmation")
    print("  Draft type: local pending")
    print(f"  Draft ID: {pending.get('draft_id') or 'unknown'}")
    print(f"  Channel: {pending.get('channel_name', '?')}")
    print(f"  Text: {pending.get('text', '')}")
    print(f"  Queue: {result.get('queue_size', '?')}/{result.get('queue_limit', '?')}")
    print("  Next step: run --buffer-confirm-x to send it live")


def buffer_confirm_x(draft_id: str | None = None):
    """Send the pending supervised X draft live."""
    print(f"\n{'='*60}")
    print("  BUFFER X CONFIRM SEND")
    print(f"{'='*60}\n")

    try:
        from tools.buffer_client import confirm_x_supervised_post
        result = confirm_x_supervised_post(draft_id=draft_id)
    except Exception as exc:
        print(f"  Error: {exc}")
        return

    post = result.get("post", {})
    confirmed_from = result.get("confirmed_from", {})
    print("  ✓ Draft sent live")
    print(f"  From draft: {confirmed_from.get('draft_id', '?')}")
    print(f"  Sent post ID: {post.get('id', '?')}")
    print(f"  Status: {post.get('status', '?')}")
    print(f"  Text: {post.get('text', '')}")
    print(f"  Queue remaining: {result.get('remaining_queue_size', '?')}")


def buffer_cancel_x(draft_id: str | None = None):
    """Cancel the pending supervised X draft."""
    print(f"\n{'='*60}")
    print("  BUFFER X CANCEL DRAFT")
    print(f"{'='*60}\n")

    try:
        from tools.buffer_client import cancel_x_supervised_post
        result = cancel_x_supervised_post(draft_id=draft_id)
    except Exception as exc:
        print(f"  Error: {exc}")
        return

    if result.get("cleared"):
        pending = result.get("pending", {})
        print("  ✓ Pending supervised draft cleared")
        print(f"  Cleared draft: {pending.get('draft_id', '?')}")
        print(f"  Queue remaining: {result.get('remaining_queue_size', '?')}")
        return

    print("  No pending supervised X draft to clear")


def discord_status():
    """Show Discord content-factory channel access."""
    print(f"\n{'='*60}")
    print("  DISCORD CONTENT FACTORY STATUS")
    print(f"{'='*60}\n")

    try:
        from tools.discord_client import get_channel, get_configured_channels, is_configured
    except ImportError as exc:
        print(f"  Error: {exc}")
        return

    channels = get_configured_channels()
    print(f"  Configured: {'yes' if is_configured() else 'no'}")
    for name, channel_id in channels.items():
        if not channel_id:
            print(f"  {name}: missing channel id")
            continue
        try:
            channel = get_channel(channel_id)
            print(f"  {name}: {channel.get('name', '?')} [id={channel_id}]")
        except Exception as exc:
            print(f"  {name}: access failed for [id={channel_id}] - {exc}")


def content_factory_status():
    """Show content-factory scheduling and publishing status."""
    print(f"\n{'='*60}")
    print("  CONTENT FACTORY STATUS")
    print(f"{'='*60}\n")

    try:
        from content_factory import get_content_factory_status
    except ImportError as exc:
        print(f"  Error: {exc}")
        return

    status = get_content_factory_status()
    print(f"  Enabled: {'yes' if status['enabled'] else 'no'}")
    print(f"  Configured: {'yes' if status['configured'] else 'no'}")
    print(f"  Timezone: {status['timezone']}")
    print(f"  Scheduled hour: {status['scheduled_hour']}:00")
    print(f"  Due now: {'yes' if status['due_now'] else 'no'}")
    print(f"  Local time now: {status['now_local']}")
    print(f"  Last run: {status.get('last_run_at') or 'never'}")
    if status.get('last_error'):
        print(f"  Last error: {status['last_error']}")
    print(f"\n  Auto-publish X: {'yes' if status['auto_publish_x'] else 'no'}")
    print(f"  X mode: {status['x_mode']} | draft only: {'yes' if status['x_save_to_draft'] else 'no'}")
    print(f"  Auto-publish Threads: {'yes' if status['auto_publish_threads'] else 'no'}")


def content_factory_run(force: bool = True):
    """Run the content factory once right now."""
    print(f"\n{'='*60}")
    print("  CONTENT FACTORY RUN")
    print(f"{'='*60}\n")

    try:
        from content_factory import run_content_factory
    except ImportError as exc:
        print(f"  Error: {exc}")
        return

    result = run_content_factory(force=force)
    if result.get("ok"):
        if result.get("skipped"):
            print(f"  Skipped: {result.get('reason', 'not due')}")
            return
        print("  ✓ Content factory completed")
        discord = result.get("discord", {})
        publish = result.get("publish", {})
        if discord:
            print(f"  Discord posts: research={discord.get('research', 0)} scripts={discord.get('scripts', 0)} thumbnails={discord.get('thumbnails', 0)}")
        if publish:
            print(f"  X: {publish.get('x', {}).get('status', 'skipped')}")
            print(f"  Threads: {publish.get('threads', {}).get('status', 'skipped')}")
        return

    print(f"  Error: {result.get('error', 'unknown error')}")


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
