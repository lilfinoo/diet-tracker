from datetime import datetime, timedelta
import hashlib
import secrets
import jwt
import requests
from itsdangerous import URLSafeTimedSerializer
from src.services import apple_auth as apple_auth_service
import logging
from flask import Blueprint, current_app, jsonify, request, session
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy.exc import IntegrityError

from src.models.user import AppleAuthChallenge, OAuthIdentity, User, db
from src.legal import AI_CONSENT_VERSION, legal_versions_payload, record_consent
from src.routes.common import _csrf_token, _google_identity_claims, _google_signup_serializer, _start_session, json_body, login_required
from src.services.badges import grant_signup_badges
from src.services.analytics import analytics_context, record_event
from src.services.rate_limit import rate_limit


auth_bp = Blueprint("auth", __name__)


@auth_bp.after_request
def log_session_diagnostic(response):
    if request.endpoint in {"auth.login", "auth.register", "auth.google_auth", "auth.check_session", "auth.logout"}:
        payload = response.get_json(silent=True) or {}
        logger = current_app.logger.getChild("auth")
        logger.setLevel(logging.INFO)
        logger.info(
            "[Auth] endpoint=%s status=%s cookie_present=%s session_user_present=%s confirmed=%s",
            request.endpoint, response.status_code,
            current_app.config.get("SESSION_COOKIE_NAME", "session") in request.cookies,
            bool(session.get("user_id")), payload.get("logged_in") is True,
        )
    if request.endpoint in {"auth.auth_config", "auth.apple_challenge", "auth.apple_login"}:
        response.headers["Cache-Control"] = "no-store"
    return response


def _account_fields(data, default_name):
    name = str(data.get("name") or default_name).strip()
    email = str(data.get("email") or "").strip().lower() or None
    if not name or len(name) > 255:
        return None, None, "Nome deve ter entre 1 e 255 caracteres"
    if email and (len(email) > 320 or "@" not in email or any(char.isspace() for char in email)):
        return None, None, "E-mail inválido"
    return name, email, None


def _sync_google_account(user, claims):
    user.name = claims["display_name"] or user.name or user.username
    if claims["email_verified"] and claims["email"]:
        user.email = claims["email"].lower()
@auth_bp.route("/auth/config", methods=["GET"])
def auth_config():
    return jsonify({
        "apple_enabled": apple_auth_service.configured(),
        "google_client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "legal": legal_versions_payload(),
    }), 200


def _validate_signup_consents(data):
    if not isinstance(data.get("ai_consent"), bool):
        return jsonify({"error": "Informe sua escolha sobre o processamento por IA."}), 400
    if data.get("ai_consent") is True and data.get("ai_consent_version") != AI_CONSENT_VERSION:
        return jsonify({"error": "A versão do consentimento de IA está desatualizada."}), 400
    return None


def _record_signup_consents(user, data):
    record_consent(user, "ai", AI_CONSENT_VERSION, data["ai_consent"], "registration")


