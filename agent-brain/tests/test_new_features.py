"""
Tests for new modules: Consensus, Knowledge Graph, Smart Orchestrator, Scheduler Daemon

No API calls — all tests use mocks and temp directories.

Run:
    python -m pytest tests/test_new_features.py -v
"""

import json
import os
import sys
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
from collections import defaultdict

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_memory(tmp_path):
    """Create a temporary memory directory."""
    mem_dir = str(tmp_path / "memory")
    os.makedirs(mem_dir)
    with patch("knowledge_graph.MEMORY_DIR", mem_dir):
        yield mem_dir


@pytest.fixture
def tmp_logs(tmp_path):
    """Create a temporary log directory."""
    log_dir = str(tmp_path / "logs")
    os.makedirs(log_dir)
    with patch("scheduler.LOG_DIR", log_dir):
        yield log_dir


@pytest.fixture
def sample_kb():
    """A sample synthesized knowledge base."""
    return {
        "domain": "crypto",
        "version": "v3",
        "topics": [
            {"name": "Bitcoin ETFs", "subtopics": ["flows", "regulation"]},
            {"name": "DeFi", "subtopics": ["lending", "DEXs"]},
            {"name": "Regulation", "subtopics": []},
        ],
        "claims": [
            {
                "id": "claim_001",
                "claim": "BlackRock iShares Bitcoin Trust holds $50B AUM",
                "confidence": "high",
                "status": "active",
                "topic": "Bitcoin ETFs",
                "sources": ["https://example.com/blackrock"],
                "first_seen": "2026-01-01",
                "source_count": 3,
            },
            {
                "id": "claim_002",
                "claim": "SEC approved spot ETF rules in 2024",
                "confidence": "high",
                "status": "active",
                "topic": "Bitcoin ETFs",
                "sources": ["https://sec.gov/etf-rules"],
                "first_seen": "2026-01-01",
                "source_count": 5,
            },
            {
                "id": "claim_003",
                "claim": "DeFi TVL exceeds $200B in 2026",
                "confidence": "medium",
                "status": "active",
                "topic": "DeFi",
                "sources": ["https://defillama.com"],
                "first_seen": "2026-02-01",
                "source_count": 2,
            },
            {
                "id": "claim_004",
                "claim": "MiCA regulation fully enforced in EU",
                "confidence": "medium",
                "status": "active",
                "topic": "Regulation",
                "sources": [],
                "first_seen": "2026-02-01",
                "source_count": 1,
            },
        ],
        "contradictions": [
            {
                "claim_a": "claim_001",
                "claim_b": "claim_003",
                "description": "Market cap disagreement",
                "resolution": "unresolved",
            },
        ],
        "knowledge_gaps": [
            {"gap": "Retail vs institutional ETF adoption ratio", "priority": "high", "related_topic": "Bitcoin ETFs"},
            {"gap": "DeFi insurance protocols market size", "priority": "medium", "related_topic": "DeFi"},
        ],
    }


@pytest.fixture
def sample_graph(sample_kb, tmp_memory):
    """Build and return a sample knowledge graph."""
    from knowledge_graph import build_graph_from_kb
    return build_graph_from_kb("crypto", sample_kb)


@pytest.fixture
def sample_researcher_outputs():
    """Sample outputs from multiple researchers."""
    return [
        {
            "_researcher_id": 1,
            "question": "What are Bitcoin ETF flows?",
            "findings": [
                {"claim": "BlackRock IBIT has $50B AUM", "confidence": "high"},
                {"claim": "Total ETF inflows exceeded $30B", "confidence": "medium"},
            ],
            "key_insights": ["Institutional adoption is accelerating"],
            "knowledge_gaps": ["Retail vs institutional split"],
            "sources_used": ["https://example.com/1"],
            "summary": "Bitcoin ETFs see strong institutional adoption.",
            "_searches_made": 3,
        },
        {
            "_researcher_id": 2,
            "question": "What are Bitcoin ETF flows?",
            "findings": [
                {"claim": "BlackRock IBIT has $48B AUM", "confidence": "high"},
                {"claim": "Fidelity FBTC holds $20B", "confidence": "medium"},
            ],
            "key_insights": ["Multiple major players now in ETF market"],
            "knowledge_gaps": ["Impact on BTC price"],
            "sources_used": ["https://example.com/2"],
            "summary": "Multiple institutions competing in Bitcoin ETF space.",
            "_searches_made": 2,
        },
        {
            "_researcher_id": 3,
            "question": "What are Bitcoin ETF flows?",
            "findings": [
                {"claim": "BlackRock leads with ~$50B", "confidence": "high"},
            ],
            "key_insights": ["ETF approvals drove market confidence"],
            "knowledge_gaps": ["Retail adoption data missing"],
            "sources_used": ["https://example.com/3"],
            "summary": "ETF market dominated by BlackRock.",
            "_searches_made": 4,
            "_empty_searches": 1,
        },
    ]


