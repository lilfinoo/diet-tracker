import base64
import inspect
import uuid
from datetime import datetime, timedelta

from celery.exceptions import OperationalError
from flask import current_app, g, jsonify
from werkzeug.exceptions import HTTPException

from src.celery_app import celery_app
from src.models.user import AITask, ChatMessage, DietPlan, User, WorkoutPlan, db


def should_enqueue_ai():
    return bool(
        current_app.config.get("AI_ASYNC_ENABLED")
        and not getattr(g, "ai_worker_execution", False)
        and g.user.has_entitlement("premium")
    )


def enqueue_ai_request(operation, payload, route_params=None):
    if not should_enqueue_ai():
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

    task = AITask(
        user_id=g.user.id,
        operation=operation,
        request_payload=stored_payload,
        request_image_data=image_data,
        request_image_mime_type=image_mime_type,
        route_params={key: str(value) for key, value in (route_params or {}).items()},
    )
    db.session.add(task)
    db.session.commit()
    try:
        execute_ai_job.apply_async(args=[str(task.id)])
    except (OperationalError, ConnectionError, OSError):
        current_app.logger.exception("Unable to enqueue AI task %s", task.id)
        message = "A fila de IA está temporariamente indisponível."
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
    from src.routes.professional_routes import (
        generate_professional_diet,
        generate_professional_workout,
        suggest_professional_diet_day,
    )
    from src.routes.profile_routes import get_ai_macros

    return {
        "chat": chat,
        "nutrition_macros": get_ai_macros,
        "diet_plan": create_guided_diet_plan,
        "workout_plan": create_guided_workout_plan,
        "diet_day": suggest_diet_day,
        "professional_diet_plan": generate_professional_diet,
        "professional_workout_plan": generate_professional_workout,
        "professional_diet_day": suggest_professional_diet_day,
    }.get(operation)


def _existing_result(task):
    if task.operation == "chat":
        message = ChatMessage.query.filter_by(ai_task_id=task.id).first()
        if message:
            return {"response": message.response, "action": None}, 200
    elif task.operation in {"diet_plan", "professional_diet_plan"}:
        plan = DietPlan.query.filter_by(ai_task_id=task.id).first()
        if plan:
            if task.operation == "diet_plan":
                return {
                    "message": "Plano alimentar criado.",
                    "plan_id": plan.id,
                    "plan": plan.to_dict_full(),
                }, 201
            return {"message": "Dieta gerada como rascunho.", "plan": plan.to_dict_full()}, 201
    elif task.operation in {"workout_plan", "professional_workout_plan"}:
        plan = WorkoutPlan.query.filter_by(ai_task_id=task.id).first()
        if plan:
            if task.operation == "workout_plan":
                return {
                    "message": "Plano de treino criado.",
                    "plan_id": plan.id,
                    "plan": plan.to_dict_full(),
                }, 201
            return {"message": "Treino gerado como rascunho.", "plan": plan.to_dict_full()}, 201
    return None


def _complete(task, result, status):
    task.status = "succeeded" if 200 <= status < 300 else "failed"
    task.result = result
    task.http_status = status
    task.error = result.get("error") if task.status == "failed" and isinstance(result, dict) else None
    task.completed_at = datetime.utcnow()
    task.request_payload = {}
    task.request_image_data = None
    task.request_image_mime_type = None
    db.session.commit()


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
        if not user.has_entitlement("premium"):
            _fail(task, "O plano Premium não está mais ativo.", 403)
            return
        if task.operation.startswith("professional_") and not user.has_entitlement("professional"):
            _fail(task, "A assinatura profissional não está mais ativa.", 403)
            return
        required_scope = {
            "professional_workout_plan": "workout",
            "professional_diet_plan": "diet",
            "professional_diet_day": "diet",
        }.get(task.operation)
        if required_scope and not user.has_entitlement(required_scope):
            _fail(task, "Seu plano profissional não inclui mais este recurso.", 403)
            return

        handler = _handler_for(task.operation)
        if handler is None:
            _fail(task, "Tipo de tarefa de IA inválido.", 422)
            return

        task.status = "running"
        task.started_at = datetime.utcnow()
        db.session.commit()

        payload = dict(task.request_payload or {})
        if task.request_image_data:
            payload["image"] = {
                "data": base64.b64encode(task.request_image_data).decode("ascii"),
                "mime_type": task.request_image_mime_type,
            }
        route_params = dict(task.route_params or {})
        for key in ("student_id",):
            if key in route_params:
                route_params[key] = uuid.UUID(route_params[key])
        for key in ("plan_id",):
            if key in route_params:
                route_params[key] = int(route_params[key])

        try:
            with app.test_request_context("/api/internal/ai-task", method="POST", json=payload):
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
