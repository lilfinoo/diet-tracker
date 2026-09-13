import base64
from datetime import datetime
import json
import uuid

import pytest

from src.models.user import AdminActionAudit, db, DietPlan, DietPlanMeal, Subscription, User, WorkoutExercise, WorkoutPlan
from src.services import ai
from src.services.ai import (
    AIQuotaExceededError,
    AIResponseError,
    AIServiceError,
    AIServiceUnavailableError,
    AITruncatedResponseError,
    generate_response,
)
from tests.helpers import registration_payload


def register(client, username="alice"):
    return client.post("/api/register", json=registration_payload(username))


def test_register_and_create_diet_entry(client):
    assert register(client).status_code == 201
    response = client.post("/api/diet", json={"date": "2026-08-05", "meal_type": "Almoço", "description": "Arroz"})
    assert response.status_code == 201
    assert response.get_json()["entry"]["description"] == "Arroz"


def test_plan_details_include_children(app, client):
    register(client)
    with app.app_context():
        user = User.query.filter_by(username="alice").one()
        diet = DietPlan(user_id=user.id, title="Plano", description="Descrição")
        workout = WorkoutPlan(user_id=user.id, title="Treino")
        db.session.add_all([diet, workout])
        db.session.flush()
        db.session.add(DietPlanMeal(diet_plan_id=diet.id, meal_type="Almoço", description="Arroz"))
        db.session.add(WorkoutExercise(workout_plan_id=workout.id, name="Agachamento"))
        db.session.commit()
        diet_id, workout_id = diet.id, workout.id

    assert client.get(f"/api/diet_plans/{diet_id}").get_json()["meals"][0]["description"] == "Arroz"
    assert client.get(f"/api/workout_plans/{workout_id}").get_json()["exercises"][0]["name"] == "Agachamento"


def test_admin_uuid_route(app, client):
    register(client, "admin")
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        admin.is_admin = True
        target = User(username="target")
        target.set_password("strong-password")
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    response = client.post(f"/api/admin/users/{target_id}/ban")
    assert response.status_code == 200
    with app.app_context():
        audit = AdminActionAudit.query.one()
        assert audit.action == "user.banned"
        assert audit.subject_user_id == target_id


def test_admin_can_grant_and_revoke_premium(app, client):
    register(client, "admin")
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        admin.is_admin = True
        target = User(username="premium-target")
        target.set_password("strong-password")
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    missing_duration = client.patch(
        f"/api/admin/users/{target_id}/premium", json={"is_premium": True}
    )
    assert missing_duration.status_code == 400
    assert "quanto tempo" in missing_duration.get_json()["error"]

    grant = client.patch(
        f"/api/admin/users/{target_id}/premium",
        json={"is_premium": True, "duration_days": 30},
    )
    assert grant.status_code == 200
    assert grant.get_json()["user"]["is_premium"] is True
    with app.app_context():
        subscription = Subscription.query.filter_by(
            user_id=target_id, provider="admin", plan_code="premium_student"
        ).one()
        assert subscription.status == "active"
        assert 29 <= (subscription.current_period_end - datetime.utcnow()).days <= 30
        assert db.session.get(User, target_id).is_premium is False
        assert AdminActionAudit.query.filter_by(action="premium.granted").count() == 1

    revoke = client.patch(f"/api/admin/users/{target_id}/premium", json={"is_premium": False})
    assert revoke.status_code == 200
    assert revoke.get_json()["user"]["is_premium"] is False
    with app.app_context():
        assert db.session.get(User, target_id).is_premium is False
        assert Subscription.query.filter_by(user_id=target_id, provider="admin").one().status == "canceled"
        assert AdminActionAudit.query.filter_by(action="premium.revoked").count() == 1


def test_admin_can_grant_permanent_premium_access(app, client):
    register(client, "permanent-admin")
    with app.app_context():
        admin = User.query.filter_by(username="permanent-admin").one()
        admin.is_admin = True
        target = User(username="permanent-premium")
        target.set_password("strong-password")
        db.session.add(target)
        db.session.commit()
        target_id = target.id

    response = client.patch(
        f"/api/admin/users/{target_id}/premium",
        json={"is_premium": True, "duration_days": None},
    )

    assert response.status_code == 200
    with app.app_context():
        grant = Subscription.query.filter_by(user_id=target_id, provider="admin").one()
        assert grant.current_period_end is None


