from flask import Blueprint, jsonify, request, session
from src.models.user import User, DietEntry, Measurement, UserProfile, ChatMessage, db
from datetime import datetime, date, timedelta
from functools import wraps
import openai
import os
import json
import re

# Configure sua chave da API OpenAI
# Defina esta variável de ambiente

user_bp = Blueprint("user", __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login necessário"}), 401
        return f(*args, **kwargs)
    return decorated_function
    
def calculate_nutrition_with_ai(food_description):
    """
    Calcula informações nutricionais usando ChatGPT-4o
    """
    try:
        prompt = f"""
Analise a seguinte descrição de alimentos e forneça as informações nutricionais aproximadas em formato JSON.

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

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # Modelo mais barato
            messages=[
                {"role": "system", "content": "Você é um nutricionista especializado em análise nutricional. Responda sempre com JSON válido."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,  # Limite para economizar
            temperature=0.3
        )
        
        # Extrair JSON da resposta
        content = response.choices[0].message.content.strip()
        
        # Tentar extrair JSON usando regex
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            nutrition_data = json.loads(json_match.group())
            return {
                "calories": float(nutrition_data.get("calories", 0)),
                "protein": float(nutrition_data.get("protein", 0)),
                "carbs": float(nutrition_data.get("carbs", 0)),
                "fat": float(nutrition_data.get("fat", 0))
            }
        else:
            raise ValueError("Resposta não contém JSON válido")
            
    except Exception as e:
        print(f"Erro ao calcular nutrição: {e}")
        # Valores padrão em caso de erro
        return {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0
        }

def generate_ai_response(message, user, profile):
    """Gera resposta da IA usando ChatGPT-4o"""
    
    try:
        # Contexto base
        context = f"Você é um assistente fitness especializado em nutrição e treino. "
        context += f"O usuário se chama {user.username}. "
        
        if profile:
            if profile.age:
                context += f"Tem {profile.age} anos. "
            if profile.gender:
                context += f"Gênero: {profile.gender}. "
            if profile.goal:
                context += f"Objetivo: {profile.goal}. "
            if profile.activity_level:
                context += f"Nível de atividade: {profile.activity_level}. "
            if profile.dietary_restrictions:
                context += f"Restrições alimentares: {profile.dietary_restrictions}. "
        
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
        # Fallback para respostas pré-definidas
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["olá", "oi", "hello"]):
            return f"Olá {user.username}! 👋 Como posso ajudá-lo hoje?"
        elif any(word in message_lower for word in ["dieta", "alimentação"]):
            return "🥗 Posso ajudar com dicas de alimentação! Qual é sua dúvida específica?"
        elif any(word in message_lower for word in ["treino", "exercício"]):
            return "💪 Vamos falar sobre treino! O que você gostaria de saber?"
        else:
            return "Desculpe, estou com dificuldades técnicas. Tente reformular sua pergunta."

    
    # Respostas baseadas em palavras-chave
    

# Rotas de Autenticação
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
            return jsonify({"error": "Usuário banido. Entre em contato com o suporte."}), 403
        
        session["user_id"] = user.id
        session["username"] = user.username
        return jsonify({"message": "Login realizado com sucesso", "user": user.to_dict()}), 200
    
    return jsonify({"error": "Credenciais inválidas"}), 401

@user_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logout realizado com sucesso"}), 200

@user_bp.route("/check_session", methods=["GET"])
def check_session():
    if "user_id" in session:
        user = User.query.get(session["user_id"])
        if user:
            return jsonify({
                "logged_in": True,
                "user": user.to_dict()
            }), 200
        else:
            # Usuário não existe mais, limpar sessão
            session.clear()
    
    return jsonify({"logged_in": False}), 200

@user_bp.route("/user_profile", methods=["GET"])
@login_required
def get_user_profile():
    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return jsonify({"error": "Usuário não encontrado"}), 404
    return jsonify(user.to_dict())

# Rotas de Dieta
@user_bp.route("/diet", methods=["GET"])
@login_required
def get_diet_entries():
    user_id = session["user_id"]
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    
    query = DietEntry.query.filter_by(user_id=user_id)
    
    if start_date:
        query = query.filter(DietEntry.date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.filter(DietEntry.date <= datetime.strptime(end_date, "%Y-%m-%d").date())
    
    entries = query.order_by(DietEntry.date.desc(), DietEntry.created_at.desc()).all()
    return jsonify([entry.to_dict() for entry in entries])

@user_bp.route("/diet", methods=["POST"])
@login_required
def create_diet_entry():
    data = request.json
    user_id = session["user_id"]
    
    # Calcular nutrientes usando IA
    nutrition = calculate_nutrition_with_ai(data["description"])
    
    entry = DietEntry(
        user_id=user_id,
        date=datetime.strptime(data["date"], "%Y-%m-%d").date(),
        meal_type=data["meal_type"],
        description=data["description"],
        calories=nutrition["calories"],
        protein=nutrition["protein"],
        carbs=nutrition["carbs"],
        fat=nutrition["fat"],
        notes=data.get("notes")
    )
    
    db.session.add(entry)
    db.session.commit()
    
    return jsonify(entry.to_dict()), 201

@user_bp.route("/diet/<int:entry_id>", methods=["PUT"])
@login_required
def update_diet_entry(entry_id):
    user_id = session["user_id"]
    entry = DietEntry.query.filter_by(id=entry_id, user_id=user_id).first_or_404()
    
    data = request.json
    
    # Recalcular nutrientes se a descrição mudou
    if data["description"] != entry.description:
        nutrition = calculate_nutrition_with_ai(data["description"])
        entry.calories = nutrition["calories"]
        entry.protein = nutrition["protein"]
        entry.carbs = nutrition["carbs"]
        entry.fat = nutrition["fat"]
    
    entry.date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    entry.meal_type = data["meal_type"]
    entry.description = data["description"]
    entry.notes = data.get("notes")
    
    db.session.commit()
    return jsonify(entry.to_dict())

@user_bp.route("/diet/<int:entry_id>", methods=["DELETE"])
@login_required
def delete_diet_entry(entry_id):
    user_id = session["user_id"]
    entry = DietEntry.query.filter_by(id=entry_id, user_id=user_id).first_or_404()
    
    db.session.delete(entry)
    db.session.commit()
    
    return "", 204

# Rotas de Medidas
@user_bp.route("/measurements", methods=["GET"])
@login_required
def get_measurements():
    user_id = session["user_id"]
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    
    query = Measurement.query.filter_by(user_id=user_id)
    
    if start_date:
        query = query.filter(Measurement.date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.filter(Measurement.date <= datetime.strptime(end_date, "%Y-%m-%d").date())
    
    measurements = query.order_by(Measurement.date.desc()).all()
    return jsonify([measurement.to_dict() for measurement in measurements])

@user_bp.route("/measurements", methods=["POST"])
@login_required
def create_measurement():
    data = request.json
    user_id = session["user_id"]
    
    measurement = Measurement(
        user_id=user_id,
        date=datetime.strptime(data["date"], "%Y-%m-%d").date(),
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
    
    db.session.add(measurement)
    db.session.commit()
    
    return jsonify(measurement.to_dict()), 201

@user_bp.route("/measurements/<int:measurement_id>", methods=["PUT"])
@login_required
def update_measurement(measurement_id):
    user_id = session["user_id"]
    measurement = Measurement.query.filter_by(id=measurement_id, user_id=user_id).first_or_404()
    
    data = request.json
    measurement.date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    measurement.weight = data.get("weight")
    measurement.height = data.get("height")
    measurement.body_fat = data.get("body_fat")
    measurement.muscle_mass = data.get("muscle_mass")
    measurement.waist = data.get("waist")
    measurement.chest = data.get("chest")
    measurement.arm = data.get("arm")
    measurement.thigh = data.get("thigh")
    measurement.notes = data.get("notes")
    
    db.session.commit()
    return jsonify(measurement.to_dict())

@user_bp.route("/measurements/<int:measurement_id>", methods=["DELETE"])
@login_required
def delete_measurement(measurement_id):
    user_id = session["user_id"]
    measurement = Measurement.query.filter_by(id=measurement_id, user_id=user_id).first_or_404()
    
    db.session.delete(measurement)
    db.session.commit()
    
    return "", 204

# Rota para estatísticas
@user_bp.route("/stats", methods=["GET"])
@login_required
def get_stats():
    user_id = session["user_id"]
    
    # Últimas medidas
    latest_measurement = Measurement.query.filter_by(user_id=user_id).order_by(Measurement.date.desc()).first()
    
    # Total de entradas de dieta
    total_diet_entries = DietEntry.query.filter_by(user_id=user_id).count()
    
    # Entradas de dieta dos últimos 7 dias
    seven_days_ago = date.today() - timedelta(days=7)
    recent_diet_entries = DietEntry.query.filter_by(user_id=user_id).filter(DietEntry.date >= seven_days_ago).count()
    
    return jsonify({
        "latest_measurement": latest_measurement.to_dict() if latest_measurement else None,
        "total_diet_entries": total_diet_entries,
        "recent_diet_entries": recent_diet_entries
    })


# Rotas para Perfil do Usuário
@user_bp.route("/profile", methods=["GET"])
@login_required
def get_profile():
    user_id = session["user_id"]
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    
    if not profile:
        return jsonify({"profile": None}), 200
    
    return jsonify({"profile": profile.to_dict()}), 200

@user_bp.route("/profile", methods=["POST", "PUT"])
@login_required
def save_profile():
    user_id = session["user_id"]
    data = request.json
    
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.session.add(profile)
    
    profile.age = data.get("age")
    profile.gender = data.get("gender")
    profile.goal = data.get("goal")
    profile.activity_level = data.get("activity_level")
    profile.dietary_restrictions = data.get("dietary_restrictions")
    profile.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({"message": "Perfil salvo com sucesso", "profile": profile.to_dict()}), 200

# Rotas para Chat com IA
@user_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    user_id = session["user_id"]
    data = request.json
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"error": "Mensagem não pode estar vazia"}), 400
    
    # Buscar perfil do usuário para personalizar resposta
    user = User.query.get(user_id)
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    
    # Gerar resposta da IA
    response = generate_ai_response(message, user, profile)
    
    # Salvar conversa no banco
    chat_message = ChatMessage(
        user_id=user_id,
        message=message,
        response=response
    )
    db.session.add(chat_message)
    db.session.commit()
    
    return jsonify({
        "message": message,
        "response": response,
        "timestamp": chat_message.created_at.isoformat()
    }), 200

@user_bp.route("/chat/history", methods=["GET"])
@login_required
def chat_history():
    user_id = session["user_id"]
    limit = request.args.get("limit", 50, type=int)
    
    messages = ChatMessage.query.filter_by(user_id=user_id)\
        .order_by(ChatMessage.created_at.desc())\
        .limit(limit)\
        .all()
    
    return jsonify({
        "messages": [msg.to_dict() for msg in reversed(messages)]
    }), 200

