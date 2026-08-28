import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, g, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.models.user import (
    DietEntry,
    DietPlan,
    Measurement,
    ProfessionalStudentRelationship,
    User,
    UserProfile,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
    db,
)
from src.routes.common import json_body, login_required, page_query, _csrf_protect_request
from src.services.ai import (
    AIQuotaExceededError,
    AIResponseError,
    AIServiceError,
    generate_diet_day,
    generate_diet_plan,
    generate_workout_plan,
)
from src.services.diet_plans import (
    calculate_nutrition_targets,
    correction_feedback,
    merge_profile_restrictions,
    normalize_manual_diet,
    normalize_diet_day,
    normalize_diet_output,
    profile_snapshot,
    validate_diet_questionnaire,
)
from src.services.plan_management import (
    add_audit,
    create_diet_plan,
    create_workout_plan,
    publish_plan,
    replace_diet_day,
    update_diet_draft,
    update_workout_draft,
)
from src.services.rate_limit import rate_limit
from src.services.workout_plans import (
    PlanValidationError,
    exercise_catalog,
    normalize_manual_workout,
    normalize_workout_output,
    validate_workout_questionnaire,
)


professional_bp = Blueprint("professional", __name__)


@professional_bp.before_request
def protect_professional_mutations():
    return _csrf_protect_request()


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
        if not g.user.is_professional:
            return jsonify({"error": "Acesso exclusivo para profissionais habilitados."}), 403
        return function(*args, **kwargs)

    return decorated_function


def professional_premium_required(function):
    @wraps(function)
    @professional_required
    def decorated_function(*args, **kwargs):
        if not g.user.has_entitlement("premium"):
            return jsonify({"error": "Este recurso de IA exige plano Premium do profissional."}), 403
        return function(*args, **kwargs)

    return decorated_function


def professional_scope_required(scope):
    def decorator(function):
        @wraps(function)
        @professional_required
        def decorated_function(*args, **kwargs):
            # A null scope identifies professionals created before specialties existed.
            if g.user.professional_scope not in {None, scope, "both"}:
                return jsonify({"error": "Seu plano profissional não inclui este recurso."}), 403
            return function(*args, **kwargs)

        return decorated_function
    return decorator


def _occupied_student_slots(professional_id):
    now = datetime.utcnow()
    relationships = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == professional_id,
        ProfessionalStudentRelationship.status.in_(("active", "pending")),
    ).all()
    return sum(
        relationship.status == "active"
        or (relationship.invite_expires_at and relationship.invite_expires_at > now)
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
    relationship = _relationship_for(g.user.id, student_id, lock=lock)
    if not relationship:
        abort(404, description="Aluno não encontrado.")
    student = db.session.get(User, student_id)
    if not student or student.is_banned:
        abort(404, description="Aluno não encontrado.")
    return student, relationship


def _workout_plan_for(student, plan_id, editable=False):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=student.id).options(
        selectinload(WorkoutPlan.days).selectinload(WorkoutDay.exercises),
        selectinload(WorkoutPlan.exercises),
    ).first()
    if not plan or (plan.status == "draft" and plan.author_user_id != g.user.id):
        abort(404, description="Plano não encontrado.")
    if editable and (plan.status != "draft" or plan.author_user_id != g.user.id):
        abort(409, description="Somente rascunhos próprios podem ser editados.")
    return plan


def _diet_plan_for(student, plan_id, editable=False):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=student.id).options(
        selectinload(DietPlan.meals)
    ).first()
    if not plan or (plan.status == "draft" and plan.author_user_id != g.user.id):
        abort(404, description="Plano não encontrado.")
    if editable and (plan.status != "draft" or plan.author_user_id != g.user.id):
        abort(409, description="Somente rascunhos próprios podem ser editados.")
    return plan


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
            relationship.status = "expired"
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
    relationship.status = "revoked"
    relationship.revoked_at = datetime.utcnow()
    relationship.revoked_by_user_id = g.user.id
    db.session.commit()
    return jsonify({"message": "Convite cancelado."}), 200


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
        or not relationship.professional.is_professional
        or relationship.professional.is_banned
    ):
        return jsonify({"error": "Convite inválido ou expirado."}), 404
    if relationship.professional_user_id == g.user.id:
        return jsonify({"error": "O profissional não pode aceitar o próprio convite."}), 409
    return jsonify({"invitation": relationship.to_dict()}), 200


