import time
from collections import defaultdict, deque
from threading import Lock

from flask import current_app, jsonify, request
from functools import wraps


class _LimiterState:
    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key, limit, window):
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

_state = _LimiterState()


def _client_key():
    from flask import session

    remote = request.remote_addr or "unknown"
    account = str(session.get("user_id") or "")
    return f"{remote}|{account}"


def _rate_config(name):
    app_config = current_app.config.get("RATE_LIMITS") or {}
    return app_config.get(name)


def rate_limit(name, default_limit, default_window):
    """In-memory sliding-window limiter keyed by client IP (+ user when logged in).

    Limits are per-process only; if the app later runs multiple gunicorn
    workers, switch to a shared backend (e.g. Redis).
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            limit, window = _rate_config(name) or (default_limit, default_window)
            key = _client_key()
            if not _state.allow(key, int(limit), int(window)):
                return jsonify({"error": "Muitas tentativas. Aguarde um instante."}), 429
            return f(*args, **kwargs)

        return wrapper

    return decorator
