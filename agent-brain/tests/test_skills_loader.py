"""Tests for skills_loader module."""

import csv
import os
import shutil
import tempfile
import pytest

# Ensure agent-brain is on the path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills_loader import (
    _parse_frontmatter,
    _get_skill_files,
    load_skills,
    list_skills,
    detect_categories,
    lookup_design_data,
    SKILLS_DIR,
    DESIGN_DATA_DIR,
    CATEGORY_PRIORITY,
)


# ── Frontmatter parsing ─────────────────────────────────────────────────

class TestParseFrontmatter:
    def test_no_frontmatter(self):
        content = "# Just a heading\n\nSome content."
        meta, body = _parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_basic_frontmatter(self):
        content = "---\nname: React Patterns\npriority: 10\n---\n# React Patterns\nContent here."
        meta, body = _parse_frontmatter(content)
        assert meta["name"] == "React Patterns"
        assert meta["priority"] == 10
        assert body == "# React Patterns\nContent here."

    def test_list_values(self):
        content = "---\ntags: [react, nextjs, typescript]\n---\nBody"
        meta, body = _parse_frontmatter(content)
        assert meta["tags"] == ["react", "nextjs", "typescript"]
        assert body == "Body"

    def test_empty_frontmatter(self):
        content = "---\n---\nBody text"
        meta, body = _parse_frontmatter(content)
        assert meta == {}
        assert body == "Body text"

    def test_no_closing_delimiter(self):
        content = "---\nname: Test\nNo closing"
        meta, body = _parse_frontmatter(content)
        assert meta == {}
        assert body == content


# ── Skill file loading ───────────────────────────────────────────────────

class TestGetSkillFiles:
    def test_nonexistent_category(self):
        result = _get_skill_files("nonexistent_category_xyzzy")
        assert result == []

    def test_coding_category_has_files(self):
        """Verify the coding category has our copied skill files."""
        skills = _get_skill_files("coding")
        filenames = [s["filename"] for s in skills]
        assert "react_best_practices.md" in filenames
        assert "web_interface_guidelines.md" in filenames

    def test_skill_dict_structure(self):
        """Each skill dict should have the expected keys."""
        skills = _get_skill_files("coding")
        if not skills:
            pytest.skip("No coding skills installed yet")
        skill = skills[0]
        assert "path" in skill
        assert "filename" in skill
        assert "name" in skill
        assert "category" in skill
        assert "size" in skill
        assert "priority" in skill
        assert "body" in skill
        assert skill["category"] == "coding"


# ── load_skills ──────────────────────────────────────────────────────────

class TestLoadSkills:
    def test_empty_categories(self):
        assert load_skills([]) == ""

    def test_nonexistent_category(self):
        assert load_skills(["nonexistent_xyz"]) == ""

    def test_coding_loads(self):
        result = load_skills(["coding"])
        assert "SKILL:" in result
        assert "React" in result or "react" in result or "Web" in result

    def test_max_chars_respected(self):
        result = load_skills(["coding"], max_chars=500)
        assert len(result) <= 600  # Small overhead for headers

    def test_dedup_across_categories(self):
        """Same file shouldn't load twice even if requested via multiple categories."""
        result1 = load_skills(["coding"])
        result2 = load_skills(["coding", "coding"])
        assert result1 == result2

    def test_multiple_categories(self):
        """Loading multiple categories should work."""
        result = load_skills(["coding", "design", "marketing"])
        # At minimum coding should have content
        assert len(result) > 0


# ── list_skills ──────────────────────────────────────────────────────────

class TestListSkills:
    def test_list_all(self):
        result = list_skills()
        assert isinstance(result, list)
        # We should have at least the 2 coding skills we copied
        coding = [s for s in result if s["category"] == "coding"]
        assert len(coding) >= 2

    def test_list_by_category(self):
        result = list_skills("coding")
        assert all(s["category"] == "coding" for s in result)

    def test_list_empty_category(self):
        result = list_skills("validation")
        assert isinstance(result, list)
        # Might be empty if no validation skills installed yet

    def test_skill_metadata(self):
        result = list_skills("coding")
        if not result:
            pytest.skip("No coding skills")
        skill = result[0]
        assert "name" in skill
        assert "category" in skill
        assert "filename" in skill
        assert "size" in skill
        assert isinstance(skill["size"], int)


