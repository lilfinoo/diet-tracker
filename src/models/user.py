from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
from sqlalchemy_utils import UUIDType
# Importa para hashing de senhas
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __table_args__ = (
        db.CheckConstraint(
            "professional_scope IS NULL OR professional_scope IN ('diet', 'workout', 'both')",
            name="ck_user_professional_scope",
        ),
        db.CheckConstraint("ai_trial_uses >= 0", name="ck_user_ai_trial_uses_nonnegative"),
    )

    id = db.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    banned_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_premium = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_professional = db.Column(db.Boolean, default=False, nullable=False)
    ai_trial_uses = db.Column(db.Integer, default=0, nullable=False)
    professional_scope = db.Column(db.String(16), nullable=True)

    # Relacionamentos
    diet_entries = db.relationship("DietEntry", backref="user", lazy=True, cascade="all, delete-orphan")
    measurements = db.relationship("Measurement", backref="user", lazy=True, cascade="all, delete-orphan")
    profile = db.relationship("UserProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="user", lazy=True, cascade="all, delete-orphan")
    
    # Relacionamentos de planos
    workout_plans = db.relationship(
        "WorkoutPlan",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
        foreign_keys="WorkoutPlan.user_id",
    )
    diet_plans = db.relationship(
        "DietPlan",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
        foreign_keys="DietPlan.user_id",
    )
    workout_sessions = db.relationship("WorkoutSession", backref="user", lazy=True, cascade="all, delete-orphan")
    oauth_identities = db.relationship("OAuthIdentity", backref="user", lazy=True, cascade="all, delete-orphan")
    subscriptions = db.relationship("Subscription", backref="user", lazy=True, cascade="all, delete-orphan")
    professional_applications = db.relationship(
        "ProfessionalApplication",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
        foreign_keys="ProfessionalApplication.user_id",
    )
    badges = db.relationship(
        "UserBadge",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="UserBadge.granted_at",
    )
    profile_highlights = db.relationship(
        "ProfileHighlight",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="ProfileHighlight.position",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return bool(self.password_hash and password and check_password_hash(self.password_hash, password))

    def active_subscription(self):
        now = datetime.utcnow()
        return next((
            subscription for subscription in sorted(
                self.subscriptions,
                key=lambda item: item.created_at or datetime.min,
                reverse=True,
            )
            if subscription.status in {"active", "trialing", "canceled"}
            and (subscription.current_period_end is None or subscription.current_period_end > now)
        ), None)

    def effective_plan_code(self):
        subscription = self.active_subscription()
        if subscription:
            return subscription.plan_code
        return "premium_student" if self.is_premium else "free"

    def has_entitlement(self, entitlement):
        plan_code = self.effective_plan_code()
        if entitlement == "premium":
            return self.is_premium or plan_code != "free"
        if entitlement == "professional":
            return self.is_professional and plan_code in {"professional_single", "professional_complete"}
        if entitlement in {"diet", "workout"}:
            return self.has_entitlement("professional") and self.professional_scope in {entitlement, "both"}
        return False

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
            "is_premium": self.has_entitlement("premium"),
            "is_professional": self.is_professional,
            "plan_code": self.effective_plan_code(),
            "professional_scope": self.professional_scope,
            "ai_trial_uses": self.ai_trial_uses,
            "diet_entries_count": count("diet_entries", lambda: self.diet_entries),
            "measurements_count": count("measurements", lambda: self.measurements),
            "chat_messages_count": count("chat_messages", lambda: self.chat_messages),
            "has_profile": counts["has_profile"] if "has_profile" in counts else self.profile is not None,
            "workout_plans_count": count("workout_plans", lambda: self.workout_plans),
            "diet_plans_count": count("diet_plans", lambda: self.diet_plans),
            "badges": [badge.to_dict() for badge in self.badges],
            "profile_highlights": [highlight.to_dict() for highlight in self.profile_highlights],
        }


class OAuthIdentity(db.Model):
    __table_args__ = (
        db.UniqueConstraint("provider", "issuer", "subject", name="uq_oauth_identity_provider_issuer_subject"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    provider = db.Column(db.String(32), nullable=False)
    issuer = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(320), nullable=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    display_name = db.Column(db.String(255), nullable=True)
    avatar_url = db.Column(db.String(2048), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)


class Subscription(db.Model):
    __table_args__ = (
        db.UniqueConstraint("provider", "external_subscription_id", name="uq_subscription_provider_external_id"),
        db.CheckConstraint(
            "plan_code IN ('free', 'premium_student', 'professional_single', 'professional_complete')",
            name="ck_subscription_plan_code",
        ),
        db.Index("ix_subscription_user_status", "user_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    provider = db.Column(db.String(32), nullable=False)
    external_customer_id = db.Column(db.String(255), nullable=True)
    external_subscription_id = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), nullable=False)
    plan_code = db.Column(db.String(32), nullable=False)
    current_period_start = db.Column(db.DateTime, nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "external_customer_id": self.external_customer_id,
            "external_subscription_id": self.external_subscription_id,
            "status": self.status,
            "plan_code": self.plan_code,
            "current_period_start": self.current_period_start.isoformat() if self.current_period_start else None,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BillingCheckout(db.Model):
    __table_args__ = (
        db.UniqueConstraint("provider", "external_checkout_id", name="uq_billing_checkout_provider_external_id"),
        db.Index("ix_billing_checkout_user", "user_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    provider = db.Column(db.String(32), nullable=False)
    external_checkout_id = db.Column(db.String(255), nullable=True)
    plan_code = db.Column(db.String(32), nullable=False)
    payment_method = db.Column(db.String(16), nullable=False)  # credit_card | pix
    status = db.Column(db.String(32), default="created", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class BillingEvent(db.Model):
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_event_id", name="uq_billing_event_provider_event_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(32), nullable=False)
    provider_event_id = db.Column(db.String(255), nullable=False)
    event_type = db.Column(db.String(64), nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class ProfessionalApplication(db.Model):
    __table_args__ = (
        db.CheckConstraint(
            "profession IN ('personal_trainer', 'nutritionist')",
            name="ck_professional_application_profession",
        ),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_professional_application_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    plan_code = db.Column(db.String(32), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    profession = db.Column(db.String(20), nullable=False)
    registration_number = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(16), default="pending", nullable=False)
    admin_note = db.Column(db.String(500), nullable=True)
    reviewed_by_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        reviewer = db.session.get(User, self.reviewed_by_user_id) if self.reviewed_by_user_id else None
        return {
            "id": self.id,
            "user_id": str(self.user_id),
            "username": self.user.username if self.user else None,
            "plan_code": self.plan_code,
            "full_name": self.full_name,
            "profession": self.profession,
            "registration_number": self.registration_number,
            "status": self.status,
            "admin_note": self.admin_note,
            "reviewed_by": reviewer.username if reviewer else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False, unique=True) # Perfil único por usuário
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(10), nullable=True)  # masculino, feminino
    goal = db.Column(db.String(100), nullable=True)  # perder peso, ganhar massa, manter
    activity_level = db.Column(db.String(50), nullable=True)  # sedentario, leve, moderado, intenso
    dietary_restrictions = db.Column(db.Text, nullable=True)
    weight = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    timezone = db.Column(db.String(64), nullable=True)
    current_workout_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id"), nullable=True)
    current_workout_schedule = db.Column(db.JSON, nullable=True)
    pending_workout_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id"), nullable=True)
    pending_workout_schedule = db.Column(db.JSON, nullable=True)
    workout_schedule_effective_from = db.Column(db.Date, nullable=True)
    workout_schedule_timezone = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    current_workout_plan = db.relationship("WorkoutPlan", foreign_keys=[current_workout_plan_id])
    pending_workout_plan = db.relationship("WorkoutPlan", foreign_keys=[pending_workout_plan_id])

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
            "timezone": self.timezone,
            "current_workout_plan_id": self.current_workout_plan_id,
            "pending_workout_plan_id": self.pending_workout_plan_id,
            "workout_schedule_effective_from": self.workout_schedule_effective_from.isoformat() if self.workout_schedule_effective_from else None,
            "workout_schedule_timezone": self.workout_schedule_timezone,
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
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey('user.id'), nullable=False)
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

# --- Modelos de planos de treino e dieta ---

class WorkoutPlan(db.Model):
    __table_args__ = (
        db.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_workout_plan_status"),
        db.CheckConstraint("source IN ('manual', 'ai', 'legacy')", name="ck_workout_plan_source"),
        db.Index("ix_workout_plan_user_created_at", "user_id", "created_at"),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey('user.id'), nullable=False)
    author_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    published_by_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=True)
    supersedes_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id"), nullable=True)
    status = db.Column(db.String(20), default="published", nullable=False)
    source = db.Column(db.String(20), default="manual", nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
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
    author = db.relationship("User", foreign_keys=[author_user_id])
    published_by = db.relationship("User", foreign_keys=[published_by_user_id])

    def __init__(self, **kwargs):
        kwargs.setdefault("author_user_id", kwargs.get("user_id"))
        if kwargs.get("status", "published") == "published":
            kwargs.setdefault("published_at", datetime.utcnow())
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "author_user_id": self.author_user_id,
            "author_username": self.author.username if self.author else None,
            "status": self.status,
            "source": self.source,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "supersedes_plan_id": self.supersedes_plan_id,
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
        data["questionnaire"] = self.questionnaire_data or {}
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
        db.Index("ix_workout_session_user_completed", "user_id", "completed_at", "id"),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    workout_plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id", ondelete="CASCADE"), nullable=False)
    workout_day_id = db.Column(db.Integer, db.ForeignKey("workout_day.id", ondelete="CASCADE"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_timezone = db.Column(db.String(64), nullable=True)
    completed_local_date = db.Column(db.Date, nullable=True)
    completed_week_start = db.Column(db.Date, nullable=True)
    pr_processed_version = db.Column(db.Integer, nullable=True)

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
            "completed_timezone": self.completed_timezone,
            "completed_local_date": self.completed_local_date.isoformat() if self.completed_local_date else None,
            "completed_week_start": self.completed_week_start.isoformat() if self.completed_week_start else None,
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
    exercise_name = db.Column(db.String(100), nullable=True)
    exercise_catalog_key = db.Column(db.String(80), nullable=True)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    session = db.relationship("WorkoutSession", back_populates="completions")
    exercise = db.relationship("WorkoutExercise")
    performed_sets = db.relationship(
        "WorkoutSetPerformance",
        back_populates="completion",
        cascade="all, delete-orphan",
        order_by="WorkoutSetPerformance.set_order",
    )


class WorkoutSetPerformance(db.Model):
    __table_args__ = (
        db.UniqueConstraint("completion_id", "set_order", name="uq_workout_set_completion_order"),
        db.CheckConstraint("set_order > 0", name="ck_workout_set_order_positive"),
        db.CheckConstraint("repetitions > 0", name="ck_workout_set_repetitions_positive"),
        db.CheckConstraint("load_kg IS NULL OR load_kg >= 0", name="ck_workout_set_load_nonnegative"),
    )
    id = db.Column(db.Integer, primary_key=True)
    completion_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_session_exercise_completion.id", ondelete="CASCADE"),
        nullable=False,
    )
    set_order = db.Column(db.Integer, nullable=False)
    repetitions = db.Column(db.Integer, nullable=False)
    load_kg = db.Column(db.Numeric(10, 2), nullable=True)
    is_warmup = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    completion = db.relationship("WorkoutSessionExerciseCompletion", back_populates="performed_sets")


class PersonalRecordEvent(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            "workout_session_id",
            "exercise_key",
            "metric_key",
            name="uq_pr_event_session_exercise_metric",
        ),
        db.Index("ix_pr_event_user_exercise_date", "user_id", "exercise_key", "achieved_at"),
        db.Index("ix_pr_event_session", "workout_session_id"),
        db.CheckConstraint(
            "metric_type IN ('max_load', 'estimated_1rm', 'reps_at_load')",
            name="ck_pr_event_metric_type",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    exercise_key = db.Column(db.String(80), nullable=False)
    exercise_name = db.Column(db.String(100), nullable=False)
    workout_session_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    completion_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_session_exercise_completion.id", ondelete="CASCADE"),
        nullable=False,
    )
    set_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_set_performance.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_type = db.Column(db.String(24), nullable=False)
    metric_key = db.Column(db.String(80), nullable=False)
    previous_value = db.Column(db.Numeric(14, 4), nullable=True)
    new_value = db.Column(db.Numeric(14, 4), nullable=False)
    previous_load_kg = db.Column(db.Numeric(10, 2), nullable=True)
    previous_repetitions = db.Column(db.Integer, nullable=True)
    load_kg = db.Column(db.Numeric(10, 2), nullable=False)
    repetitions = db.Column(db.Integer, nullable=False)
    formula = db.Column(db.String(20), nullable=True)
    formula_version = db.Column(db.Integer, nullable=True)
    is_initial = db.Column(db.Boolean, default=False, nullable=False)
    is_highlighted = db.Column(db.Boolean, default=False, nullable=False)
    is_backfilled = db.Column(db.Boolean, default=False, nullable=False)
    achieved_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    session = db.relationship("WorkoutSession")
    completion = db.relationship("WorkoutSessionExerciseCompletion")
    performed_set = db.relationship("WorkoutSetPerformance")


class WorkoutWeeklyGoal(db.Model):
    __table_args__ = (
        db.UniqueConstraint("user_id", "effective_week_start", name="uq_weekly_goal_user_week"),
        db.CheckConstraint("target_sessions BETWEEN 1 AND 14", name="ck_weekly_goal_target"),
        db.Index("ix_weekly_goal_user_effective", "user_id", "effective_week_start"),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    target_sessions = db.Column(db.Integer, nullable=False)
    effective_week_start = db.Column(db.Date, nullable=False)
    timezone = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class ExerciseGoal(db.Model):
    __table_args__ = (
        db.CheckConstraint("status IN ('active', 'achieved', 'cancelled')", name="ck_exercise_goal_status"),
        db.CheckConstraint("target_load_kg > 0", name="ck_exercise_goal_target_positive"),
        db.Index(
            "uq_exercise_goal_user_active",
            "user_id",
            unique=True,
            postgresql_where=db.text("status = 'active'"),
            sqlite_where=db.text("status = 'active'"),
        ),
    )
    id = db.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    exercise_key = db.Column(db.String(80), nullable=False)
    exercise_name = db.Column(db.String(100), nullable=False)
    target_load_kg = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    achieved_at = db.Column(db.DateTime, nullable=True)
    achieved_session_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_session.id", ondelete="SET NULL"),
        nullable=True,
    )


class AchievementUnlock(db.Model):
    __table_args__ = (
        db.UniqueConstraint("user_id", "achievement_code", name="uq_achievement_unlock_user_code"),
        db.Index("ix_achievement_unlock_user_date", "user_id", "unlocked_at"),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    achievement_code = db.Column(db.String(40), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    workout_session_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_session.id", ondelete="SET NULL"),
        nullable=True,
    )
    exercise_goal_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("exercise_goal.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_backfilled = db.Column(db.Boolean, default=False, nullable=False)


class UserBadge(db.Model):
    __table_args__ = (
        db.UniqueConstraint("user_id", "badge_code", name="uq_user_badge_user_code"),
        db.CheckConstraint(
            "badge_code IN ('pioneiro', 'desde_sempre')",
            name="ck_user_badge_code",
        ),
        db.CheckConstraint(
            "(badge_code = 'pioneiro' AND badge_rank BETWEEN 1 AND 100) OR (badge_code = 'desde_sempre' AND badge_rank IS NULL)",
            name="ck_user_badge_rank_rules",
        ),
        db.CheckConstraint("source IN ('signup', 'backfill', 'admin')", name="ck_user_badge_source"),
        db.Index(
            "uq_user_badge_pioneer_rank",
            "badge_rank",
            unique=True,
            postgresql_where=db.text("badge_code = 'pioneiro'"),
            sqlite_where=db.text("badge_code = 'pioneiro'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    badge_code = db.Column(db.String(40), nullable=False)
    badge_rank = db.Column(db.Integer, nullable=True)
    source = db.Column(db.String(16), default="backfill", nullable=False)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="badges")

    def to_dict(self):
        from src.services.badges import serialize_badge

        return serialize_badge(self)


class ProfileHighlight(db.Model):
    __table_args__ = (
        db.UniqueConstraint("user_id", "position", name="uq_profile_highlight_user_position"),
        db.UniqueConstraint("user_id", "achievement_unlock_id", name="uq_profile_highlight_user_achievement"),
        db.UniqueConstraint("user_id", "user_badge_id", name="uq_profile_highlight_user_badge"),
        db.CheckConstraint("position BETWEEN 1 AND 3", name="ck_profile_highlight_position"),
        db.CheckConstraint(
            "achievement_unlock_id IS NOT NULL OR user_badge_id IS NOT NULL",
            name="ck_profile_highlight_target_present",
        ),
        db.CheckConstraint("target_kind IN ('achievement', 'badge')", name="ck_profile_highlight_target_kind"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    target_kind = db.Column(db.String(16), nullable=False)
    achievement_unlock_id = db.Column(db.Integer, db.ForeignKey("achievement_unlock.id", ondelete="CASCADE"), nullable=True)
    user_badge_id = db.Column(db.Integer, db.ForeignKey("user_badge.id", ondelete="CASCADE"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="profile_highlights")
    achievement_unlock = db.relationship("AchievementUnlock")
    user_badge = db.relationship("UserBadge")

    def to_dict(self):
        from src.services.badges import serialize_profile_highlight

        return serialize_profile_highlight(self)


class ExerciseMediaReview(db.Model):
    catalog_key = db.Column(db.String(80), primary_key=True)
    provider_id = db.Column(db.String(32), nullable=False)
    provider_name = db.Column(db.String(200), nullable=False)
    provider_equipment = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="approved")
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class DietPlan(db.Model):
    __table_args__ = (
        db.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_diet_plan_status"),
        db.CheckConstraint("source IN ('manual', 'ai', 'legacy')", name="ck_diet_plan_source"),
        db.Index("ix_diet_plan_user_created_at", "user_id", "created_at"),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    author_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    published_by_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=True)
    supersedes_plan_id = db.Column(db.Integer, db.ForeignKey("diet_plan.id"), nullable=True)
    status = db.Column(db.String(20), default="published", nullable=False)
    source = db.Column(db.String(20), default="manual", nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
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
    author = db.relationship("User", foreign_keys=[author_user_id])
    published_by = db.relationship("User", foreign_keys=[published_by_user_id])

    def __init__(self, **kwargs):
        kwargs.setdefault("author_user_id", kwargs.get("user_id"))
        if kwargs.get("status", "published") == "published":
            kwargs.setdefault("published_at", datetime.utcnow())
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "author_user_id": self.author_user_id,
            "author_username": self.author.username if self.author else None,
            "status": self.status,
            "source": self.source,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "supersedes_plan_id": self.supersedes_plan_id,
            "title": self.title,
            "description": self.description,
            "schema_version": self.schema_version,
            "plan_mode": self.plan_mode,
            "goal_code": self.goal_code,
            "meals_per_day": self.meals_per_day,
            "nutrition_targets": (self.generation_context or {}).get("nutrition_targets"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "meals_count": len(self.meals)
        }

    def to_dict_full(self):
        data = self.to_dict()
        data["questionnaire"] = (self.generation_context or {}).get("questionnaire")
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


class ProfessionalStudentRelationship(db.Model):
    __table_args__ = (
        db.CheckConstraint(
            "student_user_id IS NULL OR professional_user_id != student_user_id",
            name="ck_professional_student_distinct_users",
        ),
        db.CheckConstraint(
            "status IN ('pending', 'active', 'declined', 'revoked', 'expired')",
            name="ck_professional_student_status",
        ),
        db.Index("ix_professional_student_professional_status", "professional_user_id", "status"),
        db.Index(
            "uq_professional_student_active_student",
            "student_user_id",
            unique=True,
            postgresql_where=db.text("status = 'active'"),
            sqlite_where=db.text("status = 'active'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    professional_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    student_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=True)
    status = db.Column(db.String(20), default="pending", nullable=False)
    invite_token_hash = db.Column(db.String(64), unique=True, nullable=False)
    invite_expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=True)

    professional = db.relationship("User", foreign_keys=[professional_user_id])
    student = db.relationship("User", foreign_keys=[student_user_id])
    revoked_by = db.relationship("User", foreign_keys=[revoked_by_user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "professional": {
                "id": self.professional.id,
                "username": self.professional.username,
            },
            "student": {
                "id": self.student.id,
                "username": self.student.username,
            } if self.student else None,
            "status": self.status,
            "invite_expires_at": self.invite_expires_at.isoformat(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }


class DelegatedActionAudit(db.Model):
    __table_args__ = (
        db.Index("ix_delegated_audit_actor_created", "actor_user_id", "created_at"),
        db.Index("ix_delegated_audit_subject_created", "subject_user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    subject_user_id = db.Column(UUIDType(binary=False), db.ForeignKey("user.id"), nullable=False)
    relationship_id = db.Column(
        db.Integer,
        db.ForeignKey("professional_student_relationship.id"),
        nullable=True,
    )
    action = db.Column(db.String(80), nullable=False)
    resource_type = db.Column(db.String(40), nullable=True)
    resource_id = db.Column(db.String(64), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    actor = db.relationship("User", foreign_keys=[actor_user_id])
    subject = db.relationship("User", foreign_keys=[subject_user_id])
    relationship = db.relationship("ProfessionalStudentRelationship")
