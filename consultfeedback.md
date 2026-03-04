tell me about threads api, and if its free or not, and how we could possibly use it as one of marketing platform for cortex

Mar 3

Synthesized Threads API research for Cortex marketing strategy
Synthesized Threads API research for Cortex marketing strategy
Here's the full picture.

Threads API — What It Actually Is
The Threads API is a specialized part of the larger Meta Graph API — the same central nervous 
Inceptmvp
 system that powers Facebook and Instagram. It's built on RESTful principles, uses OAuth 2.0 authentication, and gives developers a direct programmatic line into the Threads platform.

Meta opened the Threads API to all developers in June 2024 at the Cannes Lions Festival. Since then they've shipped consistent updates — webhooks, search, analytics, polls, location tagging, click metrics, DMs, and GIF support through July 2025. 
DEV Community

Is It Free?
Yes. And this is the big difference from every other major platform.

You need a Meta developer account and your account must be verified as a business account. You create a business app in the Meta app dashboard, select "Access the Threads API," and you're in. 
Lovable

Compare that to X/Twitter: the Basic plan runs $200 per month for a mere 15,000 tweet reads, while Pro skyrockets to $5,000 monthly. 
X

Threads API costs you nothing to access. The rate limits are generous for Cortex's use case — you're not scraping millions of posts, you're posting and reading strategically.

What It Can Actually Do
POSTING:
  → Publish text posts
  → Publish with images, videos, GIFs
  → Create polls (up to 4 options)
  → Add location tags
  → Add topic tags (their version of hashtags)
  → Set reply restrictions (who can reply)

READING:
  → Search posts by keyword or topic
  → Read replies and conversations
  → Access public profiles
  → Read trending topics
  → Monitor mentions and tags

ANALYTICS:
  → Post impressions
  → Engagement metrics (likes, replies, reposts, shares)
  → Click metrics on links — critical for Cortex
  → Follower counts and growth

REAL-TIME:
  → Webhooks — get notified when someone
    replies to your post, mentions you,
    or engages with your content
    instantly, without polling
The Platform Context
Threads reached 320 million monthly active users by early 2025, adding 30 million users in just one quarter. 
Medium

That's a growing, engaged platform with a free API, real search, and webhooks. For Cortex's growth capability, this is the best available combination right now.

How Cortex Uses This Specifically
Here's exactly how it fits into the Growth Capability inside Agent Hands:

Pre-launch — Brain uses Threads for research:

Brain searches Threads for pain points
in the target niche using keyword search API

Example:
  Searching "invoice" + "freelance" + "frustrated"
  returns real posts from real people
  with exact language they use
  
Same as Reddit research but different audience
Threads users tend to be more creator/builder focused
Reddit users tend to be more consumer focused
Both together give Brain a fuller picture
At launch — Outreach Agent posts to Threads:

Hands Growth Capability:
  → Writes a post about the product launch
    using Brain's extracted user language
  → Posts via Threads API
  → Monitors: impressions, clicks, replies
    via Analytics endpoints

Not spam. One genuine post.
"Built this because I kept seeing people
complain about X. Here's what we made: [URL]"
Post-launch — Webhook feedback loop:

Threads webhooks notify Cortex when:
  → Someone replies to the launch post
  → Someone mentions the product
  → Engagement spikes on a post

Brain reads those replies:
  → What are people saying?
  → Feature requests hiding in replies?
  → Complaints? Pain points?
  → Positive signals worth amplifying?

This closes the loop:
Post → Engagement → Brain reads responses →
Cortex decides → Hands iterates product or content
Ongoing — Content Agent builds presence:

Not daily posting spam.
Strategic posts tied to what Brain is researching.

Example cadence:
  Week 1: Launch post ("we built X for Y pain")
  Week 2: "Here's what we learned from our first users"
  Week 3: "The feature our users asked for most"
  Week 4: "How we built [specific technical thing]"

Each post:
  → Written by Content Agent using Brain's research
  → Posted via Threads API with timing variation
  → Monitored for click-through to product
  → Results fed back to Brain
Threads vs Reddit For Cortex
REDDIT                          THREADS
────────────────────────────────────────────────
Best for: research              Best for: distribution
Finding pain                    Broadcasting solutions
Specific communities            Broader reach
Anonymous complaints            Public, named conversations
Free API (100 QPM)              Free API
No native post analytics        Full click + engagement analytics
Hard to build following         Easier to build following
                                Instagram audience crossover
                                320M MAU and growing
Use both. Different jobs.

Reddit is where Brain listens and learns. Threads is where Hands Growth Capability speaks and distributes.

The Setup Required
Simpler than any other platform:

1. Meta developer account (free)
2. Business account verification (1-2 days)
3. Create a business app in Meta dashboard
4. Select "Access the Threads API"
5. Get your access token
6. One Python library handles the rest

No monthly fee. No enterprise contract.
No waiting for API access approval beyond
the business verification step.
Bottom Line
Threads API is the best marketing platform for Cortex at this stage because:

→ Free (unlike X at $200-5000/month)
→ Growing fast (320M MAU, not a dead platform)
→ Full analytics including link clicks
→ Webhooks for real-time feedback loop
→ Search API for Brain's research
→ Large enough to matter, small enough
   that organic reach still works
→ Creator/builder demographic matches
   the products Cortex will build
Add it to the Growth Capability inside Agent Hands. Brain uses it for research. Outreach Agent uses it for distribution. Analytics Agent reads the results. The feedback loop is clean, real-time, and costs nothing to run.

