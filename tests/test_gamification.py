from datetime import date, datetime, timedelta

import pytest

from src.models.user import GamificationDay, GamificationProfile, User, UserProfile, db
from src.services import gamification
from src.services.achievements import ACHIEVEMENTS, achievement_catalog, evaluate_achievements
from tests.test_water import signup
from tests.test_diet_daily import _create_plan, _outcome


@pytest.fixture
def owner(app):
    with app.app_context():
        user = User(username='gamification-owner', email='game@example.com')
        user.set_password('strong-password')
        db.session.add(user)
        db.session.flush()
        db.session.add(UserProfile(user_id=user.id, timezone='UTC'))
        db.session.commit()
        return user.id


def test_actions_are_capped_per_day_and_survive_a_new_session(app, owner):
    with app.app_context():
        today = datetime.utcnow().date()
        assert gamification.record_gamification_action(owner, 'water', today) == 30
        assert gamification.record_gamification_action(owner, 'water', today) == 0
        assert gamification.record_gamification_action(owner, 'meal', today) == 20
        assert gamification.record_gamification_action(owner, 'workout', today) == 100
        db.session.commit()
        db.session.remove()
        summary = gamification.gamification_summary(owner)
        assert summary['total_xp'] == 150
        assert summary['totalXP'] == summary['total_xp']
        assert summary['levelXP'] == summary['level_xp']
        assert summary['nextLevelXP'] == summary['next_level_xp']
        assert summary['current_streak'] == 1
        assert summary['active_days'] == 1
        assert len(summary['days']) == 28
        assert GamificationDay.query.count() == 1


def test_historical_and_future_records_do_not_earn_xp(app, owner):
    with app.app_context():
        today = datetime.utcnow().date()
        for day in (today - timedelta(days=1), today + timedelta(days=1)):
            assert gamification.record_gamification_action(owner, 'meal', day) == 0
        assert gamification.gamification_summary(owner)['total_xp'] == 0


def test_seven_active_days_award_a_protection_and_one_gap_consumes_it(app, owner, monkeypatch):
    class Clock(datetime):
        current = date(2026, 10, 1)

        @classmethod
        def now(cls, tz=None):
            return datetime.combine(cls.current, datetime.min.time(), tzinfo=tz)

    monkeypatch.setattr(gamification, 'datetime', Clock)
    with app.app_context():
        for offset in range(7):
            Clock.current = date(2026, 10, 1) + timedelta(days=offset)
            gamification.record_gamification_action(owner, 'meal', Clock.current)
        profile = GamificationProfile.query.filter_by(user_id=owner).one()
        assert (profile.current_streak, profile.available_protections) == (7, 1)
        Clock.current = date(2026, 10, 9)
        gamification.record_gamification_action(owner, 'water', Clock.current)
        assert (profile.current_streak, profile.available_protections) == (8, 0)
        Clock.current = date(2026, 10, 17)
        gamification.record_gamification_action(owner, 'workout', Clock.current)
        assert profile.current_streak == 1
        assert GamificationDay.query.filter_by(user_id=owner, local_date=Clock.current).one().return_earned


def test_first_daily_achievement_is_unlocked_once(app, owner):
    with app.app_context():
        gamification.record_gamification_action(owner, 'water', datetime.utcnow().date())
        unlocks = evaluate_achievements(owner)
        assert [item.achievement_code for item in unlocks] == ['water_1']
        assert evaluate_achievements(owner) == []
        items = {item['code']: item for item in achievement_catalog(owner)}
        assert len(ACHIEVEMENTS) == len(items) == 50
        assert items['water_1']['unlocked'] is not None
        assert items['water_3']['progress']['current'] == 1


def test_water_retry_does_not_duplicate_xp_and_account_deletion_cleans_progress(app, client):
    signup(client)
    headers = {'Idempotency-Key': 'gamification-water'}
    first = client.post('/api/water', json={'amount_ml': 300}, headers=headers)
    assert first.status_code == 201
    assert first.json['xp_gained'] == 30
    assert client.post('/api/water', json={'amount_ml': 300}, headers=headers).json == first.json
    overview = client.get('/api/progress/overview?view=summary')
    assert overview.json['gamification']['total_xp'] == 30
    assert client.delete('/api/account', json={'username': 'water-owner', 'password': 'strong-password', 'confirm_delete': True}).status_code == 200
    with app.app_context():
        assert GamificationProfile.query.count() == 0
        assert GamificationDay.query.count() == 0


def test_planned_meal_xp_is_persisted_after_the_response(app, client):
    signup(client)
    _create_plan(app, 'water-owner')
    today = datetime.utcnow().date().isoformat()
    # Use UTC for a deterministic local day on both the route and the profile.
    client.post('/api/profile', json={'timezone': 'UTC'})
    first = _outcome(client, 'breakfast', 'consumed_planned', day=today)
    assert first.status_code == 201
    assert first.json['xp_gained'] == 33
    again = _outcome(client, 'breakfast', 'consumed_planned', day=today)
    assert again.status_code == 200
    assert again.json['xp_gained'] == 0
    assert client.get('/api/progress/overview?view=summary').json['gamification']['total_xp'] == 33


@pytest.mark.parametrize('xp,level,rank', [(0, 1, 'Bronze'), (99, 1, 'Bronze'), (100, 2, 'Bronze'), (550, 5, 'Prata')])
def test_level_boundaries(xp, level, rank):
    actual, _, _ = gamification.level_for_xp(xp)
    assert actual == level
    assert gamification.rank_for_level(actual) == rank
