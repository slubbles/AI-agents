"""Tests for telegram_bot.py — Telegram chat interface."""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Conversation Manager Tests ─────────────────────────────────────────

class TestConversationManager:
    def setup_method(self):
        from telegram_bot import ConversationManager
        self.cm = ConversationManager()
    
    def test_add_and_get_messages(self):
        self.cm.add_message("123", "user", "hello")
        self.cm.add_message("123", "assistant", "hi")
        msgs = self.cm.get_messages("123")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
    
    def test_separate_chats(self):
        self.cm.add_message("123", "user", "hello")
        self.cm.add_message("456", "user", "world")
        assert len(self.cm.get_messages("123")) == 1
        assert len(self.cm.get_messages("456")) == 1
    
    def test_clear(self):
        self.cm.add_message("123", "user", "hello")
        self.cm.clear("123")
        assert len(self.cm.get_messages("123")) == 0
    
    def test_max_history_30(self):
        for i in range(35):
            self.cm.add_message("123", "user", f"msg-{i}")
        msgs = self.cm.get_messages("123")
        assert len(msgs) == 30
        # Should keep the latest 30
        assert msgs[0]["content"] == "msg-5"
    
    def test_domain_default(self):
        from config import DEFAULT_DOMAIN
        assert self.cm.get_domain("999") == DEFAULT_DOMAIN
    
    def test_set_domain(self):
        self.cm.set_domain("123", "ai")
        assert self.cm.get_domain("123") == "ai"
    
    def test_empty_chat_returns_empty_list(self):
        assert self.cm.get_messages("nonexistent") == []


# ── Markdown → HTML Conversion ─────────────────────────────────────────

class TestMarkdownToTelegram:
    def setup_method(self):
        from telegram_bot import _markdown_to_telegram
        self.convert = _markdown_to_telegram
    
    def test_bold(self):
        assert "<b>text</b>" in self.convert("**text**")
    
    def test_italic(self):
        assert "<i>text</i>" in self.convert("*text*")
    
    def test_inline_code(self):
        assert "<code>x</code>" in self.convert("`x`")
    
    def test_code_block(self):
        result = self.convert("```python\nprint(1)\n```")
        assert "<pre>" in result
        assert "print(1)" in result
    
    def test_headers(self):
        assert "<b>Title</b>" in self.convert("### Title")
        assert "<b>Title</b>" in self.convert("# Title")
    
    def test_plain_text_unchanged(self):
        assert self.convert("hello world") == "hello world"


# ── HTML Escape ────────────────────────────────────────────────────────

class TestHtmlEscape:
    def test_ampersand(self):
        from telegram_bot import _html_escape
        assert _html_escape("a & b") == "a &amp; b"
    
    def test_angle_brackets(self):
        from telegram_bot import _html_escape
        assert _html_escape("<b>") == "&lt;b&gt;"


# ── Command Handler ───────────────────────────────────────────────────

class TestHandleCommand:
    def test_start(self):
        from telegram_bot import _handle_command
        resp = _handle_command("123", "/start")
        assert "Cortex AI System" in resp
        assert "/status" in resp
    
    def test_help_same_as_start(self):
        from telegram_bot import _handle_command
        start = _handle_command("123", "/start")
        help_resp = _handle_command("123", "/help")
        assert start == help_resp
    
    def test_clear(self):
        from telegram_bot import _handle_command, _conversations
        _conversations.add_message("123", "user", "hello")
        resp = _handle_command("123", "/clear")
        assert "cleared" in resp.lower()
        assert len(_conversations.get_messages("123")) == 0
    
    def test_domain_show(self):
        from telegram_bot import _handle_command
        resp = _handle_command("123", "/domain")
        assert "Active domain" in resp
    
    def test_domain_set(self):
        from telegram_bot import _handle_command, _conversations
        resp = _handle_command("123", "/domain cybersecurity")
        assert "cybersecurity" in resp
        assert _conversations.get_domain("123") == "cybersecurity"
    
    def test_status(self):
        from telegram_bot import _handle_command
        resp = _handle_command("123", "/status")
        assert "System Status" in resp
        assert "Daily spend" in resp
    
    def test_unknown_command_returns_none(self):
        from telegram_bot import _handle_command
        assert _handle_command("123", "/nonexistent") is None
    
    def test_domains_returns_none(self):
        """'/domains' routes through LLM, so returns None."""
        from telegram_bot import _handle_command
        assert _handle_command("123", "/domains") is None


# ── Message Sending ───────────────────────────────────────────────────

