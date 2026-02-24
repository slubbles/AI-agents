"""
Knowledge Graph — Structured Relationships Between Findings

Turns the flat knowledge base (list of claims) into a graph where:
- Nodes = claims, topics, sources, questions
- Edges = relationships (supports, contradicts, supersedes, relates_to, answers)

This enables:
1. Contradiction detection across the entire domain
2. Knowledge cluster identification (what topics are well-covered?)
3. Gap detection (which topics have weak connections?)
4. Compound queries (how does X relate to Y?)
5. Provenance tracking (where did this knowledge come from?)

Stored as JSON — no external DB needed at this scale.
Each domain gets its own graph file: memory/{domain}/_knowledge_graph.json

The graph is rebuilt from the knowledge base by the synthesizer after each synthesis.
It can also be queried directly via CLI or dashboard.
"""

import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from config import MEMORY_DIR


# ============================================================
# Data Structures
# ============================================================

def _empty_graph() -> dict:
    """Create an empty knowledge graph structure."""
    return {
        "nodes": [],
        "edges": [],
        "metadata": {
            "domain": "",
            "created_at": "",
            "updated_at": "",
            "node_count": 0,
            "edge_count": 0,
            "cluster_count": 0,
        },
        "clusters": [],
        "gap_analysis": {
            "isolated_nodes": [],
            "weak_clusters": [],
            "missing_connections": [],
        },
    }


def create_node(node_id: str, node_type: str, label: str, **kwargs) -> dict:
    """
    Create a graph node.
    
    Types: claim, topic, source, question, gap
    """
    node = {
        "id": node_id,
        "type": node_type,
        "label": label,
        "confidence": kwargs.get("confidence", "medium"),
        "status": kwargs.get("status", "active"),
        "first_seen": kwargs.get("first_seen", ""),
        "last_updated": kwargs.get("last_updated", datetime.now(timezone.utc).isoformat()),
        "source_count": kwargs.get("source_count", 0),
        "metadata": kwargs.get("metadata", {}),
    }
    return node


def create_edge(source_id: str, target_id: str, edge_type: str, **kwargs) -> dict:
    """
    Create a graph edge (relationship).
    
    Types:
    - supports: source claim provides evidence for target claim
    - contradicts: source claim conflicts with target claim
    - supersedes: source claim replaces outdated target claim
    - relates_to: general topical relationship
    - belongs_to: claim belongs to topic
    - answers: claim answers a question/gap
    - sourced_from: claim came from this source URL
    """
    edge = {
        "source": source_id,
        "target": target_id,
        "type": edge_type,
        "weight": kwargs.get("weight", 1.0),
        "created_at": kwargs.get("created_at", datetime.now(timezone.utc).isoformat()),
        "metadata": kwargs.get("metadata", {}),
    }
    return edge


# ============================================================
# Graph Construction — from Knowledge Base
# ============================================================

