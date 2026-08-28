from flask import Blueprint, jsonify, request, session, abort, g, current_app
from src.models.user import (
    PersonalRecordEvent,
    User,
    UserProfile,
    WorkoutDay,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
    db,
)
from src.services.achievements import evaluate_achievements
from src.services.personal_records import (
    ensure_personal_record_history,
    serialize_personal_record,
)
from src.services.workout_progress import (
    backfill_session_weeks,
    confirmed_user_timezone,
    user_timezone,
)
from src.services.workout_plans import (
    catalog_for_prompt,
    recommend_split,
    workout_day_specs,
)
import math

from datetime import datetime, timedelta, timezone as datetime_timezone
from functools import wraps
import hmac
import secrets
from sqlalchemy.orm import selectinload
import unicodedata
from zoneinfo import ZoneInfo
from itsdangerous import URLSafeTimedSerializer

# Decorador para exigir login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify({"error": "Login necessário"}), 401
        
        # Carrega o usuário e anexa ao 'g' para uso em toda a requisição
        g.user = db.session.get(User, user_id)

        if g.user is None:
            # Caso o user_id na sessão seja inválido, limpa a sessão
            session.pop("user_id", None)
            return jsonify({"error": "Usuário não encontrado"}), 401
        if g.user.is_banned:
            session.clear()
            return jsonify({"error": "Sua conta foi banida."}), 403
            
        return f(*args, **kwargs)
    return decorated_function

# Decorador para exigir que o usuário seja admin
def admin_required(f):
    @wraps(f)
    @login_required # Garante que g.user já existe
    def decorated_function(*args, **kwargs):
        if not g.user.is_admin:
            return jsonify({"error": "Acesso negado"}), 403
        return f(*args, **kwargs)
    return decorated_function

# Decorator para exigir que o usuário seja premium
def premium_required(_func=None, *, allow_trial=False):
    def decorator(f):
        @wraps(f)
        @login_required # Garante que g.user já existe
        def decorated_function(*args, **kwargs):
            uses_trial = not g.user.has_entitlement("premium")
            if uses_trial and (not allow_trial or g.user.ai_trial_uses >= 3):
                return jsonify({
                    "error": "Acesso negado: Requer status Premium",
                    "code": "premium_required",
                }), 403
            response = current_app.make_response(f(*args, **kwargs))
            if uses_trial and 200 <= response.status_code < 300:
                g.user.ai_trial_uses += 1
                db.session.commit()
            return response
        return decorated_function
    return decorator(_func) if _func is not None else decorator


def _get_or_create_profile(user_id):
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.session.add(profile)
    return profile


def _local_date_for_timezone(timezone_name):
    return datetime.now(datetime_timezone.utc).astimezone(ZoneInfo(timezone_name)).date()


def _monday_after(date_value):
    return date_value - timedelta(days=date_value.weekday()) + timedelta(days=7)


def _promote_pending_workout_schedule(profile, timezone_name, local_date):
    if not profile.pending_workout_plan_id or not profile.workout_schedule_effective_from:
        return False
    if local_date < profile.workout_schedule_effective_from:
        return False
    profile.current_workout_plan_id = profile.pending_workout_plan_id
    profile.current_workout_schedule = profile.pending_workout_schedule
    profile.workout_schedule_timezone = timezone_name
    profile.pending_workout_plan_id = None
    profile.pending_workout_schedule = None
    profile.workout_schedule_effective_from = None
    return True


def _current_workout_schedule(profile, timezone_name, local_date):
    _promote_pending_workout_schedule(profile, timezone_name, local_date)
    schedule = profile.current_workout_schedule if profile.current_workout_plan_id else None
    if not schedule:
        return None
    if profile.workout_schedule_timezone and profile.workout_schedule_timezone != timezone_name:
        timezone_name = profile.workout_schedule_timezone
    return schedule


