from datetime import datetime

from src.models.user import AdminActionAudit, BillingCheckout, Subscription, db
from src.services.asaas import (
    AsaasError,
    get_subscription,
    list_subscription_payments,
    parse_payment_period,
    period_end_from_subscription,
)


def reconcile_asaas():
    result = {"checked": 0, "updated": 0, "failed": 0, "expired_checkouts": 0}
    now = datetime.utcnow()
    stale = BillingCheckout.query.filter(
        BillingCheckout.provider == "asaas",
        BillingCheckout.status.in_(("creating", "pending")),
        BillingCheckout.expires_at <= now,
    ).all()
    for checkout in stale:
        checkout.status = "expired"
    result["expired_checkouts"] = len(stale)

    subscriptions = Subscription.query.filter(
        Subscription.provider == "asaas",
        Subscription.external_subscription_id.isnot(None),
    ).all()
    for subscription in subscriptions:
        result["checked"] += 1
        try:
            remote = get_subscription(subscription.external_subscription_id)
            payments = list_subscription_payments(subscription.external_subscription_id).get("data") or []
        except AsaasError:
            result["failed"] += 1
            continue
        previous = (subscription.status, subscription.current_period_end, subscription.last_payment_id)
        remote_status = str(remote.get("status", "")).upper()
        paid = [
            item for item in payments
            if str(item.get("status", "")).upper() in {"CONFIRMED", "RECEIVED"}
        ]
        paid.sort(key=lambda item: str(
            item.get("dueDate") or item.get("paymentDate") or item.get("confirmedDate") or ""
        ))
        if paid and subscription.status not in {"canceled", "revoked", "disputed"}:
            latest = paid[-1]
            start, _ = parse_payment_period(latest)
            end = period_end_from_subscription(remote)
            if start and end and end > start:
                subscription.current_period_start = datetime.combine(start, datetime.min.time())
                subscription.current_period_end = datetime.combine(end, datetime.min.time())
                subscription.last_payment_id = str(latest.get("id", ""))[:255] or None
                if remote_status == "ACTIVE":
                    subscription.status = "active"
        elif subscription.status == "active":
            subscription.status = "pending"
            subscription.current_period_start = None
            subscription.current_period_end = None
            subscription.last_payment_id = None
        if remote_status in {"INACTIVE", "EXPIRED"} and subscription.status not in {
            "revoked", "disputed"
        }:
            subscription.status = "canceled"
        current = (subscription.status, subscription.current_period_end, subscription.last_payment_id)
        if current != previous:
            result["updated"] += 1
            db.session.add(AdminActionAudit(
                actor_user_id=None,
                subject_user_id=subscription.user_id,
                action="subscription.reconciled",
                resource_type="subscription",
                resource_id=str(subscription.id),
                details={"previous_status": previous[0], "new_status": subscription.status},
            ))
    db.session.commit()
    return result
