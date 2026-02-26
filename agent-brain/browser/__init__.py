"""
Stealth Browser — Playwright-based browser automation with anti-detection.

Provides authenticated browsing for sites that block HTTP scrapers:
- LinkedIn, Indeed, Glassdoor (job/people research)
- Cloudflare-protected sites
- Sites requiring JavaScript rendering
- Authenticated dashboards

Anti-detection features:
- playwright-stealth patches (WebDriver, navigator, WebGL, etc.)
- Human-like timing (random delays, realistic scroll patterns)
- Persistent browser contexts (cookies survive across sessions)
- Viewport randomization + device emulation
- Proxy support (residential/datacenter)

Integration with Agent Brain:
- Vault-backed credential storage (no plaintext passwords)
- Claude tool_use definition for researcher agent
- Falls back to Scrapling HTTP fetcher for simple pages
"""
