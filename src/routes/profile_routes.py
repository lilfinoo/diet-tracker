from src.services.body_progress import body_summary
import base64
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, g, jsonify, request, send_file

from src.models.user import AnalyticsEvent, DietEntry, Measurement, UserProfile, db
from src.routes.common import _local_date_for_timezone, _require_lengths, ai_consent_required, coerce_numbers, idempotent_mutation, json_body, login_required, page_query, premium_required
from src.services.badges import BADGE_CODES, available_profile_items, apply_profile_highlights, serialize_badges, serialize_profile_highlights
from src.services.ai import AIQuotaExceededError, AIResponseError, AIServiceError, AIServiceUnavailableError, calculate_nutrition
from src.services.analytics import record_event
from src.services.ai_queue import enqueue_ai_request
from src.services.rate_limit import rate_limit
from src.services.workoutx import WorkoutXServiceError, approved_media, get_cached_gif
from src.services.workout_progress import backfill_session_weeks, user_timezone, validate_timezone


profile_bp = Blueprint("profile", __name__)


def _validate_measurement_values(data):
    ranges = {
        "weight": (0, 500),
        "height": (0, 300),
        "body_fat": (0, 100),
        "muscle_mass": (0, 500),
        "waist": (0, 500),
        "chest": (0, 500),
        "arm": (0, 500),
        "thigh": (0, 500),
    }
    for field, (minimum, maximum) in ranges.items():
        value = data.get(field)
        if value is not None and not minimum < value <= maximum:
            return jsonify({"error": "Medida fora do intervalo permitido."}), 400
    return None


@profile_bp.route("/profile", methods=["GET"])
@login_required
def get_profile():
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if profile:
        return jsonify({"profile": profile.to_dict(), **g.user.profile_onboarding_state()}), 200
    return jsonify({"profile": None, **g.user.profile_onboarding_state()}), 200


@profile_bp.route("/profile/badges", methods=["GET"])
@login_required
def get_profile_badges():
    return jsonify({"badges": serialize_badges(g.user.badges), "catalog": BADGE_CODES}), 200


@profile_bp.route("/profile/highlights", methods=["GET", "PUT"])
@login_required
def profile_highlights():
    if request.method == "GET":
        return jsonify({
            "selected": serialize_profile_highlights(g.user.profile_highlights),
            "available": available_profile_items(g.user),
            "limit": 3,
        }), 200

    data = json_body()
    selections = data.get("items")
    if not isinstance(selections, list):
        return jsonify({"error": "Lista de destaques inválida."}), 400
    try:
        selected = apply_profile_highlights(g.user, selections)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    db.session.commit()
    return jsonify({
        "message": "Destaques atualizados.",
        "selected": serialize_profile_highlights(selected),
        "available": available_profile_items(g.user),
        "limit": 3,
    }), 200


