"""
Cost Tracker — Budget Awareness & Spend Control

Tracks estimated API costs per run and enforces daily budget limits.
Costs are approximations based on token counts, not actual billing.

Dual-writes to both JSONL (backward compat) and SQLite (fast queries).
"""

import json
import os
from datetime import datetime, timezone, date
from config import LOG_DIR, COST_PER_1K, DAILY_BUDGET_USD, TOTAL_BALANCE_USD


COST_LOG = os.path.join(LOG_DIR, "costs.jsonl")


def log_cost(model: str, input_tokens: int, output_tokens: int, agent_role: str, domain: str):
    """Log the estimated cost of an API call. Writes to both JSONL and DB."""
    os.makedirs(LOG_DIR, exist_ok=True)

    rates = COST_PER_1K.get(model, {"input": 0.003, "output": 0.015})
    cost = (input_tokens / 1000 * rates["input"]) + (output_tokens / 1000 * rates["output"])

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": date.today().isoformat(),
        "model": model,
        "agent_role": agent_role,
        "domain": domain,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": round(cost, 6),
    }

    # Write to JSONL (backward compat)
    with open(COST_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Write to SQLite
    try:
        from db import insert_cost
        insert_cost(entry)
    except Exception as e:
        print(f"[DB] \u26a0 Cost write failed (non-blocking): {e}")

    return cost


def get_daily_spend(target_date: str | None = None) -> dict:
    """
    Get total estimated spend for a given date (default: today).

    Returns:
        {date, total_usd, calls, by_agent: {role: usd}, by_model: {model: usd}}
    """
    if target_date is None:
        target_date = date.today().isoformat()

    total = 0.0
    calls = 0
    by_agent = {}
    by_model = {}

    if not os.path.exists(COST_LOG):
        return {"date": target_date, "total_usd": 0, "calls": 0, "by_agent": {}, "by_model": {}}

    with open(COST_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("date") != target_date:
                continue

            cost = entry.get("estimated_cost_usd", 0)
            total += cost
            calls += 1

            role = entry.get("agent_role", "unknown")
            by_agent[role] = by_agent.get(role, 0) + cost

            model = entry.get("model", "unknown")
            by_model[model] = by_model.get(model, 0) + cost

    return {
        "date": target_date,
        "total_usd": round(total, 4),
        "calls": calls,
        "by_agent": {k: round(v, 4) for k, v in by_agent.items()},
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
    }


def check_budget() -> dict:
    """
    Check if today's spend is within budget.

    Returns:
        {within_budget: bool, spent: float, limit: float, remaining: float}
    """
    daily = get_daily_spend()
    spent = daily["total_usd"]
    return {
        "within_budget": spent < DAILY_BUDGET_USD,
        "spent": spent,
        "limit": DAILY_BUDGET_USD,
        "remaining": round(DAILY_BUDGET_USD - spent, 4),
    }


def check_balance() -> dict:
    """
    Check remaining API credit balance (total, not daily).

    Subtracts all-time tracked spend from TOTAL_BALANCE_USD.
    Compare with Claude console to verify accuracy.

    Returns:
        {starting_balance, total_spent, remaining_balance, accuracy_note}
    """
    alltime = get_all_time_spend()
    total_spent = alltime["total_usd"]
    remaining = round(TOTAL_BALANCE_USD - total_spent, 4)
    return {
        "starting_balance": TOTAL_BALANCE_USD,
        "total_spent": total_spent,
        "remaining_balance": remaining,
        "total_calls": alltime["calls"],
        "accuracy_note": "Compare with Claude console to verify. Update TOTAL_BALANCE_USD in config.py if drifted.",
    }


def get_all_time_spend() -> dict:
    """Get total spend across all days."""
    if not os.path.exists(COST_LOG):
        return {"total_usd": 0, "calls": 0, "days": 0, "by_date": {}}

    total = 0.0
    calls = 0
    by_date = {}

    with open(COST_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            cost = entry.get("estimated_cost_usd", 0)
            total += cost
            calls += 1

            d = entry.get("date", "unknown")
            by_date[d] = by_date.get(d, 0) + cost

    return {
        "total_usd": round(total, 4),
        "calls": calls,
        "days": len(by_date),
        "by_date": {k: round(v, 4) for k, v in sorted(by_date.items())},
    }
