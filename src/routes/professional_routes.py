import hashlib
import secrets
from uuid import UUID
from datetime import datetime, timedelta
from functools import wraps
from types import SimpleNamespace

from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.models.user import (
    DietEntry,
    DietAdherenceDay,
    DietPlan,
    DietPlanMeal,
    Measurement,
    ProfessionalStudentRelationship,
    ProfessionalReviewRequest,
    User,
    UserProfile,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
    db,
)
from src.routes.common import ai_consent_error, ai_consent_required, json_body, login_required
from src.legal import PROFESSIONAL_SHARING_VERSION
from src.services.ai import (
    AIQuotaExceededError,
    generate_diet_day,
    AIResponseError,
    AIServiceError,
    generate_workout_plan,
    generate_diet_plan,
    classify_exercise_catalog_key,
)
from src.services.plan_management import (
    add_audit,
    create_workout_plan,
    create_diet_plan,
    publish_plan,
    replace_diet_day,
    update_diet_draft,
    update_workout_draft,
)
from src.services.diet_plans import (normalize_manual_diet, normalize_diet_day, correction_feedback, validate_diet_questionnaire, merge_profile_restrictions,
    calculate_nutrition_targets, normalize_diet_output, profile_snapshot)
from src.services.ai_queue import enqueue_ai_request
from src.services.rate_limit import rate_limit
from src.services.workout_plans import (
    PlanValidationError,
    build_workout_contract,
    selection_exercise_catalog,
    invalid_workout_day_numbers,
    merge_workout_day_repairs,
    normalize_manual_workout,
    normalize_workout_output,
    validate_workout_exercise_selection,
    validate_workout_questionnaire,
)


professional_bp = Blueprint("professional", __name__)


@professional_bp.route("/professional/exercises/match", methods=["POST"])
@rate_limit("professional_ai", 8, 60)
@ai_consent_required
def match_professional_exercise():
    if not g.user.has_entitlement("professional"):
        return jsonify({"error": "A área profissional exige acesso profissional aprovado e ativo."}), 403
    name = str(json_body().get("name") or "").strip()
    if not 2 <= len(name) <= 100:
        return jsonify({"error": "Informe o nome do exercício (2 a 100 caracteres)."}), 400
    try:
        key = classify_exercise_catalog_key(name)
    except AIQuotaExceededError as error:
        return jsonify({"error": str(error)}), 429
    except AIServiceError:
        current_app.logger.exception("Professional exercise matching failed")
        return jsonify({"error": "Não foi possível identificar o exercício agora."}), 503
    return jsonify({"catalog_key": key}), 200


@professional_bp.errorhandler(400)
@professional_bp.errorhandler(403)
@professional_bp.errorhandler(404)
@professional_bp.errorhandler(409)
@professional_bp.errorhandler(413)
def professional_http_error(error):
    return jsonify({"error": getattr(error, "description", "Requisição inválida")}), error.code


@professional_bp.errorhandler(500)
def professional_internal_error(error):
    current_app.logger.exception("Unhandled professional workspace error")
    return jsonify({"error": "Erro interno do servidor"}), 500


def professional_required(function):
    @wraps(function)
    @login_required
    def decorated_function(*args, **kwargs):
        if not g.user.has_entitlement("professional"):
            return jsonify({"error": "A área profissional exige acesso profissional aprovado e ativo.", "code": "professional_entitlement_required"}), 403
        return function(*args, **kwargs)

    return decorated_function


def professional_scope_required(scope):
    def decorator(function):
        @wraps(function)
        @professional_required
        def decorated_function(*args, **kwargs):
            if not g.user.has_entitlement(scope):
                return jsonify({"error": "Seu plano profissional não inclui este recurso."}), 403
            return function(*args, **kwargs)

        return decorated_function
    return decorator


def _occupied_student_slots(professional_id):
    now = datetime.utcnow()
    relationships = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == professional_id,
        ProfessionalStudentRelationship.status.in_(("offline", "active", "pending")),
    ).all()
    return sum(
        relationship.status in {"offline", "active"}
        or bool(relationship.student_name)
        or ((not relationship.student_user_id or relationship.initiated_by_user_id != relationship.student_user_id)
            and relationship.invite_expires_at and relationship.invite_expires_at > now)
        for relationship in relationships
    )


def _token_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _relationship_for(professional_id, student_id, lock=False):
    query = ProfessionalStudentRelationship.query.filter_by(
        professional_user_id=professional_id,
        student_user_id=student_id,
        status="active",
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _student_context(student_id, lock=False):
    if str(student_id).startswith("offline-"):
        try:
            relationship_id = int(str(student_id).split("-", 1)[1])
        except ValueError:
            abort(404, description="Aluno não encontrado.")
        relationship = ProfessionalStudentRelationship.query.filter(
            ProfessionalStudentRelationship.id == relationship_id,
            ProfessionalStudentRelationship.professional_user_id == g.user.id,
            ProfessionalStudentRelationship.status.in_(("offline", "pending")),
            ProfessionalStudentRelationship.student_name.isnot(None),
        )
        if lock:
            relationship = relationship.with_for_update()
        relationship = relationship.first()
        if not relationship:
            abort(404, description="Aluno não encontrado.")
        if relationship.status == "pending" and relationship.invite_expires_at <= datetime.utcnow():
            relationship.status = "offline"
            relationship.invite_token_hash = None
            db.session.commit()
        return _offline_student(relationship), relationship

    try:
        student_id = UUID(str(student_id))
    except ValueError:
        abort(404, description="Aluno não encontrado.")
    relationship = _relationship_for(g.user.id, student_id, lock=lock)
    if not relationship:
        abort(404, description="Aluno não encontrado.")
    if (
        not relationship.data_sharing_consented_at
        or relationship.data_sharing_consent_version != PROFESSIONAL_SHARING_VERSION
    ):
        abort(403, description="O consentimento de compartilhamento do aluno precisa ser renovado.")
    student = db.session.get(User, student_id)
    if not student or student.is_banned:
        abort(404, description="Aluno não encontrado.")
    return student, relationship


def _workout_plan_for(student, plan_id, editable=False):
    owner_filter = (
        {"professional_student_relationship_id": student.relationship_id}
        if getattr(student, "is_offline", False) else {"user_id": student.id}
    )
    plan = WorkoutPlan.query.filter_by(id=plan_id, **owner_filter).options(
        selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises),
        selectinload(WorkoutPlan.exercises),
    ).first()
    if not plan or plan.author_user_id != g.user.id:
        abort(404, description="Plano não encontrado.")
    if ProfessionalReviewRequest.query.filter_by(proposal_workout_plan_id=plan.id).first():
        abort(404, description="Plano não encontrado.")
    if editable and (plan.status != "draft" or plan.author_user_id != g.user.id):
        abort(409, description="Somente rascunhos próprios podem ser editados.")
    return plan




