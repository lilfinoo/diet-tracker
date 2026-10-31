import json
import math
import re
import uuid
import hashlib
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from src.models.user import AnalyticsEvent, User, db


ALLOWED_EVENTS = frozenset({
    "app_viewed",
    "signup_started",
    "signup_completed",
    "profile_completed",
    "plan_generation_requested",
    "plan_generation_succeeded",
    "plan_set_current",
    "workout_started",
    "exercise_completed",
    "workout_finished",
    "meal_logged",
    "measurement_logged",
    "ai_chat_completed",
    "free_premium_use",
    "premium_limit_reached",
    "paywall_viewed",
    "checkout_started",
    "subscription_activated",
    "returned_d1",
    "returned_d7",
    "paywall_experiment_enrolled",
    "subscription_payment_confirmed",
    "paywall_cta_clicked",
})
CLIENT_EVENTS = frozenset({
    "paywall_cta_clicked",
    "app_viewed",
    "signup_started",
    "plan_generation_requested",
    "paywall_viewed",
    "returned_d1",
    "returned_d7",
})
RETURN_EVENTS = frozenset({"returned_d1", "returned_d7"})
UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign")
_PROPERTY_KEY = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
_EMAIL_VALUE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
EVENT_PROPERTIES = {
    "paywall_cta_clicked": {"plan_code", "platform"},
    "paywall_experiment_enrolled": {"surface", "platform"},
    "subscription_payment_confirmed": {"plan_code", "provider"},
    "app_viewed": set(),
    "signup_started": {"surface"},
    "signup_completed": set(),
    "profile_completed": set(),
    "plan_generation_requested": {"plan_type", "surface"},
    "plan_generation_succeeded": {"plan_type"},
    "plan_set_current": {"plan_type"},
    "workout_started": set(),
    "exercise_completed": set(),
    "workout_finished": set(),
    "meal_logged": set(),
    "measurement_logged": set(),
    "ai_chat_completed": set(),
    "free_premium_use": set(),
    "premium_limit_reached": set(),
    "paywall_viewed": {"surface"},
    "checkout_started": {"plan_code", "payment_method"},
    "subscription_activated": {"plan_code", "provider"},
    "returned_d1": {"account_age_days"},
    "returned_d7": {"account_age_days"},
}

PAYWALL_EXPERIMENT = "paywall_message_v1"
PAYWALL_SURFACES = {"app_open", "plans_modal", "photos", "diet_plans", "workout_plans", "plans", "premium", "chat"}
EXPERIMENT_FIELDS = {"experiment_id", "variant"}
EXPERIMENT_EVENTS = {"paywall_viewed", "paywall_cta_clicked", "checkout_started", "subscription_payment_confirmed", "paywall_experiment_enrolled"}
for _event_name in EXPERIMENT_EVENTS:
    EVENT_PROPERTIES[_event_name] |= EXPERIMENT_FIELDS


def paywall_enrollment(subject_id):
    return AnalyticsEvent.query.filter_by(dedupe_key=f"{PAYWALL_EXPERIMENT}:{subject_id}").first()


def paywall_assignment(subject_id):
    # Fixed experiment salt and account identity keep the same split across devices.
    bucket = hashlib.sha256(f"{PAYWALL_EXPERIMENT}:{subject_id}".encode()).digest()[0]
    return {"experiment_id": PAYWALL_EXPERIMENT, "variant": "A" if bucket < 128 else "B"}


def record_payment_confirmed(user_id, plan_code, provider, payment_id, *, paid_at=None):
    key = "payment:" + hashlib.sha256(f"{provider}:{payment_id}".encode()).hexdigest()
    if AnalyticsEvent.query.filter_by(dedupe_key=key).first():
        return
    event = record_event("subscription_payment_confirmed", user_id=user_id,
                         properties={"plan_code": plan_code, "provider": provider}, dedupe_key=key)
    if paid_at is not None:
        event.created_at = min(paid_at, datetime.utcnow())


