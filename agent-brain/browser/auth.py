"""
Site Authenticators — Login flows for specific sites.

Each authenticator handles the login sequence for one site/service.
Credentials are retrieved from the vault (never hardcoded).

Supported sites:
- LinkedIn (email/password login)
- Indeed (email/password login) 
- GitHub (email/password + optional 2FA)
- Generic (email/password form detection)
"""

import asyncio
import logging
import os
import re
from typing import Optional

from playwright.async_api import Page

from browser.stealth_browser import StealthBrowser

logger = logging.getLogger(__name__)

# Login detection patterns
LOGIN_SUCCESS_INDICATORS = {
    "linkedin.com": [
        "feed",
        "mynetwork",
        "/in/",
        "nav[class*='global-nav']",
    ],
    "indeed.com": [
        "my.indeed.com",
        "myjobs",
        "/viewjob",
    ],
    "github.com": [
        "dashboard",
        "[aria-label='Global']",
        "octicon-mark-github",
    ],
}


class AuthError(Exception):
    """Authentication failed."""
    pass


class SiteAuthenticator:
    """Base authenticator — handles generic email/password forms."""

    def __init__(self, browser: StealthBrowser):
        self.browser = browser

    async def login(self, page: Page, credentials: dict) -> bool:
        """Generic login — find email/password fields and submit.
        
        Args:
            page: Page already navigated to login URL
            credentials: dict with "email" and "password" keys
            
        Returns:
            True if login appears successful
        """
        email = credentials.get("email", "")
        password = credentials.get("password", "")

        if not email or not password:
            raise AuthError("Credentials must include 'email' and 'password'")

        # Find email field
        email_sel = await self._find_input(page, ["email", "username", "login", "user"])
        if not email_sel:
            raise AuthError("Could not find email/username input field")

        # Find password field
        pwd_sel = await self._find_input(page, ["password", "pass", "pwd"], input_type="password")
        if not pwd_sel:
            raise AuthError("Could not find password input field")

        # Type credentials with human-like timing
        await self.browser.human_type(page, email_sel, email)
        await asyncio.sleep(0.5)
        await self.browser.human_type(page, pwd_sel, password)
        await asyncio.sleep(0.3)

        # Find and click submit button
        submit_sel = await self._find_submit(page)
        if submit_sel:
            await self.browser.human_click(page, submit_sel)
        else:
            # Fallback: press Enter
            await page.keyboard.press("Enter")

        # Wait for navigation
        await asyncio.sleep(3)
        await self.browser.wait_for_navigation(page)
        
        return True

    async def _find_input(
        self, 
        page: Page, 
        keywords: list[str], 
        input_type: Optional[str] = None,
    ) -> Optional[str]:
        """Find an input field by type, name, id, or placeholder attributes."""
        # Try by type first
        if input_type:
            sel = f'input[type="{input_type}"]'
            if await page.query_selector(sel):
                return sel

        # Try by name/id/placeholder
        for kw in keywords:
            for attr in ["name", "id", "placeholder", "aria-label", "autocomplete"]:
                sel = f'input[{attr}*="{kw}" i]'
                try:
                    if await page.query_selector(sel):
                        return sel
                except Exception:
                    continue

        return None

    async def _find_submit(self, page: Page) -> Optional[str]:
        """Find the submit/login button."""
        selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Submit")',
            'a:has-text("Sign in")',
        ]
        for sel in selectors:
            try:
                if await page.query_selector(sel):
                    return sel
            except Exception:
                continue
        return None

    async def is_logged_in(self, page: Page, domain: str) -> bool:
        """Check if currently logged in based on page indicators."""
        url = page.url
        indicators = LOGIN_SUCCESS_INDICATORS.get(domain, [])
        
        for indicator in indicators:
            if indicator in url:
                return True
            try:
                if await page.query_selector(indicator):
                    return True
            except Exception:
                continue

        return False


