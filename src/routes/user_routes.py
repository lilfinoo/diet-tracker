from flask import Blueprint, jsonify, request, session, redirect, url_for, abort, g
from src.models.user import User, DietEntry, Measurement, UserProfile, ChatMessage, db, WorkoutPlan, WorkoutExercise, DietPlan, DietPlanMeal
from datetime import datetime, date, timedelta
from functools import wraps
import openai
import os
import json
import re

# Decorador para exigir login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify({"error": "Login necessário"}), 401
        
        # Carrega o usuário e anexa ao 'g' para uso em toda a requisição
        g.user = User.query.get(user_id)

        if g.user is None:
            # Caso o user_id na sessão seja inválido, limpa a sessão
            session.pop("user_id", None)
            return jsonify({"error": "Usuário não encontrado"}), 401
            
        return f(*args, **kwargs)
    return decorated_function

# Decorador para exigir que o usuário seja admin
def admin_required(f):
    @wraps(f)
    @login_required # Garante que g.user já existe
    def decorated_function(*args, **kwargs):
        if not g.user.is_admin:
            return abort(403) # Proibido se não for admin
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

# --- Funções de IA (Sem alterações) ---
def calculate_nutrition_with_ai(food_description):
    """
    Calcula informações nutricionais usando ChatGPT-4o e retorna precisão.
    """
    is_vague = not re.search(r"\d|grama|colher|concha|fatia|ml|xícara|porção|unidade", food_description, re.IGNORECASE)
    prompt = f"""
Analise a seguinte descrição de alimentos e forneça as informações nutricionais com maior precisão possível em formato JSON.
Descrição: {food_description}
Responda APENAS com um JSON válido no seguinte formato:
{{
    "calories": número_de_calorias,
    "protein": gramas_de_proteína,
    "carbs": gramas_de_carboidratos,
    "fat": gramas_de_gordura
}}
Seja preciso e considere porções típicas mencionadas.
"""
    if is_vague:
        prompt += "\nSe não houver quantidades, assuma porções médias brasileiras para cada item listado."
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você é um nutricionista especializado em análise nutricional. Responda sempre com JSON válido."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.3
        )
        content = response.choices[0].message.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            nutrition_data = json.loads(json_match.group())
            precision = "baixa" if is_vague else "alta"
            return {
                "calories": float(nutrition_data.get("calories", 0)),
                "protein": float(nutrition_data.get("protein", 0)),
                "carbs": float(nutrition_data.get("carbs", 0)),
                "fat": float(nutrition_data.get("fat", 0)),
                "precision": precision
            }
        else:
            raise ValueError("Resposta não contém JSON válido")
    except Exception as e:
        print(f"Erro ao calcular nutrição: {e}")
        return {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "precision": "baixa"}

def generate_ai_response(message, user, profile):
    """Gera resposta da IA usando ChatGPT-4o para conversas gerais"""
    try:
        context = f"Você é um assistente fitness especializado em nutrição e treino. O usuário se chama {user.username}. "
        if profile:
            if profile.age: context += f"Tem {profile.age} anos. "
            if profile.gender: context += f"Gênero: {profile.gender}. "
            if profile.goal: context += f"Objetivo: {profile.goal}. "
            if profile.activity_level: context += f"Nível de atividade: {profile.activity_level}. "
            if profile.dietary_restrictions: context += f"Restrições alimentares: {profile.dietary_restrictions}. "
            if profile.weight: context += f"Peso: {profile.weight} kg. "
            if profile.height: context += f"Altura: {profile.height} cm. "
        context += "Responda de forma amigável, útil e personalizada. Use emojis quando apropriado."
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": message}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro na IA: {e}")
        message_lower = message.lower()
        if any(word in message_lower for word in ["olá", "oi", "hello"]):
            return f"Olá {user.username}! 👋 Como posso ajudá-lo hoje?"
        elif any(word in message_lower for word in ["dieta", "alimentação"]):
            return "🥗 Posso ajudar com dicas de alimentação! Qual é sua dúvida específica?"
        elif any(word in message_lower for word in ["treino", "exercício"]):
            return "💪 Vamos falar sobre treino! O que você gostaria de saber?"
        else:
            return "Desculpe, estou com dificuldades técnicas. Tente reformular sua pergunta."

