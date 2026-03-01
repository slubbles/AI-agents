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

### The core problem: You thought each loop used the full toolset. It doesn't.

Here's what's actually happening vs. what should happen:

### What IS wired (working today):
- **Web Search** (DuckDuckGo) → researcher uses it every run ✓
- **Web Fetcher** (fetch_page, search_and_fetch) → researcher uses it ✓
- **RAG** (ChromaDB) → passively indexes on save, enhances retrieval ✓
- **Domain Seeder** → provides first questions for new domains in auto mode ✓

### What IS NOT wired (built, sitting disconnected):

| Component | What it does | Why it matters for each cycle | What's needed to wire it |
|---|---|---|---|
| **MCP Gateway** | Docker-based external tool servers (6 files, 1,759 lines) | Could give researcher access to specialized tools (GitHub API, data sources, etc.) per domain | Import `mcp.tool_bridge.get_mcp_research_tools()` in `researcher.py`, append MCP tools to the researcher's tool list when `MCP_ENABLED=True`. ~30 lines of code. But you'd also need relevant MCP servers configured — currently none are. |
| **Browser** | Stealth Playwright browser for JS-rendered/auth-required sites | Some valuable data sources (LinkedIn job posts, paywalled research) need a real browser | Set `BROWSER_ENABLED=True` in config.py. The wiring already exists in researcher.py — it checks the flag and loads browser tools. You'd need `playwright` and `playwright-stealth` installed. |
| **Monitoring** | Health checks, trend detection, alerts | Catch degradation (score drops, budget overruns, strategy regressions) without manual checking | Add `monitoring.check_health(domain)` call at end of `run_loop()` in main.py. ~5 lines. |
| **Knowledge Graph → Research** | Graph has claim connections, contradictions | Researcher could avoid re-researching known areas, focus on actual gaps | Load graph summary in researcher.py, inject into prompt. ~20 lines. |
| **Analytics → Agents** | Score trends, efficiency metrics, cost data | Meta-analyst could make better strategy decisions with analytics context | Pass `analytics.analyze_domain()` output into meta-analyst prompt. ~15 lines. |

### Should you wire these now?

**No.** Here's why: every wiring change costs debugging time, not API money. The cost is your session hours. The current loop already produces score-7+ research for productized-services without MCP, browser, or monitoring. Wire these *after* you have revenue and want to improve cycle quality for future domains.

### The one exception:

If you want to research **specific OnlineJobsPH listings** (to personalize outreach), you'd need the **Browser** because OnlineJobsPH likely requires JavaScript rendering. That's the one wiring fix that directly impacts your revenue path. Cost: install playwright, set `BROWSER_ENABLED=True`, test. ~30 minutes.

---

## Part 3: Should You Use Other LLM APIs?

### Short answer: Not yet. Here's when you should.

**What you have now:**
- Claude Haiku 4.5 — researcher (cheap, fast, ~$0.001/1K input)
- Claude Sonnet 4 — critic, meta-analyst, synthesizer (stronger, ~$0.003/1K input)
- Balance: ~$11.74

**When other APIs make sense:**

| Scenario | Which API | Why | When |
|---|---|---|---|
| **You need vision** (screenshot scoring for Hands output) | OpenAI GPT-4o or Claude with vision | Evaluating whether a generated landing page *looks good* can't be done with text-only models. The Hands validator scores code quality but not visual quality. | When you start using Hands to build landing pages for clients — not yet |
| **You need cheap bulk** (mass outreach personalization) | Groq (Llama 3) or Mistral API | Personalizing 50 outreach messages costs ~$0.50 with Claude Haiku. Groq/Mistral could do it for ~$0.05. But the quality difference on a 200-word message is negligible. | When you're sending 50+ messages/week — not yet |
| **You need code execution scoring** | OpenAI GPT-4o or Claude Sonnet | If you want a *second opinion* critic to break the circular scoring problem (two different model families scoring the same output), a non-Claude critic adds genuine signal. | When you have 10+ Hands executions and want to validate score honesty — not yet |
| **You need embeddings** | Already using `all-MiniLM-L6-v2` locally (free) | Your RAG already uses a free local model. No API needed for embeddings. | Already handled ✓ |

**Bottom line:** Claude-only is fine for where you are. The $11.74 balance gets you roughly:
- ~47 Haiku research runs ($0.02-0.05 each)
- ~15 Sonnet critic/synthesis runs ($0.10-0.30 each)
- Or ~8-10 full Brain loops (research + critique + retry)
- Or ~2-3 full Hands executions ($0.50-1.00 each)

Adding a second API adds complexity (key management, cost tracking across providers, prompt format differences). Not worth it until you have revenue and a specific capability gap Claude can't fill.

---

## Part 4: What Actions You Can Take From the Productized-Services KB

### What Brain found (the 27 claims, distilled):

