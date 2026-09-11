from datetime import date, datetime

from src.models.user import DietAdherenceDay, DietEntry, DietMealCheckIn, DietMealDailyState, DietPlan, DietPlanMeal, db
from src.services.consistency import consistency_days
from src.services.workout_progress import create_weekly_goal, weekly_progress
from tests.test_workout_progress import create_user, create_plan, create_session


NOW = datetime(2026, 9, 9, 12)


def test_food_precedence_sparse_states_manual_days_and_privacy(app):
    with app.app_context():
        user = create_user('constancy-food')
        plan = DietPlan(user_id=user.id, title='Plano', source='manual', status='published')
        db.session.add(plan)
        db.session.flush()
        meal = DietPlanMeal(diet_plan_id=plan.id, day_of_week='1', meal_type='Almoço', description='Comida', order=1)
        db.session.add(meal)
        db.session.flush()
        for number in (1, 2, 3):
            record = DietAdherenceDay(user_id=user.id, diet_plan_id=plan.id, local_date=date(2026, 9, number), plan_day='1', status='in_progress')
            db.session.add(record)
            db.session.flush()
            db.session.add(DietMealCheckIn(adherence_day_id=record.id, diet_plan_meal_id=meal.id, status='completed'))
        for number, result in ((1, 'skipped'), (2, 'pending'), (4, 'consumed_planned'), (5, 'consumed_different')):
            db.session.add(DietMealDailyState(user_id=user.id, diet_plan_id=plan.id, selected_plan_meal_id=meal.id, slot_key='lunch', local_date=date(2026, 9, number), result=result))
        for _ in range(4):
            db.session.add(DietEntry(user_id=user.id, date=date(2026, 9, 6), meal_type='Lanche', description='Manual'))
        db.session.commit()
        data = consistency_days(user.id, NOW)
        days = {day['date']: day for day in data['days']}
        assert days['2026-09-01']['diet_states'] == ['skipped']
        assert days['2026-09-02']['diet_states'] == ['pending']
        assert not days['2026-09-02']['diet_tracked']
        assert days['2026-09-03']['diet_source'] == 'legacy_adherence'
        assert days['2026-09-04']['diet_states'] == ['consumed_planned']
        assert days['2026-09-05']['diet_states'] == ['consumed_different']
        assert days['2026-09-06']['diet_states'] == ['recorded_unclassified']
        assert sum(day['diet_tracked'] for day in days.values()) == 5
        assert days['2026-09-09']['diet_states'] == ['no_information']
        other = create_user('constancy-other')
        assert not any(day['diet_tracked'] for day in consistency_days(other.id, NOW)['days'])


def test_week_states_and_unique_workout_days_after_deletion(app):
    with app.app_context():
        user = create_user('constancy-workout', timezone='America/Sao_Paulo')
        plan, day, exercises = create_plan(user)
        create_weekly_goal(user.id, 2, 'America/Sao_Paulo', effective_week_start=date(2026, 8, 31))
        sessions = [create_session(user, plan, day, datetime(2026, 9, 8, 1), [(exercises[0], [{'repetitions': 8, 'load_kg': 20}])]) for _ in range(2)]
        db.session.commit()
        result = weekly_progress(user.id, NOW)
        assert result['history'][-1]['status'] == 'fulfilled'
        assert result['history'][-2]['status'] == 'unfulfilled'
        assert all(week['status'] == 'no_goal' for week in result['history'][:-2])
        days = consistency_days(user.id, NOW)['days']
        assert [item['date'] for item in days if item['workout']] == ['2026-09-07']
        db.session.delete(sessions[0])
        db.session.commit()
        assert weekly_progress(user.id, NOW)['history'][-1]['status'] == 'in_progress'
        db.session.delete(sessions[1])
        db.session.commit()
        assert not any(item['workout'] for item in consistency_days(user.id, NOW)['days'])
