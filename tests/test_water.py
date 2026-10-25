import pytest

from src.models.user import IdempotentOperation, User, UserProfile, WaterEntry, db
from tests.helpers import registration_payload


def signup(client, name="water-owner"):
    assert client.post("/api/register", json=registration_payload(name)).status_code == 201
    assert client.post("/api/profile", json={"timezone": "America/Sao_Paulo"}).status_code == 200


def drink(client, amount=200, key="first-water", when="2026-01-02T02:30:00Z"):
    return client.post("/api/water", json={"amount_ml": amount, "occurred_at": when},
                       headers={"Idempotency-Key": key})


def test_water_totals_bottle_and_individual_undo(app, client):
    signup(client)
    assert client.get("/api/water").json["total_ml"] == 0
    bottle = client.post("/api/water/bottle", json={"bottle_capacity_ml": 750})
    assert bottle.json["bottle_capacity_ml"] == 750
    assert bottle.json["entries"] == []
    first = drink(client)
    assert first.status_code == 201
    drink(client, 300, "second-water")
    third = drink(client, 750, "bottle-water")
    assert third.json["total_ml"] == 1250
    assert third.json["date"] == "2026-01-01"
    assert third.json["timezone"] == "America/Sao_Paulo"
    assert third.json["entry"]["occurred_at"].endswith("Z")
    changed = client.post("/api/water/bottle", json={"bottle_capacity_ml": 500})
    assert changed.status_code == 200
    day = client.get("/api/water?date=2026-01-01").json
    assert day["total_ml"] == 1250
    assert day["bottle_capacity_ml"] == 500
    undone = client.delete(f'/api/water/{first.json["entry"]["id"]}')
    assert undone.json["total_ml"] == 1050
    assert len(undone.json["entries"]) == 2
    with app.app_context():
        assert WaterEntry.query.count() == 2


def test_water_retry_survives_undo_and_does_not_recreate_drink(app, client):
    signup(client)
    first = drink(client)
    replay = drink(client)
    assert replay.json == first.json
    assert replay.status_code == 201
    client.delete(f'/api/water/{first.json["entry"]["id"]}')
    assert drink(client).json == first.json
    assert client.get("/api/water?date=2026-01-01").json["total_ml"] == 0
    with app.app_context():
        assert WaterEntry.query.count() == 0
        assert IdempotentOperation.query.count() == 1


def test_water_day_uses_profile_timezone_and_preserves_day_when_timezone_changes(client):
    signup(client)
    assert drink(client).json["date"] == "2026-01-01"
    after_midnight = drink(client, 300, "after-midnight", "2026-01-02T03:01:00Z")
    assert after_midnight.json["date"] == "2026-01-02"
    assert after_midnight.json["total_ml"] == 300
    client.post("/api/profile", json={"timezone": "Asia/Tokyo"})
    assert client.get("/api/water?date=2026-01-01").json["total_ml"] == 200
    assert drink(client).json["date"] == "2026-01-01"


def test_water_is_private_to_each_account(app, client):
    signup(client)
    first = drink(client)
    other = app.test_client()
    signup(other, "water-other")
    assert other.get("/api/water?date=2026-01-01").json["total_ml"] == 0
    assert other.delete(f'/api/water/{first.json["entry"]["id"]}').status_code == 404
    assert drink(other, 300).json["total_ml"] == 300
    assert client.get("/api/water?date=2026-01-01").json["total_ml"] == 200


@pytest.mark.parametrize("value", [None, True, False, 0, -200, 10001, 1.5, "300", {}, []])
def test_water_rejects_invalid_amount_and_bottle(client, value):
    signup(client)
    assert drink(client, value).status_code == 400
    assert client.post("/api/water/bottle", json={"bottle_capacity_ml": value}).status_code == 400


@pytest.mark.parametrize("when", [None, "bad", "2026-01-01T10:00:00", "2999-01-01T00:00:00Z", 123, {}])
def test_water_rejects_ambiguous_or_future_time(client, when):
    signup(client)
    assert drink(client, when=when).status_code == 400


def test_water_requires_auth_csrf_and_valid_key(app, client):
    assert client.get("/api/water").status_code == 401
    assert drink(client).status_code == 401
    signup(client)
    assert client.post("/api/water", json={"amount_ml": 200}).status_code == 400
    assert drink(client, key="x" * 129).status_code == 400
    app.config["CSRF_PROTECTION"] = True
    assert drink(client).status_code == 403
    assert client.post("/api/water/bottle", json={"bottle_capacity_ml": 750}).status_code == 403


def test_water_rejects_invalid_date_and_key_from_another_operation(app, client):
    signup(client)
    assert client.get("/api/water?date=20260101").status_code == 400
    assert client.get("/api/water?date=2026-02-30").status_code == 400
    with app.app_context():
        db.session.add(IdempotentOperation(user_id=User.query.one().id, idempotency_key="used-key",
                       method="POST", path="/api/elsewhere", status_code=200, response_payload={}))
        db.session.commit()
    assert drink(client, key="used-key").status_code == 409


def test_water_entry_and_receipt_share_transaction(app, client, monkeypatch):
    signup(client)
    with app.app_context():
        original_commit = db.session.commit
        seen = []

        def check_commit():
            assert WaterEntry.query.count() == 1
            assert IdempotentOperation.query.count() == 1
            seen.append(True)
            original_commit()

        monkeypatch.setattr(db.session, "commit", check_commit)
        assert drink(client).status_code == 201
        assert seen == [True]


def test_account_deletion_removes_water_and_bottle(app, client):
    signup(client)
    drink(client)
    client.post("/api/water/bottle", json={"bottle_capacity_ml": 750})
    result = client.delete("/api/account", json={"username": "water-owner", "password": "strong-password", "confirm_delete": True})
    assert result.status_code == 200
    with app.app_context():
        assert WaterEntry.query.count() == 0
        assert UserProfile.query.count() == 0
        assert IdempotentOperation.query.count() == 0


def test_water_mutations_work_with_authenticated_csrf_session(app, client):
    app.config["CSRF_PROTECTION"] = True
    registered = client.post("/api/register", json=registration_payload("water-csrf"))
    token = registered.json["csrf_token"]
    headers = {"X-CSRF-Token": token, "Idempotency-Key": "native-water"}
    bottle = client.post("/api/water/bottle", headers=headers, json={"bottle_capacity_ml": 750})
    assert bottle.status_code == 200
    added = client.post("/api/water", headers=headers, json={"amount_ml": 250})
    assert added.status_code == 201
    assert added.json["total_ml"] == 250
    assert client.get("/api/water").json["total_ml"] == 250
    assert client.post("/api/water", headers=headers, json={"amount_ml": 250}).json == added.json
    removed = client.delete(f'/api/water/{added.json["entry"]["id"]}', headers=headers)
    assert removed.status_code == 200
    assert removed.json["total_ml"] == 0
