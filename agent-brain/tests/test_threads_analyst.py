"""Tests for agents/threads_analyst.py — Threads content analysis agent."""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


SAMPLE_POSTS = [
    {"id": "1", "text": "Spending 3 hours every week on invoicing is killing me", "username": "freelancer1", "timestamp": "2026-03-01"},
    {"id": "2", "text": "Why is it so hard to get clients to pay on time?", "username": "designer2", "timestamp": "2026-03-01"},
    {"id": "3", "text": "Just lost $2000 because I forgot to send an invoice", "username": "dev3", "timestamp": "2026-02-28"},
    {"id": "4", "text": "Tried every invoicing tool. They're all too complicated", "username": "writer4", "timestamp": "2026-02-27"},
    {"id": "5", "text": "Anyone found a simple invoicing solution that just works?", "username": "creative5", "timestamp": "2026-02-26"},
]

SAMPLE_POSTS_WITH_ENGAGEMENT = [
    {"id": "1", "text": "The one thing that changed my freelance business...", "username": "user1", "timestamp": "2026-03-01", "views": 5000, "likes": 150, "replies": 45},
    {"id": "2", "text": "Stop saying 'just raise your rates.' Here's why.", "username": "user2", "timestamp": "2026-03-02", "views": 8000, "likes": 300, "replies": 80},
]


class TestAnalyzePainPoints:
    @patch("agents.threads_analyst.call_llm")
    def test_returns_structured_pain_points(self, mock_llm):
        from agents.threads_analyst import analyze_pain_points
        
        mock_llm.return_value = {
            "text": json.dumps({
                "pain_points": [
                    {
                        "pain": "Time spent on manual invoicing",
                        "user_language": "Spending 3 hours every week on invoicing",
                        "frequency": 3,
                        "specificity": 8.0,
                        "buildability": 9.0,
                        "evidence": ["Spending 3 hours every week", "forgot to send an invoice"],
                        "score": 8.3,
                    }
                ],
                "user_language_patterns": ["killing me", "too complicated", "just works"],
                "market_signals": ["Users frustrated with existing tools"],
                "content_opportunities": ["Post about simple invoicing"],
                "summary": "Freelancers struggle with time-consuming invoicing.",
            })
        }
        
        result = analyze_pain_points("invoicing", "freelance invoicing", SAMPLE_POSTS)
        
        assert len(result["pain_points"]) == 1
        assert result["pain_points"][0]["score"] == 8.3
        assert "killing me" in result["user_language_patterns"]
        assert len(result["market_signals"]) > 0
        mock_llm.assert_called_once()

    @patch("agents.threads_analyst.call_llm")
    def test_with_goal_context(self, mock_llm):
        from agents.threads_analyst import analyze_pain_points
        
        mock_llm.return_value = {"text": json.dumps({
            "pain_points": [],
            "user_language_patterns": [],
            "market_signals": [],
            "content_opportunities": [],
            "summary": "Goal-filtered analysis",
        })}
        
        result = analyze_pain_points(
            "invoicing", "invoicing tools", SAMPLE_POSTS,
            goal="Build a simple invoicing SaaS"
        )
        
        # Verify goal was included in the prompt
        call_args = mock_llm.call_args
        system_prompt = call_args[1]["system"] if "system" in call_args[1] else call_args[0][0]
        assert "Build a simple invoicing SaaS" in system_prompt

    def test_empty_posts_returns_empty(self):
        from agents.threads_analyst import analyze_pain_points
        
        result = analyze_pain_points("test", "query", [])
        assert result["pain_points"] == []
        assert "No Threads data" in result["summary"]

    @patch("agents.threads_analyst.call_llm")
    def test_llm_failure_returns_error(self, mock_llm):
        from agents.threads_analyst import analyze_pain_points
        
        mock_llm.side_effect = Exception("API error")
        
        result = analyze_pain_points("test", "query", SAMPLE_POSTS)
        assert "error" in result["summary"].lower() or "Error" in result["summary"]
        assert result["pain_points"] == []


class TestAnalyzeContentStrategy:
    @patch("agents.threads_analyst.call_llm")
    def test_returns_strategy(self, mock_llm):
        from agents.threads_analyst import analyze_content_strategy
        
        mock_llm.return_value = {
            "text": json.dumps({
                "patterns": {
                    "avg_length": 180,
                    "tone": "conversational, authentic",
                    "hooks": ["The one thing...", "Stop saying..."],
                    "cta_styles": ["subtle question"],
                    "posting_times": ["morning"],
                },
                "top_formats": ["personal story + insight", "contrarian take"],
                "draft_posts": [
                    {
                        "text": "Here's what nobody tells you about freelancing...",
                        "rationale": "Hook + insight format",
                        "target_engagement": "replies",
                    }
                ],
                "recommendations": ["Post contrarian takes for max engagement"],
            })
        }
        
        result = analyze_content_strategy("freelancing", SAMPLE_POSTS_WITH_ENGAGEMENT)
        
        assert result["patterns"]["avg_length"] == 180
        assert len(result["draft_posts"]) == 1
        assert len(result["top_formats"]) == 2

    def test_empty_posts_returns_defaults(self):
        from agents.threads_analyst import analyze_content_strategy
        
        result = analyze_content_strategy("test", [])
        assert result["patterns"]["avg_length"] == 0
        assert "No data available" in result["recommendations"][0]


