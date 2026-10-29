from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.user import (
    Affiliate, AffiliateCommission, Referral, ReferralCode, ReferralReward,
    Subscription, User, db,
)
from tests.helpers import registration_payload


def account(app, name, admin=False):
    client = app.test_client()
    result = client.post("/api/register", json=registration_payload(name))
    assert result.status_code == 201, result.json
    with app.app_context():
        user = User.query.filter_by(username=name).one()
        user.is_admin = admin
        db.session.commit()
        user_id = user.id
    return client, user_id


def partner(app, linked_user_id=None):
    with app.app_context():
        entry = Affiliate(name="Ana privada", public_name="Ana", email="ana@private.example", user_id=linked_user_id)
        db.session.add(entry)
        db.session.flush()
        db.session.add(ReferralCode(code="ANA10", affiliate_id=entry.id, kind="affiliate"))
        db.session.commit()
        return entry.id


def test_affiliate_signup_and_in_app_attribution_are_separate_from_monthly_gift(app):
    affiliate_id = partner(app)
    first = app.test_client()
    response = first.post("/api/register", json=registration_payload("ana-signup", referral_code=" ana10 "))
    assert response.status_code == 201, response.json
    second, _ = account(app, "ana-apply")
    assert second.post("/api/referrals/apply", json={"code": "ana10"}).status_code == 200
    for client in (first, second):
        attribution = client.get("/api/referrals/attribution").json["attribution"]
        assert attribution["kind"] == "affiliate" and attribution["public_name"] == "Ana"
        assert client.get("/api/referrals").json["qualified_invites"] == 0
    with app.app_context():
        entries = Referral.query.filter_by(affiliate_id=affiliate_id).all()
        assert {entry.source for entry in entries} == {"signup", "app"}
        assert len(entries) == 2
        assert ReferralReward.query.count() == 0
    ordinary, _ = account(app, "ordinary-owner")
    ordinary_code = ordinary.get("/api/referrals").json["code"]
    for index in range(3):
        assert app.test_client().post("/api/register", json=registration_payload(f"ordinary-{index}", referral_code=ordinary_code)).status_code == 201
    assert ordinary.get("/api/referrals").json["qualified_invites"] == 3
    assert ordinary.get("/api/referrals").json["rewarded_this_month"] is True


def test_application_is_idempotent_cannot_switch_and_preserves_disabled_history(app):
    affiliate_id = partner(app)
    client, user_id = account(app, "new-customer")
    assert client.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 200
    assert client.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 200
    with app.app_context():
        other = Affiliate(name="Bia", public_name="Bia")
        db.session.add(other)
        db.session.flush()
        db.session.add(ReferralCode(code="BIA10", affiliate_id=other.id, kind="affiliate"))
        db.session.commit()
    assert client.post("/api/referrals/apply", json={"code": "BIA10"}).status_code == 409
    with app.app_context():
        db.session.get(Affiliate, affiliate_id).active = False
        db.session.get(ReferralCode, "ANA10").active = False
        db.session.commit()
        assert Referral.query.filter_by(invitee_user_id=user_id).count() == 1
    assert client.get("/api/referrals/attribution").json["attribution"]["public_name"] == "Ana"
    fresh, _ = account(app, "disabled-code-customer")
    assert fresh.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 400


def test_linked_partner_cannot_use_own_code_and_invalid_signup_rolls_back(app):
    client, user_id = account(app, "influencer")
    partner(app, user_id)
    assert client.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 400
    response = app.test_client().post("/api/register", json=registration_payload("rejected-account", referral_code="BADCODE"))
    assert response.status_code == 400
    with app.app_context():
        assert User.query.filter_by(username="rejected-account").first() is None
        assert Referral.query.count() == 0


def test_admin_permissions_global_code_collision_and_finance_defaults(app):
    regular, _ = account(app, "regular-affiliate")
    admin, _ = account(app, "affiliate-admin", admin=True)
    assert app.test_client().get("/api/admin/affiliates").status_code == 401
    assert regular.get("/api/admin/affiliates").status_code == 403
    code = regular.get("/api/referrals").json["code"]
    collision = admin.post("/api/admin/affiliates", json={"name": "Ana", "code": code.lower()})
    assert collision.status_code == 409
    with app.app_context():
        assert Affiliate.query.count() == 0
    result = admin.post("/api/admin/affiliates", json={"name": "Ana", "code": "ANA10"})
    assert result.status_code == 201, result.json
    with app.app_context():
        affiliate = Affiliate.query.one()
        assert float(affiliate.first_rate) == 50 and float(affiliate.renewal_rate) == 10
        assert affiliate.recurring_months == 12
        assert affiliate.annual_first_rate is affiliate.annual_renewal_rate is None
        assert AffiliateCommission.query.count() == 0