it can have, say an own account, and or set multiple? i mean technically, if dont violate T&C

Mar 3

Crystallized perspective on multiple Threads accounts feasibility
Crystallized perspective on multiple Threads accounts feasibility
Here's the honest breakdown.

One Account — Clean, Official, No Risk
The API is aimed at business customers. You create a business app in the Meta dashboard, verify your account as a business, select 
Visual Studio Magazine
 "Access the Threads API" and you're in.

One Cortex instance. One Threads account. One Instagram business account behind it. Completely legitimate. This is what Buffer, Hootsuite, and every social scheduling tool does. No TOS issues whatsoever.

For your current goal — one Cortex building one webapp in one niche — this is all you need.

Multiple Accounts — Where It Gets Real
Yes, Meta allows multiple accounts on Threads. There's no rule saying you're limited to one. 
X

But here's the catch.

Threads deploys sophisticated systems to detect multi-account operations: device fingerprinting, IP address monitoring, shared cookies, and behavioral signals. Once accounts are linked, bans can spread across your entire network — even if only one profile violates policy. 
LinkedIn

So technically allowed. But Meta actively tries to detect and link them.

How This Maps To Cortex's Architecture
This is where it gets interesting for you specifically.

CURRENT GOAL (one Cortex, one niche):
  One Threads account
  One Instagram business account behind it
  Official API
  Zero risk
  Posts about the one webapp being built

FUTURE VISION (multiple Cortex instances, multiple niches):
  One Threads account per Cortex instance
  Each linked to its own Instagram business account
  Each on its own VPS
  Different IP addresses naturally
  Different posting behavior naturally
  
  This is exactly what agencies do legitimately.
  Each client gets their own account.
  Each Cortex is essentially a separate "client."
For agencies or businesses managing multiple Threads accounts, the approach is separate profile keys per account — each account operates independently through the same API. 
Medium

The key is that your multi-instance architecture — one Cortex per VPS per niche — naturally produces the separation Meta wants to see. Different IPs, different posting patterns, different content, different accounts. That's not evasion. That's just how multiple independent products operate.

The One Thing To Get Right
Each Threads account needs its own Instagram business account behind it. That's the constraint. Threads is linked to Instagram at the account level — one Threads profile per Instagram account. 
X

So the setup for each Cortex instance:

Cortex Instance (VPS 1, niche: freelance invoicing)
  → Instagram Business Account: @cortex_invoicetool
  → Threads Account: @cortex_invoicetool  
  → Threads API app (free, Meta developer dashboard)
  → Posts about that specific product only

Cortex Instance (VPS 2, niche: client portals)
  → Instagram Business Account: @cortex_clientportal
  → Threads Account: @cortex_clientportal
  → Separate Threads API app
  → Posts about that specific product only
Clean. Legitimate. Scalable. Each Cortex instance has its own voice, its own niche, its own audience. Not one account pretending to be many. Many accounts each genuinely representing one product.

Bottom Line
NOW:    One account. Official API. Free. Zero risk.
        Cortex posts about the one webapp it built.

LATER:  One account per Cortex instance.
        Each on its own VPS with its own IP.
        Each with its own Instagram business account.
        Fully legitimate multi-brand operation.
        Scales exactly as your VPS instances scale.
The architecture you already planned — one Cortex per VPS per niche — naturally solves the multiple account problem without any gray area. You're not running one entity pretending to be many. You're running many independent products each with their own legitimate presence.


CORTEX_CONSULTANT_HANDOFF (1).md
md

okay, heres the recent progress made so far

what you think?

9:14 AM

Assessed impressive one-day progress across multiple technical objectives
Assessed impressive one-day progress across multiple technical objectives
Genuinely impressive. Let me be specific about what stands out.

What's Real Progress
One day. Objectives 1-5. March 3 to March 4. That's the three critical bugs fixed, prompt upgrades, full three-way communication protocol, Playwright visual system, and the entire visual standard trained. That's not small. Most teams would have spread that across two weeks.

The protocol.py is the right call. Typed dataclass messages between Brain, Cortex, and Hands — this is the difference between a system that works by accident and one that works by design. 10 message types covering every direction of communication. This is the backbone everything else hangs on.

The Identity Layer expansion from 5 to 8 files matters more than it sounds. design_system.md, marketing_design.md, visual_scoring_rubric.md — these are not documentation. These are the persistent intelligence that makes every Hands execution start from a quality floor instead of zero. Brain researched what beautiful means. It's now locked in the system permanently. That compounds.

The visual gate architecture is correct. Auto-skips when no frontend files exist — zero cost when not needed. Page-type aware — app vs marketing get different standards. Resource cleanup on abort. These are details that show the system is being built to run 24/7, not just to demo.

1,737 tests passing. Up from 1,538. 199 new tests covering the new systems. This is discipline. You're not just building — you're verifying.

What I'm Honest About
VPS is still on d9800ca. Everything from Objective 2 onwards — the protocol, the visual system, the design standards — none of it is running on the server yet. The most important step right now is git pull and restart. Until that happens, the VPS is running the fixed-bugs-only version while the real system exists only locally.

Budget halt at $25.40 against a $7 limit tells you the system is researching actively — maybe too actively. When you pull the new code and restart, watch the first few cycles carefully. The budget fix from Objective 1 is in there but $25.40 in one day on a $7 budget means something ran hot before the halt kicked in. Worth understanding what drove that spend before letting it run unsupervised again.

