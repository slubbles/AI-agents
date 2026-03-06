"""
Signal Collector — Reddit RSS/Atom feed scraper for pain point discovery.

Fetches posts from target subreddits using Reddit's public RSS feeds.
No authentication needed. No PRAW dependency. Pure urllib + xml.etree.

Reddit's JSON API blocks datacenter IPs (403). RSS feeds via old.reddit.com
work reliably from any environment.

Pipeline:
    1. For each subreddit, search RSS with pain-point keywords
    2. Filter by keyword match in title/body
    3. Store in SQLite (deduped by reddit_id)
    4. Zero LLM cost — pure HTTP + regex

Modeled after: github.com/lefttree/reddit-pain-points

Rate limits: ~10 req/min unauthenticated, 3.5s delay enforced.
"""

import html as html_mod
import json
import logging
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

SIGNALS_DB_PATH = os.path.join(os.path.dirname(__file__), "logs", "signals.db")

# Reddit rate limit: ~10 req/min for unauthenticated
# Datacenter IPs need longer delays to avoid 403s
REQUEST_DELAY = 3.5  # seconds between requests (datacenter-safe)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Atom XML namespace
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

DEFAULT_SUBREDDITS = [
    "SaaS", "startups", "Entrepreneur", "smallbusiness",
    "sideproject", "indiehackers", "microsaas", "webdev",
    "EntrepreneurRideAlong", "sweatystartup", "marketing", "nocode",
]

# Pain-point search terms — used as Reddit search queries
SEARCH_TERMS = [
    "frustrated", "i wish", "need a tool", "looking for",
    "alternative to", "why isn't there", "would pay for", "tired of",
    "can't find", "doesn't exist", "pain point", "hate when",
    "struggle with", "wish there was", "anyone know of",
    "is there a", "help me find", "what do you use for",
    "waste of time", "drives me crazy", "broken",
]

# Keywords that must appear in post text to pass filter
PAIN_KEYWORDS = [
    "i wish", "frustrated", "annoying", "why isn't there",
    "looking for", "need a tool", "hate when", "pain point",
    "struggle with", "wish there was", "anyone know of",
    "alternative to", "tired of", "can't find", "doesn't exist",
    "would pay for", "shut up and take my money", "feature request",
    "deal breaker", "broken", "sucks", "terrible", "worst part",
    "is there a", "recommend a", "help me find", "what do you use for",
    "so annoying", "drives me crazy", "waste of time",
    "looking for something", "need help with", "how do you handle",
]

CATEGORIES = [
    "Productivity", "Developer Tools", "Business", "Communication",
    "Finance", "Health", "Education", "Marketing", "Design",
    "Data & Analytics", "Automation", "Other",
]


# ── Database ────────────────────────────────────────────────────────────

_db_initialized = False


@contextmanager
def get_db():
    """Thread-safe database connection."""
    conn = sqlite3.connect(SIGNALS_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_signals_db():
    """Initialize the signals database schema."""
    global _db_initialized
    if _db_initialized:
        return

    os.makedirs(os.path.dirname(SIGNALS_DB_PATH), exist_ok=True)

    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reddit_id TEXT UNIQUE,
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                author TEXT,
                url TEXT,
                score INTEGER DEFAULT 0,
                num_comments INTEGER DEFAULT 0,
                created_utc REAL,
                scraped_at TEXT NOT NULL,
                is_analyzed INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER REFERENCES posts(id),
                pain_point_summary TEXT,
                category TEXT,
                severity INTEGER,
                affected_audience TEXT,
                potential_solutions TEXT,
                market_size_estimate TEXT,
                existing_solutions TEXT,
                opportunity_score INTEGER,
                analyzed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                subreddits TEXT,
                posts_found INTEGER DEFAULT 0,
                posts_matched INTEGER DEFAULT 0,
                posts_new INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running'
            );

            CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
            CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score DESC);
            CREATE INDEX IF NOT EXISTS idx_posts_analyzed ON posts(is_analyzed);
            CREATE INDEX IF NOT EXISTS idx_analyses_score ON analyses(opportunity_score DESC);
        """)
    _db_initialized = True


def insert_post(post_data: dict) -> bool:
    """Insert a post, returning True if it was new (not duplicate)."""
    init_signals_db()
    with get_db() as conn:
        try:
            conn.execute("""
                INSERT INTO posts (reddit_id, subreddit, title, body, author, url,
                                   score, num_comments, created_utc, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_data["reddit_id"],
                post_data["subreddit"],
                post_data["title"],
                post_data.get("body", "")[:5000],
                post_data.get("author", "[deleted]"),
                post_data.get("url", ""),
                post_data.get("score", 0),
                post_data.get("num_comments", 0),
                post_data.get("created_utc", 0),
                datetime.now(timezone.utc).isoformat(),
            ))
            return True
        except sqlite3.IntegrityError:
            return False  # Duplicate reddit_id


