import pytest

from src.legal import AI_CONSENT_VERSION, AI_OPENAI_CONSENT_VERSION
from src.models.user import ConsentRecord, User
from tests.helpers import registration_payload
from tests.test_auth_and_entitlements import _begin_google_signup, _mock_google


PROVIDERS = {"X-AI-Providers": "gemini,openai"}


def test_legal_version_is_negotiated_without_upgrading_legacy(client):
    assert client.get("/api/auth/config").get_json()["legal"]["ai"]["version"] == AI_CONSENT_VERSION
    assert client.get("/api/auth/config", headers=PROVIDERS).get_json()["legal"]["ai"]["version"] == AI_OPENAI_CONSENT_VERSION
    assert client.get("/api/auth/config", headers={"X-AI-Providers": "openai"}).get_json()["legal"]["ai"]["version"] == AI_CONSENT_VERSION


def test_legacy_signup_cannot_record_openai_consent(client, app):
    payload = registration_payload("legacy")
    payload["ai_consent_version"] = AI_OPENAI_CONSENT_VERSION
    assert client.post("/api/register", json=payload).status_code == 400
    with app.app_context():
        assert User.query.count() == 0
        assert ConsentRecord.query.count() == 0


def test_new_signup_records_received_version_and_supports_gemini(client, app):
    payload = registration_payload("new-provider")
    payload["ai_consent_version"] = AI_OPENAI_CONSENT_VERSION
    assert client.post("/api/register", json=payload, headers=PROVIDERS).status_code == 201
    with app.app_context():
        user = User.query.one()
        assert user.has_current_ai_consent()
        assert user.ai_consent_version == AI_OPENAI_CONSENT_VERSION
        assert ConsentRecord.query.one().version == AI_OPENAI_CONSENT_VERSION
    assert client.get("/api/account/consents").get_json()["ai"]["accepted"]


def test_legacy_grant_is_valid_for_gemini_until_user_explicitly_upgrades(client, app):
    assert client.post("/api/register", json=registration_payload("legacy-grant")).status_code == 201
    assert client.get("/api/account/consents").get_json()["ai"]["accepted"]
    upgraded_client_payload = client.get("/api/account/consents", headers=PROVIDERS).get_json()
    assert not upgraded_client_payload["ai"]["accepted"]
    with app.app_context():
        assert User.query.one().has_current_ai_consent()
        assert User.query.one().ai_consent_version == AI_CONSENT_VERSION
    grant = {"ai_consent": True, "ai_consent_version": AI_OPENAI_CONSENT_VERSION}
    assert client.put("/api/account/consents", json=grant).status_code == 400
    upgraded = client.put("/api/account/consents", json=grant, headers=PROVIDERS)
    assert upgraded.status_code == 200
    assert upgraded.get_json()["ai"]["accepted"]
    assert client.put("/api/account/consents", json={"ai_consent": False}, headers=PROVIDERS).status_code == 200
    with app.app_context():
        user = User.query.one()
        assert not user.has_current_ai_consent()
        assert user.ai_consent_version is None
        audit = ConsentRecord.query.order_by(ConsentRecord.id).all()
        assert [(record.version, record.granted) for record in audit] == [
            (AI_CONSENT_VERSION, True), (AI_OPENAI_CONSENT_VERSION, True), (AI_OPENAI_CONSENT_VERSION, False)
        ]


@pytest.mark.parametrize("granted", [True, False])
def test_legacy_settings_cannot_record_new_version(client, app, granted):
    client.post("/api/register", json=registration_payload("legacy-settings"))
    assert client.put("/api/account/consents", json={"ai_consent": granted, "ai_consent_version": AI_OPENAI_CONSENT_VERSION}).status_code == 400
    with app.app_context():
        assert ConsentRecord.query.count() == 1


def test_google_signup_uses_negotiated_consent(client, app, monkeypatch):
    _mock_google(monkeypatch)
    token = _begin_google_signup(client)
    body = {"signup_token": token, "username": "google-provider", "ai_consent": True, "ai_consent_version": AI_OPENAI_CONSENT_VERSION}
    assert client.post("/api/auth/google", json=body).status_code == 400
    assert client.post("/api/auth/google", json=body, headers=PROVIDERS).status_code == 201
    with app.app_context():
        assert User.query.one().ai_consent_version == AI_OPENAI_CONSENT_VERSION
