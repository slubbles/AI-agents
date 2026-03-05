"""
Signal Collector — Reddit public JSON API scraper for pain point discovery.

Fetches posts from target subreddits using Reddit's public JSON API.
No authentication needed. No PRAW dependency. Pure urllib.

Pipeline:
    1. For each subreddit, search with pain-point keywords
    2. Filter by keyword match in title/body
    3. Store in SQLite (deduped by reddit_id)
    4. Zero LLM cost — pure HTTP + regex

Modeled after: github.com/lefttree/reddit-pain-points

Rate limits: Reddit public API allows ~10 req/min unauthenticated.
We enforce a 2-second delay between requests.
"""

import json
import logging
import os
import re
import sqlite3
import time
import urllib.request
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

SIGNALS_DB_PATH = os.path.join(os.path.dirname(__file__), "logs", "signals.db")

# Reddit rate limit: ~10 req/min for unauthenticated
REQUEST_DELAY = 2.5  # seconds between requests (conservative)
USER_AGENT = "cortex-signal-collector/1.0 (research tool)"

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


def _reddit_request(url: str, params: dict, timeout: int = 30) -> Optional[dict]:
    """Make a request to Reddit's public JSON API."""
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"

    req = urllib.request.Request(full_url)
    req.add_header("User-Agent", USER_AGENT)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.warning("[SIGNALS] Reddit rate limit hit, backing off 10s")
            time.sleep(10)
        else:
            logger.warning(f"[SIGNALS] HTTP {e.code} for {url}")
        return None
    except (urllib.error.URLError, Exception) as e:
        logger.warning(f"[SIGNALS] Request failed: {e}")
        return None


import urllib.parse  # needed for urlencode


def scrape_subreddit(
    subreddit: str,
    search_terms: list[str] = None,
    limit_per_term: int = 25,
    time_filter: str = "month",
) -> dict:
    """
    Scrape a subreddit using Reddit's public JSON search API.

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
        data = _reddit_request(
            f"https://www.reddit.com/r/{subreddit}/search.json",
            {
                "q": term,
                "restrict_sr": "on",
                "sort": "relevance",
                "t": time_filter,
                "limit": str(min(limit_per_term, 25)),
            },
        )

        if data is None:
            stats["errors"] += 1
            time.sleep(REQUEST_DELAY)
            continue

        posts = data.get("data", {}).get("children", [])

        for post in posts:
            pd = post.get("data", {})
            post_id = pd.get("name", "")

            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            stats["found"] += 1

            title = pd.get("title", "")
            body = pd.get("selftext", "")
            full_text = f"{title} {body}"

            if not _matches_pain_keywords(full_text):
                continue

            stats["matched"] += 1

            is_new = insert_post({
                "reddit_id": post_id,
                "subreddit": subreddit,
                "title": title,
                "body": body[:5000],
                "author": pd.get("author", "[deleted]"),
                "url": f"https://reddit.com{pd.get('permalink', '')}",
                "score": pd.get("score", 0),
                "num_comments": pd.get("num_comments", 0),
                "created_utc": pd.get("created_utc", 0),
            })
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
