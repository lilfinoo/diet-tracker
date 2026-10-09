from flask import Blueprint, g, jsonify

from src.models.user import AITask
from src.routes.common import login_required


ai_task_bp = Blueprint("ai_task", __name__)


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
        "plans": {"limit": 1, "used": g.user.free_plan_uses, "remaining": max(0, 1 - g.user.free_plan_uses)},
        "photos": {"limit": 3, "used": g.user.free_photo_uses, "remaining": max(0, 3 - g.user.free_photo_uses)},
        "manual_logging": True,
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200