def _weekday_labels():
    return ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _schedule_day_map(schedule):
    mapping = {}
    for item in schedule or []:
        try:
            weekday = int(item.get("weekday"))
            day_id = int(item.get("day_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= weekday <= 6:
            mapping[weekday] = day_id
    return mapping
    
user_bp = Blueprint("user", __name__)

PLANS = (
    {"code": "free", "name": "Gratuito", "price_brl": 0, "features": ["Diário alimentar", "Medidas e progresso", "3 usos da IA"]},
    {"code": "premium_student", "name": "Premium Aluno", "price_brl": 20, "features": ["IA sem limite de teste", "Dietas personalizadas", "Treinos personalizados"]},
    {"code": "professional_single", "name": "Profissional Especialista", "price_brl": 50, "student_limit": 5, "features": ["Até 5 alunos", "Escolha entre dietas ou treinos", "Aprovação obrigatória"]},
    {"code": "professional_complete", "name": "Profissional Completo", "price_brl": 70, "student_limit": 5, "features": ["Até 5 alunos", "Dietas e treinos", "Aprovação obrigatória"]},
)


def _google_signup_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="google-signup")


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
        "user.auth_config",
        "user.check_session",
        "user.login",
        "user.register",
        "user.google_auth",
        "user.asaas_webhook",
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


@user_bp.before_request
def protect_session_mutations():
    return _csrf_protect_request()


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


def _login_oauth_identity(identity, claims):
    if identity.user.is_banned:
        session.clear()
        return jsonify({"error": "Sua conta foi banida."}), 403
    identity.email = claims["email"]
    identity.email_verified = claims["email_verified"]
    identity.display_name = claims["display_name"]
    identity.avatar_url = claims["avatar_url"]
    identity.last_login_at = datetime.utcnow()
    db.session.commit()
    _start_session(identity.user)
    return jsonify({"message": "Login bem-sucedido", "user": identity.user.to_dict(), "csrf_token": _csrf_token()}), 200


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Corpo JSON válido é obrigatório")
    return data


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


def page_query(query, default_limit=100):
    try:
        limit = min(max(int(request.args.get("limit", default_limit)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        abort(400, description="Paginação inválida")
    return query.limit(limit).offset(offset), limit, offset


def _text_or_none(value):
    text = str(value or "").strip()
    return text or None


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


@user_bp.errorhandler(400)
def bad_request(error):
    return jsonify({"error": getattr(error, "description", "Requisição inválida")}), 400


@user_bp.errorhandler(403)
def forbidden(error):
    return jsonify({"error": getattr(error, "description", "Acesso negado")}), 403


@user_bp.errorhandler(404)
def not_found(error):
    return jsonify({"error": getattr(error, "description", "Recurso não encontrado")}), 404


@user_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": getattr(error, "description", "Método não permitido")}), 405


@user_bp.errorhandler(413)
def payload_too_large(error):
    return jsonify({"error": "Requisição muito grande. Reduza o conteúdo."}), 413


@user_bp.errorhandler(500)
def internal_error(error):
    current_app.logger.exception("Unhandled error")
    return jsonify({"error": "Erro interno do servidor"}), 500


def _require_lengths(data, specs):
    """Aborta com 400 se algum campo exceder o limite máximo de caracteres."""
    for field, (max_len, label) in specs.items():
        value = data.get(field)
        if value is None:
            continue
        if len(str(value)) > max_len:
            abort(400, description=f"{label} deve ter no máximo {max_len} caracteres.")

def _workout_today_payload(user):
    profile = _get_or_create_profile(user.id)
    timezone_name = profile.timezone or user_timezone(user.id) or "UTC"
    local_date = _local_date_for_timezone(timezone_name)
    _promote_pending_workout_schedule(profile, timezone_name, local_date)

    active_session = WorkoutSession.query.filter_by(user_id=user.id, completed_at=None).first()
    if active_session:
        active_plan = WorkoutPlan.query.filter_by(
            id=active_session.workout_plan_id,
            user_id=user.id,
            status="published",
        ).options(selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises)).first()
        active_day = None
        if active_plan:
            active_day = next((day for day in active_plan.days if day.id == active_session.workout_day_id), None)
        return {
            "state": "active",
            "timezone": timezone_name,
            "local_date": local_date.isoformat(),
            "current_plan_id": active_plan.id if active_plan else None,
            "current_plan": active_plan.to_dict() if active_plan else None,
            "current_day": active_day.to_dict_full() if active_day else None,
            "session": active_session.to_dict(),
            "next_day": None,
            "week": [],
        }

    current_plan = None
    current_day = None
    schedule = profile.current_workout_schedule or []
    schedule_map = _schedule_day_map(schedule)
    current_day_id = schedule_map.get(local_date.weekday())

    if profile.current_workout_plan_id:
        current_plan = WorkoutPlan.query.filter_by(
            id=profile.current_workout_plan_id,
            user_id=user.id,
            status="published",
        ).options(selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises)).first()
        if not current_plan:
            profile.current_workout_plan_id = None
            profile.current_workout_schedule = None
            profile.pending_workout_plan_id = None
            profile.pending_workout_schedule = None
            profile.workout_schedule_effective_from = None
            profile.workout_schedule_timezone = None

    if current_plan and current_day_id:
        current_day = next((day for day in current_plan.days if day.id == current_day_id), None)

    base = {
        "timezone": timezone_name,
        "local_date": local_date.isoformat(),
        "current_plan_id": current_plan.id if current_plan else None,
        "current_plan": current_plan.to_dict() if current_plan else None,
        "current_day": current_day.to_dict_full() if current_day else None,
        "next_day": None,
        "week": [],
    }

    if not current_plan:
        base["state"] = "unconfigured"
        return base

    week_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    week = []
    upcoming_days = []
    for weekday in range(7):
        day_id = schedule_map.get(weekday)
        planned_day = next((day for day in current_plan.days if day.id == day_id), None) if day_id else None
        week.append({
            "weekday": weekday,
            "label": week_labels[weekday],
            "day_id": planned_day.id if planned_day else None,
            "day_title": planned_day.title if planned_day else None,
            "active": weekday == local_date.weekday() and bool(planned_day),
        })
        if weekday > local_date.weekday() and planned_day:
            upcoming_days.append(planned_day)
    if not upcoming_days:
        upcoming_days = [
            day for weekday in range(7)
            for day in [next((item for item in current_plan.days if item.id == schedule_map.get(weekday)), None)]
            if day
        ]
    base["week"] = week
    base["next_day"] = upcoming_days[0].to_dict_full() if upcoming_days else None

    if current_day is None:
        base["state"] = "rest"
        return base

    completed_session = WorkoutSession.query.filter_by(
        user_id=user.id,
        workout_plan_id=current_plan.id,
        workout_day_id=current_day.id,
    ).filter(WorkoutSession.completed_at.isnot(None)).order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc()).first()
    if completed_session:
        completed_sets = len(completed_session.completions)
        total_sets = len(current_day.exercises)
        base["completed_session"] = completed_session.to_dict()
        base["completed_sets"] = completed_sets
        base["total_sets"] = total_sets
        base["state"] = "partial" if completed_sets and completed_sets < total_sets else "completed"
        return base

    base["state"] = "scheduled"
    return base


def _editable_workout_plan(plan_id):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").options(
        selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises),
    ).with_for_update().first_or_404()
    active_session = WorkoutSession.query.filter_by(
        user_id=g.user.id,
        workout_plan_id=plan.id,
        completed_at=None,
    ).first()
    if active_session:
        abort(409, description="Finalize o treino em andamento antes de editar o plano.")
    return plan


