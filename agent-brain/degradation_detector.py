"""
Degradation Detector — Long-Horizon Health Monitoring

Closes the gap in Guarantee #6: "System doesn't degrade during long unsupervised runtime."

The existing monitoring catches acute problems (sudden drops, error spikes).
This module catches SLOW decay that takes 50-100+ cycles to manifest:

1. Question diversity decay — asking repetitive/similar questions over time
2. Score stagnation — plateau that monitoring treats as "fine" but means no learning
3. Strategy drift — current strategy diverges too far from core principles
4. Knowledge saturation — diminishing returns per cycle in a domain
5. Memory health trend — is the KB getting cleaner or noisier over time?

Designed to run:
- Every N daemon cycles (alongside memory lifecycle)
- Manually via --health-pulse CLI command
- As part of --review to add long-term context

No API calls — pure data analysis.
"""

import json
import os
import math
from datetime import datetime, timezone, timedelta
from collections import Counter
from config import MEMORY_DIR, STRATEGY_DIR, LOG_DIR, DRIFT_WARNING_THRESHOLD


def check_question_diversity(domain: str, window: int = 30) -> dict:
    """
    Detect if the system is asking repetitive questions.

    Compares recent questions against all historical questions using
    word overlap. High overlap = low diversity = wasted cycles.

    Returns:
        {diversity_score: 0-1, repeated_themes: [...], verdict: "healthy"|"declining"|"repetitive"}
    """
    from memory_store import load_outputs

    outputs = load_outputs(domain, min_score=0)
    if len(outputs) < window:
        return {"diversity_score": 1.0, "verdict": "insufficient_data", "count": len(outputs)}

    questions = [o.get("question", "") for o in outputs if o.get("question")]
    if len(questions) < window:
        return {"diversity_score": 1.0, "verdict": "insufficient_data", "count": len(questions)}

    recent = questions[-window:]

    def _tokenize(text):
        return set(w.lower().strip("?.,!") for w in text.split() if len(w) > 2)

    # Pairwise similarity within recent window
    recent_tokens = [_tokenize(q) for q in recent]
    similarities = []
    for i in range(len(recent_tokens)):
        for j in range(i + 1, len(recent_tokens)):
            if recent_tokens[i] and recent_tokens[j]:
                overlap = len(recent_tokens[i] & recent_tokens[j])
                union = len(recent_tokens[i] | recent_tokens[j])
                similarities.append(overlap / union if union > 0 else 0)

    avg_similarity = sum(similarities) / len(similarities) if similarities else 0
    diversity_score = round(1.0 - avg_similarity, 3)

    # Find repeated theme words
    all_words = Counter()
    for tokens in recent_tokens:
        all_words.update(tokens)
    stop_words = {"what", "does", "about", "with", "from", "that", "this", "have",
                  "been", "will", "there", "their", "which", "would", "could", "should",
                  "into", "more", "than", "they", "them", "some", "other", "when", "where"}
    repeated = [word for word, count in all_words.most_common(10)
                if count >= window * 0.3 and word not in stop_words]

    if diversity_score >= 0.7:
        verdict = "healthy"
    elif diversity_score >= 0.4:
        verdict = "declining"
    else:
        verdict = "repetitive"

    return {
        "diversity_score": diversity_score,
        "verdict": verdict,
        "avg_pairwise_similarity": round(avg_similarity, 3),
        "repeated_themes": repeated[:5],
        "window": window,
        "count": len(questions),
    }


def check_score_stagnation(domain: str, window: int = 20, min_improvement: float = 0.3) -> dict:
    """
    Detect if scores have stagnated — not declining, but not improving either.

    Stagnation means the system is cycling without learning.
    Different from a decline (which monitoring catches) — this catches plateau.

    Returns:
        {stagnant: bool, window_avg: float, improvement_rate: float, verdict: str}
    """
    from memory_store import load_outputs

    outputs = load_outputs(domain, min_score=0)
    scores = [o.get("overall_score", 0) for o in outputs if o.get("overall_score", 0) > 0]

    if len(scores) < window * 2:
        return {"stagnant": False, "verdict": "insufficient_data", "count": len(scores)}

    early = scores[-(window * 2):-window]
    recent = scores[-window:]

    early_avg = sum(early) / len(early)
    recent_avg = sum(recent) / len(recent)
    improvement = recent_avg - early_avg

    # Check variance within recent window — flat variance = stagnation
    recent_variance = sum((s - recent_avg) ** 2 for s in recent) / len(recent)
    recent_stddev = math.sqrt(recent_variance)

    stagnant = abs(improvement) < min_improvement and recent_stddev < 1.0

    if stagnant:
        verdict = "stagnant"
    elif improvement > min_improvement:
        verdict = "improving"
    elif improvement < -min_improvement:
        verdict = "declining"
    else:
        verdict = "flat"

    return {
        "stagnant": stagnant,
        "verdict": verdict,
        "early_avg": round(early_avg, 2),
        "recent_avg": round(recent_avg, 2),
        "improvement": round(improvement, 2),
        "recent_stddev": round(recent_stddev, 2),
        "window": window,
    }


