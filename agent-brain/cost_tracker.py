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
from config import DAILY_BUDGET_CLAUDE, DAILY_BUDGET_OPENROUTER
from config import BALANCE_CLAUDE, BALANCE_OPENROUTER, MODEL_PROVIDER


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

    Source of truth: SQLite DB (fast, accurate).
    Falls back to JSONL only if DB query fails.

    Returns:
        {date, total_usd, calls, by_agent: {role: usd}, by_model: {model: usd},
         by_provider: {claude: usd, openrouter: usd}}
    """
    if target_date is None:
        target_date = date.today().isoformat()

    # Primary: read from DB
    try:
        from db import get_daily_spend_db
        db_result = get_daily_spend_db(target_date)

        # DB result doesn't include by_provider — compute it from by_model
        by_provider = {"claude": 0.0, "openrouter": 0.0}
        for model, cost in db_result.get("by_model", {}).items():
            provider = MODEL_PROVIDER.get(model, "openrouter")
            by_provider[provider] = by_provider.get(provider, 0) + cost

        db_result["by_provider"] = {k: round(v, 4) for k, v in by_provider.items()}
        return db_result
    except Exception as e:
        print(f"[COST] ⚠ DB read failed, falling back to JSONL: {e}")

    # Fallback: read from JSONL (backward compat)
    total = 0.0
    calls = 0
    by_agent = {}
    by_model = {}
    by_provider = {"claude": 0.0, "openrouter": 0.0}

    if not os.path.exists(COST_LOG):
        return {"date": target_date, "total_usd": 0, "calls": 0,
                "by_agent": {}, "by_model": {}, "by_provider": by_provider}

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

            # Provider breakdown
            provider = MODEL_PROVIDER.get(model, "openrouter")
            by_provider[provider] = by_provider.get(provider, 0) + cost

    return {
        "date": target_date,
        "total_usd": round(total, 4),
        "calls": calls,
        "by_agent": {k: round(v, 4) for k, v in by_agent.items()},
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
        "by_provider": {k: round(v, 4) for k, v in by_provider.items()},
    }


def check_budget() -> dict:
    """
    Check if today's spend is within budget (per-provider aware).

    Budget is considered within limits if BOTH providers are under their
    individual daily caps. The combined total is also tracked.

    Returns:
        {within_budget: bool, spent: float, limit: float, remaining: float,
         by_provider: {claude: {spent, limit, remaining, within},
                       openrouter: {spent, limit, remaining, within}},
         violated_provider: str|None}
    """
    daily = get_daily_spend()
    spent = daily["total_usd"]
    by_prov = daily.get("by_provider", {"claude": 0, "openrouter": 0})

    claude_spent = by_prov.get("claude", 0)
    openrouter_spent = by_prov.get("openrouter", 0)

    claude_ok = claude_spent < DAILY_BUDGET_CLAUDE
    openrouter_ok = openrouter_spent < DAILY_BUDGET_OPENROUTER

    # Identify which provider (if any) is over budget
    violated = None
    if not claude_ok:
        violated = "claude"
    elif not openrouter_ok:
        violated = "openrouter"

    return {
        "within_budget": claude_ok and openrouter_ok,
        "spent": spent,
        "limit": DAILY_BUDGET_USD,
        "remaining": round(DAILY_BUDGET_USD - spent, 4),
        "by_provider": {
            "claude": {
                "spent": claude_spent,
                "limit": DAILY_BUDGET_CLAUDE,
                "remaining": round(DAILY_BUDGET_CLAUDE - claude_spent, 4),
                "within": claude_ok,
            },
            "openrouter": {
                "spent": openrouter_spent,
                "limit": DAILY_BUDGET_OPENROUTER,
                "remaining": round(DAILY_BUDGET_OPENROUTER - openrouter_spent, 4),
                "within": openrouter_ok,
            },
        },
        "violated_provider": violated,
    }


def check_balance() -> dict:
    """
    Check remaining API credit balance (total, not daily).

    Subtracts all-time tracked spend from TOTAL_BALANCE_USD.
    Compare with Claude console / OpenRouter dashboard to verify accuracy.

    Returns:
        {starting_balance, total_spent, remaining_balance, accuracy_note,
         by_provider: {claude: {...}, openrouter: {...}}}
    """
    alltime = get_all_time_spend()
    total_spent = alltime["total_usd"]
    remaining = round(TOTAL_BALANCE_USD - total_spent, 4)

    # Per-provider balance (all-time spend by model → provider)
    by_prov_spent = {"claude": 0.0, "openrouter": 0.0}
    for model, cost in alltime.get("by_model", {}).items():
        provider = MODEL_PROVIDER.get(model, "openrouter")
        by_prov_spent[provider] = by_prov_spent.get(provider, 0) + cost

    return {
        "starting_balance": TOTAL_BALANCE_USD,
        "total_spent": total_spent,
        "remaining_balance": remaining,
        "total_calls": alltime["calls"],
        "by_provider": {
            "claude": {
                "balance": BALANCE_CLAUDE,
                "spent": round(by_prov_spent["claude"], 4),
                "remaining": round(BALANCE_CLAUDE - by_prov_spent["claude"], 4),
            },
            "openrouter": {
                "balance": BALANCE_OPENROUTER,
                "spent": round(by_prov_spent["openrouter"], 4),
                "remaining": round(BALANCE_OPENROUTER - by_prov_spent["openrouter"], 4),
            },
        },
        "accuracy_note": "Compare with Claude console / OpenRouter dashboard. "
                         "Update BALANCE_CLAUDE and BALANCE_OPENROUTER in config.py if drifted.",
    }


def get_all_time_spend() -> dict:
    """Get total spend across all days. Source of truth: DB, fallback: JSONL."""
    # Primary: read from DB
    try:
        from db import get_all_time_spend_db
        db_result = get_all_time_spend_db()

        # DB result doesn't include by_model — add it from a targeted query
        try:
            from db import get_connection, init_db
            init_db()
            by_model = {}
            with get_connection() as conn:
                for r in conn.execute(
                    "SELECT model, SUM(estimated_cost_usd) as s FROM costs GROUP BY model"
                ).fetchall():
                    by_model[r["model"]] = round(r["s"], 4)
            db_result["by_model"] = by_model
        except Exception:
            db_result["by_model"] = {}

        return db_result
    except Exception as e:
        print(f"[COST] ⚠ DB read failed, falling back to JSONL: {e}")

    # Fallback: read from JSONL
    if not os.path.exists(COST_LOG):
        return {"total_usd": 0, "calls": 0, "days": 0, "by_date": {}, "by_model": {}}

    total = 0.0
    calls = 0
    by_date = {}
    by_model = {}

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

            model = entry.get("model", "unknown")
            by_model[model] = by_model.get(model, 0) + cost

    return {
        "total_usd": round(total, 4),
        "calls": calls,
        "days": len(by_date),
        "by_date": {k: round(v, 4) for k, v in sorted(by_date.items())},
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
    }
