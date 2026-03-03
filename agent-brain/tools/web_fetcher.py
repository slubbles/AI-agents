"""
Web Fetcher — Full page content extraction via Scrapling.

Replaces the snippets-only approach with actual page reading.
Pipeline: DuckDuckGo finds URLs → Scrapling fetches full pages → 
content extracted as clean text for researcher consumption.

Uses Scrapling's adaptive Fetcher (HTTP-level, no browser needed)
with stealthy headers to avoid basic bot detection.
"""

import re
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Lazy import — only load Scrapling when actually needed
_fetcher = None

def _get_fetcher():
    """Lazy-load Scrapling Fetcher to avoid import cost on startup."""
    global _fetcher
    if _fetcher is None:
        try:
            from scrapling.fetchers import Fetcher
            _fetcher = Fetcher
        except (ImportError, Exception) as e:
            # Only warn once, and be specific about what's missing
            if isinstance(e, ImportError):
                logger.warning(f"Scrapling not available: {e}. Run: pip install 'scrapling[all]'")
            else:
                logger.warning(f"Scrapling init error: {e}")
            _fetcher = False  # sentinel: tried and failed
    return _fetcher if _fetcher else None


# --- Content extraction strategies per site type ---

# CSS selectors for known documentation sites
SITE_SELECTORS = {
    "nextjs.org": {
        "content": "article p, article li, article h2, article h3, article code, article pre",
        "title": "h1::text",
        "remove": "nav, footer, header, .sidebar, script, style",
    },
    "react.dev": {
        "content": "article p, article li, article h2, article h3, article code, article pre",
        "title": "h1::text",
        "remove": "nav, footer, header, script, style",
    },
    "developer.mozilla.org": {
        "content": "#content p, #content li, #content h2, #content h3, #content code, #content pre, .main-page-content p, .main-page-content li",
        "title": "h1::text",
        "remove": "nav, footer, header, script, style",
    },
    "vercel.com": {
        "content": "article p, article li, article h2, article h3, main p, main li, main h2",
        "title": "h1::text",
        "remove": "nav, footer, header, script, style",
    },
    "typescript-handbook": {
        "content": "#handbook-content p, #handbook-content li, #handbook-content h2",
        "title": "h1::text",
        "remove": "nav, footer, header, script, style",
    },
}

# Generic fallback selectors (works for most sites)
GENERIC_SELECTORS = {
    "content": "article p, article li, article h2, article h3, main p, main li, main h2, main h3, .content p, .content li, .post-content p, .post-content li, p",
    "title": "h1::text, title::text",
    "remove": "nav, footer, header, aside, .sidebar, .menu, .nav, script, style, .ad, .advertisement, .cookie-banner",
}

# Domains to always skip (search engines, not useful)
SKIP_DOMAINS = {
    "google.com", "bing.com", "duckduckgo.com",
    "youtube.com",
}

# Domains that require stealth browser (JS-heavy, anti-bot, or login-required)
BROWSER_REQUIRED_DOMAINS = {
    # Social media (heavy JS + anti-bot)
    "reddit.com",     # Heavy JS + anti-bot
    "twitter.com", "x.com",  # JS required
    "linkedin.com",   # Login + JS
    "facebook.com",   # Heavy JS
    "instagram.com",  # Heavy JS
    # Content platforms (JS + paywalls)
    "medium.com",     # JS + paywall workaround
    "substack.com",   # JS
    "bloomberg.com",  # JS + anti-bot
    "ft.com",         # Financial Times - JS + paywall
    "wsj.com",        # Wall Street Journal - JS + paywall
    "nytimes.com",    # NY Times - JS + paywall
    # Job sites (JS + anti-bot)
    "indeed.com",     # JS + anti-bot
    "glassdoor.com",  # Login + anti-bot
    "angel.co", "wellfound.com",  # Startup job boards
    # SaaS/Product sites with heavy JS
    "notion.so",      # Client-side rendering
    "airtable.com",   # Client-side rendering
    "figma.com",      # Client-side rendering
    "miro.com",       # Client-side rendering
    # E-commerce (anti-bot)
    "amazon.com",     # Heavy anti-bot
    "shopify.com",    # Client-side rendering
    # Developer forums
    "stackoverflow.com",  # Has anti-bot for heavy scraping
}

# Domains we can try Scrapling first, but fallback to browser if blocked
FALLBACK_DOMAINS = {
    "facebook.com", "instagram.com",
    "github.com",  # Public pages work, but may need browser for rate limits
}

