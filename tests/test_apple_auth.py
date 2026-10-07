import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa

from src.legal import AI_CONSENT_VERSION
from src.models.user import OAuthIdentity, User, db
from src.services import apple_auth


@pytest.fixture
def apple_ready(app, monkeypatch):
    app.config.update(APPLE_TEAM_ID="team", APPLE_KEY_ID="key", APPLE_PRIVATE_KEY="unused",
                      APPLE_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
    monkeypatch.setattr(apple_auth, "verify_identity", lambda credential, nonce: {
        "sub": credential, "email": "same@example.com", "email_verified": "true"})
    monkeypatch.setattr(apple_auth, "exchange_code", lambda code, subject, nonce: "encrypted-token")


def authenticate(client, subject="apple-sub"):
    nonce = client.post("/api/auth/apple/challenge").get_json()["nonce"]
    return client.post("/api/auth/apple", json={"credential": subject, "nonce": nonce, "authorization_code": "code"})


def signup(client, token, username="apple-user"):
    return client.post("/api/auth/apple", json={"signup_token": token, "username": username,
        "ai_consent": False, "ai_consent_version": AI_CONSENT_VERSION})


def test_requires_server_configuration(client):
    assert client.post("/api/auth/apple/challenge").status_code == 503


def test_new_identity_does_not_link_by_email(client, app, apple_ready):
    with app.app_context():
        db.session.add(User(username="existing", email="same@example.com"))
        db.session.commit()
    response = authenticate(client)
    assert response.status_code == 409
    created = signup(client, response.get_json()["signup_token"])
    assert created.status_code == 201
    with app.app_context():
        assert User.query.count() == 2
        identity = OAuthIdentity.query.one()
        assert identity.provider == "apple"
        assert identity.apple_refresh_token == "encrypted-token"
    client.post("/api/logout")
    assert authenticate(client).status_code == 200


def test_nonce_is_single_use_and_session_bound(client, app, apple_ready):
    nonce = client.post("/api/auth/apple/challenge").get_json()["nonce"]
    body = {"credential": "sub", "nonce": nonce, "authorization_code": "code"}
    assert app.test_client().post("/api/auth/apple", json=body).status_code == 401
    assert client.post("/api/auth/apple", json=body).status_code == 409
    assert client.post("/api/auth/apple", json=body).status_code == 401


def test_banned_identity_cannot_login(client, app, apple_ready):
    token = authenticate(client).get_json()["signup_token"]
    signup(client, token)
    with app.app_context():
        User.query.filter_by(username="apple-user").one().is_banned = True
        db.session.commit()
    client.post("/api/logout")
    assert authenticate(client).status_code == 403


def test_apple_deletion_revokes_before_delete(client, app, apple_ready, monkeypatch):
    token = authenticate(client).get_json()["signup_token"]
    signup(client, token)
    revoke = Mock()
    monkeypatch.setattr(apple_auth, "revoke_identity", revoke)
    response = client.delete("/api/account", json={"username": "apple-user", "confirm_delete": True})
    assert response.status_code == 200
    revoke.assert_called_once()
    with app.app_context():
        assert User.query.count() == 0
        assert OAuthIdentity.query.count() == 0


def test_revocation_failure_preserves_account(client, app, apple_ready, monkeypatch):
    signup(client, authenticate(client).get_json()["signup_token"])
    monkeypatch.setattr(apple_auth, "revoke_identity", Mock(side_effect=ValueError("unavailable")))
    assert client.delete("/api/account", json={"username": "apple-user", "confirm_delete": True}).status_code == 503
    with app.app_context():
        assert User.query.count() == 1


def test_real_signature_claim_validation(app, monkeypatch):
    import time
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(apple_auth.APPLE_KEYS, "get_signing_key_from_jwt", lambda token: SimpleNamespace(key=key.public_key()))
    now = int(time.time())
    claims = {"sub": "apple", "iss": apple_auth.APPLE_ISSUER, "aud": "ai.fittracker.app", "iat": now,
              "exp": now + 100, "nonce": hashlib.sha256(b"nonce").hexdigest()}
    with app.app_context():
        valid = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
        assert apple_auth.verify_identity(valid, "nonce")["sub"] == "apple"
        for change in ({"aud": "other"}, {"iss": "other"}, {"exp": now - 1}, {"nonce": "other"}):
            token = jwt.encode({**claims, **change}, key, algorithm="RS256")
            with pytest.raises((ValueError, jwt.InvalidTokenError)):
                apple_auth.verify_identity(token, "nonce")
        with pytest.raises(ValueError):
            apple_auth.verify_identity(jwt.encode(claims, "secret", algorithm="HS256"), "nonce")


def test_invalid_token_and_unavailable_apple(client, apple_ready, monkeypatch):
    monkeypatch.setattr(apple_auth, "verify_identity", Mock(side_effect=jwt.DecodeError("bad")))
    assert authenticate(client).status_code == 401
    monkeypatch.setattr(apple_auth, "verify_identity", Mock(side_effect=jwt.PyJWKClientConnectionError("offline")))
    assert authenticate(client).status_code == 503


def test_signup_requires_consent_choice(client, apple_ready):
    token = authenticate(client).get_json()["signup_token"]
    response = client.post("/api/auth/apple", json={"signup_token": token, "username": "apple-user"})
    assert response.status_code == 400
    assert client.post("/api/auth/apple", json={"signup_token": "forged", "username": "apple-user", "ai_consent": False}).status_code == 401


def test_signup_token_cannot_recreate_deleted_account(client, app, apple_ready, monkeypatch):
    token = authenticate(client).get_json()["signup_token"]
    assert signup(client, token).status_code == 201
    monkeypatch.setattr(apple_auth, "revoke_identity", Mock())
    assert client.delete("/api/account", json={"username": "apple-user", "confirm_delete": True}).status_code == 200
    assert signup(client, token).status_code == 401


def test_signup_username_retry_preserves_token(client, app, apple_ready):
    with app.app_context():
        db.session.add(User(username="taken"))
        db.session.commit()
    token = authenticate(client).get_json()["signup_token"]
    assert signup(client, token, "taken").status_code == 409
    assert signup(client, token, "available").status_code == 201


def test_exchange_encrypts_token_and_revocation_uses_private_credentials(app, monkeypatch):
    import time
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    signing = ec.generate_private_key(ec.SECP256R1())
    pem = signing.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    token_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    id_token = jwt.encode({"iss": apple_auth.APPLE_ISSUER, "aud": "ai.fittracker.app", "sub": "subject",
                          "exp": now + 100, "nonce": hashlib.sha256(b"nonce").hexdigest()}, token_key, algorithm="RS256")
    post = Mock(return_value=SimpleNamespace(status_code=200, content=b"json", json=lambda: {"id_token": id_token, "refresh_token": "private-refresh"}))
    monkeypatch.setattr(apple_auth.requests, "post", post)
    monkeypatch.setattr(apple_auth.APPLE_KEYS, "get_signing_key_from_jwt", lambda token: SimpleNamespace(key=token_key.public_key()))
    with app.app_context():
        app.config.update(APPLE_TEAM_ID="team", APPLE_KEY_ID="key", APPLE_PRIVATE_KEY=pem,
                          APPLE_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
        encrypted = apple_auth.exchange_code("authorization", "subject", "nonce")
        assert "private-refresh" not in encrypted
        client_secret = post.call_args.kwargs["data"]["client_secret"]
        assert jwt.decode(client_secret, signing.public_key(), algorithms=["ES256"], audience=apple_auth.APPLE_ISSUER)["iss"] == "team"
        with pytest.raises(ValueError):
            apple_auth.exchange_code("authorization", "different-user", "nonce")
        with pytest.raises(ValueError):
            apple_auth.exchange_code("authorization", "subject", "wrong-nonce")
        post.return_value = SimpleNamespace(status_code=200, content=b"")
        apple_auth.revoke_identity(SimpleNamespace(apple_refresh_token=encrypted))
        assert post.call_args.args[0].endswith("/auth/revoke")
        assert post.call_args.kwargs["data"]["token"] == "private-refresh"
