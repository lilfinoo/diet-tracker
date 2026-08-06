from flask import Blueprint, jsonify, request, session, abort, g, current_app
from src.models.user import (
    ChatMessage,
    DietEntry,
    DietPlan,
    DietPlanMeal,
    Measurement,
    User,
    UserProfile,
    WorkoutDay,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
    WorkoutSessionExerciseCompletion,
    WorkoutSessionExerciseOverride,
    db,
)
from src.services.ai import (
    AIQuotaExceededError,
    AIResponseError,
    AIServiceError,
    calculate_nutrition,
    classify_exercise_catalog_key,
    generate_diet_day,
    generate_diet_plan,
    generate_response,
    generate_workout_plan,
)
from src.services.diet_plans import normalize_diet_day, normalize_diet_output, validate_diet_questionnaire
from src.services.rate_limit import rate_limit
from src.services.workout_plans import (
    PlanValidationError,
    catalog_by_key,
    normalize_workout_output,
    replacement_options,
    resolve_catalog_exercise,
    validate_workout_questionnaire,
)
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
import unicodedata

# Decorador para exigir login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify({"error": "Login necessário"}), 401
        
        # Carrega o usuário e anexa ao 'g' para uso em toda a requisição
        g.user = db.session.get(User, user_id)

        if g.user is None:
            # Caso o user_id na sessão seja inválido, limpa a sessão
            session.pop("user_id", None)
            return jsonify({"error": "Usuário não encontrado"}), 401
        if g.user.is_banned:
            session.clear()
            return jsonify({"error": "Sua conta foi banida."}), 403
            
        return f(*args, **kwargs)
    return decorated_function

# Decorador para exigir que o usuário seja admin
def admin_required(f):
    @wraps(f)
    @login_required # Garante que g.user já existe
    def decorated_function(*args, **kwargs):
        if not g.user.is_admin:
            return jsonify({"error": "Acesso negado"}), 403
        return f(*args, **kwargs)
    return decorated_function

# Decorator para exigir que o usuário seja premium
def premium_required(f):
    @wraps(f)
    @login_required # Garante que g.user já existe
    def decorated_function(*args, **kwargs):
        if not g.user.is_premium:
            return jsonify({'error': 'Acesso negado: Requer status Premium'}), 403
        return f(*args, **kwargs)
    return decorated_function
    
user_bp = Blueprint("user", __name__)


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Corpo JSON válido é obrigatório")
    return data


def chat_plan_intent(data, message):
    intent = data.get("intent")
    if intent in {"diet_plan", "workout_plan"}:
        return intent
    if intent is not None:
        abort(400, description="Intenção de plano inválida")

    normalized_message = unicodedata.normalize("NFKD", message.lower())
    normalized_message = "".join(char for char in normalized_message if not unicodedata.combining(char))
    if any(term in normalized_message for term in ("plano de dieta", "plano de alimentacao", "minha dieta", "cardapio")):
        return "diet_plan"
    if any(term in normalized_message for term in ("plano de treino", "rotina de exercicios", "rotina de treino", "meu treino")):
        return "workout_plan"
    return None