def test_premium_update_requires_admin(client):
    response = client.patch(f"/api/admin/users/{uuid.uuid4()}/premium", json={"is_premium": True})
    assert response.status_code == 401

    register(client)
    response = client.patch(f"/api/admin/users/{uuid.uuid4()}/premium", json={"is_premium": True})
    assert response.status_code == 403


def test_gemini_requires_api_key(app):
    with app.app_context():
        user = User(username="gemini-user")
        with pytest.raises(AIServiceError, match="GEMINI_API_KEY"):
            generate_response("Olá", user, None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (type("ProviderError", (Exception,), {"code": 429, "status": "RESOURCE_EXHAUSTED"})(), "quota_rate_limit"),
        (type("ProviderError", (Exception,), {"code": 503, "status": "UNAVAILABLE"})(), "timeout_unavailable"),
        (ai.httpx.ReadTimeout("timed out"), "timeout_unavailable"),
        (type("ProviderError", (Exception,), {"code": 401, "status": "UNAUTHENTICATED"})(), "authentication_configuration"),
        (type("ProviderError", (Exception,), {"code": 403, "status": "PERMISSION_DENIED"})(), "authentication_configuration"),
    ],
)
def test_gemini_provider_errors_use_structured_categories(error, expected):
    assert ai._provider_error_category(error)[0] == expected


def test_gemini_failure_log_excludes_provider_message(app, monkeypatch, caplog):
    secret = "prompt health-data secret@example.com api-key-value"

    class ProviderError(Exception):
        code = 503
        status = "UNAVAILABLE"

    class Models:
        def generate_content(self, **_kwargs):
            raise ProviderError(secret)

    class Client:
        models = Models()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(ai.genai, "Client", lambda **_kwargs: Client())
    with app.app_context(), caplog.at_level("WARNING"):
        app.config["GEMINI_API_KEY"] = "configured"
        with pytest.raises(AIServiceUnavailableError, match="indisponível"):
            ai._completion("system", "private prompt", 100, 0.2)

    assert "category=timeout_unavailable http_status=503" in caplog.text
    assert secret not in caplog.text
    assert "private prompt" not in caplog.text


def test_chat_uses_configured_output_limit(app, monkeypatch):
    output_limits = []
    monkeypatch.setattr(ai, "_completion", lambda *args, **kwargs: output_limits.append((args[2], kwargs["model"])) or "Resposta")
    with app.app_context():
        app.config["GEMINI_CHAT_MAX_TOKENS"] = 777
        user = User(username="limit-user")
        assert generate_response("Olá", user, None) == "Resposta"
    assert output_limits == [(777, app.config["GEMINI_CHAT_MODEL"])]


def test_chat_retries_with_a_shorter_answer_after_truncation(app, monkeypatch):
    calls = []

    def completion(*args, **kwargs):
        calls.append((args[2], args[3]))
        if len(calls) == 1:
            raise AITruncatedResponseError("Gemini response reached the output token limit")
        return "Resposta curta"

    monkeypatch.setattr(ai, "_completion", completion)
    with app.app_context():
        app.config["GEMINI_CHAT_MAX_TOKENS"] = 768
        user = User(username="retry-user")
        assert generate_response("Como emagrecer?", user, None) == "Resposta curta"
    assert calls == [(768, 0.5), (1024, 0.3)]


def test_nutrition_parses_structured_gemini_response(app, monkeypatch):
    monkeypatch.setattr(
        ai,
        "_completion",
        lambda *args, **kwargs: '{"calories": 100, "protein": 10, "carbs": 20, "fat": 5}',
    )
    with app.app_context():
        assert ai.calculate_nutrition("100g de arroz")["calories"] == 100


