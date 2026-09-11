from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.user import DietEntry, DietMealDailyState, DietPlan, DietPlanMeal, User, UserProfile, db
from main import create_app
from src.config import TestConfig
from tests.helpers import registration_payload


TEST_DATE = "2026-09-07"


def _register(client, username):
    assert client.post("/api/register", json=registration_payload(username)).status_code == 201


def _create_plan(app, username):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        profile = UserProfile.query.filter_by(user_id=user.id).first()
        if profile is None:
            profile = UserProfile(user_id=user.id)
            db.session.add(profile)
        plan = DietPlan(
            user_id=user.id,
            status="published",
            source="manual",
            title="Plano com alternativas",
            generation_context={
                "nutrition_targets": {
                    "targetCalories": 2200,
                    "targetProtein": 150,
                    "targetCarbs": 240,
                    "targetFat": 70,
                }
            },
        )
        db.session.add(plan)
        db.session.flush()
        definitions = [
            ("Café da manhã", "breakfast", 1),
            ("Lanche da manhã", "morning_snack_2", 2),
            ("Almoço", "lunch", 3),
            ("Lanche da tarde", "afternoon_snack_4", 4),
            ("Jantar", "dinner", 5),
        ]
        meals = {}
        for day_number in (1, 2, 3):
            for label, slot_key, order in definitions:
                meal = DietPlanMeal(
                    diet_plan_id=plan.id,
                    day_of_week=f"Dia {day_number}",
                    meal_type=label,
                    description=f"{label} {day_number}",
                    calories=day_number * 100 + order,
                    protein=day_number * 10 + order,
                    carbs=day_number * 20 + order,
                    fat=day_number + order,
                    order=order,
                )
                db.session.add(meal)
                db.session.flush()
                meals[(slot_key, day_number)] = meal.id
        profile.current_diet_plan_id = plan.id
        db.session.commit()
        return user.id, plan.id, meals


def _selection(client, slot_key, meal_id, day=TEST_DATE):
    return client.put(
        f"/api/diet/days/{day}/slots/{slot_key}/selection",
        json={"diet_plan_meal_id": meal_id},
    )


def _outcome(client, slot_key, result, meal_id=None, entry=None, day=TEST_DATE):
    payload = {"result": result}
    if meal_id is not None:
        payload["diet_plan_meal_id"] = meal_id
    if entry is not None:
        payload["entry"] = entry
    return client.put(f"/api/diet/days/{day}/slots/{slot_key}/outcome", json=payload)


def test_daily_view_groups_three_options_and_keeps_two_snacks_distinct(app, client):
    _register(client, "slot-user")
    _create_plan(app, "slot-user")

    response = client.get(f"/api/diet/days/{TEST_DATE}")

    assert response.status_code == 200
    slots = {slot["slot_key"]: slot for slot in response.get_json()["slots"]}
    assert set(slots) == {"breakfast", "morning_snack_2", "lunch", "afternoon_snack_4", "dinner"}
    assert [item["option"] for item in slots["lunch"]["alternatives"]] == [1, 2, 3]
    assert len(slots["morning_snack_2"]["alternatives"]) == 3
    assert len(slots["afternoon_snack_4"]["alternatives"]) == 3


def test_daily_view_supports_one_two_and_three_alternatives(app, client):
    _register(client, "variable-options")
    _, plan_id, _ = _create_plan(app, "variable-options")
    with app.app_context():
        meals = DietPlanMeal.query.filter_by(diet_plan_id=plan_id).all()
        for meal in meals:
            if meal.slot_key == "breakfast" and meal.day_of_week != "Dia 1":
                db.session.delete(meal)
            if meal.slot_key == "lunch" and meal.day_of_week == "Dia 3":
                db.session.delete(meal)
        db.session.commit()

    slots = {slot["slot_key"]: slot for slot in client.get(f"/api/diet/days/{TEST_DATE}").get_json()["slots"]}

    assert len(slots["breakfast"]["alternatives"]) == 1
    assert len(slots["lunch"]["alternatives"]) == 2
    assert len(slots["dinner"]["alternatives"]) == 3


def test_daily_view_without_plan_keeps_manual_registration_available(client):
    _register(client, "no-plan-user")

    response = client.get(f"/api/diet/days/{TEST_DATE}")

    assert response.status_code == 200
    assert response.get_json()["plan"] is None
    assert response.get_json()["slots"] == []


