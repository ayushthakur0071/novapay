from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import bleach

from extensions import limiter
from utils.supabase_client import get_supabase_client, get_db_connection
from utils.encryption import encrypt_data
from utils.auth_helpers import hash_password, verify_password, generate_reset_token
from utils.validators import clean_input, is_valid_email, is_valid_phone, is_adult, evaluate_password_strength
from utils.account_gen import generate_account_number
from utils.notifications_helper import create_notification, dispatch_mock_email
from models import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("auth/login.html")

@auth_bp.route("/register", methods=["GET"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("auth/register.html")

@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    if current_user.is_authenticated:
        # Log audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'logout', 'users', %s)",
                    (current_user.id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        logout_user()
    return redirect(url_for("auth.login"))

@auth_bp.route("/forgot-password", methods=["GET"])
def forgot_password_page():
    return render_template("auth/login.html")  # login template contains the toggle for forgot-password

@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    
    # 1. Input Sanitization
    full_name = clean_input(data.get("full_name", ""))
    email = data.get("email", "").strip().lower()
    import re
    phone = re.sub(r'[\s\-\(\)]', '', data.get("phone", "").strip())
    dob_str = data.get("date_of_birth", "").strip()
    address = clean_input(data.get("address", ""))
    city = clean_input(data.get("city", ""))
    postcode = clean_input(data.get("postcode", ""))
    password = data.get("password", "")
    kyc_document_type = clean_input(data.get("kyc_document_type", "Passport"))
    kyc_document_file = data.get("kyc_document_file", "")
    
    # 2. Validations
    if not (full_name and email and phone and dob_str and password):
        return jsonify({"success": False, "error": {"code": "MISSING_FIELDS", "message": "All fields are required."}}), 400
        
    if not is_valid_email(email):
        return jsonify({"success": False, "error": {"code": "INVALID_EMAIL", "message": "Invalid email address format."}}), 400
        
    if not is_valid_phone(phone):
        return jsonify({"success": False, "error": {"code": "INVALID_PHONE", "message": "Invalid UK phone number format."}}), 400
        
    if not is_adult(dob_str):
        return jsonify({"success": False, "error": {"code": "UNDERAGE", "message": "You must be at least 18 years old to open an account."}}), 400
        
    pwd_eval = evaluate_password_strength(password)
    if not pwd_eval["is_valid"]:
        return jsonify({"success": False, "error": {"code": "WEAK_PASSWORD", "message": pwd_eval["feedback"][0]}}), 400
        
    supabase = get_supabase_client()
    
    # Check uniqueness
    try:
        email_check = supabase.table("users").select("id").eq("email", email).execute()
        if email_check.data:
            return jsonify({"success": False, "error": {"code": "EMAIL_TAKEN", "message": "Email is already registered."}}), 400
            
        phone_check = supabase.table("users").select("id").eq("phone", phone).execute()
        if phone_check.data:
            return jsonify({"success": False, "error": {"code": "PHONE_TAKEN", "message": "Phone number is already registered."}}), 400
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "DB_ERROR", "message": "Database error checking email/phone unique state."}}), 500

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # 3. Insert User Record
        pw_hash = hash_password(password)
        cur.execute(
            """
            INSERT INTO users (full_name, email, phone, password_hash, date_of_birth, address, city, postcode, country, is_active, is_admin, kyc_status, kyc_document_type, kyc_document_file)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'United Kingdom', True, False, 'pending', %s, %s)
            RETURNING id;
            """,
            (full_name, email, phone, pw_hash, dob_str, address, city, postcode, kyc_document_type, kyc_document_file)
        )
        user_id = cur.fetchone()["id"]
        
        # 4. Create Current Account (Initial Balance: £0.00)
        curr_acc_num = generate_account_number()
        cur.execute(
            """
            INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, nickname)
            VALUES (%s, %s, '20-45-91', 'current', 'GBP', 0.00, 0.00, 'Main Checking')
            RETURNING id;
            """,
            (user_id, curr_acc_num)
        )
        curr_acc_id = cur.fetchone()["id"]
        
        # 5. Create Savings Account (Initial Balance: £0.00)
        sav_acc_num = generate_account_number()
        cur.execute(
            """
            INSERT INTO accounts (user_id, account_number, sort_code, account_type, currency, balance, available_balance, nickname)
            VALUES (%s, %s, '20-45-91', 'savings', 'GBP', 0.00, 0.00, 'Primary Savings')
            RETURNING id;
            """,
            (user_id, sav_acc_num)
        )
        sav_acc_id = cur.fetchone()["id"]
        
        # 6. Issue Virtual Debit Card for Current Account
        import random
        raw_card_num = f"475128{random.randint(10, 99)}{random.randint(10000000, 99999999)}"
        raw_cvv = f"{random.randint(100, 999)}"
        masked_card = f"4751 28{raw_card_num[6:8]} **** {raw_card_num[-4:]}"
        cur.execute(
            """
            INSERT INTO cards (account_id, masked_number, cardholder_name, expiry_month, expiry_year, card_type, card_network, is_active, is_frozen, encrypted_card_number, encrypted_cvv)
            VALUES (%s, %s, %s, 12, 2030, 'debit', 'Visa', True, False, %s, %s);
            """,
            (curr_acc_id, masked_card, full_name.upper(), encrypt_data(raw_card_num), encrypt_data(raw_cvv))
        )
        
        # 7. Write Welcome Notification
        cur.execute(
            """
            INSERT INTO notifications (user_id, title, message, type, is_read)
            VALUES (%s, 'Welcome to NovaPay!', 'Your Checking and Savings accounts are open and active with £0.00 initial balance.', 'system', False);
            """,
            (user_id,)
        )
        
        # 8. Log registration audit
        cur.execute(
            """
            INSERT INTO audit_logs (user_id, action, resource, resource_id, ip_address)
            VALUES (%s, 'register', 'users', %s, %s);
            """,
            (user_id, user_id, request.remote_addr)
        )
        
        conn.commit()
        
        # Do not auto-login. Account is pending KYC.
        return jsonify({"success": True, "kyc_pending": True, "data": {"user_id": user_id, "email": email}})
    except Exception as e:
        conn.rollback()
        print(f"Registration insert failed: {e}")
        return jsonify({"success": False, "error": {"code": "REGISTRATION_FAILED", "message": str(e)}}), 500
    finally:
        conn.close()

