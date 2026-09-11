from datetime import datetime, timedelta
from pathlib import Path
import uuid

from src.models.user import (
    AnalyticsEvent,
    BillingCheckout,
    DietPlan,
    User,
    UserProfile,
    WorkoutDay,
    WorkoutExercise,
    WorkoutPlan,
    db,
)
from tests.helpers import registration_payload


ANONYMOUS_ID = "123e4567-e89b-42d3-a456-426614174000"
OTHER_ANONYMOUS_ID = "223e4567-e89b-42d3-a456-426614174000"


def register(client, username="analytics-user", analytics=None):
    payload = registration_payload(username)
    if analytics is not None:
        payload["analytics"] = analytics
    return client.post("/api/register", json=payload)


def event_payload(name="signup_started", anonymous_id=ANONYMOUS_ID, properties=None, **extra):
    event = {
        "name": name,
        "anonymous_id": anonymous_id,
        "properties": properties or {},
        **extra,
    }
    return {"events": [event]}


def test_anonymous_events_and_authenticated_attribution_do_not_trust_client_user_id(app, client):
    anonymous = client.post(
        "/api/analytics/events",
        json=event_payload(properties={"surface": "landing"}, user_id=str(uuid.uuid4())),
    )
    assert anonymous.status_code == 202

    assert register(client).status_code == 201
    attributed = client.post(
        "/api/analytics/events",
        json=event_payload(
            name="paywall_viewed",
            properties={"surface": "plans_modal"},
            user_id=str(uuid.uuid4()),
        ),
    )
    assert attributed.status_code == 202

    with app.app_context():
        user = User.query.filter_by(username="analytics-user").one()
        anonymous_event = AnalyticsEvent.query.filter_by(
            event_name="signup_started", properties={"surface": "landing"}
        ).one()
        attributed_event = AnalyticsEvent.query.filter_by(event_name="paywall_viewed").one()
        assert anonymous_event.subject_id is None
        assert anonymous_event.anonymous_id == ANONYMOUS_ID
        assert attributed_event.subject_id == user.analytics_subject_id
        assert attributed_event.properties == {"surface": "plans_modal"}


def test_ingestion_validates_names_ids_properties_and_batch_size(app, client):
    invalid_payloads = [
        event_payload(name="not_allowed"),
        event_payload(name=["signup_started"]),
        event_payload(anonymous_id="browser-1"),
        event_payload(anonymous_id="00000000-0000-0000-0000-000000000000"),
        event_payload(properties={"nested": {"email": "person@example.com"}}),
        {"events": [event_payload()["events"][0]] * 21},
    ]
    for payload in invalid_payloads:
        assert client.post("/api/analytics/events", json=payload).status_code == 400

    oversized = event_payload(properties={"label": "x" * 501})
    assert client.post("/api/analytics/events", json=oversized).status_code == 400
    with app.app_context():
        assert AnalyticsEvent.query.count() == 0


def test_public_ingestion_rejects_server_authoritative_events(app, client):
    for event_name in ("meal_logged", "checkout_started", "subscription_activated"):
        assert client.post(
            "/api/analytics/events",
            json=event_payload(name=event_name),
        ).status_code == 400
    with app.app_context():
        assert AnalyticsEvent.query.count() == 0


def test_signup_completed_keeps_valid_first_touch_utm_payload(app, client):
    response = register(client, analytics={
        "anonymous_id": ANONYMOUS_ID,
        "utm_source": "newsletter",
        "utm_medium": "email",
        "utm_campaign": "august_launch",
        "email": "must-not-be-recorded@example.com",
    })
    assert response.status_code == 201

    with app.app_context():
        user = User.query.filter_by(username="analytics-user").one()
        event = AnalyticsEvent.query.filter_by(event_name="signup_completed").one()
        assert event.subject_id == user.analytics_subject_id
        assert event.anonymous_id == ANONYMOUS_ID
        assert event.properties == {
            "utm_source": "newsletter",
            "utm_medium": "email",
            "utm_campaign": "august_launch",
        }