@professional_bp.route("/invitations/<token>/accept", methods=["POST"])
@login_required
def accept_invitation(token):
    relationship = ProfessionalStudentRelationship.query.filter_by(
        invite_token_hash=_token_hash(token),
    ).with_for_update().first()
    if (
        not relationship
        or relationship.status != "pending"
        or relationship.invite_expires_at <= datetime.utcnow()
        or not relationship.professional.is_professional
        or relationship.professional.is_banned
    ):
        return jsonify({"error": "Convite inválido ou expirado."}), 404
    if relationship.professional_user_id == g.user.id:
        return jsonify({"error": "O profissional não pode aceitar o próprio convite."}), 409
    active = ProfessionalStudentRelationship.query.filter_by(
        student_user_id=g.user.id,
        status="active",
    ).first()
    if active:
        return jsonify({"error": "Você já possui um profissional ativo."}), 409
    active_students = ProfessionalStudentRelationship.query.filter_by(
        professional_user_id=relationship.professional_user_id,
        status="active",
    ).count()
    if active_students >= 5:
        return jsonify({"error": "Este profissional já atingiu o limite de 5 alunos."}), 409
    relationship.student_user_id = g.user.id
    relationship.status = "active"
    relationship.accepted_at = datetime.utcnow()
    add_audit(
        relationship.professional,
        g.user,
        relationship,
        "professional_student.accepted",
        "professional_student_relationship",
        relationship.id,
    )
    conflict = _commit_or_conflict("Você já possui um profissional ativo.")
    if conflict:
        return conflict
    return jsonify({"message": "Vínculo profissional aceito.", "relationship": relationship.to_dict()}), 200


@professional_bp.route("/professional/students", methods=["GET"])
@professional_required
def list_students():
    query = ProfessionalStudentRelationship.query.filter_by(
        professional_user_id=g.user.id,
        status="active",
    ).order_by(ProfessionalStudentRelationship.accepted_at.desc())
    query, limit, offset = page_query(query, default_limit=30)
    relationships = query.all()
    return jsonify({
        "items": [_student_summary(item.student, item) for item in relationships],
        "limit": limit,
        "offset": offset,
    }), 200


def _student_summary(student, relationship):
    latest_measurement = Measurement.query.filter_by(user_id=student.id).order_by(Measurement.date.desc()).first()
    latest_workout = WorkoutPlan.query.filter_by(user_id=student.id, status="published").order_by(
        WorkoutPlan.published_at.desc(), WorkoutPlan.created_at.desc()
    ).first()
    latest_diet = DietPlan.query.filter_by(user_id=student.id, status="published").order_by(
        DietPlan.published_at.desc(), DietPlan.created_at.desc()
    ).first()
    return {
        "id": student.id,
        "username": student.username,
        "has_profile": student.profile is not None,
        "profile": student.profile.to_dict() if student.profile else None,
        "latest_measurement": latest_measurement.to_dict() if latest_measurement else None,
        "latest_workout_plan": latest_workout.to_dict() if latest_workout else None,
        "latest_diet_plan": latest_diet.to_dict() if latest_diet else None,
        "relationship": relationship.to_dict(),
    }


@professional_bp.route("/professional/students/<uuid:student_id>", methods=["GET"])
@professional_required
def get_student(student_id):
    student, relationship = _student_context(student_id)
    summary = _student_summary(student, relationship)
    summary["measurements"] = [
        item.to_dict() for item in Measurement.query.filter_by(user_id=student.id)
        .order_by(Measurement.date.desc()).limit(20).all()
    ]
    summary["recent_diet_entries"] = [
        item.to_dict() for item in DietEntry.query.filter_by(user_id=student.id)
        .order_by(DietEntry.date.desc(), DietEntry.created_at.desc()).limit(20).all()
    ]
    summary["recent_workout_sessions"] = [
        item.to_dict() for item in WorkoutSession.query.filter_by(user_id=student.id)
        .order_by(WorkoutSession.started_at.desc()).limit(20).all()
    ]
    return jsonify(summary), 200


