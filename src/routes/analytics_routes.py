from datetime import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy.exc import IntegrityError

from src.models.user import AnalyticsEvent, User, db
from src.services.analytics import (
    CLIENT_EVENTS,
    RETURN_EVENTS,
    record_event,
    validate_anonymous_id,
    validate_properties,
)


analytics_bp = Blueprint("analytics", __name__)
MAX_BATCH_SIZE = 20


@analytics_bp.route("/analytics/events", methods=["POST"])
def ingest_analytics_events():
    payload = request.get_json(silent=True)
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_BATCH_SIZE:
        return jsonify({"error": "Envie entre 1 e 20 eventos."}), 400

    user = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    accepted = 0
    try:
        for item in events:
            if not isinstance(item, dict):
                raise ValueError("Evento inválido")
            event_name = item.get("name")
            if not isinstance(event_name, str) or event_name not in CLIENT_EVENTS:
                raise ValueError("Nome de evento inválido")
            anonymous_id = validate_anonymous_id(item.get("anonymous_id"))
            properties = validate_properties(item.get("properties"), event_name)
            dedupe_key = None
            if event_name in RETURN_EVENTS:
                if user is None:
                    raise ValueError("Evento de retorno requer autenticação")
                required_days = 1 if event_name == "returned_d1" else 7
                if user.created_at is None:
                    raise ValueError("Data da conta indisponível")
                account_age_days = (datetime.utcnow() - user.created_at).total_seconds() / 86400
                if account_age_days < required_days:
                    raise ValueError("Evento de retorno antecipado")
                dedupe_key = f"return:{event_name}:{user.analytics_subject_id}:{anonymous_id}"
                if AnalyticsEvent.query.filter_by(dedupe_key=dedupe_key).first():
                    continue
            record_event(
                event_name,
                user_id=user.id if user else None,
                anonymous_id=anonymous_id,
                properties=properties,
                dedupe_key=dedupe_key,
            )
            accepted += 1
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
    except IntegrityError:
        db.session.rollback()
        # A concurrent return check may win the unique deduplication race.
        return jsonify({"accepted": 0}), 200
    return jsonify({"accepted": accepted}), 202