def check_strategy_drift(domain: str, agent_role: str = "researcher") -> dict:
    """
    Detect if the current strategy has drifted too far from the original.

    Strategy drift happens when successive evolutions gradually remove important
    elements. Each change is small, but over many evolutions the strategy
    becomes unrecognizable.

    Uses word overlap between v001 and current strategy.
    """
    from strategy_store import get_strategy, get_active_version

    strategy, version = get_strategy(agent_role, domain)
    if not strategy or version in ("default", "v001"):
        return {"drifted": False, "verdict": "no_drift", "version": version}

    # Load v001 for comparison
    v001_path = os.path.join(STRATEGY_DIR, domain, f"{agent_role}_v001.json")
    if not os.path.exists(v001_path):
        return {"drifted": False, "verdict": "no_baseline", "version": version}

    try:
        with open(v001_path) as f:
            v001_data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"drifted": False, "verdict": "baseline_corrupt", "version": version}

    v001_text = json.dumps(v001_data.get("strategy", {}), sort_keys=True).lower()
    current_text = json.dumps(strategy, sort_keys=True).lower()

    v001_words = set(v001_text.split())
    current_words = set(current_text.split())

    if not v001_words:
        return {"drifted": False, "verdict": "empty_baseline", "version": version}

    overlap = len(v001_words & current_words) / len(v001_words | current_words)

    drifted = overlap < DRIFT_WARNING_THRESHOLD

    return {
        "drifted": drifted,
        "overlap": round(overlap, 3),
        "threshold": DRIFT_WARNING_THRESHOLD,
        "version": version,
        "verdict": "drifted" if drifted else "within_bounds",
        "words_added": len(current_words - v001_words),
        "words_removed": len(v001_words - current_words),
    }


def check_knowledge_saturation(domain: str) -> dict:
    """
    Detect if a domain is saturated — adding more cycles yields diminishing returns.

    Saturation indicators:
    - Accept rate near 100% (system already knows what scores well)
    - Score variance near zero (outputs are uniform)
    - Knowledge base claims growing but insights aren't new
    """
    from memory_store import load_outputs, load_knowledge_base

    outputs = load_outputs(domain, min_score=0)
    if len(outputs) < 15:
        return {"saturated": False, "verdict": "insufficient_data"}

    recent = outputs[-10:]
    scores = [o.get("overall_score", 0) for o in recent if o.get("overall_score", 0) > 0]
    if not scores:
        return {"saturated": False, "verdict": "no_recent_scores"}

    accept_rate = sum(1 for o in recent if o.get("accepted", False)) / len(recent)
    avg_score = sum(scores) / len(scores)
    variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
    stddev = math.sqrt(variance)

    # Check KB claim growth rate
    kb = load_knowledge_base(domain)
    claim_count = len(kb.get("claims", [])) if kb else 0
    active_claims = len([c for c in kb.get("claims", []) if c.get("status") == "active"]) if kb else 0

    saturated = (accept_rate >= 0.9 and stddev < 0.5 and avg_score >= 7.5)

    if saturated:
        verdict = "saturated"
    elif accept_rate >= 0.8 and stddev < 1.0:
        verdict = "approaching_saturation"
    else:
        verdict = "active_learning"

    return {
        "saturated": saturated,
        "verdict": verdict,
        "recent_accept_rate": round(accept_rate, 2),
        "recent_avg_score": round(avg_score, 2),
        "recent_stddev": round(stddev, 2),
        "total_outputs": len(outputs),
        "kb_claims": claim_count,
        "kb_active_claims": active_claims,
    }


def check_memory_health_trend(domain: str) -> dict:
    """
    Check if the knowledge base is getting healthier or noisier over time.

    Reads synthesis timestamps, claim statuses, and verification stats
    to assess whether memory maintenance is working.
    """
    from memory_store import load_knowledge_base

    kb = load_knowledge_base(domain)
    if not kb or not kb.get("claims"):
        return {"verdict": "no_kb", "domain": domain}

    claims = kb["claims"]
    total = len(claims)
    active = sum(1 for c in claims if c.get("status") == "active")
    disputed = sum(1 for c in claims if c.get("status") == "disputed")
    expired = sum(1 for c in claims if c.get("status") == "expired")
    stale = sum(1 for c in claims if c.get("status") == "stale")
    verified = sum(1 for c in claims if c.get("_last_verified"))

    health_ratio = active / total if total > 0 else 0
    verification_rate = verified / active if active > 0 else 0

    if health_ratio >= 0.8 and disputed / max(total, 1) < 0.1:
        verdict = "healthy"
    elif health_ratio >= 0.5:
        verdict = "needs_maintenance"
    else:
        verdict = "degraded"

    return {
        "verdict": verdict,
        "domain": domain,
        "total_claims": total,
        "active": active,
        "disputed": disputed,
        "expired": expired,
        "stale": stale,
        "health_ratio": round(health_ratio, 3),
        "verification_rate": round(verification_rate, 3),
        "synthesized_at": kb.get("synthesized_at", "unknown"),
    }


