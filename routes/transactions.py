import csv
from io import StringIO
from flask import Blueprint, jsonify, request, render_template, make_response
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.transaction_engine import process_transaction
from utils.validators import clean_input
from utils.dashboard_metrics import get_monthly_spending, validate_month_key
from datetime import datetime, timezone

transactions_bp = Blueprint("transactions", __name__)

def _current_user_owns_account(account_id):
    """Returns True when the account belongs to the signed-in user."""
    if not account_id:
        return False

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
                  AND is_frozen = FALSE
                """,
                (account_id, current_user.id)
            )
            return cur.fetchone() is not None
    except Exception as e:
        print(f"Account ownership check failed: {e}")
        return False
    finally:
        conn.close()

@transactions_bp.route("/transactions/history", methods=["GET"])
@login_required
def history():
    """Renders transaction history listing page."""
    supabase = get_supabase_client()
    accounts = []
    try:
        res = supabase.table("accounts").select("id, account_number, account_type").eq("user_id", current_user.id).execute()
        accounts = res.data or []
    except Exception:
        pass
    return render_template("transactions/history.html", accounts=accounts)

@transactions_bp.route("/transactions/transfer", methods=["GET"])
@login_required
def transfer():
    """Renders transfer wizard page (internal & external transfers)."""
    supabase = get_supabase_client()
    accounts = []
    beneficiaries = []
    try:
        acc_res = supabase.table("accounts").select("*").eq("user_id", current_user.id).eq("is_frozen", False).execute()
        accounts = acc_res.data or []
        
        # Auto-provision own accounts as beneficiaries if missing
        for acc in accounts:
            ben_check = supabase.table("beneficiaries").select("id")\
                .eq("user_id", current_user.id)\
                .eq("account_number", acc["account_number"])\
                .eq("sort_code", acc["sort_code"])\
                .execute()
            if not ben_check.data:
                supabase.table("beneficiaries").insert({
                    "user_id": current_user.id,
                    "nickname": f"My {acc['nickname']}",
                    "full_name": current_user.full_name,
                    "account_number": acc["account_number"],
                    "sort_code": acc["sort_code"],
                    "bank_name": "NovaPay",
                    "reference": "Internal Transfer",
                    "is_trusted": True,
                    "is_active": True
                }).execute()
        
        ben_res = supabase.table("beneficiaries").select("*").eq("user_id", current_user.id).eq("is_active", True).execute()
        beneficiaries = ben_res.data or []
    except Exception as e:
        print(f"Error auto-populating own account beneficiaries: {e}")
        
    return render_template("transactions/transfer.html", accounts=accounts, beneficiaries=beneficiaries)

@transactions_bp.route("/api/transactions", methods=["GET"])
@login_required
def api_list():
    """Fetches paginated and filtered transactions list."""
    supabase = get_supabase_client()
    
    # 1. Fetch user accounts first
    acc_res = supabase.table("accounts").select("id").eq("user_id", current_user.id).execute()
    if not acc_res.data:
        return jsonify({"success": True, "data": []})
        
    acc_ids = [acc["id"] for acc in acc_res.data]
    
    # Filters
    account_id = request.args.get("account_id")
    category = request.args.get("category")
    txn_type = request.args.get("type")
    search = request.args.get("search", "").strip()
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # Build query
        query = """
            SELECT t.*, 
                   fa.account_number as from_account_number, fa.account_type as from_account_type,
                   ta.account_number as to_account_number, ta.account_type as to_account_type
            FROM transactions t
            LEFT JOIN accounts fa ON t.from_account_id = fa.id
            LEFT JOIN accounts ta ON t.to_account_id = ta.id
            WHERE (t.from_account_id = ANY(%s::uuid[]) OR t.to_account_id = ANY(%s::uuid[]))
        """
        params = [acc_ids, acc_ids]
        
        if account_id:
            query += " AND (t.from_account_id = %s OR t.to_account_id = %s)"
            params.extend([account_id, account_id])
            
        if category:
            query += " AND t.category = %s"
            params.append(category)
            
        if txn_type:
            if txn_type == "credit":
                # Received funds
                query += " AND (t.to_account_id = ANY(%s::uuid[]) AND (t.from_account_id NOT IN (SELECT id FROM accounts WHERE user_id = %s::uuid) OR t.from_account_id IS NULL))"
                params.extend([acc_ids, current_user.id])
            elif txn_type == "debit":
                # Spent funds
                query += " AND (t.from_account_id = ANY(%s::uuid[]) AND (t.to_account_id NOT IN (SELECT id FROM accounts WHERE user_id = %s::uuid) OR t.to_account_id IS NULL))"
                params.extend([acc_ids, current_user.id])
                
        if search:
            query += " AND (t.description ILIKE %s OR t.reference ILIKE %s OR t.transaction_ref ILIKE %s)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])
            
        query += " ORDER BY t.created_at DESC LIMIT 100"
        
        cur.execute(query, params)
        txns = cur.fetchall()
        
        # Convert Decimals and datetimes for JSON serialization
        for t in txns:
            t["amount"] = float(t["amount"])
            if t["balance_after"] is not None:
                t["balance_after"] = float(t["balance_after"])
            if t.get("fee") is not None:
                t["fee"] = float(t["fee"])
            if isinstance(t["created_at"], datetime):
                t["created_at"] = t["created_at"].isoformat()
                
        return jsonify({"success": True, "data": txns})
    except Exception as e:
        print(f"Error listing transactions: {e}")
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()

@transactions_bp.route("/api/transactions/transfer", methods=["POST"])
@login_required
def api_transfer():
    """Handles transfers between own checking/savings accounts."""
    data = request.get_json() or {}
    from_acc = data.get("from_account_id")
    to_acc = data.get("to_account_id")
    amount = data.get("amount", "0.00")
    reference = clean_input(data.get("reference", ""))
    
    if not (from_acc and to_acc and amount):
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMS", "message": "Sender, receiver, and amount are required."}}), 400

    if from_acc == to_acc:
        return jsonify({"success": False, "error": {"code": "SAME_ACCOUNTS", "message": "Choose a different destination account."}}), 400

    if not _current_user_owns_account(from_acc):
        return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Selected source account is not available."}}), 403

    if not _current_user_owns_account(to_acc):
        return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Selected destination account is not available."}}), 403
        
    res = process_transaction(
        from_account_id=from_acc,
        to_account_id=to_acc,
        amount_str=amount,
        description="Internal Transfer",
        reference=reference,
        transaction_type="transfer",
        ip_address=request.remote_addr,
        transfer_method="INTERNAL"
    )
    if res["success"]:
        return jsonify(res)
    return jsonify(res), 400

@transactions_bp.route("/api/transactions/send", methods=["POST"])
@login_required
def api_send():
    """Sends funds to a beneficiary (internal or external)."""
    data = request.get_json() or {}
    from_acc = data.get("from_account_id")
    beneficiary_id = data.get("beneficiary_id")
    amount = data.get("amount", "0.00")
    reference = clean_input(data.get("reference", ""))
    transfer_method = clean_input(data.get("transfer_method", "IMPS"))
    
    # Support custom payee details if beneficiary_id is not provided
    payee_name = clean_input(data.get("payee_name", ""))
    account_number = data.get("account_number", "").strip()
    sort_code = data.get("sort_code", "").strip()
    
    if not from_acc or not amount:
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMS", "message": "Source account and amount are required."}}), 400

    if not _current_user_owns_account(from_acc):
        return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Selected source account is not available."}}), 403

    external_recipient = None
    to_acc = None
    
    supabase = get_supabase_client()
    
    if beneficiary_id:
        # Load beneficiary from database
        try:
            ben_res = supabase.table("beneficiaries").select("*").eq("id", beneficiary_id).eq("user_id", current_user.id).execute()
            if not ben_res.data:
                return jsonify({"success": False, "error": {"code": "BENEFICIARY_NOT_FOUND", "message": "Recipient beneficiary not found."}}), 404
                
            payee = ben_res.data[0]
            payee_name = payee["full_name"]
            account_number = payee["account_number"]
            sort_code = payee["sort_code"]
            
            # Check if this payee is an internal NovaPay customer
            acc_check = supabase.table("accounts").select("id").eq("account_number", account_number).eq("sort_code", sort_code).execute()
            if acc_check.data:
                to_acc = acc_check.data[0]["id"]
            else:
                external_recipient = {
                    "nickname": payee["nickname"],
                    "account_number": account_number,
                    "sort_code": sort_code
                }
        except Exception as e:
            return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500
    else:
        if not (payee_name and account_number and sort_code):
            return jsonify({"success": False, "error": {"code": "MISSING_PAYEE_DETAILS", "message": "Recipient banking details are required."}}), 400
            
        # Check if payee details match internal customer
        try:
            acc_check = supabase.table("accounts").select("id").eq("account_number", account_number).eq("sort_code", sort_code).execute()
            if acc_check.data:
                to_acc = acc_check.data[0]["id"]
            else:
                external_recipient = {
                    "nickname": payee_name,
                    "account_number": account_number,
                    "sort_code": sort_code
                }
        except Exception:
            pass

    # Process transfer
    res = process_transaction(
        from_account_id=from_acc,
        to_account_id=to_acc,
        amount_str=amount,
        description=payee_name,
        reference=reference,
        transaction_type="payment",
        ip_address=request.remote_addr,
        external_recipient=external_recipient,
        transfer_method=transfer_method
    )
    if res["success"]:
        # Update last used timestamp for beneficiary if applicable
        if beneficiary_id:
            try:
                supabase.table("beneficiaries").update({"last_used": datetime.now(timezone.utc).isoformat()}).eq("id", beneficiary_id).execute()
            except Exception:
                pass
        return jsonify(res)
    return jsonify(res), 400

@transactions_bp.route("/api/transactions/deposit", methods=["POST"])
@login_required
def api_deposit():
    """Mock deposit for testing or loading funds (admin / demo user usage)."""
    data = request.get_json() or {}
    to_acc = data.get("to_account_id")
    amount = data.get("amount", "0.00")
    description = clean_input(data.get("description", "Demo Deposit"))
    
    if not (to_acc and amount):
        return jsonify({"success": False, "error": {"code": "MISSING_PARAMS", "message": "Target account and amount are required."}}), 400
        
    res = process_transaction(
        from_account_id=None,
        to_account_id=to_acc,
        amount_str=amount,
        description=description,
        reference="Mock Bank Deposit",
        transaction_type="deposit",
        ip_address=request.remote_addr
    )
    if res["success"]:
        return jsonify(res)
    return jsonify(res), 400

@transactions_bp.route("/api/transactions/summary", methods=["GET"])
@login_required
def api_summary():
    """Returns monthly spending breakdown by category for charts."""
    supabase = get_supabase_client()
    
    acc_res = supabase.table("accounts").select("id").eq("user_id", current_user.id).execute()
    if not acc_res.data:
        return jsonify({"success": True, "data": {}, "records": [], "total": 0})
        
    acc_ids = [acc["id"] for acc in acc_res.data]
    try:
        current_month = validate_month_key(request.args.get("month"))
        summary, records = get_monthly_spending(acc_ids, current_month)
        return jsonify({
            "success": True,
            "data": summary,
            "records": records,
            "total": round(sum(summary.values()), 2),
            "month": current_month,
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@transactions_bp.route("/api/transactions/export", methods=["GET"])
@login_required
def api_export():
    """Generates a downloadable CSV string of the transaction statement."""
    supabase = get_supabase_client()
    
    acc_res = supabase.table("accounts").select("id").eq("user_id", current_user.id).execute()
    if not acc_res.data:
        return "No transactions found", 400
        
    acc_ids = [acc["id"] for acc in acc_res.data]
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.created_at, t.transaction_ref, t.transaction_type, 
                   t.amount, t.description, t.reference, t.category, t.status, t.balance_after
            FROM transactions t
            WHERE t.from_account_id = ANY(%s::uuid[]) OR t.to_account_id = ANY(%s::uuid[])
            ORDER BY t.created_at DESC
            """,
            (acc_ids, acc_ids)
        )
        txns = cur.fetchall()
        
        # Write CSV
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(["Date", "Reference Code", "Type", "Amount", "Description", "Ref Text", "Category", "Status", "Balance After"])
        
        for t in txns:
            date_str = t["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            cw.writerow([
                date_str,
                t["transaction_ref"],
                t["transaction_type"],
                f"£{t['amount']:.2f}",
                t["description"],
                t["reference"] or "",
                t["category"],
                t["status"],
                f"£{t['balance_after']:.2f}" if t["balance_after"] is not None else ""
            ])
            
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=novapay_statement.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    except Exception as e:
        return str(e), 500
    finally:
        conn.close()
