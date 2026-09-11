from datetime import datetime, timedelta

from src.models.user import Measurement, db
from tests.test_workout_progress import create_user, create_plan, create_session, login


def test_sessions_without_pr_missing_load_pagination_and_privacy(app, client):
    with app.app_context():
        user = create_user('performance-owner')
        plan, day, exercises = create_plan(user)
        key = exercises[0].catalog_key
        for i in range(23):
            create_session(user, plan, day, datetime(2026, 8, 1) + timedelta(days=i), [
                (exercises[0], [{'load_kg': 42 if i == 0 else 40, 'repetitions': 8},
                                {'load_kg': None, 'repetitions': 10},
                                {'load_kg': 100, 'repetitions': 5, 'is_warmup': True}]),
            ])
        no_pr = create_session(user, plan, day, datetime(2026, 8, 25), [(exercises[1], [{'load_kg': None, 'repetitions': 12}])])
        no_pr.completions[0].exercise_catalog_key = None
        fallback = f'exercise-id:{exercises[1].id}'
        db.session.add(Measurement(user_id=user.id, date=datetime(2026, 8, 1).date(), weight=70))
        db.session.commit()
    assert client.get('/api/progress/exercises').status_code == 401
    login(client, 'performance-owner')
    options = client.get('/api/progress/exercises').get_json()['items']
    assert {item['key'] for item in options} == {key, fallback}
    base = f'/api/progress/exercises/{key}?view=sessions&limit=20'
    result = client.get(base).get_json()
    assert len(result['sessions']['items']) == 20
    assert result['sessions']['has_more']
    assert result['max_load_kg'] == 42
    assert result['sessions']['items'][0]['sets'][0]['load_kg'] == 40
    assert result['sessions']['items'][0]['sets'][1]['load_kg'] is None
    assert result['sessions']['items'][0]['sets'][2]['is_warmup']
    second = client.get(base + '&offset=20').get_json()['sessions']
    assert len(second['items']) == 3
    assert not second['has_more']
    assert not {item['session_id'] for item in second['items']} & {item['session_id'] for item in result['sessions']['items']}
    sparse = client.get(f'/api/progress/exercises/{fallback}').get_json()
    assert sparse['records'] == []
    assert sparse['max_load_kg'] is None
    assert sparse['sessions']['items'][0]['sets'][0]['repetitions'] == 12
    assert len(sparse['recent_activities']) == 1
    overview = client.get('/api/progress/overview?view=summary').get_json()
    assert overview['body']['metrics']['weight']['latest']['value'] == 70
    assert overview['performance']['recent']['key'] == fallback
    assert overview['recent_personal_records'] == []
    assert overview['recent_activities'] == []
    oldest = second['items'][-1]['session_id']
    assert client.delete(f'/api/activities/{oldest}').status_code == 200
    assert client.get(base).get_json()['max_load_kg'] == 40
    with app.app_context():
        create_user('performance-other')
        db.session.commit()
    other = app.test_client()
    login(other, 'performance-other')
    assert other.get('/api/progress/exercises').get_json()['items'] == []
    assert other.get(base).status_code == 404
    assert other.get('/api/progress/overview?view=summary').get_json()['performance']['recent'] is None
