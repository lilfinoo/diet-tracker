from datetime import date, datetime

from src.models.user import Measurement, User, db
from tests.test_core_user_flows import register


def test_summary_uses_latest_two_values_per_metric_and_is_private(app, client):
    assert client.get('/api/measurements/summary').status_code == 401
    register(client, 'summary-owner')
    assert client.get('/api/measurements/summary').get_json()['latest_date'] is None
    for payload in (
        {'date': '2026-08-01', 'weight': 75, 'body_fat': 20, 'waist': 90},
        {'date': '2026-08-02', 'body_fat': 19, 'muscle_mass': 35},
        {'date': '2026-08-03', 'weight': 75, 'waist': 88},
        {'date': '2026-08-04', 'chest': 95},
    ):
        assert client.post('/api/measurements', json=payload).status_code == 201
    result = client.get('/api/measurements/summary').get_json()
    assert result['latest_date'] == '2026-08-04'
    metrics = result['metrics']
    assert metrics['weight'] == {
        'latest': {'value': 75, 'date': '2026-08-03'},
        'previous': {'value': 75, 'date': '2026-08-01'}, 'change': 0,
    }
    assert metrics['body_fat']['change'] == -1
    assert metrics['waist']['change'] == -2
    assert metrics['muscle_mass']['previous'] is None
    assert metrics['height']['latest'] is None
    other = app.test_client()
    register(other, 'summary-other')
    assert other.get('/api/measurements/summary').get_json()['latest_date'] is None
    assert client.get('/api/measurements/summary').get_json() == result


def test_summary_refreshes_after_edit_and_delete(client):
    register(client, 'summary-crud')
    first = client.post('/api/measurements', json={'date': '2026-08-01', 'weight': 70}).get_json()['measurement']
    second = client.post('/api/measurements', json={'date': '2026-08-02', 'weight': 72}).get_json()['measurement']
    assert client.get('/api/measurements/summary').get_json()['metrics']['weight']['change'] == 2
    assert client.put(f"/api/measurements/{second['id']}", json={'weight': 71}).status_code == 200
    assert client.get('/api/measurements/summary').get_json()['metrics']['weight']['change'] == 1
    assert client.delete(f"/api/measurements/{second['id']}").status_code == 200
    weight = client.get('/api/measurements/summary').get_json()['metrics']['weight']
    assert weight['latest']['value'] == first['weight']
    assert weight['previous'] is None


def test_filtered_pages_and_same_day_order_agree_with_summary_and_stats(app, client):
    register(client, 'pages-owner')
    with app.app_context():
        user = User.query.filter_by(username='pages-owner').one()
        # Identical dates and timestamps exercise the final ID tie-breaker.
        rows = [Measurement(user_id=user.id, date=date(2026, 8, 10),
                            created_at=datetime(2026, 8, 10, 12), weight=70 + i)
                for i in range(25)]
        db.session.add_all(rows)
        db.session.commit()
        expected = [row.id for row in reversed(rows)]
    url = '/api/measurements?start_date=2026-08-10&end_date=2026-08-10&limit=20'
    first = client.get(url).get_json()
    second = client.get(url + '&offset=20').get_json()
    assert [row['id'] for row in first + second] == expected
    assert client.get('/api/stats').get_json()['latest_measurement']['id'] == expected[0]
    assert client.get('/api/measurements/summary').get_json()['metrics']['weight']['latest']['value'] == 94
    assert client.get('/api/measurements?start_date=2026-08-11&end_date=2026-08-10').status_code == 400


def test_recent_diet_count_is_seven_local_dates_without_future(client, monkeypatch):
    register(client, 'dates-owner')
    captured = []

    def local_date(zone):
        captured.append(zone)
        return date(2026, 8, 10)

    monkeypatch.setattr('src.routes.profile_routes._local_date_for_timezone', local_date)
    assert client.post('/api/profile', json={'timezone': 'America/Sao_Paulo'}).status_code == 200
    for day in ('2026-08-03', '2026-08-04', '2026-08-10', '2026-08-11'):
        assert client.post('/api/diet', json={'date': day, 'meal_type': 'Lanche', 'description': 'Registro'}).status_code == 201
    stats = client.get('/api/stats').get_json()
    assert stats['recent_diet_entries'] == 2
    assert stats['total_diet_entries'] == 4
    assert captured == ['America/Sao_Paulo']


def test_measurement_browser_flows():
    import os
    from pathlib import Path
    import shutil
    import subprocess

    import pytest

    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for frontend flow tests')
    result = subprocess.run(
        [node, '--test', str(Path(__file__).with_name('measurement_flows.test.cjs'))],
        env={**os.environ, 'TZ': 'America/Sao_Paulo'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
