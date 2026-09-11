from datetime import datetime, timedelta

import pytest

from src.models.user import BillingCheckout, BillingEvent, ProfessionalApplication, Subscription, User, db
from src.services.asaas import AsaasError, create_checkout
from src.services.billing_reconciliation import reconcile_asaas
from tests.helpers import registration_payload


WEBHOOK_HEADERS = {"asaas-access-token": "test-webhook-token-0123456789abcdef", "Content-Type": "application/json"}


def register(client, username):
    return client.post("/api/register", json=registration_payload(username))


def enable_billing(app):
    app.config["ASAAS_API_KEY"] = "test-asaas-key"
    app.config["BILLING_ENABLED"] = True


def make_admin(app, username):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.is_admin = True
        db.session.commit()


def mock_checkout(monkeypatch):
    captured = {"calls": 0}

    def fake_create(plan, payment_method, public_base_url, external_reference):
        captured["calls"] += 1
        captured.update({
            "plan": plan["code"],
            "payment_method": payment_method,
            "external_reference": external_reference,
            "public_base_url": public_base_url,
        })
        return {"id": "checkout-123", "link": "https://sandbox.asaas.com/checkoutSession/show/checkout-123"}

    monkeypatch.setattr("src.routes.billing_routes.create_checkout", fake_create)
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


def checkout_event(event, checkout_id, event_id):
    return {
        "id": event_id,
        "event": event,
        "checkout": {"id": checkout_id},
    }


def _create_active_checkout(app, client, monkeypatch):
    enable_billing(app)
    mock_checkout(monkeypatch)
    register(client, "subscriber")
    response = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "credit_card"},
    )
    assert response.status_code == 201
    with app.app_context():
        checkout = BillingCheckout.query.one()
        checkout.external_checkout_id = "checkout-123"
        db.session.commit()
    return "checkout-123"


def _create_paid_subscription(app, client, monkeypatch):
    checkout = _create_active_checkout(app, client, monkeypatch)
    assert client.post(
        "/api/webhooks/asaas",
        json=checkout_created_event(checkout),
        headers=WEBHOOK_HEADERS,
    ).status_code == 200
    monkeypatch.setattr(
        "src.routes.billing_routes.fetch_asaas_subscription",
        lambda subscription_id: {
            "id": subscription_id,
            "status": "ACTIVE",
            "nextDueDate": "2026-09-25",
        },
    )
    assert client.post(
        "/api/webhooks/asaas",
        json={
            "id": "evt_paid_subscription",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": "pay_subscription",
                "subscription": "sub_abc",
                "status": "RECEIVED",
                "paymentDate": "2026-08-25",
            },
        },
        headers=WEBHOOK_HEADERS,
    ).status_code == 200
    return checkout


def test_checkout_requires_login_and_valid_plan(client):
    assert client.post("/api/billing/checkout", json={}).status_code == 401
    register(client, "buyer")
    assert client.post(
        "/api/billing/checkout", json={"plan_code": "free"}
    ).status_code == 400
    assert client.post(
        "/api/billing/checkout", json={"plan_code": "premium_student", "payment_method": "boleto"}
    ).status_code == 400
    assert client.post(
        "/api/billing/checkout", json={"plan_code": "professional_complete", "payment_method": "boleto"}
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
    assert "checkout_id" not in response.get_json()
    assert captured["plan"] == "premium_student"
    assert captured["payment_method"] == "pix"
    assert captured["external_reference"].startswith("dt-checkout-")
    with app.app_context():
        checkout = BillingCheckout.query.one()
        assert checkout.external_checkout_id == "checkout-123"
        assert checkout.external_reference == captured["external_reference"]
        assert checkout.checkout_url.endswith("checkoutSession/show/checkout-123")
        assert checkout.status == "pending"
        assert checkout.plan_code == "premium_student"


def test_asaas_checkout_callback_urls_describe_all_return_states(monkeypatch):
    captured = {}

    def fake_request(method, path, payload, idempotency_key=None):
        captured.update({"method": method, "path": path, "payload": payload, "key": idempotency_key})
        return {"id": "checkout-123", "link": "https://sandbox.asaas.com/checkout-123"}

    monkeypatch.setattr("src.services.asaas._request", fake_request)
    create_checkout(
        {"name": "Premium", "price_brl": 29.9},
        "credit_card",
        "https://fit.example",
        "checkout-reference",
    )

    assert captured["payload"]["callback"] == {
        "successUrl": "https://fit.example/?billing=success",
        "cancelUrl": "https://fit.example/?billing=cancel",
        "expiredUrl": "https://fit.example/?billing=expired",
    }
    assert captured["payload"]["billingTypes"] == ["CREDIT_CARD"]
    assert captured["payload"]["chargeTypes"] == ["RECURRENT"]
    assert captured["payload"]["subscription"]["cycle"] == "MONTHLY"


def test_asaas_pix_checkout_is_detached_and_not_recurring(monkeypatch):
    captured = {}

    def fake_request(method, path, payload, idempotency_key=None):
        captured.update({"method": method, "path": path, "payload": payload})
        return {"id": "pix-checkout", "link": "https://sandbox.asaas.com/pix-checkout"}

    monkeypatch.setattr("src.services.asaas._request", fake_request)
    create_checkout(
        {"name": "Premium", "price_brl": 20},
        "pix",
        "https://fit.example",
        "pix-reference",
    )

    assert captured["payload"]["billingTypes"] == ["PIX"]
    assert captured["payload"]["chargeTypes"] == ["DETACHED"]
    assert "subscription" not in captured["payload"]


def test_repeat_checkout_returns_existing_provider_session(app, client, monkeypatch):
    enable_billing(app)
    captured = mock_checkout(monkeypatch)
    register(client, "repeat-buyer")

    first = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )
    repeated = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.get_json() == {
        "checkout_url": first.get_json()["checkout_url"],
        "existing": True,
    }
    assert captured["calls"] == 1
    with app.app_context():
        assert BillingCheckout.query.count() == 1


