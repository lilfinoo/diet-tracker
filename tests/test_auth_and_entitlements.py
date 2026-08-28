from datetime import datetime, timedelta

from itsdangerous import URLSafeTimedSerializer

from src.models.user import OAuthIdentity, Subscription, User, db


GOOGLE_PAYLOAD = {
    "iss": "https://accounts.google.com",
    "sub": "google-subject-123",
    "email": "person@example.com",
    "email_verified": True,
    "name": "Google Person",
    "picture": "https://example.com/avatar.png",
}


def _mock_google(monkeypatch, payload=None):
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda credential, request, audience: payload or GOOGLE_PAYLOAD,
    )


def _begin_google_signup(client):
    response = client.post("/api/auth/google", json={"credential": "raw-google-token"})
    assert response.status_code == 409
    assert response.get_json()["code"] == "username_required"
    return response.get_json()["signup_token"]


def test_google_first_access_creation_and_relogin(app, client, monkeypatch):
    _mock_google(monkeypatch)
    signup_token = _begin_google_signup(client)
    claims = URLSafeTimedSerializer(
        app.config["SECRET_KEY"], salt="google-signup"
    ).loads(signup_token)
    assert claims["subject"] == GOOGLE_PAYLOAD["sub"]
    assert "credential" not in claims
    assert "raw-google-token" not in signup_token

    created = client.post(
        "/api/auth/google",
        json={"signup_token": signup_token, "username": "google-user"},
    )
    assert created.status_code == 201
    assert created.get_json()["user"]["username"] == "google-user"
    with app.app_context():
        user = User.query.filter_by(username="google-user").one()
        identity = OAuthIdentity.query.one()
        assert user.password_hash is None
        assert identity.user_id == user.id
        assert identity.email_verified is True

    assert client.post("/api/logout").status_code == 200
    relogin = client.post("/api/auth/google", json={"credential": "new-google-token"})
    assert relogin.status_code == 200
    assert relogin.get_json()["user"]["username"] == "google-user"


def test_google_signup_rejects_username_collision(client, monkeypatch):
    _mock_google(monkeypatch)
    assert client.post(
        "/api/register",
        json={"username": "taken", "password": "strong-password"},
    ).status_code == 201
    signup_token = _begin_google_signup(client)
    response = client.post(
        "/api/auth/google",
        json={"signup_token": signup_token, "username": "taken"},
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == "username_taken"


def test_google_rejects_invalid_token(client, monkeypatch):
    def invalid_token(*args, **kwargs):
        raise ValueError("invalid")

    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", invalid_token)
    response = client.post("/api/auth/google", json={"credential": "invalid"})
    assert response.status_code == 401


def test_google_login_blocks_banned_user(app, client, monkeypatch):
    _mock_google(monkeypatch)
    signup_token = _begin_google_signup(client)
    assert client.post(
        "/api/auth/google",
        json={"signup_token": signup_token, "username": "banned-google"},
    ).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="banned-google").one()
        user.ban_user()
        db.session.commit()

    response = client.post("/api/auth/google", json={"credential": "valid"})
    assert response.status_code == 403
    assert client.get("/api/check_session").get_json() == {"logged_in": False}


def test_public_plans_and_active_subscription_entitlement(app, client):
    plans = client.get("/api/plans")
    assert plans.status_code == 200
    assert plans.get_json()["provider_configured"] is False
    assert {
        plan["code"]: plan["price_brl"] for plan in plans.get_json()["plans"]
    } == {
        "free": 0,
        "premium_student": 20,
        "professional_single": 50,
        "professional_complete": 70,
    }

    assert client.post(
        "/api/register",
        json={"username": "subscriber", "password": "strong-password"},
    ).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="subscriber").one()
        db.session.add(Subscription(
            user_id=user.id,
            provider="stripe",
            external_subscription_id="sub_123",
            status="active",
            plan_code="professional_complete",
            current_period_start=datetime.utcnow() - timedelta(days=1),
            current_period_end=datetime.utcnow() + timedelta(days=29),
        ))
        db.session.commit()
        assert user.is_premium is False

    subscription = client.get("/api/subscription")
    assert subscription.status_code == 200
    assert subscription.get_json()["is_premium"] is True
    assert subscription.get_json()["plan_code"] == "professional_complete"


def test_ai_trial_counts_only_successful_responses(app, client, monkeypatch):
    assert client.post(
        "/api/register",
        json={"username": "trial-user", "password": "strong-password"},
    ).status_code == 201
    monkeypatch.setattr(
        "src.routes.profile_routes.calculate_nutrition",
        lambda description, image_bytes, mime_type: {"calories": 100},
    )

    assert client.post("/api/diet/ai_macros", json={}).status_code == 400
    for _ in range(3):
        assert client.post(
            "/api/diet/ai_macros", json={"description": "banana"}
        ).status_code == 200
    blocked = client.post(
        "/api/diet/ai_macros", json={"description": "banana"}
    )
    assert blocked.status_code == 403
    assert blocked.get_json()["code"] == "premium_required"
    with app.app_context():
        assert User.query.filter_by(username="trial-user").one().ai_trial_uses == 3
