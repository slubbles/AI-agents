"""
Stealth Browser Engine — Playwright + anti-detection.

Core browser management: launch, configure stealth, manage contexts.
Each "profile" gets its own persistent context (cookies, localStorage, etc.)
stored in browser/_profiles/<profile_name>/.
"""

import asyncio
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)
from playwright_stealth import Stealth

# Singleton stealth config
_stealth = Stealth()

logger = logging.getLogger(__name__)

# Directories
BROWSER_DIR = os.path.dirname(__file__)
PROFILES_DIR = os.path.join(BROWSER_DIR, "_profiles")

# Human-like timing ranges (seconds)
TYPING_DELAY_MIN = 0.05
TYPING_DELAY_MAX = 0.15
CLICK_DELAY_MIN = 0.1
CLICK_DELAY_MAX = 0.5
SCROLL_DELAY_MIN = 0.3
SCROLL_DELAY_MAX = 1.2
PAGE_LOAD_WAIT_MIN = 1.0
PAGE_LOAD_WAIT_MAX = 3.0

# Viewport presets (common screen resolutions)
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
    {"width": 2560, "height": 1440},
]

# User agents — modern Chrome on various OS
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Timezone/locale pairs for consistency
LOCALES = [
    {"timezone": "America/New_York", "locale": "en-US"},
    {"timezone": "America/Chicago", "locale": "en-US"},
    {"timezone": "America/Los_Angeles", "locale": "en-US"},
    {"timezone": "Europe/London", "locale": "en-GB"},
]


