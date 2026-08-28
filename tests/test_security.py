import pytest
from sqlalchemy import inspect

from src.config import ProductionConfig
from main import create_app
from src.config import TestConfig
from src.models.user import db


def _register(client, username="alice", password="strong-password"):
    return client.post("/api/register", json={"username": username, "password": password})


def _login(client, username="alice", password="strong-password"):
    return client.post("/api/login", json={"username": username, "password": password})


def test_register_rejects_weak_password(client):
    assert _register(client, password="short").status_code == 400
    assert _register(client, password="").status_code == 400


def test_register_rejects_oversized_password(client):
    assert _register(client, password="x" * 129).status_code == 400


def test_register_rejects_long_username(client):
    assert _register(client, username="a" * 81).status_code == 400


def test_admin_forbidden_returns_json(client):
    assert _register(client, "regular").status_code == 201
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 403
    assert response.is_json
    assert "error" in response.get_json()


def test_admin_page_requires_an_administrator(app, client):
    assert _register(client, "regular").status_code == 201

    for path in ("/admin", "/admin/", "/admin.html", f"{app.static_url_path}/admin.html"):
        assert client.get(path).status_code == 404

    with app.app_context():
        from src.models.user import User, db

        User.query.filter_by(username="regular").one().is_admin = True
        db.session.commit()

    assert client.get("/admin").status_code == 200
    assert client.get("/admin/").status_code == 200


def test_create_owner_grants_all_roles(app):
    runner = app.test_cli_runner()

    result = runner.invoke(args=["create-owner", "owner", "--password", "owner-password"])

    assert result.exit_code == 0
    with app.app_context():
        from src.models.user import User

        owner = User.query.filter_by(username="owner").one()
        assert owner.check_password("owner-password")
        assert owner.is_admin is True
        assert owner.is_premium is True
        assert owner.is_professional is True
        assert owner.is_banned is False


def test_rate_limit_exceeded_returns_429(client, app):
    app.config["RATE_LIMITS"] = {"register": (3, 60), "login": (100, 60), "ai": (100, 60)}
    responses = [_register(client, f"user{i}", "strong-password") for i in range(4)]
    assert responses[-1].status_code == 429
    assert responses[-1].is_json


def test_rate_limit_buckets_are_isolated(client, app):
    app.config["RATE_LIMITS"] = {"register": (1, 60), "login": (2, 60), "ai": (1, 60)}

    assert _register(client, "alice").status_code == 201
    login = _login(client, "alice", "wrong-password")
    assert login.status_code == 401

    assert _login(client, "alice", "wrong-password").status_code == 401
    assert _register(client, "bob").status_code == 429


def test_diet_field_length_limits(client):
    assert _register(client).status_code == 201
    long_description = client.post("/api/diet", json={
        "date": "2026-08-05", "meal_type": "Almoço", "description": "x" * 2001,
    })
    assert long_description.status_code == 400
    long_meal_type = client.post("/api/diet", json={
        "date": "2026-08-05", "meal_type": "m" * 51, "description": "Arroz",
    })
    assert long_meal_type.status_code == 400


def test_profile_rejects_invalid_age(client):
    assert _register(client).status_code == 201
    assert client.post("/api/profile", json={"age": 999}).status_code == 400
    assert client.post("/api/profile", json={"age": -1}).status_code == 400
    assert client.post("/api/profile", json={"age": 30, "weight": 70}).status_code == 200


def test_production_config_requires_gemini_key(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "prod-secret")
    monkeypatch.setattr(ProductionConfig, "PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(ProductionConfig, "CORS_ORIGINS", ["https://example.com"])
    monkeypatch.setattr(ProductionConfig, "GEMINI_API_KEY", None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        ProductionConfig.validate()


def test_production_config_accepts_complete_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "prod-secret")
    monkeypatch.setattr(ProductionConfig, "PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(ProductionConfig, "CORS_ORIGINS", ["https://example.com"])
    monkeypatch.setattr(ProductionConfig, "GEMINI_API_KEY", "fake-key")
    ProductionConfig.validate()


def test_workout_schedule_migration_adds_foreign_keys(tmp_path):
    class MigrationConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'migration.db'}"

    app = create_app(MigrationConfig)
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0

    with app.app_context():
        foreign_keys = inspect(db.engine).get_foreign_keys("user_profile")
        constrained_columns = {tuple(item["constrained_columns"]) for item in foreign_keys}

    assert ("current_workout_plan_id",) in constrained_columns
    assert ("pending_workout_plan_id",) in constrained_columns


def test_security_headers_are_applied(client):
    response = client.get("/api/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_csrf_protects_authenticated_mutations(tmp_path):
    class CsrfConfig(TestConfig):
        CSRF_PROTECTION = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'csrf.db'}"

    app = create_app(CsrfConfig)
    with app.app_context():
        db.create_all()

    client = app.test_client()
    register = client.post("/api/register", json={"username": "csrf-user", "password": "strong-password"})
    assert register.status_code == 201
    token = register.get_json()["csrf_token"]

    blocked = client.post("/api/profile", json={"age": 30})
    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "Token CSRF inválido."

    allowed = client.post("/api/profile", headers={"X-CSRF-Token": token}, json={"age": 30})
    assert allowed.status_code == 200