def test_frontend_analytics_loads_before_app_and_uses_first_touch_storage():
    root = Path(__file__).parents[1]
    index = (root / "copilot" / "index.html").read_text()
    source = (root / "copilot" / "js" / "analytics.js").read_text()
    assert index.index('src="/js/analytics.js') < index.index('src="/script.js')
    assert "dt_analytics_anonymous_id" in source
    assert "dt_analytics_first_touch" in source
    assert source.index("const stored = storageGet(FIRST_TOUCH_KEY)") < source.index("new URLSearchParams")
    assert all(field in source for field in ("utm_source", "utm_medium", "utm_campaign"))


def test_frontend_instruments_plan_surface_and_blocked_premium_access():
    root = Path(__file__).parents[1]
    app_source = (root / "copilot" / "script.js").read_text()
    plan_source = (root / "copilot" / "js" / "plans.js").read_text()

    assert 'surface: professionalWizardContext ? "professional" : "self_service"' in plan_source
    assert "window.analytics?.track('paywall_viewed', { surface: 'plans_modal' })" in app_source
    premium_guard = app_source.split("function requireAuth", 1)[1].split("function hasAiAccess", 1)[0]
    assert "openPlansModal();" in premium_guard


def test_return_events_are_age_checked_and_deduplicated_per_browser_and_user(app, client):
    assert register(client).status_code == 201
    early = client.post(
        "/api/analytics/events",
        json=event_payload(name="returned_d7"),
    )
    assert early.status_code == 400

    with app.app_context():
        user = User.query.filter_by(username="analytics-user").one()
        user.created_at = datetime.utcnow() - timedelta(days=8)
        db.session.commit()

    payload = event_payload(name="returned_d7", properties={"account_age_days": 8})
    assert client.post("/api/analytics/events", json=payload).status_code == 202
    duplicate = client.post("/api/analytics/events", json=payload)
    assert duplicate.status_code == 202
    assert duplicate.get_json()["accepted"] == 0
    assert client.post(
        "/api/analytics/events",
        json=event_payload(name="returned_d7", anonymous_id=OTHER_ANONYMOUS_ID),
    ).status_code == 202

    with app.app_context():
        assert AnalyticsEvent.query.filter_by(event_name="returned_d7").count() == 2


def test_authoritative_meal_and_workout_events_are_emitted_once(app, client):
    assert register(client).status_code == 201
    meal = client.post("/api/diet", json={
        "date": "2026-08-29",
        "meal_type": "Almoço",
        "description": "Arroz e feijão",
    })
    assert meal.status_code == 201

    with app.app_context():
        user = User.query.filter_by(username="analytics-user").one()
        plan = WorkoutPlan(user_id=user.id, title="Treino", status="published", source="manual")
        db.session.add(plan)
        db.session.flush()
        day = WorkoutDay(workout_plan_id=plan.id, code="A", title="Treino A", order=1)
        db.session.add(day)
        db.session.flush()
        exercise = WorkoutExercise(
            workout_plan_id=plan.id,
            workout_day_id=day.id,
            name="Agachamento",
            order=1,
        )
        db.session.add(exercise)
        db.session.commit()
        plan_id, day_id, exercise_id = plan.id, day.id, exercise.id

    started = client.post(f"/api/workout_plans/{plan_id}/days/{day_id}/sessions")
    assert started.status_code == 201
    session_id = started.get_json()["session"]["id"]
    assert client.post(
        f"/api/workout_sessions/{session_id}/exercises/{exercise_id}/complete"
    ).status_code == 200
    assert client.post(
        f"/api/workout_sessions/{session_id}/exercises/{exercise_id}/complete"
    ).status_code == 200
    assert client.post(f"/api/workout_sessions/{session_id}/finish").status_code == 200
    assert client.post(f"/api/workout_sessions/{session_id}/finish").status_code == 200

    with app.app_context():
        assert AnalyticsEvent.query.filter_by(event_name="meal_logged").count() == 1
        assert AnalyticsEvent.query.filter_by(event_name="workout_started").count() == 1
        assert AnalyticsEvent.query.filter_by(event_name="exercise_completed").count() == 1
        assert AnalyticsEvent.query.filter_by(event_name="workout_finished").count() == 1


