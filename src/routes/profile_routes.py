import base64
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, g, jsonify, request, send_file

from src.models.user import DietEntry, Measurement, UserProfile, db
from src.routes.common import _csrf_protect_request, _require_lengths, coerce_numbers, json_body, login_required, page_query, premium_required
from src.services.badges import BADGE_CODES, available_profile_items, apply_profile_highlights, serialize_badges, serialize_profile_highlights
from src.services.ai import AIQuotaExceededError, AIResponseError, AIServiceError, calculate_nutrition
from src.services.rate_limit import rate_limit
from src.services.workoutx import WorkoutXServiceError, approved_media, get_cached_gif
from src.services.workout_progress import backfill_session_weeks, validate_timezone


profile_bp = Blueprint("profile", __name__)


@profile_bp.before_request
def protect_profile_mutations():
    return _csrf_protect_request()


@profile_bp.route("/profile", methods=["GET"])
@login_required
def get_profile():
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if profile:
        return jsonify({"profile": profile.to_dict()}), 200
    return jsonify({"profile": None}), 200


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
    data = coerce_numbers(json_body(), ("age", "weight", "height"))
    _require_lengths(data, {
        "gender": (10, "Gênero"),
        "goal": (100, "Objetivo"),
        "activity_level": (50, "Nível de atividade"),
        "dietary_restrictions": (2000, "Restrições alimentares"),
        "timezone": (64, "Timezone"),
    })
    age = data.get("age")
    if age is not None and not (0 <= age <= 120):
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
    profile.weight = data.get("weight", profile.weight)
    profile.height = data.get("height", profile.height)
    profile.timezone = data.get("timezone", profile.timezone)
    if "timezone" in data and profile.timezone:
        backfill_session_weeks(user.id, profile.timezone)

    db.session.commit()
    return jsonify({"message": "Perfil atualizado com sucesso", "profile": profile.to_dict()}), 200


@profile_bp.route("/diet", methods=["POST"])
@login_required
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
    )
    db.session.add(new_entry)
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
def update_diet_entry(entry_id):
    user = g.user
    data = coerce_numbers(json_body(), ("calories", "protein", "carbs", "fat"))
    _require_lengths(data, {
        "meal_type": (50, "Tipo de refeição"),
        "description": (2000, "Descrição"),
        "notes": (2000, "Observações"),
    })
    entry = DietEntry.query.filter_by(id=entry_id, user_id=user.id).first_or_404()

    date_str = data.get("date")
    if date_str:
        try:
            entry.date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Formato de data inválido"}), 400

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
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"message": "Registro de dieta excluído"}), 200


@profile_bp.route("/diet/ai_macros", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required(allow_trial=True)
def get_ai_macros():
    data = json_body()
    description = str(data.get("description", "")).strip()
    image = data.get("image") or {}
    image_data = str(image.get("data", "")).strip()
    mime_type = str(image.get("mime_type", "")).strip().lower()

    image_bytes = None
    if image_data:
        allowed_mime = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
        if mime_type not in allowed_mime:
            return jsonify({"error": "Formato de imagem não suportado"}), 400
        try:
            image_bytes = base64.b64decode(image_data, validate=True)
        except (ValueError, TypeError):
            return jsonify({"error": "Imagem inválida"}), 400
        if not image_bytes:
            return jsonify({"error": "Imagem inválida"}), 400
        if len(image_bytes) > 8 * 1024 * 1024:
            return jsonify({"error": "Imagem muito grande. Envie uma foto menor."}), 413

    if not description and not image_bytes:
        return jsonify({"error": "Descreva o alimento ou envie uma foto"}), 400

    try:
        return jsonify(calculate_nutrition(description, image_bytes, mime_type)), 200
    except AIResponseError:
        return jsonify({"error": "A IA retornou macros incompletos. Tente novamente."}), 422
    except AIQuotaExceededError as error:
        return jsonify({"error": str(error)}), 429
    except AIServiceError:
        current_app.logger.exception("Nutrition AI request failed")
        return jsonify({"error": "Não foi possível calcular macros no momento"}), 503


@profile_bp.route("/exercise-media/<catalog_key>", methods=["GET"])
@login_required
def get_exercise_media(catalog_key):
    media = approved_media(catalog_key)
    if media is None:
        abort(404)
    try:
        gif_path = get_cached_gif(catalog_key, media["provider_id"])
    except WorkoutXServiceError as error:
        current_app.logger.warning("WorkoutX GIF unavailable for %s: %s", catalog_key, error)
        abort(503, description="A animação do exercício não está disponível agora.")
    return send_file(gif_path, mimetype="image/gif", conditional=True, max_age=31_536_000)


@profile_bp.route("/measurements", methods=["POST"])
@login_required
def add_measurement():
    user = g.user
    data = coerce_numbers(json_body(), ("weight", "height", "body_fat", "muscle_mass", "waist", "chest", "arm", "thigh"))
    _require_lengths(data, {"notes": (2000, "Observações")})
    date_str = data.get("date")
    if not date_str:
        return jsonify({"error": "Data é obrigatória"}), 400
    try:
        measurement_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de data inválido. Use YYYY-MM-DD"}), 400

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

    measurements, _, _ = page_query(query.order_by(Measurement.date.desc(), Measurement.created_at.desc()))
    return jsonify([measurement.to_dict() for measurement in measurements.all()]), 200


@profile_bp.route("/measurements/<int:measurement_id>", methods=["PUT"])
@login_required
def update_measurement(measurement_id):
    user = g.user
    data = coerce_numbers(json_body(), ("weight", "height", "body_fat", "muscle_mass", "waist", "chest", "arm", "thigh"))
    _require_lengths(data, {"notes": (2000, "Observações")})
    measurement = Measurement.query.filter_by(id=measurement_id, user_id=user.id).first_or_404()

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
    latest_measurement = Measurement.query.filter_by(user_id=g.user.id).order_by(Measurement.date.desc()).first()
    total_diet_entries = DietEntry.query.filter_by(user_id=g.user.id).count()
    seven_days_ago = datetime.utcnow().date() - timedelta(days=7)
    recent_diet_entries = DietEntry.query.filter_by(user_id=g.user.id).filter(DietEntry.date >= seven_days_ago).count()

    return jsonify({
        "latest_measurement": latest_measurement.to_dict() if latest_measurement else None,
        "total_diet_entries": total_diet_entries,
        "recent_diet_entries": recent_diet_entries,
    }), 200