def _version_workout_plan_for_edit(plan):
    if not WorkoutSession.query.filter_by(workout_plan_id=plan.id).first():
        return plan, {}, {}
    replacement = WorkoutPlan(
        user_id=plan.user_id,
        author_user_id=g.user.id,
        published_by_user_id=g.user.id,
        supersedes_plan_id=plan.id,
        status="published",
        source="manual",
        title=plan.title,
        description=plan.description,
        split_type=plan.split_type,
        days_per_week=plan.days_per_week,
        goal=plan.goal,
        experience_level=plan.experience_level,
        session_duration=plan.session_duration,
        questionnaire_data=dict(plan.questionnaire_data or {}),
    )
    db.session.add(replacement)
    db.session.flush()
    day_map = {}
    exercise_map = {}
    exercise_fields = (
        "catalog_key", "name", "movement_pattern", "primary_muscle", "equipment",
        "difficulty", "sets", "reps", "weight", "rest_seconds", "effort_guidance",
        "notes", "order",
    )
    for old_day in plan.days:
        new_day = WorkoutDay(
            workout_plan_id=replacement.id,
            code=old_day.code,
            title=old_day.title,
            focus=old_day.focus,
            order=old_day.order,
        )
        db.session.add(new_day)
        db.session.flush()
        day_map[old_day.id] = new_day
        for old_exercise in old_day.exercises:
            new_exercise = WorkoutExercise(
                workout_plan_id=replacement.id,
                workout_day_id=new_day.id,
                **{field: getattr(old_exercise, field) for field in exercise_fields},
            )
            db.session.add(new_exercise)
            db.session.flush()
            exercise_map[old_exercise.id] = new_exercise
    plan.status = "archived"
    return replacement, day_map, exercise_map


