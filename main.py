import os
import sqlite3

import click
from dotenv import load_dotenv
from flask import Flask, abort, request, send_from_directory, session
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

load_dotenv()

from src.config import Config, ProductionConfig
from src.models.user import db
from src.models.user import User
from src.routes.user_routes import user_bp
from src.routes.professional_routes import professional_bp


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(config_class=Config):
    app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "copilot"))
    app.config.from_object(config_class)

    if not app.config["SECRET_KEY"]:
        # A random key would silently log users out on each restart. Fail clearly instead.
        raise RuntimeError("SECRET_KEY must be configured")

    if os.getenv("FLASK_ENV") == "production":
        ProductionConfig.validate()

    cors_origins = app.config["CORS_ORIGINS"]
    if cors_origins:
        CORS(app, supports_credentials=True, origins=cors_origins)

    db.init_app(app)
    Migrate(app, db)

    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(professional_bp, url_prefix="/api")

    admin_page_paths = {
        "/admin",
        "/admin/",
        "/admin.html",
        f"{app.static_url_path}/admin.html",
    }

    @app.before_request
    def protect_admin_page():
        if request.path not in admin_page_paths:
            return None
        user_id = session.get("user_id")
        user = db.session.get(User, user_id, populate_existing=True) if user_id else None
        if not user or not user.is_admin:
            abort(404)
        return None

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.password_option()
    def create_admin(username, password):
        """Create or promote an administrator through an audited CLI path."""
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
        user.is_admin = True
        db.session.commit()
        click.echo(f"Administrator ready: {username}")

    @app.cli.command("create-owner")
    @click.argument("username")
    @click.password_option()
    def create_owner(username, password):
        """Create or update the primary owner without storing credentials in code."""
        username = username.strip()
        if not username or len(username) > 80:
            raise click.ClickException("Username must contain between 1 and 80 characters")
        if not 8 <= len(password) <= 128:
            raise click.ClickException("Password must contain between 8 and 128 characters")
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username)
            db.session.add(user)
        user.set_password(password)
        user.is_admin = True
        user.is_premium = True
        user.is_professional = True
        user.is_banned = False
        user.banned_at = None
        db.session.commit()
        click.echo(f"Owner ready: {username}")

    @app.route("/admin")
    def serve_admin():
        return send_from_directory(app.static_folder, "admin.html")

    @app.route("/api/health")
    def health():
        db.session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve(path):
        if path.startswith("api/"):
            abort(404)
        if path and os.path.isfile(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8081")), debug=os.getenv("FLASK_DEBUG") == "1")
