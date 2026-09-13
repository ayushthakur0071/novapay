import os
import requests
from urllib.parse import urlparse
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Load cloud configuration from environment
AWS_URL = os.environ.get("AWS_URL", "http://127.0.0.1:5001").rstrip("/")
AZURE_URL = os.environ.get("AZURE_URL", "http://127.0.0.1:5002").rstrip("/")
PROXY_TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "30"))

# Active routing setup
ROUTING_TABLE = {
    "aws": AWS_URL,
    "azure": AZURE_URL
}
ACTIVE_CLOUD = os.environ.get("PRIMARY_CLOUD", "aws").lower()

# Persistent session pool for outbound cloud requests
http_session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=1)
http_session.mount("http://", adapter)
http_session.mount("https://", adapter)

@app.route("/proxy/status", methods=["GET"])
def proxy_status():
    """Admin/Monitoring endpoint to check proxy's current target state."""
    return jsonify({
        "success": True,
        "active_cloud": ACTIVE_CLOUD,
        "target_url": ROUTING_TABLE.get(ACTIVE_CLOUD),
        "routing_table": ROUTING_TABLE
    })

@app.route("/proxy/health", methods=["GET"])
def proxy_health():
    """Health check endpoint for the proxy and upstream active cloud target."""
    target_base = ROUTING_TABLE.get(ACTIVE_CLOUD, AWS_URL)
    upstream_ok = False
    upstream_latency_ms = None
    import time
    try:
        t0 = time.time()
        res = http_session.get(f"{target_base}/health", timeout=5)
        upstream_latency_ms = round((time.time() - t0) * 1000, 2)
        upstream_ok = (res.status_code == 200)
    except Exception:
        upstream_ok = False

    return jsonify({
        "proxy": "healthy",
        "active_cloud": ACTIVE_CLOUD,
        "target_url": target_base,
        "upstream_connected": upstream_ok,
        "upstream_latency_ms": upstream_latency_ms
    }), (200 if upstream_ok else 503)

@app.route("/proxy/update-routing", methods=["POST"])
def update_routing():
    """Decision engine API to dynamically failover traffic target."""
    global ACTIVE_CLOUD
    data = request.get_json() or {}
    new_target = (data.get("active") or "").lower().strip()
    
    if new_target not in ROUTING_TABLE:
        return jsonify({
            "success": False,
            "error": {"code": "INVALID_TARGET", "message": f"Target '{new_target}' is not in the routing table."}
        }), 400
        
    ACTIVE_CLOUD = new_target
    print(f"[PROXY UPDATE] Active cloud target updated to: {ACTIVE_CLOUD.upper()} ({ROUTING_TABLE[ACTIVE_CLOUD]})")
    return jsonify({
        "success": True,
        "active_cloud": ACTIVE_CLOUD,
        "target_url": ROUTING_TABLE[ACTIVE_CLOUD]
    })

def rewrite_location_header(location_url, target_base, proxy_origin):
    """Rewrites redirect Location URLs pointing to cloud backends back to proxy origin."""
    if not location_url:
        return location_url
    
    # Check if location starts with target_base or any cloud host in routing table
    for cloud_key, cloud_url in ROUTING_TABLE.items():
        if location_url.startswith(cloud_url):
            rewritten = proxy_origin + location_url[len(cloud_url):]
            return rewritten
            
    # Also handle relative URLs (keep them relative)
    return location_url

@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy(path):
    """Forwards incoming request to the currently active cloud server."""
    target_base = ROUTING_TABLE.get(ACTIVE_CLOUD, AWS_URL)
    url = f"{target_base}/{path}" if path else target_base
    
    # Forward headers excluding host-specific headers
    excluded_req_headers = ["host", "content-length"]
    headers = {k: v for k, v in request.headers if k.lower() not in excluded_req_headers}
    
    # Inject standard reverse proxy forwarding headers
    headers["X-Forwarded-Host"] = request.host
    headers["X-Forwarded-Proto"] = request.headers.get("X-Forwarded-Proto", request.scheme)
    headers["X-Forwarded-For"] = request.headers.get("X-Forwarded-For", request.remote_addr)
    headers["X-Real-IP"] = request.remote_addr
    
    # Copy query string parameters
    params = request.args.to_dict()
    proxy_origin = request.host_url.rstrip("/")
    
    try:
        resp = http_session.request(
            method=request.method,
            url=url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            params=params,
            allow_redirects=False,
            timeout=PROXY_TIMEOUT
        )
        
        # Build responses excluding hop-by-hop headers
        excluded_resp_headers = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        resp_headers = []
        for k, v in resp.raw.headers.items():
            k_lower = k.lower()
            if k_lower in excluded_resp_headers:
                continue
            
            # Rewrite Location headers so redirects remain pinned to the proxy
            if k_lower == "location":
                v = rewrite_location_header(v, target_base, proxy_origin)
                
            resp_headers.append((k, v))
        
        return Response(resp.content, resp.status_code, resp_headers)
    except requests.exceptions.RequestException as e:
        print(f"[PROXY ERROR] Failed to connect to active cloud target {ACTIVE_CLOUD.upper()} ({url}): {e}")
        return jsonify({
            "success": False,
            "error": {
                "code": "GATEWAY_TIMEOUT",
                "message": f"Failed to connect to the active banking server ({ACTIVE_CLOUD.upper()}: {target_base}). Failover in progress.",
                "details": str(e)
            }
        }), 504

# Default fallback for root path
@app.route("/", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy_root():
    return proxy("")

if __name__ == "__main__":
    port = int(os.environ.get("PROXY_PORT", "8080"))
    print("==================================================")
    print(" Starting NovaPay Load Balancer Proxy            ")
    print(f" Port:          {port}                           ")
    print(f" Active Target: {ACTIVE_CLOUD.upper()}           ")
    print(f" AWS URL:       {AWS_URL}                        ")
    print(f" Azure URL:     {AZURE_URL}                      ")
    print(f" Proxy URL:     http://localhost:{port}          ")
    print("==================================================")
    app.run(host="0.0.0.0", port=port, debug=False)
