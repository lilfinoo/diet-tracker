import pytest

from src.legal import PROFESSIONAL_SHARING_VERSION
from src.models.user import WorkoutXExercise, db
from src.services.workout_plans import workoutx_display_name
from tests.helpers import registration_payload
from tests.test_professional_workspace import account, roster, workout


@pytest.fixture
def provider_catalog(app):
    exercises = [
        {
            'id': str(990000 + index),
            'name': f'Provider chest press {index + 1}',
            'target': 'pectorals',
            'bodyPart': 'chest',
            'equipment': 'barbell',
            'mechanic': 'compound',
            'force': 'push',
            'difficulty': 'advanced',
            'gifUrl': f'https://api.workoutxapp.com/v1/gifs/{990000 + index}.gif',
        }
        for index in range(65)
    ]
    exercises[-1].pop('gifUrl')
    exercises.append({
        'id': '990999', 'name': 'Provider leg extension', 'target': 'quads',
        'bodyPart': 'upper legs', 'equipment': 'leverage machine',
        'mechanic': 'isolation', 'force': 'push', 'difficulty': 'beginner',
    })
    with app.app_context():
        assert all(workoutx_display_name(item['id']) is None for item in exercises)
        db.session.add_all(WorkoutXExercise(provider_id=item['id'], data=item) for item in exercises)
        db.session.commit()
    return exercises


def _manual_plan(client, keys):
    response = client.post('/api/workout_plans/manual', json={
        'title': 'Treino com catálogo completo',
        'days': [{'title': 'Treino A', 'exercises': [
            {'catalog_key': key, 'sets': 3, 'reps': '8-12', 'rest_seconds': 60}
            for key in keys
        ]}],
    })
    assert response.status_code == 201, response.json
    return response.json['plan']


def test_professional_and_app_catalogs_include_every_untranslated_provider_exercise(app, provider_catalog):
    coach, _ = account(app, 'full-catalog-coach', professional=True)
    student, _ = account(app, 'full-catalog-student')
    expected = {f"workoutx:{item['id']}": item['name'] for item in provider_catalog}

    professional_response = coach.get('/api/professional/exercises')
    assert professional_response.status_code == 200
    professional_items = {item['catalog_key']: item for item in professional_response.json}
    manual_response = student.get('/api/workout_plans/exercises/catalog')
    assert manual_response.status_code == 200
    manual_items = {item['key']: item for item in manual_response.json['items']}

    assert len(expected) > 60
    for key, name in expected.items():
        assert professional_items[key]['name'] == name
        assert manual_items[key]['name'] == name
    assert 'supino_maquina' in professional_items
    assert 'supino_maquina' in manual_items
    assert manual_items['workoutx:990064']['group']


def test_professional_and_app_catalogs_translate_provider_exercise_and_keep_original_alias(app):
    exercise = {
        'id': '0003', 'name': 'Air Bike', 'target': 'Abs',
        'bodyPart': 'Waist', 'equipment': 'Body Weight',
        'gifUrl': 'https://api.workoutxapp.com/v1/gifs/0003.gif',
    }
    with app.app_context():
        db.session.add(WorkoutXExercise(provider_id=exercise['id'], data=exercise))
        db.session.commit()
    coach, _ = account(app, 'translated-catalog-coach', professional=True)
    student, _ = account(app, 'translated-catalog-student')

    professional_response = coach.get('/api/professional/exercises')
    assert professional_response.status_code == 200
    professional_items = {item['catalog_key']: item for item in professional_response.json}
    manual_response = student.get('/api/workout_plans/exercises/catalog')
    assert manual_response.status_code == 200
    manual_items = {item['key']: item for item in manual_response.json['items']}

    for catalog in (professional_items, manual_items):
        item = catalog['workoutx:0003']
        assert item['name'] == 'Abdominal bicicleta'
        assert 'Air Bike' in item['aliases']


def test_personal_publishes_provider_exercise_for_student_to_activate(app, provider_catalog):
    coach, _ = account(app, 'full-provider-personal', professional=True)
    student, student_id = account(app, 'full-provider-aluno')
    offline_id = roster(coach)
    payload = workout()
    for day in payload['plan']['days']:
        day['exercises'][0]['catalog_key'] = 'workoutx:990064'
    offline_path = f'/api/professional/students/{offline_id}/workout-plans'
    response = coach.post(offline_path, json=payload)
    assert response.status_code == 201, response.json
    plan_id = response.json['plan']['id']

    invitation = coach.post(f'/api/professional/students/{offline_id}/invitation')
    assert invitation.status_code == 201, invitation.json
    accepted = student.post(f"/api/invitations/{invitation.json['token']}/accept", json={
        'data_sharing_consent': True,
        'data_sharing_consent_version': PROFESSIONAL_SHARING_VERSION,
    })
    assert accepted.status_code == 200, accepted.json
    published = coach.post(f'/api/professional/students/{student_id}/workout-plans/{plan_id}/publish')
    assert published.status_code == 200, published.json

    received = student.get(f'/api/workout_plans/{plan_id}')
    assert received.status_code == 200, received.json
    assert all(day['exercises'][0]['catalog_key'] == 'workoutx:990064' for day in received.json['days'])
    assert all(day['exercises'][0]['name'] == provider_catalog[64]['name'] for day in received.json['days'])
    activated = student.put(f'/api/workout_plans/{plan_id}/current', json={'weekdays': [1, 3]})
    assert activated.status_code == 200, activated.json


