from datetime import datetime, timedelta
import hmac

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.models.user import AdminActionAudit, BillingCheckout, BillingEvent, ProfessionalApplication, Subscription, User, db
from src.routes.common import admin_required, json_body, login_required, page_query
from src.services.asaas import (
    AsaasError,
    create_checkout,
    delete_subscription,
    get_subscription as fetch_asaas_subscription,
    parse_payment_period,
    period_end_from_subscription,
)
from src.services.analytics import record_event


billing_bp = Blueprint("billing", __name__)
PIX_ACCESS_DAYS = 30
PIX_RENEWAL_WINDOW_DAYS = 7

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


def _billing_available():
    return bool(
        current_app.config.get("BILLING_ENABLED")
        and current_app.config.get("ASAAS_API_KEY")
    )


def _audit_billing(action, user_id, details=None, resource_id=None):
    db.session.add(AdminActionAudit(
        actor_user_id=None,
        subject_user_id=user_id,
        action=action,
        resource_type="subscription",
        resource_id=str(resource_id)[:64] if resource_id else None,
        details=details or None,
    ))


@billing_bp.route("/plans", methods=["GET"])
def get_plans():
    return jsonify({
        "currency": "BRL",
        "provider_configured": _billing_available(),
        "provider_environment": current_app.config.get("ASAAS_ENV", "sandbox"),
        "payment_methods": {
            "credit_card": {"recurring": True},
            "pix": {"recurring": False, "access_days": PIX_ACCESS_DAYS},
        },
        "plans": PLANS,
    }), 200


@billing_bp.route("/subscription", methods=["GET"])
@login_required
def get_subscription():
    subscription = g.user.active_subscription()
    pix_renewal_available_at = None
    if subscription and subscription.provider == "asaas_pix" and subscription.current_period_end:
        pix_renewal_available_at = (
            subscription.current_period_end - timedelta(days=PIX_RENEWAL_WINDOW_DAYS)
        ).isoformat()
    return jsonify({
        "provider_configured": _billing_available(),
        "plan_code": g.user.effective_plan_code(),
        "is_premium": g.user.has_entitlement("premium"),
        "professional_scope": g.user.professional_scope,
        "subscription": subscription.public_dict() if subscription else None,
        "pix_renewal_available_at": pix_renewal_available_at,
    }), 200


def _pix_renewal_allowed(subscription, plan_code, payment_method, now):
    return bool(
        payment_method == "pix"
        and subscription.provider == "asaas_pix"
        and subscription.plan_code == plan_code
        and subscription.current_period_end
        and subscription.current_period_end <= now + timedelta(days=PIX_RENEWAL_WINDOW_DAYS)
    )


