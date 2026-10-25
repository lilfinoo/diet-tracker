from copy import deepcopy

import pytest

from src.services.workout_plans import (
    PlanValidationError, build_workout_contract, catalog_by_key,
    validate_workout_exercise_selection, validate_workout_questionnaire,
)


def questionnaire(duration, days=4, experience="intermediate"):
    return validate_workout_questionnaire({
        "goal": "hypertrophy", "experience_level": experience,
        "days_per_week": days, "split_type": "upper_lower",
        "session_duration": duration, "equipment": ["full_gym"],
    })


@pytest.mark.parametrize("duration", [20, 30, 45, 60, 75, 90])
@pytest.mark.parametrize("days", [2, 3, 4, 5, 6])
@pytest.mark.parametrize("experience", ["beginner", "intermediate", "advanced"])
def test_upper_lower_reserves_direct_arm_work_within_duration(duration, days, experience):
    contract = build_workout_contract(questionnaire(duration, days, experience))
    uppers = [day for day in contract["effective"]["days"] if day["code"].startswith("UPPER")]
    weekly_groups = set()
    for day in uppers:
        groups = {group for slot in day["slots"] for group in slot["allowed_groups"]}
        weekly_groups.update(groups)
        assert "horizontal_push" in groups
        assert "horizontal_pull" in groups
        assert len(day["slots"]) <= (5 if duration <= 30 else 7 if duration <= 60 else 8)
        if duration >= 45:
            assert {"biceps", "triceps", "lateral_raise", "vertical_pull"} <= groups
    assert {"biceps", "triceps"} <= weekly_groups
    assert contract["quality"] == "ideal"
def generated_workout(contract):
    days = []
    for spec in contract["effective"]["days"]:
        selected = set()
        exercises = []
        for slot in spec["slots"]:
            key = next(key for key in slot["allowed_catalog_keys"] if key not in selected)
            selected.add(key)
            exercises.append({
                "slot_id": slot["slot_id"], "catalog_key": key,
                "sets": 3, "reps": "8-12", "rest_seconds": 90,
            })
        days.append({"exercises": exercises})
    return {"type": "workout_plan", "days": days}


@pytest.mark.parametrize("arm_group", ["biceps", "triceps"])
def test_ai_selection_rejects_chest_exercise_in_arm_slot(arm_group):
    q = questionnaire(60)
    contract = build_workout_contract(q)
    catalog = catalog_by_key()
    valid = generated_workout(contract)
    validate_workout_exercise_selection(valid, q, contract)
    invalid = deepcopy(valid)
    arm = next(
        exercise for exercise in invalid["days"][0]["exercises"]
        if catalog[exercise["catalog_key"]]["substitution_group"] == arm_group
    )
    arm["catalog_key"] = "supino_reto_barra"
    with pytest.raises(PlanValidationError):
        validate_workout_exercise_selection(invalid, q, contract)


def test_upper_lower_api_saves_direct_arm_work(app, client, monkeypatch):
    from src.models.user import User, UserProfile, db
    from tests.helpers import registration_payload

    client.post("/api/register", json=registration_payload("upper-owner"))
    with app.app_context():
        user = User.query.one()
        user.is_premium = True
        db.session.add(UserProfile(user_id=user.id, age=30, weight=75, height=175))
        db.session.commit()

    q = questionnaire(60)
    contract = build_workout_contract(q)
    monkeypatch.setattr("src.routes.plan_routes.enqueue_ai_request", lambda *args: None)
    monkeypatch.setattr("src.routes.plan_routes.generate_workout_plan", lambda *args: generated_workout(contract))
    response = client.post("/api/workout_plans/generate", json=q)
    assert response.status_code == 201
    catalog = catalog_by_key()
    for day in response.json["plan"]["days"]:
        if day["code"].startswith("UPPER"):
            groups = {catalog[exercise["catalog_key"]]["substitution_group"] for exercise in day["exercises"]}
            assert {"biceps", "triceps"} <= groups