# ============================================================
# Full Degradation Pulse
# ============================================================

def run_degradation_pulse(domain: str | None = None) -> dict:
    """
    Run a comprehensive degradation check across one or all domains.

    This is the long-horizon complement to monitoring.py's acute checks.
    """
    if not os.path.exists(MEMORY_DIR):
        return {"domains": [], "alerts": []}

    domains = []
    if domain:
        domains = [domain]
    else:
        from memory_store import get_stats
        for name in sorted(os.listdir(MEMORY_DIR)):
            if os.path.isdir(os.path.join(MEMORY_DIR, name)) and not name.startswith("_"):
                stats = get_stats(name)
                if stats.get("count", 0) >= 10:
                    domains.append(name)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "domains": [],
        "alerts": [],
    }

    for d in domains:
        domain_result = {"domain": d}

        diversity = check_question_diversity(d)
        domain_result["question_diversity"] = diversity
        if diversity["verdict"] == "repetitive":
            results["alerts"].append({
                "domain": d, "type": "question_repetition", "severity": "high",
                "detail": f"Question diversity score: {diversity['diversity_score']:.2f} "
                          f"(themes: {', '.join(diversity.get('repeated_themes', []))})",
            })

        stagnation = check_score_stagnation(d)
        domain_result["score_stagnation"] = stagnation
        if stagnation.get("stagnant"):
            results["alerts"].append({
                "domain": d, "type": "score_stagnation", "severity": "medium",
                "detail": f"Scores flat at {stagnation['recent_avg']:.1f} "
                          f"(improvement: {stagnation['improvement']:+.2f} over {stagnation['window']*2} outputs)",
            })

        drift = check_strategy_drift(d)
        domain_result["strategy_drift"] = drift
        if drift.get("drifted"):
            results["alerts"].append({
                "domain": d, "type": "strategy_drift", "severity": "high",
                "detail": f"Strategy {drift['version']} has {drift['overlap']:.0%} overlap with v001 "
                          f"(threshold: {drift['threshold']:.0%})",
            })

        saturation = check_knowledge_saturation(d)
        domain_result["knowledge_saturation"] = saturation
        if saturation.get("saturated"):
            results["alerts"].append({
                "domain": d, "type": "knowledge_saturation", "severity": "info",
                "detail": f"Domain saturated: {saturation['recent_accept_rate']:.0%} accept rate, "
                          f"avg {saturation['recent_avg_score']:.1f}, stddev {saturation['recent_stddev']:.2f}",
            })

        memory = check_memory_health_trend(d)
        domain_result["memory_health"] = memory
        if memory["verdict"] == "degraded":
            results["alerts"].append({
                "domain": d, "type": "memory_degradation", "severity": "high",
                "detail": f"KB health ratio: {memory['health_ratio']:.0%} active "
                          f"({memory['disputed']} disputed, {memory['expired']} expired)",
            })

        results["domains"].append(domain_result)

    results["alerts"].sort(key=lambda a: {"high": 0, "medium": 1, "info": 2}.get(a.get("severity"), 3))
    return results


def display_degradation_pulse(results: dict):
    """Display formatted degradation pulse results."""
    print(f"\n{'='*60}")
    print(f"  DEGRADATION PULSE — Long-Horizon Health")
    print(f"{'='*60}")

    for d in results["domains"]:
        domain = d["domain"]
        div = d.get("question_diversity", {})
        stag = d.get("score_stagnation", {})
        drift = d.get("strategy_drift", {})
        sat = d.get("knowledge_saturation", {})
        mem = d.get("memory_health", {})

        print(f"\n  {domain}")
        print(f"    Questions:   {div.get('verdict', '?'):15s} (diversity: {div.get('diversity_score', '?')})")
        print(f"    Scores:      {stag.get('verdict', '?'):15s} (avg: {stag.get('recent_avg', '?')}, "
              f"improvement: {stag.get('improvement', '?')})")
        print(f"    Strategy:    {drift.get('verdict', '?'):15s} (overlap: {drift.get('overlap', '?')}, "
              f"version: {drift.get('version', '?')})")
        print(f"    Saturation:  {sat.get('verdict', '?'):15s} (accept: {sat.get('recent_accept_rate', '?')}, "
              f"stddev: {sat.get('recent_stddev', '?')})")
        print(f"    Memory:      {mem.get('verdict', '?'):15s} (health: {mem.get('health_ratio', '?')}, "
              f"verified: {mem.get('verification_rate', '?')})")

    alerts = results.get("alerts", [])
    if alerts:
        print(f"\n  --- ALERTS ({len(alerts)}) ---")
        for a in alerts:
            icon = {"high": "!!", "medium": "!", "info": "i"}.get(a["severity"], "?")
            print(f"  [{icon}] {a['domain']}: {a['type']} — {a['detail']}")
    else:
        print(f"\n  No degradation signals detected.")

    print()
