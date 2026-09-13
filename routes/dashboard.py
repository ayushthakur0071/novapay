from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.dashboard_metrics import (
    SPENDING_CATEGORY_LABELS,
    account_options,
    category_options,
    current_month_key,
    decorate_budgets,
    decorate_goals,
    get_monthly_spending,
    json_safe_row,
    money_to_decimal,
    normalise_category,
    validate_month_key,
)
from utils.supabase_client import get_db_connection
from utils.validators import clean_input

dashboard_bp = Blueprint("dashboard", __name__)


def _api_error(code, message, status=400):
    return jsonify({"success": False, "error": {"code": code, "message": message}}), status


def _fetch_accounts():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM accounts
                WHERE user_id = %s
                ORDER BY created_at
                """,
                (current_user.id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _account_ids(accounts):
    return [str(account["id"]) for account in accounts]


def _fetch_recent_transactions(account_ids):
    if not account_ids:
        return []

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    t.*,
                    fa.account_number AS from_account_number,
                    fa.account_type AS from_account_type,
                    ta.account_number AS to_account_number,
                    ta.account_type AS to_account_type
                FROM transactions t
                LEFT JOIN accounts fa ON t.from_account_id = fa.id
                LEFT JOIN accounts ta ON t.to_account_id = ta.id
                WHERE t.from_account_id = ANY(%s::uuid[])
                   OR t.to_account_id = ANY(%s::uuid[])
                ORDER BY t.created_at DESC
                LIMIT 5
                """,
                (account_ids, account_ids),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    owned = set(account_ids)
    txns = []
    for row in rows:
        txn = json_safe_row(row)
        from_id = str(txn["from_account_id"]) if txn.get("from_account_id") else None
        to_id = str(txn["to_account_id"]) if txn.get("to_account_id") else None
        amount = money_to_decimal(txn.get("amount", 0))
        fee = money_to_decimal(txn.get("fee", 0))

        if txn.get("transaction_type") == "deposit" or (to_id in owned and from_id not in owned):
            direction = "credit"
            prefix = "+"
            display_amount = amount
        elif from_id in owned and to_id in owned:
            direction = "internal"
            prefix = ""
            display_amount = amount
        else:
            direction = "debit"
            prefix = "-"
            display_amount = amount + fee

        category = normalise_category(txn.get("category"))
        txn.update({
            "category": category,
            "category_label": SPENDING_CATEGORY_LABELS[category],
            "direction": direction,
            "display_prefix": prefix,
            "display_amount": float(display_amount),
        })
        txns.append(txn)
    return txns


def _fetch_savings_goals(account_ids):
    if not account_ids:
        return []

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    sg.*,
                    a.nickname AS account_nickname,
                    a.account_number
                FROM savings_goals sg
                JOIN accounts a ON a.id = sg.account_id
                WHERE sg.account_id = ANY(%s::uuid[])
                ORDER BY sg.is_completed, sg.target_date NULLS LAST, sg.created_at DESC
                """,
                (account_ids,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _fetch_budgets(month):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM spending_budgets
                WHERE user_id = %s
                  AND month = %s
                ORDER BY category
                """,
                (current_user.id, month),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _fetch_upcoming_payments(account_ids):
    if not account_ids:
        return []

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    so.*,
                    json_build_object(
                        'account_number', a.account_number,
                        'nickname', a.nickname
                    ) AS accounts,
                    json_build_object(
                        'nickname', b.nickname,
                        'full_name', b.full_name,
                        'account_number', b.account_number,
                        'sort_code', b.sort_code
                    ) AS beneficiaries
                FROM standing_orders so
                JOIN accounts a ON a.id = so.from_account_id
                JOIN beneficiaries b ON b.id = so.beneficiary_id
                WHERE so.from_account_id = ANY(%s::uuid[])
                  AND so.is_active = TRUE
                ORDER BY so.next_payment
                LIMIT 3
                """,
                (account_ids,),
            )
            return [json_safe_row(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _fetch_unread_notifications():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM notifications
                WHERE user_id = %s
                  AND is_read = FALSE
                """,
                (current_user.id,),
            )
            row = cur.fetchone()
            return int(row["count"] or 0)
    finally:
        conn.close()


def _fetch_cloud_status():
    active_cloud = "AWS (Simulated)"
    last_failover = "None"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM failover_events
                ORDER BY triggered_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if row:
        active_cloud = row["to_server"].upper()
        triggered_at = row["triggered_at"]
        if hasattr(triggered_at, "isoformat"):
            last_failover = triggered_at.isoformat().split(".")[0].replace("T", " ")
    else:
        import os
        active_cloud = os.environ.get("PRIMARY_CLOUD", "aws").upper()

    return active_cloud, last_failover