# ── detect_categories ────────────────────────────────────────────────────

class TestDetectCategories:
    def test_empty_text(self):
        assert detect_categories("") == []

    def test_coding_keywords(self):
        cats = detect_categories("Build a React component with TypeScript")
        assert "coding" in cats

    def test_design_keywords(self):
        cats = detect_categories("Create a landing page with beautiful UI design")
        assert "design" in cats

    def test_marketing_keywords(self):
        cats = detect_categories("Write blog content for SEO marketing campaign")
        assert "marketing" in cats

    def test_sales_keywords(self):
        cats = detect_categories("Draft cold email outreach for investors")
        assert "sales" in cats

    def test_product_keywords(self):
        cats = detect_categories("Write a feature spec for the product roadmap")
        assert "product" in cats

    def test_research_keywords(self):
        cats = detect_categories("Do market research and competitor analysis")
        assert "research" in cats

    def test_validation_keywords(self):
        cats = detect_categories("Validate this idea and check if it already exists")
        assert "validation" in cats

    def test_workflow_keywords(self):
        cats = detect_categories("Set up a cost-aware pipeline with verification loop")
        assert "workflow" in cats

    def test_multiple_categories(self):
        cats = detect_categories("Build a React landing page with SEO content and design system")
        assert "coding" in cats
        assert "design" in cats
        assert "marketing" in cats

    def test_priority_ordering(self):
        """Categories should be sorted by priority."""
        cats = detect_categories("Build a React landing page with marketing content and design")
        if len(cats) >= 2:
            priorities = [CATEGORY_PRIORITY.get(c, 99) for c in cats]
            assert priorities == sorted(priorities)


# ── Design data lookup ───────────────────────────────────────────────────

class TestDesignDataLookup:
    def test_empty_industry(self):
        assert lookup_design_data("") == ""

    def test_nonexistent_industry(self):
        result = lookup_design_data("underwater_basket_weaving_xyz")
        assert result == ""

    def test_healthcare_lookup(self):
        """Healthcare should match across multiple CSV databases."""
        result = lookup_design_data("healthcare")
        assert "healthcare" in result.lower()
        assert len(result) > 50

    def test_fintech_lookup(self):
        result = lookup_design_data("fintech")
        assert "fintech" in result.lower()

    def test_ecommerce_lookup(self):
        result = lookup_design_data("ecommerce")
        assert "ecommerce" in result.lower()

    def test_saas_lookup(self):
        result = lookup_design_data("saas")
        assert "saas" in result.lower()

    def test_data_type_filter_palettes(self):
        result = lookup_design_data("healthcare", data_type="palettes")
        # Should only return palette data, not rules or other types
        if result:
            assert "Color Palettes" in result or "palette" in result.lower()

    def test_data_type_filter_rules(self):
        result = lookup_design_data("healthcare", data_type="rules")
        if result:
            assert "Industry Rules" in result

    def test_data_type_filter_fonts(self):
        result = lookup_design_data("education", data_type="fonts")
        # education appears in font_pairings best_for column
        assert isinstance(result, str)

    def test_invalid_data_type(self):
        """Invalid data_type falls through to search all databases."""
        result = lookup_design_data("healthcare", data_type="nonexistent")
        # "nonexistent" is truthy but not in databases dict,
        # so the ternary falls to else branch → searches all databases
        assert "healthcare" in result.lower()


# ── Integration tests ────────────────────────────────────────────────────