# Max content per page (chars) to avoid token explosion
MAX_CONTENT_LENGTH = 8000
# Max pages to fetch per research cycle
MAX_PAGES_PER_CYCLE = 3
# Request timeout
FETCH_TIMEOUT = 12


def _get_selectors(url: str) -> dict:
    """Get the best CSS selectors for a given URL."""
    domain = urlparse(url).netloc.lower().replace("www.", "")
    
    for site_key, selectors in SITE_SELECTORS.items():
        if site_key in domain:
            return selectors
    
    return GENERIC_SELECTORS


def _should_skip(url: str) -> bool:
    """Check if URL should be skipped entirely (search engines only)."""
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return any(skip in domain for skip in SKIP_DOMAINS)
    except Exception:
        return True


def _needs_browser(url: str) -> bool:
    """Check if URL requires stealth browser (JS, anti-bot, auth)."""
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return any(bd in domain for bd in BROWSER_REQUIRED_DOMAINS)
    except Exception:
        return False


def _is_fallback_domain(url: str) -> bool:
    """Check if URL is in the list of domains that may need browser fallback."""
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return any(fd in domain for fd in FALLBACK_DOMAINS)
    except Exception:
        return False


def _browser_fetch_sync(url: str, timeout: int = 30000) -> Optional[dict]:
    """
    Sync wrapper for stealth browser fetch.
    
    Returns content dict compatible with fetch_page output, or None on failure.
    """
    try:
        import asyncio
        from browser.session_manager import BrowserSession
        
        async def _do_fetch():
            session = BrowserSession(headless=True)
            try:
                result = await session.fetch(url, extract_mode="text", timeout=timeout)
                return result
            finally:
                await session.close_all()
        
        # Run in event loop
        try:
            loop = asyncio.get_running_loop()
            # Already in async context — create task
            result = asyncio.run_coroutine_threadsafe(_do_fetch(), loop).result(timeout=timeout/1000 + 10)
        except RuntimeError:
            # No running loop — create one
            result = asyncio.run(_do_fetch())
        
        if result and result.get("success"):
            return {
                "url": url,
                "title": result.get("title", ""),
                "content": result.get("content", "")[:MAX_CONTENT_LENGTH],
                "content_length": len(result.get("content", "")),
                "headings": [],
                "code_blocks": [],
                "source": "browser",
            }
        else:
            logger.debug(f"Browser fetch failed for {url}: {result.get('error', 'unknown')}")
            return None
            
    except Exception as e:
        logger.debug(f"Browser fetch error for {url}: {e}")
        return None


def _clean_text(text: str) -> str:
    """Clean extracted text — remove excessive whitespace, normalize."""
    # Collapse multiple whitespace/newlines
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common boilerplate phrases
    boilerplate = [
        "Skip to content", "Skip to main content", "Table of contents",
        "On this page", "Was this helpful?", "Edit this page",
        "Previous page", "Next page", "© ", "All rights reserved",
    ]
    for phrase in boilerplate:
        text = text.replace(phrase, "")
    return text.strip()


def _extract_content(page, url: str) -> dict:
    """
    Extract structured content from a Scrapling page response.
    
    Returns:
        {
            "url": str,
            "title": str,
            "content": str (cleaned text),
            "content_length": int,
            "headings": list[str],
            "code_blocks": list[str],
        }
    """
    selectors = _get_selectors(url)
    
    # Extract title
    title_sel = selectors.get("title", "h1::text, title::text")
    title = page.css(title_sel).get() or ""
    title = title.strip()
    
    # Extract headings for structure
    headings = page.css("h1::text, h2::text, h3::text").getall()
    headings = [h.strip() for h in headings if h.strip()][:20]
    
    # Extract code blocks (valuable for technical docs)
    code_blocks = page.css("pre::text, code::text").getall()
    code_blocks = [c.strip() for c in code_blocks if len(c.strip()) > 20][:10]
    
    # Extract main content — try ::text pseudo-element first
    content_sel = selectors.get("content", GENERIC_SELECTORS["content"])
    content_parts = page.css(f"{content_sel}::text").getall()
    
    # If ::text returned nothing or HTML-tagged content, extract text from elements
    if not content_parts or len(" ".join(content_parts)) < 100 or "<" in " ".join(content_parts)[:200]:
        # Try getting elements and extracting their text
        elements = page.css(content_sel)
        if hasattr(elements, '__iter__'):
            content_parts = []
            for el in elements:
                txt = el.text if hasattr(el, 'text') else ""
                if txt and txt.strip():
                    # Strip HTML tags
                    clean = re.sub(r'<[^>]+>', ' ', str(txt)).strip()
                    if clean:
                        content_parts.append(clean)
    
    # Last resort: get all text from body
    if not content_parts or len(" ".join(content_parts)) < 100:
        body = page.css("body")
        if body:
            body_text = body.get() if hasattr(body, 'get') else str(body)
            body_text = re.sub(r'<script[^>]*>.*?</script>', '', body_text, flags=re.DOTALL)
            body_text = re.sub(r'<style[^>]*>.*?</style>', '', body_text, flags=re.DOTALL)
            body_text = re.sub(r'<[^>]+>', ' ', body_text)
            content_parts = [body_text]
    
    # Clean and join
    raw_content = " ".join(content_parts)
    content = _clean_text(raw_content)
    
    # Truncate to max length
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "... [truncated]"
    
    return {
        "url": url,
        "title": title,
        "content": content,
        "content_length": len(content),
        "headings": headings,
        "code_blocks": code_blocks[:5],  # Keep top 5 code blocks
    }


