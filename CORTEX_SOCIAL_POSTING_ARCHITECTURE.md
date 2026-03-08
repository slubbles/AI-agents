# Cortex Social Posting Architecture

Generated: March 8, 2026

## Purpose

This document maps a clean social-posting architecture for Cortex with two paths:

1. Direct Threads publishing now
2. Buffer publishing later, behind the same adapter boundary

The goal is to avoid rebuilding the content pipeline twice.

## Design Goal

Cortex should have one social pipeline for:

1. Deciding what to post
2. Preparing text and media
3. Publishing to a destination
4. Reading back engagement
5. Feeding results into learning

The destination should be swappable.

That means Threads should be one adapter, not the whole system.

## Current State

The repo already has real Threads pieces:

1. `agent-brain/tools/threads_client.py`
   Direct Threads API read/write client
2. `agent-brain/tools/image_publisher.py`
   Screenshot/chart to public URL to Threads flow
3. `agent-brain/agents/threads_analyst.py`
   Content analysis, draft generation, build screenshot posting, score chart posting
4. `agent-brain/telegram_bot.py`
   Manual Threads commands for search, post, insights, analytics, and single-post stats

That means Cortex already has a working direct path for Threads.

What it does not have yet is a clean platform boundary.

Right now, content generation, media preparation, publishing, and analytics are still mostly Threads-shaped.

## Core Rule

Separate these four concerns:

1. Content planning
2. Media preparation
3. Publishing adapter
4. Outcome collection

If these stay separate, Buffer can be added later without touching the planning side.

## Recommended Architecture

```text
Signal / Research / Build Events
            |
            v
   Social Intent Generator
            |
            v
     Post Composition Layer
   text + links + media intent
            |
            v
      Media Preparation Layer
 screenshot | chart | public asset URL
            |
            v
       Publisher Router
    /                      \
   v                        v
Direct Threads Adapter   Buffer Adapter
   |                        |
   v                        v
Threads API            Buffer API
   |                        |
   +-----------+------------+
               |
               v
      Engagement / Outcome Layer
               |
               v
        Brain memory and learning
```

## Recommended Module Split

This is the clean target shape.

### 1. Social Intent Layer

Purpose:

Turn system events into a posting decision.

Examples:

1. Build finished and passed validation
2. Research quality improved enough to show publicly
3. New market insight is strong enough to share
4. Weekly recap is due

Recommended ownership:

1. `threads_analyst.py` can keep content strategy logic
2. A future `social_intents.py` should decide whether a post should happen at all

Output shape:

```python
{
    "intent_type": "build_screenshot",
    "domain": "productized-services",
    "goal": "show progress publicly",
    "audience": "founders",
    "priority": "high",
    "source_event": "hands_build_complete",
}
```

### 2. Composition Layer

Purpose:

Turn an intent into a platform-neutral post request.

This layer should decide:

1. Final text
2. Link attachment
3. Media type needed
4. Tags or metadata
5. Whether the post should go out now or be scheduled

Recommended shared contract:

```python
from dataclasses import dataclass, field

@dataclass
class PostRequest:
    channel: str
    text: str
    media_kind: str | None = None
    media_source: str | None = None
    media_url: str | None = None
    link_url: str | None = None
    publish_mode: str = "now"
    scheduled_at: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

Important:

The rest of the system should publish a `PostRequest`, not call Threads directly.

### 3. Media Preparation Layer

Purpose:

Produce a public URL for any image asset.

This is the reusable middle layer that both Threads and Buffer need.

Current pieces already exist:

1. Screenshot capture via Playwright or browser fallback
2. Chart generation via matplotlib
3. Upload to Vercel Blob

This layer should own:

1. `screenshot -> public_url`
2. `chart -> public_url`
3. later: `generated image -> public_url`

That means `image_publisher.py` should remain platform-neutral.

It should not think in terms of Threads.

Its job is only:

1. make asset
2. upload asset
3. return public URL

Recommended result shape:

```python
{
    "ok": True,
    "media_kind": "image",
    "public_url": "https://...",
    "source": "playwright_screenshot",
    "width": 2800,
    "height": 1800,
}
```

### 4. Publisher Adapter Layer

Purpose:

Take a platform-neutral `PostRequest` and send it through one platform.

Recommended interface:

```python
class SocialPublisher:
    def is_configured(self) -> bool: ...
    def publish(self, request: PostRequest) -> dict: ...
    def get_recent_engagement(self, limit: int = 10) -> dict: ...
    def get_post_insights(self, post_id: str) -> dict: ...
