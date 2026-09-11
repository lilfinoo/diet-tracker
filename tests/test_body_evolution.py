import subprocess

from tests.test_core_user_flows import register


def test_metric_series_sparse_filtered_private_and_unpaginated(app, client):
    assert client.get('/api/measurements/summary?metric=weight').status_code == 401
    register(client, 'body-chart-owner')
    assert client.get('/api/measurements/summary?metric=weight').get_json() == {'points': [], 'latest_date': None}
    for day in range(1, 26):
        assert client.post('/api/measurements', json={'date': f'2026-08-{day:02}', 'weight': 70 + day / 10}).status_code == 201
    client.post('/api/measurements', json={'date': '2026-09-01', 'waist': 80, 'body_fat': 20})
    data = client.get('/api/measurements/summary?metric=weight').get_json()
    assert len(data['points']) == 25
    assert data['latest_date'] == '2026-08-25'
    assert data['points'][0]['value'] == 70.1
    for metric in ('waist', 'body_fat'):
        assert len(client.get(f'/api/measurements/summary?metric={metric}').get_json()['points']) == 1
    for metric in ('chest', 'arm', 'thigh', 'muscle_mass'):
        assert client.get(f'/api/measurements/summary?metric={metric}').get_json()['points'] == []
    filtered = client.get('/api/measurements/summary?metric=weight&start_date=2026-08-02&end_date=2026-08-03').get_json()
    assert [point['date'] for point in filtered['points']] == ['2026-08-02', '2026-08-03']
    assert filtered['latest_date'] == '2026-08-25'
    other = app.test_client()
    register(other, 'body-chart-other')
    assert other.get('/api/measurements/summary?metric=weight').get_json()['points'] == []
    for query in ('metric=height', 'metric=bogus', 'metric=weight&start_date=bad', 'metric=weight&start_date=2026-09-01&end_date=2026-08-01'):
        assert client.get('/api/measurements/summary?' + query).status_code == 400


def test_body_chart_browser_logic():
    subprocess.run(['node', '--test', 'tests/body_evolution.test.cjs'], check=True)


def test_series_reloads_edited_deleted_and_same_day_measurements(client):
    register(client, 'chart-crud')
    ids = []
    for value in (70, 71):
        response = client.post('/api/measurements', json={'date': '2026-09-01', 'weight': value})
        ids.append(response.get_json()['measurement']['id'])
    endpoint = '/api/measurements/summary?metric=weight'
    assert [p['value'] for p in client.get(endpoint).get_json()['points']] == [70, 71]
    client.put(f'/api/measurements/{ids[0]}', json={'weight': 69})
    assert [p['value'] for p in client.get(endpoint).get_json()['points']] == [69, 71]
    client.delete(f'/api/measurements/{ids[1]}')
    assert client.get(endpoint).get_json()['points'] == [{'value': 69, 'date': '2026-09-01'}]