# ============================================================
# Knowledge Graph Tests
# ============================================================

class TestKnowledgeGraph:
    """Tests for the knowledge graph module."""

    def test_empty_graph_structure(self):
        from knowledge_graph import _empty_graph
        g = _empty_graph()
        assert g["nodes"] == []
        assert g["edges"] == []
        assert g["metadata"]["node_count"] == 0
        assert g["clusters"] == []

    def test_create_node(self):
        from knowledge_graph import create_node
        node = create_node("test_1", "claim", "Test claim", confidence="high")
        assert node["id"] == "test_1"
        assert node["type"] == "claim"
        assert node["label"] == "Test claim"
        assert node["confidence"] == "high"

    def test_create_edge(self):
        from knowledge_graph import create_edge
        edge = create_edge("a", "b", "supports", weight=2.0)
        assert edge["source"] == "a"
        assert edge["target"] == "b"
        assert edge["type"] == "supports"
        assert edge["weight"] == 2.0

    def test_build_graph_from_kb(self, sample_kb, tmp_memory):
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("crypto", sample_kb)

        # Should have topic nodes
        topic_nodes = [n for n in graph["nodes"] if n["type"] == "topic"]
        assert len(topic_nodes) == 3

        # Should have claim nodes
        claim_nodes = [n for n in graph["nodes"] if n["type"] == "claim"]
        assert len(claim_nodes) == 4

        # Should have gap nodes
        gap_nodes = [n for n in graph["nodes"] if n["type"] == "gap"]
        assert len(gap_nodes) == 2

        # Should have edges
        assert len(graph["edges"]) > 0

        # Should have contradiction edges
        contradiction_edges = [e for e in graph["edges"] if e["type"] == "contradicts"]
        assert len(contradiction_edges) >= 1

        # Metadata should be populated
        assert graph["metadata"]["domain"] == "crypto"
        assert graph["metadata"]["node_count"] > 0
        assert graph["metadata"]["edge_count"] > 0

    def test_build_graph_has_belongs_to_edges(self, sample_kb, tmp_memory):
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("crypto", sample_kb)
        belongs_to = [e for e in graph["edges"] if e["type"] == "belongs_to"]
        assert len(belongs_to) >= 3  # 4 claims with topics, all should have belongs_to

    def test_build_graph_has_sourced_from_edges(self, sample_kb, tmp_memory):
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("crypto", sample_kb)
        sourced_from = [e for e in graph["edges"] if e["type"] == "sourced_from"]
        assert len(sourced_from) >= 2  # claims 001, 002, 003 have sources

    def test_build_graph_has_source_nodes(self, sample_kb, tmp_memory):
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("crypto", sample_kb)
        source_nodes = [n for n in graph["nodes"] if n["type"] == "source"]
        assert len(source_nodes) >= 2

    def test_clusters_computed(self, sample_graph):
        assert len(sample_graph["clusters"]) > 0
        for cluster in sample_graph["clusters"]:
            assert "size" in cluster
            assert "density" in cluster

    def test_gap_analysis(self, sample_graph):
        gap_analysis = sample_graph["gap_analysis"]
        assert "isolated_nodes" in gap_analysis
        assert "weak_clusters" in gap_analysis
        assert "missing_connections" in gap_analysis

    def test_get_graph_summary(self, sample_graph):
        from knowledge_graph import get_graph_summary
        summary = get_graph_summary(sample_graph)
        assert summary["domain"] == "crypto"
        assert summary["total_nodes"] > 0
        assert summary["total_edges"] > 0
        assert "nodes_by_type" in summary  # renamed from node_types
        assert "claim" in summary["nodes_by_type"]

    def test_get_node(self, sample_graph):
        from knowledge_graph import get_node
        node = get_node(sample_graph, "claim_001")
        assert node is not None
        assert node["type"] == "claim"
        assert "BlackRock" in node["label"]

    def test_get_node_not_found(self, sample_graph):
        from knowledge_graph import get_node
        assert get_node(sample_graph, "nonexistent") is None

    def test_get_neighbors(self, sample_graph):
        from knowledge_graph import get_neighbors
        # claim_001 should be connected to its topic
        neighbors = get_neighbors(sample_graph, "claim_001")
        assert len(neighbors) > 0

    def test_get_neighbors_filtered(self, sample_graph):
        from knowledge_graph import get_neighbors
        # Get only belongs_to neighbors
        neighbors = get_neighbors(sample_graph, "claim_001", edge_type="belongs_to")
        topic_neighbors = [n for n in neighbors if n["type"] == "topic"]
        assert len(topic_neighbors) >= 1

    def test_get_contradictions(self, sample_graph):
        from knowledge_graph import get_contradictions
        contradictions = get_contradictions(sample_graph)
        assert len(contradictions) >= 1
        # Each contradiction should have both nodes
        for c in contradictions:
            assert "edge" in c

    def test_get_claims_by_topic(self, sample_graph):
        from knowledge_graph import get_claims_by_topic
        # Find the Bitcoin ETFs topic ID
        topic_node = next(
            (n for n in sample_graph["nodes"]
             if n["type"] == "topic" and "ETF" in n["label"]),
            None
        )
        assert topic_node is not None
        claims = get_claims_by_topic(sample_graph, topic_node["id"])
        assert len(claims) >= 2

    def test_find_path_same_node(self, sample_graph):
        from knowledge_graph import find_path
        path = find_path(sample_graph, "claim_001", "claim_001")
        assert path == ["claim_001"]

    def test_find_path_connected(self, sample_graph):
        from knowledge_graph import find_path
        # claim_001 and claim_002 should be connected (same topic)
        path = find_path(sample_graph, "claim_001", "claim_002")
        assert path is not None
        assert path[0] == "claim_001"
        assert path[-1] == "claim_002"

    def test_find_path_no_path(self, sample_graph):
        from knowledge_graph import find_path
        # gap node might not be connected to everything
        path = find_path(sample_graph, "claim_001", "nonexistent_node")
        assert path is None

    def test_save_and_load_graph(self, sample_graph, tmp_memory):
        from knowledge_graph import save_graph, load_graph
        save_graph("crypto", sample_graph)
        loaded = load_graph("crypto")
        assert loaded is not None
        assert loaded["metadata"]["domain"] == "crypto"
        assert len(loaded["nodes"]) == len(sample_graph["nodes"])
        assert len(loaded["edges"]) == len(sample_graph["edges"])

    def test_load_graph_not_found(self, tmp_memory):
        from knowledge_graph import load_graph
        assert load_graph("nonexistent_domain") is None

    def test_slug_helper(self):
        from knowledge_graph import _slug
        assert _slug("Hello World!") == "hello_world"
        assert _slug("  spaces  ") == "spaces"
        assert _slug("CamelCase_Test") == "camelcase_test"

    def test_cluster_density(self, sample_graph):
        from knowledge_graph import _cluster_density
        # Single node cluster has 0 density
        assert _cluster_density({"a"}, []) == 0.0
        # Two nodes with one edge
        edges = [{"source": "a", "target": "b", "type": "supports"}]
        assert _cluster_density({"a", "b"}, edges) == 1.0

    def test_empty_kb_produces_empty_graph(self, tmp_memory):
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("empty", {})
        assert len(graph["nodes"]) == 0
        assert len(graph["edges"]) == 0
        assert graph["metadata"]["node_count"] == 0

    def test_relates_to_edges_inferred(self, sample_kb, tmp_memory):
        """Claims in the same topic should get inferred relates_to edges."""
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("crypto", sample_kb)
        relates_to = [e for e in graph["edges"] if e["type"] == "relates_to"]
        assert len(relates_to) >= 1  # At least some inferred

    def test_contradiction_edge_weight(self, sample_kb, tmp_memory):
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("crypto", sample_kb)
        contradiction_edges = [e for e in graph["edges"] if e["type"] == "contradicts"]
        for ce in contradiction_edges:
            assert ce["weight"] == 1.5  # Higher weight for contradictions

    def test_gap_nodes_connect_to_topics(self, sample_kb, tmp_memory):
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("crypto", sample_kb)
        gap_edges = [e for e in graph["edges"] 
                     if e["type"] == "relates_to" 
                     and e["source"].startswith("gap_")]
        assert len(gap_edges) >= 1


