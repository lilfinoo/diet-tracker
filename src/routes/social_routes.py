from datetime import datetime, timedelta
from io import BytesIO

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.legal import PROFESSIONAL_SHARING_VERSION
from src.models.user import ProfessionalStudentRelationship, User, UserProfile, db
from src.routes.common import json_body, login_required, page_query
from src.services.badges import serialize_profile_highlights
from src.services.media_storage import (
    MediaStorageError,
    delete_avatar,
    get_avatar,
    prepare_avatar,
    upload_avatar,
)
from src.services.plan_management import add_audit
from src.services.rate_limit import rate_limit


social_bp = Blueprint("social", __name__)


def _profile_for(user):
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.session.add(profile)
    return profile


def _public_user(user):
    profile = user.profile
    highlights = []
    for highlight in serialize_profile_highlights(user.profile_highlights):
        item = highlight.get("item") or {}
        public_item = {
            key: item.get(key)
            for key in (
                "code", "title", "description", "badge_rank", "exercise_name",
                "metric_type", "new_value", "load_kg", "repetitions", "achieved_at",
            )
            if item.get(key) is not None
        }
        highlights.append({
            "position": highlight["position"],
            "target_kind": highlight["target_kind"],
            "item": public_item,
        })
    return {
        "id": user.id,
        "username": user.username,
        "is_professional": user.has_entitlement("professional"),
        "professional_scope": user.professional_scope if user.has_entitlement("professional") else None,
        "accepts_external_workout_reviews": bool(
            profile and profile.accepts_external_workout_reviews and user.has_entitlement("workout")
        ),
        "accepts_external_diet_reviews": bool(
            profile and profile.accepts_external_diet_reviews and user.has_entitlement("diet")
        ),
        "avatar_url": f"/api/profiles/by-id/{user.id}/avatar" if profile and profile.avatar_object_key else None,
        "profile_highlights": highlights,
    }


def _visible_profile(username):
    user = User.query.filter_by(username=username, is_banned=False).first()
    if not user or not user.profile or (not user.profile.is_public and user.id != g.user.id):
        return None
    return user


@social_bp.route("/profiles/search", methods=["GET"])
@login_required
@rate_limit("profile_search", 30, 60)
def search_profiles():
    query_text = str(request.args.get("q", "")).strip()
    if len(query_text) < 2:
        return jsonify({"error": "Digite ao menos 2 caracteres."}), 400
    query = (
        User.query.join(UserProfile)
        .filter(
            UserProfile.is_public.is_(True),
            User.is_banned.is_(False),
            User.username.contains(query_text, autoescape=True),
        )
        .order_by(User.username.asc())
    )
    query, limit, offset = page_query(query, default_limit=20)
    return jsonify({
        "items": [_public_user(user) for user in query.all()],
        "limit": limit,
        "offset": offset,
    }), 200


@social_bp.route("/profiles/<username>", methods=["GET"])
@login_required
def public_profile(username):
    user = _visible_profile(username)
    if not user:
        return jsonify({"error": "Perfil não encontrado."}), 404
    return jsonify({"profile": _public_user(user)}), 200


@social_bp.route("/profile/public", methods=["PUT"])
@login_required
def update_public_profile():
    data = json_body()
    profile = _profile_for(g.user)
    if "is_public" in data:
        if not isinstance(data["is_public"], bool):
            return jsonify({"error": "Visibilidade inválida."}), 400
        profile.is_public = data["is_public"]
    if "accepts_external_workout_reviews" in data:
        if not isinstance(data["accepts_external_workout_reviews"], bool):
            return jsonify({"error": "Preferência de revisão inválida."}), 400
        if data["accepts_external_workout_reviews"] and not g.user.has_entitlement("workout"):
            return jsonify({"error": "Somente profissionais habilitados para treino podem receber revisões."}), 403
        profile.accepts_external_workout_reviews = data["accepts_external_workout_reviews"]
    if "accepts_external_diet_reviews" in data:
        if not isinstance(data["accepts_external_diet_reviews"], bool):
            return jsonify({"error": "Preferência de revisão inválida."}), 400
        if data["accepts_external_diet_reviews"] and not g.user.has_entitlement("diet"):
            return jsonify({"error": "Somente profissionais habilitados para dieta podem receber revisões."}), 403
        profile.accepts_external_diet_reviews = data["accepts_external_diet_reviews"]
    db.session.commit()
    return jsonify({"message": "Perfil público atualizado.", "profile": profile.to_dict()}), 200


