"""Validate native Apple identities and revoke their server authorization."""
import hashlib
import hmac
import time

import jwt
import requests
from cryptography.fernet import Fernet
from flask import current_app

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS = jwt.PyJWKClient(f"{APPLE_ISSUER}/auth/keys", timeout=10)


def configured():
    return all(current_app.config.get(key) for key in (
        "APPLE_CLIENT_ID", "APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY", "APPLE_TOKEN_ENCRYPTION_KEY"
    ))


def verify_identity(credential, nonce):
    if not isinstance(credential, str) or len(credential) > 20000:
        raise ValueError("Invalid token")
    header = jwt.get_unverified_header(credential)
    if header.get("alg") != "RS256":
        raise ValueError("Invalid algorithm")
    key = APPLE_KEYS.get_signing_key_from_jwt(credential)
    payload = jwt.decode(credential, key.key, algorithms=["RS256"], audience=current_app.config["APPLE_CLIENT_ID"],
                         issuer=APPLE_ISSUER, options={"require": ["exp", "iat", "sub", "nonce"]})
    expected = hashlib.sha256(nonce.encode()).hexdigest()
    if not isinstance(payload["nonce"], str) or not hmac.compare_digest(payload["nonce"], expected):
        raise ValueError("Invalid nonce")
    if not isinstance(payload["sub"], str) or not payload["sub"] or len(payload["sub"]) > 255:
        raise ValueError("Invalid subject")
    return payload


def _client_secret():
    now = int(time.time())
    return jwt.encode({"iss": current_app.config["APPLE_TEAM_ID"], "iat": now, "exp": now + 300,
                       "aud": APPLE_ISSUER, "sub": current_app.config["APPLE_CLIENT_ID"]},
                      current_app.config["APPLE_PRIVATE_KEY"].replace("\\n", "\n"), algorithm="ES256",
                      headers={"kid": current_app.config["APPLE_KEY_ID"]})


def _post(path, data):
    response = requests.post(f"{APPLE_ISSUER}/auth/{path}", data={
        "client_id": current_app.config["APPLE_CLIENT_ID"], "client_secret": _client_secret(), **data,
    }, timeout=15)
    if response.status_code != 200:
        raise ValueError("Apple authorization failed")
    return response.json() if response.content else {}


def exchange_code(code, subject, nonce):
    if not isinstance(code, str) or not code or len(code) > 4096:
        raise ValueError("Invalid authorization code")
    result = _post("token", {"code": code, "grant_type": "authorization_code"})
    # Apple signs the token returned by the code exchange; it must name the same user.
    token = result.get("id_token")
    key = APPLE_KEYS.get_signing_key_from_jwt(token)
    payload = jwt.decode(token, key.key, algorithms=["RS256"], audience=current_app.config["APPLE_CLIENT_ID"],
                         issuer=APPLE_ISSUER, options={"require": ["exp", "sub"]})
    refresh = result.get("refresh_token")
    if payload["sub"] != subject or payload.get("nonce") != hashlib.sha256(nonce.encode()).hexdigest() or not isinstance(refresh, str) or not refresh:
        raise ValueError("Invalid authorization response")
    return Fernet(current_app.config["APPLE_TOKEN_ENCRYPTION_KEY"].encode()).encrypt(refresh.encode()).decode()


def revoke_identity(identity):
    if not configured() or not identity.apple_refresh_token:
        raise ValueError("Apple revocation is not configured")
    token = Fernet(current_app.config["APPLE_TOKEN_ENCRYPTION_KEY"].encode()).decrypt(identity.apple_refresh_token.encode()).decode()
    _post("revoke", {"token": token, "token_type_hint": "refresh_token"})
