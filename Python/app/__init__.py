import os
from datetime import timedelta
from flask import Flask
from dotenv import load_dotenv

from app.extensions import limiter


def create_app():
    load_dotenv()

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )
    
    app.json.ensure_ascii = False

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "clave_temporal_desarrollo")
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

    limiter.init_app(app)

    from app.routes.auth import auth_bp
    from app.routes.pages import pages_bp
    from app.routes.espacios import espacios_bp
    from app.routes.reservas import reservas_bp
    from app.routes.mantenimientos import mant_bp
    from app.routes.reportes import reportes_bp
    from app.routes.admin import admin_bp
    from app.routes.mongo_test import mongo_bp
    from app.routes.mongo_reports import mongo_reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(espacios_bp)
    app.register_blueprint(reservas_bp)
    app.register_blueprint(mant_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(mongo_bp)
    app.register_blueprint(mongo_reports_bp)

    @app.errorhandler(404)
    def not_found(error):
        return "Página no encontrada", 404

    @app.errorhandler(500)
    def server_error(error):
        return "Error interno del servidor", 500

    return app