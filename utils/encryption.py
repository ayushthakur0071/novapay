import os
from cryptography.fernet import Fernet

_fernet_instance = None

def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
        
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    key = os.environ.get("ENCRYPTION_KEY")
    
    if not key:
        # Generate new key
        new_key = Fernet.generate_key().decode('utf-8')
        os.environ["ENCRYPTION_KEY"] = new_key
        
        # Persist it to .env
        if os.path.exists(env_path):
            with open(env_path, "a") as f:
                f.write(f"\nENCRYPTION_KEY={new_key}\n")
        key = new_key
        
    _fernet_instance = Fernet(key.encode('utf-8'))
    return _fernet_instance

def encrypt_data(plain_text: str) -> str:
    if not plain_text:
        return ""
    f = get_fernet()
    return f.encrypt(plain_text.encode('utf-8')).decode('utf-8')

def decrypt_data(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    f = get_fernet()
    return f.decrypt(cipher_text.encode('utf-8')).decode('utf-8')