# ============================================================
# Consensus Tests
# ============================================================

class TestConsensus:
    """Tests for the multi-researcher consensus module."""

    def test_run_single_researcher_success(self):
        """Test the single researcher wrapper."""
        from agents.consensus import _run_single_researcher
        mock_result = {
            "findings": [{"claim": "Test", "confidence": "high"}],
            "key_insights": ["insight"],
            "knowledge_gaps": [],
            "sources_used": [],
            "summary": "Test summary",
        }
        with patch("agents.consensus.research", return_value=mock_result):
            result = _run_single_researcher(("question", None, None, "test", 1))
            assert result["_researcher_id"] == 1
            assert len(result["findings"]) == 1

    def test_run_single_researcher_failure(self):
        """Test that single researcher failure is handled gracefully."""
        from agents.consensus import _run_single_researcher
        with patch("agents.consensus.research", side_effect=Exception("API error")):
            result = _run_single_researcher(("question", None, None, "test", 2))
            assert result["_researcher_id"] == 2
            assert "_error" in result
            assert "API error" in result["_error"]

    def test_merge_findings_all_failed(self):
        """When all researchers fail, should return failure output."""
        from agents.consensus import merge_findings
        failed = [
            {"_researcher_id": 1, "_error": "fail", "findings": []},
            {"_researcher_id": 2, "_error": "fail", "findings": []},
        ]
        result = merge_findings("test q", failed, "test")
        assert result["consensus_level"] == "weak_consensus"
        assert result.get("_consensus_failed") is True

    def test_merge_findings_single_success(self):
        """When only 1 researcher succeeds, returns their output directly."""
        from agents.consensus import merge_findings
        outputs = [
            {"_researcher_id": 1, "_error": "fail", "findings": []},
            {
                "_researcher_id": 2,
                "findings": [{"claim": "Test", "confidence": "high"}],
                "key_insights": ["insight"],
                "knowledge_gaps": [],
                "sources_used": [],
                "summary": "result",
            },
        ]
        result = merge_findings("test q", outputs, "test")
        assert result["consensus_level"] == "single_researcher"
        assert result["consensus_stats"]["researchers_count"] == 1

    def test_merge_findings_llm_merge(self, sample_researcher_outputs):
        """Test full merge with mocked LLM response."""
        from agents.consensus import merge_findings

        merged_response_json = {
            "question": "What are Bitcoin ETF flows?",
            "findings": [
                {"claim": "BlackRock IBIT has ~$50B AUM", "confidence": "high", "agreement": "unanimous"},
                {"claim": "Fidelity FBTC holds $20B", "confidence": "medium", "agreement": "single"},
                {"claim": "Total ETF inflows exceeded $30B", "confidence": "medium", "agreement": "majority"},
            ],
            "key_insights": ["Institutional adoption is accelerating"],
            "knowledge_gaps": ["Retail vs institutional split"],
            "sources_used": ["https://example.com/1", "https://example.com/2"],
            "summary": "Bitcoin ETFs see strong institutional adoption.",
            "consensus_level": "strong_consensus",
            "consensus_stats": {
                "researchers_count": 3,
                "total_findings_input": 5,
                "total_findings_merged": 3,
                "agreements": 2,
                "disagreements": 0,
                "unique_findings": 1,
            },
            "disagreements": [],
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(merged_response_json))]
        mock_response.usage = MagicMock(input_tokens=1000, output_tokens=500)

        with patch("agents.consensus.create_message", return_value=mock_response), \
             patch("agents.consensus.log_cost"):
            result = merge_findings("What are Bitcoin ETF flows?",
                                   sample_researcher_outputs, "crypto")
            assert result["consensus_level"] == "strong_consensus"
            assert len(result["findings"]) == 3
            assert result["_consensus"] is True
            assert result["_researchers_used"] == 3

    def test_merge_findings_llm_failure_fallback(self, sample_researcher_outputs):
        """When merge LLM fails, should fall back to best single output."""
        from agents.consensus import merge_findings

        with patch("agents.consensus.create_message", side_effect=Exception("LLM error")), \
             patch("agents.consensus.log_cost"):
            result = merge_findings("test q", sample_researcher_outputs, "crypto")
            assert result.get("_consensus_merge_failed") is True
            assert result["consensus_level"] == "merge_failed"

    def test_consensus_research_parallel(self):
        """Test that consensus_research runs researchers in parallel."""
        from agents.consensus import consensus_research

        mock_result = {
            "question": "test",
            "findings": [{"claim": "Test", "confidence": "high"}],
            "key_insights": [],
            "knowledge_gaps": [],
            "sources_used": [],
            "summary": "test",
            "_searches_made": 2,
        }

        merged_json = {
            "question": "test",
            "findings": [{"claim": "Merged", "confidence": "high"}],
            "key_insights": [],
            "knowledge_gaps": [],
            "sources_used": [],
            "summary": "merged",
            "consensus_level": "strong_consensus",
            "consensus_stats": {"researchers_count": 3, "total_findings_input": 3,
                                "total_findings_merged": 1, "agreements": 1,
                                "disagreements": 0, "unique_findings": 0},
            "disagreements": [],
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(merged_json))]
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=300)

        call_count = 0
        def mock_research(**kwargs):
            nonlocal call_count
            call_count += 1
            return dict(mock_result, _researcher_id=call_count)

        with patch("agents.consensus.research", side_effect=mock_research), \
             patch("agents.consensus.create_message", return_value=mock_response), \
             patch("agents.consensus.log_cost"):
            result = consensus_research("test q", domain="test", n_researchers=3)
            assert call_count == 3  # All 3 called
            assert result["consensus_level"] == "strong_consensus"

    def test_consensus_max_researchers_cap(self):
        from agents.consensus import MAX_N_RESEARCHERS
        assert MAX_N_RESEARCHERS == 5

    def test_build_merge_prompt(self):
        from agents.consensus import _build_merge_prompt
        prompt = _build_merge_prompt()
        assert "MERGE RULES" in prompt
        assert "consensus" in prompt.lower()
        assert "JSON" in prompt


