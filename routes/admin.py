from functools import wraps
from datetime import date, datetime
from flask import Blueprint, jsonify, request, render_template, abort, redirect, url_for
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.transaction_engine import process_transaction
from utils.validators import clean_input
from decimal import Decimal

admin_bp = Blueprint("admin", __name__)


def _json_safe_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _json_safe_row(row):
    return {key: _json_safe_value(value) for key, value in dict(row).items()}


def _json_safe_rows(rows):
    return [_json_safe_row(row) for row in rows]


def _current_month_key():
    return datetime.utcnow().strftime("%Y-%m")

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Admin privileges required."}}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Templates
@admin_bp.route("/admin", methods=["GET"])
@admin_bp.route("/admin/dashboard", methods=["GET"])
@admin_required
def dashboard():
    return render_template("admin/dashboard.html")

@admin_bp.route("/admin/accounts", methods=["GET"])
@admin_required
def accounts_list():
    return render_template("admin/accounts.html")

@admin_bp.route("/admin/users", methods=["GET"])
@admin_required
def users_list():
    return render_template("admin/users.html")

@admin_bp.route("/admin/transactions", methods=["GET"])
@admin_required
def txns_list():
    return render_template("admin/transactions.html")

@admin_bp.route("/admin/monitoring", methods=["GET"])
@admin_required
def monitoring_dashboard():
    return render_template("admin/monitoring.html")

