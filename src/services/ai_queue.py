import base64
import inspect
import uuid
from datetime import datetime, timedelta

from celery.exceptions import OperationalError
from flask import current_app, g, jsonify, request
from werkzeug.exceptions import HTTPException
from sqlalchemy import and_, or_

from src.celery_app import celery_app
from src.models.user import AITask, ChatMessage, DietPlan, User, WorkoutPlan, db


def plan_background_ready():
    return bool(
        current_app.config.get("AI_PLAN_BACKGROUND_ENABLED", False)
        and current_app.config.get("AI_ASYNC_ENABLED")
        and current_app.config.get("CELERY_BROKER_URL")
    )


def should_enqueue_ai():
    return bool(
        current_app.config.get("AI_ASYNC_ENABLED")
        and not getattr(g, "ai_worker_execution", False)
        and g.user.has_entitlement("premium")
    )


def enqueue_ai_request(operation, payload, route_params=None):
    background_plan = (operation in {"diet_plan", "workout_plan"}
                       and request.headers.get("X-AI-Background") == "plans"
                       and plan_background_ready())
    if getattr(g, "ai_worker_execution", False):
        return None
    if not background_plan and not should_enqueue_ai():
        return None

    stored_payload = dict(payload)
    image_data = None
    image_mime_type = None
    image = stored_payload.get("image")
    if isinstance(image, dict) and image.get("data"):
        image = dict(image)
        image_data = base64.b64decode(image.pop("data"), validate=True)
        image_mime_type = image.get("mime_type")
        stored_payload["image"] = image

    metadata = {key: str(value) for key, value in (route_params or {}).items()}
    metadata["_ai_providers"] = request.headers.get("X-AI-Providers", "")
    request_key = request.headers.get("Idempotency-Key") if background_plan else None
    if request_key:
        # Serialize the durable receipt for concurrent retries on PostgreSQL.
        User.query.filter_by(id=g.user.id).with_for_update().first()
        existing = AITask.query.filter(
            AITask.user_id == g.user.id, AITask.operation == operation,
            AITask.route_params["_request_key"].as_string() == request_key,
        ).first()
        if existing:
            db.session.commit()
            return jsonify({"job_id": str(existing.id), "status": existing.status,
                            "status_url": f"/api/ai/tasks/{existing.id}"}), 202
        metadata["_request_key"] = request_key
    if background_plan and not g.user.has_entitlement("premium"):
        metadata["_free_plan_reserved"] = True
    task = AITask(
        user_id=g.user.id,
        operation=operation,
        request_payload=stored_payload,
        request_image_data=image_data,
        request_image_mime_type=image_mime_type,
        route_params=metadata,
    )
    db.session.add(task)
    db.session.commit()
    try:
        execute_ai_job.apply_async(args=[str(task.id)])
    except (OperationalError, ConnectionError, OSError):
        current_app.logger.exception("Unable to enqueue AI task %s", task.id)
        message = "A fila de IA está temporariamente indisponível."
        # The request decorator refunds the reservation when enqueueing fails.
        task.route_params = {key: value for key, value in task.route_params.items()
                             if key != "_free_plan_reserved"}
        _fail(task, message)
        return jsonify({"error": message}), 503

    response = jsonify({
        "job_id": str(task.id),
        "status": "queued",
        "status_url": f"/api/ai/tasks/{task.id}",
    })
    response.status_code = 202
    response.headers["Location"] = f"/api/ai/tasks/{task.id}"
    response.headers["Retry-After"] = "2"
    return response


def _handler_for(operation):
    from src.routes.plan_routes import (
        chat,
        create_guided_diet_plan,
        create_guided_workout_plan,
        suggest_diet_day,
    )
    from src.routes.profile_routes import get_ai_macros
    from src.routes.professional_routes import generate_professional_workout

    return {
        "chat": chat,
        "nutrition_macros": get_ai_macros,
        "diet_plan": create_guided_diet_plan,
        "workout_plan": create_guided_workout_plan,
        "professional_workout_plan": generate_professional_workout,
        "diet_day": suggest_diet_day,
    }.get(operation)


def _existing_result(task):
    if task.operation == "chat":
        message = ChatMessage.query.filter_by(ai_task_id=task.id).first()
        if message:
            return {"response": message.response, "action": None}, 200
    elif task.operation == "diet_plan":
        plan = DietPlan.query.filter_by(ai_task_id=task.id).first()
        if plan:
            return {
                "message": "Plano alimentar criado.",
                "plan_id": plan.id,
                "plan": plan.to_dict_full(),
            }, 201
    elif task.operation in {"workout_plan", "professional_workout_plan"}:
        plan = WorkoutPlan.query.filter_by(ai_task_id=task.id).first()
        if plan:
            return {
                "message": "Plano de treino criado.",
                "plan_id": plan.id,
                "plan": plan.to_dict_full(),
            }, 201
    return None


