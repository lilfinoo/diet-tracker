from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

from src.models.user import Referral, ReferralCode, ReferralReward, Subscription, User, db
from src.services import apple_auth, referrals
from tests.helpers import consent_payload, registration_payload


def owner(app):
    client = app.test_client()
    result = client.post("/api/register", json=registration_payload("owner"))
    assert result.status_code == 201
    return client, client.get("/api/referrals").get_json()["code"]


def refer(app, code, number):
    client = app.test_client()
    result = client.post(
        "/api/register", json=registration_payload(f"friend-{number}", referral_code=code)
    )
    assert result.status_code == 201, result.get_json()
    return client


def clock(monkeypatch, when):
    class Frozen(datetime):
        @classmethod
        def utcnow(cls):
            return when

    monkeypatch.setattr(referrals, "datetime", Frozen)


def test_codes_are_private_unique_and_stable_for_existing_accounts(app):
    with app.app_context():
        old = User(username="preexisting")
        db.session.add(old)
        db.session.commit()
        old_id = old.id
    first = app.test_client()
    with first.session_transaction() as session:
        session["user_id"] = old_id
    assert app.test_client().get("/api/referrals").status_code == 401
    response = first.get("/api/referrals")
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.get_json()
    assert len(payload["code"]) == 12
    assert first.get("/api/referrals").get_json() == payload
    assert payload["progress"] == 0 and payload["target"] == 3
    assert payload["rewarded_this_month"] is False
    assert payload["premium_until"] is None
    assert set(payload) == {
        "code",
        "qualified_invites",
        "progress",
        "target",
        "period",
        "period_ends_at",
        "rewarded_this_month",
        "premium_until",
    }
    second, code = owner(app)
    assert code != payload["code"]
    assert second.get("/api/referrals").get_json()["qualified_invites"] == 0


def test_third_registration_grants_once_per_month_and_extra_invites_do_not_extend(app, monkeypatch):
    now = datetime(2026, 10, 25, 12)
    clock(monkeypatch, now)
    client, code = owner(app)
    for number in range(2):
        refer(app, code.lower(), number)
    assert client.get("/api/referrals").get_json()["premium_until"] is None
    refer(app, code, 2)
    payload = client.get("/api/referrals").get_json()
    assert payload["qualified_invites"] == payload["progress"] == 3
    assert payload["rewarded_this_month"] is True
    assert payload["premium_until"] == "2026-11-25T12:00:00Z"
    for number in range(3, 7):
        refer(app, code, number)
    final = client.get("/api/referrals").get_json()
    assert final["qualified_invites"] == 7 and final["progress"] == 3
    assert final["premium_until"] == payload["premium_until"]
    assert client.get("/api/subscription").get_json()["is_premium"] is True
    assert client.get("/api/check_session").get_json()["user"]["is_premium"] is True
    with app.app_context():
        assert (
            ReferralReward.query.count()
            == Subscription.query.filter_by(provider="referral").count()
            == 1
        )


def test_month_reset_no_carry_and_new_reward_does_not_bank_unused_days(app, monkeypatch):
    clock(monkeypatch, datetime(2026, 10, 31, 21))
    client, code = owner(app)
    for number in range(4):
        refer(app, code, number)
    assert client.get("/api/referrals").get_json()["premium_until"] == "2026-11-30T21:00:00Z"
    # Midnight in Sao Paulo is 03:00 UTC. A profile timezone cannot alter this rule.
    clock(monkeypatch, datetime(2026, 11, 1, 2, 59))
    assert client.get("/api/referrals").get_json()["period"] == "2026-10"
    clock(monkeypatch, datetime(2026, 11, 1, 3))
    reset = client.get("/api/referrals").get_json()
    assert reset["period"] == "2026-11" and reset["qualified_invites"] == 0
    assert reset["rewarded_this_month"] is False
    assert reset["period_ends_at"] == "2026-12-01T03:00:00Z"
    for number in range(4, 7):
        refer(app, code, number)
    assert client.get("/api/referrals").get_json()["premium_until"] == "2026-12-01T03:00:00Z"
    with app.app_context():
        assert ReferralReward.query.count() == 2


