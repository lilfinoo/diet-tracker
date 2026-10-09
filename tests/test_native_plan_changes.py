from datetime import datetime

from src.models.user import WorkoutExercise, WorkoutPlan, db
from src.routes.workout_routes import _workout_plan_revision
from tests.test_workout_progress import create_plan, create_session, create_user, login


def test_confirmed_plan_changes_preserve_historical_exercises(app, client):
    with app.app_context():
        user = create_user("plan-change-owner")
        plan, day, exercises = create_plan(user, ("supino_reto_halteres",))
        create_session(user, plan, day, datetime(2026, 10, 8, 15), [(exercises[0], [{"load_kg": 40, "repetitions": 10}])])
        plan_id, exercise_id = plan.id, exercises[0].id
        revision = _workout_plan_revision(plan)
        db.session.commit()
    login(client, "plan-change-owner")
    response = client.post(f"/api/workout_plans/{plan_id}/apply_changes", json={"revision": revision, "changes": [{
        "exercise_id": exercise_id, "catalog_key": "supino_reto_halteres", "sets": 4, "reps": "6-8", "rest_seconds": 90,
    }]})
    assert response.status_code == 200
    assert response.get_json()["plan"]["id"] != plan_id
    with app.app_context():
        assert db.session.get(WorkoutExercise, exercise_id).sets == 3
        replacement = db.session.get(WorkoutPlan, response.get_json()["plan"]["id"])
        assert replacement.days[0].exercises[0].sets == 4


def test_invalid_batch_is_atomic(app, client):
    with app.app_context():
        user = create_user("atomic-plan-owner")
        plan, _, exercises = create_plan(user, ("supino_reto_halteres",))
        plan_id, exercise_id = plan.id, exercises[0].id
        revision = _workout_plan_revision(plan)
        db.session.commit()
    login(client, "atomic-plan-owner")
    response = client.post(f"/api/workout_plans/{plan_id}/apply_changes", json={"revision": revision, "changes": [
        {"exercise_id": exercise_id, "catalog_key": "supino_reto_halteres", "sets": 4, "reps": "6-8", "rest_seconds": 90},
        {"exercise_id": 999999, "catalog_key": "supino_reto_halteres", "sets": 4, "reps": "6-8", "rest_seconds": 90},
    ]})
    assert response.status_code == 400
    with app.app_context():
        assert db.session.get(WorkoutExercise, exercise_id).sets == 3


def test_cannot_edit_another_users_plan(app, client):
    with app.app_context():
        owner = create_user("private-plan-owner")
        create_user("other-plan-user")
        plan, _, exercises = create_plan(owner, ("supino_reto_halteres",))
        plan_id, exercise_id = plan.id, exercises[0].id
        revision = _workout_plan_revision(plan)
        db.session.commit()
    login(client, "other-plan-user")
    response = client.post(f"/api/workout_plans/{plan_id}/apply_changes", json={"revision": revision, "changes": [{
        "exercise_id": exercise_id, "catalog_key": "supino_reto_halteres", "sets": 4, "reps": "6-8", "rest_seconds": 90,
    }]})
    assert response.status_code == 404


def test_ai_proposal_requires_separate_confirmation(app, client, monkeypatch):
    from src.legal import AI_CONSENT_VERSION
    with app.app_context():
        user = create_user("draft-plan-owner")
        user.ai_consent_at = datetime.utcnow()
        user.ai_consent_version = AI_CONSENT_VERSION
        plan, _, exercises = create_plan(user, ("supino_reto_halteres",))
        plan_id, exercise_id = plan.id, exercises[0].id
        revision = _workout_plan_revision(plan)
        db.session.commit()
    monkeypatch.setattr("src.routes.workout_routes.suggest_workout_changes", lambda *args: {"changes": [{
        "exercise_id": exercise_id, "catalog_key": "supino_reto_halteres", "sets": 4, "reps": "6-8", "rest_seconds": 90,
    }]})
    login(client, "draft-plan-owner")
    response = client.post(f"/api/workout_plans/{plan_id}/suggest_changes", json={"feedback": "Quero quatro séries."})
    assert response.status_code == 200
    assert response.get_json()["changes"][0]["sets"] == 4
    assert response.get_json()["revision"] == revision
    assert response.get_json()["plan"]["days"][0]["exercises"][0]["sets"] == 3
    with app.app_context():
        assert db.session.get(WorkoutExercise, exercise_id).sets == 3
        assert WorkoutPlan.query.count() == 1


def test_stale_proposal_cannot_overwrite_plan(app, client):
    with app.app_context():
        user = create_user("stale-plan-owner")
        plan, _, exercises = create_plan(user, ("supino_reto_halteres",))
        plan_id, exercise_id = plan.id, exercises[0].id
        revision = _workout_plan_revision(plan)
        exercises[0].sets = 5
        db.session.commit()
    login(client, "stale-plan-owner")
    response = client.post(f"/api/workout_plans/{plan_id}/apply_changes", json={"revision": revision, "changes": [{
        "exercise_id": exercise_id, "catalog_key": "supino_reto_halteres", "sets": 4, "reps": "6-8", "rest_seconds": 90,
    }]})
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(WorkoutExercise, exercise_id).sets == 5


def test_ai_proposal_requires_consent_before_call(app, client, monkeypatch):
    with app.app_context():
        user = create_user("no-consent-plan-owner")
        plan, _, _ = create_plan(user, ("supino_reto_halteres",))
        plan_id = plan.id
        db.session.commit()
    def forbidden_call(*args):
        raise AssertionError("AI must not be called without consent")
    monkeypatch.setattr("src.routes.workout_routes.suggest_workout_changes", forbidden_call)
    login(client, "no-consent-plan-owner")
    response = client.post(f"/api/workout_plans/{plan_id}/suggest_changes", json={"feedback": "Quero quatro séries."})
    assert response.status_code == 403


def test_ai_proposal_cannot_modify_another_day(app, client, monkeypatch):
    from src.legal import AI_CONSENT_VERSION
    from src.models.user import WorkoutDay
    with app.app_context():
        user = create_user("scope-plan-owner")
        user.ai_consent_at = datetime.utcnow()
        user.ai_consent_version = AI_CONSENT_VERSION
        plan, day, exercises = create_plan(user)
        other_day = WorkoutDay(workout_plan_id=plan.id, code="B", title="Treino B", order=2)
        db.session.add(other_day)
        db.session.flush()
        exercises[1].workout_day_id = other_day.id
        plan_id, exercise_id, day_id = plan.id, exercises[1].id, day.id
        db.session.commit()
    monkeypatch.setattr("src.routes.workout_routes.suggest_workout_changes", lambda *args: {"changes": [{
        "exercise_id": exercise_id, "catalog_key": "remada_baixa", "sets": 4, "reps": "6-8", "rest_seconds": 90,
    }]})
    login(client, "scope-plan-owner")
    response = client.post(f"/api/workout_plans/{plan_id}/suggest_changes", json={"day_id": day_id, "feedback": "Quero quatro séries."})
    assert response.status_code == 400
    with app.app_context():
        assert db.session.get(WorkoutExercise, exercise_id).sets == 3
