import time
from datetime import datetime

from flask import Blueprint, current_app, g, jsonify, session
from sqlalchemy import or_

from src.legal import (
    AI_CONSENT_VERSION,
    legal_versions_payload,
    record_consent,
)
from src.models.user import (
    AdminActionAudit,
    AnalyticsEvent,
    BillingCheckout,
    DelegatedActionAudit,
    DietPlan,
    ProfessionalApplication,
    ProfessionalStudentRelationship,
    Subscription,
    User,
    WorkoutPlan,
    db,
)
from src.routes.common import json_body, login_required
from src.services.asaas import AsaasError, get_subscription
from src.services.media_storage import MediaStorageError, delete_avatar


account_bp = Blueprint("account", __name__)


def _consent_payload(user):
    return {
        "versions": legal_versions_payload(),
        "ai": {
            "accepted": user.has_current_ai_consent(),
            "version": user.ai_consent_version,
            "accepted_at": user.ai_consent_at.isoformat() if user.ai_consent_at else None,
        },
    }


@account_bp.route("/account/consents", methods=["GET"])
@login_required
def get_consents():
    return jsonify(_consent_payload(g.user)), 200


@account_bp.route("/account/consents", methods=["PUT"])
@login_required
def update_consents():
    data = json_body()
    if "ai_consent" in data:
        if not isinstance(data["ai_consent"], bool):
            return jsonify({"error": "Consentimento de IA inválido."}), 400
        record_consent(
            g.user,
            "ai",
            AI_CONSENT_VERSION,
            data["ai_consent"],
            "account_settings",
        )

    db.session.commit()
    return jsonify({"message": "Preferências de privacidade atualizadas.", **_consent_payload(g.user)}), 200


def _subscription_block(user):
    for subscription in sorted(user.subscriptions, key=lambda item: item.created_at or datetime.min, reverse=True):
        local_active = subscription.status in {"active", "trialing"}
        if subscription.provider == "asaas" and subscription.external_subscription_id:
            if current_app.config.get("ASAAS_API_KEY"):
                try:
                    remote = get_subscription(subscription.external_subscription_id)
                except AsaasError as error:
                    if error.status_code == 404:
                        subscription.status = "canceled"
                        continue
                    return jsonify({
                        "error": "Não foi possível confirmar o cancelamento no Asaas. Tente novamente mais tarde.",
                        "code": "subscription_status_unavailable",
                    }), 503
                remote_status = str(remote.get("status", "")).upper()
                if remote_status not in {"INACTIVE", "EXPIRED"}:
                    return jsonify({
                        "error": "Cancele a assinatura no perfil antes de excluir a conta.",
                        "code": "active_subscription",
                    }), 409
                subscription.status = "canceled"
                continue
            if local_active:
                return jsonify({
                    "error": "Cancele a assinatura no perfil antes de excluir a conta.",
                    "code": "active_subscription",
                }), 409
        elif local_active:
            return jsonify({
                "error": "Cancele a assinatura no provedor antes de excluir a conta.",
                "code": "active_subscription",
            }), 409
    return None