@pytest.mark.parametrize("field,value", [("first_rate", -1), ("renewal_rate", 101), ("first_rate", "NaN"), ("annual_first_rate", 100.001), ("recurring_months", -1), ("active", "true")])
def test_invalid_affiliate_configuration_is_atomic(app, field, value):
    admin, _ = account(app, "invalid-admin", admin=True)
    response = admin.post("/api/admin/affiliates", json={"name": "Ana", field: value})
    assert response.status_code == 400
    with app.app_context():
        assert Affiliate.query.count() == ReferralCode.query.filter_by(kind="affiliate").count() == 0


def test_influencer_dashboard_only_exposes_aggregate_data_and_no_fake_payments(app):
    influencer, user_id = account(app, "private-influencer")
    affiliate_id = partner(app, user_id)
    customer = app.test_client()
    assert customer.post("/api/register", json=registration_payload("secret-customer", referral_code="ANA10")).status_code == 201
    with app.app_context():
        referred = User.query.filter_by(username="secret-customer").one()
        db.session.add(Subscription(user_id=referred.id, provider="revenuecat", external_subscription_id="active-snapshot", status="active", plan_code="premium_student", current_period_end=datetime.utcnow() + timedelta(days=20)))
        db.session.commit()
    result = influencer.get("/api/affiliates/me")
    assert result.status_code == 200, result.json
    payload = result.json
    assert payload["financial_tracking_enabled"] is False
    assert payload["metrics"]["registrations"] == 1
    assert payload["metrics"]["active_subscribers"] == 1
    assert payload["metrics"]["confirmed_paying_users"] == 0
    assert payload["metrics"]["commissions_pending"] == []
    assert "private.example" not in result.get_data(as_text=True)
    assert "secret-customer" not in result.get_data(as_text=True)
    assert not ({"email", "name", "notes", "user_id", "referrals", "users"} & payload.keys())
    with app.app_context():
        assert AffiliateCommission.query.filter_by(affiliate_id=affiliate_id).count() == 0


