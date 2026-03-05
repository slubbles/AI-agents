"""
Tests for Objective 5: Train the Visual Standard.

Tests design system / marketing design loading, page_type-aware prompt switching,
visual scoring calibration rubric, and visual score storage/retrieval.
All tests use mocks — no real API calls.
"""

import json
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# Task 5.1: Brain Seed Questions (domain_seeder.py)
# ============================================================

class TestWebDesignSeedQuestions:
    """The web-design domain has curated seed questions."""

    def test_web_design_domain_exists(self):
        from domain_seeder import SEED_QUESTIONS
        assert "web-design" in SEED_QUESTIONS

    def test_web_design_has_questions(self):
        from domain_seeder import SEED_QUESTIONS
        questions = SEED_QUESTIONS["web-design"]
        assert len(questions) >= 3  # Enough to bootstrap meaningful research

    def test_web_design_questions_are_strings(self):
        from domain_seeder import SEED_QUESTIONS
        for q in SEED_QUESTIONS["web-design"]:
            assert isinstance(q, str)
            assert len(q) > 20  # Not trivially short

    def test_web_design_covers_key_topics(self):
        """Seed questions should cover the topics needed for visual standard."""
        from domain_seeder import SEED_QUESTIONS
        combined = " ".join(SEED_QUESTIONS["web-design"]).lower()
        # Must cover visual patterns, landing pages, Tailwind, and state patterns
        assert "visual" in combined or "design" in combined or "shadcn" in combined
        assert "landing" in combined or "saas" in combined or "marketing" in combined
        assert "tailwind" in combined or "css" in combined
        assert "state" in combined or "loading" in combined or "error" in combined

    def test_get_seed_questions_returns_web_design(self):
        from domain_seeder import get_seed_questions
        questions = get_seed_questions("web-design", count=5)
        assert len(questions) >= 3


# ============================================================
# Task 5.2: Design System Expanded (identity/design_system.md)
# ============================================================

class TestDesignSystemContent:
    """The design_system.md file has required content."""

    def _read_design_system(self):
        path = os.path.join(os.path.dirname(__file__), "..", "identity", "design_system.md")
        if not os.path.exists(path):
            pytest.skip("design_system.md not found")
        with open(path) as f:
            return f.read()

    def test_file_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "identity", "design_system.md")
        assert os.path.exists(path)

    def test_has_color_system(self):
        content = self._read_design_system()
        assert "color" in content.lower()

    def test_has_typography(self):
        content = self._read_design_system()
        assert "typography" in content.lower() or "font" in content.lower()

    def test_has_spacing(self):
        content = self._read_design_system()
        assert "spacing" in content.lower() or "padding" in content.lower()

    def test_has_loading_states(self):
        content = self._read_design_system()
        assert "loading" in content.lower()

    def test_has_error_states(self):
        content = self._read_design_system()
        assert "error" in content.lower()

    def test_has_empty_states(self):
        content = self._read_design_system()
        assert "empty" in content.lower()

    def test_has_dark_mode(self):
        content = self._read_design_system()
        assert "dark" in content.lower()

    def test_has_accessibility(self):
        content = self._read_design_system()
        lower = content.lower()
        assert "accessibility" in lower or "a11y" in lower or "focus" in lower

    def test_has_anti_patterns(self):
        content = self._read_design_system()
        assert "anti-pattern" in content.lower() or "never" in content.lower()

    def test_has_version_history(self):
        content = self._read_design_system()
        assert "version" in content.lower()


# ============================================================
# Task 5.3: Marketing Design System (identity/marketing_design.md)
# ============================================================

