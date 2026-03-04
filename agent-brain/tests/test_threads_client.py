"""Tests for tools/threads_client.py — Threads API client."""
import json
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestIsConfigured:
    def test_not_configured_when_no_token(self):
        with patch.dict(os.environ, {}, clear=True):
            # Reload module to pick up empty env
            import tools.threads_client as tc
            original_token = tc.THREADS_ACCESS_TOKEN
            original_user = tc.THREADS_USER_ID
            try:
                tc.THREADS_ACCESS_TOKEN = ""
                tc.THREADS_USER_ID = ""
                assert tc.is_configured() is False
            finally:
                tc.THREADS_ACCESS_TOKEN = original_token
                tc.THREADS_USER_ID = original_user

    def test_configured_when_both_set(self):
        import tools.threads_client as tc
        original_token = tc.THREADS_ACCESS_TOKEN
        original_user = tc.THREADS_USER_ID
        try:
            tc.THREADS_ACCESS_TOKEN = "test-token"
            tc.THREADS_USER_ID = "12345"
            assert tc.is_configured() is True
        finally:
            tc.THREADS_ACCESS_TOKEN = original_token
            tc.THREADS_USER_ID = original_user


class TestRateLimit:
    def test_rate_check_allows_under_limit(self):
        from tools.threads_client import _rate_check, _call_timestamps
        _call_timestamps.clear()
        assert _rate_check() is True

    def test_rate_check_blocks_at_limit(self):
        from tools.threads_client import _rate_check, _call_timestamps, MAX_CALLS_PER_HOUR
        _call_timestamps.clear()
        now = time.time()
        # Fill up to the limit
        _call_timestamps.extend([now - 10] * MAX_CALLS_PER_HOUR)
        assert _rate_check() is False
        _call_timestamps.clear()

    def test_rate_check_prunes_old_timestamps(self):
        from tools.threads_client import _rate_check, _call_timestamps
        _call_timestamps.clear()
        old = time.time() - 7200  # 2 hours ago
        _call_timestamps.extend([old] * 100)
        assert _rate_check() is True  # Old timestamps pruned
        _call_timestamps.clear()


class TestPublishPost:
    @patch("tools.threads_client._api_request")
    @patch("tools.threads_client.is_configured", return_value=True)
    def test_publish_success(self, mock_conf, mock_api):
        from tools.threads_client import publish_post, _call_timestamps
        _call_timestamps.clear()
        
        import tools.threads_client as tc
        tc._last_publish_time = 0.0
        tc.THREADS_ACCESS_TOKEN = "token"
        tc.THREADS_USER_ID = "user123"
        
        # Step 1: create container, Step 2: publish
        mock_api.side_effect = [
            {"id": "container_123"},  # create container
            {"id": "thread_456"},     # publish
        ]
        
        with patch("time.sleep"):  # skip container processing wait
            result = publish_post("Hello Threads!")
        
        assert result["published"] is True
        assert result["id"] == "thread_456"
        assert mock_api.call_count == 2

    def test_text_too_long(self):
        from tools.threads_client import publish_post, ThreadsAPIError
        import tools.threads_client as tc
        tc.THREADS_ACCESS_TOKEN = "token"
        tc.THREADS_USER_ID = "user123"
        tc._last_publish_time = 0.0
        
        with pytest.raises(ThreadsAPIError, match="too long"):
            publish_post("x" * 501)

    def test_cooldown_enforced(self):
        from tools.threads_client import publish_post, ThreadsAPIError
        import tools.threads_client as tc
        tc.THREADS_ACCESS_TOKEN = "token"
        tc.THREADS_USER_ID = "user123"
        tc._last_publish_time = time.time()  # Just published
        
        with pytest.raises(ThreadsAPIError, match="cooldown"):
            publish_post("Hello again!")


class TestSearchThreads:
    @patch("tools.threads_client._api_request")
    def test_search_returns_posts(self, mock_api):
        from tools.threads_client import search_threads, _call_timestamps
        _call_timestamps.clear()
        
        import tools.threads_client as tc
        tc.THREADS_ACCESS_TOKEN = "token"
        tc.THREADS_USER_ID = "user123"
        
        mock_api.return_value = {
            "data": [
                {"id": "1", "text": "Frustrated with invoicing", "username": "user1"},
                {"id": "2", "text": "Need better tools", "username": "user2"},
            ]
        }
        
        results = search_threads("freelance invoicing", limit=10)
        assert len(results) == 2
        assert results[0]["text"] == "Frustrated with invoicing"

    @patch("tools.threads_client._api_request")
    def test_search_empty_results(self, mock_api):
        from tools.threads_client import search_threads, _call_timestamps
        _call_timestamps.clear()
        
        import tools.threads_client as tc
        tc.THREADS_ACCESS_TOKEN = "token"
        tc.THREADS_USER_ID = "user123"
        
        mock_api.return_value = {"data": []}
        results = search_threads("nonexistent query")
        assert results == []


