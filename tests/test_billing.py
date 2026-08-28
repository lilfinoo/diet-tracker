from datetime import datetime

from src.models.user import BillingCheckout, ProfessionalApplication, Subscription, User, db


WEBHOOK_HEADERS = {"asaas-access-token": "test-webhook-token-0123456789abcdef", "Content-Type": "application/json"}


def register(client, username):
    return client.post("/api/register", json={"username": username, "password": "strong-password"})


def enable_billing(app):
    app.config["ASAAS_API_KEY"] = "test-asaas-key"


def make_admin(app, username):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.is_admin = True
        db.session.commit()


def mock_checkout(monkeypatch):
    captured = {}

    def fake_create(plan, payment_method, public_base_url, external_reference):
        captured.update({
            "plan": plan["code"],
            "payment_method": payment_method,
            "external_reference": external_reference,
            "public_base_url": public_base_url,
        })
        return {"id": "checkout-123", "link": "https://sandbox.asaas.com/checkoutSession/show/checkout-123"}

    monkeypatch.setattr("src.routes.billing_routes.create_recurring_checkout", fake_create)
    return captured


def checkout_created_event(checkout_reference):
    return {
        "id": "evt_subscription_created",
        "event": "SUBSCRIPTION_CREATED",
        "subscription": {
            "id": "sub_abc",
            "customer": "cus_123",
            "status": "ACTIVE",
            "nextDueDate": "2026-09-25",
            "checkoutSession": checkout_reference,
        },
    }


def _create_active_checkout(app, client, monkeypatch):
    enable_billing(app)
    mock_checkout(monkeypatch)
    register(client, "subscriber")
    response = client.post("/api/billing/checkout", json={"plan_code": "premium_student"})
    assert response.status_code == 201
    with app.app_context():
        checkout = BillingCheckout.query.one()
        checkout.external_checkout_id = "checkout-123"
        db.session.commit()
    return "checkout-123"


def test_checkout_requires_login_and_valid_plan(client):
    assert client.post("/api/billing/checkout", json={}).status_code == 401
    register(client, "buyer")
    assert client.post(
        "/api/billing/checkout", json={"plan_code": "free"}
    ).status_code == 400
    assert client.post(
        "/api/billing/checkout", json={"plan_code": "premium_student", "payment_method": "boleto"}
    ).status_code == 400


def test_premium_checkout_created_with_provider_payload(app, client, monkeypatch):
    enable_billing(app)
    captured = mock_checkout(monkeypatch)
    register(client, "buyer")
    response = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )
    assert response.status_code == 201
    assert response.get_json()["checkout_url"].endswith("checkoutSession/show/checkout-123")
    assert captured["plan"] == "premium_student"
    assert captured["payment_method"] == "pix"
    assert captured["external_reference"].startswith("dt-checkout-")
    with app.app_context():
        checkout = BillingCheckout.query.one()
        assert checkout.external_checkout_id == "checkout-123"
        assert checkout.plan_code == "premium_student"


def test_professional_checkout_requires_approval_first(app, client, monkeypatch):
    enable_billing(app)
    mock_checkout(monkeypatch)
    register(client, "trainer")
    blocked = client.post("/api/billing/checkout", json={"plan_code": "professional_complete"})
    assert blocked.status_code == 403
    assert blocked.get_json()["code"] == "approval_required"

    with app.app_context():
        user = User.query.filter_by(username="trainer").one()
        application = ProfessionalApplication(
            user_id=user.id,
            plan_code="professional_complete",
            full_name="Treinador Completo",
            profession="personal_trainer",
            registration_number="CREF 000000-G/SP",
        )
        db.session.add(application)
        db.session.commit()
        application_id = application.id

    admin_client = app.test_client()
    register(admin_client, "admin")
    make_admin(app, "admin")
    review = admin_client.post(
        f"/api/admin/professional-applications/{application_id}/review",
        json={"decision": "approve"},
    )
    assert review.status_code == 200

    allowed = client.post("/api/billing/checkout", json={"plan_code": "professional_complete"})
    assert allowed.status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="trainer").one()
        assert user.professional_scope == "both"


def test_webhook_rejects_missing_or_wrong_token(client):
    event = checkout_created_event("missing")
    assert client.post("/api/webhooks/asaas", json=event).status_code == 401
    wrong = dict(WEBHOOK_HEADERS, **{"asaas-access-token": "wrong-token-value-wrong-token-value"})
    assert client.post("/api/webhooks/asaas", json=event, headers=wrong).status_code == 401


