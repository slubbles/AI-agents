"""
Tests for Signal Intelligence system:
1. Signal collector (signal_collector.py) — DB, keyword matching, scraping
2. Opportunity scorer (opportunity_scorer.py) — analysis, ranking, briefs
3. CLI commands (cli/signals_cmd.py)
"""

import json
import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# 1. Signal Collector — Database Tests
# ============================================================

class TestSignalsDatabase:
    """Test SQLite storage for collected posts."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        """Use a temp database for each test."""
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield db_path
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_init_creates_tables(self):
        from signal_collector import init_signals_db, get_db
        init_signals_db()
        with get_db() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            names = {r[0] for r in tables}
            assert "posts" in names
            assert "analyses" in names
            assert "collection_runs" in names

    def test_insert_post_returns_true_for_new(self):
        from signal_collector import insert_post, init_signals_db
        init_signals_db()
        result = insert_post({
            "reddit_id": "t3_abc123",
            "subreddit": "SaaS",
            "title": "I wish there was a better tool",
            "body": "Frustrated with current options",
            "author": "testuser",
            "url": "https://reddit.com/r/SaaS/abc123",
            "score": 42,
            "num_comments": 10,
            "created_utc": 1700000000,
        })
        assert result is True

    def test_insert_post_returns_false_for_duplicate(self):
        from signal_collector import insert_post, init_signals_db
        init_signals_db()
        post = {
            "reddit_id": "t3_dup001",
            "subreddit": "SaaS",
            "title": "Duplicate test",
        }
        assert insert_post(post) is True
        assert insert_post(post) is False

    def test_get_unanalyzed_posts(self):
        from signal_collector import insert_post, get_unanalyzed_posts, init_signals_db
        init_signals_db()
        for i in range(3):
            insert_post({
                "reddit_id": f"t3_un{i}",
                "subreddit": "SaaS",
                "title": f"Test post {i}",
                "score": i * 10,
                "num_comments": i * 5,
            })
        posts = get_unanalyzed_posts(limit=10)
        assert len(posts) == 3
        # Should be ordered by engagement (score + comments*2)
        assert posts[0]["score"] >= posts[-1]["score"]

    def test_insert_analysis_marks_as_analyzed(self):
        from signal_collector import (
            insert_post, insert_analysis, get_unanalyzed_posts,
            init_signals_db, get_db,
        )
        init_signals_db()
        insert_post({"reddit_id": "t3_ana001", "subreddit": "SaaS", "title": "Test"})
        posts = get_unanalyzed_posts()
        assert len(posts) == 1

        insert_analysis(posts[0]["id"], {
            "pain_point_summary": "Needs better tool",
            "category": "Productivity",
            "severity": 3,
            "opportunity_score": 65,
        })

        remaining = get_unanalyzed_posts()
        assert len(remaining) == 0

    def test_get_top_opportunities(self):
        from signal_collector import (
            insert_post, insert_analysis, get_top_opportunities, init_signals_db,
        )
        init_signals_db()
        for i in range(3):
            insert_post({
                "reddit_id": f"t3_top{i}",
                "subreddit": "SaaS",
                "title": f"Pain point {i}",
                "score": 10,
                "num_comments": 5,
            })
        posts_data = [
            {"pain_point_summary": "Low pain", "opportunity_score": 20},
            {"pain_point_summary": "Medium pain", "opportunity_score": 55},
            {"pain_point_summary": "High pain", "opportunity_score": 90},
        ]
        from signal_collector import get_unanalyzed_posts
        posts = get_unanalyzed_posts()
        for post, analysis in zip(posts, posts_data):
            insert_analysis(post["id"], analysis)

        top = get_top_opportunities(limit=3)
        assert len(top) == 3
        assert top[0]["opportunity_score"] == 90  # Highest first

    def test_get_collection_stats(self):
        from signal_collector import insert_post, get_collection_stats, init_signals_db
        init_signals_db()
        insert_post({"reddit_id": "t3_s1", "subreddit": "SaaS", "title": "Test 1"})
        insert_post({"reddit_id": "t3_s2", "subreddit": "startups", "title": "Test 2"})

        stats = get_collection_stats()
        assert stats["total_posts"] == 2
        assert stats["unanalyzed"] == 2
        assert len(stats["subreddits"]) == 2

    def test_body_truncated_to_5000(self):
        from signal_collector import insert_post, get_unanalyzed_posts, init_signals_db
        init_signals_db()
        long_body = "x" * 10000
        insert_post({
            "reddit_id": "t3_long1",
            "subreddit": "SaaS",
            "title": "Long post",
            "body": long_body,
        })
        posts = get_unanalyzed_posts()
        assert len(posts[0]["body"]) <= 5000


# ============================================================
# 2. Signal Collector — Keyword Matching
# ============================================================

class TestKeywordMatching:
    """Test pain-point keyword filtering."""

    def test_matches_exact_keyword(self):
        from signal_collector import _matches_pain_keywords
        assert _matches_pain_keywords("I wish there was a better tool") is True

    def test_matches_case_insensitive(self):
        from signal_collector import _matches_pain_keywords
        assert _matches_pain_keywords("I WISH there was something") is True

    def test_no_match_for_neutral_text(self):
        from signal_collector import _matches_pain_keywords
        assert _matches_pain_keywords("Today I went to the park and had lunch") is False

    def test_matches_alternative_keyword(self):
        from signal_collector import _matches_pain_keywords
        assert _matches_pain_keywords("Looking for alternative to Notion") is True

    def test_matches_would_pay(self):
        from signal_collector import _matches_pain_keywords
        assert _matches_pain_keywords("I would pay for this feature") is True

    def test_matches_frustrated(self):
        from signal_collector import _matches_pain_keywords
        assert _matches_pain_keywords("So frustrated with this process") is True

    def test_matches_waste_of_time(self):
        from signal_collector import _matches_pain_keywords
        assert _matches_pain_keywords("This workflow is a waste of time") is True


# ============================================================
# 3. Signal Collector — Reddit Fetching (RSS)
# ============================================================

class TestRedditFetching:
    """Test Reddit RSS/Atom feed fetching and parsing."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_strip_html_removes_tags(self):
        from signal_collector import _strip_html
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_strip_html_decodes_entities(self):
        from signal_collector import _strip_html
        assert _strip_html("&amp; &lt;b&gt;bold&lt;/b&gt;") == "& bold"

    @patch("signal_collector._reddit_rss_request")
    @patch("signal_collector.REQUEST_DELAY", 0)
    def test_scrape_subreddit_extracts_posts(self, mock_rss):
        from signal_collector import scrape_subreddit
        mock_rss.return_value = [
            {
                "reddit_id": "t3_mock001",
                "title": "I wish there was a better CRM",
                "body": "So frustrated with current tools",
                "author": "mockuser",
                "url": "https://old.reddit.com/r/SaaS/comments/mock001/test/",
                "subreddit": "SaaS",
                "score": 0,
                "num_comments": 0,
                "created_utc": 1700000000,
            }
        ]

        stats = scrape_subreddit("SaaS", search_terms=["frustrated"])
        assert stats["found"] >= 1
        assert stats["matched"] >= 1
        assert stats["new"] >= 1

    @patch("signal_collector._reddit_rss_request")
    @patch("signal_collector.REQUEST_DELAY", 0)
    def test_scrape_skips_non_matching_posts(self, mock_rss):
        from signal_collector import scrape_subreddit
        mock_rss.return_value = [
            {
                "reddit_id": "t3_nomatch",
                "title": "Beautiful day today",
                "body": "Everything is great",
                "author": "happyuser",
                "url": "https://old.reddit.com/r/SaaS/comments/nomatch/",
                "subreddit": "SaaS",
                "score": 0,
                "num_comments": 0,
                "created_utc": 1700000000,
            }
        ]

        stats = scrape_subreddit("SaaS", search_terms=["frustrated"])
        assert stats["found"] >= 1
        assert stats["matched"] == 0

    @patch("signal_collector._reddit_rss_request")
    @patch("signal_collector.REQUEST_DELAY", 0)
    def test_scrape_handles_api_failure(self, mock_rss):
        from signal_collector import scrape_subreddit
        mock_rss.return_value = None  # RSS failure

        stats = scrape_subreddit("SaaS", search_terms=["frustrated"])
        assert stats["errors"] >= 1

    @patch("signal_collector._reddit_rss_request")
    @patch("signal_collector.REQUEST_DELAY", 0)
    def test_scrape_deduplicates_across_terms(self, mock_rss):
        from signal_collector import scrape_subreddit
        # Same post returned for two different search terms
        post_entry = {
            "reddit_id": "t3_dedup001",
            "title": "I wish I could find a tool to automate this",
            "body": "Frustrated with manual work",
            "author": "user1",
            "url": "https://old.reddit.com/r/SaaS/comments/dedup001/",
            "subreddit": "SaaS",
            "score": 0,
            "num_comments": 0,
            "created_utc": 1700000000,
        }
        mock_rss.return_value = [post_entry]

        stats = scrape_subreddit("SaaS", search_terms=["i wish", "frustrated"])
        # Found once per term but only counted/stored once
        assert stats["new"] == 1

    def test_reddit_rss_request_parses_atom(self):
        """Test that _reddit_rss_request correctly parses Atom XML."""
        from signal_collector import _reddit_rss_request
        atom_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <id>t3_test123</id>
                <title>I wish there was a better tool</title>
                <link href="https://old.reddit.com/r/SaaS/comments/test123/"/>
                <updated>2026-03-01T12:00:00+00:00</updated>
                <published>2026-03-01T12:00:00+00:00</published>
                <author><name>/u/testuser</name></author>
                <category term="SaaS"/>
                <content type="html">&lt;p&gt;Frustrated with current tools&lt;/p&gt;</content>
            </entry>
        </feed>'''

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = atom_xml.encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            entries = _reddit_rss_request("https://old.reddit.com/r/SaaS/search.rss", {"q": "test"})
            assert entries is not None
            assert len(entries) == 1
            assert entries[0]["reddit_id"] == "t3_test123"
            assert entries[0]["title"] == "I wish there was a better tool"
            assert entries[0]["author"] == "testuser"
            assert entries[0]["subreddit"] == "SaaS"
            assert "Frustrated" in entries[0]["body"]


# ============================================================
# 4. Signal Collector — Full Collection Cycle
# ============================================================

class TestCollectSignals:
    """Test full collection cycle."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    @patch("signal_collector.scrape_subreddit")
    def test_collect_signals_aggregates(self, mock_scrape):
        from signal_collector import collect_signals
        mock_scrape.return_value = {"found": 10, "matched": 5, "new": 3, "errors": 0}

        result = collect_signals(subreddits=["SaaS", "startups"])
        assert result["total_found"] == 20  # 10 per sub
        assert result["total_matched"] == 10
        assert result["total_new"] == 6
        assert "duration_seconds" in result
        assert "per_subreddit" in result
        assert "SaaS" in result["per_subreddit"]

    @patch("signal_collector.scrape_subreddit")
    def test_collect_signals_logs_run(self, mock_scrape):
        from signal_collector import collect_signals, get_db, init_signals_db
        init_signals_db()
        mock_scrape.return_value = {"found": 5, "matched": 2, "new": 1, "errors": 0}

        collect_signals(subreddits=["SaaS"])
        with get_db() as conn:
            runs = conn.execute("SELECT * FROM collection_runs").fetchall()
            assert len(runs) == 1
            assert dict(runs[0])["status"] == "completed"


# ============================================================
# 5. Opportunity Scorer — Analysis
# ============================================================

class TestOpportunityScorer:
    """Test LLM-based analysis and scoring."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_format_posts_block(self):
        from opportunity_scorer import _format_posts_block
        posts = [
            {"id": 1, "subreddit": "SaaS", "title": "Test", "body": "Body text",
             "score": 10, "num_comments": 5},
        ]
        block = _format_posts_block(posts)
        assert "Post ID: 1" in block
        assert "r/SaaS" in block
        assert "Test" in block

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_analyze_batch_parses_response(self, mock_cost, mock_llm):
        from opportunity_scorer import analyze_batch

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "post_id": 1,
                "pain_point_summary": "No good CRM for small teams",
                "category": "Business",
                "severity": 4,
                "affected_audience": "Small business owners",
                "potential_solutions": ["Simple CRM", "AI assistant"],
                "market_size_estimate": "Large",
                "existing_solutions": ["HubSpot", "Salesforce"],
                "opportunity_score": 72,
            }
        ]))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)
        mock_llm.return_value = mock_response

        posts = [{"id": 1, "subreddit": "SaaS", "title": "Need CRM", "body": "", "score": 5, "num_comments": 2}]
        results = analyze_batch(posts)
        assert len(results) == 1
        assert results[0]["opportunity_score"] == 72

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_analyze_batch_empty_input(self, mock_cost, mock_llm):
        from opportunity_scorer import analyze_batch
        results = analyze_batch([])
        assert results == []
        mock_llm.assert_not_called()

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_score_unanalyzed_processes_posts(self, mock_cost, mock_llm):
        from signal_collector import insert_post, init_signals_db
        from opportunity_scorer import score_unanalyzed

        init_signals_db()
        insert_post({"reddit_id": "t3_score1", "subreddit": "SaaS", "title": "I wish there was X"})
        insert_post({"reddit_id": "t3_score2", "subreddit": "SaaS", "title": "Frustrated with Y"})

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"post_id": 1, "pain_point_summary": "Pain X", "opportunity_score": 60, "severity": 3,
             "category": "Productivity", "affected_audience": "devs", "potential_solutions": [],
             "market_size_estimate": "Medium", "existing_solutions": []},
            {"post_id": 2, "pain_point_summary": "Pain Y", "opportunity_score": 80, "severity": 4,
             "category": "Business", "affected_audience": "founders", "potential_solutions": [],
             "market_size_estimate": "Large", "existing_solutions": []},
        ]))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=200)
        mock_llm.return_value = mock_response

        result = score_unanalyzed(batch_size=10)
        assert result["analyzed"] == 2
        assert result["top_score"] == 80

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_score_clamps_to_100(self, mock_cost, mock_llm):
        from signal_collector import insert_post, init_signals_db
        from opportunity_scorer import score_unanalyzed

        init_signals_db()
        insert_post({"reddit_id": "t3_clamp1", "subreddit": "SaaS", "title": "I wish X"})

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"post_id": 1, "pain_point_summary": "Over-scored", "opportunity_score": 150,
             "severity": 5, "category": "Other", "affected_audience": "all",
             "potential_solutions": [], "market_size_estimate": "Large", "existing_solutions": []},
        ]))]
        mock_response.usage = MagicMock(input_tokens=50, output_tokens=100)
        mock_llm.return_value = mock_response

        result = score_unanalyzed()
        assert result["top_score"] <= 100


# ============================================================
# 6. Opportunity Scorer — Weekly Brief
# ============================================================

class TestWeeklyBrief:
    """Test weekly brief generation."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_brief_returns_message_when_empty(self):
        from opportunity_scorer import generate_weekly_brief
        from signal_collector import init_signals_db
        init_signals_db()
        result = generate_weekly_brief()
        assert "No opportunities" in result

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_brief_includes_header(self, mock_cost, mock_llm):
        from signal_collector import insert_post, insert_analysis, init_signals_db
        from opportunity_scorer import generate_weekly_brief

        init_signals_db()
        insert_post({"reddit_id": "t3_brief1", "subreddit": "SaaS", "title": "Pain test", "score": 10, "num_comments": 5})
        from signal_collector import get_unanalyzed_posts
        posts = get_unanalyzed_posts()
        insert_analysis(posts[0]["id"], {
            "pain_point_summary": "Users need X",
            "opportunity_score": 75,
            "severity": 4,
            "category": "Productivity",
            "affected_audience": "Developers",
            "potential_solutions": json.dumps(["Build X"]),
            "market_size_estimate": "Medium",
            "existing_solutions": json.dumps(["Tool A"]),
        })

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Top Opportunities\nBuild X for developers.")]
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=300)
        mock_llm.return_value = mock_response

        brief = generate_weekly_brief()
        assert "Weekly Signal Brief" in brief
        assert "Collection stats" in brief


# ============================================================
# 7. CLI Commands
# ============================================================

class TestSignalsCLI:
    """Test CLI command wrappers."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    @patch("signal_collector.collect_signals")
    def test_run_collect_signals(self, mock_collect, capsys):
        from cli.signals_cmd import run_collect_signals
        mock_collect.return_value = {
            "total_found": 50,
            "total_matched": 20,
            "total_new": 15,
            "per_subreddit": {"SaaS": {"found": 50, "matched": 20, "new": 15}},
            "duration_seconds": 30.5,
        }
        run_collect_signals()
        output = capsys.readouterr().out
        assert "COLLECTION COMPLETE" in output
        assert "15" in output  # new count

    def test_run_signal_status_empty(self, capsys):
        from cli.signals_cmd import run_signal_status
        from signal_collector import init_signals_db
        init_signals_db()
        run_signal_status()
        output = capsys.readouterr().out
        assert "SIGNAL INTELLIGENCE STATUS" in output
        assert "0" in output  # total posts

    def test_rank_opportunities_no_unanalyzed(self, capsys):
        from cli.signals_cmd import run_rank_opportunities
        from signal_collector import init_signals_db
        init_signals_db()
        run_rank_opportunities()
        output = capsys.readouterr().out
        assert "Run --collect-signals first" in output


# ============================================================
# 8. Config Constants
# ============================================================

class TestSignalConfig:
    """Test configuration values are sensible."""

    def test_default_subreddits_nonempty(self):
        from signal_collector import DEFAULT_SUBREDDITS
        assert len(DEFAULT_SUBREDDITS) >= 5

    def test_pain_keywords_nonempty(self):
        from signal_collector import PAIN_KEYWORDS
        assert len(PAIN_KEYWORDS) >= 20

    def test_search_terms_nonempty(self):
        from signal_collector import SEARCH_TERMS
        assert len(SEARCH_TERMS) >= 10

    def test_categories_include_basics(self):
        from signal_collector import CATEGORIES
        assert "Productivity" in CATEGORIES
        assert "Developer Tools" in CATEGORIES
        assert "Business" in CATEGORIES


# ============================================================
# 9. Scrapling Enrichment
# ============================================================

class TestScraplingEnrichment:
    """Test Scrapling-based post enrichment."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_update_post_engagement(self):
        from signal_collector import insert_post, update_post_engagement, get_unanalyzed_posts, init_signals_db
        init_signals_db()
        insert_post({
            "reddit_id": "t3_enrich1",
            "subreddit": "SaaS",
            "title": "Test enrichment",
            "url": "https://reddit.com/r/SaaS/test",
            "score": 0,
            "num_comments": 0,
        })
        posts = get_unanalyzed_posts()
        assert posts[0]["score"] == 0

        update_post_engagement(posts[0]["id"], score=42, num_comments=15)

        posts = get_unanalyzed_posts()
        assert posts[0]["score"] == 42
        assert posts[0]["num_comments"] == 15

    @patch("signal_collector._get_scrapling_fetcher")
    def test_enrich_post_extracts_data(self, mock_fetcher):
        from signal_collector import enrich_post

        mock_page = MagicMock()

        def css_side_effect(selector):
            if "score.unvoted" in selector:
                return ["142"]
            if "score" in selector:
                return ["142"]
            if "bylink" in selector:
                mock_links = MagicMock()
                mock_links.getall = MagicMock(return_value=["23 comments"])
                return mock_links
            return []

        mock_page.css = MagicMock(side_effect=css_side_effect)
        mock_fetcher_cls = MagicMock()
        mock_fetcher_cls.return_value.get.return_value = mock_page
        mock_fetcher.return_value = mock_fetcher_cls

        result = enrich_post("https://www.reddit.com/r/SaaS/comments/test123/test/")
        assert result is not None
        assert isinstance(result, dict)
        assert "score" in result
        assert "num_comments" in result

    def test_enrich_post_returns_none_without_scrapling(self):
        from signal_collector import enrich_post
        with patch("signal_collector._get_scrapling_fetcher", return_value=None):
            result = enrich_post("https://reddit.com/r/SaaS/test")
            assert result is None

    def test_enrich_top_posts_skips_without_scrapling(self):
        from signal_collector import enrich_top_posts, insert_post, insert_analysis, init_signals_db
        init_signals_db()
        insert_post({
            "reddit_id": "t3_enrich_skip",
            "subreddit": "SaaS",
            "title": "I wish there was X",
            "url": "https://reddit.com/r/SaaS/test",
            "score": 0,
            "num_comments": 0,
        })
        from signal_collector import get_unanalyzed_posts
        posts = get_unanalyzed_posts()
        insert_analysis(posts[0]["id"], {"pain_point_summary": "Test", "opportunity_score": 80})

        with patch("signal_collector._get_scrapling_fetcher", return_value=None):
            stats = enrich_top_posts(limit=10)
            assert stats["skipped"] == 1
            assert stats["enriched"] == 0

    def test_enrich_top_posts_empty_db(self):
        from signal_collector import enrich_top_posts, init_signals_db
        init_signals_db()
        stats = enrich_top_posts(limit=10)
        assert stats["enriched"] == 0
        assert stats["failed"] == 0


# ============================================================
# 10. Build Spec Generator
# ============================================================

class TestBuildSpecGenerator:
    """Test LLM-based build spec generation."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_generate_build_spec_returns_dict(self, mock_cost, mock_llm, tmp_path):
        from opportunity_scorer import generate_build_spec

        spec_data = {
            "product_name": "PayPal Shield",
            "problem_statement": "SaaS founders face unexpected PayPal restrictions",
            "target_audience": "SaaS founders processing $1K-50K/mo via PayPal",
            "core_features": ["Risk dashboard", "Alert system", "Compliance checker"],
            "tech_stack": "Next.js + Supabase + PayPal API",
            "mvp_scope": "3 pages: dashboard, alerts, settings",
            "monetization": "$29/mo SaaS subscription",
            "existing_competitors": ["PayPal Business (limited)"],
            "competitive_gap": "No tool monitors PayPal risk specifically for SaaS",
            "research_questions": ["What PayPal API endpoints expose account health?"],
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(spec_data))]
        mock_response.usage = MagicMock(input_tokens=300, output_tokens=400)
        mock_llm.return_value = mock_response

        opp = {
            "pain_point_summary": "PayPal account restrictions for SaaS founders",
            "category": "Finance",
            "severity": 5,
            "affected_audience": "SaaS founders",
            "market_size_estimate": "Large",
            "existing_solutions": json.dumps(["PayPal Business"]),
            "potential_solutions": json.dumps(["Risk dashboard"]),
            "title": "PayPal froze my account",
            "subreddit": "SaaS",
            "opportunity_score": 90,
        }

        # Patch _save_build_spec to write to tmp_path
        with patch("opportunity_scorer._save_build_spec"):
            spec = generate_build_spec(opp)

        assert spec is not None
        assert spec["product_name"] == "PayPal Shield"
        assert "core_features" in spec
        assert len(spec["core_features"]) >= 1
        assert "research_questions" in spec

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_generate_build_spec_supports_reality_check_fields(self, mock_cost, mock_llm, tmp_path):
        from opportunity_scorer import generate_build_spec

        spec_data = {
            "product_name": "CallGuard",
            "problem_statement": "Missed emergency calls cost local contractors real revenue.",
            "target_audience": "1-3 employee HVAC shops",
            "core_features": ["Alerts"],
            "tech_stack": "Next.js + Supabase + Twilio",
            "mvp_scope": "Landing page + callback alerts",
            "monetization": "$97/mo",
            "existing_competitors": ["Smith.ai"],
            "competitive_gap": "Cheaper than live answering for micro-shops",
            "narrow_wedge": "After-hours emergency HVAC shops",
            "distribution_strategy": "Manual outreach to Google Maps prospects",
            "killer_objections": ["Trust", "Already use dispatcher"],
            "why_this_could_fail": "Crowded and hard to distribute",
            "research_questions": ["Will they trust automation?"],
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(spec_data))]
        mock_response.usage = MagicMock(input_tokens=300, output_tokens=400)
        mock_llm.return_value = mock_response

        opp = {
            "pain_point_summary": "Missed emergency calls for contractors",
            "category": "Communication",
            "severity": 5,
            "affected_audience": "HVAC contractors",
            "market_size_estimate": "Medium",
            "existing_solutions": json.dumps(["Smith.ai"]),
            "potential_solutions": json.dumps(["Call alerts"]),
            "title": "Missing after-hours HVAC calls",
            "subreddit": "smallbusiness",
            "opportunity_score": 85,
        }

        with patch("opportunity_scorer._save_build_spec"):
            spec = generate_build_spec(opp)

        assert spec is not None
        assert spec["narrow_wedge"] == "After-hours emergency HVAC shops"
        assert "distribution_strategy" in spec
        assert "killer_objections" in spec
        assert "why_this_could_fail" in spec

    @patch("opportunity_scorer.call_llm")
    @patch("opportunity_scorer.log_cost")
    def test_generate_build_spec_handles_parse_failure(self, mock_cost, mock_llm):
        from opportunity_scorer import generate_build_spec

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not valid JSON at all")]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_llm.return_value = mock_response

        opp = {
            "pain_point_summary": "Test pain",
            "category": "Other",
            "severity": 2,
            "title": "Test",
            "subreddit": "test",
        }

        with patch("opportunity_scorer._save_build_spec"):
            spec = generate_build_spec(opp)
        assert spec is None

    def test_save_build_spec_creates_file(self, tmp_path):
        from opportunity_scorer import _save_build_spec
        import opportunity_scorer

        # Temporarily redirect log dir
        orig_file = opportunity_scorer.__file__
        with patch.object(opportunity_scorer.os.path, "dirname", return_value=str(tmp_path)):
            _save_build_spec(
                {"product_name": "TestProd", "mvp_scope": "test"},
                {"post_id": 1, "opportunity_score": 80, "pain_point_summary": "test", "subreddit": "SaaS", "title": "T"},
            )
        spec_dir = tmp_path / "logs" / "build_specs"
        assert spec_dir.exists()
        files = list(spec_dir.glob("*.json"))
        assert len(files) == 1

    @patch("opportunity_scorer.generate_build_spec")
    @patch("opportunity_scorer._save_decision_packet")
    @patch("agents.cortex.reality_check_opportunity")
    def test_generate_opportunity_decision_packet_returns_combined_packet(
        self,
        mock_reality_check,
        mock_save_packet,
        mock_build_spec,
    ):
        from opportunity_scorer import generate_opportunity_decision_packet

        mock_build_spec.return_value = {
            "product_name": "CallGuard",
            "narrow_wedge": "Emergency HVAC shops",
            "distribution_strategy": "Direct cold outreach",
            "core_features": ["Missed-call alerting"],
        }
        mock_reality_check.return_value = {
            "verdict": "Test concierge wedge first",
            "worth_building_now": False,
            "underserved_wedge": "Emergency HVAC shops",
            "direct_gtm_plan": "Manual outreach to owner-operators",
        }
        mock_save_packet.return_value = "/tmp/callguard_decision.json"

        opp = {
            "post_id": 7,
            "pain_point_summary": "Missed after-hours service calls",
            "opportunity_score": 84,
            "severity": 5,
            "affected_audience": "Local contractors",
            "subreddit": "smallbusiness",
            "title": "We keep missing emergency calls",
        }

        packet = generate_opportunity_decision_packet(opp, focus="Be ruthless")

        assert packet is not None
        assert packet["build_spec"]["product_name"] == "CallGuard"
        assert packet["reality_check"]["verdict"] == "Test concierge wedge first"
        assert packet["decision_summary"]["best_wedge"] == "Emergency HVAC shops"
        assert packet["artifact_path"] == "/tmp/callguard_decision.json"

    def test_save_decision_packet_creates_file(self, tmp_path):
        from opportunity_scorer import _save_decision_packet
        import opportunity_scorer

        packet = {
            "decision_summary": {"verdict": "Skip"},
            "generated_at": "2026-03-06T00:00:00+00:00",
        }
        spec = {"product_name": "TestProd"}

        with patch.object(opportunity_scorer.os.path, "dirname", return_value=str(tmp_path)):
            filepath = _save_decision_packet(packet, spec)

        assert filepath.endswith("_decision.json")
        spec_dir = tmp_path / "logs" / "build_specs"
        assert spec_dir.exists()
        files = list(spec_dir.glob("*_decision.json"))
        assert len(files) == 1


# ============================================================
# 11. Signal Bridge — Signal → Brain Integration
# ============================================================

class TestSignalBridge:
    """Test signal-to-brain question generation bridge."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_generate_signal_questions_empty_db(self):
        from signal_bridge import generate_signal_questions
        from signal_collector import init_signals_db
        init_signals_db()
        questions = generate_signal_questions(limit=3)
        assert questions == []

    def test_generate_signal_questions_with_data(self):
        from signal_bridge import generate_signal_questions
        from signal_collector import insert_post, insert_analysis, init_signals_db
        init_signals_db()

        # Insert a high-scoring opportunity
        insert_post({
            "reddit_id": "t3_bridge1",
            "subreddit": "SaaS",
            "title": "PayPal froze my account",
            "body": "I wish there was a tool to monitor PayPal risk",
            "score": 50,
            "num_comments": 20,
        })
        from signal_collector import get_unanalyzed_posts
        posts = get_unanalyzed_posts()
        insert_analysis(posts[0]["id"], {
            "pain_point_summary": "SaaS founders face unexpected PayPal restrictions",
            "category": "Finance",
            "severity": 5,
            "affected_audience": "SaaS founders processing via PayPal",
            "potential_solutions": json.dumps(["Risk dashboard"]),
            "existing_solutions": json.dumps(["PayPal Business"]),
            "opportunity_score": 90,
        })

        questions = generate_signal_questions(limit=3, min_score=60)
        assert len(questions) >= 1
        assert questions[0]["source"] == "signal"
        assert questions[0]["opportunity_score"] == 90
        assert questions[0]["priority"] == "high"
        assert "PayPal" in questions[0]["question"]

    def test_generate_signal_questions_filters_low_scores(self):
        from signal_bridge import generate_signal_questions
        from signal_collector import insert_post, insert_analysis, init_signals_db
        init_signals_db()

        insert_post({
            "reddit_id": "t3_bridge_low",
            "subreddit": "SaaS",
            "title": "Minor annoyance",
        })
        from signal_collector import get_unanalyzed_posts
        posts = get_unanalyzed_posts()
        insert_analysis(posts[0]["id"], {
            "pain_point_summary": "Minor inconvenience",
            "opportunity_score": 25,
        })

        questions = generate_signal_questions(limit=3, min_score=60)
        assert len(questions) == 0

    def test_domain_mapping(self):
        from signal_bridge import get_signal_domain_for_category
        assert get_signal_domain_for_category("Finance") == "fintech"
        assert get_signal_domain_for_category("Marketing") == "marketing-tools"
        assert get_signal_domain_for_category("Developer Tools") == "dev-tools"
        assert get_signal_domain_for_category("Unknown Category") == "micro-saas"

    def test_deduplicates_similar_pain_points(self):
        from signal_bridge import generate_signal_questions
        from signal_collector import insert_post, insert_analysis, init_signals_db
        init_signals_db()

        for i in range(3):
            insert_post({
                "reddit_id": f"t3_dup_bridge{i}",
                "subreddit": "SaaS",
                "title": f"PayPal problem {i}",
            })
        from signal_collector import get_unanalyzed_posts
        posts = get_unanalyzed_posts()
        for p in posts:
            insert_analysis(p["id"], {
                "pain_point_summary": "SaaS founders face unexpected PayPal restrictions",
                "category": "Finance",
                "severity": 5,
                "affected_audience": "SaaS founders",
                "opportunity_score": 85,
            })

        questions = generate_signal_questions(limit=5, min_score=60)
        # Should deduplicate — same pain point summary
        assert len(questions) == 1


# ============================================================
# 12. CLI — Enrichment + Build Spec
# ============================================================

class TestSignalsCLIExtended:
    """Test new CLI commands for enrichment and build specs."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_run_enrich_empty_db(self, capsys):
        from cli.signals_cmd import run_enrich_signals
        from signal_collector import init_signals_db
        init_signals_db()
        run_enrich_signals()
        output = capsys.readouterr().out
        assert "No posts" in output

    @patch("signal_collector.enrich_top_posts")
    def test_run_enrich_shows_results(self, mock_enrich, capsys):
        from cli.signals_cmd import run_enrich_signals
        from signal_collector import insert_post, init_signals_db
        init_signals_db()
        insert_post({"reddit_id": "t3_cli_enrich", "subreddit": "SaaS", "title": "Test"})
        mock_enrich.return_value = {"enriched": 5, "failed": 1, "skipped": 0}

        run_enrich_signals()
        output = capsys.readouterr().out
        assert "ENRICHMENT COMPLETE" in output
        assert "5" in output

    def test_run_build_spec_no_opportunities(self, capsys):
        from cli.signals_cmd import run_build_spec
        from signal_collector import init_signals_db
        init_signals_db()
        run_build_spec(1)
        output = capsys.readouterr().out
        assert "not found" in output

    def test_run_reality_check_no_opportunities(self, capsys):
        from cli.signals_cmd import run_reality_check
        from signal_collector import init_signals_db
        init_signals_db()
        run_reality_check(1)
        output = capsys.readouterr().out
        assert "not found" in output

    @patch("cli.signals_cmd.generate_opportunity_decision_packet")
    @patch("cli.signals_cmd.get_top_opportunities")
    def test_run_reality_check_shows_results(self, mock_get_top, mock_packet, capsys):
        from cli.signals_cmd import run_reality_check

        mock_get_top.return_value = [{
            "pain_point_summary": "Missed emergency service calls",
            "opportunity_score": 88,
        }]
        mock_packet.return_value = {
            "build_spec": {"product_name": "CallGuard"},
            "reality_check": {
                "verdict": "Test first",
                "worth_building_now": False,
                "why_not": "Crowded market",
                "strongest_objections": ["Switching costs"],
                "final_recommendation": "Run concierge validation",
            },
            "decision_summary": {
                "verdict": "Test first",
                "worth_building_now": False,
                "best_wedge": "Emergency HVAC shops",
                "direct_gtm_plan": "Manual outreach",
            },
            "artifact_path": "/tmp/callguard_decision.json",
        }

        run_reality_check(1, focus="Be blunt")
        output = capsys.readouterr().out
        assert "REALITY CHECK" in output
        assert "CallGuard" in output
        assert "Worth Building Now: No" in output
        assert "Emergency HVAC shops" in output


# ============================================================
# Signal-Aware Daemon Tests
# ============================================================

class TestSignalDaemon:
    """Test signal intelligence integration in the scheduler daemon."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        """Use a temp database for each test."""
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield db_path
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    @pytest.fixture(autouse=True)
    def tmp_logs(self, tmp_path):
        """Use temp log directory for signal state."""
        import scheduler
        self._orig_signal_state = scheduler.SIGNAL_STATE_FILE
        scheduler.SIGNAL_STATE_FILE = str(tmp_path / "signal_state.json")
        scheduler._last_signal_collection = None
        yield
        scheduler.SIGNAL_STATE_FILE = self._orig_signal_state
        scheduler._last_signal_collection = None

    def test_should_run_signals_first_time(self):
        """First run (no state file) should return True."""
        from scheduler import _should_run_signals
        assert _should_run_signals() is True

    def test_should_run_signals_within_interval(self):
        """Returns False if we just ran."""
        import scheduler
        scheduler._last_signal_collection = datetime.now(timezone.utc)
        assert scheduler._should_run_signals() is False

    def test_should_run_signals_after_interval(self):
        """Returns True after interval has elapsed."""
        import scheduler
        from datetime import timedelta
        scheduler._last_signal_collection = (
            datetime.now(timezone.utc) - timedelta(hours=7)
        )
        assert scheduler._should_run_signals() is True

    def test_signal_state_persistence(self, tmp_path):
        """State file is written and read correctly."""
        import scheduler
        state = {"last_collection": "2025-01-01T00:00:00+00:00", "last_results": {}}
        scheduler._save_signal_state(state)
        loaded = scheduler._load_signal_state()
        assert loaded["last_collection"] == "2025-01-01T00:00:00+00:00"

    @patch("signal_bridge.generate_signal_questions")
    @patch("signal_collector.enrich_top_posts")
    @patch("opportunity_scorer.score_unanalyzed")
    @patch("signal_collector.collect_signals")
    def test_run_signal_cycle_full(self, mock_collect, mock_score, mock_enrich, mock_bridge):
        """Full signal cycle runs collect + score + enrich + bridge."""
        import scheduler
        scheduler._last_signal_collection = None
        # Reset state file so _should_run_signals returns True
        scheduler._save_signal_state({})

        mock_collect.return_value = {
            "total_new": 15, "total_found": 50, "total_matched": 30,
        }
        mock_score.return_value = {"analyzed": 10, "top_score": 85}
        mock_enrich.return_value = {"enriched": 7, "failed": 1, "skipped": 2}
        mock_bridge.return_value = [{"question": "q1"}, {"question": "q2"}]

        result = scheduler._run_signal_cycle()
        assert result is not None
        assert result["collected"] == 15
        assert result["scored"] == 10
        assert result["top_score"] == 85
        assert result["enriched"] == 7
        assert result["questions_queued"] == 2
        mock_collect.assert_called_once()
        mock_score.assert_called_once()
        mock_enrich.assert_called_once_with(limit=20)
        mock_bridge.assert_called_once()

    def test_run_signal_cycle_skips_within_interval(self):
        """Signal cycle returns None if interval not elapsed."""
        import scheduler
        scheduler._last_signal_collection = datetime.now(timezone.utc)
        result = scheduler._run_signal_cycle()
        assert result is None

    @patch("signal_collector.collect_signals", side_effect=Exception("network error"))
    def test_run_signal_cycle_handles_collection_error(self, mock_collect):
        """If collection fails, returns partial results (not crash)."""
        import scheduler
        scheduler._last_signal_collection = None
        scheduler._save_signal_state({})
        result = scheduler._run_signal_cycle()
        assert result is not None
        assert result["collected"] == 0

    @patch("signal_bridge.generate_signal_questions")
    @patch("signal_collector.enrich_top_posts", side_effect=Exception("scrapling unavailable"))
    @patch("opportunity_scorer.score_unanalyzed")
    @patch("signal_collector.collect_signals")
    def test_run_signal_cycle_enrichment_failure_is_nonfatal(
        self, mock_collect, mock_score, mock_enrich, mock_bridge
    ):
        """Enrichment failure does not abort the cycle — bridge still runs."""
        import scheduler
        scheduler._last_signal_collection = None
        scheduler._save_signal_state({})

        mock_collect.return_value = {"total_new": 5, "total_found": 10, "total_matched": 5}
        mock_score.return_value = {"analyzed": 3, "top_score": 72}
        mock_bridge.return_value = [{"question": "q1"}]

        result = scheduler._run_signal_cycle()
        assert result is not None
        assert result["collected"] == 5
        assert result["scored"] == 3
        # enriched defaults to 0 when enrichment fails
        assert result.get("enriched", 0) == 0
        # Bridge still ran despite enrichment failure
        assert result["questions_queued"] == 1
        mock_bridge.assert_called_once()


# ============================================================
# Build Spec Pipeline Tests (Obj 5)
# ============================================================

class TestBuildSpecPipeline:
    """Test auto build-spec generation from signal opportunities."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield db_path
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    @pytest.fixture(autouse=True)
    def tmp_logs(self, tmp_path):
        import scheduler
        self._orig_log_dir = scheduler.LOG_DIR
        scheduler.LOG_DIR = str(tmp_path / "logs")
        os.makedirs(str(tmp_path / "logs"), exist_ok=True)
        yield
        scheduler.LOG_DIR = self._orig_log_dir

    @patch("opportunity_scorer.generate_build_spec")
    def test_generates_specs_for_high_score(self, mock_gen):
        """Generate build specs for opportunities >= 70."""
        from signal_collector import init_signals_db, insert_post, insert_analysis
        init_signals_db()
        insert_post({"reddit_id": "t3_spec1", "subreddit": "SaaS", "title": "Need X"})
        insert_analysis(1, {"pain_point_summary": "X is broken", "opportunity_score": 85})
        mock_gen.return_value = {"product_name": "FixX", "core_features": []}

        from scheduler import _generate_signal_build_specs
        result = _generate_signal_build_specs({"top_score": 85})
        assert result["generated"] == 1
        mock_gen.assert_called_once()

    def test_skips_low_score_opportunities(self):
        """Opportunities under 70 are skipped."""
        from signal_collector import init_signals_db, insert_post, insert_analysis
        init_signals_db()
        insert_post({"reddit_id": "t3_low", "subreddit": "SaaS", "title": "Meh"})
        insert_analysis(1, {"pain_point_summary": "minor", "opportunity_score": 40})

        from scheduler import _generate_signal_build_specs
        result = _generate_signal_build_specs({"top_score": 40})
        assert result["generated"] == 0

    @patch("opportunity_scorer.generate_build_spec")
    def test_skips_existing_specs(self, mock_gen, tmp_path):
        """Don't regenerate specs for the same post."""
        import scheduler
        from signal_collector import init_signals_db, insert_post, insert_analysis
        init_signals_db()
        insert_post({"reddit_id": "t3_dup", "subreddit": "SaaS", "title": "Dup"})
        insert_analysis(1, {"pain_point_summary": "dup", "opportunity_score": 90})

        # Create existing spec file that has post_id "1" in the name
        specs_dir = os.path.join(scheduler.LOG_DIR, "build_specs")
        os.makedirs(specs_dir, exist_ok=True)
        with open(os.path.join(specs_dir, "2025_1_dup_product.json"), "w") as f:
            f.write("{}")

        result = scheduler._generate_signal_build_specs({"top_score": 90})
        assert result["skipped"] == 1
        assert result["generated"] == 0
        mock_gen.assert_not_called()

    @patch("sync.create_task")
    @patch("opportunity_scorer.generate_build_spec")
    def test_creates_sync_task_on_spec(self, mock_gen, mock_task):
        """Build spec generation creates a sync task for Hands."""
        from signal_collector import init_signals_db, insert_post, insert_analysis
        init_signals_db()
        insert_post({"reddit_id": "t3_task1", "subreddit": "SaaS", "title": "Need Y"})
        insert_analysis(1, {"pain_point_summary": "Y hurts", "opportunity_score": 80})
        mock_gen.return_value = {
            "product_name": "FixY",
            "problem_statement": "Y is hard",
            "target_audience": "devs",
            "core_features": ["auto-fix", "dashboard"],
            "tech_stack": {"frontend": "Next.js"},
            "mvp_scope": "Landing + core feature",
        }

        from scheduler import _generate_signal_build_specs
        result = _generate_signal_build_specs({"top_score": 80})
        assert result["generated"] == 1
        mock_task.assert_called_once()
        call_kwargs = mock_task.call_args[1]
        assert "FixY" in call_kwargs["title"]
        assert call_kwargs["task_type"] == "build"
        assert call_kwargs["priority"] == "high"
        assert call_kwargs["metadata"]["signal_score"] == 80


# ============================================================
# Engagement Feedback Loop Tests (Obj 7)
# ============================================================

class TestEngagementFeedback:
    """Test engagement re-checking and feedback loop."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield db_path
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    def test_no_posts_returns_empty(self):
        """No enriched posts returns empty list."""
        from signal_collector import check_engagement_changes, init_signals_db
        init_signals_db()
        result = check_engagement_changes()
        assert result == []

    def test_skips_unenriched_posts(self):
        """Posts with score=0 and comments=0 are not checked."""
        from signal_collector import (
            check_engagement_changes, init_signals_db,
            insert_post, insert_analysis,
        )
        init_signals_db()
        insert_post({"reddit_id": "t3_no_eng", "subreddit": "SaaS", "title": "Test"})
        insert_analysis(1, {"pain_point_summary": "test", "opportunity_score": 80})
        # Post has score=0, num_comments=0 by default — should be skipped
        result = check_engagement_changes()
        assert result == []

    @patch("signal_collector.enrich_post")
    def test_detects_growing_engagement(self, mock_enrich):
        """Detects when upvotes/comments increase."""
        from signal_collector import (
            check_engagement_changes, init_signals_db,
            insert_post, insert_analysis, update_post_engagement,
        )
        init_signals_db()
        insert_post({"reddit_id": "t3_grow", "subreddit": "SaaS",
                      "title": "Growing", "url": "https://old.reddit.com/r/SaaS/t3_grow"})
        insert_analysis(1, {"pain_point_summary": "growing pain", "opportunity_score": 85})
        update_post_engagement(1, 10, 5)  # Initial enrichment

        mock_enrich.return_value = {"score": 25, "num_comments": 12}

        result = check_engagement_changes(min_score=60)
        assert len(result) == 1
        assert result[0]["growing"] is True
        assert result[0]["score_delta"] == 15
        assert result[0]["comment_delta"] == 7

    @patch("signal_collector.enrich_post")
    def test_detects_stable_engagement(self, mock_enrich):
        """Detects when engagement is unchanged."""
        from signal_collector import (
            check_engagement_changes, init_signals_db,
            insert_post, insert_analysis, update_post_engagement,
        )
        init_signals_db()
        insert_post({"reddit_id": "t3_stable", "subreddit": "SaaS",
                      "title": "Stable", "url": "https://old.reddit.com/r/SaaS/t3_stable"})
        insert_analysis(1, {"pain_point_summary": "stable", "opportunity_score": 75})
        update_post_engagement(1, 10, 5)

        mock_enrich.return_value = {"score": 10, "num_comments": 5}

        result = check_engagement_changes(min_score=60)
        assert len(result) == 1
        assert result[0]["growing"] is False

    def test_engagement_cli_no_data(self, capsys):
        """CLI engagement check with no data."""
        from cli.signals_cmd import run_engagement_check
        from signal_collector import init_signals_db
        init_signals_db()
        run_engagement_check()
        output = capsys.readouterr().out
        assert "No posts" in output


# ============================================================
# End-to-End Integration Test (Obj 8)
# ============================================================

class TestEndToEndPipeline:
    """Integration test: full signal pipeline from collection to build spec."""

    @pytest.fixture(autouse=True)
    def tmp_db(self, tmp_path):
        db_path = str(tmp_path / "test_signals.db")
        import signal_collector
        signal_collector._db_initialized = False
        self._orig_path = signal_collector.SIGNALS_DB_PATH
        signal_collector.SIGNALS_DB_PATH = db_path
        yield db_path
        signal_collector.SIGNALS_DB_PATH = self._orig_path
        signal_collector._db_initialized = False

    @pytest.fixture(autouse=True)
    def tmp_logs(self, tmp_path):
        import scheduler
        self._orig_signal_state = scheduler.SIGNAL_STATE_FILE
        self._orig_log_dir = scheduler.LOG_DIR
        scheduler.SIGNAL_STATE_FILE = str(tmp_path / "signal_state.json")
        scheduler.LOG_DIR = str(tmp_path / "logs")
        os.makedirs(str(tmp_path / "logs"), exist_ok=True)
        scheduler._last_signal_collection = None
        yield
        scheduler.SIGNAL_STATE_FILE = self._orig_signal_state
        scheduler.LOG_DIR = self._orig_log_dir
        scheduler._last_signal_collection = None

    @patch("sync.create_task")
    @patch("opportunity_scorer.generate_build_spec")
    @patch("signal_bridge.generate_signal_questions")
    @patch("opportunity_scorer.score_unanalyzed")
    @patch("signal_collector.collect_signals")
    def test_full_pipeline(self, mock_collect, mock_score, mock_bridge,
                           mock_build_spec, mock_sync_task):
        """
        Full pipeline:
        1. Signal cycle collects posts
        2. Scoring finds high-value opportunities
        3. Bridge generates research questions
        4. Build spec pipeline generates specs for top opportunities
        5. Sync tasks created for Hands execution
        """
        import scheduler

        # Step 1+2+3: Signal cycle
        mock_collect.return_value = {
            "total_new": 20, "total_found": 100, "total_matched": 40,
        }
        mock_score.return_value = {"analyzed": 15, "top_score": 92}
        mock_bridge.return_value = [
            {"question": "Validate demand for X", "pain_point": "X is broken",
             "opportunity_score": 92, "category": "SaaS"},
        ]

        result = scheduler._run_signal_cycle()
        assert result is not None
        assert result["collected"] == 20
        assert result["scored"] == 15
        assert result["top_score"] == 92
        assert result["questions_queued"] == 1

        # Step 4+5: Build spec pipeline (needs real DB data)
        from signal_collector import init_signals_db, insert_post, insert_analysis
        init_signals_db()
        insert_post({"reddit_id": "t3_e2e", "subreddit": "SaaS", "title": "X is broken"})
        insert_analysis(1, {"pain_point_summary": "X is broken", "opportunity_score": 92})

        mock_build_spec.return_value = {
            "product_name": "FixX Pro",
            "problem_statement": "X breaks constantly",
            "target_audience": "SaaS developers",
            "core_features": ["auto-fix", "monitoring"],
            "tech_stack": {"backend": "FastAPI", "frontend": "Next.js"},
            "mvp_scope": "Core fix + dashboard",
        }

        spec_results = scheduler._generate_signal_build_specs({"top_score": 92})
        assert spec_results["generated"] == 1
        mock_build_spec.assert_called_once()
        mock_sync_task.assert_called_once()

        # Verify sync task has correct structure
        task_kwargs = mock_sync_task.call_args[1]
        assert "FixX Pro" in task_kwargs["title"]
        assert task_kwargs["task_type"] == "build"
        assert task_kwargs["priority"] == "high"
        assert task_kwargs["source_domain"] == "micro-saas"

    def test_config_defaults(self):
        """Signal config values are set."""
        from config import (
            SIGNAL_COLLECTION_INTERVAL_HOURS,
            SIGNAL_SCORING_BATCH,
            SIGNAL_SCORING_MAX_BATCHES,
        )
        assert SIGNAL_COLLECTION_INTERVAL_HOURS == 6
        assert SIGNAL_SCORING_BATCH == 10
        assert SIGNAL_SCORING_MAX_BATCHES == 3

    def test_alert_function_exists(self):
        """Signal alert function is importable."""
        from alerts import alert_signal_collection
        assert callable(alert_signal_collection)
