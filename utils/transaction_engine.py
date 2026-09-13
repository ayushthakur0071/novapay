import re
import string
import random
from datetime import datetime, timezone
from decimal import Decimal
from utils.supabase_client import get_db_connection
from utils.notifications_helper import create_notification

CATEGORIES = {
  "salary":        ["salary","payroll","wages","employer","bacs"],
  "bills":         ["electric","gas","water","council tax","broadband","bt","virgin","ee","sky"],
  "shopping":      ["amazon","tesco","sainsbury","asda","morrisons","waitrose","marks","ebay"],
  "eating_out":    ["uber eats","deliveroo","just eat","mcdonalds","kfc","nandos","starbucks","cafe"],
  "transport":     ["tfl","oyster","train","trainline","uber","taxi","petrol","bp","shell","fuel"],
  "entertainment": ["netflix","spotify","disney","apple tv","cinema","vue","odeon","tickets"],
  "health":        ["boots","pharmacy","nhs","dentist","gym","david lloyd","pure gym"],
  "travel":        ["airbnb","booking.com","expedia","british airways","easyjet","holiday","hotel"],
  "savings":       ["savings","isa","investment","deposit"],
}

TRANSFER_CHARGES = {
    "NEFT": Decimal("0.50"),
    "IMPS": Decimal("1.50"),
    "RTGS": Decimal("5.00"),
    "OVERDRAFT": Decimal("10.00"),
    "INTERNAL": Decimal("0.00")
}


def categorise_transaction(description: str) -> str:
    """Auto-categorises a transaction based on keywords in its description."""
    if not description:
        return "other"
    desc_lower = description.lower()
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    return "other"

