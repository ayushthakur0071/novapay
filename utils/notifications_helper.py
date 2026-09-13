import os
from datetime import datetime, timezone
from utils.supabase_client import get_supabase_client

def dispatch_mock_email(to_email: str, subject: str, body: str):
    """Logs a formatted mock email alert to mock_emails.log in the workspace root."""
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mock_emails.log")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    email_entry = f"""===============================================================================
[MOCK EMAIL DISPATCHED]
Timestamp: {timestamp}
To:        {to_email}
Subject:   {subject}
-------------------------------------------------------------------------------
{body}
===============================================================================
\n"""
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(email_entry)
        print(f"[MOCK EMAIL] Sent to {to_email}: '{subject}'")
    except Exception as e:
        print(f"Error writing mock email: {e}")

def create_notification(user_id: str, title: str, message: str, notif_type: str = "info", action_url: str = None) -> bool:
    """Inserts a notification record in the database and dispatches a mock email alert."""
    supabase = get_supabase_client()
    try:
        data = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notif_type,
            "is_read": False,
            "action_url": action_url
        }
        res = supabase.table("notifications").insert(data).execute()
        
        # Look up user email to dispatch alert
        try:
            user_res = supabase.table("users").select("email").eq("id", user_id).execute()
            if user_res.data:
                email = user_res.data[0]["email"]
                dispatch_mock_email(email, f"NovaPay Alert: {title}", message)
        except Exception as ex:
            print(f"Failed to lookup email for notification alert: {ex}")
            
        return bool(res.data)
    except Exception as e:
        print(f"Error creating notification: {e}")
        return False
