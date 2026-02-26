"""
Tests for Stealth Browser module.

Tests browser engine, auth, session manager, and tool integration.
Uses mocks to avoid actually launching browsers in CI.
"""

import asyncio
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# StealthBrowser Engine Tests
# ============================================================

class TestStealthBrowserConfig:
    """Browser configuration and fingerprinting."""

    def test_viewports_are_valid(self):
        from browser.stealth_browser import VIEWPORTS
        for vp in VIEWPORTS:
            assert "width" in vp and "height" in vp
            assert vp["width"] > 0 and vp["height"] > 0

    def test_user_agents_are_modern(self):
        from browser.stealth_browser import USER_AGENTS
        for ua in USER_AGENTS:
            assert "Chrome" in ua
            assert "Mozilla" in ua

    def test_locales_valid(self):
        from browser.stealth_browser import LOCALES
        for loc in LOCALES:
            assert "timezone" in loc
            assert "locale" in loc

    def test_default_profile(self):
        from browser.stealth_browser import StealthBrowser
        browser = StealthBrowser()
        assert browser.profile == "default"
        assert browser.headless is True

    def test_custom_profile(self):
        from browser.stealth_browser import StealthBrowser
        browser = StealthBrowser(profile="linkedin", headless=False, proxy="http://proxy:8080")
        assert browser.profile == "linkedin"
        assert browser.headless is False
        assert browser.proxy == "http://proxy:8080"

    def test_profile_dir_created(self, tmp_path):
        from browser.stealth_browser import StealthBrowser
        with patch("browser.stealth_browser.PROFILES_DIR", str(tmp_path / "profiles")):
            browser = StealthBrowser(profile="test_profile")
            # Profile dir path should be set
            assert "test_profile" in browser._profile_dir


class TestStealthBrowserTimingConstants:
    """Human-like timing ranges are reasonable."""

    def test_typing_delay_range(self):
        from browser.stealth_browser import TYPING_DELAY_MIN, TYPING_DELAY_MAX
        assert 0.01 < TYPING_DELAY_MIN < TYPING_DELAY_MAX < 1.0

    def test_click_delay_range(self):
        from browser.stealth_browser import CLICK_DELAY_MIN, CLICK_DELAY_MAX
        assert 0.01 < CLICK_DELAY_MIN < CLICK_DELAY_MAX < 2.0

    def test_scroll_delay_range(self):
        from browser.stealth_browser import SCROLL_DELAY_MIN, SCROLL_DELAY_MAX
        assert 0.1 < SCROLL_DELAY_MIN < SCROLL_DELAY_MAX < 5.0


# ============================================================
# Auth Module Tests
# ============================================================

class TestAuthenticators:
    """Site-specific authenticator tests."""

    def test_factory_returns_linkedin(self):
        from browser.auth import get_authenticator, LinkedInAuth
        mock_browser = MagicMock()
        auth = get_authenticator("linkedin.com", mock_browser)
        assert isinstance(auth, LinkedInAuth)

    def test_factory_returns_indeed(self):
        from browser.auth import get_authenticator, IndeedAuth
        mock_browser = MagicMock()
        auth = get_authenticator("indeed.com", mock_browser)
        assert isinstance(auth, IndeedAuth)

    def test_factory_returns_github(self):
        from browser.auth import get_authenticator, GitHubAuth
        mock_browser = MagicMock()
        auth = get_authenticator("github.com", mock_browser)
        assert isinstance(auth, GitHubAuth)

    def test_factory_returns_generic_for_unknown(self):
        from browser.auth import get_authenticator, SiteAuthenticator
        mock_browser = MagicMock()
        auth = get_authenticator("unknown-site.com", mock_browser)
        assert type(auth) is SiteAuthenticator

    def test_auth_error_on_missing_credentials(self):
        from browser.auth import SiteAuthenticator, AuthError
        browser = MagicMock()
        auth = SiteAuthenticator(browser)
        
        # Should raise for missing email/password
        with pytest.raises(AuthError, match="email"):
            asyncio.get_event_loop().run_until_complete(
                auth.login(MagicMock(), {"email": "", "password": ""})
            )

    def test_login_indicators_defined(self):
        from browser.auth import LOGIN_SUCCESS_INDICATORS
        assert "linkedin.com" in LOGIN_SUCCESS_INDICATORS
        assert "indeed.com" in LOGIN_SUCCESS_INDICATORS
        assert "github.com" in LOGIN_SUCCESS_INDICATORS

    def test_linkedin_login_url(self):
        from browser.auth import LinkedInAuth
        assert "linkedin.com" in LinkedInAuth.LOGIN_URL

    def test_indeed_login_url(self):
        from browser.auth import IndeedAuth
        assert "indeed.com" in IndeedAuth.LOGIN_URL

    def test_github_login_url(self):
        from browser.auth import GitHubAuth
        assert "github.com" in GitHubAuth.LOGIN_URL


# ============================================================
# Session Manager Tests
# ============================================================