def test_each_slot_can_select_a_different_rotation_option(app, client):
    _register(client, "mixed-options")
    _, _, meals = _create_plan(app, "mixed-options")
    choices = {
        "breakfast": meals[("breakfast", 1)],
        "lunch": meals[("lunch", 3)],
        "afternoon_snack_4": meals[("afternoon_snack_4", 2)],
        "dinner": meals[("dinner", 1)],
    }
    for slot_key, meal_id in choices.items():
        assert _selection(client, slot_key, meal_id).status_code == 200

    slots = {item["slot_key"]: item for item in client.get(f"/api/diet/days/{TEST_DATE}").get_json()["slots"]}
    assert {key: slots[key]["selected_plan_meal_id"] for key in choices} == choices
    assert all(slots[key]["result"] == "pending" for key in choices)


def test_selection_is_isolated_by_date_and_user(app):
    first = app.test_client()
    second = app.test_client()
    _register(first, "first-diet-user")
    _, _, first_meals = _create_plan(app, "first-diet-user")
    _register(second, "second-diet-user")
    _, _, second_meals = _create_plan(app, "second-diet-user")

    assert _selection(first, "lunch", first_meals[("lunch", 3)]).status_code == 200
    first_next_day = first.get("/api/diet/days/2026-09-08").get_json()["slots"]
    assert next(item for item in first_next_day if item["slot_key"] == "lunch")["selected_plan_meal_id"] == first_meals[("lunch", 1)]
    second_today = second.get(f"/api/diet/days/{TEST_DATE}").get_json()["slots"]
    assert next(item for item in second_today if item["slot_key"] == "lunch")["selected_plan_meal_id"] == second_meals[("lunch", 1)]


def test_changing_option_does_not_create_entries_or_macros(app, client):
    _register(client, "selection-only")
    user_id, _, meals = _create_plan(app, "selection-only")

    assert _selection(client, "lunch", meals[("lunch", 3)]).status_code == 200
    view = client.get(f"/api/diet/days/{TEST_DATE}").get_json()
    assert view["totals"] == {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    with app.app_context():
        assert DietEntry.query.filter_by(user_id=user_id).count() == 0


def test_consumed_planned_is_idempotent_and_database_constraints_prevent_duplicates(app, client):
    _register(client, "planned-entry")
    user_id, plan_id, meals = _create_plan(app, "planned-entry")
    meal_id = meals[("lunch", 3)]

    first = _outcome(client, "lunch", "consumed_planned", meal_id)
    repeated = _outcome(client, "lunch", "consumed_planned", meal_id)

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert first.get_json()["state"]["entry"]["id"] == repeated.get_json()["state"]["entry"]["id"]
    with app.app_context():
        assert DietEntry.query.filter_by(user_id=user_id).count() == 1
        state = DietMealDailyState.query.filter_by(user_id=user_id, slot_key="lunch").one()
        duplicate = DietMealDailyState(
            user_id=user_id,
            local_date=date.fromisoformat(TEST_DATE),
            slot_key="lunch",
            diet_plan_id=plan_id,
            selected_plan_meal_id=meal_id,
        )
        db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        duplicate_entry = DietEntry(
            user_id=user_id,
            date=date.fromisoformat(TEST_DATE),
            meal_type="Almoço",
            description="Duplicado",
            daily_meal_state_id=state.id,
            source="planned",
        )
        db.session.add(duplicate_entry)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_concurrent_consumed_planned_requests_create_one_entry(tmp_path):
    class ConcurrentConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'daily-concurrency.db'}"
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False, "timeout": 10}}

    concurrent_app = create_app(ConcurrentConfig)
    with concurrent_app.app_context():
        db.create_all()
    first_client = concurrent_app.test_client()
    second_client = concurrent_app.test_client()
    _register(first_client, "concurrent-diet-user")
    assert second_client.post(
        "/api/login",
        json={"username": "concurrent-diet-user", "password": "strong-password"},
    ).status_code == 200
    user_id, _, meals = _create_plan(concurrent_app, "concurrent-diet-user")
    meal_id = meals[("lunch", 1)]
    barrier = Barrier(2)

    def consume(client):
        barrier.wait()
        return _outcome(client, "lunch", "consumed_planned", meal_id).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(consume, (first_client, second_client)))

    assert statuses == [200, 201]
    with concurrent_app.app_context():
        assert DietEntry.query.filter_by(user_id=user_id).count() == 1
        assert DietMealDailyState.query.filter_by(user_id=user_id, slot_key="lunch").count() == 1
        db.session.remove()
        db.drop_all()


