"""
Browser Tool — Playwright-based browser automation for Agent Hands.

Gives Hands the ability to see what it builds and interact with web pages.
Uses Playwright (Chromium) for headless browser control.

Supports:
- screenshot: Capture a page as base64 PNG (full page or viewport)
- navigate: Load a URL and return page info
- click: Click an element by CSS selector
- fill: Fill an input field by CSS selector
- wait_for: Wait for an element to appear
- evaluate: Run JavaScript in the page context
- get_text: Extract visible text from the page

Safety:
- Headless only (no GUI)
- Timeout enforced per action
- No access to file:// or internal IPs
- Browser context isolated per session
- Screenshots capped at reasonable resolution
"""

import base64
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from hands.tools.registry import BaseTool, ToolResult


# Max screenshot dimensions
_MAX_VIEWPORT_WIDTH = 1920
_MAX_VIEWPORT_HEIGHT = 1080
_DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
_MOBILE_VIEWPORT = {"width": 375, "height": 812}

# Action timeout in milliseconds
_ACTION_TIMEOUT_MS = 30_000

# Block internal/dangerous URLs (but NOT localhost for dev builds)
_BLOCKED_URL_PATTERN = re.compile(
    r"^(file://|javascript:|data:|about:|chrome://|"
    r"https?://(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|"
    r"0\.0\.0\.0|\[::1\]|169\.254\.))"
)

# Localhost patterns allowed for dev builds
_LOCALHOST_PATTERN = re.compile(
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?(/|$)"
)


def _is_safe_url(url: str) -> str | None:
    """Check if a URL is safe to navigate to. Returns error string if unsafe, None if safe."""
    if not url:
        return "URL is required"
    # Allow localhost for dev builds (before blocking internal IPs)
    if _LOCALHOST_PATTERN.match(url):
        return None
    if _BLOCKED_URL_PATTERN.match(url):
        return f"Blocked URL (internal/dangerous): {url}"
    if not url.startswith(("http://", "https://")):
        return f"URL must start with http:// or https:// (got: {url[:50]})"
    return None