def _complete(task, result, status):
    was_pending = task.status in {"queued", "running"}
    task.status = "succeeded" if 200 <= status < 300 else "failed"
    if was_pending and task.status == "failed" and (task.route_params or {}).get("_free_plan_reserved"):
        column = User.free_workout_plan_uses if task.operation == "workout_plan" else User.free_diet_plan_uses
        User.query.filter(User.id == task.user_id, column > 0).update(
            {column: column - 1}, synchronize_session=False,
        )
        User.query.filter(User.id == task.user_id, User.ai_trial_uses > 0).update(
            {User.ai_trial_uses: User.ai_trial_uses - 1}, synchronize_session=False,
        )
    task.result = current_app.json.loads(current_app.json.dumps(result))
    task.http_status = status
    task.error = result.get("error") if task.status == "failed" and isinstance(result, dict) else None
    task.completed_at = datetime.utcnow()
    task.request_payload = {}
    task.request_image_data = None
    task.request_image_mime_type = None
    db.session.commit()
    if was_pending and task.status == "succeeded":
        from src.services.push_notifications import notify_plan_ready
        notify_plan_ready(task)


def _fail(task, message, status=503):
    _complete(task, {"error": message}, status)


@celery_app.task(bind=True, max_retries=None, name="diet_tracker.execute_ai_job")
def execute_ai_job(self, task_id):
    app = celery_app.flask_app
    if app is None:
        raise RuntimeError("Celery has not been initialized with the Flask application")

    with app.app_context():
        task = db.session.get(AITask, uuid.UUID(str(task_id)))
        if task is None or task.status in {"succeeded", "failed"}:
            return
        if task.operation == "professional_workout_plan":
            user = db.session.get(User, task.user_id)
            if not user or user.is_banned or not user.has_current_ai_consent() or not user.has_entitlement("workout"):
                _fail(task, "A autorização profissional para executar esta tarefa não está mais válida.", 403)
                return

        existing = _existing_result(task)
        if existing:
            _complete(task, *existing)
            return

        stale_before = datetime.utcnow() - timedelta(seconds=app.config["AI_JOB_STALE_SECONDS"])
        if task.status == "running" and task.started_at and task.started_at > stale_before:
            return

        user = db.session.get(User, task.user_id)
        if not user or user.is_banned or not user.has_current_ai_consent():
            _fail(task, "A autorização para executar esta tarefa não está mais válida.", 403)
            return
        reserved_plan = (task.operation in {"diet_plan", "workout_plan"}
                         and (task.route_params or {}).get("_free_plan_reserved"))
        if not user.has_entitlement("premium") and not reserved_plan:
            _fail(task, "O plano Premium não está mais ativo.", 403)
            return
        handler = _handler_for(task.operation)
        if handler is None:
            _fail(task, "Tipo de tarefa de IA inválido.", 422)
            return

        claimed = AITask.query.filter(
            AITask.id == task.id,
            or_(AITask.status == "queued", and_(AITask.status == "running",
                AITask.started_at <= stale_before)),
        ).update({AITask.status: "running", AITask.started_at: datetime.utcnow()},
                 synchronize_session=False)
        db.session.commit()
        if not claimed:
            return
        db.session.refresh(task)

        payload = dict(task.request_payload or {})
        if task.request_image_data:
            payload["image"] = {
                "data": base64.b64encode(task.request_image_data).decode("ascii"),
                "mime_type": task.request_image_mime_type,
            }
        route_params = dict(task.route_params or {})
        provider_header = route_params.pop("_ai_providers", "")
        route_params.pop("_free_plan_reserved", None)
        route_params.pop("_request_key", None)
        for key in ("student_id",):
            if key in route_params:
                route_params[key] = uuid.UUID(route_params[key])
        for key in ("plan_id",):
            if key in route_params:
                route_params[key] = int(route_params[key])

        try:
            with app.test_request_context("/api/internal/ai-task", method="POST", json=payload,
                                          headers={"X-AI-Providers": provider_header}):
                g.user = user
                g.ai_worker_execution = True
                g.ai_task_id = task.id
                value = inspect.unwrap(handler)(**route_params)
                response = app.make_response(value)
                result = response.get_json(silent=True) or {"error": "Resposta inválida da tarefa de IA."}
                status = response.status_code
        except HTTPException as error:
            result = {"error": error.description}
            status = error.code or 500
        except Exception as error:
            db.session.rollback()
            if self.request.retries < app.config["AI_JOB_MAX_RETRIES"]:
                task = db.session.get(AITask, uuid.UUID(str(task_id)))
                if task is None:
                    return
                task.status = "queued"
                db.session.commit()
                raise self.retry(
                    exc=error,
                    countdown=min(30 * (2 ** self.request.retries), 300),
                )
            app.logger.exception("AI task %s failed after retries", task_id)
            task = db.session.get(AITask, uuid.UUID(str(task_id)))
            if task is None:
                return
            _fail(task, "A tarefa de IA falhou após novas tentativas.")
            return

        if status in {429, 503} and self.request.retries < app.config["AI_JOB_MAX_RETRIES"]:
            task.status = "queued"
            db.session.commit()
            raise self.retry(
                countdown=min(30 * (2 ** self.request.retries), 300),
            )
        _complete(task, result, status)