def test_pending_checkout_blocks_a_second_plan(app, client, monkeypatch):
    enable_billing(app)
    mock_checkout(monkeypatch)
    register(client, "multi-plan-buyer")
    with app.app_context():
        user = User.query.filter_by(username="multi-plan-buyer").one()
        user.is_professional = True
        user.professional_scope = "both"
        db.session.add(ProfessionalApplication(
            user_id=user.id,
            plan_code="professional_complete",
            full_name="Professional Buyer",
            profession="personal_trainer",
            registration_number="CREF 123",
            status="approved",
        ))
        db.session.commit()

    assert client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student"},
    ).status_code == 201
    blocked = client.post(
        "/api/billing/checkout",
        json={"plan_code": "professional_complete"},
    )

    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "checkout_pending"
    with app.app_context():
        assert BillingCheckout.query.count() == 1


def test_checkout_provider_retry_reuses_persisted_operation(app, client, monkeypatch):
    enable_billing(app)
    register(client, "retry-buyer")
    references = []

    def flaky_create(plan, payment_method, public_base_url, external_reference):
        checkout = BillingCheckout.query.one()
        assert checkout.status == "creating"
        assert checkout.external_reference == external_reference
        references.append(external_reference)
        if len(references) == 1:
            raise AsaasError("provider unavailable")
        return {"id": "checkout-retried", "link": "https://example.test/checkout-retried"}

    monkeypatch.setattr("src.routes.billing_routes.create_checkout", flaky_create)
    failed = client.post("/api/billing/checkout", json={"plan_code": "premium_student"})
    retried = client.post("/api/billing/checkout", json={"plan_code": "premium_student"})

    assert failed.status_code == 502
    assert retried.status_code == 201
    assert references == [references[0], references[0]]
    with app.app_context():
        assert BillingCheckout.query.count() == 1
        assert BillingCheckout.query.one().status == "pending"


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
    assert status["is_premium"] is False
    assert status["plan_code"] == "free"
    with app.app_context():
        assert BillingCheckout.query.one().status == "completed"
        assert Subscription.query.one().status == "pending"

    blocked_checkout = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student"},
    )
    assert blocked_checkout.status_code == 409
    assert blocked_checkout.get_json()["code"] == "subscription_pending"

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
    status = client.get("/api/subscription").get_json()
    assert status["is_premium"] is True
    assert status["plan_code"] == "premium_student"
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