@billing_bp.route("/billing/checkout", methods=["POST"])
@login_required
def create_billing_checkout():
    data = json_body()
    plan = _plan_or_none(str(data.get("plan_code", "")))
    payment_method = str(data.get("payment_method", "pix")).lower()
    if not plan or plan["code"] == "free":
        return jsonify({"error": "Escolha um plano válido."}), 400
    if payment_method not in {"pix", "credit_card"}:
        return jsonify({"error": "Forma de pagamento inválida."}), 400
    if plan["code"] in PROFESSIONAL_PLAN_SCOPES:
        application = _professional_application_for(g.user.id)
        if not application or application.status != "approved" or application.plan_code != plan["code"]:
            return jsonify({"error": "A solicitação profissional precisa ser aprovada antes da contratação.", "code": "approval_required"}), 403
    if not _billing_available():
        return jsonify({"error": "Cobrança indisponível no momento."}), 503

    now = datetime.utcnow()
    active = g.user.active_subscription()
    if active and not _pix_renewal_allowed(active, plan["code"], payment_method, now):
        renewal_available_at = None
        if active.provider == "asaas_pix" and active.current_period_end:
            renewal_available_at = (
                active.current_period_end - timedelta(days=PIX_RENEWAL_WINDOW_DAYS)
            ).isoformat()
        return jsonify({
            "error": "Você já possui uma assinatura ativa.",
            "code": "subscription_active",
            "pix_renewal_available_at": renewal_available_at,
        }), 409

    pending_subscription = Subscription.query.filter_by(
        user_id=g.user.id,
        provider="asaas",
        status="pending",
    ).first()
    if pending_subscription:
        return jsonify({
            "error": "Seu pagamento ainda está pendente de confirmação.",
            "code": "subscription_pending",
        }), 409

    open_checkout = BillingCheckout.query.filter(
        BillingCheckout.user_id == g.user.id,
        BillingCheckout.provider == "asaas",
        BillingCheckout.status.in_(("creating", "pending")),
    ).order_by(BillingCheckout.created_at.desc()).first()
    if open_checkout and (open_checkout.expires_at is None or open_checkout.expires_at <= now):
        open_checkout.status = "expired"
        db.session.commit()
        open_checkout = None
    if open_checkout and (
        open_checkout.plan_code != plan["code"]
        or open_checkout.payment_method != payment_method
    ):
        return jsonify({
            "error": "Você já possui um checkout pendente para outro plano.",
            "code": "checkout_pending",
        }), 409
    if open_checkout and open_checkout.status == "pending" and open_checkout.checkout_url:
        return jsonify({
            "checkout_url": open_checkout.checkout_url,
            "existing": True,
        }), 200

    checkout = open_checkout
    if checkout is None:
        checkout = BillingCheckout.query.filter(
            BillingCheckout.user_id == g.user.id,
            BillingCheckout.provider == "asaas",
            BillingCheckout.plan_code == plan["code"],
            BillingCheckout.payment_method == payment_method,
            BillingCheckout.status == "failed",
            BillingCheckout.expires_at > now,
        ).order_by(BillingCheckout.created_at.desc()).first()
    if checkout is None:
        checkout = BillingCheckout(
            user_id=g.user.id,
            provider="asaas",
            plan_code=plan["code"],
            payment_method=payment_method,
            expires_at=now + timedelta(days=1),
        )
        db.session.add(checkout)
    else:
        checkout.status = "creating"
    try:
        # Commit before contacting Asaas so retries and webhooks have a stable correlation row.
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        winner = BillingCheckout.query.filter(
            BillingCheckout.user_id == g.user.id,
            BillingCheckout.provider == "asaas",
            BillingCheckout.status.in_(("creating", "pending")),
        ).first()
        if winner and winner.plan_code == plan["code"] and winner.checkout_url:
            return jsonify({
                "checkout_url": winner.checkout_url,
                "existing": True,
            }), 200
        return jsonify({"error": "Checkout já está sendo criado.", "code": "checkout_in_progress"}), 409

    try:
        result = create_checkout(
            plan,
            checkout.payment_method,
            current_app.config["PUBLIC_BASE_URL"],
            checkout.external_reference,
        )
    except AsaasError as error:
        checkout.status = "failed"
        db.session.commit()
        current_app.logger.warning("Asaas checkout creation failed status=%s", error.status_code)
        return jsonify({"error": "Não foi possível iniciar o pagamento agora."}), 502

    checkout.external_checkout_id = str(result["id"])[:255]
    checkout.checkout_url = str(result["link"])[:2048]
    db.session.flush()
    BillingCheckout.query.filter(
        BillingCheckout.id == checkout.id,
        BillingCheckout.status != "completed",
    ).update({BillingCheckout.status: "pending"}, synchronize_session=False)
    record_event(
        "checkout_started",
        user_id=g.user.id,
        properties={"plan_code": plan["code"], "payment_method": checkout.payment_method},
    )
    db.session.commit()
    return jsonify({
        "checkout_url": checkout.checkout_url,
        "existing": False,
    }), 201


@billing_bp.route("/billing/cancel", methods=["POST"])
@login_required
def cancel_billing_subscription():
    now = datetime.utcnow()
    subscriptions = Subscription.query.filter(
        Subscription.user_id == g.user.id,
        Subscription.provider == "asaas",
        Subscription.status.in_(("active", "trialing", "pending")),
    ).all()
    plan_rank = {
        "free": 0,
        "premium_student": 1,
        "professional_single": 2,
        "professional_complete": 3,
    }
    subscription = max(
        subscriptions,
        key=lambda item: (
            item.status in {"active", "trialing"},
            plan_rank.get(item.plan_code, 0),
            item.created_at or datetime.min,
        ),
        default=None,
    )
    if not subscription:
        subscription = Subscription.query.filter(
            Subscription.user_id == g.user.id,
            Subscription.provider == "asaas",
            Subscription.status == "canceled",
            Subscription.current_period_end > now,
        ).order_by(Subscription.current_period_end.desc()).first()
    if not subscription:
        return jsonify({"error": "Nenhuma assinatura ativa para cancelar."}), 404
    if not subscription.external_subscription_id:
        return jsonify({"error": "Esta assinatura não pode ser cancelada pelo provedor."}), 409
    if subscription.status != "canceled":
        try:
            delete_subscription(subscription.external_subscription_id)
        except AsaasError as error:
            if error.status_code != 404:
                current_app.logger.warning(
                    "Asaas subscription cancellation failed status=%s", error.status_code
                )
                return jsonify({"error": "Não foi possível cancelar a assinatura agora."}), 502
    subscription.status = "canceled"
    _audit_billing(
        "subscription.canceled_by_user",
        g.user.id,
        {"plan_code": subscription.plan_code},
        subscription.id,
    )
    db.session.commit()
    until = subscription.current_period_end.strftime("%d/%m/%Y") if subscription.current_period_end else None
    message = "Assinatura cancelada"
    if until:
        message += f". Acesso mantido até {until}."
    return jsonify({"message": message, "subscription": subscription.public_dict()}), 200


