import base64

from flask import jsonify

from src.models.user import User, db
from src.routes.common import premium_required
from tests.helpers import registration_payload


PHOTO = {"image": {"data": base64.b64encode(b"\xff\xd8\xffexample").decode(), "mime_type": "image/jpeg"}}


def signup(client):
    assert client.post("/api/register", json=registration_payload("free-user")).status_code == 201


def add_plan_routes(app):
    @app.post("/test/plan-a")
    @premium_required(allow_trial=True, trial_kind="plans")
    def plan_a():
        return jsonify({"plan": "workout"}), 201

    @app.post("/test/plan-b")
    @premium_required(allow_trial=True, trial_kind="plans")
    def plan_b():
        return jsonify({"plan": "diet"}), 201

    @app.post("/test/failed-plan")
    @premium_required(allow_trial=True, trial_kind="plans")
    def failed_plan():
        return jsonify({"error": "AI unavailable"}), 503


def test_plan_allowance_shared_lifetime_and_survives_relogin(app, client):
    add_plan_routes(app)
    signup(client)
    assert client.post("/test/plan-a").status_code == 201
    blocked = client.post("/test/plan-b")
    assert blocked.status_code == 403
    assert blocked.get_json()["quota_kind"] == "plans"
    assert client.post("/api/logout").status_code == 200
    assert client.post("/api/login", json={"username": "free-user", "password": "strong-password"}).status_code == 200
    assert client.get("/api/ai/usage").get_json()["plans"]["remaining"] == 0


def test_failed_generation_refunds_slot(app, client):
    add_plan_routes(app)
    signup(client)
    assert client.post("/test/failed-plan").status_code == 503
    assert client.get("/api/ai/usage").get_json()["plans"]["used"] == 0
    assert client.post("/test/plan-b").status_code == 201


def test_photos_separate_from_plan_and_failures_refunded(app, client, monkeypatch):
    add_plan_routes(app)
    signup(client)
    monkeypatch.setattr("src.routes.profile_routes.calculate_nutrition", lambda *args: {"calories": 100})
    invalid = {"image": {"data": "invalid", "mime_type": "image/jpeg"}}
    assert client.post("/api/diet/ai_macros", json=invalid).status_code == 400
    for _ in range(3):
        assert client.post("/api/diet/ai_macros", json=PHOTO).status_code == 200
    blocked = client.post("/api/diet/ai_macros", json=PHOTO)
    assert blocked.status_code == 403
    assert blocked.get_json()["quota_kind"] == "photos"
    assert client.post("/test/plan-a").status_code == 201
    usage = client.get("/api/ai/usage").get_json()
    assert usage["policy"] == "lifetime"
    assert usage["photos"] == {"used": 3, "limit": 3, "remaining": 0}
    assert usage["manual_logging"] is True


def test_free_text_ai_requires_premium_but_manual_macros_are_optional(app, client):
    signup(client)
    assert client.post("/api/diet/ai_macros", json={"description": "banana"}).status_code == 403
    assert client.get("/api/ai/usage").get_json()["photos"]["used"] == 0
    response = client.post("/api/diet", json={"date": "2026-10-09", "meal_type": "almoço", "description": "banana", "calories": 100})
    assert response.status_code == 201
    entries = client.get("/api/diet?date=2026-10-09").get_json()
    assert entries[0]["protein"] is None
    assert entries[0]["carbs"] is None
    assert entries[0]["fat"] is None


def test_other_account_has_own_allowance(app, client):
    add_plan_routes(app)
    signup(client)
    assert client.post("/test/plan-a").status_code == 201
    assert client.post("/api/logout").status_code == 200
    assert client.post("/api/register", json=registration_payload("second-free")).status_code == 201
    assert client.post("/test/plan-b").status_code == 201


def test_existing_legacy_total_does_not_infer_photo_usage(app, client):
    signup(client)
    with app.app_context():
        user = User.query.filter_by(username="free-user").one()
        user.ai_trial_uses = 3
        db.session.commit()
    assert client.get("/api/ai/usage").get_json()["photos"]["remaining"] == 3


def test_premium_does_not_spend_free_allowances(app, client):
    from src.models.user import Subscription
    add_plan_routes(app)
    signup(client)
    with app.app_context():
        user = User.query.filter_by(username="free-user").one()
        db.session.add(Subscription(user_id=user.id, provider="admin", external_subscription_id="free-allowance-test", status="active", plan_code="premium_student"))
        db.session.commit()
    for path in ("/test/plan-a", "/test/plan-b", "/test/plan-a"):
        assert client.post(path).status_code == 201
    usage = client.get("/api/ai/usage").get_json()
    assert usage["premium"] is True
    assert usage["plans"]["used"] == 0


def test_in_flight_plan_reservation_blocks_another_generation(app, client):
    add_plan_routes(app)
    observed = []
    other_client = app.test_client()

    @app.post("/test/held-plan")
    @premium_required(allow_trial=True, trial_kind="plans")
    def held_plan():
        # Interleave a second request before the first generation has returned.
        observed.append(other_client.post("/test/plan-b").status_code)
        return jsonify({"plan": "workout"}), 201

    signup(client)
    other_client.set_cookie("session", client.get_cookie("session").value)
    assert client.post("/test/held-plan").status_code == 201
    assert observed == [403]
    assert client.get("/api/ai/usage").get_json()["plans"]["used"] == 1
