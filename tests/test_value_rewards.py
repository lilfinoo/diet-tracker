from datetime import datetime, timedelta

import pytest

from src.models.user import GamificationAward, GamificationProfile, User, UserProfile, db
from src.services import gamification
from tests.test_water import signup


@pytest.fixture
def owner(app):
    with app.app_context():
        user = User(username='reward-owner', email='reward@example.com')
        user.set_password('strong-password')
        db.session.add(user)
        db.session.flush()
        db.session.add(UserProfile(user_id=user.id, timezone='UTC'))
        db.session.commit()
        return user.id


def test_meals_share_daily_cap_and_retries_survive_new_session(app, owner):
    with app.app_context():
        today = datetime.utcnow().date()
        assert gamification.record_meal_xp(owner, today, 'breakfast', planned_meals=4) == 25
        db.session.commit()
        db.session.remove()
        assert gamification.record_meal_xp(owner, today, 'breakfast', planned_meals=4) == 0
        assert gamification.record_meal_xp(owner, today, 'analysis', planned_meals=4, analysis=True) == 75
        assert gamification.record_meal_xp(owner, today, 'dinner', planned_meals=4) == 0
        assert gamification.gamification_summary(owner)['total_xp'] == 100
        assert gamification.record_meal_xp(owner, today - timedelta(days=1), 'old') == 0
        assert GamificationAward.query.count() == 3


def test_water_entries_cap_at_40_and_do_not_double_activate_day(app, owner):
    with app.app_context():
        today = datetime.utcnow().date()
        assert [gamification.record_water_xp(owner, today, str(i)) for i in range(4)] == [30, 10, 0, 0]
        assert gamification.record_water_xp(owner, today, '0') == 0
        gamification.record_meal_xp(owner, today, 'meal')
        assert GamificationProfile.query.one().active_days == 1


def test_generation_monthly_limits_are_independent_and_sources_never_repeat(app, owner):
    with app.app_context():
        assert gamification.award_plan_generation(owner, 'diet', 'diet:1') == 500
        assert gamification.award_plan_generation(owner, 'diet', 'diet:2') == 0
        assert gamification.award_plan_generation(owner, 'workout', 'workout:1') == 500
        profile = GamificationProfile.query.one()
        profile.last_diet_plan_xp_at = datetime.utcnow() - timedelta(days=31)
        assert gamification.award_plan_generation(owner, 'diet', 'diet:1') == 0
        assert gamification.award_plan_generation(owner, 'diet', 'diet:2') == 500
        assert gamification.gamification_summary(owner)['total_xp'] == 1500
        assert profile.active_days == 1


def test_rest_checkin_only_on_confirmed_rest_and_once_per_day(app, client, monkeypatch):
    signup(client)
    monkeypatch.setattr('src.routes.workout_routes._workout_today_payload', lambda _: {'state': 'ready'})
    assert client.post('/api/workouts/rest-checkin').status_code == 409
    monkeypatch.setattr('src.routes.workout_routes._workout_today_payload', lambda _: {'state': 'rest'})
    first = client.post('/api/workouts/rest-checkin')
    assert first.status_code == 200
    assert first.json['xp_gained'] == 100
    assert first.json['gamification']['total_xp'] == 100
    assert client.post('/api/workouts/rest-checkin').json['xp_gained'] == 0


@pytest.mark.parametrize('meals,expected', [(3, 33), (4, 25), (5, 20)])
def test_analysis_gives_more_than_planned_meal(app, owner, meals, expected):
    with app.app_context():
        today = datetime.utcnow().date()
        assert gamification.record_meal_xp(owner, today, 'planned', planned_meals=meals) == expected
        assert gamification.record_meal_xp(owner, today, 'analysis', planned_meals=meals, analysis=True) > expected


def test_successful_analysis_returns_xp_once_for_replayed_request(app, client, monkeypatch):
    signup(client)
    calls = []
    def analyze(*args):
        calls.append(args)
        return {'calories': 300, 'protein': 20, 'carbs': 40, 'fat': 7}
    monkeypatch.setattr('src.routes.profile_routes.calculate_nutrition', analyze)
    headers = {'Idempotency-Key': 'analysis-reward'}
    first = client.post('/api/diet/ai_macros', json={'description': 'arroz e frango'}, headers=headers)
    assert first.status_code == 200
    assert first.json['xp_gained'] == 80
    assert client.post('/api/diet/ai_macros', json={'description': 'arroz e frango'}, headers=headers).json == first.json
    assert len(calls) == 1
    assert client.get('/api/progress/overview?view=summary').json['gamification']['total_xp'] == 80


def test_deleting_account_removes_award_history(app, client):
    signup(client)
    assert client.post('/api/water', json={'amount_ml': 300}, headers={'Idempotency-Key': 'cleanup-water'}).status_code == 201
    assert client.delete('/api/account', json={
        'username': 'water-owner', 'password': 'strong-password', 'confirm_delete': True,
    }).status_code == 200
    with app.app_context():
        assert GamificationAward.query.count() == 0
