import sys
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from dotenv import load_dotenv
from utils.supabase_client import get_db_connection
from utils.auth_helpers import hash_password
from utils.account_gen import generate_account_number
from utils.transaction_engine import categorise_transaction, generate_transaction_ref

load_dotenv()

# Helper to execute clean deletes
TABLES_TO_CLEAN = [
    "spending_budgets", "savings_goals", "audit_logs", "failover_events", 
    "monitoring_logs", "support_tickets", "notifications", "standing_orders", 
    "cards", "beneficiaries", "transactions", "accounts", "users"
]

def clean_database(cur):
    """Truncates tables in dependency order for a fresh seed run."""
    print("Clearing existing data...")
    for table in TABLES_TO_CLEAN:
        try:
            cur.execute(f"TRUNCATE TABLE {table} CASCADE;")
        except Exception as e:
            print(f"Error cleaning {table}: {e}")
            # Fallback if CASCADE is not fully permitted
            try:
                cur.execute(f"DELETE FROM {table};")
            except Exception:
                pass

def create_users(cur):
    """Inserts mock user records into Supabase and returns a dict mapping email to user dict."""
    users_data = [
        {
            "full_name": "System Administrator",
            "email": "admin@novapay.co.uk",
            "phone": "+447000000000",
            "password_hash": hash_password("Admin@Nova2025!"),
            "date_of_birth": "1990-01-01",
            "is_admin": True,
            "is_verified": True,
            "kyc_status": "approved"
        },
        {
            "full_name": "Sarah Johnson",
            "email": "sarah@example.com",
            "phone": "+447111222333",
            "password_hash": hash_password("Demo@2025!"),
            "date_of_birth": "1988-04-12",
            "is_admin": False,
            "is_verified": True,
            "kyc_status": "approved"
        },
        {
            "full_name": "James Wilson",
            "email": "james@example.com",
            "phone": "+447222333444",
            "password_hash": hash_password("Demo@2025!"),
            "date_of_birth": "1995-09-24",
            "is_admin": False,
            "is_verified": True,
            "kyc_status": "approved"
        },
        {
            "full_name": "Priya Patel",
            "email": "priya@example.com",
            "phone": "+447333444555",
            "password_hash": hash_password("Demo@2025!"),
            "date_of_birth": "1991-11-03",
            "is_admin": False,
            "is_verified": True,
            "kyc_status": "approved"
        },
        {
            "full_name": "Marcus Brown",
            "email": "marcus@example.com",
            "phone": "+447444555666",
            "password_hash": hash_password("Demo@2025!"),
            "date_of_birth": "2000-06-18",
            "is_admin": False,
            "is_verified": True,
            "kyc_status": "approved"
        }
    ]
    
    users_by_email = {}
    print("Seeding users...")
    for u in users_data:
        cur.execute(
            """
            INSERT INTO users (full_name, email, phone, password_hash, date_of_birth, address, city, postcode, country, is_admin, is_verified, kyc_status)
            VALUES (%s, %s, %s, %s, %s, '12 Bank Lane', 'London', 'EC1A 1BB', 'United Kingdom', %s, %s, %s)
            RETURNING id, full_name, email;
            """,
            (
                u["full_name"], u["email"], u["phone"], u["password_hash"], 
                u["date_of_birth"], u["is_admin"], u["is_verified"], u["kyc_status"]
            )
        )
        res = cur.fetchone()
        users_by_email[u["email"]] = res
        
    return users_by_email

def create_accounts(cur, users):
    """Creates banking accounts for seeded users."""
    print("Seeding accounts...")
    accounts_by_user = {}
    
    # 1. Sarah Johnson (Current + Savings)
    sarah_id = users["sarah@example.com"]["id"]
    sarah_accs = []
    
    # Current
    cur.execute(
        """
        INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, overdraft_limit, nickname)
        VALUES (%s, '55224411', '20-45-91', 'current', 'GBP', 5420.50, 6420.50, 1000.00, 'Main Checking')
        RETURNING id, account_number, balance;
        """,
        (sarah_id,)
    )
    sarah_accs.append(cur.fetchone())
    # Savings
    cur.execute(
        """
        INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, nickname)
        VALUES (%s, '99887766', '20-45-91', 'savings', 'GBP', 12500.00, 12500.00, 'Emergency Fund')
        RETURNING id, account_number, balance;
        """,
        (sarah_id,)
    )
    sarah_accs.append(cur.fetchone())
    accounts_by_user[sarah_id] = sarah_accs

    # 2. James Wilson (Current only)
    james_id = users["james@example.com"]["id"]
    cur.execute(
        """
        INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, overdraft_limit, nickname)
        VALUES (%s, '33445566', '20-45-91', 'current', 'GBP', 1250.75, 1750.75, 500.00, 'Primary Current')
        RETURNING id, account_number, balance;
        """,
        (james_id,)
    )
    accounts_by_user[james_id] = [cur.fetchone()]

    # 3. Priya Patel (Current + ISA)
    priya_id = users["priya@example.com"]["id"]
    priya_accs = []
    # Current
    cur.execute(
        """
        INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, nickname)
        VALUES (%s, '77889900', '20-45-91', 'current', 'GBP', 3200.40, 3200.40, 'Checking Wallet')
        RETURNING id, account_number, balance;
        """,
        (priya_id,)
    )
    priya_accs.append(cur.fetchone())
    # ISA
    cur.execute(
        """
        INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, nickname)
        VALUES (%s, '11223344', '20-45-91', 'isa', 'GBP', 18000.00, 18000.00, 'Cash ISA Savings')
        RETURNING id, account_number, balance;
        """,
        (priya_id,)
    )
    priya_accs.append(cur.fetchone())
    accounts_by_user[priya_id] = priya_accs

    # 4. Marcus Brown (Current)
    marcus_id = users["marcus@example.com"]["id"]
    cur.execute(
        """
        INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, nickname)
        VALUES (%s, '44556677', '20-45-91', 'current', 'GBP', 1850.20, 1850.20, 'Pocket Account')
        RETURNING id, account_number, balance;
        """,
        (marcus_id,)
    )
    accounts_by_user[marcus_id] = [cur.fetchone()]
    
    return accounts_by_user