@pytest.mark.parametrize("bad", ["missing", 123, [], {"code": "ABC"}])
def test_invalid_code_rolls_back_entire_registration(app, bad):
    client, _ = owner(app)
    response = app.test_client().post(
        "/api/register", json=registration_payload("invalid", referral_code=bad)
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_referral_code"
    client.get("/api/referrals")  # A later commit must not accidentally save a rejected account.
    with app.app_context():
        assert User.query.filter_by(username="invalid").first() is None
        assert Referral.query.count() == 0


def test_banned_inviter_rejected_and_blank_optional_code_allowed(app):
    _, code = owner(app)
    with app.app_context():
        User.query.filter_by(username="owner").one().is_banned = True
        db.session.commit()
    result = app.test_client().post(
        "/api/register", json=registration_payload("banned-referral", referral_code=code)
    )
    assert result.status_code == 400
    assert (
        app.test_client()
        .post("/api/register", json=registration_payload("no-referral", referral_code="  "))
        .status_code
        == 201
    )


def test_repeated_attribution_is_idempotent_and_self_referral_rejected(app):
    _, code = owner(app)
    refer(app, code, 0)
    with app.app_context():
        friend = User.query.filter_by(username="friend-0").one()
        referrals.attach_referral(friend, code)
        db.session.commit()
        assert Referral.query.count() == 1
        person = User.query.filter_by(username="owner").one()
        from werkzeug.exceptions import HTTPException

        with pytest.raises(HTTPException) as error:
            referrals.attach_referral(person, code)
        assert error.value.response.status_code == 400


def test_database_enforces_unique_invitee_and_month_even_if_service_retried(app):
    _, code = owner(app)
    for number in range(3):
        refer(app, code, number)
    with app.app_context():
        entry = Referral.query.first()
        db.session.add(
            Referral(inviter_user_id=entry.inviter_user_id, invitee_user_id=entry.invitee_user_id)
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        reward = ReferralReward.query.one()
        db.session.add(
            ReferralReward(
                inviter_user_id=reward.inviter_user_id,
                period=reward.period,
                granted_at=reward.granted_at,
                expires_at=reward.expires_at,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert ReferralReward.query.count() == 1


def test_gift_overlaps_paid_access_without_altering_billing_or_legacy_flag(app, monkeypatch):
    now = datetime(2026, 10, 25, 12)
    clock(monkeypatch, now)
    client, code = owner(app)
    with app.app_context():
        user = User.query.filter_by(username="owner").one()
        db.session.add(
            Subscription(
                user_id=user.id,
                provider="revenuecat",
                external_subscription_id="paid",
                status="active",
                plan_code="premium_student_annual",
                current_period_end=now + timedelta(days=300),
            )
        )
        db.session.commit()
    for number in range(3):
        refer(app, code, number)
    assert client.get("/api/referrals").get_json()["premium_until"] == "2026-11-25T12:00:00Z"
    with app.app_context():
        paid = Subscription.query.filter_by(provider="revenuecat").one()
        assert paid.current_period_end == now + timedelta(days=300)
        assert paid.status == "active"
        assert User.query.filter_by(username="owner").one().is_premium is False


def test_gift_expiration_uses_existing_entitlement_checks(app):
    client, _ = owner(app)
    with app.app_context():
        user = User.query.filter_by(username="owner").one()
        db.session.add(
            Subscription(
                user_id=user.id,
                provider="referral",
                status="active",
                plan_code="premium_student",
                current_period_end=datetime.utcnow() - timedelta(seconds=1),
            )
        )
        db.session.commit()
    assert client.get("/api/subscription").get_json()["is_premium"] is False
    assert client.get("/api/referrals").get_json()["premium_until"] is None


def test_account_deletion_with_gift_preserves_other_users_and_qualified_count(app):
    client, code = owner(app)
    friends = [refer(app, code, n) for n in range(3)]
    assert (
        friends[0]
        .delete(
            "/api/account",
            json={"username": "friend-0", "password": "strong-password", "confirm_delete": True},
        )
        .status_code
        == 200
    )
    assert client.get("/api/referrals").get_json()["qualified_invites"] == 3
    assert (
        client.delete(
            "/api/account",
            json={"username": "owner", "password": "strong-password", "confirm_delete": True},
        ).status_code
        == 200
    )
    with app.app_context():
        assert Referral.query.count() == ReferralReward.query.count() == 0
        assert ReferralCode.query.count() == User.query.count() == 2
        assert Subscription.query.filter_by(provider="referral").count() == 0


def test_registration_requires_csrf_when_already_authenticated(app):
    client, code = owner(app)
    app.config["CSRF_PROTECTION"] = True
    result = client.post("/api/register", json=registration_payload("csrf", referral_code=code))
    assert result.status_code == 403
    with app.app_context():
        assert Referral.query.count() == 0


def test_google_code_applies_only_on_new_signup_not_existing_login(app, monkeypatch):
    _, code = owner(app)
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *args, **kwargs: {
            "iss": "https://accounts.google.com",
            "sub": "friend-google",
            "email": "friend@example.com",
            "email_verified": True,
            "name": "Friend",
        },
    )
    client = app.test_client()
    begin = client.post("/api/auth/google", json={"credential": "token", "referral_code": code})
    assert begin.status_code == 409
    with app.app_context():
        assert Referral.query.count() == 0
    body = {
        "signup_token": begin.get_json()["signup_token"],
        "username": "google-friend",
        "referral_code": code,
        **consent_payload(),
    }
    assert client.post("/api/auth/google", json=body).status_code == 201
    client.post("/api/logout")
    assert (
        client.post(
            "/api/auth/google", json={"credential": "token", "referral_code": "invalid"}
        ).status_code
        == 200
    )
    with app.app_context():
        assert Referral.query.count() == 1


def test_apple_invalid_code_can_retry_same_signup_token_and_login_does_not_count(app, monkeypatch):
    _, code = owner(app)
    app.config.update(
        APPLE_TEAM_ID="team",
        APPLE_KEY_ID="key",
        APPLE_PRIVATE_KEY="unused",
        APPLE_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr(
        apple_auth,
        "verify_identity",
        lambda credential, nonce: {
            "sub": "friend-apple",
            "email": "friend@example.com",
            "email_verified": "true",
        },
    )
    monkeypatch.setattr(apple_auth, "exchange_code", lambda *args: "encrypted-token")
    client = app.test_client()

    def begin():
        nonce = client.post("/api/auth/apple/challenge").get_json()["nonce"]
        return client.post(
            "/api/auth/apple",
            json={
                "credential": "token",
                "nonce": nonce,
                "authorization_code": "code",
                "referral_code": "invalid",
            },
        )

    result = begin()
    body = {
        "signup_token": result.get_json()["signup_token"],
        "username": "apple-friend",
        "referral_code": "invalid",
        **consent_payload(),
    }
    assert client.post("/api/auth/apple", json=body).status_code == 400
    body["referral_code"] = code
    assert client.post("/api/auth/apple", json=body).status_code == 201
    client.post("/api/logout")
    assert begin().status_code == 200
    with app.app_context():
        assert Referral.query.count() == 1


def test_summary_is_rate_limited(app):
    client, _ = owner(app)
    app.config["RATE_LIMITS"] = {"referrals": (1, 60)}
    assert client.get("/api/referrals").status_code == 429


@pytest.mark.parametrize(
    "given, expected",
    [
        (datetime(2027, 1, 31, 12), datetime(2027, 2, 28, 12)),
        (datetime(2028, 1, 31, 12), datetime(2028, 2, 29, 12)),
        (datetime(2026, 12, 25, 12), datetime(2027, 1, 25, 12)),
    ],
)
def test_reward_month_handles_short_months_leap_year_and_year_boundary(given, expected):
    assert referrals._month_later(given) == expected


def test_failed_third_signup_rolls_back_referral_reward_and_gift_together(app, monkeypatch):
    from src.routes import auth_routes

    client, code = owner(app)
    refer(app, code, 0)
    refer(app, code, 1)
    original = auth_routes.grant_signup_badges

    def fail_signup(user):
        raise IntegrityError("forced signup failure", {}, Exception("test"))

    monkeypatch.setattr(auth_routes, "grant_signup_badges", fail_signup)
    rejected = app.test_client().post(
        "/api/register", json=registration_payload("friend-2", referral_code=code)
    )
    assert rejected.status_code == 409
    summary = client.get("/api/referrals").get_json()
    assert summary["qualified_invites"] == 2 and summary["premium_until"] is None
    with app.app_context():
        assert User.query.filter_by(username="friend-2").first() is None
        assert (
            ReferralReward.query.count()
            == Subscription.query.filter_by(provider="referral").count()
            == 0
        )
    monkeypatch.setattr(auth_routes, "grant_signup_badges", original)
    refer(app, code, 2)
    assert client.get("/api/referrals").get_json()["rewarded_this_month"] is True
