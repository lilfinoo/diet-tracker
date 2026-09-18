import hmac
import math
import secrets
import time
import unicodedata
from functools import wraps

from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from flask import abort, current_app, jsonify, request, session

from src.models.user import IdempotentOperation, User, db
from src.services.analytics import record_event


def _start_session(user):
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    session["csrf_token"] = secrets.token_urlsafe(32)
    session["authenticated_at"] = int(time.time())


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _csrf_protect_request():
    if not current_app.config.get("CSRF_PROTECTION", True):
        return None
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.endpoint == "billing.asaas_webhook":
        return None
    if request.endpoint in {"auth.login", "auth.register", "auth.google_auth"} and not session.get("user_id"):
        return None
    if not session.get("user_id"):
        return None
    expected = session.get("csrf_token")
    received = request.headers.get("X-CSRF-Token", "")
    if not expected or not received or not hmac.compare_digest(str(expected), str(received)):
        return jsonify({"error": "Token CSRF inválido."}), 403
    return None


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify({"error": "Login necessário"}), 401

        g_user = db.session.get(User, user_id)
        if g_user is None:
            session.pop("user_id", None)
            return jsonify({"error": "Usuário não encontrado"}), 401
        if g_user.is_banned:
            session.clear()
            return jsonify({"error": "Sua conta foi banida."}), 403

        from flask import g
        g.user = g_user
        return f(*args, **kwargs)

    return decorated_function