@profile_bp.route("/profile", methods=["POST"])
@login_required
def update_profile():
    user = g.user
    data = coerce_numbers(json_body(), ("age", "weight", "height"), height_fields=("height",))
    _require_lengths(data, {
        "gender": (10, "Gênero"),
        "goal": (100, "Objetivo"),
        "activity_level": (50, "Nível de atividade"),
        "dietary_restrictions": (2000, "Restrições alimentares"),
        "timezone": (64, "Timezone"),
    })
    age = data.get("age")
    if age is not None and (not age.is_integer() or not 0 <= age <= 120):
        return jsonify({"error": "Idade inválida"}), 400
    weight = data.get("weight")
    if weight is not None and not (0 < weight <= 500):
        return jsonify({"error": "Peso inválido"}), 400
    height = data.get("height")
    if height is not None and not (0 < height <= 300):
        return jsonify({"error": "Altura inválida"}), 400
    if "timezone" in data and data["timezone"] not in (None, ""):
        try:
            data["timezone"] = validate_timezone(data["timezone"])
        except ValueError:
            return jsonify({"error": "Timezone inválido"}), 400

    profile = UserProfile.query.filter_by(user_id=user.id).first()
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.session.add(profile)

    profile.age = data.get("age", profile.age)
    profile.gender = data.get("gender", profile.gender)
    profile.goal = data.get("goal", profile.goal)
    profile.activity_level = data.get("activity_level", profile.activity_level)
    profile.dietary_restrictions = data.get("dietary_restrictions", profile.dietary_restrictions)
    body_changes = {}
    for field in ("weight", "height"):
        if field not in data:
            continue
        value = data[field]
        has_measurement = Measurement.query.filter(
            Measurement.user_id == user.id, getattr(Measurement, field).isnot(None),
        ).first() is not None
        if has_measurement:
            if value is None:
                return jsonify({"error": "Edite as medições para remover peso ou altura do histórico."}), 400
            if value != getattr(profile, field):
                body_changes[field] = value
        else:
            setattr(profile, field, value)
    if body_changes:
        db.session.add(Measurement(
            user_id=user.id,
            date=_local_date_for_timezone(data.get("timezone") or profile.timezone or "UTC"),
            **body_changes,
        ))
    profile.timezone = data.get("timezone", profile.timezone)
    if "timezone" in data and profile.timezone:
        backfill_session_weeks(user.id, profile.timezone)

    if not AnalyticsEvent.query.filter_by(
        event_name="profile_completed", subject_id=user.analytics_subject_id
    ).first():
        record_event(
            "profile_completed",
            user_id=user.id,
        )
    db.session.commit()
    return jsonify({
        "message": "Perfil atualizado com sucesso",
        "profile": profile.to_dict(),
        **user.profile_onboarding_state(),
    }), 200


@profile_bp.route("/diet", methods=["POST"])
@login_required
@idempotent_mutation
def add_diet_entry():
    user = g.user
    data = coerce_numbers(json_body(), ("calories", "protein", "carbs", "fat"))
    _require_lengths(data, {
        "meal_type": (50, "Tipo de refeição"),
        "description": (2000, "Descrição"),
        "notes": (2000, "Observações"),
    })

    date_str = data.get("date")
    meal_type = data.get("meal_type")
    description = data.get("description")

    if not all([date_str, meal_type, description]):
        return jsonify({"error": "Data, tipo de refeição e descrição são obrigatórios"}), 400

    try:
        entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de data inválido. Use YYYY-MM-DD"}), 400

    for field in ("calories", "protein", "carbs", "fat"):
        value = data.get(field)
        maximum = 20_000 if field == "calories" else 5_000
        if value is not None and not 0 <= value <= maximum:
            return jsonify({"error": "Valores nutricionais devem ser finitos e não negativos."}), 400

    new_entry = DietEntry(
        user_id=user.id,
        date=entry_date,
        meal_type=meal_type,
        description=description,
        calories=data.get("calories"),
        protein=data.get("protein"),
        carbs=data.get("carbs"),
        fat=data.get("fat"),
        notes=data.get("notes"),
        source="manual",
    )
    db.session.add(new_entry)
    db.session.flush()
    record_event(
        "meal_logged",
        user_id=user.id,
    )
    db.session.commit()
    return jsonify({"message": "Registro de dieta adicionado", "entry": new_entry.to_dict()}), 201


@profile_bp.route("/diet", methods=["GET"])
@login_required
def get_diet_entries():
    user = g.user
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    query = DietEntry.query.filter_by(user_id=user.id)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            query = query.filter(DietEntry.date >= start_date)
        except ValueError:
            return jsonify({"error": "Formato de data inicial inválido"}), 400
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            query = query.filter(DietEntry.date <= end_date)
        except ValueError:
            return jsonify({"error": "Formato de data final inválido"}), 400

    entries, _, _ = page_query(query.order_by(DietEntry.date.desc(), DietEntry.created_at.desc()))
    return jsonify([entry.to_dict() for entry in entries.all()]), 200


