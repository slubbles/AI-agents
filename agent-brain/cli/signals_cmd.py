"""CLI commands for signal collection and opportunity scoring."""

import json

from signal_collector import (
    collect_signals,
    get_collection_stats,
    get_top_opportunities,
    enrich_top_posts,
    check_engagement_changes,
    DEFAULT_SUBREDDITS,
    init_signals_db,
)
from opportunity_scorer import (
    score_unanalyzed,
    generate_weekly_brief,
    generate_build_spec,
    generate_opportunity_decision_packet,
)


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


def run_enrich_signals(limit: int = 50):
    """Enrich top posts with real engagement data via Scrapling."""
    stats = get_collection_stats()

    if stats["total_posts"] == 0:
        print("\n  No posts to enrich. Run --collect-signals first.\n")
        return

    print(f"\n{'='*60}")
    print(f"  ENRICHING POSTS (Scrapling)")
    print(f"  Posts available: {stats['total_posts']}")
    print(f"  Max to enrich: {limit}")
    print(f"{'='*60}\n")

    result = enrich_top_posts(limit=limit)

    print(f"\n{'='*60}")
    print(f"  ENRICHMENT COMPLETE")
    print(f"  Enriched: {result['enriched']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Skipped: {result['skipped']}")
    print(f"{'='*60}\n")


def run_build_spec(opportunity_rank: int):
    """Generate a build spec for a specific opportunity by rank."""
    opps = get_top_opportunities(limit=opportunity_rank)

    if not opps or len(opps) < opportunity_rank:
        print(f"\n  Opportunity #{opportunity_rank} not found. Only {len(opps) if opps else 0} scored.\n")
        return

    opp = opps[opportunity_rank - 1]
    print(f"\n{'='*60}")
    print(f"  GENERATING BUILD SPEC")
    print(f"  Opportunity #{opportunity_rank}: {opp.get('pain_point_summary', 'N/A')[:60]}")
    print(f"  Score: {opp.get('opportunity_score', 0)}/100")
    print(f"{'='*60}\n")

    spec = generate_build_spec(opp)

    if not spec:
        print("  Failed to generate build spec.\n")
        return

    print(f"  Product: {spec.get('product_name', 'N/A')}")
    print(f"  Problem: {spec.get('problem_statement', 'N/A')}")
    print(f"  Audience: {spec.get('target_audience', 'N/A')}")
    print(f"  Tech: {spec.get('tech_stack', 'N/A')}")
    print(f"  MVP: {spec.get('mvp_scope', 'N/A')}")
    print(f"  Revenue: {spec.get('monetization', 'N/A')}")

    features = spec.get("core_features", [])
    if features:
        print(f"\n  Core Features:")
        for f in features[:8]:
            print(f"    - {f}")

    competitors = spec.get("existing_competitors", [])
    if competitors:
        print(f"\n  Existing Competitors:")
        for c in competitors[:5]:
            print(f"    - {c}")

    gap = spec.get("competitive_gap", "")
    if gap:
        print(f"\n  Competitive Gap: {gap}")

    rqs = spec.get("research_questions", [])
    if rqs:
        print(f"\n  Research Questions for Brain:")
        for q in rqs[:5]:
            print(f"    ? {q}")

    print()


def run_reality_check(opportunity_rank: int, focus: str = ""):
    """Generate a commercial decision packet for a ranked opportunity."""
    opps = get_top_opportunities(limit=opportunity_rank)

    if not opps or len(opps) < opportunity_rank:
        print(f"\n  Opportunity #{opportunity_rank} not found. Only {len(opps) if opps else 0} scored.\n")
        return

    opp = opps[opportunity_rank - 1]
    print(f"\n{'='*60}")
    print("  REALITY CHECK")
    print(f"  Opportunity #{opportunity_rank}: {opp.get('pain_point_summary', 'N/A')[:60]}")
    print(f"  Score: {opp.get('opportunity_score', 0)}/100")
    print(f"{'='*60}\n")

    packet = generate_opportunity_decision_packet(opp, focus=focus)
    if not packet:
        print("  Failed to generate decision packet.\n")
        return

    spec = packet.get("build_spec", {})
    reality = packet.get("reality_check", {})
    summary = packet.get("decision_summary", {})

    print(f"  Product: {spec.get('product_name', 'N/A')}")
    print(f"  Verdict: {summary.get('verdict', reality.get('verdict', 'N/A'))}")
    worth = summary.get("worth_building_now", reality.get("worth_building_now"))
    if worth is not None:
        print(f"  Worth Building Now: {'Yes' if worth else 'No'}")

    wedge = summary.get("best_wedge")
    if wedge:
        print(f"  Best Wedge: {wedge}")

    gtm = summary.get("direct_gtm_plan")
    if gtm:
        print(f"  Direct GTM: {gtm}")

    why_not = reality.get("why_not")
    if why_not:
        print(f"\n  Why Not: {why_not}")

    objections = reality.get("strongest_objections", [])
    if objections:
        print("\n  Strongest Objections:")
        for item in objections[:5]:
            print(f"    - {item}")

    recommendation = reality.get("final_recommendation")
    if recommendation:
        print(f"\n  Final Recommendation: {recommendation}")

    artifact_path = packet.get("artifact_path")
    if artifact_path:
        print(f"\n  Saved: {artifact_path}")

    print()


def run_engagement_check():
    """Check engagement changes on high-scoring opportunities."""
    init_signals_db()

    print(f"\n{'='*60}")
    print(f"  ENGAGEMENT FEEDBACK CHECK")
    print(f"{'='*60}\n")

    changes = check_engagement_changes(min_score=60)

    if not changes:
        print("  No posts with engagement data to check.")
        print("  Run --enrich-signals first to collect engagement data.")
        return

    growing = [c for c in changes if c["growing"]]
    print(f"  Checked: {len(changes)} posts")
    print(f"  Growing: {len(growing)}")
    print(f"  Stable/declining: {len(changes) - len(growing)}")

    if growing:
        print(f"\n  GROWING OPPORTUNITIES (demand validated):")
        for c in growing:
            print(f"    Post #{c['post_id']} (score: {c['opportunity_score']}/100)")
            print(f"      Upvotes: {c['old_score']} -> {c['new_score']} ({c['score_delta']:+d})")
            print(f"      Comments: {c['old_comments']} -> {c['new_comments']} ({c['comment_delta']:+d})")

    print()
