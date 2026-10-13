import logging
from types import SimpleNamespace

import pytest
from flask import g

from src.legal import AI_CONSENT_VERSION, AI_OPENAI_CONSENT_VERSION
from src.services import ai, openai_fallback


@pytest.mark.parametrize('failure', [ai.AIServiceUnavailableError, ai.AIQuotaExceededError, ai.AIServiceError, ai.AIResponseError])
def test_authorized_gemini_failure_uses_openai(app, monkeypatch, failure):
    calls = []
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: (_ for _ in ()).throw(failure('failed')))
    monkeypatch.setattr(openai_fallback, 'completion', lambda *args, **kwargs: calls.append(kwargs) or '{"ok":true}')
    with app.test_request_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        g.user = SimpleNamespace(ai_consent_version=AI_OPENAI_CONSENT_VERSION, has_current_ai_consent=lambda: True)
        assert ai._completion('system', 'prompt', 100, .2, json_response=True) == '{"ok":true}'
    assert len(calls) == 1


@pytest.mark.parametrize('version,granted', [(AI_CONSENT_VERSION, True), (AI_OPENAI_CONSENT_VERSION, False)])
def test_legacy_or_revoked_consent_never_sends_to_openai(app, monkeypatch, version, granted):
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: (_ for _ in ()).throw(ai.AIServiceUnavailableError('failed')))
    monkeypatch.setattr(openai_fallback, 'completion', lambda *args, **kwargs: pytest.fail('Unauthorized provider request'))
    with app.test_request_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        g.user = SimpleNamespace(ai_consent_version=version, has_current_ai_consent=lambda: granted)
        with pytest.raises(ai.AIServiceUnavailableError):
            ai._completion('system', 'prompt', 100, .2)


def test_gemini_success_does_not_call_openai(app, monkeypatch):
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: '{"ok":true}')
    monkeypatch.setattr(openai_fallback, 'completion', lambda *args, **kwargs: pytest.fail('Unnecessary fallback'))
    with app.test_request_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        g.user = SimpleNamespace(ai_consent_version=AI_OPENAI_CONSENT_VERSION, has_current_ai_consent=lambda: True)
        assert ai._completion('system', 'prompt', 100, .2, json_response=True) == '{"ok":true}'


def test_refusal_is_not_bypassed(app, monkeypatch):
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: (_ for _ in ()).throw(ai.AIRefusalError('refused')))
    monkeypatch.setattr(openai_fallback, 'completion', lambda *args, **kwargs: pytest.fail('Refusal bypassed'))
    with app.test_request_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        g.user = SimpleNamespace(ai_consent_version=AI_OPENAI_CONSENT_VERSION, has_current_ai_consent=lambda: True)
        with pytest.raises(ai.AIRefusalError):
            ai._completion('system', 'prompt', 100, .2)


def test_invalid_gemini_json_uses_fallback(app, monkeypatch):
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: 'not JSON')
    monkeypatch.setattr(openai_fallback, 'completion', lambda *args, **kwargs: '{"ok":true}')
    with app.test_request_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        g.user = SimpleNamespace(ai_consent_version=AI_OPENAI_CONSENT_VERSION, has_current_ai_consent=lambda: True)
        assert ai._completion('system', 'prompt', 100, .2, json_response=True) == '{"ok":true}'


def test_strict_schema_preserves_optional_fields_without_mutation():
    schema = {'type': 'object', 'required': ['name'], 'properties': {
        'name': {'type': 'string'}, 'notes': {'type': 'string'},
        'items': {'type': 'array', 'items': {'type': 'object', 'properties': {'load': {'type': 'number'}}}}}}
    converted = openai_fallback._strict_schema(schema)
    assert converted['additionalProperties'] is False
    assert converted['required'] == ['name', 'notes', 'items']
    assert converted['properties']['notes']['anyOf'][1] == {'type': 'null'}
    assert converted['properties']['items']['anyOf'][0]['items']['additionalProperties'] is False
    assert 'additionalProperties' not in schema


def test_openai_transport_uses_structured_schema_and_disables_storage(app, monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured['options'] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return SimpleNamespace(status_code=200, json=lambda: {
                'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"name":"rice"}'}]}]})

    monkeypatch.setattr(openai_fallback.httpx, 'Client', Client)
    with app.app_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        result = openai_fallback.completion('system', 'prompt', 100, .2, json_response=True,
            json_schema={'type': 'object', 'properties': {'name': {'type': 'string'}}},
            image_bytes=b'photo', mime_type='image/jpeg', timeout=10)
    assert result == '{"name":"rice"}'
    assert captured['url'] == 'https://api.openai.com/v1/responses'
    assert captured['json']['store'] is False
    assert captured['json']['text']['format']['strict'] is True
    assert captured['options']['timeout'] == 10
    assert captured['json']['input'][0]['content'][1]['image_url'].startswith('data:image/jpeg;base64,')


@pytest.mark.parametrize('status,failure', [(401, ai.AIServiceError), (429, ai.AIQuotaExceededError), (503, ai.AIServiceUnavailableError)])
def test_openai_errors_exclude_provider_body(app, monkeypatch, caplog, status, failure):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            return SimpleNamespace(status_code=status, json=lambda: pytest.fail('Sensitive error body accessed'))

    monkeypatch.setattr(openai_fallback.httpx, 'Client', Client)
    with app.app_context(), caplog.at_level(logging.WARNING):
        app.config['OPENAI_API_KEY'] = 'private-key'
        with pytest.raises(failure):
            openai_fallback.completion('system', 'private-prompt', 100, .2)
    assert 'private-key' not in caplog.text
    assert 'private-prompt' not in caplog.text


def test_plan_time_budget_prevents_another_provider_after_deadline(app, monkeypatch):
    monkeypatch.setattr(ai.time, 'monotonic', lambda: 151)
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: pytest.fail('Expired generation invoked'))
    monkeypatch.setattr(openai_fallback, 'completion', lambda *args, **kwargs: pytest.fail('Expired fallback invoked'))
    with app.test_request_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        g.user = SimpleNamespace(ai_consent_version=AI_OPENAI_CONSENT_VERSION, has_current_ai_consent=lambda: True)
        g.ai_generation_deadline = 150
        with pytest.raises(ai.AIServiceUnavailableError):
            ai._completion('system', 'prompt', 100, .2)


def test_plan_validation_repair_uses_authorized_fallback_without_repeating_gemini(app, monkeypatch):
    monkeypatch.setattr(ai, '_gemini_completion', lambda *args, **kwargs: pytest.fail('Failed plan sent to Gemini again'))
    calls = []
    monkeypatch.setattr(openai_fallback, 'completion', lambda *args, **kwargs: calls.append(args[1]) or '{"days":[]}')
    with app.test_request_context():
        app.config['OPENAI_API_KEY'] = 'test-key'
        g.user = SimpleNamespace(ai_consent_version=AI_OPENAI_CONSENT_VERSION, has_current_ai_consent=lambda: True)
        assert ai._completion('system', 'repair only invalid days', 100, .2, json_response=True,
                              fallback_only=True) == '{"days":[]}'
    assert calls == ['repair only invalid days']
