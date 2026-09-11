import base64
from datetime import datetime, timedelta

from src.legal import AI_CONSENT_VERSION, PRIVACY_VERSION, TERMS_VERSION
from src.models.user import (
    AdminActionAudit,
    AnalyticsEvent,
    BillingCheckout,
    ConsentRecord,
    DelegatedActionAudit,
    DietEntry,
    ProfessionalStudentRelationship,
    Subscription,
    User,
    WorkoutPlan,
    db,
)
from tests.helpers import consent_payload, registration_payload
from main import create_app
from src.config import TestConfig


def test_registration_requires_current_legal_acceptance_and_records_choices(app, client):
    missing = client.post("/api/register", json={
        "username": "missing-consent",
        "password": "strong-password",
    })
    assert missing.status_code == 400
    assert missing.get_json()["code"] == "terms_acceptance_required"

    stale = registration_payload("stale-consent")
    stale["privacy_version"] = "old"
    response = client.post("/api/register", json=stale)
    assert response.status_code == 400
    assert response.get_json()["code"] == "privacy_acceptance_required"

    created = client.post(
        "/api/register", json=registration_payload("legal-user", ai_consent=False)
    )
    assert created.status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="legal-user").one()
        assert user.terms_version == TERMS_VERSION
        assert user.privacy_version == PRIVACY_VERSION
        assert user.ai_consent_at is None
        records = ConsentRecord.query.filter_by(user_id=user.id).order_by(ConsentRecord.id).all()
        assert [(item.document_type, item.granted) for item in records] == [
            ("terms", True),
            ("privacy", True),
            ("ai", False),
        ]


def test_existing_user_can_inspect_grant_and_revoke_ai_consent(app, client, monkeypatch):
    created = client.post(
        "/api/register", json=registration_payload("ai-choice", ai_consent=False)
    )
    assert created.status_code == 201

    blocked = client.post("/api/diet/ai_macros", json={"description": "banana"})
    assert blocked.status_code == 403
    assert blocked.get_json()["code"] == "ai_consent_required"

    current = client.get("/api/account/consents").get_json()
    assert current["terms"]["accepted"] is True
    assert current["privacy"]["accepted"] is True
    assert current["ai"]["accepted"] is False

    granted = client.put("/api/account/consents", json={"ai_consent": True})
    assert granted.status_code == 200
    assert granted.get_json()["ai"]["version"] == AI_CONSENT_VERSION
    monkeypatch.setattr(
        "src.routes.profile_routes.calculate_nutrition",
        lambda *args: {"calories": 90, "protein": 1, "carbs": 23, "fat": 0},
    )
    assert client.post(
        "/api/diet/ai_macros", json={"description": "banana 100g"}
    ).status_code == 200

    revoked = client.put("/api/account/consents", json={"ai_consent": False})
    assert revoked.status_code == 200
    assert revoked.get_json()["ai"]["accepted"] is False
    assert client.post(
        "/api/diet/ai_macros", json={"description": "banana"}
    ).get_json()["code"] == "ai_consent_required"


