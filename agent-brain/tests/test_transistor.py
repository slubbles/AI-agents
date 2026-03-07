"""
Tests for Transistor Core Systems — Bootstrap, Calibration, Lifecycle, Claim Verifier

Zero API calls. All tests use mocks and temp directories.

Run:
    python -m pytest tests/test_transistor.py -v
"""

import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_memory(tmp_path):
    mem_dir = str(tmp_path / "memory")
    os.makedirs(mem_dir)
    with patch("memory_store.MEMORY_DIR", mem_dir), \
         patch("config.MEMORY_DIR", mem_dir):
        yield mem_dir


@pytest.fixture
def tmp_strategy(tmp_path):
    strat_dir = str(tmp_path / "strategies")
    os.makedirs(strat_dir)
    with patch("strategy_store.STRATEGY_DIR", strat_dir), \
         patch("config.STRATEGY_DIR", strat_dir):
        yield strat_dir


def _make_output(domain_dir, score, accepted=True, age_days=0, question="test?"):
    """Helper: write a fake scored output to a domain directory."""
    os.makedirs(domain_dir, exist_ok=True)
    ts = datetime.now(timezone.utc) - timedelta(days=age_days)
    filename = f"{ts.strftime('%Y%m%d_%H%M%S')}_{ts.strftime('%f')}_0_score{int(score)}.json"
    record = {
        "timestamp": ts.isoformat(),
        "domain": os.path.basename(domain_dir),
        "question": question,
        "attempt": 1,
        "strategy_version": "default",
        "research": {"summary": "test", "findings": [], "key_insights": []},
        "critique": {
            "scores": {"accuracy": score, "depth": score, "completeness": score,
                       "specificity": score, "intellectual_honesty": score},
            "overall_score": score,
            "verdict": "accept" if accepted else "reject",
        },
        "overall_score": score,
        "accepted": accepted,
        "verdict": "accept" if accepted else "reject",
    }
    filepath = os.path.join(domain_dir, filename)
    with open(filepath, "w") as f:
        json.dump(record, f)
    return filepath


def _make_kb(domain_dir, claims):
    """Helper: write a fake knowledge base."""
    os.makedirs(domain_dir, exist_ok=True)
    kb = {
        "domain": os.path.basename(domain_dir),
        "synthesized_at": datetime.now(timezone.utc).isoformat(),
        "claims": claims,
    }
    path = os.path.join(domain_dir, "_knowledge_base.json")
    with open(path, "w") as f:
        json.dump(kb, f)
    return path


# ============================================================
# A. Domain Bootstrap Tests
# ============================================================

