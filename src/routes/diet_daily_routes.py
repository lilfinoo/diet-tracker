import re
from datetime import datetime

from flask import Blueprint, g, jsonify

from src.models.user import db
from src.routes.common import _require_lengths, coerce_numbers, json_body, login_required
from src.services.diet_daily import (
    DietDailyError,
    daily_diet_view,
    reset_daily_outcome,
    select_daily_option,
    set_daily_outcome,
)


diet_daily_bp = Blueprint("diet_daily", __name__)


def _date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise DietDailyError("Formato de data inválido. Use YYYY-MM-DD.") from None


def _slot(value):
    if not re.fullmatch(r"[a-z0-9_]{1,64}", value or ""):
        raise DietDailyError("Slot de refeição inválido.")
    return value


def _error_response(error):
    db.session.rollback()
    return jsonify({"error": str(error)}), error.status_code


@diet_daily_bp.route("/diet/days/<date_value>", methods=["GET"])
@login_required
def get_daily_diet(date_value):
    try:
        local_date = _date(date_value)
        return jsonify(daily_diet_view(g.user.id, local_date)), 200
    except DietDailyError as error:
        return _error_response(error)


@diet_daily_bp.route("/diet/days/<date_value>/slots/<slot_key>/selection", methods=["PUT"])
@login_required
def choose_daily_diet_option(date_value, slot_key):
    try:
        state = select_daily_option(
            g.user.id,
            _date(date_value),
            _slot(slot_key),
            json_body().get("diet_plan_meal_id"),
        )
        return jsonify({"state": state.to_dict()}), 200
    except DietDailyError as error:
        return _error_response(error)


@diet_daily_bp.route("/diet/days/<date_value>/slots/<slot_key>/outcome", methods=["PUT"])
@login_required
def update_daily_diet_outcome(date_value, slot_key):
    try:
        data = json_body()
        result = str(data.get("result") or "")
        entry_data = data.get("entry")
        if result == "consumed_different":
            if not isinstance(entry_data, dict):
                raise DietDailyError("Informe o consumo realizado.")
            entry_data = coerce_numbers(entry_data, ("calories", "protein", "carbs", "fat"))
            _require_lengths(entry_data, {
                "meal_type": (50, "Tipo de refeição"),
                "description": (2000, "Descrição"),
                "notes": (2000, "Observações"),
            })
            for field in ("calories", "protein", "carbs", "fat"):
                value = entry_data.get(field)
                maximum = 20_000 if field == "calories" else 5_000
                if value is not None and not 0 <= value <= maximum:
                    raise DietDailyError("Valores nutricionais devem ser finitos e não negativos.")
        state, created = set_daily_outcome(
            g.user.id,
            _date(date_value),
            _slot(slot_key),
            result,
            meal_id=data.get("diet_plan_meal_id"),
            entry_data=entry_data,
        )
        return jsonify({"state": state.to_dict()}), 201 if created else 200
    except DietDailyError as error:
        return _error_response(error)


@diet_daily_bp.route("/diet/days/<date_value>/slots/<slot_key>/outcome", methods=["DELETE"])
@login_required
def clear_daily_diet_outcome(date_value, slot_key):
    try:
        state, changed = reset_daily_outcome(g.user.id, _date(date_value), _slot(slot_key))
        return jsonify({"state": state.to_dict() if state else None}), 200 if changed else 204
    except DietDailyError as error:
        return _error_response(error)