class TestMarketingDesignContent:
    """The marketing_design.md file has required content."""

    def _read_marketing_design(self):
        path = os.path.join(os.path.dirname(__file__), "..", "identity", "marketing_design.md")
        if not os.path.exists(path):
            pytest.skip("marketing_design.md not found")
        with open(path) as f:
            return f.read()

    def test_file_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "identity", "marketing_design.md")
        assert os.path.exists(path)

    def test_has_hero_section(self):
        content = self._read_marketing_design()
        assert "hero" in content.lower()

    def test_has_social_proof(self):
        content = self._read_marketing_design()
        assert "social proof" in content.lower()

    def test_has_cta(self):
        content = self._read_marketing_design()
        assert "cta" in content.lower()

    def test_has_above_fold(self):
        content = self._read_marketing_design()
        assert "fold" in content.lower() or "above" in content.lower()

    def test_has_testimonials(self):
        content = self._read_marketing_design()
        assert "testimonial" in content.lower()

    def test_has_pricing(self):
        content = self._read_marketing_design()
        assert "pricing" in content.lower()

    def test_has_footer(self):
        content = self._read_marketing_design()
        assert "footer" in content.lower()

    def test_has_animation_patterns(self):
        content = self._read_marketing_design()
        assert "framer" in content.lower() or "animation" in content.lower()

    def test_has_responsive_rules(self):
        content = self._read_marketing_design()
        assert "responsive" in content.lower() or "mobile" in content.lower()

    def test_has_conversion_rules(self):
        content = self._read_marketing_design()
        assert "conversion" in content.lower()


# ============================================================
# Task 5.4: Executor Design System Injection
# ============================================================

