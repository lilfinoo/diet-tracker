import pytest

from src.models.user import (
    DietPlan,
    User,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
    WorkoutSessionExerciseCompletion,
    db,
)
from src.services.workout_plans import PlanValidationError, normalize_workout_output


def register_premium(app, client):
    client.post("/api/register", json={"username": "guided", "password": "strong-password"})
    with app.app_context():
        user = User.query.filter_by(username="guided").one()
        user.is_premium = True
        db.session.commit()


def workout_questionnaire(**overrides):
    data = {
        "goal": "hypertrophy",
        "experience_level": "beginner",
        "days_per_week": 2,
        "split_type": "full_body",
        "session_duration": 45,
        "equipment": ["full_gym"],
        "limitations": "",
        "priorities": "",
        "avoid_exercises": "",
    }
    data.update(overrides)
    return data


def generated_workout():
    day_keys = [
        ["leg_press_45", "supino_maquina", "remada_maquina", "prancha_frontal"],
        ["agachamento_goblet", "supino_reto_halteres", "remada_unilateral_halter", "bird_dog"],
    ]
    return {
        "type": "workout_plan",
        "title": "Full Body para iniciantes",
        "description": "Dois treinos equilibrados.",
        "days": [
            {
                "focus": "Corpo inteiro",
                "exercises": [
                    {
                        "catalog_key": key,
                        "sets": 3,
                        "reps": "8-12",
                        "weight": "Carga moderada",
                        "rest_seconds": 60,
                        "effort_guidance": "2 repetições em reserva",
                        "notes": "Execução controlada",
                    }
                    for key in keys
                ],
            }
            for keys in day_keys
        ],
    }


def diet_questionnaire():
    return {
        "goal": "general_health",
        "meals_per_day": 3,
        "diet_pattern": "omnivore",
        "allergies": [],
        "intolerances": [],
        "disliked_foods": [],
        "preferred_foods": ["arroz", "feijão"],
        "available_ingredients": ["arroz", "frango", "banana"],
        "budget": "economical",
        "prep_minutes": 30,
        "notes": "",
    }


def generated_diet():
    return {
        "type": "diet_plan",
        "title": "Rotação alimentar simples",
        "description": "Três dias econômicos.",
        "days": [
            {
                "meals": [
                    {
                        "meal_type": meal_type,
                        "items": ["1 porção de arroz", "1 porção de feijão"],
                        "prep": "Sirva os alimentos preparados.",
                        "prep_minutes": 10,
                        "calories": 400,
                        "protein": 20,
                        "carbs": 60,
                        "fat": 8,
                        "notes": "Ajuste a porção à fome.",
                        "substitutions": [{"replace": "arroz", "alternatives": ["batata"]}],
                    }
                    for meal_type in ("Café da manhã", "Almoço", "Jantar")
                ],
            }
            for _ in range(3)
        ],
    }


def prescribed_exercises(*keys):
    return [
        {
            "catalog_key": key,
            "sets": 3,
            "reps": "8-12",
            "weight": "Carga moderada",
            "rest_seconds": 60,
            "effort_guidance": "2 repetições em reserva",
            "notes": "Execução controlada",
        }
        for key in keys
    ]


def test_workout_validation_rejects_equivalent_chest_press_variations():
    generated = generated_workout()
    generated["days"][0]["exercises"] = prescribed_exercises(
        "leg_press_45",
        "supino_reto_halteres",
        "supino_maquina",
        "flexao_de_bracos",
        "remada_maquina",
    )

    with pytest.raises(PlanValidationError) as error:
        normalize_workout_output(generated, workout_questionnaire())

    assert "mesma variação biomecânica" in " ".join(error.value.errors.values())


def test_workout_validation_accepts_complementary_chest_angles():
    generated = generated_workout()
    generated["days"][0]["exercises"] = prescribed_exercises(
        "leg_press_45",
        "supino_reto_halteres",
        "supino_inclinado_halteres",
        "remada_maquina",
        "prancha_frontal",
    )

    normalized = normalize_workout_output(generated, workout_questionnaire())

    assert [exercise["catalog_key"] for exercise in normalized["days"][0]["exercises"]][1:3] == [
        "supino_reto_halteres",
        "supino_inclinado_halteres",
    ]


