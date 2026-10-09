from src.models.user import OAuthIdentity, User, db
from src.services import apple_auth


def signed_in(app, client):
    with app.app_context():
        user = User(username="original", email="same@example.com")
        db.session.add(user)
        db.session.commit()
        owner = str(user.id)
    with client.session_transaction() as session:
        session["user_id"] = owner
        session["csrf_token"] = "fresh"
    return owner


def google(monkeypatch, subject="provider-sub"):
    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", lambda *args: {
        "iss": "https://accounts.google.com", "sub": subject, "email": "same@example.com",
        "email_verified": True, "name": "Provider Name", "picture": None})


def test_link_requires_session(client):
    assert client.post("/api/account/identities/google", json={"credential": "token"}).status_code == 401


def test_google_links_to_authenticated_owner_without_changing_account(app, client, monkeypatch):
    owner = signed_in(app, client)
    google(monkeypatch)
    app.config["CSRF_PROTECTION"] = True
    assert client.post("/api/account/identities/google", json={"credential": "token"}).status_code == 403
    response = client.post("/api/account/identities/google", json={"credential": "token"}, headers={"X-CSRF-Token": "fresh"})
    assert response.status_code == 200
    assert response.get_json()["providers"] == ["google"]
    with app.app_context():
        assert User.query.count() == 1
        assert str(OAuthIdentity.query.one().user_id) == owner
        assert User.query.one().username == "original"
    assert client.get("/api/account/identities").get_json()["providers"] == ["google"]


def test_link_refuses_identity_owned_by_another_user(app, client, monkeypatch):
    signed_in(app, client)
    google(monkeypatch)
    with app.app_context():
        other = User(username="other", email="same@example.com")
        db.session.add(OAuthIdentity(user=other, provider="google", issuer="https://accounts.google.com", subject="provider-sub"))
        db.session.commit()
    response = client.post("/api/account/identities/google", json={"credential": "token"})
    assert response.status_code == 409
    assert response.get_json()["code"] == "identity_already_linked"
    with app.app_context():
        assert OAuthIdentity.query.one().user.username == "other"
        assert User.query.count() == 2


def test_repeated_link_is_idempotent(app, client, monkeypatch):
    signed_in(app, client)
    google(monkeypatch)
    for _ in range(2):
        assert client.post("/api/account/identities/google", json={"credential": "token"}).status_code == 200
    with app.app_context():
        assert OAuthIdentity.query.count() == 1


def test_apple_link_requires_bound_single_use_nonce_and_stores_refresh_token(app, client, monkeypatch):
    from cryptography.fernet import Fernet
    owner = signed_in(app, client)
    app.config.update(APPLE_TEAM_ID="team", APPLE_KEY_ID="key", APPLE_PRIVATE_KEY="unused", APPLE_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
    monkeypatch.setattr(apple_auth, "verify_identity", lambda token, nonce: {"sub": "apple-sub", "email": "relay@example.com", "email_verified": True})
    monkeypatch.setattr(apple_auth, "exchange_code", lambda *args: "encrypted-refresh")
    nonce = client.post("/api/auth/apple/challenge").get_json()["nonce"]
    body = {"nonce": nonce, "credential": "id-token", "authorization_code": "code"}
    assert client.post("/api/account/identities/apple", json=body).status_code == 200
    assert client.post("/api/account/identities/apple", json=body).status_code == 401
    with app.app_context():
        identity = OAuthIdentity.query.one()
        assert str(identity.user_id) == owner
        assert identity.apple_refresh_token == "encrypted-refresh"
