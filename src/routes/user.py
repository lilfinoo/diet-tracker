from flask import Blueprint, jsonify, request, session
from src.models.user import User, DietEntry, Measurement, UserProfile, ChatMessage, db
from datetime import datetime, date, timedelta
from functools import wraps

user_bp = Blueprint("user", __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login necessário"}), 401
        return f(*args, **kwargs)
    return decorated_function

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

def generate_ai_response(message, user, profile):
    """Gera resposta da IA baseada na mensagem e perfil do usuário"""
    
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
    
    # Respostas baseadas em palavras-chave
    message_lower = message.lower()
    
    if any(word in message_lower for word in ["olá", "oi", "hello", "começar"]):
        if not profile:
            return f"Olá {user.username}! 👋 Bem-vindo ao Diet Tracker! Sou seu assistente fitness pessoal. Para começar, que tal me contar um pouco sobre você? Qual é seu objetivo principal: perder peso, ganhar massa muscular ou manter o peso atual?"
        else:
            return f"Olá {user.username}! 👋 Como posso ajudá-lo hoje? Posso dar dicas sobre nutrição, ajudar com o planejamento de refeições ou tirar dúvidas sobre o uso do site!"
    
    elif any(word in message_lower for word in ["como usar", "tutorial", "ajuda", "como funciona"]):
        return """📱 **Como usar o Diet Tracker:**

1. **Aba Dieta**: Registre suas refeições diárias
   - Clique em "Adicionar" para registrar uma refeição
   - Escolha o tipo (café, almoço, jantar, etc.)
   - Adicione o alimento, quantidade e calorias

2. **Aba Medidas**: Acompanhe sua evolução física
   - Registre peso, medidas corporais, % de gordura
   - Use os filtros de data para ver seu progresso

3. **Aba Estatísticas**: Veja seu resumo e evolução

Precisa de ajuda com algo específico?"""
    
    elif any(word in message_lower for word in ["dieta", "alimentação", "comida", "calorias"]):
        if profile and profile.goal:
            if "perder peso" in profile.goal.lower():
                return """🥗 **Dicas para Perda de Peso:**

• Crie um déficit calórico de 300-500 kcal/dia
• Priorize proteínas (1,6-2,2g por kg de peso)
• Inclua vegetais em todas as refeições
• Beba bastante água (35ml por kg de peso)
• Evite alimentos ultraprocessados

**Sugestão de refeição:**
- Café: Ovos mexidos + aveia + frutas
- Almoço: Peito de frango + arroz integral + salada
- Jantar: Peixe + batata doce + legumes

Quer que eu ajude a calcular suas necessidades calóricas?"""
            
            elif "ganhar massa" in profile.goal.lower():
                return """💪 **Dicas para Ganho de Massa:**

• Mantenha superávit calórico de 300-500 kcal/dia
• Consuma 2-2,5g de proteína por kg de peso
• Carboidratos: 4-6g por kg de peso
• Faça 5-6 refeições por dia
• Hidrate-se bem

**Sugestão de refeição:**
- Café: Aveia + whey + banana + pasta de amendoim
- Almoço: Carne + arroz + feijão + salada
- Jantar: Frango + macarrão integral + legumes

Precisa de ajuda para calcular suas macros?"""
        
        return """🍎 **Dicas Gerais de Alimentação:**

• Faça refeições regulares (3-5 por dia)
• Inclua proteína em cada refeição
• Consuma frutas e vegetais variados
• Beba 2-3 litros de água por dia
• Evite pular refeições

Qual é seu objetivo principal? Assim posso dar dicas mais específicas!"""
    
    elif any(word in message_lower for word in ["treino", "exercício", "academia", "musculação"]):
        if profile and profile.activity_level:
            if "sedentario" in profile.activity_level.lower():
                return """🏃‍♂️ **Começando a se Exercitar:**

• Comece com 2-3x por semana
• Foque em exercícios básicos (agachamento, flexão, prancha)
• Caminhadas de 20-30 minutos
• Aumente gradualmente a intensidade

**Treino Iniciante (3x semana):**
- Agachamento: 3x10
- Flexão (joelhos se necessário): 3x8
- Prancha: 3x30s
- Caminhada: 20 min

Quer um plano mais detalhado?"""
            
            else:
                return """💪 **Dicas de Treino:**

• Treine 3-5x por semana
• Combine musculação + cardio
• Descanse 48h entre treinos do mesmo grupo muscular
• Foque em exercícios compostos
• Progrida gradualmente

**Divisão Sugerida:**
- Segunda: Peito + Tríceps
- Terça: Costas + Bíceps  
- Quarta: Pernas + Glúteos
- Quinta: Ombros + Abdômen
- Sexta: Cardio

Precisa de ajuda com algum exercício específico?"""
        
        return """🏋️‍♂️ **Dicas Gerais de Treino:**

• Consistência é mais importante que intensidade
• Aqueça sempre antes do treino
• Foque na técnica correta
• Descanse adequadamente
• Vari



"""

