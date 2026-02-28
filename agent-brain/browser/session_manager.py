"""
Browser Session Manager — Orchestrates stealth browser + auth + vault.

High-level interface for Agent Brain to:
1. Open authenticated browser sessions
2. Fetch pages requiring JavaScript or login
3. Manage persistent sessions across runs

This is what the researcher agent calls.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional, TYPE_CHECKING
from urllib.parse import urlparse

from browser.stealth_browser import StealthBrowser
from browser.auth import get_authenticator, AuthError

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Sites that require authentication for useful data
AUTH_REQUIRED_DOMAINS = {
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "github.com",  # private repos only
    "angel.co",
    "wellfound.com",
}

# Sites that need JS rendering but not auth
JS_REQUIRED_DOMAINS = {
    "medium.com",
    "substack.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "nytimes.com",
    "reddit.com",
    "twitter.com",
    "x.com",
    "notion.so",
    "airtable.com",
    "stackoverflow.com",
}


class BrowserSession:
    """High-level browser session with automatic auth management.
    
    Usage:
        session = BrowserSession(vault=my_vault)
        result = await session.fetch("https://linkedin.com/in/someone")
        # Automatically: detects auth needed → retrieves creds → logs in → fetches
    """

    def __init__(self, vault=None, headless: bool = True, proxy: Optional[str] = None):
        """
        Args:
            vault: CredentialVault instance (unlocked). If None, auth features disabled.
            headless: Run browser headless (True) or visible (False for debugging)
            proxy: Optional proxy URL (e.g. "http://user:pass@proxy:8080")
        """
        self.vault = vault
        self.headless = headless
        self.proxy = proxy
        self._browsers: dict[str, StealthBrowser] = {}  # profile -> browser

    async def fetch(
        self,
        url: str,
        extract_mode: str = "text",  # "text", "html", "structured", "links"
        require_auth: bool = False,
        timeout: int = 30000,
    ) -> dict:
        """Fetch a URL with appropriate browser configuration.
        
        Auto-detects if JS or auth is needed.
        Returns dict with {url, content, title, success, error?}.
        """
        domain = self._extract_domain(url)
        needs_auth = require_auth or domain in AUTH_REQUIRED_DOMAINS
        
        profile = domain.replace(".", "_") if needs_auth else "default"
        
        try:
            browser = await self._get_browser(profile)
            page = await browser.new_page()

            try:
                # Handle auth if needed
                if needs_auth:
                    logged_in = await self._ensure_logged_in(browser, page, domain)
                    if not logged_in:
                        return {
                            "url": url,
                            "content": "",
                            "title": "",
                            "success": False,
                            "error": f"Authentication failed for {domain}",
                        }

                # Navigate to target URL
                success = await browser.navigate(page, url, timeout=timeout)
                if not success:
                    return {
                        "url": url,
                        "content": "",
                        "title": "",
                        "success": False,
                        "error": "Navigation failed",
                    }

                # Extract content
                title = await page.title()
                content = await self._extract(page, extract_mode)

                return {
                    "url": url,
                    "content": content,
                    "title": title,
                    "success": True,
                    "domain": domain,
                    "extract_mode": extract_mode,
                    "char_count": len(content),
                }

            finally:
                await page.close()

        except Exception as e:
            logger.error(f"Browser fetch failed: {url} — {e}")
            return {
                "url": url,
                "content": "",
                "title": "",
                "success": False,
                "error": str(e),
            }

    async def fetch_multiple(
        self,
        urls: list[str],
        extract_mode: str = "text",
        max_concurrent: int = 3,
    ) -> list[dict]:
        """Fetch multiple URLs with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _fetch_one(url: str) -> dict:
            async with semaphore:
                return await self.fetch(url, extract_mode=extract_mode)

        return await asyncio.gather(*[_fetch_one(url) for url in urls])

    async def search_and_fetch(
        self,
        query: str,
        site: Optional[str] = None,
        max_results: int = 5,
    ) -> list[dict]:
        """Search within a site and fetch results.
        
        Example: search_and_fetch("python developer", site="linkedin.com")
        """
        # Build search URL
        search_query = f"{query} site:{site}" if site else query
        search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
        
        browser = await self._get_browser("search")
        page = await browser.new_page()

        try:
            await browser.navigate(page, search_url)
            await asyncio.sleep(2)

            # Extract search result links
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(h => h.startsWith('http') && !h.includes('google.com'))
                    .slice(0, arguments[0] || 10)
            """)

            # Filter to site if specified
            if site:
                links = [l for l in links if site in l]

            links = links[:max_results]
            
        finally:
            await page.close()

        # Fetch each result
        if links:
            return await self.fetch_multiple(links)
        return []

    # ── Internal ─────────────────────────────────────────────

    async def _get_browser(self, profile: str) -> StealthBrowser:
        """Get or create a browser instance for the given profile."""
        if profile not in self._browsers:
            browser = StealthBrowser(
                profile=profile,
                headless=self.headless,
                proxy=self.proxy,
            )
            await browser.launch()
            self._browsers[profile] = browser
        return self._browsers[profile]

    async def _ensure_logged_in(
        self, browser: StealthBrowser, page: Page, domain: str
    ) -> bool:
        """Check if logged in; if not, attempt login using vault credentials."""
        # Check existing session
        auth = get_authenticator(domain, browser)
        
        # Navigate to site root to check session
        await browser.navigate(page, f"https://www.{domain}")
        if await auth.is_logged_in(page, domain):
            logger.info(f"Already logged in to {domain}")
            return True

        # Need to log in — get credentials from vault
        if not self.vault:
            logger.error(f"No vault configured — cannot authenticate to {domain}")
            return False

        vault_key = domain.replace(".", "_")  # e.g. "linkedin_com"
        try:
            creds = self.vault.retrieve(vault_key)
        except KeyError:
            logger.error(f"No credentials in vault for '{vault_key}'")
            return False

        if not isinstance(creds, dict):
            logger.error(f"Credentials for '{vault_key}' must be a dict with email/password")
            return False

        # Attempt login
        try:
            success = await auth.login(page, creds)
            if success:
                logger.info(f"Successfully logged in to {domain}")
                await browser.save_session()
            else:
                logger.warning(f"Login to {domain} returned False (possible challenge)")
            return success
        except AuthError as e:
            logger.error(f"Auth error for {domain}: {e}")
            return False

    async def _extract(self, page, mode: str) -> str:
        """Extract content based on mode."""
        browser = None
        for b in self._browsers.values():
            browser = b
            break
        
        if not browser:
            return await page.inner_text("body")

        if mode == "text":
            return await browser.extract_text(page)
        elif mode == "html":
            return await browser.extract_html(page)
        elif mode == "structured":
            import json
            data = await browser.extract_structured(page)
            return json.dumps(data, indent=2)
        elif mode == "links":
            import json
            links = await browser.extract_links(page)
            return json.dumps(links, indent=2)
        else:
            return await browser.extract_text(page)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    async def close_all(self) -> None:
        """Close all browser instances."""
        for browser in self._browsers.values():
            await browser.close()
        self._browsers.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close_all()


# ── Synchronous Wrapper ─────────────────────────────────────

def fetch_with_browser(
    url: str,
    vault=None,
    headless: bool = True,
    extract_mode: str = "text",
) -> dict:
    """Synchronous wrapper for browser fetch.
    
    For use in non-async code (e.g., researcher agent).
    """
    async def _run():
        async with BrowserSession(vault=vault, headless=headless) as session:
            return await session.fetch(url, extract_mode=extract_mode)
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in an async context — create a new one
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(_run())
    except RuntimeError:
        return asyncio.run(_run())


def fetch_multiple_with_browser(
    urls: list[str],
    vault=None,
    headless: bool = True,
    extract_mode: str = "text",
    max_concurrent: int = 3,
) -> list[dict]:
    """Synchronous wrapper for multiple browser fetches."""
    async def _run():
        async with BrowserSession(vault=vault, headless=headless) as session:
            return await session.fetch_multiple(urls, extract_mode, max_concurrent)
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result(timeout=120)
        else:
            return loop.run_until_complete(_run())
    except RuntimeError:
        return asyncio.run(_run())
