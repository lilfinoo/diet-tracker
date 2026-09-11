import json

import pytest

from src.services import ai
from tests.helpers import registration_payload


def test_identification_description_and_zero(app, monkeypatch):
    captured = {}

    def completion(*args, **kwargs):
        captured['prompt'] = args[1]
        return json.dumps({'description': 'Café sem açúcar, porção aproximada.',
                           'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0})

    monkeypatch.setattr(ai, '_completion', completion)
    with app.app_context():
        result = ai.calculate_nutrition('Sem açúcar', b'photo', 'image/jpeg')
    assert result['description'] == 'Café sem açúcar, porção aproximada.'
    assert result['calories'] == 0
    assert 'Sem açúcar' in captured['prompt']
    assert 'aproximadas' in captured['prompt']


@pytest.mark.parametrize('description', [None, [], 12, 'a' * 2001])
def test_invalid_description_rejected(app, monkeypatch, description):
    monkeypatch.setattr(ai, '_completion', lambda *args, **kwargs: json.dumps({
        'description': description, 'calories': 1, 'protein': 0, 'carbs': 0, 'fat': 0,
    }))
    with app.app_context(), pytest.raises(ai.AIResponseError):
        ai.calculate_nutrition('Arroz')


def test_missing_identification_not_fabricated(app, monkeypatch):
    monkeypatch.setattr(ai, '_completion', lambda *args, **kwargs:
                        '{"calories": 1, "protein": 0, "carbs": 0, "fat": 0}')
    with app.app_context():
        assert ai.calculate_nutrition('', b'photo', 'image/jpeg')['description'] == ''


def test_macro_endpoint_explains_temporary_unavailability(client, monkeypatch):
    client.post('/api/register', json=registration_payload('macro-unavailable'))

    def unavailable(*args, **kwargs):
        raise ai.AIServiceUnavailableError('provider unavailable')

    monkeypatch.setattr('src.routes.profile_routes.calculate_nutrition', unavailable)
    response = client.post('/api/diet/ai_macros', json={'description': 'Arroz'})
    assert response.status_code == 503
    assert 'temporariamente indisponível' in response.get_json()['error']
    assert 'sem estimativa' in response.get_json()['error']
