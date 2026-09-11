import math

from sqlalchemy.exc import IntegrityError

from src.models.user import DietEntry, DietMealDailyState, DietPlan, UserProfile, db
from src.services.diet_slots import meal_slot_key, plan_day_number


NUTRIENT_FIELDS = ("calories", "protein", "carbs", "fat")
TARGET_FIELDS = {
    "calories": "targetCalories",
    "protein": "targetProtein",
    "carbs": "targetCarbs",
    "fat": "targetFat",
}


class DietDailyError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def active_diet_plan(user_id):
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile or not profile.current_diet_plan_id:
        return None
    return DietPlan.query.filter_by(
        id=profile.current_diet_plan_id,
        user_id=user_id,
        status="published",
    ).first()


def grouped_plan_slots(plan):
    slots = {}
    ordered = sorted(
        plan.meals,
        key=lambda meal: (
            plan_day_number(meal.day_of_week) or 999,
            meal.order if meal.order is not None else 999,
            meal.id or 0,
        ),
    )
    for meal in ordered:
        key = meal.slot_key or meal_slot_key(meal.meal_type, meal.order)
        slots.setdefault(key, []).append(meal)
    return slots


def _valid_targets(plan):
    source = (plan.generation_context or {}).get("nutrition_targets") if plan else None
    targets = {}
    for field, source_key in TARGET_FIELDS.items():
        value = (source or {}).get(source_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
            targets[field] = value
    return targets


def _totals(entries):
    return {
        field: sum(float(getattr(entry, field) or 0) for entry in entries)
        for field in NUTRIENT_FIELDS
    }


def _alternative(meal):
    data = meal.to_dict()
    data["option"] = plan_day_number(meal.day_of_week)
    return data


def daily_diet_view(user_id, local_date):
    plan = active_diet_plan(user_id)
    entries = DietEntry.query.filter_by(user_id=user_id, date=local_date).order_by(DietEntry.created_at, DietEntry.id).all()
    states = {
        state.slot_key: state
        for state in DietMealDailyState.query.filter_by(user_id=user_id, local_date=local_date).all()
    }
    slots = []
    if plan:
        for key, alternatives in grouped_plan_slots(plan).items():
            state = states.get(key)
            selected = next(
                (meal for meal in alternatives if state and meal.id == state.selected_plan_meal_id),
                alternatives[0],
            )
            slots.append({
                "slot_key": key,
                "label": selected.meal_type,
                "alternatives": [_alternative(meal) for meal in alternatives],
                "selected_plan_meal_id": selected.id,
                "result": state.result if state else "pending",
                "planned_snapshot": state.planned_snapshot if state else None,
                "entry": state.linked_entry.to_dict() if state and state.linked_entry else None,
            })
    return {
        "date": local_date.isoformat(),
        "plan": plan.to_dict() if plan else None,
        "slots": slots,
        "manual_entries": [entry.to_dict() for entry in entries if entry.daily_meal_state_id is None],
        "totals": _totals(entries),
        "targets": _valid_targets(plan),
    }


def _plan_slot(user_id, slot_key):
    plan = active_diet_plan(user_id)
    if not plan:
        raise DietDailyError("Nenhum plano alimentar atual foi encontrado.", 409)
    alternatives = grouped_plan_slots(plan).get(slot_key)
    if not alternatives:
        raise DietDailyError("Slot de refeição inválido.", 404)
    return plan, alternatives


def _selected_meal(alternatives, meal_id):
    try:
        meal_id = int(meal_id)
    except (TypeError, ValueError):
        raise DietDailyError("Escolha uma opção válida.") from None
    meal = next((item for item in alternatives if item.id == meal_id), None)
    if not meal:
        raise DietDailyError("A opção não pertence a este slot.")
    return meal


def _locked_state(user_id, local_date, slot_key):
    return DietMealDailyState.query.filter_by(
        user_id=user_id,
        local_date=local_date,
        slot_key=slot_key,
    ).with_for_update().first()


def select_daily_option(user_id, local_date, slot_key, meal_id):
    plan, alternatives = _plan_slot(user_id, slot_key)
    meal = _selected_meal(alternatives, meal_id)
    state = _locked_state(user_id, local_date, slot_key)
    if state and state.result != "pending":
        raise DietDailyError("Esta refeição já possui um resultado. Corrija o registro para trocar a referência.", 409)
    if state is None:
        state = DietMealDailyState(
            user_id=user_id,
            local_date=local_date,
            slot_key=slot_key,
            diet_plan_id=plan.id,
            selected_plan_meal_id=meal.id,
        )
        db.session.add(state)
    else:
        state.diet_plan_id = plan.id
        state.selected_plan_meal_id = meal.id
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise DietDailyError("A seleção foi atualizada em outra solicitação.", 409) from None
    return state


def _snapshot(meal):
    return {
        key: value
        for key, value in meal.to_dict().items()
        if key in {
            "id", "diet_plan_id", "day_of_week", "meal_type", "slot_key", "description",
            "calories", "protein", "carbs", "fat", "notes", "items", "prep_instructions",
            "prep_minutes", "substitutions", "order",
        }
    }


def set_daily_outcome(user_id, local_date, slot_key, result, meal_id=None, entry_data=None):
    if result not in {"consumed_planned", "consumed_different", "skipped"}:
        raise DietDailyError("Resultado alimentar inválido.")
    plan, alternatives = _plan_slot(user_id, slot_key)
    state = _locked_state(user_id, local_date, slot_key)
    selected_id = meal_id or (state.selected_plan_meal_id if state else alternatives[0].id)
    meal = _selected_meal(alternatives, selected_id)
    if state and state.result != "pending":
        if state.result == result and (result != "consumed_planned" or state.selected_plan_meal_id == meal.id):
            return state, False
        raise DietDailyError("Esta refeição já possui um resultado. Corrija o registro existente.", 409)
    try:
        if state is None:
            state = DietMealDailyState(
                user_id=user_id,
                local_date=local_date,
                slot_key=slot_key,
                diet_plan_id=plan.id,
                selected_plan_meal_id=meal.id,
            )
            db.session.add(state)
            db.session.flush()
        else:
            state.diet_plan_id = plan.id
            state.selected_plan_meal_id = meal.id

        if result == "consumed_planned":
            entry = DietEntry(
                user_id=user_id,
                date=local_date,
                meal_type=meal.meal_type,
                description=meal.description,
                calories=meal.calories,
                protein=meal.protein,
                carbs=meal.carbs,
                fat=meal.fat,
                notes=meal.notes,
                daily_meal_state_id=state.id,
                source="planned",
            )
            db.session.add(entry)
        elif result == "consumed_different":
            entry_data = entry_data or {}
            description = str(entry_data.get("description") or "").strip()
            if not description:
                raise DietDailyError("Descreva o que foi consumido.")
            entry = DietEntry(
                user_id=user_id,
                date=local_date,
                meal_type=str(entry_data.get("meal_type") or meal.meal_type).strip(),
                description=description,
                calories=entry_data.get("calories"),
                protein=entry_data.get("protein"),
                carbs=entry_data.get("carbs"),
                fat=entry_data.get("fat"),
                notes=entry_data.get("notes"),
                daily_meal_state_id=state.id,
                source="different",
            )
            db.session.add(entry)
        state.result = result
        state.planned_snapshot = _snapshot(meal)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = _locked_state(user_id, local_date, slot_key)
        if existing and existing.result == result and (
            result == "skipped" or existing.linked_entry is not None
        ):
            return existing, False
        raise DietDailyError("A refeição foi atualizada em outra solicitação.", 409) from None
    return state, True


def reset_daily_outcome(user_id, local_date, slot_key):
    _plan_slot(user_id, slot_key)
    state = _locked_state(user_id, local_date, slot_key)
    if state is None or state.result == "pending":
        return state, False
    if state.linked_entry is not None:
        db.session.delete(state.linked_entry)
    state.result = "pending"
    state.planned_snapshot = None
    db.session.commit()
    return state, True
