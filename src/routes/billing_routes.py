from datetime import datetime
import hmac

from flask import Blueprint, current_app, g, jsonify, request

from src.models.user import BillingCheckout, BillingEvent, ProfessionalApplication, Subscription, User, db
from src.routes.common import admin_required, json_body, login_required, page_query
from src.services.asaas import (
    AsaasError,
    create_recurring_checkout,
    delete_subscription,
    get_subscription as fetch_asaas_subscription,
    parse_payment_period,
    period_end_from_subscription,
)


billing_bp = Blueprint("billing", __name__)

PLANS = (
    {"code": "free", "name": "Gratuito", "price_brl": 0, "features": ["Diário alimentar", "Medidas e progresso", "3 usos da IA"]},
    {"code": "premium_student", "name": "Premium Aluno", "price_brl": 20, "features": ["IA sem limite de teste", "Dietas personalizadas", "Treinos personalizados"]},
    {"code": "professional_single", "name": "Profissional Especialista", "price_brl": 50, "student_limit": 5, "features": ["Até 5 alunos", "Escolha entre dietas ou treinos", "Aprovação obrigatória"]},
    {"code": "professional_complete", "name": "Profissional Completo", "price_brl": 70, "student_limit": 5, "features": ["Até 5 alunos", "Dietas e treinos", "Aprovação obrigatória"]},
)

PAID_PLAN_CODES = {"premium_student", "professional_single", "professional_complete"}
PROFESSIONAL_PLAN_SCOPES = {
    "professional_single": {"personal_trainer": "workout", "nutritionist": "diet"},
    "professional_complete": {"personal_trainer": "both", "nutritionist": "both"},
}
PROFESSION_LABELS = {"personal_trainer": "Personal trainer (CREF)", "nutritionist": "Nutricionista (CRN)"}


def _plan_or_none(plan_code):
    return next((plan for plan in PLANS if plan["code"] == plan_code), None)


def _professional_application_for(user_id):
    return ProfessionalApplication.query.filter_by(user_id=user_id).order_by(
        ProfessionalApplication.created_at.desc(),
        ProfessionalApplication.id.desc(),
    ).first()


def _scope_for_application(application):
    mapping = PROFESSIONAL_PLAN_SCOPES.get(application.plan_code, {})
    return mapping.get(application.profession)


@billing_bp.route("/plans", methods=["GET"])
def get_plans():
    return jsonify({
        "currency": "BRL",
        "provider_configured": bool(current_app.config.get("ASAAS_API_KEY")),
        "plans": PLANS,
    }), 200


@billing_bp.route("/subscription", methods=["GET"])
@login_required
def get_subscription():
    subscription = g.user.active_subscription()
    return jsonify({
        "provider_configured": bool(current_app.config.get("ASAAS_API_KEY")),
        "plan_code": g.user.effective_plan_code(),
        "is_premium": g.user.has_entitlement("premium"),
        "professional_scope": g.user.professional_scope,
        "subscription": subscription.to_dict() if subscription else None,
    }), 200


@billing_bp.route("/billing/checkout", methods=["POST"])
@login_required
def create_billing_checkout():
    data = json_body()
    plan = _plan_or_none(str(data.get("plan_code", "")))
    payment_method = str(data.get("payment_method", "pix")).lower()
    if not plan or plan["code"] == "free":
        return jsonify({"error": "Escolha um plano válido."}), 400
    if payment_method not in {"pix", "credit_card", "boleto"}:
        return jsonify({"error": "Forma de pagamento inválida."}), 400
    if plan["code"] == "premium_student" and payment_method == "boleto":
        return jsonify({"error": "Boleto indisponível para este plano."}), 400
    if plan["code"] in PROFESSIONAL_PLAN_SCOPES:
        application = _professional_application_for(g.user.id)
        if not application or application.status != "approved" or application.plan_code != plan["code"]:
            return jsonify({"error": "A solicitação profissional precisa ser aprovada antes da contratação.", "code": "approval_required"}), 403
    if not current_app.config.get("ASAAS_API_KEY"):
        return jsonify({"error": "Cobrança indisponível no momento."}), 503

    checkout = BillingCheckout(user_id=g.user.id, provider="asaas", plan_code=plan["code"], payment_method=payment_method)
    db.session.add(checkout)
    db.session.flush()
    try:
        result = create_recurring_checkout(
            plan,
            payment_method,
            current_app.config["PUBLIC_BASE_URL"],
            f"dt-checkout-{checkout.id}",
        )
    except AsaasError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 502

    checkout.external_checkout_id = str(result["id"])[:255]
    checkout.checkout_url = result["link"]
    db.session.commit()
    return jsonify({"checkout_url": result["link"], "checkout_id": checkout.external_checkout_id}), 201