def build_graph_from_kb(domain: str, knowledge_base: dict) -> dict:
    """
    Build a knowledge graph from a synthesized knowledge base.
    
    Extracts:
    1. Topic nodes from kb.topics
    2. Claim nodes from kb.claims
    3. Gap nodes from kb.knowledge_gaps
    4. Edges: belongs_to (claim→topic), supports/contradicts (claim↔claim),
       supersedes, sourced_from, answers
    
    Returns the full graph dict.
    """
    graph = _empty_graph()
    graph["metadata"]["domain"] = domain
    graph["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()
    graph["metadata"]["updated_at"] = graph["metadata"]["created_at"]

    claims = knowledge_base.get("claims", [])
    topics = knowledge_base.get("topics", [])
    contradictions = knowledge_base.get("contradictions", [])
    gaps = knowledge_base.get("knowledge_gaps", [])

    # --- Topic nodes ---
    topic_ids = {}
    for i, topic in enumerate(topics):
        topic_name = topic.get("name", f"topic_{i}")
        topic_id = f"topic_{_slug(topic_name)}"
        topic_ids[topic_name.lower()] = topic_id
        
        node = create_node(
            node_id=topic_id,
            node_type="topic",
            label=topic_name,
            metadata={"subtopics": topic.get("subtopics", [])},
        )
        graph["nodes"].append(node)

    # --- Claim nodes + edges ---
    claim_id_map = {}  # Map kb claim IDs to graph node IDs
    claim_topic_map = defaultdict(list)  # topic → list of claim IDs
    
    for claim in claims:
        kb_id = claim.get("id", "")
        claim_text = claim.get("claim", "")
        if not claim_text:
            continue
            
        node_id = kb_id if kb_id else f"claim_{_slug(claim_text[:50])}"
        claim_id_map[kb_id] = node_id
        
        node = create_node(
            node_id=node_id,
            node_type="claim",
            label=claim_text[:200],
            confidence=claim.get("confidence", "medium"),
            status=claim.get("status", "active"),
            first_seen=claim.get("first_seen", ""),
            last_updated=claim.get("last_confirmed", ""),
            source_count=claim.get("source_count", 0),
            metadata={
                "full_text": claim_text,
                "sources": claim.get("sources", []),
                "notes": claim.get("notes", ""),
            },
        )
        graph["nodes"].append(node)

        # Edge: claim → topic (belongs_to)
        claim_topic = claim.get("topic", "")
        if claim_topic:
            topic_id = topic_ids.get(claim_topic.lower())
            if topic_id:
                edge = create_edge(node_id, topic_id, "belongs_to")
                graph["edges"].append(edge)
                claim_topic_map[topic_id].append(node_id)

        # Edge: claim → sources (sourced_from)
        for source_url in claim.get("sources", [])[:5]:
            source_node_id = f"source_{_slug(source_url[:80])}"
            # Add source node if not already present
            if not any(n["id"] == source_node_id for n in graph["nodes"]):
                graph["nodes"].append(create_node(
                    node_id=source_node_id,
                    node_type="source",
                    label=source_url[:120],
                    metadata={"url": source_url},
                ))
            edge = create_edge(node_id, source_node_id, "sourced_from")
            graph["edges"].append(edge)

        # Edge: supersedes
        supersedes_id = claim.get("supersedes")
        if supersedes_id and supersedes_id in claim_id_map:
            edge = create_edge(
                node_id, claim_id_map[supersedes_id], "supersedes",
                metadata={"reason": "newer data replaces older"},
            )
            graph["edges"].append(edge)

    # --- Contradiction edges ---
    for contradiction in contradictions:
        claim_a_id = contradiction.get("claim_a", "")
        claim_b_id = contradiction.get("claim_b", "")
        
        a_node = claim_id_map.get(claim_a_id, claim_a_id)
        b_node = claim_id_map.get(claim_b_id, claim_b_id)
        
        if a_node and b_node:
            edge = create_edge(
                a_node, b_node, "contradicts",
                weight=1.5,  # Higher weight for contradictions
                metadata={
                    "description": contradiction.get("description", ""),
                    "resolution": contradiction.get("resolution", "unresolved"),
                },
            )
            graph["edges"].append(edge)

    # --- Gap nodes ---
    for i, gap in enumerate(gaps):
        gap_text = gap.get("gap", "")
        if not gap_text:
            continue
        gap_id = f"gap_{i:03d}"
        node = create_node(
            node_id=gap_id,
            node_type="gap",
            label=gap_text[:200],
            confidence="low",
            metadata={
                "priority": gap.get("priority", "medium"),
                "related_topic": gap.get("related_topic", ""),
                "full_text": gap_text,
            },
        )
        graph["nodes"].append(node)

        # Edge: gap → topic (relates_to)
        related = gap.get("related_topic", "")
        if related:
            topic_id = topic_ids.get(related.lower())
            if topic_id:
                edge = create_edge(gap_id, topic_id, "relates_to")
                graph["edges"].append(edge)

    # --- Infer support edges between claims in same topic ---
    for topic_id, claim_ids in claim_topic_map.items():
        active_claims = [
            cid for cid in claim_ids
            if any(n["id"] == cid and n.get("status") == "active" for n in graph["nodes"])
        ]
        # Claims in the same topic with same confidence level likely support each other
        for i in range(len(active_claims)):
            for j in range(i + 1, len(active_claims)):
                # Only add support edges between non-contradicting claims
                contradicting = any(
                    (e["source"] == active_claims[i] and e["target"] == active_claims[j]) or
                    (e["source"] == active_claims[j] and e["target"] == active_claims[i])
                    for e in graph["edges"] if e["type"] == "contradicts"
                )
                if not contradicting:
                    edge = create_edge(
                        active_claims[i], active_claims[j], "relates_to",
                        weight=0.5,  # Inferred relationship, lower weight
                    )
                    graph["edges"].append(edge)

    # --- Compute clusters ---
    graph["clusters"] = _compute_clusters(graph)

    # --- Gap analysis ---
    graph["gap_analysis"] = _analyze_gaps(graph)

    # --- Update metadata ---
    graph["metadata"]["node_count"] = len(graph["nodes"])
    graph["metadata"]["edge_count"] = len(graph["edges"])
    graph["metadata"]["cluster_count"] = len(graph["clusters"])

    return graph


# ============================================================
# Graph Analysis
# ============================================================

def _compute_clusters(graph: dict) -> list[dict]:
    """
    Find clusters of related nodes using simple connected components.
    Only considers claim and topic nodes.
    """
    # Build adjacency list (undirected)
    adj = defaultdict(set)
    claim_and_topic_ids = {
        n["id"] for n in graph["nodes"]
        if n["type"] in ("claim", "topic")
    }
    
    for edge in graph["edges"]:
        if edge["source"] in claim_and_topic_ids and edge["target"] in claim_and_topic_ids:
            adj[edge["source"]].add(edge["target"])
            adj[edge["target"]].add(edge["source"])

    # BFS to find connected components
    visited = set()
    clusters = []
    
    for node_id in claim_and_topic_ids:
        if node_id in visited:
            continue
        # BFS
        component = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        
        if component:
            # Get cluster details
            topics = [nid for nid in component 
                      if any(n["id"] == nid and n["type"] == "topic" for n in graph["nodes"])]
            claims = [nid for nid in component 
                      if any(n["id"] == nid and n["type"] == "claim" for n in graph["nodes"])]
            
            cluster = {
                "id": f"cluster_{len(clusters)}",
                "topics": topics,
                "claims": claims,
                "size": len(component),
                "density": _cluster_density(component, graph["edges"]),
            }
            clusters.append(cluster)

    # Sort by size descending
    clusters.sort(key=lambda c: c["size"], reverse=True)
    return clusters


def _cluster_density(nodes: set, edges: list) -> float:
    """Calculate edge density within a cluster."""
    n = len(nodes)
    if n < 2:
        return 0.0
    internal_edges = sum(
        1 for e in edges
        if e["source"] in nodes and e["target"] in nodes
    )
    max_edges = n * (n - 1) / 2
    return round(internal_edges / max_edges, 3) if max_edges > 0 else 0.0


def _analyze_gaps(graph: dict) -> dict:
    """Analyze the graph for knowledge gaps and weak spots."""
    connected_nodes = set()
    for edge in graph["edges"]:
        connected_nodes.add(edge["source"])
        connected_nodes.add(edge["target"])

    # Isolated nodes (no edges at all)
    isolated = [
        n["id"] for n in graph["nodes"]
        if n["id"] not in connected_nodes and n["type"] == "claim"
    ]

    # Weak clusters (fewer than 3 claims)
    weak = [
        {"cluster_id": c["id"], "size": c["size"], "topics": c["topics"]}
        for c in graph.get("clusters", [])
        if c["size"] < 3
    ]

    # Topics with no claims
    topic_ids_with_claims = set()
    for edge in graph["edges"]:
        if edge["type"] == "belongs_to":
            # target is the topic
            topic_ids_with_claims.add(edge["target"])
    
    empty_topics = [
        n["id"] for n in graph["nodes"]
        if n["type"] == "topic" and n["id"] not in topic_ids_with_claims
    ]

    return {
        "isolated_nodes": isolated,
        "weak_clusters": weak,
        "missing_connections": empty_topics,
    }


# ============================================================
# Graph Queries
# ============================================================

def get_node(graph: dict, node_id: str) -> dict | None:
    """Get a node by ID."""
    for node in graph["nodes"]:
        if node["id"] == node_id:
            return node
    return None


def get_neighbors(graph: dict, node_id: str, edge_type: str | None = None) -> list[dict]:
    """Get all neighbors of a node, optionally filtered by edge type."""
    neighbor_ids = set()
    for edge in graph["edges"]:
        if edge_type and edge["type"] != edge_type:
            continue
        if edge["source"] == node_id:
            neighbor_ids.add(edge["target"])
        elif edge["target"] == node_id:
            neighbor_ids.add(edge["source"])
    
    return [n for n in graph["nodes"] if n["id"] in neighbor_ids]


def get_contradictions(graph: dict) -> list[dict]:
    """Get all contradiction edges with their connected nodes."""
    results = []
    for edge in graph["edges"]:
        if edge["type"] == "contradicts":
            source_node = get_node(graph, edge["source"])
            target_node = get_node(graph, edge["target"])
            results.append({
                "edge": edge,
                "claim_a": source_node,
                "claim_b": target_node,
            })
    return results


def get_claims_by_topic(graph: dict, topic_id: str) -> list[dict]:
    """Get all claims belonging to a specific topic."""
    claim_ids = set()
    for edge in graph["edges"]:
        if edge["type"] == "belongs_to" and edge["target"] == topic_id:
            claim_ids.add(edge["source"])
    return [n for n in graph["nodes"] if n["id"] in claim_ids]


def get_graph_summary(graph: dict) -> dict:
    """Get a summary of the knowledge graph for display."""
    nodes_by_type = defaultdict(int)
    for node in graph["nodes"]:
        nodes_by_type[node["type"]] += 1
    
    edges_by_type = defaultdict(int)
    for edge in graph["edges"]:
        edges_by_type[edge["type"]] += 1

    gap_analysis = graph.get("gap_analysis", {})
    
    return {
        "domain": graph["metadata"]["domain"],
        "total_nodes": graph["metadata"]["node_count"],
        "total_edges": graph["metadata"]["edge_count"],
        "total_clusters": graph["metadata"]["cluster_count"],
        "nodes_by_type": dict(nodes_by_type),
        "edges_by_type": dict(edges_by_type),
        "isolated_claims": len(gap_analysis.get("isolated_nodes", [])),
        "weak_clusters": len(gap_analysis.get("weak_clusters", [])),
        "empty_topics": len(gap_analysis.get("missing_connections", [])),
        "updated_at": graph["metadata"]["updated_at"],
    }


def find_path(graph: dict, start_id: str, end_id: str, max_depth: int = 5) -> list[str] | None:
    """
    Find shortest path between two nodes using BFS.
    Returns list of node IDs forming the path, or None if no path exists.
    """
    if start_id == end_id:
        return [start_id]
    
    # Build adjacency list
    adj = defaultdict(set)
    for edge in graph["edges"]:
        adj[edge["source"]].add(edge["target"])
        adj[edge["target"]].add(edge["source"])

    # BFS
    visited = {start_id}
    queue = [(start_id, [start_id])]
    
    while queue:
        current, path = queue.pop(0)
        if len(path) > max_depth:
            continue
        for neighbor in adj.get(current, []):
            if neighbor == end_id:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    
    return None


# ============================================================
# Persistence
# ============================================================

def _graph_path(domain: str) -> str:
    """Path to the knowledge graph file for a domain."""
    return os.path.join(MEMORY_DIR, domain, "_knowledge_graph.json")


def save_graph(domain: str, graph: dict) -> str:
    """Save a knowledge graph to disk."""
    filepath = _graph_path(domain)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(graph, f, indent=2)
    return filepath


def load_graph(domain: str) -> dict | None:
    """Load a knowledge graph from disk. Returns None if not found."""
    filepath = _graph_path(domain)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# ============================================================
# Helpers
# ============================================================

def _slug(text: str) -> str:
    """Convert text to a URL-safe slug for use as node ID."""
    import re
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = text.strip('_')
    return text[:60]