def test_account_deletion_requires_password_and_anonymizes_retained_records(app, client):
    assert client.post(
        "/api/register",
        json=registration_payload(
            "delete-me",
            analytics={"anonymous_id": "123e4567-e89b-42d3-a456-426614174000"},
        ),
    ).status_code == 201
    assert client.post("/api/diet", json={
        "date": "2026-08-29",
        "meal_type": "Almoço",
        "description": "Arroz",
    }).status_code == 201

    student = User(username="retained-student")
    student.set_password("strong-password")
    with app.app_context():
        user = User.query.filter_by(username="delete-me").one()
        signup_event = AnalyticsEvent.query.filter_by(event_name="signup_completed").one()
        signup_event.dedupe_key = f"return:returned_d7:{user.analytics_subject_id}:browser"
        db.session.add(AdminActionAudit(
            subject_user_id=user.id,
            action="user.banned",
            resource_type="user",
            resource_id=str(user.id),
        ))
        db.session.add(student)
        db.session.flush()
        plan = WorkoutPlan(
            user_id=student.id,
            author_user_id=user.id,
            published_by_user_id=user.id,
            title="Plano mantido pelo aluno",
            status="published",
            source="manual",
        )
        relationship = ProfessionalStudentRelationship(
            professional_user_id=user.id,
            student_user_id=student.id,
            status="active",
            invite_token_hash="a" * 64,
            invite_expires_at=datetime.utcnow() + timedelta(days=1),
            accepted_at=datetime.utcnow(),
        )
        db.session.add_all((plan, relationship))
        db.session.flush()
        db.session.add(DelegatedActionAudit(
            actor_user_id=user.id,
            subject_user_id=student.id,
            relationship_id=relationship.id,
            action="workout_plan.published",
        ))
        db.session.add(Subscription(
            user_id=user.id,
            provider="asaas",
            external_subscription_id="sub-inactive",
            status="canceled",
            plan_code="premium_student",
        ))
        db.session.add(BillingCheckout(
            user_id=user.id,
            provider="asaas",
            external_checkout_id="checkout-retained",
            plan_code="premium_student",
            payment_method="pix",
            status="completed",
        ))
        db.session.commit()
        user_id = user.id
        student_id = student.id

    assert client.delete("/api/account", json={
        "username": "delete-me",
        "password": "wrong-password",
        "confirm_delete": True,
    }).status_code == 403
    deleted = client.delete("/api/account", json={
        "username": "delete-me",
        "password": "strong-password",
        "confirm_delete": True,
    })
    assert deleted.status_code == 200
    assert client.get("/api/check_session").get_json() == {"logged_in": False}

    with app.app_context():
        assert db.session.get(User, user_id) is None
        assert DietEntry.query.filter_by(user_id=user_id).count() == 0
        retained_plan = WorkoutPlan.query.filter_by(user_id=student_id).one()
        assert retained_plan.author_user_id == student_id
        assert retained_plan.published_by_user_id == student_id
        relationship = ProfessionalStudentRelationship.query.one()
        assert relationship.professional_user_id is None
        assert relationship.status == "revoked"
        assert DelegatedActionAudit.query.one().actor_user_id is None
        assert Subscription.query.filter_by(external_subscription_id="sub-inactive").one().user_id is None
        assert BillingCheckout.query.filter_by(external_checkout_id="checkout-retained").one().user_id is None
        signup_event = AnalyticsEvent.query.filter_by(event_name="signup_completed").one()
        assert signup_event.subject_id is None
        assert signup_event.anonymous_id is None
        assert signup_event.dedupe_key is None
        admin_audit = AdminActionAudit.query.one()
        assert admin_audit.subject_user_id is None
        assert admin_audit.resource_id is None


def test_account_deletion_blocks_remote_active_subscription(app, client, monkeypatch):
    assert client.post(
        "/api/register", json=registration_payload("subscribed-delete")
    ).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="subscribed-delete").one()
        db.session.add(Subscription(
            user_id=user.id,
            provider="asaas",
            external_subscription_id="sub-remote-active",
            status="canceled",
            plan_code="premium_student",
        ))
        db.session.commit()
    app.config["ASAAS_API_KEY"] = "configured"
    monkeypatch.setattr(
        "src.routes.account_routes.get_subscription",
        lambda external_id: {"id": external_id, "status": "ACTIVE"},
    )

    blocked = client.delete("/api/account", json={
        "username": "subscribed-delete",
        "password": "strong-password",
        "confirm_delete": True,
    })
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "active_subscription"
    with app.app_context():
        assert User.query.filter_by(username="subscribed-delete").count() == 1


