"""Knowledge base, synthesis, and graph CLI commands."""

import os

from config import MIN_OUTPUTS_FOR_SYNTHESIS
from cost_tracker import check_budget
from memory_store import get_stats, get_archive_stats, prune_domain
from agents.synthesizer import synthesize, show_knowledge_base
from knowledge_graph import build_graph_from_kb, save_graph, load_graph, get_graph_summary


def run_synthesize(domain: str):
    """Force knowledge synthesis for a domain."""
    print(f"\n{'='*60}")
    print(f"  KNOWLEDGE SYNTHESIS \u2014 Domain: {domain}")
    print(f"{'='*60}\n")

    b = check_budget()
    if not b["within_budget"]:
        print(f"  \u2717 Budget exceeded. Use --budget to see details.")
        return

    result = synthesize(domain, force=True)
    if not result:
        print(f"\n  \u2717 Synthesis failed or not enough data.")
        print(f"  Need at least {MIN_OUTPUTS_FOR_SYNTHESIS} accepted outputs.")
    else:
        print(f"\n[GRAPH] Building knowledge graph...")
        graph = build_graph_from_kb(domain, result)
        save_graph(domain, graph)
        summary = get_graph_summary(graph)
        print(f"[GRAPH] \u2713 {summary['total_nodes']} nodes, {summary['total_edges']} edges, "
              f"{summary['total_clusters']} clusters")
    print()


def show_kb(domain: str):
    """Display the knowledge base for a domain."""
    print(f"\n{'='*60}")
    print(f"  KNOWLEDGE BASE \u2014 Domain: {domain}")
    print(f"{'='*60}")

    show_knowledge_base(domain)
    print()


def versions(domain: str):
    """List knowledge base version history."""
    from memory_store import list_kb_versions
    print(f"\n{'='*60}")
    print(f"  KB VERSION HISTORY \u2014 Domain: {domain}")
    print(f"{'='*60}\n")

    ver = list_kb_versions(domain)
    if not ver:
        print("  No previous versions found.")
        print("  Versions are created automatically each time the KB is synthesized.")
    else:
        print(f"  {len(ver)} version(s) available:\n")
        for v in ver:
            print(f"    {v['version']}  ({v['claims_count']} claims)")
    print()


def kb_rollback(domain: str, version: str):
    """Roll back knowledge base to a previous version."""
    from memory_store import rollback_knowledge_base, list_kb_versions
    print(f"\n{'='*60}")
    print(f"  KB ROLLBACK \u2014 Domain: {domain}")
    print(f"{'='*60}\n")

    if version == "latest":
        ver = list_kb_versions(domain)
        if not ver:
            print("  No previous versions found. Nothing to roll back to.")
            print()
            return
        version = None

    result = rollback_knowledge_base(domain, version)
    if result["status"] == "success":
        print(f"  Rolled back to: {result['version']}")
        print(f"  Claims restored: {result['claims_count']}")
    else:
        print(f"  Error: {result['error']}")
    print()


def prune(domain: str, dry_run: bool = False):
    """Run memory hygiene on a domain."""
    action = "DRY RUN" if dry_run else "PRUNING"
    print(f"\n{'='*60}")
    print(f"  MEMORY HYGIENE ({action}) \u2014 Domain: {domain}")
    print(f"{'='*60}\n")

    stats = get_stats(domain)
    print(f"  Before: {stats['count']} outputs, {stats['accepted']} accepted, {stats['rejected']} rejected")

    archive_stats = get_archive_stats(domain)
    if archive_stats["count"] > 0:
        print(f"  Already archived: {archive_stats['count']} outputs")

    result = prune_domain(domain, dry_run=dry_run)

    if result["archived"] == 0:
        print(f"\n  \u2713 Memory is clean \u2014 nothing to archive")
    else:
        verb = "Would archive" if dry_run else "Archived"
        print(f"\n  {verb} {result['archived']} output(s):")
        for detail in result.get("details", []):
            print(f"    \u2192 {detail['filename']} (score {detail['score']}, "
                  f"{detail['verdict']}, {detail['age_days']}d old) \u2014 {detail['reason']}")

    print(f"\n  After: {result['kept']} active outputs")
    if not dry_run and result["archived"] > 0:
        print(f"  Archived files in: memory/{domain}/_archive/")
        print(f"  Note: archived outputs can be restored if needed")
    print()


def graph(domain: str):
    """Display knowledge graph summary for a domain."""
    print(f"\n{'='*60}")
    print(f"  KNOWLEDGE GRAPH \u2014 {domain}")
    print(f"{'='*60}")

    g = load_graph(domain)
    if not g or not g.get("nodes"):
        print(f"\n  No knowledge graph found for '{domain}'.")
        print(f"  Run --synthesize first to build knowledge base, then graph auto-builds.")
        print()
        return

    summary = get_graph_summary(g)

    print(f"\n  Nodes: {summary['total_nodes']}")
    print(f"  Edges: {summary['total_edges']}")
    print(f"  Clusters: {summary['total_clusters']}")

    print(f"\n  Node Types:")
    for ntype, count in sorted(summary.get("node_types", {}).items(), key=lambda x: -x[1]):
        print(f"    {ntype:<16} {count:>4}")

    print(f"\n  Edge Types:")
    for etype, count in sorted(summary.get("edge_types", {}).items(), key=lambda x: -x[1]):
        print(f"    {etype:<16} {count:>4}")

    from knowledge_graph import get_contradictions
    contradictions = get_contradictions(g)
    if contradictions:
        print(f"\n  \u26a0 Contradictions ({len(contradictions)}):")
        for c in contradictions[:5]:
            src = next((n for n in g["nodes"] if n["id"] == c["source"]), {})
            tgt = next((n for n in g["nodes"] if n["id"] == c["target"]), {})
            print(f"    \u2022 {src.get('label', c['source'])[:40]}")
            print(f"      \u2194 {tgt.get('label', c['target'])[:40]}")

    gaps = summary.get("gaps", {})
    isolated = gaps.get("isolated_nodes", [])
    if isolated:
        print(f"\n  Knowledge Gaps ({len(isolated)} isolated nodes):")
        for node_id in isolated[:5]:
            node = next((n for n in g["nodes"] if n["id"] == node_id), {})
            print(f"    \u2022 {node.get('label', node_id)[:60]}")

    print()