def page_query(query, model, default_limit=100):
    try:
        limit = min(max(int(request.args.get("limit", default_limit)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        abort(400, description="Paginação inválida")
    return query.limit(limit).offset(offset), limit, offset


def _text_or_none(value):
    text = str(value or "").strip()
    return text or None


def coerce_numbers(data, fields):
    data = data.copy()
    try:
        for field in fields:
            if field in data and data[field] not in (None, ""):
                data[field] = float(data[field])
            elif field in data:
                data[field] = None
    except (TypeError, ValueError):
        abort(400, description="Campo numérico inválido")
    return data


@user_bp.errorhandler(400)
def bad_request(error):
    return jsonify({"error": getattr(error, "description", "Requisição inválida")}), 400


@user_bp.errorhandler(403)
def forbidden(error):
    return jsonify({"error": getattr(error, "description", "Acesso negado")}), 403


@user_bp.errorhandler(404)
def not_found(error):
    return jsonify({"error": getattr(error, "description", "Recurso não encontrado")}), 404


@user_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": getattr(error, "description", "Método não permitido")}), 405


@user_bp.errorhandler(413)
def payload_too_large(error):
    return jsonify({"error": "Requisição muito grande. Reduza o conteúdo."}), 413


@user_bp.errorhandler(500)
def internal_error(error):
    current_app.logger.exception("Unhandled error")
    return jsonify({"error": "Erro interno do servidor"}), 500


def _require_lengths(data, specs):
    """Aborta com 400 se algum campo exceder o limite máximo de caracteres."""
    for field, (max_len, label) in specs.items():
        value = data.get(field)
        if value is None:
            continue
        if len(str(value)) > max_len:
            abort(400, description=f"{label} deve ter no máximo {max_len} caracteres.")

# --- Rotas de Autenticação ---
@user_bp.route("/register", methods=["POST"])
@rate_limit("register", 10, 60)
def register():
    data = json_body()
    username = str(data.get("username", "")).strip()
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Nome de usuário e senha são obrigatórios"}), 400
    if len(username) > 80:
        return jsonify({"error": "Nome de usuário deve ter no máximo 80 caracteres"}), 400
    if len(str(password)) < 8 or len(str(password)) > 128:
        return jsonify({"error": "A senha deve ter entre 8 e 128 caracteres"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Nome de usuário já existe"}), 400
    
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Nome de usuário já existe"}), 409
    
    session["user_id"] = user.id
    session["username"] = user.username
    return jsonify({"message": "Usuário criado com sucesso", "user": user.to_dict()}), 201

@user_bp.route("/login", methods=["POST"])
@rate_limit("login", 10, 60)
def login():
    data = json_body()
    username = str(data.get("username", "")).strip()
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Nome de usuário e senha são obrigatórios"}), 400
    
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        if user.is_banned:
            return jsonify({"error": "Sua conta foi banida."}), 403
        session["user_id"] = user.id
        session["username"] = user.username
        return jsonify({"message": "Login bem-sucedido", "user": user.to_dict()}), 200
    else:
        return jsonify({"error": "Nome de usuário ou senha inválidos"}), 401

@user_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return jsonify({"message": "Logout bem-sucedido"}), 200

@user_bp.route("/check_session", methods=["GET"])
def check_session():
    user_id = session.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if user:
            return jsonify({"logged_in": True, "user": user.to_dict()}), 200
    return jsonify({"logged_in": False}), 200

# --- Rotas de Perfil (Corrigido) ---
@user_bp.route("/profile", methods=["GET"])
@login_required
def get_profile():
    user = g.user
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    if profile:
        return jsonify({"profile": profile.to_dict()}), 200
    return jsonify({"profile": None}), 200

@user_bp.route("/profile", methods=["POST"])
@login_required
def update_profile():
    user = g.user
    data = coerce_numbers(json_body(), ("age", "weight", "height"))
    _require_lengths(data, {
        "gender": (10, "Gênero"),
        "goal": (100, "Objetivo"),
        "activity_level": (50, "Nível de atividade"),
        "dietary_restrictions": (2000, "Restrições alimentares"),
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
    
    db.session.commit()
    return jsonify({"message": "Perfil atualizado com sucesso", "profile": profile.to_dict()}), 200

# --- Rotas de Dieta (Corrigido) ---
@user_bp.route("/diet", methods=["POST"])
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
        notes=data.get("notes")
    )
    db.session.add(new_entry)
    db.session.commit()
    return jsonify({"message": "Registro de dieta adicionado", "entry": new_entry.to_dict()}), 201

@user_bp.route("/diet", methods=["GET"])
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
            
    entries, _, _ = page_query(query.order_by(DietEntry.date.desc(), DietEntry.created_at.desc()), DietEntry)
    entries = entries.all()
    return jsonify([entry.to_dict() for entry in entries]), 200

@user_bp.route("/diet/<int:entry_id>", methods=["PUT"])
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

@user_bp.route("/diet/<int:entry_id>", methods=["DELETE"])
@login_required
def delete_diet_entry(entry_id):
    user = g.user
    entry = DietEntry.query.filter_by(id=entry_id, user_id=user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"message": "Registro de dieta excluído"}), 200

@user_bp.route("/diet/ai_macros", methods=["POST"])
@rate_limit("ai", 8, 60)
@login_required
def get_ai_macros():
    data = json_body()
    description = str(data.get("description", "")).strip()
    if not description:
        return jsonify({"error": "Descrição do alimento é obrigatória"}), 400
    
    try:
        return jsonify(calculate_nutrition(description)), 200
    except AIResponseError:
        current_app.logger.warning("Gemini returned invalid nutrition JSON")
        return jsonify({"error": "A IA retornou macros incompletos. Tente novamente."}), 422
    except AIQuotaExceededError as error:
        current_app.logger.warning("Chat AI quota exceeded: %s", error)
        return jsonify({"error": str(error)}), 429
    except AIServiceError:
        current_app.logger.exception("Nutrition AI request failed")
        return jsonify({"error": "Não foi possível calcular macros no momento"}), 503

# --- Rotas de Medidas (Corrigido) ---
@user_bp.route("/measurements", methods=["POST"])
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
        notes=data.get("notes")
    )
    db.session.add(new_measurement)
    db.session.commit()
    return jsonify({"message": "Medida adicionada", "measurement": new_measurement.to_dict()}), 201

@user_bp.route("/measurements", methods=["GET"])
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
            
    measurements, _, _ = page_query(query.order_by(Measurement.date.desc(), Measurement.created_at.desc()), Measurement)
    measurements = measurements.all()
    return jsonify([m.to_dict() for m in measurements]), 200

@user_bp.route("/measurements/<int:measurement_id>", methods=["PUT"])
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

@user_bp.route("/measurements/<int:measurement_id>", methods=["DELETE"])
@login_required
def delete_measurement(measurement_id):
    user = g.user
    measurement = Measurement.query.filter_by(id=measurement_id, user_id=user.id).first_or_404()
    db.session.delete(measurement)
    db.session.commit()
    return jsonify({"message": "Medida excluída"}), 200

# --- Rotas de Estatísticas (Corrigido) ---
@user_bp.route("/stats", methods=["GET"])
@login_required
def get_stats():
    user = g.user
    latest_measurement = Measurement.query.filter_by(user_id=user.id).order_by(Measurement.date.desc()).first()
    total_diet_entries = DietEntry.query.filter_by(user_id=user.id).count()
    
    seven_days_ago = datetime.utcnow().date() - timedelta(days=7)
    recent_diet_entries = DietEntry.query.filter_by(user_id=user.id).filter(DietEntry.date >= seven_days_ago).count()
    
    return jsonify({
        "latest_measurement": latest_measurement.to_dict() if latest_measurement else None,
        "total_diet_entries": total_diet_entries,
        "recent_diet_entries": recent_diet_entries
    }), 200

# --- Rotas de Chat (Corrigido) ---
@user_bp.route("/chat", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required
def chat():
    user = g.user 
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    data = json_body()
    message = str(data.get("message", "")).strip()

    if not message or len(message) > 2_000:
        return jsonify({"error": "Mensagem vazia"}), 400
    try:
        plan_intent = chat_plan_intent(data, message)
        action = None
        if plan_intent == "diet_plan":
            response_text = "Vamos personalizar sua dieta. Responda ao questionário rápido para eu montar três dias rotativos."
            action = {"type": "open_diet_plan_questionnaire"}
        elif plan_intent == "workout_plan":
            response_text = "Vamos montar seu treino. Informe sua frequência, experiência e equipamentos no questionário rápido."
            action = {"type": "open_workout_questionnaire"}
        else:
            response_text = generate_response(message, user, profile)
        db.session.add(ChatMessage(user_id=user.id, message=message, response=response_text))
        db.session.commit()
    except AIResponseError as error:
        current_app.logger.warning("Chat AI response was unusable: %s", error)
        return jsonify({"error": str(error)}), 422
    except AIQuotaExceededError as error:
        current_app.logger.warning("Chat AI quota exceeded: %s", error)
        return jsonify({"error": str(error)}), 429
    except AIServiceError:
        current_app.logger.exception("Chat AI request failed")
        return jsonify({"error": "A IA está indisponível no momento"}), 503
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to persist AI response")
        return jsonify({"error": "Não foi possível salvar o resultado gerado"}), 422
    
    return jsonify({
        "response": response_text,
        "action": action,
    }), 200

@user_bp.route("/chat/history", methods=["GET"])
@premium_required
def chat_history():
    user = g.user
    messages, _, _ = page_query(ChatMessage.query.filter_by(user_id=user.id).order_by(ChatMessage.created_at.asc()), ChatMessage)
    messages = messages.all()
    return jsonify([msg.to_dict() for msg in messages]), 200

# --- Rotas de Planos (Corrigido) ---
@user_bp.route("/diet_plans/generate", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required
def create_guided_diet_plan():
    user = g.user
    try:
        questionnaire = validate_diet_questionnaire(json_body())
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências da dieta.", "fields": error.errors}), 400
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    try:
        generated = generate_diet_plan(questionnaire, profile)
        plan_data = normalize_diet_output(generated, questionnaire)
    except AIQuotaExceededError as error:
        return jsonify({"error": str(error)}), 429
    except AIResponseError:
        current_app.logger.warning("Diet plan AI returned invalid JSON")
        return jsonify({"error": "A dieta gerada ficou incompleta. Tente novamente."}), 502
    except AIServiceError:
        current_app.logger.exception("Diet plan generation failed")
        return jsonify({"error": "A IA não conseguiu gerar a dieta agora."}), 503
    except PlanValidationError as error:
        current_app.logger.warning("Invalid generated diet plan: %s", error.errors)
        return jsonify({"error": "A dieta gerada ficou incompleta. Tente novamente."}), 502

    try:
        plan = DietPlan(
            user_id=user.id,
            title=plan_data["title"],
            description=plan_data["description"],
            schema_version=2,
            plan_mode="rotation_3_day",
            goal_code=questionnaire["goal"],
            meals_per_day=questionnaire["meals_per_day"],
            generation_context=questionnaire,
        )
        db.session.add(plan)
        db.session.flush()
        allowed = {
            "day_of_week", "meal_type", "description", "calories", "protein", "carbs", "fat",
            "notes", "items", "prep_instructions", "prep_minutes", "substitutions", "order",
        }
        for meal in plan_data["meals"]:
            db.session.add(DietPlanMeal(
                diet_plan_id=plan.id,
                **{key: meal[key] for key in allowed if key in meal},
            ))
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save guided diet plan")
        return jsonify({"error": "Não foi possível salvar a dieta gerada."}), 422
    response = jsonify({"message": "Plano alimentar criado.", "plan_id": plan.id, "plan": plan.to_dict_full()})
    response.status_code = 201
    response.headers["Location"] = f"/api/diet_plans/{plan.id}"
    return response


@user_bp.route("/workout_plans/generate", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required
def create_guided_workout_plan():
    user = g.user
    try:
        questionnaire = validate_workout_questionnaire(json_body())
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências do treino.", "fields": error.errors}), 400
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    try:
        generated = generate_workout_plan(questionnaire, profile)
        plan_data = normalize_workout_output(generated, questionnaire)
    except AIQuotaExceededError as error:
        return jsonify({"error": str(error)}), 429
    except AIResponseError:
        current_app.logger.warning("Workout plan AI returned invalid JSON")
        return jsonify({"error": "O treino gerado ficou incompleto. Tente novamente."}), 502
    except AIServiceError:
        current_app.logger.exception("Workout plan generation failed")
        return jsonify({"error": "A IA não conseguiu gerar o treino agora."}), 503
    except PlanValidationError as error:
        current_app.logger.warning("Invalid generated workout plan: %s", error.errors)
        return jsonify({"error": "O treino gerado ficou incompleto. Tente novamente."}), 502

    try:
        plan = WorkoutPlan(
            user_id=user.id,
            title=plan_data["title"],
            description=plan_data["description"],
            split_type=questionnaire["split_type"],
            days_per_week=questionnaire["days_per_week"],
            goal=questionnaire["goal"],
            experience_level=questionnaire["experience_level"],
            session_duration=questionnaire["session_duration"],
            questionnaire_data=questionnaire,
        )
        db.session.add(plan)
        db.session.flush()
        exercise_fields = {
            "catalog_key", "name", "movement_pattern", "primary_muscle", "equipment", "difficulty",
            "sets", "reps", "weight", "rest_seconds", "effort_guidance", "notes", "order",
        }
        for day_data in plan_data["days"]:
            day = WorkoutDay(
                workout_plan_id=plan.id,
                code=day_data["code"],
                title=day_data["title"],
                focus=day_data["focus"],
                order=day_data["order"],
            )
            db.session.add(day)
            db.session.flush()
            for exercise in day_data["exercises"]:
                db.session.add(WorkoutExercise(
                    workout_plan_id=plan.id,
                    workout_day_id=day.id,
                    **{key: exercise[key] for key in exercise_fields if key in exercise},
                ))
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save guided workout plan")
        return jsonify({"error": "Não foi possível salvar o treino gerado."}), 422
    response = jsonify({"message": "Plano de treino criado.", "plan_id": plan.id, "plan": plan.to_dict_full()})
    response.status_code = 201
    response.headers["Location"] = f"/api/workout_plans/{plan.id}"
    return response


@user_bp.route("/diet_plans", methods=["GET"])
@login_required
def get_diet_plans():
    user = g.user
    plans, _, _ = page_query(
        DietPlan.query.filter_by(user_id=user.id)
        .options(selectinload(DietPlan.meals))
        .order_by(DietPlan.created_at.desc()),
        DietPlan,
    )
    plans = plans.all()
    return jsonify([plan.to_dict() for plan in plans]), 200

@user_bp.route("/diet_plans/<int:plan_id>", methods=["GET"])
@login_required
def get_diet_plan_details(plan_id):
    user = g.user
    plan = DietPlan.query.filter_by(id=plan_id, user_id=user.id).options(selectinload(DietPlan.meals)).first_or_404()
    return jsonify(plan.to_dict_full()), 200

@user_bp.route("/diet_plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_diet_plan(plan_id):
    user = g.user
    plan = DietPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plano de dieta excluído com sucesso"}), 200


@user_bp.route("/diet_plans/<int:plan_id>/meals/<int:meal_id>", methods=["PATCH"])
@login_required
def update_diet_plan_meal(plan_id, meal_id):
    user = g.user
    plan = DietPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    meal = DietPlanMeal.query.filter_by(id=meal_id, diet_plan_id=plan.id).first_or_404()
    data = coerce_numbers(json_body(), ("calories", "protein", "carbs", "fat"))
    _require_lengths(data, {
        "meal_type": (50, "Tipo de refeição"),
        "notes": (500, "Observações"),
        "description": (2000, "Descrição"),
    })
    description = _text_or_none(data.get("description"))
    if data.get("description") is not None and not description:
        return jsonify({"error": "Descrição da refeição é obrigatória"}), 400
    if description:
        meal.description = description
    if data.get("items") is not None:
        items = data.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 8:
            return jsonify({"error": "Ingredientes inválidos"}), 400
        cleaned = [str(item).strip()[:160] for item in items if str(item).strip()]
        if not cleaned:
            return jsonify({"error": "A refeição precisa de ingredientes"}), 400
        meal.items = cleaned
        meal.description = ", ".join(cleaned)
    for field in ("meal_type", "notes"):
        if data.get(field) is not None:
            setattr(meal, field, data[field])
    for field in ("calories", "protein", "carbs", "fat"):
        if data.get(field) is not None:
            setattr(meal, field, data[field])
    db.session.commit()
    return jsonify({"message": "Refeição do plano atualizada", "meal": meal.to_dict()}), 200


@user_bp.route("/diet_plans/<int:plan_id>/suggest", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required
def suggest_diet_day(plan_id):
    user = g.user
    plan = DietPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    data = json_body()
    day_index = data.get("day")
    try:
        day_index = int(day_index)
    except (TypeError, ValueError):
        return jsonify({"error": "Dia inválido."}), 400
    if day_index not in {1, 2, 3}:
        return jsonify({"error": "Escolha um dia entre 1 e 3."}), 400
    feedback = str(data.get("feedback", "")).strip()[:500]

    questionnaire = plan.generation_context or {}
    if not questionnaire:
        return jsonify({"error": "Este plano não possui contexto para sugestões."}), 422
    existing_meals = [
        {"meal_type": meal.meal_type, "items": meal.items or [], "description": meal.description}
        for meal in plan.meals
        if meal.day_of_week == f"Dia {day_index}"
    ]
    if not existing_meals:
        return jsonify({"error": "Nenhuma refeição encontrada para este dia."}), 404
    if not feedback:
        return jsonify({"error": "Descreva a mudança desejada."}), 400

    profile = UserProfile.query.filter_by(user_id=user.id).first()
    try:
        generated = generate_diet_day(questionnaire, profile, existing_meals, feedback)
        day_data = normalize_diet_day(generated, questionnaire)
    except AIQuotaExceededError as error:
        return jsonify({"error": str(error)}), 429
    except AIResponseError:
        current_app.logger.warning("Diet day AI returned invalid JSON")
        return jsonify({"error": "A sugestão ficou incompleta. Tente novamente."}), 502
    except AIServiceError:
        current_app.logger.exception("Diet day generation failed")
        return jsonify({"error": "A IA não conseguiu sugerir mudanças agora."}), 503
    except PlanValidationError as error:
        current_app.logger.warning("Invalid generated diet day: %s", error.errors)
        return jsonify({"error": "A sugestão ficou incompleta. Tente novamente."}), 502
    return jsonify({"day": day_index, "meals": day_data["meals"]}), 200


@user_bp.route("/diet_plans/<int:plan_id>/days/<int:day_index>", methods=["PUT"])
@login_required
def replace_diet_day(plan_id, day_index):
    user = g.user
    plan = DietPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    if day_index not in {1, 2, 3}:
        return jsonify({"error": "Escolha um dia entre 1 e 3."}), 400
    data = json_body()
    meals = data.get("meals")
    if not isinstance(meals, list) or not meals or len(meals) > 8:
        return jsonify({"error": "Lista de refeições inválida."}), 400
    allowed = {
        "meal_type", "description", "calories", "protein", "carbs", "fat",
        "notes", "items", "prep_instructions", "prep_minutes", "substitutions", "order",
    }
    old_meals = [
        meal for meal in plan.meals if meal.day_of_week == f"Dia {day_index}"
    ]
    for meal in old_meals:
        db.session.delete(meal)
    for order, meal in enumerate(meals, start=1):
        meal_data = dict(meal)
        meal_data["order"] = order
        db.session.add(DietPlanMeal(
            diet_plan_id=plan.id,
            day_of_week=f"Dia {day_index}",
            **{key: meal_data[key] for key in allowed if key in meal_data},
        ))
    db.session.commit()
    return jsonify({"message": "Cardápio do dia atualizado.", "plan": plan.to_dict_full()}), 200

@user_bp.route("/workout_plans", methods=["GET"])
@login_required
def get_workout_plans():
    user = g.user
    plans, _, _ = page_query(
        WorkoutPlan.query.filter_by(user_id=user.id)
        .options(selectinload(WorkoutPlan.days), selectinload(WorkoutPlan.exercises))
        .order_by(WorkoutPlan.created_at.desc()),
        WorkoutPlan,
    )
    plans = plans.all()
    return jsonify([plan.to_dict() for plan in plans]), 200

@user_bp.route("/workout_plans/<int:plan_id>", methods=["GET"])
@login_required
def get_workout_plan_details(plan_id):
    user = g.user
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id).options(
        selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises),
        selectinload(WorkoutPlan.exercises),
    ).first_or_404()
    return jsonify(plan.to_dict_full()), 200

@user_bp.route("/workout_plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_workout_plan(plan_id):
    user = g.user
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id).with_for_update().first_or_404()
    if WorkoutSession.query.filter_by(workout_plan_id=plan.id, user_id=user.id, completed_at=None).first():
        return jsonify({"error": "Finalize o treino em andamento antes de excluir este plano."}), 409
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plano de treino excluído com sucesso"}), 200


def _owned_active_session(session_id):
    return WorkoutSession.query.filter_by(
        id=session_id,
        user_id=g.user.id,
        completed_at=None,
    ).with_for_update().first()


def _session_exercise(session, exercise_id):
    return WorkoutExercise.query.filter_by(
        id=exercise_id,
        workout_plan_id=session.workout_plan_id,
        workout_day_id=session.workout_day_id,
    ).first()


@user_bp.route("/workout_sessions/active", methods=["GET"])
@login_required
def get_user_active_workout_session():
    session_record = WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).first()
    if not session_record:
        return jsonify({"session": None}), 200
    return jsonify({
        "session": session_record.to_dict(),
        "plan": {"id": session_record.plan.id, "title": session_record.plan.title},
        "day": {"id": session_record.day.id, "title": session_record.day.title},
    }), 200


@user_bp.route("/workout_plans/<int:plan_id>/days/<int:day_id>/sessions/active", methods=["GET"])
@login_required
def get_active_workout_session(plan_id, day_id):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=g.user.id).first()
    if not plan or not WorkoutDay.query.filter_by(id=day_id, workout_plan_id=plan.id).first():
        return jsonify({"error": "Treino não encontrado."}), 404
    session_record = WorkoutSession.query.filter_by(
        user_id=g.user.id,
        workout_plan_id=plan.id,
        workout_day_id=day_id,
        completed_at=None,
    ).first()
    return jsonify({"session": session_record.to_dict() if session_record else None}), 200


@user_bp.route("/workout_plans/<int:plan_id>/days/<int:day_id>/sessions", methods=["POST"])
@login_required
def start_workout_session(plan_id, day_id):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=g.user.id).with_for_update().first()
    day = WorkoutDay.query.filter_by(id=day_id, workout_plan_id=plan.id if plan else None).first()
    if not plan or not day:
        return jsonify({"error": "Treino não encontrado."}), 404
    if not day.exercises:
        return jsonify({"error": "Este treino não possui exercícios para iniciar."}), 400
    active = WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).first()
    if active:
        if active.workout_plan_id == plan.id and active.workout_day_id == day.id:
            return jsonify({"session": active.to_dict()}), 200
        return jsonify({
            "error": "Finalize o treino em andamento antes de iniciar outro.",
            "session": active.to_dict(),
        }), 409
    session_record = WorkoutSession(
        user_id=g.user.id,
        workout_plan_id=plan.id,
        workout_day_id=day.id,
    )
    db.session.add(session_record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        active = WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).first()
        if active:
            if active.workout_plan_id == plan.id and active.workout_day_id == day.id:
                return jsonify({"session": active.to_dict()}), 200
            return jsonify({
                "error": "Outro treino foi iniciado ao mesmo tempo. Abra o treino em andamento.",
                "session": active.to_dict(),
            }), 409
        raise
    return jsonify({"session": session_record.to_dict()}), 201


@user_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/replacement_options", methods=["POST"])
@login_required
def get_exercise_replacement_options(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    data = json_body()
    unavailable = data.get("unavailable_equipment", [])
    available = data.get("available_equipment") or (session_record.plan.questionnaire_data or {}).get("equipment", [])
    if not isinstance(unavailable, list) or len(unavailable) > 10:
        return jsonify({"error": "Equipamentos indisponíveis inválidos."}), 400
    if not isinstance(available, list) or len(available) > 12:
        return jsonify({"error": "Equipamentos disponíveis inválidos."}), 400

    catalog_item = resolve_catalog_exercise(exercise.catalog_key, exercise.name)
    if not catalog_item and exercise.catalog_key != "__unresolved__":
        try:
            catalog_key = classify_exercise_catalog_key(exercise.name)
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceError:
            return jsonify({"error": "Não foi possível classificar este exercício agora."}), 503
        catalog_item = catalog_by_key().get(catalog_key)
        if catalog_item:
            exercise.catalog_key = catalog_item["key"]
            exercise.movement_pattern = catalog_item["movement_pattern"]
            exercise.primary_muscle = catalog_item["primary_muscle"]
            exercise.equipment = catalog_item["equipment"]
            exercise.difficulty = catalog_item["difficulty"]
        else:
            exercise.catalog_key = "__unresolved__"
        db.session.commit()
    options = replacement_options(exercise, unavailable, available)
    return jsonify({
        "exercise_id": exercise.id,
        "options": options,
        "source": "catalog",
        "message": None if options else "Não encontramos uma alternativa segura com os equipamentos informados.",
    }), 200


@user_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/replace", methods=["POST"])
@login_required
def replace_exercise_for_session(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    data = json_body()
    catalog_key = str(data.get("catalog_key", "")).strip()
    unavailable = data.get("unavailable_equipment", [])
    available = data.get("available_equipment") or (session_record.plan.questionnaire_data or {}).get("equipment", [])
    option = next((item for item in replacement_options(exercise, unavailable, available) if item["catalog_key"] == catalog_key), None)
    if not option:
        return jsonify({"error": "Essa substituição não é mais válida."}), 409
    override = WorkoutSessionExerciseOverride.query.filter_by(
        workout_session_id=session_record.id,
        workout_exercise_id=exercise.id,
    ).first()
    if not override:
        override = WorkoutSessionExerciseOverride(
            workout_session_id=session_record.id,
            workout_exercise_id=exercise.id,
            catalog_key=option["catalog_key"],
            name=option["name"],
        )
        db.session.add(override)
    for field in (
        "catalog_key", "name", "movement_pattern", "primary_muscle", "equipment", "difficulty",
        "sets", "reps", "weight", "rest_seconds", "effort_guidance", "notes",
    ):
        setattr(override, field, option.get(field))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        override = WorkoutSessionExerciseOverride.query.filter_by(
            workout_session_id=session_record.id,
            workout_exercise_id=exercise.id,
        ).one()
    return jsonify({"message": "Exercício substituído somente neste treino.", "override": override.to_dict()}), 200


@user_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/replace", methods=["DELETE"])
@login_required
def restore_session_exercise(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    override = WorkoutSessionExerciseOverride.query.filter_by(
        workout_session_id=session_record.id,
        workout_exercise_id=exercise.id,
    ).first()
    if override:
        db.session.delete(override)
        db.session.commit()
    return jsonify({"message": "Exercício original restaurado."}), 200


@user_bp.route("/workout_sessions/<int:session_id>/exercises/<int:exercise_id>/complete", methods=["POST"])
@login_required
def complete_session_exercise(session_id, exercise_id):
    session_record = _owned_active_session(session_id)
    exercise = _session_exercise(session_record, exercise_id) if session_record else None
    if not session_record or not exercise:
        return jsonify({"error": "Sessão ou exercício não encontrado."}), 404
    completion = WorkoutSessionExerciseCompletion.query.filter_by(
        workout_session_id=session_record.id,
        workout_exercise_id=exercise.id,
    ).first()
    if not completion:
        completion = WorkoutSessionExerciseCompletion(
            workout_session_id=session_record.id,
            workout_exercise_id=exercise.id,
        )
        db.session.add(completion)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            completion = WorkoutSessionExerciseCompletion.query.filter_by(
                workout_session_id=session_record.id,
                workout_exercise_id=exercise.id,
            ).one()
    return jsonify({"message": "Exercício concluído.", "session": session_record.to_dict()}), 200


@user_bp.route("/workout_sessions/<int:session_id>/finish", methods=["POST"])
@login_required
def finish_workout_session(session_id):
    session_record = _owned_active_session(session_id)
    if not session_record:
        return jsonify({"error": "Sessão de treino não encontrada."}), 404
    session_record.completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Treino finalizado.", "session": session_record.to_dict()}), 200

# --- Rotas de Admin (Corrigido) ---
@user_bp.route("/admin/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    stats = {
        "total_users": User.query.count(),
        "total_admins": User.query.filter_by(is_admin=True).count(),
        "total_banned": User.query.filter_by(is_banned=True).count(),
        "total_diet_entries": DietEntry.query.count(),
        "total_measurements": Measurement.query.count(),
        "total_chat_messages": ChatMessage.query.count()
    }
    return jsonify(stats), 200

@user_bp.route("/admin/users", methods=["GET"])
@admin_required
def list_users():
    users, _, _ = page_query(User.query.order_by(User.created_at.desc()), User)
    users = users.all()
    user_ids = [user.id for user in users]
    if not user_ids:
        return jsonify([]), 200

    def grouped_counts(model):
        return dict(db.session.query(model.user_id, func.count(model.id)).filter(model.user_id.in_(user_ids)).group_by(model.user_id))

    counts = {
        "diet_entries": grouped_counts(DietEntry),
        "measurements": grouped_counts(Measurement),
        "chat_messages": grouped_counts(ChatMessage),
        "workout_plans": grouped_counts(WorkoutPlan),
        "diet_plans": grouped_counts(DietPlan),
        "profiles": set(value for value, in db.session.query(UserProfile.user_id).filter(UserProfile.user_id.in_(user_ids))),
    }
    return jsonify([user.to_dict({
        "diet_entries": counts["diet_entries"].get(user.id, 0), "measurements": counts["measurements"].get(user.id, 0),
        "chat_messages": counts["chat_messages"].get(user.id, 0), "workout_plans": counts["workout_plans"].get(user.id, 0),
        "diet_plans": counts["diet_plans"].get(user.id, 0), "has_profile": user.id in counts["profiles"],
    }) for user in users]), 200

@user_bp.route("/admin/users/<uuid:user_id>/ban", methods=["POST"])
@admin_required
def ban_user(user_id):
    user_to_ban = db.get_or_404(User, user_id)
    if user_to_ban.is_admin:
        return jsonify({"error": "Não é possível banir um administrador."}), 403
    user_to_ban.ban_user()
    db.session.commit()
    return jsonify({"message": f"Usuário {user_to_ban.username} banido com sucesso."}), 200

@user_bp.route("/admin/users/<uuid:user_id>/unban", methods=["POST"])
@admin_required
def unban_user(user_id):
    user_to_unban = db.get_or_404(User, user_id)
    user_to_unban.unban_user()
    db.session.commit()
    return jsonify({"message": f"Usuário {user_to_unban.username} desbanido com sucesso."}), 200

@user_bp.route("/admin/users/<uuid:user_id>/premium", methods=["PATCH"])
@admin_required
def update_premium_status(user_id):
    data = json_body()
    is_premium = data.get("is_premium")
    if not isinstance(is_premium, bool):
        return jsonify({"error": "is_premium deve ser verdadeiro ou falso"}), 400

    user_to_update = db.get_or_404(User, user_id)
    user_to_update.is_premium = is_premium
    db.session.commit()
    action = "concedido" if is_premium else "revogado"
    return jsonify({
        "message": f"Acesso Premium {action} para {user_to_update.username}.",
        "user": user_to_update.to_dict(),
    }), 200

@user_bp.route("/admin/users/<uuid:user_id>/toggle_admin", methods=["POST"])
@admin_required
def toggle_admin_status(user_id):
    admin_user = g.user
    user_to_toggle = db.get_or_404(User, user_id)
    
    if user_to_toggle.id == admin_user.id:
        return jsonify({"error": "Você não pode remover seus próprios privilégios de administrador."}), 403

    demoting = user_to_toggle.is_admin
    if demoting and User.query.filter_by(is_admin=True).count() <= 1:
        return jsonify({"error": "Não é possível remover o último administrador."}), 403

    user_to_toggle.is_admin = not user_to_toggle.is_admin
    db.session.commit()
    status = "promovido a" if user_to_toggle.is_admin else "rebaixado de"
    return jsonify({"message": f"Usuário {user_to_toggle.username} {status} administrador."}), 200

@user_bp.route("/admin/recent_activity", methods=["GET"])
@admin_required
def get_recent_activity():
    limit = 10
    recent_diet = DietEntry.query.order_by(DietEntry.created_at.desc()).options(joinedload(DietEntry.user)).limit(limit).all()
    recent_measurements = Measurement.query.order_by(Measurement.created_at.desc()).options(joinedload(Measurement.user)).limit(limit).all()
    recent_chats = ChatMessage.query.order_by(ChatMessage.created_at.desc()).options(joinedload(ChatMessage.user)).limit(limit).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(limit).all()

    activities = []
    for d in recent_diet:
        activities.append({"type": "diet", "username": d.user.username, "description": d.description, "created_at": d.created_at.isoformat()})
    for m in recent_measurements:
        activities.append({"type": "measurement", "username": m.user.username, "created_at": m.created_at.isoformat()})
    for c in recent_chats:
        activities.append({"type": "chat", "username": c.user.username, "created_at": c.created_at.isoformat()})
    for u in recent_users:
        activities.append({"type": "user", "username": u.username, "created_at": u.created_at.isoformat()})

    activities.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(activities[:20]), 200