def test_guided_workout_creation_and_temporary_replacement(app, client, monkeypatch):
    register_premium(app, client)
    monkeypatch.setattr("src.routes.user_routes.generate_workout_plan", lambda *args: generated_workout())

    response = client.post("/api/workout_plans/generate", json=workout_questionnaire())

    assert response.status_code == 201
    plan = response.get_json()["plan"]
    assert plan["split_type"] == "full_body"
    assert len(plan["days"]) == 2
    assert len(plan["days"][0]["exercises"]) == 4

    day = plan["days"][0]
    exercise = day["exercises"][0]
    session_response = client.post(f"/api/workout_plans/{plan['id']}/days/{day['id']}/sessions")
    assert session_response.status_code == 201
    session_id = session_response.get_json()["session"]["id"]
    active_response = client.get("/api/workout_sessions/active")
    assert active_response.status_code == 200
    assert active_response.get_json()["session"]["id"] == session_id
    assert active_response.get_json()["day"]["id"] == day["id"]
    conflicting_start = client.post(
        f"/api/workout_plans/{plan['id']}/days/{plan['days'][1]['id']}/sessions"
    )
    assert conflicting_start.status_code == 409
    assert conflicting_start.get_json()["session"]["id"] == session_id
    assert client.delete(f"/api/workout_plans/{plan['id']}").status_code == 409

    options_response = client.post(
        f"/api/workout_sessions/{session_id}/exercises/{exercise['id']}/replacement_options",
        json={"unavailable_equipment": ["machine"], "available_equipment": ["full_gym"]},
    )
    assert options_response.status_code == 200
    options = options_response.get_json()["options"]
    assert options
    assert all(option["equipment"] != "machine" for option in options)

    replace_response = client.post(
        f"/api/workout_sessions/{session_id}/exercises/{exercise['id']}/replace",
        json={
            "catalog_key": options[0]["catalog_key"],
            "unavailable_equipment": ["machine"],
            "available_equipment": ["full_gym"],
        },
    )
    assert replace_response.status_code == 200
    assert replace_response.get_json()["override"]["name"] == options[0]["name"]
    assert replace_response.get_json()["override"]["equipment"] == options[0]["equipment"]

    other_client = app.test_client()
    other_client.post("/api/register", json={"username": "other", "password": "strong-password"})
    forbidden = other_client.post(
        f"/api/workout_sessions/{session_id}/exercises/{exercise['id']}/replacement_options",
        json={"unavailable_equipment": ["machine"]},
    )
    assert forbidden.status_code == 404
    assert other_client.post(
        f"/api/workout_sessions/{session_id}/exercises/{exercise['id']}/complete"
    ).status_code == 404

    completed_ids = []
    for day_exercise in day["exercises"]:
        complete_response = client.post(
            f"/api/workout_sessions/{session_id}/exercises/{day_exercise['id']}/complete"
        )
        assert complete_response.status_code == 200
        completed_ids.append(day_exercise["id"])
        assert complete_response.get_json()["session"]["completed_exercise_ids"] == completed_ids
    assert client.post(
        f"/api/workout_sessions/{session_id}/exercises/{exercise['id']}/complete"
    ).get_json()["session"]["completed_exercise_ids"] == completed_ids
    assert client.get("/api/workout_sessions/active").get_json()["session"]["completed_exercise_ids"] == completed_ids

    detail = client.get(f"/api/workout_plans/{plan['id']}").get_json()
    assert detail["days"][0]["exercises"][0]["name"] == "Leg press 45°"
    assert client.post(f"/api/workout_sessions/{session_id}/finish").status_code == 200
    assert client.get("/api/workout_sessions/active").get_json()["session"] is None
    with app.app_context():
        assert WorkoutSession.query.one().completed_at is not None
        assert WorkoutSessionExerciseCompletion.query.count() == 4
        assert WorkoutExercise.query.filter_by(id=exercise["id"]).one().name == "Leg press 45°"


def test_guided_diet_creation(app, client, monkeypatch):
    register_premium(app, client)
    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", lambda *args: generated_diet())

    response = client.post("/api/diet_plans/generate", json=diet_questionnaire())

    assert response.status_code == 201
    plan = response.get_json()["plan"]
    assert plan["schema_version"] == 2
    assert plan["plan_mode"] == "rotation_3_day"
    assert len(plan["meals"]) == 9
    assert plan["meals"][0]["items"] == ["1 porção de arroz", "1 porção de feijão"]
    with app.app_context():
        assert DietPlan.query.one().meals_per_day == 3


