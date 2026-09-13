from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client

notifications_bp = Blueprint("notifications", __name__)

@notifications_bp.route("/notifications", methods=["GET"])
@login_required
def index():
    """Renders user notifications feed view."""
    supabase = get_supabase_client()
    notifications = []
    try:
        res = supabase.table("notifications").select("*").eq("user_id", current_user.id).order("created_at", desc=True).limit(50).execute()
        notifications = res.data or []
    except Exception:
        pass
    return render_template("notifications/index.html", notifications=notifications)

@notifications_bp.route("/api/notifications", methods=["GET"])
@login_required
def api_list():
    """Fetches user notifications JSON list (unread first)."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("notifications").select("*").eq("user_id", current_user.id).order("is_read").order("created_at", desc=True).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@notifications_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required
def api_read_all():
    """Marks all user notifications as read with a sweeping transition."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("notifications").update({"is_read": True}).eq("user_id", current_user.id).eq("is_read", False).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500

@notifications_bp.route("/api/notifications/<uuid_id>/read", methods=["PATCH"])
@login_required
def api_read_one(uuid_id):
    """Marks a single notification as read."""
    supabase = get_supabase_client()
    try:
        # Check ownership
        check = supabase.table("notifications").select("id").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        res = supabase.table("notifications").update({"is_read": True}).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500

@notifications_bp.route("/api/notifications/<uuid_id>", methods=["DELETE"])
@login_required
def api_delete(uuid_id):
    """Deletes a notification from user feed."""
    supabase = get_supabase_client()
    try:
        check = supabase.table("notifications").select("id").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        supabase.table("notifications").delete().eq("id", uuid_id).execute()
        return jsonify({"success": True, "message": "Notification deleted."})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "DELETE_FAILED", "message": str(e)}}), 500
