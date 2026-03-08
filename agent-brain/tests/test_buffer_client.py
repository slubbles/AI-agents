"""Tests for tools/buffer_client.py."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestIsConfigured:
    def test_not_configured_without_key(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.delenv("BUFFER_API_KEY", raising=False)
        monkeypatch.setattr(bc, "_DOTENV_ATTEMPTED", True)
        assert bc.is_configured() is False

    def test_configured_with_key(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setenv("BUFFER_API_KEY", "test-key")
        assert bc.is_configured() is True

    def test_reads_key_after_env_is_set_late(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.delenv("BUFFER_API_KEY", raising=False)
        monkeypatch.setattr(bc, "_DOTENV_ATTEMPTED", True)
        assert bc.is_configured() is False

        monkeypatch.setenv("BUFFER_API_KEY", "late-key")
        assert bc.is_configured() is True


class TestGetXChannels:
    def test_filters_twitter_channels(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(
            bc,
            "list_channels",
            lambda organization_id=None: [
                {"id": "1", "service": "twitter", "name": "x1"},
                {"id": "2", "service": "threads", "name": "t1"},
                {"id": "3", "service": "twitter", "name": "x2"},
            ],
        )

        results = bc.get_x_channels()
        assert [item["id"] for item in results] == ["1", "3"]

    def test_get_recent_x_posts_filters_non_x_channels(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(bc, "get_default_organization", lambda: {"id": "org_1"})
        monkeypatch.setattr(bc, "get_x_channels", lambda organization_id=None: [{"id": "chan_x", "service": "twitter"}])
        monkeypatch.setattr(
            bc,
            "_graphql_request",
            lambda query, variables=None, timeout=30: {
                "posts": {
                    "edges": [
                        {"node": {"id": "p1", "text": "x text", "status": "sent", "channel": {"id": "chan_x", "service": "twitter"}}},
                        {"node": {"id": "p2", "text": "threads text", "status": "sent", "channel": {"id": "chan_t", "service": "threads"}}},
                    ]
                }
            },
        )

        results = bc.get_recent_x_posts(limit=5)
        assert [item["id"] for item in results] == ["p1"]


class TestCreatePost:
    def test_create_post_success(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(
            bc,
            "_graphql_request",
            lambda query, variables=None, timeout=30: {
                "createPost": {
                    "__typename": "PostActionSuccess",
                    "post": {
                        "id": "post_123",
                        "status": "draft",
                        "text": "hello",
                        "createdAt": "2026-03-08T00:00:00Z",
                        "channel": {"id": "chan_1", "name": "acct", "service": "twitter"},
                    },
                }
            },
        )

        result = bc.create_post("chan_1", "hello", save_to_draft=True)
        assert result["ok"] is True
        assert result["post"]["id"] == "post_123"

    def test_create_post_error_union(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(
            bc,
            "_graphql_request",
            lambda query, variables=None, timeout=30: {
                "createPost": {
                    "__typename": "InvalidInputError",
                    "message": "Bad input",
                }
            },
        )

        with pytest.raises(bc.BufferAPIError, match="Bad input"):
            bc.create_post("chan_1", "hello")


class TestCreateXDraftTest:
    def test_uses_first_x_channel(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(
            bc,
            "get_x_channels",
            lambda organization_id=None: [
                {"id": "chan_x", "service": "twitter", "name": "acct", "displayName": "acct"}
            ],
        )

        captured = {}

        def fake_create_post(channel_id, text, **kwargs):
            captured["channel_id"] = channel_id
            captured["text"] = text
            captured.update(kwargs)
            return {
                "ok": True,
                "post": {"id": "post_1", "status": "draft", "text": text},
            }

        monkeypatch.setattr(bc, "create_post", fake_create_post)

        result = bc.create_x_draft_test("test text")
        assert captured["channel_id"] == "chan_x"
        assert captured["save_to_draft"] is True
        assert result["channel"]["id"] == "chan_x"

    def test_no_x_channels_raises(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(bc, "get_x_channels", lambda organization_id=None: [])

        with pytest.raises(bc.BufferAPIError, match="No connected X channels"):
            bc.create_x_draft_test()


class TestSupervisedXFlow:
    def test_create_supervised_draft_persists_pending_state(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(
            bc,
            "get_x_channels",
            lambda organization_id=None: [
                {"id": "chan_x", "service": "twitter", "name": "acct", "displayName": "acct"}
            ],
        )

        captured = {}
        monkeypatch.setattr(bc, "_set_pending_x_supervision", lambda record: captured.update(record=record))
        monkeypatch.setattr(bc, "get_pending_x_queue", lambda: [captured["record"]] if "record" in captured else [])

        result = bc.create_x_supervised_draft("hello world")
        assert result["pending"]["draft_id"].startswith("xdraft_")
        assert result["pending"]["draft_post_id"] is None
        assert result["pending"]["status"] == "pending_confirmation"
        assert captured["record"]["text"] == "hello world"
        assert result["queue_size"] == 1

    def test_confirm_supervised_post_sends_pending_text(self, monkeypatch):
        import tools.buffer_client as bc

        pending_record = {
            "draft_id": "xdraft_1",
            "draft_post_id": None,
            "channel_id": "chan_x",
            "channel_name": "acct",
            "text": "ship this",
        }
        monkeypatch.setattr(
            bc,
            "get_pending_x_queue",
            lambda: [pending_record],
        )

        sent = {}

        def fake_create_post(channel_id, text="", **kwargs):
            sent["channel_id"] = channel_id
            sent["text"] = text
            sent.update(kwargs)
            return {
                "ok": True,
                "post": {"id": "sent_1", "status": "sent", "text": text},
            }

        monkeypatch.setattr(bc, "create_post", fake_create_post)
        removed = {}
        monkeypatch.setattr(
            bc,
            "_remove_pending_x_supervision",
            lambda draft_id=None, last_sent=None: removed.update(draft_id=draft_id, last_sent=last_sent) or pending_record,
        )

        result = bc.confirm_x_supervised_post()
        assert sent["channel_id"] == "chan_x"
        assert sent["text"] == "ship this"
        assert "draft_id" not in sent
        assert sent["mode"] == "shareNow"
        assert result["post"]["id"] == "sent_1"
        assert removed["draft_id"] == "xdraft_1"
        assert removed["last_sent"]["source_draft_id"] == "xdraft_1"

    def test_confirm_supervised_post_requires_pending_draft(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(bc, "get_pending_x_queue", lambda: [])
        with pytest.raises(bc.BufferAPIError, match="No pending supervised X draft"):
            bc.confirm_x_supervised_post()

    def test_cancel_supervised_post_clears_pending_state(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(bc, "get_pending_x_queue", lambda: [{"draft_id": "xdraft_1"}])
        removed = {}
        monkeypatch.setattr(
            bc,
            "_remove_pending_x_supervision",
            lambda draft_id=None, last_sent=None: removed.update(draft_id=draft_id) or {"draft_id": "xdraft_1"},
        )

        result = bc.cancel_x_supervised_post()
        assert result["cleared"] is True
        assert removed["draft_id"] is None

    def test_queue_limit_blocks_new_drafts(self, monkeypatch):
        import tools.buffer_client as bc

        monkeypatch.setattr(bc, "get_pending_x_queue", lambda: [{} for _ in range(bc.MAX_PENDING_X_DRAFTS)])

        with pytest.raises(bc.BufferAPIError, match="queue is full"):
            bc._set_pending_x_supervision({"draft_id": "xdraft_overflow"})

    def test_confirm_can_target_specific_draft_id(self, monkeypatch):
        import tools.buffer_client as bc

        queue = [
            {"draft_id": "xdraft_1", "channel_id": "chan_x", "channel_name": "acct", "text": "first", "draft_post_id": None},
            {"draft_id": "xdraft_2", "channel_id": "chan_x", "channel_name": "acct", "text": "second", "draft_post_id": None},
        ]
        monkeypatch.setattr(bc, "get_pending_x_queue", lambda: queue)
        sent = {}

        def fake_create_post(channel_id, text="", **kwargs):
            sent["text"] = text
            return {"ok": True, "post": {"id": "sent_2", "status": "sent", "text": text}}

        monkeypatch.setattr(bc, "create_post", fake_create_post)
        monkeypatch.setattr(bc, "_remove_pending_x_supervision", lambda draft_id=None, last_sent=None: {"draft_id": draft_id})

        result = bc.confirm_x_supervised_post("xdraft_2")
        assert sent["text"] == "second"
        assert result["confirmed_from"]["draft_id"] == "xdraft_2"