def idempotent_mutation(f):
    """Replay the original JSON response for a repeated mutation key."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key:
            return f(*args, **kwargs)
        if len(key) > 128:
            return jsonify({"error": "Idempotency-Key inválida."}), 400

        user_id = session.get("user_id")
        existing = IdempotentOperation.query.filter_by(
            user_id=user_id,
            idempotency_key=key,
        ).first()
        if existing:
            if existing.method != request.method or existing.path != request.path:
                return jsonify({"error": "A chave de idempotência já foi usada em outra operação."}), 409
            return jsonify(existing.response_payload), existing.status_code

        response = current_app.make_response(f(*args, **kwargs))
        if not 200 <= response.status_code < 300 or not response.is_json:
            return response
        payload = response.get_json(silent=True)
        if not isinstance(payload, dict):
            return response

        operation = IdempotentOperation(
            user_id=user_id,
            idempotency_key=key,
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            response_payload=payload,
        )
        db.session.add(operation)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = IdempotentOperation.query.filter_by(
                user_id=user_id,
                idempotency_key=key,
            ).first()
            if existing:
                return jsonify(existing.response_payload), existing.status_code
            raise
        return response

    return decorated_function


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        from flask import g
        if not g.user.is_admin:
            return jsonify({"error": "Acesso negado"}), 403
        return f(*args, **kwargs)

    return decorated_function


def premium_required(_func=None, *, allow_trial=False):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            from flask import g
            uses_trial = not g.user.has_entitlement("premium")
            if uses_trial and not allow_trial:
                record_event("premium_limit_reached", user_id=g.user.id, commit=True)
                return jsonify({"error": "Acesso negado: Requer status Premium", "code": "premium_required"}), 403
            reserved_trial = False
            if uses_trial:
                reserved_trial = bool(User.query.filter(
                    User.id == g.user.id,
                    User.ai_trial_uses < 3,
                ).update({User.ai_trial_uses: User.ai_trial_uses + 1}, synchronize_session=False))
                db.session.commit()
                if not reserved_trial:
                    record_event("premium_limit_reached", user_id=g.user.id, commit=True)
                    return jsonify({"error": "Acesso negado: Requer status Premium", "code": "premium_required"}), 403
            try:
                response = current_app.make_response(f(*args, **kwargs))
            except Exception:
                if reserved_trial:
                    User.query.filter(User.id == g.user.id, User.ai_trial_uses > 0).update(
                        {User.ai_trial_uses: User.ai_trial_uses - 1},
                        synchronize_session=False,
                    )
                    db.session.commit()
                raise
            if reserved_trial and 200 <= response.status_code < 300:
                record_event("free_premium_use", user_id=g.user.id, commit=True)
            elif reserved_trial:
                User.query.filter(User.id == g.user.id, User.ai_trial_uses > 0).update(
                    {User.ai_trial_uses: User.ai_trial_uses - 1},
                    synchronize_session=False,
                )
                db.session.commit()
            return response

        return decorated_function

    return decorator(_func) if _func is not None else decorator


def ai_consent_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        from flask import g

        if not g.user.has_current_ai_consent():
            return jsonify({
                "error": "Autorize o processamento por IA antes de usar este recurso.",
                "code": "ai_consent_required",
            }), 403
        return f(*args, **kwargs)

    return decorated_function


def ai_consent_error():
    return jsonify({
        "error": "O titular dos dados precisa autorizar o processamento por IA.",
        "code": "ai_consent_required",
    }), 403


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Corpo JSON válido é obrigatório")
    return data


def page_query(query, default_limit=100):
    try:
        limit = min(max(int(request.args.get("limit", default_limit)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        abort(400, description="Paginação inválida")
    return query.limit(limit).offset(offset), limit, offset


_USER_ROUTE_HELPERS = {
    "_get_or_create_profile",
    "_local_date_for_timezone",
    "_monday_after",
    "_promote_pending_workout_schedule",
    "_current_workout_schedule",
    "_weekday_labels",
    "_schedule_day_map",
    "_workout_today_payload",
    "_editable_workout_plan",
    "_version_workout_plan_for_edit",
    "_apply_workout_plan_schedule",
    "_plan_catalog",
    "_prescription",
    "_redistribute_workout_plan_data",
    "_set_catalog_exercise",
    "_workout_questionnaire_for_plan",
    "_owned_active_session",
    "_session_exercise",
    "_performed_sets_payload",
    "_workout_session_summary",
    "_ensure_user_workout_history",
    "_activity_list_item",
}


def __getattr__(name):
    if name in _USER_ROUTE_HELPERS:
        from src.routes import user_routes

        return getattr(user_routes, name)
    raise AttributeError(f"module 'src.routes.common' has no attribute {name!r}")


def _coerce_number(value):
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def normalize_height(value):
    number = _coerce_number(value)
    if 0 < number <= 3:
        number *= 100
    return round(number, 6)


def coerce_numbers(data, fields, *, height_fields=()):
    data = data.copy()
    height_fields = set(height_fields)
    try:
        for field in fields:
            if field in data and data[field] not in (None, ""):
                data[field] = normalize_height(data[field]) if field in height_fields else _coerce_number(data[field])
            elif field in data:
                data[field] = None
    except (TypeError, ValueError):
        abort(400, description="Campo numérico inválido")
    return data


def _text_or_none(value):
    text = str(value or "").strip()
    return text or None


def chat_plan_intent(data, message):
    intent = data.get("intent")
    if intent in {"diet_plan", "workout_plan"}:
        return intent
    if intent is not None:
        abort(400, description="Intenção de plano inválida")

    normalized_message = unicodedata.normalize("NFKD", message.lower())
    normalized_message = "".join(char for char in normalized_message if not unicodedata.combining(char))
    if any(term in normalized_message for term in ("plano de dieta", "plano de alimentacao", "minha dieta", "cardapio")):
        return "diet_plan"
    if any(term in normalized_message for term in ("plano de treino", "rotina de exercicios", "rotina de treino", "meu treino")):
        return "workout_plan"
    return None


def _require_lengths(data, specs):
    for field, (max_len, label) in specs.items():
        value = data.get(field)
        if value is None:
            continue
        if len(str(value)) > max_len:
            abort(400, description=f"{label} deve ter no máximo {max_len} caracteres.")


def _google_signup_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="google-signup")


def _google_identity_claims(payload):
    issuer = payload.get("iss")
    subject = payload.get("sub")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"} or not subject:
        raise ValueError("Invalid Google identity")
    return {
        "provider": "google",
        "issuer": issuer,
        "subject": str(subject),
        "email": str(payload.get("email", ""))[:320] or None,
        "email_verified": payload.get("email_verified") is True or payload.get("email_verified") == "true",
        "display_name": str(payload.get("name", ""))[:255] or None,
        "avatar_url": str(payload.get("picture", ""))[:2048] or None,
    }