class TestDomainBootstrap:
    def test_is_cold_empty_domain(self, tmp_memory):
        from domain_bootstrap import is_cold
        assert is_cold("robotics") is True

    def test_is_cold_with_few_outputs(self, tmp_memory):
        from domain_bootstrap import is_cold
        domain_dir = os.path.join(tmp_memory, "robotics")
        for i in range(3):
            _make_output(domain_dir, 7.0)
        # Invalidate cache
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("robotics")
        assert is_cold("robotics") is True

    def test_is_cold_with_enough_outputs(self, tmp_memory):
        from domain_bootstrap import is_cold
        domain_dir = os.path.join(tmp_memory, "robotics")
        for i in range(6):
            _make_output(domain_dir, 7.0)
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("robotics")
        assert is_cold("robotics") is False

    def test_get_bootstrap_status_empty(self, tmp_memory):
        from domain_bootstrap import get_bootstrap_status
        assert get_bootstrap_status("robotics") == {}

    def test_bootstrap_questions_uses_generic_for_unknown_domain(self):
        from domain_bootstrap import get_bootstrap_questions
        questions = get_bootstrap_questions("underwater-basket-weaving", count=3)
        assert len(questions) == 3
        for q in questions:
            assert "underwater-basket-weaving" in q.lower() or len(q) > 10

    def test_bootstrap_questions_uses_curated_when_available(self):
        from domain_bootstrap import get_bootstrap_questions
        questions = get_bootstrap_questions("crypto", count=3)
        assert len(questions) == 3
        assert any("crypto" in q.lower() or "bitcoin" in q.lower() for q in questions)

    def test_bootstrap_status_lifecycle(self, tmp_memory):
        from domain_bootstrap import (
            _save_bootstrap_status, get_bootstrap_status, mark_bootstrap_complete,
        )
        _save_bootstrap_status("robotics", {
            "domain": "robotics",
            "phase": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        status = get_bootstrap_status("robotics")
        assert status["phase"] == "in_progress"

        domain_dir = os.path.join(tmp_memory, "robotics")
        for i in range(6):
            _make_output(domain_dir, 7.0)
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("robotics")

        mark_bootstrap_complete("robotics")
        status = get_bootstrap_status("robotics")
        assert status["phase"] == "complete"

    def test_get_bootstrap_question_returns_sequentially(self, tmp_memory):
        from domain_bootstrap import _save_bootstrap_status, get_bootstrap_question
        _save_bootstrap_status("robotics", {
            "domain": "robotics",
            "phase": "in_progress",
            "bootstrap_questions": ["Q1 first?", "Q2 second?", "Q3 third?"],
        })
        # 0 outputs → first question
        q = get_bootstrap_question("robotics")
        assert q == "Q1 first?"


# ============================================================
# B. Domain Calibration Tests
# ============================================================

class TestDomainCalibration:
    def test_update_domain_stats_no_data(self, tmp_memory):
        from domain_calibration import update_domain_stats
        result = update_domain_stats("empty-domain")
        assert result == {}

    def test_update_domain_stats_computes_correctly(self, tmp_memory):
        from domain_calibration import update_domain_stats
        domain_dir = os.path.join(tmp_memory, "test-domain")
        scores = [5.0, 6.0, 7.0, 8.0, 9.0]
        for s in scores:
            _make_output(domain_dir, s, accepted=(s >= 6))
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("test-domain")

        result = update_domain_stats("test-domain")
        assert result["count"] == 5
        assert abs(result["mean"] - 7.0) < 0.01
        assert result["accepted_count"] == 4
        assert result["rejected_count"] == 1
        assert result["accept_rate"] == 0.8

    def test_get_domain_difficulty_unknown(self, tmp_memory):
        from domain_calibration import get_domain_difficulty
        result = get_domain_difficulty("nonexistent")
        assert result["difficulty"] == "unknown"

    def test_get_domain_difficulty_hard(self, tmp_memory):
        from domain_calibration import update_domain_stats, get_domain_difficulty
        domain_dir = os.path.join(tmp_memory, "hard-domain")
        for _ in range(12):
            _make_output(domain_dir, 4.5, accepted=False)
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("hard-domain")

        update_domain_stats("hard-domain")
        result = get_domain_difficulty("hard-domain")
        assert result["difficulty"] == "hard"

    def test_get_calibration_context_empty(self, tmp_memory):
        from domain_calibration import get_calibration_context
        result = get_calibration_context("nonexistent")
        assert result == ""

    def test_get_normalized_score_passthrough(self, tmp_memory):
        from domain_calibration import get_normalized_score
        assert get_normalized_score(7.0, "nonexistent") == 7.0

    def test_get_normalized_score_adjusts(self, tmp_memory):
        from domain_calibration import update_domain_stats, get_normalized_score
        domain_dir = os.path.join(tmp_memory, "cal-domain")
        for s in [4, 5, 5, 6, 6, 6, 7, 7, 8, 9]:
            _make_output(domain_dir, float(s), accepted=(s >= 6))
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("cal-domain")
        update_domain_stats("cal-domain")

        # A score well above mean should normalize higher
        norm = get_normalized_score(9.0, "cal-domain")
        assert norm > 7.0

    def test_update_all_domains(self, tmp_memory):
        from domain_calibration import update_all_domains
        for domain in ["dom-a", "dom-b"]:
            domain_dir = os.path.join(tmp_memory, domain)
            for s in [5.0, 6.0, 7.0]:
                _make_output(domain_dir, s, accepted=(s >= 6))
            from memory_store import _invalidate_output_cache
            _invalidate_output_cache(domain)

        result = update_all_domains()
        assert "dom-a" in result
        assert "dom-b" in result


# ============================================================
# C. Memory Lifecycle Tests
# ============================================================

class TestMemoryLifecycle:
    def test_maintenance_disabled(self, tmp_memory):
        with patch("memory_lifecycle.MAINTENANCE_ENABLED", False):
            from memory_lifecycle import run_maintenance
            result = run_maintenance("test-domain")
            assert result["skipped"] is True

    def test_maintenance_empty_domain(self, tmp_memory):
        from memory_lifecycle import run_maintenance
        result = run_maintenance("empty-domain")
        assert result.get("skipped") is True

    def test_maintenance_runs_on_populated_domain(self, tmp_memory):
        domain_dir = os.path.join(tmp_memory, "pop-domain")
        for s in [5.0, 6.0, 7.0, 8.0]:
            _make_output(domain_dir, s, accepted=(s >= 6))
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("pop-domain")

        with patch("memory_lifecycle.CLAIM_VERIFY_ENABLED", False):
            from memory_lifecycle import run_maintenance
            result = run_maintenance("pop-domain", verbose=False)
            assert result["domain"] == "pop-domain"
            assert "actions" in result

    def test_maintenance_all(self, tmp_memory):
        for domain in ["d1", "d2"]:
            domain_dir = os.path.join(tmp_memory, domain)
            for s in [6.0, 7.0, 8.0]:
                _make_output(domain_dir, s)
            from memory_store import _invalidate_output_cache
            _invalidate_output_cache(domain)

        with patch("memory_lifecycle.CLAIM_VERIFY_ENABLED", False):
            from memory_lifecycle import run_maintenance_all
            result = run_maintenance_all(verbose=False)
            assert result["total_domains"] == 2


# ============================================================
# D. Claim Verifier Tests
# ============================================================

class TestClaimVerifier:
    def test_get_verifiable_claims_empty(self, tmp_memory):
        from agents.claim_verifier import _get_verifiable_claims
        result = _get_verifiable_claims("empty-domain")
        assert result == []

    def test_get_verifiable_claims_filters_by_confidence(self, tmp_memory):
        domain_dir = os.path.join(tmp_memory, "cv-domain")
        claims = [
            {"id": "c1", "claim": "High conf claim", "confidence": "high", "status": "active"},
            {"id": "c2", "claim": "Low conf claim", "confidence": "low", "status": "active"},
            {"id": "c3", "claim": "Medium conf claim", "confidence": "medium", "status": "active"},
            {"id": "c4", "claim": "Expired claim", "confidence": "high", "status": "expired"},
        ]
        _make_kb(domain_dir, claims)

        with patch("agents.claim_verifier.CLAIM_VERIFY_MIN_CONFIDENCE", "high"):
            from agents.claim_verifier import _get_verifiable_claims
            result = _get_verifiable_claims("cv-domain")
            assert len(result) == 1
            assert result[0]["id"] == "c1"

    def test_get_verifiable_claims_skips_recently_verified(self, tmp_memory):
        domain_dir = os.path.join(tmp_memory, "cv2-domain")
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        claims = [
            {"id": "c1", "claim": "Recently verified", "confidence": "high",
             "status": "active", "_last_verified": recent},
            {"id": "c2", "claim": "Never verified", "confidence": "high",
             "status": "active"},
        ]
        _make_kb(domain_dir, claims)

        from agents.claim_verifier import _get_verifiable_claims
        result = _get_verifiable_claims("cv2-domain")
        assert len(result) == 1
        assert result[0]["id"] == "c2"

    def test_build_search_query(self):
        from agents.claim_verifier import _build_search_query
        claim = {"claim": "Bitcoin reached $100,000 in December 2025 after SEC approved multiple ETFs"}
        query = _build_search_query(claim)
        assert len(query) > 10
        assert "that" not in query.lower().split()

    def test_get_claim_verification_stats_empty(self, tmp_memory):
        from agents.claim_verifier import get_claim_verification_stats
        result = get_claim_verification_stats("empty-domain")
        assert result["total"] == 0

    def test_get_claim_verification_stats_computes(self, tmp_memory):
        domain_dir = os.path.join(tmp_memory, "stats-domain")
        claims = [
            {"id": "c1", "claim": "Verified true", "confidence": "high",
             "status": "active", "_last_verified": "2026-01-01", "_verification_verdict": "confirmed"},
            {"id": "c2", "claim": "Verified false", "confidence": "high",
             "status": "disputed", "_last_verified": "2026-01-01", "_verification_verdict": "refuted"},
            {"id": "c3", "claim": "Not verified", "confidence": "high", "status": "active"},
        ]
        _make_kb(domain_dir, claims)

        from agents.claim_verifier import get_claim_verification_stats
        result = get_claim_verification_stats("stats-domain")
        assert result["total_active"] == 3
        assert result["verified"] == 2
        assert result["unverified"] == 1
        assert result["verdicts"]["confirmed"] == 1
        assert result["verdicts"]["refuted"] == 1


# ============================================================
# E. Brain-to-Hands Handoff Tests
# ============================================================

class TestHandoffClassification:
    def test_action_verbs_cover_non_coding_domains(self):
        from main import _ACTION_VERBS
        non_coding_verbs = ["analyze", "evaluate", "survey", "contact",
                           "negotiate", "propose", "pitch", "assess"]
        for verb in non_coding_verbs:
            assert verb in _ACTION_VERBS, f"Missing non-coding verb: {verb}"

    def test_classify_task_priority(self):
        from main import _classify_task_priority
        assert _classify_task_priority("build", "insight") == "high"
        assert _classify_task_priority("deploy", "insight") == "high"
        assert _classify_task_priority("action", "insight") == "medium"
        assert _classify_task_priority("action", "gap") == "low"
        assert _classify_task_priority("build", "gap") == "low"

    def test_handoff_detects_broad_verbs(self):
        """Verify that non-technical insights still generate tasks."""
        from main import _ACTION_VERBS

        biotech_insight = "Monitor Phase 3 clinical trial results for the new mRNA therapy"
        crypto_insight = "Track regulatory developments in EU MiCA framework"
        business_insight = "Contact potential partners for distribution agreement"

        for insight in [biotech_insight, crypto_insight, business_insight]:
            found = False
            for verb in _ACTION_VERBS:
                if verb in insight.lower():
                    found = True
                    break
            assert found, f"No verb matched for: {insight}"


# ============================================================
# F. Error Path Tests
# ============================================================

class TestErrorPaths:
    def test_bootstrap_survives_missing_llm_router(self, tmp_memory):
        """Bootstrap should not crash if LLM router is unavailable."""
        from domain_bootstrap import generate_orientation
        with patch("domain_bootstrap.call_llm", side_effect=ImportError("no module")):
            result = generate_orientation("test-domain")
            # Should return None, not crash
            assert result is None

    def test_calibration_survives_corrupt_file(self, tmp_memory):
        """Calibration should handle corrupt calibration file gracefully."""
        from domain_calibration import _load_calibration
        cal_path = os.path.join(tmp_memory, "_calibration.json")
        with open(cal_path, "w") as f:
            f.write("not valid json{{{")
        with patch("domain_calibration.CALIBRATION_FILE", cal_path):
            result = _load_calibration()
            assert "domains" in result

    def test_lifecycle_survives_partial_failure(self, tmp_memory):
        """Maintenance should continue even if one step fails."""
        domain_dir = os.path.join(tmp_memory, "fail-domain")
        for s in [6.0, 7.0, 8.0]:
            _make_output(domain_dir, s)
        from memory_store import _invalidate_output_cache
        _invalidate_output_cache("fail-domain")

        with patch("memory_lifecycle.expire_stale_claims", side_effect=Exception("boom")), \
             patch("memory_lifecycle.CLAIM_VERIFY_ENABLED", False):
            from memory_lifecycle import run_maintenance
            result = run_maintenance("fail-domain", verbose=False)
            assert any(a.get("error") for a in result["actions"])
            # Should still have attempted other actions
            assert len(result["actions"]) > 1