@social_bp.route("/profile/avatar", methods=["POST", "DELETE"])
@login_required
@rate_limit("avatar", 10, 3600)
def own_avatar():
    profile = _profile_for(g.user)
    old_key = profile.avatar_object_key
    if request.method == "DELETE":
        try:
            delete_avatar(old_key)
        except MediaStorageError as error:
            return jsonify({"error": str(error)}), 503
        profile.avatar_object_key = None
        profile.avatar_updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Foto removida.", "avatar_url": None}), 200

    image = request.files.get("photo")
    if image is None:
        return jsonify({"error": "Selecione uma foto."}), 400
    try:
        content = prepare_avatar(image.stream)
    except MediaStorageError as error:
        return jsonify({"error": str(error)}), 400
    try:
        key = upload_avatar(g.user.id, content)
        delete_avatar(old_key)
    except MediaStorageError as error:
        if "key" in locals():
            try:
                delete_avatar(key)
            except MediaStorageError:
                pass
        return jsonify({"error": str(error)}), 503
    profile.avatar_object_key = key
    profile.avatar_updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        try:
            delete_avatar(key)
        except MediaStorageError:
            pass
        profile = UserProfile.query.filter_by(user_id=g.user.id).first()
        if profile and profile.avatar_object_key == old_key:
            profile.avatar_object_key = None
            profile.avatar_updated_at = datetime.utcnow()
            db.session.commit()
        return jsonify({"error": "Não foi possível atualizar a foto agora."}), 503
    return jsonify({
        "message": "Foto atualizada.",
        "avatar_url": f"/api/profiles/by-id/{g.user.id}/avatar?v={int(profile.avatar_updated_at.timestamp())}",
    }), 200


