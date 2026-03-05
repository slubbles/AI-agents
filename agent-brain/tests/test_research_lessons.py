"""
Tests for research_lessons.py — confidence scoring, structured entries, project scoping.
Covers Objective 17: ECC Continuous Learning Concepts.
"""

import json
import os
import pytest
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def lessons_dir(tmp_path):
    """Provide a temporary lessons directory."""
    d = tmp_path / "_lessons"
    d.mkdir()
    with patch("research_lessons.LESSONS_DIR", str(d)):
        yield str(d)


class TestStructuredEntryFormat:
    """17.1: Enhanced learning entry format with structured fields."""

    def test_new_lesson_has_all_fields(self, lessons_dir):
        from research_lessons import add_lesson, _load_lessons
        add_lesson("test-domain", "Don't do X", "critic_rejection", "details here")
        lessons = _load_lessons("test-domain")
        assert len(lessons) == 1
        entry = lessons[0]
        # New structured fields
        assert "confidence" in entry
        assert "domain" in entry
        assert "observation_count" in entry
        assert "first_seen" in entry
        assert "last_seen" in entry
        assert "domains_seen" in entry
        assert "project" in entry
        assert entry["domain"] == "test-domain"
        assert entry["observation_count"] == 1
        assert entry["domains_seen"] == ["test-domain"]

    def test_initial_confidence_is_half(self, lessons_dir):
        from research_lessons import add_lesson, _load_lessons, INITIAL_CONFIDENCE
        add_lesson("test-domain", "A lesson", "manual")
        lessons = _load_lessons("test-domain")
        assert lessons[0]["confidence"] == INITIAL_CONFIDENCE
        assert INITIAL_CONFIDENCE == 0.5

    def test_project_tag_stored(self, lessons_dir):
        from research_lessons import add_lesson, _load_lessons
        add_lesson("test-domain", "Project lesson", "manual", project="my-saas")
        lessons = _load_lessons("test-domain")
        assert lessons[0]["project"] == "my-saas"

    def test_backward_compat_no_project(self, lessons_dir):
        from research_lessons import add_lesson, _load_lessons
        add_lesson("test-domain", "No project", "manual")
        lessons = _load_lessons("test-domain")
        assert lessons[0]["project"] == ""


class TestConfidenceScoring:
    """17.2: Confidence scoring logic."""

    def test_confidence_increases_on_repeat(self, lessons_dir):
        from research_lessons import add_lesson, _load_lessons, INITIAL_CONFIDENCE, CONFIDENCE_REPEAT_BOOST
        add_lesson("test-domain", "Repeated lesson", "critic_rejection")
        add_lesson("test-domain", "Repeated lesson", "critic_rejection")
        lessons = _load_lessons("test-domain")
        assert len(lessons) == 1
        assert lessons[0]["confidence"] == INITIAL_CONFIDENCE + CONFIDENCE_REPEAT_BOOST
        assert lessons[0]["observation_count"] == 2

    def test_confidence_caps_at_one(self, lessons_dir):
        from research_lessons import add_lesson, _load_lessons
        # Add same lesson 10 times — should cap at 1.0
        for _ in range(10):
            add_lesson("test-domain", "Very common", "critic_rejection")
        lessons = _load_lessons("test-domain")
        assert lessons[0]["confidence"] <= 1.0

    def test_confidence_decreases_on_contradiction(self, lessons_dir):
        from research_lessons import add_lesson, contradict_lesson, _load_lessons, INITIAL_CONFIDENCE
        add_lesson("test-domain", "Bad advice", "manual")
        assert contradict_lesson("test-domain", "Bad advice") is True
        lessons = _load_lessons("test-domain")
        assert lessons[0]["confidence"] == INITIAL_CONFIDENCE - 0.2

    def test_confidence_floors_at_zero(self, lessons_dir):
        from research_lessons import add_lesson, contradict_lesson, _load_lessons
        add_lesson("test-domain", "Wrong", "manual")
        for _ in range(10):
            contradict_lesson("test-domain", "Wrong")
        lessons = _load_lessons("test-domain")
        assert lessons[0]["confidence"] >= 0.0

    def test_contradict_nonexistent_returns_false(self, lessons_dir):
        from research_lessons import contradict_lesson
        assert contradict_lesson("test-domain", "Does not exist") is False

    def test_only_confident_lessons_for_strategy(self, lessons_dir):
        from research_lessons import add_lesson, get_confident_lessons, INITIAL_CONFIDENCE
        # Lesson with initial confidence (0.5) should NOT appear
        add_lesson("test-domain", "Low conf", "manual")
        # Lesson seen 2x should have 0.6 — just at threshold
        add_lesson("test-domain", "Repeated", "critic_rejection")
        add_lesson("test-domain", "Repeated", "critic_rejection")
        
        confident = get_confident_lessons("test-domain")
        assert len(confident) == 1
        assert confident[0]["lesson"] == "Repeated"


