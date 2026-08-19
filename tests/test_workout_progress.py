from datetime import datetime, timedelta

from src.models.user import (
    AchievementUnlock,
    ExerciseGoal,
    PersonalRecordEvent,
    User,
    UserProfile,
    WorkoutDay,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
    WorkoutSessionExerciseCompletion,
    WorkoutSetPerformance,
    db,
)
from src.services.achievements import evaluate_achievements
from src.services.personal_records import (
    E1RM_METRIC_KEY,
    process_session_personal_records,
)
from src.services.workout_progress import (
    create_weekly_goal,
    snapshot_session_week,
    weekly_progress,
)


def create_user(username, timezone="America/Sao_Paulo"):
    user = User(username=username)
    user.set_password("strong-password")
    db.session.add(user)
    db.session.flush()
    db.session.add(UserProfile(user_id=user.id, timezone=timezone))
    db.session.flush()
    return user


def create_plan(user, exercise_keys=("supino_reto_halteres", "remada_baixa")):
    plan = WorkoutPlan(
        user_id=user.id,
        title="Push A",
        status="published",
        source="manual",
        days_per_week=3,
    )
    db.session.add(plan)
    db.session.flush()
    day = WorkoutDay(workout_plan_id=plan.id, code="A", title="Push A", order=1)
    db.session.add(day)
    db.session.flush()
    exercises = []
    for index, key in enumerate(exercise_keys, start=1):
        exercise = WorkoutExercise(
            workout_plan_id=plan.id,
            workout_day_id=day.id,
            catalog_key=key,
            name=f"Exercício {index}",
            sets=3,
            reps="8-12",
            order=index,
        )
        db.session.add(exercise)
        exercises.append(exercise)
    db.session.flush()
    return plan, day, exercises


def create_session(user, plan, day, completed_at, performances, started_at=None):
    session = WorkoutSession(
        user_id=user.id,
        workout_plan_id=plan.id,
        workout_day_id=day.id,
        started_at=started_at or completed_at - timedelta(minutes=50),
        completed_at=completed_at,
    )
    db.session.add(session)
    db.session.flush()
    for exercise, sets in performances:
        completion = WorkoutSessionExerciseCompletion(
            workout_session_id=session.id,
            workout_exercise_id=exercise.id,
            exercise_name=exercise.name,
            exercise_catalog_key=exercise.catalog_key,
        )
        db.session.add(completion)
        db.session.flush()
        for order, values in enumerate(sets, start=1):
            db.session.add(WorkoutSetPerformance(
                completion_id=completion.id,
                set_order=order,
                load_kg=values.get("load_kg"),
                repetitions=values["repetitions"],
                is_warmup=values.get("is_warmup", False),
            ))
    db.session.flush()
    return session


def login(client, username):
    response = client.post("/api/login", json={"username": username, "password": "strong-password"})
    assert response.status_code == 200


def test_activities_are_private_and_preserve_real_session_data(app, client):
    with app.app_context():
        owner = create_user("activity-owner")
        create_user("activity-other")
        plan, day, exercises = create_plan(owner)
        completed_at = datetime(2026, 8, 18, 15, 0)
        activity = create_session(
            owner,
            plan,
            day,
            completed_at,
            [(exercises[0], [
                {"load_kg": 80, "repetitions": 8},
                {"load_kg": 82.5, "repetitions": 6},
            ])],
            started_at=completed_at - timedelta(minutes=58),
        )
        process_session_personal_records(activity, backfilled=True)
        activity_id = activity.id
        plan_id = plan.id
        db.session.commit()

    login(client, "activity-owner")
    listing = client.get("/api/activities")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.get_json()["items"]] == [activity_id]
    detail = client.get(f"/api/activities/{activity_id}")
    assert detail.status_code == 200
    payload = detail.get_json()["activity"]
    assert payload["duration_seconds"] == 58 * 60
    assert payload["exercises_performed"] == 1
    assert payload["sets_performed"] == 2
    assert payload["volume_total_kg"] == 1135
    assert payload["exercises"][0]["sets"][1]["load_kg"] == 82.5

    client.post("/api/logout")
    login(client, "activity-other")
    assert client.get(f"/api/activities/{activity_id}").status_code == 404
    assert client.get("/api/activities").get_json()["items"] == []

    client.post("/api/logout")
    login(client, "activity-owner")
    removed = client.delete(f"/api/workout_plans/{plan_id}")
    assert removed.status_code == 200
    assert client.get(f"/api/activities/{activity_id}").status_code == 200
    with app.app_context():
        assert db.session.get(WorkoutPlan, plan_id).status == "archived"