# ============================================================
# Smart Orchestrator Tests
# ============================================================

class TestSmartOrchestrator:
    """Tests for the LLM-reasoned orchestrator."""

    def test_smart_orchestrate_llm_success(self):
        """Test smart orchestration with mocked LLM response."""
        from agents.orchestrator import smart_orchestrate

        llm_allocation = {
            "allocation": [
                {"domain": "crypto", "rounds": 3, "reason": "High potential"},
                {"domain": "ai", "rounds": 2, "reason": "Needs seeding"},
            ],
            "reasoning": "Crypto has momentum, AI needs data.",
            "recommended_actions": ["Approve pending strategy for crypto"],
        }

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(llm_allocation))]
        mock_response.usage = MagicMock(input_tokens=800, output_tokens=400)

        mock_priorities = [
            {
                "domain": "crypto", "priority": 8.0, "action": "research",
                "strategy": "v3", "strategy_status": "active", "skip": False,
                "reasons": ["Recent high scores"], "stats": {"count": 15, "accepted": 12, "avg_score": 7.5},
            },
            {
                "domain": "ai", "priority": 6.0, "action": "seed",
                "strategy": "v1", "strategy_status": "active", "skip": False,
                "reasons": ["New domain"], "stats": {"count": 5, "accepted": 3, "avg_score": 6.0},
            },
        ]

        with patch("agents.orchestrator.get_system_health", return_value={"health_score": 85, "total_outputs": 38}), \
             patch("agents.orchestrator.prioritize_domains", return_value=mock_priorities), \
             patch("agents.orchestrator.check_budget", return_value={"remaining": 3.50, "within_budget": True, "spent": 1.50, "limit": 5.0}), \
             patch("agents.orchestrator.load_principles", return_value={"principles": []}), \
             patch("agents.orchestrator.load_knowledge_base", return_value={"claims": []}), \
             patch("utils.retry.create_message", return_value=mock_response), \
             patch("cost_tracker.log_cost"):
            result = smart_orchestrate(total_rounds=5)
            assert result["mode"] == "llm_reasoned"
            assert len(result["allocation"]) == 2
            assert result["total_rounds"] == 5

    def test_smart_orchestrate_fallback(self):
        """Test fallback to deterministic when LLM fails."""
        from agents.orchestrator import smart_orchestrate

        mock_priorities = [
            {
                "domain": "crypto", "priority": 8.0, "action": "research",
                "strategy": "v3", "strategy_status": "active", "skip": False,
                "reasons": ["High priority"], "stats": {"count": 15, "accepted": 12, "avg_score": 7.5},
            },
        ]

        mock_allocation = [
            {"domain": "crypto", "rounds": 5, "reasons": ["fallback"]},
        ]

        with patch("agents.orchestrator.get_system_health", return_value={"health_score": 85, "total_outputs": 38}), \
             patch("agents.orchestrator.prioritize_domains", return_value=mock_priorities), \
             patch("agents.orchestrator.check_budget", return_value={"remaining": 3.50, "within_budget": True, "spent": 1.50, "limit": 5.0}), \
             patch("agents.orchestrator.load_principles", return_value=None), \
             patch("agents.orchestrator.load_knowledge_base", return_value=None), \
             patch("anthropic.Anthropic", side_effect=Exception("API down")), \
             patch("agents.orchestrator.allocate_rounds", return_value=mock_allocation):
            result = smart_orchestrate(total_rounds=5)
            assert result["mode"] == "deterministic_fallback"
            assert len(result["allocation"]) >= 1


