import pytest
import uuid
from types import SimpleNamespace

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from src.models.user import PushDevice, User, db
from src.services.push_notifications import notify_plan_ready
from tests.helpers import registration_payload


def test_registration_validation_logout_and_owner_deletion(app, client):
    assert client.post("/api/register", json=registration_payload("push-one")).status_code == 201
    installation = str(uuid.uuid4())
    payload = {"installation_id": installation, "token": "a" * 64, "environment": "production"}
    assert client.post("/api/push/devices", json={**payload, "token": "bad"}).status_code == 400
    response = client.post("/api/push/devices", json=payload)
    assert response.status_code == 200
    assert response.json == {"registered": True, "push_enabled": False}
    with app.app_context():
        assert PushDevice.query.count() == 1
    assert client.post("/api/logout").status_code == 200
    with app.app_context():
        assert PushDevice.query.count() == 0


def test_other_user_cannot_unregister_device(app, client):
    client.post("/api/register", json=registration_payload("push-owner"))
    installation = str(uuid.uuid4())
    client.post("/api/push/devices", json={"installation_id": installation, "token": "b" * 64, "environment": "sandbox"})
    other = app.test_client()
    other.post("/api/register", json=registration_payload("push-other"))
    assert other.delete(f"/api/push/devices/{installation}").status_code == 200
    with app.app_context():
        assert PushDevice.query.count() == 1


@pytest.mark.parametrize("status", [200, 410, 503])
def test_apns_signed_request_and_expired_token_cleanup(app, monkeypatch, status):
    private = ec.generate_private_key(ec.SECP256R1())
    app.config.update(APNS_ENABLED=True, APNS_KEY_ID="key-id", APNS_TEAM_ID="team-id", APNS_TOPIC="app.fittracker",
                      APNS_PRIVATE_KEY=private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode())
    captured = []

    def transport(request):
        captured.append(request)
        auth = request.headers["authorization"].removeprefix("bearer ")
        assert jwt.decode(auth, private.public_key(), algorithms=["ES256"])["iss"] == "team-id"
        assert request.headers["apns-push-type"] == "alert"
        return httpx.Response(status)

    real_client = httpx.Client
    def mock_client(**kwargs):
        assert kwargs.pop("http2") is True
        return real_client(transport=httpx.MockTransport(transport), **kwargs)
    monkeypatch.setattr("src.services.push_notifications.httpx.Client", mock_client)
    with app.app_context():
        user = User(username="push-test", email="push@example.com")
        user.set_password("test-password")
        db.session.add(user)
        db.session.flush()
        db.session.add(PushDevice(user_id=user.id, installation_id=str(uuid.uuid4()), token="c" * 64, environment="sandbox"))
        db.session.commit()
        task = SimpleNamespace(id=uuid.uuid4(), user_id=user.id, status="succeeded", operation="workout_plan", result={"plan_id": 12})
        assert notify_plan_ready(task) is (status == 200)
        assert "api.sandbox.push.apple.com" == captured[0].url.host
        assert str(task.id) in captured[0].content.decode()
        assert PushDevice.query.count() == (0 if status == 410 else 1)


def test_disabled_push_does_not_call_provider(app, monkeypatch):
    monkeypatch.setattr("src.services.push_notifications.httpx.Client", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not call")))
    with app.app_context():
        assert notify_plan_ready(SimpleNamespace(status="succeeded", operation="diet_plan")) is False