def test_database_guards_against_retried_attribution_and_financial_duplicates(app):
    affiliate_id = partner(app)
    client, user_id = account(app, "constraint-customer")
    assert client.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 200
    with app.app_context():
        db.session.add(Referral(invitee_user_id=user_id, affiliate_id=affiliate_id, code="ANA10", kind="affiliate"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert Referral.query.filter_by(invitee_user_id=user_id).count() == 1
        def transaction(environment="production", **values):
            return AffiliateCommission(affiliate_id=affiliate_id, user_id=user_id, provider="revenuecat", transaction_id="transaction-1", environment=environment, kind="initial", currency="BRL", rate=50, occurred_at=datetime.utcnow(), **values)
        db.session.add(transaction())
        db.session.commit()
        db.session.add(transaction())
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.add(transaction(environment="sandbox"))
        db.session.commit()
        assert AffiliateCommission.query.count() == 2
        db.session.add(AffiliateCommission(affiliate_id=affiliate_id, provider="revenuecat", transaction_id="invalid-rate", environment="production", kind="initial", currency="BRL", rate=101, occurred_at=datetime.utcnow()))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert AffiliateCommission.query.count() == 2


def test_affiliate_routes_enforce_csrf_and_admin_code_controls(app):
    app.config["CSRF_PROTECTION"] = True
    admin, _ = account(app, "csrf-affiliate-admin", admin=True)
    token = admin.get("/api/check_session").json["csrf_token"]
    assert admin.post("/api/admin/affiliates", json={"name": "Ana"}).status_code == 403
    result = admin.post("/api/admin/affiliates", headers={"X-CSRF-Token": token}, json={"name": "Ana", "code": "ANA10"})
    assert result.status_code == 201, result.json
    affiliate_id = result.json["id"]
    assert admin.patch(f"/api/admin/affiliates/{affiliate_id}", json={"active": False}).status_code == 403
    headers = {"X-CSRF-Token": token}
    assert admin.post(f"/api/admin/affiliates/{affiliate_id}/codes", headers=headers, json={"code": "ANA20"}).status_code == 201
    assert admin.patch(f"/api/admin/affiliates/{affiliate_id}/codes/ANA20", headers=headers, json={"active": False}).status_code == 200
    with app.app_context():
        assert db.session.get(ReferralCode, "ANA20").active is False
    fresh, _ = account(app, "csrf-customer")
    assert fresh.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 403
    customer_token = fresh.get("/api/check_session").json["csrf_token"]
    assert fresh.post("/api/referrals/apply", headers={"X-CSRF-Token": customer_token}, json={"code": "ANA10"}).status_code == 200
    for method, path in (("get", "/api/referrals/attribution"), ("post", "/api/referrals/apply"), ("get", "/api/affiliates/me")):
        assert getattr(app.test_client(), method)(path, json={"code": "ANA10"} if method == "post" else None).status_code == 401


@pytest.mark.parametrize("provider,status", [
    ("revenuecat", "active"), ("revenuecat", "expired"), ("revenuecat", "trialing"),
    ("revenuecat", "canceled"), ("asaas", "pending"), ("asaas", "expired"),
])
def test_existing_accounts_with_subscription_history_can_apply_partner(app, provider, status):
    affiliate_id = partner(app)
    client, user_id = account(app, "already-subscribed")
    with app.app_context():
        user = db.session.get(User, user_id)
        user.created_at = datetime(2025, 1, 1)
        subscription = Subscription(user_id=user_id, provider=provider,
            external_subscription_id="existing-purchase", status=status,
            plan_code="premium_student", current_period_end=datetime.utcnow() + timedelta(days=10))
        db.session.add(subscription)
        db.session.commit()
        subscription_id, end = subscription.id, subscription.current_period_end
    assert client.get("/api/referrals/attribution").json["can_apply_affiliate"] is True
    assert client.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 200
    with app.app_context():
        entry = Referral.query.filter_by(invitee_user_id=user_id, kind="affiliate").one()
        assert entry.affiliate_id == affiliate_id
        assert entry.created_at > datetime(2025, 1, 1)
        subscription = db.session.get(Subscription, subscription_id)
        assert subscription.status == status and subscription.current_period_end == end
        assert Subscription.query.filter_by(user_id=user_id).count() == 1
        assert AffiliateCommission.query.count() == ReferralReward.query.count() == 0


def test_disabled_code_signup_rolls_back_without_deleting_existing_attribution(app):
    affiliate_id = partner(app)
    original = app.test_client()
    assert original.post("/api/register", json=registration_payload("original-customer", referral_code="ANA10")).status_code == 201
    with app.app_context():
        db.session.get(ReferralCode, "ANA10").active = False
        db.session.commit()
    assert app.test_client().post("/api/register", json=registration_payload("blocked-customer", referral_code="ANA10")).status_code == 400
    with app.app_context():
        assert User.query.filter_by(username="blocked-customer").first() is None
        assert Referral.query.filter_by(affiliate_id=affiliate_id).count() == 1


def test_partner_application_does_not_depend_on_purchase_provider_availability(app, monkeypatch):
    partner(app)
    client, _ = account(app, "unsynced-customer")
    app.config["REVENUECAT_SECRET_API_KEY"] = "test-key"
    def must_not_query(_):
        pytest.fail("Partner attribution must not query or change past purchases")
    monkeypatch.setattr("src.services.revenuecat.fetch_subscriber", must_not_query)
    assert client.post("/api/referrals/apply", json={"code": " A N A 1 0 "}).status_code == 200
    with app.app_context():
        assert Referral.query.filter_by(kind="affiliate").count() == 1
        assert Subscription.query.count() == AffiliateCommission.query.count() == 0


def test_duplicate_refund_trial_restore_events_never_create_unverified_commissions(app, monkeypatch):
    from tests.test_revenuecat import subscriber
    partner(app)
    client, user_id = account(app, "webhook-customer")
    assert client.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 200
    app.config.update(REVENUECAT_SECRET_API_KEY="test-key", REVENUECAT_WEBHOOK_AUTHORIZATION="Bearer test")
    headers = {"Authorization": "Bearer test"}
    for event_type, state in [
        ("INITIAL_PURCHASE", subscriber(trial=True)),
        ("RENEWAL", subscriber()), ("RENEWAL", subscriber()),
        ("TRANSFER", subscriber()), ("CANCELLATION", subscriber(expired=True)),
        ("EXPIRATION", subscriber(expired=True)),
    ]:
        monkeypatch.setattr("src.services.revenuecat.fetch_subscriber", lambda _, state=state: state)
        response = client.post("/api/billing/revenuecat/webhook", headers=headers,
                               json={"event": {"id": "replayed-event", "type": event_type, "app_user_id": str(user_id)}})
        assert response.status_code == 200
    with app.app_context():
        assert Referral.query.count() == 1
        assert AffiliateCommission.query.count() == 0
        assert Subscription.query.filter_by(provider="revenuecat").count() == 1


def test_two_concurrent_attributions_cannot_create_two_rows(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}", connect_args={"timeout": 15})
    db.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions.begin() as session:
        person = User(username="concurrent-customer")
        affiliate = Affiliate(name="Ana", public_name="Ana")
        session.add_all([person, affiliate])
        session.flush()
        user_id, affiliate_id = person.id, affiliate.id
        session.add(ReferralCode(code="ANAFIT", affiliate_id=affiliate_id, kind="affiliate"))
    barrier = Barrier(2)
    def attempt():
        with sessions() as session:
            session.add(Referral(invitee_user_id=user_id, affiliate_id=affiliate_id, code="ANAFIT", kind="affiliate"))
            barrier.wait(timeout=10)
            try:
                session.commit()
                return "committed"
            except IntegrityError:
                session.rollback()
                return "duplicate"
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: attempt(), range(2)))
        assert sorted(results) == ["committed", "duplicate"]
        with sessions() as session:
            assert session.query(Referral).filter_by(invitee_user_id=user_id).count() == 1
    finally:
        engine.dispose()


