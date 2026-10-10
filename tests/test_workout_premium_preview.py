from datetime import datetime, timedelta

import pytest

from src.models.user import DietPlan, Subscription, User, UserProfile, WorkoutPlan, WorkoutSession, db
from tests.helpers import registration_payload
from tests.test_guided_plans import generated_workout, workout_questionnaire
from tests.test_workout_progress import create_plan, create_session, create_user, login


def test_free_generation_is_readable_preview_without_activation(app, client, monkeypatch):
    monkeypatch.setattr("src.routes.plan_routes.generate_workout_plan", lambda *args: generated_workout())
    assert client.post("/api/register", json=registration_payload("preview-free")).status_code == 201
    result = client.post("/api/workout_plans/generate", json=workout_questionnaire())
    assert result.status_code == 201
    plan = result.get_json()["plan"]
    assert client.get(f"/api/workout_plans/{plan['id']}").status_code == 200
    assert client.get("/api/workout_plans").get_json()[0]["is_current"] is False
    usage = client.get("/api/ai/usage").get_json()
    assert usage["plans"] == {"used": 1, "limit": 1, "remaining": 0}
    # The same lifetime slot is shared with diet generation; no second AI call.
    assert client.post("/api/diet_plans/generate", json={}).status_code == 403
    with app.app_context():
        user = User.query.filter_by(username="preview-free").one()
        profile = UserProfile.query.filter_by(user_id=user.id).first()
        assert profile is None or profile.current_workout_plan_id is None
        assert WorkoutSession.query.count() == 0


@pytest.mark.parametrize("action", ["activate", "adapt", "start"])
def test_free_cannot_apply_or_start_preview_without_changing_data(app, client, action):
    with app.app_context():
        user = create_user("blocked-preview")
        plan, day, _ = create_plan(user)
        plan_id, day_id = plan.id, day.id
        db.session.commit()
    login(client, "blocked-preview")
    if action == "activate":
        result = client.put(f"/api/workout_plans/{plan_id}/current", json={"weekdays": [0]})
    elif action == "adapt":
        result = client.post(f"/api/workout_plans/{plan_id}/current/adapt", json={"weekdays": [0, 2]})
    else:
        result = client.post(f"/api/workout_plans/{plan_id}/days/{day_id}/sessions")
    assert result.status_code == 403
    assert result.get_json()["code"] == "premium_required"
    assert "treino" in result.get_json()["error"]
    with app.app_context():
        assert WorkoutPlan.query.count() == 1
        assert db.session.get(WorkoutPlan, plan_id).status == "published"
        assert UserProfile.query.one().current_workout_plan_id is None
        assert WorkoutSession.query.count() == 0
        assert User.query.one().free_plan_uses == 0


def test_subscription_upgrade_unlocks_same_preview_and_preserves_ownership(app, client):
    with app.app_context():
        user = create_user("upgraded-preview")
        other = create_user("other-preview")
        plan, day, _ = create_plan(user)
        other_plan, other_day, _ = create_plan(other)
        plan_id, day_id = plan.id, day.id
        other_plan_id, other_day_id = other_plan.id, other_day.id
        db.session.add(Subscription(
            user_id=user.id, provider="admin", external_subscription_id="preview-upgrade",
            status="active", plan_code="premium_student",
        ))
        db.session.commit()
    login(client, "upgraded-preview")
    assert client.put(f"/api/workout_plans/{other_plan_id}/current", json={"weekdays": [0]}).status_code == 404
    assert client.post(f"/api/workout_plans/{other_plan_id}/days/{other_day_id}/sessions").status_code == 404
    assert client.put(f"/api/workout_plans/{plan_id}/current", json={"weekdays": [0]}).status_code == 200
    result = client.post(f"/api/workout_plans/{plan_id}/days/{day_id}/sessions")
    assert result.status_code == 201
    assert client.post(f"/api/workout_plans/{plan_id}/days/{day_id}/sessions").get_json() == result.get_json()
    assert client.get("/api/ai/usage").get_json()["plans"]["used"] == 0


def test_expired_subscription_does_not_unlock_workout(app, client):
    with app.app_context():
        user = create_user("expired-preview")
        plan, day, _ = create_plan(user)
        plan_id, day_id = plan.id, day.id
        db.session.add(Subscription(
            user_id=user.id, provider="admin", external_subscription_id="preview-expired",
            status="active", plan_code="premium_student", current_period_end=datetime.utcnow() - timedelta(days=1),
        ))
        db.session.commit()
    login(client, "expired-preview")
    assert client.post(f"/api/workout_plans/{plan_id}/days/{day_id}/sessions").status_code == 403


def test_free_diet_activation_and_workout_history_remain_available(app, client):
    with app.app_context():
        user = create_user("preserved-preview")
        plan, day, exercises = create_plan(user)
        historical = create_session(user, plan, day, datetime(2026, 10, 8, 15), [(exercises[0], [{"load_kg": 20, "repetitions": 8}])])
        diet = DietPlan(user_id=user.id, title="Dieta", status="published")
        db.session.add(diet)
        db.session.flush()
        diet_id, activity_id = diet.id, historical.id
        db.session.commit()
    login(client, "preserved-preview")
    assert client.put(f"/api/diet_plans/{diet_id}/current").status_code == 200
    history = client.get(f"/api/activities/{activity_id}")
    assert history.status_code == 200
    assert history.get_json()["activity"]["exercises"][0]["sets"][0]["load_kg"] == 20
    manual = client.post("/api/diet", json={"date": "2026-10-10", "meal_type": "Almoço", "description": "Banana", "calories": 100})
    assert manual.status_code == 201


def test_workout_premium_guard_keeps_login_and_csrf_protection(app, client):
    with app.app_context():
        user = create_user("protected-preview")
        user.is_premium = True
        plan, day, _ = create_plan(user)
        plan_id, day_id = plan.id, day.id
        db.session.commit()
    path = f"/api/workout_plans/{plan_id}/days/{day_id}/sessions"
    assert client.post(path).status_code == 401
    login(client, "protected-preview")
    app.config["CSRF_PROTECTION"] = True
    assert client.post(path).status_code == 403
    with client.session_transaction() as session:
        token = session["csrf_token"]
    assert client.post(path, headers={"X-CSRF-Token": token}).status_code == 201


def test_already_started_session_can_finish_after_subscription_expires(app, client):
    with app.app_context():
        user = create_user("pending-preview")
        plan, day, exercises = create_plan(user)
        active = WorkoutSession(user_id=user.id, workout_plan_id=plan.id, workout_day_id=day.id)
        db.session.add(active)
        db.session.flush()
        session_id, exercise_id = active.id, exercises[0].id
        db.session.commit()
    login(client, "pending-preview")
    assert client.get("/api/workout_sessions/active").get_json()["session"]["id"] == session_id
    saved = client.post(f"/api/workout_sessions/{session_id}/exercises/{exercise_id}/complete", json={
        "sets": [{"load_kg": 20, "repetitions": 8}],
    })
    assert saved.status_code == 200
    assert client.post(f"/api/workout_sessions/{session_id}/finish").status_code == 200
    assert client.get(f"/api/activities/{session_id}").status_code == 200
