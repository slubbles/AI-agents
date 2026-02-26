"""
Execution Analytics — Deep insights into execution patterns and performance.

Analyzes execution memory to surface:
- Tool usage patterns (most/least used, success rates per tool)
- Error pattern trends (most common failure categories)
- Score trajectory (is the system improving?)
- Step efficiency (average steps per task, retry rates)
- Time-of-day patterns (optional)

Used by --exec-status for rich reporting and by the meta-analyst
for data-driven strategy evolution.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hands.exec_memory import load_exec_outputs


def analyze_executions(domain: str) -> dict:
    """
    Comprehensive analysis of all execution outputs for a domain.
    
    Returns dict with:
        - summary: basic stats
        - tool_stats: per-tool success rates and usage counts
        - error_patterns: most common error categories
        - score_trajectory: score over time
        - efficiency: steps per task, retry rates
        - complexity_breakdown: scores by estimated complexity
    """
    outputs = load_exec_outputs(domain)
    
    if not outputs:
        return {"summary": {"count": 0}, "has_data": False}
    
    # === Summary ===
    scores = [o.get("overall_score", 0) for o in outputs]
    accepted = sum(1 for o in outputs if o.get("accepted"))
    
    summary = {
        "count": len(outputs),
        "avg_score": sum(scores) / len(scores),
        "min_score": min(scores),
        "max_score": max(scores),
        "accepted": accepted,
        "rejected": len(outputs) - accepted,
        "accept_rate": accepted / len(outputs) if outputs else 0,
    }
    
    # === Tool Stats ===
    tool_usage = Counter()
    tool_success = Counter()
    tool_failures = Counter()
    
    for o in outputs:
        exec_data = o.get("execution", {})
        for step in exec_data.get("step_results", []):
            tool = step.get("tool", "unknown")
            tool_usage[tool] += 1
            if step.get("success"):
                tool_success[tool] += 1
            else:
                tool_failures[tool] += 1
    
    tool_stats = {}
    for tool in tool_usage:
        total = tool_usage[tool]
        successes = tool_success.get(tool, 0)
        tool_stats[tool] = {
            "total_uses": total,
            "successes": successes,
            "failures": tool_failures.get(tool, 0),
            "success_rate": successes / total if total > 0 else 0,
        }
    
    # Sort by usage count
    tool_stats = dict(sorted(tool_stats.items(), key=lambda x: x[1]["total_uses"], reverse=True))
    
    # === Error Patterns ===
    error_categories = Counter()
    error_examples = defaultdict(list)
    
    for o in outputs:
        val = o.get("validation", {})
        static = val.get("static_checks", {})
        
        # From static checks
        for issue in static.get("issues", []):
            check = issue.get("check", "unknown")
            error_categories[f"static:{check}"] += 1
        
        # From critical issues
        for issue in val.get("critical_issues", []):
            if isinstance(issue, str):
                # Simplify the issue description
                simplified = issue[:60]
                error_categories[simplified] += 1
        
        # From weaknesses
        for weakness in val.get("weaknesses", []):
            if isinstance(weakness, str) and len(weakness) > 10:
                error_categories[weakness[:60]] += 1
    
    # Top error patterns
    error_patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in error_categories.most_common(10)
    ]
    
    # === Score Trajectory ===
    score_trajectory = []
    for o in outputs:
        ts = o.get("timestamp", "")
        score = o.get("overall_score", 0)
        if ts:
            score_trajectory.append({"timestamp": ts[:10], "score": score})
    
    # Rolling average (window of 3)
    rolling_avg = []
    window = 3
    for i in range(len(scores)):
        start = max(0, i - window + 1)
        window_scores = scores[start:i + 1]
        rolling_avg.append(sum(window_scores) / len(window_scores))
    
    # Score trend: compare first third vs last third
    third = max(1, len(scores) // 3)
    first_third_avg = sum(scores[:third]) / third
    last_third_avg = sum(scores[-third:]) / third
    trend = "improving" if last_third_avg > first_third_avg + 0.3 else (
        "declining" if last_third_avg < first_third_avg - 0.3 else "stable"
    )
    
    trajectory = {
        "scores": score_trajectory,
        "rolling_avg": rolling_avg,
        "trend": trend,
        "first_third_avg": round(first_third_avg, 2),
        "last_third_avg": round(last_third_avg, 2),
    }
    
    # === Efficiency ===
    total_steps_planned = 0
    total_steps_completed = 0
    total_steps_failed = 0
    total_retried = 0
    
    for o in outputs:
        exec_data = o.get("execution", {})
        total_steps_planned += exec_data.get("total_steps", 0)
        total_steps_completed += exec_data.get("completed_steps", 0)
        total_steps_failed += exec_data.get("failed_steps", 0)
    
    efficiency = {
        "avg_steps_per_task": total_steps_planned / len(outputs) if outputs else 0,
        "completion_rate": (
            total_steps_completed / total_steps_planned
            if total_steps_planned > 0 else 0
        ),
        "failure_rate": (
            total_steps_failed / total_steps_planned
            if total_steps_planned > 0 else 0
        ),
        "total_steps_executed": total_steps_completed + total_steps_failed,
    }
    
    # === Complexity Breakdown ===
    complexity_scores = defaultdict(list)
    for o in outputs:
        complexity = o.get("plan", {}).get("estimated_complexity", "unknown")
        complexity_scores[complexity].append(o.get("overall_score", 0))
    
    complexity_breakdown = {}
    for complexity, c_scores in complexity_scores.items():
        complexity_breakdown[complexity] = {
            "count": len(c_scores),
            "avg_score": sum(c_scores) / len(c_scores),
        }
    
    # === Dimension Scores ===
    dimension_totals = defaultdict(list)
    for o in outputs:
        val_scores = o.get("validation", {}).get("scores", {})
        for dim, score in val_scores.items():
            if isinstance(score, (int, float)):
                dimension_totals[dim].append(score)
    
    dimension_averages = {
        dim: round(sum(vals) / len(vals), 2)
        for dim, vals in dimension_totals.items()
        if vals
    }
    
    return {
        "has_data": True,
        "summary": summary,
        "tool_stats": tool_stats,
        "error_patterns": error_patterns,
        "score_trajectory": trajectory,
        "efficiency": efficiency,
        "complexity_breakdown": complexity_breakdown,
        "dimension_averages": dimension_averages,
    }


def format_analytics_report(analytics: dict) -> str:
    """Format analytics into a rich CLI report."""
    if not analytics.get("has_data"):
        return "No execution data available."
    
    lines = []
    s = analytics["summary"]
    
    # Summary
    lines.append(f"  Executions: {s['count']} | Avg: {s['avg_score']:.1f} | "
                 f"Range: {s['min_score']:.1f}-{s['max_score']:.1f} | "
                 f"Accept: {s['accept_rate']:.0%}")
    
    # Score trajectory
    traj = analytics.get("score_trajectory", {})
    if traj.get("trend"):
        trend_arrow = {"improving": "↑", "declining": "↓", "stable": "→"}.get(traj["trend"], "?")
        lines.append(f"\n  Score Trend: {trend_arrow} {traj['trend']} "
                     f"({traj['first_third_avg']:.1f} → {traj['last_third_avg']:.1f})")
    
    # Dimension scores
    dims = analytics.get("dimension_averages", {})
    if dims:
        dim_parts = [f"{d}: {v:.1f}" for d, v in sorted(dims.items())]
        lines.append(f"\n  Dimensions: {' | '.join(dim_parts)}")
    
    # Tool stats
    tool_stats = analytics.get("tool_stats", {})
    if tool_stats:
        lines.append(f"\n  Tool Usage:")
        for tool, stats in list(tool_stats.items())[:6]:
            bar = "█" * int(stats["success_rate"] * 10) + "░" * (10 - int(stats["success_rate"] * 10))
            lines.append(f"    {tool:12s} {bar} {stats['success_rate']:.0%} "
                        f"({stats['successes']}/{stats['total_uses']})")
    
    # Efficiency
    eff = analytics.get("efficiency", {})
    if eff:
        lines.append(f"\n  Efficiency: {eff['avg_steps_per_task']:.1f} steps/task | "
                     f"Step completion: {eff['completion_rate']:.0%}")
    
    # Complexity breakdown
    cpx = analytics.get("complexity_breakdown", {})
    if cpx:
        cpx_parts = [f"{k}: {v['avg_score']:.1f} ({v['count']})" for k, v in sorted(cpx.items())]
        lines.append(f"\n  By Complexity: {' | '.join(cpx_parts)}")
    
    # Error patterns
    errors = analytics.get("error_patterns", [])
    if errors:
        lines.append(f"\n  Top Issues:")
        for e in errors[:5]:
            lines.append(f"    {e['count']}x {e['pattern']}")
    
    return "\n".join(lines)