The 4 stale imports are a time bomb. sync.py calling execute instead of execute_plan, project_orchestrator.py same issue, scheduler.py missing page_type in the execute_plan call. These will silently fail at runtime in ways that are confusing to debug. Fix them before Objective 6 — not after.

The One Thing That Changes Everything Now
You are one git pull and one Hands execution away from knowing if the whole system works end to end.

Everything you built in Objectives 1-5 was infrastructure. Protocol, visual system, design standards, communication layer — all of it was setting the stage. Objective 6 is the performance. The first time Cortex takes a niche, Brain researches it, Hands builds something, Playwright screenshots it, Claude Vision evaluates it, and a URL comes back to Telegram — that's when you know the transistor works.

Immediate next steps, in order:

1. git pull on VPS
2. Fix 4 stale imports (30 minutes)
3. Restart services
4. Watch one full cycle complete cleanly
5. Trigger first Hands execution manually
6. Get the URL
Everything else — Reddit pipeline, Growth capability, Threads API, multi-instance — waits for that URL.

You're close. Closer than the document makes it feel because the hard architectural decisions are already made and implemented. What remains is execution, not design.

I cant do this part for now as I have no budget for API Claude for now, but can still able to develop it and improve the whole AI system but not the self learning by running cycles.

What was the next big goal from here? Divide it into objectives and divide those objectives into tasks

but without the running cycles for now

9:21 AM

Architected comprehensive development roadmap for autonomous builder system
Architected comprehensive development roadmap for autonomous builder system
The Next Big Goal
Build Agent Hands into a fully capable autonomous builder — so when budget returns, Objective 6 executes on the first try.

Right now Hands exists but isn't built for the 7-phase full-stack build we defined. The visual system is there. The tools are there. The communication protocol is there. But the actual build pipeline — the phases, the Hands-as-orchestrator architecture, the MCP integrations, the Docker isolation — none of that is wired up yet.

That's all pure code. Zero API calls needed.

OBJECTIVE A: Fix The Foundation First
Before building anything new, clean up what's broken.

Task A1: Fix sync.py stale imports

execute → execute_plan
validate → validate_execution
Task A2: Fix project_orchestrator.py stale import

Same execute → execute_plan fix
Task A3: Fix scheduler.py missing params

execute_plan() call needs page_type and visual_context parameters
Task A4: Update VPS

git pull
systemctl restart cortex-daemon cortex-telegram
Verify services start clean
Task A5: Verify 1,737 tests still pass after fixes

Run full test suite locally
Fix any regressions before moving forward
OBJECTIVE B: Agent Hands as Its Own Orchestrator
Right now Hands is flat — Planner → Executor → Validator with no internal intelligence supervising the process. This objective restructures Hands so it coordinates its own phases internally, communicating with Cortex as a peer not a subordinate.

Task B1: Create hands/orchestrator.py

The internal brain of Agent Hands.

Responsibilities:
  → Receives BuildTask from Cortex via protocol
  → Owns the phase sequence internally
  → Decides: proceed, retry, ask Brain, escalate
  → Tracks cost across all phases
  → Routes ContextNeeded messages up to Cortex
  → Sends PhaseComplete and BuildComplete back
  → Never lets phase agents talk directly to Cortex

Methods:
  run_build(task: BuildTask) → BuildComplete | BuildFailed
  _run_phase(phase, context) → PhaseResult
  _handle_phase_failure(phase, error) → Decision
  _request_context(question) → ContextResponse
  _check_budget(phase) → bool
Task B2: Define the phase registry

hands/phases/__init__.py

PHASES = [
  "context_intake",
  "architecture", 
  "workspace_setup",
  "backend",
  "frontend",
  "integration_test",
  "deploy",
  "critic"
]

Each phase:
  → has a name
  → has a required flag (if required fails → abort)
  → has a cost ceiling
  → has a success condition
  → has a max retry count
Task B3: Create base phase class

hands/phases/base.py

class BuildPhase:
  name: str
  required: bool
  max_retries: int
  cost_ceiling: float
  
  def run(self, context: PhaseContext) → PhaseResult
  def validate(self, result: PhaseResult) → bool
  def on_failure(self, error, attempt) → FailureAction
Task B4: Wire orchestrator into scheduler

scheduler.py currently calls executor directly
Change: scheduler → Hands Orchestrator → phases
Hands Orchestrator is the only entry point
OBJECTIVE C: Build The 7 Phase Agents
Each phase is its own focused agent with a single responsibility. Build them one by one.

Task C1: hands/phases/context_intake.py

Input: BuildTask (niche, goal, constraints)
Does:
  → Reads Brain's knowledge base for this domain
  → Extracts: user pain, core feature, tech constraints
  → Defines success criteria for this specific build
  → Writes PRD.md to workspace

Output: Structured PRD with:
  → Who the user is
  → What the one core problem is
  → What the MVP feature set is
  → What success looks like
  → Stack decision (Next.js + Supabase + Vercel default)

No API call needed to write this phase.
The logic is deterministic from Brain's output.
Task C2: hands/phases/architecture.py

Input: PRD from context_intake
Does:
  → Decides file/folder structure
  → Defines API contract (endpoints, request/response)
  → Designs Supabase schema
  → Maps component hierarchy
  → Lists environment variables needed
  → Writes ARCHITECTURE.md to workspace

Output: Blueprint document
Flag: requires_human_review = True (the one gate)
Task C3: hands/phases/workspace_setup.py

