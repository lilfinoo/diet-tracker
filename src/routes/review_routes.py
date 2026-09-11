from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from src.legal import PROFESSIONAL_SHARING_VERSION
from src.models.user import (
    DietPlan,
    ProfessionalReviewRequest,
    ProfessionalStudentRelationship,
    User,
    WorkoutPlan,
    WorkoutSession,
    db,
)
from src.routes.common import (
    _apply_workout_plan_schedule,
    _get_or_create_profile,
    _local_date_for_timezone,
    json_body,
    login_required,
    page_query,
)
from src.services.diet_plans import normalize_manual_diet, profile_snapshot, validate_diet_questionnaire
from src.services.plan_management import (
    add_audit,
    clone_plan_for_review,
    plan_snapshot,
    professional_review_for_plan,
    publish_plan,
    snapshot_fingerprint,
    update_diet_draft,
    update_workout_draft,
)
from src.services.workout_plans import PlanValidationError, normalize_manual_workout, validate_workout_questionnaire
from src.services.workout_progress import user_timezone


review_bp = Blueprint("reviews", __name__)
ACTIVE_STATUSES = ("pending", "accepted", "in_review")
TERMINAL_STATUSES = ("completed", "declined", "cancelled", "expired")
REVIEW_FOCUS = {
    "workout": {"structure", "volume", "exercises", "progression", "goal_fit", "limitations"},
    "diet": {"structure", "portions", "foods", "routine", "goal_fit", "limitations"},
}


def professional_scope_required(scope):
    def decorator(function):
        @wraps(function)
        @login_required
        def wrapped(*args, **kwargs):
            if not g.user.has_entitlement(scope):
                return jsonify({"error": "Profissional sem habilitação para esta revisão."}), 403
            return function(*args, **kwargs)

        return wrapped
    return decorator


def _source_plan(plan_type, plan_id, owner_id):
    model = WorkoutPlan if plan_type == "workout" else DietPlan
    return model.query.filter_by(id=plan_id, user_id=owner_id, status="published").first()


def _scope(plan_type):
    return "workout" if plan_type == "workout" else "diet"


def _accepts_external(professional, plan_type):
    field = f"accepts_external_{plan_type}_reviews"
    return bool(professional.profile and getattr(professional.profile, field, False))


def _context(plan, profile):
    snapshot = plan_snapshot(plan)
    questionnaire = snapshot.get("questionnaire") or {}
    allowed = {
        "goal", "experience_level", "days_per_week", "session_duration", "equipment",
        "limitations", "priorities", "avoid_exercises", "meals_per_day", "diet_pattern",
        "allergies", "intolerances", "disliked_foods", "preferred_foods",
    }
    context = {key: value for key, value in questionnaire.items() if key in allowed}
    if profile and profile.goal and "goal" not in context:
        context["goal"] = profile.goal
    return context


def _authorized_review(review, professional=False):
    if professional:
        allowed = review.assigned_professional_user_id == g.user.id or (
            review.status == "pending" and review.requested_professional_user_id == g.user.id
        )
    else:
        allowed = review.student_user_id == g.user.id
    return review if allowed else None


def _professional_access(review):
    return (
        g.user.id != review.student_user_id
        and g.user.has_entitlement(_scope(review.plan_type))
        and (
            review.assigned_professional_user_id == g.user.id
            or (review.status == "pending" and review.requested_professional_user_id == g.user.id)
        )
    )


def _expire_pending(review):
    if review.status == "pending" and review.expires_at <= datetime.utcnow():
        review.status = "expired"
        review.resolved_at = datetime.utcnow()
        db.session.commit()
        return True
    return False


