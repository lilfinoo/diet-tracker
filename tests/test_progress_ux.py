from datetime import datetime, timedelta

from src.models.user import ExerciseGoal, db
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
