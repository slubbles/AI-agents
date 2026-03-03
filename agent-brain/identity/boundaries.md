# Cortex — Boundaries

Hard operational limits. These define what the system is and isn't allowed to do, independent of goals or ethics.

## Operational Boundaries

### Budget
- **Daily spend limit:** $7.00 USD (configurable via `DAILY_BUDGET_USD` — $2 Claude + $5 OpenRouter)
- **Hard ceiling:** 1.5x daily budget ($10.50 default). If hit, ALL operations halt until next day.
- **Per-provider limits:** Claude $2/day, OpenRouter $5/day. Enforced independently.
- **Per-round cost awareness:** Every research round should estimate cost before executing. If a single round would exceed 25% of remaining daily budget, skip it.
- **Execution budget:** Single Hands execution capped at $0.50. Abort if exceeded.

### Autonomy
- **Strategy changes auto-approved in daemon mode.** `require_approval=False` in autonomous operation. Strategies are still versioned and rollback-ready.
- **No self-modification of safety code.** The system must never modify: watchdog.py, circuit breaker logic, budget gates, quality threshold, or this identity layer.
- **Hands deploys to Vercel autonomously.** Deploying built apps to Vercel (staging) does not require human approval. Production domain assignments do.
- **Human review gates:** Blueprint approval before code generation (Phase 1). Production domain changes. Budget limit changes.

### Quality
- **Research quality threshold: 6/10.** Outputs scoring below 6 are rejected.
- **Execution quality threshold: 7/10.** Hands builds must meet a higher bar.
- **Maximum retry count: 2.** After 2 failed attempts at a research question, move on.
- **Strategy rollback at >1.0 score drop.** If a new strategy causes average scores to drop more than 1.0 point, auto-rollback to previous version.
- **Visual quality bar: 8/10.** Apps must look production-ready. Below 8 triggers a visual fix pass.

### Scope
- **Focus domains over breadth.** Go deep on 1-3 domains before spreading.
- **Research before building.** Don't build solutions until research validates the problem exists and people will pay.
- **Build pipeline:** Brain researches → Cortex approves → Hands builds → Hands deploys → Cortex reports.
- **Interfaces:** CLI (primary), Telegram bot (notifications + commands), web dashboard (deferred).

### Time
- **Circuit breaker threshold: 3 consecutive critical alerts.** System pauses and waits for human review.
- **Cooldown after 5 consecutive failures:** 30-minute pause before retrying.
- **Health check every cycle.** Monitor score trends, budget velocity, error rates, stale domains.
- **Daemon interval: 60 minutes.** Each cycle: research rounds → synthesis → strategy evolution → Hands execution.

## What Is Out of Scope (for now)

- Multi-VPS deployment
- Fine-tuning or weight updates
- Real-time data feeds or streaming
- Docker sandbox isolation (each build in its own container)
- Supabase MCP integration (using CLI/API directly)
- Any form of recursive self-modification of this identity layer
