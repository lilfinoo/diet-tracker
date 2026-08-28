from datetime import datetime
from flask import Blueprint, current_app, jsonify, session
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy.exc import IntegrityError

from src.models.user import OAuthIdentity, User, db
from src.routes.common import _csrf_token, _google_identity_claims, _google_signup_serializer, _start_session, json_body, login_required
from src.services.badges import grant_signup_badges
from src.services.rate_limit import rate_limit


auth_bp = Blueprint("auth", __name__)
@auth_bp.route("/auth/config", methods=["GET"])
def auth_config():
    return jsonify({"google_client_id": current_app.config.get("GOOGLE_CLIENT_ID")}), 200


@auth_bp.route("/auth/google", methods=["POST"])
@rate_limit("login", 10, 60)
def google_auth():
    data = json_body()
    signup_token = data.get("signup_token")

    if signup_token:
        try:
            claims = _google_signup_serializer().loads(
                signup_token,
                max_age=current_app.config["GOOGLE_SIGNUP_TOKEN_MAX_AGE"],
            )
            if claims.get("provider") != "google":
                raise BadSignature("Invalid provider")
        except SignatureExpired:
            return jsonify({"error": "Token de cadastro expirado", "code": "invalid_signup_token"}), 401
        except BadSignature:
            return jsonify({"error": "Token de cadastro inválido", "code": "invalid_signup_token"}), 401

        identity = OAuthIdentity.query.filter_by(
            provider="google", issuer=claims["issuer"], subject=claims["subject"]
        ).first()
        if identity:
            if identity.user.is_banned:
                session.clear()
                return jsonify({"error": "Sua conta foi banida."}), 403
            identity.email = claims["email"]
            identity.email_verified = claims["email_verified"]
            identity.display_name = claims["display_name"]
            identity.avatar_url = claims["avatar_url"]
            identity.last_login_at = datetime.utcnow()
            db.session.commit()
            _start_session(identity.user)
            return jsonify({"message": "Login bem-sucedido", "user": identity.user.to_dict(), "csrf_token": _csrf_token()}), 200

        username = str(data.get("username", "")).strip()
        if not username or len(username) > 80:
            return jsonify({"error": "Nome de usuário deve ter entre 1 e 80 caracteres"}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({"error": "Nome de usuário já existe", "code": "username_taken"}), 409

        user = User(username=username)
        identity = OAuthIdentity(user=user, last_login_at=datetime.utcnow(), **claims)
        db.session.add_all((user, identity))
        db.session.flush()
        grant_signup_badges(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Nome de usuário já existe", "code": "username_taken"}), 409
        _start_session(user)
        return jsonify({"message": "Usuário criado com sucesso", "user": user.to_dict(), "csrf_token": _csrf_token()}), 201

    credential = data.get("credential")
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    if not client_id:
        return jsonify({"error": "Login Google não configurado"}), 503
    if not credential:
        return jsonify({"error": "Credential Google é obrigatória"}), 400
    try:
        payload = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
        )
        claims = _google_identity_claims(payload)
    except ValueError:
        return jsonify({"error": "Token Google inválido"}), 401

    identity = OAuthIdentity.query.filter_by(
        provider="google", issuer=claims["issuer"], subject=claims["subject"]
    ).first()
    if identity:
        if identity.user.is_banned:
            session.clear()
            return jsonify({"error": "Sua conta foi banida."}), 403
        identity.email = claims["email"]
        identity.email_verified = claims["email_verified"]
        identity.display_name = claims["display_name"]
        identity.avatar_url = claims["avatar_url"]
        identity.last_login_at = datetime.utcnow()
        db.session.commit()
        _start_session(identity.user)
        return jsonify({"message": "Login bem-sucedido", "user": identity.user.to_dict(), "csrf_token": _csrf_token()}), 200

    return jsonify({
        "error": "Nome de usuário necessário",
        "code": "username_required",
        "signup_token": _google_signup_serializer().dumps(claims),
    }), 409


@auth_bp.route("/register", methods=["POST"])
@rate_limit("register", 10, 60)
def register():
    data = json_body()
    username = str(data.get("username", "")).strip()
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Nome de usuário e senha são obrigatórios"}), 400
    if len(username) > 80:
        return jsonify({"error": "Nome de usuário deve ter no máximo 80 caracteres"}), 400
    if len(str(password)) < 8 or len(str(password)) > 128:
        return jsonify({"error": "A senha deve ter entre 8 e 128 caracteres"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Nome de usuário já existe"}), 400

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    grant_signup_badges(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Nome de usuário já existe"}), 409

    _start_session(user)
    return jsonify({"message": "Usuário criado com sucesso", "user": user.to_dict(), "csrf_token": _csrf_token()}), 201


@auth_bp.route("/login", methods=["POST"])
@rate_limit("login", 10, 60)
def login():
    data = json_body()
    username = str(data.get("username", "")).strip()
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Nome de usuário e senha são obrigatórios"}), 400

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        if user.is_banned:
            session.clear()
            return jsonify({"error": "Sua conta foi banida."}), 403
        _start_session(user)
        return jsonify({"message": "Login bem-sucedido", "user": user.to_dict(), "csrf_token": _csrf_token()}), 200
    return jsonify({"error": "Nome de usuário ou senha inválidos"}), 401


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return jsonify({"message": "Logout bem-sucedido"}), 200


@auth_bp.route("/check_session", methods=["GET"])
def check_session():
    user_id = session.get("user_id")
    if user_id:
        user = db.session.get(User, user_id)
        if user:
            if user.is_banned:
                session.clear()
                return jsonify({"logged_in": False, "error": "Sua conta foi banida."}), 403
            return jsonify({"logged_in": True, "user": user.to_dict(), "csrf_token": _csrf_token()}), 200
        session.clear()
    return jsonify({"logged_in": False}), 200