class TestExecutorDesignInjection:
    """Executor loads the correct design system based on page_type."""

    def test_build_system_prompt_loads_app_design(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc", page_type="app")
        assert "DESIGN SYSTEM" in prompt

    def test_build_system_prompt_loads_marketing_design(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc", page_type="marketing")
        assert "MARKETING DESIGN SYSTEM" in prompt

    def test_build_system_prompt_default_is_app(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc")
        # Default page_type is "app"
        assert "DESIGN SYSTEM" in prompt

    def test_build_system_prompt_contains_date(self):
        from hands.executor import _build_system_prompt
        from datetime import date
        prompt = _build_system_prompt("tools desc")
        assert date.today().isoformat() in prompt

    def test_build_system_prompt_contains_execution_rules(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc")
        assert "EXECUTION RULES" in prompt
        assert "placeholder" in prompt.lower()

    def test_build_system_prompt_includes_execution_strategy(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc", execution_strategy="Use TDD approach")
        assert "EXECUTION STRATEGY" in prompt
        assert "TDD" in prompt

    def test_build_system_prompt_no_truncation(self):
        """Design system content should NOT be truncated to 2000 chars."""
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc", page_type="app")
        # The design_system.md is ~400+ lines. If truncated at 2000, we'd lose most of it.
        # Check that we have substantial content (the full file)
        design_start = prompt.find("=== DESIGN SYSTEM ===")
        design_end = prompt.find("=== END DESIGN SYSTEM ===")
        if design_start != -1 and design_end != -1:
            design_content = prompt[design_start:design_end]
            # Full design system is well over 2000 chars
            assert len(design_content) > 2000, "Design system appears truncated"

    def test_marketing_design_content_differs_from_app(self):
        """Marketing and app design systems should have different content."""
        from hands.executor import _build_system_prompt
        app_prompt = _build_system_prompt("tools desc", page_type="app")
        marketing_prompt = _build_system_prompt("tools desc", page_type="marketing")
        # They should not be identical (different design files)
        assert app_prompt != marketing_prompt


# ============================================================
# Vercel Agent Skills Integration
# ============================================================

class TestExecutorVercelSkillsInjection:
    """Executor loads react best practices and web interface guidelines."""

    def test_executor_prompt_contains_react_best_practices(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc", page_type="app")
        assert "REACT BEST PRACTICES" in prompt
        assert "Promise.all" in prompt or "Waterfalls" in prompt

    def test_executor_prompt_contains_web_guidelines(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc", page_type="app")
        assert "WEB INTERFACE GUIDELINES" in prompt
        assert "Accessibility" in prompt

    def test_executor_marketing_also_gets_skills(self):
        from hands.executor import _build_system_prompt
        prompt = _build_system_prompt("tools desc", page_type="marketing")
        assert "REACT BEST PRACTICES" in prompt
        assert "WEB INTERFACE GUIDELINES" in prompt


class TestPlannerVercelSkillsInjection:
    """Planner loads react best practices and web interface guidelines."""

    def test_planner_prompt_contains_react_best_practices(self):
        from hands.planner import _build_system_prompt
        prompt = _build_system_prompt("tools desc")
        assert "REACT BEST PRACTICES" in prompt

    def test_planner_prompt_contains_web_guidelines(self):
        from hands.planner import _build_system_prompt
        prompt = _build_system_prompt("tools desc")
        assert "WEB INTERFACE GUIDELINES" in prompt

    def test_planner_prompt_still_contains_design_system(self):
        from hands.planner import _build_system_prompt
        prompt = _build_system_prompt("tools desc")
        assert "DESIGN SYSTEM" in prompt


# ============================================================
# Task 5.4: Visual Evaluator Page-Type Switching
# ============================================================

class TestVisualEvaluatorDesignSwitch:
    """Visual evaluator loads correct design based on page_type."""

    def test_get_design_system_returns_string(self):
        from hands.visual_evaluator import _get_design_system
        result = _get_design_system()
        assert isinstance(result, str)

    def test_get_marketing_design_returns_string(self):
        from hands.visual_evaluator import _get_marketing_design
        result = _get_marketing_design()
        assert isinstance(result, str)

    def test_get_scoring_rubric_returns_string(self):
        from hands.visual_evaluator import _get_scoring_rubric
        result = _get_scoring_rubric()
        assert isinstance(result, str)

    def test_build_eval_system_app_type(self):
        from hands.visual_evaluator import _build_eval_system
        system = _build_eval_system("app")
        assert "DESIGN STANDARD" in system
        assert "SCORING RUBRIC" in system

    def test_build_eval_system_marketing_type(self):
        from hands.visual_evaluator import _build_eval_system
        system = _build_eval_system("marketing")
        assert "MARKETING DESIGN STANDARD" in system

    def test_build_eval_system_includes_calibration(self):
        from hands.visual_evaluator import _build_eval_system
        system = _build_eval_system("app")
        assert "SCORING CALIBRATION" in system

    def test_build_eval_system_has_dimensions(self):
        from hands.visual_evaluator import _build_eval_system
        system = _build_eval_system("app")
        assert "Layout" in system
        assert "Typography" in system
        assert "Color" in system

    def test_identity_file_helper_missing_file(self):
        from hands.visual_evaluator import _get_identity_file
        result = _get_identity_file("nonexistent_file_12345.md")
        assert result == ""

    def test_identity_file_helper_truncation(self):
        from hands.visual_evaluator import _get_identity_file
        # Get system loads with a default truncation
        result = _get_identity_file("design_system.md", max_chars=100)
        assert len(result) <= 100


# ============================================================
# Task 5.5: Visual Scoring Calibration
# ============================================================

class TestVisualScoringRubric:
    """The visual scoring rubric exists and has required content."""

    def _read_rubric(self):
        path = os.path.join(os.path.dirname(__file__), "..", "identity", "visual_scoring_rubric.md")
        if not os.path.exists(path):
            pytest.skip("visual_scoring_rubric.md not found")
        with open(path) as f:
            return f.read()

    def test_file_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "identity", "visual_scoring_rubric.md")
        assert os.path.exists(path)

    def test_has_score_10_definition(self):
        content = self._read_rubric()
        assert "10" in content and "agency" in content.lower()

    def test_has_score_8_definition(self):
        content = self._read_rubric()
        assert "8" in content and "production" in content.lower()

    def test_has_score_5_definition(self):
        content = self._read_rubric()
        assert "4-5" in content or "below average" in content.lower()

    def test_has_dimension_calibration(self):
        content = self._read_rubric()
        assert "layout" in content.lower()
        assert "typography" in content.lower()
        assert "color" in content.lower()

    def test_has_marketing_adjustments(self):
        content = self._read_rubric()
        assert "marketing" in content.lower()


# ============================================================
# Task 5.5: Visual Score Storage & Retrieval
# ============================================================

class TestVisualScoreStorage:
    """Visual scores are stored and retrievable for strategy evolution."""

    def test_store_visual_score_creates_file(self):
        from hands.visual_evaluator import store_visual_score
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                result = store_visual_score(
                    domain="test-domain",
                    task_id="task-001",
                    evaluation={"score": 7, "dimensions": {"layout": 8}, "issues": []},
                    page_type="app",
                )
                assert result is not None
                assert os.path.exists(result)

    def test_store_visual_score_writes_jsonl(self):
        from hands.visual_evaluator import store_visual_score
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                store_visual_score(
                    domain="test-domain",
                    task_id="task-001",
                    evaluation={"score": 7, "dimensions": {"layout": 8}, "issues": []},
                )
                scores_path = os.path.join(tmpdir, "visual_scores", "test-domain.jsonl")
                with open(scores_path) as f:
                    line = f.readline().strip()
                record = json.loads(line)
                assert record["task_id"] == "task-001"
                assert record["score"] == 7

    def test_store_visual_score_appends(self):
        from hands.visual_evaluator import store_visual_score
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                store_visual_score(
                    domain="test-domain",
                    task_id="task-001",
                    evaluation={"score": 7, "dimensions": {}, "issues": []},
                )
                store_visual_score(
                    domain="test-domain",
                    task_id="task-002",
                    evaluation={"score": 8, "dimensions": {}, "issues": []},
                )
                scores_path = os.path.join(tmpdir, "visual_scores", "test-domain.jsonl")
                with open(scores_path) as f:
                    lines = f.readlines()
                assert len(lines) == 2

    def test_store_counts_critical_issues(self):
        from hands.visual_evaluator import store_visual_score
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                store_visual_score(
                    domain="test-domain",
                    task_id="task-001",
                    evaluation={
                        "score": 4,
                        "dimensions": {},
                        "issues": [
                            {"severity": "critical", "description": "broken layout"},
                            {"severity": "major", "description": "bad colors"},
                            {"severity": "minor", "description": "icon size"},
                        ],
                    },
                )
                scores_path = os.path.join(tmpdir, "visual_scores", "test-domain.jsonl")
                with open(scores_path) as f:
                    record = json.loads(f.readline())
                assert record["critical_issues"] == 1
                assert record["major_issues"] == 1
                assert record["issue_count"] == 3

    def test_store_records_page_type(self):
        from hands.visual_evaluator import store_visual_score
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                store_visual_score(
                    domain="test-domain",
                    task_id="task-001",
                    evaluation={"score": 8, "dimensions": {}, "issues": []},
                    page_type="marketing",
                )
                scores_path = os.path.join(tmpdir, "visual_scores", "test-domain.jsonl")
                with open(scores_path) as f:
                    record = json.loads(f.readline())
                assert record["page_type"] == "marketing"


class TestVisualScoreRetrieval:
    """Load and summarize visual scores for strategy evolution."""

    def _write_scores(self, tmpdir, domain, scores):
        """Helper to write score records to JSONL."""
        scores_dir = os.path.join(tmpdir, "visual_scores")
        os.makedirs(scores_dir, exist_ok=True)
        path = os.path.join(scores_dir, f"{domain}.jsonl")
        with open(path, "w") as f:
            for s in scores:
                f.write(json.dumps(s) + "\n")

    def test_load_visual_scores_empty(self):
        from hands.visual_evaluator import load_visual_scores
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                result = load_visual_scores("nonexistent-domain")
                assert result == []

    def test_load_visual_scores_returns_records(self):
        from hands.visual_evaluator import load_visual_scores
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_scores(tmpdir, "test-domain", [
                {"task_id": "t1", "score": 6, "dimensions": {}},
                {"task_id": "t2", "score": 8, "dimensions": {}},
            ])
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                result = load_visual_scores("test-domain")
                assert len(result) == 2
                assert result[0]["task_id"] == "t1"

    def test_load_visual_scores_last_n(self):
        from hands.visual_evaluator import load_visual_scores
        with tempfile.TemporaryDirectory() as tmpdir:
            records = [{"task_id": f"t{i}", "score": i} for i in range(10)]
            self._write_scores(tmpdir, "test-domain", records)
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                result = load_visual_scores("test-domain", last_n=3)
                assert len(result) == 3
                assert result[0]["task_id"] == "t7"

    def test_get_visual_score_summary_no_data(self):
        from hands.visual_evaluator import get_visual_score_summary
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                summary = get_visual_score_summary("nonexistent")
                assert summary["count"] == 0
                assert summary["trend"] == "no_data"

    def test_get_visual_score_summary_computes_averages(self):
        from hands.visual_evaluator import get_visual_score_summary
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_scores(tmpdir, "test-domain", [
                {"task_id": "t1", "score": 6, "dimensions": {"layout": 7, "typography": 5}, "critical_issues": 1, "major_issues": 2},
                {"task_id": "t2", "score": 8, "dimensions": {"layout": 9, "typography": 7}, "critical_issues": 0, "major_issues": 1},
                {"task_id": "t3", "score": 7, "dimensions": {"layout": 8, "typography": 6}, "critical_issues": 0, "major_issues": 0},
                {"task_id": "t4", "score": 9, "dimensions": {"layout": 9, "typography": 8}, "critical_issues": 0, "major_issues": 0},
            ])
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                summary = get_visual_score_summary("test-domain")
                assert summary["count"] == 4
                assert summary["avg_score"] == 7.5  # (6+8+7+9)/4
                assert summary["min_score"] == 6
                assert summary["max_score"] == 9
                assert "layout" in summary["avg_dimensions"]
                assert summary["common_issues"] == 4  # 1+2+0+1+0+0+0+0

    def test_get_visual_score_summary_trend_improving(self):
        from hands.visual_evaluator import get_visual_score_summary
        with tempfile.TemporaryDirectory() as tmpdir:
            # First half low, second half high → improving
            self._write_scores(tmpdir, "test-domain", [
                {"score": 4, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 5, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 5, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 4, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 8, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 9, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 8, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 9, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
            ])
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                summary = get_visual_score_summary("test-domain")
                assert summary["trend"] == "improving"

    def test_get_visual_score_summary_trend_declining(self):
        from hands.visual_evaluator import get_visual_score_summary
        with tempfile.TemporaryDirectory() as tmpdir:
            # First half high, second half low → declining
            self._write_scores(tmpdir, "test-domain", [
                {"score": 9, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 8, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 9, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 8, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 4, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 5, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 4, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
                {"score": 5, "dimensions": {}, "critical_issues": 0, "major_issues": 0},
            ])
            with patch("hands.visual_evaluator.LOG_DIR", tmpdir):
                summary = get_visual_score_summary("test-domain")
                assert summary["trend"] == "declining"


# ============================================================
# Visual Gate stores scores after evaluation
# ============================================================

class TestVisualGateStoresScores:
    """Visual gate imports and uses store_visual_score."""

    def test_store_visual_score_imported(self):
        from hands.visual_gate import store_visual_score
        assert callable(store_visual_score)

    def test_visual_gate_page_type_propagates(self):
        from hands.visual_gate import VisualGate
        gate = VisualGate(
            workspace_dir="/tmp/test",
            domain="test",
            context="Test page",
            page_type="marketing",
        )
        assert gate.page_type == "marketing"


# ============================================================
# Integration: executor + evaluator consistent page_type
# ============================================================

class TestDesignStandardIntegration:
    """Executor and evaluator use the same page_type switching logic."""

    def test_executor_and_evaluator_both_support_marketing(self):
        from hands.executor import _build_system_prompt
        from hands.visual_evaluator import _build_eval_system

        exec_prompt = _build_system_prompt("tools desc", page_type="marketing")
        eval_prompt = _build_eval_system("marketing")

        assert "MARKETING" in exec_prompt
        assert "MARKETING" in eval_prompt

    def test_executor_and_evaluator_both_support_app(self):
        from hands.executor import _build_system_prompt
        from hands.visual_evaluator import _build_eval_system

        exec_prompt = _build_system_prompt("tools desc", page_type="app")
        eval_prompt = _build_eval_system("app")

        # Both should include design content but NOT marketing label
        assert "DESIGN SYSTEM" in exec_prompt
        assert "DESIGN STANDARD" in eval_prompt

    def test_three_identity_files_exist(self):
        """All three identity files required by Objective 5 exist."""
        identity_dir = os.path.join(os.path.dirname(__file__), "..", "identity")
        assert os.path.exists(os.path.join(identity_dir, "design_system.md"))
        assert os.path.exists(os.path.join(identity_dir, "marketing_design.md"))
        assert os.path.exists(os.path.join(identity_dir, "visual_scoring_rubric.md"))