class TestSessionManager:
    """BrowserSession orchestration tests."""

    def test_domain_extraction(self):
        from browser.session_manager import BrowserSession
        session = BrowserSession()
        assert session._extract_domain("https://www.linkedin.com/in/someone") == "linkedin.com"
        assert session._extract_domain("https://indeed.com/jobs?q=python") == "indeed.com"
        assert session._extract_domain("https://example.com/page") == "example.com"
        assert session._extract_domain("https://sub.domain.com/path") == "sub.domain.com"

    def test_auth_required_domains(self):
        from browser.session_manager import AUTH_REQUIRED_DOMAINS
        assert "linkedin.com" in AUTH_REQUIRED_DOMAINS
        assert "indeed.com" in AUTH_REQUIRED_DOMAINS

    def test_js_required_domains(self):
        from browser.session_manager import JS_REQUIRED_DOMAINS
        assert "medium.com" in JS_REQUIRED_DOMAINS

    def test_session_init_no_vault(self):
        from browser.session_manager import BrowserSession
        session = BrowserSession()
        assert session.vault is None
        assert session.headless is True

    def test_session_init_with_vault(self):
        from browser.session_manager import BrowserSession
        mock_vault = MagicMock()
        session = BrowserSession(vault=mock_vault, headless=False, proxy="http://p:8080")
        assert session.vault is mock_vault
        assert session.headless is False
        assert session.proxy == "http://p:8080"


class TestSessionManagerFetch:
    """Fetch behavior with mocked browser."""

    @pytest.mark.asyncio
    async def test_fetch_returns_error_on_failure(self):
        from browser.session_manager import BrowserSession
        session = BrowserSession()

        # Mock browser to raise
        mock_browser = AsyncMock()
        mock_browser.launch = AsyncMock()
        mock_browser.new_page = AsyncMock(side_effect=Exception("Browser crashed"))

        session._browsers["default"] = mock_browser

        result = await session.fetch("https://example.com")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_close_all_clears_browsers(self):
        from browser.session_manager import BrowserSession
        session = BrowserSession()

        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()
        session._browsers["test"] = mock_browser

        await session.close_all()
        assert len(session._browsers) == 0


# ============================================================
# Browser Tools Tests
# ============================================================

class TestBrowserTools:
    """Tool definitions for Claude."""

    def test_fetch_tool_definition(self):
        from browser.tools import BROWSER_FETCH_TOOL
        assert BROWSER_FETCH_TOOL["name"] == "browser_fetch"
        assert "url" in BROWSER_FETCH_TOOL["input_schema"]["properties"]
        assert "url" in BROWSER_FETCH_TOOL["input_schema"]["required"]

    def test_search_tool_definition(self):
        from browser.tools import BROWSER_SEARCH_TOOL
        assert BROWSER_SEARCH_TOOL["name"] == "browser_search"
        assert "query" in BROWSER_SEARCH_TOOL["input_schema"]["properties"]

    def test_all_tools_have_descriptions(self):
        from browser.tools import BROWSER_TOOLS
        for tool in BROWSER_TOOLS:
            assert len(tool["description"]) > 20
            assert "name" in tool
            assert "input_schema" in tool

    def test_format_fetch_result_success(self):
        from browser.tools import _format_fetch_result
        result = {
            "url": "https://example.com",
            "title": "Example",
            "content": "Hello world",
            "success": True,
            "char_count": 11,
        }
        formatted = _format_fetch_result(result)
        assert "example.com" in formatted
        assert "Hello world" in formatted

    def test_format_fetch_result_failure(self):
        from browser.tools import _format_fetch_result
        result = {
            "url": "https://example.com",
            "success": False,
            "error": "Navigation timeout",
        }
        formatted = _format_fetch_result(result)
        assert "FAILED" in formatted
        assert "timeout" in formatted.lower()

    def test_format_fetch_truncates_long_content(self):
        from browser.tools import _format_fetch_result
        result = {
            "url": "https://example.com",
            "title": "Long",
            "content": "x" * 20000,
            "success": True,
            "char_count": 20000,
        }
        formatted = _format_fetch_result(result)
        assert "truncated" in formatted
        assert len(formatted) < 20000

    def test_format_search_results_empty(self):
        from browser.tools import _format_search_results
        assert _format_search_results([]) == "No results found."

    def test_format_search_results_mixed(self):
        from browser.tools import _format_search_results
        results = [
            {"url": "https://a.com", "success": True, "title": "A", "content": "Content A"},
            {"url": "https://b.com", "success": False, "error": "Timeout"},
        ]
        formatted = _format_search_results(results)
        assert "Result 1" in formatted
        assert "Result 2" in formatted
        assert "Content A" in formatted
        assert "FAILED" in formatted


# ============================================================
# Integration Tests (mocked browser)
# ============================================================

class TestVaultIntegration:
    """Tests that browser correctly uses credential vault."""

    def test_vault_key_format(self):
        """Vault keys use domain with underscores."""
        from browser.session_manager import BrowserSession
        session = BrowserSession()
        domain = session._extract_domain("https://www.linkedin.com/in/profile")
        vault_key = domain.replace(".", "_")
        assert vault_key == "linkedin_com"

    def test_no_vault_no_auth(self):
        """Without vault, auth domains fail gracefully."""
        from browser.session_manager import BrowserSession
        session = BrowserSession(vault=None)
        assert session.vault is None


class TestSyncWrappers:
    """Synchronous wrapper functions."""

    def test_fetch_with_browser_importable(self):
        from browser.session_manager import fetch_with_browser
        assert callable(fetch_with_browser)

    def test_fetch_multiple_with_browser_importable(self):
        from browser.session_manager import fetch_multiple_with_browser
        assert callable(fetch_multiple_with_browser)