def _workout_questionnaire_for_plan(plan, days_per_week):
    questionnaire = dict(plan.questionnaire_data or {})
    questionnaire.setdefault("goal", plan.goal or "hypertrophy")
    questionnaire.setdefault("experience_level", plan.experience_level or "beginner")
    questionnaire.setdefault("session_duration", plan.session_duration or 45)
    questionnaire.setdefault("equipment", ["full_gym"])
    questionnaire.setdefault("limitations", "")
    questionnaire.setdefault("priorities", "")
    questionnaire.setdefault("avoid_exercises", "")
    questionnaire["days_per_week"] = days_per_week
    questionnaire["split_type"] = recommend_split(days_per_week, questionnaire["experience_level"])
    return questionnaire


def _flatten_workout_plan_exercises(plan):
    exercises = []
    for day in sorted(plan.days, key=lambda item: item.order):
        exercises.extend(sorted(day.exercises, key=lambda item: item.order or 0))
    return exercises


def _redistribute_workout_plan_data(plan, days_per_week):
    exercises = _flatten_workout_plan_exercises(plan)
    split_type = recommend_split(days_per_week, plan.experience_level or "beginner")
    specs = workout_day_specs(split_type, days_per_week)
    buckets = [[] for _ in range(days_per_week)]
    for index, exercise in enumerate(exercises):
        buckets[index % days_per_week].append(exercise)
    days = []
    for spec, bucket in zip(specs, buckets):
        days.append({
            "code": spec["code"],
            "title": spec["title"],
            "focus": spec.get("focus_guidance") or spec["title"],
            "order": spec["order"],
            "exercises": [
                {
                    "catalog_key": exercise.catalog_key,
                    "name": exercise.name,
                    "movement_pattern": exercise.movement_pattern,
                    "primary_muscle": exercise.primary_muscle,
                    "equipment": exercise.equipment,
                    "difficulty": exercise.difficulty,
                    "sets": exercise.sets,
                    "reps": exercise.reps,
                    "weight": exercise.weight,
                    "rest_seconds": exercise.rest_seconds,
                    "effort_guidance": exercise.effort_guidance,
                    "notes": exercise.notes,
                    "order": order,
                }
                for order, exercise in enumerate(bucket, start=1)
            ],
        })
    return {
        "title": f"{plan.title} (adaptado)",
        "description": f"Treino ajustado para {days_per_week} dias por semana."[:200],
        "days": days,
    }


def _apply_workout_plan_schedule(profile, plan, weekdays, timezone_name, local_date):
    schedule = [
        {"weekday": weekday, "day_id": day.id, "day_title": day.title, "day_code": day.code}
        for weekday, day in zip(weekdays, plan.days)
    ]
    profile.current_workout_plan_id = plan.id
    profile.current_workout_schedule = schedule
    profile.pending_workout_plan_id = None
    profile.pending_workout_schedule = None
    profile.workout_schedule_timezone = timezone_name
    profile.workout_schedule_effective_from = local_date
    return schedule


def _plan_catalog(plan):
    questionnaire = dict(plan.questionnaire_data or {})
    questionnaire.setdefault("experience_level", plan.experience_level or "beginner")
    questionnaire.setdefault("equipment", ["full_gym"])
    return catalog_for_prompt(questionnaire)


