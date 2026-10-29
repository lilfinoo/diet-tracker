"""Server-authorized partner management and privacy-safe partner summaries."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from src.models.user import (
    AdminActionAudit, Affiliate, AffiliateCommission, AffiliatePayout, Referral, ReferralCode,
    Subscription, User, db,
)
from src.routes.common import admin_required, json_body, login_required
from src.services.affiliates import (
    affiliate_dict, affiliate_page_dicts, code_dict, configure_affiliate, create_code, payout_dict, payouts_query,
)
from src.services.referrals import normalize_code


affiliate_bp = Blueprint("affiliates", __name__)


@affiliate_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def audit(action, affiliate, details=None):
    db.session.add(AdminActionAudit(
        actor_user_id=g.user.id, action=action, resource_type="affiliate",
        resource_id=str(affiliate.id), details=details,
    ))


def page(query, key, serialize):
    try:
        number = int(request.args.get("page", 1))
        size = int(request.args.get("per_page", 25))
        if number < 1 or not 1 <= size <= 100:
            raise ValueError()
    except ValueError:
        return jsonify(error="Paginação inválida."), 400
    result = query.paginate(page=number, per_page=size, error_out=False)
    return jsonify({key: [serialize(row) for row in result.items], "page": number,
                    "pages": result.pages, "total": result.total})


@affiliate_bp.route("/admin/affiliates", methods=["GET"])
@admin_required
def list_affiliates():
    try:
        number = int(request.args.get("page", 1))
        size = int(request.args.get("per_page", 25))
        if number < 1 or not 1 <= size <= 100:
            raise ValueError()
    except ValueError:
        return jsonify(error="Paginação inválida."), 400
    result = Affiliate.query.order_by(Affiliate.id.desc()).paginate(
        page=number, per_page=size, error_out=False,
    )
    return jsonify(affiliates=affiliate_page_dicts(result.items), page=number,
                   pages=result.pages, total=result.total)


@affiliate_bp.route("/admin/affiliates", methods=["POST"])
@admin_required
def add_affiliate():
    data = json_body()
    affiliate = Affiliate()
    try:
        configure_affiliate(affiliate, data, creating=True)
        db.session.add(affiliate)
        db.session.flush()
        create_code(affiliate, data.get("code"))
        audit("affiliate_created", affiliate)
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Código ou conta vinculada já está em uso."), 409
    return jsonify(affiliate_dict(affiliate)), 201


@affiliate_bp.route("/admin/affiliates/<int:affiliate_id>", methods=["PATCH"])
@admin_required
def update_affiliate(affiliate_id):
    data = json_body()
    if data.get("user_id"):
        try:
            linked_id = UUID(str(data["user_id"]))
        except ValueError:
            return jsonify(error="Conta vinculada inválida."), 400
        # User before affiliate, matching attribution lock order and FK checks.
        User.query.filter_by(id=linked_id).with_for_update().first()
    affiliate = Affiliate.query.filter_by(id=affiliate_id).with_for_update().first_or_404()
    try:
        before = {key: str(getattr(affiliate, key)) for key in data if hasattr(affiliate, key)}
        configure_affiliate(affiliate, data)
        audit("affiliate_updated", affiliate, {"before": before,
              "after": {key: str(getattr(affiliate, key)) for key in data}})
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify(error=str(error)), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Conta vinculada já está em uso."), 409
    return jsonify(affiliate_dict(affiliate))


@affiliate_bp.route("/admin/affiliates/<int:affiliate_id>/codes", methods=["POST"])
@admin_required
def add_code(affiliate_id):
    affiliate = Affiliate.query.filter_by(id=affiliate_id).with_for_update().first_or_404()
    data = json_body()
    if set(data) - {"code"}:
        return jsonify(error="Informe somente o código."), 400
    try:
        code = create_code(affiliate, data.get("code"))
        audit("affiliate_code_created", affiliate, {"code": code.code})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Código já está em uso."), 409
    return jsonify(code_dict(code)), 201


@affiliate_bp.route("/admin/affiliates/<int:affiliate_id>/codes/<code>", methods=["PATCH"])
@admin_required
def update_code(affiliate_id, code):
    # Lock order matches apply: user -> code -> affiliate; do not lock the
    # affiliate first here because apply holds the code while reading status.
    entry = ReferralCode.query.filter_by(
        affiliate_id=affiliate_id, code=normalize_code(code), kind="affiliate"
    ).with_for_update().first_or_404()
    data = json_body()
    if set(data) != {"active"} or not isinstance(data["active"], bool):
        return jsonify(error="Informe o status ativo do código."), 400
    entry.active = data["active"]
    affiliate = db.session.get(Affiliate, affiliate_id)
    audit("affiliate_code_updated", affiliate, {"code": entry.code, "active": entry.active})
    db.session.commit()
    return jsonify(code_dict(entry))


@affiliate_bp.route("/admin/affiliates/<int:affiliate_id>/referrals", methods=["GET"])
@admin_required
def affiliate_referrals(affiliate_id):
    db.get_or_404(Affiliate, affiliate_id)
    query = db.session.query(Referral, User).outerjoin(User, User.id == Referral.invitee_user_id).filter(
        Referral.affiliate_id == affiliate_id
    ).order_by(Referral.id.desc())
    # Batch subscription snapshots for each page; don't disclose financial claims
    # from an active entitlement. Paid confirmations are not integrated yet.
    try:
        number, size = int(request.args.get("page", 1)), int(request.args.get("per_page", 25))
        if number < 1 or not 1 <= size <= 100:
            raise ValueError()
    except ValueError:
        return jsonify(error="Paginação inválida."), 400
    total = query.count()
    rows = query.limit(size).offset((number - 1) * size).all()
    ids = [entry.invitee_user_id for entry, _ in rows if entry.invitee_user_id]
    snapshots = {}
    for subscription in Subscription.query.filter(
        Subscription.user_id.in_(ids), Subscription.provider.notin_(("admin", "referral"))
    ).order_by(Subscription.updated_at):
        snapshots[subscription.user_id] = subscription.status
    return jsonify(referrals=[{
        "id": entry.id, "user_id": str(user.id) if user else None,
        "username": user.username if user else None, "code": entry.code,
        "created_at": entry.created_at.isoformat() + "Z", "validation_state": entry.validation_state,
        "paid_confirmed": False, "subscription_status": snapshots.get(entry.invitee_user_id),
    } for entry, user in rows], page=number, pages=(total + size - 1) // size, total=total)


@affiliate_bp.route("/admin/affiliates/<int:affiliate_id>/payouts", methods=["GET"])
@admin_required
def affiliate_payouts(affiliate_id):
    db.get_or_404(Affiliate, affiliate_id)
    return page(payouts_query(affiliate_id), "payouts", payout_dict)


@affiliate_bp.route("/admin/affiliates/<int:affiliate_id>/payouts", methods=["POST"])
@admin_required
def record_payout(affiliate_id):
    """Record a manual payment of released production commissions only.

    Currently unavailable: no adapter can release commissions. Never accept
    client-supplied amounts, percentages, or claims of a verified transaction.
    """
    from src.services.affiliates import FINANCIAL_TRACKING_ENABLED
    if not FINANCIAL_TRACKING_ENABLED:
        return jsonify(error="Registro financeiro desativado até a integração de transações verificadas.",
                       code="affiliate_finance_disabled"), 503
    affiliate = Affiliate.query.filter_by(id=affiliate_id).with_for_update().first_or_404()
    data = json_body()
    if set(data) != {"commission_ids", "reference"}:
        return jsonify(error="Informe as comissões liberadas e a referência do pagamento."), 400
    ids, reference = data["commission_ids"], data["reference"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100 or
            any(type(item) is not int for item in ids) or len(set(ids)) != len(ids) or
            not isinstance(reference, str) or not reference.strip() or len(reference) > 255):
        return jsonify(error="Dados de pagamento inválidos."), 400
    commissions = AffiliateCommission.query.filter(
        AffiliateCommission.id.in_(ids), AffiliateCommission.affiliate_id == affiliate_id
    ).with_for_update().all()
    if (len(commissions) != len(ids) or len({c.currency for c in commissions}) != 1 or
            any(c.status != "released" or c.payout_id or c.environment != "production" or
                c.amount is None or c.net_amount is None for c in commissions)):
        return jsonify(error="Pagamento exige comissões liberadas com receita líquida confirmada."), 409
    now = datetime.utcnow()
    payout = AffiliatePayout(
        affiliate_id=affiliate_id, period_start=min(c.occurred_at for c in commissions),
        period_end=max(c.occurred_at for c in commissions),
        amount=sum((c.amount for c in commissions), Decimal(0)), currency=commissions[0].currency,
        status="paid", paid_at=now, reference=reference.strip(),
    )
    db.session.add(payout)
    db.session.flush()
    for commission in commissions:
        commission.payout_id, commission.status = payout.id, "paid"
    audit("affiliate_payout_recorded", affiliate, {"payout_id": payout.id, "commission_ids": ids})
    db.session.commit()
    return jsonify(payout_dict(payout)), 201


@affiliate_bp.route("/affiliates/me", methods=["GET"])
@login_required
def partner_summary():
    affiliate = Affiliate.query.filter_by(user_id=g.user.id).first_or_404()
    result = affiliate_dict(affiliate, private=False)
    result["payouts"] = [payout_dict(p) for p in payouts_query(affiliate.id).limit(100)]
    return jsonify(result)
