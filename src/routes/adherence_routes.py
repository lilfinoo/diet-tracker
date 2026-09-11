from datetime import date, datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from src.models.user import DietAdherenceDay, DietMealCheckIn, DietPlan, db
from src.routes.common import _local_date_for_timezone, json_body, login_required, page_query
from src.services.workout_progress import user_timezone


adherence_bp = Blueprint("adherence", __name__)
CHECKIN_STATUSES = {"completed", "substituted", "skipped"}


def _local_date(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


@adherence_bp.route("/diet/adherence", methods=["GET"])
@login_required
def adherence_history():
    query = DietAdherenceDay.query.filter_by(user_id=g.user.id).order_by(
        DietAdherenceDay.local_date.desc()
    )
    query, limit, offset = page_query(query, default_limit=30)
    return jsonify({
        "items": [item.to_dict() for item in query.all()],
        "limit": limit,
        "offset": offset,
    }), 200


@adherence_bp.route("/diet_plans/<int:plan_id>/adherence/<date_value>", methods=["GET", "PUT"])
@login_required
def plan_adherence(plan_id, date_value):
    local_date = _local_date(date_value)
    if local_date is None:
        return jsonify({"error": "Data inválida."}), 400
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    if not g.user.profile or g.user.profile.current_diet_plan_id != plan.id:
        return jsonify({"error": "Acompanhe apenas o plano alimentar atual."}), 409
    today = _local_date_for_timezone(user_timezone(g.user.id) or "UTC")
    if local_date > today:
        return jsonify({"error": "Não é possível registrar uma data futura."}), 400

    if request.method == "GET":
        record = DietAdherenceDay.query.filter_by(
            user_id=g.user.id,
            diet_plan_id=plan.id,
            local_date=local_date,
        ).first()
        return jsonify({"adherence": record.to_dict() if record else None}), 200

    data = json_body()
    plan_day = str(data.get("plan_day", "")).strip()
    day_meals = [meal for meal in plan.meals if meal.day_of_week == plan_day]
    if not day_meals:
        return jsonify({"error": "Escolha um dia válido do plano."}), 400
    checkins = data.get("meal_checkins")
    if not isinstance(checkins, list) or len(checkins) > len(day_meals):
        return jsonify({"error": "Marcações de refeições inválidas."}), 400
    allowed_ids = {meal.id for meal in day_meals}
    normalized = {}
    for item in checkins:
        if not isinstance(item, dict):
            return jsonify({"error": "Marcação de refeição inválida."}), 400
        try:
            meal_id = int(item.get("diet_plan_meal_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Refeição inválida."}), 400
        status = str(item.get("status", ""))
        note = str(item.get("note", "")).strip()
        if meal_id not in allowed_ids or status not in CHECKIN_STATUSES or len(note) > 500:
            return jsonify({"error": "Marcação de refeição inválida."}), 400
        normalized[meal_id] = (status, note or None)

    record = DietAdherenceDay.query.filter_by(
        user_id=g.user.id,
        local_date=local_date,
    ).with_for_update().first()
    if record is None:
        record = DietAdherenceDay(
            user_id=g.user.id,
            diet_plan_id=plan.id,
            local_date=local_date,
            plan_day=plan_day,
        )
        db.session.add(record)
        db.session.flush()
    elif record.diet_plan_id != plan.id:
        return jsonify({"error": "Esta data já foi registrada em outro plano alimentar."}), 409
    elif record.plan_day != plan_day and record.meal_checkins:
        return jsonify({"error": "Remova as marcações antes de trocar o dia do plano."}), 409
    record.plan_day = plan_day
    current = {item.diet_plan_meal_id: item for item in record.meal_checkins}
    for meal_id, checkin in current.items():
        if meal_id not in normalized:
            db.session.delete(checkin)
    for meal_id, (status, note) in normalized.items():
        checkin = current.get(meal_id)
        if checkin is None:
            checkin = DietMealCheckIn(adherence_day_id=record.id, diet_plan_meal_id=meal_id)
            db.session.add(checkin)
        checkin.status = status
        checkin.note = note
    finalize = data.get("finalize") is True
    db.session.flush()
    if finalize:
        if set(normalized) != allowed_ids:
            return jsonify({"error": "Marque todas as refeições antes de concluir o dia."}), 409
        record.status = "completed"
        record.completed_at = datetime.utcnow()
    else:
        record.status = "in_progress"
        record.completed_at = None
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "O acompanhamento desta data foi atualizado em outra solicitação."}), 409
    return jsonify({
        "message": "Dia alimentar concluído." if finalize else "Acompanhamento salvo.",
        "adherence": record.to_dict(),
    }), 200
