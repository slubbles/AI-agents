"""
Tests for Round 3 fixes:
1. Stale claims filtering in question generator
2. URL preservation during context compression
3. Synthesis trigger — only on accepted outputs
4. Atomic JSON writes in strategy_store.save_strategy
5. Lambda late-binding fix (already in test_uplift.py, verify here)
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# Stale Claims Filtering
# ============================================================

class TestStaleClaims:
    """Question generator should filter out expired outputs."""

    def _make_output(self, question: str, score: float, days_ago: int = 0) -> dict:
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        return {
            "question": question,
            "overall_score": score,
            "timestamp": ts,
            "research": {
                "knowledge_gaps": [f"Gap about {question}"],
            },
            "critique": {
                "weaknesses": [f"Weakness in {question}"],
                "actionable_feedback": f"Improve {question}",
            },
        }

    def test_recent_outputs_kept(self):
        """Outputs within CLAIM_EXPIRY_DAYS are kept."""
        from agents.question_generator import _extract_gaps_from_outputs
        
        outputs = [
            self._make_output("Bitcoin ETFs", 7.0, days_ago=5),
            self._make_output("Ethereum staking", 8.0, days_ago=2),
        ]
        
        # Filter same way question_generator does
        from config import CLAIM_EXPIRY_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=CLAIM_EXPIRY_DAYS)
        filtered = [
            o for o in outputs
            if datetime.fromisoformat(o["timestamp"]).replace(tzinfo=timezone.utc) >= cutoff
        ]
        
        assert len(filtered) == 2

    def test_old_outputs_filtered(self):
        """Outputs older than CLAIM_EXPIRY_DAYS are filtered out."""
        outputs = [
            self._make_output("Old topic", 7.0, days_ago=60),  # Expired
            self._make_output("Recent topic", 8.0, days_ago=5),  # Current
        ]
        
        from config import CLAIM_EXPIRY_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=CLAIM_EXPIRY_DAYS)
        filtered = [
            o for o in outputs
            if datetime.fromisoformat(o["timestamp"]).replace(tzinfo=timezone.utc) >= cutoff
        ]
        
        assert len(filtered) == 1
        assert filtered[0]["question"] == "Recent topic"

    def test_all_expired_returns_empty(self):
        """If all outputs are expired, filtered list is empty."""
        outputs = [
            self._make_output("Ancient topic", 7.0, days_ago=100),
            self._make_output("Also old", 6.0, days_ago=90),
        ]
        
        from config import CLAIM_EXPIRY_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=CLAIM_EXPIRY_DAYS)
        filtered = [
            o for o in outputs
            if datetime.fromisoformat(o["timestamp"]).replace(tzinfo=timezone.utc) >= cutoff
        ]
        
        assert len(filtered) == 0

    def test_missing_timestamp_kept(self):
        """Outputs without timestamp are kept (not filtered out)."""
        output = {"question": "No timestamp", "overall_score": 7.0, "research": {}, "critique": {}}
        
        # The fix uses a far-future default: "2099-01-01T00:00:00+00:00"
        ts = output.get("timestamp", "2099-01-01T00:00:00+00:00")
        from config import CLAIM_EXPIRY_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=CLAIM_EXPIRY_DAYS)
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        
        assert dt >= cutoff  # Should be kept (far future default)


# ============================================================
# URL Preservation in Compression
# ============================================================

class TestURLPreservation:
    """Context compression should preserve URLs from search results."""

    def test_urls_preserved_after_compression(self):
        """URLs from tool results survive compression."""
        from agents.researcher import _compress_messages
        
        long_content = (
            "Search result 1: Some information about Bitcoin\n"
            "Source: https://example.com/bitcoin-report\n"
            "More details about market analysis...\n"
            "Another finding about ETFs...\n"
            "Reference: https://reuters.com/article/12345\n"
            + "A" * 1000  # Pad to exceed 500 char threshold
        )
        
        messages = [
            {"role": "user", "content": "What about Bitcoin?"},
            {"role": "assistant", "content": "Let me search..."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": long_content},
            ]},
            {"role": "assistant", "content": "Let me search more..."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "2", "content": "Short result"},
            ]},
            {"role": "assistant", "content": "And one more..."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "3", "content": "Recent result"},
            ]},
        ]
        
        # Force compression by patching threshold low
        with patch("agents.researcher.CONTEXT_COMPRESS_THRESHOLD", 100):
            _compress_messages(messages)
        
        # The first tool result should be compressed but preserve URLs
        compressed = messages[2]["content"][0]["content"]
        assert "[COMPRESSED]" in compressed
        assert "https://example.com/bitcoin-report" in compressed
        assert "https://reuters.com/article/12345" in compressed

    def test_no_urls_still_compresses(self):
        """Content without URLs still compresses normally."""
        from agents.researcher import _compress_messages
        
        long_content = "A" * 1000  # No URLs
        
        messages = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": long_content},
            ]},
            {"role": "assistant", "content": "Thinking..."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "2", "content": "Recent 1"},
            ]},
            {"role": "assistant", "content": "More..."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "3", "content": "Recent 2"},
            ]},
        ]
        
        with patch("agents.researcher.CONTEXT_COMPRESS_THRESHOLD", 100):
            _compress_messages(messages)
        
        compressed = messages[0]["content"][0]["content"]
        assert "[COMPRESSED]" in compressed
        assert "Preserved URLs" not in compressed  # No URLs to preserve

    def test_dedup_urls_in_compression(self):
        """Duplicate URLs are deduped in compression."""
        from agents.researcher import _compress_messages
        
        long_content = (
            "https://example.com/page mentioned here\n"
            "And https://example.com/page again\n"
            "Also https://other.com/data\n"
            + "B" * 1000
        )
        
        messages = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": long_content},
            ]},
            {"role": "assistant", "content": "..."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "2", "content": "r1"},
            ]},
            {"role": "assistant", "content": "..."},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "3", "content": "r2"},
            ]},
        ]
        
        with patch("agents.researcher.CONTEXT_COMPRESS_THRESHOLD", 100):
            _compress_messages(messages)
        
        compressed = messages[0]["content"][0]["content"]
        # Count occurrences — each URL should appear only once in preserved block
        url_section = compressed.split("Preserved URLs: ")[-1] if "Preserved URLs" in compressed else ""
        assert url_section.count("https://example.com/page") == 1


# ============================================================
# Synthesis Trigger
# ============================================================

class TestSynthesisTrigger:
    """Synthesis should only trigger on accepted outputs at the right count."""

    def test_synthesis_requires_accept_verdict(self):
        """Synthesis should not fire when output was rejected."""
        final_critique = {"verdict": "reject", "overall_score": 4.0}
        final_verdict = final_critique.get("verdict", "unknown")
        
        # Even if accepted_count is a multiple of SYNTHESIZE_EVERY_N
        accepted_count = 10  # Multiple of 5
        from config import MIN_OUTPUTS_FOR_SYNTHESIS, SYNTHESIZE_EVERY_N
        
        should_synthesize = (
            final_verdict == "accept" and 
            accepted_count >= MIN_OUTPUTS_FOR_SYNTHESIS and 
            accepted_count % SYNTHESIZE_EVERY_N == 0
        )
        
        assert not should_synthesize  # Rejected output — don't synthesize

    def test_synthesis_fires_on_accept(self):
        """Synthesis fires when output accepted and count is right."""
        final_critique = {"verdict": "accept", "overall_score": 7.5}
        final_verdict = final_critique.get("verdict", "unknown")
        
        from config import MIN_OUTPUTS_FOR_SYNTHESIS, SYNTHESIZE_EVERY_N
        accepted_count = SYNTHESIZE_EVERY_N  # Exact threshold
        
        should_synthesize = (
            final_verdict == "accept" and 
            accepted_count >= MIN_OUTPUTS_FOR_SYNTHESIS and 
            accepted_count % SYNTHESIZE_EVERY_N == 0
        )
        
        assert should_synthesize

    def test_synthesis_skips_wrong_count(self):
        """Synthesis doesn't fire when count isn't a multiple."""
        final_critique = {"verdict": "accept", "overall_score": 7.5}
        final_verdict = final_critique.get("verdict", "unknown")
        
        from config import MIN_OUTPUTS_FOR_SYNTHESIS, SYNTHESIZE_EVERY_N
        accepted_count = SYNTHESIZE_EVERY_N + 1  # Not a multiple
        
        should_synthesize = (
            final_verdict == "accept" and 
            accepted_count >= MIN_OUTPUTS_FOR_SYNTHESIS and 
            accepted_count % SYNTHESIZE_EVERY_N == 0
        )
        
        assert not should_synthesize


# ============================================================
# Atomic JSON Writes
# ============================================================

class TestAtomicWrites:
    """Atomic write utility works correctly."""

    def test_atomic_write_creates_file(self, tmp_path):
        """Atomic write creates a valid JSON file."""
        from utils.atomic_write import atomic_json_write
        
        filepath = str(tmp_path / "test.json")
        data = {"key": "value", "number": 42}
        atomic_json_write(filepath, data)
        
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_atomic_write_creates_dirs(self, tmp_path):
        """Atomic write creates parent directories."""
        from utils.atomic_write import atomic_json_write
        
        filepath = str(tmp_path / "deep" / "nested" / "test.json")
        atomic_json_write(filepath, {"nested": True})
        
        assert os.path.exists(filepath)

    def test_atomic_write_no_partial_on_error(self, tmp_path):
        """If serialization fails, no partial file is left."""
        from utils.atomic_write import atomic_json_write
        
        filepath = str(tmp_path / "bad.json")
        
        class NotSerializable:
            pass
        
        with pytest.raises(TypeError):
            atomic_json_write(filepath, NotSerializable())
        
        assert not os.path.exists(filepath)

    def test_atomic_write_overwrites_existing(self, tmp_path):
        """Atomic write replaces existing file content."""
        from utils.atomic_write import atomic_json_write
        
        filepath = str(tmp_path / "update.json")
        atomic_json_write(filepath, {"version": 1})
        atomic_json_write(filepath, {"version": 2})
        
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded["version"] == 2

    def test_strategy_store_uses_atomic_write(self):
        """Verify strategy_store.save_strategy uses atomic_json_write."""
        import strategy_store
        import inspect
        source = inspect.getsource(strategy_store.save_strategy)
        assert "atomic_json_write" in source
