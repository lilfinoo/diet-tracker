from types import SimpleNamespace

import pytest
from flask import g

from src.legal import AI_CONSENT_VERSION, AI_OPENAI_CONSENT_VERSION
from src.services import ai, openai_fallback


@pytest.fixture
def recovery(app, monkeypatch):
    app.config.update(
        GEMINI_MODEL='primary', GEMINI_FALLBACK_MODEL='backup',
        OPENAI_API_KEY='test-key', OPENAI_FALLBACK_ENABLED=False,
    )
    monkeypatch.setattr(openai_fallback, 'completion',
                        lambda *args, **kwargs: pytest.fail('OpenAI is disabled'))
    with app.test_request_context():
        g.user = SimpleNamespace(ai_consent_version=AI_OPENAI_CONSENT_VERSION,
                                 has_current_ai_consent=lambda: True)
        yield app


@pytest.mark.parametrize('failure', [ai.AIServiceUnavailableError, ai.AIQuotaExceededError])
def test_transient_failure_recovers_with_another_gemini_model(recovery, monkeypatch, failure):
    calls = []

    def completion(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise failure('primary unavailable')
        return '{"ok":true}'

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}}
    assert ai._completion('system', 'prompt', 100, .2, model='primary',
                          json_response=True, json_schema=schema,
                          image_bytes=b'image', mime_type='image/png',
                          request_timeout=10) == '{"ok":true}'
    assert [call[1]['model'] for call in calls] == ['primary', 'backup']
    assert calls[0][0] == calls[1][0] == ('system', 'prompt', 100, .2)
    for _, kwargs in calls:
        assert kwargs['json_schema'] == schema
        assert kwargs['json_response'] is True
        assert kwargs['image_bytes'] == b'image'
        assert kwargs['mime_type'] == 'image/png'


def test_primary_success_never_calls_backup(recovery, monkeypatch):
    models = []
    monkeypatch.setattr(ai, '_gemini_completion',
                        lambda *args, **kwargs: models.append(kwargs['model']) or 'ok')
    assert ai._completion('system', 'prompt', 100, .2, model='primary') == 'ok'
    assert models == ['primary']


@pytest.mark.parametrize('fallback', ['', 'primary'])
def test_empty_or_duplicate_backup_is_not_retried(recovery, monkeypatch, fallback):
    recovery.config['GEMINI_FALLBACK_MODEL'] = fallback
    models = []

    def completion(*args, **kwargs):
        models.append(kwargs['model'])
        raise ai.AIServiceUnavailableError('busy')

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    with pytest.raises(ai.AIServiceUnavailableError):
        ai._completion('system', 'prompt', 100, .2, model='primary')
    assert models == ['primary']


@pytest.mark.parametrize('failure', [ai.AIRefusalError, ai.AIServiceError, ai.AIResponseError])
def test_nontransient_error_does_not_switch_gemini_models(recovery, monkeypatch, failure):
    models = []

    def completion(*args, **kwargs):
        models.append(kwargs['model'])
        raise failure('failed')

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    with pytest.raises(failure):
        ai._completion('system', 'prompt', 100, .2, model='primary')
    assert models == ['primary']


def test_invalid_json_does_not_switch_gemini_models(recovery, monkeypatch):
    models = []
    monkeypatch.setattr(ai, '_gemini_completion',
                        lambda *args, **kwargs: models.append(kwargs['model']) or 'invalid')
    with pytest.raises(ai.AIResponseError):
        ai._completion('system', 'prompt', 100, .2, model='primary', json_response=True)
    assert models == ['primary']


def test_exhausted_gemini_models_preserve_last_error(recovery, monkeypatch):
    models = []
    exhausted = ai.AIQuotaExceededError('backup quota')

    def completion(*args, **kwargs):
        models.append(kwargs['model'])
        if kwargs['model'] == 'primary':
            raise ai.AIServiceUnavailableError('busy')
        raise exhausted

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    with pytest.raises(ai.AIQuotaExceededError) as caught:
        ai._completion('system', 'prompt', 100, .2, model='primary')
    assert caught.value is exhausted
    assert models == ['primary', 'backup']


