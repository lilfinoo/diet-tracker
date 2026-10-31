from datetime import datetime, timedelta, timezone

import pytest

from src.models.user import AnalyticsEvent, User, db
from src.services.revenuecat import sync_subscription


def payment_events():
    return AnalyticsEvent.query.filter_by(event_name="subscription_payment_confirmed").all()


def payment_user():
    user = User(username="paywall-buyer")
    user.set_password("strong-password")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.mark.parametrize("period,sandbox,amount,expected", [
    ("normal", False, 20, 1),
    ("trial", False, 0, 0),
    ("promotional", False, 0, 0),
    ("normal", False, 0, 0),
    ("normal", True, 20, 0),
])
def test_native_payment_excludes_trials_free_and_sandbox_and_dedupes(
        app, monkeypatch, period, sandbox, amount, expected):
    app.config["REVENUECAT_ALLOW_SANDBOX"] = True
    now = datetime.now(timezone.utc)
    purchase_date = now.isoformat()
    product = "ai.fittracker.premium.monthly"
    canonical = {
        "entitlements": {"fittracker_ai_pro": {
            "product_identifier": product,
            "expires_date": (now + timedelta(days=30)).isoformat(),
            "purchase_date": purchase_date,
        }},
        "subscriptions": {product: {
            "store": "app_store", "is_sandbox": sandbox, "period_type": period,
            "purchase_date": purchase_date, "store_transaction_id": "native-paid-transaction",
            "price": {"amount": amount, "currency": "BRL"},
        }},
    }
    monkeypatch.setattr("src.services.revenuecat.fetch_subscriber", lambda _: canonical)
    with app.app_context():
        user = payment_user()
        for _ in range(2):
            sync_subscription(user)
            db.session.commit()
        events = payment_events()
        assert len(events) == expected
        if events:
            assert events[0].created_at == now.replace(tzinfo=None)