**Your market positioning (what to say in pitches):**

1. **Freelancer ghosting is epidemic.** 72% of freelancers experienced client ghosting in 2024, ~50% in 2025. The problem is massive and widely felt — from both sides.
2. **No platform publishes completion rates.** Upwork, Toptal, Fiverr — none disclose project success rates. Your transparency ("fixed scope, fixed price, you see exactly what you get") directly addresses this trust gap.
3. **62% of solo tech projects experience scope creep.** 45% run over budget. Your fixed-price model eliminates this.
4. **Very few true productized landing page services exist.** Your known competitors: SprintPage (48-hour Webflow, unlimited revisions), Superside (modular Webflow + CRO), Flowout (Webflow subscription). None of these do Next.js.
5. **Webflow and ConvertKit do NOT offer direct build services** — Brain verified this. Don't worry about them as competitors.
6. **70% of freelancers are under 35**, and the perception is lack of professional maturity. You can position as the "adult in the room" — fixed process, fixed deliverable, no surprises.

**Your competitive edge (based on KB gaps = nobody has this data):**

- No one publishes React/Next.js specific completion rates → you can become the authority
- No comparative data exists: freelance vs. agency vs. productized → your case studies become the evidence
- SprintPage does Webflow. Superside does Webflow. Flowout does Webflow. **Nobody productizes Next.js builds.** That's your lane.

**What you still don't know (9 knowledge gaps Brain identified):**

| Gap | Actionable? | What to do |
|---|---|---|
| No data on freelance project abandonment rates | Not directly actionable — the data doesn't exist publicly | Use this as positioning: "The industry won't tell you how often projects fail. I guarantee mine don't." |
| No platform-specific completion rates | Same — use as trust angle | "Unlike platforms that hide their success rates, I show you exactly what you're getting." |
| No React/Next.js specific project data | You'll create this data yourself by delivering | After 3-5 deliveries, you ARE the data source. |
| Pricing info for most competitors | Somewhat actionable | Run Brain: "What are SprintPage, Superside, Flowout current pricing plans in 2026?" |
| Documented reasons founders switch to productized | Very actionable | Run Brain: "What do startup founders on Reddit/Indie Hackers say about switching from freelancers to productized services?" |
| Formal QA processes of competitors | Low priority | Nice to know, not need to know |

**Immediate actions from KB findings:**

1. **Finalize your offer spec.** The KB gives you the competitive landscape. Nobody does productized Next.js. SprintPage does Webflow in 48 hours. You do Next.js in 5 days. Your offer: "5-page Next.js marketing site, SEO-optimized, deployed to Vercel, CMS included, 5 business days, $X fixed price."

2. **Set your price.** The KB doesn't have direct pricing data for Next.js productized services (because none exist). But SprintPage charges for Webflow (simpler stack). You're offering a more technical stack. $300-500 is the range your notes suggest. Start at $300 if you want faster closes on OnlineJobsPH, $500 if targeting LinkedIn/Upwork.

3. **Build your pitch around the trust gap.** The KB's strongest finding: nobody publishes success rates, freelancers ghost constantly, scope creep is ~62%. Your entire pitch is: "I'm the opposite of that risk."

---

## Part 5: Your OnlineJobsPH Strategy — What Cortex Can Actually Do For You

### Your strategy (as I understand it):

1. Go to OnlineJobsPH
2. Search for job listings matching your skills (full-stack, Next.js, TypeScript, landing pages)
3. Click "Apply" — which opens a message form (subject + message body)
4. Instead of pitching yourself as a hire, pitch your **productized service** — fixed scope, fixed price, fixed timeline
5. If they're interested, they reach out

This is high-intent lead interception. The person already wants this thing built. You're offering a better way to get it done than hiring someone.

### What Cortex can do for each step:

| Step | What you do | What Cortex does | How |
|---|---|---|---|
| **Find listings** | You browse OnlineJobsPH manually | Brain can't do this yet (would need Browser wired + OnlineJobsPH scraping). **This stays manual for now.** | — |
| **Research the company** | You'd normally skip this | Brain researches the company/person posting the job: their website, what they sell, who their customers are, what their current site looks like. This takes Brain ~2 minutes and costs ~$0.03. | `python main.py --domain productized-services "What does [company name] do, who are their customers, and what does their current website look like?"` |
| **Personalize the message** | You'd write something generic | Brain's research gives you one killer personalized line: "I looked at [their site] — your [product] is strong but [specific issue] on the landing page is likely costing you conversions." | Read Brain's output, extract the specific insight, paste it into the opening line of your template |
| **Draft the full message** | You write it from the template | Cortex can generate a full draft using the template structure + company research + KB intelligence about market pain points. | `python main.py --domain productized-services "Draft an outreach message for [company] who posted a job for a Next.js developer. Use the productized service pitch format: pattern interrupt, reframe, specific deliverable, friction removal, single CTA. Company context: [paste what you found]."` |
| **Follow up** | You send a follow-up 3-5 days later | Brain can draft the follow-up too. But honestly, follow-ups are short enough to write yourself. | Manual — it's 2 sentences |

