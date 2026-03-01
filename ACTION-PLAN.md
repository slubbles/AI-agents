# Cortex Action Plan — What Needs to Be Done

> Generated: March 1, 2026  
> Context: Solo builder, Claude API only, ~$11.74 balance, need revenue to fund development cycles

---

## Part 1: What's Left on Agent Brain?

### Short answer: The research loop is done. What's missing is reality-grounding.

The Brain's 5-layer architecture (accumulate → evaluate → adapt → evolve → transfer) works for any domain. All 5 layers are proven. **You do not need to build more Brain features to use it.**

What would make Brain *better* (not blocking, but high-value):

| What | Why | How | Priority |
|---|---|---|---|
| **Wire the Verifier** | The critic (LLM) judges the researcher (LLM). Score 5.4→8.0 might be real improvement or the system pleasing itself. Verifier breaks this circle by checking predictions against reality. | Run `--verify --domain productized-services`. It extracts time-bound claims, checks them against the web. Wire results back to KB claim confidence levels. | HIGH — but not before first sale |
| **Feed Knowledge Graph into Researcher** | Graph is built on synthesis but the researcher never reads it. Cross-claim connections and contradictions are invisible during research. | Code change: in `researcher.py`, load graph summary for the domain and inject it into the system prompt alongside strategy + KB context. | MEDIUM |
| **Auto-trigger Monitoring** | Health checks exist but only run when you manually type `--check-health`. The loop doesn't self-monitor. | Code change: call `monitoring.check_health()` at the end of `run_loop()` in `main.py`. Log alerts. Takes 20 minutes. | LOW — cosmetic until you run the daemon |

**Brain is production-ready for productized-services.** It already has 18 scored outputs, 27 KB claims, a knowledge graph, an evolved strategy, and 9 identified knowledge gaps. That's usable intelligence. Don't wait on Brain improvements to act.

---

## Part 2: Wiring — What Was Supposed to Be Connected But Isn't

### The core problem: Each loop does NOT use the full toolset. Most infrastructure is CLI-only.

### What IS wired (working today):
- **Web Search** (DuckDuckGo) → researcher uses it every run ✓
- **Web Fetcher / Scrapling** (fetch_page, search_and_fetch) → researcher uses it ✓
- **RAG** (ChromaDB) → passively indexes on save, enhances retrieval ✓
- **Domain Seeder** → provides first questions for new domains in auto mode ✓

### What IS NOT wired (built, sitting disconnected):

| Component | What it does | Why it matters | What's needed |
|---|---|---|---|
| **MCP Gateway** | Docker-based external tool servers | Could give researcher specialized tools per domain | Import `mcp.tool_bridge.get_mcp_research_tools()` in `researcher.py`. ~30 lines. Needs MCP servers configured first. |
| **Browser (Playwright)** | Stealth browser for JS-rendered/auth-required sites | Some valuable data sources need a real browser | Set `BROWSER_ENABLED=True` in config.py. Wiring exists. Need playwright + playwright-stealth installed. |
| **Monitoring** | Health checks, trend detection, alerts | Catch degradation without manual checking | Add `monitoring.check_health(domain)` at end of `run_loop()`. ~5 lines. |
| **Knowledge Graph → Research** | Graph has claim connections and contradictions | Researcher could avoid re-researching known areas | Load graph summary in researcher.py, inject into prompt. ~20 lines. |
| **Analytics → Agents** | Score trends, efficiency metrics | Meta-analyst could make better decisions with analytics context | Pass `analytics.analyze_domain()` into meta-analyst prompt. ~15 lines. |

**Recommendation:** Wire Browser first (enables researching OnlineJobsPH listings and JS-heavy prospect sites). Wire monitoring second (costs 5 lines). Others after revenue.

---

## Part 3: Should You Use Other LLM APIs?

**Not yet.** Claude-only is fine for current stage.

When to consider adding others:

| Scenario | Which API | When |
|---|---|---|
| Vision scoring (does page look good?) | OpenAI GPT-4o or Claude vision | When Hands builds landing pages for clients |
| Cheap bulk personalization (50+ messages/week) | Groq (Llama 3) | When outreach volume justifies the complexity |
| Second-opinion critic (break circular scoring) | Any non-Claude model | When you have 10+ Hands executions and want score honesty validation |
| Embeddings | Already free via `all-MiniLM-L6-v2` locally | Already handled ✓ |

Your $11.74 balance = ~8-10 full Brain loops, or ~2-3 Hands executions. Adding a second API key adds management overhead. Not worth it until you have revenue and a specific capability gap.

---

## Part 4: What Actions You Can Take From Productized-Services KB

### What Brain's 27 claims tell you:

**Your pitch positioning:**
1. Freelancer ghosting: 72% experienced it in 2024, ~50% in 2025 — epidemic scale
2. No platform publishes completion rates — your transparency is a direct counter
3. 62% of solo tech projects experience scope creep; 45% run over budget — fixed-price model eliminates this
4. Very few productized Next.js services exist (SprintPage, Superside, Flowout are all Webflow — NOT Next.js)
5. Webflow and ConvertKit do NOT offer direct build services — not competitors
6. 70% of freelancers are under 35 — perception of professional immaturity to position against

**Your competitive gap:** Nobody productizes Next.js builds. SprintPage does Webflow. Superside does Webflow. Flowout does Webflow. Next.js is your lane.

**From the 9 identified knowledge gaps — what to run next:**
- "What do startup founders on Reddit/Indie Hackers say about switching from freelancers to productized services?" (high value for pitch refinement)
- "What are SprintPage, Superside, Flowout current pricing in 2026?" (competitor intelligence)