def _dashboard_payload(month=None):
    month = validate_month_key(month)
    accounts = _fetch_accounts()
    account_ids = _account_ids(accounts)
    spending_summary, spending_rows = get_monthly_spending(account_ids, month)
    goals = decorate_goals(_fetch_savings_goals(account_ids))
    budgets = decorate_budgets(_fetch_budgets(month), spending_summary)

    return {
        "accounts": accounts,
        "account_ids": account_ids,
        "recent_transactions": _fetch_recent_transactions(account_ids),
        "savings_goals": goals,
        "budgets": budgets,
        "upcoming_payments": _fetch_upcoming_payments(account_ids),
        "spending_summary": spending_summary,
        "spending_rows": spending_rows,
        "spending_total": round(sum(spending_summary.values()), 2),
        "current_month": month,
    }


def _parse_budget_payload(data):
    category_raw = (data.get("category") or "").strip().lower()
    if category_raw not in SPENDING_CATEGORY_LABELS:
        raise ValueError("Choose a supported spending category.")

    limit_amount = money_to_decimal(data.get("limit_amount", 0), field_name="Budget limit")
    if limit_amount <= 0:
        raise ValueError("Budget limit must be greater than zero.")

    month = validate_month_key(data.get("month"))
    return category_raw, limit_amount, month