@auth_bp.route("/auth/google", methods=["POST"])
@rate_limit("login", 10, 60)
def google_auth():
    data = json_body()
    signup_token = data.get("signup_token")

    if signup_token:
        consent_error = _validate_signup_consents(data)
        if consent_error:
            return consent_error
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
            _sync_google_account(identity.user, claims)
            db.session.commit()
            _start_session(identity.user)
            return jsonify({"message": "Login bem-sucedido", "user": identity.user.session_dict(), "csrf_token": _csrf_token()}), 200

        username = str(data.get("username", "")).strip()
        if not username or len(username) > 80:
            return jsonify({"error": "Nome de usuário deve ter entre 1 e 80 caracteres"}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({"error": "Nome de usuário já existe", "code": "username_taken"}), 409

        user = User(
            username=username,
            name=claims["display_name"] or username,
            email=claims["email"].lower() if claims["email_verified"] and claims["email"] else None,
        )
        identity = OAuthIdentity(user=user, last_login_at=datetime.utcnow(), **claims)
        db.session.add_all((user, identity))
        db.session.flush()
        _record_signup_consents(user, data)
        grant_signup_badges(user)
        anonymous_id, analytics_properties = analytics_context(data.get("analytics"))
        record_event(
            "signup_completed",
            user_id=user.id,
            anonymous_id=anonymous_id,
            properties=analytics_properties,
        )
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Nome de usuário já existe", "code": "username_taken"}), 409
        _start_session(user)
        return jsonify({"message": "Usuário criado com sucesso", "user": user.session_dict(), "csrf_token": _csrf_token()}), 201

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
        _sync_google_account(identity.user, claims)
        db.session.commit()
        _start_session(identity.user)
        return jsonify({"message": "Login bem-sucedido", "user": identity.user.session_dict(), "csrf_token": _csrf_token()}), 200

    return jsonify({
        "error": "Nome de usuário necessário",
        "code": "username_required",
        "signup_token": _google_signup_serializer().dumps(claims),
    }), 409


@auth_bp.route("/auth/apple/challenge", methods=["POST"])
@rate_limit("apple_challenge", 10, 60)
def apple_challenge():
    if not apple_auth_service.configured():
        return jsonify({"error": "Login Apple não configurado"}), 503
    nonce = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    AppleAuthChallenge.query.filter(AppleAuthChallenge.expires_at <= now).delete()
    db.session.add(AppleAuthChallenge(nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(), expires_at=now + timedelta(minutes=5)))
    db.session.commit()
    session["apple_nonce"] = nonce
    return jsonify({"nonce": nonce}), 200


@auth_bp.route("/auth/apple", methods=["POST"])
@rate_limit("apple_login", 10, 60)
def apple_login():
    if not apple_auth_service.configured():
        return jsonify({"error": "Login Apple não configurado"}), 503
    data = json_body()
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="apple-signup")
    signup_token = data.get("signup_token")
    if signup_token and (not isinstance(signup_token, str) or len(signup_token) > 20000):
        return jsonify({"error": "Cadastro Apple expirado ou inválido"}), 401
    if signup_token:
        consent_error = _validate_signup_consents(data)
        if consent_error:
            return consent_error
        try:
            claims = serializer.loads(signup_token, max_age=600)
            if claims.get("provider") != "apple":
                raise BadSignature("Invalid provider")
            if not AppleAuthChallenge.query.filter_by(nonce_hash=hashlib.sha256(signup_token.encode()).hexdigest()).filter(AppleAuthChallenge.expires_at > datetime.utcnow()).first():
                raise BadSignature("Used signup token")
        except BadSignature:
            return jsonify({"error": "Cadastro Apple expirado ou inválido"}), 401
    else:
        nonce = data.get("nonce")
        expected = session.pop("apple_nonce", None)
        if not isinstance(nonce, str) or not expected or not secrets.compare_digest(nonce, expected):
            return jsonify({"error": "Solicitação Apple inválida"}), 401
        consumed = AppleAuthChallenge.query.filter_by(nonce_hash=hashlib.sha256(nonce.encode()).hexdigest()).filter(
            AppleAuthChallenge.expires_at > datetime.utcnow()
        ).delete()
        db.session.commit()
        if consumed != 1:
            return jsonify({"error": "Solicitação Apple expirada ou já utilizada"}), 401
        try:
            payload = apple_auth_service.verify_identity(data.get("credential"), nonce)
            encrypted_token = apple_auth_service.exchange_code(data.get("authorization_code"), payload["sub"], nonce)
        except (ValueError, jwt.InvalidTokenError):
            return jsonify({"error": "Credencial Apple inválida"}), 401
        except (requests.RequestException, jwt.PyJWKClientError):
            return jsonify({"error": "Apple indisponível. Tente novamente."}), 503
        email = payload.get("email")
        claims = {"provider": "apple", "issuer": apple_auth_service.APPLE_ISSUER, "subject": payload["sub"],
                  "email": email[:320] if isinstance(email, str) else None,
                  "email_verified": payload.get("email_verified") in (True, "true"),
                  "display_name": str(data.get("display_name") or "")[:255] or None,
                  "apple_refresh_token": encrypted_token}
    identity = OAuthIdentity.query.filter_by(provider="apple", issuer=claims["issuer"], subject=claims["subject"]).first()
    if identity:
        if signup_token:
            consumed = AppleAuthChallenge.query.filter_by(nonce_hash=hashlib.sha256(signup_token.encode()).hexdigest()).filter(AppleAuthChallenge.expires_at > datetime.utcnow()).delete()
            if consumed != 1:
                db.session.rollback()
                return jsonify({"error": "Cadastro Apple expirado ou já utilizado"}), 401
        if identity.user.is_banned:
            session.clear()
            return jsonify({"error": "Sua conta foi banida."}), 403
        identity.last_login_at = datetime.utcnow()
        identity.apple_refresh_token = claims["apple_refresh_token"]
        db.session.commit()
        _start_session(identity.user)
        return jsonify({"message": "Login bem-sucedido", "user": identity.user.session_dict(), "csrf_token": _csrf_token()}), 200
    if not signup_token:
        token = serializer.dumps(claims)
        db.session.add(AppleAuthChallenge(nonce_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(minutes=10)))
        db.session.commit()
        return jsonify({"error": "Nome de usuário necessário", "code": "username_required", "signup_token": token}), 409
    username = str(data.get("username") or "").strip()
    if not username or len(username) > 80:
        return jsonify({"error": "Nome de usuário deve ter entre 1 e 80 caracteres"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Nome de usuário já existe", "code": "username_taken"}), 409
    consumed = AppleAuthChallenge.query.filter_by(nonce_hash=hashlib.sha256(signup_token.encode()).hexdigest()).filter(AppleAuthChallenge.expires_at > datetime.utcnow()).delete()
    if consumed != 1:
        db.session.rollback()
        return jsonify({"error": "Cadastro Apple expirado ou já utilizado"}), 401
    user = User(username=username, name=claims["display_name"] or username,
                email=claims["email"] if claims["email_verified"] else None)
    identity = OAuthIdentity(user=user, last_login_at=datetime.utcnow(), **claims)
    db.session.add_all((user, identity))
    try:
        db.session.flush()
        _record_signup_consents(user, data)
        grant_signup_badges(user)
        anonymous_id, properties = analytics_context(data.get("analytics"))
        record_event("signup_completed", user_id=user.id, anonymous_id=anonymous_id, properties=properties)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Cadastro já utilizado ou nome de usuário indisponível"}), 409
    _start_session(user)
    return jsonify({"message": "Usuário criado com sucesso", "user": user.session_dict(), "csrf_token": _csrf_token()}), 201


@auth_bp.route("/register", methods=["POST"])
@rate_limit("register", 10, 60)
def register():
    data = json_body()
    consent_error = _validate_signup_consents(data)
    if consent_error:
        return consent_error
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
    name, email, account_error = _account_fields(data, username)
    if account_error:
        return jsonify({"error": account_error}), 400

    user = User(username=username, name=name, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    _record_signup_consents(user, data)
    grant_signup_badges(user)
    anonymous_id, analytics_properties = analytics_context(data.get("analytics"))
    record_event(
        "signup_completed",
        user_id=user.id,
        anonymous_id=anonymous_id,
        properties=analytics_properties,
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Nome de usuário já existe"}), 409

    _start_session(user)
    return jsonify({"message": "Usuário criado com sucesso", "user": user.session_dict(), "csrf_token": _csrf_token()}), 201


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
        return jsonify({"message": "Login bem-sucedido", "user": user.session_dict(), "csrf_token": _csrf_token()}), 200
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
            return jsonify({"logged_in": True, "user": user.session_dict(), "csrf_token": _csrf_token()}), 200
        session.clear()
    return jsonify({"logged_in": False}), 200