class TestIntegration:
    def test_skills_dir_exists(self):
        assert os.path.isdir(SKILLS_DIR)

    def test_category_dirs_exist(self):
        for cat in CATEGORY_PRIORITY:
            cat_dir = os.path.join(SKILLS_DIR, cat)
            assert os.path.isdir(cat_dir), f"Missing category directory: {cat}"

    def test_end_to_end_detect_and_load(self):
        """Detect categories from text then load matching skills."""
        cats = detect_categories("Build a Next.js React web application")
        assert len(cats) > 0
        result = load_skills(cats, max_chars=8000)
        # Should load at least the coding skills
        assert len(result) > 0

    def test_planner_import_works(self):
        """Verify planner can import skills_loader."""
        from hands.planner import _build_system_prompt
        # Just verify it's callable
        assert callable(_build_system_prompt)

    def test_executor_import_works(self):
        """Verify executor can import skills_loader."""
        from hands.executor import _build_system_prompt
        assert callable(_build_system_prompt)

    def test_frontend_design_skill_installed(self):
        """The frontend-design anti-slop skill should be in the design category."""
        skills = list_skills("design")
        filenames = [s["filename"] for s in skills]
        assert "frontend_design.md" in filenames

    def test_frontend_design_loads_for_ui_tasks(self):
        """Design skill should load when UI/design task detected."""
        cats = detect_categories("Build a beautiful landing page with custom UI design")
        assert "design" in cats
        result = load_skills(["design"], max_chars=8000)
        assert "Anti-Slop" in result or "AI slop" in result.lower() or "distinctive" in result.lower()

    def test_design_data_dir_has_csvs(self):
        """Verify CSV databases are installed."""
        assert os.path.isdir(DESIGN_DATA_DIR)
        csv_files = [f for f in os.listdir(DESIGN_DATA_DIR) if f.endswith(".csv")]
        assert len(csv_files) >= 5
        expected = {"industry_rules.csv", "ui_styles.csv", "color_palettes.csv", "font_pairings.csv", "ux_guidelines.csv"}
        assert expected.issubset(set(csv_files))

    def test_design_lookup_end_to_end(self):
        """Full pipeline: detect design category, load skills, and lookup industry data."""
        cats = detect_categories("Build a healthcare patient portal with modern UI")
        assert "design" in cats
        data = lookup_design_data("healthcare")
        assert len(data) > 0
        assert "healthcare" in data.lower()


# ── ECC Skills Tests ─────────────────────────────────────────────────────

class TestECCSkills:
    """Tests for everything-claude-code skill integration."""

    def test_research_skills_installed(self):
        skills = list_skills("research")
        filenames = [s["filename"] for s in skills]
        assert "market_research.md" in filenames

    def test_workflow_skills_installed(self):
        skills = list_skills("workflow")
        filenames = [s["filename"] for s in skills]
        assert "search_first.md" in filenames
        assert "verification_loop.md" in filenames
        assert "cost_aware_pipeline.md" in filenames

    def test_marketing_skills_installed(self):
        skills = list_skills("marketing")
        filenames = [s["filename"] for s in skills]
        assert "content_engine.md" in filenames
        assert "article_writing.md" in filenames

    def test_coding_skills_installed(self):
        skills = list_skills("coding")
        filenames = [s["filename"] for s in skills]
        assert "frontend_patterns.md" in filenames
        assert "backend_patterns.md" in filenames
        assert "security_review.md" in filenames
        assert "deployment_patterns.md" in filenames

    def test_total_skills_count(self):
        """Should have at least 13 skills installed."""
        all_skills = list_skills()
        assert len(all_skills) >= 13

    def test_coding_loads_within_budget(self):
        """Coding has many large files. Budget should limit what loads."""
        result = load_skills(["coding"], max_chars=8000)
        assert len(result) <= 8200  # Small overhead for last skill boundary
        assert "SKILL:" in result  # At least one skill loaded

    def test_workflow_loads_priority_order(self):
        """Workflow skills should load in priority order (search_first=1 first)."""
        result = load_skills(["workflow"], max_chars=8000)
        # search_first has priority 1, should appear before cost_aware_pipeline (priority 8)
        search_pos = result.find("Search First")
        cost_pos = result.find("Cost-Aware")
        if search_pos >= 0 and cost_pos >= 0:
            assert search_pos < cost_pos

    def test_multi_category_build_task(self):
        """A full build task should detect and load from multiple categories."""
        cats = detect_categories("Build a Next.js SaaS landing page with marketing content")
        assert "coding" in cats
        assert "design" in cats or "marketing" in cats
        result = load_skills(cats, max_chars=8000)
        assert len(result) > 0

    def test_skills_have_valid_frontmatter(self):
        """All installed skills should have parseable frontmatter with name."""
        all_skills = list_skills()
        for skill in all_skills:
            # Name should not be just the filename slug
            assert skill["name"] is not None
            assert len(skill["name"]) > 0
            assert skill["size"] > 0

    def test_security_detected_for_security_task(self):
        """Security skill should load when security-related task detected."""
        cats = detect_categories("Review the code for security vulnerabilities")
        result = load_skills(cats, max_chars=8000)
        # security_review should be in coding category, which gets loaded
        assert "coding" in cats


