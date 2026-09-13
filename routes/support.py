import json
import random
from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client
from utils.validators import clean_input

support_bp = Blueprint("support", __name__)

@support_bp.route("/support", methods=["GET"])
@login_required
def index():
    """Renders user support tickets dashboard page."""
    supabase = get_supabase_client()
    tickets = []
    try:
        res = supabase.table("support_tickets").select("*").eq("user_id", current_user.id).order("created_at", desc=True).execute()
        tickets = res.data or []
    except Exception:
        pass
    return render_template("support/index.html", tickets=tickets)

@support_bp.route("/api/support/tickets", methods=["GET"])
@login_required
def api_list():
    """API returning customer's support tickets."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("support_tickets").select("*").eq("user_id", current_user.id).order("created_at", desc=True).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@support_bp.route("/api/support/tickets", methods=["POST"])
@login_required
def api_create():
    """Creates a new support ticket. Auto-sets Fraud/Security category to Urgent priority."""
    data = request.get_json() or {}
    subject = clean_input(data.get("subject", ""))
    message = clean_input(data.get("message", ""))
    category = clean_input(data.get("category", "general"))
    
    if not (subject and message):
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMS", "message": "Subject and message are required."}}), 400

    # Auto-escalation rules
    priority = "normal"
    if category in ["fraud", "security"]:
        priority = "urgent"
        
    ticket_ref = f"TKT-{random.randint(10000, 99999)}"
    
    # Store initial message in serialized JSON thread format inside the description field
    thread = [
        {
            "sender": "customer",
            "name": current_user.full_name,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat() if 'datetime' in globals() else ""
        }
    ]
    # Local import for datetime
    from datetime import datetime, timezone
    thread[0]["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    supabase = get_supabase_client()
    try:
        new_ticket = {
            "user_id": current_user.id,
            "ticket_ref": ticket_ref,
            "subject": subject,
            "description": json.dumps(thread),
            "category": category,
            "status": "open",
            "priority": priority
        }
        res = supabase.table("support_tickets").insert(new_ticket).execute()
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "CREATE_FAILED", "message": str(e)}}), 500

@support_bp.route("/api/support/tickets/<uuid_id>", methods=["GET"])
@login_required
def api_detail(uuid_id):
    """Fetches details and thread of a specific ticket."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("support_tickets").select("*").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not res.data:
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "Ticket not found."}}), 404
            
        ticket = res.data[0]
        try:
            ticket["thread"] = json.loads(ticket["description"])
        except Exception:
            # Fallback if raw text is found
            ticket["thread"] = [{"sender": "customer", "name": current_user.full_name, "message": ticket["description"], "timestamp": ticket["created_at"]}]
            
        return jsonify({"success": True, "data": ticket})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@support_bp.route("/api/support/tickets/<uuid_id>/reply", methods=["POST"])
@login_required
def api_reply(uuid_id):
    """Appends customer or agent replies to support threads."""
    data = request.get_json() or {}
    message = clean_input(data.get("message", ""))
    
    if not message:
        return jsonify({"success": False, "error": {"code": "MISSING_MESSAGE", "message": "Reply message cannot be empty."}}), 400
        
    supabase = get_supabase_client()
    try:
        # Load ticket details
        res = supabase.table("support_tickets").select("*").eq("id", uuid_id).eq("user_id", current_user.id).execute()
        if not res.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        ticket = res.data[0]
        try:
            thread = json.loads(ticket["description"])
        except Exception:
            thread = [{"sender": "customer", "name": current_user.full_name, "message": ticket["description"], "timestamp": ticket["created_at"]}]
            
        # Append message
        from datetime import datetime, timezone
        thread.append({
            "sender": "customer",
            "name": current_user.full_name,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Simulate auto-reply from helper bot if ticket is open
        if ticket["status"] == "open":
            thread.append({
                "sender": "support",
                "name": "NovaPay Support Agent",
                "message": "Thank you for contacting NovaPay support. We have received your query and a representative will reply shortly.",
                "timestamp": (datetime.now(timezone.utc) + timedelta(seconds=1) if 'timedelta' in globals() else datetime.now(timezone.utc)).isoformat()
            })
            
        upd = supabase.table("support_tickets").update({
            "description": json.dumps(thread),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", uuid_id).execute()
        
        return jsonify({"success": True, "data": thread})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "REPLY_FAILED", "message": str(e)}}), 500
