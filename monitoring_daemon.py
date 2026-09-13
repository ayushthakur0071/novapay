import time
import os
import requests
from datetime import datetime, timezone
from decimal import Decimal
from dotenv import load_dotenv
from utils.supabase_client import get_db_connection
from utils.transaction_engine import process_transaction

load_dotenv()

# Load parameters from environment
AWS_URL = os.environ.get("AWS_URL", "http://127.0.0.1:5001").rstrip("/")
AZURE_URL = os.environ.get("AZURE_URL", "http://127.0.0.1:5002").rstrip("/")
PROXY_URL = os.environ.get("PROXY_URL", f"http://127.0.0.1:{os.environ.get('PROXY_PORT', '8080')}").rstrip("/")

THRESHOLD_MS = int(os.environ.get("FAILOVER_THRESHOLD_MS", "3000"))
FAILURE_COUNT_LIMIT = int(os.environ.get("FAILOVER_FAILURE_COUNT", "3"))
INTERVAL = int(os.environ.get("MONITOR_INTERVAL_SECONDS", "30"))
HEALTH_CHECK_TIMEOUT = int(os.environ.get("HEALTH_CHECK_TIMEOUT", "10"))

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
AZURE_REGION = os.environ.get("AZURE_REGION", "uk-south")

# State tracker
current_active = os.environ.get("PRIMARY_CLOUD", "aws").lower()
consecutive_aws_failures = 0
consecutive_azure_failures = 0

def check_instance_health(url):
    """Pings a cloud server instance to fetch response time, CPU, memory, and status."""
    start_time = time.time()
    headers = {"User-Agent": "NovaPay-DR-Daemon/1.0"}
    try:
        resp = requests.get(f"{url}/health", timeout=HEALTH_CHECK_TIMEOUT, headers=headers)
        latency = (time.time() - start_time) * 1000
        if resp.status_code == 200:
            data = resp.json()
            return {
                "status": "UP",
                "latency_ms": round(latency, 2),
                "cpu": data.get("cpu_usage", 0.0),
                "memory": data.get("memory_usage", 0.0),
                "sessions": data.get("active_sessions", 0),
                "error": None
            }
        else:
            return {
                "status": "DOWN",
                "latency_ms": round(latency, 2),
                "cpu": 0.0,
                "memory": 0.0,
                "sessions": 0,
                "error": f"HTTP {resp.status_code}"
            }
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return {
            "status": "DOWN",
            "latency_ms": round(latency, 2),
            "cpu": 0.0,
            "memory": 0.0,
            "sessions": 0,
            "error": str(e)
        }

def save_monitoring_log(server, status, result):
    """Saves instance metrics into the database."""
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        region_label = AWS_REGION if server == "aws" else AZURE_REGION
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO monitoring_logs (server, status, response_time, cpu_usage, memory_usage, active_sessions, region, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    server,
                    status,
                    Decimal(str(result["latency_ms"] / 1000.0)),
                    Decimal(str(result["cpu"])),
                    Decimal(str(result["memory"])),
                    result["sessions"],
                    region_label,
                    result["error"]
                )
            )
    except Exception as e:
        print(f"[DAEMON ERROR] Failed to save monitoring logs to DB: {e}")
    finally:
        if conn:
            conn.close()

def notify_admins(title, message):
    """Sends notification to all admin users in the database."""
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE is_admin = True")
            admins = cur.fetchall()
            for admin in admins:
                cur.execute(
                    """
                    INSERT INTO notifications (user_id, title, message, type, is_read)
                    VALUES (%s, %s, %s, 'system', False)
                    """,
                    (admin["id"], title, message)
                )
    except Exception as e:
        print(f"[DAEMON ERROR] Failed to alert admins: {e}")
    finally:
        if conn:
            conn.close()

def trigger_failover(from_server, to_server, reason):
    """Updates routing configuration and records failover timeline."""
    global current_active
    start_time = time.time()
    print(f"[FAILOVER DETECTED] Triggering active-passive failover from {from_server.upper()} to {to_server.upper()}. Reason: {reason}")
    
    # 1. Update global proxy routing server
    try:
        resp = requests.post(f"{PROXY_URL}/proxy/update-routing", json={"active": to_server}, timeout=3)
        proxy_ok = resp.status_code == 200
    except Exception as e:
        proxy_ok = False
        print(f"[DAEMON ERROR] Failed to signal proxy routing change: {e}")
        
    rto = time.time() - start_time
    current_active = to_server
    
    # 2. Log incident and recover RTO details to DB
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO failover_events (from_server, to_server, trigger_reason, rto_seconds, triggered_at, resolved_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    from_server,
                    to_server,
                    reason + (" | Proxy updated successfully" if proxy_ok else " | Proxy update failed"),
                    Decimal(str(rto))
                )
            )
            
        notify_admins(
            "Multi-Cloud Failover Activated",
            f"NovaPay has successfully failed over from {from_server.upper()} to {to_server.upper()} in {rto:.3f} seconds. Reason: {reason}."
        )
    except Exception as e:
        print(f"[DAEMON ERROR] Failed to write failover events to DB: {e}")
    finally:
        if conn:
            conn.close()

