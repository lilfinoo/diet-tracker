from datetime import timedelta

from flask import Blueprint, g, jsonify, request

from src.models.user import AchievementUnlock, ExerciseGoal, PersonalRecordEvent, UserProfile, WorkoutSession, WorkoutSessionExerciseCompletion, db
from src.routes.common import _csrf_protect_request
from src.routes.common import _activity_list_item, _ensure_user_workout_history, json_body, login_required
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
    suggested_days_per_week,
    validate_timezone,
    week_start_for,
    weekly_progress,
)
from decimal import Decimal, InvalidOperation


progress_bp = Blueprint("progress", __name__)


@progress_bp.before_request
def protect_progress_mutations():
    return _csrf_protect_request()


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
    has_goal = ExerciseGoal.query.filter_by(user_id=g.user.id).first() is not None
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
    records = exercise_progress(g.user.id, exercise_key)
    if not records:
        return jsonify({"error": "Histórico do exercício não encontrado."}), 404
    activities = (
        WorkoutSession.query.join(WorkoutSessionExerciseCompletion)
        .filter(
            WorkoutSession.user_id == g.user.id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSessionExerciseCompletion.exercise_catalog_key == exercise_key,
        )
        .order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc())
        .limit(20)
        .all()
    )
    return jsonify({
        "exercise_key": exercise_key,
        "exercise_name": records[-1]["exercise_name"],
        "max_load_kg": float(current_max_load(g.user.id, exercise_key) or 0),
        "records": records,
        "recent_activities": [_activity_list_item(item) for item in activities],
    }), 200


@progress_bp.route("/progress/achievements", methods=["GET"])
@login_required
def get_achievements():
    _ensure_user_workout_history(g.user.id)
    return jsonify({
        "items": achievement_catalog(g.user.id),
        "badges": serialize_badges(g.user.badges),
        "selected": serialize_profile_highlights(g.user.profile_highlights),
        "highlight_limit": 3,
    }), 200


@progress_bp.route("/progress/overview", methods=["GET"])
@login_required
def progress_overview():
    _ensure_user_workout_history(g.user.id)
    recent_sessions = (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == g.user.id,
            WorkoutSession.completed_at.isnot(None),
        )
        .order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc())
        .limit(5)
        .all()
    )
    recent_records = PersonalRecordEvent.query.filter(
        PersonalRecordEvent.user_id == g.user.id,
        PersonalRecordEvent.is_highlighted.is_(True),
        PersonalRecordEvent.is_initial.is_(False),
    ).order_by(PersonalRecordEvent.achieved_at.desc(), PersonalRecordEvent.id.desc()).limit(5).all()
    recent_unlocks = AchievementUnlock.query.filter_by(user_id=g.user.id).order_by(
        AchievementUnlock.unlocked_at.desc(), AchievementUnlock.id.desc()
    ).limit(5).all()
    return jsonify({
        "weekly": weekly_progress(g.user.id),
        "exercise_goal": serialize_exercise_goal(current_exercise_goal(g.user.id)),
        "recent_personal_records": [serialize_personal_record(item) for item in recent_records],
        "recent_achievements": [serialize_unlock(item) for item in recent_unlocks],
        "recent_activities": [_activity_list_item(item) for item in recent_sessions],
        "suggested_weekly_target": suggested_days_per_week(g.user.id),
    }), 200
