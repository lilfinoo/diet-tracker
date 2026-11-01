from tests.test_guided_plans import diet_questionnaire, generated_diet, register_premium


def test_diet_repairs_only_invalid_days_after_full_plan_retries(app, client, monkeypatch):
    register_premium(app, client)
    calls = []

    def full_plan(questionnaire, profile, targets, correction):
        plan = generated_diet(targets)
        plan['days'][1]['meals'][0]['calories'] = 0
        return plan

    def repair(questionnaire, profile, existing_meals, feedback, targets, correction):
        calls.append(correction)
        return {'type': 'diet_plan_day', **generated_diet(targets)['days'][1]}

    monkeypatch.setattr('src.routes.plan_routes.generate_diet_plan', full_plan)
    monkeypatch.setattr('src.routes.plan_routes.generate_diet_day', repair)
    response = client.post('/api/diet_plans/generate', json=diet_questionnaire())

    assert response.status_code == 201, response.get_json()
    assert len(calls) == 1
    assert 'day.meals.1.nutrition' in calls[0]['validation_errors']
    assert len(response.get_json()['plan']['meals']) == 9


def test_diet_repair_rejects_invalid_day(app, client, monkeypatch):
    register_premium(app, client)
    def full_plan(questionnaire, profile, targets, correction):
        plan = generated_diet(targets)
        plan['days'][1]['meals'][0]['calories'] = 0
        return plan
    def repair(questionnaire, profile, existing_meals, feedback, targets, correction):
        day = generated_diet(targets)['days'][1]
        day['meals'][0]['items'] = ['Cerveja']
        return {'type': 'diet_plan_day', **day}
    monkeypatch.setattr('src.routes.plan_routes.generate_diet_plan', full_plan)
    monkeypatch.setattr('src.routes.plan_routes.generate_diet_day', repair)
    response = client.post('/api/diet_plans/generate', json=diet_questionnaire())
    assert response.status_code == 502
