import random
from utils.supabase_client import get_supabase_client

def generate_account_number() -> str:
    """Generates a unique 8-digit account number."""
    supabase = get_supabase_client()
    
    while True:
        # Generate random 8-digit string
        acc_num = "".join([str(random.randint(0, 9)) for _ in range(8)])
        
        # Check uniqueness in database
        try:
            res = supabase.table("accounts").select("id").eq("account_number", acc_num).execute()
            if not res.data:
                return acc_num
        except Exception:
            # If database error (e.g. table not initialized yet), return the generated number
            # and let the database constraint handle collision if any
            return acc_num
