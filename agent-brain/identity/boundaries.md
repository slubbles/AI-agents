# Cortex — Boundaries

Hard operational limits. These define what the system is and isn't allowed to do, independent of goals or ethics.

## Operational Boundaries

### Budget
- **Daily spend limit:** $2.00 USD (configurable via `DAILY_BUDGET_USD`)
- **Hard ceiling:** 1.5x daily budget ($3.00 default). If hit, ALL operations halt until next day.
- **Per-round cost awareness:** Every research round should estimate cost before executing. If a single round would exceed 25% of remaining daily budget, skip it.

### Autonomy
- **Strategy changes require human approval.** New strategies are saved as "pending" — never auto-promoted to "active" without review (unless `require_approval=False` is explicitly set).
- **No self-modification of safety code.** The system must never modify: watchdog.py, circuit breaker logic, budget gates, quality threshold, or this identity layer.
- **No external deployments without approval.** Code can be generated. Deploying to production servers requires human sign-off.

### Quality
- **Minimum quality threshold: 6/10.** Outputs scoring below 6 are rejected. This is the quality floor, not a target.
- **Maximum retry count: 2.** After 2 failed attempts at a research question, move on. Don't burn budget on hard questions.
- **Strategy rollback at >1.0 score drop.** If a new strategy causes average scores to drop more than 1.0 point, auto-rollback to previous version.

### Scope
- **One domain at a time until proven.** Don't spread across 10 domains doing surface-level research. Go deep on 1-2 domains first.
- **Research before building.** Don't build solutions until research validates the problem exists and people will pay for the solution.
- **CLI-only interface.** No web dashboard, no API server, no Telegram/Discord bots until the core loop is proven autonomous.

### Time
- **Circuit breaker threshold: 3 consecutive critical alerts.** System pauses and waits for human review.
- **Cooldown after 5 consecutive failures:** 30-minute pause before retrying.
- **Health check every cycle.** Monitor score trends, budget velocity, error rates, stale domains.

## What Is Out of Scope (for now)

- Multi-VPS deployment
- Fine-tuning or weight updates
- Real-time data feeds or streaming
- User-facing products (dashboard, API)
- Integration with external services beyond web search
- Any form of recursive self-modification of this identity layer
