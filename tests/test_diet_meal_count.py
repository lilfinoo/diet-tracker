import pytest

from src.services.diet_plans import validate_diet_questionnaire
from src.services.workout_plans import PlanValidationError
from tests.test_guided_plans import diet_questionnaire, generated_diet, register_premium


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6, 7])
def test_diet_questionnaire_accepts_meal_counts_offered_by_ios(count):
    assert validate_diet_questionnaire(diet_questionnaire(meals_per_day=count))["meals_per_day"] == count


@pytest.mark.parametrize("count", [0, 8])
def test_diet_questionnaire_rejects_meal_counts_outside_ios_range(count):
    with pytest.raises(PlanValidationError) as exc:
        validate_diet_questionnaire(diet_questionnaire(meals_per_day=count))
    assert "meals_per_day" in exc.value.errors


@pytest.mark.parametrize("count", [1, 2, 6, 7])
def test_generate_diet_preserves_requested_meal_count(app, client, monkeypatch, count):
    register_premium(app, client)

    def generate(questionnaire, profile, targets, correction):
        plan = generated_diet(targets)
        for day in plan["days"]:
            template = day["meals"][0]
            day["meals"] = [
                {**template, "meal_type": f"Refeição {index + 1}",
                 **{key: round(targets[target] / count, 1) for key, target in (
                     ("calories", "targetCalories"), ("protein", "targetProtein"),
                     ("carbs", "targetCarbs"), ("fat", "targetFat"))}}
                for index in range(count)
            ]
        return plan

    monkeypatch.setattr("src.routes.plan_routes.generate_diet_plan", generate)
    response = client.post("/api/diet_plans/generate", json=diet_questionnaire(meals_per_day=count))
    assert response.status_code == 201, response.get_json()
    meals = response.get_json()["plan"]["meals"]
    assert [sum(meal["day_of_week"] == f"Dia {day}" for meal in meals) for day in range(1, 4)] == [count] * 3