@auth_bp.route("/api/auth/login", methods=["POST"])
@limiter.limit("5 per minute")
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    remember = bool(data.get("remember", False))
    
    if not (email and password):
        return jsonify({"success": False, "error": {"code": "MISSING_CREDENTIALS", "message": "Email and password are required."}}), 400
        
    supabase = get_supabase_client()
    
    try:
        res = supabase.table("users").select("*").eq("email", email).execute()
        if not res.data:
            return jsonify({"success": False, "error": {"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."}}), 401
            
        user_data = res.data[0]
        user = User(user_data)
        
        # Check KYC Verification status (skip for admins)
        if not user.is_admin:
            if user.kyc_status == "pending":
                return jsonify({"success": False, "error": {"code": "KYC_PENDING", "message": "Your registration is pending document verification by compliance."}}), 403
            elif user.kyc_status == "hold":
                return jsonify({"success": False, "error": {"code": "KYC_HOLD", "message": "Your registration is on hold. Please contact compliance support."}}), 403
            elif user.kyc_status == "declined":
                return jsonify({"success": False, "error": {"code": "KYC_DECLINED", "message": "Your registration request has been declined."}}), 403
        
        # Check brute force lockout status
        if user.is_locked:
            locked_until_dt = user.locked_until
            from dateutil import parser
            if isinstance(locked_until_dt, str):
                locked_until_dt = parser.parse(locked_until_dt)
            minutes_left = max(1, int((locked_until_dt - datetime.now(timezone.utc)).total_seconds() / 60))
            return jsonify({
                "success": False,
                "error": {
                    "code": "ACCOUNT_LOCKED",
                    "message": f"Account locked due to consecutive failed attempts. Try again in {minutes_left} minutes."
                }
            }), 403
            
        if not verify_password(password, user.password_hash):
            # Increment failed attempts
            new_attempts = user.failed_attempts + 1
            update_data = {"failed_attempts": new_attempts}
            
            if new_attempts >= 5:
                # Set 15 minutes lockout
                lock_time_dt = datetime.now(timezone.utc) + timedelta(minutes=15)
                lock_time = lock_time_dt.isoformat()
                update_data["locked_until"] = lock_time
                print(f"[SECURITY ALERT] Email {email} locked out until {lock_time}")
                
                # Send security email
                try:
                    subject = "Security Alert: Account Temporarily Locked"
                    body = f"Hello {user.full_name},\n\nYour NovaPay account has been temporarily locked for 15 minutes due to 5 consecutive failed login attempts from IP address {request.remote_addr}.\n\nIf you did not request this, please contact NovaPay support immediately to secure your account."
                    dispatch_mock_email(user.email, subject, body)
                except Exception as ex:
                    print(f"Failed to dispatch lockout email: {ex}")
                
            supabase.table("users").update(update_data).eq("id", user.id).execute()
            
            # Log failure audit
            conn = get_db_connection()
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'login_failed', 'users', %s)",
                        (user.id, request.remote_addr)
                    )
            except Exception:
                pass
            finally:
                conn.close()
                
            return jsonify({"success": False, "error": {"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."}}), 401
            
        # Success! Clear attempts, update last login
        supabase.table("users").update({
            "failed_attempts": 0,
            "locked_until": None,
            "last_login": datetime.now(timezone.utc).isoformat()
        }).eq("id", user.id).execute()
        
        # Log successful login audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'login_success', 'users', %s)",
                    (user.id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        if user.mfa_enabled:
            session['pending_mfa_user_id'] = str(user.id)
            session['pending_mfa_remember'] = remember
            return jsonify({"success": True, "mfa_required": True})
            
        login_user(user, remember=remember)
        
        # Send login security alert email
        try:
            subject = "Security Alert: New Account Login"
            body = f"Hello {user.full_name},\n\nWe detected a successful login to your NovaPay account on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} from IP address {request.remote_addr}.\n\nIf this was you, no action is required. If you suspect unauthorized access, please lock your account or contact support immediately."
            dispatch_mock_email(user.email, subject, body)
        except Exception as ex:
            print(f"Failed to dispatch login alert: {ex}")
            
        return jsonify({"success": True, "mfa_required": False, "data": {"user_id": user.id, "email": user.email, "full_name": user.full_name}})
        
    except Exception as e:
        print(f"Login failed: {e}")
        return jsonify({"success": False, "error": {"code": "LOGIN_ERROR", "message": "An error occurred during authentication."}}), 500

@auth_bp.route("/api/auth/me", methods=["GET"])
@login_required
def api_me():
    return jsonify({
        "success": True,
        "data": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "phone": current_user.phone,
            "is_admin": current_user.is_admin,
            "is_verified": current_user.is_verified,
            "kyc_status": current_user.kyc_status,
            "last_login": current_user.last_login
        }
    })

