"""
Browser Tool — agent-browser powered browser automation for Agent Hands.

Wraps the agent-browser CLI (https://github.com/vercel-labs/agent-browser)
to provide AI-optimized browser automation. The key advantage over raw
Playwright is the `snapshot` action which returns an accessibility tree
with @ref identifiers — allowing any LLM to "see" page structure as text
without expensive vision API calls.

Supports:
- screenshot: Capture a page as base64 PNG
- snapshot: Get accessibility tree with @ref element identifiers (KEY FEATURE)
- navigate: Load a URL and return page info
- click: Click an element by @ref from snapshot or CSS selector
- fill: Fill an input field by @ref from snapshot or CSS selector
- wait_for: Wait for text to appear on the page
- evaluate: Run JavaScript in the page context
- get_text: Extract visible text from the page

Safety:
- Headless only (no GUI)
- Timeout enforced per action
- No access to file:// or internal IPs
- Screenshots capped at reasonable resolution
"""

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from hands.tools.registry import BaseTool, ToolResult


# Viewport presets (used for viewport command)
_DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
_MOBILE_VIEWPORT = {"width": 375, "height": 812}

# Action timeout in seconds for subprocess calls
_ACTION_TIMEOUT_S = 30

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


def _find_agent_browser() -> str | None:
    """Find the agent-browser CLI binary. Returns path or None."""
    return shutil.which("agent-browser")