@review_bp.route("/plan-reviews", methods=["POST", "GET"])
@login_required
def plan_reviews():
    if request.method == "GET":
        query = ProfessionalReviewRequest.query.filter_by(student_user_id=g.user.id).order_by(
            ProfessionalReviewRequest.created_at.desc()
        )
        query, limit, offset = page_query(query, default_limit=30)
        return jsonify({
            "items": [item.to_dict() for item in query.all()],
            "limit": limit,
            "offset": offset,
        }), 200

    data = json_body()
    plan_type = str(data.get("plan_type", ""))
    if plan_type not in {"workout", "diet"}:
        return jsonify({"error": "Tipo de plano inválido."}), 400
    try:
        plan_id = int(data.get("plan_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Plano inválido."}), 400
    plan = _source_plan(plan_type, plan_id, g.user.id)
    if not plan:
        return jsonify({"error": "Plano não encontrado."}), 404
    if data.get("data_sharing_consent") is not True:
        return jsonify({"error": "Confirme o compartilhamento dos dados desta revisão."}), 400
    if data.get("sharing_consent_version") != PROFESSIONAL_SHARING_VERSION:
        return jsonify({"error": "Atualize e confirme o consentimento de compartilhamento."}), 409
    source_column = (
        ProfessionalReviewRequest.source_workout_plan_id
        if plan_type == "workout"
        else ProfessionalReviewRequest.source_diet_plan_id
    )
    if ProfessionalReviewRequest.query.filter(
        ProfessionalReviewRequest.student_user_id == g.user.id,
        ProfessionalReviewRequest.status.in_(ACTIVE_STATUSES),
        source_column == plan.id,
    ).first():
        return jsonify({"error": "Este plano já possui uma revisão em andamento."}), 409

    mode = str(data.get("target_mode", ""))
    requested = None
    relationship = None
    if mode == "linked":
        relationship = ProfessionalStudentRelationship.query.filter_by(
            student_user_id=g.user.id,
            status="active",
            data_sharing_consent_version=PROFESSIONAL_SHARING_VERSION,
        ).first()
        requested = relationship.professional if relationship else None
    elif mode == "specific":
        requested = User.query.filter_by(id=data.get("professional_id"), is_banned=False).first()
        if requested and (not requested.profile or not requested.profile.is_public or not _accepts_external(requested, plan_type)):
            requested = None
    elif mode != "open":
        return jsonify({"error": "Destino da revisão inválido."}), 400
    if requested and not requested.has_entitlement(_scope(plan_type)):
        requested = None
    if requested and requested.id == g.user.id:
        return jsonify({"error": "Você não pode revisar o próprio plano."}), 409
    if mode in {"linked", "specific"} and not requested:
        return jsonify({"error": "Profissional indisponível para esta revisão."}), 409

    focus = data.get("review_focus") or []
    if not isinstance(focus, list) or not focus or any(item not in REVIEW_FOCUS[plan_type] for item in focus):
        return jsonify({"error": "Escolha ao menos um ponto válido para revisão."}), 400
    note = str(data.get("student_note", "")).strip()
    if len(note) > 2000:
        return jsonify({"error": "A observação deve ter no máximo 2000 caracteres."}), 400
    snapshot = plan_snapshot(plan)
    review = ProfessionalReviewRequest(
        student_user_id=g.user.id,
        requested_professional_user_id=requested.id if requested else None,
        relationship_id=relationship.id if relationship else None,
        plan_type=plan_type,
        source_workout_plan_id=plan.id if plan_type == "workout" else None,
        source_diet_plan_id=plan.id if plan_type == "diet" else None,
        target_mode=mode,
        review_focus=focus,
        student_note=note or None,
        context_snapshot=_context(plan, g.user.profile),
        source_snapshot=snapshot,
        source_fingerprint=snapshot_fingerprint(snapshot),
        sharing_consent_version=PROFESSIONAL_SHARING_VERSION,
        sharing_consented_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.session.add(review)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Este plano já possui uma revisão em andamento."}), 409
    return jsonify({"message": "Revisão solicitada.", "review": review.to_dict()}), 201


@review_bp.route("/plan-reviews/<uuid:review_id>", methods=["GET"])
@login_required
def review_details(review_id):
    review = ProfessionalReviewRequest.query.get_or_404(review_id)
    _expire_pending(review)
    professional_access = _professional_access(review)
    if review.student_user_id != g.user.id and not professional_access:
        return jsonify({"error": "Revisão não encontrada."}), 404
    return jsonify({"review": review.to_dict(include_private=True)}), 200


@review_bp.route("/plan-reviews/<uuid:review_id>/cancel", methods=["POST"])
@login_required
def cancel_review(review_id):
    review = ProfessionalReviewRequest.query.filter_by(id=review_id, student_user_id=g.user.id).with_for_update().first_or_404()
    if review.status not in ACTIVE_STATUSES:
        return jsonify({"error": "Esta revisão não pode mais ser cancelada."}), 409
    review.status = "cancelled"
    review.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Revisão cancelada."}), 200


@review_bp.route("/professional/plan-reviews", methods=["GET"])
@login_required
def professional_reviews():
    if not g.user.has_entitlement("professional"):
        return jsonify({"error": "Acesso profissional necessário."}), 403
    ProfessionalReviewRequest.query.filter(
        ProfessionalReviewRequest.status == "pending",
        ProfessionalReviewRequest.expires_at <= datetime.utcnow(),
        or_(
            ProfessionalReviewRequest.assigned_professional_user_id == g.user.id,
            ProfessionalReviewRequest.requested_professional_user_id == g.user.id,
        ),
    ).update({"status": "expired", "resolved_at": datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    query = ProfessionalReviewRequest.query.filter(or_(
        ProfessionalReviewRequest.assigned_professional_user_id == g.user.id,
        ProfessionalReviewRequest.requested_professional_user_id == g.user.id,
    )).order_by(ProfessionalReviewRequest.created_at.desc())
    query, limit, offset = page_query(query, default_limit=30)
    return jsonify({"items": [item.to_dict() for item in query.all()], "limit": limit, "offset": offset}), 200


@review_bp.route("/professional/plan-reviews/open", methods=["GET"])
@login_required
def open_reviews():
    scopes = [scope for scope in ("workout", "diet") if g.user.has_entitlement(scope) and _accepts_external(g.user, scope)]
    if not scopes:
        return jsonify({"items": []}), 200
    reviews = ProfessionalReviewRequest.query.filter(
        ProfessionalReviewRequest.target_mode == "open",
        ProfessionalReviewRequest.status == "pending",
        ProfessionalReviewRequest.plan_type.in_(scopes),
        ProfessionalReviewRequest.student_user_id != g.user.id,
        ProfessionalReviewRequest.expires_at > datetime.utcnow(),
    ).order_by(ProfessionalReviewRequest.created_at.asc()).limit(100).all()
    return jsonify({"items": [{
        "id": item.id,
        "plan_type": item.plan_type,
        "review_focus": item.review_focus,
        "context": {key: value for key, value in (item.context_snapshot or {}).items() if key not in {"limitations", "allergies", "intolerances"}},
        "created_at": item.created_at.isoformat(),
        "expires_at": item.expires_at.isoformat(),
    } for item in reviews]}), 200


def _professional_review(review_id, required_status=None):
    query = ProfessionalReviewRequest.query.filter_by(id=review_id).with_for_update()
    review = query.first()
    if not review or (required_status and review.status != required_status):
        return None
    return review


@review_bp.route("/professional/plan-reviews/<uuid:review_id>/accept", methods=["POST"])
@login_required
def accept_review(review_id):
    review = _professional_review(review_id, "pending")
    if not review or review.student_user_id == g.user.id or not g.user.has_entitlement(_scope(review.plan_type)):
        return jsonify({"error": "Revisão não encontrada."}), 404
    if review.expires_at <= datetime.utcnow():
        review.status = "expired"
        db.session.commit()
        return jsonify({"error": "Revisão expirada."}), 409
    if review.target_mode != "open" and review.requested_professional_user_id != g.user.id:
        return jsonify({"error": "Revisão não encontrada."}), 404
    if review.target_mode != "linked" and not _accepts_external(g.user, review.plan_type):
        return jsonify({"error": "Ative revisões avulsas no seu perfil."}), 409
    review.assigned_professional_user_id = g.user.id
    review.status = "accepted"
    review.accepted_at = datetime.utcnow()
    add_audit(g.user, review.student, review.relationship, "plan_review.accepted", "professional_review", review.id)
    db.session.commit()
    return jsonify({"message": "Revisão aceita.", "review": review.to_dict(include_private=True)}), 200


@review_bp.route("/professional/plan-reviews/<uuid:review_id>/decline", methods=["POST"])
@login_required
def decline_review(review_id):
    review = _professional_review(review_id, "pending")
    if not review or review.requested_professional_user_id != g.user.id:
        return jsonify({"error": "Revisão não encontrada."}), 404
    review.status = "declined"
    review.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Revisão recusada."}), 200


@review_bp.route("/professional/plan-reviews/<uuid:review_id>/start", methods=["POST"])
@login_required
def start_review(review_id):
    review = _professional_review(review_id, "accepted")
    if not review or review.assigned_professional_user_id != g.user.id or not g.user.has_entitlement(_scope(review.plan_type)):
        return jsonify({"error": "Revisão não encontrada."}), 404
    review.status = "in_review"
    review.started_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Revisão iniciada.", "review": review.to_dict(include_private=True)}), 200


@review_bp.route("/professional/plan-reviews/<uuid:review_id>/proposal", methods=["PUT"])
@login_required
def update_review_proposal(review_id):
    review = _professional_review(review_id, "in_review")
    if not review or review.assigned_professional_user_id != g.user.id or not g.user.has_entitlement(_scope(review.plan_type)):
        return jsonify({"error": "Revisão não encontrada."}), 404
    data = json_body()
    try:
        if review.plan_type == "workout":
            questionnaire = validate_workout_questionnaire(data.get("questionnaire") or {})
            plan_data = normalize_manual_workout(data.get("plan") or {}, questionnaire)
            proposal = review.proposal_workout_plan or clone_plan_for_review(review.source_workout_plan, review.student, g.user)
            update_workout_draft(proposal, questionnaire, plan_data)
            review.proposal_workout_plan = proposal
        else:
            questionnaire = validate_diet_questionnaire(data.get("questionnaire") or {})
            plan_data = normalize_manual_diet(data.get("plan") or {}, questionnaire)
            proposal = review.proposal_diet_plan or clone_plan_for_review(review.source_diet_plan, review.student, g.user)
            context = proposal.generation_context or {}
            update_diet_draft(
                proposal,
                questionnaire,
                context.get("nutrition_targets") or {},
                plan_data,
                context.get("profile_snapshot") or profile_snapshot(review.student.profile),
            )
            review.proposal_diet_plan = proposal
    except PlanValidationError as error:
        return jsonify({"error": "Revise a proposta.", "fields": error.errors}), 400
    db.session.commit()
    return jsonify({"message": "Proposta salva.", "review": review.to_dict(include_private=True)}), 200


@review_bp.route("/professional/plan-reviews/<uuid:review_id>/complete", methods=["POST"])
@login_required
def complete_review(review_id):
    review = _professional_review(review_id, "in_review")
    if not review or review.assigned_professional_user_id != g.user.id or not g.user.has_entitlement(_scope(review.plan_type)):
        return jsonify({"error": "Revisão não encontrada."}), 404
    data = json_body()
    evaluation = str(data.get("evaluation", "")).strip()
    outcome = str(data.get("outcome", ""))
    suggestions = data.get("suggestions") or []
    if not 20 <= len(evaluation) <= 5000 or outcome not in {"approved_as_is", "changes_proposed"}:
        return jsonify({"error": "Informe uma avaliação e um resultado válidos."}), 400
    if not isinstance(suggestions, list) or len(suggestions) > 20 or any(not 2 <= len(str(item).strip()) <= 500 for item in suggestions):
        return jsonify({"error": "Sugestões inválidas."}), 400
    proposal = review.proposal_workout_plan if review.plan_type == "workout" else review.proposal_diet_plan
    if outcome == "changes_proposed" and proposal is None:
        return jsonify({"error": "Salve a proposta alterada antes de concluir."}), 409
    source = review.source_workout_plan if review.plan_type == "workout" else review.source_diet_plan
    if not source or snapshot_fingerprint(plan_snapshot(source)) != review.source_fingerprint:
        return jsonify({"error": "O plano original mudou. Solicite uma nova revisão."}), 409
    review.evaluation = evaluation
    review.suggestions = [str(item).strip() for item in suggestions]
    review.outcome = outcome
    review.proposal_fingerprint = snapshot_fingerprint(plan_snapshot(proposal)) if proposal else None
    review.status = "completed"
    review.completed_at = datetime.utcnow()
    add_audit(g.user, review.student, review.relationship, "plan_review.completed", "professional_review", review.id, {"outcome": outcome})
    db.session.commit()
    return jsonify({"message": "Revisão concluída.", "review": review.to_dict(include_private=True)}), 200


@review_bp.route("/plan-reviews/<uuid:review_id>/decision", methods=["POST"])
@login_required
def decide_review(review_id):
    review = ProfessionalReviewRequest.query.filter_by(id=review_id, student_user_id=g.user.id, status="completed").with_for_update().first_or_404()
    if review.student_decision != "pending":
        return jsonify({"error": "Esta revisão já foi respondida."}), 409
    data = json_body()
    decision = str(data.get("decision", ""))
    if decision == "reject":
        review.student_decision = "rejected"
        review.resolved_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Proposta mantida apenas no histórico."}), 200
    if decision != "apply":
        return jsonify({"error": "Decisão inválida."}), 400
    if review.outcome == "approved_as_is":
        source = review.source_workout_plan if review.plan_type == "workout" else review.source_diet_plan
        if not source or source.status != "published" or snapshot_fingerprint(plan_snapshot(source)) != review.source_fingerprint:
            return jsonify({"error": "O plano mudou depois da revisão."}), 409
    if review.outcome == "changes_proposed":
        proposal = review.proposal_workout_plan if review.plan_type == "workout" else review.proposal_diet_plan
        source = review.source_workout_plan if review.plan_type == "workout" else review.source_diet_plan
        if not source or source.status != "published" or snapshot_fingerprint(plan_snapshot(source)) != review.source_fingerprint:
            return jsonify({"error": "O plano original mudou depois da revisão."}), 409
        if (
            not proposal
            or proposal.status != "draft"
            or snapshot_fingerprint(plan_snapshot(proposal)) != review.proposal_fingerprint
        ):
            return jsonify({"error": "Proposta indisponível."}), 409
        profile = _get_or_create_profile(g.user.id)
        if review.plan_type == "workout":
            if WorkoutSession.query.filter_by(user_id=g.user.id, completed_at=None).first():
                return jsonify({"error": "Finalize o treino em andamento antes de aplicar a revisão."}), 409
            weekdays = data.get("weekdays") or []
            try:
                weekdays = [int(day) for day in weekdays]
            except (TypeError, ValueError):
                weekdays = []
            if len(weekdays) != len(proposal.days) or len(set(weekdays)) != len(weekdays) or any(day < 0 or day > 6 for day in weekdays):
                return jsonify({"error": "Escolha um dia da semana para cada treino."}), 400
            timezone_name = profile.timezone or user_timezone(g.user.id) or "UTC"
            publish_plan(proposal, review.assigned_professional, g.user, review.relationship, "workout_plan")
            _apply_workout_plan_schedule(
                profile,
                proposal,
                weekdays,
                timezone_name,
                _local_date_for_timezone(timezone_name),
            )
        else:
            publish_plan(proposal, review.assigned_professional, g.user, review.relationship, "diet_plan")
            if profile.current_diet_plan_id == source.id:
                profile.current_diet_plan_id = proposal.id
    review.student_decision = "applied"
    review.resolved_at = datetime.utcnow()
    add_audit(g.user, g.user, review.relationship, "plan_review.applied", "professional_review", review.id)
    db.session.commit()
    return jsonify({"message": "Revisão aplicada.", "review": review.to_dict(include_private=True)}), 200


@review_bp.route("/workout_plans/<int:plan_id>/professional-review", methods=["GET"])
@login_required
def workout_review_badge(plan_id):
    plan = WorkoutPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    return jsonify({"professional_review": professional_review_for_plan(plan)}), 200


@review_bp.route("/diet_plans/<int:plan_id>/professional-review", methods=["GET"])
@login_required
def diet_review_badge(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    return jsonify({"professional_review": professional_review_for_plan(plan)}), 200
