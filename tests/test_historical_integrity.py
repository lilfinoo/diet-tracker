from datetime import datetime, timedelta

from src.models.user import AchievementUnlock, ExerciseGoal, PersonalRecordEvent, ProfileHighlight, db
from src.services.achievements import evaluate_achievements
from src.services.personal_records import current_max_load, process_session_personal_records
from tests.test_core_user_flows import register
from tests.test_workout_progress import create_user, create_plan, create_session, login


def test_old_measurement_does_not_override_current_body_values(client):
    register(client, 'body-history')
    client.post('/api/profile', json={'weight': 80, 'height': 180})
    old = client.post('/api/measurements', json={'date': '2026-01-01', 'weight': 79, 'height': 179}).get_json()['measurement']
    newest = client.post('/api/measurements', json={'date': '2026-02-01', 'weight': 75}).get_json()['measurement']
    client.put(f"/api/measurements/{old['id']}", json={'weight': 78, 'height': 178})
    profile = client.get('/api/profile').get_json()['profile']
    assert (profile['weight'], profile['height']) == (75, 178)
    client.delete(f"/api/measurements/{newest['id']}")
    assert client.get('/api/profile').get_json()['profile']['weight'] == 78
    client.delete(f"/api/measurements/{old['id']}")
    profile = client.get('/api/profile').get_json()['profile']
    assert (profile['weight'], profile['height']) == (80, 180)


def _history(app, loads):
    with app.app_context():
        user = create_user('history-owner')
        plan, day, exercises = create_plan(user)
        ids = []
        for index, load in enumerate(loads):
            session = create_session(user, plan, day, datetime(2026, 1, 2) + timedelta(days=index), [
                (exercises[0], [{'load_kg': load, 'repetitions': 5}]),
                (exercises[1], [{'load_kg': 20 + index, 'repetitions': 5}]),
            ])
            process_session_personal_records(session)
            ids.append(session.id)
        evaluate_achievements(user.id)
        db.session.commit()
        return user.id, exercises[0].catalog_key, exercises[1].catalog_key, ids


def test_delete_record_holder_promotes_remaining_result_and_preserves_other_records(app, client):
    user_id, key, other_key, sessions = _history(app, [100, 90, 95])
    with app.app_context():
        unaffected = [(r.id, r.new_value) for r in PersonalRecordEvent.query.filter_by(user_id=user_id, exercise_key=other_key).filter(PersonalRecordEvent.workout_session_id != sessions[0]).all()]
    login(client, 'history-owner')
    assert client.delete(f'/api/activities/{sessions[0]}').status_code == 200
    with app.app_context():
        assert current_max_load(user_id, key) == 95
        events = PersonalRecordEvent.query.filter_by(user_id=user_id, exercise_key=key, metric_type='max_load').order_by(PersonalRecordEvent.achieved_at).all()
        assert [(r.new_value, r.previous_value) for r in events] == [(90, None), (95, 90)]
        assert [(r.id, r.new_value) for r in PersonalRecordEvent.query.filter_by(user_id=user_id, exercise_key=other_key).order_by(PersonalRecordEvent.achieved_at).all()] == unaffected


def test_delete_middle_record_repairs_previous_values_preserving_valid_ids_and_pins(app, client):
    user_id, key, _, sessions = _history(app, [80, 100, 110])
    with app.app_context():
        record = PersonalRecordEvent.query.filter_by(workout_session_id=sessions[2], exercise_key=key, metric_type='max_load').one()
        record_id = record.id
        db.session.add(ProfileHighlight(user_id=user_id, position=1, target_kind='personal_record', personal_record_event_id=record_id))
        db.session.commit()
    login(client, 'history-owner')
    assert client.delete(f'/api/activities/{sessions[1]}').status_code == 200
    with app.app_context():
        record = db.session.get(PersonalRecordEvent, record_id)
        assert record.previous_value == 80
        assert record.previous_load_kg == 80
        assert ProfileHighlight.query.one().personal_record_event_id == record_id
    assert client.get('/api/progress/exercises/' + key).status_code == 200
    with app.app_context():
        assert db.session.get(PersonalRecordEvent, record_id).previous_value == 80


def test_deletion_reconciles_goals_and_achievements_and_removes_invalid_pins(app, client):
    user_id, key, _, sessions = _history(app, [100])
    with app.app_context():
        goal = ExerciseGoal(user_id=user_id, exercise_key=key, exercise_name='Supino', target_load_kg=100,
                            created_at=datetime(2026, 1, 1), status='achieved', achieved_at=datetime(2026, 1, 2), achieved_session_id=sessions[0])
        db.session.add(goal)
        db.session.flush()
        goal_id = goal.id
        evaluate_achievements(user_id)
        unlock = AchievementUnlock.query.filter_by(user_id=user_id, achievement_code='first_step').one()
        db.session.add(ProfileHighlight(user_id=user_id, position=1, target_kind='achievement', achievement_unlock_id=unlock.id))
        db.session.commit()
    login(client, 'history-owner')
    assert client.delete(f'/api/activities/{sessions[0]}').status_code == 200
    with app.app_context():
        goal = db.session.get(ExerciseGoal, goal_id)
        assert goal.status == 'active'
        assert goal.achieved_at is None and goal.achieved_session_id is None
        assert AchievementUnlock.query.filter_by(user_id=user_id).count() == 0
        assert ProfileHighlight.query.filter_by(user_id=user_id).count() == 0


