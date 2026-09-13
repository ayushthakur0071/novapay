import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "novapay-fallback-secret-key-32-chars-at-least")
    
    # Supabase Credentials
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://placeholder.supabase.co")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "placeholder-anon-key")
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    
    # Cookie & Session Safety
    # SECURE is True in production, False for local development HTTP testing
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") != "development"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    WTF_CSRF_ENABLED = True
    
    # Cloud & Remote Host URLs
    AWS_URL = os.environ.get("AWS_URL", "http://localhost:5001")
    AZURE_URL = os.environ.get("AZURE_URL", "http://localhost:5002")
    PRIMARY_CLOUD = os.environ.get("PRIMARY_CLOUD", "aws")
    AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
    AZURE_REGION = os.environ.get("AZURE_REGION", "uk-south")
    
    # DR Thresholds & Timeouts
    FAILOVER_THRESHOLD_MS = int(os.environ.get("FAILOVER_THRESHOLD_MS", "3000"))
    FAILOVER_FAILURE_COUNT = int(os.environ.get("FAILOVER_FAILURE_COUNT", "3"))
    MONITOR_INTERVAL_SECONDS = int(os.environ.get("MONITOR_INTERVAL_SECONDS", "30"))
    HEALTH_CHECK_TIMEOUT = int(os.environ.get("HEALTH_CHECK_TIMEOUT", "10"))
    PROXY_TIMEOUT = int(os.environ.get("PROXY_TIMEOUT", "30"))
    
    # Reverse Proxy Integration
    BEHIND_PROXY = os.environ.get("BEHIND_PROXY", "1").lower() in ("1", "true", "yes")

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() in ("1", "true", "yes")

config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig
}
