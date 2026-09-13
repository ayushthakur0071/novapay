from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.validators import clean_input
from datetime import datetime, timedelta, date, timezone
from dateutil.relativedelta import relativedelta

standing_orders_bp = Blueprint("standing_orders", __name__)

@standing_orders_bp.route("/standing-orders", methods=["GET"])
@login_required
def index():
    """Renders user's standing orders schedules page."""
    supabase = get_supabase_client()
    standing_orders = []
    accounts = []
    beneficiaries = []
    try:
        # Load user accounts
        acc_res = supabase.table("accounts").select("id, account_number, nickname, account_type").eq("user_id", current_user.id).execute()
        accounts = acc_res.data or []
        
        # Load active beneficiaries
        ben_res = supabase.table("beneficiaries").select("id, nickname, full_name").eq("user_id", current_user.id).eq("is_active", True).execute()
        beneficiaries = ben_res.data or []
        
        if accounts:
            acc_ids = [acc["id"] for acc in accounts]
            # Load active standing orders
            so_res = supabase.table("standing_orders")\
                .select("*, accounts(account_number, nickname), beneficiaries(nickname, full_name, account_number, sort_code)")\
                .in_("from_account_id", acc_ids)\
                .eq("is_active", True)\
                .execute()
            standing_orders = so_res.data or []
    except Exception:
        pass
    return render_template("standing_orders/index.html", standing_orders=standing_orders, accounts=accounts, beneficiaries=beneficiaries)

@standing_orders_bp.route("/api/standing-orders", methods=["GET"])
@login_required
def api_list():
    """JSON list of standing orders."""
    supabase = get_supabase_client()
    try:
        acc_res = supabase.table("accounts").select("id").eq("user_id", current_user.id).execute()
        if not acc_res.data:
            return jsonify({"success": True, "data": []})
            
        acc_ids = [acc["id"] for acc in acc_res.data]
        res = supabase.table("standing_orders").select("*").in_("from_account_id", acc_ids).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@standing_orders_bp.route("/api/standing-orders", methods=["POST"])
@login_required
def api_create():
    """Sets up a new standing order schedule."""
    data = request.get_json() or {}
    from_account_id = data.get("from_account_id")
    beneficiary_id = data.get("beneficiary_id")
    amount = float(data.get("amount", 0.0))
    reference = clean_input(data.get("reference", ""))
    frequency = data.get("frequency", "monthly").lower() # monthly, weekly, daily
    start_date_str = data.get("start_date") # YYYY-MM-DD
    
    if not (from_account_id and beneficiary_id and amount and start_date_str):
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMS", "message": "Source account, recipient, amount, and start date are required."}}), 400
        
    if amount <= 0:
        return jsonify({"success": False, "error": {"code": "INVALID_AMOUNT", "message": "Amount must be greater than zero."}}), 400
        
    if frequency not in ["daily", "weekly", "monthly"]:
        return jsonify({"success": False, "error": {"code": "INVALID_FREQUENCY", "message": "Frequency must be daily, weekly, or monthly."}}), 400

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"success": False, "error": {"code": "INVALID_DATE", "message": "Start date must match YYYY-MM-DD format."}}), 400

    supabase = get_supabase_client()
    try:
        # Check source account ownership
        acc_check = supabase.table("accounts").select("id").eq("id", from_account_id).eq("user_id", current_user.id).execute()
        if not acc_check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied on source account."}}), 403
            
        # Check beneficiary ownership
        ben_check = supabase.table("beneficiaries").select("id").eq("id", beneficiary_id).eq("user_id", current_user.id).execute()
        if not ben_check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied on target recipient."}}), 403

        # Compute next payment date
        next_payment = start_date
        today = date.today()
        if start_date < today:
            # Shift next_payment based on frequency until it is today or in the future
            while next_payment < today:
                if frequency == "daily":
                    next_payment += timedelta(days=1)
                elif frequency == "weekly":
                    next_payment += timedelta(weeks=1)
                elif frequency == "monthly":
                    next_payment += relativedelta(months=1)

        new_so = {
            "from_account_id": from_account_id,
            "beneficiary_id": beneficiary_id,
            "amount": amount,
            "reference": reference,
            "frequency": frequency,
            "start_date": start_date.isoformat(),
            "next_payment": next_payment.isoformat(),
            "is_active": True
        }
        
        res = supabase.table("standing_orders").insert(new_so).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "CREATE_FAILED", "message": str(e)}}), 500

@standing_orders_bp.route("/api/standing-orders/<uuid_id>", methods=["PATCH"])
@login_required
def api_update(uuid_id):
    """Edits a standing order schedule."""
    data = request.get_json() or {}
    amount = data.get("amount")
    reference = clean_input(data.get("reference", ""))
    
    supabase = get_supabase_client()
    try:
        # Check ownership
        check = supabase.table("standing_orders").select("*, accounts(user_id)").eq("id", uuid_id).execute()
        if not check.data or check.data[0]["accounts"]["user_id"] != current_user.id:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        update_fields = {}
        if amount is not None:
            val = float(amount)
            if val <= 0:
                return jsonify({"success": False, "error": {"code": "INVALID_AMOUNT", "message": "Amount must be greater than zero."}}), 400
            update_fields["amount"] = val
        if reference:
            update_fields["reference"] = reference
            
        if not update_fields:
            return jsonify({"success": False, "error": {"code": "NO_FIELDS", "message": "No fields specified to update."}}), 400
            
        upd = supabase.table("standing_orders").update(update_fields).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": upd.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500

@standing_orders_bp.route("/api/standing-orders/<uuid_id>", methods=["DELETE"])
@login_required
def api_cancel(uuid_id):
    """Cancels/deletes a standing order."""
    supabase = get_supabase_client()
    try:
        # Check ownership
        check = supabase.table("standing_orders").select("*, accounts(user_id)").eq("id", uuid_id).execute()
        if not check.data or check.data[0]["accounts"]["user_id"] != current_user.id:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        # Hard or soft delete, let's update is_active to False
        res = supabase.table("standing_orders").update({"is_active": False}).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "CANCEL_FAILED", "message": str(e)}}), 500
