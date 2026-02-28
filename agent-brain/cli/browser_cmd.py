"""Stealth browser CLI commands."""


def fetch_url(url: str):
    """Fetch a URL using the stealth browser."""
    print(f"\n{'='*60}")
    print(f"  BROWSER FETCH")
    print(f"{'='*60}\n")
    print(f"  URL: {url}")

    try:
        from browser.session_manager import fetch_with_browser
        from cli.vault import get_vault
        vault = get_vault()
        result = fetch_with_browser(url, vault=vault, headless=True)

        if result["success"]:
            print(f"  Title: {result.get('title', 'N/A')}")
            print(f"  Characters: {result.get('char_count', 0)}")
            print(f"  Domain: {result.get('domain', 'N/A')}")
            print(f"\n--- Content (first 2000 chars) ---")
            print(result.get("content", "")[:2000])
        else:
            print(f"  FAILED: {result.get('error', 'Unknown error')}")
    except ImportError as e:
        print(f"  ERROR: Browser dependencies not installed: {e}")
        print("  Run: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


def test_stealth():
    """Test browser stealth detection."""
    print(f"\n{'='*60}")
    print(f"  BROWSER STEALTH TEST")
    print(f"{'='*60}\n")

    try:
        import asyncio
        from browser.stealth_browser import StealthBrowser

        async def _test():
            async with StealthBrowser(headless=True) as browser:
                page = await browser.new_page()
                await browser.navigate(page, "https://bot.sannysoft.com")
                detection = await browser.check_detection(page)
                await page.close()
                return detection

        result = asyncio.run(_test())
        stealth_ok = result.pop("stealth_ok", False)
        print(f"  Stealth: {'PASS' if stealth_ok else 'FAIL'}")
        for key, val in result.items():
            print(f"    {key}: {val}")
    except ImportError as e:
        print(f"  ERROR: Browser dependencies not installed: {e}")
        print("  Run: pip install playwright && playwright install chromium")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