---

## Part 5: The OnlineJobsPH Outreach Strategy

### What it is:
Find job listings for Next.js/TypeScript/landing page development on OnlineJobsPH → Click "Apply" → Send a pitch for your productized service instead of hiring yourself.

### The message structure (200-250 words):

```
Subject: Next.js site — done-for-you, 5 days, fixed price

[1. Pattern interrupt — proves you read their post]
"You're looking for a developer to build [specific thing from their listing].
I want to offer you something better than hiring."

[2. Reframe — make the alternative feel safer]
"Instead of hiring on hourly rates, I deliver this as a fixed-scope service.
You know exactly what you're getting, what it costs, and when it's done."

[3. Specific deliverable — the list that builds trust]
"Here's what's included:
- Fully responsive Next.js site, up to 5 pages
- On-page SEO (meta tags, structured data, sitemap)
- Deployed to Vercel, connected to your domain
- CMS integration so you can edit content yourself
- Delivered in 5 business days"

[4. Personalized line — from Brain's research on their company]
"I looked at [their current site/product] — [specific observation].
This build would address that specifically."

[5. Friction removal]
"50% to start, 50% when you approve the final delivery.
Revisions included until you're satisfied."

[6. Single CTA]
"Reply with 'interested' and I'll send you a detailed scope document today."
```

### What Cortex does per listing:

| Step | You | Cortex |
|---|---|---|
| Find listing | Manual browse on OnlineJobsPH | Can't do this (would need Browser + scraper) |
| Research the company | Read briefly | `python main.py "What does [company] do, who are their customers, what does their site look like?"` — ~$0.03, ~2 min |
| Personalize the opening line | Write it yourself using Brain's output | Brain gives you the specific observation |
| Draft the full message | Edit the template | Can ask Brain to draft a full message variant |
| Send | You, manually | Can't automate — platform TOS |
| Follow up (3-5 days later) | 2-sentence reminder | Too short to need automation |

### Feasibility concerns:
- **TOS risk:** Low at 5-10 messages/week. High at 50+/week (account ban risk)
- **Price sensitivity:** OnlineJobsPH skews toward hiring Filipino workers at local rates. Target project-based listings, not ongoing employment listings
- **Expected response rate:** 1-3% generic, 10-15% with genuine personalization
- **Expected sales conversion:** ~1 sale per 20-30 messages at 10-15% response rate

---

## Part 6: Lead Discovery Beyond OnlineJobsPH

### What you already have (no building needed):

Ask Brain to find leads using existing search tools:

```bash
python main.py --domain productized-services "Find recent posts (last 60 days) on Reddit, Indie Hackers, Twitter where someone is actively looking for a Next.js or React landing page developer. For each: URL, what they need, budget if stated, how to contact them."
```

Cost: ~$0.05. Uses DuckDuckGo + Scrapling already wired in.

### Platform-by-platform viability:

| Platform | Scrapable? | Risk | Best approach |
|---|---|---|---|
| OnlineJobsPH | Probably yes | Low | Manual browse + Brain research per listing |
| Reddit (r/forhire, r/webdev, r/startups) | Yes — public API | Low | Brain search query finds recent posts |
| Indie Hackers | Moderate — JS-rendered | Medium | Brain search query, fallback to Browser |
| Upwork | Difficult — anti-bot | High | Don't scrape; post your own fixed-price service |
| LinkedIn | Very difficult — requires login | Very high | Manual DM after finding posts via search |
| Twitter/X | Difficult — API is paid | High | DuckDuckGo via Brain finds public tweets |

### The three tiers:

**Tier 1 (now, $0.05, zero building):** Ask Brain to find leads via search. Manual outreach. Prove the pitch works.

**Tier 2 (after first sale, ~2 hours coding):** Add scheduled daily lead searches to the scheduler. 4-5 targeted DuckDuckGo queries. Results saved to JSON. You review each morning. ~30 lines of code.

**Tier 3 (after 5 sales with revenue):** Per-platform scrapers, auto-research, auto-draft queue. Brain finds + researches + drafts. You approve + send.

**Build Tier 3 after Tier 1 is proven, not before.**

---

## Part 7: Priority Decision — Build Cortex More or Use It Now?

| Path | Time to first revenue | API cost | Risk |
|---|---|---|---|
| Make Cortex fully autonomous first | 2-4 weeks dev, then start selling | $5-10 + all session time | Run out of credits before selling anything |
| Use what Cortex knows, sell manually | This week | ~$1 for prospect research | Revenue funds next dev cycle |
| Hybrid (Brain researches, you sell, Hands helps build) | This week for outreach, 1-2 days/delivery | $1-3 per delivery | Best balance |

**Recommendation: Hybrid.** Brain already did the productized-services research. The KB exists. The strategy exists. The pitch template exists. The intelligence is ready to use.

### The sequence this week:

1. Read the 27 KB claims → finalize your offer (scope, price, deliverables, guarantee)
2. Write your first pitch message using the template above
3. Find 5 listings on OnlineJobsPH manually
4. For each: run Brain to research the company (~$0.15 total) → add personalized line → send
5. While waiting for responses: `python main.py --auto --domain productized-services --rounds 3` to fill KB gaps (~$0.30)
6. When you get a client: use Hands to generate the initial site structure, review/fix/deploy

**Revenue funds development. Development improves revenue. That's the compound loop — but it runs through you, not around you.**
