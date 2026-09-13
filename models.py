from flask_login import UserMixin
from datetime import datetime

class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data.get("id")
        self.full_name = user_data.get("full_name")
        self.email = user_data.get("email")
        self.phone = user_data.get("phone")
        self.password_hash = user_data.get("password_hash")
        self.date_of_birth = user_data.get("date_of_birth")
        if isinstance(self.date_of_birth, str):
            self.date_of_birth = datetime.strptime(self.date_of_birth.split("T")[0], "%Y-%m-%d").date()
        self.address = user_data.get("address")
        self.city = user_data.get("city")
        self.postcode = user_data.get("postcode")
        self.country = user_data.get("country", "United Kingdom")
        self._is_active = user_data.get("is_active", True)
        self.is_admin = user_data.get("is_admin", False)
        self.is_verified = user_data.get("is_verified", False)
        self.kyc_status = user_data.get("kyc_status", "pending")
        self.failed_attempts = user_data.get("failed_attempts", 0)
        self.locked_until = user_data.get("locked_until")
        self.last_login = user_data.get("last_login")
        self.mfa_enabled = user_data.get("mfa_enabled", False)
        self.mfa_secret = user_data.get("mfa_secret")
        self.kyc_document_type = user_data.get("kyc_document_type")
        self.kyc_document_file = user_data.get("kyc_document_file")
        self.created_at = user_data.get("created_at")

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

    @property
    def is_locked(self):
        if not self.locked_until:
            return False
        # Handle timezone string conversion or parsing if locked_until is string
        # Supabase returns ISO format strings
        from dateutil import parser
        from datetime import timezone
        
        locked_time = self.locked_until
        if isinstance(locked_time, str):
            locked_time = parser.parse(locked_time)
            
        now = datetime.now(timezone.utc)
        return locked_time > now

    @staticmethod
    def get(user_id):
        # We import here to avoid circular imports
        from utils.supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        try:
            res = supabase.table("users").select("*").eq("id", user_id).execute()
            if res.data and len(res.data) > 0:
                return User(res.data[0])
        except Exception:
            return None
        return None