### The actual message template (from your notes, refined with KB data):

**Subject:** `Next.js site — done-for-you, 5 days, fixed price`

**Body structure (200-250 words):**

```
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

[5. Friction removal — kill the biggest objection]
"50% to start, 50% when you approve the final delivery.
Revisions included until you're satisfied."

[6. Single CTA]
"Reply with 'interested' and I'll send you a detailed scope document today."
```

### What Cortex CANNOT do for you (be honest about this):

- **Send messages.** You send them manually. OnlineJobsPH doesn't have an API. Even if it did, automated messaging would get you banned.
- **Close sales.** The conversation, trust-building, scope negotiation — that's you. Cortex researches and drafts. You deliver.
- **Build the actual site autonomously (yet).** Hands has 1 execution output ever. It can attempt to build a landing page, but you'd need to review and fix it heavily. For the first 2-3 deliveries, you're building manually (or using Hands as a starting point and finishing it yourself).
- **Research OnlineJobsPH listings directly.** Would need Browser wired + scraping logic. Not worth building until you've validated the outreach works manually.

### What Cortex CAN do that gives you real competitive advantage:

- **Per-listing research in 2 minutes** — what the company does, their current site, their market. Nobody else applying to that listing does this.
- **Draft personalized pitches at volume** — once you have the template working, Brain customizes each one with company research. The difference between 3% and 15% response rate.
- **Knowledge base that compounds** — every research run adds to what Brain knows about the productized services market. After 10 deliveries, Brain understands your niche better than you do.
- **Eventually: build the deliverable** — once Hands has enough scored executions (20+), it can generate the initial Next.js site that you then polish and deliver. That's when you go from "I build sites" to "my system builds sites and I QA them."

---

## Part 6: The Priority Decision — Build Cortex or Use It Now?

### The math:

| Path | Time to first revenue | API cost | Risk |
|---|---|---|---|
| **A: Make Cortex fully autonomous first** | 2-4 weeks of development, then start selling | $5-10 in API + all your session time | You run out of credits before selling anything. Cortex gets better but produces $0. |
| **B: Use what Cortex already knows, sell manually** | This week. You have the KB, the template, the strategy. | $0.50-1.00 for per-listing research | Revenue funds the next development cycle. |
| **C: Hybrid — use Brain for research, Hands for first draft, you for delivery** | This week for outreach, 1-2 days per delivery | $1-3 per delivery (research + execution attempt) | Best balance. Cortex helps where it's strong (research, drafting), you handle what it can't (sales, final QA, deployment). |

### My recommendation: **Path C.**

Here's the sequence:

1. **Today:** Read the KB claims above. Finalize your offer (scope, price, deliverables list). Write the first version of your pitch message using the template.

2. **Tomorrow:** Go to OnlineJobsPH. Find 5 listings. For each one, run Brain to research the company (~$0.15 total). Personalize the pitch. Send 5 messages.

3. **While waiting for responses:** Run `python main.py --auto --domain productized-services --rounds 3` to fill KB gaps (~$0.30). This makes future pitches sharper.

4. **When you get a client:** Use Hands to generate the initial site structure: `python main.py --execute --goal "Build a 5-page Next.js marketing site for [client's business]" --workspace /path/to/project`. Review what it produces. Fix what's wrong. Deploy.

5. **After delivery:** The execution output gets scored. That's data point #2 for Hands. After 5 deliveries, Hands has enough data to start evolving its execution strategy.

**Revenue funds development. Development improves revenue. That's the compound loop — but it runs through you, not around you.**

---

## Part 7: What to Do in This Session (Right Now)

If you want to act based on everything above, here's what costs $0 in API:

1. **Read the 27 KB claims** in `memory/productized-services/_knowledge_base.json` — you're looking for insights that sharpen your pitch
2. **Write your offer spec** — deliverables list, price, timeline, guarantee
3. **Write your first pitch message** using the template structure from your notes
4. **Identify 5 OnlineJobsPH listing keywords** you'll search for tomorrow

What costs ~$0.50 in API:
- Run Brain on 5 company names from OnlineJobsPH listings to personalize pitches
- Run `--auto --rounds 2` to fill the top 2 KB gaps

What costs nothing but session time:
- Set `BROWSER_ENABLED=True` and install playwright if you want Brain to fetch JS-rendered pages (useful for researching prospect companies)
- Wire monitoring into the loop (5 lines of code, helps when you eventually run auto mode longer)

**The KB is your weapon. The pitch template is your ammo. OnlineJobsPH is your battlefield. Cortex already did the reconnaissance. Now you execute.**