def test_unmatched_webhook_can_be_retried_after_checkout_reconciliation(app, client):
    external_reference = "dt-checkout-reconciliation-test"
    event = checkout_created_event(None)
    event["id"] = "evt_unmatched_then_retried"
    event["subscription"].pop("checkoutSession")
    event["subscription"]["externalReference"] = external_reference

    unmatched = client.post("/api/webhooks/asaas", json=event, headers=WEBHOOK_HEADERS)
    assert unmatched.status_code == 409
    assert unmatched.get_json() == {"received": False, "retryable": True}
    with app.app_context():
        failed_event = BillingEvent.query.one()
        assert failed_event.processing_status == "failed"
        assert failed_event.attempt_count == 1
        assert Subscription.query.count() == 0
        user = User(username="reconciled-buyer")
        user.set_password("strong-password")
        db.session.add(user)
        db.session.flush()
        db.session.add(BillingCheckout(
            user_id=user.id,
            provider="asaas",
            external_reference=external_reference,
            external_checkout_id="checkout-late",
            checkout_url="https://example.test/checkout-late",
            plan_code="premium_student",
            payment_method="credit_card",
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=1),
        ))
        db.session.commit()

    reconciled = client.post("/api/webhooks/asaas", json=event, headers=WEBHOOK_HEADERS)
    assert reconciled.status_code == 200
    with app.app_context():
        assert BillingEvent.query.count() == 1
        assert BillingEvent.query.one().processing_status == "processed"
        assert BillingEvent.query.one().attempt_count == 2
        assert Subscription.query.one().status == "pending"
        assert BillingCheckout.query.one().status == "completed"


def test_webhook_inbox_discards_unapproved_provider_payload_fields(app, client):
    event = checkout_created_event("missing-checkout")
    event["id"] = "evt_safe_payload"
    event["subscription"]["email"] = "payer@example.com"
    event["subscription"]["creditCardNumber"] = "4111111111111111"

    assert client.post(
        "/api/webhooks/asaas", json=event, headers=WEBHOOK_HEADERS
    ).status_code == 409
    with app.app_context():
        payload = BillingEvent.query.one().payload
        assert "email" not in payload["subscription"]
        assert "creditCardNumber" not in payload["subscription"]


def test_pix_checkout_paid_grants_thirty_days_once(app, client, monkeypatch):
    enable_billing(app)
    mock_checkout(monkeypatch)
    register(client, "pix-buyer")
    response = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )
    assert response.status_code == 201
    with app.app_context():
        checkout_id = BillingCheckout.query.one().external_checkout_id

    paid = client.post(
        "/api/webhooks/asaas",
        json=checkout_event("CHECKOUT_PAID", checkout_id, "evt_pix_paid"),
        headers=WEBHOOK_HEADERS,
    )
    assert paid.status_code == 200
    with app.app_context():
        checkout = BillingCheckout.query.one()
        access = Subscription.query.filter_by(provider="asaas_pix").one()
        first_end = access.current_period_end
        assert checkout.status == "completed"
        assert access.status == "active"
        assert 29 <= (first_end - datetime.utcnow()).days <= 30

    duplicate_id = client.post(
        "/api/webhooks/asaas",
        json=checkout_event("CHECKOUT_PAID", checkout_id, "evt_pix_paid_again"),
        headers=WEBHOOK_HEADERS,
    )
    assert duplicate_id.status_code == 200
    with app.app_context():
        assert Subscription.query.filter_by(provider="asaas_pix").one().current_period_end == first_end


@pytest.mark.parametrize(
    ("event_name", "expected_status"),
    (("CHECKOUT_CANCELED", "canceled"), ("CHECKOUT_EXPIRED", "expired")),
)
def test_pix_checkout_status_events_do_not_grant_access(
    app, client, monkeypatch, event_name, expected_status
):
    enable_billing(app)
    mock_checkout(monkeypatch)
    register(client, "pix-canceled")
    response = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )
    assert response.status_code == 201
    with app.app_context():
        checkout_id = BillingCheckout.query.one().external_checkout_id

    canceled = client.post(
        "/api/webhooks/asaas",
        json=checkout_event(event_name, checkout_id, f"evt_pix_{expected_status}"),
        headers=WEBHOOK_HEADERS,
    )

    assert canceled.status_code == 200
    with app.app_context():
        assert BillingCheckout.query.one().status == expected_status
        assert Subscription.query.count() == 0


