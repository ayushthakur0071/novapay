from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

from utils.supabase_client import get_db_connection


SPENDING_CATEGORY_LABELS = {
    "shopping": "Shopping",
    "eating_out": "Eating Out",
    "bills": "Bills",
    "transport": "Transport",
    "entertainment": "Entertainment",
    "health": "Health",
    "travel": "Travel",
    "other": "Other",
}


def current_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def validate_month_key(month: str | None) -> str:
    if not month:
        return current_month_key()

    if not re.match(r"^\d{4}-\d{2}$", month):
        raise ValueError("Month must match YYYY-MM format.")

    datetime.strptime(f"{month}-01", "%Y-%m-%d")
    return month


def normalise_category(category: str | None) -> str:
    key = (category or "other").strip().lower()
    return key if key in SPENDING_CATEGORY_LABELS else "other"


def category_options() -> list[dict]:
    return [
        {"value": value, "label": label}
        for value, label in SPENDING_CATEGORY_LABELS.items()
    ]


def money_to_decimal(value, *, field_name: str = "Amount") -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid number.")

    if amount.is_nan() or amount.is_infinite():
        raise ValueError(f"{field_name} must be a valid number.")
    return amount


def money_to_float(value) -> float:
    return float(money_to_decimal(value or "0.00"))


def json_safe_row(row: dict) -> dict:
    safe = {}
    for key, value in dict(row).items():
        if isinstance(value, Decimal):
            safe[key] = money_to_float(value)
        elif hasattr(value, "isoformat"):
            safe[key] = value.isoformat()
        else:
            safe[key] = value
    return safe


def account_options(accounts: list[dict]) -> list[dict]:
    options = []
    for account in accounts:
        nickname = account.get("nickname") or account.get("account_type", "Account").title()
        account_number = account.get("account_number") or ""
        options.append({
            "id": str(account.get("id")),
            "label": f"{nickname} ({account_number})",
            "balance": money_to_float(account.get("balance", 0)),
        })
    return options


def get_monthly_spending(account_ids: list[str], month: str | None = None) -> tuple[dict, list[dict]]:
    month = validate_month_key(month)
    if not account_ids:
        return {}, []

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(NULLIF(category, ''), 'other') AS category,
                    SUM(amount + COALESCE(fee, 0)) AS total,
                    COUNT(*) AS record_count
                FROM transactions
                WHERE from_account_id = ANY(%s::uuid[])
                  AND status = 'completed'
                  AND TO_CHAR(created_at, 'YYYY-MM') = %s
                  AND (to_account_id IS NULL OR NOT (to_account_id = ANY(%s::uuid[])))
                GROUP BY COALESCE(NULLIF(category, ''), 'other')
                ORDER BY total DESC
                """,
                (account_ids, month, account_ids),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    summary = {}
    records = []
    for row in rows:
        category = normalise_category(row["category"])
        total = money_to_float(row["total"])
        summary[category] = summary.get(category, 0.0) + total
        records.append({
            "category": category,
            "label": SPENDING_CATEGORY_LABELS[category],
            "total": total,
            "record_count": int(row["record_count"] or 0),
        })

    return summary, records


def decorate_budgets(budgets: list[dict], spending_summary: dict) -> list[dict]:
    decorated = []
    for budget in budgets:
        category = normalise_category(budget.get("category"))
        limit_amount = money_to_decimal(budget.get("limit_amount", 0), field_name="Budget limit")
        spent_amount = money_to_decimal(spending_summary.get(category, 0), field_name="Spent amount")
        percent = Decimal("0")
        if limit_amount > 0:
            percent = (spent_amount / limit_amount) * Decimal("100")

        remaining = limit_amount - spent_amount
        status = "ok"
        if percent >= 100:
            status = "over"
        elif percent >= 80:
            status = "near"

        item = json_safe_row(budget)
        item.update({
            "category": category,
            "category_label": SPENDING_CATEGORY_LABELS[category],
            "limit_amount": money_to_float(limit_amount),
            "spent_amount": money_to_float(spent_amount),
            "remaining_amount": money_to_float(max(remaining, Decimal("0"))),
            "over_amount": money_to_float(max(spent_amount - limit_amount, Decimal("0"))),
            "percent": float(round(percent, 1)),
            "progress_width": float(min(max(percent, Decimal("0")), Decimal("100"))),
            "status": status,
        })
        decorated.append(item)
    return decorated


def decorate_goals(goals: list[dict]) -> list[dict]:
    decorated = []
    for goal in goals:
        target_amount = money_to_decimal(goal.get("target_amount", 0), field_name="Target amount")
        current_amount = money_to_decimal(goal.get("current_amount", 0), field_name="Current amount")
        percent = Decimal("0")
        if target_amount > 0:
            percent = (current_amount / target_amount) * Decimal("100")

        item = json_safe_row(goal)
        item.update({
            "target_amount": money_to_float(target_amount),
            "current_amount": money_to_float(current_amount),
            "percent": float(round(percent, 1)),
            "progress_width": float(min(max(percent, Decimal("0")), Decimal("100"))),
            "is_completed": bool(goal.get("is_completed") or current_amount >= target_amount > 0),
        })
        decorated.append(item)
    return decorated
