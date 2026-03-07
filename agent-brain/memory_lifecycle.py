"""
Memory Lifecycle — Self-Managing Maintenance

Runs the full memory maintenance cycle for a domain or all domains:
1. Expire stale claims in the knowledge base
2. Re-synthesize if too many claims went stale
3. Rebuild the knowledge graph if KB changed
4. Prune old/rejected outputs
5. Verify high-confidence claims against external evidence
6. Update calibration stats

This module is designed to be called:
- By the daemon every N cycles (MAINTENANCE_EVERY_N_CYCLES)
- Manually via CLI (--maintenance)
- After significant changes to a domain's data

The lifecycle is the system's self-cleaning mechanism — without it,
the knowledge base accumulates stale claims, the graph drifts from
reality, and storage grows unbounded.
"""

import os
from datetime import datetime, timezone

from config import (
    MEMORY_DIR, MAINTENANCE_ENABLED, MAINTENANCE_STALE_THRESHOLD,
    CLAIM_VERIFY_ENABLED, CLAIM_VERIFY_MAX_PER_CYCLE,
)
from memory_store import (
    expire_stale_claims, prune_domain, get_stats,
    load_knowledge_base, save_knowledge_base,
)


def run_maintenance(domain: str, verbose: bool = True) -> dict:
    """
    Run the full memory maintenance cycle for a single domain.

    Returns a summary dict of all actions taken.
    """
    if not MAINTENANCE_ENABLED:
        return {"skipped": True, "reason": "maintenance disabled"}

    results = {
        "domain": domain,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actions": [],
    }

    stats = get_stats(domain)
    if stats.get("count", 0) == 0:
        return {"domain": domain, "skipped": True, "reason": "empty domain"}

    # 1. Expire stale claims
    try:
        expiry = expire_stale_claims(domain)
        if expiry.get("flagged", 0) > 0 or expiry.get("expired", 0) > 0:
            results["actions"].append({
                "action": "claim_expiry",
                "flagged_stale": expiry.get("flagged", 0),
                "expired": expiry.get("expired", 0),
                "active_remaining": expiry.get("active", 0),
            })
            if verbose:
                print(f"  [LIFECYCLE] {domain}: {expiry['flagged']} stale, "
                      f"{expiry['expired']} expired claims")
    except Exception as e:
        results["actions"].append({"action": "claim_expiry", "error": str(e)})

    # 2. Re-synthesize if too many claims went stale
    stale_count = sum(1 for a in results["actions"]
                      if a.get("action") == "claim_expiry"
                      for _ in range(a.get("flagged_stale", 0)))
    total_stale = 0
    for a in results["actions"]:
        if a.get("action") == "claim_expiry":
            total_stale = a.get("flagged_stale", 0) + a.get("expired", 0)

    if total_stale >= MAINTENANCE_STALE_THRESHOLD:
        try:
            from agents.synthesizer import synthesize
            kb = synthesize(domain, force=True)
            if kb:
                claims = len([c for c in kb.get("claims", []) if c.get("status") == "active"])
                results["actions"].append({
                    "action": "re_synthesis",
                    "reason": f"{total_stale} stale/expired claims",
                    "active_claims": claims,
                })
                if verbose:
                    print(f"  [LIFECYCLE] {domain}: re-synthesized KB ({claims} active claims)")
        except Exception as e:
            results["actions"].append({"action": "re_synthesis", "error": str(e)})

    # 3. Rebuild knowledge graph
    kb = load_knowledge_base(domain)
    if kb:
        try:
            from knowledge_graph import build_graph_from_kb, save_graph, get_graph_summary
            graph = build_graph_from_kb(domain, kb)
            save_graph(domain, graph)
            gs = get_graph_summary(graph)
            results["actions"].append({
                "action": "graph_rebuild",
                "nodes": gs.get("total_nodes", 0),
                "edges": gs.get("total_edges", 0),
            })
            if verbose:
                print(f"  [LIFECYCLE] {domain}: graph rebuilt "
                      f"({gs['total_nodes']} nodes, {gs['total_edges']} edges)")
        except Exception as e:
            results["actions"].append({"action": "graph_rebuild", "error": str(e)})

    # 4. Prune old/rejected outputs
    try:
        prune_result = prune_domain(domain)
        archived = prune_result.get("archived", 0)
        if archived > 0:
            results["actions"].append({
                "action": "prune",
                "archived": archived,
                "kept": prune_result.get("kept", 0),
            })
            if verbose:
                print(f"  [LIFECYCLE] {domain}: pruned {archived} outputs")
    except Exception as e:
        results["actions"].append({"action": "prune", "error": str(e)})

    # 5. Verify high-confidence claims against external evidence
    if CLAIM_VERIFY_ENABLED and kb:
        try:
            from agents.claim_verifier import verify_claims
            verifications = verify_claims(domain, max_checks=CLAIM_VERIFY_MAX_PER_CYCLE)
            if verifications:
                confirmed = sum(1 for v in verifications if v.get("verdict") == "confirmed")
                refuted = sum(1 for v in verifications if v.get("verdict") == "refuted")
                results["actions"].append({
                    "action": "claim_verification",
                    "checked": len(verifications),
                    "confirmed": confirmed,
                    "refuted": refuted,
                })
                if verbose:
                    print(f"  [LIFECYCLE] {domain}: verified {len(verifications)} claims "
                          f"({confirmed} confirmed, {refuted} refuted)")
        except Exception as e:
            results["actions"].append({"action": "claim_verification", "error": str(e)})

    # 6. Update calibration stats
    try:
        from domain_calibration import update_domain_stats
        cal = update_domain_stats(domain)
        if cal:
            results["actions"].append({
                "action": "calibration_update",
                "mean": cal.get("mean", 0),
                "accept_rate": cal.get("accept_rate", 0),
            })
    except Exception as e:
        results["actions"].append({"action": "calibration_update", "error": str(e)})

    results["total_actions"] = len([a for a in results["actions"] if "error" not in a])
    return results


def run_maintenance_all(verbose: bool = True) -> dict:
    """
    Run maintenance across all domains with data.

    Returns a summary of all domain maintenance results.
    """
    if not os.path.exists(MEMORY_DIR):
        return {"domains": [], "reason": "no memory directory"}

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domains": [],
    }

    if verbose:
        print("\n[LIFECYCLE] Running maintenance across all domains...")

    for name in sorted(os.listdir(MEMORY_DIR)):
        domain_dir = os.path.join(MEMORY_DIR, name)
        if not os.path.isdir(domain_dir) or name.startswith("_"):
            continue

        stats = get_stats(name)
        if stats.get("count", 0) == 0:
            continue

        domain_result = run_maintenance(name, verbose=verbose)
        results["domains"].append(domain_result)

    total_actions = sum(d.get("total_actions", 0) for d in results["domains"])
    results["total_domains"] = len(results["domains"])
    results["total_actions"] = total_actions

    if verbose:
        print(f"\n[LIFECYCLE] Maintenance complete: "
              f"{results['total_domains']} domains, {total_actions} actions taken")

    return results