```

#### Direct Threads Adapter

Purpose:

Use the Meta Threads API directly.

Backed by current code:

1. `publish_post()`
2. `get_recent_engagement()`
3. `get_thread_insights()`
4. `search_threads()`

Responsibilities:

1. Publish immediately
2. Read engagement directly from Threads
3. Support replies later if needed

Strengths:

1. No middleman
2. Best fit for current repo state
3. Direct analytics loop

Limits:

1. Single-channel shape
2. Scheduling is limited compared with a social scheduler

#### Buffer Adapter

Purpose:

Send the same `PostRequest` through Buffer if access is available.

Responsibilities:

1. Map `PostRequest` to Buffer payload
2. Route by connected profile IDs
3. Support queue, now, top, or scheduled publishing
4. Read back status if the API provides it

Important constraint:

Buffer should be treated as optional and not required for the first working loop.

If Buffer access is missing, the router should fall back to Direct Threads.

### 5. Router Layer

Purpose:

Choose which adapter to use.

Recommended rules:

1. If `publish_mode == "direct_threads"`, use Threads adapter
2. If `publish_mode == "buffer"` and Buffer is configured, use Buffer adapter
3. If `publish_mode == "buffer"` and Buffer is not configured, fail cleanly or fall back depending on policy
4. Default to Direct Threads until Buffer is proven stable

Suggested policy:

```python
PUBLISHER_PRIORITY = ["threads_direct", "buffer"]
```

But for the current phase, the real operating default should be:

```python
PUBLISHER_PRIORITY = ["threads_direct"]
```

Buffer should be opt-in, not default.

### 6. Engagement and Learning Layer

Purpose:

Feed social results back into Cortex.

Metrics to capture:

1. impressions or views
2. likes
3. replies
4. reposts
5. quotes
6. engagement rate
7. post type
8. domain
9. trigger source
10. whether media was attached

This should answer questions like:

1. Do build screenshots beat text-only posts?
2. Do score charts actually help credibility?
3. Which domains produce stronger engagement?
4. Which hook styles work best?

Recommended storage:

1. One log file or table for published posts
2. One log file or table for engagement snapshots over time

Recommended record shape:

```python
{
    "post_id": "...",
    "publisher": "threads_direct",
    "channel": "threads",
    "domain": "productized-services",
    "intent_type": "build_screenshot",
    "text": "...",
    "media_kind": "image",
    "published_at": "2026-03-08T12:00:00Z",
    "source_event": "hands_build_complete",
}
```

Later snapshot:

```python
{
    "post_id": "...",
    "captured_at": "2026-03-08T18:00:00Z",
    "views": 2100,
    "likes": 74,
    "replies": 11,
    "reposts": 6,
    "quotes": 2,
    "engagement_rate": 4.43,
}
```

## Current Direct Threads Flow

The clean version of the current live path should be thought of like this:

```text
build/research event
    -> threads_analyst decides post type
    -> compose PostRequest
    -> image_publisher prepares public image URL if needed
    -> threads_direct adapter publishes
    -> telemetry stored
    -> later engagement pulled back in
```

This means the current code is already useful.

It just needs a cleaner boundary so Buffer can slot in later.

## Future Buffer Flow

The Buffer version should look almost the same:

```text
build/research event
    -> threads_analyst or future social planner decides post type
    -> compose PostRequest
    -> image_publisher prepares public image URL if needed
    -> buffer adapter publishes or schedules
    -> publish receipt stored
    -> status and engagement synced back if available
```

The key point is this:

The media pipeline should be shared.

Only the last publishing step should change.

## Recommended File Layout

This is the clean layout to grow toward.

```text
agent-brain/
  social/
    contracts.py
    router.py
    telemetry.py
    intents.py
    providers/
      threads_direct.py
      buffer.py
```

What stays where:

1. `tools/image_publisher.py` stays as the shared media utility
2. `agents/threads_analyst.py` can stay as the content strategy and draft generator for now
3. `tools/threads_client.py` becomes the low-level Threads transport used by `social/providers/threads_direct.py`

## Command Surface

The architecture should support two kinds of use.

### 1. Manual control

Used from Telegram or CLI.

Examples:

1. draft a post
2. publish now
3. publish screenshot post from a URL
4. publish score chart for a domain
5. inspect recent engagement
6. inspect one post's stats

### 2. Automatic control

Used by scheduler or future growth loops.

Examples:

1. after a successful deploy, queue a build screenshot post
2. once a week, publish a score trend chart
3. when a domain crosses a proof threshold, publish an insight thread

Manual and automatic paths should both call the same `PostRequest -> router -> adapter` flow.

## Safety Rules

Publishing should have gates.

Recommended minimum rules:

1. no auto-post unless a feature flag is on
2. no post if text is over the platform limit
3. no post if media upload failed and the request requires media
4. no Buffer publish if no confirmed Buffer access
5. rate-limit autoposting so Cortex does not spam
6. store every publish attempt and result

Suggested flags:

```python
SOCIAL_POSTING_ENABLED = False
SOCIAL_AUTOPUBLISH_ENABLED = False
SOCIAL_DEFAULT_PUBLISHER = "threads_direct"
```

## Best First Implementation Order

Do this in order.

### Phase 1

Clean up the existing Threads path without changing behavior.

1. Introduce `PostRequest`
2. Wrap current direct Threads calls behind a Threads adapter
3. Make `image_publisher.py` fully platform-neutral
4. Add publish telemetry storage

### Phase 2

Route all manual Threads commands through the adapter.

1. Telegram `/threads post`
2. screenshot posting helpers
3. chart posting helpers

### Phase 3

Add router support.

1. choose adapter by config
2. keep Threads direct as default
3. add explicit fallback policy

### Phase 4

Add Buffer only if access is real and stable.

1. create Buffer adapter
2. map `PostRequest` fields to Buffer payload
3. test one real profile first
4. only then expose it to scheduler automation

## Recommendation

For Cortex right now:

1. Keep Direct Threads as the main path
2. Treat Buffer as a future adapter, not a replacement
3. Invest in the shared media and telemetry layers first
4. Make all post generation produce one platform-neutral request shape

That gives Cortex one social system instead of one Threads system now and a second Buffer system later.

## Short Version

The right architecture is:

1. one content planner
2. one media pipeline
3. one router
4. many publishing adapters
5. one feedback loop

Threads is adapter one.

Buffer is adapter two, later.