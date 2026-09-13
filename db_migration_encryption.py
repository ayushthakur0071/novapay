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
            print("Adding encrypted_card_number column to cards...")
            cur.execute("ALTER TABLE cards ADD COLUMN IF NOT EXISTS encrypted_card_number TEXT;")
            
            print("Adding encrypted_cvv column to cards...")
            cur.execute("ALTER TABLE cards ADD COLUMN IF NOT EXISTS encrypted_cvv TEXT;")
            
            print("[SUCCESS] Cards encryption columns added successfully!")
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        return False

if __name__ == "__main__":
    run_migration()