# ── Temp directory tests for edge cases ──────────────────────────────────

class TestWithTempSkills:
    """Tests using temporary skill files to verify loading behavior."""

    @pytest.fixture
    def temp_skills_dir(self, tmp_path, monkeypatch):
        """Create a temp skills directory with test skill files."""
        import skills_loader

        skills_dir = tmp_path / "skills"
        coding_dir = skills_dir / "coding"
        coding_dir.mkdir(parents=True)

        # Create test skill files
        (coding_dir / "skill_a.md").write_text(
            "---\nname: Skill A\npriority: 1\n---\nContent of skill A."
        )
        (coding_dir / "skill_b.md").write_text(
            "---\nname: Skill B\npriority: 2\n---\nContent of skill B which is longer."
        )
        (coding_dir / "not_a_skill.txt").write_text("Should be ignored.")

        design_dir = skills_dir / "design"
        design_dir.mkdir()
        (design_dir / "visual.md").write_text("Visual design guidelines here.")

        # Monkeypatch SKILLS_DIR
        monkeypatch.setattr(skills_loader, "SKILLS_DIR", str(skills_dir))
        return skills_dir

    def test_loads_only_md_files(self, temp_skills_dir):
        skills = _get_skill_files("coding")
        filenames = [s["filename"] for s in skills]
        assert "not_a_skill.txt" not in filenames
        assert "skill_a.md" in filenames

    def test_priority_ordering(self, temp_skills_dir):
        skills = _get_skill_files("coding")
        # skill_a has priority 1, skill_b has priority 2
        names = [s["name"] for s in skills]
        assert names[0] == "Skill A" or names[1] == "Skill B"

    def test_load_with_budget(self, temp_skills_dir):
        # Small budget should limit the number of skills loaded
        result = load_skills(["coding"], max_chars=200)
        # Should load at least something
        assert "SKILL:" in result
        # Full budget should load more content
        full = load_skills(["coding"], max_chars=10000)
        assert len(full) >= len(result)

    def test_load_multiple_categories(self, temp_skills_dir):
        result = load_skills(["coding", "design"])
        assert "Skill A" in result or "visual" in result.lower()

    def test_list_all_temp(self, temp_skills_dir):
        result = list_skills()
        assert len(result) >= 2  # At least skill_a and skill_b

    def test_csv_design_data(self, temp_skills_dir, monkeypatch):
        """Test CSV design data loading."""
        import skills_loader

        data_dir = temp_skills_dir / "design" / "data"
        data_dir.mkdir(parents=True)

        # Create a test CSV
        csv_path = data_dir / "industry_rules.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["industry", "rule", "description"])
            writer.writerow(["healthcare", "HIPAA compliance", "All health data must be encrypted"])
            writer.writerow(["fintech", "PCI DSS", "Payment card data handling"])
            writer.writerow(["healthcare", "Accessibility", "WCAG 2.1 AA required"])

        monkeypatch.setattr(skills_loader, "DESIGN_DATA_DIR", str(data_dir))

        result = lookup_design_data("healthcare")
        assert "healthcare" in result.lower()
        assert "HIPAA" in result or "Accessibility" in result

        # Non-matching industry
        result2 = lookup_design_data("automotive")
        assert result2 == ""

    def test_csv_data_type_filter(self, temp_skills_dir, monkeypatch):
        """Test filtering by data_type."""
        import skills_loader

        data_dir = temp_skills_dir / "design" / "data"
        data_dir.mkdir(parents=True)

        csv_path = data_dir / "color_palettes.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["industry", "palette_name", "colors"])
            writer.writerow(["healthcare", "Medical Blue", "#0066CC,#FFFFFF,#E8F4FD"])

        monkeypatch.setattr(skills_loader, "DESIGN_DATA_DIR", str(data_dir))

        # Filter to palettes only
        result = lookup_design_data("healthcare", data_type="palettes")
        assert "Medical Blue" in result

        # Filter to rules should find nothing (no rules CSV)
        result2 = lookup_design_data("healthcare", data_type="rules")
        assert result2 == ""
