from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client
from utils.validators import clean_input, is_valid_account_number, is_valid_sort_code

beneficiaries_bp = Blueprint("beneficiaries", __name__)

@beneficiaries_bp.route("/beneficiaries", methods=["GET"])
@login_required
def index():
    """Renders the beneficiaries management dashboard."""
    supabase = get_supabase_client()
    beneficiaries = []
    try:
        res = supabase.table("beneficiaries").select("*").eq("user_id", current_user.id).eq("is_active", True).execute()
        beneficiaries = res.data or []
    except Exception:
        pass
    return render_template("beneficiaries/index.html", beneficiaries=beneficiaries)

@beneficiaries_bp.route("/api/beneficiaries", methods=["GET"])
@login_required
def api_list():
    """Fetches beneficiaries list JSON."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("beneficiaries").select("*").eq("user_id", current_user.id).eq("is_active", True).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@beneficiaries_bp.route("/api/beneficiaries", methods=["POST"])
@login_required
def api_create():
    """Inserts a new beneficiary for the user."""
    data = request.get_json() or {}
    nickname = clean_input(data.get("nickname", ""))
    full_name = clean_input(data.get("full_name", ""))
    account_number = data.get("account_number", "").strip()
    sort_code = data.get("sort_code", "").strip()
    bank_name = clean_input(data.get("bank_name", "Other Bank"))
    reference = clean_input(data.get("reference", ""))
    
    if not (nickname and full_name and account_number and sort_code):
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMS", "message": "Nickname, full name, account number, and sort code are required."}}), 400
        
    if not is_valid_account_number(account_number):
        return jsonify({"success": False, "error": {"code": "INVALID_ACCOUNT", "message": "Account number must be exactly 8 digits."}}), 400
        
    if not is_valid_sort_code(sort_code):
        return jsonify({"success": False, "error": {"code": "INVALID_SORT", "message": "Sort code must match XX-XX-XX format."}}), 400
        
    supabase = get_supabase_client()
    try:
        # Check duplicate
        check = supabase.table("beneficiaries")\
            .select("id, is_active")\
            .eq("user_id", current_user.id)\
            .eq("account_number", account_number)\
            .eq("sort_code", sort_code)\
            .execute()
            
        if check.data:
            exist = check.data[0]
            if exist["is_active"]:
                return jsonify({"success": False, "error": {"code": "DUPLICATE", "message": "A beneficiary with these details already exists."}}), 400
            else:
                # Reactivate soft deleted payee
                res = supabase.table("beneficiaries").update({
                    "is_active": True,
                    "nickname": nickname,
                    "full_name": full_name,
                    "bank_name": bank_name,
                    "reference": reference
                }).eq("id", exist["id"]).execute()
                return jsonify({"success": True, "data": res.data[0]})

        new_ben = {
            "user_id": current_user.id,
            "nickname": nickname,
            "full_name": full_name,
            "account_number": account_number,
            "sort_code": sort_code,
            "bank_name": bank_name,
            "reference": reference,
            "is_trusted": False,
            "is_active": True
        }
        res = supabase.table("beneficiaries").insert(new_ben).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "CREATE_FAILED", "message": str(e)}}), 500

@beneficiaries_bp.route("/api/beneficiaries/<uuid_id>", methods=["GET"])
@login_required
def api_detail(uuid_id):
    """Fetches details of a beneficiary."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("beneficiaries").select("*").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not res.data:
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "Beneficiary not found."}}), 404
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@beneficiaries_bp.route("/api/beneficiaries/<uuid_id>", methods=["PATCH"])
@login_required
def api_update(uuid_id):
    """Updates beneficiary nickname and references."""
    data = request.get_json() or {}
    nickname = clean_input(data.get("nickname", ""))
    reference = clean_input(data.get("reference", ""))
    
    if not nickname:
        return jsonify({"success": False, "error": {"code": "MISSING_NICKNAME", "message": "Nickname is required."}}), 400
        
    supabase = get_supabase_client()
    try:
        # Check ownership
        check = supabase.table("beneficiaries").select("id").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        res = supabase.table("beneficiaries").update({
            "nickname": nickname,
            "reference": reference
        }).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500

@beneficiaries_bp.route("/api/beneficiaries/<uuid_id>", methods=["DELETE"])
@login_required
def api_delete(uuid_id):
    """Soft-deletes a beneficiary."""
    supabase = get_supabase_client()
    try:
        check = supabase.table("beneficiaries").select("id").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        res = supabase.table("beneficiaries").update({"is_active": False}).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "DELETE_FAILED", "message": str(e)}}), 500

@beneficiaries_bp.route("/api/beneficiaries/<uuid_id>/trust", methods=["POST"])
@login_required
def api_trust(uuid_id):
    """Toggles beneficiary trust badge."""
    supabase = get_supabase_client()
    try:
        check = supabase.table("beneficiaries").select("id, is_trusted").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        new_trust = not check.data[0]["is_trusted"]
        res = supabase.table("beneficiaries").update({"is_trusted": new_trust}).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "TRUST_FAILED", "message": str(e)}}), 500