def test_pr_engine_detects_strict_progress_epley_and_warmup(app):
    with app.app_context():
        user = create_user("pr-owner")
        plan, day, exercises = create_plan(user)
        base = datetime(2026, 7, 1, 12, 0)

        first = create_session(user, plan, day, base, [(exercises[0], [
            {"load_kg": 80, "repetitions": 8},
            {"load_kg": 80, "repetitions": 10},
        ])])
        initial = process_session_personal_records(first)
        assert initial
        assert all(item.is_initial for item in initial)
        assert not any(item.is_highlighted for item in initial)

        lower = create_session(user, plan, day, base + timedelta(days=1), [(exercises[0], [
            {"load_kg": 75, "repetitions": 12},
        ])])
        lower_events = process_session_personal_records(lower)
        assert not any(item.metric_type in {"max_load", "estimated_1rm"} for item in lower_events)
        assert not any(item.is_highlighted for item in lower_events)

        reps_progress = create_session(user, plan, day, base + timedelta(days=2), [(exercises[0], [
            {"load_kg": 80, "repetitions": 12},
        ])])
        reps_events = process_session_personal_records(reps_progress)
        assert not any(item.metric_type == "max_load" for item in reps_events)
        assert any(item.metric_key == E1RM_METRIC_KEY for item in reps_events)
        assert any(item.metric_type == "reps_at_load" for item in reps_events)
        assert sum(item.is_highlighted for item in reps_events) == 1

        load_progress = create_session(user, plan, day, base + timedelta(days=3), [(exercises[0], [
            {"load_kg": 100, "repetitions": 1, "is_warmup": True},
            {"load_kg": 90, "repetitions": 5},
        ])])
        load_events = process_session_personal_records(load_progress)
        max_load = next(item for item in load_events if item.metric_type == "max_load")
        assert float(max_load.new_value) == 90
        assert max_load.is_highlighted

        other_exercise = create_session(user, plan, day, base + timedelta(days=4), [(exercises[1], [
            {"load_kg": 30, "repetitions": 10},
        ])])
        other_events = process_session_personal_records(other_exercise)
        assert all(item.exercise_key == exercises[1].catalog_key for item in other_events)

        before = PersonalRecordEvent.query.count()
        process_session_personal_records(load_progress)
        assert PersonalRecordEvent.query.count() == before
        db.session.commit()


def test_pr_histories_are_independent_between_users(app):
    with app.app_context():
        first_user = create_user("pr-first")
        second_user = create_user("pr-second")
        first_plan, first_day, first_exercises = create_plan(first_user, ("supino_reto_halteres",))
        second_plan, second_day, second_exercises = create_plan(second_user, ("supino_reto_halteres",))
        when = datetime(2026, 7, 10, 12, 0)
        first_session = create_session(first_user, first_plan, first_day, when, [(first_exercises[0], [
            {"load_kg": 100, "repetitions": 5},
        ])])
        second_session = create_session(second_user, second_plan, second_day, when, [(second_exercises[0], [
            {"load_kg": 40, "repetitions": 5},
        ])])
        first_events = process_session_personal_records(first_session)
        second_events = process_session_personal_records(second_session)
        assert all(item.is_initial for item in first_events)
        assert all(item.is_initial for item in second_events)
        assert {float(item.new_value) for item in second_events if item.metric_type == "max_load"} == {40}