def test_profile_edit_adds_a_current_measurement_without_changing_legacy_fallback(client):
    register(client, 'profile-body-edit')
    client.post('/api/profile', json={'weight': 80, 'height': 180})
    client.post('/api/measurements', json={'date': '2026-01-01', 'weight': 75})
    assert client.post('/api/profile', json={'weight': 74, 'height': 180}).status_code == 200
    rows = client.get('/api/measurements').get_json()
    assert len(rows) == 2 and rows[0]['weight'] == 74
    assert rows[1]['weight'] == 75
    # Re-saving an unchanged profile must not create duplicates.
    client.post('/api/profile', json={'weight': 74, 'height': 180})
    assert len(client.get('/api/measurements').get_json()) == 2
    for row in rows:
        client.delete(f"/api/measurements/{row['id']}")
    assert client.get('/api/profile').get_json()['profile']['weight'] == 80


def test_goal_uses_remaining_sets_even_without_a_new_pr_and_keeps_valid_achievement(app, client):
    user_id, key, _, sessions = _history(app, [100, 100])
    with app.app_context():
        goal = ExerciseGoal(user_id=user_id, exercise_key=key, exercise_name='Supino', target_load_kg=100,
                            created_at=datetime(2026, 1, 1), status='achieved', achieved_at=datetime(2026, 1, 2), achieved_session_id=sessions[0])
        db.session.add(goal)
        db.session.flush()
        goal_id = goal.id
        evaluate_achievements(user_id)
        unlock_id = AchievementUnlock.query.filter_by(user_id=user_id, achievement_code='first_goal').one().id
        db.session.commit()
    login(client, 'history-owner')
    assert client.delete(f'/api/activities/{sessions[0]}').status_code == 200
    with app.app_context():
        goal = db.session.get(ExerciseGoal, goal_id)
        assert goal.status == 'achieved' and goal.achieved_session_id == sessions[1]
        unlock = db.session.get(AchievementUnlock, unlock_id)
        assert unlock.workout_session_id == sessions[1]
        assert unlock.unlocked_at == datetime(2026, 1, 3)


def test_invalidated_old_goal_does_not_displace_new_active_goal(app, client):
    user_id, key, _, sessions = _history(app, [100])
    with app.app_context():
        old = ExerciseGoal(user_id=user_id, exercise_key=key, exercise_name='Supino', target_load_kg=100,
                           created_at=datetime(2026, 1, 1), status='achieved', achieved_at=datetime(2026, 1, 2), achieved_session_id=sessions[0])
        active = ExerciseGoal(user_id=user_id, exercise_key=key, exercise_name='Supino', target_load_kg=110,
                              created_at=datetime(2026, 1, 3), status='active')
        db.session.add_all([old, active])
        db.session.commit()
        old_id, active_id = old.id, active.id
    login(client, 'history-owner')
    assert client.delete(f'/api/activities/{sessions[0]}').status_code == 200
    with app.app_context():
        assert db.session.get(ExerciseGoal, old_id).status == 'cancelled'
        assert db.session.get(ExerciseGoal, active_id).status == 'active'


def test_rebuilt_metrics_match_clean_history_and_do_not_touch_another_user(app, client):
    user_id, key, _, sessions = _history(app, [100, 90, 95])
    with app.app_context():
        control = create_user('control-history')
        plan, day, exercises = create_plan(control)
        for index, load in enumerate([90, 95]):
            session = create_session(control, plan, day, datetime(2026, 1, 3) + timedelta(days=index), [
                (exercises[0], [{'load_kg': load, 'repetitions': 5}]),
            ])
            process_session_personal_records(session)
        db.session.commit()
        control_id = control.id
        control_ids = [r.id for r in PersonalRecordEvent.query.filter_by(user_id=control_id).all()]
    login(client, 'history-owner')
    assert client.delete(f'/api/activities/{sessions[0]}').status_code == 200
    with app.app_context():
        def metrics(owner):
            rows = PersonalRecordEvent.query.filter_by(user_id=owner, exercise_key=key).order_by(PersonalRecordEvent.achieved_at, PersonalRecordEvent.metric_key).all()
            return [(r.metric_key, r.new_value, r.previous_value, r.previous_load_kg, r.previous_repetitions, r.is_initial, r.is_highlighted) for r in rows]
        assert metrics(user_id) == metrics(control_id)
        assert [r.id for r in PersonalRecordEvent.query.filter_by(user_id=control_id).all()] == control_ids


def test_failed_reconciliation_rolls_back_the_entire_deletion(app, client, monkeypatch):
    import pytest
    from src.models.user import WorkoutSession

    user_id, key, _, sessions = _history(app, [100, 90])
    login(client, 'history-owner')

    def fail(*args):
        raise RuntimeError('reconciliation failed')

    monkeypatch.setattr('src.routes.session_routes.rebuild_personal_records', fail)
    with pytest.raises(RuntimeError, match='reconciliation failed'):
        client.delete(f'/api/activities/{sessions[0]}')
    with app.app_context():
        assert db.session.get(WorkoutSession, sessions[0]) is not None
        assert current_max_load(user_id, key) == 100