class LinkedInAuth(SiteAuthenticator):
    """LinkedIn-specific login flow."""

    LOGIN_URL = "https://www.linkedin.com/login"
    
    async def login(self, page: Page, credentials: dict) -> bool:
        """LinkedIn login with specific selectors."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")

        if not email or not password:
            raise AuthError("LinkedIn credentials must include 'email' and 'password'")

        # Navigate to login page
        await self.browser.navigate(page, self.LOGIN_URL)
        await asyncio.sleep(2)

        # LinkedIn-specific selectors
        await self.browser.human_type(page, "#username", email)
        await asyncio.sleep(0.8)
        await self.browser.human_type(page, "#password", password)
        await asyncio.sleep(0.5)

        # Random mouse movement before clicking
        await self.browser.random_mouse_movement(page)
        await asyncio.sleep(0.3)

        # Click sign-in button
        await self.browser.human_click(page, 'button[type="submit"]')
        
        # Wait for redirect
        await asyncio.sleep(4)

        # Check for challenges (CAPTCHA, verification)
        challenge = await self._check_challenge(page)
        if challenge:
            logger.warning(f"LinkedIn challenge detected: {challenge}")
            return False

        # Verify login
        return await self.is_logged_in(page, "linkedin.com")

    async def _check_challenge(self, page: Page) -> Optional[str]:
        """Detect LinkedIn security challenges."""
        url = page.url
        
        if "checkpoint" in url:
            return "security_checkpoint"
        if "challenge" in url:
            return "challenge"
        
        # Check for CAPTCHA
        captcha_sels = [
            'iframe[src*="captcha"]',
            '#captcha',
            '.challenge-dialog',
        ]
        for sel in captcha_sels:
            try:
                if await page.query_selector(sel):
                    return "captcha"
            except Exception:
                continue

        return None


class IndeedAuth(SiteAuthenticator):
    """Indeed-specific login flow."""

    LOGIN_URL = "https://secure.indeed.com/auth"

    async def login(self, page: Page, credentials: dict) -> bool:
        email = credentials.get("email", "")
        password = credentials.get("password", "")

        await self.browser.navigate(page, self.LOGIN_URL)
        await asyncio.sleep(2)

        # Indeed uses a multi-step login (email first, then password)
        email_sel = 'input[name="__email"]'
        if not await page.query_selector(email_sel):
            email_sel = 'input[type="email"]'

        await self.browser.human_type(page, email_sel, email)
        await self.browser.human_click(page, 'button[type="submit"]')
        await asyncio.sleep(3)

        # Password step
        pwd_sel = 'input[type="password"]'
        await self.browser.wait_for_selector(page, pwd_sel, timeout=10000)
        await self.browser.human_type(page, pwd_sel, password)
        await self.browser.human_click(page, 'button[type="submit"]')
        await asyncio.sleep(4)

        return await self.is_logged_in(page, "indeed.com")


class GitHubAuth(SiteAuthenticator):
    """GitHub login — supports 2FA via TOTP."""

    LOGIN_URL = "https://github.com/login"

    async def login(self, page: Page, credentials: dict) -> bool:
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        totp_secret = credentials.get("totp_secret")  # Optional

        await self.browser.navigate(page, self.LOGIN_URL)
        await asyncio.sleep(2)

        await self.browser.human_type(page, "#login_field", email)
        await asyncio.sleep(0.5)
        await self.browser.human_type(page, "#password", password)
        await asyncio.sleep(0.3)
        await self.browser.human_click(page, 'input[type="submit"]')
        await asyncio.sleep(3)

        # Check for 2FA
        if totp_secret and "two-factor" in page.url:
            try:
                import pyotp
                totp = pyotp.TOTP(totp_secret)
                code = totp.now()
                await self.browser.human_type(page, "#app_totp", code)
                await page.keyboard.press("Enter")
                await asyncio.sleep(3)
            except ImportError:
                logger.warning("pyotp not installed — cannot handle 2FA")
                return False

        return await self.is_logged_in(page, "github.com")


# ── Factory ─────────────────────────────────────────────────

AUTHENTICATORS = {
    "linkedin.com": LinkedInAuth,
    "indeed.com": IndeedAuth,
    "github.com": GitHubAuth,
}


def get_authenticator(domain: str, browser: StealthBrowser) -> SiteAuthenticator:
    """Get the appropriate authenticator for a domain."""
    for key, cls in AUTHENTICATORS.items():
        if key in domain:
            return cls(browser)
    return SiteAuthenticator(browser)  # Generic fallback
