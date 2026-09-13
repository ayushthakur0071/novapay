import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

def run_migration():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[ERROR] DATABASE_URL not found in .env file!")
        return False
        
    print("Connecting to database...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Adding fee column to transactions...")
            cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fee NUMERIC(15,2) DEFAULT 0.00;")
            
            print("Adding transfer_method column to transactions...")
            cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS transfer_method VARCHAR(30) DEFAULT 'IMPS';")
            
            print("[SUCCESS] Transactions table updated successfully with charges and method columns!")
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        return False

if __name__ == "__main__":
    run_migration()
