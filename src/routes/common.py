import hmac
import secrets
import unicodedata
from functools import wraps

from itsdangerous import URLSafeTimedSerializer

from flask import abort, current_app, jsonify, request, session

from src.models.user import User, db


def _start_session(user):
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    session["csrf_token"] = secrets.token_urlsafe(32)


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
    if request.endpoint in {"auth.auth_config", "auth.check_session", "auth.login", "auth.register", "auth.google_auth"}:
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
            if uses_trial and (not allow_trial or g.user.ai_trial_uses >= 3):
                return jsonify({"error": "Acesso negado: Requer status Premium", "code": "premium_required"}), 403
            response = current_app.make_response(f(*args, **kwargs))
            if uses_trial and 200 <= response.status_code < 300:
                g.user.ai_trial_uses += 1
                db.session.commit()
            return response

        return decorated_function

    return decorator(_func) if _func is not None else decorator


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


def coerce_numbers(data, fields):
    data = data.copy()
    try:
        for field in fields:
            if field in data and data[field] not in (None, ""):
                data[field] = float(data[field])
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


def _start_session(user):
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    session["csrf_token"] = secrets.token_urlsafe(32)


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _csrf_exempt():
    return request.endpoint in {
        "auth.auth_config",
        "auth.check_session",
        "auth.login",
        "auth.register",
        "auth.google_auth",
        "billing.asaas_webhook",
    }


def _csrf_protect_request():
    if not current_app.config.get("CSRF_PROTECTION", True):
        return None
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if _csrf_exempt() or not session.get("user_id"):
        return None
    expected = session.get("csrf_token")
    received = request.headers.get("X-CSRF-Token", "")
    if not expected or not received or not hmac.compare_digest(str(expected), str(received)):
        return jsonify({"error": "Token CSRF inválido."}), 403
    return None
