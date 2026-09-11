from src.models.user import AITask, User, db
from src.services.ai_queue import execute_ai_job
from src.services.rate_limit import rate_limit
from tests.helpers import registration_payload


def _premium_user(app, client, username="queued-user"):
    assert client.post("/api/register", json=registration_payload(username)).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.is_premium = True
        db.session.commit()
        return user.id


def test_paid_ai_request_is_queued_and_visible_only_to_owner(app, client, monkeypatch):
    user_id = _premium_user(app, client)
    app.config["AI_ASYNC_ENABLED"] = True
    queued = []
    monkeypatch.setattr(
        execute_ai_job,
        "apply_async",
        lambda args: queued.append(args[0]),
    )

    response = client.post("/api/diet/ai_macros", json={"description": "100g de arroz"})

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["status"] == "queued"
    assert queued == [payload["job_id"]]
    status = client.get(payload["status_url"])
    assert status.status_code == 200
    assert status.get_json()["operation"] == "nutrition_macros"
    with app.app_context():
        task = db.session.get(AITask, payload["job_id"])
        assert task.user_id == user_id
        assert task.request_payload == {"description": "100g de arroz"}

    assert client.post("/api/logout").status_code == 200
    assert client.post(
        "/api/register", json=registration_payload("other-user")
    ).status_code == 201
    assert client.get(payload["status_url"]).status_code == 404


def test_worker_completes_durable_nutrition_job(app, client, monkeypatch):
    user_id = _premium_user(app, client, "worker-user")
    with app.app_context():
        task = AITask(
            user_id=user_id,
            operation="nutrition_macros",
            request_payload={"description": "banana"},
        )
        db.session.add(task)
        db.session.commit()
        task_id = str(task.id)

    monkeypatch.setattr(
        "src.routes.profile_routes.calculate_nutrition",
        lambda *args: {"calories": 90, "protein": 1, "carbs": 23, "fat": 0},
    )
    execute_ai_job.run(task_id)

    with app.app_context():
        task = db.session.get(AITask, task_id)
        assert task.status == "succeeded"
        assert task.http_status == 200
        assert task.result["calories"] == 90
        assert task.request_payload == {}


def test_metrics_require_bearer_token_and_expose_operational_series(client):
    assert client.get("/metrics").status_code == 401
    response = client.get(
        "/metrics", headers={"Authorization": "Bearer test-metrics-token"}
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "diet_tracker_http_requests_total" in body
    assert "diet_tracker_ai_oldest_queued_seconds" in body
    assert "diet_tracker_active_subscriptions" in body


def test_rate_limit_uses_shared_redis_counter(app, client, monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.count = 0

        def eval(self, *_args):
            self.count += 1
            return self.count

    fake_redis = FakeRedis()
    app.config["REDIS_URL"] = "redis://shared.example/0"
    monkeypatch.setattr("src.services.rate_limit._redis_client", lambda _url: fake_redis)

    @app.route("/test-shared-rate-limit")
    @rate_limit("test-shared", 1, 60)
    def limited():
        return {"ok": True}

    assert client.get("/test-shared-rate-limit").status_code == 200
    assert client.get("/test-shared-rate-limit").status_code == 429
