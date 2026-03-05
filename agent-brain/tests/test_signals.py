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
