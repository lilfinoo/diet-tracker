import os

import click
from dotenv import load_dotenv
from flask import Flask, abort, send_from_directory
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import text

load_dotenv()

from src.config import Config, ProductionConfig
from src.models.user import db
from src.models.user import User
from src.routes.user_routes import user_bp


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
