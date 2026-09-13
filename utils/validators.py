import re
import html
from datetime import date, datetime
from email_validator import validate_email, EmailNotValidError

def clean_input(text: str) -> str:
    """Escapes HTML entities in input strings to prevent XSS."""
    if not text:
        return ""
    return html.escape(text.strip())

def is_valid_email(email: str) -> bool:
    """Checks if email is RFC compliant and under 255 chars."""
    if not email or len(email) > 255:
        return False
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False

def is_valid_phone(phone: str) -> bool:
    """Validates phone number using E.164 pattern (+447123456789 or 07123456789)."""
    if not phone:
        return False
    # Remove spaces, dashes, and brackets commonly typed in phone numbers
    clean_phone = re.sub(r'[\s\-\(\)]', '', phone.strip())
    # E.164 international format or simple UK phone formats
    pattern = r'^\+?[1-9]\d{1,14}$|^0[1-9]\d{9}$'
    return bool(re.match(pattern, clean_phone))

def is_valid_account_number(acc_num: str) -> bool:
    """Checks if account number is exactly 8 digits."""
    if not acc_num:
        return False
    return bool(re.match(r'^\d{8}$', acc_num.strip()))

def is_valid_sort_code(sort_code: str) -> bool:
    """Checks if sort code is in XX-XX-XX format."""
    if not sort_code:
        return False
    return bool(re.match(r'^\d{2}-\d{2}-\d{2}$', sort_code.strip()))

def is_adult(dob_str: str) -> bool:
    """Verifies that the date of birth corresponds to an adult (18+)."""
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except Exception:
        return False
    
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return age >= 18

def evaluate_password_strength(password: str) -> dict:
    """
    Evaluates password strength. Returns a dict with:
    - is_valid: bool
    - score: int (0 to 4)
    - feedback: list of errors
    """
    feedback = []
    score = 0
    
    if len(password) < 8:
        feedback.append("Password must be at least 8 characters long.")
    else:
        score += 1
        
    if not re.search(r"[A-Z]", password):
        feedback.append("Password must contain at least one uppercase letter.")
    else:
        score += 1
        
    if not re.search(r"[a-z]", password):
        feedback.append("Password must contain at least one lowercase letter.")
    else:
        score += 1
        
    if not re.search(r"\d", password):
        feedback.append("Password must contain at least one digit.")
    else:
        score += 1
        
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        feedback.append("Password must contain at least one special character.")
    else:
        # Give a small boost if we have special chars, but score is capped at 4
        if score < 4:
            score += 1

    # Adjust score mapping for display
    final_score = min(max(score, 0), 4)
    is_valid = len(feedback) == 0 and len(password) >= 8
    
    return {
        "is_valid": is_valid,
        "score": final_score,
        "feedback": feedback
    }