class StealthBrowser:
    """Playwright browser with anti-detection and persistent profiles.
    
    Usage:
        async with StealthBrowser(profile="linkedin") as browser:
            page = await browser.new_page()
            await browser.navigate(page, "https://linkedin.com")
            content = await browser.extract_text(page)
    """

    def __init__(
        self,
        profile: str = "default",
        headless: bool = True,
        proxy: Optional[str] = None,
        slow_mo: int = 0,
    ):
        self.profile = profile
        self.headless = headless
        self.proxy = proxy
        self.slow_mo = slow_mo
        
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._profile_dir = os.path.join(PROFILES_DIR, profile)
        
        # Random but consistent fingerprint for this profile
        self._viewport = random.choice(VIEWPORTS)
        self._user_agent = random.choice(USER_AGENTS)
        self._locale_info = random.choice(LOCALES)

    async def __aenter__(self):
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ── Lifecycle ────────────────────────────────────────────

    async def launch(self) -> None:
        """Launch browser with stealth configuration."""
        os.makedirs(self._profile_dir, exist_ok=True)

        self._playwright = await async_playwright().start()
        
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        launch_kwargs = {
            "headless": self.headless,
            "args": launch_args,
            "slow_mo": self.slow_mo,
        }

        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        
        # Persistent context preserves cookies/localStorage across sessions
        context_kwargs = {
            "viewport": self._viewport,
            "user_agent": self._user_agent,
            "locale": self._locale_info["locale"],
            "timezone_id": self._locale_info["timezone"],
            "color_scheme": "light",
            "has_touch": False,
            "is_mobile": False,
            "java_script_enabled": True,
            "accept_downloads": False,
            "ignore_https_errors": False,
        }

        # Load saved storage state if it exists
        storage_file = os.path.join(self._profile_dir, "storage.json")
        if os.path.exists(storage_file):
            context_kwargs["storage_state"] = storage_file
            logger.info(f"Loaded saved session for profile '{self.profile}'")

        self._context = await self._browser.new_context(**context_kwargs)
        
        # Block unnecessary resource types for speed
        await self._context.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf}", 
                                   lambda route: route.abort())

        logger.info(f"Stealth browser launched (profile={self.profile}, headless={self.headless})")

    async def close(self) -> None:
        """Save state and close browser."""
        if self._context:
            try:
                await self.save_session()
            except Exception as e:
                logger.warning(f"Failed to save session: {e}")
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info(f"Stealth browser closed (profile={self.profile})")

    async def save_session(self) -> None:
        """Save cookies and localStorage for future sessions."""
        if self._context:
            storage_file = os.path.join(self._profile_dir, "storage.json")
            await self._context.storage_state(path=storage_file)
            logger.debug(f"Session saved: {storage_file}")

    # ── Page Management ──────────────────────────────────────

    async def new_page(self) -> Page:
        """Create a new stealth page."""
        if not self._context:
            raise RuntimeError("Browser not launched. Call launch() first.")
        page = await self._context.new_page()
        await _stealth.apply_stealth_async(page)
        return page

    async def navigate(
        self, 
        page: Page, 
        url: str, 
        wait_until: str = "domcontentloaded",
        timeout: int = 30000,
    ) -> bool:
        """Navigate to URL with human-like behavior.
        
        Returns True if navigation succeeded.
        """
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            await self._human_wait()
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {url} — {e}")
            return False

    # ── Human-Like Actions ──────────────────────────────────

    async def _human_wait(self) -> None:
        """Wait a random human-like duration."""
        delay = random.uniform(PAGE_LOAD_WAIT_MIN, PAGE_LOAD_WAIT_MAX)
        await asyncio.sleep(delay)

    async def human_type(self, page: Page, selector: str, text: str) -> None:
        """Type text with realistic per-character delays."""
        await page.click(selector)
        await asyncio.sleep(random.uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))
        
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX))

    async def human_click(self, page: Page, selector: str) -> None:
        """Click with a small random delay."""
        await asyncio.sleep(random.uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))
        await page.click(selector)
        await asyncio.sleep(random.uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))

    async def human_scroll(self, page: Page, distance: int = 300) -> None:
        """Scroll with realistic behavior."""
        current = 0
        while current < distance:
            step = random.randint(50, 150)
            await page.mouse.wheel(0, step)
            current += step
            await asyncio.sleep(random.uniform(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX))

    async def random_mouse_movement(self, page: Page) -> None:
        """Move mouse to a random position (creates realistic fingerprint)."""
        vp = self._viewport
        x = random.randint(100, vp["width"] - 100)
        y = random.randint(100, vp["height"] - 100)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.3))

    # ── Content Extraction ──────────────────────────────────

    async def extract_text(self, page: Page, selector: str = "body") -> str:
        """Extract visible text content from page."""
        try:
            return await page.inner_text(selector, timeout=10000)
        except Exception:
            # Fallback: get all text
            return await page.evaluate("() => document.body.innerText") or ""

    async def extract_html(self, page: Page, selector: str = "body") -> str:
        """Extract HTML content."""
        try:
            return await page.inner_html(selector, timeout=10000)
        except Exception:
            return await page.content()

    async def extract_links(self, page: Page) -> list[dict]:
        """Extract all links from page."""
        return await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim().slice(0, 200),
                href: a.href,
            })).filter(l => l.href.startsWith('http'))
        """)

    async def extract_structured(self, page: Page) -> dict:
        """Extract structured content (title, headings, paragraphs, links)."""
        return await page.evaluate("""
            () => {
                const title = document.title || '';
                const headings = Array.from(document.querySelectorAll('h1,h2,h3')).map(h => ({
                    level: h.tagName,
                    text: h.innerText.trim().slice(0, 300),
                }));
                const paragraphs = Array.from(document.querySelectorAll('p')).map(p => 
                    p.innerText.trim()
                ).filter(t => t.length > 20);
                const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim().slice(0, 100),
                    href: a.href,
                })).filter(l => l.href.startsWith('http')).slice(0, 50);
                
                return { title, headings, paragraphs, links };
            }
        """)

    async def screenshot(self, page: Page, path: Optional[str] = None) -> bytes:
        """Take a screenshot (useful for debugging)."""
        if path is None:
            path = os.path.join(self._profile_dir, "screenshot.png")
        return await page.screenshot(path=path, full_page=False)

    # ── Wait Utilities ──────────────────────────────────────

    async def wait_for_selector(
        self, page: Page, selector: str, timeout: int = 10000
    ) -> bool:
        """Wait for a selector to appear. Returns True if found."""
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def wait_for_navigation(self, page: Page, timeout: int = 30000) -> bool:
        """Wait for navigation to complete."""
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)
            return True
        except Exception:
            return False

    # ── Cookie Management ────────────────────────────────────

    async def get_cookies(self, urls: Optional[list[str]] = None) -> list[dict]:
        """Get cookies, optionally filtered by URL."""
        if not self._context:
            return []
        return await self._context.cookies(urls or [])

    async def add_cookies(self, cookies: list[dict]) -> None:
        """Add cookies to the browser context."""
        if self._context:
            await self._context.add_cookies(cookies)

    async def clear_cookies(self) -> None:
        """Clear all cookies."""
        if self._context:
            await self._context.clear_cookies()

    # ── Detection Testing ────────────────────────────────────

    async def check_detection(self, page: Page) -> dict:
        """Run detection tests to see if the browser is flagged.
        
        Checks common bot-detection vectors.
        Returns dict of detection results.
        """
        results = await page.evaluate("""
            () => {
                return {
                    webdriver: navigator.webdriver,
                    languages: navigator.languages,
                    plugins_count: navigator.plugins.length,
                    platform: navigator.platform,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    vendor: navigator.vendor,
                    chrome_runtime: typeof window.chrome !== 'undefined',
                    notification_permission: typeof Notification !== 'undefined' ? Notification.permission : 'N/A',
                };
            }
        """)
        
        # Ideal: webdriver should be false/undefined
        results["stealth_ok"] = results.get("webdriver") in (False, None, "undefined")
        return results