@profile_bp.route("/diet/<int:entry_id>", methods=["PUT"])
@login_required
@idempotent_mutation
def update_diet_entry(entry_id):
    user = g.user
    data = coerce_numbers(json_body(), ("calories", "protein", "carbs", "fat"))
    _require_lengths(data, {
        "meal_type": (50, "Tipo de refeição"),
        "description": (2000, "Descrição"),
        "notes": (2000, "Observações"),
    })
    entry = DietEntry.query.filter_by(id=entry_id, user_id=user.id).first_or_404()
    for field in ("calories", "protein", "carbs", "fat"):
        value = data.get(field)
        maximum = 20_000 if field == "calories" else 5_000
        if value is not None and not 0 <= value <= maximum:
            return jsonify({"error": "Valores nutricionais devem ser finitos e não negativos."}), 400

    date_str = data.get("date")
    if date_str:
        try:
            updated_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Formato de data inválido"}), 400
        if entry.daily_meal_state_id and updated_date != entry.date:
            return jsonify({"error": "A data de uma refeição vinculada ao diário não pode ser alterada."}), 409
        entry.date = updated_date

    if entry.daily_meal_state_id and data.get("meal_type", entry.meal_type) != entry.meal_type:
        return jsonify({"error": "O tipo de uma refeição vinculada ao diário não pode ser alterado."}), 409

    entry.meal_type = data.get("meal_type", entry.meal_type)
    entry.description = data.get("description", entry.description)
    entry.calories = data.get("calories", entry.calories)
    entry.protein = data.get("protein", entry.protein)
    entry.carbs = data.get("carbs", entry.carbs)
    entry.fat = data.get("fat", entry.fat)
    entry.notes = data.get("notes", entry.notes)

    db.session.commit()
    return jsonify({"message": "Registro de dieta atualizado", "entry": entry.to_dict()}), 200


@profile_bp.route("/diet/<int:entry_id>", methods=["DELETE"])
@login_required
def delete_diet_entry(entry_id):
    user = g.user
    entry = DietEntry.query.filter_by(id=entry_id, user_id=user.id).first_or_404()
    state = entry.daily_meal_state
    db.session.delete(entry)
    if state is not None:
        state.result = "pending"
        state.planned_snapshot = None
    db.session.commit()
    return jsonify({"message": "Registro de dieta excluído"}), 200


@profile_bp.route("/diet/ai_macros", methods=["POST"])
@rate_limit("ai", 8, 60)
@ai_consent_required
@premium_required(allow_trial=True)
def get_ai_macros():
    data = json_body()
    raw_description = data.get("description", "")
    if not isinstance(raw_description, str) or len(raw_description) > 2_000:
        return jsonify({"error": "Descrição inválida ou muito longa."}), 400
    description = raw_description.strip()
    image = data.get("image")
    if image is not None and not isinstance(image, dict):
        return jsonify({"error": "Imagem inválida"}), 400
    image = image or {}
    image_data = image.get("data", "")
    mime_type = image.get("mime_type", "")
    if not isinstance(image_data, str) or not isinstance(mime_type, str):
        return jsonify({"error": "Imagem inválida"}), 400
    image_data = image_data.strip()
    mime_type = mime_type.strip().lower()

    image_bytes = None
    if image_data:
        allowed_mime = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
        if mime_type not in allowed_mime:
            return jsonify({"error": "Formato de imagem não suportado"}), 400
        if len(image_data) > 11 * 1024 * 1024:
            return jsonify({"error": "Imagem muito grande. Envie uma foto menor."}), 413
        try:
            image_bytes = base64.b64decode(image_data, validate=True)
        except (ValueError, TypeError):
            return jsonify({"error": "Imagem inválida"}), 400
        if not image_bytes:
            return jsonify({"error": "Imagem inválida"}), 400
        if len(image_bytes) > 8 * 1024 * 1024:
            return jsonify({"error": "Imagem muito grande. Envie uma foto menor."}), 413
        valid_magic = {
            "image/jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
            "image/png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP",
            "image/heic": len(image_bytes) >= 12 and image_bytes[4:8] == b"ftyp" and image_bytes[8:12] in {b"heic", b"heix", b"hevc", b"hevx"},
            "image/heif": len(image_bytes) >= 12 and image_bytes[4:8] == b"ftyp" and image_bytes[8:12] in {b"mif1", b"msf1", b"heif"},
        }
        if not valid_magic[mime_type]:
            return jsonify({"error": "O conteúdo do arquivo não corresponde ao formato informado."}), 400

    if not description and not image_bytes:
        return jsonify({"error": "Descreva o alimento ou envie uma foto"}), 400

    queued = enqueue_ai_request("nutrition_macros", data)
    if queued is not None:
        return queued

    try:
        return jsonify(calculate_nutrition(description, image_bytes, mime_type)), 200
    except AIResponseError:
        return jsonify({"error": "A IA retornou macros incompletos. Tente novamente."}), 422
    except AIQuotaExceededError as error:
        return jsonify({"error": str(error)}), 429
    except AIServiceUnavailableError:
        return jsonify({"error": "A análise está temporariamente indisponível. Tente novamente ou continue sem estimativa."}), 503
    except AIServiceError:
        current_app.logger.exception("Nutrition AI request failed")
        return jsonify({"error": "Não foi possível calcular macros no momento"}), 503


