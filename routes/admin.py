from functools import wraps
from flask import Blueprint, jsonify, request, render_template, abort, redirect, url_for
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.transaction_engine import process_transaction
from utils.validators import clean_input
from decimal import Decimal

admin_bp = Blueprint("admin", __name__)

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
@admin_bp.route("/admin/dashboard", methods=["GET"])
@admin_required
def dashboard():
    return render_template("admin/dashboard.html")

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
    """Fetches full list of registered customers."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("id, full_name, email, phone, is_active, kyc_status, created_at").eq("is_admin", False).order("created_at", desc=True).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@admin_bp.route("/api/admin/users/<uuid_id>", methods=["GET"])
@admin_required
def api_user_detail(uuid_id):
    """Loads a customer's detailed record including cards, logs, and accounts."""
    supabase = get_supabase_client()
    try:
        # Load user
        user_res = supabase.table("users").select("*").eq("id", uuid_id).execute()
        if not user_res.data:
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "User not found."}}), 404
            
        user = user_res.data[0]
        # Remove password hash for safety
        user.pop("password_hash", None)
        
        # Load user accounts
        acc_res = supabase.table("accounts").select("*").eq("user_id", uuid_id).execute()
        accounts = acc_res.data or []
        
        return jsonify({
            "success": True,
            "data": {
                "user": user,
                "accounts": accounts
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

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
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.*, u.full_name as user_full_name, u.email as user_email
            FROM transactions t
            LEFT JOIN accounts a ON (t.from_account_id = a.id OR t.to_account_id = a.id)
            LEFT JOIN users u ON a.user_id = u.id
            ORDER BY t.created_at DESC LIMIT 200
            """
        )
        txns = cur.fetchall()
        for t in txns:
            t["amount"] = float(t["amount"])
            if t["balance_after"] is not None:
                t["balance_after"] = float(t["balance_after"])
            t["created_at"] = t["created_at"].isoformat()
            
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