def get_unanalyzed_posts(limit: int = 50) -> list[dict]:
    """Get posts that haven't been analyzed yet, ordered by engagement."""
    init_signals_db()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, reddit_id, subreddit, title, body, author, url,
                   score, num_comments, created_utc
            FROM posts
            WHERE is_analyzed = 0
            ORDER BY (score + num_comments * 2) DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def mark_analyzed(post_id: int):
    """Mark a post as analyzed."""
    with get_db() as conn:
        conn.execute("UPDATE posts SET is_analyzed = 1 WHERE id = ?", (post_id,))


def insert_analysis(post_id: int, analysis: dict):
    """Store analysis results for a post and mark it as analyzed."""
    init_signals_db()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO analyses (post_id, pain_point_summary, category, severity,
                                  affected_audience, potential_solutions,
                                  market_size_estimate, existing_solutions,
                                  opportunity_score, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post_id,
            analysis.get("pain_point_summary", ""),
            analysis.get("category", "Other"),
            analysis.get("severity", 1),
            analysis.get("affected_audience", ""),
            json.dumps(analysis.get("potential_solutions", [])),
            analysis.get("market_size_estimate", "Unknown"),
            json.dumps(analysis.get("existing_solutions", [])),
            analysis.get("opportunity_score", 0),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.execute("UPDATE posts SET is_analyzed = 1 WHERE id = ?", (post_id,))


def get_top_opportunities(limit: int = 20) -> list[dict]:
    """Get top-scored opportunities with post context."""
    init_signals_db()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT a.*, p.subreddit, p.title, p.url, p.score as post_score,
                   p.num_comments, p.body
            FROM analyses a
            JOIN posts p ON a.post_id = p.id
            ORDER BY a.opportunity_score DESC
            LIMIT ?
        """, (limit,)).fetchall()
        results = []
        for r in dict(r) if False else []:
            pass
        for r in rows:
            d = dict(r)
            # Parse JSON fields
            for field in ("potential_solutions", "existing_solutions"):
                if isinstance(d.get(field), str):
                    try:
                        d[field] = json.loads(d[field])
                    except (json.JSONDecodeError, TypeError):
                        d[field] = []
            results.append(d)
        return results


def get_collection_stats() -> dict:
    """Get overall collection statistics."""
    init_signals_db()
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        analyzed = conn.execute("SELECT COUNT(*) FROM posts WHERE is_analyzed = 1").fetchone()[0]
        unanalyzed = total - analyzed
        subs = conn.execute("SELECT DISTINCT subreddit FROM posts").fetchall()
        top_subs = conn.execute("""
            SELECT subreddit, COUNT(*) as cnt
            FROM posts GROUP BY subreddit ORDER BY cnt DESC LIMIT 5
        """).fetchall()
        runs = conn.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0]
        return {
            "total_posts": total,
            "analyzed": analyzed,
            "unanalyzed": unanalyzed,
            "subreddits": [r[0] for r in subs],
            "top_subreddits": {r[0]: r[1] for r in top_subs},
            "collection_runs": runs,
        }


# ── Reddit Fetcher ──────────────────────────────────────────────────────

def _matches_pain_keywords(text: str) -> bool:
    """Check if text contains any pain-point keywords."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in PAIN_KEYWORDS)


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities from RSS content."""
    text = html_mod.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _reddit_rss_request(url: str, params: dict = None, timeout: int = 30) -> Optional[list[dict]]:
    """Fetch Reddit RSS/Atom feed and parse entries into dicts.

    Returns list of post dicts or None on failure.
    """
    if params:
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
    else:
        full_url = url

    req = urllib.request.Request(full_url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "text/xml,application/xml,application/atom+xml")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.warning("[SIGNALS] Reddit rate limit hit, backing off 15s")
            time.sleep(15)
        else:
            logger.warning(f"[SIGNALS] HTTP {e.code} for {full_url}")
        return None
    except (urllib.error.URLError, Exception) as e:
        logger.warning(f"[SIGNALS] Request failed: {e}")
        return None

    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        logger.warning(f"[SIGNALS] XML parse error: {e}")
        return None

    entries = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        eid = entry.find("atom:id", _ATOM_NS)
        title = entry.find("atom:title", _ATOM_NS)
        link = entry.find("atom:link", _ATOM_NS)
        updated = entry.find("atom:updated", _ATOM_NS)
        published = entry.find("atom:published", _ATOM_NS)
        author_el = entry.find("atom:author", _ATOM_NS)
        content = entry.find("atom:content", _ATOM_NS)
        category = entry.find("atom:category", _ATOM_NS)

        # Extract author name (format: "/u/username")
        author = "[deleted]"
        if author_el is not None:
            name_el = author_el.find("atom:name", _ATOM_NS)
            if name_el is not None and name_el.text:
                author = name_el.text.replace("/u/", "")

        # Extract body text from HTML content
        body = ""
        if content is not None and content.text:
            body = _strip_html(content.text)

        # Parse timestamp
        ts_text = (published.text if published is not None else
                   updated.text if updated is not None else None)
        created_utc = 0.0
        if ts_text:
            try:
                dt = datetime.fromisoformat(ts_text.replace("Z", "+00:00"))
                created_utc = dt.timestamp()
            except (ValueError, OSError):
                pass

        entries.append({
            "reddit_id": eid.text if eid is not None else "",
            "title": title.text if title is not None else "",
            "body": body[:5000],
            "author": author,
            "url": link.get("href", "") if link is not None else "",
            "subreddit": category.get("term", "") if category is not None else "",
            "created_utc": created_utc,
            # RSS doesn't provide score/comments — set to 0
            "score": 0,
            "num_comments": 0,
        })

    return entries


def scrape_subreddit(
    subreddit: str,
    search_terms: list[str] = None,
    limit_per_term: int = 25,
    time_filter: str = "month",
) -> dict:
    """
    Scrape a subreddit using Reddit's public RSS/Atom search feed.

    Uses old.reddit.com search RSS — works from datacenter IPs where
    the JSON API returns 403.

    Args:
        subreddit: Subreddit name (without r/)
        search_terms: Pain-point search queries (default: SEARCH_TERMS)
        limit_per_term: Max results per search term
        time_filter: Time range — hour, day, week, month, year, all

    Returns:
        {"found": int, "matched": int, "new": int, "errors": int}
    """
    init_signals_db()

    if search_terms is None:
        search_terms = SEARCH_TERMS

    stats = {"found": 0, "matched": 0, "new": 0, "errors": 0}
    seen_ids = set()

    for term in search_terms:
        entries = _reddit_rss_request(
            f"https://old.reddit.com/r/{subreddit}/search.rss",
            {
                "q": term,
                "restrict_sr": "on",
                "sort": "relevance",
                "t": time_filter,
                "limit": str(min(limit_per_term, 25)),
            },
        )

        if entries is None:
            stats["errors"] += 1
            time.sleep(REQUEST_DELAY)
            continue

        for post_data in entries:
            post_id = post_data["reddit_id"]

            if post_id in seen_ids or not post_id:
                continue
            seen_ids.add(post_id)
            stats["found"] += 1

            full_text = f"{post_data['title']} {post_data['body']}"

            if not _matches_pain_keywords(full_text):
                continue

            stats["matched"] += 1

            # Override subreddit with our target (RSS may differ in casing)
            post_data["subreddit"] = subreddit

            is_new = insert_post(post_data)
            if is_new:
                stats["new"] += 1

        time.sleep(REQUEST_DELAY)

    return stats


def collect_signals(
    subreddits: list[str] = None,
    search_terms: list[str] = None,
    time_filter: str = "month",
) -> dict:
    """
    Run a full collection cycle across all target subreddits.

    Args:
        subreddits: List of subreddit names (default: DEFAULT_SUBREDDITS)
        search_terms: Pain-point search queries (default: SEARCH_TERMS)
        time_filter: Time range for Reddit search

    Returns:
        {"total_found": int, "total_matched": int, "total_new": int,
         "per_subreddit": {sub: stats}, "duration_seconds": float}
    """
    init_signals_db()

    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS

    start_time = time.time()

    # Log collection run
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO collection_runs (started_at, subreddits, status)
            VALUES (?, ?, 'running')
        """, (datetime.now(timezone.utc).isoformat(), ",".join(subreddits)))
        run_id = cur.lastrowid

    total = {"found": 0, "matched": 0, "new": 0}
    per_sub = {}

    for sub in subreddits:
        logger.info(f"[SIGNALS] Collecting r/{sub}...")
        print(f"  Collecting r/{sub}...", end=" ", flush=True)

        stats = scrape_subreddit(sub, search_terms, time_filter=time_filter)
        per_sub[sub] = stats

        total["found"] += stats["found"]
        total["matched"] += stats["matched"]
        total["new"] += stats["new"]

        print(f"found={stats['found']} matched={stats['matched']} new={stats['new']}")

    duration = time.time() - start_time

    # Update collection run
    with get_db() as conn:
        conn.execute("""
            UPDATE collection_runs
            SET finished_at = ?, posts_found = ?, posts_matched = ?,
                posts_new = ?, status = 'completed'
            WHERE id = ?
        """, (
            datetime.now(timezone.utc).isoformat(),
            total["found"], total["matched"], total["new"], run_id,
        ))

    return {
        "total_found": total["found"],
        "total_matched": total["matched"],
        "total_new": total["new"],
        "per_subreddit": per_sub,
        "duration_seconds": round(duration, 1),
    }