def _detach_account_attribution(user):
    user_id = user.id
    now = datetime.utcnow()

    for model in (WorkoutPlan, DietPlan):
        model.query.filter(
            model.author_user_id == user_id,
            model.user_id != user_id,
        ).update({model.author_user_id: model.user_id}, synchronize_session=False)
        model.query.filter(
            model.published_by_user_id == user_id,
            model.user_id != user_id,
        ).update({model.published_by_user_id: model.user_id}, synchronize_session=False)

        owned_ids = [item_id for item_id, in db.session.query(model.id).filter(model.user_id == user_id)]
        if owned_ids:
            model.query.filter(model.supersedes_plan_id.in_(owned_ids)).update(
                {model.supersedes_plan_id: None}, synchronize_session=False
            )

    relationships = ProfessionalStudentRelationship.query.filter(or_(
        ProfessionalStudentRelationship.professional_user_id == user_id,
        ProfessionalStudentRelationship.student_user_id == user_id,
    )).all()
    for relationship in relationships:
        if relationship.status in {"active", "pending"}:
            relationship.status = "revoked"
            relationship.revoked_at = now
        if relationship.professional_user_id == user_id:
            relationship.professional_user_id = None
        if relationship.student_user_id == user_id:
            relationship.student_user_id = None
        if relationship.revoked_by_user_id == user_id:
            relationship.revoked_by_user_id = None

    ProfessionalStudentRelationship.query.filter_by(revoked_by_user_id=user_id).update(
        {ProfessionalStudentRelationship.revoked_by_user_id: None}, synchronize_session=False
    )
    ProfessionalStudentRelationship.query.filter_by(initiated_by_user_id=user_id).update(
        {ProfessionalStudentRelationship.initiated_by_user_id: None}, synchronize_session=False
    )
    DelegatedActionAudit.query.filter_by(actor_user_id=user_id).update(
        {DelegatedActionAudit.actor_user_id: None}, synchronize_session=False
    )
    DelegatedActionAudit.query.filter_by(subject_user_id=user_id).update(
        {DelegatedActionAudit.subject_user_id: None}, synchronize_session=False
    )
    AdminActionAudit.query.filter_by(actor_user_id=user_id).update(
        {AdminActionAudit.actor_user_id: None}, synchronize_session=False
    )
    AdminActionAudit.query.filter_by(subject_user_id=user_id).update(
        {AdminActionAudit.subject_user_id: None}, synchronize_session=False
    )
    AdminActionAudit.query.filter_by(
        resource_type="user", resource_id=str(user_id)
    ).update({AdminActionAudit.resource_id: None}, synchronize_session=False)
    ProfessionalApplication.query.filter_by(reviewed_by_user_id=user_id).update(
        {ProfessionalApplication.reviewed_by_user_id: None}, synchronize_session=False
    )
    AnalyticsEvent.query.filter_by(subject_id=user.analytics_subject_id).update(
        {
            AnalyticsEvent.subject_id: None,
            AnalyticsEvent.anonymous_id: None,
            AnalyticsEvent.dedupe_key: None,
        },
        synchronize_session=False,
    )
    Subscription.query.filter_by(user_id=user_id).update(
        {Subscription.user_id: None}, synchronize_session=False
    )
    BillingCheckout.query.filter_by(user_id=user_id).update(
        {BillingCheckout.user_id: None}, synchronize_session=False
    )

    if user.profile:
        user.profile.current_diet_plan_id = None
        user.profile.current_workout_plan_id = None
        user.profile.pending_workout_plan_id = None


@account_bp.route("/account", methods=["DELETE"])
@login_required
def delete_account():
    data = json_body()
    if data.get("username") != g.user.username or data.get("confirm_delete") is not True:
        return jsonify({
            "error": "Confirme exatamente seu nome de usuário e a exclusão definitiva.",
            "code": "confirmation_required",
        }), 400

    if g.user.password_hash:
        if not g.user.check_password(data.get("password")):
            return jsonify({"error": "Senha inválida.", "code": "invalid_password"}), 403
    elif not g.user.oauth_identities:
        return jsonify({"error": "A conta não possui método de reautenticação válido."}), 409
    elif int(time.time()) - int(session.get("authenticated_at", 0)) > 600:
        return jsonify({
            "error": "Entre novamente com Google antes de excluir a conta.",
            "code": "reauthentication_required",
        }), 403

    if g.user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        return jsonify({"error": "Transfira o acesso antes de excluir o último administrador."}), 409

    blocked = _subscription_block(g.user)
    if blocked:
        return blocked

    user = g.user
    avatar_key = user.profile.avatar_object_key if user.profile else None
    try:
        delete_avatar(avatar_key)
    except MediaStorageError as error:
        return jsonify({"error": str(error)}), 503
    _detach_account_attribution(user)
    db.session.flush()
    db.session.delete(user)
    db.session.commit()
    session.clear()
    return jsonify({"message": "Conta excluída definitivamente."}), 200