@auth_bp.route("/api/auth/check-email", methods=["GET"])
def api_check_email():
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"success": False, "error": {"code": "INVALID_EMAIL", "message": "Email is required."}}), 400
        
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("id").eq("email", email).execute()
        return jsonify({"success": True, "available": len(res.data) == 0})
    except Exception:
        return jsonify({"success": True, "available": True})

@auth_bp.route("/mfa-verify", methods=["GET"])
def mfa_verify_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if not session.get('pending_mfa_user_id'):
        return redirect(url_for("auth.login"))
    return render_template("auth/mfa_verify.html")

@auth_bp.route("/api/auth/mfa-verify", methods=["POST"])
@limiter.limit("5 per minute")
def api_mfa_verify():
    if current_user.is_authenticated:
        return jsonify({"success": False, "error": {"code": "ALREADY_LOGGED_IN", "message": "Already authenticated."}}), 400
        
    pending_user_id = session.get('pending_mfa_user_id')
    if not pending_user_id:
        return jsonify({"success": False, "error": {"code": "SESSION_EXPIRED", "message": "Session expired. Please log in again."}}), 401
        
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "error": {"code": "MISSING_CODE", "message": "Verification code is required."}}), 400
        
    supabase = get_supabase_client()
    try:
        res = supabase.table("users").select("*").eq("id", pending_user_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": {"code": "USER_NOT_FOUND", "message": "User profile not found."}}), 404
            
        user_data = res.data[0]
        user = User(user_data)
        
        # Check lockout
        if user.is_locked:
            locked_until_dt = user.locked_until
            from dateutil import parser
            if isinstance(locked_until_dt, str):
                locked_until_dt = parser.parse(locked_until_dt)
            minutes_left = max(1, int((locked_until_dt - datetime.now(timezone.utc)).total_seconds() / 60))
            return jsonify({
                "success": False,
                "error": {
                    "code": "ACCOUNT_LOCKED",
                    "message": f"Account locked due to consecutive failed attempts. Try again in {minutes_left} minutes."
                }
            }), 403
            
        import pyotp
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(code):
            # Increment failed attempts
            new_attempts = user.failed_attempts + 1
            update_data = {"failed_attempts": new_attempts}
            
            if new_attempts >= 5:
                lock_time = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
                update_data["locked_until"] = lock_time
                print(f"[SECURITY ALERT] User ID {user.id} locked out due to MFA failures until {lock_time}")
                
            supabase.table("users").update(update_data).eq("id", user.id).execute()
            
            # Log failure audit
            conn = get_db_connection()
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'mfa_failed', 'users', %s)",
                        (user.id, request.remote_addr)
                    )
            except Exception:
                pass
            finally:
                conn.close()
                
            return jsonify({"success": False, "error": {"code": "INVALID_CODE", "message": "Invalid 2FA code. Please check your authenticator app."}}), 401
            
        # Success! Clear attempts, update last login
        supabase.table("users").update({
            "failed_attempts": 0,
            "locked_until": None,
            "last_login": datetime.now(timezone.utc).isoformat()
        }).eq("id", user.id).execute()
        
        # Log successful login audit
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'login_success_mfa', 'users', %s)",
                    (user.id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        remember = session.get('pending_mfa_remember', False)
        # Clear mfa session flags
        session.pop('pending_mfa_user_id', None)
        session.pop('pending_mfa_remember', None)
        
        login_user(user, remember=remember)
        
        # Send login security alert email
        try:
            subject = "Security Alert: New Account Login (2FA Verified)"
            body = f"Hello {user.full_name},\n\nWe detected a successful login to your NovaPay account on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} from IP address {request.remote_addr}.\n\nThis login was secured and verified with 2-Factor Authentication (2FA).\n\nIf you did not execute this login, please contact support immediately."
            dispatch_mock_email(user.email, subject, body)
        except Exception as ex:
            print(f"Failed to dispatch login alert: {ex}")
            
        return jsonify({"success": True, "data": {"user_id": user.id, "email": user.email, "full_name": user.full_name}})
        
    except Exception as e:
        print(f"MFA verification failed: {e}")
        return jsonify({"success": False, "error": {"code": "MFA_ERROR", "message": "An error occurred during verification."}}), 500

@auth_bp.route("/api/auth/mfa-setup", methods=["POST"])
@login_required
def api_mfa_setup():
    import pyotp
    # Check if already enabled
    if current_user.mfa_enabled:
        return jsonify({"success": False, "error": {"code": "MFA_ALREADY_ENABLED", "message": "MFA is already enabled on your account."}}), 400
        
    secret = pyotp.random_base32()
    # Store it in session temporarily
    session['pending_mfa_secret'] = secret
    
    # Generate provisioning URI
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.email, issuer_name="NovaPay")
    
    return jsonify({"success": True, "secret": secret, "uri": uri})

