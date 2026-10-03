from datetime import datetime
import hashlib
import json

from src.models.user import (
    DietPlan,
    DietPlanMeal,
    WorkoutDay,
    WorkoutExercise,
    WorkoutPlan,
    db,
)


WORKOUT_EXERCISE_FIELDS = {
    "catalog_key", "name", "movement_pattern", "primary_muscle", "equipment", "difficulty",
    "sets", "reps", "weight", "rest_seconds", "effort_guidance", "notes", "order",
}
DIET_MEAL_FIELDS = {
    "day_of_week", "meal_type", "description", "calories", "protein", "carbs", "fat",
    "notes", "items", "prep_instructions", "prep_minutes", "substitutions", "order",
}


def plan_snapshot(plan):
    if isinstance(plan, WorkoutPlan):
        return {
            "type": "workout",
            "title": plan.title,
            "description": plan.description,
            "questionnaire": plan.questionnaire_data or {},
            "days": [{
                "code": day.code,
                "title": day.title,
                "focus": day.focus,
                "order": day.order,
                "exercises": [{key: getattr(exercise, key) for key in WORKOUT_EXERCISE_FIELDS}
                              for exercise in day.exercises],
            } for day in plan.days],
        }
    return {
        "type": "diet",
        "title": plan.title,
        "description": plan.description,
        "questionnaire": (plan.generation_context or {}).get("questionnaire") or {},
        "nutrition_targets": (plan.generation_context or {}).get("nutrition_targets") or {},
        "profile_snapshot": (plan.generation_context or {}).get("profile_snapshot") or {},
        "meals": [
            {key: getattr(meal, key) for key in DIET_MEAL_FIELDS}
            for meal in sorted(plan.meals, key=lambda item: (item.day_of_week, item.order, item.id or 0))
        ],
    }


def snapshot_fingerprint(snapshot):
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def create_workout_plan(
    owner,
    author,
    questionnaire,
    plan_data,
    *,
    status="published",
    source="manual",
    supersedes_plan_id=None,
):
    plan = WorkoutPlan(
        user_id=owner.id if owner else None,
        author_user_id=author.id,
        published_by_user_id=author.id if status == "published" else None,
        published_at=datetime.utcnow() if status == "published" else None,
        supersedes_plan_id=supersedes_plan_id,
        status=status,
        source=source,
        title=plan_data["title"],
        description=plan_data["description"],
        split_type=questionnaire["split_type"],
        days_per_week=questionnaire["days_per_week"],
        goal=questionnaire["goal"],
        experience_level=questionnaire["experience_level"],
        session_duration=questionnaire["session_duration"],
        questionnaire_data=questionnaire,
    )
    db.session.add(plan)
    db.session.flush()
    _replace_workout_days(plan, plan_data["days"])
    return plan


def update_workout_draft(plan, questionnaire, plan_data):
    plan.title = plan_data["title"]
    plan.description = plan_data["description"]
    plan.split_type = questionnaire["split_type"]
    plan.days_per_week = questionnaire["days_per_week"]
    plan.goal = questionnaire["goal"]
    plan.experience_level = questionnaire["experience_level"]
    plan.session_duration = questionnaire["session_duration"]
    plan.questionnaire_data = questionnaire
    _replace_workout_days(plan, plan_data["days"])
    return plan


def _replace_workout_days(plan, days):
    for exercise in list(plan.exercises):
        db.session.delete(exercise)
    for day in list(plan.days):
        db.session.delete(day)
    db.session.flush()
    for day_data in days:
        day = WorkoutDay(
            workout_plan_id=plan.id,
            code=day_data["code"],
            title=day_data["title"],
            focus=day_data["focus"],
            order=day_data["order"],
        )
        db.session.add(day)
        db.session.flush()
        for exercise in day_data["exercises"]:
            db.session.add(WorkoutExercise(
                workout_plan_id=plan.id,
                workout_day_id=day.id,
                **{key: exercise[key] for key in WORKOUT_EXERCISE_FIELDS if key in exercise},
            ))


def create_diet_plan(
    owner,
    author,
    questionnaire,
    nutrition_targets,
    plan_data,
    profile_snapshot,
    *,
    status="published",
    source="manual",
    supersedes_plan_id=None,
):
    plan = DietPlan(
        user_id=owner.id if owner else None,
        author_user_id=author.id,
        published_by_user_id=author.id if status == "published" else None,
        published_at=datetime.utcnow() if status == "published" else None,
        supersedes_plan_id=supersedes_plan_id,
        status=status,
        source=source,
        title=plan_data["title"],
        description=plan_data["description"],
        schema_version=3,
        plan_mode="rotation_3_day",
        goal_code=questionnaire["goal"],
        meals_per_day=questionnaire["meals_per_day"],
        generation_context={
            "questionnaire": questionnaire,
            "profile_snapshot": profile_snapshot,
            "nutrition_targets": nutrition_targets,
        },
    )
    db.session.add(plan)
    db.session.flush()
    _replace_diet_meals(plan, plan_data["meals"])
    return plan


def update_diet_draft(plan, questionnaire, nutrition_targets, plan_data, profile_snapshot):
    plan.title = plan_data["title"]
    plan.description = plan_data["description"]
    plan.goal_code = questionnaire["goal"]
    plan.meals_per_day = questionnaire["meals_per_day"]
    plan.generation_context = {
        "questionnaire": questionnaire,
        "profile_snapshot": profile_snapshot,
        "nutrition_targets": nutrition_targets,
    }
    _replace_diet_meals(plan, plan_data["meals"])
    return plan


def replace_diet_day(plan, day_index, meals):
    day_label = f"Dia {day_index}"
    for meal in list(plan.meals):
        if meal.day_of_week == day_label:
            db.session.delete(meal)
    for order, meal in enumerate(meals, start=1):
        meal_data = dict(meal)
        meal_data["order"] = order
        meal_data["day_of_week"] = day_label
        db.session.add(DietPlanMeal(
            diet_plan_id=plan.id,
            **{key: meal_data[key] for key in DIET_MEAL_FIELDS if key in meal_data},
        ))


def _replace_diet_meals(plan, meals):
    plan.meals.clear()
    db.session.flush()
    for meal in meals:
        db.session.add(DietPlanMeal(
            diet_plan_id=plan.id,
            **{key: meal[key] for key in DIET_MEAL_FIELDS if key in meal},
        ))