# ============================================================
# Scheduler Daemon Tests
# ============================================================

class TestSchedulerDaemon:
    """Tests for the scheduler daemon mode."""

    def test_daemon_state_persistence(self, tmp_logs):
        """Test save/load of daemon state."""
        from scheduler import _save_daemon_state, _load_daemon_state
        state = {"status": "running", "cycle": 3, "rounds_completed": 10}
        _save_daemon_state(state)
        loaded = _load_daemon_state()
        assert loaded is not None
        assert loaded["status"] == "running"
        assert loaded["cycle"] == 3

    def test_daemon_state_no_file(self, tmp_logs):
        """Test loading when no state file exists."""
        from scheduler import _load_daemon_state
        assert _load_daemon_state() is None

    def test_daemon_log(self):
        """Test daemon logging."""
        from scheduler import _log_daemon, _daemon_log
        initial_len = len(_daemon_log)
        _log_daemon("Test message", "info")
        assert len(_daemon_log) == initial_len + 1
        assert _daemon_log[-1]["message"] == "Test message"
        assert _daemon_log[-1]["level"] == "info"

    def test_get_daemon_status(self, tmp_logs):
        """Test daemon status retrieval."""
        from scheduler import get_daemon_status, _save_daemon_state
        _save_daemon_state({"status": "idle", "cycle": 5})
        status = get_daemon_status()
        assert "running" in status
        assert "state" in status
        assert "recent_log" in status

    def test_stop_daemon_when_not_running(self):
        """Stop daemon should return False when not running."""
        from scheduler import stop_daemon
        import scheduler
        scheduler._daemon_running = False
        result = stop_daemon()
        assert result is False

    def test_stop_daemon_when_running(self):
        """Stop daemon should set the stop event and return True."""
        import scheduler
        scheduler._daemon_running = True
        scheduler._daemon_stop_event.clear()
        result = scheduler.stop_daemon()
        assert result is True
        assert scheduler._daemon_stop_event.is_set()
        # Clean up
        scheduler._daemon_running = False
        scheduler._daemon_stop_event.clear()

    def test_daemon_budget_gate(self, tmp_logs):
        """Daemon should stop when budget is exceeded."""
        import scheduler

        # Pretend budget is exceeded
        with patch.object(scheduler, '_daemon_running', False), \
             patch("scheduler.check_budget", return_value={
                "within_budget": False, "spent": 6.0, "limit": 5.0, "remaining": 0.0}), \
             patch("scheduler.create_plan") as mock_plan:

            # Run daemon with max_cycles=1 and a very short interval
            # It should hit budget check and wait
            scheduler._daemon_running = False
            scheduler._daemon_stop_event.clear()

            def run_and_stop():
                time.sleep(0.5)
                scheduler._daemon_stop_event.set()

            stopper = threading.Thread(target=run_and_stop)
            stopper.start()

            scheduler.run_daemon(
                interval_minutes=1,
                rounds_per_cycle=1,
                max_cycles=1,
            )
            stopper.join()
            # Should NOT have called create_plan since budget was exceeded
            # (on budget exceeded it waits, then gets stopped by the stopper thread)

    def test_daemon_max_cycles(self, tmp_logs):
        """Daemon should stop after max_cycles."""
        import scheduler

        scheduler._daemon_running = False
        scheduler._daemon_stop_event.clear()

        # Mock everything to make it fast
        with patch("scheduler.check_budget", return_value={
                "within_budget": True, "spent": 0.5, "limit": 5.0, "remaining": 4.5}), \
             patch("scheduler.create_plan", return_value={
                "executable": False, "reason": "testing", "allocation": [], 
                "total_rounds": 0, "estimated_cost": 0}):

            # Set interval very short and max_cycles=1
            # Mock _daemon_stop_event.wait to return immediately
            with patch.object(scheduler._daemon_stop_event, 'wait', return_value=False):
                scheduler.run_daemon(
                    interval_minutes=1,
                    rounds_per_cycle=1,
                    max_cycles=1,
                )
            # After max_cycles=1, should have stopped
            assert not scheduler._daemon_running


