from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.validators import clean_input, is_valid_phone, evaluate_password_strength
from utils.auth_helpers import hash_password, verify_password

profile_bp = Blueprint("profile", __name__)

@profile_bp.route("/profile", methods=["GET"])
@login_required
def index():
    """Renders profile page showing details and session histories."""
    supabase = get_supabase_client()
    audit_logs = []
    try:
        # Load user audit logs for login history
        logs_res = supabase.table("audit_logs")\
            .select("*")\
            .eq("user_id", current_user.id)\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()
        audit_logs = logs_res.data or []
    except Exception:
        pass
    return render_template("profile/index.html", audit_logs=audit_logs)

@profile_bp.route("/settings", methods=["GET"])
@login_required
def settings():
    """Renders settings control dashboard."""
    return render_template("settings/index.html")

@profile_bp.route("/api/profile", methods=["GET"])
@login_required
def api_get():
    """Returns profile JSON."""
    return jsonify({
        "success": True,
        "data": {
            "full_name": current_user.full_name,
            "email": current_user.email,
            "phone": current_user.phone,
            "date_of_birth": str(current_user.date_of_birth),
            "address": current_user.address,
            "city": current_user.city,
            "postcode": current_user.postcode,
            "country": current_user.country,
            "kyc_status": current_user.kyc_status
        }
    })

@profile_bp.route("/api/profile", methods=["PATCH"])
@login_required
def api_update():
    """Updates user address, city, postcode, and phone number."""
    data = request.get_json() or {}
    full_name = clean_input(data.get("full_name", ""))
    phone = data.get("phone", "").strip()
    address = clean_input(data.get("address", ""))
    city = clean_input(data.get("city", ""))
    postcode = clean_input(data.get("postcode", ""))
    
    update_data = {}
    if full_name:
        update_data["full_name"] = full_name
    if phone:
        if not is_valid_phone(phone):
            return jsonify({"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid UK phone number."}}), 400
        update_data["phone"] = phone
    if address:
        update_data["address"] = address
    if city:
        update_data["city"] = city
    if postcode:
        update_data["postcode"] = postcode
        
    if not update_data:
        return jsonify({"success": False, "error": {"code": "NO_FIELDS", "message": "No profile updates specified."}}), 400
        
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").update(update_data).eq("id", current_user.id).execute()
        
        # Log audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'update_profile', 'users', %s)",
                    (current_user.id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500

@profile_bp.route("/api/profile/change-password", methods=["POST"])
@login_required
def api_change_password():
    """Verifies old credentials and commits updated bcrypt password hash."""
    data = request.get_json() or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    
    if not (old_password and new_password):
        return jsonify({"success": False, "error": {"code": "MISSING_FIELDS", "message": "Current and new passwords are required."}}), 400
        
    if not verify_password(old_password, current_user.password_hash):
        return jsonify({"success": False, "error": {"code": "INVALID_PASSWORD", "message": "Current password verification failed."}}), 401
        
    pwd_eval = evaluate_password_strength(new_password)
    if not pwd_eval["is_valid"]:
        return jsonify({"success": False, "error": {"code": "WEAK_PASSWORD", "message": pwd_eval["feedback"][0]}}), 400
        
    new_hash = hash_password(new_password)
    supabase = get_supabase_client()
    
    try:
        supabase.table("users").update({"password_hash": new_hash}).eq("id", current_user.id).execute()
        
        # Log audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'change_password', 'users', %s)",
                    (current_user.id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True, "message": "Password changed successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500
