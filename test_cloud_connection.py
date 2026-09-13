#!/usr/bin/env python3
"""
NovaPay Multi-Cloud Diagnostic & Pre-Flight Verification Tool
Tests connectivity to AWS, Azure, Supabase DB, and Proxy Balancer.
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

AWS_URL = os.environ.get("AWS_URL", "http://127.0.0.1:5001").rstrip("/")
AZURE_URL = os.environ.get("AZURE_URL", "http://127.0.0.1:5002").rstrip("/")
PROXY_PORT = os.environ.get("PROXY_PORT", "8080")
PROXY_URL = os.environ.get("PROXY_URL", f"http://127.0.0.1:{PROXY_PORT}").rstrip("/")
DATABASE_URL = os.environ.get("DATABASE_URL")
TIMEOUT = int(os.environ.get("HEALTH_CHECK_TIMEOUT", "10"))

def print_header(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN} {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")

def test_node(cloud_name, url):
    print(f"\nTesting {BOLD}{cloud_name.upper()}{RESET} Cloud Node at: {url}")
    target_endpoint = f"{url}/health"
    start = time.time()
    try:
        resp = requests.get(target_endpoint, timeout=TIMEOUT, headers={"User-Agent": "NovaPay-Diagnostic/1.0"})
        latency_ms = round((time.time() - start) * 1000, 2)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  [{GREEN}PASS{RESET}] HTTP {resp.status_code} OK (Latency: {BOLD}{latency_ms}ms{RESET})")
            print(f"         Status:        {data.get('status')}")
            print(f"         Server:        {data.get('server')}")
            print(f"         Database:      {data.get('db')}")
            print(f"         DB Latency:    {data.get('db_latency_ms')}ms")
            print(f"         CPU Usage:     {data.get('cpu_usage')}%")
            print(f"         Memory Usage:  {data.get('memory_usage')}%")
            print(f"         Node Uptime:   {data.get('uptime')}s")
            return True, latency_ms
        else:
            print(f"  [{RED}FAIL{RESET}] HTTP {resp.status_code} returned by {target_endpoint}")
            return False, latency_ms
    except requests.exceptions.Timeout:
        print(f"  [{RED}FAIL{RESET}] Connection to {target_endpoint} timed out after {TIMEOUT}s")
        return False, None
    except requests.exceptions.SSLError as ssl_err:
        print(f"  [{RED}FAIL{RESET}] SSL Certificate Verification Failed: {ssl_err}")
        return False, None
    except Exception as e:
        print(f"  [{RED}FAIL{RESET}] Connection error: {e}")
        return False, None

def test_proxy():
    print(f"\nTesting {BOLD}NovaPay Proxy Balancer{RESET} at: {PROXY_URL}")
    try:
        resp = requests.get(f"{PROXY_URL}/proxy/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  [{GREEN}PASS{RESET}] Proxy Status OK")
            print(f"         Active Cloud:  {BOLD}{data.get('active_cloud', '').upper()}{RESET}")
            print(f"         Target URL:    {data.get('target_url')}")
            
            # Check upstream health via proxy
            health_resp = requests.get(f"{PROXY_URL}/proxy/health", timeout=10)
            health_data = health_resp.json()
            upstream_status = f"{GREEN}Connected{RESET}" if health_data.get("upstream_connected") else f"{RED}Disconnected{RESET}"
            print(f"         Upstream:      {upstream_status} ({health_data.get('upstream_latency_ms')}ms)")
            return True
        else:
            print(f"  [{RED}FAIL{RESET}] Proxy returned status {resp.status_code}")
            return False
    except Exception as e:
        print(f"  [{YELLOW}WARN{RESET}] Proxy not running or unreachable ({e})")
        return False

def test_database():
    print(f"\nTesting {BOLD}Direct Supabase PostgreSQL Connection{RESET}...")
    if not DATABASE_URL:
        print(f"  [{RED}FAIL{RESET}] DATABASE_URL is not set in environment.")
        return False
    
    # Mask password for display
    try:
        from urllib.parse import urlparse
        parsed = urlparse(DATABASE_URL)
        masked_host = parsed.hostname
        masked_user = parsed.username
        print(f"  Target Host: {masked_host} (User: {masked_user})")
    except Exception:
        pass

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        db_url = DATABASE_URL
        if "supabase.co" in db_url and "sslmode" not in db_url:
            db_url += ("&sslmode=require" if "?" in db_url else "?sslmode=require")
            
        t0 = time.time()
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor, connect_timeout=10)
        conn_time = round((time.time() - t0) * 1000, 2)
        
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as user_count FROM users;")
            users = cur.fetchone()["user_count"]
            cur.execute("SELECT COUNT(*) as log_count FROM monitoring_logs;")
            logs = cur.fetchone()["log_count"]
            
        conn.close()
        print(f"  [{GREEN}PASS{RESET}] DB Connected successfully (Handshake: {BOLD}{conn_time}ms{RESET})")
        print(f"         Total Users:     {users}")
        print(f"         Telemetry Logs:  {logs}")
        return True
    except Exception as e:
        print(f"  [{YELLOW}WARN{RESET}] DB connection check: {e}")
        return False

def main():
    print_header("NovaPay Multi-Cloud Diagnostic & Pre-Flight Tool")
    print(f"Current Configuration:")
    print(f"  AWS_URL:        {AWS_URL}")
    print(f"  AZURE_URL:      {AZURE_URL}")
    print(f"  PROXY_URL:      {PROXY_URL}")
    
    aws_ok, aws_lat = test_node("AWS", AWS_URL)
    azure_ok, azure_lat = test_node("Azure", AZURE_URL)
    proxy_ok = test_proxy()
    db_ok = test_database()
    
    print_header("Diagnostic Summary")
    print(f"  AWS Node:      [{GREEN}UP{RESET} - {aws_lat}ms]" if aws_ok else f"  AWS Node:      [{RED}DOWN / UNREACHABLE{RESET}]")
    print(f"  Azure Node:    [{GREEN}UP{RESET} - {azure_lat}ms]" if azure_ok else f"  Azure Node:    [{RED}DOWN / UNREACHABLE{RESET}]")
    print(f"  Proxy Balancer:[{GREEN}RUNNING{RESET}]" if proxy_ok else f"  Proxy Balancer:[{YELLOW}NOT RUNNING{RESET}]")
    print(f"  Postgres DB:   [{GREEN}CONNECTED{RESET}]" if db_ok else f"  Postgres DB:   [{YELLOW}CHECK NETWORK / SANDBOX{RESET}]")
    
    if aws_ok and azure_ok:
        print(f"\n{GREEN}{BOLD}Ready for Real-Time Multi-Cloud Traffic!{RESET}")
    else:
        print(f"\n{YELLOW}{BOLD}Next step:{RESET} Deploy or start the cloud nodes using deploy scripts, or update AWS_URL / AZURE_URL in .env.")

if __name__ == "__main__":
    main()
