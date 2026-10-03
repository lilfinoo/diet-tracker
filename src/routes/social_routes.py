from datetime import datetime
from io import BytesIO

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy.exc import SQLAlchemyError

from src.models.user import User, UserProfile, db
from src.routes.common import idempotent_mutation, json_body, login_required, page_query
from src.services.badges import serialize_profile_highlights
from src.services.media_storage import (
    MediaStorageError,
    delete_avatar,
    get_avatar,
    prepare_avatar,
    upload_avatar,
)
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
    db.session.commit()
    return jsonify({"message": "Perfil público atualizado.", "profile": profile.to_dict()}), 200


@social_bp.route("/profile/avatar", methods=["POST", "DELETE"])
@login_required
@idempotent_mutation
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
        return jsonify({"error": "Foto não encontrada."}), 404
    try:
        content = get_avatar(user.profile.avatar_object_key)
    except MediaStorageError:
        return jsonify({"error": "Foto não encontrada."}), 404
    response = send_file(BytesIO(content), mimetype="image/webp", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    return response
