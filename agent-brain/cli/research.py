"""Research CLI commands — auto mode, orchestration, next questions."""

import json
import os
from datetime import datetime, timezone

from config import DEFAULT_DOMAIN, LOG_DIR, AUTO_DEDUP_RETRIES
from cost_tracker import check_budget, get_daily_spend
from memory_store import get_stats
from strategy_store import list_pending
from agents.question_generator import generate_questions, get_next_question
from domain_seeder import get_seed_question, get_seed_questions, has_curated_seeds


def show_next(domain: str):
    """Show self-generated next questions for a domain."""
    print(f"\n{'='*60}")
    print(f"  NEXT QUESTIONS — Domain: {domain}")
    print(f"  (Stage 1: Diagnose Needs → Stage 2: Set Goals)")
    print(f"{'='*60}\n")

    budget = check_budget()
    if not budget["within_budget"]:
        print(f"  ✗ Budget exceeded. Use --budget to see details.")
        return

    result = generate_questions(domain)
    if not result:
        print("  No questions generated. Need at least 1 output in this domain first.")
        return

    print(f"\n  To auto-research the top question:")
    print(f"    python main.py --domain {domain} --auto")
    print(f"\n  Or pick one manually:")
    for i, q in enumerate(result["questions"], 1):
        print(f"    python main.py --domain {domain} \"{q.get('question', '')}\"")
    print()


