import os
import time
from flask import Blueprint, jsonify, request, Response
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.monitoring_helpers import check_db_health, get_system_telemetry

from extensions import limiter

monitoring_bp = Blueprint("monitoring", __name__)

# Track server startup time for uptime metric
START_TIME = time.time()

@monitoring_bp.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """Banking node health check interface for proxy checks and load balancers."""
    db_res = check_db_health()
    sys_res = get_system_telemetry()
    uptime = time.time() - START_TIME
    
    status = "healthy"
    if db_res["status"] != "connected":
        status = "degraded"
        
    return jsonify({
        "status": status,
        "server": os.environ.get("PRIMARY_CLOUD", "aws"),
        "db": db_res["status"],
        "db_latency_ms": db_res["latency_ms"],
        "cpu_usage": sys_res["cpu_usage"],
        "memory_usage": sys_res["memory_usage"],
        "active_sessions": sys_res["active_sessions"],
        "uptime": round(uptime, 2)
    })

@monitoring_bp.route("/metrics", methods=["GET"])
@limiter.exempt
def metrics():
    """Prometheus telemetry endpoints format."""
    db_res = check_db_health()
    sys_res = get_system_telemetry()
    uptime = time.time() - START_TIME
    
    server_lbl = os.environ.get("PRIMARY_CLOUD", "aws")
    
    # Format standard text metric outputs
    lines = [
        f'# HELP novapay_uptime_seconds Uptime of the NovaPay node in seconds.',
        f'# TYPE novapay_uptime_seconds gauge',
        f'novapay_uptime_seconds{{server="{server_lbl}"}} {uptime:.2f}',
        
        f'# HELP novapay_cpu_usage CPU utilization percent.',
        f'# TYPE novapay_cpu_usage gauge',
        f'novapay_cpu_usage{{server="{server_lbl}"}} {sys_res["cpu_usage"]:.2f}',
        
        f'# HELP novapay_memory_usage Memory utilization percent.',
        f'# TYPE novapay_memory_usage gauge',
        f'novapay_memory_usage{{server="{server_lbl}"}} {sys_res["memory_usage"]:.2f}',
        
        f'# HELP novapay_db_latency_ms Latency of database ping in milliseconds.',
        f'# TYPE novapay_db_latency_ms gauge',
        f'novapay_db_latency_ms{{server="{server_lbl}"}} {db_res["latency_ms"]:.2f}',
        
        f'# HELP novapay_active_sessions Count of active user sessions.',
        f'# TYPE novapay_active_sessions gauge',
        f'novapay_active_sessions{{server="{server_lbl}"}} {sys_res["active_sessions"]}'
    ]
    
    return Response("\n".join(lines) + "\n", mimetype="text/plain")

@monitoring_bp.route("/api/monitoring/current", methods=["GET"])
def api_current_telemetry():
    """Returns the latest telemetry log entries for both cloud systems."""
    supabase = get_supabase_client()
    try:
        aws_res = supabase.table("monitoring_logs").select("*").eq("server", "aws").order("created_at", desc=True).limit(1).execute()
        azure_res = supabase.table("monitoring_logs").select("*").eq("server", "azure").order("created_at", desc=True).limit(1).execute()
        
        data = {
            "aws": aws_res.data[0] if aws_res.data else None,
            "azure": azure_res.data[0] if azure_res.data else None
        }
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@monitoring_bp.route("/api/monitoring/history", methods=["GET"])
def api_history():
    """Returns past 100 system performance logs."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("monitoring_logs").select("*").order("created_at", desc=True).limit(100).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@monitoring_bp.route("/api/failover/history", methods=["GET"])
def api_failover_history():
    """Returns the last 20 failover records."""
    supabase = get_supabase_client()
    try:
        res = supabase.table("failover_events").select("*").order("triggered_at", desc=True).limit(20).execute()
        return jsonify({"success": True, "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "FETCH_FAILED", "message": str(e)}}), 500

@monitoring_bp.route("/api/failover/manual", methods=["POST"])
def api_manual_failover():
    """Admin-triggered manual disaster recovery failover."""
    # Enforce admin credentials check
    from flask_login import current_user
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Admin privileges required."}}), 403
        
    data = request.get_json() or {}
    confirmation = data.get("confirmation", "").strip()
    target_server = data.get("target", "").strip().lower() # aws or azure
    
    if confirmation != "FAILOVER":
        return jsonify({"success": False, "error": {"code": "CONFIRMATION_FAILED", "message": "Please write 'FAILOVER' to confirm manual override."}}), 400
        
    if target_server not in ["aws", "azure"]:
        return jsonify({"success": False, "error": {"code": "INVALID_TARGET", "message": "Target server must be 'aws' or 'azure'."}}), 400
        
    current_active = os.environ.get("PRIMARY_CLOUD", "aws").lower()
    if current_active == target_server:
        return jsonify({"success": False, "error": {"code": "ALREADY_ACTIVE", "message": f"{target_server.upper()} is already the active server."}}), 400
        
    start_time = time.time()
    
    # 1. Update proxy router server
    PROXY_URL = f"http://127.0.0.1:{os.environ.get('PROXY_PORT', '8080')}"
    import requests
    try:
        requests.post(f"{PROXY_URL}/proxy/update-routing", json={"active": target_server}, timeout=3)
        proxy_ok = True
    except Exception as e:
        proxy_ok = False
        print(f"[FAILOVER ERROR] Failed to signal proxy routing: {e}")
        
    rto = time.time() - start_time
    
    # Update current node config env
    os.environ["PRIMARY_CLOUD"] = target_server
    
    # 2. Write to logs
    conn = get_db_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO failover_events (from_server, to_server, trigger_reason, rto_seconds, triggered_at, resolved_at, triggered_by)
                VALUES (%s, %s, %s, %s, NOW(), NOW(), %s)
                """,
                (
                    current_active,
                    target_server,
                    f"Manual admin trigger | Proxy update={'Success' if proxy_ok else 'Failed'}",
                    Decimal(str(rto)),
                    current_user.full_name
                )
            )
            
            # Send notification alert
            cur.execute("SELECT id FROM users WHERE is_admin = True")
            admins = cur.fetchall()
            for admin in admins:
                cur.execute(
                    """
                    INSERT INTO notifications (user_id, title, message, type, is_read)
                    VALUES (%s, 'Manual Failover Triggered', %s, 'security', False)
                    """,
                    (admin["id"], f"Manual override failover from {current_active.upper()} to {target_server.upper()} completed in {rto:.3f}s by {current_user.full_name}.")
                )
        return jsonify({"success": True, "data": {"from": current_active, "to": target_server, "rto_seconds": rto}})
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "DB_WRITE_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()