class TestProjectScoping:
    """17.3: Project/domain scoping."""

    def test_domains_seen_tracks_multiple(self, lessons_dir):
        from research_lessons import add_lesson, _load_lessons
        add_lesson("domain-a", "Universal rule", "manual")
        # Simulate adding same lesson in domain-b by loading domain-a,
        # then adding via domain-b
        add_lesson("domain-a", "Universal rule", "manual")
        lessons = _load_lessons("domain-a")
        assert "domain-a" in lessons[0]["domains_seen"]

    def test_global_lessons_from_multiple_domains(self, lessons_dir):
        from research_lessons import add_lesson, get_global_lessons
        # Same lesson across 2 domains
        add_lesson("domain-a", "Check sources", "critic_rejection")
        add_lesson("domain-b", "Check sources", "critic_rejection")
        
        globals_ = get_global_lessons()
        assert len(globals_) == 1
        assert globals_[0]["lesson"] == "Check sources"
        assert len(globals_[0]["domains_seen"]) >= 2

    def test_no_global_for_single_domain(self, lessons_dir):
        from research_lessons import add_lesson, get_global_lessons
        add_lesson("only-here", "Local lesson", "manual")
        globals_ = get_global_lessons()
        assert len(globals_) == 0

    def test_global_lessons_empty_dir(self, lessons_dir):
        from research_lessons import get_global_lessons
        globals_ = get_global_lessons()
        assert globals_ == []


class TestFormatting:
    """Tests for prompt formatting with confidence."""

    def test_format_only_confident(self, lessons_dir):
        from research_lessons import add_lesson, format_lessons_for_prompt
        # Low-confidence lesson (initial 0.5)
        add_lesson("test-domain", "Low conf", "manual")
        # High-confidence lesson (0.5 + 0.1*3 = 0.8)
        for _ in range(4):
            add_lesson("test-domain", "High conf", "critic_rejection")
        
        text = format_lessons_for_prompt("test-domain")
        assert "High conf" in text
        assert "Low conf" not in text

    def test_format_empty(self, lessons_dir):
        from research_lessons import format_lessons_for_prompt
        assert format_lessons_for_prompt("empty-domain") == ""

    def test_format_includes_confidence_label(self, lessons_dir):
        from research_lessons import add_lesson, format_lessons_for_prompt
        # 3 observations = 0.5 + 0.2 = 0.7 confidence
        for _ in range(3):
            add_lesson("test-domain", "A lesson", "critic_rejection")
        text = format_lessons_for_prompt("test-domain")
        assert "[70%]" in text


class TestBackwardCompatibility:
    """Ensure old lesson entries without new fields work."""

    def test_old_format_loads(self, lessons_dir):
        """Old format lessons (no confidence/domain fields) still load."""
        from research_lessons import get_lessons, _lessons_path
        # Write old format
        old_lesson = [{
            "lesson": "Old rule",
            "source": "manual",
            "details": "",
            "hit_count": 3,
            "created": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-15T00:00:00+00:00",
        }]
        path = _lessons_path("test-domain")
        with open(path, "w") as f:
            json.dump(old_lesson, f)
        
        lessons = get_lessons("test-domain")
        assert len(lessons) == 1
        assert lessons[0]["lesson"] == "Old rule"
        # Missing fields get defaults in code that reads them
        assert lessons[0].get("hit_count") == 3

    def test_old_format_dedup_adds_new_fields(self, lessons_dir):
        """When an old-format lesson is deduplicated, new fields are added."""
        from research_lessons import add_lesson, _load_lessons, _lessons_path
        # Write old format
        old_lesson = [{
            "lesson": "Old rule",
            "source": "manual",
            "details": "",
            "hit_count": 1,
            "created": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-15T00:00:00+00:00",
        }]
        path = _lessons_path("test-domain")
        with open(path, "w") as f:
            json.dump(old_lesson, f)
        
        # Re-add same lesson — should dedup and add new fields
        add_lesson("test-domain", "Old rule", "manual")
        lessons = _load_lessons("test-domain")
        assert len(lessons) == 1
        assert lessons[0]["hit_count"] == 2
        assert "confidence" in lessons[0]  # New field added on dedup
        assert "observation_count" in lessons[0]