Input: ARCHITECTURE.md
Does:
  → Creates isolated workspace directory
  → Scaffolds Next.js project (npx create-next-app)
  → Installs dependencies (shadcn, framer-motion, etc.)
  → Initializes Git repo
  → Creates .env.local template
  → Sets up Supabase project via MCP (when added)
  → Runs: npm run dev → verifies starts clean
  → Takes first Playwright screenshot

Output: Running scaffold, verified green
Task C4: hands/phases/backend.py

Input: ARCHITECTURE.md + workspace
Does:
  → Creates Supabase schema (SQL migrations)
  → Writes API routes one by one
  → Tests each route via HTTP tool before moving on
  → Implements auth (Supabase Auth)
  → Writes RLS policies
  → Verifies: all endpoints return correct shapes

Rule: frontend phase cannot start until this passes
Output: Verified API contract + working auth
Task C5: hands/phases/frontend.py

Input: ARCHITECTURE.md + verified API + design_system.md
Does:
  → Injects full design system prompt
  → Builds layout shell first
  → Builds auth pages
  → Builds core feature pages
  → After each major component: screenshot + evaluate
  → Iterates until visual score ≥ 8
  → Mobile-first, all states designed

Output: Complete UI, visual score ≥ 8
Task C6: hands/phases/integration_test.py

Input: Running app (dev server)
Does via Playwright:
  → Navigate to /signup
  → Fill form → submit → verify redirect
  → Complete core user action
  → Verify data in database (HTTP tool to API)
  → Log out → log back in → verify session
  → Test one error state (bad input)
  → Run npm run build → must pass clean

Output: Test results (pass/fail per step)
Abort condition: build fails or auth broken
Task C7: hands/phases/deploy.py

Input: Passing integration tests
Does:
  → Push to GitHub via Git tool
  → Deploy to Vercel via CLI or MCP
  → Set production environment variables
  → Wait for deploy URL
  → Screenshot live URL (not localhost)
  → Run smoke test against production URL
  → Verify core flow works in production

Output: Live URL + screenshot
Task C8: hands/phases/build_critic.py

Input: Live URL + test results + total cost
Does:
  → Scores the full build against PRD
  → Evaluates visual quality from screenshot
  → Checks all success criteria defined in context_intake
  → Extracts execution lessons
  → Stores lessons in exec_memory
  → Feeds patterns to pattern_learner
  → Reports score + URL + lessons to Cortex

Output: Build score + lessons + final report
OBJECTIVE D: MCP Integrations
These are the tools that make the phases actually work without manual intervention. All setup and integration work — no API calls needed.

Task D1: Set up Playwright MCP

Install playwright MCP server
Wire into browser.py tool
Test: can take screenshot of a URL
Test: can click, fill, navigate
This already exists partially — complete and verify
Task D2: Set up Supabase MCP

Install Supabase MCP
Add to tools registry
Methods needed:
  → create_table(schema)
  → run_migration(sql)
  → query(sql)
  → get_project_url()
  → get_anon_key()
Test: can create table, insert row, query it
Task D3: Set up Vercel MCP

Install Vercel MCP or use Vercel CLI wrapper
Methods needed:
  → deploy(project_dir, env_vars)
  → get_deployment_url(deployment_id)
  → set_env_var(key, value)
Test: can deploy a Next.js scaffold, get URL back
Task D4: Docker sandbox setup

Create Dockerfile for isolated build environments
Each Hands build gets its own container:
  → Own filesystem
  → Own Node process
  → Own port (auto-assigned)
  → Torn down after deploy completes

hands/sandbox.py:
  → create_sandbox() → container_id
  → run_in_sandbox(container_id, command)
  → copy_to_sandbox(container_id, local_path)
  → copy_from_sandbox(container_id, path)
  → destroy_sandbox(container_id)
Task D5: MCP registry in tools

Update hands/tools/registry.py to include:
  → playwright_mcp
  → supabase_mcp
  → vercel_mcp
Each with health check on startup
OBJECTIVE E: Reddit Research Pipeline
Brain learns to find product opportunities on Reddit. Pure code — PRAW is free, no API costs for reading Reddit.

Task E1: Add PRAW to Brain's tools

tools/reddit_scraper.py

Methods:
  → search_posts(subreddit, query, limit, time_filter)
  → get_top_posts(subreddit, limit, time_filter)
  → get_comments(post_id, limit)
  → search_by_flair(subreddit, flair)

Returns: structured post data with
  → title, body, score, comment_count
  → top comments
  → timestamp, author karma
Task E2: Pain point extractor

agents/reddit_analyst.py

Takes: raw Reddit posts
Does:
  → Filters for complaint/frustration signals
  → Extracts exact user language
  → Scores each pain: specificity, frequency,
    willingness-to-pay signals, buildability
  → Deduplicates similar pain points
  → Ranks opportunities

Returns: top 3 opportunities with:
  → Pain description in user's own words
  → Evidence (post links, quote count)
  → Confidence score
  → Suggested solution direction
Task E3: Connect Reddit analyst to Brain's research loop

In question_generator.py:
  → Add reddit_research as a question type
  → When domain goal involves finding opportunities:
    route to reddit_analyst instead of web search

In scheduler.py:
  → Add reddit research cycle option
  → Different from standard research cycle
  → Runs before build tasks, not alongside them
Task E4: Dual output from research

When Brain finishes Reddit research, 
it produces two documents simultaneously:

