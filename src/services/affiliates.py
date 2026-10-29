"""Affiliate attribution. Financial ingestion remains disabled until verified data exists."""
from datetime import datetime
from decimal import Decimal
import secrets
from uuid import UUID

from flask import abort, current_app, jsonify, make_response
from sqlalchemy import case, func

from src.models.user import (
    Affiliate, AffiliateCommission, AffiliatePayout, BillingCheckout, Referral, ReferralCode,
    Subscription, User, db,
)
from src.services.referrals import _invalid_code, _locked_user, normalize_code
from src.services.revenuecat import fetch_subscriber

FINANCIAL_TRACKING_ENABLED = False


def reject(message, code="referral_not_eligible", status=409):
    db.session.rollback()
    abort(make_response(jsonify(error=message, code=code), status))


def eligible_for_affiliate(user):
    return not (
        Referral.query.filter_by(invitee_user_id=user.id).first()
        or Subscription.query.filter(
            Subscription.user_id == user.id, Subscription.provider.notin_(("admin", "referral"))
        ).first()
        or BillingCheckout.query.filter_by(user_id=user.id).first()
    )


def verify_purchase_history(user):
    """Do network I/O before locks; local eligibility is rechecked under lock."""
    if not eligible_for_affiliate(user):
        reject("Aplique o código antes de iniciar uma assinatura ou compra.")
    if current_app.config.get("REVENUECAT_SECRET_API_KEY"):
        # Canonical history also catches expired/restored subscriptions not yet
        # synced locally. Fail closed on provider outages through the caller.
        subscriber = fetch_subscriber(user.id)
        history = subscriber.get("subscriptions")
        purchases = subscriber.get("non_subscriptions")
        if (history is not None and not isinstance(history, dict)) or (
            purchases is not None and not isinstance(purchases, dict)
        ):
            from src.services.revenuecat import RevenueCatError
            raise RevenueCatError("Não foi possível verificar o histórico de compras.")
        if history or purchases:
            reject("Aplique o código antes de iniciar uma assinatura ou compra.")


def attach_affiliate(user, code, source):
    # The same user lock is taken for signup and post-signup application. The
    # unique invitee constraint remains the final guard across all code types.
    _locked_user(user.id)
    affiliate = Affiliate.query.filter_by(id=code.affiliate_id).with_for_update().one()
    if not code.active or not affiliate.active or affiliate.user_id == user.id:
        _invalid_code()
    previous = Referral.query.filter_by(invitee_user_id=user.id).first()
    if previous:
        if previous.kind == "affiliate" and previous.code == code.code:
            return previous
        reject("Esta conta já possui uma indicação e não pode trocá-la.", "referral_already_applied")
    if not eligible_for_affiliate(user):
        reject("Aplique o código antes de iniciar uma assinatura ou compra.")
    attribution = Referral(
        invitee_user_id=user.id, affiliate_id=affiliate.id, code=code.code,
        kind="affiliate", source=source,
    )
    db.session.add(attribution)
    db.session.flush()
    return attribution


def attribution_dict(entry):
    if entry.kind == "affiliate":
        owner = db.session.get(Affiliate, entry.affiliate_id)
        name = owner.public_name
    else:
        owner = db.session.get(User, entry.inviter_user_id) if entry.inviter_user_id else None
        name = (owner.name or owner.username) if owner else "uma pessoa do Fit Tracker"
    return {"kind": entry.kind, "public_name": name, "code": entry.code,
            "created_at": entry.created_at.isoformat() + "Z"}


def create_code(affiliate, raw_code=None):
    code = normalize_code(raw_code) if raw_code is not None else secrets.token_hex(6).upper()
    if ReferralCode.query.filter_by(code=code).first():
        reject("Este código já está em uso.", "referral_code_conflict")
    entry = ReferralCode(code=code, affiliate_id=affiliate.id, kind="affiliate")
    db.session.add(entry)
    db.session.flush()
    return entry


