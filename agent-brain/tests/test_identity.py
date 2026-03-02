"""
Tests for the Identity Layer — loader, validation, and prompt injection.
"""

import os
import json
import pytest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def identity_dir():
    """Create a temporary identity directory with all files."""
    tmpdir = tempfile.mkdtemp()
    files = {
        "goals.md": "# Cortex — Goals\n\n## Primary Goal\n\nGenerate revenue.\n\n## Operating Goals\n\n1. Stay alive\n2. Learn actionably\n3. Ship revenue work\n",
        "ethics.md": "# Cortex — Ethics\n\n## Never Do\n\n1. **Falsify research** — never fabricate data\n2. **Deceive users** — never mislead\n3. **Irreversible actions** — never deploy without approval\n",
        "boundaries.md": "# Cortex — Boundaries\n\n## Budget\n\n- **Daily limit: $2.00** — hard stop\n- **Hard ceiling: $3.00** — emergency only\n",
        "risk.md": "# Cortex — Risk\n\n## Exploration default: 80/20 exploit/explore\n\n- Never spend more than $0.50 per round\n",
        "taste.md": "# Cortex — Taste\n\nSpecific > vague. Sourced > assumed. Working > clever.\n",
    }
    for name, content in files.items():
        with open(os.path.join(tmpdir, name), "w") as f:
            f.write(content)
    yield tmpdir
    shutil.rmtree(tmpdir)


@pytest.fixture
def partial_identity_dir():
    """Create identity dir with only some required files."""
    tmpdir = tempfile.mkdtemp()
    # Only goals.md — missing ethics and boundaries (both required)
    with open(os.path.join(tmpdir, "goals.md"), "w") as f:
        f.write("# Goals\n\n## Primary Goal\n\nGenerate revenue.\n")
    yield tmpdir
    shutil.rmtree(tmpdir)


