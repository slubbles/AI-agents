"""Tests for tools/discord_client.py."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDiscordConfiguration:
    def test_is_configured_false_without_token(self, monkeypatch):
        import tools.discord_client as dc

        monkeypatch.setattr(dc, "DISCORD_BOT_TOKEN", "")
        monkeypatch.setattr(
            dc,
            "get_configured_channels",
            lambda: {"research": "1", "scripts": "2", "thumbnails": "3"},
        )
        assert dc.is_configured() is False

    def test_is_configured_true_with_token_and_channels(self, monkeypatch):
        import tools.discord_client as dc

        monkeypatch.setattr(dc, "DISCORD_BOT_TOKEN", "token")
        monkeypatch.setattr(
            dc,
            "get_configured_channels",
            lambda: {"research": "1", "scripts": "2", "thumbnails": "3"},
        )
        assert dc.is_configured() is True


class TestDiscordMessaging:
    def test_get_channel_messages_uses_api(self, monkeypatch):
        import tools.discord_client as dc

        captured = {}

        def fake_request(endpoint, method="GET", payload=None, timeout=30):
            captured["endpoint"] = endpoint
            return [{"id": "m1", "content": "hello"}]

        monkeypatch.setattr(dc, "_discord_request", fake_request)

        result = dc.get_channel_messages("123", limit=15)
        assert result[0]["id"] == "m1"
        assert "/channels/123/messages?limit=15" in captured["endpoint"]

    def test_send_message_splits_long_content(self, monkeypatch):
        import tools.discord_client as dc

        calls = []

        def fake_request(endpoint, method="GET", payload=None, timeout=30):
            calls.append({"endpoint": endpoint, "payload": payload})
            return {"id": str(len(calls))}

        monkeypatch.setattr(dc, "_discord_request", fake_request)

        content = "A" * (dc.DISCORD_MAX_MESSAGE_LEN + 25)
        result = dc.send_message("456", content)

        assert len(result) == 2
        assert len(calls) == 2
        assert calls[0]["endpoint"] == "/channels/456/messages"
        assert calls[0]["payload"]["allowed_mentions"] == {"parse": []}

    def test_request_raises_without_token(self, monkeypatch):
        import tools.discord_client as dc

        monkeypatch.setattr(dc, "DISCORD_BOT_TOKEN", "")
        with pytest.raises(dc.DiscordAPIError, match="bot token"):
            dc._discord_request("/channels/1")
