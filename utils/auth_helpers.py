import bcrypt
import secrets

def hash_password(password: str) -> str:
    """Hashes a password with bcrypt using a cost factor of 12."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verifies a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def generate_reset_token() -> str:
    """Generates a secure cryptographically random token for password resets."""
    return secrets.token_urlsafe(32)