def process_scheduled_transfers():
    """Finds and processes scheduled transfers whose execution date has arrived."""
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        scheduled_txns = []
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM transactions 
                WHERE status = 'scheduled' AND created_at <= NOW()
                """
            )
            scheduled_txns = cur.fetchall()
            
        for txn in scheduled_txns:
            print(f"[DAEMON PAYMENT] Processing scheduled transaction {txn['transaction_ref']}")
            # Execute transfer
            res = execute_scheduled_transfer(txn)
            if res["success"]:
                print(f"[DAEMON PAYMENT] Successfully processed transaction {txn['transaction_ref']}")
            else:
                print(f"[DAEMON PAYMENT] Scheduled transaction {txn['transaction_ref']} failed: {res['error']['message']}")
    except Exception as e:
        print(f"[DAEMON ERROR] Failed to fetch scheduled transfers: {e}")
    finally:
        if conn:
            conn.close()

def execute_scheduled_transfer(txn):
    """Executes money transfer for a single scheduled database record."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Lock accounts
        from_id = txn["from_account_id"]
        to_id = txn["to_account_id"]
        amount = Decimal(txn["amount"])
        
        cur.execute("SELECT balance, overdraft_limit, user_id FROM accounts WHERE id = %s FOR UPDATE", (from_id,))
        sender = cur.fetchone()
        
        if not sender:
            cur.execute("UPDATE transactions SET status = 'failed' WHERE id = %s", (txn["id"],))
            conn.commit()
            return {"success": False, "error": {"message": "Sender account not found"}}
            
        avail_bal = Decimal(sender["balance"]) + Decimal(sender["overdraft_limit"])
        if avail_bal < amount:
            cur.execute("UPDATE transactions SET status = 'failed' WHERE id = %s", (txn["id"],))
            conn.commit()
            return {"success": False, "error": {"message": "Insufficient funds"}}
            
        # Update sender
        new_sender_bal = Decimal(sender["balance"]) - amount
        cur.execute("UPDATE accounts SET balance = %s, available_balance = %s WHERE id = %s", (new_sender_bal, new_sender_bal, from_id))
        
        # Update receiver
        new_receiver_bal = None
        if to_id:
            cur.execute("SELECT balance FROM accounts WHERE id = %s FOR UPDATE", (to_id,))
            receiver = cur.fetchone()
            if receiver:
                new_receiver_bal = Decimal(receiver["balance"]) + amount
                cur.execute("UPDATE accounts SET balance = %s, available_balance = %s WHERE id = %s", (new_receiver_bal, new_receiver_bal, to_id))
        
        # Complete transaction
        cur.execute(
            "UPDATE transactions SET status = 'completed', balance_after = %s WHERE id = %s",
            (new_sender_bal, txn["id"])
        )
        conn.commit()
        return {"success": True}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"success": False, "error": {"message": str(e)}}
    finally:
        if conn:
            conn.close()

def main_loop():
    global consecutive_aws_failures, consecutive_azure_failures, current_active
    print(f"[DAEMON START] NovaPay Disaster Recovery monitoring active. Checking every {INTERVAL}s.")
    
    while True:
        # 1. Probe cloud instances
        aws_res = check_instance_health(AWS_URL)
        azure_res = check_instance_health(AZURE_URL)
        
        # 2. Write to logs
        save_monitoring_log("aws", aws_res["status"], aws_res)
        save_monitoring_log("azure", azure_res["status"], azure_res)
        
        # Update consecutive failure tracks
        if aws_res["status"] == "DOWN":
            consecutive_aws_failures += 1
        else:
            consecutive_aws_failures = 0
            
        if azure_res["status"] == "DOWN":
            consecutive_azure_failures += 1
        else:
            consecutive_azure_failures = 0
            
        # 3. Decision Engine Logic
        if current_active == "aws":
            # Primary active is AWS
            if consecutive_aws_failures >= FAILURE_COUNT_LIMIT:
                trigger_failover("aws", "azure", "AWS consecutive failures limit exceeded")
            elif aws_res["status"] == "UP" and aws_res["latency_ms"] >= THRESHOLD_MS:
                # Check latency of last 5 entries in database
                avg_latency = aws_res["latency_ms"]
                conn = None
                try:
                    conn = get_db_connection()
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT response_time FROM monitoring_logs WHERE server='aws' ORDER BY created_at DESC LIMIT 5"
                        )
                        rows = cur.fetchall()
                        if len(rows) >= 5:
                            avg_latency = sum(float(r["response_time"]) for r in rows) / len(rows) * 1000
                except Exception:
                    pass
                finally:
                    if conn:
                        conn.close()
                
                if avg_latency >= THRESHOLD_MS:
                    trigger_failover("aws", "azure", f"AWS response time rolling average ({avg_latency:.1f}ms) exceeded threshold")
                    
        elif current_active == "azure":
            # Active is Azure, check if AWS has recovered and we want to fail back (optional, but let's keep passive-active stability)
            if consecutive_azure_failures >= FAILURE_COUNT_LIMIT:
                trigger_failover("azure", "aws", "Azure consecutive failures limit exceeded")
            elif azure_res["status"] == "UP" and azure_res["latency_ms"] >= THRESHOLD_MS:
                trigger_failover("azure", "aws", f"Azure latency exceeded threshold")
                
        # 4. Check secondary state to notify admins if degraded
        if current_active == "aws" and azure_res["status"] == "DOWN" and consecutive_azure_failures == FAILURE_COUNT_LIMIT:
            notify_admins("Secondary Cloud Offline", "Azure cloud host or database is currently unreachable.")
        elif current_active == "azure" and aws_res["status"] == "DOWN" and consecutive_aws_failures == FAILURE_COUNT_LIMIT:
            notify_admins("Primary Cloud Offline", "AWS cloud host or database is currently unreachable.")

        # 5. Process scheduled bank transfers
        process_scheduled_transfers()
        
        # Sleep
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main_loop()
