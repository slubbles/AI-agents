# Transistor Mindset — Cortex Core Reliability Spec

> A transistor doesn't care what circuit it's placed in. It just switches — predictably, cleanly, billions of times. That's the standard for Cortex's core loop.

## The Guarantee

Before Cortex scales (more domains, more agents, more autonomy), the **single core loop** must be reliable enough that:

1. Given a domain and a goal, it produces useful output **without manual setup**
2. The quality signal (critic scores) means the **same thing across all domains**
3. The knowledge base **gets better over time**, not noisier
4. Strategy evolution **measurably improves** the next cycle
5. Wrong beliefs get **caught and corrected**, not compounded
6. The system **doesn't degrade** during long unsupervised runtime

If any of these break, nothing downstream matters — not multi-agent coordination, not revenue generation, not scaling to 100 domains.

---

## The Core Loop (The "Binary Switch")

```
Domain + Goal
    → Bootstrap (if cold)
    → Research (scored, structured findings)
    → Critique (calibrated, honest evaluation)
    → Store (memory accumulation)
    → Strategy Evolution (behavioral adaptation)
    → Handoff to Hands (domain-agnostic task creation)
    → Outcome Feedback
    → Repeat
```

This loop either fires cleanly or it doesn't. "Without inconsistency" means it fires the same way for crypto, biotech, policy analysis, or any domain you point it at.

---

## Four Reliability Systems

These exist to close the gaps that make the core loop inconsistent.

### A. Cold-Start Bootstrap (`domain_bootstrap.py`)

**Problem**: New domains with zero history produce garbage for 5-10 cycles before self-correcting.

**Guarantee**: Any new domain reaches passable output within a predictable number of cycles without human configuration.

**Mechanism**:
- Detect cold domain (< N accepted outputs)
- Generate domain orientation via LLM (key concepts, source types, research profile, pitfalls)
- Auto-transfer cross-domain principles from proven domains
- Generate progressive seed questions (broad → specific)
- Fall back to generic seeds if LLM unavailable — never crash, never stall

**Test**: Point Cortex at 3 domains it has never seen. Give each a goal. Run 5 auto rounds. Output should be useful, not noise.

### B. Critic Calibration (`domain_calibration.py`)

**Problem**: A score of 7 in crypto and 7 in quantum physics don't mean the same quality. Domain difficulty makes raw scores unreliable for cross-domain comparison.

**Guarantee**: Strategy evolution compares apples to apples. Score-based decisions are trustworthy.

**Mechanism**:
- Track per-domain score distributions (mean, stddev, accept rate)
- Compute domain difficulty signal (easy/medium/hard)
- Inject calibration context into critic prompt (baseline awareness, weakest dimension)
- Offer normalized scores for cross-domain analytics
- **Does NOT inflate scores for hard domains** — maintains absolute standard, but recognizes relative improvement

**Principle**: The calibration is descriptive, not prescriptive. The critic makes better judgments when it knows the landscape.

### C. Memory Lifecycle (`memory_lifecycle.py`)

**Problem**: Without maintenance, the knowledge base accumulates stale claims, the graph drifts, and storage grows unbounded. Some domains self-clean; others silently rot.

**Guarantee**: Memory hygiene runs on its own schedule. If a domain has data, it self-organizes. If it doesn't, it stays in early-stage mode without corruption.