def test_admin_can_create_anafit_and_inspect_and_disable_without_losing_history(app):
    admin, _ = account(app, "acceptance-admin", admin=True)
    result = admin.post("/api/admin/affiliates", json={
        "name": "Ana Fitness", "public_name": "Ana Fitness", "code": "ANAFIT",
        "first_rate": 50, "renewal_rate": 10, "recurring_months": 12,
        "annual_first_rate": None, "annual_renewal_rate": None,
        "email": None, "user_id": None, "notes": "", "active": True,
    })
    assert result.status_code == 201, result.json
    affiliate_id = result.json["id"]
    customer, customer_id = account(app, "acceptance-customer")
    assert customer.post("/api/referrals/apply", json={"code": " ana fit "}).json["message"] == "Código de Ana Fitness aplicado com sucesso."
    referrals = admin.get(f"/api/admin/affiliates/{affiliate_id}/referrals").json
    assert referrals["total"] == 1
    assert referrals["referrals"][0]["user_id"] == str(customer_id)
    assert referrals["referrals"][0]["paid_confirmed"] is False
    listing = admin.get("/api/admin/affiliates").json
    assert listing["affiliates"][0]["metrics"]["registrations"] == 1
    assert listing["affiliates"][0]["codes"][0]["code"] == "ANAFIT"
    assert admin.patch(f"/api/admin/affiliates/{affiliate_id}/codes/ANAFIT", json={"active": False}).status_code == 200
    assert admin.get(f"/api/admin/affiliates/{affiliate_id}/referrals").json["total"] == 1
    blocked = admin.post(f"/api/admin/affiliates/{affiliate_id}/payouts", json={"commission_ids": [1], "reference": "manual"})
    assert blocked.status_code == 503 and blocked.json["code"] == "affiliate_finance_disabled"
    assert customer.post("/api/referrals/apply", json={"code": "ANAFIT", "affiliate_id": affiliate_id}).status_code == 400
    assert customer.get(f"/api/admin/affiliates/{affiliate_id}/referrals").status_code == 403


def test_friend_invitation_and_reward_survive_later_partner_at_checkout(app):
    affiliate_id = partner(app)
    inviter, _ = account(app, "original-friend")
    code = inviter.get("/api/referrals").json["code"]
    invited = []
    for number in range(3):
        client = app.test_client()
        assert client.post("/api/register", json=registration_payload(
            f"friend-with-partner-{number}", referral_code=code)).status_code == 201
        invited.append(client)
    before = inviter.get("/api/referrals").json
    assert before["rewarded_this_month"] is True
    customer = invited[0]
    original = customer.get("/api/referrals/attribution").json
    assert original["attribution"]["kind"] == "user_referral"
    assert original["can_apply_affiliate"] is True
    assert customer.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 200
    assert customer.post("/api/referrals/apply", json={"code": "ANA10"}).status_code == 200
    status = customer.get("/api/referrals/attribution").json
    assert status["attribution"]["kind"] == "affiliate"
    assert status["attribution"]["public_name"] == "Ana"
    assert status["can_apply_affiliate"] is False
    assert inviter.get("/api/referrals").json == before
    with app.app_context():
        assert Referral.query.filter_by(kind="user_referral").count() == 3
        assert Referral.query.filter_by(kind="affiliate", affiliate_id=affiliate_id).count() == 1
        assert ReferralReward.query.count() == 1
        assert AffiliateCommission.query.count() == 0