1. product_brief.md:
   → What to build
   → Core feature
   → Technical constraints

2. marketing_brief.md:
   → User's exact language (becomes copy)
   → Channels where these users are
   → What messaging will resonate
   → Competitor weaknesses to exploit

Both passed to Cortex.
Cortex passes product_brief to Hands build.
Cortex stores marketing_brief for Growth capability later.
OBJECTIVE F: Threads API Integration
Marketing foundation. Free to set up, free to use.

Task F1: Create Threads API client

tools/threads_client.py

Methods:
  → post(text, media_url=None) → post_id
  → reply(post_id, text) → reply_id
  → search(query, limit) → posts
  → get_metrics(post_id) → impressions, clicks, likes
  → get_mentions() → mention list
Task F2: Set up webhook listener

tools/threads_webhook.py

Listens for:
  → New reply to any Cortex post
  → New mention of product
  → Engagement spike

On event:
  → Store to DB (new table: social_events)
  → Queue for Brain to analyze
Task F3: Outreach Agent (Growth Capability — Phase 1)

hands/growth/outreach_agent.py

Takes: marketing_brief + product URL
Does:
  → Identifies top 3-5 relevant threads on Threads
  → Drafts genuine, non-spammy reply for each
    (helpful first, product second)
  → Posts with randomized timing (not all at once)
  → Tracks: did anyone click? did anyone reply?
  → Reports metrics back to Cortex

Constraints baked in:
  → Max 3 posts per day per account
  → Minimum 2 hours between posts
  → Never post same content twice
  → Flag for human review if reply seems negative
Task F4: Social events table in DB

db.py: add social_events table
  → platform (threads, reddit)
  → event_type (post, reply, mention, click)
  → content
  → metrics
  → timestamp
  → linked_product

This is the raw data Brain will analyze
for what marketing is working.
OBJECTIVE G: Cortex Pipeline Method
The full end-to-end flow wired together. The method that accepts your one-sentence instruction and coordinates everything.

Task G1: Complete agents/cortex.py pipeline() method

def pipeline(niche: str, build_type: str):
  
  # Phase 1: Research
  research_req = ResearchRequest(
    domain=niche,
    question=f"Find product opportunity in {niche}",
    source="reddit+web"
  )
  brain_result = self._send_to_brain(research_req)
  
  # Phase 2: Evaluate
  if brain_result.confidence < 0.7:
    return self._request_more_research(niche)
  
  # Phase 3: Notify human (via Telegram)
  self._send_telegram(f"Brain found opportunity: {brain_result.summary}\nApprove build? /yes /no")
  approval = self._wait_for_approval(timeout=3600)
  if not approval:
    return self._abort("Human did not approve")
  
  # Phase 4: Build
  build_task = BuildTask(
    spec=brain_result.product_brief,
    brief=brain_result.full_findings,
    constraints=self._get_constraints(),
    budget=self._get_build_budget()
  )
  build_result = self._send_to_hands(build_task)
  
  # Phase 5: Report
  self._send_telegram(
    f"Build complete.\nURL: {build_result.url}\nScore: {build_result.score}\nCost: ${build_result.cost}"
  )
  
  return TaskComplete(...)
Task G2: Telegram command handler for pipeline

telegram_bot.py: add /build command

/build <niche>
  → Triggers cortex.pipeline(niche)
  → Shows progress updates as phases complete
  → Asks for approval at architecture gate
  → Final message: live URL
Task G3: Build monitoring in Cortex

agents/cortex.py: monitor_build() method

Runs during Hands execution:
  → Polls PhaseComplete messages
  → Updates Telegram with phase progress
  → Detects if build is stuck (no update in 30min)
  → Can inject Brain context if Hands requests it
  → Can abort if cost ceiling approaching
Full Map
OBJECTIVE A: Fix foundation          → 1-2 days
  Tasks: A1-A5 (stale imports, VPS update)

OBJECTIVE B: Hands as orchestrator   → 3-5 days
  Tasks: B1-B4 (orchestrator.py, phase registry, base class, wiring)

OBJECTIVE C: 7 phase agents          → 1-2 weeks
  Tasks: C1-C8 (one phase at a time, in order)

OBJECTIVE D: MCP integrations        → 3-5 days
  Tasks: D1-D5 (Playwright, Supabase, Vercel, Docker, registry)

OBJECTIVE E: Reddit pipeline         → 3-5 days
  Tasks: E1-E4 (PRAW, analyst, loop integration, dual output)

OBJECTIVE F: Threads API             → 2-3 days
  Tasks: F1-F4 (client, webhooks, outreach agent, DB table)

OBJECTIVE G: Cortex pipeline method  → 3-5 days
  Tasks: G1-G3 (pipeline(), Telegram /build, monitoring)

TOTAL: 3-5 weeks of pure development
       Zero API calls needed
       Zero dollars needed
The Principle For This Phase
Every task here is pure architecture and code. You're building the machine that runs when the budget returns. When it does, you don't run a test — you run Objective 6 for real. One sentence to Cortex, one live URL back.

That's what this phase buys you.


is that all, plus executing those goals to object and tasks

what should I expect it can do now?

give me a sample, its workflow, the output, and the loop

9:27 AM

Evaluated objective completeness and envisioned Cortex's operational capabilities
Evaluated objective completeness and envisioned Cortex's operational capabilities
Is That All?
No. I left out three things that belong in this phase.