class TestGeneratePost:
    @patch("agents.threads_analyst.call_llm")
    def test_generates_post(self, mock_llm):
        from agents.threads_analyst import generate_post
        
        mock_llm.return_value = {
            "text": json.dumps({
                "text": "Just built something for freelancers who hate invoicing. What's the one thing you'd want to fix about getting paid?",
                "hashtags": ["freelancing", "invoicing"],
                "hook_type": "question",
                "estimated_engagement": "medium",
            })
        }
        
        result = generate_post("invoicing", "launch post for invoicing tool")
        
        assert len(result["text"]) <= 500
        assert result["hook_type"] == "question"
        assert "invoicing" in result["hashtags"]

    @patch("agents.threads_analyst.call_llm")
    def test_enforces_character_limit(self, mock_llm):
        from agents.threads_analyst import generate_post
        
        mock_llm.return_value = {
            "text": json.dumps({
                "text": "x" * 600,  # Too long
                "hashtags": [],
                "hook_type": "story",
                "estimated_engagement": "low",
            })
        }
        
        result = generate_post("test", "test post", max_length=500)
        assert len(result["text"]) <= 500

    @patch("agents.threads_analyst.call_llm")
    def test_with_knowledge_context(self, mock_llm):
        from agents.threads_analyst import generate_post
        
        mock_llm.return_value = {"text": json.dumps({
            "text": "Test post",
            "hashtags": [],
            "hook_type": "insight",
            "estimated_engagement": "high",
        })}
        
        result = generate_post(
            "invoicing",
            "invoicing pain",
            knowledge_context="Users spend 3h/week on invoicing"
        )
        
        # Verify KB context was passed to prompt
        call_args = mock_llm.call_args
        system_prompt = call_args[1]["system"] if "system" in call_args[1] else call_args[0][0]
        assert "3h/week" in system_prompt

    @patch("agents.threads_analyst.call_llm")
    def test_llm_failure_returns_error(self, mock_llm):
        from agents.threads_analyst import generate_post
        mock_llm.side_effect = Exception("API error")
        
        result = generate_post("test", "test")
        assert "error" in result["hook_type"].lower() or "Error" in result["text"]


class TestFormatPosts:
    def test_format_basic_posts(self):
        from agents.threads_analyst import _format_posts
        
        result = _format_posts(SAMPLE_POSTS)
        assert "@freelancer1" in result
        assert "Spending 3 hours" in result
        assert "[1]" in result  # numbered

    def test_format_with_engagement(self):
        from agents.threads_analyst import _format_posts
        
        result = _format_posts(SAMPLE_POSTS_WITH_ENGAGEMENT, include_engagement=True)
        assert "5000 views" in result
        assert "150 likes" in result

    def test_format_empty(self):
        from agents.threads_analyst import _format_posts
        assert _format_posts([]) == "(no posts)"


class TestTelegramThreadsCommands:
    """Test /threads commands in telegram_bot.py."""

    def test_threads_help(self):
        from telegram_bot import _handle_command
        with patch("tools.threads_client.is_configured", return_value=True):
            result = _handle_command("123", "/threads")
        assert result is not None
        assert "search" in result.lower()
        assert "post" in result.lower()

    @patch("tools.threads_client.is_configured", return_value=False)
    def test_threads_not_configured(self, mock_conf):
        from telegram_bot import _handle_command
        result = _handle_command("123", "/threads search test")
        assert "not configured" in result.lower()

    @patch("tools.threads_client.search_threads")
    @patch("tools.threads_client.is_configured", return_value=True)
    def test_threads_search_command(self, mock_conf, mock_search):
        from telegram_bot import _handle_command
        mock_search.return_value = [
            {"id": "1", "text": "Found post", "username": "user1"},
        ]
        result = _handle_command("123", "/threads search invoicing")
        assert "Found post" in result

    @patch("tools.threads_client.publish_post")
    @patch("tools.threads_client.is_configured", return_value=True)
    def test_threads_post_command(self, mock_conf, mock_publish):
        from telegram_bot import _handle_command
        mock_publish.return_value = {"id": "t1", "published": True}
        result = _handle_command("123", "/threads post Hello from Cortex!")
        assert "Posted" in result

    @patch("tools.threads_client.is_configured", return_value=True)
    def test_threads_draft_command(self, mock_conf):
        from telegram_bot import _handle_command
        with patch("agents.threads_analyst.generate_post") as mock_gen, \
             patch("memory_store.load_knowledge_base", return_value=None):
            mock_gen.return_value = {
                "text": "Draft post text here",
                "hashtags": ["test"],
                "hook_type": "question",
                "estimated_engagement": "medium",
            }
            result = _handle_command("123", "/threads draft freelance invoicing")
            assert "Draft" in result
            assert "Draft post text here" in result

    @patch("tools.threads_client.get_recent_engagement")
    @patch("tools.threads_client.is_configured", return_value=True)
    def test_threads_insights_command(self, mock_conf, mock_eng):
        from telegram_bot import _handle_command
        mock_eng.return_value = {
            "posts": [],
            "total_views": 5000,
            "total_likes": 200,
            "total_replies": 50,
            "avg_engagement_rate": 5.0,
            "top_post": None,
        }
        result = _handle_command("123", "/threads insights")
        assert "5,000" in result  # formatted views
        assert "200" in result

    @patch("tools.threads_client.is_configured", return_value=True)
    def test_threads_unknown_subcommand(self, mock_conf):
        from telegram_bot import _handle_command
        result = _handle_command("123", "/threads blah")
        assert "Unknown" in result or "help" in result.lower()

    def test_start_includes_threads_commands(self):
        from telegram_bot import _handle_command
        result = _handle_command("123", "/start")
        assert "/threads" in result
        assert "search" in result.lower()