# ── Reddit Engagement Enrichment ───────────────────────────────────────

def _get_scrapling_fetcher():
    """Lazy-load Scrapling Fetcher for Reddit page enrichment."""
    try:
        from scrapling.fetchers import Fetcher
        return Fetcher
    except (ImportError, Exception):
        return None


def enrich_post(post_url: str) -> Optional[dict]:
    """
    Fetch a Reddit post page to extract real engagement data
    (upvotes + comment count) that RSS feeds don't provide.

    Uses Reddit's .json endpoint with proper User-Agent.
    Returns None if Reddit blocks the request (common from server IPs).
    """
    # Build .json URL
    url = post_url.rstrip("/")
    if not url.endswith(".json"):
        url += ".json"
    # Use www.reddit.com (not old.)
    url = url.replace("old.reddit.com", "www.reddit.com")

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "cortex-signal:v1.0 (research tool)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        post_data = data[0]["data"]["children"][0]["data"]
        return {
            "score": post_data.get("score", 0),
            "num_comments": post_data.get("num_comments", 0),
        }

    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.info(f"[SIGNALS] Reddit blocked enrichment (403) — server IP likely blocked")
            return None
        logger.warning(f"[SIGNALS] Enrichment HTTP {e.code} for {post_url}")
        return None
    except Exception as e:
        logger.warning(f"[SIGNALS] Enrichment failed for {post_url}: {e}")
        return None