class TestSendMessage:
    @patch("telegram_bot._tg_request")
    def test_send_short_message(self, mock_req):
        from telegram_bot import _send_message
        _send_message(123, "hello")
        mock_req.assert_called_once()
        payload = mock_req.call_args[0][1]
        assert payload["text"] == "hello"
        assert payload["chat_id"] == 123
    
    @patch("telegram_bot._tg_request")
    def test_split_long_message(self, mock_req):
        from telegram_bot import _send_message
        long_text = "x" * 5000
        _send_message(123, long_text)
        assert mock_req.call_count == 2  # Split into 2 chunks
    
    @patch("telegram_bot._tg_request")
    def test_empty_becomes_placeholder(self, mock_req):
        from telegram_bot import _send_message
        _send_message(123, "")
        payload = mock_req.call_args[0][1]
        assert payload["text"] == "(empty response)"
    
    @patch("telegram_bot._tg_request", side_effect=Exception("fail"))
    def test_send_failure_returns_false(self, mock_req):
        from telegram_bot import _send_message
        result = _send_message(123, "hello")
        assert result is False


# ── Typing Indicator ──────────────────────────────────────────────────

class TestSendTyping:
    @patch("telegram_bot._tg_request")
    def test_typing_sends_action(self, mock_req):
        from telegram_bot import _send_typing
        _send_typing(123)
        mock_req.assert_called_once_with("sendChatAction", {
            "chat_id": 123,
            "action": "typing",
        }, timeout=5)
    
    @patch("telegram_bot._tg_request", side_effect=Exception("net err"))
    def test_typing_swallows_errors(self, mock_req):
        from telegram_bot import _send_typing
        # Should not raise
        _send_typing(123)


# ── Process Message Pipeline ──────────────────────────────────────────

class TestProcessMessage:
    @patch("telegram_bot.log_cost")
    @patch("telegram_bot.call_llm")
    def test_basic_response(self, mock_llm, mock_cost):
        """Test that a simple text response flows through correctly."""
        from telegram_bot import _process_message, _conversations
        
        # Mock LLM response (simple text, no tools)
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Hello! I'm Cortex."
        mock_response.content = [mock_text_block]
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_llm.return_value = mock_response
        
        _conversations.clear("99999")
        result = _process_message("99999", "hi")
        
        assert "Hello! I'm Cortex." in result
        assert "tokens" in result  # Cost footer
        mock_llm.assert_called_once()
    
    @patch("telegram_bot._send_typing")
    @patch("telegram_bot.log_cost")
    @patch("telegram_bot.call_llm")
    def test_tool_use_loop(self, mock_llm, mock_cost, mock_typing):
        """Test that tool use triggers a second LLM call."""
        from telegram_bot import _process_message, _conversations
        
        # First call: tool use
        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_1"
        tool_block.name = "show_budget"
        tool_block.input = {}
        tool_response.content = [tool_block]
        tool_response.usage = MagicMock()
        tool_response.usage.input_tokens = 100
        tool_response.usage.output_tokens = 50
        
        # Second call: final text
        text_response = MagicMock()
        text_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Budget looks good!"
        text_response.content = [text_block]
        text_response.usage = MagicMock()
        text_response.usage.input_tokens = 200
        text_response.usage.output_tokens = 30
        
        mock_llm.side_effect = [tool_response, text_response]
        
        _conversations.clear("88888")
        result = _process_message("88888", "show me budget")
        
        assert "Budget looks good!" in result
        assert mock_llm.call_count == 2


# ── Security ──────────────────────────────────────────────────────────

class TestSecurity:
    def test_no_token_exits(self):
        """Bot should not start without TELEGRAM_BOT_TOKEN."""
        import telegram_bot
        original = telegram_bot.TELEGRAM_BOT_TOKEN
        try:
            telegram_bot.TELEGRAM_BOT_TOKEN = ""
            # run_telegram_bot should return early
            telegram_bot.run_telegram_bot()
        finally:
            telegram_bot.TELEGRAM_BOT_TOKEN = original


# ── Module-level Checks ──────────────────────────────────────────────

class TestModuleStructure:
    def test_imports(self):
        import telegram_bot
        assert hasattr(telegram_bot, "run_telegram_bot")
        assert hasattr(telegram_bot, "_process_message")
        assert hasattr(telegram_bot, "_handle_command")
        assert hasattr(telegram_bot, "_send_message")
        assert hasattr(telegram_bot, "ConversationManager")
    
    def test_max_msg_len(self):
        from telegram_bot import MAX_MSG_LEN
        assert MAX_MSG_LEN == 4096