def generate_digest(domain: str, round_results: list[dict], dedup_skipped: int = 0) -> dict:
    """
    Generate a run digest summarizing what happened.

    Includes: questions researched, scores, strategy changes, alerts, spend.
    Returns dict that can be printed or sent via webhook.
    """
    stats = get_stats(domain)
    daily = get_daily_spend()

    # Compute score stats from this run
    scores = [r["score"] for r in round_results if r.get("score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    accepted = sum(1 for r in round_results if r.get("verdict") == "accept")
    rejected = len(round_results) - accepted

    # Check for strategy changes
    pending = list_pending("researcher", domain)

    # Check recent alerts
    try:
        from db import get_alerts
        recent_alerts = get_alerts(limit=10, severity=None, domain=domain)
    except Exception:
        recent_alerts = []

    digest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "rounds_completed": len(round_results),
        "dedup_skipped": dedup_skipped,
        "scores": {
            "avg": round(avg_score, 1),
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "accepted": accepted,
            "rejected": rejected,
        },
        "questions": [r.get("question", "")[:80] for r in round_results],
        "domain_totals": {
            "count": stats["count"],
            "avg_score": round(stats["avg_score"], 1),
            "accepted": stats["accepted"],
        },
        "spend_today_usd": round(daily["total_usd"], 4),
        "pending_strategies": len(pending),
        "recent_alerts": len(recent_alerts),
    }

    # Print digest summary
    print(f"\n  ── Run Digest ──")
    print(f"  Avg score this run: {avg_score:.1f} ({accepted} accepted, {rejected} rejected)")
    if dedup_skipped > 0:
        print(f"  Dedup skipped: {dedup_skipped} duplicate question(s)")
    if pending:
        print(f"  ⚠ {len(pending)} pending strategy(ies) await approval")
    if recent_alerts:
        print(f"  ⚠ {len(recent_alerts)} recent alert(s) — run --check-health for details")

    # Save digest to log file
    digest_path = os.path.join(LOG_DIR, "digests.jsonl")
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        with open(digest_path, "a") as f:
            f.write(json.dumps(digest) + "\n")
    except Exception as e:
        print(f"  [DIGEST] ⚠ Failed to save digest: {e}")

    # Webhook push (if configured)
    webhook_url = os.environ.get("AGENT_BRAIN_WEBHOOK_URL")
    if webhook_url:
        push_webhook(webhook_url, digest)

    return digest


def push_webhook(url: str, payload: dict):
    """Push a digest payload to a webhook URL (Slack, Discord, etc.)."""
    import urllib.request
    import urllib.error

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 300:
                print(f"  [WEBHOOK] ✓ Digest pushed ({resp.status})")
            else:
                print(f"  [WEBHOOK] ⚠ Unexpected status: {resp.status}")
    except urllib.error.URLError as e:
        print(f"  [WEBHOOK] ⚠ Failed to push: {e}")
    except Exception as e:
        print(f"  [WEBHOOK] ⚠ Error: {e}")


def run_auto(domain: str, rounds: int = 1):
    """
    Self-directed learning mode.

    The system:
    1. Diagnoses its own knowledge gaps (Stage 1)
    2. Generates the best next question (Stage 2)
    3. Researches it (Stages 3+4)
    4. Evaluates the result (Stage 5)
    5. Repeats for N rounds

    This is the full Knowles self-directed learning cycle, automated.
    Questions are directed by the domain goal (if set) to keep research actionable.
    """
    from main import run_loop  # lazy import — avoids circular dependency
    from domain_goals import get_goal

    goal = get_goal(domain)

    print(f"\n{'='*60}")
    print(f"  SELF-DIRECTED LEARNING MODE")
    print(f"  Domain: {domain}")
    print(f"  Rounds: {rounds}")
    if goal:
        print(f"  Goal: {goal[:80]}{'...' if len(goal) > 80 else ''}")
    else:
        print(f"  Goal: NOT SET — research may not be actionable")
        print(f"         Set with: python main.py --set-goal --domain {domain}")
    print(f"{'='*60}\n")

    question = None  # Initialize before loop to avoid NameError in summary
    round_results = []
    dedup_skipped = 0
    for round_num in range(1, rounds + 1):
        print(f"\n{'─'*50}")
        print(f"  ROUND {round_num}/{rounds}")
        print(f"{'─'*50}\n")

        # Budget check each round
        budget = check_budget()
        if not budget["within_budget"]:
            print(f"[BUDGET] ✗ BLOCKED — daily limit reached after {round_num - 1} rounds")
            break

        print(f"[BUDGET] ${budget['remaining']:.4f} remaining")

        # Stage 1+2: Diagnose needs → Set goal
        print(f"\n[STAGE 1+2] Diagnosing knowledge gaps and generating next question...")
        question = get_next_question(domain)

        if not question:
            # First time in domain — use seed questions
            stats = get_stats(domain)
            if stats["count"] == 0:
                question = get_seed_question(domain)
                curated = "curated" if has_curated_seeds(domain) else "generic"
                print(f"[SEED] Domain '{domain}' has no outputs — using {curated} seed question")
            else:
                print(f"[QUESTION-GEN] Failed to generate question. Stopping.")
                break

        print(f"\n[QUESTION] → {question}")

        # Dedup check — avoid re-researching known questions
        from memory_store import is_duplicate_question
        is_dup, matched = is_duplicate_question(domain, question, threshold=0.80)
        if is_dup:
            # Retry question generation up to AUTO_DEDUP_RETRIES times
            retried = False
            for dedup_attempt in range(AUTO_DEDUP_RETRIES):
                print(f"[DEDUP] ⚠ Too similar to: {matched[:100]}")
                print(f"[DEDUP] Regenerating question (attempt {dedup_attempt + 2})...")
                question = get_next_question(domain)
                if not question:
                    break
                is_dup, matched = is_duplicate_question(domain, question, threshold=0.80)
                if not is_dup:
                    retried = True
                    print(f"[DEDUP] ✓ New question accepted: {question[:80]}")
                    break
            if not retried:
                print(f"[DEDUP] ⚠ Skipping — all {AUTO_DEDUP_RETRIES + 1} attempts were duplicates")
                dedup_skipped += 1
                continue

        # Stages 3+4+5: Research → Evaluate (handled by run_loop)
        print(f"\n[STAGE 3-5] Researching, evaluating, storing...")
        try:
            result = run_loop(question=question, domain=domain)
        except SystemExit:
            # run_loop calls sys.exit on budget exceeded
            print(f"[AUTO] Stopped — budget exceeded during round {round_num}")
            break

        if result is None:
            print(f"\n[ROUND {round_num}] Research failed — no result returned")
            round_results.append({
                "round": round_num,
                "question": question,
                "score": 0,
                "verdict": "failed",
            })
            continue

        score = result.get("critique", {}).get("overall_score", 0)
        verdict = result.get("critique", {}).get("verdict", "unknown")
        round_results.append({
            "round": round_num,
            "question": question,
            "score": score,
            "verdict": verdict,
        })

        print(f"\n[ROUND {round_num} COMPLETE] Score: {score}/10 — {verdict}")

        if round_num < rounds:
            print(f"\n  Continuing to round {round_num + 1}...")

    # Run claim expiry check after auto rounds
    from memory_store import expire_stale_claims
    expiry = expire_stale_claims(domain)
    if expiry["flagged"] > 0 or expiry["expired"] > 0:
        print(f"\n[CLAIM EXPIRY] Flagged {expiry['flagged']} stale, expired {expiry['expired']} claims")

    # Generate digest
    digest = generate_digest(domain, round_results, dedup_skipped)

    # Summary
    stats = get_stats(domain)
    daily = get_daily_spend()
    print(f"\n{'='*60}")
    print(f"  AUTO MODE COMPLETE")
    print(f"  Rounds completed: {len(round_results)}/{rounds} ({dedup_skipped} skipped as duplicates)")
    print(f"  Domain '{domain}': {stats['count']} total outputs, avg {stats['avg_score']:.1f}")
    print(f"  Today's spend: ${daily['total_usd']:.4f}")
    print(f"{'='*60}\n")

    return digest


def run_orchestrate(target_domains: list[str] | None, total_rounds: int):
    """
    Smart multi-domain orchestration.

    The Orchestrator:
    1. Analyzes all domains → computes priority scores
    2. Allocates rounds based on priority (budget-aware)
    3. Runs auto mode per domain
    4. After each domain: checks for synthesis/evolution triggers
    5. At end: re-extracts cross-domain principles if applicable
    """
    from main import run_loop  # lazy import
    from agents.meta_analyst import analyze_and_evolve
    from agents.synthesizer import synthesize
    from agents.cross_domain import extract_principles, get_transfer_sources
    from agents.orchestrator import (
        prioritize_domains, allocate_rounds, get_post_run_actions,
        get_system_health,
    )
    from utils.retry import retry_api_call, is_retryable

    print(f"\n{'='*60}")
    print(f"  ORCHESTRATOR — Multi-Domain Coordination")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    # Budget gate
    budget = check_budget()
    if not budget["within_budget"]:
        print(f"\n  ✗ Budget exceeded (${budget['spent']:.2f}/${budget['limit']:.2f})")
        return

    print(f"\n  Budget: ${budget['remaining']:.2f} remaining today")
    print(f"  Total rounds requested: {total_rounds}")

    # Step 1: Prioritize domains
    print(f"\n  ── Domain Priority Analysis ──")
    priorities = prioritize_domains(target_domains)

    if not priorities:
        print(f"  No domains found. Run a manual question first.")
        return

    print(f"  {'Domain':<16} {'Priority':>8} {'Outputs':>7} {'Rate':>6} {'Strategy':<10} {'Action'}")
    print(f"  {'─'*70}")
    for p in priorities:
        count = p["stats"]["count"]
        accepted = p["stats"]["accepted"]
        rate = f"{accepted/count*100:.0f}%" if count > 0 else "—"
        print(f"  {p['domain']:<16} {p['priority']:>8.1f} {count:>7} {rate:>6} {p['strategy']:<10} {p['action']}")
        for reason in p["reasons"][:2]:
            print(f"  {'':>16} ↳ {reason}")

    # Step 2: Allocate rounds
    allocation = allocate_rounds(priorities, total_rounds)

    if not allocation:
        print(f"\n  No actionable domains. Check pending approvals.")
        # Show what's blocked
        for p in priorities:
            if p["skip"]:
                print(f"  ⚠ {p['domain']}: {'; '.join(p['reasons'])}")
        return

    print(f"\n  ── Round Allocation ──")
    for a in allocation:
        print(f"  {a['domain']:<16} → {a['rounds']} round(s)")
    total_allocated = sum(a["rounds"] for a in allocation)
    print(f"  {'TOTAL':<16} → {total_allocated} round(s)")

    # Step 3: Execute rounds per domain
    results_summary = []
    total_completed = 0

    for i, alloc in enumerate(allocation):
        domain = alloc["domain"]
        rounds = alloc["rounds"]

        print(f"\n{'='*60}")
        print(f"  DOMAIN {i+1}/{len(allocation)}: {domain.upper()}")
        print(f"  Allocated: {rounds} round(s)")
        print(f"{'='*60}")

        # Budget check before each domain
        budget = check_budget()
        if not budget["within_budget"]:
            print(f"\n  ✗ Budget exceeded — stopping orchestration")
            break

        domain_scores = []
        domain_completed = 0

        for round_num in range(1, rounds + 1):
            # Budget check each round
            budget = check_budget()
            if not budget["within_budget"]:
                print(f"\n  [BUDGET] ✗ Daily limit reached after {round_num - 1} rounds in {domain}")
                break

            print(f"\n  ── Round {round_num}/{rounds} (${budget['remaining']:.2f} remaining) ──")

            # Generate question (with retry for transient API errors)
            question = None
            domain_stats = get_stats(domain)

            if domain_stats["count"] == 0:
                # Use seed questions for empty domains (no API call needed!)
                seed_questions = get_seed_questions(domain, count=rounds)
                seed_idx = round_num - 1
                if seed_idx < len(seed_questions):
                    question = seed_questions[seed_idx]
                    curated = "curated" if has_curated_seeds(domain) else "generic"
                    print(f"  [SEED] Using {curated} seed question ({seed_idx+1}/{len(seed_questions)})")
                else:
                    question = get_seed_question(domain)
                    print(f"  [SEED] Reusing seed question (all seeds exhausted)")
            else:
                try:
                    question = retry_api_call(
                        lambda d=domain: get_next_question(d),
                        max_attempts=5, base_delay=30, verbose=True,
                    )
                except Exception as e:
                    if is_retryable(e):
                        print(f"  ✗ API still overloaded after retries. Skipping {domain}.")
                    else:
                        print(f"  ✗ Question generation error: {e}")
            if not question:
                print(f"  ✗ Failed to generate question for {domain}. Stopping.")
                break

            print(f"  [Q] {question[:80]}")

            # Run the loop (with retry for transient API errors)
            result = None
            try:
                result = retry_api_call(
                    lambda q=question, d=domain: run_loop(question=q, domain=d),
                    max_attempts=5, base_delay=30, verbose=True,
                )
            except SystemExit:
                print(f"  ✗ Budget exceeded during run in {domain}")
                break
            except Exception as e:
                if is_retryable(e):
                    print(f"  ✗ API still overloaded after retries. Skipping round.")
                else:
                    print(f"  ✗ Run error: {e}")

            if result is None:
                print(f"  ✗ Round failed for {domain}. Continuing...")
                continue

            score = result.get("critique", {}).get("overall_score", 0)
            verdict = result.get("critique", {}).get("verdict", "unknown")
            domain_scores.append(score)
            domain_completed += 1
            total_completed += 1

            print(f"  [RESULT] {score}/10 — {verdict}")

        # Post-run actions for this domain
        post_actions = get_post_run_actions(domain)
        for pa in post_actions:
            if pa["action"] == "synthesize":
                print(f"\n  [POST] Synthesizing knowledge base... ({pa['reason']})")
                try:
                    kb = synthesize(domain, force=True)
                    if kb:
                        active_claims = len([c for c in kb.get("claims", []) if c.get("status") == "active"])
                        print(f"  [SYNTHESIZE] ✓ {active_claims} active claims")
                except Exception as e:
                    print(f"  [SYNTHESIZE] ✗ Failed: {e}")

            elif pa["action"] == "evolve":
                print(f"\n  [POST] Triggering strategy evolution... ({pa['reason']})")
                try:
                    evolution = analyze_and_evolve(domain)
                    if evolution:
                        print(f"  [EVOLVE] ✓ Strategy evolved to {evolution['new_version']}")
                except Exception as e:
                    print(f"  [EVOLVE] ✗ Failed: {e}")

        # Domain summary
        avg = sum(domain_scores) / len(domain_scores) if domain_scores else 0
        stats = get_stats(domain)
        results_summary.append({
            "domain": domain,
            "rounds_completed": domain_completed,
            "rounds_allocated": rounds,
            "avg_score": round(avg, 1),
            "total_outputs": stats["count"],
            "accepted": stats["accepted"],
        })

    # Step 4: Cross-domain principle extraction (if applicable)
    budget = check_budget()
    if budget["within_budget"] and total_completed >= 3:
        sources = get_transfer_sources()
        if len(sources) >= 2:
            print(f"\n  ── Cross-Domain Principles ──")
            print(f"  {len(sources)} qualifying domains — extracting updated principles...")
            try:
                principles = extract_principles(force=True)
                if principles:
                    p_count = len(principles.get("principles", []))
                    print(f"  ✓ Extracted {p_count} principles (v{principles.get('version', '?')})")
            except Exception as e:
                print(f"  ✗ Principle extraction failed: {e}")

    # Final Summary
    daily = get_daily_spend()
    health = get_system_health()

    print(f"\n{'='*60}")
    print(f"  ORCHESTRATION COMPLETE")
    print(f"{'='*60}")
    print(f"\n  Rounds completed: {total_completed}/{total_allocated}")
    print(f"\n  Results by domain:")
    print(f"  {'Domain':<16} {'Done':>5} {'Avg':>5} {'Total':>6} {'Accepted':>8}")
    print(f"  {'─'*45}")
    for r in results_summary:
        print(f"  {r['domain']:<16} {r['rounds_completed']:>5} {r['avg_score']:>5.1f} {r['total_outputs']:>6} {r['accepted']:>8}")

    print(f"\n  Budget: ${daily['total_usd']:.4f} spent today ({daily['calls']} API calls)")
    print(f"  System health: {health['health_score']}/100")
    print(f"{'='*60}\n")


def run_smart_orchestrate(args):
    """LLM-reasoned orchestration — Claude decides domain allocation."""
    from agents.orchestrator import smart_orchestrate

    print(f"\n{'='*60}")
    print(f"  SMART ORCHESTRATOR — LLM-Reasoned Allocation")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    total = args.rounds if hasattr(args, 'rounds') and args.rounds else 5
    target = args.target.split(",") if hasattr(args, 'target') and args.target else None

    result = smart_orchestrate(total_rounds=total, target_domains=target)

    if not result:
        print("\n  ✗ Smart orchestration failed.")
        return

    print(f"\n  Reasoning: {result.get('reasoning', 'N/A')}")
    print(f"\n  Allocation:")
    allocation = result.get("allocation", [])
    for a in allocation:
        print(f"    {a['domain']:<16} → {a['rounds']} round(s)")
        if a.get("reason"):
            print(f"    {'':>16}   ↳ {a['reason']}")

    actions = result.get("recommended_actions", [])
    if actions:
        print(f"\n  Recommended actions:")
        for act in actions:
            print(f"    • {act}")

    # Execute the allocation
    if allocation:
        print(f"\n  Executing allocation...")
        targets = [a["domain"] for a in allocation]
        total_rounds = sum(a["rounds"] for a in allocation)
        run_orchestrate(targets, total_rounds)