def generate_structured_plan_with_ai(message, user, profile):
    context = f"Você é um assistente fitness especializado em nutrição e treino. O usuário se chama {user.username}. "
    if profile:
        context += f"Tem {profile.age} anos. Gênero: {profile.gender}. Objetivo: {profile.goal}. Nível de atividade: {profile.activity_level}. Restrições alimentares: {profile.dietary_restrictions}. "
        if profile.weight: context += f"Peso: {profile.weight} kg. "
        if profile.height: context += f"Altura: {profile.height} cm. "
    context += """
Gere um plano detalhado em formato JSON.
Se for um plano de dieta, use o formato:
{
    "type": "diet_plan", "title": "Título", "description": "Descrição.",
    "meals": [{"day_of_week": "Segunda-feira", "meal_type": "Café da Manhã", "description": "...", "calories": 250, "protein": 18, "carbs": 25, "fat": 10, "notes": "..."}]
}
Se for um plano de treino, use o formato:
{
    "type": "workout_plan", "title": "Título", "description": "Descrição.",
    "exercises": [{"name": "Agachamento", "sets": 3, "reps": "8-12", "weight": "20kg", "notes": "..."}]
}
Responda APENAS com o JSON válido.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": message}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json_match.group()
        return content
    except Exception as e:
        print(f"Erro na IA ao gerar plano: {e}")
        return "Desculpe, não consegui gerar um plano estruturado no momento."

# --- Rotas de Autenticação ---
@user_bp.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Nome de usuário e senha são obrigatórios"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Nome de usuário já existe"}), 400
    
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    session["user_id"] = user.id
    session["username"] = user.username
    return jsonify({"message": "Usuário criado com sucesso", "user": user.to_dict()}), 201

@user_bp.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
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
        user = User.query.get(user_id)
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
    data = request.json
    
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
    data = request.json
    
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
            
    entries = query.order_by(DietEntry.date.desc(), DietEntry.created_at.desc()).all()
    return jsonify([entry.to_dict() for entry in entries]), 200

@user_bp.route("/diet/<int:entry_id>", methods=["PUT"])
@login_required
def update_diet_entry(entry_id):
    user = g.user
    data = request.json
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
@login_required
def get_ai_macros():
    data = request.json
    description = data.get("description")
    if not description:
        return jsonify({"error": "Descrição do alimento é obrigatória"}), 400
    
    nutrition_data = calculate_nutrition_with_ai(description)
    return jsonify(nutrition_data), 200

# --- Rotas de Medidas (Corrigido) ---
@user_bp.route("/measurements", methods=["POST"])
@login_required
def add_measurement():
    user = g.user
    data = request.json
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
            
    measurements = query.order_by(Measurement.date.desc(), Measurement.created_at.desc()).all()
    return jsonify([m.to_dict() for m in measurements]), 200

@user_bp.route("/measurements/<int:measurement_id>", methods=["PUT"])
@login_required
def update_measurement(measurement_id):
    user = g.user
    data = request.json
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
@premium_required
def chat():
    user = g.user 
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    data = request.json
    message = data.get("message")

    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400
    
    response_text = ""
    
    if "plano de dieta" in message.lower() or "plano de alimentação" in message.lower():
        ai_response_json = generate_structured_plan_with_ai(message, user, profile)
        try:
            plan_data = json.loads(ai_response_json)
            if plan_data.get("type") == "diet_plan":
                new_diet_plan = DietPlan(
                    user_id=user.id,
                    title=plan_data.get("title", "Plano de Dieta Gerado pela IA"),
                    description=plan_data.get("description", "Plano de dieta personalizado.")
                )
                db.session.add(new_diet_plan)
                db.session.flush()

                if "meals" in plan_data and isinstance(plan_data["meals"], list):
                    for meal_data in plan_data["meals"]:
                        db.session.add(DietPlanMeal(diet_plan_id=new_diet_plan.id, **meal_data))
                db.session.commit()
                response_text = f"✅ Seu plano de dieta '{new_diet_plan.title}' foi gerado e salvo!"
            else:
                response_text = "Desculpe, não consegui gerar um plano de dieta válido."
        except Exception as e:
            db.session.rollback()
            response_text = f"Ocorreu um erro ao salvar o plano de dieta: {e}."

    elif "plano de treino" in message.lower() or "rotina de exercícios" in message.lower():
        ai_response_json = generate_structured_plan_with_ai(message, user, profile)
        try:
            plan_data = json.loads(ai_response_json)
            if plan_data.get("type") == "workout_plan":
                new_workout_plan = WorkoutPlan(
                    user_id=user.id,
                    title=plan_data.get("title", "Plano de Treino Gerado pela IA"),
                    description=plan_data.get("description", "Plano de treino personalizado.")
                )
                db.session.add(new_workout_plan)
                db.session.flush()

                if "exercises" in plan_data and isinstance(plan_data["exercises"], list):
                    for exercise_data in plan_data["exercises"]:
                        db.session.add(WorkoutExercise(workout_plan_id=new_workout_plan.id, **exercise_data))
                db.session.commit()
                response_text = f"✅ Seu plano de treino '{new_workout_plan.title}' foi gerado e salvo!"
            else:
                response_text = "Desculpe, não consegui gerar um plano de treino válido."
        except Exception as e:
            db.session.rollback()
            response_text = f"Ocorreu um erro ao salvar o plano de treino: {e}."

    else:
        response_text = generate_ai_response(message, user, profile)
    
    new_chat_message = ChatMessage(user_id=user.id, message=message, response=response_text)
    db.session.add(new_chat_message)
    db.session.commit()
    
    return jsonify({"response": response_text}), 200

@user_bp.route("/chat/history", methods=["GET"])
@admin_required
def chat_history():
    user = g.user
    messages = ChatMessage.query.filter_by(user_id=user.id).order_by(ChatMessage.created_at.asc()).all()
    return jsonify([msg.to_dict() for msg in messages]), 200

# --- Rotas de Planos (Corrigido) ---
@user_bp.route("/diet_plans", methods=["GET"])
@login_required
def get_diet_plans():
    user = g.user
    plans = DietPlan.query.filter_by(user_id=user.id).order_by(DietPlan.created_at.desc()).all()
    return jsonify([plan.to_dict() for plan in plans]), 200

@user_bp.route("/diet_plans/<int:plan_id>", methods=["GET"])
@login_required
def get_diet_plan_details(plan_id):
    user = g.user
    plan = DietPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    return jsonify(plan.to_dict_full()), 200

@user_bp.route("/diet_plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_diet_plan(plan_id):
    user = g.user
    plan = DietPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plano de dieta excluído com sucesso"}), 200

@user_bp.route("/workout_plans", methods=["GET"])
@login_required
def get_workout_plans():
    user = g.user
    plans = WorkoutPlan.query.filter_by(user_id=user.id).order_by(WorkoutPlan.created_at.desc()).all()
    return jsonify([plan.to_dict() for plan in plans]), 200

@user_bp.route("/workout_plans/<int:plan_id>", methods=["GET"])
@login_required
def get_workout_plan_details(plan_id):
    user = g.user
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    return jsonify(plan.to_dict_full()), 200

@user_bp.route("/workout_plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_workout_plan(plan_id):
    user = g.user
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plano de treino excluído com sucesso"}), 200

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
    users = User.query.all()
    return jsonify([user.to_dict() for user in users]), 200

@user_bp.route("/admin/users/<int:user_id>/ban", methods=["POST"])
@admin_required
def ban_user(user_id):
    user_to_ban = User.query.get_or_404(user_id)
    if user_to_ban.is_admin:
        return jsonify({"error": "Não é possível banir um administrador."}), 403
    user_to_ban.ban_user()
    db.session.commit()
    return jsonify({"message": f"Usuário {user_to_ban.username} banido com sucesso."}), 200

@user_bp.route("/admin/users/<int:user_id>/unban", methods=["POST"])
@admin_required
def unban_user(user_id):
    user_to_unban = User.query.get_or_404(user_id)
    user_to_unban.unban_user()
    db.session.commit()
    return jsonify({"message": f"Usuário {user_to_unban.username} desbanido com sucesso."}), 200

@user_bp.route("/admin/users/<int:user_id>/toggle_admin", methods=["POST"])
@admin_required
def toggle_admin_status(user_id):
    admin_user = g.user
    user_to_toggle = User.query.get_or_404(user_id)
    
    if user_to_toggle.id == admin_user.id:
        return jsonify({"error": "Você não pode remover seus próprios privilégios de administrador."}), 403
    
    user_to_toggle.is_admin = not user_to_toggle.is_admin
    db.session.commit()
    status = "promovido a" if user_to_toggle.is_admin else "rebaixado de"
    return jsonify({"message": f"Usuário {user_to_toggle.username} {status} administrador."}), 200

@user_bp.route("/admin/recent_activity", methods=["GET"])
@admin_required
def get_recent_activity():
    limit = 10
    recent_diet = DietEntry.query.order_by(DietEntry.created_at.desc()).limit(limit).all()
    recent_measurements = Measurement.query.order_by(Measurement.created_at.desc()).limit(limit).all()
    recent_chats = ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(limit).all()
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