def test_webhook_full_lifecycle_is_idempotent(app, client, monkeypatch):
    checkout = _create_active_checkout(app, client, monkeypatch)

    created = client.post(
        "/api/webhooks/asaas",
        json=checkout_created_event(checkout),
        headers=WEBHOOK_HEADERS,
    )
    assert created.status_code == 200
    status = client.get("/api/subscription").get_json()
    assert status["is_premium"] is True
    assert status["plan_code"] == "premium_student"

    # Duplicate delivery of the same event must be ignored.
    duplicate = client.post(
        "/api/webhooks/asaas",
        json=checkout_created_event(checkout),
        headers=WEBHOOK_HEADERS,
    )
    assert duplicate.status_code == 200
    with app.app_context():
        from src.models.user import BillingEvent
        assert BillingEvent.query.count() == 1
        assert Subscription.query.count() == 1

    def fake_get_subscription(subscription_id):
        assert subscription_id == "sub_abc"
        return {"id": "sub_abc", "status": "ACTIVE", "nextDueDate": "2026-09-25"}

    monkeypatch.setattr("src.routes.billing_routes.fetch_asaas_subscription", fake_get_subscription)
    paid = client.post(
        "/api/webhooks/asaas",
        json={
            "id": "evt_payment_received",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": "pay_1",
                "subscription": "sub_abc",
                "status": "RECEIVED",
                "dueDate": "2026-08-25",
                "paymentDate": "2026-08-24",
            },
        },
        headers=WEBHOOK_HEADERS,
    )
    assert paid.status_code == 200
    with app.app_context():
        subscription = Subscription.query.one()
        assert subscription.current_period_start == datetime(2026, 8, 24)
        assert subscription.current_period_end == datetime(2026, 9, 25)

    inactivated = client.post(
        "/api/webhooks/asaas",
        json={
            "id": "evt_subscription_deleted",
            "event": "SUBSCRIPTION_INACTIVATED",
            "subscription": {"id": "sub_abc"},
        },
        headers=WEBHOOK_HEADERS,
    )
    assert inactivated.status_code == 200
    # Access continues until the already paid period ends.
    still_premium = client.get("/api/subscription")
    assert still_premium.get_json()["is_premium"] is True


def test_cancel_calls_provider_and_keeps_paid_period(app, client, monkeypatch):
    checkout = _create_active_checkout(app, client, monkeypatch)
    client.post(
        "/api/webhooks/asaas",
        json=checkout_created_event(checkout),
        headers=WEBHOOK_HEADERS,
    )

    deleted = {}
    def fake_delete(subscription_id):
        deleted["id"] = subscription_id
        return {"deleted": True, "id": subscription_id}

    monkeypatch.setattr("src.routes.billing_routes.delete_subscription", fake_delete)
    response = client.post("/api/billing/cancel")
    assert response.status_code == 200
    assert deleted["id"] == "sub_abc"
    assert "acesso mantido" in response.get_json()["message"].lower()


def test_application_validation_and_rejection(app, client):
    register(client, "nutri")
    missing = client.post("/api/professional-application", json={"plan_code": "professional_single"})
    assert missing.status_code == 400

    created = client.post("/api/professional-application", json={
        "plan_code": "professional_single",
        "full_name": "Nutricionista Teste",
        "profession": "nutritionist",
        "registration_number": "CRN 12345",
    })
    assert created.status_code == 201

    duplicate = client.post("/api/professional-application", json={
        "plan_code": "professional_single",
        "full_name": "Nutricionista Teste",
        "profession": "nutritionist",
        "registration_number": "CRN 12345",
    })
    assert duplicate.status_code == 409

    admin_client = app.test_client()
    register(admin_client, "admin")
    make_admin(app, "admin")
    listing = admin_client.get("/api/admin/professional-applications?status=pending")
    items = listing.get_json()
    assert len(items) == 1
    application_id = items[0]["id"]

    rejected = admin_client.post(
        f"/api/admin/professional-applications/{application_id}/review",
        json={"decision": "reject", "note": "Registro não localizado."},
    )
    assert rejected.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username="nutri").one()
        assert user.is_professional is False
        application = ProfessionalApplication.query.one()
        assert application.status == "rejected"
        assert application.admin_note == "Registro não localizado."
