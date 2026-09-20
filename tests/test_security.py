import pytest
from sqlalchemy import inspect, text

from src.config import ProductionConfig
from main import create_app
from src.config import TestConfig
from src.models.user import db
from tests.helpers import registration_payload


def _register(client, username="alice", password="strong-password"):
    return client.post("/api/register", json=registration_payload(username, password))


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
    admin_source = client.get("/admin").get_data(as_text=True)
    assert "confirmDestructiveUserAction" in admin_source
    assert "Rejeitar esta solicitação profissional?" in admin_source
    assert "runAdminAction" in admin_source
    assert 'aria-live="polite"' in admin_source
    assert 'role="tablist"' in admin_source
    assert 'role="tabpanel"' in admin_source
    assert 'id="premiumDurationSelect"' in admin_source
    assert 'id="professionalDurationSelect"' in admin_source
    assert "Sem prazo, até revogação" in admin_source


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
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "postgresql://example/db")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "Qf8!xT2#vN7@kL4$pR9&wY6*zC3-mH5_sJ1")
    monkeypatch.setattr(ProductionConfig, "PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(ProductionConfig, "CORS_ORIGINS", ["https://example.com"])
    monkeypatch.setattr(ProductionConfig, "ASAAS_ENV", "production")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_BASE_URL", "https://api.asaas.com/v3")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_KEY", "$aact_prod_valid-looking-key-123456")
    monkeypatch.setattr(ProductionConfig, "ASAAS_WEBHOOK_TOKEN", "Asaas-Webhook-9xK2pL7vQ4mN8sT5wR3y")
    monkeypatch.setattr(ProductionConfig, "GEMINI_API_KEY", None)
    monkeypatch.setattr(ProductionConfig, "REDIS_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "CELERY_BROKER_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "METRICS_TOKEN", "Metrics-Token-9xK2pL7vQ4mN8sT5wR3y")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        ProductionConfig.validate()


def test_production_config_accepts_complete_env(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "postgresql://example/db")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "Lm9!qW4#sE7@rT2$yU8&iO5*pA3-dF6_gH1")
    monkeypatch.setattr(ProductionConfig, "PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(ProductionConfig, "CORS_ORIGINS", ["https://example.com"])
    monkeypatch.setattr(ProductionConfig, "ASAAS_ENV", "production")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_BASE_URL", "https://api.asaas.com/v3")
    monkeypatch.setattr(ProductionConfig, "GEMINI_API_KEY", "AIzaSyD-valid-looking-production-key-123456")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_KEY", "$aact_prod_valid-looking-key-123456")
    monkeypatch.setattr(ProductionConfig, "ASAAS_WEBHOOK_TOKEN", "Asaas-Webhook-9xK2pL7vQ4mN8sT5wR3y")
    monkeypatch.setattr(ProductionConfig, "REDIS_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "CELERY_BROKER_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "METRICS_TOKEN", "Metrics-Token-9xK2pL7vQ4mN8sT5wR3y")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_ENDPOINT_URL", None)
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_ACCESS_KEY_ID", None)
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_SECRET_ACCESS_KEY", None)
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_BUCKET", None)
    ProductionConfig.validate()


def test_production_config_accepts_optional_r2_env(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "postgresql://example/db")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "Lm9!qW4#sE7@rT2$yU8&iO5*pA3-dF6_gH1")
    monkeypatch.setattr(ProductionConfig, "PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(ProductionConfig, "CORS_ORIGINS", ["https://example.com"])
    monkeypatch.setattr(ProductionConfig, "ASAAS_ENV", "production")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_BASE_URL", "https://api.asaas.com/v3")
    monkeypatch.setattr(ProductionConfig, "GEMINI_API_KEY", "AIzaSyD-valid-looking-production-key-123456")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_KEY", "$aact_prod_valid-looking-key-123456")
    monkeypatch.setattr(ProductionConfig, "ASAAS_WEBHOOK_TOKEN", "Asaas-Webhook-9xK2pL7vQ4mN8sT5wR3y")
    monkeypatch.setattr(ProductionConfig, "REDIS_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "CELERY_BROKER_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "METRICS_TOKEN", "Metrics-Token-9xK2pL7vQ4mN8sT5wR3y")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_ENDPOINT_URL", "https://account.r2.cloudflarestorage.com")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_ACCESS_KEY_ID", "r2-access-key")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_SECRET_ACCESS_KEY", "r2-secret-key")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_BUCKET", "diet-tracker-media")
    ProductionConfig.validate()


@pytest.mark.parametrize(("name", "value", "message"), [
    ("SECRET_KEY", "replace-with-a-long-random-secret", "SECRET_KEY"),
    ("SQLALCHEMY_DATABASE_URI", "sqlite:///production.db", "SQLite"),
    ("PUBLIC_BASE_URL", "http://example.com", "HTTPS"),
    ("CORS_ORIGINS", ["https://*.example.com"], "Wildcard CORS"),
    ("ASAAS_ENV", "sandbox", "ASAAS_ENV"),
    ("ASAAS_API_KEY", None, "ASAAS_API_KEY"),
    ("GEMINI_API_KEY", "fake-key", "GEMINI_API_KEY"),
])
def test_production_config_rejects_launch_unsafe_values(monkeypatch, name, value, message):
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", "postgresql://example/db")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "Nr6!tY2#uI9@oP4$aS7&dF3*gH8-jK5_lZ1")
    monkeypatch.setattr(ProductionConfig, "PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(ProductionConfig, "CORS_ORIGINS", ["https://example.com"])
    monkeypatch.setattr(ProductionConfig, "ASAAS_ENV", "production")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_BASE_URL", "https://api.asaas.com/v3")
    monkeypatch.setattr(ProductionConfig, "ASAAS_API_KEY", "$aact_prod_valid-looking-key-123456")
    monkeypatch.setattr(ProductionConfig, "ASAAS_WEBHOOK_TOKEN", "Asaas-Webhook-9xK2pL7vQ4mN8sT5wR3y")
    monkeypatch.setattr(ProductionConfig, "GEMINI_API_KEY", "AIzaSyD-valid-looking-production-key-123456")
    monkeypatch.setattr(ProductionConfig, "REDIS_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "CELERY_BROKER_URL", "rediss://redis.example/0")
    monkeypatch.setattr(ProductionConfig, "METRICS_TOKEN", "Metrics-Token-9xK2pL7vQ4mN8sT5wR3y")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_ENDPOINT_URL", "https://account.r2.cloudflarestorage.com")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_ACCESS_KEY_ID", "r2-access-key")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_SECRET_ACCESS_KEY", "r2-secret-key")
    monkeypatch.setattr(ProductionConfig, "MEDIA_R2_BUCKET", "diet-tracker-media")
    monkeypatch.setattr(ProductionConfig, name, value)

    with pytest.raises(RuntimeError, match=message):
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


def test_privacy_migration_preserves_existing_professional_audit(tmp_path):
    class MigrationConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'privacy-migration.db'}"

    app = create_app(MigrationConfig)
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade", "c7e4a9d2f5b1"]).exit_code == 0

    professional_id = "11111111111111111111111111111111"
    student_id = "22222222222222222222222222222222"
    with app.app_context():
        for user_id, username in ((professional_id, "trainer"), (student_id, "student")):
            db.session.execute(text("""
                INSERT INTO user (
                    id, username, is_banned, created_at, is_premium, is_admin,
                    is_professional, ai_trial_uses, professional_scope
                ) VALUES (:id, :username, 0, CURRENT_TIMESTAMP, 0, 0, 0, 0, NULL)
            """), {"id": user_id, "username": username})
        db.session.execute(text("""
            INSERT INTO professional_student_relationship (
                id, professional_user_id, student_user_id, status, invite_token_hash,
                invite_expires_at, created_at, accepted_at
            ) VALUES (
                1, :professional_id, :student_id, 'active', 'migration-test-token',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {"professional_id": professional_id, "student_id": student_id})
        db.session.execute(text("""
            INSERT INTO delegated_action_audit (
                id, actor_user_id, subject_user_id, relationship_id, action, created_at
            ) VALUES (1, :professional_id, :student_id, 1, 'migration_test', CURRENT_TIMESTAMP)
        """), {"professional_id": professional_id, "student_id": student_id})
        db.session.execute(text("""
            INSERT INTO subscription (
                user_id, provider, external_subscription_id, status, plan_code, created_at, updated_at
            ) VALUES (
                :user_id, 'asaas', 'legacy-unverified', 'active', 'premium_student',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {"user_id": student_id})
        db.session.commit()

    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output

    with app.app_context():
        relationship_columns = {
            column["name"]: column
            for column in inspect(db.engine).get_columns("professional_student_relationship")
        }
        assert relationship_columns["professional_user_id"]["nullable"] is True
        assert "data_sharing_consent_version" in relationship_columns
        assert db.session.execute(text("SELECT COUNT(*) FROM professional_student_relationship")).scalar() == 1
        assert db.session.execute(text("SELECT COUNT(*) FROM delegated_action_audit")).scalar() == 1
        legacy_subscription = db.session.execute(text(
            "SELECT status, current_period_start, current_period_end FROM subscription "
            "WHERE external_subscription_id = 'legacy-unverified'"
        )).one()
        assert legacy_subscription == ("pending", None, None)
        assert db.session.execute(text("PRAGMA foreign_key_check")).all() == []


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
    register = client.post("/api/register", json=registration_payload("csrf-user"))
    assert register.status_code == 201
    token = register.get_json()["csrf_token"]

    blocked = client.post("/api/profile", json={"age": 30})
    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "Token CSRF inválido."

    allowed = client.post("/api/profile", headers={"X-CSRF-Token": token}, json={"age": 30})
    assert allowed.status_code == 200