def _upsert_subscription_from_event(user_id, plan_code, remote):
    external_id = str(remote.get("id", ""))[:255]
    if not external_id:
        return None
    local = Subscription.query.with_for_update().filter_by(
        provider="asaas", external_subscription_id=external_id
    ).first()
    if not local:
        local = Subscription(user_id=user_id, provider="asaas", plan_code=plan_code, status="pending")
        db.session.add(local)
    local.external_subscription_id = external_id or None
    if remote.get("customer"):
        local.external_customer_id = remote["customer"]
    remote_status = str(remote.get("status", "")).upper()
    if remote_status == "ACTIVE":
        if local.status not in {"active", "canceled", "revoked", "disputed"}:
            local.status = "pending"
    elif remote_status in {"INACTIVE", "EXPIRED"}:
        local.status = "canceled"
    return local


def _checkout_for_remote(remote, payload):
    checkout_reference = remote.get("checkoutSession") or payload.get("checkoutSession")
    external_reference = remote.get("externalReference") or payload.get("externalReference")
    checkout_match = BillingCheckout.query.filter_by(
        provider="asaas", external_checkout_id=str(checkout_reference)
    ).first() if checkout_reference else None
    reference_match = BillingCheckout.query.filter_by(
        provider="asaas", external_reference=str(external_reference)
    ).first() if external_reference else None
    if checkout_match and reference_match and checkout_match.id != reference_match.id:
        return None
    return checkout_match or reference_match


def _checkout_for_checkout_event(payload):
    remote = payload.get("checkout") or {}
    checkout_id = str(remote.get("id", ""))
    external_reference = str(remote.get("externalReference", ""))
    checkout_match = BillingCheckout.query.with_for_update().filter_by(
        provider="asaas", external_checkout_id=checkout_id
    ).first() if checkout_id else None
    reference_match = BillingCheckout.query.with_for_update().filter_by(
        provider="asaas", external_reference=external_reference
    ).first() if external_reference else None
    if checkout_match and reference_match and checkout_match.id != reference_match.id:
        return None
    return checkout_match or reference_match


def _activate_pix_checkout(checkout):
    if checkout.status == "completed":
        return True
    now = datetime.utcnow()
    external_id = f"pix-access-{checkout.user_id}-{checkout.plan_code}"
    access = Subscription.query.filter_by(
        provider="asaas_pix", external_subscription_id=external_id
    ).first()
    was_active = bool(
        access
        and access.status == "active"
        and access.current_period_end
        and access.current_period_end > now
    )
    base = access.current_period_end if was_active else now
    if access is None:
        access = Subscription(
            user_id=checkout.user_id,
            provider="asaas_pix",
            external_subscription_id=external_id,
            plan_code=checkout.plan_code,
            status="active",
        )
        db.session.add(access)
    access.status = "active"
    access.plan_code = checkout.plan_code
    access.current_period_start = now
    access.current_period_end = base + timedelta(days=PIX_ACCESS_DAYS)
    checkout.status = "completed"
    if not was_active:
        record_event(
            "subscription_activated",
            user_id=checkout.user_id,
            properties={"plan_code": checkout.plan_code, "provider": "asaas_pix"},
        )
        _audit_billing(
            "subscription.activated",
            checkout.user_id,
            {"plan_code": checkout.plan_code, "payment_method": "pix"},
            access.id,
        )
    return True


def _subscription_for_remote(remote, payload):
    external_id = str(remote.get("id", ""))
    local = Subscription.query.filter_by(
        provider="asaas",
        external_subscription_id=external_id,
    ).first() if external_id else None
    if local:
        return local
    origin = _checkout_for_remote(remote, payload)
    if not origin:
        return None
    local = _upsert_subscription_from_event(origin.user_id, origin.plan_code, remote)
    if local:
        origin.status = "completed"
    return local


