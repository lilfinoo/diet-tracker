from datetime import datetime

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from src.models.user import (
    AchievementUnlock,
    ExerciseGoal,
    PersonalRecordEvent,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
    WorkoutSessionExerciseCompletion,
    WorkoutSessionExerciseOverride,
    WorkoutSetPerformance,
    db,
)
from src.routes.common import _activity_list_item, _csrf_protect_request, _ensure_user_workout_history, _owned_active_session, _performed_sets_payload, _session_exercise, _workout_session_summary, json_body, login_required
from src.services.ai import AIQuotaExceededError, AIServiceError, classify_exercise_catalog_key
from src.services.achievements import evaluate_achievements, serialize_unlock
from src.services.personal_records import (
    ensure_personal_record_history,
    process_session_personal_records,
)
from src.services.workout_plans import catalog_by_key, replacement_options, resolve_catalog_exercise
from src.services.workout_progress import (
    complete_exercise_goal,
    confirmed_user_timezone,
    serialize_exercise_goal,
    snapshot_session_week,
    weekly_progress,
)


session_bp = Blueprint("session", __name__)


@session_bp.before_request
def protect_session_mutations():
    return _csrf_protect_request()


@session_bp.route("/workout_sessions/active", methods=["GET"])
@login_required
def get_user_active_workout_session():
    session_record = WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).first()
    if not session_record:
        return jsonify({"session": None}), 200
    return jsonify({
        "session": session_record.to_dict(),
        "plan": {"id": session_record.plan.id, "title": session_record.plan.title},
        "day": {"id": session_record.day.id, "title": session_record.day.title},
    }), 200


@session_bp.route("/workout_plans/<int:plan_id>/days/<int:day_id>/sessions/active", methods=["GET"])
@login_required
def get_active_workout_session(plan_id, day_id):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first()
    if not plan or not WorkoutDay.query.filter_by(id=day_id, workout_plan_id=plan.id).first():
        return jsonify({"error": "Treino não encontrado."}), 404
    session_record = WorkoutSession.query.filter_by(
        user_id=g.user.id,
        workout_plan_id=plan.id,
        workout_day_id=day_id,
        completed_at=None,
    ).first()
    return jsonify({"session": session_record.to_dict() if session_record else None}), 200


@session_bp.route("/workout_plans/<int:plan_id>/days/<int:day_id>/sessions", methods=["POST"])
@login_required
def start_workout_session(plan_id, day_id):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").with_for_update().first()
    day = WorkoutDay.query.filter_by(id=day_id, workout_plan_id=plan.id if plan else None).first()
    if not plan or not day:
        return jsonify({"error": "Treino não encontrado."}), 404
    if not day.exercises:
        return jsonify({"error": "Este treino não possui exercícios para iniciar."}), 400
    active = WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).first()
    if active:
        if active.workout_plan_id == plan.id and active.workout_day_id == day.id:
            return jsonify({"session": active.to_dict()}), 200
        return jsonify({
            "error": "Finalize o treino em andamento antes de iniciar outro.",
            "session": active.to_dict(),
        }), 409
    session_record = WorkoutSession(
        user_id=g.user.id,
        workout_plan_id=plan.id,
        workout_day_id=day.id,
    )
    db.session.add(session_record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        active = WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).first()
        if active:
            if active.workout_plan_id == plan.id and active.workout_day_id == day.id:
                return jsonify({"session": active.to_dict()}), 200
            return jsonify({
                "error": "Outro treino foi iniciado ao mesmo tempo. Abra o treino em andamento.",
                "session": active.to_dict(),
            }), 409
        raise
    return jsonify({"session": session_record.to_dict()}), 201


