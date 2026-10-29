"""Monthly referral rewards, granted atomically with a new account."""

import calendar
from datetime import datetime, timezone
import re
import secrets
from zoneinfo import ZoneInfo

from flask import abort, jsonify, make_response

from src.models.user import Referral, ReferralCode, ReferralReward, Subscription, User, db

REFERRAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
TARGET = 3


def _locked_user(user_id):
    return User.query.filter_by(id=user_id).with_for_update().populate_existing().one()


def ensure_code(user):
    _locked_user(user.id)
    existing = ReferralCode.query.filter_by(user_id=user.id).first()
    if existing:
        return existing.code
    code = secrets.token_hex(6).upper()
    while ReferralCode.query.filter_by(code=code).first():
        code = secrets.token_hex(6).upper()
    db.session.add(ReferralCode(user_id=user.id, code=code))
    db.session.flush()
    return code


def _month(now):
    local = now.replace(tzinfo=timezone.utc).astimezone(REFERRAL_TIMEZONE)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    following = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1)
    return (
        local.strftime("%Y-%m"),
        start.astimezone(timezone.utc).replace(tzinfo=None),
        following.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _month_later(now):
    local = now.replace(tzinfo=timezone.utc).astimezone(REFERRAL_TIMEZONE)
    year, month = local.year + (local.month == 12), local.month % 12 + 1
    local = local.replace(
        year=year, month=month, day=min(local.day, calendar.monthrange(year, month)[1])
    )
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _count(user_id, start, end):
    return Referral.query.filter(
        Referral.inviter_user_id == user_id, Referral.kind == "user_referral",
        Referral.created_at >= start, Referral.created_at < end
    ).count()


def _invalid_code():
    db.session.rollback()
    abort(
        make_response(
            jsonify(
                {
                    "error": "Código de convite inválido ou indisponível.",
                    "code": "invalid_referral_code",
                }
            ),
            400,
        )
    )


def normalize_code(raw_code):
    if not isinstance(raw_code, str):
        _invalid_code()
    code = "".join(raw_code.split()).upper()
    if not re.fullmatch(r"[A-Z0-9]{3,32}", code):
        _invalid_code()
    return code


def attach_referral(user, raw_code):
    """Called only while committing a newly created password/Google/Apple account."""
    ensure_code(user)
    if raw_code is None or (isinstance(raw_code, str) and not raw_code.strip()):
        return
    code = ReferralCode.query.filter_by(code=normalize_code(raw_code)).with_for_update().first()
    if not code or not code.active or code.user_id == user.id:
        _invalid_code()
    if code.kind == "affiliate":
        from src.services.affiliates import attach_affiliate
        attach_affiliate(user, code, source="signup")
        return
    inviter = _locked_user(code.user_id)
    if inviter.is_banned:
        _invalid_code()
    if Referral.query.filter_by(invitee_user_id=user.id).first():
        return
    now = datetime.utcnow()
    db.session.add(Referral(inviter_user_id=inviter.id, invitee_user_id=user.id, code=code.code, created_at=now))
    db.session.flush()
    period, start, end = _month(now)
    if (
        _count(inviter.id, start, end) < TARGET
        or ReferralReward.query.filter_by(inviter_user_id=inviter.id, period=period).first()
    ):
        return
    expires = _month_later(now)
    subscription = Subscription.query.filter_by(user_id=inviter.id, provider="referral").first()
    if subscription is None:
        subscription = Subscription(
            user_id=inviter.id,
            provider="referral",
            external_subscription_id=str(inviter.id),
            plan_code="premium_student",
            status="active",
            current_period_start=now,
        )
        db.session.add(subscription)
    if not subscription.current_period_end or subscription.current_period_end <= now:
        subscription.current_period_start = now
    subscription.current_period_end = max(subscription.current_period_end or expires, expires)
    subscription.status = "active"
    db.session.add(
        ReferralReward(
            inviter_user_id=inviter.id, period=period, granted_at=now, expires_at=expires
        )
    )
    db.session.flush()


def referral_summary(user):
    code = ensure_code(user)
    now = datetime.utcnow()
    period, start, end = _month(now)
    count = _count(user.id, start, end)
    gift = Subscription.query.filter_by(
        user_id=user.id, provider="referral", status="active"
    ).first()
    return {
        "code": code,
        "qualified_invites": count,
        "progress": min(count, TARGET),
        "target": TARGET,
        "period": period,
        "period_ends_at": end.isoformat() + "Z",
        "rewarded_this_month": ReferralReward.query.filter_by(
            inviter_user_id=user.id, period=period
        ).first()
        is not None,
        "premium_until": gift.current_period_end.isoformat() + "Z"
        if gift and gift.current_period_end and gift.current_period_end > now
        else None,
    }