def test_google_only_account_can_delete_from_recent_authenticated_session(app, client, monkeypatch):
    payload = {
        "iss": "https://accounts.google.com",
        "sub": "delete-google-subject",
        "email": "delete@example.com",
        "email_verified": True,
    }
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token", lambda *args, **kwargs: payload
    )
    started = client.post("/api/auth/google", json={"credential": "google-token"})
    signup_token = started.get_json()["signup_token"]
    assert client.post("/api/auth/google", json={
        "signup_token": signup_token,
        "username": "google-delete",
        **consent_payload(),
    }).status_code == 201

    deleted = client.delete("/api/account", json={
        "username": "google-delete",
        "confirm_delete": True,
    })
    assert deleted.status_code == 200
    with app.app_context():
        assert User.query.filter_by(username="google-delete").count() == 0


def test_numeric_and_image_validation_rejects_unsafe_values(client, monkeypatch):
    assert client.post(
        "/api/register", json=registration_payload("validation-user")
    ).status_code == 201
    assert client.post("/api/diet", json={
        "date": "2026-08-29", "meal_type": "Almoço", "description": "Arroz", "calories": -1,
    }).status_code == 400
    assert client.post("/api/diet", json={
        "date": "2026-08-29", "meal_type": "Almoço", "description": "Arroz", "calories": float("nan"),
    }).status_code == 400
    assert client.post("/api/measurements", json={
        "date": "2026-08-29", "body_fat": 101,
    }).status_code == 400
    assert client.post("/api/diet/ai_macros", json={
        "description": "x" * 2001,
    }).status_code == 400
    assert client.post("/api/diet/ai_macros", json={
        "image": "not-an-object",
    }).status_code == 400
    fake_jpeg = base64.b64encode(b"not really jpeg").decode()
    assert client.post("/api/diet/ai_macros", json={
        "image": {"mime_type": "image/jpeg", "data": fake_jpeg},
    }).status_code == 400

    monkeypatch.setattr(
        "src.routes.profile_routes.calculate_nutrition",
        lambda *args: {"calories": 100, "protein": 2, "carbs": 20, "fat": 1},
    )
    jpeg = base64.b64encode(b"\xff\xd8\xffminimal").decode()
    assert client.post("/api/diet/ai_macros", json={
        "image": {"mime_type": "image/jpeg", "data": jpeg},
    }).status_code == 200


def test_legal_pages_are_explicit_drafts_with_placeholders(client):
    for path in ("/terms.html", "/privacy.html"):
        response = client.get(path)
        assert response.status_code == 200
        assert "RASCUNHO JURÍDICO" in response.get_data(as_text=True)
        assert "[" in response.get_data(as_text=True)


def test_app_wide_csrf_covers_logout_billing_admin_and_exempts_webhook(tmp_path):
    class CsrfConfig(TestConfig):
        CSRF_PROTECTION = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'csrf-launch.db'}"

    app = create_app(CsrfConfig)
    with app.app_context():
        db.create_all()
    client = app.test_client()
    registered = client.post("/api/register", json=registration_payload("csrf-admin"))
    token = registered.get_json()["csrf_token"]

    assert client.post("/api/logout").status_code == 403
    assert client.post("/api/billing/checkout", json={"plan_code": "free"}).status_code == 403

    with app.app_context():
        admin = User.query.filter_by(username="csrf-admin").one()
        admin.is_admin = True
        target = User(username="csrf-target")
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    assert client.post(f"/api/admin/users/{target_id}/ban").status_code == 403
    assert client.post(
        f"/api/admin/users/{target_id}/ban", headers={"X-CSRF-Token": token}
    ).status_code == 200
    assert client.post(
        "/api/billing/checkout",
        headers={"X-CSRF-Token": token},
        json={"plan_code": "free"},
    ).status_code == 400

    webhook = client.post(
        "/api/webhooks/asaas",
        headers={"asaas-access-token": CsrfConfig.ASAAS_WEBHOOK_TOKEN},
        json={"id": "evt-csrf-exempt", "event": "UNKNOWN"},
    )
    assert webhook.status_code == 200
    assert client.post("/api/logout", headers={"X-CSRF-Token": token}).status_code == 200

    with app.app_context():
        db.session.remove()
        db.drop_all()
