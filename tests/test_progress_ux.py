from datetime import datetime, timedelta

from src.models.user import ExerciseGoal, PersonalRecordEvent, db
from src.services.personal_records import process_session_personal_records
from src.services.workout_progress import create_weekly_goal, weekly_progress
from tests.test_workout_progress import create_user, login


def test_scheduled_goal_is_reported_without_changing_current_target(app):
    with app.app_context():
        user = create_user('scheduled-ux')
        now = datetime(2026, 9, 9, 15)
        current = create_weekly_goal(user.id, 3, 'America/Sao_Paulo', now=now)
        next_week = current.effective_week_start + timedelta(days=7)
        create_weekly_goal(user.id, 5, 'America/Sao_Paulo', effective_week_start=next_week)
        result = weekly_progress(user.id, now=now)
        assert result['current']['target'] == 3
        assert result['scheduled_goal']['target_sessions'] == 5
        assert result['scheduled_goal']['effective_week_start'] == next_week.isoformat()
        advanced = weekly_progress(user.id, now=now + timedelta(days=7))
        assert advanced['current']['target'] == 5
        assert advanced['scheduled_goal'] is None


def test_cancel_goal_preserves_history_and_does_not_allow_other_user(app, client):
    with app.app_context():
        user = create_user('cancel-ux')
        create_user('other-cancel-ux')
        goal = ExerciseGoal(user_id=user.id, exercise_key='supino_reto_halteres', exercise_name='Supino', target_load_kg=47.5)
        db.session.add(goal)
        db.session.commit()
        goal_id = goal.id
    login(client, 'other-cancel-ux')
    assert client.delete(f'/api/progress/exercise-goals/{goal_id}').status_code == 404
    client.post('/api/logout')
    login(client, 'cancel-ux')
    assert client.delete(f'/api/progress/exercise-goals/{goal_id}').status_code == 200
    result = client.get('/api/progress/exercise-goals').get_json()
    assert result['active'] is None
    assert result['items'][0]['status'] == 'cancelled'
    assert result['items'][0]['target_load_kg'] == 47.5


def test_personal_record_search_filters_before_pagination(app, client, monkeypatch):
    from tests.test_workout_progress import create_plan, create_session

    monkeypatch.setattr('src.routes.progress_routes._ensure_user_workout_history', lambda _: None)
    with app.app_context():
        owner = create_user('pr-search-owner')
        other = create_user('pr-search-other')
        plan, day, exercises = create_plan(owner)
        other_plan, other_day, other_exercises = create_plan(other)
        for index, exercise in enumerate((exercises[0], exercises[1], exercises[0]), start=1):
            session = create_session(owner, plan, day, datetime(2026, 9, index, 12),
                                     [(exercise, [{'load_kg': 30 + index, 'repetitions': 8}])])
            process_session_personal_records(session, backfilled=True)
        other_session = create_session(other, other_plan, other_day, datetime(2026, 9, 4, 12),
                                       [(other_exercises[0], [{'load_kg': 90, 'repetitions': 8}])])
        process_session_personal_records(other_session, backfilled=True)
        for record in PersonalRecordEvent.query.filter_by(user_id=owner.id).all():
            record.exercise_name = 'Supino' if record.exercise_key == exercises[0].catalog_key else 'Remada'
            record.is_highlighted = True
        db.session.commit()
        expected = [record.id for record in PersonalRecordEvent.query.filter_by(
            user_id=owner.id, exercise_name='Supino', is_highlighted=True
        ).order_by(PersonalRecordEvent.achieved_at.desc(), PersonalRecordEvent.id.desc()).all()]

    assert len(expected) >= 2
    login(client, 'pr-search-owner')
    page = client.get('/api/progress/personal-records?search=SUP&limit=1&offset=1').get_json()
    assert [record['id'] for record in page['items']] == expected[1:2]
    assert page['limit'] == 1
    assert page['offset'] == 1
    assert client.get('/api/progress/personal-records?search=%25').get_json()['items'] == []