def _superseded_plan_id(student, data, model):
    plan_id = data.get("supersedes_plan_id")
    if plan_id is None:
        return None
    if not isinstance(plan_id, int) or isinstance(plan_id, bool):
        abort(400, description="Plano anterior inválido.")
    previous = (_workout_plan_for(student, plan_id) if model is WorkoutPlan
                else _diet_plan_for(student, plan_id))
    if previous.status != "published":
        abort(409, description="Somente planos enviados podem receber uma atualização.")
    return previous.id


def _commit_or_conflict(message):
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": message}), 409
    return None


@professional_bp.route("/professional/invitations", methods=["POST"])
@professional_required
def create_invitation():
    db.session.get(User, g.user.id, with_for_update=True)
    if _occupied_student_slots(g.user.id) >= 5:
        return jsonify({"error": "Seu plano permite acompanhar até 5 alunos."}), 409
    token = secrets.token_urlsafe(32)
    relationship = ProfessionalStudentRelationship(
        professional_user_id=g.user.id,
        status="pending",
        invite_token_hash=_token_hash(token),
        invite_expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.session.add(relationship)
    db.session.commit()
    return jsonify({
        "invitation": relationship.to_dict(),
        "token": token,
        "invite_path": f"/?invite={token}",
    }), 201


@professional_bp.route("/professional/invitations", methods=["GET"])
@professional_required
def list_invitations():
    relationships = ProfessionalStudentRelationship.query.filter_by(
        professional_user_id=g.user.id,
        status="pending",
    ).order_by(ProfessionalStudentRelationship.created_at.desc()).all()
    now = datetime.utcnow()
    changed = False
    for relationship in relationships:
        if relationship.invite_expires_at <= now:
            relationship.status = "offline" if relationship.student_name else "expired"
            relationship.invite_token_hash = None
            changed = True
    if changed:
        db.session.commit()
    return jsonify([item.to_dict() for item in relationships if item.status == "pending"]), 200


@professional_bp.route("/professional/invitations/<int:relationship_id>", methods=["DELETE"])
@professional_required
def cancel_invitation(relationship_id):
    relationship = ProfessionalStudentRelationship.query.filter_by(
        id=relationship_id,
        professional_user_id=g.user.id,
        status="pending",
    ).first_or_404()
    relationship.status = "offline" if relationship.student_name else "revoked"
    relationship.invite_token_hash = None
    relationship.revoked_at = datetime.utcnow()
    relationship.revoked_by_user_id = g.user.id
    db.session.commit()
    return jsonify({"message": "Convite cancelado."}), 200


@professional_bp.route("/professional/students/<string:student_id>/invitation", methods=["POST"])
@professional_required
def invite_roster_student(student_id):
    if not str(student_id).startswith("offline-"):
        return jsonify({"error": "Cadastro independente não encontrado."}), 404
    try:
        relationship_id = int(str(student_id).split("-", 1)[1])
    except ValueError:
        return jsonify({"error": "Cadastro independente não encontrado."}), 404
    relationship = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.id == relationship_id,
        ProfessionalStudentRelationship.professional_user_id == g.user.id,
        ProfessionalStudentRelationship.status.in_(("offline", "pending")),
        ProfessionalStudentRelationship.student_name.isnot(None),
    ).with_for_update().first_or_404()
    token = secrets.token_urlsafe(32)
    relationship.status = "pending"
    relationship.invite_token_hash = _token_hash(token)
    relationship.invite_expires_at = datetime.utcnow() + timedelta(days=7)
    db.session.commit()
    return jsonify({
        "invitation": relationship.to_dict(),
        "token": token,
        "invite_path": f"/?invite={token}",
    }), 201


@professional_bp.route("/invitations/<token>", methods=["GET"])
@login_required
def invitation_details(token):
    relationship = ProfessionalStudentRelationship.query.filter_by(
        invite_token_hash=_token_hash(token),
        status="pending",
    ).first()
    if (
        not relationship
        or relationship.invite_expires_at <= datetime.utcnow()
        or not relationship.professional
        or not relationship.professional.has_entitlement("professional")
        or relationship.professional.is_banned
    ):
        return jsonify({"error": "Convite inválido ou expirado."}), 404
    if relationship.professional_user_id == g.user.id:
        return jsonify({"error": "O profissional não pode aceitar o próprio convite."}), 409
    return jsonify({
        "invitation": relationship.to_dict(),
        "data_sharing_consent_version": PROFESSIONAL_SHARING_VERSION,
    }), 200


@professional_bp.route("/invitations/<token>/accept", methods=["POST"])
@login_required
def accept_invitation(token):
    data = json_body()
    if data.get("data_sharing_consent") is not True or data.get("data_sharing_consent_version") != PROFESSIONAL_SHARING_VERSION:
        return jsonify({
            "error": "Confirme o compartilhamento de dados com o profissional.",
            "code": "data_sharing_consent_required",
        }), 400
    relationship = ProfessionalStudentRelationship.query.filter_by(
        invite_token_hash=_token_hash(token),
    ).with_for_update().first()
    if (
        not relationship
        or relationship.status != "pending"
        or relationship.invite_expires_at <= datetime.utcnow()
        or not relationship.professional
        or not relationship.professional.has_entitlement("professional")
        or relationship.professional.is_banned
    ):
        return jsonify({"error": "Convite inválido ou expirado."}), 404
    if relationship.professional_user_id == g.user.id:
        return jsonify({"error": "O profissional não pode aceitar o próprio convite."}), 409
    db.session.get(User, g.user.id, with_for_update=True)
    if _active_professional_count(g.user.id) >= 2:
        return jsonify({"error": "Você já possui dois profissionais ativos."}), 409
    if _relationship_for(relationship.professional_user_id, g.user.id):
        return jsonify({"error": "Você já está vinculado a este profissional."}), 409
    db.session.get(User, relationship.professional_user_id, with_for_update=True)
    active_students = ProfessionalStudentRelationship.query.filter_by(
        professional_user_id=relationship.professional_user_id,
        status="active",
    ).count()
    if active_students >= 5:
        return jsonify({"error": "Este profissional já atingiu o limite de 5 alunos."}), 409
    relationship.student_user_id = g.user.id
    if relationship.student_name:
        profile_values = relationship.student_profile or {}
        profile = g.user.profile
        if not profile:
            profile = UserProfile(user_id=g.user.id)
            db.session.add(profile)
        if profile.age is None and profile_values.get("birth_year"):
            profile.age = datetime.utcnow().year - int(profile_values["birth_year"])
        for field in ("gender", "goal", "activity_level", "weight", "height", "dietary_restrictions"):
            value = profile_values.get(field)
            if getattr(profile, field) in (None, "") and value not in (None, ""):
                setattr(profile, field, value)
        WorkoutPlan.query.filter_by(professional_student_relationship_id=relationship.id).update({
            "user_id": g.user.id,
            "professional_student_relationship_id": None,
        }, synchronize_session=False)
    DietPlan.query.filter_by(professional_student_relationship_id=relationship.id).update({
        "user_id": g.user.id, "professional_student_relationship_id": None,
    }, synchronize_session=False)
    relationship.status = "active"
    relationship.accepted_at = datetime.utcnow()
    relationship.data_sharing_consented_at = relationship.accepted_at
    relationship.data_sharing_consent_version = PROFESSIONAL_SHARING_VERSION
    add_audit(
        relationship.professional,
        g.user,
        relationship,
        "professional_student.accepted",
        "professional_student_relationship",
        relationship.id,
    )
    conflict = _commit_or_conflict("Você já está vinculado a este profissional.")
    if conflict:
        return conflict
    return jsonify({"message": "Vínculo profissional aceito.", "relationship": relationship.to_dict()}), 200