@social_bp.route("/profiles/<username>/avatar", methods=["GET"])
@social_bp.route("/profiles/by-id/<uuid:user_id>/avatar", methods=["GET"])
@login_required
def profile_avatar(username=None, user_id=None):
    query = User.query.filter_by(is_banned=False)
    user = query.filter_by(id=user_id).first() if user_id else query.filter_by(username=username).first()
    if not user or not user.profile or not user.profile.avatar_object_key:
        return jsonify({"error": "Foto não encontrada."}), 404
    allowed = user.id == g.user.id or user.profile.is_public
    if not allowed:
        allowed = ProfessionalStudentRelationship.query.filter(
            ProfessionalStudentRelationship.status == "active",
            ProfessionalStudentRelationship.data_sharing_consent_version == PROFESSIONAL_SHARING_VERSION,
            ProfessionalStudentRelationship.data_sharing_consented_at.isnot(None),
            or_(
                and_(
                    ProfessionalStudentRelationship.professional_user_id == user.id,
                    ProfessionalStudentRelationship.student_user_id == g.user.id,
                ),
                and_(
                    ProfessionalStudentRelationship.professional_user_id == g.user.id,
                    ProfessionalStudentRelationship.student_user_id == user.id,
                ),
            ),
        ).first() is not None
    if not allowed:
        return jsonify({"error": "Foto não encontrada."}), 404
    try:
        content = get_avatar(user.profile.avatar_object_key)
    except MediaStorageError:
        return jsonify({"error": "Foto não encontrada."}), 404
    response = send_file(BytesIO(content), mimetype="image/webp", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@social_bp.route("/connections", methods=["GET", "POST"])
@login_required
@rate_limit("connections", 30, 60)
def connections():
    if request.method == "GET":
        ProfessionalStudentRelationship.query.filter(
            ProfessionalStudentRelationship.status == "pending",
            ProfessionalStudentRelationship.invite_expires_at <= datetime.utcnow(),
            or_(
                ProfessionalStudentRelationship.professional_user_id == g.user.id,
                ProfessionalStudentRelationship.student_user_id == g.user.id,
            ),
        ).update({"status": "expired"}, synchronize_session=False)
        db.session.commit()
        items = ProfessionalStudentRelationship.query.filter(
            ProfessionalStudentRelationship.student_user_id.isnot(None),
            or_(
                ProfessionalStudentRelationship.professional_user_id == g.user.id,
                ProfessionalStudentRelationship.student_user_id == g.user.id,
            ),
        ).order_by(ProfessionalStudentRelationship.created_at.desc()).all()
        return jsonify({"items": [item.to_dict() for item in items]}), 200

    data = json_body()
    target = User.query.filter_by(username=str(data.get("username", "")).strip(), is_banned=False).first()
    direction = str(data.get("direction", ""))
    if not target or target.id == g.user.id or not target.profile or not target.profile.is_public:
        return jsonify({"error": "Usuário não encontrado."}), 404
    if direction == "request_professional":
        professional, student = target, g.user
        if not professional.has_entitlement("professional"):
            return jsonify({"error": "Este usuário não é um profissional disponível."}), 400
        if data.get("data_sharing_consent") is not True:
            return jsonify({"error": "Confirme o compartilhamento de dados."}), 400
        if data.get("sharing_consent_version") != PROFESSIONAL_SHARING_VERSION:
            return jsonify({"error": "Atualize e confirme o consentimento de compartilhamento."}), 409
    elif direction == "invite_student":
        professional, student = g.user, target
        if not professional.has_entitlement("professional"):
            return jsonify({"error": "Apenas profissionais podem convidar alunos."}), 403
    else:
        return jsonify({"error": "Tipo de solicitação inválido."}), 400
    if ProfessionalStudentRelationship.query.filter_by(
        professional_user_id=professional.id,
        status="active",
    ).count() >= 5:
        return jsonify({"error": "Este profissional já atingiu o limite de 5 alunos."}), 409
    existing = ProfessionalStudentRelationship.query.filter(
        ProfessionalStudentRelationship.professional_user_id == professional.id,
        ProfessionalStudentRelationship.student_user_id == student.id,
        ProfessionalStudentRelationship.status.in_(("pending", "active")),
    ).first()
    if existing:
        return jsonify({"error": "Já existe uma solicitação ou vínculo entre vocês."}), 409
    relationship = ProfessionalStudentRelationship(
        professional_user_id=professional.id,
        student_user_id=student.id,
        status="pending",
        invite_expires_at=datetime.utcnow() + timedelta(days=7),
        initiated_by_user_id=g.user.id,
        request_message=str(data.get("message", "")).strip()[:500] or None,
    )
    if student.id == g.user.id:
        relationship.data_sharing_consent_version = PROFESSIONAL_SHARING_VERSION
        relationship.data_sharing_consented_at = datetime.utcnow()
    db.session.add(relationship)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Já existe uma solicitação ou vínculo entre vocês."}), 409
    return jsonify({"message": "Solicitação enviada.", "connection": relationship.to_dict()}), 201


def _pending_connection(connection_id):
    return ProfessionalStudentRelationship.query.filter_by(id=connection_id, status="pending").with_for_update().first()


@social_bp.route("/connections/<int:connection_id>/accept", methods=["POST"])
@login_required
def accept_connection(connection_id):
    data = json_body()
    relationship = _pending_connection(connection_id)
    if not relationship or relationship.initiated_by_user_id == g.user.id or g.user.id not in {
        relationship.professional_user_id,
        relationship.student_user_id,
    }:
        return jsonify({"error": "Solicitação não encontrada."}), 404
    if relationship.invite_expires_at <= datetime.utcnow():
        relationship.status = "expired"
        db.session.commit()
        return jsonify({"error": "Solicitação expirada."}), 409
    if not relationship.professional or not relationship.professional.has_entitlement("professional"):
        return jsonify({"error": "Profissional indisponível."}), 409
    if g.user.id == relationship.student_user_id:
        if data.get("data_sharing_consent") is not True:
            return jsonify({"error": "Confirme o compartilhamento de dados."}), 400
        if data.get("sharing_consent_version") != PROFESSIONAL_SHARING_VERSION:
            return jsonify({"error": "Atualize e confirme o consentimento de compartilhamento."}), 409
        relationship.data_sharing_consent_version = PROFESSIONAL_SHARING_VERSION
        relationship.data_sharing_consented_at = datetime.utcnow()
    if (
        not relationship.data_sharing_consented_at
        or relationship.data_sharing_consent_version != PROFESSIONAL_SHARING_VERSION
    ):
        return jsonify({"error": "O aluno precisa autorizar o compartilhamento de dados."}), 409
    if ProfessionalStudentRelationship.query.filter_by(
        student_user_id=relationship.student_user_id,
        status="active",
    ).first():
        return jsonify({"error": "O aluno já possui um profissional ativo."}), 409
    db.session.get(User, relationship.professional_user_id, with_for_update=True)
    active_students = ProfessionalStudentRelationship.query.filter_by(
        professional_user_id=relationship.professional_user_id,
        status="active",
    ).count()
    if active_students >= 5:
        return jsonify({"error": "Este profissional já atingiu o limite de 5 alunos."}), 409
    relationship.status = "active"
    relationship.accepted_at = datetime.utcnow()
    add_audit(
        g.user,
        relationship.student,
        relationship,
        "professional_student.request_accepted",
        "professional_student_relationship",
        relationship.id,
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Este vínculo não pode mais ser aceito."}), 409
    return jsonify({"message": "Vínculo profissional criado.", "connection": relationship.to_dict()}), 200


@social_bp.route("/connections/<int:connection_id>/decline", methods=["POST"])
@login_required
def decline_connection(connection_id):
    relationship = _pending_connection(connection_id)
    if not relationship or relationship.initiated_by_user_id == g.user.id or g.user.id not in {
        relationship.professional_user_id,
        relationship.student_user_id,
    }:
        return jsonify({"error": "Solicitação não encontrada."}), 404
    relationship.status = "declined"
    db.session.commit()
    return jsonify({"message": "Solicitação recusada."}), 200


@social_bp.route("/connections/<int:connection_id>", methods=["DELETE"])
@login_required
def cancel_connection(connection_id):
    relationship = ProfessionalStudentRelationship.query.filter_by(
        id=connection_id,
        status="pending",
        initiated_by_user_id=g.user.id,
    ).first_or_404()
    relationship.status = "revoked"
    relationship.revoked_at = datetime.utcnow()
    relationship.revoked_by_user_id = g.user.id
    db.session.commit()
    return jsonify({"message": "Solicitação cancelada."}), 200
