from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
from sqlalchemy_utils import UUIDType
# Importa para hashing de senhas
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    banned_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_premium = db.Column(db.Boolean, default=False, nullable=False)
    is_adm = db.Column(db.Boolean, default=False, nullable=False)

    # Relacionamentos
    diet_entries = db.relationship("DietEntry", backref="user", lazy=True, cascade="all, delete-orphan")
    measurements = db.relationship("Measurement", backref="user", lazy=True, cascade="all, delete-orphan")
    profile = db.relationship("UserProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="user", lazy=True, cascade="all, delete-orphan")
    
    # NOVOS RELACIONAMENTOS PARA PLANOS
    workout_plans = db.relationship("WorkoutPlan", backref="user", lazy=True, cascade="all, delete-orphan")
    diet_plans = db.relationship("DietPlan", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def ban_user(self):
        self.is_banned = True
        self.banned_at = datetime.utcnow()

    def unban_user(self):
        self.is_banned = False
        self.banned_at = None

    def __repr__(self):
        return f"<User {self.username}>"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "is_banned": self.is_banned,
            "banned_at": self.banned_at.isoformat() if self.banned_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_admin": self.is_admin,
            "diet_entries_count": len(self.diet_entries) if self.diet_entries else 0, # Renomeado para evitar conflito
            "measurements_count": len(self.measurements) if self.measurements else 0, # Renomeado
            "chat_messages_count": len(self.chat_messages) if self.chat_messages else 0, # Renomeado
            "has_profile": self.profile is not None,
            "workout_plans_count": len(self.workout_plans) if self.workout_plans else 0, # NOVO
            "diet_plans_count": len(self.diet_plans) if self.diet_plans else 0 # NOVO
        }

class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False, unique=True) # Perfil único por usuário
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(10), nullable=True)  # masculino, feminino
    goal = db.Column(db.String(100), nullable=True)  # perder peso, ganhar massa, manter
    activity_level = db.Column(db.String(50), nullable=True)  # sedentario, leve, moderado, intenso
    dietary_restrictions = db.Column(db.Text, nullable=True)
    # Adicionado peso e altura ao perfil para a IA
    weight = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "age": self.age,
            "gender": self.gender,
            "goal": self.goal,
            "activity_level": self.activity_level,
            "dietary_restrictions": self.dietary_restrictions,
            "weight": self.weight,
            "height": self.height,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "message": self.message,
            "response": self.response,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class DietEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)  # café, almoço, jantar, lanche
    description = db.Column(db.Text, nullable=False)  # Descrição livre do que foi consumido
    calories = db.Column(db.Float, nullable=True)  # Calculado pela IA
    protein = db.Column(db.Float, nullable=True)  # Proteínas em gramas
    carbs = db.Column(db.Float, nullable=True)  # Carboidratos em gramas
    fat = db.Column(db.Float, nullable=True)  # Gorduras em gramas
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DietEntry {self.description[:50]} - {self.date}>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "meal_type": self.meal_type,
            "description": self.description,
            "calories": self.calories,
            "protein": self.protein,
            "carbs": self.carbs,
            "fat": self.fat,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Measurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey('user.id'), nullable=False) # <--- Mude para UUIDType
    date = db.Column(db.Date, nullable=False)
    weight = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    body_fat = db.Column(db.Float, nullable=True)
    muscle_mass = db.Column(db.Float, nullable=True)
    waist = db.Column(db.Float, nullable=True)
    chest = db.Column(db.Float, nullable=True)
    arm = db.Column(db.Float, nullable=True)
    thigh = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Measurement {self.date} - User {self.user_id}>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "weight": self.weight,
            "height": self.height,
            "body_fat": self.body_fat,
            "muscle_mass": self.muscle_mass,
            "waist": self.waist,
            "chest": self.chest,
            "arm": self.arm,
            "thigh": self.thigh,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

# --- NOVOS MODELOS PARA PLANOS DE TREINO E DIETA ---

class WorkoutPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey('user.id'), nullable=False) # <--- Mude para UUIDType
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True) # Descrição geral do plano
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamento com exercícios específicos
    exercises = db.relationship("WorkoutExercise", backref="plan", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "exercises_count": len(self.exercises) # Exemplo
        }

class WorkoutExercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workout_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sets = db.Column(db.Integer, nullable=True)
    reps = db.Column(db.String(50), nullable=True) # Ex: "8-12", "até a falha"
    weight = db.Column(db.String(50), nullable=True) # Ex: "10kg", "peso corporal"
    notes = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, nullable=True) # Ordem dos exercícios no plano

    def to_dict(self):
        return {
            "id": self.id,
            "workout_plan_id": self.workout_plan_id,
            "name": self.name,
            "sets": self.sets,
            "reps": self.reps,
            "weight": self.weight,
            "notes": self.notes,
            "order": self.order
        }

class DietPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True) # Descrição geral do plano
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamento com refeições específicas do plano
    meals = db.relationship("DietPlanMeal", backref="plan", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "meals_count": len(self.meals) # Exemplo
        }

class DietPlanMeal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    diet_plan_id = db.Column(db.Integer, db.ForeignKey("diet_plan.id"), nullable=False)
    day_of_week = db.Column(db.String(20), nullable=True) # Ex: "Segunda", "Todos os dias"
    meal_type = db.Column(db.String(50), nullable=False) # Ex: "Café da Manhã", "Almoço"
    description = db.Column(db.Text, nullable=False) # Ex: "2 ovos, 1 fatia de pão integral"
    calories = db.Column(db.Float, nullable=True)
    protein = db.Column(db.Float, nullable=True)
    carbs = db.Column(db.Float, nullable=True)
    fat = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, nullable=True) # Ordem das refeições no dia

    def to_dict(self):
        return {
            "id": self.id,
            "diet_plan_id": self.diet_plan_id,
            "day_of_week": self.day_of_week,
            "meal_type": self.meal_type,
            "description": self.description,
            "calories": self.calories,
            "protein": self.protein,
            "carbs": self.carbs,
            "fat": self.fat,
            "notes": self.notes,
            "order": self.order
        }