class BrowserSession:
    """
    Manages a Playwright browser session.
    
    Lazy initialization — browser is only started when first needed.
    Reused across multiple tool calls within one execution.
    Cleaned up explicitly via close() or on garbage collection.
    """
    
    _instance: "BrowserSession | None" = None
    
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
    
    @classmethod
    def get(cls) -> "BrowserSession":
        """Get or create the singleton browser session."""
        if cls._instance is None:
            cls._instance = BrowserSession()
        return cls._instance
    
    @classmethod
    def reset(cls):
        """Close and reset the singleton (for tests)."""
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None
    
    def _ensure_started(self) -> None:
        """Start browser if not already running."""
        if self._page is not None:
            return
        
        from playwright.sync_api import sync_playwright
        
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ],
        )
        self._context = self._browser.new_context(
            viewport=_DEFAULT_VIEWPORT,
            device_scale_factor=1,
            # Block unnecessary resources for faster loading
            # (we still need images for screenshot accuracy)
        )
        self._page = self._context.new_page()
    
    @property
    def page(self):
        """Get the active page, starting browser if needed."""
        self._ensure_started()
        return self._page
    
    def set_viewport(self, width: int, height: int) -> None:
        """Change viewport size."""
        width = min(width, _MAX_VIEWPORT_WIDTH)
        height = min(height, _MAX_VIEWPORT_HEIGHT)
        self._ensure_started()
        self._page.set_viewport_size({"width": width, "height": height})
    
    def close(self) -> None:
        """Shut down the browser cleanly."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._playwright = None
            self._browser = None
            self._context = None
            self._page = None


class BrowserTool(BaseTool):
    """
    Playwright browser tool for Agent Hands.
    
    Actions:
    - screenshot: Capture page as base64 PNG
    - navigate: Load a URL
    - click: Click an element
    - fill: Fill an input
    - wait_for: Wait for element
    - evaluate: Run JS in page
    - get_text: Extract page text
    """
    
    name = "browser"
    description = (
        "Browser automation tool. Take screenshots of built pages, navigate URLs, "
        "click elements, fill forms, and extract text. Use 'screenshot' after building "
        "UI to verify visual quality. Use 'navigate' to load pages for testing."
    )
    
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["screenshot", "navigate", "click", "fill", "wait_for", "evaluate", "get_text"],
                "description": "The browser action to perform",
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to (for 'navigate' and 'screenshot' actions)",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for element (for 'click', 'fill', 'wait_for' actions)",
            },
            "text": {
                "type": "string",
                "description": "Text to fill into input (for 'fill' action)",
            },
            "script": {
                "type": "string",
                "description": "JavaScript to evaluate (for 'evaluate' action)",
            },
            "viewport": {
                "type": "string",
                "enum": ["desktop", "mobile"],
                "description": "Viewport size preset (default: desktop). Use 'mobile' for responsive testing.",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full page scroll height (for 'screenshot', default: false)",
            },
            "save_path": {
                "type": "string",
                "description": "Optional file path to save screenshot PNG (in addition to base64 return)",
            },
        },
        "required": ["action"],
    }
    
    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        
        dispatch = {
            "screenshot": self._screenshot,
            "navigate": self._navigate,
            "click": self._click,
            "fill": self._fill,
            "wait_for": self._wait_for,
            "evaluate": self._evaluate,
            "get_text": self._get_text,
        }
        
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(
                success=False,
                error=f"Unknown action '{action}'. Available: {', '.join(dispatch.keys())}",
            )
        
        return handler(**kwargs)
    
    def _screenshot(self, **kwargs) -> ToolResult:
        """Take a screenshot of the current page or a new URL."""
        url = kwargs.get("url", "")
        viewport = kwargs.get("viewport", "desktop")
        full_page = kwargs.get("full_page", False)
        save_path = kwargs.get("save_path", "")
        
        try:
            session = BrowserSession.get()
            
            # Set viewport
            if viewport == "mobile":
                session.set_viewport(_MOBILE_VIEWPORT["width"], _MOBILE_VIEWPORT["height"])
            else:
                session.set_viewport(_DEFAULT_VIEWPORT["width"], _DEFAULT_VIEWPORT["height"])
            
            # Navigate if URL provided
            if url:
                error = _is_safe_url(url)
                if error:
                    return ToolResult(success=False, error=error)
                session.page.goto(url, timeout=_ACTION_TIMEOUT_MS, wait_until="networkidle")
            
            # Take screenshot
            screenshot_bytes = session.page.screenshot(
                full_page=full_page,
                type="png",
            )
            
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            # Optionally save to disk
            artifacts = []
            if save_path:
                os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(screenshot_bytes)
                artifacts.append(save_path)
            
            page_title = session.page.title()
            page_url = session.page.url
            
            return ToolResult(
                success=True,
                output=f"Screenshot captured: {page_title} ({page_url}) — {len(screenshot_bytes)} bytes, {viewport} viewport",
                artifacts=artifacts,
                metadata={
                    "base64_image": b64,
                    "page_title": page_title,
                    "page_url": page_url,
                    "viewport": viewport,
                    "full_page": full_page,
                    "image_size_bytes": len(screenshot_bytes),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Screenshot failed: {e}")
    
    def _navigate(self, **kwargs) -> ToolResult:
        """Navigate to a URL and return page info."""
        url = kwargs.get("url", "")
        if not url:
            return ToolResult(success=False, error="URL is required for navigate action")
        
        error = _is_safe_url(url)
        if error:
            return ToolResult(success=False, error=error)
        
        try:
            session = BrowserSession.get()
            response = session.page.goto(url, timeout=_ACTION_TIMEOUT_MS, wait_until="networkidle")
            
            status = response.status if response else 0
            title = session.page.title()
            final_url = session.page.url
            
            return ToolResult(
                success=status < 400,
                output=f"Navigated to {final_url} — HTTP {status}, title: '{title}'",
                metadata={
                    "status_code": status,
                    "title": title,
                    "final_url": final_url,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Navigation failed: {e}")
    
    def _click(self, **kwargs) -> ToolResult:
        """Click an element by CSS selector."""
        selector = kwargs.get("selector", "")
        if not selector:
            return ToolResult(success=False, error="CSS selector is required for click action")
        
        try:
            session = BrowserSession.get()
            session.page.click(selector, timeout=_ACTION_TIMEOUT_MS)
            
            return ToolResult(
                success=True,
                output=f"Clicked element: {selector}",
                metadata={"selector": selector},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Click failed on '{selector}': {e}")
    
    def _fill(self, **kwargs) -> ToolResult:
        """Fill an input field by CSS selector."""
        selector = kwargs.get("selector", "")
        text = kwargs.get("text", "")
        if not selector:
            return ToolResult(success=False, error="CSS selector is required for fill action")
        
        try:
            session = BrowserSession.get()
            session.page.fill(selector, text, timeout=_ACTION_TIMEOUT_MS)
            
            return ToolResult(
                success=True,
                output=f"Filled '{selector}' with text ({len(text)} chars)",
                metadata={"selector": selector, "text_length": len(text)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Fill failed on '{selector}': {e}")
    
    def _wait_for(self, **kwargs) -> ToolResult:
        """Wait for an element to appear."""
        selector = kwargs.get("selector", "")
        if not selector:
            return ToolResult(success=False, error="CSS selector is required for wait_for action")
        
        try:
            session = BrowserSession.get()
            session.page.wait_for_selector(selector, timeout=_ACTION_TIMEOUT_MS)
            
            return ToolResult(
                success=True,
                output=f"Element found: {selector}",
                metadata={"selector": selector},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Wait failed for '{selector}': {e}")
    
    def _evaluate(self, **kwargs) -> ToolResult:
        """Evaluate JavaScript in the page context."""
        script = kwargs.get("script", "")
        if not script:
            return ToolResult(success=False, error="JavaScript code is required for evaluate action")
        
        # Block dangerous JS patterns
        dangerous = ["require(", "process.env", "child_process", "fs.write", "fs.unlink", "eval("]
        for pattern in dangerous:
            if pattern in script:
                return ToolResult(success=False, error=f"Blocked dangerous JS pattern: {pattern}")
        
        try:
            session = BrowserSession.get()
            result = session.page.evaluate(script)
            
            # Serialize result
            output = str(result) if result is not None else "undefined"
            if len(output) > 5000:
                output = output[:5000] + "... (truncated)"
            
            return ToolResult(
                success=True,
                output=f"JS result: {output}",
                metadata={"result": result if isinstance(result, (str, int, float, bool, list, dict, type(None))) else str(result)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"JS evaluation failed: {e}")
    
    def _get_text(self, **kwargs) -> ToolResult:
        """Extract visible text from the page or a specific element."""
        selector = kwargs.get("selector", "body")
        
        try:
            session = BrowserSession.get()
            text = session.page.inner_text(selector, timeout=_ACTION_TIMEOUT_MS)
            
            # Cap text length
            if len(text) > 10000:
                text = text[:10000] + "\n... (truncated)"
            
            return ToolResult(
                success=True,
                output=text,
                metadata={"selector": selector, "text_length": len(text)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"get_text failed for '{selector}': {e}")
