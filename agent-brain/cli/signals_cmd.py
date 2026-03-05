"""CLI commands for signal collection and opportunity scoring."""

import json

from signal_collector import (
    collect_signals,
    get_collection_stats,
    get_top_opportunities,
    DEFAULT_SUBREDDITS,
    init_signals_db,
)
from opportunity_scorer import score_unanalyzed, generate_weekly_brief


def run_collect_signals(subreddits: str = "", time_filter: str = "month"):
    """Collect pain-point signals from Reddit."""
    subs = [s.strip() for s in subreddits.split(",") if s.strip()] if subreddits else None

    print(f"\n{'='*60}")
    print(f"  SIGNAL COLLECTION")
    print(f"  Subreddits: {', '.join(subs or DEFAULT_SUBREDDITS)}")
    print(f"  Time filter: {time_filter}")
    print(f"{'='*60}\n")

    result = collect_signals(subreddits=subs, time_filter=time_filter)

    print(f"\n{'='*60}")
    print(f"  COLLECTION COMPLETE")
    print(f"  Duration: {result['duration_seconds']}s")
    print(f"  Posts found: {result['total_found']}")
    print(f"  Pain-point matches: {result['total_matched']}")
    print(f"  New (not seen before): {result['total_new']}")
    print(f"{'='*60}\n")


def run_rank_opportunities(batch_size: int = 10, max_batches: int = 5):
    """Score unanalyzed posts and show top opportunities."""
    stats = get_collection_stats()

    if stats["unanalyzed"] == 0:
        print("\n  No unanalyzed posts. Run --collect-signals first.\n")
        return

    print(f"\n{'='*60}")
    print(f"  SCORING OPPORTUNITIES")
    print(f"  Unanalyzed posts: {stats['unanalyzed']}")
    print(f"  Batch size: {batch_size}, Max batches: {max_batches}")
    print(f"{'='*60}\n")

    result = score_unanalyzed(batch_size=batch_size, max_batches=max_batches)

    print(f"\n  Analyzed: {result['analyzed']} posts in {result['batches']} batches")
    print(f"  Highest score: {result['top_score']}/100\n")

    # Show top 10
    _show_top_opportunities(10)


def run_weekly_brief():
    """Generate and display the weekly opportunity brief."""
    stats = get_collection_stats()

    if stats["analyzed"] == 0:
        print("\n  No analyzed posts yet. Run --collect-signals then --rank-opportunities first.\n")
        return

    print(f"\n  Generating weekly brief (premium model for top-3 synthesis)...\n")

    brief = generate_weekly_brief()
    print(brief)


def run_signal_status():
    """Show signal collection and analysis stats."""
    init_signals_db()
    stats = get_collection_stats()

    print(f"\n{'='*60}")
    print(f"  SIGNAL INTELLIGENCE STATUS")
    print(f"{'='*60}")
    print(f"  Total posts collected: {stats['total_posts']}")
    print(f"  Analyzed: {stats['analyzed']}")
    print(f"  Awaiting analysis: {stats['unanalyzed']}")
    print(f"  Collection runs: {stats['collection_runs']}")
    print(f"  Subreddits tracked: {len(stats.get('subreddits', []))}")

    if stats.get("top_subreddits"):
        print(f"\n  Top subreddits by post count:")
        for sub, count in stats["top_subreddits"].items():
            print(f"    r/{sub}: {count} posts")

    # Show top 5 opportunities if any exist
    if stats["analyzed"] > 0:
        print(f"\n  Top 5 Opportunities:")
        _show_top_opportunities(5)

    print()


def _show_top_opportunities(limit: int = 10):
    """Display top opportunities in a table format."""
    opps = get_top_opportunities(limit=limit)

    if not opps:
        print("  No scored opportunities yet.")
        return

    print(f"\n  {'#':<3} {'Score':<6} {'Sev':<4} {'Subreddit':<20} {'Pain Point':<50}")
    print(f"  {'-'*3} {'-'*5} {'-'*3} {'-'*19} {'-'*49}")

    for i, opp in enumerate(opps, 1):
        pain = (opp.get("pain_point_summary") or "N/A")[:48]
        sub = opp.get("subreddit", "?")[:18]
        score = opp.get("opportunity_score", 0)
        sev = opp.get("severity", 0)
        print(f"  {i:<3} {score:<6} {sev:<4} r/{sub:<18} {pain}")
