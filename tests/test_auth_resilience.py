import logging
from unittest.mock import Mock

from google.auth.exceptions import TransportError
from sqlalchemy.exc import IntegrityError

from src.models.user import OAuthIdentity, User, db
from src.routes.auth_routes import _BoundedGoogleRequest
from tests.helpers import consent_payload
from tests.test_auth_and_entitlements import GOOGLE_PAYLOAD, _begin_google_signup, _mock_google


def test_google_certificates_use_bounded_timeout(monkeypatch):
    transport = Mock(return_value="certificates")
    monkeypatch.setattr("google.auth.transport.requests.Request.__call__", transport)
    assert _BoundedGoogleRequest()("https://www.googleapis.com/oauth2/v1/certs", timeout=120) == "certificates"
    assert transport.call_args.kwargs["timeout"] == 10


def test_google_transport_failure_is_retryable_without_leaking_token(client, monkeypatch, caplog):
    monkeypatch.setattr("google.oauth2.id_token.verify_oauth2_token", Mock(side_effect=TransportError("private-token")))
    with caplog.at_level(logging.INFO):
        response = client.post("/api/auth/google", json={"credential": "private-token"})
    assert response.status_code == 503
    assert response.get_json()["code"] == "provider_unavailable"
    assert "private-token" not in response.get_data(as_text=True)
    assert "private-token" not in caplog.text
    assert "duration_ms=" in caplog.text
    assert "provider_unavailable" in caplog.text


def test_google_flush_conflict_rolls_back_entire_signup(client, app, monkeypatch):
    _mock_google(monkeypatch)
    token = _begin_google_signup(client)
    real_flush = db.session.flush
    monkeypatch.setattr(db.session, "flush", Mock(side_effect=IntegrityError("insert", {}, Exception("collision"))))
    response = client.post("/api/auth/google", json={"signup_token": token, "username": "fresh-user", **consent_payload()})
    assert response.status_code == 409
    assert response.get_json()["code"] == "signup_conflict"
    monkeypatch.setattr(db.session, "flush", real_flush)
    with app.app_context():
        assert User.query.count() == 0
        assert OAuthIdentity.query.count() == 0
    # A rolled-back attempt did not destroy a valid signup credential.
    assert client.post("/api/auth/google", json={"signup_token": token, "username": "fresh-user", **consent_payload()}).status_code == 201


def test_google_distinct_subjects_with_same_email_remain_distinct(client, app, monkeypatch):
    _mock_google(monkeypatch)
    token = _begin_google_signup(client)
    assert client.post("/api/auth/google", json={"signup_token": token, "username": "first-user", **consent_payload()}).status_code == 201
    second = app.test_client()
    _mock_google(monkeypatch, {**GOOGLE_PAYLOAD, "sub": "different-subject"})
    token = _begin_google_signup(second)
    assert second.post("/api/auth/google", json={"signup_token": token, "username": "second-user", **consent_payload()}).status_code == 201
    with app.app_context():
        assert User.query.count() == 2
        assert OAuthIdentity.query.count() == 2


def test_google_signup_replay_does_not_duplicate_account(client, app, monkeypatch):
    _mock_google(monkeypatch)
    token = _begin_google_signup(client)
    body = {"signup_token": token, "username": "fresh-user", **consent_payload()}
    assert client.post("/api/auth/google", json=body).status_code == 201
    assert client.post("/api/auth/google", json=body).status_code == 200
    with app.app_context():
        assert User.query.count() == 1
        assert OAuthIdentity.query.count() == 1