@billing_bp.route("/billing/cancel", methods=["POST"])
@login_required
def cancel_billing_subscription():
    subscription = g.user.active_subscription()
    if not subscription:
        return jsonify({"error": "Nenhuma assinatura ativa para cancelar."}), 404
    if subscription.provider == "asaas" and subscription.external_subscription_id:
        try:
            delete_subscription(subscription.external_subscription_id)
        except AsaasError:
            pass
    subscription.status = "canceled"
    db.session.commit()
    until = subscription.current_period_end.strftime("%d/%m/%Y") if subscription.current_period_end else None
    message = "Assinatura cancelada"
    if until:
        message += f". Acesso mantido até {until}."
    return jsonify({"message": message, "subscription": subscription.to_dict()}), 200


def _upsert_subscription_from_event(user_id, plan_code, remote):
    external_id = str(remote.get("id", ""))[:255]
    local = Subscription.query.filter_by(provider="asaas", external_subscription_id=external_id).first()
    if not local:
        local = Subscription(user_id=user_id, provider="asaas", plan_code=plan_code)
        db.session.add(local)
    local.external_subscription_id = external_id or None
    local.external_customer_id = remote.get("customer")
    remote_status = str(remote.get("status", "")).upper()
    if remote_status == "ACTIVE":
        local.status = "active"
        period_end = period_end_from_subscription(remote)
        if period_end:
            local.current_period_end = datetime.combine(period_end, datetime.min.time())
    elif remote_status in {"INACTIVE", "EXPIRED"}:
        local.status = "canceled"
    return local


def _process_asaas_event(payload):
    event = str(payload.get("event", ""))
    if event == "SUBSCRIPTION_CREATED":
        remote = payload.get("subscription") or {}
        checkout_ref = remote.get("checkoutSession")
        origin = BillingCheckout.query.filter_by(
            provider="asaas",
            external_checkout_id=str(checkout_ref or ""),
        ).first() if checkout_ref else None
        if origin is None:
            return
        _upsert_subscription_from_event(origin.user_id, origin.plan_code, remote)
    elif event == "SUBSCRIPTION_UPDATED":
        remote = payload.get("subscription") or {}
        external_id = str(remote.get("id", ""))
        local = Subscription.query.filter_by(provider="asaas", external_subscription_id=external_id).first()
        if local:
            remote_status = str(remote.get("status", "")).upper()
            local.status = "active" if remote_status == "ACTIVE" else "canceled"
            if remote_status == "ACTIVE":
                period_end = period_end_from_subscription(remote)
                if period_end:
                    local.current_period_end = datetime.combine(period_end, datetime.min.time())
    elif event in ("SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"):
        remote = payload.get("subscription") or {}
        external_id = str(remote.get("id", ""))
        local = Subscription.query.filter_by(provider="asaas", external_subscription_id=external_id).first()
        if local:
            local.status = "canceled"
    elif event.startswith("PAYMENT_"):
        payment = payload.get("payment") or {}
        external_id = str(payment.get("subscription", ""))
        local = Subscription.query.filter_by(provider="asaas", external_subscription_id=external_id).first()
        if local:
            if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
                start, end = parse_payment_period(payment)
                local.status = "active"
                if start:
                    local.current_period_start = datetime.combine(start, datetime.min.time())
                try:
                    remote = fetch_asaas_subscription(external_id)
                    precise_end = period_end_from_subscription(remote)
                    if precise_end:
                        end = precise_end
                except AsaasError:
                    pass
                local.current_period_end = datetime.combine(end, datetime.min.time())
            elif event in ("PAYMENT_REFUNDED", "PAYMENT_CHARGEBACK_REQUESTED"):
                local.status = "canceled"
                local.current_period_end = datetime.utcnow()