def create_beneficiaries(cur, users):
    """Inserts mock payee records."""
    print("Seeding beneficiaries...")
    beneficiaries_by_user = {}
    
    payees_data = [
        {"nickname": "Landlord", "full_name": "London Properties Ltd", "account_number": "12348899", "sort_code": "40-11-22", "bank_name": "Barclays"},
        {"nickname": "Netflix Subscription", "full_name": "Netflix UK", "account_number": "99221100", "sort_code": "20-00-01", "bank_name": "HSBC"},
        {"nickname": "Gym Group", "full_name": "The Gym Group Plc", "account_number": "33449911", "sort_code": "09-01-24", "bank_name": "Lloyds"},
        {"nickname": "Starbucks Corp", "full_name": "Starbucks UK", "account_number": "88775533", "sort_code": "12-34-56", "bank_name": "Monzo"},
        {"nickname": "Tesco Superstore", "full_name": "Tesco Stores Ltd", "account_number": "44332211", "sort_code": "11-22-33", "bank_name": "NatWest"}
    ]
    
    for email, u in users.items():
        if u["email"] == "admin@novapay.co.uk":
            continue
        beneficiaries_by_user[u["id"]] = []
        # Add a couple of payees
        selected = random.sample(payees_data, 3)
        for payee in selected:
            cur.execute(
                """
                INSERT INTO beneficiaries (user_id, nickname, full_name, account_number, sort_code, bank_name, reference, is_trusted)
                VALUES (%s, %s, %s, %s, %s, %s, 'Bill Payment', %s)
                RETURNING id, nickname, account_number, sort_code;
                """,
                (u["id"], payee["nickname"], payee["full_name"], payee["account_number"], payee["sort_code"], payee["bank_name"], random.choice([True, False]))
            )
            beneficiaries_by_user[u["id"]].append(cur.fetchone())
            
    return beneficiaries_by_user

