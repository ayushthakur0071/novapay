import random
from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.encryption import encrypt_data, decrypt_data

cards_bp = Blueprint("cards", __name__)

@cards_bp.route("/cards", methods=["GET"])
@login_required
def index():
    """Renders user cards dashboard page."""
    supabase = get_supabase_client()
    cards = []
    accounts = []
    try:
        # Load user accounts
        acc_res = supabase.table("accounts").select("id, account_number, nickname, account_type").eq("user_id", current_user.id).execute()
        accounts = acc_res.data or []
        
        if accounts:
            acc_ids = [acc["id"] for acc in accounts]
            # Load cards linked to any of these accounts
            cards_res = supabase.table("cards").select("*, accounts(account_number, account_type)").in_("account_id", acc_ids).execute()
            cards = cards_res.data or []
    except Exception:
        pass
    return render_template("cards/index.html", cards=cards, accounts=accounts)

@cards_bp.route("/api/cards", methods=["GET"])
@login_required
def api_list():
    """Fetches user cards data in JSON format."""
    supabase = get_supabase_client()
    try:
        acc_res = supabase.table("accounts").select("id").eq("user_id", current_user.id).execute()
        if not acc_res.data:
            return jsonify({"success": True, "data": []})
            
        acc_ids = [acc["id"] for acc in acc_res.data]
        res = supabase.table("cards").select("*").in_("account_id", acc_ids).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@cards_bp.route("/api/cards", methods=["POST"])
@login_required
def api_issue():
    """Issues a new virtual card for a specific account."""
    data = request.get_json() or {}
    account_id = data.get("account_id")
    card_type = data.get("card_type", "debit")
    
    if not account_id:
        return jsonify({"success": False, "error": {"code": "MISSING_ACCOUNT", "message": "Account ID is required to bind a card."}}), 400
        
    supabase = get_supabase_client()
    try:
        # Check ownership
        check = supabase.table("accounts").select("id, account_number").eq("id", account_id).eq("user_id", current_user.id).execute()
        if not check.data:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        # Generate real card number and CVV details
        raw_card_num = f"475128{random.randint(10, 99)}{random.randint(10000000, 99999999)}"
        raw_cvv = f"{random.randint(100, 999)}"
        
        masked = f"4751 28{raw_card_num[6:8]} **** {raw_card_num[-4:]}"
        new_card = {
            "account_id": account_id,
            "masked_number": masked,
            "cardholder_name": current_user.full_name.upper(),
            "expiry_month": 12,
            "expiry_year": 2030,
            "card_type": card_type,
            "card_network": "Visa",
            "is_active": True,
            "is_frozen": False,
            "contactless_enabled": True,
            "online_payments_enabled": True,
            "international_payments": False,
            "daily_limit": 1000.00,
            "encrypted_card_number": encrypt_data(raw_card_num),
            "encrypted_cvv": encrypt_data(raw_cvv)
        }
        res = supabase.table("cards").insert(new_card).execute()
        
        # Log audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, resource_id, ip_address) VALUES (%s, 'issue_card', 'cards', %s, %s)",
                    (current_user.id, res.data[0]["id"], request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "ISSUE_FAILED", "message": str(e)}}), 500

