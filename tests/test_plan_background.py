from flask import g, request

from src.models.user import AITask, User, db
from src.routes.common import idempotent_mutation, login_required, premium_required
from src.services.ai_queue import enqueue_ai_request, execute_ai_job
from tests.helpers import registration_payload


def setup_plan(app, client, monkeypatch):
    app.config.update(AI_ASYNC_ENABLED=True, AI_PLAN_BACKGROUND_ENABLED=True,
                      CELERY_BROKER_URL='redis://worker/0')
    calls = []
    monkeypatch.setattr(execute_ai_job, 'apply_async', lambda args: calls.append(args[0]))

    @app.route('/test-background-plan', methods=['POST'])
    @login_required
    @idempotent_mutation
    @premium_required(allow_trial=True, trial_kind='workout_plans')
    def start():
        return enqueue_ai_request('workout_plan', {}) or {'sync': True}

    client.post('/api/register', json=registration_payload('background-free'))
    return calls


def test_free_background_replay_reserves_once_and_retains_provider(app, client, monkeypatch):
    calls = setup_plan(app, client, monkeypatch)
    headers = {'X-AI-Background': 'plans', 'X-AI-Providers': 'gemini,openai',
               'Idempotency-Key': 'workout-request'}
    first = client.post('/test-background-plan', json={}, headers=headers)
    second = client.post('/test-background-plan', json={}, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.get_json() == second.get_json()
    assert len(calls) == 1
    seen = []
    monkeypatch.setattr('src.services.ai_queue._handler_for', lambda operation: lambda: (
        seen.append((str(g.user.id), request.headers['X-AI-Providers'])) or {'plan_id': 42}, 201))
    execute_ai_job.run(calls[0])
    execute_ai_job.run(calls[0])
    assert len(seen) == 1
    result = client.get('/api/ai/tasks').get_json()
    assert result['plan_background_enabled'] is True
    assert result['tasks'][0]['status'] == 'succeeded'
    assert result['tasks'][0]['result'] == {'plan_id': 42}
    with app.app_context():
        assert User.query.filter_by(username='background-free').one().free_workout_plan_uses == 1


def test_terminal_failure_refunds_reserved_free_plan_once(app, client, monkeypatch):
    calls = setup_plan(app, client, monkeypatch)
    client.post('/test-background-plan', json={}, headers={'X-AI-Background': 'plans'})
    app.config['AI_JOB_MAX_RETRIES'] = 0
    monkeypatch.setattr('src.services.ai_queue._handler_for',
                        lambda operation: lambda: ({'error': 'provider unavailable'}, 503))
    execute_ai_job.run(calls[0])
    execute_ai_job.run(calls[0])
    with app.app_context():
        user = User.query.filter_by(username='background-free').one()
        assert user.free_workout_plan_uses == user.ai_trial_uses == 0
        assert db.session.get(AITask, calls[0]).status == 'failed'


def test_capability_is_false_without_configured_worker_and_jobs_owner_scoped(app, client, monkeypatch):
    setup_plan(app, client, monkeypatch)
    client.post('/test-background-plan', json={}, headers={'X-AI-Background': 'plans'})
    app.config['AI_PLAN_BACKGROUND_ENABLED'] = False
    assert client.get('/api/ai/tasks').get_json()['plan_background_enabled'] is False
    client.post('/api/logout')
    client.post('/api/register', json=registration_payload('other-background-user'))
    assert client.get('/api/ai/tasks').get_json()['tasks'] == []
