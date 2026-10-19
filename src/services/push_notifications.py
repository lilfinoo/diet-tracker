import os
import time

import httpx
import jwt
from flask import current_app

from src.models.user import PushDevice, db


def _setting(name):
    return current_app.config.get(name) or os.environ.get(name, "")


def push_ready():
    return str(_setting("APNS_ENABLED")).lower() in {"true", "1"} and all(
        _setting(name) for name in ("APNS_KEY_ID", "APNS_TEAM_ID", "APNS_PRIVATE_KEY", "APNS_TOPIC")
    )


def notify_plan_ready(task):
    """Best effort APNs alert; never turn an already saved plan into a failure."""
    if not push_ready() or task.status != "succeeded" or task.operation not in {"diet_plan", "workout_plan"}:
        return False
    try:
        token = jwt.encode({"iss": _setting("APNS_TEAM_ID"), "iat": int(time.time())},
                           _setting("APNS_PRIVATE_KEY").replace("\\n", "\n"), algorithm="ES256",
                           headers={"kid": _setting("APNS_KEY_ID")})
        devices = PushDevice.query.filter_by(user_id=task.user_id).limit(10).all()
        accepted = False
        with httpx.Client(http2=True, timeout=5) as client:
            for device in devices:
                host = "api.sandbox.push.apple.com" if device.environment == "sandbox" else "api.push.apple.com"
                response = client.post(f"https://{host}/3/device/{device.token}", headers={
                    "authorization": f"bearer {token}", "apns-topic": _setting("APNS_TOPIC"),
                    "apns-push-type": "alert", "apns-priority": "10",
                    "apns-collapse-id": str(task.id),
                }, json={"aps": {"alert": {"title": "Seu plano está pronto", "body": "Abra o Fit Tracker para conferir seu novo plano."}, "sound": "default"},
                         "task_id": str(task.id), "plan_kind": "diet" if task.operation == "diet_plan" else "workout",
                         "plan_id": (task.result or {}).get("plan_id")})
                accepted = accepted or response.status_code == 200
                if response.status_code == 410:
                    db.session.delete(device)
        db.session.commit()
        return accepted
    except Exception:
        db.session.rollback()
        # Provider responses and exceptions can include tokens or credentials.
        current_app.logger.warning("plan_ready_push_unavailable")
        return False