def configure_affiliate(affiliate, data, creating=False):
    allowed = {"name", "public_name", "email", "user_id", "active", "first_rate", "renewal_rate",
               "recurring_months", "annual_first_rate", "annual_renewal_rate", "notes"}
    if set(data) - allowed - ({"code"} if creating else set()):
        raise ValueError("Campo de parceiro não permitido.")
    for key in ("name", "public_name", "email", "notes"):
        if key not in data:
            continue
        value = data[key]
        limit = 5000 if key == "notes" else 255
        if key in {"email", "notes"} and (value is None or (isinstance(value, str) and not value.strip())):
            setattr(affiliate, key, None)
        elif not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f"Campo {key} inválido.")
        else:
            setattr(affiliate, key, value.strip())
    if creating:
        if not affiliate.name:
            raise ValueError("Informe o nome da influencer.")
        if not affiliate.public_name:
            affiliate.public_name = affiliate.name
    if "active" in data:
        if not isinstance(data["active"], bool):
            raise ValueError("Status inválido.")
        affiliate.active = data["active"]
    for key in ("first_rate", "renewal_rate", "annual_first_rate", "annual_renewal_rate"):
        if key not in data:
            continue
        value = data[key]
        if value is None and key.startswith("annual_"):
            setattr(affiliate, key, None)
            continue
        try:
            if isinstance(value, bool):
                raise ValueError()
            rate = Decimal(str(value))
            if not rate.is_finite() or not 0 <= rate <= 100 or rate != rate.quantize(Decimal("0.01")):
                raise ValueError()
        except (ValueError, ArithmeticError):
            raise ValueError("Percentual inválido; use de 0 a 100 com até 2 decimais.") from None
        setattr(affiliate, key, rate)
    if "recurring_months" in data:
        value = data["recurring_months"]
        if type(value) is not int or not 0 <= value <= 1200:
            raise ValueError("Duração recorrente inválida.")
        affiliate.recurring_months = value
    if "user_id" in data:
        value = data["user_id"]
        try:
            user_id = UUID(str(value)) if value else None
        except ValueError:
            raise ValueError("Conta vinculada inválida.") from None
        if user_id:
            user = db.session.get(User, user_id)
            if not user or user.is_banned:
                raise ValueError("Conta vinculada inválida.")
            # Prevent linking a partner to someone already attributed to them.
            if affiliate.id and Referral.query.filter_by(
                invitee_user_id=user_id, affiliate_id=affiliate.id
            ).first():
                raise ValueError("A conta vinculada não pode ser uma indicação da própria parceria.")
        affiliate.user_id = user_id


def code_dict(code):
    return {"code": code.code, "kind": code.kind, "active": code.active,
            "created_at": code.created_at.isoformat() + "Z"}


