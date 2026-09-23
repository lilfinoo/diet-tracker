from datetime import datetime
import hashlib
import json

from sqlalchemy import or_

from src.models.user import (
    DelegatedActionAudit,
    DietPlan,
    DietPlanMeal,
    WorkoutDay,
    WorkoutExercise,
    WorkoutPlan,
    ProfessionalReviewRequest,
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


def clone_plan_for_review(plan, owner, professional):
    snapshot = plan_snapshot(plan)
    if isinstance(plan, WorkoutPlan):
        return create_workout_plan(
            owner,
            professional,
            snapshot["questionnaire"],
            {
                "title": snapshot["title"],
                "description": snapshot["description"],
                "days": snapshot["days"],
            },
            status="draft",
            source="manual",
            supersedes_plan_id=plan.id,
        )
    return create_diet_plan(
        owner,
        professional,
        snapshot["questionnaire"],
        snapshot["nutrition_targets"],
        {"title": snapshot["title"], "description": snapshot["description"], "meals": snapshot["meals"]},
        snapshot["profile_snapshot"],
        status="draft",
        source="manual",
        supersedes_plan_id=plan.id,
    )


def professional_review_for_plan(plan):
    if isinstance(plan, WorkoutPlan):
        source_field = ProfessionalReviewRequest.source_workout_plan_id
        proposal_field = ProfessionalReviewRequest.proposal_workout_plan_id
    else:
        source_field = ProfessionalReviewRequest.source_diet_plan_id
        proposal_field = ProfessionalReviewRequest.proposal_diet_plan_id
    reviews = ProfessionalReviewRequest.query.filter(
        ProfessionalReviewRequest.status == "completed",
        or_(source_field == plan.id, proposal_field == plan.id),
    ).order_by(ProfessionalReviewRequest.completed_at.desc()).all()
    fingerprint = snapshot_fingerprint(plan_snapshot(plan))
    for review in reviews:
        approved_source = review.outcome == "approved_as_is" and getattr(review, source_field.key) == plan.id
        applied_proposal = (
            review.outcome == "changes_proposed"
            and review.student_decision == "applied"
            and getattr(review, proposal_field.key) == plan.id
        )
        expected = review.source_fingerprint if approved_source else review.proposal_fingerprint
        if (approved_source or applied_proposal) and expected == fingerprint:
            professional = review.assigned_professional
            return {
                "review_id": review.id,
                "professional": {
                    "id": professional.id,
                    "username": professional.username,
                    "avatar_url": (
                        f"/api/profiles/by-id/{professional.id}/avatar"
                        if professional.profile and professional.profile.avatar_object_key
                        else None
                    ),
                } if professional else None,
                "reviewed_at": review.completed_at.isoformat() if review.completed_at else None,
            }
    if (
        plan.author
        and plan.author_user_id != plan.user_id
        and plan.published_by_user_id == plan.author_user_id
        and plan.professional_verified_fingerprint == fingerprint
    ):
        return {
            "review_id": None,
            "professional": {
                "id": plan.author.id,
                "username": plan.author.username,
                "avatar_url": (
                    f"/api/profiles/by-id/{plan.author.id}/avatar"
                    if plan.author.profile and plan.author.profile.avatar_object_key
                    else None
                ),
            },
            "reviewed_at": plan.published_at.isoformat() if plan.published_at else None,
        }
    return None


def create_workout_plan(
    owner,
    author,
    questionnaire,
    plan_data,
    *,
    status="published",
    source="manual",
    relationship=None,
    roster_relationship=None,
    supersedes_plan_id=None,
):
    plan = WorkoutPlan(
        user_id=owner.id if owner else None,
        professional_student_relationship_id=roster_relationship.id if roster_relationship else None,
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
    if relationship:
        add_audit(author, owner, relationship, "workout_plan.created", "workout_plan", plan.id, {
            "source": source,
            "status": status,
        })
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
    relationship=None,
    roster_relationship=None,
    supersedes_plan_id=None,
):
    plan = DietPlan(
        user_id=owner.id if owner else None,
        professional_student_relationship_id=roster_relationship.id if roster_relationship else None,
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
    if relationship:
        add_audit(author, owner, relationship, "diet_plan.created", "diet_plan", plan.id, {
            "source": source,
            "status": status,
        })
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


def publish_plan(plan, actor, owner, relationship, resource_type):
    plan.status = "published"
    plan.published_at = datetime.utcnow()
    plan.published_by_user_id = actor.id
    plan.professional_verified_fingerprint = snapshot_fingerprint(plan_snapshot(plan))
    if plan.supersedes_plan_id:
        model = WorkoutPlan if resource_type == "workout_plan" else DietPlan
        previous = db.session.get(model, plan.supersedes_plan_id)
        if previous and previous.user_id == owner.id:
            previous.status = "archived"
    add_audit(actor, owner, relationship, f"{resource_type}.published", resource_type, plan.id)
    return plan


def add_audit(actor, subject, relationship, action, resource_type=None, resource_id=None, details=None):
    db.session.add(DelegatedActionAudit(
        actor_user_id=actor.id,
        subject_user_id=subject.id,
        relationship_id=relationship.id if relationship else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=details,
    ))