def _parse_goal_payload(data, existing_goal=None):
    update_fields = {}

    if existing_goal is None or "account_id" in data:
        account_id = data.get("account_id")
        if not account_id:
            raise ValueError("Choose an account for this goal.")
        update_fields["account_id"] = account_id

    if existing_goal is None or "name" in data:
        name = clean_input(data.get("name", ""))
        if not name:
            raise ValueError("Goal name is required.")
        if len(name) > 100:
            raise ValueError("Goal name must be 100 characters or fewer.")
        update_fields["name"] = name

    if existing_goal is None or "target_amount" in data:
        target_amount = money_to_decimal(data.get("target_amount", 0), field_name="Target amount")
        if target_amount <= 0:
            raise ValueError("Target amount must be greater than zero.")
        update_fields["target_amount"] = target_amount

    if existing_goal is None or "current_amount" in data:
        current_amount = money_to_decimal(data.get("current_amount", 0), field_name="Saved amount")
        if current_amount < 0:
            raise ValueError("Saved amount cannot be negative.")
        update_fields["current_amount"] = current_amount

    if existing_goal is None or "target_date" in data:
        target_date = (data.get("target_date") or "").strip()
        if target_date:
            try:
                datetime.strptime(target_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Target date must match YYYY-MM-DD format.")
            update_fields["target_date"] = target_date
        else:
            update_fields["target_date"] = None

    target_for_status = money_to_decimal(
        update_fields.get("target_amount", existing_goal["target_amount"] if existing_goal else 0),
        field_name="Target amount",
    )
    current_for_status = money_to_decimal(
        update_fields.get("current_amount", existing_goal["current_amount"] if existing_goal else 0),
        field_name="Saved amount",
    )
    update_fields["is_completed"] = bool(target_for_status > 0 and current_for_status >= target_for_status)
    return update_fields


def _ensure_account_belongs_to_user(account_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM accounts
                WHERE id = %s
                  AND user_id = %s
                  AND is_active = TRUE
                """,
                (account_id, current_user.id),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def _fetch_goal_for_user(goal_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sg.*
                FROM savings_goals sg
                JOIN accounts a ON a.id = sg.account_id
                WHERE sg.id = %s
                  AND a.user_id = %s
                """,
                (goal_id, current_user.id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _decorate_single_budget(row):
    payload = _dashboard_payload(row["month"])
    return decorate_budgets([row], payload["spending_summary"])[0]


def _decorate_single_goal(row):
    account = {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nickname AS account_nickname, account_number
                FROM accounts
                WHERE id = %s
                  AND user_id = %s
                """,
                (row["account_id"], current_user.id),
            )
            account = cur.fetchone() or {}
    finally:
        conn.close()

    merged = dict(row)
    merged.update(dict(account))
    return decorate_goals([merged])[0]


@dashboard_bp.route("/", methods=["GET"])
def home():
    """Redirects base path to dashboard or login depending on session status."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@dashboard_bp.route("/dashboard", methods=["GET"])
@login_required
def index():
    """Serves the main customer dashboard view."""
    try:
        payload = _dashboard_payload()
    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        payload = {
            "accounts": [],
            "account_ids": [],
            "recent_transactions": [],
            "savings_goals": [],
            "budgets": [],
            "spending_summary": {},
            "spending_rows": [],
            "spending_total": 0,
            "current_month": current_month_key(),
        }

    active_cloud, last_failover = _fetch_cloud_status()

    dashboard_data = {
        "accounts": account_options(payload["accounts"]),
        "budgetCategories": category_options(),
        "currentMonth": payload["current_month"],
        "spendingRows": payload["spending_rows"],
        "spendingSummary": payload["spending_summary"],
        "spendingTotal": payload["spending_total"],
    }

    return render_template(
        "dashboard/index.html",
        accounts=payload["accounts"],
        recent_transactions=payload["recent_transactions"],
        savings_goals=payload["savings_goals"],
        budgets=payload["budgets"],
        monthly_spending_rows=payload["spending_rows"],
        monthly_spending_total=payload["spending_total"],
        dashboard_data=dashboard_data,
        upcoming_payments=payload.get("upcoming_payments", []),
        unread_notifs=_fetch_unread_notifications(),
        active_cloud=active_cloud,
        last_failover=last_failover,
    )


@dashboard_bp.route("/api/dashboard/metrics", methods=["GET"])
@login_required
def api_metrics():
    try:
        payload = _dashboard_payload(request.args.get("month"))
        return jsonify({
            "success": True,
            "data": {
                "budgets": payload["budgets"],
                "goals": payload["savings_goals"],
                "spending_rows": payload["spending_rows"],
                "spending_summary": payload["spending_summary"],
                "spending_total": payload["spending_total"],
            },
        })
    except ValueError as e:
        return _api_error("INVALID_INPUT", str(e))
    except Exception as e:
        return _api_error("FETCH_FAILED", str(e), 500)


@dashboard_bp.route("/api/dashboard/budgets", methods=["POST"])
@login_required
def api_save_budget():
    data = request.get_json() or {}
    try:
        category, limit_amount, month = _parse_budget_payload(data)
    except ValueError as e:
        return _api_error("INVALID_INPUT", str(e))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM spending_budgets
                WHERE user_id = %s
                  AND category = %s
                  AND month = %s
                """,
                (current_user.id, category, month),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE spending_budgets
                    SET limit_amount = %s
                    WHERE id = %s
                    RETURNING *
                    """,
                    (limit_amount, existing["id"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO spending_budgets (user_id, category, limit_amount, month)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (current_user.id, category, limit_amount, month),
                )
            row = dict(cur.fetchone())
        conn.commit()
        return jsonify({"success": True, "data": _decorate_single_budget(row)})
    except Exception as e:
        conn.rollback()
        return _api_error("SAVE_FAILED", str(e), 500)
    finally:
        conn.close()


@dashboard_bp.route("/api/dashboard/budgets/<uuid_id>", methods=["PATCH"])
@login_required
def api_update_budget(uuid_id):
    data = request.get_json() or {}
    fields = {}

    try:
        if "category" in data:
            category = (data.get("category") or "").strip().lower()
            if category not in SPENDING_CATEGORY_LABELS:
                raise ValueError("Choose a supported spending category.")
            fields["category"] = category

        if "limit_amount" in data:
            limit_amount = money_to_decimal(data.get("limit_amount"), field_name="Budget limit")
            if limit_amount <= 0:
                raise ValueError("Budget limit must be greater than zero.")
            fields["limit_amount"] = limit_amount
    except ValueError as e:
        return _api_error("INVALID_INPUT", str(e))

    if not fields:
        return _api_error("NO_FIELDS", "No budget fields were supplied.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM spending_budgets WHERE id = %s AND user_id = %s",
                (uuid_id, current_user.id),
            )
            if not cur.fetchone():
                return _api_error("FORBIDDEN", "Access denied.", 403)

            assignments = ", ".join(f"{key} = %s" for key in fields)
            params = list(fields.values()) + [uuid_id, current_user.id]
            cur.execute(
                f"""
                UPDATE spending_budgets
                SET {assignments}
                WHERE id = %s
                  AND user_id = %s
                RETURNING *
                """,
                params,
            )
            row = dict(cur.fetchone())
        conn.commit()
        return jsonify({"success": True, "data": _decorate_single_budget(row)})
    except Exception as e:
        conn.rollback()
        return _api_error("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@dashboard_bp.route("/api/dashboard/budgets/<uuid_id>", methods=["DELETE"])
@login_required
def api_delete_budget(uuid_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM spending_budgets
                WHERE id = %s
                  AND user_id = %s
                RETURNING id
                """,
                (uuid_id, current_user.id),
            )
            row = cur.fetchone()
            if not row:
                return _api_error("FORBIDDEN", "Access denied.", 403)
        conn.commit()
        return jsonify({"success": True, "data": {"id": str(row["id"])}})
    except Exception as e:
        conn.rollback()
        return _api_error("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()


@dashboard_bp.route("/api/dashboard/goals", methods=["POST"])
@login_required
def api_create_goal():
    data = request.get_json() or {}
    try:
        fields = _parse_goal_payload(data)
    except ValueError as e:
        return _api_error("INVALID_INPUT", str(e))

    if not _ensure_account_belongs_to_user(fields["account_id"]):
        return _api_error("FORBIDDEN", "Selected account is not available.", 403)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO savings_goals (
                    account_id,
                    name,
                    target_amount,
                    current_amount,
                    target_date,
                    icon,
                    is_completed
                )
                VALUES (%s, %s, %s, %s, %s, 'goal', %s)
                RETURNING *
                """,
                (
                    fields["account_id"],
                    fields["name"],
                    fields["target_amount"],
                    fields["current_amount"],
                    fields["target_date"],
                    fields["is_completed"],
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
        return jsonify({"success": True, "data": _decorate_single_goal(row)})
    except Exception as e:
        conn.rollback()
        return _api_error("CREATE_FAILED", str(e), 500)
    finally:
        conn.close()


@dashboard_bp.route("/api/dashboard/goals/<uuid_id>", methods=["PATCH"])
@login_required
def api_update_goal(uuid_id):
    existing = _fetch_goal_for_user(uuid_id)
    if not existing:
        return _api_error("FORBIDDEN", "Access denied.", 403)

    data = request.get_json() or {}
    try:
        fields = _parse_goal_payload(data, existing)
    except ValueError as e:
        return _api_error("INVALID_INPUT", str(e))

    if "account_id" in fields and not _ensure_account_belongs_to_user(fields["account_id"]):
        return _api_error("FORBIDDEN", "Selected account is not available.", 403)

    if not fields:
        return _api_error("NO_FIELDS", "No goal fields were supplied.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            assignments = ", ".join(f"{key} = %s" for key in fields)
            params = list(fields.values()) + [uuid_id]
            cur.execute(
                f"""
                UPDATE savings_goals
                SET {assignments}
                WHERE id = %s
                RETURNING *
                """,
                params,
            )
            row = dict(cur.fetchone())
        conn.commit()
        return jsonify({"success": True, "data": _decorate_single_goal(row)})
    except Exception as e:
        conn.rollback()
        return _api_error("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@dashboard_bp.route("/api/dashboard/goals/<uuid_id>/contribute", methods=["POST"])
@login_required
def api_contribute_goal(uuid_id):
    existing = _fetch_goal_for_user(uuid_id)
    if not existing:
        return _api_error("FORBIDDEN", "Access denied.", 403)

    data = request.get_json() or {}
    try:
        amount = money_to_decimal(data.get("amount", 0), field_name="Progress amount")
        if amount <= 0:
            raise ValueError("Progress amount must be greater than zero.")
    except ValueError as e:
        return _api_error("INVALID_INPUT", str(e))

    current_amount = money_to_decimal(existing["current_amount"], field_name="Saved amount")
    target_amount = money_to_decimal(existing["target_amount"], field_name="Target amount")
    new_current = current_amount + amount
    is_completed = bool(target_amount > 0 and new_current >= target_amount)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE savings_goals
                SET current_amount = %s,
                    is_completed = %s
                WHERE id = %s
                RETURNING *
                """,
                (new_current, is_completed, uuid_id),
            )
            row = dict(cur.fetchone())
        conn.commit()
        return jsonify({"success": True, "data": _decorate_single_goal(row)})
    except Exception as e:
        conn.rollback()
        return _api_error("UPDATE_FAILED", str(e), 500)
    finally:
        conn.close()


@dashboard_bp.route("/api/dashboard/goals/<uuid_id>", methods=["DELETE"])
@login_required
def api_delete_goal(uuid_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM savings_goals
                WHERE id = %s
                  AND account_id IN (
                    SELECT id
                    FROM accounts
                    WHERE user_id = %s
                  )
                RETURNING id
                """,
                (uuid_id, current_user.id),
            )
            row = cur.fetchone()
            if not row:
                return _api_error("FORBIDDEN", "Access denied.", 403)
        conn.commit()
        return jsonify({"success": True, "data": {"id": str(row["id"])}})
    except Exception as e:
        conn.rollback()
        return _api_error("DELETE_FAILED", str(e), 500)
    finally:
        conn.close()
