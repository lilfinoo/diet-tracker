from datetime import datetime, timedelta
from uuid import UUID

from src.models.user import AnalyticsEvent, User, db
from src.services.analytics import paywall_assignment, paywall_report, record_event, record_payment_confirmed
from tests.helpers import registration_payload


def enroll(client, surface="photos"):
    return client.post("/api/analytics/paywall", json={"surface": surface, "platform": "web"})


def test_assignment_is_stable_and_split():
    assignments = [paywall_assignment(UUID(int=value)) for value in range(100)]
    assert {item["variant"] for item in assignments} == {"A", "B"}
    assert assignments == [paywall_assignment(UUID(int=value)) for value in range(100)]


def test_enrollment_is_authenticated_persistent_and_excludes_premium(app, client):
    assert enroll(client).status_code == 401
    assert client.post("/api/register", json=registration_payload("paywall-user")).status_code == 201
    first = enroll(client).get_json()["experiment"]
    assert first["variant"] in {"A", "B"}
    assert enroll(client, "chat").get_json()["experiment"] == first
    with client.session_transaction() as session:
        user_id = session["user_id"]
    other_device = app.test_client()
    with other_device.session_transaction() as session:
        session["user_id"] = user_id
    assert enroll(other_device).get_json()["experiment"] == first
    with app.app_context():
        assert AnalyticsEvent.query.filter_by(event_name="paywall_experiment_enrolled").count() == 1
        user = db.session.get(User, user_id)
        user.is_premium = True
        db.session.commit()
    db.session.expire_all()
    assert enroll(client).get_json()["experiment"] is None


def test_enrollment_validates_context_and_admin_is_excluded(app, client):
    client.post("/api/register", json=registration_payload("paywall-admin"))
    assert enroll(client, "private-user-text").status_code == 400
    with app.app_context():
        user = User.query.filter_by(username="paywall-admin").one()
        user.is_admin = True
        db.session.commit()
    db.session.expire_all()
    assert enroll(client).get_json()["experiment"] is None
    with app.app_context():
        assert not AnalyticsEvent.query.filter_by(event_name="paywall_experiment_enrolled").count()


def test_server_attributes_client_and_payment_events_and_rejects_fake_payment(app, client):
    client.post("/api/register", json=registration_payload("paywall-attribution"))
    experiment = enroll(client).get_json()["experiment"]
    event = {"name": "paywall_viewed", "anonymous_id": "123e4567-e89b-42d3-a456-426614174000",
             "properties": {"surface": "photos", "experiment_id": "fake", "variant": "fake"}}
    assert client.post("/api/analytics/events", json={"events": [event]}).status_code == 202
    event["name"] = "subscription_payment_confirmed"
    assert client.post("/api/analytics/events", json={"events": [event]}).status_code == 400
    with app.app_context():
        user = User.query.filter_by(username="paywall-attribution").one()
        viewed = AnalyticsEvent.query.filter_by(event_name="paywall_viewed").one()
        assert viewed.properties == {"surface": "photos", **experiment}
        for _ in range(2):
            record_payment_confirmed(user.id, "premium_student", "asaas", "confirmed-payment")
            db.session.commit()
        paid = AnalyticsEvent.query.filter_by(event_name="subscription_payment_confirmed").one()
        assert paid.properties == {"plan_code": "premium_student", "provider": "asaas", **experiment}


def test_report_uses_enrollment_cohort_and_complete_windows(app, client):
    client.post("/api/register", json=registration_payload("paywall-cohort"))
    experiment = enroll(client).get_json()["experiment"]
    now = datetime.utcnow()
    with app.app_context():
        user = User.query.filter_by(username="paywall-cohort").one()
        enrollment = AnalyticsEvent.query.filter_by(event_name="paywall_experiment_enrolled").one()
        enrollment.created_at = now - timedelta(days=35)
        for name, days in [("paywall_viewed", 34), ("checkout_started", 34),
                           ("subscription_payment_confirmed", 33), ("meal_logged", 27)]:
            record_event(name, user_id=user.id).created_at = now - timedelta(days=days)
        # Historical native restore and late payments cannot increase this cohort's conversion.
        record_event("subscription_payment_confirmed", user_id=user.id).created_at = now - timedelta(days=40)
        record_event("subscription_payment_confirmed", user_id=user.id).created_at = now - timedelta(days=1)
        db.session.commit()
        report = paywall_report((now - timedelta(days=36)).date(), (now - timedelta(days=34)).date())
        row = next(row for row in report["variants"] if row["variant"] == experiment["variant"])
        assert (row["users"], row["viewed"], row["checkout"], row["paid"], row["mature_30"], row["paid_30"], row["retained_d7"]) == (1, 1, 1, 1, 1, 1, 1)
        enrollment.created_at = now - timedelta(days=1)
        db.session.commit()
        report = paywall_report((now - timedelta(days=2)).date(), now.date())
        row = next(row for row in report["variants"] if row["variant"] == experiment["variant"])
        assert row["mature_30"] == row["eligible_d7"] == row["paid_30"] == 0


def test_admin_report_requires_admin(client):
    assert client.get("/api/admin/analytics").status_code == 401
    client.post("/api/register", json=registration_payload("paywall-regular"))
    assert client.get("/api/admin/analytics").status_code == 403


def test_paywall_endpoint_keeps_csrf_and_admin_can_read_results(app, client):
    client.post("/api/register", json=registration_payload("paywall-csrf"))
    app.config["CSRF_PROTECTION"] = True
    assert enroll(client).status_code == 403
    session = client.get("/api/check_session").get_json()
    response = client.post("/api/analytics/paywall", json={"surface": "app_open", "platform": "ios"},
                           headers={"X-CSRF-Token": session["csrf_token"]})
    assert response.status_code == 200
    user = User.query.filter_by(username="paywall-csrf").one()
    user.is_admin = True
    db.session.commit()
    response = client.get("/api/admin/analytics")
    assert response.status_code == 200
    assert {row["variant"] for row in response.get_json()["paywall_experiment"]["variants"]} == {"A", "B"}