def _serve_exercise_media(catalog_key):
    media = approved_media(catalog_key)
    if media is None:
        abort(404)
    try:
        gif_path = get_cached_gif(catalog_key, media["provider_id"])
    except WorkoutXServiceError as error:
        current_app.logger.warning("WorkoutX GIF unavailable for %s: %s", catalog_key, error)
        response = jsonify({"error": "A animação do exercício não está disponível agora."})
        response.status_code = 503
        response.headers["Cache-Control"] = "private, max-age=60"
        if error.retry_after:
            response.headers["Retry-After"] = str(error.retry_after)
        return response
    return send_file(gif_path, mimetype="image/gif", conditional=True, max_age=31_536_000)


@profile_bp.route("/exercise-media/<catalog_key>", methods=["GET"])
@login_required
def get_exercise_media(catalog_key):
    return _serve_exercise_media(catalog_key)


@profile_bp.route("/public/exercise-media/<catalog_key>", methods=["GET"])
def get_public_exercise_media(catalog_key):
    return _serve_exercise_media(catalog_key)


@profile_bp.route("/measurements", methods=["POST"])
@login_required
@idempotent_mutation
def add_measurement():
    user = g.user
    data = coerce_numbers(
        json_body(),
        ("weight", "height", "body_fat", "muscle_mass", "waist", "chest", "arm", "thigh"),
        height_fields=("height",),
    )
    _require_lengths(data, {"notes": (2000, "Observações")})
    date_str = data.get("date")
    if not date_str:
        return jsonify({"error": "Data é obrigatória"}), 400
    try:
        measurement_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de data inválido. Use YYYY-MM-DD"}), 400
    validation_error = _validate_measurement_values(data)
    if validation_error:
        return validation_error

    new_measurement = Measurement(
        user_id=user.id,
        date=measurement_date,
        weight=data.get("weight"),
        height=data.get("height"),
        body_fat=data.get("body_fat"),
        muscle_mass=data.get("muscle_mass"),
        waist=data.get("waist"),
        chest=data.get("chest"),
        arm=data.get("arm"),
        thigh=data.get("thigh"),
        notes=data.get("notes"),
    )
    db.session.add(new_measurement)
    if not UserProfile.query.filter_by(user_id=user.id).first():
        db.session.add(UserProfile(user_id=user.id))
    record_event("measurement_logged", user_id=user.id)
    db.session.commit()
    return jsonify({"message": "Medida adicionada", "measurement": new_measurement.to_dict()}), 201


@profile_bp.route("/measurements", methods=["GET"])
@login_required
def get_measurements():
    user = g.user
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    query = Measurement.query.filter_by(user_id=user.id)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            query = query.filter(Measurement.date >= start_date)
        except ValueError:
            return jsonify({"error": "Formato de data inicial inválido"}), 400
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            query = query.filter(Measurement.date <= end_date)
        except ValueError:
            return jsonify({"error": "Formato de data final inválido"}), 400

    if start_date_str and end_date_str and start_date > end_date:
        return jsonify({"error": "A data inicial deve ser anterior ou igual à data final."}), 400

    measurements, _, _ = page_query(query.order_by(Measurement.date.desc(), Measurement.created_at.desc(), Measurement.id.desc()))
    return jsonify([measurement.to_dict() for measurement in measurements.all()]), 200