Missing Objective H: Growth Capability — Content Agent The Outreach Agent posts. But something needs to write the content that gets people to click once they land. Blog posts, SEO pages, email sequences. All pure code to build, zero API calls to develop the structure.

Missing Objective I: Economics Agent (basic) Right now Cortex has no kill switch. No logic for "this isn't working, stop spending on it." Before real money flows, something needs to watch the numbers and make decisions. Even a simple rules-based version.

Missing Objective J: Domain Goals for all revenue domains onlinejobsph-employers still has no goal. Neither do most domains. Without goals, Question Generator produces generic research. This is a content task, not a code task — but it unblocks everything else.

What To Expect After All Objectives Complete
Here's the exact sample. One concrete niche. Full workflow. Real output. The loop that runs forever.

The Sample
You type in Telegram:

/build freelance invoice tracker
The Workflow
CORTEX receives the command

cortex.pipeline("freelance invoice tracker", "saas")
Logs: JournalEntry — pipeline started
Sends: ResearchRequest to Brain
  domain: "freelance-invoicing"
  question: "Find product opportunity in freelance invoice pain"
  source: "reddit+web"
  depth: "deep"
AGENT BRAIN starts working

reddit_scraper.get_top_posts("freelance", limit=100)
reddit_scraper.search_posts("freelance", "invoice nightmare")
reddit_scraper.search_posts("freelancers", "chasing payments")
reddit_scraper.search_posts("smallbusiness", "invoice software hate")

Finds 47 relevant posts. Sample:
  → "I've been using FreshBooks for 2 years and I STILL 
     can't split one invoice across multiple clients"
  → "Why does every invoice tool make you upgrade for 
     recurring payments? It's 2026"
  → "Sent invoice 3 weeks ago. Client says they never got it.
     No read receipts on any of these tools"

reddit_analyst extracts pain points:
  → Pain 1: No invoice split/partial payment (23 mentions)
  → Pain 2: Recurring payments locked behind paywall (31 mentions)
  → Pain 3: No delivery confirmation / read receipts (18 mentions)
  → Pain 4: Too complex for freelancers who just need simple (41 mentions)

Scores opportunities:
  Pain 4 wins: highest frequency, clear willingness to pay,
  direct competitor weakness (FreshBooks/Wave are over-engineered)

Synthesizer produces simultaneously:

product_brief.md:
  User: freelancer billing 1-10 clients
  Core pain: every tool is built for accountants not freelancers
  Core feature: send invoice in under 60 seconds, know when it's opened
  Stack: Next.js + Supabase + Stripe + Resend (email)
  MVP scope: create invoice, send via email, track open/paid status
  Success: user can go from zero to sent invoice in under 2 minutes

marketing_brief.md:
  Headline: "Send an invoice in 60 seconds. Know when they open it."
  User language: "chasing payments", "they say they never got it",
                 "too complicated", "just need something simple"
  Channels: r/freelance (31k active), r/digitalnomad, Threads
  Competitor weakness: FreshBooks/Wave too complex, Wave has ads
  Angle: radically simple, with one killer feature (read receipts)

Brain → Cortex: ResearchComplete
  confidence: 0.84
  summary: "Freelance invoicing pain is real and specific.
            Opportunity: radically simple tool with delivery confirmation.
            41 mentions of complexity frustration in top 100 posts."
CORTEX evaluates

Confidence 0.84 → above 0.7 threshold → proceed

Sends Telegram to you:
  "🧠 Brain found opportunity in freelance invoicing.
   
   Pain: Freelancers need something radically simpler.
   Killer feature: know when client opens your invoice.
   Competitor gap: FreshBooks too complex, Wave has ads.
   Confidence: 84%
   
   Top Reddit signal:
   'Why does every invoice tool make you upgrade for
   recurring payments? It's 2026' — 847 upvotes
   
   Approve build? /yes /no"
You reply: /yes

Cortex creates BuildTask:
  spec: product_brief.md contents
  brief: full Brain research
  budget: $3.50 (half daily budget reserved for this)
  constraints: Next.js + Supabase + Vercel + Stripe
  
Sends to Agent Hands orchestrator
Telegram: "🏗️ Build started. I'll update you as each phase completes."
AGENT HANDS — Phase 0: Context Intake

Reads product_brief.md
Reads design_system.md from Identity Layer
Extracts:
  → Core user: solo freelancer, not accountant
  → MVP features (not more):
      1. Create invoice (client name, items, amount)
      2. Send via email (Resend API)
      3. Track status (draft / sent / opened / paid)
      4. Read receipt (Supabase edge function on email open)
  → Success criteria:
      □ User creates account in <60 seconds
      □ User creates and sends invoice in <2 minutes  
      □ Status updates in real-time when client opens
      □ Stripe payment link in invoice email
      □ Build passes: npm run build clean
      □ Visual score: ≥ 8/10

Writes: workspace/PRD.md
Telegram: "📋 Phase 0 complete: PRD written. 4 MVP features scoped."
AGENT HANDS — Phase 1: Architecture

Writes ARCHITECTURE.md:

FILE STRUCTURE:
  app/
    (auth)/login/page.tsx
    (auth)/signup/page.tsx
    dashboard/page.tsx
    invoices/new/page.tsx
    invoices/[id]/page.tsx
    api/invoices/route.ts
    api/invoices/[id]/route.ts
    api/invoices/[id]/send/route.ts
    api/webhooks/email-open/route.ts
    api/webhooks/stripe/route.ts

