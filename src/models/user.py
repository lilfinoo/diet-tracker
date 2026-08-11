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
    password_hash = db.Column(db.String(255), nullable=False)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    banned_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_premium = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Relacionamentos
    diet_entries = db.relationship("DietEntry", backref="user", lazy=True, cascade="all, delete-orphan")
    measurements = db.relationship("Measurement", backref="user", lazy=True, cascade="all, delete-orphan")
    profile = db.relationship("UserProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="user", lazy=True, cascade="all, delete-orphan")
    
    # NOVOS RELACIONAMENTOS PARA PLANOS
    workout_plans = db.relationship("WorkoutPlan", backref="user", lazy=True, cascade="all, delete-orphan")
    diet_plans = db.relationship("DietPlan", backref="user", lazy=True, cascade="all, delete-orphan")
    workout_sessions = db.relationship("WorkoutSession", backref="user", lazy=True, cascade="all, delete-orphan")

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

    def to_dict(self, counts=None):
        counts = counts or {}
        def count(name, relation_loader):
            return counts[name] if name in counts else len(relation_loader())

        return {
            "id": self.id,
            "username": self.username,
            "is_banned": self.is_banned,
            "banned_at": self.banned_at.isoformat() if self.banned_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_admin": self.is_admin,
            "is_premium": self.is_premium,
            "diet_entries_count": count("diet_entries", lambda: self.diet_entries),
            "measurements_count": count("measurements", lambda: self.measurements),
            "chat_messages_count": count("chat_messages", lambda: self.chat_messages),
            "has_profile": counts["has_profile"] if "has_profile" in counts else self.profile is not None,
            "workout_plans_count": count("workout_plans", lambda: self.workout_plans),
            "diet_plans_count": count("diet_plans", lambda: self.diet_plans)
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
    __table_args__ = (db.Index("ix_chat_message_user_created_at", "user_id", "created_at"),)
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
    __table_args__ = (db.Index("ix_diet_entry_user_date", "user_id", "date"),)
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
    __table_args__ = (db.Index("ix_measurement_user_date", "user_id", "date"),)
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
    __table_args__ = (db.Index("ix_workout_plan_user_created_at", "user_id", "created_at"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey('user.id'), nullable=False) # <--- Mude para UUIDType
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True) # Descrição geral do plano
    split_type = db.Column(db.String(32), nullable=True)
    days_per_week = db.Column(db.Integer, nullable=True)
    goal = db.Column(db.String(50), nullable=True)
    experience_level = db.Column(db.String(20), nullable=True)
    session_duration = db.Column(db.Integer, nullable=True)
    questionnaire_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    days = db.relationship("WorkoutDay", back_populates="plan", order_by="WorkoutDay.order", cascade="all, delete-orphan")
    exercises = db.relationship("WorkoutExercise", backref="plan", order_by="WorkoutExercise.order", cascade="all, delete-orphan")
    sessions = db.relationship("WorkoutSession", back_populates="plan", cascade="all, delete")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "split_type": self.split_type,
            "days_per_week": self.days_per_week,
            "days_count": len(self.days),
            "goal": self.goal,
            "experience_level": self.experience_level,
            "session_duration": self.session_duration,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "exercises_count": len(self.exercises)
        }

    def to_dict_full(self):
        data = self.to_dict()
        data["exercises"] = [exercise.to_dict() for exercise in self.exercises]
        if self.days:
            data["days"] = [day.to_dict_full() for day in self.days]
        elif self.exercises:
            data["days"] = [{
                "id": None,
                "code": "A",
                "title": "Treino A",
                "focus": "Plano anterior",
                "order": 1,
                "exercises": [exercise.to_dict() for exercise in self.exercises],
            }]
        else:
            data["days"] = []
        return data


class WorkoutDay(db.Model):
    __table_args__ = (
        db.UniqueConstraint("workout_plan_id", "order", name="uq_workout_day_plan_order"),
        db.Index("ix_workout_day_plan_order", "workout_plan_id", "order"),
    )
    id = db.Column(db.Integer, primary_key=True)
    workout_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id", ondelete="CASCADE"), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    focus = db.Column(db.String(200), nullable=True)
    order = db.Column(db.Integer, nullable=False)

    plan = db.relationship("WorkoutPlan", back_populates="days")
    exercises = db.relationship("WorkoutExercise", back_populates="day", order_by="WorkoutExercise.order")

    def to_dict(self):
        return {
            "id": self.id,
            "workout_plan_id": self.workout_plan_id,
            "code": self.code,
            "title": self.title,
            "focus": self.focus,
            "order": self.order,
            "exercises_count": len(self.exercises),
        }

    def to_dict_full(self):
        data = self.to_dict()
        data["exercises"] = [exercise.to_dict() for exercise in self.exercises]
        return data


class WorkoutExercise(db.Model):
    __table_args__ = (db.Index("ix_workout_exercise_day_order", "workout_day_id", "order"),)
    id = db.Column(db.Integer, primary_key=True)
    workout_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id"), nullable=False)
    workout_day_id = db.Column(db.Integer, db.ForeignKey("workout_day.id", ondelete="CASCADE"), nullable=True)
    catalog_key = db.Column(db.String(80), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    movement_pattern = db.Column(db.String(50), nullable=True)
    primary_muscle = db.Column(db.String(50), nullable=True)
    equipment = db.Column(db.String(50), nullable=True)
    difficulty = db.Column(db.String(20), nullable=True)
    sets = db.Column(db.Integer, nullable=True)
    reps = db.Column(db.String(50), nullable=True) # Ex: "8-12", "até a falha"
    weight = db.Column(db.String(50), nullable=True) # Ex: "10kg", "peso corporal"
    rest_seconds = db.Column(db.Integer, nullable=True)
    effort_guidance = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, nullable=True) # Ordem dos exercícios no plano

    day = db.relationship("WorkoutDay", back_populates="exercises")

    def to_dict(self):
        return {
            "id": self.id,
            "workout_plan_id": self.workout_plan_id,
            "workout_day_id": self.workout_day_id,
            "catalog_key": self.catalog_key,
            "name": self.name,
            "movement_pattern": self.movement_pattern,
            "primary_muscle": self.primary_muscle,
            "equipment": self.equipment,
            "difficulty": self.difficulty,
            "sets": self.sets,
            "reps": self.reps,
            "weight": self.weight,
            "rest_seconds": self.rest_seconds,
            "effort_guidance": self.effort_guidance,
            "notes": self.notes,
            "order": self.order
        }


class WorkoutSession(db.Model):
    __table_args__ = (
        db.Index(
            "ix_workout_session_user_active",
            "user_id",
            unique=True,
            postgresql_where=db.text("completed_at IS NULL"),
            sqlite_where=db.text("completed_at IS NULL"),
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    workout_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id", ondelete="CASCADE"), nullable=False)
    workout_day_id = db.Column(db.Integer, db.ForeignKey("workout_day.id", ondelete="CASCADE"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    plan = db.relationship("WorkoutPlan", back_populates="sessions")
    day = db.relationship("WorkoutDay")
    overrides = db.relationship("WorkoutSessionExerciseOverride", back_populates="session", cascade="all, delete-orphan")
    completions = db.relationship(
        "WorkoutSessionExerciseCompletion",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="WorkoutSessionExerciseCompletion.completed_at",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "workout_plan_id": self.workout_plan_id,
            "workout_day_id": self.workout_day_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "overrides": [override.to_dict() for override in self.overrides],
            "completed_exercise_ids": [completion.workout_exercise_id for completion in self.completions],
        }


class WorkoutSessionExerciseOverride(db.Model):
    __table_args__ = (
        db.UniqueConstraint("workout_session_id", "workout_exercise_id", name="uq_session_exercise_override"),
    )
    id = db.Column(db.Integer, primary_key=True)
    workout_session_id = db.Column(db.Integer, db.ForeignKey("workout_session.id", ondelete="CASCADE"), nullable=False)
    workout_exercise_id = db.Column(db.Integer, db.ForeignKey("workout_exercise.id", ondelete="CASCADE"), nullable=False)
    catalog_key = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    movement_pattern = db.Column(db.String(50), nullable=True)
    primary_muscle = db.Column(db.String(50), nullable=True)
    equipment = db.Column(db.String(50), nullable=True)
    difficulty = db.Column(db.String(20), nullable=True)
    sets = db.Column(db.Integer, nullable=True)
    reps = db.Column(db.String(50), nullable=True)
    weight = db.Column(db.String(50), nullable=True)
    rest_seconds = db.Column(db.Integer, nullable=True)
    effort_guidance = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    session = db.relationship("WorkoutSession", back_populates="overrides")
    exercise = db.relationship("WorkoutExercise")

    def to_dict(self):
        return {
            "id": self.id,
            "workout_exercise_id": self.workout_exercise_id,
            "catalog_key": self.catalog_key,
            "name": self.name,
            "movement_pattern": self.movement_pattern,
            "primary_muscle": self.primary_muscle,
            "equipment": self.equipment,
            "difficulty": self.difficulty,
            "sets": self.sets,
            "reps": self.reps,
            "weight": self.weight,
            "rest_seconds": self.rest_seconds,
            "effort_guidance": self.effort_guidance,
            "notes": self.notes,
        }


class WorkoutSessionExerciseCompletion(db.Model):
    __table_args__ = (
        db.UniqueConstraint("workout_session_id", "workout_exercise_id", name="uq_session_exercise_completion"),
    )
    id = db.Column(db.Integer, primary_key=True)
    workout_session_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    workout_exercise_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_exercise.id", ondelete="CASCADE"),
        nullable=False,
    )
    completed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    session = db.relationship("WorkoutSession", back_populates="completions")
    exercise = db.relationship("WorkoutExercise")

class DietPlan(db.Model):
    __table_args__ = (db.Index("ix_diet_plan_user_created_at", "user_id", "created_at"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True) # Descrição geral do plano
    schema_version = db.Column(db.Integer, default=1, nullable=False)
    plan_mode = db.Column(db.String(24), nullable=True)
    goal_code = db.Column(db.String(32), nullable=True)
    meals_per_day = db.Column(db.Integer, nullable=True)
    generation_context = db.Column(db.JSON, nullable=True)
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
            "schema_version": self.schema_version,
            "plan_mode": self.plan_mode,
            "goal_code": self.goal_code,
            "meals_per_day": self.meals_per_day,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "meals_count": len(self.meals) # Exemplo
        }

    def to_dict_full(self):
        data = self.to_dict()
        data["meals"] = [meal.to_dict() for meal in self.meals]
        return data

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
    items = db.Column(db.JSON, nullable=True)
    prep_instructions = db.Column(db.Text, nullable=True)
    prep_minutes = db.Column(db.Integer, nullable=True)
    substitutions = db.Column(db.JSON, nullable=True)
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
            "items": self.items or [],
            "prep_instructions": self.prep_instructions,
            "prep_minutes": self.prep_minutes,
            "substitutions": self.substitutions or [],
            "order": self.order
        }