def _activate_recurring_payment(local, payment):
    payment_id = str(payment.get("id", ""))
    if not payment_id:
        return False
    if local.last_payment_id == payment_id:
        return True
    start, _ = parse_payment_period(payment)
    if not start:
        raise ValueError("Asaas payment did not provide a period start")
    if (
        local.current_period_start
        and start < local.current_period_start.date()
    ):
        return True
    reversal = BillingEvent.query.filter(
        BillingEvent.provider == "asaas",
        BillingEvent.resource_id == payment_id,
        BillingEvent.event_type.in_((
            "PAYMENT_REFUNDED",
            "PAYMENT_DELETED",
            "PAYMENT_CHARGEBACK_REQUESTED",
        )),
    ).order_by(BillingEvent.received_at.desc()).first()
    if reversal:
        local.last_payment_id = payment_id[:255]
        local.current_period_start = datetime.combine(start, datetime.min.time())
        local.current_period_end = datetime.utcnow()
        local.status = (
            "disputed"
            if reversal.event_type == "PAYMENT_CHARGEBACK_REQUESTED"
            else "revoked"
        )
        return True
    remote = fetch_asaas_subscription(local.external_subscription_id)
    period_end = period_end_from_subscription(remote)
    if not period_end:
        raise ValueError("Asaas subscription did not provide a paid-through date")
    if period_end <= start:
        raise ValueError("Asaas payment period is invalid")
    was_entitled = local.status in {"active", "canceled"} and (
        local.current_period_end is None or local.current_period_end > datetime.utcnow()
    )
    local.current_period_start = datetime.combine(start, datetime.min.time())
    local.current_period_end = datetime.combine(period_end, datetime.min.time())
    local.last_payment_id = payment_id[:255]
    if local.status != "canceled":
        local.status = "active"
    if not was_entitled:
        record_event(
            "subscription_activated",
            user_id=local.user_id,
            properties={"plan_code": local.plan_code, "provider": "asaas"},
        )
        _audit_billing(
            "subscription.activated",
            local.user_id,
            {"plan_code": local.plan_code},
            local.id,
        )
    return True


def _process_asaas_event(payload):
    event = str(payload.get("event", ""))
    if event.startswith("CHECKOUT_"):
        checkout = _checkout_for_checkout_event(payload)
        if not checkout:
            return False
        if event == "CHECKOUT_PAID":
            if checkout.payment_method == "pix":
                return _activate_pix_checkout(checkout)
            checkout.status = "completed"
        elif event == "CHECKOUT_CANCELED":
            if checkout.status != "completed":
                checkout.status = "canceled"
        elif event == "CHECKOUT_EXPIRED":
            if checkout.status != "completed":
                checkout.status = "expired"
        return True
    if event == "SUBSCRIPTION_CREATED":
        remote = payload.get("subscription") or {}
        return _subscription_for_remote(remote, payload) is not None
    elif event == "SUBSCRIPTION_UPDATED":
        remote = payload.get("subscription") or {}
        local = _subscription_for_remote(remote, payload)
        if not local:
            return False
        _upsert_subscription_from_event(local.user_id, local.plan_code, remote)
        return True
    elif event in ("SUBSCRIPTION_INACTIVATED", "SUBSCRIPTION_DELETED"):
        remote = payload.get("subscription") or {}
        local = _subscription_for_remote(remote, payload)
        if not local:
            return False
        local.status = "canceled"
        return True
    elif event.startswith("PAYMENT_"):
        payment = payload.get("payment") or {}
        external_id = str(payment.get("subscription", ""))
        local = Subscription.query.with_for_update().filter_by(
            provider="asaas", external_subscription_id=external_id
        ).first()
        if not local:
            return False
        if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
            return _activate_recurring_payment(local, payment)
        payment_id = str(payment.get("id", ""))
        affects_current_period = bool(payment_id and payment_id == local.last_payment_id)
        if event in ("PAYMENT_OVERDUE", "PAYMENT_CREDIT_CARD_CAPTURE_REFUSED"):
            if not local.current_period_end or local.current_period_end <= datetime.utcnow():
                local.status = "past_due"
        elif event in ("PAYMENT_REFUNDED", "PAYMENT_DELETED") and affects_current_period:
            local.status = "revoked"
            local.current_period_end = datetime.utcnow()
            _audit_billing("subscription.revoked_after_payment_reversal", local.user_id, {
                "plan_code": local.plan_code,
                "event": event,
            }, local.id)
        elif event == "PAYMENT_CHARGEBACK_REQUESTED" and affects_current_period:
            local.status = "disputed"
            local.current_period_end = datetime.utcnow()
            _audit_billing("subscription.suspended_for_chargeback", local.user_id, {
                "plan_code": local.plan_code,
            }, local.id)
        elif event == "PAYMENT_PARTIALLY_REFUNDED":
            _audit_billing("subscription.partial_refund_review", local.user_id, {
                "plan_code": local.plan_code,
            }, local.id)
        return True
    return True


