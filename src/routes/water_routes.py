from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from src.models.user import IdempotentOperation, UserProfile, WaterEntry, db
from src.routes.common import json_body, login_required
from src.services.workout_progress import user_timezone


water_bp = Blueprint("water", __name__)


def _volume(value):
    if type(value) is not int or not 1 <= value <= 10000:
        abort(400, description="Informe um volume inteiro entre 1 e 10.000 mL.")
    return value


def _day_summary(selected_date=None):
    timezone_name = user_timezone(g.user.id)
    selected_date = selected_date or datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
    entries = WaterEntry.query.filter_by(user_id=g.user.id, local_date=selected_date).order_by(
        WaterEntry.occurred_at.desc(), WaterEntry.id.desc(),
    ).all()
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    return {
        "date": selected_date.isoformat(),
        "timezone": timezone_name,
        "total_ml": sum(entry.amount_ml for entry in entries),
        "bottle_capacity_ml": profile.bottle_capacity_ml if profile else None,
        "entries": [entry.to_dict() for entry in entries],
    }


@water_bp.route("/water", methods=["GET"])
@login_required
def get_water():
    selected_date = None
    if "date" in request.args:
        try:
            selected_date = date.fromisoformat(request.args["date"])
            if selected_date.isoformat() != request.args["date"]:
                raise ValueError
        except ValueError:
            abort(400, description="Formato de data inválido.")
    return jsonify(_day_summary(selected_date))


def _replay(key):
    operation = IdempotentOperation.query.filter_by(user_id=g.user.id, idempotency_key=key).first()
    if operation:
        if operation.method != request.method or operation.path != request.path:
            abort(409, description="A chave de idempotência já foi usada em outra operação.")
        return jsonify(operation.response_payload), operation.status_code
    return None


@water_bp.route("/water", methods=["POST"])
@login_required
def add_water():
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        abort(400, description="Envie uma Idempotency-Key válida para registrar água.")
    replay = _replay(key)
    if replay:
        return replay
    data = json_body()
    amount = _volume(data.get("amount_ml"))
    now = datetime.now(timezone.utc)
    occurred_at = now
    if "occurred_at" in data:
        try:
            occurred_at = datetime.fromisoformat(data["occurred_at"].replace("Z", "+00:00"))
            if occurred_at.tzinfo is None:
                raise ValueError
            occurred_at = occurred_at.astimezone(timezone.utc)
        except (ValueError, TypeError, AttributeError, OverflowError):
            abort(400, description="Horário de registro inválido.")
        if occurred_at > now + timedelta(minutes=5):
            abort(400, description="O horário de registro não pode estar no futuro.")
    timezone_name = user_timezone(g.user.id)
    entry = WaterEntry(
        user_id=g.user.id,
        amount_ml=amount,
        occurred_at=occurred_at.replace(tzinfo=None),
        local_date=occurred_at.astimezone(ZoneInfo(timezone_name)).date(),
        timezone=timezone_name,
    )
    db.session.add(entry)
    db.session.flush()
    result = {**_day_summary(entry.local_date), "entry": entry.to_dict()}
    # Save the receipt with the entry: concurrent retries cannot create two drinks.
    db.session.add(IdempotentOperation(
        user_id=g.user.id, idempotency_key=key, method=request.method, path=request.path,
        status_code=201, response_payload=result,
    ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        replay = _replay(key)
        if replay:
            return replay
        raise
    return jsonify(result), 201


@water_bp.route("/water/bottle", methods=["POST"])
@login_required
def set_water_bottle():
    capacity = _volume(json_body().get("bottle_capacity_ml"))
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if profile is None:
        profile = UserProfile(user_id=g.user.id)
        db.session.add(profile)
    profile.bottle_capacity_ml = capacity
    db.session.commit()
    return jsonify(_day_summary())


@water_bp.route("/water/<int:entry_id>", methods=["DELETE"])
@login_required
def delete_water(entry_id):
    entry = WaterEntry.query.filter_by(id=entry_id, user_id=g.user.id).first()
    if entry is None:
        abort(404, description="Registro de água não encontrado.")
    selected_date = entry.local_date
    db.session.delete(entry)
    db.session.commit()
    return jsonify(_day_summary(selected_date))
