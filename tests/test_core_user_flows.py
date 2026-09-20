from datetime import datetime, timedelta, timezone

from tests.helpers import registration_payload


PASSWORD = "strong-password"


def register(client, username):
    response = client.post(
        "/api/register", json=registration_payload(username, PASSWORD)
    )
    assert response.status_code == 201


def test_login_logout_and_check_session(client):
    register(client, "alice")
    session = client.get("/api/check_session")
    assert session.get_json()["user"]["onboarding_status"] == "new"
    assert session.get_json()["user"]["profile_complete"] is False
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/check_session").get_json() == {"logged_in": False}

    invalid = client.post(
        "/api/login", json={"username": "alice", "password": "wrong-password"}
    )
    assert invalid.status_code == 401
    assert client.get("/api/check_session").get_json() == {"logged_in": False}

    valid = client.post(
        "/api/login", json={"username": "alice", "password": PASSWORD}
    )
    assert valid.status_code == 200
    assert valid.get_json()["user"]["username"] == "alice"

    session = client.get("/api/check_session")
    assert session.status_code == 200
    assert session.get_json()["logged_in"] is True
    assert session.get_json()["user"]["username"] == "alice"
    assert session.get_json()["user"]["onboarding_status"] == "new"

    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/check_session").get_json() == {"logged_in": False}
    assert client.get("/api/diet").status_code == 401


def test_profile_onboarding_state_transitions(client):
    register(client, "onboarding")
    initial = client.get("/api/profile")
    assert initial.status_code == 200
    assert initial.get_json()["onboarding_status"] == "new"
    assert set(initial.get_json()["profile_missing_fields"]) == {
        "goal", "activity_level", "age", "gender", "weight", "height",
    }

    partial = client.post("/api/profile", json={"goal": "perder peso", "height": "1,80"})
    assert partial.status_code == 200
    partial_data = partial.get_json()
    assert partial_data["profile"]["height"] == 180
    assert partial_data["onboarding_status"] == "incomplete"
    assert partial_data["profile_complete"] is False

    complete = client.post("/api/profile", json={
        "goal": "perder peso",
        "activity_level": "moderado",
        "age": 30,
        "gender": "masculino",
        "weight": 82,
        "height": "1.80",
        "timezone": "America/Sao_Paulo",
    })
    assert complete.status_code == 200
    assert complete.get_json()["onboarding_status"] == "complete"
    assert complete.get_json()["profile_complete"] is True
    assert complete.get_json()["profile_missing_fields"] == []
    assert client.get("/api/check_session").get_json()["user"]["profile_complete"] is True


def test_diet_crud_and_user_isolation(app, client):
    register(client, "alice")
    created = client.post(
        "/api/diet",
        json={
            "date": "2026-08-10",
            "meal_type": "Almoco",
            "description": "Arroz e feijao",
            "calories": 450,
        },
    )
    assert created.status_code == 201
    alice_entry_id = created.get_json()["entry"]["id"]

    bob = app.test_client()
    register(bob, "bob")
    bob_entry = bob.post(
        "/api/diet",
        json={
            "date": "2026-08-11",
            "meal_type": "Jantar",
            "description": "Sopa",
        },
    ).get_json()["entry"]

    entries = client.get("/api/diet").get_json()
    assert [entry["description"] for entry in entries] == ["Arroz e feijao"]

    updated = client.put(
        f"/api/diet/{alice_entry_id}",
        json={"description": "Arroz, feijao e salada", "protein": 20},
    )
    assert updated.status_code == 200
    assert updated.get_json()["entry"]["description"] == "Arroz, feijao e salada"
    assert updated.get_json()["entry"]["protein"] == 20

    assert client.put(
        f"/api/diet/{bob_entry['id']}", json={"description": "Invadido"}
    ).status_code == 404
    assert client.delete(f"/api/diet/{bob_entry['id']}").status_code == 404
    assert bob.get("/api/diet").get_json()[0]["description"] == "Sopa"

    assert client.delete(f"/api/diet/{alice_entry_id}").status_code == 200
    assert client.get("/api/diet").get_json() == []


def test_measurement_crud_and_user_isolation(app, client):
    register(client, "alice")
    created = client.post(
        "/api/measurements",
        json={"date": "2026-08-10", "weight": 72.5, "waist": 81},
    )
    assert created.status_code == 201
    alice_measurement_id = created.get_json()["measurement"]["id"]

    bob = app.test_client()
    register(bob, "bob")
    bob_measurement = bob.post(
        "/api/measurements",
        json={"date": "2026-08-11", "weight": 90, "notes": "Bob"},
    ).get_json()["measurement"]

    measurements = client.get("/api/measurements").get_json()
    assert len(measurements) == 1
    assert measurements[0]["weight"] == 72.5

    updated = client.put(
        f"/api/measurements/{alice_measurement_id}",
        json={"weight": 71.8, "body_fat": 18.2},
    )
    assert updated.status_code == 200
    assert updated.get_json()["measurement"]["weight"] == 71.8
    assert updated.get_json()["measurement"]["body_fat"] == 18.2

    assert client.put(
        f"/api/measurements/{bob_measurement['id']}", json={"weight": 1}
    ).status_code == 404
    assert client.delete(
        f"/api/measurements/{bob_measurement['id']}"
    ).status_code == 404
    assert bob.get("/api/measurements").get_json()[0]["weight"] == 90

    assert client.delete(
        f"/api/measurements/{alice_measurement_id}"
    ).status_code == 200
    assert client.get("/api/measurements").get_json() == []


def test_height_normalization_for_profile_and_measurements(client):
    register(client, "height-user")
    for raw, expected in (("190", 190), ("1.90", 190), ("1,90", 190), ("1.80", 180), ("1,80", 180)):
        response = client.post("/api/profile", json={"height": raw})
        assert response.status_code == 200
        assert response.get_json()["profile"]["height"] == expected

    measurement = client.post("/api/measurements", json={"date": "2026-08-10", "height": "1,80"})
    assert measurement.status_code == 201
    assert measurement.get_json()["measurement"]["height"] == 180

    invalid = client.post("/api/profile", json={"height": "abc"})
    assert invalid.status_code == 400


def test_stats_reports_latest_measurement_and_diet_counts(client):
    register(client, "alice")
    today = datetime.now(timezone.utc).date()
    old_date = today - timedelta(days=8)

    for entry_date, description in ((old_date, "Antiga"), (today, "Recente")):
        assert client.post(
            "/api/diet",
            json={
                "date": entry_date.isoformat(),
                "meal_type": "Lanche",
                "description": description,
            },
        ).status_code == 201

    assert client.post(
        "/api/measurements",
        json={"date": old_date.isoformat(), "weight": 75},
    ).status_code == 201
    assert client.post(
        "/api/measurements",
        json={"date": today.isoformat(), "weight": 73},
    ).status_code == 201

    response = client.get("/api/stats")
    assert response.status_code == 200
    stats = response.get_json()
    assert stats["total_diet_entries"] == 2
    assert stats["recent_diet_entries"] == 1
    assert stats["latest_measurement"]["date"] == today.isoformat()
    assert stats["latest_measurement"]["weight"] == 73