def fetch_page(url: str, timeout: int = FETCH_TIMEOUT, allow_browser: bool = True) -> Optional[dict]:
    """
    Fetch a single page and extract its content.
    
    Strategy:
    1. Skip search engine domains entirely
    2. Use browser directly for JS-heavy / anti-bot sites
    3. Try Scrapling first for others, fallback to browser if blocked
    
    Args:
        url: Page URL to fetch
        timeout: Timeout in seconds for Scrapling (browser uses 30s)
        allow_browser: Allow stealth browser fallback (True default)
    
    Returns:
        Content dict or None if fetch failed.
    """
    # Global rate limiting
    try:
        from utils.rate_limiter import wait_for_slot
        if not wait_for_slot("fetch", timeout=30):
            logger.warning(f"Rate limited, skipping fetch for {url}")
            return None
    except ImportError:
        pass

    if _should_skip(url):
        logger.debug(f"Skipping {url} (search engine)")
        return None
    
    # For browser-required domains, go straight to browser
    if _needs_browser(url):
        if allow_browser:
            logger.info(f"Using browser for {url} (JS/anti-bot domain)")
            return _browser_fetch_sync(url)
        else:
            logger.debug(f"Skipping {url} (needs browser but disabled)")
            return None
    
    # Try Scrapling first
    Fetcher = _get_fetcher()
    scrapling_failed = False
    
    if Fetcher:
        try:
            page = Fetcher.get(
                url,
                stealthy_headers=True,
                timeout=timeout,
                follow_redirects=True,
            )
            
            if page.status == 200:
                result = _extract_content(page, url)
                if result and result.get("content_length", 0) > 100:
                    result["source"] = "scrapling"
                    return result
                else:
                    scrapling_failed = True
                    logger.debug(f"Scrapling returned empty content for {url}")
            elif page.status in (403, 429, 503):
                # Blocked — try browser
                scrapling_failed = True
                logger.debug(f"Blocked ({page.status}) for {url}, will try browser")
            else:
                logger.debug(f"Non-200 status ({page.status}) for {url}")
                return None
                
        except Exception as e:
            scrapling_failed = True
            logger.debug(f"Scrapling failed for {url}: {e}")
    else:
        scrapling_failed = True
    
    # Try browser fallback if Scrapling failed and it's a fallback-eligible domain
    if scrapling_failed and allow_browser and (_is_fallback_domain(url) or Fetcher is None):
        logger.info(f"Trying browser fallback for {url}")
        return _browser_fetch_sync(url)
    
    return None


def fetch_pages(urls: list[str], max_pages: int = MAX_PAGES_PER_CYCLE) -> list[dict]:
    """
    Fetch multiple pages, respecting limits.
    
    Filters out skip-domains, deduplicates, fetches up to max_pages.
    Returns list of content dicts.
    """
    # Deduplicate and filter
    seen = set()
    filtered = []
    for url in urls:
        if url not in seen and not _should_skip(url):
            seen.add(url)
            filtered.append(url)
    
    results = []
    for url in filtered[:max_pages]:
        result = fetch_page(url)
        if result and result["content_length"] > 100:
            results.append(result)
            logger.info(f"Fetched {url} — {result['content_length']} chars")
        else:
            logger.debug(f"Skipped {url} — insufficient content")
    
    return results


