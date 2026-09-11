import logging
from datetime import datetime, timedelta

from src.models.user import AITask, AnalyticsEvent, User, db
from src.services.privacy_cleanup import cleanup_expired_private_data
from src.services.privacy_logging import PrivacyLogFilter


def test_privacy_cleanup_expires_stale_inputs_and_enforces_retention(app):
    now = datetime.utcnow()
    with app.app_context():
        user = User(username="cleanup-user")
        user.set_password("strong-password")
        db.session.add(user)
        db.session.flush()
        stale = AITask(
            user_id=user.id,
            operation="chat",
            status="running",
            request_payload={"message": "private prompt"},
            request_image_data=b"private image",
            request_image_mime_type="image/jpeg",
            created_at=now - timedelta(hours=1),
        )
        expired = AITask(
            user_id=user.id,
            operation="chat",
            status="succeeded",
            request_payload={"message": "old prompt"},
            result={"answer": "old answer"},
            completed_at=now - timedelta(days=8),
        )
        recent = AITask(
            user_id=user.id,
            operation="chat",
            status="succeeded",
            request_payload={},
            completed_at=now - timedelta(days=1),
        )
        old_event = AnalyticsEvent(
            event_name="signup_started",
            created_at=now - timedelta(days=396),
        )
        recent_event = AnalyticsEvent(event_name="signup_started", created_at=now)
        db.session.add_all((stale, expired, recent, old_event, recent_event))
        db.session.commit()
        stale_id = stale.id
        recent_id = recent.id

        result = cleanup_expired_private_data(7, 395, 900)

        assert result == {
            "expired_ai_tasks": 1,
            "deleted_ai_tasks": 1,
            "deleted_analytics_events": 1,
        }
        stale = db.session.get(AITask, stale_id)
        assert stale.status == "failed"
        assert stale.request_payload == {}
        assert stale.request_image_data is None
        assert db.session.get(AITask, recent_id) is not None
        assert AnalyticsEvent.query.count() == 1


def test_privacy_log_filter_redacts_identifiers_and_preserves_formatting():
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "user=%s retries=%d password=%s path=%s",
        (
            "person@example.com/123e4567-e89b-42d3-a456-426614174000",
            2,
            "top-secret",
            "/api/invitations/raw-invitation-token/accept",
        ),
        None,
    )

    assert PrivacyLogFilter().filter(record) is True
    message = record.getMessage()
    assert "person@example.com" not in message
    assert "123e4567-e89b-42d3-a456-426614174000" not in message
    assert "top-secret" not in message
    assert "raw-invitation-token" not in message
    assert "retries=2" in message