@billing_bp.route("/webhooks/asaas", methods=["POST"])
def asaas_webhook():
    expected_token = current_app.config.get("ASAAS_WEBHOOK_TOKEN")
    received_token = request.headers.get("asaas-access-token", "")
    if not expected_token or not hmac.compare_digest(str(received_token), str(expected_token)):
        return jsonify({"error": "Token de webhook inválido."}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload.get("id"):
        return jsonify({"error": "Evento inválido."}), 400

    event_id = str(payload["id"])[:255]
    duplicate = BillingEvent.query.filter_by(provider="asaas", provider_event_id=event_id).first()
    if duplicate:
        return jsonify({"received": True}), 200

    db.session.add(BillingEvent(provider="asaas", provider_event_id=event_id, event_type=str(payload.get("event", ""))[:64]))
    _process_asaas_event(payload)
    db.session.commit()
    return jsonify({"received": True}), 200


@billing_bp.route("/professional-application", methods=["GET"])
@login_required
def get_my_professional_application():
    application = _professional_application_for(g.user.id)
    return jsonify({"application": application.to_dict() if application else None}), 200


@billing_bp.route("/professional-application", methods=["POST"])
@login_required
def create_professional_application():
    data = json_body()
    plan = _plan_or_none(str(data.get("plan_code", "")))
    profession = str(data.get("profession", ""))
    full_name = str(data.get("full_name", "")).strip()
    registration_number = str(data.get("registration_number", "")).strip()
    if not plan or plan["code"] not in PROFESSIONAL_PLAN_SCOPES:
        return jsonify({"error": "Escolha um plano profissional válido."}), 400
    if profession not in PROFESSION_LABELS:
        return jsonify({"error": "Informe a sua profissão."}), 400
    if not full_name or len(full_name) > 120:
        return jsonify({"error": "Informe seu nome completo (até 120 caracteres)."}), 400
    if not registration_number or len(registration_number) > 40:
        return jsonify({"error": "Informe o número do registro (CREF ou CRN)."}), 400
    existing = _professional_application_for(g.user.id)
    if existing and existing.status == "pending":
        return jsonify({"error": "Você já possui uma solicitação em análise."}), 409
    application = ProfessionalApplication(
        user_id=g.user.id,
        plan_code=plan["code"],
        full_name=full_name,
        profession=profession,
        registration_number=registration_number,
    )
    db.session.add(application)
    db.session.commit()
    return jsonify({"message": "Solicitação enviada para análise.", "application": application.to_dict()}), 201


@billing_bp.route("/admin/professional-applications", methods=["GET"])
@admin_required
def list_professional_applications():
    status_filter = request.args.get("status")
    query = ProfessionalApplication.query.order_by(ProfessionalApplication.created_at.desc())
    if status_filter in {"pending", "approved", "rejected"}:
        query = query.filter_by(status=status_filter)
    applications, _, _ = page_query(query, default_limit=50)
    return jsonify([item.to_dict() for item in applications.all()]), 200


@billing_bp.route("/admin/professional-applications/<int:application_id>/review", methods=["POST"])
@admin_required
def review_professional_application(application_id):
    data = json_body()
    decision = str(data.get("decision", ""))
    note = str(data.get("note", "")).strip()[:500] or None
    application = db.get_or_404(ProfessionalApplication, application_id)
    if application.status != "pending":
        return jsonify({"error": "Esta solicitação já foi analisada."}), 409
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "Decisão inválida."}), 400
    application.reviewed_by_user_id = g.user.id
    application.reviewed_at = datetime.utcnow()
    application.admin_note = note
    if decision == "approve":
        scope = _scope_for_application(application)
        if not scope:
            return jsonify({"error": "Combinação de plano e profissão inválida."}), 422
        applicant = db.session.get(User, application.user_id)
        applicant.is_professional = True
        applicant.professional_scope = scope
        application.status = "approved"
        message = f"Solicitação aprovada. Especialidade: {scope}."
    else:
        application.status = "rejected"
        message = "Solicitação recusada."
    db.session.commit()
    return jsonify({"message": message, "application": application.to_dict()}), 200
