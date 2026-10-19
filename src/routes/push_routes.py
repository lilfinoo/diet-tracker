import re
import uuid
from datetime import datetime

from flask import Blueprint, g, jsonify, request, session

from src.models.user import PushDevice, db
from src.routes.common import login_required
from src.services.push_notifications import push_ready

push_bp = Blueprint("push", __name__)


@push_bp.route("/push/devices", methods=["POST"])
@login_required
def register_device():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Dispositivo inválido."}), 400
    try:
        installation_id = str(uuid.UUID(str(data.get("installation_id", ""))))
    except ValueError:
        return jsonify({"error": "Dispositivo inválido."}), 400
    token = data.get("token", "")
    environment = data.get("environment")
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-fA-F]{64,512}", token) or environment not in {"production", "sandbox"}:
        return jsonify({"error": "Dispositivo inválido."}), 400
    token = token.lower()
    # Possession of the unpredictable APNs token authorizes binding this installation
    # to the currently authenticated account, replacing an older login on this phone.
    device = PushDevice.query.filter_by(token=token).first()
    previous = PushDevice.query.filter_by(installation_id=installation_id).first()
    if previous is not None and previous is not device:
        if previous.user_id != g.user.id:
            return jsonify({"error": "Dispositivo pertence a outra sessão."}), 409
        db.session.delete(previous)
        db.session.flush()
    if device is None:
        if PushDevice.query.filter_by(user_id=g.user.id).count() >= 10:
            return jsonify({"error": "Limite de dispositivos atingido."}), 429
        device = PushDevice(token=token)
        db.session.add(device)
    device.user_id = g.user.id
    device.installation_id = installation_id
    device.environment = environment
    device.updated_at = datetime.utcnow()
    db.session.commit()
    session["push_installation_id"] = installation_id
    return jsonify({"registered": True, "push_enabled": push_ready()}), 200


@push_bp.route("/push/devices/<uuid:installation_id>", methods=["DELETE"])
@login_required
def unregister_device(installation_id):
    PushDevice.query.filter_by(user_id=g.user.id, installation_id=str(installation_id)).delete()
    db.session.commit()
    if session.get("push_installation_id") == str(installation_id):
        session.pop("push_installation_id", None)
    return jsonify({"unregistered": True}), 200
