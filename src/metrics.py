import hmac
import time
from datetime import datetime

from flask import Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import and_, func, or_

from src.models.user import AITask, BillingEvent, Subscription, db


HTTP_REQUESTS = Counter(
    "diet_tracker_http_requests_total",
    "HTTP requests handled by the application.",
    ("method", "endpoint", "status"),
)
HTTP_DURATION = Histogram(
    "diet_tracker_http_request_duration_seconds",
    "HTTP request duration by endpoint.",
    ("method", "endpoint"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
AI_JOBS = Gauge(
    "diet_tracker_ai_jobs",
    "Durable AI jobs stored in PostgreSQL.",
    ("operation", "status"),
)
AI_OLDEST_QUEUED = Gauge(
    "diet_tracker_ai_oldest_queued_seconds",
    "Age in seconds of the oldest queued AI job.",
)
ACTIVE_SUBSCRIPTIONS = Gauge(
    "diet_tracker_active_subscriptions",
    "Subscriptions that currently grant access.",
    ("plan_code",),
)
BILLING_EVENTS = Gauge(
    "diet_tracker_billing_events",
    "Billing webhook events retained for idempotency.",
    ("provider",),
)


def _refresh_operational_metrics():
    AI_JOBS.clear()
    for operation, status, count in db.session.query(
        AITask.operation, AITask.status, func.count(AITask.id)
    ).group_by(AITask.operation, AITask.status):
        AI_JOBS.labels(operation=operation, status=status).set(count)

    oldest = db.session.query(func.min(AITask.created_at)).filter_by(status="queued").scalar()
    AI_OLDEST_QUEUED.set(max(0, (datetime.utcnow() - oldest).total_seconds()) if oldest else 0)

    ACTIVE_SUBSCRIPTIONS.clear()
    now = datetime.utcnow()
    active = db.session.query(Subscription.plan_code, func.count(Subscription.id)).filter(or_(
        and_(
            Subscription.status.in_(("active", "trialing")),
            or_(
                and_(Subscription.provider == "admin", Subscription.current_period_end.is_(None)),
                Subscription.current_period_end > now,
            ),
        ),
        and_(Subscription.status == "canceled", Subscription.current_period_end > now),
    )).group_by(Subscription.plan_code)
    for plan_code, count in active:
        ACTIVE_SUBSCRIPTIONS.labels(plan_code=plan_code).set(count)

    BILLING_EVENTS.clear()
    for provider, count in db.session.query(
        BillingEvent.provider, func.count(BillingEvent.id)
    ).group_by(BillingEvent.provider):
        BILLING_EVENTS.labels(provider=provider).set(count)


def init_metrics(app):
    if not app.config.get("METRICS_ENABLED"):
        return

    @app.before_request
    def start_request_metrics():
        g.metrics_started_at = time.perf_counter()

    @app.after_request
    def finish_request_metrics(response):
        started_at = getattr(g, "metrics_started_at", None)
        if started_at is not None:
            endpoint = request.endpoint or "unmatched"
            HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=endpoint,
                status=str(response.status_code),
            ).inc()
            HTTP_DURATION.labels(method=request.method, endpoint=endpoint).observe(
                time.perf_counter() - started_at
            )
        return response

    @app.route("/metrics")
    def metrics():
        expected = str(app.config.get("METRICS_TOKEN") or "")
        authorization = request.headers.get("Authorization", "")
        received = authorization.removeprefix("Bearer ").strip()
        if not expected or not received or not hmac.compare_digest(expected, received):
            return {"error": "Não autorizado"}, 401
        _refresh_operational_metrics()
        return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)
