import os
import psycopg2
from psycopg2.extras import RealDictCursor
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_supabase_client = None

def get_supabase_client() -> Client:
    """Returns a singleton Supabase Client instance for REST queries."""
    global _supabase_client
    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL", "https://placeholder.supabase.co")
        key = os.environ.get("SUPABASE_KEY", "placeholder-anon-key")
        _supabase_client = create_client(url, key)
    return _supabase_client

def get_db_connection():
    """Returns a raw psycopg2 database connection for transaction-safe SQL queries."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is missing.")
    
    # Enable SSL mode if connecting to hosted Supabase PostgreSQL
    if "supabase.co" in db_url and "sslmode" not in db_url:
        if "?" in db_url:
            db_url += "&sslmode=require"
        else:
            db_url += "?sslmode=require"
            
    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    conn.autocommit = False  # Keep transactions manual for safe rollback
    return conn

def execute_query(query, params=None, fetch=True):
    """Utility to execute queries via psycopg2 with automatic connection handling."""
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if fetch:
                return cur.fetchall()
            return None
    except Exception as e:
        print(f"Database query error: {e}")
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()
