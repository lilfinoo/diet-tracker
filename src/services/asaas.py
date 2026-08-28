"""Minimal Asaas API client for hosted recurring checkouts and subscriptions."""
from datetime import datetime, timedelta

import requests
from flask import current_app


class AsaasError(Exception):
    """Raised when the Asaas API call fails or is not configured."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code or 502


def _headers():
    api_key = current_app.config.get("ASAAS_API_KEY")
    if not api_key:
        raise AsaasError("Asaas não configurado", 503)
    return {"access_token": api_key, "Content-Type": "application/json"}


def _request(method, path, payload=None):
    base_url = current_app.config["ASAAS_API_BASE_URL"].rstrip("/")
    try:
        response = requests.request(
            method,
            f"{base_url}{path}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
    except requests.RequestException as error:
        current_app.logger.warning("Asaas request failed: %s", error)
        raise AsaasError("Falha de comunicação com o provedor de pagamento") from error
    if response.status_code >= 400:
        description = ""
        try:
            errors = response.json().get("errors") or []
            description = "; ".join(str(item.get("description", "")) for item in errors)
        except ValueError:
            description = response.text[:200]
        current_app.logger.warning("Asaas %s %s -> %s: %s", method, path, response.status_code, description)
        raise AsaasError(description or "Erro do provedor de pagamento", response.status_code)
    if not response.content:
        return {}
    return response.json()


def create_recurring_checkout(plan, payment_method, public_base_url, external_reference):
    """Create a hosted Asaas Checkout that starts a MONTHLY subscription.

    payment_method: "credit_card" (auto renewal) or "pix" (new charge each month).
    The customer fills their own data on the Asaas-hosted page.
    """
    # 1x1 transparent PNG; the checkout schema marks imageBase64 as required.
    transparent_png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    today = datetime.utcnow().date()
    payload = {
        "billingTypes": ["CREDIT_CARD"] if payment_method == "credit_card" else ["PIX"],
        "chargeTypes": ["RECURRENT"],
        "minutesToExpire": 1440,
        "externalReference": external_reference,
        "callback": {
            "successUrl": f"{public_base_url}/?billing=success",
            "cancelUrl": f"{public_base_url}/?billing=cancel",
            "expiredUrl": f"{public_base_url}/?billing=expired",
        },
        "items": [{
            "name": str(plan["name"])[:30],
            "description": "Assinatura mensal Diet Tracker",
            "quantity": 1,
            "value": float(plan["price_brl"]),
            "imageBase64": transparent_png,
        }],
        "subscription": {
            "cycle": "MONTHLY",
            "nextDueDate": today.isoformat(),
        },
    }
    data = _request("POST", "/checkouts", payload)
    checkout_id = data.get("id")
    link = data.get("link") or f"https://sandbox.asaas.com/checkoutSession/show/{checkout_id}"
    return {"id": checkout_id, "link": link}


def get_subscription(external_subscription_id):
    return _request("GET", f"/subscriptions/{external_subscription_id}")


def delete_subscription(external_subscription_id):
    return _request("DELETE", f"/subscriptions/{external_subscription_id}")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def period_end_from_subscription(remote):
    """Best-effort current period end derived from the remote subscription."""
    next_due = _parse_date(remote.get("nextDueDate"))
    if next_due:
        return next_due
    return None


def fallback_period_end(due_date_value):
    due = _parse_date(due_date_value) or datetime.utcnow().date()
    return due + timedelta(days=31)


def parse_payment_period(payment):
    start = _parse_date(payment.get("paymentDate")) or _parse_date(payment.get("dueDate"))
    end = fallback_period_end(payment.get("dueDate"))
    return start, end


__all__ = [
    "AsaasError",
    "create_recurring_checkout",
    "delete_subscription",
    "fallback_period_end",
    "get_subscription",
    "parse_payment_period",
    "period_end_from_subscription",
]