def update_post_engagement(post_id: int, score: int, num_comments: int):
    """Update a post's engagement data (from Scrapling enrichment)."""
    init_signals_db()
    with get_db() as conn:
        conn.execute("""
            UPDATE posts SET score = ?, num_comments = ?
            WHERE id = ?
        """, (score, num_comments, post_id))


def enrich_top_posts(limit: int = 50) -> dict:
    """
    Enrich top-scored posts with real engagement data from old.reddit.com.

    Only enriches posts that still have score=0 (RSS default).
    Respects rate limits with delays between requests.
    """
    init_signals_db()

    with get_db() as conn:
        # Get analyzed posts with no engagement data, ordered by opportunity score
        rows = conn.execute("""
            SELECT p.id, p.url, p.score, p.num_comments
            FROM posts p
            LEFT JOIN analyses a ON a.post_id = p.id
            WHERE p.score = 0 AND p.num_comments = 0
                AND p.url != '' AND p.url IS NOT NULL
            ORDER BY COALESCE(a.opportunity_score, 0) DESC
            LIMIT ?
        """, (limit,)).fetchall()

    stats = {"enriched": 0, "failed": 0, "skipped": 0}

    if not rows:
        return stats

    for row in rows:
        post_id = row[0]
        url = row[1]

        if not url:
            stats["skipped"] += 1
            continue

        result = enrich_post(url)
        if result and (result["score"] > 0 or result["num_comments"] > 0):
            update_post_engagement(post_id, result["score"], result["num_comments"])
            stats["enriched"] += 1
            logger.info(f"[SIGNALS] Enriched post {post_id}: score={result['score']}, comments={result['num_comments']}")
        else:
            stats["failed"] += 1

        time.sleep(REQUEST_DELAY)  # Respect rate limits

    return stats


