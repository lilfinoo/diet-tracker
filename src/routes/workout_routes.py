import uuid

from flask import Blueprint, abort, g, jsonify
from sqlalchemy.orm import selectinload

from src.models.user import WorkoutDay, WorkoutExercise, WorkoutPlan, WorkoutSession, UserProfile, db
from src.routes.common import _csrf_protect_request
from src.routes.common import (_apply_workout_plan_schedule, _editable_workout_plan, _get_or_create_profile, _local_date_for_timezone, _plan_catalog, _prescription, _redistribute_workout_plan_data, _set_catalog_exercise, _workout_questionnaire_for_plan, _workout_today_payload, _version_workout_plan_for_edit, json_body, login_required, page_query)
from src.services.plan_management import create_workout_plan
from src.services.workout_plans import catalog_by_key, replacement_options
from src.services.workout_progress import user_timezone


workout_bp = Blueprint("workout", __name__)


@workout_bp.before_request
def protect_workout_mutations():
    return _csrf_protect_request()


@workout_bp.route("/workouts/today", methods=["GET"])
@login_required
def workout_today():
    payload = _workout_today_payload(g.user)
    db.session.commit()
    return jsonify(payload), 200


@workout_bp.route("/workout_plans/<int:plan_id>/current", methods=["PUT"])
@login_required
def set_current_workout_plan(plan_id):
    user = g.user
    data = json_body()
    weekdays = data.get("weekdays") or []
    try:
        weekdays = [int(day) for day in weekdays]
    except (TypeError, ValueError):
        return jsonify({"error": "Selecione os dias da semana."}), 400
    if len(weekdays) != len(set(weekdays)) or any(day < 0 or day > 6 for day in weekdays):
        return jsonify({"error": "Dias da semana inválidos."}), 400

    profile = _get_or_create_profile(user.id)
    timezone_name = profile.timezone or user_timezone(user.id) or "UTC"
    local_date = _local_date_for_timezone(timezone_name)
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id, status="published").options(
        selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises),
        selectinload(WorkoutPlan.exercises),
    ).first_or_404()
    if len(weekdays) != len(plan.days):
        return jsonify({"error": "Escolha um dia para cada etapa do plano."}), 400
    if WorkoutSession.query.filter_by(user_id=user.id, completed_at=None).first():
        return jsonify({"error": "Finalize o treino em andamento antes de trocar o plano principal."}), 409

    was_unconfigured = profile.current_workout_plan_id is None
    _apply_workout_plan_schedule(profile, plan, weekdays, timezone_name, local_date)
    message = "Plano principal definido para hoje." if was_unconfigured else "Agenda atualizada."

    db.session.commit()
    return jsonify({
        "message": message,
        "plan_id": plan.id,
        "current_plan_id": profile.current_workout_plan_id,
        "pending_plan_id": profile.pending_workout_plan_id,
        "effective_from": profile.workout_schedule_effective_from.isoformat() if profile.workout_schedule_effective_from else None,
    }), 200


@workout_bp.route("/workout_plans/<int:plan_id>/current/adapt", methods=["POST"])
@login_required
def adapt_current_workout_plan(plan_id):
    user = g.user
    data = json_body()
    weekdays = data.get("weekdays") or []
    try:
        weekdays = [int(day) for day in weekdays]
    except (TypeError, ValueError):
        return jsonify({"error": "Selecione os dias da semana."}), 400
    if not 1 <= len(weekdays) <= 7:
        return jsonify({"error": "Escolha entre 1 e 7 dias para a nova agenda."}), 400
    if len(weekdays) != len(set(weekdays)) or any(day < 0 or day > 6 for day in weekdays):
        return jsonify({"error": "Dias da semana inválidos."}), 400

    profile = _get_or_create_profile(user.id)
    timezone_name = profile.timezone or user_timezone(user.id) or "UTC"
    local_date = _local_date_for_timezone(timezone_name)
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id, status="published").options(
        selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises),
        selectinload(WorkoutPlan.exercises),
    ).first_or_404()
    if WorkoutSession.query.filter_by(user_id=user.id, completed_at=None).first():
        return jsonify({"error": "Finalize o treino em andamento antes de trocar o plano principal."}), 409

    questionnaire = _workout_questionnaire_for_plan(plan, len(weekdays))
    plan_data = _redistribute_workout_plan_data(plan, len(weekdays))
    adapted_plan = create_workout_plan(
        owner=user,
        author=user,
        questionnaire=questionnaire,
        plan_data=plan_data,
        status="published",
        source="manual",
        supersedes_plan_id=plan.id,
    )
    plan.status = "archived"
    _apply_workout_plan_schedule(profile, adapted_plan, weekdays, timezone_name, local_date)
    db.session.commit()
    return jsonify({
        "message": "Treino adaptado à nova agenda.",
        "plan_id": adapted_plan.id,
        "current_plan_id": profile.current_workout_plan_id,
        "effective_from": profile.workout_schedule_effective_from.isoformat() if profile.workout_schedule_effective_from else None,
        "plan": adapted_plan.to_dict_full(),
    }), 200


