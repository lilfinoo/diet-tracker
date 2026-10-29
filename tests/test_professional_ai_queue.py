import pytest

from src.models.user import AITask, User, WorkoutPlan, db
from src.services.ai_queue import execute_ai_job
from tests.test_professional_workspace import account


@pytest.mark.parametrize('scope', ['workout', None, 'diet'])
def test_professional_workout_retry_rechecks_scope_and_recovers_saved_draft(app, monkeypatch, scope):
    _, coach_id = account(app, 'retry-professional', professional=True)
    _, student_id = account(app, 'retry-student')
    with app.app_context():
        coach = db.session.get(User, coach_id)
        coach.professional_scope = scope
        assert coach.has_entitlement('premium')
        task = AITask(user_id=coach_id, operation='professional_workout_plan',
                      request_payload={}, route_params={'student_id': student_id})
        db.session.add(task)
        db.session.flush()
        plan = WorkoutPlan(user_id=student_id, author_user_id=coach_id,
                           title='Rascunho salvo', status='draft', source='ai', ai_task_id=task.id)
        db.session.add(plan)
        db.session.commit()
        task_id, plan_id = task.id, plan.id

    def forbidden(*args, **kwargs):
        raise AssertionError('A saved draft must be recovered without another AI call')

    monkeypatch.setattr('src.routes.professional_routes.generate_workout_plan', forbidden)
    execute_ai_job.run(str(task_id))
    with app.app_context():
        task = db.session.get(AITask, task_id)
        if scope == 'workout':
            assert task.status == 'succeeded'
            assert task.result['plan']['id'] == plan_id
            assert task.result['plan']['user_id'] == student_id
            assert task.result['plan']['status'] == 'draft'
        else:
            assert task.status == 'failed'
            assert task.http_status == 403
            assert 'plan' not in task.result
        assert WorkoutPlan.query.count() == 1