def generate_transaction_ref() -> str:
    """Generates unique transaction reference: TXN-{YYYYMMDD}-{8 random uppercase alphanum}."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    chars = string.ascii_uppercase + string.digits
    rand_part = "".join(random.choice(chars) for _ in range(8))
    return f"TXN-{date_str}-{rand_part}"

def process_transaction(
    from_account_id=None,
    to_account_id=None,
    amount_str: str = "0.00",
    description: str = "",
    reference: str = "",
    transaction_type: str = "transfer",
    ip_address: str = "127.0.0.1",
    external_recipient: dict = None,  # keys: nickname, account_number, sort_code
    transfer_method: str = "IMPS"
):
    """
    Executes transaction with complete ledger validation inside a database transaction.
    """
    amount = Decimal(amount_str)
    if amount <= 0:
        return {"success": False, "error": {"code": "INVALID_AMOUNT", "message": "Amount must be greater than zero."}}
    if amount > Decimal("50000.00"):
        return {"success": False, "error": {"code": "LIMIT_EXCEEDED", "message": "Maximum transaction limit is £50,000."}}
        
    method_upper = (transfer_method or "IMPS").upper().strip()
    fee = TRANSFER_CHARGES.get(method_upper, Decimal("1.50")) if from_account_id else Decimal("0.00")
    total_debit = amount + fee
    
    if from_account_id == to_account_id and from_account_id is not None:
        return {"success": False, "error": {"code": "SAME_ACCOUNTS", "message": "Sender and receiver accounts cannot be the same."}}

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # 1. Lock and validate sender account (if debit transaction)
        sender_acc = None
        sender_user = None
        if from_account_id:
            cur.execute("SELECT * FROM accounts WHERE id = %s FOR UPDATE", (from_account_id,))
            sender_acc = cur.fetchone()
            if not sender_acc:
                conn.rollback()
                return {"success": False, "error": {"code": "ACCOUNT_NOT_FOUND", "message": "Sender account not found."}}
            
            if not sender_acc["is_active"] or sender_acc["is_frozen"]:
                conn.rollback()
                return {"success": False, "error": {"code": "ACCOUNT_INACTIVE", "message": "Sender account is frozen or inactive."}}
            
            # Check if user is locked
            cur.execute("SELECT * FROM users WHERE id = %s", (sender_acc["user_id"],))
            sender_user = cur.fetchone()
            if sender_user and sender_user["locked_until"]:
                locked_until = sender_user["locked_until"]
                if locked_until > datetime.now(timezone.utc):
                    conn.rollback()
                    return {"success": False, "error": {"code": "USER_LOCKED", "message": "User account is temporarily locked."}}
            
            # Check available balance (must cover amount + transfer fee)
            avail_bal = Decimal(sender_acc["balance"]) + Decimal(sender_acc["overdraft_limit"])
            if avail_bal < total_debit:
                conn.rollback()
                return {"success": False, "error": {"code": "INSUFFICIENT_FUNDS", "message": f"Insufficient funds. Transfer amount + {method_upper} fee is £{total_debit:.2f}."}}

        # 2. Lock and validate receiver account (if internal transfer)
        receiver_acc = None
        receiver_user = None
        if to_account_id:
            cur.execute("SELECT * FROM accounts WHERE id = %s FOR UPDATE", (to_account_id,))
            receiver_acc = cur.fetchone()
            if not receiver_acc:
                conn.rollback()
                return {"success": False, "error": {"code": "ACCOUNT_NOT_FOUND", "message": "Receiver account not found."}}
            
            if not receiver_acc["is_active"] or receiver_acc["is_frozen"]:
                conn.rollback()
                return {"success": False, "error": {"code": "ACCOUNT_INACTIVE", "message": "Receiver account is frozen or inactive."}}
            
            cur.execute("SELECT * FROM users WHERE id = %s", (receiver_acc["user_id"],))
            receiver_user = cur.fetchone()

        # 3. Handle external recipient if transaction is an external payment
        # Check if to_account_id was not provided but external recipient details are present
        if not to_account_id and external_recipient:
            # Check if we have an internal account matching the sort code and account number
            cur.execute(
                "SELECT * FROM accounts WHERE account_number = %s AND sort_code = %s FOR UPDATE",
                (external_recipient["account_number"], external_recipient["sort_code"])
            )
            matched_acc = cur.fetchone()
            if matched_acc:
                to_account_id = matched_acc["id"]
                receiver_acc = matched_acc
                cur.execute("SELECT * FROM users WHERE id = %s", (receiver_acc["user_id"],))
                receiver_user = cur.fetchone()

        # Override fee to zero for internal transfers between same user's accounts
        if sender_acc and receiver_acc and sender_acc["user_id"] == receiver_acc["user_id"]:
            fee = Decimal("0.00")
            method_upper = "INTERNAL"
            total_debit = amount
            avail_bal = Decimal(sender_acc["balance"]) + Decimal(sender_acc["overdraft_limit"])
            if avail_bal < total_debit:
                conn.rollback()
                return {"success": False, "error": {"code": "INSUFFICIENT_FUNDS", "message": "Insufficient funds."}}

        # Generate unique reference
        txn_ref = generate_transaction_ref()
        category = categorise_transaction(description or reference)
        
        # 4. Perform balances update and insert transaction records
        debit_bal_after = None
        credit_bal_after = None
        
        if from_account_id:
            # Debit sender (amount + fee)
            new_sender_bal = Decimal(sender_acc["balance"]) - total_debit
            cur.execute(
                "UPDATE accounts SET balance = %s, available_balance = %s WHERE id = %s",
                (new_sender_bal, new_sender_bal, from_account_id)
            )
            debit_bal_after = new_sender_bal
            
        if to_account_id:
            # Credit receiver (receives just amount)
            new_receiver_bal = Decimal(receiver_acc["balance"]) + amount
            cur.execute(
                "UPDATE accounts SET balance = %s, available_balance = %s WHERE id = %s",
                (new_receiver_bal, new_receiver_bal, to_account_id)
            )
            credit_bal_after = new_receiver_bal
            
        # Write transaction record (including fee and transfer_method)
        cur.execute(
            """
            INSERT INTO transactions (from_account_id, to_account_id, transaction_ref, transaction_type, amount, description, reference, category, status, balance_after, ip_address, fee, transfer_method)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                from_account_id,
                to_account_id,
                txn_ref,
                transaction_type,
                amount,
                description or ("Transfer" if to_account_id else "External Payment"),
                reference,
                category,
                "completed",
                debit_bal_after if from_account_id else credit_bal_after,
                ip_address,
                fee,
                method_upper
            )
        )
        txn_id = cur.fetchone()["id"]

        # Write audit logs
        user_id = sender_acc["user_id"] if sender_acc else (receiver_acc["user_id"] if receiver_acc else None)
        cur.execute(
            """
            INSERT INTO audit_logs (user_id, action, resource, resource_id, new_value, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                f"transaction_{transaction_type}",
                "transactions",
                txn_id,
                f'{{"amount": "{amount_str}", "fee": "{fee}", "method": "{method_upper}", "ref": "{txn_ref}"}}',
                ip_address
            )
        )

        conn.commit()
        
        # 5. Send notifications (Post-Commit)
        if sender_acc:
            create_notification(
                user_id=sender_acc["user_id"],
                title="Money Sent",
                message=f"You sent £{amount:,.2f} from account {sender_acc['account_number']}. Ref: {txn_ref}",
                notif_type="transaction",
                action_url=f"/transactions/history"
            )
        if receiver_acc:
            create_notification(
                user_id=receiver_acc["user_id"],
                title="Money Received",
                message=f"You received £{amount:,.2f} into account {receiver_acc['account_number']}. Ref: {txn_ref}",
                notif_type="transaction",
                action_url=f"/transactions/history"
            )
            
        return {"success": True, "data": {"transaction_id": txn_id, "ref": txn_ref}}
        
    except Exception as e:
        conn.rollback()
        print(f"Transaction execution failed: {e}")
        return {"success": False, "error": {"code": "TRANSACTION_FAILED", "message": str(e)}}
    finally:
        conn.close()