# ── Engagement Feedback Loop ────────────────────────────────────────────

def check_engagement_changes(min_score: int = 60) -> list[dict]:
    """
    Re-check engagement on high-scoring posts to validate demand.

    Compares current engagement (via Scrapling) against stored values.
    Flags posts where engagement is growing (demand validated).

    Args:
        min_score: Minimum opportunity score to check (default: 60)

    Returns:
        List of dicts with post_id, old/new engagement, delta, growing flag.
    """
    init_signals_db()

    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.id, p.url, p.score, p.num_comments, a.opportunity_score
            FROM posts p
            JOIN analyses a ON a.post_id = p.id
            WHERE a.opportunity_score >= ?
                AND p.url != '' AND p.url IS NOT NULL
                AND (p.score > 0 OR p.num_comments > 0)
            ORDER BY a.opportunity_score DESC
            LIMIT 20
        """, (min_score,)).fetchall()

    if not rows:
        return []

    Fetcher = _get_scrapling_fetcher()
    if not Fetcher:
        logger.warning("[SIGNALS] Scrapling not available for engagement check")
        return []

    results = []
    for row in rows:
        post_id, url, old_score, old_comments, opp_score = row

        current = enrich_post(url)
        if not current:
            continue

        new_score = current["score"]
        new_comments = current["num_comments"]
        score_delta = new_score - old_score
        comment_delta = new_comments - old_comments
        growing = score_delta > 0 or comment_delta > 0

        # Update stored engagement
        if new_score > 0 or new_comments > 0:
            update_post_engagement(post_id, new_score, new_comments)

        results.append({
            "post_id": post_id,
            "opportunity_score": opp_score,
            "old_score": old_score,
            "new_score": new_score,
            "score_delta": score_delta,
            "old_comments": old_comments,
            "new_comments": new_comments,
            "comment_delta": comment_delta,
            "growing": growing,
        })

        time.sleep(REQUEST_DELAY)

    return results
