import hashlib
import time
from collections import defaultdict, deque
from threading import Lock

from flask import current_app, jsonify, request, session
from functools import wraps
from redis import Redis
from redis.exceptions import RedisError


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
_redis_clients = {}
_redis_lock = Lock()


_INCREMENT_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def _redis_client(url):
    with _redis_lock:
        client = _redis_clients.get(url)
        if client is None:
            client = Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            _redis_clients[url] = client
        return client


def _client_key(name):
    remote = request.remote_addr or "unknown"
    user_id = None if name in {"login", "register"} else session.get("user_id")
    identity = f"{remote}:{user_id or 'anonymous'}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _rate_config(name):
    app_config = current_app.config.get("RATE_LIMITS") or {}
    return app_config.get(name)


def rate_limit(name, default_limit, default_window):
    """Apply a shared fixed-window limit, with an in-memory development fallback."""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            limit, window = _rate_config(name) or (default_limit, default_window)
            limit = int(limit)
            window = int(window)
            redis_url = current_app.config.get("REDIS_URL")
            allowed = True
            if redis_url:
                bucket = int(time.time()) // window
                key = f"diet-tracker:rate:{name}:{bucket}:{_client_key(name)}"
                try:
                    allowed = int(_redis_client(redis_url).eval(
                        _INCREMENT_WINDOW, 1, key, window + 1
                    )) <= limit
                except RedisError:
                    current_app.logger.exception("Shared rate limiter is unavailable")
                    return jsonify({"error": "Proteção de acesso temporariamente indisponível."}), 503
            else:
                key = (id(current_app._get_current_object()), name, _client_key(name))
                allowed = _state.allow(key, limit, window)
            if not allowed:
                return jsonify({"error": "Muitas tentativas. Aguarde um instante."}), 429
            return f(*args, **kwargs)

        return wrapper

    return decorator
