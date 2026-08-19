import pytest
from datetime import datetime, timedelta
from types import SimpleNamespace

from src.models.user import (
    DietPlan,
    User,
    UserProfile,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
    WorkoutSessionExerciseCompletion,
    WorkoutSetPerformance,
    db,
)
from src.services.diet_plans import (
    calculate_nutrition_targets,
    diet_restriction_policy,
    merge_profile_restrictions,
    normalize_diet_output,
    validate_diet_questionnaire,
)
from src.services.workout_plans import (
    PlanValidationError,
    normalize_workout_output,
    validate_workout_questionnaire,
    workout_day_specs,
)


def register_premium(app, client):
    client.post("/api/register", json={"username": "guided", "password": "strong-password"})
    with app.app_context():
        user = User.query.filter_by(username="guided").one()
        user.is_premium = True
        db.session.add(UserProfile(
            user_id=user.id,
            age=30,
            gender="masculino",
            activity_level="moderado",
            weight=80,
            height=180,
        ))
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


@pytest.mark.parametrize("split_type", ["full_body", "upper_lower", "abc", "abcd", "abcde"])
def test_five_day_workout_accepts_user_selected_split(split_type):
    questionnaire = validate_workout_questionnaire(
        workout_questionnaire(days_per_week=5, split_type=split_type)
    )

    specs = workout_day_specs(questionnaire["split_type"], questionnaire["days_per_week"])

    assert questionnaire["split_type"] == split_type
    assert len(specs) == 5
    assert [spec["order"] for spec in specs] == [1, 2, 3, 4, 5]


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


def diet_questionnaire(**overrides):
    data = {
        "goal": "general_health",
        "meals_per_day": 3,
        "diet_pattern": "omnivore",
        "training_days_per_week": 3,
        "change_pace": "conservative",
        "allergies": [],
        "intolerances": [],
        "disliked_foods": [],
        "preferred_foods": ["arroz", "feijão"],
        "available_ingredients": ["arroz", "frango", "banana"],
        "budget": "economical",
        "prep_minutes": 30,
        "notes": "",
    }
    data.update(overrides)
    return data


def generated_diet(targets):
    meal_totals = {
        "calories": round(targets["targetCalories"] / 3, 1),
        "protein": round(targets["targetProtein"] / 3, 1),
        "carbs": round(targets["targetCarbs"] / 3, 1),
        "fat": round(targets["targetFat"] / 3, 1),
    }
    return {
        "type": "diet_plan",
        "title": "Rotação alimentar simples",
        "description": "Três dias econômicos.",
        "days": [
            {
                "meals": [
                    {
                        "meal_type": meal_type,
                        "items": ["Arroz cozido", "Peito de frango grelhado", "Azeite e vegetais"],
                        "prep": "Sirva os alimentos preparados.",
                        "prep_minutes": 10,
                        **meal_totals,
                        "notes": "Ajuste a porção à fome.",
                        "substitutions": [],
                    }
                    for meal_type in ("Café da manhã", "Almoço", "Jantar")
                ],
            }
            for _ in range(3)
        ],
    }