def test_pix_renewal_opens_in_last_seven_days_and_extends_current_end(app, client, monkeypatch):
    enable_billing(app)
    checkout_ids = iter(("pix-first", "pix-renewal"))

    def fake_create(plan, payment_method, public_base_url, external_reference):
        checkout_id = next(checkout_ids)
        return {"id": checkout_id, "link": f"https://sandbox.asaas.com/{checkout_id}"}

    monkeypatch.setattr("src.routes.billing_routes.create_checkout", fake_create)
    register(client, "pix-renewal-buyer")
    first = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )
    assert first.status_code == 201
    with app.app_context():
        first_checkout_id = BillingCheckout.query.one().external_checkout_id
    client.post(
        "/api/webhooks/asaas",
        json=checkout_event("CHECKOUT_PAID", first_checkout_id, "evt_pix_first"),
        headers=WEBHOOK_HEADERS,
    )

    blocked = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )
    assert blocked.status_code == 409
    assert blocked.get_json()["pix_renewal_available_at"]

    with app.app_context():
        access = Subscription.query.filter_by(provider="asaas_pix").one()
        access.current_period_end = datetime.utcnow() + timedelta(days=6)
        db.session.commit()
        previous_end = access.current_period_end
        db.session.expire_all()

    renewal = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "pix"},
    )
    assert renewal.status_code == 201, renewal.get_json()
    with app.app_context():
        renewal_checkout_id = BillingCheckout.query.filter_by(status="pending").one().external_checkout_id
    client.post(
        "/api/webhooks/asaas",
        json=checkout_event("CHECKOUT_PAID", renewal_checkout_id, "evt_pix_renewal"),
        headers=WEBHOOK_HEADERS,
    )
    with app.app_context():
        access = Subscription.query.filter_by(provider="asaas_pix").one()
        assert access.current_period_end == previous_end + timedelta(days=30)


def test_cancel_calls_provider_and_keeps_paid_period(app, client, monkeypatch):
    _create_paid_subscription(app, client, monkeypatch)

    deleted = {}
    def fake_delete(subscription_id):
        deleted["id"] = subscription_id
        return {"deleted": True, "id": subscription_id}

    monkeypatch.setattr("src.routes.billing_routes.delete_subscription", fake_delete)
    response = client.post("/api/billing/cancel")
    assert response.status_code == 200
    assert deleted["id"] == "sub_abc"
    assert "acesso mantido" in response.get_json()["message"].lower()
    assert client.post("/api/billing/cancel").status_code == 200


def test_cancel_provider_failure_keeps_subscription_active(app, client, monkeypatch):
    _create_paid_subscription(app, client, monkeypatch)

    def failed_delete(subscription_id):
        raise AsaasError("provider unavailable")

    monkeypatch.setattr("src.routes.billing_routes.delete_subscription", failed_delete)
    response = client.post("/api/billing/cancel")

    assert response.status_code == 502
    assert response.get_json()["error"] == "Não foi possível cancelar a assinatura agora."
    with app.app_context():
        assert Subscription.query.one().status == "active"


def test_older_payment_event_does_not_replace_current_paid_period(app, client, monkeypatch):
    _create_paid_subscription(app, client, monkeypatch)
    older = client.post(
        "/api/webhooks/asaas",
        json={
            "id": "evt_older_payment",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": "pay_older",
                "subscription": "sub_abc",
                "status": "RECEIVED",
                "paymentDate": "2026-07-25",
            },
        },
        headers=WEBHOOK_HEADERS,
    )

    assert older.status_code == 200
    with app.app_context():
        subscription = Subscription.query.one()
        assert subscription.last_payment_id == "pay_subscription"
        assert subscription.current_period_start == datetime(2026, 8, 25)


def test_reconciliation_does_not_reactivate_canceled_subscription(app, monkeypatch):
    with app.app_context():
        user = User(username="canceled-reconciliation")
        user.set_password("strong-password")
        db.session.add(user)
        db.session.flush()
        subscription = Subscription(
            user_id=user.id,
            provider="asaas",
            external_subscription_id="sub_canceled",
            last_payment_id="pay_current",
            status="canceled",
            plan_code="premium_student",
            current_period_start=datetime(2026, 8, 1),
            current_period_end=datetime(2026, 9, 1),
        )
        db.session.add(subscription)
        db.session.commit()

        monkeypatch.setattr(
            "src.services.billing_reconciliation.get_subscription",
            lambda subscription_id: {
                "id": subscription_id,
                "status": "ACTIVE",
                "nextDueDate": "2026-10-01",
            },
        )
        monkeypatch.setattr(
            "src.services.billing_reconciliation.list_subscription_payments",
            lambda subscription_id: {
                "data": [{
                    "id": "pay_newer",
                    "status": "RECEIVED",
                    "paymentDate": "2026-09-01",
                }],
            },
        )

        result = reconcile_asaas()
        db.session.refresh(subscription)
        assert result["updated"] == 0
        assert subscription.status == "canceled"
        assert subscription.last_payment_id == "pay_current"


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
