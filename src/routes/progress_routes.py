from src.services.body_progress import body_summary
from src.services.performance import performed_exercises, exercise_sessions, historical_load
from datetime import timedelta

from flask import Blueprint, g, jsonify, request

from src.models.user import AchievementUnlock, ExerciseGoal, PersonalRecordEvent, UserProfile, WorkoutSession, WorkoutSessionExerciseCompletion, WorkoutWeeklyGoal, db
from src.routes.common import _activity_list_item, _ensure_user_workout_history, json_body, login_required, page_query
from src.services.consistency import consistency_days
from src.services.achievements import achievement_catalog, serialize_unlock
from src.services.badges import serialize_badges, serialize_profile_highlights
from src.services.personal_records import current_max_load, exercise_progress, serialize_personal_record
from src.services.workout_plans import catalog_by_key
from src.services.workout_progress import (
    backfill_session_weeks,
    create_weekly_goal,
    current_exercise_goal,
    serialize_exercise_goal,
    serialize_weekly_goal,
    validate_timezone,
    week_start_for,
    weekly_progress,
)
from decimal import Decimal, InvalidOperation


progress_bp = Blueprint("progress", __name__)


@progress_bp.route("/progress/weekly", methods=["GET", "PUT"])
@login_required
def weekly_goal_progress():
    if request.method == "GET":
        _ensure_user_workout_history(g.user.id)
        return jsonify(weekly_progress(g.user.id)), 200

    data = json_body()
    try:
        timezone_name = validate_timezone(data.get("timezone"))
    except ValueError:
        return jsonify({"error": "Confirme um timezone válido."}), 400
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if not profile:
        profile = UserProfile(user_id=g.user.id)
        db.session.add(profile)
    profile.timezone = timezone_name
    current_week = week_start_for(None, timezone_name)
    has_goal = WorkoutWeeklyGoal.query.filter_by(user_id=g.user.id).first() is not None
    effective_week = current_week + timedelta(days=7) if has_goal else current_week
    try:
        goal = create_weekly_goal(
            g.user.id,
            data.get("target_sessions"),
            timezone_name,
            effective_week_start=effective_week,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    backfill_session_weeks(g.user.id, timezone_name)
    db.session.commit()
    return jsonify({
        "message": "Meta semanal salva.",
        "goal": serialize_weekly_goal(goal),
        "progress": weekly_progress(g.user.id),
    }), 200


@progress_bp.route("/progress/exercise-goals", methods=["GET", "POST"])
@login_required
def exercise_goals():
    _ensure_user_workout_history(g.user.id)
    if request.method == "GET":
        goals = ExerciseGoal.query.filter_by(user_id=g.user.id).order_by(
            ExerciseGoal.created_at.desc()
        ).all()
        return jsonify({
            "active": serialize_exercise_goal(current_exercise_goal(g.user.id)),
            "items": [serialize_exercise_goal(item) for item in goals],
        }), 200

    if current_exercise_goal(g.user.id):
        return jsonify({"error": "Conclua ou cancele a meta de exercício atual."}), 409
    data = json_body()
    exercise_key = str(data.get("exercise_key", "")).strip()
    try:
        target_load = Decimal(str(data.get("target_load_kg"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({"error": "Carga alvo inválida."}), 400
    if not target_load.is_finite() or target_load <= 0 or target_load > Decimal("100000"):
        return jsonify({"error": "Carga alvo inválida."}), 400
    completion = (
        WorkoutSessionExerciseCompletion.query.join(WorkoutSession)
        .filter(
            WorkoutSession.user_id == g.user.id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSessionExerciseCompletion.exercise_catalog_key == exercise_key,
        )
        .order_by(WorkoutSession.completed_at.desc())
        .first()
    )
    catalog_item = catalog_by_key().get(exercise_key)
    if not completion and not catalog_item:
        return jsonify({"error": "Exercício sem histórico ou identidade estável."}), 404
    current_load = current_max_load(g.user.id, exercise_key)
    if current_load is not None and target_load <= current_load:
        return jsonify({"error": "A meta deve superar sua maior carga atual."}), 400
    goal = ExerciseGoal(
        user_id=g.user.id,
        exercise_key=exercise_key,
        exercise_name=(completion.exercise_name if completion else catalog_item["name"]),
        target_load_kg=target_load,
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify({"message": "Meta de exercício criada.", "goal": serialize_exercise_goal(goal)}), 201


@progress_bp.route("/progress/exercise-goals/<uuid:goal_id>", methods=["DELETE"])
@login_required
def cancel_exercise_goal(goal_id):
    goal = ExerciseGoal.query.filter_by(
        id=goal_id,
        user_id=g.user.id,
        status="active",
    ).with_for_update().first_or_404()
    if goal.status != "active":
        return jsonify({"error": "Esta meta não está mais ativa."}), 409
    goal.status = "cancelled"
    db.session.commit()
    return jsonify({"message": "Meta cancelada.", "goal": serialize_exercise_goal(goal)}), 200


@progress_bp.route("/progress/exercises/<path:exercise_key>", methods=["GET"])
@login_required
def get_exercise_progress(exercise_key):
    _ensure_user_workout_history(g.user.id)
    options = performed_exercises(g.user.id)
    exercise = next((item for item in options if item['key'] == exercise_key), None)
    if exercise is None:
        return jsonify({"error": "Histórico do exercício não encontrado."}), 404
    _, limit, offset = page_query(WorkoutSession.query, default_limit=20)
    sessions = exercise_sessions(g.user.id, exercise_key, limit, offset)
    return jsonify({
        "exercise_key": exercise_key, "exercise_name": exercise['name'],
        "max_load_kg": historical_load(g.user.id, exercise_key),
        "records": exercise_progress(g.user.id, exercise_key),
        "sessions": sessions,
        "recent_activities": [_activity_list_item(item) for item in WorkoutSession.query.filter(
            WorkoutSession.user_id == g.user.id,
            WorkoutSession.id.in_([item['session_id'] for item in sessions['items']]),
        ).order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc()).all()] if request.args.get('view') != 'sessions' else [],
    }), 200


@progress_bp.route("/progress/exercises", methods=["GET"])
@login_required
def exercise_options():
    return jsonify({"items": performed_exercises(g.user.id)}), 200


@progress_bp.route("/progress/achievements", methods=["GET"])
@login_required
def get_achievements():
    _ensure_user_workout_history(g.user.id)
    records = PersonalRecordEvent.query.filter_by(
        user_id=g.user.id,
        is_highlighted=True,
    ).order_by(PersonalRecordEvent.achieved_at.desc()).limit(100).all()
    return jsonify({
        "items": achievement_catalog(g.user.id),
        "badges": serialize_badges(g.user.badges),
        "selected": serialize_profile_highlights(g.user.profile_highlights),
        "personal_records": [serialize_personal_record(item) for item in records],
        "highlight_limit": 3,
    }), 200


@progress_bp.route("/progress/personal-records", methods=["GET"])
@login_required
def personal_records():
    _ensure_user_workout_history(g.user.id)
    query = PersonalRecordEvent.query.filter_by(
        user_id=g.user.id,
        is_highlighted=True,
    ).order_by(PersonalRecordEvent.achieved_at.desc(), PersonalRecordEvent.id.desc())
    query, limit, offset = page_query(query, default_limit=50)
    records = query.all()
    return jsonify({
        "items": [serialize_personal_record(item) for item in records],
        "limit": limit,
        "offset": offset,
    }), 200


@progress_bp.route("/progress/overview", methods=["GET"])
@login_required
def progress_overview():
    _ensure_user_workout_history(g.user.id)
    compact = request.args.get("view") == "summary"
    recent_sessions = [] if compact else (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == g.user.id,
            WorkoutSession.completed_at.isnot(None),
        )
        .order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc())
        .limit(5)
        .all()
    )
    recent_records = [] if compact else PersonalRecordEvent.query.filter(
        PersonalRecordEvent.user_id == g.user.id,
        PersonalRecordEvent.is_highlighted.is_(True),
    ).order_by(PersonalRecordEvent.achieved_at.desc(), PersonalRecordEvent.id.desc()).limit(5).all()
    recent_unlocks = [] if compact else AchievementUnlock.query.filter_by(user_id=g.user.id).order_by(
        AchievementUnlock.unlocked_at.desc(), AchievementUnlock.id.desc()
    ).limit(5).all()
    exercises = performed_exercises(g.user.id)
    recent_performance = None
    if exercises:
        selected = exercises[0]
        recent_performance = {
            **selected,
            "sessions": exercise_sessions(g.user.id, selected['key'], limit=1),
            "max_load_kg": historical_load(g.user.id, selected['key']),
        }
    weekly = weekly_progress(g.user.id)
    return jsonify({
        "body": body_summary(g.user.id),
        "performance": {"exercises": exercises, "recent": recent_performance},
        "weekly": weekly,
        "consistency": consistency_days(g.user.id),
        "exercise_goal": serialize_exercise_goal(current_exercise_goal(g.user.id)),
        "recent_personal_records": [serialize_personal_record(item) for item in recent_records],
        "recent_achievements": [serialize_unlock(item) for item in recent_unlocks],
        "recent_activities": [_activity_list_item(item) for item in recent_sessions],
        "suggested_weekly_target": (weekly.get("suggestion") or {}).get("days_per_week"),
    }), 200
