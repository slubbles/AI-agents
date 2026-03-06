"""
Image Publisher — Screenshot → public URL → Threads post pipeline.

Provides:
  upload_to_vercel_blob(image_bytes, filename) → public URL
  capture_and_post(page_url, text, full_page)  → Threads post result
  generate_score_chart(dates, scores, title)   → PNG bytes
  post_with_chart(text, chart_data)            → Threads post result

Setup (one-time):
  1. vercel.com → your project → Storage → Create Blob store
  2. Copy BLOB_READ_WRITE_TOKEN to VPS .env

All functions gracefully degrade — if credentials are missing, they return
an error dict rather than raising (Narrator can still post text-only).

Pure stdlib for upload. matplotlib optional for charts (falls back to None).
"""

import base64
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

BLOB_READ_WRITE_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
VERCEL_BLOB_API = "https://blob.vercel-storage.com"


def blob_configured() -> bool:
    """True if BLOB_READ_WRITE_TOKEN is set."""
    return bool(BLOB_READ_WRITE_TOKEN)


# ── Upload layer ─────────────────────────────────────────────────────────

def upload_to_vercel_blob(image_bytes: bytes, filename: str) -> str:
    """
    Upload image bytes to Vercel Blob storage.

    Args:
        image_bytes: Raw PNG/JPEG bytes.
        filename:    Filename for the blob (e.g. "cortex_1234.png").

    Returns:
        Permanent public HTTPS URL.

    Raises:
        RuntimeError: if BLOB_READ_WRITE_TOKEN is missing or upload fails.
    """
    if not BLOB_READ_WRITE_TOKEN:
        raise RuntimeError(
            "BLOB_READ_WRITE_TOKEN not set. "
            "Create a blob store at vercel.com → Storage → Blob and add the token to .env"
        )

    url = f"{VERCEL_BLOB_API}/{filename}"
    ext = os.path.splitext(filename)[1].lower()
    content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    req = urllib.request.Request(url, data=image_bytes, method="PUT")
    req.add_header("Authorization", f"Bearer {BLOB_READ_WRITE_TOKEN}")
    req.add_header("Content-Type", content_type)
    req.add_header("x-content-type", content_type)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        public_url = result.get("url", "")
        if not public_url:
            raise RuntimeError(f"Vercel Blob returned no URL: {result}")
        logger.info(f"[IMAGE] Uploaded {filename} → {public_url}")
        return public_url
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Vercel Blob upload failed HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Vercel Blob upload connection error: {e.reason}") from e


# ── Screenshot → post pipeline ────────────────────────────────────────────

def capture_and_post(
    page_url: str,
    post_text: str,
    full_page: bool = False,
    retina: bool = True,
) -> dict:
    """
    Screenshot a URL at retina quality → Vercel Blob → Threads post.

    Args:
        page_url:   URL to screenshot (live Vercel deploy, localhost, etc.)
        post_text:  Up to 500 chars for the Threads post.
        full_page:  Capture full scroll height (True) or viewport only (False).
        retina:     Use 2× device_scale_factor for crisp Retina quality.

    Returns:
        {"id": str, "published": bool, "image_url": str}
        or {"error": str} on failure.
    """
    if not blob_configured():
        return {"error": "BLOB_READ_WRITE_TOKEN not configured — text-only post fallback"}

    # Step 1: Screenshot via Playwright (preferred — full quality control)
    img_bytes = _playwright_screenshot(page_url, full_page=full_page, retina=retina)

    # Step 2: Fall back to agent-browser if Playwright not available
    if img_bytes is None:
        img_bytes = _agent_browser_screenshot(page_url, full_page=full_page)

    if img_bytes is None:
        return {"error": f"Could not capture screenshot of {page_url}"}

    # Step 3: Upload to Vercel Blob
    try:
        filename = f"cortex_{int(time.time())}.png"
        public_url = upload_to_vercel_blob(img_bytes, filename)
    except RuntimeError as e:
        return {"error": str(e)}

    # Step 4: Post to Threads with image
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from tools.threads_client import publish_post
        result = publish_post(text=post_text, image_url=public_url)
        result["image_url"] = public_url
        return result
    except Exception as e:
        return {"error": f"Threads post failed after upload: {e}", "image_url": public_url}


