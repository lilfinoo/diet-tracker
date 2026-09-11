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