@workout_bp.route("/workout_plans", methods=["GET"])
@login_required
def get_workout_plans():
    user = g.user
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    if profile:
        _workout_today_payload(user)
        db.session.commit()
        profile = UserProfile.query.filter_by(user_id=user.id).first()
    current_plan_id = profile.current_workout_plan_id if profile else None
    plans, _, _ = page_query(
        WorkoutPlan.query.filter_by(user_id=user.id, status="published")
        .options(selectinload(WorkoutPlan.days), selectinload(WorkoutPlan.exercises))
        .order_by(WorkoutPlan.created_at.desc()),
    )
    plans = plans.all()
    payload = []
    for plan in plans:
        data = plan.to_dict()
        data["is_current"] = plan.id == current_plan_id
        payload.append(data)
    return jsonify(payload), 200


@workout_bp.route("/workout_plans/<int:plan_id>", methods=["GET"])
@login_required
def get_workout_plan_details(plan_id):
    user = g.user
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id, status="published").options(
        selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises),
        selectinload(WorkoutPlan.exercises),
    ).first_or_404()
    return jsonify(plan.to_dict_full()), 200


@workout_bp.route("/workout_plans/<int:plan_id>/exercises/catalog", methods=["GET"])
@login_required
def workout_plan_exercise_catalog(plan_id):
    plan = _editable_workout_plan(plan_id)
    return jsonify({"items": _plan_catalog(plan)}), 200


@workout_bp.route("/workout_plans/<int:plan_id>/exercises/<int:exercise_id>/replacement_options", methods=["GET"])
@login_required
def permanent_replacement_options(plan_id, exercise_id):
    plan = _editable_workout_plan(plan_id)
    exercise = WorkoutExercise.query.filter_by(id=exercise_id, workout_plan_id=plan.id).first_or_404()
    questionnaire = plan.questionnaire_data or {}
    options = replacement_options(
        exercise,
        unavailable_equipment=[],
        available_equipment=questionnaire.get("equipment") or ["full_gym"],
        limit=8,
    )
    return jsonify({"options": options}), 200


@workout_bp.route("/workout_plans/<int:plan_id>/exercises/<int:exercise_id>", methods=["PATCH"])
@login_required
def replace_plan_exercise(plan_id, exercise_id):
    plan = _editable_workout_plan(plan_id)
    exercise = WorkoutExercise.query.filter_by(id=exercise_id, workout_plan_id=plan.id).first_or_404()
    data = json_body()
    catalog_item = catalog_by_key().get(str(data.get("catalog_key", "")))
    source = catalog_by_key().get(exercise.catalog_key)
    allowed_keys = {item["key"] for item in _plan_catalog(plan)}
    if not catalog_item or catalog_item["key"] not in allowed_keys:
        abort(400, description="Escolha um exercício compatível com o plano.")
    if source and catalog_item["substitution_group"] != source["substitution_group"]:
        abort(400, description="A substituição deve manter o mesmo padrão de movimento.")
    plan, _, exercise_map = _version_workout_plan_for_edit(plan)
    exercise = exercise_map.get(exercise.id, exercise)
    _set_catalog_exercise(exercise, catalog_item)
    for field, value in _prescription(data, exercise).items():
        setattr(exercise, field, value)
    db.session.commit()
    return jsonify({"message": "Exercício substituído no plano.", "plan": plan.to_dict_full()}), 200