def test_disabled_openai_repair_uses_gemini(recovery, monkeypatch):
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: '{"days":[]}')
    assert ai._completion('system', 'repair', 100, .2, json_response=True,
                          fallback_only=True) == '{"days":[]}'
    assert ai._openai_fallback_allowed() is False


@pytest.mark.parametrize('plan_deadline', [False, True])
def test_backup_receives_only_remaining_time(recovery, monkeypatch, plan_deadline):
    now = [100.0]
    monkeypatch.setattr(ai.time, 'monotonic', lambda: now[0])
    if plan_deadline:
        g.ai_generation_deadline = 110.0
    timeouts = []

    def completion(*args, **kwargs):
        timeouts.append(kwargs['request_timeout'])
        if len(timeouts) == 1:
            now[0] = 107.0
            raise ai.AIServiceUnavailableError('busy')
        return 'ok'

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    assert ai._completion('system', 'prompt', 100, .2,
                          model='primary', request_timeout=10) == 'ok'
    assert timeouts == [10, 3]


@pytest.mark.parametrize('plan_deadline', [False, True])
def test_no_backup_after_budget_is_exhausted(recovery, monkeypatch, plan_deadline):
    now = [100.0]
    monkeypatch.setattr(ai.time, 'monotonic', lambda: now[0])
    if plan_deadline:
        g.ai_generation_deadline = 110.0
    models = []

    def completion(*args, **kwargs):
        models.append(kwargs['model'])
        now[0] = 111.0
        raise ai.AIServiceUnavailableError('busy')

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    with pytest.raises(ai.AIServiceUnavailableError):
        ai._completion('system', 'prompt', 100, .2, model='primary', request_timeout=10)
    assert models == ['primary']


def test_authorized_openai_is_used_only_after_gemini_models(recovery, monkeypatch):
    recovery.config['OPENAI_FALLBACK_ENABLED'] = True
    calls = []

    def completion(*args, **kwargs):
        calls.append(kwargs['model'])
        raise ai.AIServiceUnavailableError('busy')

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    monkeypatch.setattr(openai_fallback, 'completion',
                        lambda *args, **kwargs: calls.append('openai') or 'ok')
    assert ai._completion('system', 'prompt', 100, .2, model='primary') == 'ok'
    assert calls == ['primary', 'backup', 'openai']


def test_gemini_recovery_does_not_require_openai_consent(recovery, monkeypatch):
    recovery.config['OPENAI_FALLBACK_ENABLED'] = True
    g.user.ai_consent_version = AI_CONSENT_VERSION
    models = []

    def completion(*args, **kwargs):
        models.append(kwargs['model'])
        if len(models) == 1:
            raise ai.AIServiceUnavailableError('busy')
        return 'ok'

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    assert ai._completion('system', 'prompt', 100, .2, model='primary') == 'ok'
    assert models == ['primary', 'backup']


def test_default_timeout_is_shared_by_models(recovery, monkeypatch):
    recovery.config['GEMINI_TIMEOUT'] = 20
    now = [100.0]
    monkeypatch.setattr(ai.time, 'monotonic', lambda: now[0])
    timeouts = []

    def completion(*args, **kwargs):
        timeouts.append(kwargs['request_timeout'])
        if len(timeouts) == 1:
            now[0] = 118.0
            raise ai.AIServiceUnavailableError('busy')
        return 'ok'

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    assert ai._completion('system', 'prompt', 100, .2, model='primary') == 'ok'
    assert timeouts == [20, 2]


def test_default_model_is_not_repeated_as_its_own_backup(recovery, monkeypatch):
    recovery.config['GEMINI_FALLBACK_MODEL'] = 'primary'
    calls = []

    def completion(*args, **kwargs):
        calls.append(kwargs)
        raise ai.AIServiceUnavailableError('busy')

    monkeypatch.setattr(ai, '_gemini_completion', completion)
    with pytest.raises(ai.AIServiceUnavailableError):
        ai._completion('system', 'prompt', 100, .2)
    assert len(calls) == 1