@professional_bp.route("/professional/students/<uuid:student_id>", methods=["DELETE"])
@professional_required
def revoke_student(student_id):
    student, relationship = _student_context(student_id, lock=True)
    relationship.status = "revoked"
    relationship.revoked_at = datetime.utcnow()
    relationship.revoked_by_user_id = g.user.id
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
        }
        for item in exercise_catalog()
    ]), 200


@professional_bp.route("/professional/students/<uuid:student_id>/workout-plans", methods=["GET"])
@professional_scope_required("workout")
def professional_workout_plans(student_id):
    student, _ = _student_context(student_id)
    plans = WorkoutPlan.query.filter_by(user_id=student.id).options(
        selectinload(WorkoutPlan.days), selectinload(WorkoutPlan.exercises)
    ).order_by(WorkoutPlan.created_at.desc()).all()
    return jsonify([
        plan.to_dict() for plan in plans
        if plan.status != "draft" or plan.author_user_id == g.user.id
    ]), 200


@professional_bp.route("/professional/students/<uuid:student_id>/workout-plans/<int:plan_id>", methods=["GET"])
@professional_scope_required("workout")
def professional_workout_plan_details(student_id, plan_id):
    student, _ = _student_context(student_id)
    return jsonify(_workout_plan_for(student, plan_id).to_dict_full()), 200


