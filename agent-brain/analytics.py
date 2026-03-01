"""
Analytics Engine — Performance Analysis & Insights

Provides deep analysis of system performance:
- Score trends over time (per domain, per strategy)
- Strategy effectiveness comparison
- Cost efficiency metrics
- Domain cross-comparison
- Research quality patterns
- Critic behavior analysis
- Knowledge accumulation velocity

No API calls — pure computation on stored data.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from config import MEMORY_DIR, LOG_DIR, QUALITY_THRESHOLD
from memory_store import load_outputs, get_stats, load_knowledge_base
from strategy_store import (
    get_active_version, get_strategy_status, get_strategy_performance,
    get_version_history, list_versions,
)
from cost_tracker import get_daily_spend, get_all_time_spend
from agents.orchestrator import discover_domains, get_system_health


# ============================================================
# Score Trend Analysis
# ============================================================

def score_trajectory(domain: str, window: int = 3) -> dict:
    """
    Compute score trajectory for a domain showing how quality evolves.
    
    Args:
        domain: Domain to analyze
        window: Rolling average window size
        
    Returns:
        {
            domain, total_outputs, scores: [{score, timestamp, strategy, accepted}],
            rolling_avg: [float], trend: "improving"|"declining"|"stable"|"insufficient",
            first_score, last_score, best_score, worst_score,
            improvement: float (last_avg - first_avg)
        }
    """
    outputs = load_outputs(domain)
    if not outputs:
        return {"domain": domain, "total_outputs": 0, "trend": "insufficient"}
    
    # Sort by timestamp
    outputs.sort(key=lambda o: o.get("timestamp", ""))
    
    scores = []
    for o in outputs:
        scores.append({
            "score": o.get("overall_score", 0),
            "timestamp": o.get("timestamp", ""),
            "strategy": o.get("strategy_version", "default"),
            "accepted": o.get("accepted", False),
            "question": o.get("question", "")[:80],
        })
    
    raw_scores = [s["score"] for s in scores]
    
    # Rolling average
    rolling_avg = []
    for i in range(len(raw_scores)):
        start = max(0, i - window + 1)
        window_scores = raw_scores[start:i+1]
        rolling_avg.append(round(sum(window_scores) / len(window_scores), 2))
    
    # Determine trend
    if len(rolling_avg) < 3:
        trend = "insufficient"
        first_avg = rolling_avg[0] if rolling_avg else 0
        last_avg = rolling_avg[-1] if rolling_avg else 0
    else:
        third = max(1, len(rolling_avg) // 3)
        first_avg = sum(rolling_avg[:third]) / third
        last_avg = sum(rolling_avg[-third:]) / third
        diff = last_avg - first_avg
        if diff > 0.5:
            trend = "improving"
        elif diff < -0.5:
            trend = "declining"
        else:
            trend = "stable"
    
    return {
        "domain": domain,
        "total_outputs": len(scores),
        "scores": scores,
        "rolling_avg": rolling_avg,
        "trend": trend,
        "first_score": raw_scores[0] if raw_scores else 0,
        "last_score": raw_scores[-1] if raw_scores else 0,
        "best_score": max(raw_scores) if raw_scores else 0,
        "worst_score": min(raw_scores) if raw_scores else 0,
        "avg_score": round(sum(raw_scores) / len(raw_scores), 2) if raw_scores else 0,
        "improvement": round(last_avg - first_avg, 2) if len(rolling_avg) >= 2 else 0,
    }


def score_distribution(domain: str) -> dict:
    """
    Histogram of score distribution for a domain.
    
    Returns:
        {domain, total, distribution: {1: count, 2: count, ...10: count},
         below_threshold: int, above_threshold: int, acceptance_rate: float}
    """
    outputs = load_outputs(domain)
    if not outputs:
        return {"domain": domain, "total": 0, "distribution": {}}
    
    dist = defaultdict(int)
    for o in outputs:
        score = int(round(o.get("overall_score", 0)))
        score = max(1, min(10, score))  # Clamp to 1-10
        dist[score] += 1
    
    below = sum(1 for o in outputs if o.get("overall_score", 0) < QUALITY_THRESHOLD)
    above = len(outputs) - below
    
    return {
        "domain": domain,
        "total": len(outputs),
        "distribution": dict(sorted(dist.items())),
        "below_threshold": below,
        "above_threshold": above,
        "acceptance_rate": round(above / len(outputs) * 100, 1) if outputs else 0,
    }


# ============================================================
# Strategy Effectiveness
# ============================================================

def strategy_comparison(domain: str) -> list[dict]:
    """
    Compare effectiveness of different strategy versions for a domain.
    
    Returns list of strategy versions with their performance metrics.
    """
    versions = list_versions("researcher", domain)
    if not versions:
        versions = ["default"]
    
    results = []
    for version in versions:
        perf = get_strategy_performance(domain, version)
        if perf["count"] == 0:
            continue
        
        results.append({
            "version": version,
            "outputs": perf["count"],
            "avg_score": round(perf["avg_score"], 2) if perf["avg_score"] else 0,
            "accepted": perf.get("accepted", 0),
            "rejected": perf.get("rejected", 0),
            "acceptance_rate": round(perf.get("accepted", 0) / perf["count"] * 100, 1) if perf["count"] else 0,
            "score_range": f"{min(perf['scores'])}-{max(perf['scores'])}" if perf.get("scores") else "N/A",
            "scores": perf.get("scores", []),
        })
    
    # Sort by avg_score descending
    results.sort(key=lambda r: r["avg_score"], reverse=True)
    return results


# ============================================================
# Cost Efficiency
# ============================================================

def cost_efficiency() -> dict:
    """
    Analyze cost efficiency across the system.
    
    Returns:
        {
            total_spend, total_outputs, total_accepted,
            cost_per_output, cost_per_accepted_output,
            by_agent: {role: {spend, calls, avg_cost}},
            by_domain: {domain: {outputs, accepted, estimated_cost}},
            daily_trend: [{date, spend, outputs}]
        }
    """
    all_time = get_all_time_spend()
    
    # Count outputs per domain
    domains = discover_domains()
    total_outputs = 0
    total_accepted = 0
    by_domain = {}
    
    for domain in domains:
        stats = get_stats(domain)
        total_outputs += stats["count"]
        total_accepted += stats["accepted"]
        by_domain[domain] = {
            "outputs": stats["count"],
            "accepted": stats["accepted"],
            "rejected": stats["rejected"],
            "avg_score": round(stats["avg_score"], 2),
        }
    
    # Parse cost log for per-domain cost estimates
    cost_log = os.path.join(LOG_DIR, "costs.jsonl")
    domain_costs = defaultdict(float)
    agent_stats = defaultdict(lambda: {"spend": 0.0, "calls": 0})
    daily_data = defaultdict(lambda: {"spend": 0.0, "outputs": 0})
    
    if os.path.exists(cost_log):
        with open(cost_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                cost = entry.get("estimated_cost_usd", 0)
                d = entry.get("domain", "unknown")
                domain_costs[d] += cost
                
                role = entry.get("agent_role", "unknown")
                agent_stats[role]["spend"] += cost
                agent_stats[role]["calls"] += 1
                
                dt = entry.get("date", "unknown")
                daily_data[dt]["spend"] += cost
    
    # Merge domain costs into by_domain
    for d, cost in domain_costs.items():
        if d in by_domain:
            by_domain[d]["estimated_cost"] = round(cost, 4)
    
    # Daily trend
    daily_trend = []
    for dt in sorted(daily_data.keys()):
        daily_trend.append({
            "date": dt,
            "spend": round(daily_data[dt]["spend"], 4),
        })
    
    total_spend = all_time["total_usd"]
    
    return {
        "total_spend": total_spend,
        "total_outputs": total_outputs,
        "total_accepted": total_accepted,
        "cost_per_output": round(total_spend / total_outputs, 4) if total_outputs else 0,
        "cost_per_accepted_output": round(total_spend / total_accepted, 4) if total_accepted else 0,
        "by_agent": {
            k: {"spend": round(v["spend"], 4), "calls": v["calls"], 
                "avg_cost": round(v["spend"] / v["calls"], 4) if v["calls"] else 0}
            for k, v in sorted(agent_stats.items())
        },
        "by_domain": by_domain,
        "daily_trend": daily_trend,
    }


# ============================================================
# Critic Analysis
# ============================================================

def critic_analysis(domain: str) -> dict:
    """
    Analyze critic scoring patterns — which dimensions score highest/lowest.
    
    Returns:
        {domain, total_critiques, dimension_avgs: {dim: avg},
         weakest_dimension, strongest_dimension,
         common_weaknesses: [str], common_strengths: [str]}
    """
    outputs = load_outputs(domain)
    if not outputs:
        return {"domain": domain, "total_critiques": 0}
    
    dimensions = defaultdict(list)
    weaknesses = []
    strengths = []
    
    for o in outputs:
        critique = o.get("critique", {})
        
        # Extract dimension scores (stored under critique["scores"])
        scores_dict = critique.get("scores", {})
        for dim_name in ["accuracy", "depth", "completeness", "specificity", "intellectual_honesty"]:
            dim_data = scores_dict.get(dim_name)
            if isinstance(dim_data, dict) and "score" in dim_data:
                dimensions[dim_name].append(dim_data["score"])
            elif isinstance(dim_data, (int, float)):
                dimensions[dim_name].append(dim_data)
        
        # Collect weaknesses and strengths from critique
        for w in critique.get("weaknesses", []):
            if isinstance(w, str):
                weaknesses.append(w)
        for s in critique.get("strengths", []):
            if isinstance(s, str):
                strengths.append(s)
    
    # Compute averages
    dim_avgs = {}
    for dim, scores in dimensions.items():
        if scores:
            dim_avgs[dim] = round(sum(scores) / len(scores), 2)
    
    # Find weakest and strongest
    weakest = min(dim_avgs, key=dim_avgs.get) if dim_avgs else None
    strongest = max(dim_avgs, key=dim_avgs.get) if dim_avgs else None
    
    # Frequency count for weaknesses/strengths
    weakness_counts = defaultdict(int)
    for w in weaknesses:
        weakness_counts[w.lower().strip()] += 1
    strength_counts = defaultdict(int)
    for s in strengths:
        strength_counts[s.lower().strip()] += 1
    
    top_weaknesses = sorted(weakness_counts.items(), key=lambda x: -x[1])[:5]
    top_strengths = sorted(strength_counts.items(), key=lambda x: -x[1])[:5]
    
    return {
        "domain": domain,
        "total_critiques": len(outputs),
        "dimension_avgs": dim_avgs,
        "weakest_dimension": weakest,
        "strongest_dimension": strongest,
        "common_weaknesses": [{"text": w, "count": c} for w, c in top_weaknesses],
        "common_strengths": [{"text": s, "count": c} for s, c in top_strengths],
    }


# ============================================================
# Research Pattern Analysis
# ============================================================

def research_patterns(domain: str) -> dict:
    """
    Analyze research patterns — retry rates, search usage, question topics.
    
    Returns:
        {domain, total_outputs, avg_attempts, retry_rate,
         questions: [str], topic_clusters: {topic: count},
         avg_findings_per_output, avg_insights_per_output}
    """
    outputs = load_outputs(domain)
    if not outputs:
        return {"domain": domain, "total_outputs": 0}
    
    attempts = []
    questions = []
    findings_counts = []
    insights_counts = []
    search_counts = []
    
    for o in outputs:
        attempts.append(o.get("attempt", 1))
        questions.append(o.get("question", ""))
        
        research = o.get("research", {})
        findings_counts.append(len(research.get("findings", [])))
        insights_counts.append(len(research.get("key_insights", [])))
        search_counts.append(research.get("_searches_made", 0))
    
    retry_count = sum(1 for a in attempts if a > 1)
    
    return {
        "domain": domain,
        "total_outputs": len(outputs),
        "avg_attempts": round(sum(attempts) / len(attempts), 2) if attempts else 0,
        "retry_rate": round(retry_count / len(outputs) * 100, 1) if outputs else 0,
        "max_attempts": max(attempts) if attempts else 0,
        "questions": questions,
        "avg_findings_per_output": round(sum(findings_counts) / len(findings_counts), 1) if findings_counts else 0,
        "avg_insights_per_output": round(sum(insights_counts) / len(insights_counts), 1) if insights_counts else 0,
        "avg_searches_per_output": round(sum(search_counts) / len(search_counts), 1) if search_counts else 0,
    }


# ============================================================
# Cross-Domain Comparison
# ============================================================

def domain_comparison() -> list[dict]:
    """
    Side-by-side comparison of all domains.
    
    Returns list of dicts, one per domain, sorted by avg_score descending.
    """
    domains = discover_domains()
    if not domains:
        return []
    
    comparisons = []
    for domain in domains:
        stats = get_stats(domain)
        trajectory = score_trajectory(domain)
        
        version = get_active_version("researcher", domain)
        status = get_strategy_status("researcher", domain)
        
        kb = load_knowledge_base(domain)
        kb_claims = len(kb.get("claims", [])) if kb else 0
        kb_topics = len(kb.get("topics", [])) if kb else 0
        
        comparisons.append({
            "domain": domain,
            "outputs": stats["count"],
            "accepted": stats["accepted"],
            "rejected": stats["rejected"],
            "avg_score": round(stats["avg_score"], 2),
            "acceptance_rate": round(stats["accepted"] / stats["count"] * 100, 1) if stats["count"] else 0,
            "trend": trajectory.get("trend", "insufficient"),
            "improvement": trajectory.get("improvement", 0),
            "strategy_version": version,
            "strategy_status": status,
            "kb_claims": kb_claims,
            "kb_topics": kb_topics,
            "best_score": trajectory.get("best_score", 0),
            "worst_score": trajectory.get("worst_score", 0),
        })
    
    comparisons.sort(key=lambda c: c["avg_score"], reverse=True)
    return comparisons


# ============================================================
# Knowledge Accumulation Velocity
# ============================================================

def knowledge_velocity(domain: str) -> dict:
    """
    Track how fast useful knowledge is being accumulated.
    
    Returns:
        {domain, total_accepted, total_claims, unique_topics,
         claims_per_output, gaps_identified, gaps_addressed,
         velocity_rating: "fast"|"moderate"|"slow"|"stalled"}
    """
    outputs = load_outputs(domain)
    accepted = [o for o in outputs if o.get("accepted", False)]
    
    kb = load_knowledge_base(domain)
    claims = len(kb.get("claims", [])) if kb else 0
    topics = len(kb.get("topics", [])) if kb else 0
    gaps = len(kb.get("knowledge_gaps", [])) if kb else 0
    
    # Count total unique findings across all accepted outputs
    total_findings = 0
    all_gaps = set()
    for o in accepted:
        research = o.get("research", {})
        total_findings += len(research.get("findings", []))
        for gap in research.get("knowledge_gaps", []):
            all_gaps.add(gap if isinstance(gap, str) else str(gap))
    
    # Velocity rating
    if len(accepted) == 0:
        velocity = "stalled"
    elif len(accepted) < 3:
        velocity = "slow"  
    elif claims > 0 and claims / max(1, len(accepted)) >= 2:
        velocity = "fast"
    else:
        velocity = "moderate"
    
    return {
        "domain": domain,
        "total_outputs": len(outputs),
        "total_accepted": len(accepted),
        "total_findings": total_findings,
        "total_claims": claims,
        "unique_topics": topics,
        "claims_per_accepted": round(claims / len(accepted), 1) if accepted else 0,
        "findings_per_accepted": round(total_findings / len(accepted), 1) if accepted else 0,
        "knowledge_gaps_identified": len(all_gaps),
        "knowledge_gaps_in_kb": gaps,
        "velocity_rating": velocity,
    }


# ============================================================
# Full Analytics Report
# ============================================================

def full_report() -> dict:
    """
    Generate a comprehensive analytics report covering all aspects.
    
    Returns a nested dict with all analytics sections.
    """
    domains = discover_domains()
    health = get_system_health()
    cost_eff = cost_efficiency()
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system_health": health,
        "cost_efficiency": cost_eff,
        "domain_comparison": domain_comparison(),
        "domains": {},
    }
    
    for domain in domains:
        report["domains"][domain] = {
            "trajectory": score_trajectory(domain),
            "distribution": score_distribution(domain),
            "strategies": strategy_comparison(domain),
            "critic": critic_analysis(domain),
            "research": research_patterns(domain),
            "velocity": knowledge_velocity(domain),
        }
    
    return report


# ============================================================
# CLI Display Helpers
# ============================================================

def display_analytics(domain: str | None = None):
    """
    Print formatted analytics to stdout.
    
    If domain is specified, show domain-specific deep dive.
    If None, show cross-domain overview.
    """
    if domain:
        _display_domain_analytics(domain)
    else:
        _display_overview()


def _display_overview():
    """Cross-domain overview analytics."""
    health = get_system_health()
    comparisons = domain_comparison()
    cost_eff = cost_efficiency()
    
    print(f"\n{'='*70}")
    print(f"  ANALYTICS — System Overview")
    print(f"{'='*70}")
    
    # System Health
    hs = health["health_score"]
    bar = "█" * (hs // 5) + "░" * (20 - hs // 5)
    print(f"\n  System Health: [{bar}] {hs}/100")
    print(f"  Total outputs: {health['total_outputs']}  |  Accepted: {health['total_accepted']}  |  Rejected: {health['total_rejected']}")
    print(f"  Overall acceptance rate: {health['acceptance_rate']:.0f}%")
    print(f"  Average score: {health['avg_score']:.1f}/10")
    print(f"  Domains: {health['domain_count']}  |  With strategy: {health['domains_with_strategy']}  |  With KB: {health['domains_with_kb']}")
    
    # Cost Overview
    print(f"\n  {'─'*50}")
    print(f"  Cost Efficiency")
    print(f"  {'─'*50}")
    print(f"  Total spend: ${cost_eff['total_spend']:.4f}")
    print(f"  Cost per output: ${cost_eff['cost_per_output']:.4f}")
    print(f"  Cost per accepted output: ${cost_eff['cost_per_accepted_output']:.4f}")
    
    if cost_eff["by_agent"]:
        print(f"\n  By Agent:")
        for agent, data in cost_eff["by_agent"].items():
            print(f"    {agent:20s} ${data['spend']:.4f}  ({data['calls']} calls)")
    
    # Domain Comparison Table
    print(f"\n  {'─'*50}")
    print(f"  Domain Comparison")
    print(f"  {'─'*50}")
    
    if comparisons:
        header = f"  {'Domain':<15} {'Outputs':>7} {'Acc%':>6} {'Avg':>5} {'Trend':<11} {'Δ':>5} {'Strategy':>10} {'KB':>5}"
        print(header)
        print(f"  {'─'*15} {'─'*7} {'─'*6} {'─'*5} {'─'*11} {'─'*5} {'─'*10} {'─'*5}")
        
        for c in comparisons:
            trend_icon = {"improving": "▲ improve", "declining": "▼ decline", "stable": "─ stable", "insufficient": "? data?"}.get(c["trend"], "?")
            kb_str = f"{c['kb_claims']}c" if c["kb_claims"] else "—"
            print(f"  {c['domain']:<15} {c['outputs']:>7} {c['acceptance_rate']:>5.0f}% {c['avg_score']:>5.1f} {trend_icon:<11} {c['improvement']:>+5.1f} {c['strategy_version']:>10} {kb_str:>5}")
    
    # Recommendations
    print(f"\n  {'─'*50}")
    print(f"  Recommendations")
    print(f"  {'─'*50}")
    
    recs = _generate_recommendations(comparisons, cost_eff, health)
    for i, rec in enumerate(recs, 1):
        print(f"  {i}. {rec}")
    
    print()


def _display_domain_analytics(domain: str):
    """Deep-dive analytics for a specific domain."""
    trajectory = score_trajectory(domain)
    dist = score_distribution(domain)
    strategies = strategy_comparison(domain)
    critic = critic_analysis(domain)
    patterns = research_patterns(domain)
    velocity = knowledge_velocity(domain)
    
    if trajectory.get("total_outputs", 0) == 0:
        print(f"\n  No data for domain '{domain}'")
        return
    
    print(f"\n{'='*70}")
    print(f"  ANALYTICS — {domain.upper()} Deep Dive")
    print(f"{'='*70}")
    
    # Score Trajectory
    print(f"\n  Score Trajectory")
    print(f"  {'─'*50}")
    
    trend_icon = {"improving": "▲", "declining": "▼", "stable": "─", "insufficient": "?"}.get(trajectory["trend"], "?")
    print(f"  Trend: {trend_icon} {trajectory['trend']}  |  Improvement: {trajectory['improvement']:+.1f}")
    print(f"  Range: {trajectory['worst_score']}-{trajectory['best_score']}  |  Average: {trajectory['avg_score']}")
    print(f"  Latest: {trajectory['last_score']}  |  First: {trajectory['first_score']}")
    
    # ASCII sparkline of scores
    scores = trajectory.get("scores", [])
    if scores:
        print(f"\n  Score Timeline:")
        for s in scores:
            bar_len = int(s["score"])
            accepted_mark = "✓" if s["accepted"] else "✗"
            print(f"    {accepted_mark} {'█' * bar_len}{'░' * (10 - bar_len)} {s['score']:>4.0f}  [{s['strategy']}]")
    
    # Distribution
    print(f"\n  Score Distribution")
    print(f"  {'─'*50}")
    if dist.get("distribution"):
        max_count = max(dist["distribution"].values()) if dist["distribution"] else 1
        for score_val in range(1, 11):
            count = dist["distribution"].get(score_val, 0)
            bar = "█" * int(count / max_count * 20) if max_count > 0 else ""
            threshold_mark = " ◄ threshold" if score_val == QUALITY_THRESHOLD else ""
            print(f"    {score_val:>2}: {bar:<20} {count}{threshold_mark}")
    print(f"  Acceptance rate: {dist.get('acceptance_rate', 0):.0f}% ({dist.get('above_threshold', 0)}/{dist.get('total', 0)})")
    
    # Strategy Comparison
    if strategies:
        print(f"\n  Strategy Effectiveness")
        print(f"  {'─'*50}")
        header = f"  {'Version':<12} {'Outputs':>7} {'Avg':>5} {'Acc%':>6} {'Range':>7}"
        print(header)
        print(f"  {'─'*12} {'─'*7} {'─'*5} {'─'*6} {'─'*7}")
        for s in strategies:
            print(f"  {s['version']:<12} {s['outputs']:>7} {s['avg_score']:>5.1f} {s['acceptance_rate']:>5.0f}% {s['score_range']:>7}")
    
    # Critic Dimensions
    if critic.get("dimension_avgs"):
        print(f"\n  Critic Dimension Analysis")
        print(f"  {'─'*50}")
        for dim, avg in sorted(critic["dimension_avgs"].items(), key=lambda x: -x[1]):
            bar = "█" * int(avg) + "░" * (10 - int(avg))
            marker = ""
            if dim == critic["strongest_dimension"]:
                marker = " ★ strongest"
            elif dim == critic["weakest_dimension"]:
                marker = " ▽ weakest"
            label = dim.replace("_", " ").title()
            print(f"    {label:<22} [{bar}] {avg:.1f}{marker}")
    
    if critic.get("common_weaknesses"):
        print(f"\n  Top Weaknesses (from critic):")
        for w in critic["common_weaknesses"][:3]:
            print(f"    • {w['text'][:70]} ({w['count']}x)")
    
    # Research Patterns
    print(f"\n  Research Patterns")
    print(f"  {'─'*50}")
    print(f"  Avg attempts per question: {patterns.get('avg_attempts', 0):.1f}")
    print(f"  Retry rate: {patterns.get('retry_rate', 0):.0f}%")
    print(f"  Avg findings per output: {patterns.get('avg_findings_per_output', 0):.1f}")
    print(f"  Avg insights per output: {patterns.get('avg_insights_per_output', 0):.1f}")
    print(f"  Avg searches per output: {patterns.get('avg_searches_per_output', 0):.1f}")
    
    # Knowledge Velocity
    print(f"\n  Knowledge Accumulation")
    print(f"  {'─'*50}")
    vel_icon = {"fast": "🚀", "moderate": "▶", "slow": "▷", "stalled": "⏸"}.get(velocity.get("velocity_rating", ""), "?")
    print(f"  Velocity: {vel_icon} {velocity.get('velocity_rating', 'unknown')}")
    print(f"  Accepted outputs: {velocity.get('total_accepted', 0)}")
    print(f"  Total findings: {velocity.get('total_findings', 0)}")
    print(f"  KB claims: {velocity.get('total_claims', 0)}  |  Topics: {velocity.get('unique_topics', 0)}")
    print(f"  Claims per accepted output: {velocity.get('claims_per_accepted', 0):.1f}")
    print(f"  Knowledge gaps identified: {velocity.get('knowledge_gaps_identified', 0)}")
    
    print()


def _generate_recommendations(comparisons: list, cost_eff: dict, health: dict) -> list[str]:
    """Generate actionable recommendations from analytics data."""
    recs = []
    
    # Low acceptance rate domains
    for c in comparisons:
        if c["acceptance_rate"] < 50 and c["outputs"] >= 3:
            recs.append(f"[{c['domain']}] Low acceptance rate ({c['acceptance_rate']:.0f}%) — review strategy or question quality")
    
    # Declining domains
    for c in comparisons:
        if c["trend"] == "declining":
            recs.append(f"[{c['domain']}] Scores are declining — consider strategy rollback or manual review")
    
    # Domains without KB
    for c in comparisons:
        if c["kb_claims"] == 0 and c["accepted"] >= 3:
            recs.append(f"[{c['domain']}] Has {c['accepted']} accepted outputs but no KB — run --synthesize")
    
    # Domains with default strategy that have enough data
    for c in comparisons:
        if c["strategy_version"] == "default" and c["outputs"] >= 3:
            recs.append(f"[{c['domain']}] Still using default strategy with {c['outputs']} outputs — run --evolve")
    
    # High cost per accepted output
    if cost_eff["cost_per_accepted_output"] > 0.20:
        recs.append(f"High cost per accepted output (${cost_eff['cost_per_accepted_output']:.4f}) — focus on improving acceptance rate")
    
    # Low domain count
    if health["domain_count"] < 3:
        recs.append("Only {0} domain(s) — consider expanding into new research areas".format(health["domain_count"]))
    
    # Health score suggestions
    if health["health_score"] < 50:
        recs.append("System health below 50 — prioritize data accumulation and strategy evolution")
    
    if not recs:
        recs.append("System looks healthy! Continue accumulating data and evolving strategies.")
    
    return recs


# ============================================================
# Memory Search
# ============================================================

def search_memory(query: str, domains: list[str] | None = None, min_score: float = 0) -> list[dict]:
    """
    Search across all memory for outputs matching a query.
    
    Uses keyword matching against questions, summaries, and findings.
    
    Args:
        query: Search query text
        domains: Optional list of domains to search (default: all)
        min_score: Minimum score filter
        
    Returns:
        List of matching outputs, ranked by relevance
    """
    from memory_store import _tokenize, _relevance_score
    
    if domains is None:
        domains = discover_domains()
    
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    
    results = []
    for domain in domains:
        outputs = load_outputs(domain, min_score=min_score)
        for o in outputs:
            score = _relevance_score(query_tokens, o)
            if score > 0.05:
                results.append({
                    "domain": domain,
                    "question": o.get("question", ""),
                    "score": o.get("overall_score", 0),
                    "accepted": o.get("accepted", False),
                    "timestamp": o.get("timestamp", ""),
                    "summary": o.get("research", {}).get("summary", "")[:400],
                    "key_insights": o.get("research", {}).get("key_insights", [])[:5],
                    "relevance": round(score, 3),
                    "strategy": o.get("strategy_version", "default"),
                })
    
    results.sort(key=lambda r: r["relevance"], reverse=True)
    return results


def display_search_results(query: str, results: list[dict], max_display: int = 10):
    """Display formatted search results."""
    print(f"\n{'='*70}")
    print(f"  SEARCH RESULTS — \"{query}\"")
    print(f"{'='*70}")
    
    if not results:
        print(f"\n  No results found.")
        print()
        return
    
    print(f"\n  Found {len(results)} result(s):\n")
    
    for i, r in enumerate(results[:max_display], 1):
        accepted_mark = "✓" if r["accepted"] else "✗"
        print(f"  {i}. [{r['domain']}] {accepted_mark} Score: {r['score']}/10  |  Relevance: {r['relevance']:.3f}")
        print(f"     Q: {r['question'][:80]}")
        if r["summary"]:
            print(f"     → {r['summary'][:120]}")
        print()
    
    if len(results) > max_display:
        print(f"  ... and {len(results) - max_display} more results")
    print()
