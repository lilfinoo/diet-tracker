from tests.helpers import registration_payload


def register(client, username):
    response = client.post("/api/register", json=registration_payload(username))
    assert response.status_code == 201


def meal_payload(description):
    return {
        "date": "2026-09-17",
        "meal_type": "Almoço",
        "description": description,
        "calories": 450,
    }


def test_diet_mutation_replays_the_original_response(app, client):
    register(client, "idempotent-alice")
    headers = {"Idempotency-Key": "meal-create-1"}

    first = client.post("/api/diet", json=meal_payload("Arroz e feijão"), headers=headers)
    repeated = client.post("/api/diet", json=meal_payload("Arroz e feijão"), headers=headers)

    assert first.status_code == 201
    assert repeated.status_code == first.status_code
    assert repeated.get_json() == first.get_json()
    assert len(client.get("/api/diet").get_json()) == 1

    with app.app_context():
        from src.models.user import IdempotentOperation

        assert IdempotentOperation.query.count() == 1


def test_idempotency_keys_are_scoped_to_the_authenticated_user(client):
    register(client, "idempotent-bob")
    headers = {"Idempotency-Key": "same-key"}
    first = client.post("/api/diet", json=meal_payload("Refeição de Bob"), headers=headers)
    assert first.status_code == 201

    other = client.application.test_client()
    register(other, "idempotent-carol")
    second = other.post("/api/diet", json=meal_payload("Refeição de Carol"), headers=headers)

    assert second.status_code == 201
    assert second.get_json()["entry"]["description"] == "Refeição de Carol"
