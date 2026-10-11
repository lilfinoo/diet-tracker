from copy import deepcopy

import pytest

from src.services.diet_plans import correction_feedback
from src.services.workout_plans import PlanValidationError


TARGETS = {
    "bmr": 2000,
    "targetCalories": 2000,
    "targetProtein": 150,
    "targetCarbs": 215,
    "targetFat": 60,
}


def test_correction_keeps_every_failure_and_respects_bmr_floor():
    errors = {f"days.{index}.nutrition": "invalid" for index in range(1, 25)}
    targets = {**TARGETS, "targetCalories": 1900}

    feedback = correction_feedback(PlanValidationError(errors), targets=targets)

    assert feedback["validation_errors"] == errors
    assert feedback["allowed_daily_ranges"]["calories"]["min"] == 1800


@pytest.mark.parametrize("plan_type", ["diet_plan", "diet_plan_day"])
def test_correction_reports_meal_sums_and_target_differences_without_mutation(plan_type):
    meals = [
        {"calories": 800, "protein": 60, "carbs": 80, "fat": 25},
        {"calories": 1000, "protein": 60, "carbs": 110, "fat": 30},
    ]
    candidate = {"type": plan_type}
    if plan_type == "diet_plan":
        candidate["days"] = [{"meals": meals}]
    else:
        candidate["meals"] = meals
    original = deepcopy(candidate)

    feedback = correction_feedback(PlanValidationError({"nutrition": "invalid"}), candidate, TARGETS)

    assert feedback["daily_totals"] == [{
        "day_number": 1,
        "totals": {"calories": 1800, "protein": 120, "carbs": 190, "fat": 55},
        "target_differences": {"calories": 200, "protein": 30, "carbs": 25, "fat": 5},
    }]
    assert candidate == original


@pytest.mark.parametrize("meals", [None, [], [None], [{"calories": float("nan")}], [{"calories": "bad"}]])
def test_correction_does_not_fabricate_totals_for_malformed_meals(meals):
    candidate = {"type": "diet_plan_day", "meals": meals}
    feedback = correction_feedback(PlanValidationError({"day": "invalid"}), candidate, TARGETS)
    assert feedback["daily_totals"] == []
