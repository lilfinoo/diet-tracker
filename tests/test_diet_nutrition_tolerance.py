import pytest

from src.services.diet_plans import calculate_nutrition_targets, normalize_diet_output, validate_diet_questionnaire
from src.services.workout_plans import PlanValidationError
from tests.test_guided_plans import _profile, diet_questionnaire, generated_diet, register_premium


def test_diet_can_be_generated_when_estimates_differ_from_targets(app, client, monkeypatch):
    register_premium(app, client)
    def generate(questionnaire, profile, targets, correction):
        result = generated_diet(targets)
        for day in result['days']:
            original = day['meals'][0]
            day['meals'] = [
                {**original, 'meal_type': f'Refeição {i + 1}',
                 'calories': targets['targetCalories'] / 7,
                 'protein': targets['targetProtein'] * 0.5 / 7,
                 'carbs': targets['targetCarbs'] * 0.5 / 7,
                 'fat': targets['targetFat'] * 0.5 / 7}
                for i in range(7)
            ]
        return result
    monkeypatch.setattr('src.routes.plan_routes.generate_diet_plan', generate)
    response = client.post('/api/diet_plans/generate', json=diet_questionnaire(meals_per_day=7))
    assert response.status_code == 201, response.get_json()
    plan = response.get_json()['plan']
    assert len(plan['meals']) == 21
    assert sum(m['protein'] for m in plan['meals'] if m['day_of_week'] == 'Dia 1') < plan['nutrition_targets']['targetProtein'] * 0.6


def test_diet_still_rejects_unsafe_low_calories_and_invalid_values():
    questionnaire = validate_diet_questionnaire(diet_questionnaire())
    targets = calculate_nutrition_targets(_profile(), questionnaire)
    plan = generated_diet(targets)
    for meal in plan['days'][0]['meals']:
        meal['calories'] = targets['bmr'] * 0.8 / 3
    with pytest.raises(PlanValidationError) as exc:
        normalize_diet_output(plan, questionnaire, targets)
    assert any(key.endswith('.bmr') for key in exc.value.errors)
    plan['days'][0]['meals'][0]['protein'] = -1
    with pytest.raises(PlanValidationError) as exc:
        normalize_diet_output(plan, questionnaire, targets)
    assert any(key.endswith('.protein') for key in exc.value.errors)
