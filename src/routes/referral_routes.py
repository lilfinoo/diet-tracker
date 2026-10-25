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