@session_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/replacement_options", methods=["POST"])
@login_required
def get_exercise_replacement_options(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    data = json_body()
    unavailable = data.get("unavailable_equipment", [])
    available = data.get("available_equipment") or (session_record.plan.questionnaire_data or {}).get("equipment", [])
    if not isinstance(unavailable, list) or len(unavailable) > 10:
        return jsonify({"error": "Equipamentos indisponíveis inválidos."}), 400
    if not isinstance(available, list) or len(available) > 12:
        return jsonify({"error": "Equipamentos disponíveis inválidos."}), 400

    catalog_item = resolve_catalog_exercise(exercise.catalog_key, exercise.name)
    if not catalog_item and exercise.catalog_key != "__unresolved__":
        try:
            catalog_key = classify_exercise_catalog_key(exercise.name)
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceError:
            return jsonify({"error": "Não foi possível classificar este exercício agora."}), 503
        catalog_item = catalog_by_key().get(catalog_key)
        if catalog_item:
            exercise.catalog_key = catalog_item["key"]
            exercise.movement_pattern = catalog_item["movement_pattern"]
            exercise.primary_muscle = catalog_item["primary_muscle"]
            exercise.equipment = catalog_item["equipment"]
            exercise.difficulty = catalog_item["difficulty"]
        else:
            exercise.catalog_key = "__unresolved__"
        db.session.commit()
    options = replacement_options(exercise, unavailable, available)
    return jsonify({
        "exercise_id": exercise.id,
        "options": options,
        "source": "catalog",
        "message": None if options else "Não encontramos uma alternativa segura com os equipamentos informados.",
    }), 200


@session_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/replace", methods=["POST"])
@login_required
def replace_exercise_for_session(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    data = json_body()
    catalog_key = str(data.get("catalog_key", "")).strip()
    unavailable = data.get("unavailable_equipment", [])
    available = data.get("available_equipment") or (session_record.plan.questionnaire_data or {}).get("equipment", [])
    option = next((item for item in replacement_options(exercise, unavailable, available) if item["catalog_key"] == catalog_key), None)
    if not option:
        return jsonify({"error": "Essa substituição não é mais válida."}), 409
    override = WorkoutSessionExerciseOverride.query.filter_by(
        workout_session_id=session_record.id,
        workout_exercise_id=exercise.id,
    ).first()
    if not override:
        override = WorkoutSessionExerciseOverride(
            workout_session_id=session_record.id,
            workout_exercise_id=exercise.id,
            catalog_key=option["catalog_key"],
            name=option["name"],
        )
        db.session.add(override)
    for field in (
        "catalog_key", "name", "movement_pattern", "primary_muscle", "equipment", "difficulty",
        "sets", "reps", "weight", "rest_seconds", "effort_guidance", "notes",
    ):
        setattr(override, field, option.get(field))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        override = WorkoutSessionExerciseOverride.query.filter_by(
            workout_session_id=session_record.id,
            workout_exercise_id=exercise.id,
        ).one()
    return jsonify({"message": "Exercício substituído somente neste treino.", "override": override.to_dict()}), 200


@session_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/replace", methods=["DELETE"])
@login_required
def restore_session_exercise(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    override = WorkoutSessionExerciseOverride.query.filter_by(
        workout_session_id=session_record.id,
        workout_exercise_id=exercise.id,
    ).first()
    if override:
        db.session.delete(override)
        db.session.commit()
    return jsonify({"message": "Exercício original restaurado."}), 200


@session_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/complete", methods=["POST"])
@login_required
def complete_session_exercise(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    performed_sets = _performed_sets_payload(request.get_json(silent=True))
    completion = WorkoutSessionExerciseCompletion.query.filter_by(
        workout_session_id=session_record.id,
        workout_exercise_id=exercise.id,
    ).first()
    if not completion:
        override = WorkoutSessionExerciseOverride.query.filter_by(
            workout_session_id=session_record.id,
            workout_exercise_id=exercise.id,
        ).first()
        completion = WorkoutSessionExerciseCompletion(
            workout_session_id=session_record.id,
            workout_exercise_id=exercise.id,
            exercise_name=override.name if override else exercise.name,
            exercise_catalog_key=override.catalog_key if override else exercise.catalog_key,
        )
        db.session.add(completion)
        for performed_set in performed_sets:
            completion.performed_sets.append(WorkoutSetPerformance(**performed_set))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            completion = WorkoutSessionExerciseCompletion.query.filter_by(
                workout_session_id=session_record.id,
                workout_exercise_id=exercise.id,
            ).one()
    return jsonify({"message": "Exercício concluído.", "session": session_record.to_dict()}), 200


@session_bp.route("/workout_sessions/<int:session_id>/finish", methods=["POST"])
@login_required
def finish_workout_session(session_id):
    session_record = WorkoutSession.query.filter_by(
        id=session_id,
        user_id=g.user.id,
    ).with_for_update().first()
    if not session_record:
        return jsonify({"error": "Sessão de treino não encontrada."}), 404
    WorkoutPlan.query.filter_by(id=session_record.workout_plan_id).with_for_update().first()
    new_unlocks = []
    reached_goal = None
    if session_record.completed_at is None:
        ensure_personal_record_history(g.user.id, exclude_session_id=session_record.id)
        evaluate_achievements(g.user.id, backfilled=True)
        session_record.completed_at = datetime.utcnow()
        timezone_name = confirmed_user_timezone(g.user.id)
        if timezone_name:
            snapshot_session_week(session_record, timezone=timezone_name)
        process_session_personal_records(session_record)
        reached_goal = complete_exercise_goal(session_record)
        db.session.flush()
        new_unlocks = evaluate_achievements(g.user.id, related_session=session_record)
    else:
        ensure_personal_record_history(g.user.id)
        timezone_name = confirmed_user_timezone(g.user.id)
        if timezone_name:
            snapshot_session_week(session_record, timezone=timezone_name)
        evaluate_achievements(g.user.id, backfilled=True)
    progress = weekly_progress(g.user.id)
    db.session.commit()
    return jsonify({
        "message": "Treino finalizado.",
        "session": session_record.to_dict(),
        "summary": _workout_session_summary(session_record),
        "weekly_progress": progress,
        "exercise_goals_reached": [serialize_exercise_goal(reached_goal)] if reached_goal else [],
        "achievements_unlocked": [serialize_unlock(item) for item in new_unlocks],
    }), 200


@session_bp.route("/activities", methods=["GET"])
@login_required
def list_activities():
    _ensure_user_workout_history(g.user.id)
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 50)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        abort(400, description="Paginação inválida")
    sessions = (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == g.user.id,
            WorkoutSession.completed_at.isnot(None),
        )
        .options(
            joinedload(WorkoutSession.plan),
            joinedload(WorkoutSession.day),
            selectinload(WorkoutSession.overrides),
            selectinload(WorkoutSession.completions)
            .joinedload(WorkoutSessionExerciseCompletion.exercise),
            selectinload(WorkoutSession.completions)
            .selectinload(WorkoutSessionExerciseCompletion.performed_sets),
        )
        .order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    return jsonify({
        "items": [_activity_list_item(item) for item in sessions[:limit]],
        "limit": limit,
        "offset": offset,
        "has_more": len(sessions) > limit,
    }), 200


@session_bp.route("/activities/<int:activity_id>", methods=["GET"])
@login_required
def get_activity(activity_id):
    _ensure_user_workout_history(g.user.id)
    session_record = (
        WorkoutSession.query.filter(
            WorkoutSession.id == activity_id,
            WorkoutSession.user_id == g.user.id,
            WorkoutSession.completed_at.isnot(None),
        )
        .options(
            joinedload(WorkoutSession.plan),
            joinedload(WorkoutSession.day),
            selectinload(WorkoutSession.overrides),
            selectinload(WorkoutSession.completions)
            .joinedload(WorkoutSessionExerciseCompletion.exercise),
            selectinload(WorkoutSession.completions)
            .selectinload(WorkoutSessionExerciseCompletion.performed_sets),
        )
        .first_or_404()
    )
    activity_unlocks = AchievementUnlock.query.filter_by(
        user_id=g.user.id,
        workout_session_id=session_record.id,
    ).order_by(AchievementUnlock.id).all()
    return jsonify({
        "activity": _workout_session_summary(session_record),
        "achievements": [serialize_unlock(item) for item in activity_unlocks],
    }), 200


@session_bp.route("/activities/<int:activity_id>", methods=["DELETE"])
@login_required
def delete_activity(activity_id):
    session_record = WorkoutSession.query.filter(
        WorkoutSession.id == activity_id,
        WorkoutSession.user_id == g.user.id,
        WorkoutSession.completed_at.isnot(None),
    ).with_for_update().first()
    if not session_record:
        return jsonify({"error": "Atividade não encontrada."}), 404
    completion_ids = db.session.query(WorkoutSessionExerciseCompletion.id).filter(
        WorkoutSessionExerciseCompletion.workout_session_id == session_record.id,
    )
    WorkoutSetPerformance.query.filter(WorkoutSetPerformance.completion_id.in_(completion_ids)).delete(synchronize_session=False)
    WorkoutSessionExerciseCompletion.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    WorkoutSessionExerciseOverride.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    PersonalRecordEvent.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    AchievementUnlock.query.filter_by(workout_session_id=session_record.id).update({"workout_session_id": None}, synchronize_session=False)
    ExerciseGoal.query.filter_by(achieved_session_id=session_record.id).update({"achieved_session_id": None}, synchronize_session=False)
    db.session.delete(session_record)
    db.session.commit()
    return jsonify({"message": "Atividade excluída com sucesso."}), 200


@session_bp.route("/workout_sessions/active", methods=["DELETE"])
@login_required
def cancel_active_workout_session():
    session_record = WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).with_for_update().first()
    if not session_record:
        return jsonify({"error": "Nenhum treino em andamento foi encontrado."}), 404
    completion_ids = db.session.query(WorkoutSessionExerciseCompletion.id).filter(
        WorkoutSessionExerciseCompletion.workout_session_id == session_record.id,
    )
    WorkoutSetPerformance.query.filter(WorkoutSetPerformance.completion_id.in_(completion_ids)).delete(synchronize_session=False)
    WorkoutSessionExerciseCompletion.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    WorkoutSessionExerciseOverride.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    PersonalRecordEvent.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    AchievementUnlock.query.filter_by(workout_session_id=session_record.id).update({"workout_session_id": None}, synchronize_session=False)
    ExerciseGoal.query.filter_by(achieved_session_id=session_record.id).update({"achieved_session_id": None}, synchronize_session=False)
    db.session.delete(session_record)
    db.session.commit()
    return jsonify({"message": "Treino atual cancelado."}), 200


@session_bp.route("/workout_sessions/<int:session_id>", methods=["DELETE"])
@login_required
def cancel_workout_session(session_id):
    session_record = WorkoutSession.query.filter_by(
        id=session_id,
        user_id=g.user.id,
        completed_at=None,
    ).with_for_update().first()
    if not session_record:
        return jsonify({"error": "Nenhum treino em andamento foi encontrado."}), 404
    completion_ids = db.session.query(WorkoutSessionExerciseCompletion.id).filter(
        WorkoutSessionExerciseCompletion.workout_session_id == session_record.id,
    )
    WorkoutSetPerformance.query.filter(WorkoutSetPerformance.completion_id.in_(completion_ids)).delete(synchronize_session=False)
    WorkoutSessionExerciseCompletion.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    WorkoutSessionExerciseOverride.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    PersonalRecordEvent.query.filter_by(workout_session_id=session_record.id).delete(synchronize_session=False)
    AchievementUnlock.query.filter_by(workout_session_id=session_record.id).update({"workout_session_id": None}, synchronize_session=False)
    ExerciseGoal.query.filter_by(achieved_session_id=session_record.id).update({"achieved_session_id": None}, synchronize_session=False)
    db.session.delete(session_record)
    db.session.commit()
    return jsonify({"message": "Treino atual cancelado."}), 200