def search_and_fetch(query: str, max_results: int = 5, max_fetch: int = MAX_PAGES_PER_CYCLE) -> dict:
    """
    Combined search + fetch pipeline.
    
    1. DuckDuckGo search to find URLs  
    2. Scrapling fetches top pages
    3. Returns both snippets and full content
    
    Returns:
        {
            "query": str,
            "search_results": list[dict],  # Original DuckDuckGo results
            "fetched_pages": list[dict],    # Full page content
            "total_content_chars": int,
        }
    """
    from tools.web_search import web_search
    
    # Step 1: Search
    search_results = web_search(query, max_results=max_results)
    
    # Step 2: Extract URLs worth fetching
    urls = [r["url"] for r in search_results if r.get("url") and not r.get("error")]
    
    # Step 3: Fetch top pages
    fetched = fetch_pages(urls, max_pages=max_fetch)
    
    total_chars = sum(p["content_length"] for p in fetched)
    
    return {
        "query": query,
        "search_results": search_results,
        "fetched_pages": fetched,
        "total_content_chars": total_chars,
    }


def crawl_docs_site(
    start_url: str,
    max_pages: int = 20,
    url_pattern: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> list[dict]:
    """
    Crawl a documentation site starting from a URL.
    
    Follows internal links matching url_pattern (or same domain).
    Returns list of page content dicts.
    
    Args:
        start_url: Starting URL to crawl from
        max_pages: Maximum pages to crawl
        url_pattern: Regex pattern for URLs to follow (default: same domain)
        output_dir: Optional directory to save crawled content as JSON
    """
    import json
    from collections import deque
    
    Fetcher = _get_fetcher()
    if not Fetcher:
        return []
    
    domain = urlparse(start_url).netloc
    if not url_pattern:
        url_pattern = re.escape(domain)
    
    visited = set()
    queue = deque([start_url])
    results = []
    
    while queue and len(results) < max_pages:
        url = queue.popleft()
        
        if url in visited:
            continue
        visited.add(url)
        
        # Fetch page ONCE — extract both content and links from same response
        try:
            page = Fetcher.get(url, stealthy_headers=True, timeout=15, follow_redirects=True)
            if page.status != 200:
                continue
        except Exception as e:
            logger.debug(f"Crawl fetch failed for {url}: {e}")
            continue
        
        # Extract content
        content = _extract_content(page, url)
        if not content or content["content_length"] < 50:
            continue
        
        results.append(content)
        logger.info(f"Crawled [{len(results)}/{max_pages}] {url} — {content['content_length']} chars")
        
        # Extract links from the SAME page object (no double-fetch)
        try:
            links = page.css("a::attr(href)").getall()
            
            for link in links:
                # Resolve relative URLs
                if link.startswith("/"):
                    link = f"https://{domain}{link}"
                elif not link.startswith("http"):
                    continue
                
                # Check if link matches pattern and hasn't been visited
                if re.search(url_pattern, link) and link not in visited:
                    # Skip anchors, query params for dedup
                    clean = link.split("#")[0].split("?")[0].rstrip("/")
                    if clean not in visited:
                        queue.append(clean)
        except Exception as e:
            logger.debug(f"Link extraction failed for {url}: {e}")
    
    # Save to disk if output_dir specified
    if output_dir and results:
        import os
        from utils.atomic_write import atomic_json_write
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"crawl_{domain.replace('.', '_')}.json")
        atomic_json_write(output_path, {
            "domain": domain,
            "start_url": start_url,
            "pages_crawled": len(results),
            "total_chars": sum(r["content_length"] for r in results),
            "pages": results,
        })
        logger.info(f"Saved crawl to {output_path}")
    
    return results


# --- Claude tool definition for researcher agent ---
FETCH_TOOL_DEFINITION = {
    "name": "fetch_page",
    "description": "Fetch and read the full content of a web page. Use this AFTER web_search to read the actual content of promising URLs. Returns the page title, full text content, headings, and code blocks. Much more detailed than search snippets.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch (must start with http:// or https://)",
            },
        },
        "required": ["url"],
    },
}

SEARCH_AND_FETCH_TOOL_DEFINITION = {
    "name": "search_and_fetch",
    "description": "Search the web AND read the top results in one step. Combines web_search with page fetching. Returns both search snippets and full page content of the top results. Use SHORT, FOCUSED queries (3-6 words) — same rules as web_search.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Short focused search query (3-6 words ideal). Do NOT use the full research question as the query — break it into targeted sub-queries.",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of search results to return (default 5)",
                "default": 5,
            },
            "max_fetch": {
                "type": "integer",
                "description": "Number of top pages to fetch full content from (default 3, max 5)",
                "default": 3,
            },
        },
        "required": ["query"],
    },
}