def test_diet_ai_receives_fixed_targets_without_full_food_catalog(app, monkeypatch):
    captured = {}

    def completion(*args, **kwargs):
        captured["system"] = args[0]
        captured["payload"] = json.loads(args[1])
        captured["schema"] = kwargs["json_schema"]
        return '{"type":"diet_plan","title":"Plano","description":"Teste","days":[]}'

    monkeypatch.setattr(ai, "_completion", completion)
    targets = {
        "bmr": 1700,
        "maintenanceCalories": 2500,
        "targetCalories": 2625,
        "targetProtein": 150,
        "targetCarbs": 335,
        "targetFat": 76,
    }

    with app.app_context():
        ai.generate_diet_plan({"meals_per_day": 3}, None, targets)

    meal_schema = captured["schema"]["properties"]["days"]["items"]["properties"]["meals"]["items"]
    assert captured["payload"]["nutritionTargets"] == targets
    assert "foodCatalog" not in captured["payload"]
    assert len(json.dumps(captured["payload"])) < 2000
    assert "restrições do sistema" in captured["system"]
    assert "items" in meal_schema["required"]
    assert {"calories", "protein", "carbs", "fat"} <= set(meal_schema["properties"])


def test_diet_generation_retries_temporary_unavailability(app, monkeypatch):
    calls = []
    waits = []

    def completion(*args, **kwargs):
        calls.append((args[2], kwargs["model"]))
        if len(calls) == 1:
            raise AIServiceUnavailableError("busy")
        return '{"type":"diet_plan","title":"Plano","description":"Teste","days":[]}'

    monkeypatch.setattr(ai, "_completion", completion)
    monkeypatch.setattr(ai.time, "sleep", waits.append)
    with app.app_context():
        app.config.update(
            GEMINI_DIET_PLAN_MODEL="diet-model",
            GEMINI_DIET_PLAN_MAX_TOKENS=8192,
            GEMINI_DIET_RETRY_ATTEMPTS=2,
        )
        result = ai.generate_diet_plan({"meals_per_day": 3}, None, {"targetCalories": 2000})

    assert result["type"] == "diet_plan"
    assert calls == [(8192, "diet-model"), (8192, "diet-model")]
    assert waits == [1]