def seed_transactions_and_cards(cur, users, accounts):
    """Generates 50+ transactions per user spanning the last 6 months and binds payment cards."""
    print("Seeding transaction ledgers and cards...")
    
    merchants = [
        {"name": "Tesco Store", "category": "shopping"},
        {"name": "Amazon UK", "category": "shopping"},
        {"name": "Netflix", "category": "entertainment"},
        {"name": "Spotify Premium", "category": "entertainment"},
        {"name": "TfL Oyster", "category": "transport"},
        {"name": "Deliveroo Coffee", "category": "eating_out"},
        {"name": "Starbucks Coffee", "category": "eating_out"},
        {"name": "British Gas", "category": "bills"},
        {"name": "BT Broadband", "category": "bills"},
        {"name": "Gym Group Fee", "category": "health"},
        {"name": "Airbnb Booking", "category": "travel"},
        {"name": "Uber Trip", "category": "transport"},
        {"name": "Boots Pharmacy", "category": "health"},
        {"name": "Sainsburys", "category": "shopping"}
    ]
    
    for user_email, u in users.items():
        if user_email == "admin@novapay.co.uk":
            continue
            
        user_id = u["id"]
        user_accs = accounts[user_id]
        
        # 1. Bind credit/debit card to main current account
        current_acc = user_accs[0]
        masked = f"4751 28** **** {random.randint(1000,9999)}"
        cur.execute(
            """
            INSERT INTO cards (account_id, masked_number, cardholder_name, expiry_month, expiry_year, card_type, card_network, is_active, is_frozen)
            VALUES (%s, %s, %s, %s, %s, 'debit', 'Visa', True, False);
            """,
            (current_acc["id"], masked, u["full_name"].upper(), 12, 2030)
        )
        
        if len(user_accs) > 1:
            # Bind a savings ISA card if they have one
            savings_acc = user_accs[1]
            masked_sav = f"4751 29** **** {random.randint(1000,9999)}"
            cur.execute(
                """
                INSERT INTO cards (account_id, masked_number, cardholder_name, expiry_month, expiry_year, card_type, card_network, is_active, is_frozen)
                VALUES (%s, %s, %s, %s, %s, 'savings', 'Visa', True, False);
                """,
                (savings_acc["id"], masked_sav, u["full_name"].upper(), 6, 2031)
            )

        # 2. Generate 55 transactions spread across 180 days
        balance_tracker = Decimal(str(current_acc["balance"]))
        start_date = datetime.now(timezone.utc) - timedelta(days=180)
        
        # We write them backwards from 180 days ago to today
        # To make it realistic, we start with a large Salary credit!
        for i in range(55):
            txn_date = start_date + timedelta(days=i * 3) + timedelta(hours=random.randint(1,12))
            
            # Every 30 days (10 iterations roughly), we credit Salary
            if i % 10 == 0:
                amount = Decimal(random.randint(2000, 3500))
                desc = "BACS Payroll Employer Salary"
                category = "salary"
                balance_tracker += amount
                cur.execute(
                    """
                    INSERT INTO transactions (from_account_id, to_account_id, transaction_ref, transaction_type, amount, currency, description, reference, category, status, balance_after, created_at)
                    VALUES (NULL, %s, %s, 'deposit', %s, 'GBP', %s, 'Payroll Payment', %s, 'completed', %s, %s);
                    """,
                    (current_acc["id"], generate_transaction_ref(), amount, desc, category, balance_tracker, txn_date)
                )
            else:
                # Debit transaction
                merchant = random.choice(merchants)
                amount = Decimal(round(random.uniform(5.50, 150.00), 2))
                desc = merchant["name"]
                category = merchant["category"]
                balance_tracker -= amount
                cur.execute(
                    """
                    INSERT INTO transactions (from_account_id, to_account_id, transaction_ref, transaction_type, amount, currency, description, reference, category, status, balance_after, created_at)
                    VALUES (%s, NULL, %s, 'debit', %s, 'GBP', %s, 'Contactless payment', %s, 'completed', %s, %s);
                    """,
                    (current_acc["id"], generate_transaction_ref(), amount, desc, category, balance_tracker, txn_date)
                )

        # Update final balance in accounts table to match the end tracker
        cur.execute(
            "UPDATE accounts SET balance = %s, available_balance = %s WHERE id = %s",
            (balance_tracker, balance_tracker, current_acc["id"])
        )

def seed_extras(cur, users, accounts, beneficiaries):
    """Seeds standing orders, notifications, tickets, savings goals, and budgets."""
    print("Seeding extra services (budgets, goals, tickets, standing orders)...")
    
    for email, u in users.items():
        if email == "admin@novapay.co.uk":
            continue
            
        user_id = u["id"]
        user_accs = accounts[user_id]
        current_acc = user_accs[0]
        payees = beneficiaries[user_id]
        
        # 1. Standing Orders (Rent/Bills)
        if payees:
            payee = payees[0]
            cur.execute(
                """
                INSERT INTO standing_orders (from_account_id, beneficiary_id, amount, reference, frequency, start_date, next_payment, is_active)
                VALUES (%s, %s, 500.00, 'Rent payment', 'monthly', '2026-01-01', '2026-07-01', True);
                """,
                (current_acc["id"], payee["id"])
            )
            
        # 2. Savings Goals
        cur.execute(
            """
            INSERT INTO savings_goals (account_id, name, target_amount, current_amount, target_date, icon, is_completed)
            VALUES (%s, 'Summer Holiday 2026', 1500.00, 300.00, '2026-08-01', '✈️', False);
            """,
            (current_acc["id"],)
        )
        
        # 3. Budgets
        cur.execute(
            """
            INSERT INTO spending_budgets (user_id, category, limit_amount, month)
            VALUES (%s, 'shopping', 300.00, '2026-06'),
                   (%s, 'eating_out', 150.00, '2026-06')
            ON CONFLICT DO NOTHING;
            """,
            (user_id, user_id)
        )

        # 4. Support Tickets
        ref = f"TKT-{random.randint(10000, 99999)}"
        cur.execute(
            """
            INSERT INTO support_tickets (user_id, ticket_ref, subject, description, category, status, priority)
            VALUES (%s, %s, 'Card Contactless Issue', 'My contactless payments fail at grocery stores.', 'cards', 'open', 'normal');
            """,
            (user_id, ref)
        )
        
        # 5. Notifications
        cur.execute(
            """
            INSERT INTO notifications (user_id, title, message, type, is_read)
            VALUES (%s, 'Welcome to NovaPay', 'Welcome to your premium banking interface.', 'system', True),
                   (%s, 'Direct Debit Added', 'New standing order for London Properties set up.', 'account', False);
            """,
            (user_id, user_id)
        )

def main():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Run seed workflow
        clean_database(cur)
        users = create_users(cur)
        accs = create_accounts(cur, users)
        bens = create_beneficiaries(cur, users)
        seed_transactions_and_cards(cur, users, accs)
        seed_extras(cur, users, accs, bens)
        
        conn.commit()
        print("NovaPay successfully seeded with high-fidelity production data!")
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Failed to seed database: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
