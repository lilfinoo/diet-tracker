from celery import Celery


celery_app = Celery("diet_tracker")
celery_app.flask_app = None


def init_celery(app):
    celery_app.flask_app = app
    celery_app.conf.update(
        broker_url=app.config.get("CELERY_BROKER_URL") or "memory://",
        broker_connection_retry_on_startup=True,
        task_serializer="json",
        accept_content=["json"],
        result_backend=None,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_transport_options={"visibility_timeout": app.config["AI_JOB_STALE_SECONDS"]},
        timezone="UTC",
        enable_utc=True,
    )
    app.extensions["celery"] = celery_app
    return celery_app