SUPABASE SCHEMA:
  users (id, email, name, stripe_customer_id)
  invoices (id, user_id, client_name, client_email,
            items jsonb, total, status, sent_at,
            opened_at, paid_at, stripe_payment_id)

API CONTRACT:
  POST /api/invoices → create invoice → {id, status: "draft"}
  GET  /api/invoices → list invoices → [{id, client, total, status}]
  POST /api/invoices/[id]/send → send email → {status: "sent"}
  POST /api/webhooks/email-open → update opened_at
  POST /api/webhooks/stripe → update paid_at

ENV VARS NEEDED:
  NEXT_PUBLIC_SUPABASE_URL
  NEXT_PUBLIC_SUPABASE_ANON_KEY
  SUPABASE_SERVICE_ROLE_KEY
  RESEND_API_KEY
  STRIPE_SECRET_KEY
  STRIPE_WEBHOOK_SECRET

Telegram: "📐 Phase 1 complete: Blueprint ready.
           Review ARCHITECTURE.md and approve: /approve /revise"
You review. Reply: /approve

AGENT HANDS — Phase 2: Workspace Setup

Terminal tool:
  npx create-next-app@latest invoicer --typescript 
       --tailwind --app --no-src-dir
  cd invoicer
  npx shadcn@latest init
  npm install framer-motion @supabase/supabase-js 
              resend stripe @stripe/stripe-js
  git init && git add . && git commit -m "scaffold"

Supabase MCP:
  create_project("invoicer")
  run_migration(schema_sql)
  get_project_url() → stores in .env.local
  get_anon_key() → stores in .env.local

Terminal: npm run dev → PORT 3001
Browser tool: screenshot(localhost:3001)
  → Sees: Next.js default page, confirms running

Telegram: "⚙️ Phase 2 complete: Scaffold running on dev server.
           Supabase project created. Dependencies installed."
AGENT HANDS — Phase 3: Backend

Code tool writes API routes one by one.
After each route, HTTP tool tests it:

  Write: app/api/invoices/route.ts (POST)
  Test:  POST localhost:3001/api/invoices
         body: {client_name: "Test Co", items: [...], total: 500}
         expects: {id: "uuid", status: "draft"}
         → PASS ✓

  Write: app/api/invoices/route.ts (GET)  
  Test:  GET localhost:3001/api/invoices
         → PASS ✓

  Write: app/api/invoices/[id]/send/route.ts
  Test:  POST with invoice id
         → Resend sends email to test address
         → Supabase status updates to "sent"
         → PASS ✓

  Write: app/api/webhooks/email-open/route.ts
  Test:  POST with invoice id
         → opened_at timestamp set
         → PASS ✓

All 5 routes pass. Auth flow verified.
Supabase RLS policies active.

Telegram: "🔧 Phase 3 complete: All 5 API routes passing.
           Auth working. RLS policies active."
AGENT HANDS — Phase 4: Frontend

Injects: identity/design_system.md (420 lines)
Injects: API contract from ARCHITECTURE.md
Injects: user language from marketing_brief.md

Builds components in order:

  1. Layout shell (header, nav)
     → Screenshot → Visual score: 7.2
     → Fix: nav too cramped, padding increase
     → Screenshot → Visual score: 8.4 ✓

  2. Auth pages (/login, /signup)
     → Screenshot → Visual score: 8.1 ✓

  3. Dashboard (/dashboard)
     Shows: invoice list, total outstanding, quick stats
     → Screenshot → Visual score: 6.8
     → Fix: empty state not designed, numbers not prominent
     → Screenshot → Visual score: 8.6 ✓

  4. New invoice form (/invoices/new)
     Line items, client email, send button
     → Screenshot → Visual score: 7.5
     → Fix: line item UX cluttered
     → Screenshot → Visual score: 8.3 ✓

  5. Invoice detail (/invoices/[id])
     Status timeline: Draft → Sent → Opened → Paid
     → Screenshot → Visual score: 9.1 ✓

All components visual score ≥ 8. 
Framer Motion: page transitions, status updates animate.

Telegram: "🎨 Phase 4 complete: Frontend built.
           Visual scores: 8.4, 8.1, 8.6, 8.3, 9.1
           Average: 8.5/10"
AGENT HANDS — Phase 5: Integration Test

Playwright runs full user journey:

  navigate(localhost:3001/signup)
  fill("#email", "test@example.com")
  fill("#password", "TestPass123!")
  click("#signup-btn")
  wait_for(".dashboard")                    ✓ redirected

  click("#new-invoice-btn")
  fill("#client-name", "Acme Corp")
  fill("#client-email", "client@acme.com")
  fill("#item-description", "Website design")
  fill("#item-amount", "1500")
  click("#add-item-btn")
  click("#send-invoice-btn")
  wait_for(".status-sent")                  ✓ status updated
  
  HTTP: GET /api/invoices
  → finds invoice with status "sent"        ✓ persisted

  HTTP: POST /api/webhooks/email-open {id}
  → wait_for(".status-opened")              ✓ real-time update

  click("#logout-btn")
  navigate(localhost:3001/login)
  fill credentials → click login
  wait_for(".dashboard")                    ✓ session restored

Terminal: npm run build
  → Compiled successfully                   ✓ no errors
  → No TypeScript errors                    ✓
  → No missing env vars                     ✓

All 8 test steps: PASS

Telegram: "✅ Phase 5 complete: All integration tests pass.
           Build compiles clean. Ready to deploy."
AGENT HANDS — Phase 6: Deploy