def test_weekly_goal_and_streak_use_completed_qualifying_sessions(app):
    with app.app_context():
        user = create_user("weekly-owner", "UTC")
        plan, day, exercises = create_plan(user)
        start = datetime(2026, 6, 1, 12, 0)
        create_weekly_goal(user.id, 2, "UTC", effective_week_start=start.date())
        for week in range(4):
            for offset in (0, 3):
                session = create_session(
                    user,
                    plan,
                    day,
                    start + timedelta(weeks=week, days=offset),
                    [(exercises[0], [{"load_kg": 50 + week, "repetitions": 8}])],
                )
                snapshot_session_week(session, timezone="UTC")
        empty = WorkoutSession(
            user_id=user.id,
            workout_plan_id=plan.id,
            workout_day_id=day.id,
            started_at=start + timedelta(weeks=4),
            completed_at=start + timedelta(weeks=4, minutes=10),
        )
        db.session.add(empty)
        db.session.flush()
        progress = weekly_progress(user.id, now=start + timedelta(weeks=3, days=4))
        assert progress["current"]["completed"] == 2
        assert progress["current"]["streak"] == 4

        progress_next_week = weekly_progress(user.id, now=start + timedelta(weeks=4, days=4))
        assert progress_next_week["current"]["completed"] == 0
        assert progress_next_week["current"]["streak"] == 4

        progress_after_failure = weekly_progress(user.id, now=start + timedelta(weeks=5, days=4))
        assert progress_after_failure["current"]["streak"] == 0


def test_exercise_goal_and_achievements_are_idempotent(app, client):
    with app.app_context():
        user = create_user("goal-owner", "UTC")
        plan, day, exercises = create_plan(user, ("supino_reto_halteres",))
        baseline = create_session(user, plan, day, datetime(2026, 8, 1, 12), [(exercises[0], [
            {"load_kg": 80, "repetitions": 8},
        ])])
        process_session_personal_records(baseline, backfilled=True)
        evaluate_achievements(user.id, backfilled=True)
        active = WorkoutSession(
            user_id=user.id,
            workout_plan_id=plan.id,
            workout_day_id=day.id,
            started_at=datetime.utcnow() - timedelta(minutes=45),
        )
        db.session.add(active)
        db.session.flush()
        completion = WorkoutSessionExerciseCompletion(
            workout_session_id=active.id,
            workout_exercise_id=exercises[0].id,
            exercise_name=exercises[0].name,
            exercise_catalog_key=exercises[0].catalog_key,
        )
        db.session.add(completion)
        db.session.flush()
        db.session.add(WorkoutSetPerformance(
            completion_id=completion.id,
            set_order=1,
            load_kg=90,
            repetitions=6,
            is_warmup=False,
        ))
        goal = ExerciseGoal(
            user_id=user.id,
            exercise_key=exercises[0].catalog_key,
            exercise_name=exercises[0].name,
            target_load_kg=90,
        )
        db.session.add(goal)
        db.session.commit()
        session_id = active.id

    login(client, "goal-owner")
    first = client.post(f"/api/workout_sessions/{session_id}/finish")
    assert first.status_code == 200
    assert first.get_json()["exercise_goals_reached"]
    assert first.get_json()["summary"]["personal_records"]
    second = client.post(f"/api/workout_sessions/{session_id}/finish")
    assert second.status_code == 200
    assert second.get_json()["exercise_goals_reached"] == []
    assert second.get_json()["achievements_unlocked"] == []
    with app.app_context():
        assert ExerciseGoal.query.one().status == "achieved"
        codes = [item.achievement_code for item in AchievementUnlock.query.all()]
        assert len(codes) == len(set(codes))
        assert "first_pr" in codes
        assert "first_goal" in codes