@profile_bp.route("/measurements/summary", methods=["GET"])
@login_required
def measurement_summary():
    metric = request.args.get("metric")
    if metric is not None:
        if metric not in ("weight", "body_fat", "waist", "chest", "arm", "thigh", "muscle_mass"):
            return jsonify({"error": "Métrica inválida"}), 400
        try:
            start = datetime.strptime(request.args["start_date"], "%Y-%m-%d").date() if request.args.get("start_date") else None
            end = datetime.strptime(request.args["end_date"], "%Y-%m-%d").date() if request.args.get("end_date") else None
        except ValueError:
            return jsonify({"error": "Formato de data inválido"}), 400
        if start and end and start > end:
            return jsonify({"error": "A data inicial deve ser anterior ou igual à data final."}), 400
        column = getattr(Measurement, metric)
        series_query = Measurement.query.filter_by(user_id=g.user.id).filter(column.isnot(None)).order_by(
            Measurement.date.desc(), Measurement.created_at.desc(), Measurement.id.desc()
        )
        latest_metric = series_query.first()
        if start:
            series_query = series_query.filter(Measurement.date >= start)
        if end:
            series_query = series_query.filter(Measurement.date <= end)
        points = [{"date": item.date.isoformat(), "value": getattr(item, metric)} for item in reversed(series_query.all())]
        return jsonify({"points": points, "latest_date": latest_metric.date.isoformat() if latest_metric else None}), 200
    return jsonify(body_summary(g.user.id)), 200


@profile_bp.route("/measurements/<int:measurement_id>", methods=["PUT"])
@login_required
@idempotent_mutation
def update_measurement(measurement_id):
    user = g.user
    data = coerce_numbers(
        json_body(),
        ("weight", "height", "body_fat", "muscle_mass", "waist", "chest", "arm", "thigh"),
        height_fields=("height",),
    )
    _require_lengths(data, {"notes": (2000, "Observações")})
    measurement = Measurement.query.filter_by(id=measurement_id, user_id=user.id).first_or_404()
    validation_error = _validate_measurement_values(data)
    if validation_error:
        return validation_error

    date_str = data.get("date")
    if date_str:
        try:
            measurement.date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Formato de data inválido"}), 400

    measurement.weight = data.get("weight", measurement.weight)
    measurement.height = data.get("height", measurement.height)
    measurement.body_fat = data.get("body_fat", measurement.body_fat)
    measurement.muscle_mass = data.get("muscle_mass", measurement.muscle_mass)
    measurement.waist = data.get("waist", measurement.waist)
    measurement.chest = data.get("chest", measurement.chest)
    measurement.arm = data.get("arm", measurement.arm)
    measurement.thigh = data.get("thigh", measurement.thigh)
    measurement.notes = data.get("notes", measurement.notes)

    db.session.commit()
    return jsonify({"message": "Medida atualizada", "measurement": measurement.to_dict()}), 200


@profile_bp.route("/measurements/<int:measurement_id>", methods=["DELETE"])
@login_required
def delete_measurement(measurement_id):
    user = g.user
    measurement = Measurement.query.filter_by(id=measurement_id, user_id=user.id).first_or_404()
    db.session.delete(measurement)
    db.session.commit()
    return jsonify({"message": "Medida excluída"}), 200


@profile_bp.route("/stats", methods=["GET"])
@login_required
def get_stats():
    latest_measurement = Measurement.query.filter_by(user_id=g.user.id).order_by(
        Measurement.date.desc(), Measurement.created_at.desc(), Measurement.id.desc()
    ).first()
    total_diet_entries = DietEntry.query.filter_by(user_id=g.user.id).count()
    today = _local_date_for_timezone(user_timezone(g.user.id))
    seven_days_start = today - timedelta(days=6)
    recent_diet_entries = DietEntry.query.filter_by(user_id=g.user.id).filter(
        DietEntry.date >= seven_days_start, DietEntry.date <= today
    ).count()

    return jsonify({
        "latest_measurement": latest_measurement.to_dict() if latest_measurement else None,
        "total_diet_entries": total_diet_entries,
        "recent_diet_entries": recent_diet_entries,
    }), 200