def _playwright_screenshot(
    url: str,
    full_page: bool = False,
    retina: bool = True,
) -> Optional[bytes]:
    """
    Take a retina-quality screenshot using Playwright.
    Returns PNG bytes, or None if Playwright is unavailable.
    """
    try:
        from playwright.sync_api import sync_playwright  # optional dep

        scale = 2 if retina else 1
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(
                device_scale_factor=scale,
                viewport={"width": 1400, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            img_bytes = page.screenshot(
                type="png",
                full_page=full_page,
                scale="device",
            )
            browser.close()
        logger.info(f"[IMAGE] Playwright screenshot: {len(img_bytes):,} bytes ({scale}x scale)")
        return img_bytes
    except ImportError:
        logger.debug("[IMAGE] Playwright not installed — falling back to agent-browser")
        return None
    except Exception as e:
        logger.warning(f"[IMAGE] Playwright screenshot failed: {e}")
        return None


def _agent_browser_screenshot(
    url: str,
    full_page: bool = False,
) -> Optional[bytes]:
    """
    Take a screenshot using the existing agent-browser CLI tool.
    Returns PNG bytes, or None on failure.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from hands.tools.browser import BrowserTool

        bt = BrowserTool()
        result = bt.execute(
            action="screenshot",
            url=url,
            viewport="desktop",
            full_page=full_page,
        )
        if not result.success:
            logger.warning(f"[IMAGE] agent-browser screenshot failed: {result.error}")
            return None

        b64 = result.metadata.get("base64_image", "")
        if not b64:
            return None

        img_bytes = base64.b64decode(b64)
        logger.info(f"[IMAGE] agent-browser screenshot: {len(img_bytes):,} bytes")
        return img_bytes
    except Exception as e:
        logger.warning(f"[IMAGE] agent-browser fallback failed: {e}")
        return None


# ── Chart generation ──────────────────────────────────────────────────────

def generate_score_chart(
    dates: list[str],
    scores: list[float],
    title: str = "Research Quality Over Time",
    ylabel: str = "Score (out of 10)",
) -> Optional[bytes]:
    """
    Generate a score trend chart as PNG bytes.
    Returns None if matplotlib is not installed (zero-dep fallback).

    Args:
        dates:  List of date strings (x axis labels).
        scores: Corresponding float scores.
        title:  Chart title.
        ylabel: Y-axis label.

    Returns:
        PNG bytes, or None if matplotlib unavailable.
    """
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend (safe in headless env)
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker

        fig, ax = plt.subplots(figsize=(10, 5))
        fig.patch.set_facecolor("#0f1117")
        ax.set_facecolor("#0f1117")

        # Line + scatter
        ax.plot(dates, scores, color="#7c3aed", linewidth=2.5, zorder=3)
        ax.scatter(dates, scores, color="#a78bfa", s=60, zorder=4)

        # Threshold line at 6.0 (accept threshold)
        ax.axhline(y=6.0, color="#ef4444", linewidth=1, linestyle="--", alpha=0.6, label="Accept threshold (6.0)")

        # Styling
        ax.set_title(title, color="white", fontsize=14, pad=16)
        ax.set_ylabel(ylabel, color="#9ca3af", fontsize=11)
        ax.set_ylim(0, 10)
        ax.yaxis.set_major_locator(ticker.MultipleLocator(2))
        ax.tick_params(colors="#9ca3af", labelsize=9)
        ax.spines[:].set_color("#374151")
        for spine in ax.spines.values():
            spine.set_color("#374151")

        # Rotate x labels if many dates
        if len(dates) > 6:
            plt.xticks(rotation=30, ha="right")

        ax.legend(facecolor="#1f2937", edgecolor="#374151", labelcolor="white", fontsize=9)
        fig.tight_layout(pad=1.5)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except ImportError:
        logger.debug("[IMAGE] matplotlib not installed — chart generation unavailable")
        return None
    except Exception as e:
        logger.warning(f"[IMAGE] Chart generation failed: {e}")
        return None


def post_with_chart(
    post_text: str,
    dates: list[str],
    scores: list[float],
    title: str = "Research Quality Over Time",
) -> dict:
    """
    Generate a score trend chart, upload to Vercel Blob, post to Threads.

    Args:
        post_text: Up to 500 chars for the Threads post.
        dates:     X-axis dates for the chart.
        scores:    Y-axis scores (0-10).
        title:     Chart title.

    Returns:
        {"id": str, "published": bool, "image_url": str}
        or {"error": str} on failure.
    """
    if not blob_configured():
        return {"error": "BLOB_READ_WRITE_TOKEN not configured"}

    chart_bytes = generate_score_chart(dates, scores, title=title)
    if chart_bytes is None:
        return {"error": "Chart generation failed (matplotlib may not be installed)"}

    try:
        filename = f"cortex_chart_{int(time.time())}.png"
        public_url = upload_to_vercel_blob(chart_bytes, filename)
    except RuntimeError as e:
        return {"error": str(e)}

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from tools.threads_client import publish_post
        result = publish_post(text=post_text, image_url=public_url)
        result["image_url"] = public_url
        return result
    except Exception as e:
        return {"error": f"Threads post failed: {e}", "image_url": public_url}