def _prescription(data, existing=None):
    try:
        sets = int(data.get("sets", existing.sets if existing else 3))
        rest_seconds = int(data.get("rest_seconds", existing.rest_seconds if existing else 60))
    except (TypeError, ValueError):
        abort(400, description="Séries ou descanso inválidos.")
    reps = str(data.get("reps", existing.reps if existing else "8-12")).strip()
    if not 1 <= sets <= 10 or not reps or len(reps) > 30 or not 0 <= rest_seconds <= 600:
        abort(400, description="Revise séries, repetições e descanso.")
    return {
        "sets": sets,
        "reps": reps,
        "rest_seconds": rest_seconds,
        "weight": str(data.get("weight", existing.weight if existing else "")).strip()[:50] or None,
        "effort_guidance": str(data.get("effort_guidance", existing.effort_guidance if existing else "")).strip()[:100] or None,
        "notes": str(data.get("notes", existing.notes if existing else "")).strip()[:500] or None,
    }


def _set_catalog_exercise(exercise, catalog_item):
    exercise.catalog_key = catalog_item["key"]
    exercise.name = catalog_item["name"]
    exercise.movement_pattern = catalog_item["movement_pattern"]
    exercise.primary_muscle = catalog_item["primary_muscle"]
    exercise.equipment = catalog_item["equipment"]
    exercise.difficulty = catalog_item["difficulty"]


def _owned_active_session(session_id):
    return WorkoutSession.query.filter_by(
        id=session_id,
        user_id=g.user.id,
        completed_at=None,
    ).with_for_update().first()


def _session_exercise(session, exercise_id):
    return WorkoutExercise.query.filter_by(
        id=exercise_id,
        workout_plan_id=session.workout_plan_id,
        workout_day_id=session.workout_day_id,
    ).first()


def _performed_sets_payload(data):
    if data is None:
        return []
    if not isinstance(data, dict):
        abort(400, description="Corpo JSON inválido")
    raw_sets = data.get("sets", [])
    if not isinstance(raw_sets, list) or len(raw_sets) > 20:
        abort(400, description="Séries executadas inválidas")

    performed_sets = []
    for index, raw_set in enumerate(raw_sets, start=1):
        if not isinstance(raw_set, dict):
            abort(400, description="Série executada inválida")
        try:
            raw_repetitions = raw_set.get("repetitions")
            numeric_repetitions = float(raw_repetitions)
            if isinstance(raw_repetitions, bool) or not numeric_repetitions.is_integer():
                raise ValueError
            repetitions = int(numeric_repetitions)
            raw_load = raw_set.get("load_kg")
            if isinstance(raw_load, bool):
                raise ValueError
            load_kg = None if raw_load in (None, "") else float(raw_load)
        except (TypeError, ValueError):
            abort(400, description="Carga ou repetições inválidas")
        if repetitions < 1 or repetitions > 1000:
            abort(400, description="Repetições devem estar entre 1 e 1000")
        if load_kg is not None and (not math.isfinite(load_kg) or load_kg < 0 or load_kg > 100000):
            abort(400, description="Carga deve estar entre 0 e 100000 kg")
        is_warmup = raw_set.get("is_warmup", False)
        if not isinstance(is_warmup, bool):
            abort(400, description="Tipo de série inválido")
        performed_sets.append({
            "set_order": index,
            "repetitions": repetitions,
            "load_kg": load_kg,
            "is_warmup": is_warmup,
        })
    return performed_sets