def test_different_skip_manual_and_legacy_entries_keep_separate_meanings(app, client):
    _register(client, "outcomes-user")
    user_id, _, meals = _create_plan(app, "outcomes-user")
    different = _outcome(
        client,
        "lunch",
        "consumed_different",
        meals[("lunch", 2)],
        {"description": "Sushi", "calories": 480, "protein": 28, "carbs": 62, "fat": 12},
    )
    repeated_different = _outcome(
        client,
        "lunch",
        "consumed_different",
        meals[("lunch", 2)],
        {"description": "Sushi", "calories": 480, "protein": 28, "carbs": 62, "fat": 12},
    )
    skipped = _outcome(client, "dinner", "skipped", meals[("dinner", 1)])
    manual = client.post("/api/diet", json={
        "date": TEST_DATE,
        "meal_type": "Café da manhã",
        "description": "Iogurte",
        "calories": 120,
        "protein": 8,
    })

    assert different.status_code == 201
    assert repeated_different.status_code == 200
    assert repeated_different.get_json()["state"]["entry"]["id"] == different.get_json()["state"]["entry"]["id"]
    assert different.get_json()["state"]["entry"]["description"] == "Sushi"
    assert skipped.status_code == 201
    assert skipped.get_json()["state"]["entry"] is None
    assert manual.status_code == 201
    view = client.get(f"/api/diet/days/{TEST_DATE}").get_json()
    assert view["totals"]["calories"] == 600
    assert len(view["manual_entries"]) == 1
    slots = {item["slot_key"]: item for item in view["slots"]}
    assert slots["lunch"]["result"] == "consumed_different"
    assert slots["dinner"]["result"] == "skipped"
    assert slots["breakfast"]["result"] == "pending"

    with app.app_context():
        historical = DietEntry(
            user_id=user_id,
            date=date(2026, 9, 6),
            meal_type="Almoço",
            description="Registro antigo",
            calories=300,
        )
        db.session.add(historical)
        db.session.commit()
        assert historical.source is None
        assert historical.daily_meal_state_id is None
    history = client.get("/api/diet?start_date=2026-09-06&end_date=2026-09-06").get_json()
    assert len(history) == 1
    assert history[0]["source"] is None
    assert history[0]["daily_meal_state_id"] is None


def test_skipped_slot_can_be_reopened_without_creating_nutrients(app, client):
    _register(client, "reopen-skipped")
    _, _, meals = _create_plan(app, "reopen-skipped")
    assert _outcome(client, "lunch", "skipped", meals[("lunch", 2)]).status_code == 201

    response = client.delete(f"/api/diet/days/{TEST_DATE}/slots/lunch/outcome")

    assert response.status_code == 200
    view = client.get(f"/api/diet/days/{TEST_DATE}").get_json()
    lunch = next(slot for slot in view["slots"] if slot["slot_key"] == "lunch")
    assert lunch["result"] == "pending"
    assert lunch["selected_plan_meal_id"] == meals[("lunch", 2)]
    assert lunch["entry"] is None
    assert view["totals"] == {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}


def test_linked_entry_can_be_corrected_and_deletion_reopens_slot(app, client):
    _register(client, "correct-linked")
    _, _, meals = _create_plan(app, "correct-linked")
    result = _outcome(client, "lunch", "consumed_planned", meals[("lunch", 1)]).get_json()
    entry = result["state"]["entry"]

    corrected = client.put(f"/api/diet/{entry['id']}", json={
        **entry,
        "description": "Almoço corrigido",
        "calories": 510,
    })
    wrong_date = client.put(f"/api/diet/{entry['id']}", json={**entry, "date": "2026-09-08"})
    wrong_type = client.put(f"/api/diet/{entry['id']}", json={**entry, "meal_type": "Jantar"})

    assert corrected.status_code == 200
    assert corrected.get_json()["entry"]["description"] == "Almoço corrigido"
    assert wrong_date.status_code == 409
    assert wrong_type.status_code == 409
    assert client.delete(f"/api/diet/{entry['id']}").status_code == 200
    view = client.get(f"/api/diet/days/{TEST_DATE}").get_json()
    lunch = next(slot for slot in view["slots"] if slot["slot_key"] == "lunch")
    assert lunch["result"] == "pending"
    assert lunch["entry"] is None
    assert view["totals"] == {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