def _safe_webhook_payload(payload):
    event = str(payload.get("event", ""))[:64]
    safe = {"id": str(payload.get("id", "")), "event": event}
    field_map = {
        "checkout": ("id", "externalReference", "status"),
        "subscription": (
            "id", "customer", "status", "nextDueDate", "externalReference",
            "checkoutSession", "cycle",
        ),
        "payment": (
            "id", "subscription", "status", "dueDate", "paymentDate", "confirmedDate",
        ),
    }
    for object_name, allowed_fields in field_map.items():
        value = payload.get(object_name)
        if isinstance(value, dict):
            safe[object_name] = {
                key: value[key]
                for key in allowed_fields
                if value.get(key) is not None
            }
    for key in ("checkoutSession", "externalReference"):
        if payload.get(key) is not None:
            safe[key] = payload[key]
    return safe


def _webhook_resource_id(payload):
    for object_name in ("payment", "subscription", "checkout"):
        value = payload.get(object_name)
        if isinstance(value, dict) and value.get("id"):
            return str(value["id"])[:255]
    return None


@billing_bp.route("/webhooks/asaas", methods=["POST"])
def asaas_webhook():
    expected_token = current_app.config.get("ASAAS_WEBHOOK_TOKEN")
    received_token = request.headers.get("asaas-access-token", "")
    if not expected_token or not hmac.compare_digest(str(received_token), str(expected_token)):
        return jsonify({"error": "Token de webhook inválido."}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload.get("id"):
        return jsonify({"error": "Evento inválido."}), 400

    event_id = str(payload["id"])
    if not event_id or len(event_id) > 255:
        return jsonify({"error": "Identificador de evento inválido."}), 400
    safe_payload = _safe_webhook_payload(payload)
    event = BillingEvent.query.filter_by(provider="asaas", provider_event_id=event_id).first()
    if event and event.processing_status == "processed":
        return jsonify({"received": True}), 200
    if event is None:
        event = BillingEvent(
            provider="asaas",
            provider_event_id=event_id,
            event_type=str(payload.get("event", ""))[:64],
            resource_id=_webhook_resource_id(safe_payload),
            payload=safe_payload,
            processing_status="pending",
        )
        db.session.add(event)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            event = BillingEvent.query.filter_by(
                provider="asaas", provider_event_id=event_id
            ).one()
            if event.processing_status == "processed":
                return jsonify({"received": True}), 200

    try:
        event = BillingEvent.query.populate_existing().with_for_update().filter_by(
            provider="asaas", provider_event_id=event_id
        ).one()
        if event.processing_status == "processed":
            return jsonify({"received": True}), 200
        event.attempt_count += 1
        event.processing_status = "pending"
        event.last_error = None
        if not _process_asaas_event(event.payload):
            event.processing_status = "failed"
            event.last_error = "Evento ainda não pôde ser correlacionado."
            db.session.commit()
            return jsonify({"received": False, "retryable": True}), 409
        event.processing_status = "processed"
        event.processed_at = datetime.utcnow()
        db.session.commit()
    except (AsaasError, SQLAlchemyError, TypeError, ValueError):
        db.session.rollback()
        event = BillingEvent.query.filter_by(
            provider="asaas", provider_event_id=event_id
        ).one()
        event.attempt_count += 1
        event.processing_status = "failed"
        event.last_error = "Falha temporária ao processar evento."
        db.session.commit()
        current_app.logger.exception(
            "Asaas webhook processing failed event=%s", event.event_type
        )
        return jsonify({"received": False, "retryable": True}), 503
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
    db.session.add(AdminActionAudit(
        actor_user_id=g.user.id,
        subject_user_id=application.user_id,
        action=f"professional_application.{application.status}",
        resource_type="professional_application",
        resource_id=str(application.id),
        details={"plan_code": application.plan_code, "profession": application.profession},
    ))
    db.session.commit()
    return jsonify({"message": message, "application": application.to_dict()}), 200