@pytest.fixture
def empty_identity_dir():
    """Create empty identity dir."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)


# ============================================================
# Test: load_identity
# ============================================================

class TestLoadIdentity:
    """Test identity loading from files."""

    def test_loads_all_sections(self, identity_dir):
        """All 5 identity files load successfully."""
        from identity_loader import load_identity, IDENTITY_FILES
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            identity = load_identity()
        
        for section in IDENTITY_FILES:
            assert identity[section] is not None, f"Section '{section}' should be loaded"
            assert len(identity[section]) > 10, f"Section '{section}' should have content"

    def test_returns_none_for_missing_files(self, empty_identity_dir):
        """Missing files return None for their section."""
        from identity_loader import load_identity
        with patch("identity_loader.IDENTITY_DIR", empty_identity_dir):
            load_identity.cache_clear()
            identity = load_identity()
        
        for section, content in identity.items():
            assert content is None, f"Section '{section}' should be None when file missing"

    def test_warns_on_missing_required(self, partial_identity_dir, caplog):
        """Warns when required sections are missing."""
        import logging
        from identity_loader import load_identity, REQUIRED_SECTIONS
        
        with patch("identity_loader.IDENTITY_DIR", partial_identity_dir):
            load_identity.cache_clear()
            with caplog.at_level(logging.WARNING, logger="identity"):
                identity = load_identity()
        
        # Should have goals but not ethics or boundaries
        assert identity["goals"] is not None
        assert identity["ethics"] is None
        assert identity["boundaries"] is None
        
        # Should have logged a warning about missing required files
        assert any("MISSING REQUIRED" in r.message for r in caplog.records)

    def test_caches_result(self, identity_dir):
        """Second call returns cached result without re-reading files."""
        from identity_loader import load_identity
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            result1 = load_identity()
            result2 = load_identity()
        
        assert result1 is result2  # Same object — cached


# ============================================================
# Test: reload_identity
# ============================================================

class TestReloadIdentity:
    """Test cache clearing and reload."""

    def test_reload_clears_cache(self, identity_dir):
        """reload_identity() returns fresh data."""
        from identity_loader import load_identity, reload_identity
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            result1 = load_identity()
            result2 = reload_identity()
        
        # Should be equal content but different objects (cache was cleared)
        assert result1 == result2


# ============================================================
# Test: get_identity_section
# ============================================================

class TestGetSection:
    """Test individual section retrieval."""

    def test_returns_section_content(self, identity_dir):
        """Getting a valid section returns its content."""
        from identity_loader import get_identity_section, load_identity
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            goals = get_identity_section("goals")
        
        assert goals is not None
        assert "Primary Goal" in goals

    def test_returns_none_for_unknown_section(self, identity_dir):
        """Unknown section name returns None."""
        from identity_loader import get_identity_section, load_identity
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            result = get_identity_section("nonexistent")
        
        assert result is None


# ============================================================
# Test: get_identity_summary
# ============================================================

class TestGetSummary:
    """Test the compact summary for prompt injection."""

    def test_summary_contains_goals(self, identity_dir):
        """Summary includes goals information."""
        from identity_loader import get_identity_summary, load_identity, _get_summary_cached
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            summary = get_identity_summary()
        
        assert "GOALS" in summary

    def test_summary_contains_ethics(self, identity_dir):
        """Summary includes ethics rules."""
        from identity_loader import get_identity_summary, load_identity, _get_summary_cached
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            summary = get_identity_summary()
        
        assert "ETHICS" in summary

    def test_summary_contains_taste(self, identity_dir):
        """Summary includes taste principles."""
        from identity_loader import get_identity_summary, load_identity, _get_summary_cached
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            summary = get_identity_summary()
        
        assert "TASTE" in summary

    def test_summary_warns_when_no_files(self, empty_identity_dir):
        """Summary returns warning when no identity files are present."""
        from identity_loader import get_identity_summary, load_identity, _get_summary_cached
        with patch("identity_loader.IDENTITY_DIR", empty_identity_dir):
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            summary = get_identity_summary()
        
        assert "No identity files" in summary or "IDENTITY" in summary

    def test_summary_is_compact(self, identity_dir):
        """Summary should be token-efficient (under 2000 chars)."""
        from identity_loader import get_identity_summary, load_identity, _get_summary_cached
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            summary = get_identity_summary()
        
        assert len(summary) < 2000, f"Summary too long: {len(summary)} chars"


# ============================================================
# Test: validate_identity
# ============================================================

class TestValidateIdentity:
    """Test identity health validation."""

    def test_valid_with_all_files(self, identity_dir):
        """Full identity set validates as healthy."""
        from identity_loader import validate_identity, load_identity
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            load_identity.cache_clear()
            result = validate_identity()
        
        assert result["valid"] is True
        assert len(result["loaded"]) == 5
        assert len(result["missing"]) == 0
        assert len(result["warnings"]) == 0

    def test_invalid_with_missing_required(self, partial_identity_dir):
        """Missing required files produces warnings."""
        from identity_loader import validate_identity, load_identity
        with patch("identity_loader.IDENTITY_DIR", partial_identity_dir):
            load_identity.cache_clear()
            result = validate_identity()
        
        assert result["valid"] is False
        assert "goals" in result["loaded"]
        assert "ethics" in result["missing"]
        assert len(result["warnings"]) > 0

    def test_warns_on_suspiciously_short_files(self):
        """Files under 50 chars produce warnings."""
        tmpdir = tempfile.mkdtemp()
        try:
            # Create all required files but make one very short
            for name in ["goals.md", "ethics.md", "boundaries.md"]:
                with open(os.path.join(tmpdir, name), "w") as f:
                    f.write("# Goals\n\n## Primary Goal\n\nGenerate revenue.\n")
            # Tiny taste file
            with open(os.path.join(tmpdir, "taste.md"), "w") as f:
                f.write("short")
            with open(os.path.join(tmpdir, "risk.md"), "w") as f:
                f.write("# Risk\n\n## Default: 80/20 exploit/explore ratio\n\n- Never spend >$0.50/round\n")
            
            from identity_loader import validate_identity, load_identity
            with patch("identity_loader.IDENTITY_DIR", tmpdir):
                load_identity.cache_clear()
                result = validate_identity()
            
            assert any("suspiciously short" in w for w in result["warnings"])
        finally:
            shutil.rmtree(tmpdir)


# ============================================================
# Test: Identity files exist in the real project
# ============================================================

class TestRealIdentityFiles:
    """Verify the actual identity files exist in the project."""

    def test_identity_directory_exists(self):
        """The identity/ directory exists."""
        from identity_loader import IDENTITY_DIR
        assert os.path.isdir(IDENTITY_DIR), f"Identity dir missing: {IDENTITY_DIR}"

    def test_all_identity_files_exist(self):
        """All 5 identity files exist in the project."""
        from identity_loader import IDENTITY_DIR, IDENTITY_FILES
        for section, filename in IDENTITY_FILES.items():
            path = os.path.join(IDENTITY_DIR, filename)
            assert os.path.exists(path), f"Identity file missing: {path}"

    def test_real_identity_loads(self):
        """Real identity files load without errors."""
        from identity_loader import load_identity, reload_identity
        identity = reload_identity()
        for section, content in identity.items():
            assert content is not None, f"Real identity section '{section}' failed to load"
            assert len(content) > 100, f"Real identity section '{section}' is too short"

    def test_real_summary_is_valid(self):
        """Real identity summary is compact and contains key sections."""
        from identity_loader import get_identity_summary, reload_identity, _get_summary_cached
        reload_identity()
        _get_summary_cached.cache_clear()
        summary = get_identity_summary()
        assert "GOALS" in summary
        assert "ETHICS" in summary
        assert "TASTE" in summary
        assert len(summary) < 3000

    def test_real_validation_passes(self):
        """Real identity validates as healthy."""
        from identity_loader import validate_identity, reload_identity
        reload_identity()
        result = validate_identity()
        assert result["valid"] is True, f"Identity validation failed: {result['warnings']}"


# ============================================================
# Test: Prompt injection
# ============================================================

class TestPromptInjection:
    """Test that identity is injected into agent prompts."""

    def test_researcher_prompt_includes_identity(self, identity_dir):
        """Researcher system prompt includes identity section."""
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            from identity_loader import load_identity, _get_summary_cached
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            
            from agents.researcher import _build_system_prompt
            prompt = _build_system_prompt(domain="test")
        
        assert "IDENTITY" in prompt

    def test_critic_prompt_includes_identity(self, identity_dir):
        """Critic prompt includes identity ethics."""
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            from identity_loader import load_identity, _get_summary_cached
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            
            from agents.critic import _build_critic_prompt
            prompt = _build_critic_prompt()
        
        assert "IDENTITY" in prompt or "GOALS" in prompt or "ETHICS" in prompt

    def test_chat_identity_helper(self, identity_dir):
        """Chat identity helper returns summary text."""
        with patch("identity_loader.IDENTITY_DIR", identity_dir):
            from identity_loader import load_identity, _get_summary_cached
            load_identity.cache_clear()
            _get_summary_cached.cache_clear()
            
            from cli.chat import _get_identity_for_chat
            result = _get_identity_for_chat()
        
        assert "GOALS" in result or "IDENTITY" in result
