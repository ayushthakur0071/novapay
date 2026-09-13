from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from utils.supabase_client import get_supabase_client, get_db_connection

statements_bp = Blueprint("statements", __name__)

@statements_bp.route("/statements", methods=["GET"])
@login_required
def index():
    """Renders statement generator page."""
    supabase = get_supabase_client()
    accounts = []
    selected_account_id = request.args.get("account_id")
    month_val = request.args.get("month") # YYYY-MM
    
    transactions = []
    opening_balance = 0.00
    closing_balance = 0.00
    
    try:
        # Load user accounts
        acc_res = supabase.table("accounts").select("id, account_number, nickname, balance").eq("user_id", current_user.id).execute()
        accounts = acc_res.data or []
        
        if accounts:
            if not selected_account_id:
                selected_account_id = accounts[0]["id"]
                
            # Get selected account details
            curr_acc = next((a for a in accounts if a["id"] == selected_account_id), accounts[0])
            closing_balance = float(curr_acc["balance"])
            
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                # If month filter is applied
                if month_val:
                    cur.execute(
                        """
                        SELECT * FROM transactions
                        WHERE (from_account_id = %s OR to_account_id = %s)
                          AND TO_CHAR(created_at, 'YYYY-MM') = %s
                        ORDER BY created_at ASC
                        """,
                        (selected_account_id, selected_account_id, month_val)
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM transactions
                        WHERE (from_account_id = %s OR to_account_id = %s)
                        ORDER BY created_at ASC LIMIT 100
                        """,
                        (selected_account_id, selected_account_id)
                    )
                transactions = cur.fetchall()
                
                # Compute opening balance (Closing balance minus Net delta of all fetched transactions)
                net_delta = 0.00
                for t in transactions:
                    t["amount"] = float(t["amount"])
                    if t["balance_after"] is not None:
                        t["balance_after"] = float(t["balance_after"])
                    
                    # If this user account sent the money, delta is negative
                    if str(t["from_account_id"]) == selected_account_id:
                        net_delta -= t["amount"]
                    else:
                        net_delta += t["amount"]
                
                opening_balance = closing_balance - net_delta
                
                # For display, reverse transaction list so newest is first
                transactions.reverse()
            except Exception as e:
                print(f"Error fetching statement transactions: {e}")
            finally:
                conn.close()
    except Exception:
        pass
        
    return render_template(
        "statements/index.html",
        accounts=accounts,
        selected_account_id=selected_account_id,
        month_val=month_val,
        transactions=transactions,
        opening_balance=opening_balance,
        closing_balance=closing_balance
    )