def _workout_session_summary(session_record):
    overrides = {override.workout_exercise_id: override for override in session_record.overrides}
    exercises = []
    total_sets = 0
    volume_total = 0.0
    has_performed_sets = False
    all_sets_have_load = True
    record_events = PersonalRecordEvent.query.filter_by(
        workout_session_id=session_record.id,
    ).order_by(PersonalRecordEvent.id).all()
    records_by_set = {}
    records_by_completion = {}
    for event in record_events:
        records_by_set.setdefault(event.set_id, []).append(event)
        records_by_completion.setdefault(event.completion_id, []).append(event)

    for completion in session_record.completions:
        override = overrides.get(completion.workout_exercise_id)
        exercise = completion.exercise
        performed_sets = [
            {
                "set_order": item.set_order,
                "repetitions": item.repetitions,
                "load_kg": float(item.load_kg) if item.load_kg is not None else None,
                "is_warmup": item.is_warmup,
                "personal_records": [
                    serialize_personal_record(event)
                    for event in records_by_set.get(item.id, [])
                    if event.is_highlighted and not event.is_initial
                ],
            }
            for item in completion.performed_sets
        ]
        total_sets += len(performed_sets)
        if performed_sets:
            has_performed_sets = True
        if performed_sets and all(item["load_kg"] is not None for item in performed_sets):
            volume_total += sum(item["load_kg"] * item["repetitions"] for item in performed_sets)
        elif performed_sets:
            all_sets_have_load = False

        effective_sets = [item for item in performed_sets if not item["is_warmup"]]
        best_set_item = max(
            effective_sets,
            key=lambda item: (
                item["load_kg"] if item["load_kg"] is not None else -1,
                item["repetitions"],
            ),
            default=None,
        )
        best_set = ({
            "set_order": best_set_item["set_order"],
            "repetitions": best_set_item["repetitions"],
            "load_kg": best_set_item["load_kg"],
        } if best_set_item else None)
        exercises.append({
            "exercise_id": completion.workout_exercise_id,
            "name": completion.exercise_name or (override.name if override else exercise.name),
            "catalog_key": completion.exercise_catalog_key or (
                override.catalog_key if override else exercise.catalog_key
            ),
            "sets_performed": len(performed_sets),
            "sets": performed_sets,
            "best_set": best_set,
            "personal_records": [
                serialize_personal_record(event)
                for event in records_by_completion.get(completion.id, [])
                if event.is_highlighted and not event.is_initial
            ],
        })

    completed_at = session_record.completed_at or datetime.utcnow()
    duration_seconds = max(0, int((completed_at - session_record.started_at).total_seconds()))
    total_exercises = WorkoutExercise.query.filter_by(
        workout_plan_id=session_record.workout_plan_id,
        workout_day_id=session_record.workout_day_id,
    ).count()
    return {
        "id": session_record.id,
        "session_id": session_record.id,
        "user_id": str(session_record.user_id),
        "workout_name": session_record.day.title or session_record.plan.title,
        "plan_name": session_record.plan.title,
        "started_at": session_record.started_at.isoformat(),
        "completed_at": session_record.completed_at.isoformat() if session_record.completed_at else None,
        "duration_seconds": duration_seconds,
        "exercises_performed": len(exercises),
        "total_exercises": total_exercises,
        "sets_performed": total_sets,
        "volume_total_kg": round(volume_total, 2) if has_performed_sets and all_sets_have_load else None,
        "workout_plan_id": session_record.workout_plan_id,
        "workout_day_id": session_record.workout_day_id,
        "privacy": "private",
        "personal_records": [
            serialize_personal_record(event)
            for event in record_events
            if event.is_highlighted and not event.is_initial
        ],
        "exercises": exercises,
    }


def _ensure_user_workout_history(user_id):
    User.query.filter_by(id=user_id).with_for_update().first()
    ensure_personal_record_history(user_id)
    timezone_name = confirmed_user_timezone(user_id)
    if timezone_name:
        backfill_session_weeks(user_id, timezone_name)
    evaluate_achievements(user_id, backfilled=True)
    db.session.commit()


def _activity_list_item(session_record):
    summary = _workout_session_summary(session_record)
    return {
        "id": session_record.id,
        "workout_name": summary["workout_name"],
        "plan_name": summary["plan_name"],
        "started_at": summary["started_at"],
        "completed_at": summary["completed_at"],
        "duration_seconds": summary["duration_seconds"],
        "exercises_performed": summary["exercises_performed"],
        "total_exercises": summary["total_exercises"],
        "sets_performed": summary["sets_performed"],
        "volume_total_kg": summary["volume_total_kg"],
        "personal_record_count": len(summary["personal_records"]),
        "privacy": "private",
    }
