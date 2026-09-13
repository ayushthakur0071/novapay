from flask import Blueprint, jsonify, request, render_template, redirect, url_for
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.validators import clean_input
from utils.account_gen import generate_account_number
from decimal import Decimal

accounts_bp = Blueprint("accounts", __name__)

@accounts_bp.route("/accounts", methods=["GET"])
@login_required
def list_view():
    """Renders page listing all user bank accounts."""
    supabase = get_supabase_client()
    accounts = []
    try:
        res = supabase.table("accounts").select("*").eq("user_id", current_user.id).order("created_at").execute()
        accounts = res.data or []
    except Exception as e:
        print(f"Error fetching accounts list: {e}")
    return render_template("accounts/list.html", accounts=accounts)

@accounts_bp.route("/accounts/<uuid_id>", methods=["GET"])
@login_required
def detail_view(uuid_id):
    """Renders details page for a specific bank account."""
    supabase = get_supabase_client()
    try:
        # Fetch account details
        acc_res = supabase.table("accounts").select("*").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not acc_res.data:
            return render_template("errors/404.html"), 404
            
        account = acc_res.data[0]
        
        # Fetch card details linked to this account
        cards_res = supabase.table("cards").select("*").eq("account_id", uuid_id).execute()
        cards = cards_res.data or []
        
        # Fetch savings goals bound to this account
        goals_res = supabase.table("savings_goals").select("*").eq("account_id", uuid_id).execute()
        goals = goals_res.data or []
        
        return render_template("accounts/detail.html", account=account, cards=cards, savings_goals=goals)
    except Exception as e:
        print(f"Error loading account detail: {e}")
        return render_template("errors/500.html"), 500

@accounts_bp.route("/api/accounts", methods=["GET"])
@login_required
def api_list():
    """JSON API to retrieve user accounts."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("accounts").select("*").eq("user_id", current_user.id).order("created_at").execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@accounts_bp.route("/api/accounts/<uuid_id>", methods=["GET"])
@login_required
def api_detail(uuid_id):
    """JSON API for single account details."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("accounts").select("*").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not res.data:
            return jsonify({"success": False, "error": {"code": "ACCOUNT_NOT_FOUND", "message": "Account not found."}}), 404
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@accounts_bp.route("/api/accounts", methods=["POST"])
@login_required
def api_create():
    """API endpoint to create a new Savings or ISA account."""
    data = request.get_json() or {}
    account_type = data.get("account_type", "savings").lower()
    nickname = clean_input(data.get("nickname", ""))
    
    if account_type not in ["savings", "isa"]:
        return jsonify({"success": False, "error": {"code": "INVALID_TYPE", "message": "Can only create savings or ISA accounts."}}), 400
        
    acc_num = generate_account_number()
    supabase = get_supabase_client()
    
    try:
        new_acc = {
            "user_id": current_user.id,
            "account_number": acc_num,
            "sort_code": "20-45-91",
            "account_type": account_type,
            "currency": "GBP",
            "balance": 0.00,
            "available_balance": 0.00,
            "overdraft_limit": 0.00,
            "nickname": nickname or f"My New {account_type.upper()}"
        }
        res = supabase.table("accounts").insert(new_acc).execute()
        
        # Log audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, resource_id, ip_address) VALUES (%s, 'create_account', 'accounts', %s, %s)",
                    (current_user.id, res.data[0]["id"], request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "CREATE_FAILED", "message": str(e)}}), 500

@accounts_bp.route("/api/accounts/<uuid_id>", methods=["PATCH"])
@login_required
def api_update_nickname(uuid_id):
    """API to edit account nickname."""
    data = request.get_json() or {}
    nickname = clean_input(data.get("nickname", ""))
    
    if not nickname:
        return jsonify({"success": False, "error": {"code": "MISSING_NICKNAME", "message": "Nickname is required."}}), 400
        
    supabase = get_supabase_client()
    try:
        # Check ownership first
        check = supabase.table("accounts").select("id").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        res = supabase.table("accounts").update({"nickname": nickname}).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500

@accounts_bp.route("/api/accounts/<uuid_id>/freeze", methods=["POST"])
@login_required
def api_freeze_toggle(uuid_id):
    """API endpoint to toggle freeze status on a banking account."""
    supabase = get_supabase_client()
    try:
        # Check ownership
        check = supabase.table("accounts").select("id, is_frozen").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        new_freeze_state = not check.data[0]["is_frozen"]
        res = supabase.table("accounts").update({"is_frozen": new_freeze_state}).eq("id", uuid_id).execute()
        
        # Log audit
        action = "freeze_account" if new_freeze_state else "unfreeze_account"
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, resource_id, ip_address) VALUES (%s, %s, 'accounts', %s, %s)",
                    (current_user.id, uuid_id, action, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FREEZE_FAILED", "message": str(e)}}), 500

@accounts_bp.route("/api/accounts/<uuid_id>/balance", methods=["GET"])
@login_required
def api_balance(uuid_id):
    """Fetches balance stats for telemetry updates."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("accounts").select("balance, available_balance, overdraft_limit").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not res.data:
            return jsonify({"success": False, "error": {"code": "ACCOUNT_NOT_FOUND", "message": "Account not found."}}), 404
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