def test_app_manual_creation_and_addition_preserve_provider_catalog_identity(client, provider_catalog):
    assert client.post('/api/register', json=registration_payload('full-provider-manual')).status_code == 201
    plan = _manual_plan(client, ['workoutx:990000'])
    first = plan['days'][0]['exercises'][0]
    assert first['catalog_key'] == 'workoutx:990000'
    assert first['name'] == provider_catalog[0]['name']

    catalog_response = client.get(f"/api/workout_plans/{plan['id']}/exercises/catalog")
    assert catalog_response.status_code == 200, catalog_response.json
    plan_items = {item['key']: item for item in catalog_response.json['items']}
    assert {f"workoutx:{item['id']}" for item in provider_catalog} <= plan_items.keys()
    assert plan_items['workoutx:990000']['group'] == plan_items['workoutx:990064']['group']
    assert plan_items['workoutx:990000']['group']

    day = plan['days'][0]
    added = client.post(f"/api/workout_plans/{plan['id']}/days/{day['id']}/exercises", json={
        'catalog_key': 'workoutx:990064', 'sets': 4, 'reps': '10',
    })
    assert added.status_code == 201, added.json
    exercises = added.json['plan']['days'][0]['exercises']
    assert [(item['catalog_key'], item['name']) for item in exercises] == [
        ('workoutx:990000', provider_catalog[0]['name']),
        ('workoutx:990064', provider_catalog[64]['name']),
    ]
    duplicate = client.post(f"/api/workout_plans/{plan['id']}/days/{day['id']}/exercises", json={
        'catalog_key': 'workoutx:990064',
    })
    assert duplicate.status_code == 409, duplicate.json


def test_app_permanent_replacement_uses_full_provider_catalog_and_keeps_group_validation(client, provider_catalog, monkeypatch):
    assert client.post('/api/register', json=registration_payload('full-provider-swap')).status_code == 201
    plan = _manual_plan(client, ['workoutx:990000', 'workoutx:990001'])
    exercise = plan['days'][0]['exercises'][0]
    path = f"/api/workout_plans/{plan['id']}/exercises/{exercise['id']}"
    monkeypatch.setattr('src.routes.workout_routes.replacement_options', lambda *args, **kwargs: [])

    replaced = client.patch(path, json={'catalog_key': 'workoutx:990064'})
    assert replaced.status_code == 200, replaced.json
    updated = replaced.json['plan']['days'][0]['exercises'][0]
    assert updated['catalog_key'] == 'workoutx:990064'
    assert updated['name'] == provider_catalog[64]['name']

    incompatible = client.patch(path, json={'catalog_key': 'workoutx:990999'})
    assert incompatible.status_code == 400, incompatible.json
    duplicate = client.patch(path, json={'catalog_key': 'workoutx:990001'})
    assert duplicate.status_code in {400, 409}, duplicate.json
    unchanged = client.get(f"/api/workout_plans/{plan['id']}").json['days'][0]['exercises']
    assert [item['catalog_key'] for item in unchanged] == ['workoutx:990064', 'workoutx:990001']


def test_app_similar_options_keep_exercises_without_local_translation(client, provider_catalog, monkeypatch):
    assert client.post('/api/register', json=registration_payload('full-provider-similar')).status_code == 201
    plan = _manual_plan(client, ['workoutx:990000'])
    exercise = plan['days'][0]['exercises'][0]

    def no_provider_call(*args, **kwargs):
        raise AssertionError('Imported exercise matching must work without calling WorkoutX')

    monkeypatch.setattr('src.services.workoutx._request', no_provider_call)
    response = client.get(f"/api/workout_plans/{plan['id']}/exercises/{exercise['id']}/replacement_options")
    assert response.status_code == 200, response.json
    options = response.json['options']
    assert options
    names = {f"workoutx:{item['id']}": item['name'] for item in provider_catalog}
    for item in options:
        assert item['catalog_key'] != 'workoutx:990000'
        assert item['name'] == names[item['catalog_key']]