def paywall_report(from_date, to_date):
    now = datetime.utcnow()
    enrollments = AnalyticsEvent.query.filter(
        AnalyticsEvent.event_name == "paywall_experiment_enrolled",
        AnalyticsEvent.created_at >= datetime.combine(from_date, datetime.min.time()),
        AnalyticsEvent.created_at <= datetime.combine(to_date, datetime.max.time()),
    ).all()
    cohorts = {event.subject_id: event for event in enrollments
               if event.properties.get("experiment_id") == PAYWALL_EXPERIMENT}
    events_by_subject = {}
    if cohorts:
        events = AnalyticsEvent.query.filter(
            AnalyticsEvent.subject_id.in_(cohorts),
            AnalyticsEvent.created_at >= min(event.created_at for event in cohorts.values()),
            AnalyticsEvent.created_at <= now,
            AnalyticsEvent.event_name.in_({"paywall_viewed", "paywall_cta_clicked", "checkout_started", "subscription_payment_confirmed",
                                          "meal_logged", "workout_finished", "measurement_logged", "returned_d7"}),
        ).all()
        for event in events:
            events_by_subject.setdefault(event.subject_id, []).append(event)
    rows = []
    for variant in ("A", "B"):
        row = dict(variant=variant, users=0, viewed=0, clicked=0, checkout=0, paid=0,
                   mature_30=0, paid_30=0, eligible_d7=0, retained_d7=0)
        for subject_id, enrollment in cohorts.items():
            if enrollment.properties.get("variant") != variant:
                continue
            row["users"] += 1
            events = [event for event in events_by_subject.get(subject_id, [])
                      if timedelta(0) <= event.created_at - enrollment.created_at < timedelta(days=30)]
            names = {event.event_name for event in events}
            row["viewed"] += "paywall_viewed" in names
            row["clicked"] += "paywall_cta_clicked" in names
            row["checkout"] += "checkout_started" in names
            paid = "subscription_payment_confirmed" in names
            row["paid"] += paid
            if now - enrollment.created_at >= timedelta(days=30):
                row["mature_30"] += 1
                row["paid_30"] += paid
            if now - enrollment.created_at >= timedelta(days=14):
                row["eligible_d7"] += 1
                row["retained_d7"] += any(
                    timedelta(days=7) <= event.created_at - enrollment.created_at < timedelta(days=14)
                    and event.event_name in {"meal_logged", "workout_finished", "measurement_logged", "returned_d7"}
                    for event in events)
        rows.append(row)
    return {"experiment_id": PAYWALL_EXPERIMENT, "variants": rows}


def validate_anonymous_id(value, *, required=True):
    if value in (None, "") and not required:
        return None
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("anonymous_id inválido")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValueError("anonymous_id inválido") from None
    if str(parsed) != value.lower() or parsed.version != 4:
        raise ValueError("anonymous_id inválido")
    return str(parsed)


def validate_properties(value, event_name=None):
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 20:
        raise ValueError("properties inválidas")
    cleaned = {}
    allowed = EVENT_PROPERTIES.get(event_name) if event_name else None
    for key, item in value.items():
        if not isinstance(key, str) or not _PROPERTY_KEY.fullmatch(key):
            raise ValueError("properties inválidas")
        if allowed is not None and key not in allowed and key not in UTM_FIELDS:
            raise ValueError("property não permitida para este evento")
        if item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("properties inválidas")
        if isinstance(item, str) and len(item) > 500:
            raise ValueError("properties inválidas")
        if isinstance(item, str) and _EMAIL_VALUE.search(item):
            raise ValueError("properties não podem conter e-mail")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("properties inválidas")
        cleaned[key] = item
    if len(json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 4096:
        raise ValueError("properties muito grandes")
    return cleaned


def analytics_context(value):
    if not isinstance(value, dict):
        return None, {}
    try:
        anonymous_id = validate_anonymous_id(value.get("anonymous_id"), required=False)
        properties = validate_properties({
            key: value[key]
            for key in UTM_FIELDS
            if isinstance(value.get(key), str) and value[key] and len(value[key]) <= 200
        })
    except ValueError:
        return None, {}
    return anonymous_id, properties


def record_event(event_name, *, user_id=None, subject_id=None, anonymous_id=None, properties=None, dedupe_key=None, commit=False):
    if event_name not in ALLOWED_EVENTS:
        raise ValueError("Evento de analytics inválido")
    if user_id is not None:
        user = db.session.get(User, user_id)
        if user is None:
            raise ValueError("Usuário de analytics inválido")
        subject_id = user.analytics_subject_id
    properties = dict(properties or {})
    if event_name in EXPERIMENT_EVENTS:
        # Attribution is always server-owned, even for public client events.
        for field in EXPERIMENT_FIELDS:
            properties.pop(field, None)
        enrollment = paywall_enrollment(subject_id) if subject_id is not None else None
        if enrollment:
            properties.update({field: enrollment.properties[field] for field in EXPERIMENT_FIELDS})
        elif event_name == "paywall_experiment_enrolled":
            properties.update(paywall_assignment(subject_id))
    event = AnalyticsEvent(
        event_name=event_name,
        subject_id=subject_id,
        anonymous_id=validate_anonymous_id(anonymous_id, required=False),
        properties=validate_properties(properties, event_name),
        dedupe_key=dedupe_key,
    )
    db.session.add(event)
    if not commit:
        return event
    try:
        db.session.commit()
        return event
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to persist analytics event %s", event_name)
        return None
