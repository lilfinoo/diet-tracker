from flask import Blueprint, g, jsonify

from src.models.user import db
from src.routes.common import login_required
from src.services.rate_limit import rate_limit
from src.services.referrals import referral_summary

referral_bp = Blueprint("referrals", __name__)


@referral_bp.route("/referrals", methods=["GET"])
@login_required
@rate_limit("referrals", 60, 60)
def get_referrals():
    payload = referral_summary(g.user)
    db.session.commit()
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@referral_bp.route("/referrals/attribution", methods=["GET"])
@login_required
def get_attribution():
    from src.models.user import Referral
    from src.services.affiliates import attribution_dict, eligible_for_affiliate

    entry = Referral.query.filter_by(invitee_user_id=g.user.id).order_by(
        (Referral.kind == "affiliate").desc()
    ).first()
    response = jsonify(attribution=attribution_dict(entry) if entry else None,
                       can_apply_affiliate=eligible_for_affiliate(g.user))
    response.headers["Cache-Control"] = "no-store"
    return response


@referral_bp.route("/referrals/apply", methods=["POST"])
@login_required
@rate_limit("referral_apply", 10, 60)
def apply_code():
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError
    from src.models.user import ReferralCode
    from src.routes.common import json_body
    from src.services.affiliates import attach_affiliate, attribution_dict
    from src.services.referrals import _invalid_code, _locked_user, normalize_code

    data = json_body()
    if set(data) != {"code"}:
        return jsonify(error="Informe somente o código."), 400
    try:
        normalized = normalize_code(data["code"])
        _locked_user(g.user.id)
        code = ReferralCode.query.filter_by(code=normalized).with_for_update().populate_existing().first()
        if not code or not code.active:
            _invalid_code()
        if code.kind != "affiliate":
            return jsonify(error="Convites de amigos são aplicados somente no cadastro.",
                           code="user_referral_signup_only"), 400
        entry = attach_affiliate(g.user, code, source="app")
        payload = attribution_dict(entry)
        db.session.commit()
        return jsonify(**payload, message=f"Código de {payload['public_name']} aplicado com sucesso.")
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Esta conta já possui uma indicação.", code="referral_already_applied"), 409
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Não foi possível aplicar o código agora. Tente novamente."), 503