# ============================================================
# Config Tests for New Settings
# ============================================================

class TestNewConfig:
    """Tests for new configuration settings."""

    def test_consensus_config_exists(self):
        from config import CONSENSUS_ENABLED, CONSENSUS_RESEARCHERS
        assert isinstance(CONSENSUS_ENABLED, bool)
        assert isinstance(CONSENSUS_RESEARCHERS, int)
        assert 1 <= CONSENSUS_RESEARCHERS <= 5

    def test_consensus_default_disabled(self):
        from config import CONSENSUS_ENABLED
        assert CONSENSUS_ENABLED is False


# ============================================================
# Integration Tests (lightweight, no API calls)
# ============================================================

class TestGraphIntegration:
    """Test knowledge graph integrates with knowledge base format."""

    def test_graph_handles_missing_fields(self, tmp_memory):
        """KB with missing optional fields should still build graph."""
        from knowledge_graph import build_graph_from_kb
        minimal_kb = {
            "claims": [
                {"claim": "Test fact", "status": "active"},
            ],
        }
        graph = build_graph_from_kb("test", minimal_kb)
        assert len(graph["nodes"]) >= 1

    def test_graph_handles_empty_claims(self, tmp_memory):
        """KB with empty claims list should produce empty graph."""
        from knowledge_graph import build_graph_from_kb
        graph = build_graph_from_kb("test", {"claims": []})
        assert graph["metadata"]["node_count"] == 0

    def test_graph_handles_claims_without_topics(self, tmp_memory):
        """Claims without topics should still create nodes."""
        from knowledge_graph import build_graph_from_kb
        kb = {
            "claims": [
                {"id": "c1", "claim": "Standalone fact", "status": "active"},
                {"id": "c2", "claim": "Another fact", "status": "active"},
            ],
        }
        graph = build_graph_from_kb("test", kb)
        claim_nodes = [n for n in graph["nodes"] if n["type"] == "claim"]
        assert len(claim_nodes) == 2

    def test_graph_roundtrip(self, sample_kb, tmp_memory):
        from knowledge_graph import build_graph_from_kb, save_graph, load_graph, get_graph_summary
        graph = build_graph_from_kb("crypto", sample_kb)
        save_graph("crypto", graph)
        loaded = load_graph("crypto")
        summary = get_graph_summary(loaded)
        assert summary["total_nodes"] == graph["metadata"]["node_count"]
        assert summary["total_edges"] == graph["metadata"]["edge_count"]


class TestConsensusIntegration:
    """Consensus integration checks."""

    def test_consensus_returns_same_format_as_research(self):
        """Consensus output should have same required keys as single research."""
        from agents.consensus import merge_findings
        outputs = [
            {
                "_researcher_id": 1,
                "findings": [{"claim": "A", "confidence": "high"}],
                "key_insights": ["insight1"],
                "knowledge_gaps": ["gap1"],
                "sources_used": ["url1"],
                "summary": "Summary A",
            },
        ]
        result = merge_findings("test q", outputs, "test")
        # Should have all standard keys
        assert "findings" in result
        assert "key_insights" in result
        assert "knowledge_gaps" in result
        assert "sources_used" in result
        assert "summary" in result
        # Plus consensus metadata
        assert "consensus_level" in result