@professional_bp.route("/professional/students", methods=["GET"])
@professional_required
def list_students():
    relationships = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == g.user.id,
        ProfessionalStudentRelationship.status == "active",
        ProfessionalStudentRelationship.data_sharing_consent_version == PROFESSIONAL_SHARING_VERSION,
        ProfessionalStudentRelationship.data_sharing_consented_at.isnot(None),
    ).all()
    roster = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == g.user.id,
        ProfessionalStudentRelationship.status.in_(("offline", "pending")),
        ProfessionalStudentRelationship.student_name.isnot(None),
    ).all()
    items = [_student_summary(item.student, item) for item in relationships
             if item.student and not item.student.is_banned]
    items.extend(_offline_student_summary(item) for item in roster)
    return jsonify({
        "items": items,
        "limit": len(items),
        "offset": 0,
    }), 200


def _student_profile_payload(data):
    raw = data.get("profile") if isinstance(data.get("profile"), dict) else data
    try:
        age = int(raw.get("age"))
        weight = float(raw["weight"]) if raw.get("weight") not in (None, "") else None
        height = float(raw["height"]) if raw.get("height") not in (None, "") else None
    except (TypeError, ValueError, KeyError):
        abort(400, description="Informe idade, peso e altura válidos.")
    if not 0 <= age <= 120 or weight is None or not 0 < weight <= 500 or height is None or not 0 < height <= 300:
        abort(400, description="Confira idade, peso e altura do aluno.")
    gender = str(raw.get("gender") or "").strip()
    if gender and gender not in UserProfile.VALID_GENDERS:
        abort(400, description="Gênero inválido.")
    activity = str(raw.get("activity_level") or "").strip()
    if activity and activity not in UserProfile.VALID_ACTIVITY_LEVELS:
        abort(400, description="Nível de atividade inválido.")
    goal = str(raw.get("goal") or "").strip()
    restrictions = str(raw.get("dietary_restrictions") or "").strip()
    if len(goal) > 100 or len(restrictions) > 2000:
        abort(400, description="Objetivo ou restrições excedem o limite permitido.")
    return {
        "birth_year": datetime.utcnow().year - age,
        "gender": gender or None,
        "goal": goal or None,
        "activity_level": activity or None,
        "weight": weight,
        "height": height,
        "dietary_restrictions": restrictions or None,
    }


