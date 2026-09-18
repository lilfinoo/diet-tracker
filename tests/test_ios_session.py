from tests.helpers import registration_payload


def test_native_session_cookie_cors_and_csrf(app, client):
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="None",
        CSRF_PROTECTION=True,
    )
    origin = {"Origin": "capacitor://localhost"}
    registered = client.post(
        "/api/register", json=registration_payload("native-session"), headers=origin
    )
    assert registered.status_code == 201
    cookie = registered.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=None" in cookie
    assert registered.headers["Access-Control-Allow-Origin"] == "capacitor://localhost"
    assert registered.headers["Access-Control-Allow-Credentials"] == "true"

    confirmed = client.get("/api/check_session", headers=origin).get_json()
    assert confirmed["logged_in"] is True
    assert confirmed["user"]["id"] == registered.get_json()["user"]["id"]
    assert confirmed["csrf_token"]
    assert client.get("/api/profile", headers=origin).status_code == 200
    assert client.post("/api/logout", headers=origin).status_code == 403
    assert client.post(
        "/api/logout", headers={**origin, "X-CSRF-Token": confirmed["csrf_token"]}
    ).status_code == 200
    assert client.get("/api/check_session", headers=origin).get_json()["logged_in"] is False
    assert client.get("/api/profile", headers=origin).status_code == 401


def test_native_preflight_permits_session_headers_but_not_unknown_origins(client):
    response = client.options("/api/profile", headers={
        "Origin": "capacitor://localhost",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-csrf-token,idempotency-key",
    })
    assert response.headers["Access-Control-Allow-Origin"] == "capacitor://localhost"
    allowed = response.headers["Access-Control-Allow-Headers"].lower()
    assert all(header in allowed for header in ("content-type", "x-csrf-token", "idempotency-key"))
    denied = client.get("/api/check_session", headers={"Origin": "https://unknown.example"})
    assert "Access-Control-Allow-Origin" not in denied.headers
