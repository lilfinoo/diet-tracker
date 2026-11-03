from datetime import datetime

from src.models.user import WorkoutSession, WorkoutSessionExerciseCompletion, Subscription, User, WorkoutDay, WorkoutPlan, db
from tests.test_workout_progress import create_plan, create_session, create_user, login


def test_repeat_last_copies_performed_sets_and_requires_complete_history(app, client):
    with app.app_context():
        user = create_user("repeat-last")
        plan, day, exercises = create_plan(user)
        create_session(user, plan, day, datetime(2026, 9, 1), [
            (exercises[0], [{"load_kg": 30, "repetitions": 8}, {"load_kg": 25, "repetitions": 10, "is_warmup": True}]),
            (exercises[1], [{"load_kg": 40, "repetitions": 12}]),
        ])
        active = WorkoutSession(user_id=user.id, workout_plan_id=plan.id, workout_day_id=day.id)
        db.session.add(active)
        db.session.commit()
        session_id = active.id
    login(client, "repeat-last")
    response = client.post(f"/api/workout_sessions/{session_id}/repeat-last")
    assert response.status_code == 200
    with app.app_context():
        completions = WorkoutSessionExerciseCompletion.query.filter_by(workout_session_id=session_id).all()
        assert len(completions) == 2
        assert [(float(s.load_kg), s.repetitions, s.is_warmup) for s in completions[0].performed_sets] == [(30, 8, False), (25, 10, True)]
    assert client.post(f"/api/workout_sessions/{session_id}/repeat-last").status_code == 409


def test_repeat_last_rejects_missing_history_without_partial_changes(app, client):
    with app.app_context():
        user = create_user("repeat-empty")
        plan, day, _ = create_plan(user)
        active = WorkoutSession(user_id=user.id, workout_plan_id=plan.id, workout_day_id=day.id)
        db.session.add(active)
        db.session.commit()
        session_id = active.id
    login(client, "repeat-empty")
    assert client.post(f"/api/workout_sessions/{session_id}/repeat-last").status_code == 409
    with app.app_context():
        assert WorkoutSessionExerciseCompletion.query.filter_by(workout_session_id=session_id).count() == 0


def test_calisthenics_is_session_only_and_uses_bodyweight(app, client):
    with app.app_context():
        user = create_user("bodyweight")
        plan, day, exercises = create_plan(user)
        originals = [item.catalog_key for item in exercises]
        active = WorkoutSession(user_id=user.id, workout_plan_id=plan.id, workout_day_id=day.id)
        db.session.add(active)
        db.session.commit()
        session_id = active.id
    login(client, "bodyweight")
    response = client.post(f"/api/workout_sessions/{session_id}/calisthenics")
    assert response.status_code == 200
    overrides = response.get_json()["session"]["overrides"]
    assert len(overrides) == 2
    assert all(item["equipment"] == "bodyweight" and item["weight"] == "Peso corporal" for item in overrides)
    assert overrides[0]["catalog_key"] == "flexao_de_bracos"
    with app.app_context():
        session = db.session.get(WorkoutSession, session_id)
        assert [item.catalog_key for item in session.day.exercises] == originals


def test_atomic_repeat_last_and_calisthenics(app, client):
    with app.app_context():
        user = create_user("atomic-actions")
        plan, day, exercises = create_plan(user)
        db.session.add(Subscription(user_id=user.id, provider="admin", external_subscription_id="atomic-actions", status="active", plan_code="premium_student"))
        db.session.commit()
        user_id, plan_id, day_id = user.id, plan.id, day.id
    login(client, "atomic-actions")
    base = f"/api/workout_plans/{plan_id}/days/{day_id}"
    assert client.get(base + "/repeat-last").get_json()["available"] is False
    assert client.post(base + "/repeat-last").status_code == 409
    with app.app_context():
        assert WorkoutSession.query.filter_by(user_id=user_id).count() == 0
        user = db.session.get(User, user_id)
        plan = db.session.get(WorkoutPlan, plan_id)
        day = db.session.get(WorkoutDay, day_id)
        create_session(user, plan, day, datetime(2026, 9, 1), [(e, [{"load_kg": 20, "repetitions": 8}]) for e in day.exercises])
        db.session.commit()
    assert client.get(base + "/repeat-last").get_json()["available"] is True
    headers = {"Idempotency-Key": "repeat-atomic"}
    first = client.post(base + "/repeat-last", headers=headers)
    assert first.status_code == 200
    assert client.post(base + "/repeat-last", headers=headers).get_json() == first.get_json()
    response = client.post(base + "/calisthenics", headers={"Idempotency-Key": "bodyweight-atomic"})
    assert response.status_code == 201
    assert all(item["equipment"] == "bodyweight" for item in response.get_json()["session"]["overrides"])