def _profile(**overrides):
    data = {
        "age": 30,
        "gender": "masculino",
        "activity_level": "moderado",
        "dietary_restrictions": None,
        "weight": 80,
        "height": 180,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.parametrize(
    ("profile", "questionnaire", "expected"),
    [
        (
            _profile(age=25, height=200, weight=100),
            diet_questionnaire(goal="muscle_gain", training_days_per_week=5),
            {"bmr": 2130, "maintenanceCalories": 3302, "targetCalories": 3467, "targetProtein": 180},
        ),
        (
            _profile(age=30, gender="feminino", height=160, weight=55, activity_level="sedentario"),
            diet_questionnaire(goal="maintenance", training_days_per_week=0),
            {"bmr": 1239, "maintenanceCalories": 1487, "targetCalories": 1487, "targetProtein": 88},
        ),
        (
            _profile(age=35, height=175, weight=110, activity_level="leve"),
            diet_questionnaire(goal="fat_loss", training_days_per_week=1, change_pace="moderate"),
            {"bmr": 2024, "maintenanceCalories": 2732, "targetCalories": 2322, "targetProtein": 198},
        ),
    ],
)
def test_nutrition_targets_for_representative_profiles(profile, questionnaire, expected):
    questionnaire = validate_diet_questionnaire(questionnaire)

    targets = calculate_nutrition_targets(profile, questionnaire)

    assert targets | expected == targets
    macro_calories = targets["targetProtein"] * 4 + targets["targetCarbs"] * 4 + targets["targetFat"] * 9
    assert abs(macro_calories - targets["targetCalories"]) / targets["targetCalories"] <= 0.01


def test_high_training_volume_caps_activity_factor():
    questionnaire = validate_diet_questionnaire(diet_questionnaire(training_days_per_week=7))

    targets = calculate_nutrition_targets(_profile(activity_level="intenso"), questionnaire)

    assert targets["activityFactor"] == 1.7
    assert targets["maintenanceCalories"] == round(targets["bmr"] * 1.7)


def test_nutrition_target_direction_matches_goal():
    profile = _profile(weight=110, activity_level="leve")
    loss = calculate_nutrition_targets(profile, validate_diet_questionnaire(diet_questionnaire(goal="fat_loss")))
    gain = calculate_nutrition_targets(profile, validate_diet_questionnaire(diet_questionnaire(goal="muscle_gain")))

    assert loss["bmr"] <= loss["targetCalories"] < loss["maintenanceCalories"]
    assert gain["targetCalories"] > gain["maintenanceCalories"]


def test_partial_custom_targets_preserve_values_and_complete_missing_macros():
    questionnaire = validate_diet_questionnaire(diet_questionnaire(custom_targets={
        "calories": 2600,
        "protein": 170,
        "carbs": None,
        "fat": None,
    }))

    targets = calculate_nutrition_targets(_profile(), questionnaire)

    assert targets["targetCalories"] == 2600
    assert targets["targetProtein"] == 170
    assert targets["targetCarbs"] > 0
    assert targets["targetFat"] > 0
    assert abs(targets["targetProtein"] * 4 + targets["targetCarbs"] * 4 + targets["targetFat"] * 9 - 2600) / 2600 <= 0.01


def test_incompatible_complete_custom_targets_are_rejected():
    questionnaire = validate_diet_questionnaire(diet_questionnaire(custom_targets={
        "calories": 2000,
        "protein": 250,
        "carbs": 500,
        "fat": 150,
    }))

    with pytest.raises(PlanValidationError) as error:
        calculate_nutrition_targets(_profile(), questionnaire)

    assert "custom_targets" in error.value.errors


def test_custom_macros_complete_missing_calories():
    questionnaire = validate_diet_questionnaire(diet_questionnaire(custom_targets={
        "calories": None,
        "protein": 150,
        "carbs": 300,
        "fat": 80,
    }))

    targets = calculate_nutrition_targets(_profile(), questionnaire)

    assert targets["targetCalories"] == 2520


def test_diet_output_rejects_profile_restriction():
    questionnaire = validate_diet_questionnaire(diet_questionnaire())
    profile = _profile(dietary_restrictions="Não consumir frango")
    questionnaire = merge_profile_restrictions(questionnaire, profile)
    targets = calculate_nutrition_targets(profile, questionnaire)

    with pytest.raises(PlanValidationError) as error:
        normalize_diet_output(generated_diet(targets), questionnaire, targets)

    assert any("restrição" in message for message in error.value.errors.values())


def test_profile_dislikes_are_preferences_not_prohibitions():
    questionnaire = validate_diet_questionnaire(diet_questionnaire(disliked_foods=["frango"]))
    questionnaire = merge_profile_restrictions(
        questionnaire,
        _profile(dietary_restrictions="Não gosto de feijão e salada"),
    )
    targets = calculate_nutrition_targets(_profile(), questionnaire)

    policy = diet_restriction_policy(questionnaire)
    normalized = normalize_diet_output(generated_diet(targets), questionnaire, targets)

    assert policy["prohibited"] == []
    assert policy["avoid_when_possible"] == ["feijao", "frango", "salada"]
    assert len(normalized["meals"]) == 9


def test_lactose_free_and_plant_alternatives_are_allowed():
    questionnaire = validate_diet_questionnaire(diet_questionnaire(intolerances=["lactose"]))
    questionnaire = merge_profile_restrictions(questionnaire, _profile())
    targets = calculate_nutrition_targets(_profile(), questionnaire)
    generated = generated_diet(targets)
    generated["days"][0]["meals"][0]["items"] = ["Iogurte sem lactose", "Leite de aveia", "Banana"]

    normalized = normalize_diet_output(generated, questionnaire, targets)

    assert normalized["meals"][0]["items"][0] == "Iogurte sem lactose"


def test_regular_dairy_is_rejected_for_lactose_intolerance():
    questionnaire = validate_diet_questionnaire(diet_questionnaire(intolerances=["lactose"]))
    questionnaire = merge_profile_restrictions(questionnaire, _profile())
    targets = calculate_nutrition_targets(_profile(), questionnaire)
    generated = generated_diet(targets)
    generated["days"][0]["meals"][0]["items"] = ["Iogurte integral", "Banana"]

    with pytest.raises(PlanValidationError) as error:
        normalize_diet_output(generated, questionnaire, targets)

    assert any("iogurte" in message.lower() and "lactose" in message for message in error.value.errors.values())


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


def test_workout_validation_discards_excess_equivalent_chest_press_variations():
    generated = generated_workout()
    generated["days"][0]["exercises"] = prescribed_exercises(
        "leg_press_45",
        "supino_reto_halteres",
        "supino_maquina",
        "flexao_de_bracos",
        "remada_maquina",
    )

    normalized = normalize_workout_output(generated, workout_questionnaire())

    assert len(normalized["days"][0]["exercises"]) == 4
    assert [item["catalog_key"] for item in normalized["days"][0]["exercises"]].count(
        "flexao_de_bracos"
    ) == 0


def test_workout_validation_allows_two_equivalent_chest_press_variations():
    generated = generated_workout()
    generated["days"][0]["exercises"] = prescribed_exercises(
        "leg_press_45",
        "supino_reto_halteres",
        "supino_maquina",
        "remada_maquina",
        "prancha_frontal",
    )

    normalized = normalize_workout_output(generated, workout_questionnaire())

    assert len(normalized["days"][0]["exercises"]) == 5


def test_workout_validation_trims_exercises_beyond_duration_maximum():
    generated = generated_workout()
    generated["days"][0]["exercises"] = prescribed_exercises(
        "leg_press_45",
        "supino_reto_halteres",
        "remada_maquina",
        "prancha_frontal",
        "ponte_de_gluteos",
        "puxada_alta_frente",
        "rosca_alternada",
        "triceps_na_polia",
    )

    normalized = normalize_workout_output(generated, workout_questionnaire())

    assert len(normalized["days"][0]["exercises"]) == 7
    assert normalized["days"][0]["exercises"][-1]["catalog_key"] == "rosca_alternada"


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


def test_finished_workout_summary_uses_performed_sets_and_is_idempotent(app, client, monkeypatch):
    register_premium(app, client)
    monkeypatch.setattr("src.routes.user_routes.generate_workout_plan", lambda *args: generated_workout())
    plan = client.post("/api/workout_plans/generate", json=workout_questionnaire()).get_json()["plan"]
    day = plan["days"][0]
    exercises = day["exercises"][:2]
    session = client.post(
        f"/api/workout_plans/{plan['id']}/days/{day['id']}/sessions"
    ).get_json()["session"]

    completed = client.post(
        f"/api/workout_sessions/{session['id']}/exercises/{exercises[0]['id']}/complete",
        json={"sets": [
            {"load_kg": 80, "repetitions": 8},
            {"load_kg": 80, "repetitions": 10},
            {"load_kg": 75, "repetitions": 12},
        ]},
    )
    assert completed.status_code == 200
    assert client.post(
        f"/api/workout_sessions/{session['id']}/exercises/{exercises[1]['id']}/complete",
        json={"sets": [
            {"load_kg": 20, "repetitions": 10},
            {"load_kg": 20, "repetitions": 12},
        ]},
    ).status_code == 200

    finished_at = datetime(2026, 8, 18, 12, 0, 0)
    with app.app_context():
        session_record = db.session.get(WorkoutSession, session["id"])
        session_record.started_at = finished_at - timedelta(minutes=58)
        db.session.commit()

    class FixedDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return finished_at

    monkeypatch.setattr("src.routes.user_routes.datetime", FixedDateTime)
    finish_response = client.post(f"/api/workout_sessions/{session['id']}/finish")
    assert finish_response.status_code == 200
    summary = finish_response.get_json()["summary"]
    assert summary["workout_name"] == day["title"]
    assert summary["duration_seconds"] == 58 * 60
    assert summary["exercises_performed"] == 2
    assert summary["total_exercises"] == len(day["exercises"])
    assert [item["exercise_id"] for item in summary["exercises"]] == [
        exercises[0]["id"],
        exercises[1]["id"],
    ]
    assert all(
        item["exercise_id"] not in {exercise["id"] for exercise in day["exercises"][2:]}
        for item in summary["exercises"]
    )
    assert summary["sets_performed"] == 5
    assert summary["volume_total_kg"] == 2780
    assert summary["personal_records"] == []
    assert summary["exercises"][0]["best_set"] == {
        "set_order": 2,
        "load_kg": 80.0,
        "repetitions": 10,
    }

    repeated = client.post(f"/api/workout_sessions/{session['id']}/finish")
    assert repeated.status_code == 200
    assert repeated.get_json()["summary"] == summary
    assert client.get("/api/workout_sessions/active").get_json()["session"] is None
    with app.app_context():
        assert WorkoutSession.query.one().completed_at == finished_at
        assert WorkoutSessionExerciseCompletion.query.count() == 2
        assert WorkoutSetPerformance.query.count() == 5

    other_client = app.test_client()
    other_client.post("/api/register", json={"username": "summary-other", "password": "strong-password"})
    assert other_client.post(f"/api/workout_sessions/{session['id']}/finish").status_code == 404


def test_workout_summary_omits_volume_when_a_performed_set_has_no_load(app, client, monkeypatch):
    register_premium(app, client)
    monkeypatch.setattr("src.routes.user_routes.generate_workout_plan", lambda *args: generated_workout())
    plan = client.post("/api/workout_plans/generate", json=workout_questionnaire()).get_json()["plan"]
    day = plan["days"][0]
    exercise = day["exercises"][0]
    session = client.post(
        f"/api/workout_plans/{plan['id']}/days/{day['id']}/sessions"
    ).get_json()["session"]

    response = client.post(
        f"/api/workout_sessions/{session['id']}/exercises/{exercise['id']}/complete",
        json={"sets": [{"load_kg": None, "repetitions": 12}]},
    )
    assert response.status_code == 200
    summary = client.post(f"/api/workout_sessions/{session['id']}/finish").get_json()["summary"]
    assert summary["sets_performed"] == 1
    assert summary["volume_total_kg"] is None
    assert summary["exercises"][0]["best_set"]["repetitions"] == 12


def test_owner_can_add_replace_and_remove_plan_exercises(app, client, monkeypatch):
    register_premium(app, client)
    monkeypatch.setattr("src.routes.user_routes.generate_workout_plan", lambda *args: generated_workout())
    plan = client.post("/api/workout_plans/generate", json=workout_questionnaire()).get_json()["plan"]
    day = plan["days"][0]
    original = next(item for item in day["exercises"] if item["catalog_key"] == "supino_maquina")

    catalog = client.get(f"/api/workout_plans/{plan['id']}/exercises/catalog")
    assert catalog.status_code == 200
    assert "supino_inclinado_halteres" in {item["key"] for item in catalog.get_json()["items"]}

    replaced = client.patch(
        f"/api/workout_plans/{plan['id']}/exercises/{original['id']}",
        json={"catalog_key": "supino_reto_halteres"},
    )
    assert replaced.status_code == 200
    replaced_exercise = next(
        item
        for item in replaced.get_json()["plan"]["days"][0]["exercises"]
        if item["id"] == original["id"]
    )
    assert replaced_exercise["catalog_key"] == "supino_reto_halteres"

    added = client.post(
        f"/api/workout_plans/{plan['id']}/days/{day['id']}/exercises",
        json={
            "catalog_key": "supino_inclinado_halteres",
            "sets": 3,
            "reps": "10-12",
            "rest_seconds": 75,
        },
    )
    assert added.status_code == 201
    added_exercise = next(
        item
        for item in added.get_json()["plan"]["days"][0]["exercises"]
        if item["catalog_key"] == "supino_inclinado_halteres"
    )

    custom = client.post(
        f"/api/workout_plans/{plan['id']}/days/{day['id']}/exercises",
        json={"name": "Movimento personalizado", "sets": 2, "reps": "12", "rest_seconds": 60},
    )
    assert custom.status_code == 201
    assert any(
        item["name"] == "Movimento personalizado"
        and item["catalog_key"].startswith("custom:")
        for item in custom.get_json()["plan"]["days"][0]["exercises"]
    )

    removed = client.delete(
        f"/api/workout_plans/{plan['id']}/exercises/{added_exercise['id']}"
    )
    assert removed.status_code == 200
    assert "supino_inclinado_halteres" not in {
        item["catalog_key"] for item in removed.get_json()["plan"]["days"][0]["exercises"]
    }

    session_response = client.post(
        f"/api/workout_plans/{plan['id']}/days/{day['id']}/sessions", json={}
    )
    assert session_response.status_code == 201
    assert client.patch(
        f"/api/workout_plans/{plan['id']}/exercises/{original['id']}",
        json={"catalog_key": "supino_maquina"},
    ).status_code == 409
    assert client.post(
        f"/api/workout_sessions/{session_response.get_json()['session']['id']}/finish"
    ).status_code == 200

    versioned = client.patch(
        f"/api/workout_plans/{plan['id']}/exercises/{original['id']}",
        json={"catalog_key": "supino_maquina"},
    )
    assert versioned.status_code == 200
    assert versioned.get_json()["plan"]["id"] != plan["id"]
    with app.app_context():
        old_plan = db.session.get(WorkoutPlan, plan["id"])
        assert old_plan.status == "archived"
        assert WorkoutSession.query.one().workout_plan_id == old_plan.id
        assert db.session.get(WorkoutExercise, original["id"]).catalog_key == "supino_reto_halteres"


def test_guided_workout_retries_on_validation_error(app, client, monkeypatch):
    register_premium(app, client)
    calls = {"count": 0}

    def flaky_generate(*args):
        calls["count"] += 1
        if calls["count"] == 1:
            raise PlanValidationError({"days.1": "Para 45 minutos, cada treino deve ter entre 4 e 7 exercícios."})
        return generated_workout()

    monkeypatch.setattr("src.routes.user_routes.generate_workout_plan", flaky_generate)

    response = client.post("/api/workout_plans/generate", json=workout_questionnaire())

    assert response.status_code == 201
    assert calls["count"] == 2
    with app.app_context():
        assert WorkoutPlan.query.count() == 1


def test_guided_workout_returns_502_when_retries_exhausted(app, client, monkeypatch):
    register_premium(app, client)

    def always_bad(*args):
        raise PlanValidationError({"days.1": "Para 45 minutos, cada treino deve ter entre 4 e 7 exercícios."})

    monkeypatch.setattr("src.routes.user_routes.generate_workout_plan", always_bad)

    response = client.post("/api/workout_plans/generate", json=workout_questionnaire())

    assert response.status_code == 502
    with app.app_context():
        assert WorkoutPlan.query.count() == 0


def test_guided_diet_creation(app, client, monkeypatch):
    register_premium(app, client)
    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", lambda *args: generated_diet(args[2]))

    response = client.post("/api/diet_plans/generate", json=diet_questionnaire())

    assert response.status_code == 201
    plan = response.get_json()["plan"]
    assert plan["schema_version"] == 3
    assert plan["plan_mode"] == "rotation_3_day"
    assert len(plan["meals"]) == 9
    assert plan["meals"][0]["items"][0] == "Arroz cozido"
    targets = plan["nutrition_targets"]
    first_day = [meal for meal in plan["meals"] if meal["day_of_week"] == "Dia 1"]
    assert abs(sum(meal["calories"] for meal in first_day) - targets["targetCalories"]) / targets["targetCalories"] <= 0.10
    assert abs(sum(meal["protein"] for meal in first_day) - targets["targetProtein"]) / targets["targetProtein"] <= 0.15
    with app.app_context():
        assert DietPlan.query.one().meals_per_day == 3


def test_guided_diet_persists_custom_targets_and_questionnaire(app, client, monkeypatch):
    register_premium(app, client)
    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", lambda *args: generated_diet(args[2]))
    questionnaire = diet_questionnaire(custom_targets={
        "calories": 2600,
        "protein": 170,
        "carbs": None,
        "fat": None,
    })

    response = client.post("/api/diet_plans/generate", json=questionnaire)

    assert response.status_code == 201
    plan = response.get_json()["plan"]
    assert plan["nutrition_targets"]["targetCalories"] == 2600
    assert plan["nutrition_targets"]["targetProtein"] == 170
    assert plan["questionnaire"]["custom_targets"] == questionnaire["custom_targets"]


def test_guided_diet_requires_complete_adult_profile(app, client, monkeypatch):
    client.post("/api/register", json={"username": "incomplete", "password": "strong-password"})
    with app.app_context():
        user = User.query.filter_by(username="incomplete").one()
        user.is_premium = True
        db.session.commit()
    called = {"value": False}
    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", lambda *args: called.update(value=True))

    response = client.post("/api/diet_plans/generate", json=diet_questionnaire())

    assert response.status_code == 400
    assert "profile.age" in response.get_json()["fields"]
    assert called["value"] is False


def test_guided_diet_retries_with_validation_feedback(app, client, monkeypatch):
    register_premium(app, client)
    calls = []

    def generate(*args):
        calls.append(args[3])
        result = generated_diet(args[2])
        if len(calls) == 1:
            result["days"][0]["meals"][0]["calories"] = 0
        return result

    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", generate)

    response = client.post("/api/diet_plans/generate", json=diet_questionnaire())

    assert response.status_code == 201
    assert len(calls) == 2
    assert calls[0] is None
    assert "validation_errors" in calls[1]
    assert calls[1]["previous_plan"]["type"] == "diet_plan"
    assert calls[1]["allowed_daily_ranges"]["protein"]["min"] > 0
    with app.app_context():
        assert DietPlan.query.count() == 1


def test_guided_diet_does_not_persist_after_invalid_attempts(app, client, monkeypatch):
    register_premium(app, client)
    calls = {"count": 0}

    def generate(*args):
        calls["count"] += 1
        result = generated_diet(args[2])
        result["days"][0]["meals"][0]["calories"] = 0
        return result

    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", generate)

    response = client.post("/api/diet_plans/generate", json=diet_questionnaire())

    assert response.status_code == 502
    assert calls["count"] == app.config["GEMINI_DIET_VALIDATION_ATTEMPTS"]
    with app.app_context():
        assert DietPlan.query.count() == 0


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
    monkeypatch.setattr("src.routes.user_routes.generate_diet_plan", lambda *args: generated_diet(args[2]))
    response = client.post("/api/diet_plans/generate", json=diet_questionnaire())
    return response.get_json()["plan"]


def _generated_day(targets):
    plan = generated_diet(targets)
    return {"type": "diet_plan_day", "meals": plan["days"][0]["meals"]}


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
    monkeypatch.setattr("src.routes.user_routes.generate_diet_day", lambda *args: _generated_day(args[4]))

    suggest = client.post(f"/api/diet_plans/{plan['id']}/suggest", json={"day": 1, "feedback": "mais proteína"})
    assert suggest.status_code == 200
    suggested = suggest.get_json()
    assert suggested["day"] == 1
    assert len(suggested["meals"]) == 3
    assert suggested["meals"][0]["items"][0] == "Arroz cozido"

    replace = client.put(f"/api/diet_plans/{plan['id']}/days/1", json={"meals": suggested["meals"]})
    assert replace.status_code == 200
    updated = replace.get_json()["plan"]
    day_meals = [m for m in updated["meals"] if m["day_of_week"] == "Dia 1"]
    assert len(day_meals) == 3
    assert day_meals[0]["items"][0] == "Arroz cozido"


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

    response = client.put(f"/api/diet_plans/{plan['id']}/days/1", json={"meals": []})
    assert response.status_code == 404
