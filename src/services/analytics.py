import json
import math
import re
import uuid

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
})
CLIENT_EVENTS = frozenset({
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
