import json
from types import SimpleNamespace

import pytest

from src.services import ai


RESULT = json.dumps({'description': 'Arroz, porção aproximada', 'calories': 100,
                     'protein': 2, 'carbs': 20, 'fat': 1})


def test_nutrition_retry_preserves_photo_and_description(app, monkeypatch):
    calls = []

    def completion(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise ai.AIServiceUnavailableError('unavailable')
        return RESULT

    monkeypatch.setattr(ai, '_completion', completion)
    monkeypatch.setattr(ai.time, 'sleep', lambda _: None)
    with app.app_context():
        app.config.update(GEMINI_NUTRITION_MODEL='primary', GEMINI_MODEL='fallback')
        result = ai.calculate_nutrition('Arroz e feijão', b'photo', 'image/jpeg')
    assert result['calories'] == 100
    assert [kwargs['model'] for _, kwargs in calls] == ['primary', 'primary']
    for args, kwargs in calls:
        assert 'Arroz e feijão' in args[1]
        assert kwargs['image_bytes'] == b'photo'
        assert kwargs['mime_type'] == 'image/jpeg'
        assert kwargs['request_timeout'] <= 10


@pytest.mark.parametrize('failure', [ai.AIQuotaExceededError, ai.AIServiceError, ai.AIResponseError])
def test_nutrition_does_not_retry_permanent_failures(app, monkeypatch, failure):
    calls = []

    def completion(*args, **kwargs):
        calls.append(kwargs)
        raise failure('failed')

    monkeypatch.setattr(ai, '_completion', completion)
    with app.app_context(), pytest.raises(failure):
        ai.calculate_nutrition('Arroz')
    assert len(calls) == 1


def test_nutrition_unavailable_stops_after_two_attempts(app, monkeypatch):
    calls = []

    def completion(*args, **kwargs):
        calls.append(kwargs)
        raise ai.AIServiceUnavailableError('failed')

    monkeypatch.setattr(ai, '_completion', completion)
    monkeypatch.setattr(ai.time, 'sleep', lambda _: None)
    with app.app_context(), pytest.raises(ai.AIServiceUnavailableError):
        ai.calculate_nutrition('Arroz')
    assert len(calls) == 2


def test_nutrition_skips_fallback_when_window_has_expired(app, monkeypatch):
    clock = iter([0, 0, 23])
    monkeypatch.setattr(ai.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(ai.time, 'sleep', lambda _: None)
    calls = []

    def completion(*args, **kwargs):
        calls.append(kwargs)
        raise ai.AIServiceUnavailableError('failed')

    monkeypatch.setattr(ai, '_completion', completion)
    with app.app_context(), pytest.raises(ai.AIServiceUnavailableError):
        ai.calculate_nutrition('Arroz')
    assert len(calls) == 1


def test_nutrition_http_timeout_disables_hidden_sdk_retries(app, monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason='STOP', content=SimpleNamespace(
                parts=[SimpleNamespace(text=RESULT, thought=False)]))], usage_metadata=None)

    monkeypatch.setattr(ai.genai, 'Client', Client)
    with app.app_context():
        app.config['GEMINI_API_KEY'] = 'test-key'
        ai._completion('system', 'prompt', 1024, 0.3, request_timeout=10)
    assert captured['http_options'].timeout == 10000
    assert captured['http_options'].retry_options.attempts == 1


@pytest.mark.parametrize('recover', [True, False])
def test_photo_fallback_counts_only_successful_analysis(client, monkeypatch, recover):
    from tests.helpers import registration_payload
    from tests.test_free_ai_allowances import PHOTO

    assert client.post('/api/register', json=registration_payload('photo-retry')).status_code == 201
    calls = []

    def completion(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1 or not recover:
            raise ai.AIServiceUnavailableError('unavailable')
        return RESULT

    monkeypatch.setattr(ai, '_completion', completion)
    monkeypatch.setattr(ai.time, 'sleep', lambda _: None)
    response = client.post('/api/diet/ai_macros', json={**PHOTO, 'description': 'Arroz'})
    assert response.status_code == (200 if recover else 503)
    assert len(calls) == 2
    assert client.get('/api/ai/usage').get_json()['photos']['used'] == (1 if recover else 0)