@auth_bp.route("/api/auth/mfa-confirm", methods=["POST"])
@login_required
def api_mfa_confirm():
    pending_secret = session.get('pending_mfa_secret')
    if not pending_secret:
        return jsonify({"success": False, "error": {"code": "NO_SETUP_ACTIVE", "message": "Setup session expired. Please refresh setup."}}), 400
        
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "error": {"code": "MISSING_CODE", "message": "Verification code is required."}}), 400
        
    import pyotp
    totp = pyotp.TOTP(pending_secret)
    if not totp.verify(code):
        return jsonify({"success": False, "error": {"code": "INVALID_CODE", "message": "Invalid code. Please try again."}}), 400
        
    # Save to Supabase
    supabase = get_supabase_client()
    try:
        supabase.table("users").update({
            "mfa_enabled": True,
            "mfa_secret": pending_secret
        }).eq("id", current_user.id).execute()
        
        # Log audit log
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'mfa_enabled', 'users', %s)",
                    (current_user.id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        session.pop('pending_mfa_secret', None)
        return jsonify({"success": True})
    except Exception as e:
        print(f"Failed to confirm MFA: {e}")
        return jsonify({"success": False, "error": {"code": "DB_ERROR", "message": "Failed to save MFA configuration."}}), 500

@auth_bp.route("/api/auth/mfa-disable", methods=["POST"])
@login_required
def api_mfa_disable():
    if not current_user.mfa_enabled:
        return jsonify({"success": False, "error": {"code": "MFA_NOT_ENABLED", "message": "MFA is not enabled."}}), 400
        
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "error": {"code": "MISSING_CODE", "message": "Verification code is required."}}), 400
        
    import pyotp
    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(code):
        return jsonify({"success": False, "error": {"code": "INVALID_CODE", "message": "Invalid code. Disabling failed."}}), 400
        
    # Disable
    supabase = get_supabase_client()
    try:
        supabase.table("users").update({
            "mfa_enabled": False,
            "mfa_secret": None
        }).eq("id", current_user.id).execute()
        
        # Log audit log
        conn = get_db_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_logs (user_id, action, resource, ip_address) VALUES (%s, 'mfa_disabled', 'users', %s)",
                    (current_user.id, request.remote_addr)
                )
        except Exception:
            pass
        finally:
            conn.close()
            
        return jsonify({"success": True})
    except Exception as e:
        print(f"Failed to disable MFA: {e}")
        return jsonify({"success": False, "error": {"code": "DB_ERROR", "message": "Failed to update database."}}), 500