def test_guided_generation_requires_premium(app, client, monkeypatch):
    client.post("/api/register", json={"username": "free", "password": "strong-password"})
    monkeypatch.setattr("src.routes.user_routes.generate_workout_plan", lambda *args: generated_workout())

    response = client.post("/api/workout_plans/generate", json=workout_questionnaire())

    assert response.status_code == 403
    with app.app_context():
        assert WorkoutPlan.query.count() == 0


def test_guided_workout_rejects_incompatible_split(app, client):
    register_premium(app, client)

    response = client.post(
        "/api/workout_plans/generate",
        json=workout_questionnaire(days_per_week=4, split_type="abcde"),
    )

    assert response.status_code == 400
    assert "split_type" in response.get_json()["fields"]


def _create_diet_plan(client, monkeypatch):
    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", lambda *args: generated_diet())
    response = client.post("/api/diet_plans/generate", json=diet_questionnaire())
    return response.get_json()["plan"]


def _generated_day():
    return {
        "type": "diet_plan_day",
        "meals": [
            {
                "meal_type": meal_type,
                "items": ["1 ovo", "1 fatia de pão integral"],
                "prep": "Prepare rapidamente.",
                "prep_minutes": 10,
                "calories": 350,
                "protein": 22,
                "carbs": 30,
                "fat": 12,
                "notes": "Refeição ajustada.",
                "substitutions": [],
            }
            for meal_type in ("Café da manhã", "Almoço", "Jantar")
        ],
    }


def test_diet_plan_meal_edit(app, client, monkeypatch):
    register_premium(app, client)
    plan = _create_diet_plan(client, monkeypatch)
    meal_id = plan["meals"][0]["id"]

    response = client.patch(f"/api/diet_plans/{plan['id']}/meals/{meal_id}", json={
        "description": "2 ovos mexidos, 1 fatia de pão integral",
        "notes": "Sem café",
    })

    assert response.status_code == 200
    meal = response.get_json()["meal"]
    assert meal["description"] == "2 ovos mexidos, 1 fatia de pão integral"
    assert meal["notes"] == "Sem café"


def test_diet_plan_day_suggest_and_replace(app, client, monkeypatch):
    register_premium(app, client)
    plan = _create_diet_plan(client, monkeypatch)
    monkeypatch.setattr("src.routes.user_routes.generate_diet_day", lambda *args: _generated_day())

    suggest = client.post(f"/api/diet_plans/{plan['id']}/suggest", json={"day": 1, "feedback": "mais proteína"})
    assert suggest.status_code == 200
    suggested = suggest.get_json()
    assert suggested["day"] == 1
    assert len(suggested["meals"]) == 3
    assert "1 ovo" in suggested["meals"][0]["items"]

    replace = client.put(f"/api/diet_plans/{plan['id']}/days/1", json={"meals": suggested["meals"]})
    assert replace.status_code == 200
    updated = replace.get_json()["plan"]
    day_meals = [m for m in updated["meals"] if m["day_of_week"] == "Dia 1"]
    assert len(day_meals) == 3
    assert "1 ovo" in day_meals[0]["items"]


def test_diet_plan_day_suggest_requires_feedback(app, client, monkeypatch):
    register_premium(app, client)
    plan = _create_diet_plan(client, monkeypatch)

    response = client.post(f"/api/diet_plans/{plan['id']}/suggest", json={"day": 1, "feedback": "  "})

    assert response.status_code == 400


def test_diet_plan_day_suggest_invalid_day(app, client, monkeypatch):
    register_premium(app, client)
    plan = _create_diet_plan(client, monkeypatch)

    response = client.post(f"/api/diet_plans/{plan['id']}/suggest", json={"day": 5, "feedback": "x"})

    assert response.status_code == 400


def test_diet_plan_day_replace_requires_owned_plan(app, client, monkeypatch):
    register_premium(app, client)
    plan = _create_diet_plan(client, monkeypatch)

    client.post("/api/logout")
    client.post("/api/register", json={"username": "other", "password": "strong-password"})

    response = client.put(f"/api/diet_plans/{plan['id']}/days/1", json={"meals": _generated_day()["meals"]})
    assert response.status_code == 404