Git tool:
  add . && commit -m "feat: invoicer MVP complete"
  push origin main

Vercel MCP:
  deploy(project_dir="invoicer", 
         env_vars={SUPABASE_URL, SUPABASE_ANON_KEY, 
                   RESEND_API_KEY, STRIPE_SECRET_KEY...})
  → deployment_id: "dpl_abc123"
  → wait for completion

get_deployment_url("dpl_abc123")
  → https://invoicer-abc123.vercel.app

Browser tool:
  screenshot("https://invoicer-abc123.vercel.app")
  → sees: production login page, looks identical to dev

HTTP tool:
  POST /api/invoices on production URL
  → PASS ✓ works in production

Telegram: "🚀 Phase 6 complete: Live on Vercel.
           URL: https://invoicer-abc123.vercel.app"
AGENT HANDS — Phase 7: Critic

Evaluates against PRD success criteria:
  □ User creates account in <60 seconds      ✓ (Playwright: 23s)
  □ Invoice created and sent in <2 minutes   ✓ (Playwright: 47s)
  □ Status updates when client opens         ✓ (webhook working)
  □ Stripe payment link in email             ✓ (confirmed in send route)
  □ Build passes clean                       ✓
  □ Visual score ≥ 8                         ✓ (avg 8.5)

Build score: 9.1/10

Lessons extracted to exec_memory:
  → "Resend webhook needs 5s delay before status check"
  → "Supabase RLS must be set BEFORE testing auth routes"
  → "Empty state must be designed before visual gate or score tanks"
  → "Status timeline component reusable for any workflow app"

Sends BuildComplete to Cortex:
  url: "https://invoicer-abc123.vercel.app"
  score: 9.1
  cost: $2.84
  time: 2h 23min
  tests_passed: 8/8
  visual_avg: 8.5
CORTEX receives BuildComplete

Compares against goal: ✓ production-ready, ✓ beautiful, ✓ working

Triggers Outreach Agent:
  Finds top 3 Reddit threads where invoice pain was expressed
  Drafts replies:
    "Freelancer here — I had the exact same problem with
     [specific pain they mentioned]. Built something to solve it,
     would love your feedback: [URL]"
  Schedules: post 1 now, post 2 in 3 hours, post 3 tomorrow

Triggers Threads post:
  "Spent too long chasing invoice payments with no idea 
   if clients even opened them. Built a fix: 
   send an invoice in 60 seconds, know the second they open it.
   [URL] — free while in beta"

Stores marketing_brief.md for future content use

Sends final Telegram to you:
The Final Output You Receive
🎉 BUILD COMPLETE

Product:  Invoicer — Simple invoicing for freelancers
URL:      https://invoicer-abc123.vercel.app
Score:    9.1/10
Cost:     $2.84
Time:     2h 23min

What was built:
  ✓ Auth (signup, login, session, logout)
  ✓ Create + send invoices via email
  ✓ Real-time open tracking (read receipts)
  ✓ Stripe payment links
  ✓ Status timeline (Draft → Sent → Opened → Paid)
  ✓ Mobile responsive
  ✓ Deployed on Vercel + Supabase

Test results:
  ✓ 8/8 integration tests passed
  ✓ Build compiles clean
  ✓ Works in production

Visual quality:
  Dashboard:     8.6/10
  Invoice form:  8.3/10
  Status view:   9.1/10
  Average:       8.5/10

Marketing launched:
  ✓ 3 Reddit replies scheduled (r/freelance, r/digitalnomad)
  ✓ Threads post published
  ✓ Marketing brief stored for content expansion

Brain learned:
  47 pain points indexed
  4 execution lessons stored
  Principles transferred to cross-domain store

Next: Monitor signups via /metrics
      First user in 24-48 hours expected

You wrote: 0 lines of code.
The Loop That Runs Forever
Day 1:
  /build freelance invoice tracker
  → 2h 23min later: live URL in Telegram
  → Reddit outreach posted
  → Threads post live

Day 2:
  Analytics Agent reports:
  "3 Reddit replies posted. 47 clicks to URL.
   12 signups. 2 users created real invoices."
  
  Brain analyzes signups:
  "Users drop off at line item entry. Too many fields."
  
  Cortex decides: iterate
  Hands fixes: simplifies line item UX
  Redeploy: 23 minutes
  Telegram: "UX fix deployed. Watching for drop-off improvement."

Day 5:
  Brain reads Threads replies:
  "5 people asked about recurring invoices"
  Cortex: add recurring to backlog
  
Day 7:
  First paid user. $9/month.
  Economics Agent: "Revenue signal confirmed. Scale."
  Brain: researches growth channels for this audience
  Hands: builds blog post targeting "invoice software for freelancers"
  SEO Agent: technical setup, sitemap, meta tags

Month 2:
  Cortex has learned:
  → What features convert free to paid
  → What copy drives signups
  → What channels work for this audience
  → What took longest to build and why
  
  /build expense tracker for freelancers
  → Same audience. Brain already knows them deeply.
  → Build is faster because lessons are loaded.
  → Marketing is better because you know what works.
  → Cost is lower because local judge handles more scoring.
  
  This is the compound effect starting.

Month 6:
  5 products. Different niches, same quality.
  Each one informed by everything that came before.
  Each one cheaper and faster to build than the last.
  
  You: point direction.
  Cortex: does everything else.
That's what these objectives build toward. Not a demo. A machine that produces real products, gets them in front of real users, and gets smarter each time it does.