class TestGetThreadInsights:
    @patch("tools.threads_client._api_request")
    def test_insights_parsing(self, mock_api):
        from tools.threads_client import get_thread_insights, _call_timestamps
        _call_timestamps.clear()
        
        import tools.threads_client as tc
        tc.THREADS_ACCESS_TOKEN = "token"
        tc.THREADS_USER_ID = "user123"
        
        mock_api.return_value = {
            "data": [
                {"name": "views", "values": [{"value": 1500}]},
                {"name": "likes", "values": [{"value": 42}]},
                {"name": "replies", "values": [{"value": 8}]},
            ]
        }
        
        insights = get_thread_insights("thread_123")
        assert insights["views"] == 1500
        assert insights["likes"] == 42
        assert insights["replies"] == 8


class TestGetRecentEngagement:
    @patch("tools.threads_client.get_thread_insights")
    @patch("tools.threads_client.get_user_threads")
    def test_engagement_summary(self, mock_threads, mock_insights):
        from tools.threads_client import get_recent_engagement, _call_timestamps
        _call_timestamps.clear()
        
        mock_threads.return_value = [
            {"id": "t1", "text": "Post 1", "timestamp": "2026-03-01"},
            {"id": "t2", "text": "Post 2", "timestamp": "2026-03-02"},
        ]
        mock_insights.side_effect = [
            {"views": 100, "likes": 10, "replies": 5},
            {"views": 200, "likes": 30, "replies": 10},
        ]
        
        result = get_recent_engagement(limit=2)
        assert result["total_views"] == 300
        assert result["total_likes"] == 40
        assert result["total_replies"] == 15
        assert result["top_post"]["id"] == "t2"  # Higher engagement
        assert result["avg_engagement_rate"] > 0


class TestExecuteThreadsTool:
    @patch("tools.threads_client.search_threads")
    def test_search_tool(self, mock_search):
        from tools.threads_client import execute_threads_tool
        mock_search.return_value = [{"id": "1", "text": "test"}]
        
        result = json.loads(execute_threads_tool("threads_search", {"query": "test"}))
        assert result["count"] == 1

    @patch("tools.threads_client.publish_post")
    def test_post_tool(self, mock_publish):
        from tools.threads_client import execute_threads_tool
        mock_publish.return_value = {"id": "t1", "published": True, "text": "hello"}
        
        result = json.loads(execute_threads_tool("threads_post", {"text": "hello"}))
        assert result["published"] is True

    @patch("tools.threads_client.get_recent_engagement")
    def test_insights_tool(self, mock_eng):
        from tools.threads_client import execute_threads_tool
        mock_eng.return_value = {"total_views": 100}
        
        result = json.loads(execute_threads_tool("threads_insights", {}))
        assert result["total_views"] == 100

    def test_unknown_tool(self):
        from tools.threads_client import execute_threads_tool
        result = json.loads(execute_threads_tool("threads_unknown", {}))
        assert "error" in result

    @patch("tools.threads_client.search_threads")
    def test_tool_error_handling(self, mock_search):
        from tools.threads_client import execute_threads_tool, ThreadsAPIError
        mock_search.side_effect = ThreadsAPIError("Rate limit")
        
        result = json.loads(execute_threads_tool("threads_search", {"query": "test"}))
        assert "error" in result
        assert "Rate limit" in result["error"]


class TestToolDefinitions:
    def test_search_tool_definition_shape(self):
        from tools.threads_client import THREADS_SEARCH_TOOL
        assert THREADS_SEARCH_TOOL["name"] == "threads_search"
        assert "input_schema" in THREADS_SEARCH_TOOL
        assert "query" in THREADS_SEARCH_TOOL["input_schema"]["properties"]

    def test_post_tool_definition_shape(self):
        from tools.threads_client import THREADS_POST_TOOL
        assert THREADS_POST_TOOL["name"] == "threads_post"
        assert "text" in THREADS_POST_TOOL["input_schema"]["properties"]

    def test_insights_tool_definition_shape(self):
        from tools.threads_client import THREADS_INSIGHTS_TOOL
        assert THREADS_INSIGHTS_TOOL["name"] == "threads_insights"
