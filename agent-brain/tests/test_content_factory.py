"""Tests for content_factory.py."""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_should_run_now_after_hour(monkeypatch):
    import content_factory as cf

    monkeypatch.setattr(cf, "CONTENT_FACTORY_ENABLED", True)
    monkeypatch.setattr(cf, "CONTENT_FACTORY_SCHEDULE_HOUR", 8)
    monkeypatch.setattr(cf, "_load_state", lambda: {})
    monkeypatch.setattr(cf, "_now_local", lambda now=None: datetime(2026, 3, 9, 8, 15, tzinfo=timezone.utc))

    class FakeDiscord:
        @staticmethod
        def is_configured():
            return True

    monkeypatch.setitem(sys.modules, "tools.discord_client", FakeDiscord)

    assert cf.should_run_now() is True


def test_should_not_run_twice_same_day(monkeypatch):
    import content_factory as cf

    monkeypatch.setattr(cf, "CONTENT_FACTORY_ENABLED", True)
    monkeypatch.setattr(cf, "CONTENT_FACTORY_SCHEDULE_HOUR", 8)
    monkeypatch.setattr(cf, "_load_state", lambda: {"last_run_local_date": "2026-03-09"})
    monkeypatch.setattr(cf, "_now_local", lambda now=None: datetime(2026, 3, 9, 9, 0, tzinfo=timezone.utc))

    class FakeDiscord:
        @staticmethod
        def is_configured():
            return True

    monkeypatch.setitem(sys.modules, "tools.discord_client", FakeDiscord)

    assert cf.should_run_now() is False


def test_run_content_factory_success(monkeypatch, tmp_path):
    import content_factory as cf

    state_path = tmp_path / "factory_state.json"
    log_path = tmp_path / "factory_runs.jsonl"

    monkeypatch.setattr(cf, "CONTENT_FACTORY_ENABLED", True)
    monkeypatch.setattr(cf, "CONTENT_FACTORY_STATE_FILE", str(state_path))
    monkeypatch.setattr(cf, "CONTENT_FACTORY_RUN_LOG", str(log_path))
    monkeypatch.setattr(cf, "_now_local", lambda now=None: datetime(2026, 3, 9, 8, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(cf, "_collect_context", lambda: {"top_opportunities": []})
    monkeypatch.setattr(
        cf,
        "generate_content_pack",
        lambda context: {
            "research_brief": {"angle": "Angle", "why_now": "Why now", "evidence": ["One"]},
            "scripts": {"hook": "Hook", "x_post": "X copy", "threads_post": "Threads copy", "notes": ["note"]},
            "thumbnail": {"headline": "Headline", "subline": "Subline", "visual_direction": "Direction", "image_notes": ["Note"]},
            "learning": {"patterns_to_keep": ["plain words"], "patterns_to_avoid": ["hype"]},
        },
    )
    monkeypatch.setattr(cf, "_post_to_discord", lambda pack: {"research": 1, "scripts": 1, "thumbnails": 1})
    monkeypatch.setattr(
        cf,
        "_publish_social_posts",
        lambda pack: {"x": {"status": "skipped"}, "threads": {"status": "skipped"}},
    )

    class FakeDiscord:
        @staticmethod
        def is_configured():
            return True

    monkeypatch.setitem(sys.modules, "tools.discord_client", FakeDiscord)

    result = cf.run_content_factory(force=True)
    assert result["ok"] is True
    assert state_path.exists()

    state = json.loads(state_path.read_text())
    assert state["last_run_local_date"] == "2026-03-09"
    assert state["last_pack_summary"]["angle"] == "Angle"


def test_run_content_factory_if_due_skips(monkeypatch):
    import content_factory as cf

    monkeypatch.setattr(cf, "should_run_now", lambda now=None: False)
    result = cf.run_content_factory_if_due()
    assert result["skipped"] is True