def test_workout_generation_uses_fallback_model(app, monkeypatch):
    models = []

    def completion(*args, **kwargs):
        models.append(kwargs["model"])
        if len(models) == 1:
            raise AIServiceUnavailableError("busy")
        return '{"type":"workout_plan","title":"Plano","description":"Teste","days":[]}'

    monkeypatch.setattr(ai, "_completion", completion)
    questionnaire = {
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
    with app.app_context():
        app.config.update(
            GEMINI_WORKOUT_MODEL="primary-model",
            GEMINI_WORKOUT_FALLBACK_MODEL="fallback-model",
        )
        result = ai.generate_workout_plan(questionnaire, None)

    assert result["type"] == "workout_plan"
    assert models == ["primary-model", "fallback-model"]


def test_workout_generation_retries_models_after_temporary_unavailability(app, monkeypatch):
    models = []
    waits = []

    def completion(*args, **kwargs):
        models.append(kwargs["model"])
        if len(models) < 3:
            raise AIServiceUnavailableError("busy")
        return '{"type":"workout_plan","title":"Plano","description":"Teste","days":[]}'

    monkeypatch.setattr(ai, "_completion", completion)
    monkeypatch.setattr(ai.time, "sleep", waits.append)
    questionnaire = {
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
    with app.app_context():
        app.config.update(
            GEMINI_WORKOUT_MODEL="primary-model",
            GEMINI_WORKOUT_FALLBACK_MODEL="fallback-model",
            GEMINI_WORKOUT_UNAVAILABLE_RETRIES=2,
        )
        result = ai.generate_workout_plan(questionnaire, None)

    assert result["type"] == "workout_plan"
    assert models == ["primary-model", "fallback-model", "primary-model"]
    assert waits == [1]


def test_workout_retry_sends_only_invalid_days_and_previous_plan(app, monkeypatch):
    captured = {}

    def completion(*args, **kwargs):
        captured["system"] = args[0]
        captured["payload"] = json.loads(args[1])
        captured["schema"] = kwargs["json_schema"]
        return '{"days":[]}'

    monkeypatch.setattr(ai, "_completion", completion)
    questionnaire = {
        "goal": "hypertrophy",
        "experience_level": "advanced",
        "days_per_week": 5,
        "split_type": "abcde",
        "session_duration": 90,
        "equipment": ["full_gym"],
        "limitations": "",
        "priorities": "",
        "avoid_exercises": "",
    }
    previous_plan = {"type": "workout_plan", "days": [{"focus": f"Dia {index}", "exercises": []} for index in range(1, 6)]}
    correction = {
        "previous_plan": previous_plan,
        "validation_errors": {
            "days.1.roles.2": "Faltou pressão inclinada.",
            "days.4.focus": "Exercício fora do foco.",
        },
        "invalid_day_numbers": [1, 4],
    }

    with app.app_context():
        ai.generate_workout_plan(questionnaire, None, correction)

    assert captured["payload"]["repair"] == correction
    assert [day["day_number"] for day in captured["payload"]["required_days"]] == [1, 4]
    assert captured["payload"]["required_days"][0]["selection_limits"]["unique_catalog_keys"] is True
    assert captured["payload"]["required_days"][0]["selection_limits"]["max_per_group"]["horizontal_push"] == 4
    assert captured["payload"]["required_days"][1]["selection_limits"]["max_per_group"]["horizontal_pull"] == 2
    assert captured["payload"]["required_days"][1]["selection_limits"]["max_per_training_role"] == 2
    assert all(len(day["slots"]) == 6 for day in captured["payload"]["required_days"])
    assert [slot["allowed_groups"] for slot in captured["payload"]["required_days"][1]["slots"][:4]] == [
        ["vertical_push"],
        ["vertical_push"],
        ["lateral_raise"],
        ["lateral_raise"],
    ]
    shoulder_slots = captured["payload"]["required_days"][1]["slots"]
    assert shoulder_slots[0]["allowed_catalog_keys"] == shoulder_slots[1]["allowed_catalog_keys"]
    assert shoulder_slots[2]["allowed_catalog_keys"] == shoulder_slots[3]["allowed_catalog_keys"]
    assert captured["schema"]["properties"]["days"]["items"]["properties"]["exercises"]["minItems"] == 6
    exercise_schema = captured["schema"]["properties"]["days"]["items"]["properties"]["exercises"]["items"]
    assert "slot_id" in exercise_schema["required"]
    assert exercise_schema["properties"]["sets"] == {"type": "integer", "minimum": 1, "maximum": 6}
    assert exercise_schema["properties"]["reps"] == {"type": "string", "minLength": 1, "maxLength": 30}
    assert exercise_schema["properties"]["rest_seconds"] == {"type": "integer", "minimum": 20, "maximum": 300}
    allowed_slot_keys = {
        catalog_key
        for day in captured["payload"]["required_days"]
        for slot in day["slots"]
        for catalog_key in slot["allowed_catalog_keys"]
    }
    assert set(exercise_schema["properties"]["catalog_key"]["enum"]) == allowed_slot_keys
    assert captured["schema"]["properties"]["days"]["items"]["properties"]["day_number"]["enum"] == [1, 4]
    assert "Retorne somente" in captured["system"]
    assert "três funções distintas" in captured["system"]
    assert "horizontal_pull" in captured["system"]


def test_macro_endpoint_reports_invalid_ai_json(client, monkeypatch):
    register(client)
    monkeypatch.setattr(
        "src.routes.profile_routes.calculate_nutrition",
        lambda description, image_bytes=None, mime_type=None: (_ for _ in ()).throw(
            AIResponseError("invalid JSON")
        ),
    )
    response = client.post("/api/diet/ai_macros", json={"description": "arroz"})
    assert response.status_code == 422


def test_macro_endpoint_with_photo_passes_image_to_ai(client, monkeypatch):
    register(client)
    captured = {}

    def fake_calculate(description, image_bytes, mime_type):
        captured["image_bytes"] = image_bytes
        captured["mime_type"] = mime_type
        return {
            "calories": 300,
            "protein": 20,
            "carbs": 30,
            "fat": 10,
            "precision": "alta",
        }

    monkeypatch.setattr("src.routes.profile_routes.calculate_nutrition", fake_calculate)
    gif = base64.b64encode(b"\xff\xd8\xff\xe0fakejpg").decode()
    response = client.post(
        "/api/diet/ai_macros",
        json={"image": {"data": gif, "mime_type": "image/jpeg"}},
    )
    assert response.status_code == 200
    assert captured["mime_type"] == "image/jpeg"
    assert captured["image_bytes"] == b"\xff\xd8\xff\xe0fakejpg"


def test_macro_endpoint_photo_without_description_is_valid(client, monkeypatch):
    register(client)
    monkeypatch.setattr(
        "src.routes.profile_routes.calculate_nutrition",
        lambda description, image_bytes=None, mime_type=None: {
            "calories": 1,
            "protein": 1,
            "carbs": 1,
            "fat": 1,
            "precision": "alta",
        },
    )
    gif = base64.b64encode(b"\x89PNG\r\n\x1a\nminimal").decode()
    response = client.post(
        "/api/diet/ai_macros",
        json={"image": {"data": gif, "mime_type": "image/png"}},
    )
    assert response.status_code == 200


def test_macro_endpoint_requires_description_or_photo(client):
    register(client)
    response = client.post("/api/diet/ai_macros", json={})
    assert response.status_code == 400


def test_macro_endpoint_rejects_unsupported_image_mime(client):
    register(client)
    response = client.post(
        "/api/diet/ai_macros",
        json={"image": {"data": "abc", "mime_type": "image/svg+xml"}},
    )
    assert response.status_code == 400


def test_macro_endpoint_rejects_invalid_image_base64(client):
    register(client)
    response = client.post(
        "/api/diet/ai_macros",
        json={"image": {"data": "!!not-base64!!", "mime_type": "image/jpeg"}},
    )
    assert response.status_code == 400


def test_chat_opens_diet_questionnaire(app, client):
    register(client)
    with app.app_context():
        User.query.filter_by(username="alice").one().is_premium = True
        db.session.commit()

    response = client.post("/api/chat", json={"message": "Monte algo saudável", "intent": "diet_plan"})

    assert response.status_code == 200
    assert response.get_json()["action"]["type"] == "open_diet_plan_questionnaire"
    with app.app_context():
        assert DietPlan.query.count() == 0


def test_chat_reports_other_invalid_ai_response(app, client, monkeypatch):
    register(client)
    with app.app_context():
        User.query.filter_by(username="alice").one().is_premium = True
        db.session.commit()
    monkeypatch.setattr(
        "src.routes.plan_routes.generate_response",
        lambda *args: (_ for _ in ()).throw(AIResponseError("Resposta inválida da IA.")),
    )

    response = client.post("/api/chat", json={"message": "Explique tudo"})

    assert response.status_code == 422
    assert response.get_json()["error"] == "Resposta inválida da IA."


def test_chat_reports_gemini_quota_limit(app, client, monkeypatch):
    register(client)
    with app.app_context():
        User.query.filter_by(username="alice").one().is_premium = True
        db.session.commit()
    monkeypatch.setattr(
        "src.routes.plan_routes.generate_response",
        lambda *args: (_ for _ in ()).throw(AIQuotaExceededError("A cota da IA foi atingida. Tente novamente em cerca de 30 segundos.")),
    )

    response = client.post("/api/chat", json={"message": "Olá"})

    assert response.status_code == 429
    assert "cota da IA" in response.get_json()["error"]


def test_chat_opens_workout_questionnaire(app, client):
    register(client)
    with app.app_context():
        User.query.filter_by(username="alice").one().is_premium = True
        db.session.commit()

    response = client.post("/api/chat", json={"message": "Monte meus exercícios", "intent": "workout_plan"})

    assert response.status_code == 200
    assert response.get_json()["action"]["type"] == "open_workout_questionnaire"
    with app.app_context():
        assert WorkoutPlan.query.count() == 0
