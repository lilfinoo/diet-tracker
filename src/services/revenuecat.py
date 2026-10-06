"""Server-authoritative Apple subscription access through RevenueCat."""
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from flask import current_app

from src.models.user import Subscription, db

ENTITLEMENT_ID = "fittracker_ai_pro"
PRODUCT_PLANS = {
    "ai.fittracker.premium.monthly": "premium_student",
    "ai.fittracker.premium.annual": "premium_student_annual",
}


class RevenueCatError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def fetch_subscriber(user_id):
    key = current_app.config.get("REVENUECAT_SECRET_API_KEY")
    if not key:
        raise RevenueCatError("Compras da Apple ainda não configuradas.", 503)
    try:
        response = requests.get(
            "https://api.revenuecat.com/v1/subscribers/" + quote(str(user_id), safe=""),
            headers={"Authorization": f"Bearer {key}"}, timeout=15,
        )
        if response.status_code != 200:
            raise RevenueCatError("Não foi possível verificar sua assinatura.")
        payload = response.json()
        subscriber = payload.get("subscriber")
        if not isinstance(subscriber, dict):
            raise ValueError("Invalid subscriber response")
        return subscriber
    except (requests.RequestException, ValueError, AttributeError) as error:
        raise RevenueCatError("Não foi possível verificar sua assinatura.") from error


def _date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Missing timezone")
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, AttributeError):
        raise RevenueCatError("Resposta inválida do provedor de assinatura.") from None


def sync_subscription(user):
    subscriber = fetch_subscriber(user.id)
    entitlements = subscriber.get("entitlements") or {}
    subscriptions = subscriber.get("subscriptions") or {}
    if not isinstance(entitlements, dict) or not isinstance(subscriptions, dict):
        raise RevenueCatError("Resposta inválida do provedor de assinatura.")
    entitlement = entitlements.get(ENTITLEMENT_ID) or {}
    if not isinstance(entitlement, dict):
        raise RevenueCatError("Resposta inválida do provedor de assinatura.")
    product = entitlement.get("product_identifier")
    if product is not None and not isinstance(product, str):
        raise RevenueCatError("Resposta inválida do provedor de assinatura.")
    details = subscriptions.get(product) or {}
    if not isinstance(details, dict):
        raise RevenueCatError("Resposta inválida do provedor de assinatura.")
    end = _date(entitlement.get("expires_date"))
    grace_end = _date(details.get("grace_period_expires_date"))
    if end and grace_end and grace_end > end:
        end = grace_end
    sandbox_users = {
        item.strip() for item in current_app.config.get("REVENUECAT_SANDBOX_USER_IDS", "").split(",")
        if item.strip()
    }
    sandbox_allowed = current_app.config.get("REVENUECAT_ALLOW_SANDBOX", False) or str(user.id) in sandbox_users
    allowed = (
        product in PRODUCT_PLANS
        and details.get("store") == "app_store"
        and (details.get("is_sandbox") is False or (details.get("is_sandbox") is True and sandbox_allowed))
    )
    active = allowed and end is not None and end > datetime.utcnow()
    subscription = Subscription.query.filter_by(provider="revenuecat", user_id=user.id).first()
    if subscription is None and not active:
        return None
    if subscription is None:
        subscription = Subscription(provider="revenuecat", user_id=user.id,
                                    external_subscription_id=str(user.id))
        db.session.add(subscription)
    subscription.external_customer_id = str(user.id)
    subscription.plan_code = PRODUCT_PLANS.get(product, subscription.plan_code or "premium_student")
    subscription.status = "trialing" if active and details.get("period_type") == "trial" else "active" if active else "expired"
    subscription.current_period_start = _date(entitlement.get("purchase_date"))
    # A rejected sandbox/store must never retain a future canceled period granting access.
    subscription.current_period_end = end if allowed else None
    return subscription