# APIs
@admin_bp.route("/api/admin/stats", methods=["GET"])
@admin_required
def api_stats():
    """Gathers KPIs: users count, transactions count, and AUM."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # 1. Total users
        cur.execute("SELECT COUNT(*) as count FROM users WHERE is_admin = False")
        total_users = cur.fetchone()["count"]
        
        # 2. Total Assets Under Management (AUM)
        cur.execute("SELECT SUM(balance) as total FROM accounts")
        aum = cur.fetchone()["total"] or 0.00
        
        # 3. Transaction stats (Count and volume today)
        cur.execute("SELECT COUNT(*) as count, SUM(amount) as volume FROM transactions WHERE status = 'completed'")
        txn = cur.fetchone()
        txn_count = txn["count"]
        txn_volume = txn["volume"] or 0.00
        
        return jsonify({
            "success": True,
            "data": {
                "total_users": total_users,
                "aum": float(aum),
                "transaction_count": txn_count,
                "transaction_volume": float(txn_volume)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()

@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def api_users():
    """Fetches full list of registered customers with account exposure."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.id,
                    u.full_name,
                    u.email,
                    u.phone,
                    u.is_active,
                    u.kyc_status,
                    u.is_verified,
                    u.last_login,
                    u.created_at,
                    COUNT(a.id)::int AS account_count,
                    COALESCE(SUM(a.balance), 0) AS total_balance,
                    COALESCE(SUM(a.available_balance), 0) AS total_available_balance
                FROM users u
                LEFT JOIN accounts a ON a.user_id = u.id
                WHERE u.is_admin = FALSE
                GROUP BY
                    u.id,
                    u.full_name,
                    u.email,
                    u.phone,
                    u.is_active,
                    u.kyc_status,
                    u.is_verified,
                    u.last_login,
                    u.created_at
                ORDER BY u.created_at DESC
                """
            )
            rows = cur.fetchall()
        return jsonify({"success": True, "data": _json_safe_rows(rows)})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()


@admin_bp.route("/api/admin/accounts", methods=["GET"])
@admin_required
def api_accounts():
    """Returns all customer accounts with owner and ledger rollups."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH txn_rollup AS (
                    SELECT
                        a.id AS account_id,
                        COUNT(t.id)::int AS transaction_count,
                        COALESCE(SUM(CASE WHEN t.to_account_id = a.id THEN t.amount ELSE 0 END), 0) AS incoming_total,
                        COALESCE(SUM(CASE WHEN t.from_account_id = a.id THEN t.amount + COALESCE(t.fee, 0) ELSE 0 END), 0) AS outgoing_total,
                        MAX(t.created_at) AS last_transaction_at
                    FROM accounts a
                    LEFT JOIN transactions t ON t.from_account_id = a.id OR t.to_account_id = a.id
                    GROUP BY a.id
                )
                SELECT
                    a.*,
                    u.full_name AS user_full_name,
                    u.email AS user_email,
                    u.phone AS user_phone,
                    u.kyc_status AS user_kyc_status,
                    u.is_active AS user_is_active,
                    COALESCE(tr.transaction_count, 0)::int AS transaction_count,
                    COALESCE(tr.incoming_total, 0) AS incoming_total,
                    COALESCE(tr.outgoing_total, 0) AS outgoing_total,
                    tr.last_transaction_at
                FROM accounts a
                JOIN users u ON u.id = a.user_id
                LEFT JOIN txn_rollup tr ON tr.account_id = a.id
                WHERE u.is_admin = FALSE
                ORDER BY u.full_name, a.created_at
                """
            )
            rows = cur.fetchall()
        return jsonify({"success": True, "data": _json_safe_rows(rows)})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()

@admin_bp.route("/api/admin/users/<uuid_id>", methods=["GET"])
@admin_required
def api_user_detail(uuid_id):
    """Loads a customer's detailed record including accounts, ledger, spend, and product signals."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s AND is_admin = FALSE", (uuid_id,))
            user_row = cur.fetchone()
        if not user_row:
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "User not found."}}), 404

        user = _json_safe_row(user_row)
        user.pop("password_hash", None)

        with conn.cursor() as cur:
            cur.execute(
                """
                WITH txn_rollup AS (
                    SELECT
                        a.id AS account_id,
                        COUNT(t.id)::int AS transaction_count,
                        COALESCE(SUM(CASE WHEN t.to_account_id = a.id THEN t.amount ELSE 0 END), 0) AS incoming_total,
                        COALESCE(SUM(CASE WHEN t.from_account_id = a.id THEN t.amount + COALESCE(t.fee, 0) ELSE 0 END), 0) AS outgoing_total,
                        MAX(t.created_at) AS last_transaction_at
                    FROM accounts a
                    LEFT JOIN transactions t ON t.from_account_id = a.id OR t.to_account_id = a.id
                    WHERE a.user_id = %s
                    GROUP BY a.id
                )
                SELECT
                    a.*,
                    COALESCE(tr.transaction_count, 0)::int AS transaction_count,
                    COALESCE(tr.incoming_total, 0) AS incoming_total,
                    COALESCE(tr.outgoing_total, 0) AS outgoing_total,
                    tr.last_transaction_at
                FROM accounts a
                LEFT JOIN txn_rollup tr ON tr.account_id = a.id
                WHERE a.user_id = %s
                ORDER BY a.created_at
                """,
                (uuid_id, uuid_id),
            )
            account_rows = cur.fetchall()

        accounts = _json_safe_rows(account_rows)
        account_ids = [str(account["id"]) for account in accounts]
        current_month = _current_month_key()

        recent_transactions = []
        spending_by_category = []
        transaction_count = 0
        monthly_income = Decimal("0")
        monthly_spending = Decimal("0")

        if account_ids:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        t.*,
                        fa.account_number AS from_account_number,
                        fa.account_type AS from_account_type,
                        fu.id AS from_user_id,
                        fu.full_name AS from_user_name,
                        fu.email AS from_user_email,
                        ta.account_number AS to_account_number,
                        ta.account_type AS to_account_type,
                        tu.id AS to_user_id,
                        tu.full_name AS to_user_name,
                        tu.email AS to_user_email
                    FROM transactions t
                    LEFT JOIN accounts fa ON fa.id = t.from_account_id
                    LEFT JOIN users fu ON fu.id = fa.user_id
                    LEFT JOIN accounts ta ON ta.id = t.to_account_id
                    LEFT JOIN users tu ON tu.id = ta.user_id
                    WHERE t.from_account_id = ANY(%s::uuid[])
                       OR t.to_account_id = ANY(%s::uuid[])
                    ORDER BY t.created_at DESC
                    LIMIT 80
                    """,
                    (account_ids, account_ids),
                )
                transaction_rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT COUNT(DISTINCT t.id)::int AS count
                    FROM transactions t
                    WHERE t.from_account_id = ANY(%s::uuid[])
                       OR t.to_account_id = ANY(%s::uuid[])
                    """,
                    (account_ids, account_ids),
                )
                transaction_count = cur.fetchone()["count"]

                cur.execute(
                    """
                    SELECT
                        COALESCE(NULLIF(t.category, ''), 'other') AS category,
                        COUNT(*)::int AS transaction_count,
                        COALESCE(SUM(t.amount + COALESCE(t.fee, 0)), 0) AS total
                    FROM transactions t
                    WHERE t.from_account_id = ANY(%s::uuid[])
                      AND t.status = 'completed'
                      AND t.created_at >= date_trunc('month', NOW())
                      AND (t.to_account_id IS NULL OR NOT (t.to_account_id = ANY(%s::uuid[])))
                    GROUP BY COALESCE(NULLIF(t.category, ''), 'other')
                    ORDER BY total DESC
                    """,
                    (account_ids, account_ids),
                )
                spending_by_category = _json_safe_rows(cur.fetchall())

                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE
                            WHEN t.to_account_id = ANY(%s::uuid[])
                             AND (t.from_account_id IS NULL OR NOT (t.from_account_id = ANY(%s::uuid[])))
                            THEN t.amount ELSE 0 END), 0) AS monthly_income,
                        COALESCE(SUM(CASE
                            WHEN t.from_account_id = ANY(%s::uuid[])
                             AND (t.to_account_id IS NULL OR NOT (t.to_account_id = ANY(%s::uuid[])))
                            THEN t.amount + COALESCE(t.fee, 0) ELSE 0 END), 0) AS monthly_spending
                    FROM transactions t
                    WHERE t.status = 'completed'
                      AND t.created_at >= date_trunc('month', NOW())
                      AND (t.from_account_id = ANY(%s::uuid[]) OR t.to_account_id = ANY(%s::uuid[]))
                    """,
                    (account_ids, account_ids, account_ids, account_ids, account_ids, account_ids),
                )
                month_row = cur.fetchone()
                monthly_income = month_row["monthly_income"] or Decimal("0")
                monthly_spending = month_row["monthly_spending"] or Decimal("0")

            owned = set(account_ids)
            for row in transaction_rows:
                txn = _json_safe_row(row)
                from_id = str(txn.get("from_account_id")) if txn.get("from_account_id") else None
                to_id = str(txn.get("to_account_id")) if txn.get("to_account_id") else None
                from_owned = from_id in owned
                to_owned = to_id in owned

                if to_owned and not from_owned:
                    direction = "credit"
                    counterparty = txn.get("from_user_name") or "External deposit"
                    prefix = "+"
                elif from_owned and to_owned:
                    direction = "internal"
                    counterparty = "Own account transfer"
                    prefix = ""
                else:
                    direction = "debit"
                    counterparty = txn.get("to_user_name") or txn.get("reference") or "External recipient"
                    prefix = "-"

                txn["direction"] = direction
                txn["display_prefix"] = prefix
                txn["display_amount"] = float(txn.get("amount") or 0) + (float(txn.get("fee") or 0) if direction == "debit" else 0)
                txn["counterparty"] = counterparty
                recent_transactions.append(txn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM spending_budgets
                WHERE user_id = %s
                  AND month = %s
                ORDER BY category
                """,
                (uuid_id, current_month),
            )
            budgets = _json_safe_rows(cur.fetchall())

            cur.execute(
                """
                SELECT
                    sg.*,
                    a.nickname AS account_nickname,
                    a.account_number
                FROM savings_goals sg
                JOIN accounts a ON a.id = sg.account_id
                WHERE a.user_id = %s
                ORDER BY sg.is_completed, sg.target_date NULLS LAST, sg.created_at DESC
                """,
                (uuid_id,),
            )
            savings_goals = _json_safe_rows(cur.fetchall())

            cur.execute(
                """
                SELECT
                    c.*,
                    a.account_number,
                    a.nickname AS account_nickname
                FROM cards c
                JOIN accounts a ON a.id = c.account_id
                WHERE a.user_id = %s
                ORDER BY c.created_at DESC
                """,
                (uuid_id,),
            )
            cards = _json_safe_rows(cur.fetchall())

            cur.execute(
                """
                SELECT
                    so.*,
                    a.account_number,
                    a.nickname AS account_nickname,
                    b.nickname AS beneficiary_nickname,
                    b.full_name AS beneficiary_name
                FROM standing_orders so
                JOIN accounts a ON a.id = so.from_account_id
                JOIN beneficiaries b ON b.id = so.beneficiary_id
                WHERE a.user_id = %s
                ORDER BY so.next_payment NULLS LAST, so.created_at DESC
                LIMIT 20
                """,
                (uuid_id,),
            )
            standing_orders = _json_safe_rows(cur.fetchall())

            cur.execute(
                """
                SELECT id, ticket_ref, subject, category, status, priority, created_at, updated_at
                FROM support_tickets
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT 10
                """,
                (uuid_id,),
            )
            support_tickets = _json_safe_rows(cur.fetchall())

            cur.execute(
                """
                SELECT id, title, message, type, is_read, action_url, created_at
                FROM notifications
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (uuid_id,),
            )
            notifications = _json_safe_rows(cur.fetchall())

            cur.execute(
                """
                SELECT id, action, resource, resource_id, ip_address, created_at
                FROM audit_logs
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 15
                """,
                (uuid_id,),
            )
            audit_logs = _json_safe_rows(cur.fetchall())

        total_balance = sum(float(account.get("balance") or 0) for account in accounts)
        total_available = sum(float(account.get("available_balance") or 0) for account in accounts)
        total_overdraft = sum(float(account.get("overdraft_limit") or 0) for account in accounts)

        return jsonify({
            "success": True,
            "data": {
                "user": user,
                "accounts": accounts,
                "recent_transactions": recent_transactions,
                "spending_by_category": spending_by_category,
                "budgets": budgets,
                "savings_goals": savings_goals,
                "cards": cards,
                "standing_orders": standing_orders,
                "support_tickets": support_tickets,
                "notifications": notifications,
                "audit_logs": audit_logs,
                "summary": {
                    "account_count": len(accounts),
                    "total_balance": total_balance,
                    "total_available_balance": total_available,
                    "total_overdraft_limit": total_overdraft,
                    "transaction_count": transaction_count,
                    "monthly_income": float(monthly_income),
                    "monthly_spending": float(monthly_spending),
                    "current_month": current_month,
                    "active_cards": len([card for card in cards if card.get("is_active") is not False and card.get("is_frozen") is not True]),
                    "active_standing_orders": len([order for order in standing_orders if order.get("is_active") is not False]),
                    "open_tickets": len([ticket for ticket in support_tickets if str(ticket.get("status", "")).lower() in ["open", "pending"]]),
                    "unread_notifications": len([notif for notif in notifications if notif.get("is_read") is False])
                }
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()

@admin_bp.route("/api/admin/users/<uuid_id>/freeze", methods=["POST"])
@admin_required
def api_freeze_user(uuid_id):
    """Toggles active/frozen flag for a customer profile."""
    supabase = get_supabase_client()
    try:
        check = supabase.table("users").select("is_active").eq("id", uuid_id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "User not found."}}), 404
            
        new_state = not check.data[0]["is_active"]
        res = supabase.table("users").update({"is_active": new_state}).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FREEZE_FAILED", "message": str(e)}}), 500

@admin_bp.route("/api/admin/users/<uuid_id>/verify-kyc", methods=["POST"])
@admin_required
def api_verify_kyc(uuid_id):
    """Updates KYC verify states for compliance audits."""
    data = request.get_json() or {}
    status = data.get("status", "approved") # approved, hold, declined, pending
    
    if status not in ["approved", "hold", "declined", "pending"]:
        return jsonify({"success": False, "error": {"code": "INVALID_STATUS", "message": "KYC status must be approved, hold, declined, or pending."}}), 400
        
    supabase = get_supabase_client()
    try:
        is_active = False if status == "declined" else True
        res = supabase.table("users").update({
            "kyc_status": status,
            "is_verified": status == "approved",
            "is_active": is_active
        }).eq("id", uuid_id).execute()
        
        # Send notification
        cur_user_id = uuid_id
        from utils.notifications_helper import create_notification
        create_notification(
            user_id=cur_user_id,
            title="KYC Status Updated",
            message=f"Your KYC compliance check has been updated to: {status.upper()}.",
            notif_type="security"
        )
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "KYC_FAILED", "message": str(e)}}), 500

@admin_bp.route("/api/admin/transactions", methods=["GET"])
@admin_required
def api_transactions():
    """Aggregates master transaction ledger."""
    conn = get_db_connection()
    try:
        query_text = clean_input(request.args.get("search", "")).strip()
        status = clean_input(request.args.get("status", "all")).strip().lower()
        category = clean_input(request.args.get("category", "all")).strip().lower()
        txn_type = clean_input(request.args.get("type", "all")).strip().lower()

        try:
            limit = min(max(int(request.args.get("limit", 250)), 1), 500)
        except (TypeError, ValueError):
            limit = 250

        where = []
        params = []

        if query_text:
            where.append(
                """
                (
                    t.transaction_ref ILIKE %s
                    OR t.description ILIKE %s
                    OR t.reference ILIKE %s
                    OR fa.account_number ILIKE %s
                    OR ta.account_number ILIKE %s
                    OR fu.full_name ILIKE %s
                    OR tu.full_name ILIKE %s
                    OR fu.email ILIKE %s
                    OR tu.email ILIKE %s
                )
                """
            )
            like = f"%{query_text}%"
            params.extend([like] * 9)

        if status != "all":
            where.append("LOWER(t.status) = %s")
            params.append(status)

        if category != "all":
            where.append("LOWER(COALESCE(t.category, 'other')) = %s")
            params.append(category)

        if txn_type != "all":
            where.append("LOWER(t.transaction_type) = %s")
            params.append(txn_type)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    t.*,
                    fa.account_number AS from_account_number,
                    fa.account_type AS from_account_type,
                    fu.id AS from_user_id,
                    fu.full_name AS from_user_full_name,
                    fu.email AS from_user_email,
                    ta.account_number AS to_account_number,
                    ta.account_type AS to_account_type,
                    tu.id AS to_user_id,
                    tu.full_name AS to_user_full_name,
                    tu.email AS to_user_email
                FROM transactions t
                LEFT JOIN accounts fa ON t.from_account_id = fa.id
                LEFT JOIN users fu ON fa.user_id = fu.id
                LEFT JOIN accounts ta ON t.to_account_id = ta.id
                LEFT JOIN users tu ON ta.user_id = tu.id
                {where_sql}
                ORDER BY t.created_at DESC
                LIMIT %s
                """,
                params + [limit],
            )
            txns = _json_safe_rows(cur.fetchall())

        for txn in txns:
            txn["display_amount"] = float(txn.get("amount") or 0) + float(txn.get("fee") or 0)

        return jsonify({"success": True, "data": txns})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()