@professional_bp.route("/professional/students/<uuid:student_id>/workout-plans", methods=["POST"])
@professional_scope_required("workout")
def create_manual_workout(student_id):
    student, relationship = _student_context(student_id)
    data = json_body()
    try:
        questionnaire = validate_workout_questionnaire(data.get("questionnaire") or {})
        plan_data = normalize_manual_workout(data.get("plan") or {}, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o plano de treino.", "fields": error.errors}), 400
    try:
        plan = create_workout_plan(
            student,
            g.user,
            questionnaire,
            plan_data,
            status="draft",
            source="manual",
            relationship=relationship,
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save professional workout draft")
        return jsonify({"error": "Não foi possível salvar o treino."}), 422
    return jsonify({"message": "Rascunho de treino criado.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<uuid:student_id>/workout-plans/generate", methods=["POST"])
@rate_limit("professional_ai", 8, 60)
@professional_scope_required("workout")
@professional_premium_required
def generate_professional_workout(student_id):
    student, relationship = _student_context(student_id)
    try:
        questionnaire = validate_workout_questionnaire(json_body())
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências do treino.", "fields": error.errors}), 400
    profile = UserProfile.query.filter_by(user_id=student.id).first()
    for attempt in range(1, 4):
        try:
            plan_data = normalize_workout_output(generate_workout_plan(questionnaire, profile), questionnaire)
            break
        except (PlanValidationError, AIResponseError):
            if attempt == 3:
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
            relationship=relationship,
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        return jsonify({"error": "Não foi possível salvar o treino gerado."}), 422
    return jsonify({"message": "Treino gerado como rascunho.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<uuid:student_id>/workout-plans/<int:plan_id>", methods=["PUT"])
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
    add_audit(g.user, student, relationship, "workout_plan.updated", "workout_plan", plan.id)
    db.session.commit()
    return jsonify({"message": "Rascunho atualizado.", "plan": plan.to_dict_full()}), 200


@professional_bp.route("/professional/students/<uuid:student_id>/workout-plans/<int:plan_id>/publish", methods=["POST"])
@professional_scope_required("workout")
def publish_professional_workout(student_id, plan_id):
    student, relationship = _student_context(student_id, lock=True)
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
        normalize_workout_output(raw_plan, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o treino antes de publicar.", "fields": error.errors}), 400
    publish_plan(plan, g.user, student, relationship, "workout_plan")
    db.session.commit()
    return jsonify({"message": "Treino enviado ao aluno.", "plan": plan.to_dict_full()}), 200


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans", methods=["GET"])
@professional_scope_required("diet")
def professional_diet_plans(student_id):
    student, _ = _student_context(student_id)
    plans = DietPlan.query.filter_by(user_id=student.id).options(selectinload(DietPlan.meals)).order_by(
        DietPlan.created_at.desc()
    ).all()
    return jsonify([
        plan.to_dict() for plan in plans
        if plan.status != "draft" or plan.author_user_id == g.user.id
    ]), 200


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans/<int:plan_id>", methods=["GET"])
@professional_scope_required("diet")
def professional_diet_plan_details(student_id, plan_id):
    student, _ = _student_context(student_id)
    return jsonify(_diet_plan_for(student, plan_id).to_dict_full()), 200


def _validated_diet_context(student, raw_questionnaire):
    questionnaire = validate_diet_questionnaire(raw_questionnaire)
    profile = UserProfile.query.filter_by(user_id=student.id).first()
    questionnaire = merge_profile_restrictions(questionnaire, profile)
    targets = calculate_nutrition_targets(profile, questionnaire)
    return questionnaire, profile, targets


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans", methods=["POST"])
@professional_scope_required("diet")
def create_manual_diet(student_id):
    student, relationship = _student_context(student_id)
    data = json_body()
    try:
        questionnaire, profile, targets = _validated_diet_context(student, data.get("questionnaire") or {})
        plan_data = normalize_manual_diet(data.get("plan") or {}, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o plano alimentar.", "fields": error.errors}), 400
    try:
        plan = create_diet_plan(
            student,
            g.user,
            questionnaire,
            targets,
            plan_data,
            profile_snapshot(profile),
            status="draft",
            source="manual",
            relationship=relationship,
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        return jsonify({"error": "Não foi possível salvar o plano alimentar."}), 422
    return jsonify({"message": "Rascunho alimentar criado.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans/generate", methods=["POST"])
@rate_limit("professional_ai", 8, 60)
@professional_scope_required("diet")
@professional_premium_required
def generate_professional_diet(student_id):
    student, relationship = _student_context(student_id)
    try:
        questionnaire, profile, targets = _validated_diet_context(student, json_body())
    except PlanValidationError as error:
        return jsonify({"error": "Revise o perfil e as preferências alimentares.", "fields": error.errors}), 400
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
            student,
            g.user,
            questionnaire,
            targets,
            plan_data,
            profile_snapshot(profile),
            status="draft",
            source="ai",
            relationship=relationship,
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        return jsonify({"error": "Não foi possível salvar a dieta gerada."}), 422
    return jsonify({"message": "Dieta gerada como rascunho.", "plan": plan.to_dict_full()}), 201


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans/<int:plan_id>", methods=["PUT"])
@professional_scope_required("diet")
def update_professional_diet(student_id, plan_id):
    student, relationship = _student_context(student_id)
    plan = _diet_plan_for(student, plan_id, editable=True)
    data = json_body()
    try:
        questionnaire, profile, targets = _validated_diet_context(student, data.get("questionnaire") or {})
        plan_data = normalize_manual_diet(data.get("plan") or {}, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise o plano alimentar.", "fields": error.errors}), 400
    update_diet_draft(plan, questionnaire, targets, plan_data, profile_snapshot(profile))
    add_audit(g.user, student, relationship, "diet_plan.updated", "diet_plan", plan.id)
    db.session.commit()
    return jsonify({"message": "Rascunho atualizado.", "plan": plan.to_dict_full()}), 200


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans/<int:plan_id>/suggest", methods=["POST"])
@rate_limit("professional_ai", 8, 60)
@professional_scope_required("diet")
@professional_premium_required
def suggest_professional_diet_day(student_id, plan_id):
    student, _ = _student_context(student_id)
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


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans/<int:plan_id>/days/<int:day_index>", methods=["PUT"])
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
    add_audit(g.user, student, relationship, "diet_plan.day_updated", "diet_plan", plan.id, {"day": day_index})
    db.session.commit()
    return jsonify({"message": "Cardápio atualizado.", "plan": plan.to_dict_full()}), 200


@professional_bp.route("/professional/students/<uuid:student_id>/diet-plans/<int:plan_id>/publish", methods=["POST"])
@professional_scope_required("diet")
def publish_professional_diet(student_id, plan_id):
    student, relationship = _student_context(student_id, lock=True)
    plan = _diet_plan_for(student, plan_id, editable=True)
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
