from datetime import datetime, timedelta

from src.models.user import AITask, AnalyticsEvent, db


def cleanup_expired_private_data(ai_retention_days, analytics_retention_days, stale_seconds):
    now = datetime.utcnow()
    stale_before = now - timedelta(seconds=stale_seconds)
    stale_tasks = AITask.query.filter(
        AITask.status.in_(("queued", "running")),
        AITask.created_at < stale_before,
    ).all()
    for task in stale_tasks:
        task.status = "failed"
        task.http_status = 503
        task.error = "Tarefa expirada antes da conclusão."
        task.result = {"error": task.error}
        task.completed_at = now
        task.request_payload = {}
        task.request_image_data = None
        task.request_image_mime_type = None

    completed_before = now - timedelta(days=ai_retention_days)
    deleted_tasks = AITask.query.filter(
        AITask.status.in_(("succeeded", "failed")),
        AITask.completed_at < completed_before,
    ).delete(synchronize_session=False)
    analytics_before = now - timedelta(days=analytics_retention_days)
    deleted_events = AnalyticsEvent.query.filter(
        AnalyticsEvent.created_at < analytics_before
    ).delete(synchronize_session=False)
    db.session.commit()
    return {
        "expired_ai_tasks": len(stale_tasks),
        "deleted_ai_tasks": deleted_tasks,
        "deleted_analytics_events": deleted_events,
    }