@workout_bp.route("/workout_plans/<int:plan_id>/days/<int:day_id>/exercises", methods=["POST"])
@login_required
def add_plan_exercise(plan_id, day_id):
    plan = _editable_workout_plan(plan_id)
    day = WorkoutDay.query.filter_by(id=day_id, workout_plan_id=plan.id).first_or_404()
    if len(day.exercises) >= 12:
        abort(400, description="Este treino já atingiu o limite de 12 exercícios.")
    data = json_body()
    catalog_item = catalog_by_key().get(str(data.get("catalog_key", "")))
    allowed_keys = {item["key"] for item in _plan_catalog(plan)}
    custom_name = str(data.get("name", "")).strip()
    if catalog_item and catalog_item["key"] not in allowed_keys:
        abort(400, description="Escolha um exercício compatível com o plano.")
    if not catalog_item and not 2 <= len(custom_name) <= 100:
        abort(400, description="Digite um nome de exercício entre 2 e 100 caracteres.")
    if catalog_item and any(item.catalog_key == catalog_item["key"] for item in day.exercises):
        abort(409, description="Este exercício já faz parte do treino.")
    if not catalog_item and any(item.name.casefold() == custom_name.casefold() for item in day.exercises):
        abort(409, description="Este exercício já faz parte do treino.")
    plan, day_map, _ = _version_workout_plan_for_edit(plan)
    day = day_map.get(day.id, day)
    exercise = WorkoutExercise(
        workout_plan_id=plan.id,
        workout_day_id=day.id,
        name=catalog_item["name"] if catalog_item else custom_name,
        catalog_key=catalog_item["key"] if catalog_item else f"custom:{uuid.uuid4()}",
        movement_pattern=catalog_item["movement_pattern"] if catalog_item else "custom",
        primary_muscle=catalog_item["primary_muscle"] if catalog_item else None,
        equipment=catalog_item["equipment"] if catalog_item else None,
        difficulty=catalog_item["difficulty"] if catalog_item else None,
        order=max((item.order or 0 for item in day.exercises), default=0) + 1,
        **_prescription(data),
    )
    db.session.add(exercise)
    db.session.commit()
    return jsonify({"message": "Exercício adicionado ao plano.", "plan": plan.to_dict_full()}), 201


@workout_bp.route("/workout_plans/<int:plan_id>/exercises/<int:exercise_id>", methods=["DELETE"])
@login_required
def delete_plan_exercise(plan_id, exercise_id):
    plan = _editable_workout_plan(plan_id)
    exercise = WorkoutExercise.query.filter_by(id=exercise_id, workout_plan_id=plan.id).first_or_404()
    day = exercise.day
    if day and len(day.exercises) <= 1:
        abort(400, description="O treino precisa manter ao menos um exercício.")
    plan, _, exercise_map = _version_workout_plan_for_edit(plan)
    exercise = exercise_map.get(exercise.id, exercise)
    day = exercise.day
    db.session.delete(exercise)
    db.session.flush()
    if day:
        remaining = [item for item in day.exercises if item is not exercise]
        for order, item in enumerate(remaining, start=1):
            item.order = order
    db.session.commit()
    return jsonify({"message": "Exercício removido do plano.", "plan": plan.to_dict_full()}), 200


@workout_bp.route("/workout_plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_workout_plan(plan_id):
    user = g.user
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id, status="published").with_for_update().first_or_404()
    if WorkoutSession.query.filter_by(workout_plan_id=plan.id, user_id=user.id, completed_at=None).first():
        return jsonify({"error": "Finalize o treino em andamento antes de excluir este plano."}), 409
    if WorkoutSession.query.filter_by(workout_plan_id=plan.id, user_id=user.id).first():
        plan.status = "archived"
        db.session.commit()
        return jsonify({"message": "Plano removido. O histórico de atividades foi preservado."}), 200
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plano de treino excluído com sucesso"}), 200