@professional_bp.route("/professional/students", methods=["POST"])
@professional_required
def create_offline_student():
    db.session.get(User, g.user.id, with_for_update=True)
    if _occupied_student_slots(g.user.id) >= 5:
        return jsonify({"error": "Seu plano permite acompanhar até 5 alunos."}), 409
    data = json_body()
    name = str(data.get("name") or data.get("username") or "").strip()
    if not name or len(name) > 100:
        return jsonify({"error": "Informe o nome do aluno (até 100 caracteres)."}), 400
    profile = _student_profile_payload(data)
    relationship = ProfessionalStudentRelationship(
        professional_user_id=g.user.id,
        student_name=name,
        student_profile=profile,
        status="offline",
        invite_expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.session.add(relationship)
    db.session.commit()
    return jsonify({"student": _offline_student_summary(relationship)}), 201


def _offline_student(relationship):
    profile_data = dict(relationship.student_profile or {})
    birth_year = profile_data.get("birth_year")
    profile_data["age"] = datetime.utcnow().year - birth_year if birth_year else profile_data.get("age")
    return SimpleNamespace(
        id=f"offline-{relationship.id}",
        relationship_id=relationship.id,
        username=relationship.student_name,
        name=relationship.student_name,
        profile=SimpleNamespace(**profile_data),
        is_offline=True,
    )


def _offline_student_summary(relationship):
    student = _offline_student(relationship)
    workout = WorkoutPlan.query.filter_by(
        professional_student_relationship_id=relationship.id,
    ).order_by(WorkoutPlan.created_at.desc()).first() if g.user.has_entitlement("workout") else None
    diet = DietPlan.query.filter_by(
        professional_student_relationship_id=relationship.id,
    ).order_by(DietPlan.created_at.desc()).first() if g.user.has_entitlement("diet") else None
    profile = student.profile
    return {
        "id": student.id,
        "username": student.username,
        "avatar_url": None,
        "has_profile": True,
        "is_offline": True,
        "roster_status": relationship.status,
        "profile": {
            "age": profile.age,
            "gender": profile.gender,
            "goal": profile.goal,
            "activity_level": profile.activity_level,
            "weight": profile.weight,
            "height": profile.height,
            "dietary_restrictions": profile.dietary_restrictions,
        },
        "latest_measurement": {"weight": profile.weight} if profile.weight is not None else None,
        "latest_workout_plan": workout.to_dict() if workout else None,
        "latest_diet_plan": diet.to_dict() if diet else None,
        "relationship": relationship.to_dict(),
    }


def _student_summary(student, relationship):
    if getattr(student, "is_offline", False):
        return _offline_student_summary(relationship)
    latest_measurement = Measurement.query.filter_by(user_id=student.id).order_by(Measurement.date.desc()).first()
    latest_workout = None
    if g.user.has_entitlement("workout"):
        latest_workout = WorkoutPlan.query.filter_by(user_id=student.id, author_user_id=g.user.id, status="published").order_by(
            WorkoutPlan.published_at.desc(), WorkoutPlan.created_at.desc()
        ).first()
    latest_diet = None
    if g.user.has_entitlement("diet"):
        latest_diet = DietPlan.query.filter_by(user_id=student.id, author_user_id=g.user.id, status="published").order_by(
            DietPlan.published_at.desc(), DietPlan.created_at.desc()
        ).first()
    profile = student.profile
    profile_data = None
    if profile:
        profile_data = {
            "age": profile.age,
            "gender": profile.gender,
            "goal": profile.goal,
            "activity_level": profile.activity_level,
            "weight": profile.weight,
            "height": profile.height,
            "timezone": profile.timezone,
        }
        if g.user.has_entitlement("diet"):
            profile_data["dietary_restrictions"] = profile.dietary_restrictions
    measurement_data = None
    if latest_measurement:
        measurement_data = {
            "date": latest_measurement.date.isoformat() if latest_measurement.date else None,
            "weight": latest_measurement.weight,
        }
        if g.user.has_entitlement("workout"):
            measurement_data = latest_measurement.to_dict()
    return {
        "id": student.id,
        "username": student.username,
        "avatar_url": (
            f"/api/profiles/by-id/{student.id}/avatar"
            if student.profile and student.profile.avatar_object_key else None
        ),
        "has_profile": student.profile is not None,
        "profile": profile_data,
        "latest_measurement": measurement_data,
        "latest_workout_plan": latest_workout.to_dict() if latest_workout else None,
        "latest_diet_plan": latest_diet.to_dict() if latest_diet else None,
        "relationship": relationship.to_dict(),
    }


@professional_bp.route("/professional/students/<string:student_id>", methods=["GET"])
@professional_required
def get_student(student_id):
    student, relationship = _student_context(student_id)
    summary = _student_summary(student, relationship)
    if getattr(student, "is_offline", False):
        summary.update({
            "measurements": [],
            "recent_diet_entries": [],
            "recent_diet_adherence": [],
            "recent_workout_sessions": [],
        })
        return jsonify(summary), 200
    if g.user.has_entitlement("workout"):
        summary["measurements"] = [
            item.to_dict() for item in Measurement.query.filter_by(user_id=student.id)
            .order_by(Measurement.date.desc()).limit(20).all()
        ]
    if g.user.has_entitlement("diet"):
        summary["recent_diet_entries"] = [
            item.to_dict() for item in DietEntry.query.filter_by(user_id=student.id)
            .order_by(DietEntry.date.desc(), DietEntry.created_at.desc()).limit(20).all()
        ]
        summary["recent_diet_adherence"] = [
            item.to_dict() for item in DietAdherenceDay.query.filter_by(user_id=student.id)
            .order_by(DietAdherenceDay.local_date.desc()).limit(30).all()
        ]
    if g.user.has_entitlement("workout"):
        summary["recent_workout_sessions"] = [
            item.to_dict() for item in WorkoutSession.query.filter(
                WorkoutSession.user_id == student.id,
                WorkoutSession.completed_at.isnot(None),
                WorkoutSession.workout_plan_id.in_(db.session.query(WorkoutPlan.id).filter_by(author_user_id=g.user.id)),
            ).order_by(WorkoutSession.completed_at.desc()).limit(20).all()
        ]
    return jsonify(summary), 200


@professional_bp.route("/professional/students/<string:student_id>", methods=["PUT"])
@professional_required
def update_offline_student(student_id):
    student, relationship = _student_context(student_id)
    if not getattr(student, "is_offline", False):
        return jsonify({"error": "O perfil de um aluno com conta é atualizado pelo próprio aluno."}), 409
    data = json_body()
    name = str(data.get("name") or "").strip()
    if not name or len(name) > 100:
        return jsonify({"error": "Informe o nome do aluno (até 100 caracteres)."}), 400
    relationship.student_name = name
    relationship.student_profile = _student_profile_payload(data)
    db.session.commit()
    return jsonify({"student": _offline_student_summary(relationship)}), 200


@professional_bp.route("/professional/students/<string:student_id>", methods=["DELETE"])
@professional_required
def revoke_student(student_id):
    student, relationship = _student_context(student_id, lock=True)
    relationship.status = "revoked"
    relationship.revoked_at = datetime.utcnow()
    relationship.revoked_by_user_id = g.user.id
    if not getattr(student, "is_offline", False):
        add_audit(g.user, student, relationship, "professional_student.revoked", "professional_student_relationship", relationship.id)
    db.session.commit()
    return jsonify({"message": "Vínculo encerrado. Os planos publicados permanecem com o aluno."}), 200


@professional_bp.route("/professional-relationship", methods=["GET"])
@login_required
def get_own_professional_relationship():
    relationship = ProfessionalStudentRelationship.query.filter_by(
        student_user_id=g.user.id,
        status="active",
    ).first()
    return jsonify({"relationship": relationship.to_dict() if relationship else None}), 200


@professional_bp.route("/professional-relationship", methods=["DELETE"])
@login_required
def revoke_own_professional_relationship():
    relationship = ProfessionalStudentRelationship.query.filter_by(
        student_user_id=g.user.id,
        status="active",
    ).with_for_update().first()
    if not relationship:
        return jsonify({"error": "Vínculo profissional não encontrado."}), 404
    relationship.status = "revoked"
    relationship.revoked_at = datetime.utcnow()
    relationship.revoked_by_user_id = g.user.id
    add_audit(
        g.user,
        g.user,
        relationship,
        "professional_student.revoked_by_student",
        "professional_student_relationship",
        relationship.id,
    )
    db.session.commit()
    return jsonify({"message": "Vínculo profissional encerrado."}), 200


@professional_bp.route("/professional/exercises", methods=["GET"])
@professional_scope_required("workout")
def get_exercises():
    return jsonify([
        {
            "catalog_key": item["key"],
            "name": item["name"],
            "primary_muscle": item["primary_muscle"],
            "equipment": item["equipment"],
            "difficulty": item["difficulty"],
            "aliases": item.get("aliases", []),
        }
        for item in selection_exercise_catalog()
    ]), 200


@professional_bp.route("/professional/students/<string:student_id>/workout-plans", methods=["GET"])
@professional_scope_required("workout")
def professional_workout_plans(student_id):
    student, _ = _student_context(student_id)
    owner_filter = {"professional_student_relationship_id": student.relationship_id} if getattr(student, "is_offline", False) else {"user_id": student.id}
    plans = WorkoutPlan.query.filter_by(**owner_filter).options(
        selectinload(WorkoutPlan.days), selectinload(WorkoutPlan.exercises)
    ).order_by(WorkoutPlan.created_at.desc()).all()
    return jsonify([
        plan.to_dict() for plan in plans
        if plan.author_user_id == g.user.id
        and not ProfessionalReviewRequest.query.filter_by(proposal_workout_plan_id=plan.id).first()
    ]), 200


@professional_bp.route("/professional/students/<string:student_id>/workout-plans/<int:plan_id>", methods=["GET"])
@professional_scope_required("workout")
def professional_workout_plan_details(student_id, plan_id):
    student, _ = _student_context(student_id)
    return jsonify(_workout_plan_for(student, plan_id).to_dict_full()), 200


@professional_bp.route("/professional/students/<string:student_id>/workout-plans", methods=["POST"])
@professional_scope_required("workout")
def create_manual_workout(student_id):
    student, relationship = _student_context(student_id)
    data = json_body()
    supersedes_plan_id = _superseded_plan_id(student, data, WorkoutPlan)
    try:
        questionnaire = validate_workout_questionnaire(data.get("questionnaire") or {})
        plan_data = normalize_manual_workout(data.get("plan") or {}, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o plano de treino.", "fields": error.errors}), 400
    try:
        plan = create_workout_plan(
            None if getattr(student, "is_offline", False) else student,
            g.user,
            questionnaire,
            plan_data,
            status="draft",
            source="manual",
            supersedes_plan_id=supersedes_plan_id,
            relationship=relationship if not getattr(student, "is_offline", False) else None,
            roster_relationship=relationship if getattr(student, "is_offline", False) else None,
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save professional workout draft")
        return jsonify({"error": "Não foi possível salvar o treino."}), 422
    return jsonify({"message": "Rascunho de treino criado.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<string:student_id>/workout-plans/generate", methods=["POST"])
@rate_limit("professional_ai", 8, 60)
@professional_scope_required("workout")
@ai_consent_required
def generate_professional_workout(student_id):
    student, relationship = _student_context(student_id)
    if getattr(student, "is_offline", False):
        return jsonify({"error": "A geração com IA fica disponível quando o aluno tiver uma conta e autorizar esse uso."}), 409
    if not student.has_current_ai_consent():
        return ai_consent_error()
    data = json_body()
    supersedes_plan_id = _superseded_plan_id(student, data, WorkoutPlan)
    try:
        questionnaire = validate_workout_questionnaire(data)
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências do treino.", "fields": error.errors}), 400
    queued = enqueue_ai_request("professional_workout_plan", data, {"student_id": student_id})
    if queued is not None:
        return queued
    contract = build_workout_contract(questionnaire)
    profile = UserProfile.query.filter_by(user_id=student.id).first()
    correction = None
    previous_generated = None
    max_attempts = current_app.config["GEMINI_WORKOUT_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        generated = previous_generated
        try:
            response_data = generate_workout_plan(questionnaire, profile, correction, contract)
            generated = (
                merge_workout_day_repairs(
                    previous_generated,
                    response_data,
                    correction["invalid_day_numbers"],
                    questionnaire["days_per_week"],
                )
                if correction
                else response_data
            )
            validate_workout_exercise_selection(generated, questionnaire, contract)
            plan_data = normalize_workout_output(generated, questionnaire, contract)
            break
        except PlanValidationError as error:
            if generated is not None:
                previous_generated = generated
                correction = {
                    "previous_plan": generated,
                    "validation_errors": error.errors,
                    "invalid_day_numbers": invalid_workout_day_numbers(
                        error.errors,
                        questionnaire["days_per_week"],
                    ),
                }
            if attempt == max_attempts:
                return jsonify({"error": "O treino gerado ficou incompleto. Tente novamente."}), 502
        except AIResponseError:
            if attempt == max_attempts:
                return jsonify({"error": "O treino gerado ficou incompleto. Tente novamente."}), 502
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceError:
            current_app.logger.exception("Professional workout generation failed")
            return jsonify({"error": "A IA não conseguiu gerar o treino agora."}), 503
    try:
        plan = create_workout_plan(
            student,
            g.user,
            questionnaire,
            plan_data,
            status="draft",
            source="ai",
            supersedes_plan_id=supersedes_plan_id,
            relationship=relationship if not getattr(student, "is_offline", False) else None,
        )
        plan.ai_task_id = getattr(g, "ai_task_id", None)
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        return jsonify({"error": "Não foi possível salvar o treino gerado."}), 422
    return jsonify({"message": "Treino gerado como rascunho.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<string:student_id>/workout-plans/<int:plan_id>", methods=["PUT"])
@professional_scope_required("workout")
def update_professional_workout(student_id, plan_id):
    student, relationship = _student_context(student_id)
    plan = _workout_plan_for(student, plan_id, editable=True)
    data = json_body()
    try:
        questionnaire = validate_workout_questionnaire(data.get("questionnaire") or {})
        plan_data = normalize_manual_workout(data.get("plan") or {}, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o plano de treino.", "fields": error.errors}), 400
    update_workout_draft(plan, questionnaire, plan_data)
    if not getattr(student, "is_offline", False):
        add_audit(g.user, student, relationship, "workout_plan.updated", "workout_plan", plan.id)
    db.session.commit()
    return jsonify({"message": "Rascunho atualizado.", "plan": plan.to_dict_full()}), 200


@professional_bp.route("/professional/students/<string:student_id>/workout-plans/<int:plan_id>/publish", methods=["POST"])
@professional_scope_required("workout")
def publish_professional_workout(student_id, plan_id):
    student, relationship = _student_context(student_id, lock=True)
    if getattr(student, "is_offline", False):
        return jsonify({"error": "Este aluno não possui conta no aplicativo para receber o plano."}), 409
    plan = _workout_plan_for(student, plan_id, editable=True)
    questionnaire = plan.questionnaire_data or {}
    raw_plan = {
        "type": "workout_plan",
        "title": plan.title,
        "description": plan.description,
        "days": [
            {
                "focus": day.focus,
                "exercises": [exercise.to_dict() for exercise in day.exercises],
            }
            for day in plan.days
        ],
    }
    try:
        normalize_manual_workout(raw_plan, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o treino antes de publicar.", "fields": error.errors}), 400
    publish_plan(plan, g.user, student, relationship, "workout_plan")
    db.session.commit()
    return jsonify({"message": "Treino enviado ao aluno.", "plan": plan.to_dict_full()}), 200


def _diet_plan_for(student, plan_id, editable=False):
    owner_filter = (
        {"professional_student_relationship_id": student.relationship_id}
        if getattr(student, "is_offline", False) else {"user_id": student.id}
    )
    plan = DietPlan.query.filter_by(author_user_id=g.user.id, id=plan_id, **owner_filter).options(
        selectinload(DietPlan.meals)
    ).first()
    if not plan or (plan.status == "draft" and plan.author_user_id != g.user.id):
        abort(404, description="Plano não encontrado.")
    if ProfessionalReviewRequest.query.filter_by(proposal_diet_plan_id=plan.id).first():
        abort(404, description="Plano não encontrado.")
    if editable and (plan.status != "draft" or plan.author_user_id != g.user.id):
        abort(409, description="Somente rascunhos próprios podem ser editados.")
    return plan


def _active_professional_count(student_id):
    return ProfessionalStudentRelationship.query.filter_by(student_user_id=student_id, status="active").count()


@professional_bp.route("/professionals/search", methods=["GET"])
@login_required
@rate_limit("professional_search", 30, 60)
def search_professionals():
    term = request.args.get("q", "").strip().lstrip("@")
    if not 2 <= len(term) <= 100:
        return jsonify({"items": []}), 200
    query = User.query.filter_by(is_professional=True, is_banned=False)
    try:
        professional_id = UUID(term)
        query = query.filter(User.id == professional_id)
    except ValueError:
        query = query.filter(db.func.lower(User.username) == term.lower())
    return jsonify({"items": [
        {"id": user.id, "username": user.username, "code": str(user.id)}
        for user in query.limit(10).all() if user.has_entitlement("professional") and user.id != g.user.id
    ]}), 200


@professional_bp.route("/professional-relationships", methods=["GET"])
@login_required
def own_professional_relationships():
    relationships = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.student_user_id == g.user.id,
        ProfessionalStudentRelationship.status.in_(("active", "pending")),
    ).order_by(ProfessionalStudentRelationship.created_at.desc()).all()
    return jsonify({"relationships": [item.to_dict() for item in relationships], "limit": 2,
                    "data_sharing_consent_version": PROFESSIONAL_SHARING_VERSION}), 200


@professional_bp.route("/professional-relationships/<int:relationship_id>", methods=["DELETE"])
@login_required
def revoke_relationship_by_id(relationship_id):
    relationship = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.id == relationship_id,
        ProfessionalStudentRelationship.student_user_id == g.user.id,
        ProfessionalStudentRelationship.status.in_(("active", "pending")),
    ).with_for_update().first_or_404()
    relationship.status = "revoked"
    relationship.invite_token_hash = None
    relationship.revoked_at = datetime.utcnow()
    relationship.revoked_by_user_id = g.user.id
    add_audit(g.user, g.user, relationship, "professional_student.revoked_by_student", "professional_student_relationship", relationship.id)
    db.session.commit()
    return jsonify({"message": "Vínculo profissional encerrado."}), 200


@professional_bp.route("/professionals/<uuid:professional_id>/requests", methods=["POST"])
@login_required
def request_professional_relationship(professional_id):
    data = json_body()
    if data.get("data_sharing_consent") is not True or data.get("data_sharing_consent_version") != PROFESSIONAL_SHARING_VERSION:
        return jsonify({"error": "Confirme o compartilhamento de dados.", "code": "data_sharing_consent_required"}), 400
    professional = db.session.get(User, professional_id)
    if not professional or professional.is_banned or not professional.has_entitlement("professional"):
        abort(404, description="Profissional não encontrado.")
    if professional.id == g.user.id:
        abort(409, description="Você não pode solicitar acompanhamento a si mesmo.")
    db.session.get(User, g.user.id, with_for_update=True)
    if _active_professional_count(g.user.id) >= 2:
        abort(409, description="Você já possui dois profissionais ativos.")
    ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == professional.id,
        ProfessionalStudentRelationship.student_user_id == g.user.id,
        ProfessionalStudentRelationship.status == "pending",
        ProfessionalStudentRelationship.invite_expires_at <= datetime.utcnow(),
    ).update({"status": "expired", "invite_token_hash": None}, synchronize_session=False)
    if ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == professional.id,
        ProfessionalStudentRelationship.student_user_id == g.user.id,
        ProfessionalStudentRelationship.status.in_(("pending", "active")),
    ).first():
        abort(409, description="Já existe um vínculo ou solicitação com este profissional.")
    relationship = ProfessionalStudentRelationship(
        professional_user_id=professional.id, student_user_id=g.user.id,
        initiated_by_user_id=g.user.id, request_message=str(data.get("message") or "")[:500],
        status="pending", invite_expires_at=datetime.utcnow() + timedelta(days=7),
        data_sharing_consented_at=datetime.utcnow(), data_sharing_consent_version=PROFESSIONAL_SHARING_VERSION,
    )
    db.session.add(relationship)
    conflict = _commit_or_conflict("Já existe uma solicitação com este profissional.")
    if conflict:
        return conflict
    return jsonify({"relationship": relationship.to_dict()}), 201


@professional_bp.route("/professional/requests", methods=["GET"])
@professional_required
def professional_relationship_requests():
    items = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == g.user.id,
        ProfessionalStudentRelationship.status == "pending",
        ProfessionalStudentRelationship.initiated_by_user_id == ProfessionalStudentRelationship.student_user_id,
        ProfessionalStudentRelationship.invite_expires_at > datetime.utcnow(),
    ).all()
    return jsonify({"items": [item.to_dict() for item in items]}), 200


@professional_bp.route("/professional/requests/<int:relationship_id>/accept", methods=["POST"])
@professional_required
def approve_relationship_request(relationship_id):
    relationship = ProfessionalStudentRelationship.query.filter_by(
        id=relationship_id, professional_user_id=g.user.id, status="pending",
    ).with_for_update().first_or_404()
    if not relationship.student_user_id or relationship.initiated_by_user_id != relationship.student_user_id or relationship.invite_expires_at <= datetime.utcnow():
        abort(404, description="Solicitação inválida ou expirada.")
    student = db.session.get(User, relationship.student_user_id, with_for_update=True)
    if not student or student.is_banned:
        abort(404, description="Aluno não encontrado.")
    db.session.get(User, g.user.id, with_for_update=True)
    if _active_professional_count(student.id) >= 2:
        abort(409, description="O aluno já possui dois profissionais ativos.")
    if _occupied_student_slots(g.user.id) >= 5:
        abort(409, description="Seu plano permite acompanhar até 5 alunos.")
    if relationship.data_sharing_consent_version != PROFESSIONAL_SHARING_VERSION:
        abort(409, description="O aluno precisa renovar o consentimento.")
    relationship.status = "active"
    relationship.accepted_at = datetime.utcnow()
    add_audit(g.user, student, relationship, "professional_student.accepted", "professional_student_relationship", relationship.id)
    db.session.commit()
    return jsonify({"relationship": relationship.to_dict()}), 200


@professional_bp.route("/professional-plans/inbox", methods=["GET"])
@login_required
def received_professional_plans():
    def items(model):
        plans = model.query.filter(
            model.user_id == g.user.id, model.author_user_id != g.user.id,
            model.status == "published", model.student_accepted_at.is_(None), model.student_declined_at.is_(None),
            model.author_user_id.in_(db.session.query(ProfessionalStudentRelationship.professional_user_id).filter_by(
                student_user_id=g.user.id, status="active")),
        ).order_by(model.published_at.desc()).all()
        return [{**plan.to_dict(), "professional": {"id": plan.author_user_id, "username": plan.author.username if plan.author else None}} for plan in plans]
    return jsonify({"workout_plans": items(WorkoutPlan), "diet_plans": items(DietPlan)}), 200


@professional_bp.route("/professional-plans/<string:kind>/<int:plan_id>/decline", methods=["POST"])
@login_required
def decline_professional_plan(kind, plan_id):
    model = {"workout": WorkoutPlan, "diet": DietPlan}.get(kind)
    if model is None:
        abort(404)
    plan = model.query.filter(model.id == plan_id, model.user_id == g.user.id,
                              model.author_user_id != g.user.id, model.status == "published").first_or_404()
    if plan.student_accepted_at:
        abort(409, description="O plano já foi aceito.")
    plan.student_declined_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Plano recusado."}), 200


def _manual_diet_payload(data):
    title = str(data.get("title") or "").strip()
    meals = data.get("meals")
    if not title or len(title) > 100 or not isinstance(meals, list) or not 1 <= len(meals) <= 24:
        abort(400, description="Informe título e entre 1 e 24 refeições.")
    normalized = []
    for order, meal in enumerate(meals, 1):
        if not isinstance(meal, dict):
            abort(400, description="Refeição inválida.")
        description = str(meal.get("description") or "").strip()
        meal_type = str(meal.get("meal_type") or "").strip()
        day = meal.get("day_of_week") or "Dia 1"
        if not description or len(description) > 2000 or not meal_type or len(meal_type) > 50 or day not in {"Dia 1", "Dia 2", "Dia 3"}:
            abort(400, description="Revise as refeições.")
        values = {}
        for field in ("calories", "protein", "carbs", "fat"):
            try:
                value = float(meal[field]) if meal.get(field) is not None else None
            except (TypeError, ValueError):
                abort(400, description="Valor nutricional inválido.")
            if value is not None and not 0 <= value <= (20000 if field == "calories" else 5000):
                abort(400, description="Valor nutricional inválido.")
            values[field] = value
        normalized.append({"day_of_week": day, "meal_type": meal_type, "description": description,
                           "order": order, **values})
    return {"title": title, "description": str(data.get("description") or "")[:2000], "meals": normalized}


@professional_bp.route("/professional/students/<string:student_id>/diet-plans", methods=["GET"])
@professional_scope_required("diet")
def professional_diet_plans(student_id):
    student, _ = _student_context(student_id)
    owner_filter = {"professional_student_relationship_id": student.relationship_id} if getattr(student, "is_offline", False) else {"user_id": student.id}
    plans = DietPlan.query.filter_by(author_user_id=g.user.id, **owner_filter).options(selectinload(DietPlan.meals)).order_by(
        DietPlan.created_at.desc()
    ).all()
    return jsonify([
        plan.to_dict() for plan in plans
        if (plan.status != "draft" or plan.author_user_id == g.user.id)
        and not ProfessionalReviewRequest.query.filter_by(proposal_diet_plan_id=plan.id).first()
    ]), 200


@professional_bp.route("/professional/students/<string:student_id>/diet-plans/<int:plan_id>", methods=["GET"])
@professional_scope_required("diet")
def professional_diet_plan_details(student_id, plan_id):
    student, _ = _student_context(student_id)
    return jsonify(_diet_plan_for(student, plan_id).to_dict_full()), 200


def _validated_diet_context(student, raw_questionnaire):
    questionnaire = validate_diet_questionnaire(raw_questionnaire)
    profile = student.profile if getattr(student, "is_offline", False) else UserProfile.query.filter_by(user_id=student.id).first()
    questionnaire = merge_profile_restrictions(questionnaire, profile)
    targets = calculate_nutrition_targets(profile, questionnaire)
    return questionnaire, profile, targets


@professional_bp.route("/professional/students/<string:student_id>/diet-plans", methods=["POST"])
@professional_scope_required("diet")
def create_manual_diet(student_id):
    student, relationship = _student_context(student_id)
    data = json_body()
    if "meals" in data:
        payload = json_body()
        supersedes_plan_id = _superseded_plan_id(student, payload, DietPlan)
        data = _manual_diet_payload(payload)
        plan = DietPlan(user_id=None if getattr(student, "is_offline", False) else student.id,
                        professional_student_relationship_id=student.relationship_id if getattr(student, "is_offline", False) else None,
                        author_user_id=g.user.id, status="draft", source="manual", title=data["title"],
                        supersedes_plan_id=supersedes_plan_id,
                        description=data["description"], schema_version=3, plan_mode="rotation_3_day",
                        meals_per_day=sum(meal["day_of_week"] == "Dia 1" for meal in data["meals"]))
        db.session.add(plan)
        db.session.flush()
        for meal in data["meals"]:
            db.session.add(DietPlanMeal(diet_plan_id=plan.id, **meal))
        db.session.commit()
        return jsonify({"plan": plan.to_dict_full()}), 201

    supersedes_plan_id = _superseded_plan_id(student, data, DietPlan)
    try:
        questionnaire, profile, targets = _validated_diet_context(student, data.get("questionnaire") or {})
        plan_data = normalize_manual_diet(data.get("plan") or {}, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o plano alimentar.", "fields": error.errors}), 400
    try:
        plan = create_diet_plan(
            None if getattr(student, "is_offline", False) else student,
            g.user,
            questionnaire,
            targets,
            plan_data,
            profile_snapshot(profile),
            status="draft",
            supersedes_plan_id=supersedes_plan_id,
            source="manual",
            relationship=relationship if not getattr(student, "is_offline", False) else None,
            roster_relationship=relationship if getattr(student, "is_offline", False) else None,
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        return jsonify({"error": "Não foi possível salvar o plano alimentar."}), 422
    return jsonify({"message": "Rascunho alimentar criado.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<string:student_id>/diet-plans/generate", methods=["POST"])
@rate_limit("professional_ai", 8, 60)
@professional_scope_required("diet")
@ai_consent_required
def generate_professional_diet(student_id):
    student, relationship = _student_context(student_id)
    if getattr(student, "is_offline", False):
        return jsonify({"error": "A geração com IA fica disponível quando o aluno tiver uma conta e autorizar esse uso."}), 409
    if not student.has_current_ai_consent():
        return ai_consent_error()
    data = json_body()
    supersedes_plan_id = _superseded_plan_id(student, data, DietPlan)
    try:
        questionnaire, profile, targets = _validated_diet_context(student, data)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o perfil e as preferências alimentares.", "fields": error.errors}), 400
    queued = enqueue_ai_request(
        "professional_diet_plan",
        data,
        {"student_id": student.id},
    )
    if queued is not None:
        return queued
    correction = None
    max_attempts = current_app.config["GEMINI_DIET_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        try:
            generated = generate_diet_plan(questionnaire, profile, targets, correction)
            plan_data = normalize_diet_output(generated, questionnaire, targets)
            break
        except PlanValidationError as error:
            if attempt == max_attempts:
                return jsonify({"error": "A dieta não atingiu as metas nutricionais."}), 502
            correction = correction_feedback(error, generated, targets)
        except AIResponseError:
            if attempt == max_attempts:
                return jsonify({"error": "A dieta gerada ficou incompleta."}), 502
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceError:
            current_app.logger.exception("Professional diet generation failed")
            return jsonify({"error": "A IA não conseguiu gerar a dieta agora."}), 503
    try:
        plan = create_diet_plan(
            None if getattr(student, "is_offline", False) else student,
            g.user,
            questionnaire,
            targets,
            plan_data,
            profile_snapshot(profile),
            status="draft",
            supersedes_plan_id=supersedes_plan_id,
            source="ai",
            relationship=relationship if not getattr(student, "is_offline", False) else None,
            roster_relationship=relationship if getattr(student, "is_offline", False) else None,
        )
        plan.ai_task_id = getattr(g, "ai_task_id", None)
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        return jsonify({"error": "Não foi possível salvar a dieta gerada."}), 422
    return jsonify({"message": "Dieta gerada como rascunho.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<string:student_id>/diet-plans/<int:plan_id>", methods=["PUT"])
@professional_scope_required("diet")
def update_professional_diet(student_id, plan_id):
    student, relationship = _student_context(student_id)
    plan = _diet_plan_for(student, plan_id, editable=True)
    data = json_body()
    if "meals" in data:
        data = _manual_diet_payload(json_body())
        plan.title, plan.description = data["title"], data["description"]
        plan.generation_context = {**(plan.generation_context or {}), "manual_edit": True}
        plan.meals.clear()
        db.session.flush()
        for meal in data["meals"]:
            plan.meals.append(DietPlanMeal(**meal))
        plan.meals_per_day = sum(meal["day_of_week"] == "Dia 1" for meal in data["meals"])
        if not getattr(student, "is_offline", False):
            add_audit(g.user, student, relationship, "diet_plan.updated", "diet_plan", plan.id)
        db.session.commit()
        return jsonify({"plan": plan.to_dict_full()}), 200

    try:
        questionnaire, profile, targets = _validated_diet_context(student, data.get("questionnaire") or {})
        plan_data = normalize_manual_diet(data.get("plan") or {}, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o plano alimentar.", "fields": error.errors}), 400
    update_diet_draft(plan, questionnaire, targets, plan_data, profile_snapshot(profile))
    if not getattr(student, "is_offline", False):
        add_audit(g.user, student, relationship, "diet_plan.updated", "diet_plan", plan.id)
    db.session.commit()
    return jsonify({"message": "Rascunho atualizado.", "plan": plan.to_dict_full()}), 200


@professional_bp.route("/professional/students/<string:student_id>/diet-plans/<int:plan_id>/suggest", methods=["POST"])
@rate_limit("professional_ai", 8, 60)
@professional_scope_required("diet")
@ai_consent_required
def suggest_professional_diet_day(student_id, plan_id):
    student, _ = _student_context(student_id)
    if getattr(student, "is_offline", False):
        return jsonify({"error": "Sugestões com IA ficam disponíveis quando o aluno tiver uma conta e autorizar esse uso."}), 409
    if not student.has_current_ai_consent():
        return ai_consent_error()
    plan = _diet_plan_for(student, plan_id, editable=True)
    data = json_body()
    try:
        day_index = int(data.get("day"))
    except (TypeError, ValueError):
        day_index = 0
    feedback = str(data.get("feedback", "")).strip()[:500]
    if day_index not in {1, 2, 3} or not feedback:
        return jsonify({"error": "Informe um dia válido e a mudança desejada."}), 400
    context = plan.generation_context or {}
    questionnaire = context.get("questionnaire")
    targets = context.get("nutrition_targets")
    if not questionnaire or not targets:
        return jsonify({"error": "Este plano não possui contexto para sugestões."}), 422
    existing_meals = [
        {"meal_type": meal.meal_type, "items": meal.items or [], "description": meal.description}
        for meal in plan.meals if meal.day_of_week == f"Dia {day_index}"
    ]
    profile = UserProfile.query.filter_by(user_id=student.id).first()
    queued = enqueue_ai_request(
        "professional_diet_day",
        data,
        {"student_id": student.id, "plan_id": plan.id},
    )
    if queued is not None:
        return queued
    correction = None
    max_attempts = current_app.config["GEMINI_DIET_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        try:
            generated = generate_diet_day(
                questionnaire, profile, existing_meals, feedback, targets, correction
            )
            day_data = normalize_diet_day(generated, questionnaire, targets)
            break
        except PlanValidationError as error:
            if attempt == max_attempts:
                return jsonify({"error": "A sugestão não atingiu as metas nutricionais."}), 502
            correction = correction_feedback(error, generated, targets)
        except AIResponseError:
            if attempt == max_attempts:
                return jsonify({"error": "A sugestão ficou incompleta."}), 502
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceError:
            return jsonify({"error": "A IA não conseguiu sugerir mudanças agora."}), 503
    return jsonify({"day": day_index, "meals": day_data["meals"]}), 200


@professional_bp.route("/professional/students/<string:student_id>/diet-plans/<int:plan_id>/days/<int:day_index>", methods=["PUT"])
@professional_scope_required("diet")
def replace_professional_diet_day(student_id, plan_id, day_index):
    student, relationship = _student_context(student_id)
    plan = _diet_plan_for(student, plan_id, editable=True)
    context = plan.generation_context or {}
    questionnaire = context.get("questionnaire")
    targets = context.get("nutrition_targets")
    meals = json_body().get("meals")
    raw_day = {
        "type": "diet_plan_day",
        "meals": [
            {
                "meal_type": meal.get("meal_type"),
                "items": meal.get("items"),
                "prep": meal.get("prep_instructions"),
                "prep_minutes": meal.get("prep_minutes"),
                "calories": meal.get("calories"),
                "protein": meal.get("protein"),
                "carbs": meal.get("carbs"),
                "fat": meal.get("fat"),
                "notes": meal.get("notes"),
                "substitutions": meal.get("substitutions"),
            }
            for meal in meals if isinstance(meal, dict)
        ] if isinstance(meals, list) else None,
    }
    if day_index not in {1, 2, 3} or not questionnaire or not targets:
        return jsonify({"error": "Plano ou dia inválido."}), 422
    try:
        normalized = normalize_diet_day(raw_day, questionnaire, targets)["meals"]
    except PlanValidationError as error:
        return jsonify({"error": "O cardápio informado não é válido.", "fields": error.errors}), 400
    replace_diet_day(plan, day_index, normalized)
    if not getattr(student, "is_offline", False):
        add_audit(g.user, student, relationship, "diet_plan.day_updated", "diet_plan", plan.id, {"day": day_index})
    db.session.commit()
    return jsonify({"message": "Cardápio atualizado.", "plan": plan.to_dict_full()}), 200


@professional_bp.route("/professional/students/<string:student_id>/diet-plans/<int:plan_id>/publish", methods=["POST"])
@professional_scope_required("diet")
def publish_professional_diet(student_id, plan_id):
    student, relationship = _student_context(student_id, lock=True)
    if getattr(student, "is_offline", False):
        return jsonify({"error": "Este aluno não possui conta no aplicativo para receber o plano."}), 409
    plan = _diet_plan_for(student, plan_id, editable=True)
    if not (plan.generation_context or {}).get("questionnaire") or (plan.generation_context or {}).get("manual_edit"):
        _manual_diet_payload(plan.to_dict_full())
    else:
        context = plan.generation_context or {}
        questionnaire = context.get("questionnaire") or {}
        targets = context.get("nutrition_targets") or {}
        raw_days = []
        for day_index in range(1, 4):
            raw_days.append({"meals": [
                {
                    "meal_type": meal.meal_type,
                    "items": meal.items,
                    "prep": meal.prep_instructions,
                    "prep_minutes": meal.prep_minutes,
                    "calories": meal.calories,
                    "protein": meal.protein,
                    "carbs": meal.carbs,
                    "fat": meal.fat,
                    "notes": meal.notes,
                    "substitutions": meal.substitutions,
                }
                for meal in plan.meals if meal.day_of_week == f"Dia {day_index}"
            ]})
        try:
            normalize_diet_output({
                "type": "diet_plan",
                "title": plan.title,
                "description": plan.description,
                "days": raw_days,
            }, questionnaire, targets)
        except PlanValidationError as error:
            return jsonify({"error": "Revise a dieta antes de publicar.", "fields": error.errors}), 400
    publish_plan(plan, g.user, student, relationship, "diet_plan")
    db.session.commit()
    return jsonify({"message": "Plano alimentar enviado ao aluno.", "plan": plan.to_dict_full()}), 200