@admin_bp.route("/api/admin/transactions/<uuid_id>/reverse", methods=["POST"])
@admin_required
def api_reverse_txn(uuid_id):
    """Reverses a transaction by processing a matching counter-transaction."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM transactions WHERE id = %s", (uuid_id,))
        txn = cur.fetchone()
        
        if not txn:
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "Transaction not found."}}), 404
            
        if txn["status"] != "completed":
            return jsonify({"success": False, "error": {"code": "INVALID_STATE", "message": "Can only reverse completed transactions."}}), 400
            
        # Execute processing of reversal
        # We swap from_account_id and to_account_id
        res = process_transaction(
            from_account_id=txn["to_account_id"],
            to_account_id=txn["from_account_id"],
            amount_str=str(txn["amount"]),
            description=f"REVERSAL OF {txn['transaction_ref']}",
            reference="Admin Reversal",
            transaction_type="reversal",
            ip_address=request.remote_addr
        )
        
        if res["success"]:
            # Mark original transaction as reversed
            cur.execute("UPDATE transactions SET status = 'reversed' WHERE id = %s", (uuid_id,))
            conn.commit()
            return jsonify({"success": True, "data": {"reversal_ref": res["data"]["ref"]}})
        else:
            return jsonify({"success": False, "error": res["error"]}), 400
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "REVERSAL_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()

@admin_bp.route("/api/admin/broadcast", methods=["POST"])
@admin_required
def api_broadcast():
    """Sends custom system messages to all customers."""
    data = request.get_json() or {}
    title = clean_input(data.get("title", ""))
    message = clean_input(data.get("message", ""))
    
    if not (title and message):
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMS", "message": "Title and message are required."}}), 400
        
    supabase = get_supabase_client()
    try:
        # Fetch all user IDs
        users_res = supabase.table("users").select("id").eq("is_admin", False).execute()
        user_ids = [u["id"] for u in users_res.data or []]
        
        notifications_to_insert = [
            {"user_id": uid, "title": title, "message": message, "type": "system", "is_read": False}
            for uid in user_ids
        ]
        
        if notifications_to_insert:
            supabase.table("notifications").insert(notifications_to_insert).execute()
            
        return jsonify({"success": True, "message": f"Broadcast sent to {len(user_ids)} users."})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "BROADCAST_FAILED", "message": str(e)}}), 500