**Mechanism**:
- Expire stale claims (time-based confidence decay)
- Re-synthesize KB when too many claims go stale
- Rebuild knowledge graph from updated KB
- Prune old/rejected outputs (archive, don't delete)
- Verify high-confidence claims against external evidence
- Update calibration stats
- Each step is independently try/excepted — one failure doesn't stop the rest

**Test**: A domain left alone for 30 days should have cleaner memory than day 1, not dirtier.

### D. Claim Verifier (`agents/claim_verifier.py`)

**Problem**: Without external grounding, the system's quality signal is closed-loop. It can converge on "outputs that score well" instead of "outputs that are actually right." Over 50 cycles, wrong beliefs compound silently.

**Guarantee**: The system periodically checks its own claims against reality and adjusts confidence. It cannot confidently compound wrong beliefs indefinitely.

**Mechanism**:
- Sample high-confidence active claims from the knowledge base
- Build web search queries, fetch evidence
- LLM judges: confirmed / refuted / weakened / inconclusive
- Refuted claims get status="disputed", confidence lowered, correction noted
- Refutations fed back as research lessons (breaking the LLM-judging-LLM loop)
- Prioritizes never-verified claims, then oldest-verified

**Principle**: The goal isn't perfect verification. It's preventing confident convergence on falsehood.

---

## Domain-Agnostic Handoff

The Brain-to-Hands bridge uses **40+ universal action verbs** (analyze, evaluate, survey, contact, negotiate, propose, pitch, monitor, track, assess...) instead of coding-centric keywords. A biotech insight about "monitor clinical trials" generates a task just like a coding insight about "build an API endpoint."

Task priority is classified by intent (creation → high, delivery → high, operational → medium, knowledge gaps → low), not by domain assumptions.

---

## Outcome Feedback — Closing the Loop (`outcome_feedback.py`)

**Problem**: Brain creates tasks, Hands executes them, results are stored — but Brain never learns from what actually worked or failed in practice. The core loop was open at the last step.

**Guarantee**: Every completed or failed execution produces lessons that flow back to Brain's research system. Brain adapts based on real-world outcomes, not just self-evaluation.

**Mechanism**:
- After Hands completes/fails tasks, extract structured lessons from execution results
- Successful executions: "this approach validated in practice" → research lesson with source `execution_success`
- Failed executions: "research insight may not be directly actionable" → research lesson with source `execution_failure`
- Pattern detection: timeouts → "break tasks into smaller steps"; permission errors → "account for execution constraints"
- Mark tasks as `_feedback_processed` to prevent double-processing
- All processing is zero-API-cost (pure data extraction from existing results)
- Runs automatically in daemon after Hands execution; `--process-feedback` CLI for manual review
- Logs all feedback events to `outcome_feedback.jsonl`

**Principle**: Research that leads to successful execution is more valuable than research that scores well. This signal closes the loop.

---

## Guarantee Enforcement

### #4: Strategy Evolution Measurably Improves (`strategy_impact.py`)

**Problem**: After a strategy was confirmed, no one checked if it actually kept performing well. Pending evolutions could sit forever. No cumulative "has evolution helped?" signal.

**Mechanism**:
- **Post-approval validation**: After confirmation, track next N outputs. If performance drops >15% from trial avg, flag regression.
- **Cumulative impact**: Compare avg scores across all strategy versions to measure the total improvement (or decline) from evolution.
- **Stale cleanup**: Close evolution entries that stayed "pending" for 14+ days.
- `--strategy-impact` CLI command for manual review.
- Runs automatically every 10 daemon cycles.

### #6: No Degradation During Long Runtime (`degradation_detector.py`)

**Problem**: Monitoring catches acute issues (sudden drops, error spikes). But slow decay over 50-100 cycles goes undetected: repetitive questions, score plateaus, strategy drift, knowledge saturation.

**Mechanism**:
- **Question diversity**: Pairwise word overlap within recent window. Score below 0.4 = "repetitive."
- **Score stagnation**: Compare early-window vs recent-window averages. Flat + low variance = stagnant.
- **Strategy drift**: Word overlap between current strategy and v001. Below 60% = drifted.
- **Knowledge saturation**: Accept rate near 100% + low variance + high avg = domain is saturated, cycles add diminishing value.
- **Memory health trend**: Ratio of active/total claims, disputed claim rate, verification rate.
- **Daemon dedup**: Question dedup now runs IN the daemon (was CLI-only). Rejects questions too similar to recent ones before spending credits.
- `--health-pulse` CLI command. Runs automatically every 10 daemon cycles.

---

## What NOT to Do

Until the core loop is proven reliable across domains:

- **Don't** expand Hands capabilities or add new tool types
- **Don't** add new agent roles or multi-instance coordination
- **Don't** optimize for cost, speed, or scale
- **Don't** chase impressive demos in one domain

A transistor that switches slowly but correctly is infinitely more valuable than one that switches fast but sometimes flips the wrong bit.

---

## How to Verify the Transistor Works

### Structural (Zero-API-Cost)
- `python main.py --readiness` — system configuration check
- `python main.py --validate` — data integrity across all subsystems
- `python main.py --dry-run --domain crypto` — full pipeline trace with mock LLM
- `python main.py --dry-run --domain new-domain --rounds 3` — multi-round simulation
- `python -m pytest tests/test_transistor.py -v` — mock-based structural tests

### Before Spending Credits
- `python main.py --estimate --domain crypto --rounds 5` — see expected cost
- `python main.py --estimate --domain crypto --rounds 5 --conservative` — cost in conservative mode

### Operational (Requires API Credits)
- `python main.py --auto --domain crypto --rounds 3 --conservative` — run real cycles at minimum cost
- Bootstrap test: 3 fresh domains, 5 rounds each, measure first-cycle quality
- Calibration test: compare scores across easy vs hard domains after 10+ outputs each
- Lifecycle test: run maintenance on a domain with 20+ outputs, verify cleaner state
- Verifier test: check 5 high-confidence claims, see if any get corrected

### Post-Cycle Review
- `python main.py --review` — score trends, anomalies, costs, verification stats
- `python main.py --review-cycles 10` — daemon cycle history
- `python main.py --process-feedback` — extract lessons from completed Hands tasks → Brain
- Look for: score drops, rejection streaks, strategy changes, uncorrected claims

---

## The Scaling Path (After the Transistor is Proven)

```
Transistor  → Proven single-loop reliability across domains       [CURRENT]
Logic Gate  → Composable multi-step reasoning chains
Chip        → Multi-agent coordination with shared memory
Board       → Specialized subsystems (research, execution, outreach)
System      → Full autonomous operation with human oversight
H100        → Massively parallel domain processing
```

Each layer only works if the one below it is solid. We're at layer 1. Stay here until the tests pass.

---

## Budget Reality

API credits are finite. This means:
- Architecture > live testing (for now)
- Every cycle should teach something — no exploratory waste
- Use `--conservative` to run all agents on cheapest models with single attempt
- Use `--estimate` before every real run to know the cost upfront
- Use `--dry-run` to verify pipeline integrity without spending anything
- The review system (`--review`) should extract maximum insight per dollar spent

The transistor mindset applies to budget too: make every API call count, or don't make it.

### Conservative Mode Details
When `--conservative` is active:
- All agent roles use DeepSeek V3.2 (cheapest model: ~$0.00027/$0.0011 per 1K tokens)
- Single attempt per question (no retry loop)
- 4 tool rounds max (vs 8 standard)
- 5 searches max (vs 10 standard)
- 3 page fetches max (vs 8 standard)
- No consensus (single researcher)
- No critic ensemble (single critic)
- Estimated cost: ~$0.01-0.02 per cycle vs ~$0.05-0.15 standard