def test_current_plan_event_is_server_authoritative(app, client):
    assert register(client).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="analytics-user").one()
        plan = DietPlan(user_id=user.id, title="Dieta atual", status="published", source="manual")
        db.session.add(plan)
        db.session.commit()
        plan_id = plan.id

    assert client.put(f"/api/diet_plans/{plan_id}/current").status_code == 200
    with app.app_context():
        event = AnalyticsEvent.query.filter_by(event_name="plan_set_current").one()
        assert event.properties == {"plan_type": "diet"}


def test_profile_completion_is_emitted_once_even_when_profile_already_exists(app, client):
    assert register(client).status_code == 201
    with app.app_context():
        user = User.query.filter_by(username="analytics-user").one()
        db.session.add(UserProfile(user_id=user.id))
        db.session.commit()

    assert client.post("/api/profile", json={"goal": "ganhar massa muscular"}).status_code == 200
    assert client.post("/api/profile", json={"goal": "manter peso"}).status_code == 200
    with app.app_context():
        assert AnalyticsEvent.query.filter_by(event_name="profile_completed").count() == 1


def test_checkout_and_subscription_activation_events_follow_server_success(app, client, monkeypatch):
    app.config["ASAAS_API_KEY"] = "test-asaas-key"
    app.config["BILLING_ENABLED"] = True
    monkeypatch.setattr(
        "src.routes.billing_routes.create_checkout",
        lambda plan, payment_method, public_base_url, external_reference: {
            "id": "analytics-checkout",
            "link": "https://example.test/analytics-checkout",
        },
    )
    assert register(client).status_code == 201
    checkout_response = client.post(
        "/api/billing/checkout",
        json={"plan_code": "premium_student", "payment_method": "credit_card"},
    )
    assert checkout_response.status_code == 201

    webhook = client.post(
        "/api/webhooks/asaas",
        headers={"asaas-access-token": "test-webhook-token-0123456789abcdef"},
        json={
            "id": "analytics-subscription-created",
            "event": "SUBSCRIPTION_CREATED",
            "subscription": {
                "id": "analytics-subscription",
                "status": "ACTIVE",
                "checkoutSession": "analytics-checkout",
                "nextDueDate": "2026-09-29",
            },
        },
    )
    assert webhook.status_code == 200

    with app.app_context():
        checkout = BillingCheckout.query.one()
        checkout_event = AnalyticsEvent.query.filter_by(event_name="checkout_started").one()
        user = db.session.get(User, checkout.user_id)
        assert AnalyticsEvent.query.filter_by(event_name="subscription_activated").count() == 0
        assert checkout_event.subject_id == user.analytics_subject_id
        assert checkout_event.properties["plan_code"] == "premium_student"

    monkeypatch.setattr(
        "src.routes.billing_routes.fetch_asaas_subscription",
        lambda subscription_id: {
            "id": subscription_id,
            "status": "ACTIVE",
            "nextDueDate": "2026-09-29",
        },
    )
    paid = client.post(
        "/api/webhooks/asaas",
        headers={"asaas-access-token": "test-webhook-token-0123456789abcdef"},
        json={
            "id": "analytics-payment-received",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": "analytics-payment",
                "subscription": "analytics-subscription",
                "status": "RECEIVED",
                "paymentDate": "2026-08-29",
            },
        },
    )
    assert paid.status_code == 200
    with app.app_context():
        activation_event = AnalyticsEvent.query.filter_by(event_name="subscription_activated").one()
        user = User.query.filter_by(username="analytics-user").one()
        assert activation_event.subject_id == user.analytics_subject_id