def affiliate_metrics_batch(affiliate_ids):
    metrics = {affiliate_id: {
        "registrations": 0, "confirmed_paying_users": 0, "active_subscribers": 0,
        "cancellations": 0, "commissions_pending": [], "commissions_released": [],
    } for affiliate_id in affiliate_ids}
    if not metrics:
        return metrics
    registrations = db.session.query(Referral.affiliate_id, func.count(Referral.id)).filter(
        Referral.affiliate_id.in_(affiliate_ids), Referral.validation_state == "valid",
    ).group_by(Referral.affiliate_id).all()
    for affiliate_id, count in registrations:
        metrics[affiliate_id]["registrations"] = count
    subscribers = db.session.query(
        Referral.affiliate_id,
        func.count(func.distinct(case((db.and_(
            Subscription.status.in_(("active", "canceled")),
            Subscription.current_period_end > datetime.utcnow(),
        ), Subscription.user_id)))),
        func.count(func.distinct(case((Subscription.status == "canceled", Subscription.user_id)))),
    ).join(Subscription, Subscription.user_id == Referral.invitee_user_id).filter(
        Referral.affiliate_id.in_(affiliate_ids), Referral.validation_state == "valid",
        Subscription.provider.notin_(("referral", "admin")),
    ).group_by(Referral.affiliate_id).all()
    for affiliate_id, active, canceled in subscribers:
        metrics[affiliate_id]["active_subscribers"] = active
        metrics[affiliate_id]["cancellations"] = canceled
    # Access snapshots are not proof of payment. Only future verified production
    # transactions can contribute to confirmed_paying_users.
    confirmed = db.session.query(
        AffiliateCommission.affiliate_id, func.count(func.distinct(AffiliateCommission.user_id)),
    ).filter(
        AffiliateCommission.affiliate_id.in_(affiliate_ids),
        AffiliateCommission.environment == "production",
        AffiliateCommission.status.in_(("pending", "released", "paid")),
    ).group_by(AffiliateCommission.affiliate_id).all()
    for affiliate_id, count in confirmed:
        metrics[affiliate_id]["confirmed_paying_users"] = count
    totals = db.session.query(
        AffiliateCommission.affiliate_id, AffiliateCommission.status, AffiliateCommission.currency,
        func.count(AffiliateCommission.id), func.sum(AffiliateCommission.amount),
        func.count(AffiliateCommission.amount),
    ).filter(
        AffiliateCommission.affiliate_id.in_(affiliate_ids),
        AffiliateCommission.environment == "production",
        AffiliateCommission.status.in_(("pending", "released")),
    ).group_by(
        AffiliateCommission.affiliate_id, AffiliateCommission.status, AffiliateCommission.currency,
    ).all()
    for affiliate_id, status, currency, count, amount, valued in totals:
        metrics[affiliate_id]["commissions_" + status].append({
            "currency": currency, "count": count,
            "amount": str(amount) if amount is not None else None,
            "awaiting_net_revenue": count - valued,
        })
    return metrics


def affiliate_metrics(affiliate_id):
    return affiliate_metrics_batch([affiliate_id])[affiliate_id]


def affiliate_page_dicts(affiliates):
    ids = [affiliate.id for affiliate in affiliates]
    if not ids:
        return []
    metrics = affiliate_metrics_batch(ids)
    codes = {affiliate_id: [] for affiliate_id in ids}
    for code in ReferralCode.query.filter(ReferralCode.affiliate_id.in_(ids)).order_by(ReferralCode.created_at):
        codes[code.affiliate_id].append(code_dict(code))
    return [affiliate_dict(affiliate, metrics=metrics[affiliate.id], codes=codes[affiliate.id])
            for affiliate in affiliates]


def affiliate_dict(affiliate, private=True, metrics=None, codes=None):
    result = {"id": affiliate.id, "public_name": affiliate.public_name, "active": affiliate.active,
              "codes": codes if codes is not None else [code_dict(c) for c in ReferralCode.query.filter_by(affiliate_id=affiliate.id).order_by(ReferralCode.created_at)],
              "metrics": metrics if metrics is not None else affiliate_metrics(affiliate.id), "financial_tracking_enabled": FINANCIAL_TRACKING_ENABLED}
    if private:
        result.update({key: getattr(affiliate, key) for key in ("name", "email", "notes", "recurring_months")})
        result["user_id"] = str(affiliate.user_id) if affiliate.user_id else None
        for key in ("first_rate", "renewal_rate", "annual_first_rate", "annual_renewal_rate"):
            value = getattr(affiliate, key)
            result[key] = str(value) if value is not None else None
    return result


def payout_dict(payout):
    return {"id": payout.id, "period_start": payout.period_start.isoformat() + "Z",
            "period_end": payout.period_end.isoformat() + "Z", "amount": str(payout.amount),
            "currency": payout.currency, "status": payout.status,
            "paid_at": payout.paid_at.isoformat() + "Z" if payout.paid_at else None}


def payouts_query(affiliate_id):
    return AffiliatePayout.query.filter_by(affiliate_id=affiliate_id).order_by(AffiliatePayout.id.desc())