@cards_bp.route("/api/cards/<uuid_id>/freeze", methods=["POST"])
@login_required
def api_freeze_toggle(uuid_id):
    """Toggles freeze state on a card."""
    supabase = get_supabase_client()
    try:
        # Check ownership of the account linked to this card
        res = supabase.table("cards").select("*, accounts(user_id)").eq("id", uuid_id).execute()
        if not res.data or res.data[0]["accounts"]["user_id"] != current_user.id:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        new_state = not res.data[0]["is_frozen"]
        upd = supabase.table("cards").update({"is_frozen": new_state}).eq("id", uuid_id).execute()
        
        # Log audit
        action = "freeze_card" if new_state else "unfreeze_card"
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, resource_id, ip_address) VALUES (%s, %s, 'cards', %s, %s)",
                    (current_user.id, action, uuid_id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True, "data": upd.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FREEZE_FAILED", "message": str(e)}}), 500

@cards_bp.route("/api/cards/<uuid_id>/settings", methods=["PATCH"])
@login_required
def api_update_settings(uuid_id):
    """Updates active card security and limit options."""
    data = request.get_json() or {}
    
    supabase = get_supabase_client()
    try:
        # Check ownership
        res = supabase.table("cards").select("*, accounts(user_id)").eq("id", uuid_id).execute()
        if not res.data or res.data[0]["accounts"]["user_id"] != current_user.id:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        update_fields = {}
        if "contactless_enabled" in data:
            update_fields["contactless_enabled"] = bool(data["contactless_enabled"])
        if "online_payments_enabled" in data:
            update_fields["online_payments_enabled"] = bool(data["online_payments_enabled"])
        if "international_payments" in data:
            update_fields["international_payments"] = bool(data["international_payments"])
        if "daily_limit" in data:
            update_fields["daily_limit"] = float(data["daily_limit"])
            
        if not update_fields:
            return jsonify({"success": False, "error": {"code": "NO_FIELDS", "message": "No settings parameters specified to update."}}), 400
            
        upd = supabase.table("cards").update(update_fields).eq("id", uuid_id).execute()
        return jsonify({"success": True, "data": upd.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "UPDATE_FAILED", "message": str(e)}}), 500

@cards_bp.route("/api/cards/<uuid_id>", methods=["DELETE"])
@login_required
def api_cancel(uuid_id):
    """Cancels a card completely (removes row)."""
    supabase = get_supabase_client()
    try:
        # Check ownership
        res = supabase.table("cards").select("*, accounts(user_id)").eq("id", uuid_id).execute()
        if not res.data or res.data[0]["accounts"]["user_id"] != current_user.id:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        supabase.table("cards").delete().eq("id", uuid_id).execute()
        
        # Log audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, resource_id, ip_address) VALUES (%s, 'cancel_card', 'cards', %s, %s)",
                    (current_user.id, uuid_id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True, "message": "Card cancelled successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "CANCEL_FAILED", "message": str(e)}}), 500

@cards_bp.route("/api/cards/<uuid_id>/reveal", methods=["POST"])
@login_required
def api_reveal(uuid_id):
    """Decrypts and reveals the full card number and CVV details, logging to audit logs."""
    supabase = get_supabase_client()
    try:
        # Check ownership
        res = supabase.table("cards").select("*, accounts(user_id)").eq("id", uuid_id).execute()
        if not res.data or res.data[0]["accounts"]["user_id"] != current_user.id:
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied."}}), 403
            
        card = res.data[0]
        enc_num = card.get("encrypted_card_number")
        enc_cvv = card.get("encrypted_cvv")
        if not enc_num or not enc_cvv:
            # Self-healing: generate new encrypted card credentials for legacy cards
            raw_card_num = f"475128{random.randint(10, 99)}{random.randint(10000000, 99999999)}"
            raw_cvv = f"{random.randint(100, 999)}"
            
            enc_num = encrypt_data(raw_card_num)
            enc_cvv = encrypt_data(raw_cvv)
            masked = f"4751 28{raw_card_num[6:8]} **** {raw_card_num[-4:]}"
            
            supabase.table("cards").update({
                "encrypted_card_number": enc_num,
                "encrypted_cvv": enc_cvv,
                "masked_number": masked
            }).eq("id", uuid_id).execute()
            
        dec_num = decrypt_data(enc_num)
        dec_cvv = decrypt_data(enc_cvv)
        
        # Log to audit trail
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, resource_id, ip_address) VALUES (%s, 'reveal_card_details', 'cards', %s, %s)",
                    (current_user.id, uuid_id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({
            "success": True,
            "card_number": dec_num,
            "cvv": dec_cvv
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "REVEAL_FAILED", "message": str(e)}}), 500
