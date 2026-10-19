from tests.helpers import registration_payload


def test_free_manual_plans_and_workout_session(client):
    client.post('/api/register', json=registration_payload('manual-free'))
    catalog = client.get('/api/workout_plans/exercises/catalog').get_json()['items']
    response = client.post('/api/workout_plans/manual', json={
        'title': 'Meu treino', 'days': [{'title': 'A', 'exercises': [
            {'catalog_key': catalog[0]['key'], 'sets': 3, 'reps': '10'},
            {'name': 'Meu exercício', 'sets': 2, 'reps': '12'}]}]})
    assert response.status_code == 201
    plan = response.get_json()['plan']
    assert plan['source'] == 'manual'
    assert client.put(f"/api/workout_plans/{plan['id']}/current", json={'weekdays': [1]}).status_code == 200
    response = client.post('/api/diet_plans/manual', json={'title': 'Minha dieta', 'meals': [
        {'meal_type': 'Almoço', 'description': 'Arroz e feijão'}]})
    assert response.status_code == 201
    diet = response.get_json()['plan']
    assert client.put(f"/api/diet_plans/{diet['id']}/current").status_code == 200
    meal = diet['meals'][0]
    assert client.patch(f"/api/diet_plans/{diet['id']}/meals/{meal['id']}", json={'description': 'Arroz, feijão e salada'}).status_code == 200
    usage = client.get('/api/ai/usage').get_json()
    assert usage['workout_plans']['used'] == usage['diet_plans']['used'] == usage['photos']['used'] == 0


def test_free_premium_preferences_rejected_without_spending_slot(client):
    client.post('/api/register', json=registration_payload('preferences-free'))
    for kind, fields in [('workout', {'priorities': 'Braços'}), ('workout', {'avoid_exercises': 'Agachamento'}),
                         ('diet', {'preferred_foods': ['arroz']}), ('diet', {'disliked_foods': ['feijão']})]:
        response = client.post(f'/api/{kind}_plans/generate', json=fields)
        assert response.status_code == 403
        assert response.get_json()['code'] == 'premium_required'
    usage = client.get('/api/ai/usage').get_json()
    assert usage['workout_plans']['used'] == usage['diet_plans']['used'] == 0


def test_manual_plan_validation_and_ownership(client, app):
    client.post('/api/register', json=registration_payload('manual-owner'))
    assert client.post('/api/workout_plans/manual', json={'title': 'A', 'days': []}).status_code == 400
    assert client.post('/api/diet_plans/manual', json={'title': 'A', 'meals': [{'meal_type': 'Almoço', 'description': 'Arroz', 'calories': -1}]}).status_code == 400
    plan = client.post('/api/diet_plans/manual', json={'title': 'A', 'meals': [{'meal_type': 'Almoço', 'description': 'Arroz'}]}).get_json()['plan']
    other = app.test_client()
    other.post('/api/register', json=registration_payload('manual-other'))
    assert other.put(f"/api/diet_plans/{plan['id']}/current").status_code == 404


def test_free_ai_edit_is_denied_without_calling_provider(client, monkeypatch):
    client.post('/api/register', json=registration_payload('free-edit'))
    plan = client.post('/api/workout_plans/manual', json={'title': 'Treino', 'days': [
        {'title': 'A', 'exercises': [{'name': 'Exercício próprio'}]}]}).get_json()['plan']
    def forbidden(*args):
        raise AssertionError('Free AI editing must not call provider')
    monkeypatch.setattr('src.routes.workout_routes.suggest_workout_changes', forbidden)
    response = client.post(f"/api/workout_plans/{plan['id']}/suggest_changes", json={'feedback': 'Mais séries'})
    assert response.status_code == 403
    exercise = plan['days'][0]['exercises'][0]
    response = client.patch(f"/api/workout_plans/{plan['id']}/exercises/{exercise['id']}", json={'name': 'Outro exercício', 'sets': 4})
    assert response.status_code == 200
    assert response.get_json()['plan']['days'][0]['exercises'][0]['name'] == 'Outro exercício'
    assert client.post(f"/api/workout_plans/{plan['id']}/days/{plan['days'][0]['id']}/sessions").status_code == 201


def test_free_diet_keeps_allergies_and_intolerances(app, client, monkeypatch):
    from src.models.user import User, db
    from src.services.ai import AIServiceError
    from tests.test_guided_plans import register_premium, diet_questionnaire
    register_premium(app, client)
    with app.app_context():
        User.query.filter_by(username='guided').one().is_premium = False
        db.session.commit()
    captured = {}
    def generation(questionnaire, *args):
        captured.update(questionnaire)
        raise AIServiceError('mock unavailable')
    monkeypatch.setattr('src.routes.plan_routes.generate_diet_plan', generation)
    response = client.post('/api/diet_plans/generate', json=diet_questionnaire(
        preferred_foods=[], allergies=['amendoim'], intolerances=['lactose']))
    assert response.status_code == 503
    assert 'amendoim' in captured['allergies']
    assert 'lactose' in captured['intolerances']
    assert client.get('/api/ai/usage').get_json()['diet_plans']['used'] == 0
