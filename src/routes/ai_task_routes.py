from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify

from src.models.user import AITask
from src.routes.common import login_required
from src.services.ai_queue import plan_background_ready
from src.services.push_notifications import push_ready


ai_task_bp = Blueprint("ai_task", __name__)


@ai_task_bp.route("/ai/tasks", methods=["GET"])
@login_required
def list_ai_tasks():
    tasks = AITask.query.filter(
        AITask.user_id == g.user.id,
        AITask.operation.in_(["diet_plan", "workout_plan"]),
        AITask.created_at >= datetime.utcnow() - timedelta(days=7),
    ).order_by(AITask.created_at.desc()).limit(20).all()
    response = jsonify({
        "plan_background_enabled": plan_background_ready(),
        "push_enabled": push_ready(),
        "tasks": [{**task.to_dict(include_result=True),
                   "request_key": (task.route_params or {}).get("_request_key")} for task in tasks],
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@ai_task_bp.route("/ai/tasks/<uuid:task_id>", methods=["GET"])
@login_required
def get_ai_task(task_id):
    task = AITask.query.filter_by(id=task_id, user_id=g.user.id).first_or_404()
    response = jsonify(task.to_dict(include_result=True))
    if task.status in {"queued", "running"}:
        response.headers["Retry-After"] = "2"
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@ai_task_bp.route("/ai/usage", methods=["GET"])
@login_required
def get_ai_usage():
    response = jsonify({
        "premium": g.user.has_entitlement("premium"),
        "policy": "lifetime",
        "plans": {"limit": 2, "used": g.user.free_workout_plan_uses + g.user.free_diet_plan_uses, "remaining": max(0, 1 - g.user.free_workout_plan_uses) + max(0, 1 - g.user.free_diet_plan_uses)},
        "workout_plans": {"limit": 1, "used": g.user.free_workout_plan_uses, "remaining": max(0, 1 - g.user.free_workout_plan_uses)},
        "diet_plans": {"limit": 1, "used": g.user.free_diet_plan_uses, "remaining": max(0, 1 - g.user.free_diet_plan_uses)},
        "photos": {"limit": 3, "used": g.user.free_photo_uses, "remaining": max(0, 3 - g.user.free_photo_uses)},
        "manual_logging": True,
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200