def _run_cli(*args: str, timeout: int = _ACTION_TIMEOUT_S) -> tuple[bool, str, str]:
    """
    Run an agent-browser CLI command.

    Returns (success, stdout, stderr).
    """
    binary = _find_agent_browser()
    if not binary:
        return False, "", "agent-browser CLI not found. Install with: npm install -g agent-browser"

    cmd = [binary] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except Exception as e:
        return False, "", f"CLI error: {e}"


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
    Manages an agent-browser session.

    agent-browser persists its browser instance between CLI calls,
    so this class primarily handles open/close lifecycle and provides
    the same singleton interface as before for VisualGate compatibility.
    """

    _instance: "BrowserSession | None" = None
    _started: bool = False

    def __init__(self):
        self._started = False

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

    @classmethod
    def close(cls):
        """Shut down the browser cleanly."""
        try:
            _run_cli("close", timeout=5)
        except Exception:
            pass
        if cls._instance is not None:
            cls._instance._started = False

    def set_viewport(self, width: int, height: int) -> None:
        """Change viewport size via agent-browser."""
        _run_cli("viewport", str(width), str(height), timeout=10)


class BrowserTool(BaseTool):
    """
    agent-browser powered browser tool for Agent Hands.

    Actions:
    - screenshot: Capture page as base64 PNG
    - snapshot: Get accessibility tree with @ref identifiers (AI-optimized)
    - navigate: Load a URL
    - click: Click by @ref (from snapshot) or CSS selector
    - fill: Fill input by @ref (from snapshot) or CSS selector
    - wait_for: Wait for text on page
    - evaluate: Run JS in page
    - get_text: Extract page text
    """

    name = "browser"
    description = (
        "Browser automation tool powered by agent-browser. Take screenshots, get page "
        "accessibility snapshots (with @ref identifiers for clicking/filling), navigate "
        "URLs, click elements, fill forms, and extract text. Use 'snapshot' to see page "
        "structure as text — much cheaper than screenshots for understanding layout. "
        "Use 'screenshot' after building UI to verify visual quality."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["screenshot", "snapshot", "navigate", "click", "fill",
                         "wait_for", "evaluate", "get_text"],
                "description": "The browser action to perform",
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to (for 'navigate' and 'screenshot' actions)",
            },
            "ref": {
                "type": "string",
                "description": "Element @ref from snapshot (e.g. 'e5') for 'click' and 'fill' actions. Preferred over selector.",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for element (fallback for 'click', 'fill' if no @ref available)",
            },
            "text": {
                "type": "string",
                "description": "Text to type into input (for 'fill' action), or text to wait for (for 'wait_for')",
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
            "snapshot": self._snapshot,
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
        """Take a screenshot of the current page or navigate to a URL first."""
        url = kwargs.get("url", "")
        viewport = kwargs.get("viewport", "desktop")
        full_page = kwargs.get("full_page", False)
        save_path = kwargs.get("save_path", "")

        try:
            # Set viewport
            vp = _MOBILE_VIEWPORT if viewport == "mobile" else _DEFAULT_VIEWPORT
            _run_cli("viewport", str(vp["width"]), str(vp["height"]), timeout=10)

            # Navigate if URL provided
            if url:
                error = _is_safe_url(url)
                if error:
                    return ToolResult(success=False, error=error)
                ok, out, err = _run_cli("open", url)
                if not ok:
                    return ToolResult(success=False, error=f"Navigation failed: {err or out}")

            # Determine screenshot path
            if save_path:
                screenshot_path = save_path
            else:
                screenshot_path = os.path.join(tempfile.gettempdir(), "cortex_screenshot.png")

            # Take screenshot
            cli_args = ["screenshot", screenshot_path]
            if full_page:
                cli_args.append("--full-page")
            ok, out, err = _run_cli(*cli_args)

            if not ok:
                return ToolResult(success=False, error=f"Screenshot failed: {err or out}")

            # Read the file and base64 encode
            if not os.path.exists(screenshot_path):
                return ToolResult(success=False, error="Screenshot file not created")

            with open(screenshot_path, "rb") as f:
                screenshot_bytes = f.read()

            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            # Build artifacts list
            artifacts = [save_path] if save_path else []

            # Clean up temp file if we created it
            if not save_path and os.path.exists(screenshot_path):
                try:
                    os.unlink(screenshot_path)
                except OSError:
                    pass

            return ToolResult(
                success=True,
                output=f"Screenshot captured ({len(screenshot_bytes)} bytes, {viewport} viewport) {out}",
                artifacts=artifacts,
                metadata={
                    "base64_image": b64,
                    "viewport": viewport,
                    "full_page": full_page,
                    "image_size_bytes": len(screenshot_bytes),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Screenshot failed: {e}")

    def _snapshot(self, **kwargs) -> ToolResult:
        """
        Get page accessibility tree with @ref identifiers.

        This is the KEY feature — returns the page structure as text with
        clickable/fillable element references like @e1, @e2. The executor
        can then use these refs in click/fill actions instead of CSS selectors.
        Much cheaper than sending screenshots to a vision model.
        """
        try:
            ok, out, err = _run_cli("snapshot")
            if not ok:
                return ToolResult(
                    success=False,
                    error=f"Snapshot failed: {err or out or 'No output from agent-browser'}",
                )

            if not out:
                return ToolResult(
                    success=False,
                    error="Snapshot returned empty — is a page loaded? Use navigate first.",
                )

            # Count refs for metadata
            ref_count = len(re.findall(r'\[ref=\w+\]', out))

            return ToolResult(
                success=True,
                output=out,
                metadata={
                    "ref_count": ref_count,
                    "snapshot_length": len(out),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Snapshot failed: {e}")

    def _navigate(self, **kwargs) -> ToolResult:
        """Navigate to a URL and return page info."""
        url = kwargs.get("url", "")
        if not url:
            return ToolResult(success=False, error="URL is required for navigate action")

        error = _is_safe_url(url)
        if error:
            return ToolResult(success=False, error=error)

        try:
            ok, out, err = _run_cli("open", url)
            if not ok:
                return ToolResult(
                    success=False,
                    error=f"Navigation failed: {err or out}",
                )

            return ToolResult(
                success=True,
                output=f"Navigated: {out}" if out else f"Navigated to {url}",
                metadata={"url": url},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Navigation failed: {e}")

    def _click(self, **kwargs) -> ToolResult:
        """Click an element by @ref (preferred) or CSS selector."""
        ref = kwargs.get("ref", "")
        selector = kwargs.get("selector", "")

        if not ref and not selector:
            return ToolResult(
                success=False,
                error="Either 'ref' (from snapshot, e.g. 'e5') or 'selector' (CSS) is required for click",
            )

        try:
            if ref:
                ok, out, err = _run_cli("click", ref)
            else:
                ok, out, err = _run_cli("click", selector)

            if not ok:
                target = f"@{ref}" if ref else selector
                return ToolResult(success=False, error=f"Click failed on '{target}': {err or out}")

            target = f"@{ref}" if ref else selector
            return ToolResult(
                success=True,
                output=f"Clicked element: {target}" + (f" — {out}" if out else ""),
                metadata={"ref": ref, "selector": selector},
            )
        except Exception as e:
            target = f"@{ref}" if ref else selector
            return ToolResult(success=False, error=f"Click failed on '{target}': {e}")

    def _fill(self, **kwargs) -> ToolResult:
        """Fill an input field by @ref (preferred) or CSS selector."""
        ref = kwargs.get("ref", "")
        selector = kwargs.get("selector", "")
        text = kwargs.get("text", "")

        if not ref and not selector:
            return ToolResult(
                success=False,
                error="Either 'ref' (from snapshot, e.g. 'e5') or 'selector' (CSS) is required for fill",
            )

        try:
            if ref:
                ok, out, err = _run_cli("fill", ref, text)
            else:
                ok, out, err = _run_cli("fill", selector, text)

            if not ok:
                target = f"@{ref}" if ref else selector
                return ToolResult(success=False, error=f"Fill failed on '{target}': {err or out}")

            target = f"@{ref}" if ref else selector
            return ToolResult(
                success=True,
                output=f"Filled '{target}' with text ({len(text)} chars)",
                metadata={"ref": ref, "selector": selector, "text_length": len(text)},
            )
        except Exception as e:
            target = f"@{ref}" if ref else selector
            return ToolResult(success=False, error=f"Fill failed on '{target}': {e}")

    def _wait_for(self, **kwargs) -> ToolResult:
        """Wait for text to appear on the page."""
        text = kwargs.get("text", "") or kwargs.get("selector", "")
        if not text:
            return ToolResult(
                success=False,
                error="'text' is required for wait_for action (text to wait for on page)",
            )

        try:
            ok, out, err = _run_cli("wait", text)
            if not ok:
                return ToolResult(success=False, error=f"Wait failed for '{text}': {err or out}")

            return ToolResult(
                success=True,
                output=f"Found on page: {text}",
                metadata={"text": text},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Wait failed for '{text}': {e}")

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
            ok, out, err = _run_cli("evaluate", script)
            if not ok:
                return ToolResult(success=False, error=f"JS evaluation failed: {err or out}")

            # Cap output length
            if len(out) > 5000:
                out = out[:5000] + "... (truncated)"

            return ToolResult(
                success=True,
                output=f"JS result: {out}" if out else "JS result: undefined",
                metadata={"result": out},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"JS evaluation failed: {e}")

    def _get_text(self, **kwargs) -> ToolResult:
        """Extract visible text from the page."""
        selector = kwargs.get("selector", "")

        try:
            # Use agent-browser's textContent command or evaluate innerText
            if selector and selector != "body":
                ok, out, err = _run_cli(
                    "evaluate",
                    f"document.querySelector('{selector}')?.innerText || ''",
                )
            else:
                ok, out, err = _run_cli("evaluate", "document.body.innerText")

            if not ok:
                return ToolResult(
                    success=False,
                    error=f"get_text failed for '{selector or 'body'}': {err or out}",
                )

            # Cap text length
            if len(out) > 10000:
                out = out[:10000] + "\n... (truncated)"

            return ToolResult(
                success=True,
                output=out,
                metadata={"selector": selector or "body", "text_length": len(out)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"get_text failed for '{selector or 'body'}': {e}")
