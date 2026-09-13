import os
from flask import Flask, jsonify, render_template, request, session
from datetime import datetime, timezone
from config import config_by_name
from extensions import login_manager, csrf, limiter, cors
from models import User

def create_app(config_name=None):
    """Flask application factory."""
    if not config_name:
        config_name = os.environ.get("FLASK_ENV", "development")
        
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    
    # Initialize Extensions
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cors.init_app(app)
    
    # Configure ProxyFix for reverse proxy routing (X-Forwarded headers)
    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)
    
    # Session Timeout Warning Context Processor
    @app.context_processor
    def inject_session_life():
        user_name = ""
        from flask_login import current_user
        if current_user.is_authenticated:
            user_name = current_user.full_name
        return {
            "server_time": datetime.now(timezone.utc).isoformat(),
            "user_name": user_name
        }

    @app.route("/manifest.json")
    def serve_manifest():
        return app.send_static_file("manifest.json")

    @app.route("/service-worker.js")
    def serve_sw():
        return app.send_static_file("service-worker.js")

    # Security Headers after each request
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # CSP Configuration allowing CDNs for Charts, Google Fonts, and inline scripts/styles for animations
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
            "font-src 'self' fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
        return response

    # Global Custom Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "API endpoint not found"}}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Access denied"}}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": {"code": "TOO_MANY_REQUESTS", "message": "Rate limit exceeded. Please try again later"}}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": {"code": "INTERNAL_ERROR", "message": "An internal server error occurred"}}), 500
        return render_template("errors/500.html"), 500

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.accounts import accounts_bp
    from routes.transactions import transactions_bp
    from routes.beneficiaries import beneficiaries_bp
    from routes.cards import cards_bp
    from routes.standing_orders import standing_orders_bp
    from routes.statements import statements_bp
    from routes.notifications import notifications_bp
    from routes.support import support_bp
    from routes.profile import profile_bp
    from routes.admin import admin_bp
    from routes.monitoring_routes import monitoring_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(beneficiaries_bp)
    app.register_blueprint(cards_bp)
    app.register_blueprint(standing_orders_bp)
    app.register_blueprint(statements_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(monitoring_bp)

    return app
