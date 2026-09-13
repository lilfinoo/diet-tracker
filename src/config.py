import os
from pathlib import Path
from urllib.parse import urlsplit


BASE_DIR = Path(__file__).resolve().parent.parent


def _csv(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


class Config:
    APP_ENV = "development"
    IS_PRODUCTION = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'diet_tracker.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    HSTS_ENABLED = False
    CSRF_PROTECTION = True
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
    CORS_ORIGINS = _csv("CORS_ORIGINS")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_SIGNUP_TOKEN_MAX_AGE = int(os.getenv("GOOGLE_SIGNUP_TOKEN_MAX_AGE", "600"))
    ASAAS_API_KEY = os.getenv("ASAAS_API_KEY")
    ASAAS_ENV = os.getenv("ASAAS_ENV", "sandbox")
    ASAAS_API_BASE_URL = os.getenv(
        "ASAAS_API_BASE_URL",
        "https://api.asaas.com/v3" if ASAAS_ENV == "production" else "https://api-sandbox.asaas.com/v3",
    )
    ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN")
    BILLING_ENABLED = os.getenv("BILLING_ENABLED", "false").lower() == "true"
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-flash-lite-latest")
    GEMINI_STRUCTURED_MODEL = os.getenv("GEMINI_STRUCTURED_MODEL", "gemini-flash-lite-latest")
    GEMINI_PLAN_MODEL = os.getenv("GEMINI_PLAN_MODEL", "gemini-flash-latest")
    GEMINI_WORKOUT_MODEL = os.getenv("GEMINI_WORKOUT_MODEL", GEMINI_STRUCTURED_MODEL)
    GEMINI_WORKOUT_FALLBACK_MODEL = os.getenv(
        "GEMINI_WORKOUT_FALLBACK_MODEL", GEMINI_PLAN_MODEL
    )
    GEMINI_WORKOUT_UNAVAILABLE_RETRIES = int(
        os.getenv("GEMINI_WORKOUT_UNAVAILABLE_RETRIES", "2")
    )
    GEMINI_WORKOUT_VALIDATION_ATTEMPTS = int(
        os.getenv("GEMINI_WORKOUT_VALIDATION_ATTEMPTS", "3")
    )
    GEMINI_CHAT_MAX_TOKENS = int(os.getenv("GEMINI_CHAT_MAX_TOKENS", "768"))
    GEMINI_PLAN_MAX_TOKENS = int(os.getenv("GEMINI_PLAN_MAX_TOKENS", "12288"))
    GEMINI_DIET_PLAN_MODEL = os.getenv("GEMINI_DIET_PLAN_MODEL", GEMINI_STRUCTURED_MODEL)
    GEMINI_DIET_PLAN_MAX_TOKENS = int(os.getenv("GEMINI_DIET_PLAN_MAX_TOKENS", "8192"))
    GEMINI_DIET_RETRY_ATTEMPTS = int(os.getenv("GEMINI_DIET_RETRY_ATTEMPTS", "2"))
    GEMINI_DIET_VALIDATION_ATTEMPTS = int(
        os.getenv("GEMINI_DIET_VALIDATION_ATTEMPTS", "3")
    )
    GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "90"))
    REDIS_URL = os.getenv("REDIS_URL")
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or REDIS_URL
    AI_ASYNC_ENABLED = os.getenv("AI_ASYNC_ENABLED", "false").lower() == "true"
    AI_JOB_MAX_RETRIES = int(os.getenv("AI_JOB_MAX_RETRIES", "3"))
    AI_JOB_STALE_SECONDS = int(os.getenv("AI_JOB_STALE_SECONDS", "900"))
    AI_TASK_RETENTION_DAYS = int(os.getenv("AI_TASK_RETENTION_DAYS", "7"))
    ANALYTICS_RETENTION_DAYS = int(os.getenv("ANALYTICS_RETENTION_DAYS", "395"))
    METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").lower() == "true"
    METRICS_TOKEN = os.getenv("METRICS_TOKEN")
    MEDIA_R2_ENDPOINT_URL = os.getenv("MEDIA_R2_ENDPOINT_URL")
    MEDIA_R2_ACCESS_KEY_ID = os.getenv("MEDIA_R2_ACCESS_KEY_ID")
    MEDIA_R2_SECRET_ACCESS_KEY = os.getenv("MEDIA_R2_SECRET_ACCESS_KEY")
    MEDIA_R2_BUCKET = os.getenv("MEDIA_R2_BUCKET")
    WORKOUTX_API_KEY = os.getenv("WORKOUTX_API_KEY")
    WORKOUTX_TIMEOUT = int(os.getenv("WORKOUTX_TIMEOUT", "15"))
    WORKOUTX_MAX_RESPONSE_BYTES = int(
        os.getenv("WORKOUTX_MAX_RESPONSE_BYTES", str(15 * 1024 * 1024))
    )
    WORKOUTX_CACHE_DIR = BASE_DIR / "instance" / "workoutx-gifs"
    WORKOUTX_MEDIA_MAPPING_PATH = BASE_DIR / "src" / "data" / "workoutx_media.json"


class TestConfig(Config):
    APP_ENV = "test"
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SESSION_COOKIE_SECURE = False
    CSRF_PROTECTION = False
    GEMINI_API_KEY = None
    GOOGLE_CLIENT_ID = "test-google-client-id"
    ASAAS_API_KEY = None
    ASAAS_ENV = "sandbox"
    ASAAS_API_BASE_URL = "https://api-sandbox.asaas.com/v3"
    ASAAS_WEBHOOK_TOKEN = "test-webhook-token-0123456789abcdef"
    PUBLIC_BASE_URL = "https://test.example"
    WORKOUTX_API_KEY = None
    REDIS_URL = None
    CELERY_BROKER_URL = None
    AI_ASYNC_ENABLED = False
    METRICS_ENABLED = True
    METRICS_TOKEN = "test-metrics-token"
    RATE_LIMITS = {"login": (1000, 60), "register": (1000, 60), "ai": (1000, 60)}


class ProductionConfig(Config):
    APP_ENV = "production"
    IS_PRODUCTION = True
    SESSION_COOKIE_SECURE = True
    HSTS_ENABLED = True
    AI_ASYNC_ENABLED = os.getenv("AI_ASYNC_ENABLED", "true").lower() == "true"
    METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "300")),
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    }

    @classmethod
    def validate(cls, config=None) -> None:
        values = config or cls
        get = values.get if isinstance(values, dict) else lambda name: getattr(values, name)
        missing = [
            name
            for name, value in (
                ("SECRET_KEY", get("SECRET_KEY")),
                ("DATABASE_URL", get("SQLALCHEMY_DATABASE_URI")),
                ("GEMINI_API_KEY", get("GEMINI_API_KEY")),
                ("ASAAS_API_KEY", get("ASAAS_API_KEY")),
                ("ASAAS_WEBHOOK_TOKEN", get("ASAAS_WEBHOOK_TOKEN")),
                ("PUBLIC_BASE_URL", get("PUBLIC_BASE_URL")),
                ("REDIS_URL", get("REDIS_URL")),
                ("METRICS_TOKEN", get("METRICS_TOKEN")),
                ("MEDIA_R2_ENDPOINT_URL", get("MEDIA_R2_ENDPOINT_URL")),
                ("MEDIA_R2_ACCESS_KEY_ID", get("MEDIA_R2_ACCESS_KEY_ID")),
                ("MEDIA_R2_SECRET_ACCESS_KEY", get("MEDIA_R2_SECRET_ACCESS_KEY")),
                ("MEDIA_R2_BUCKET", get("MEDIA_R2_BUCKET")),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")

        secret = str(get("SECRET_KEY"))
        lowered_secret = secret.lower()
        if len(secret) < 32 or len(set(secret)) < 12 or any(marker in lowered_secret for marker in ("replace-with", "change-me", "changeme", "placeholder", "local-development", "test-secret")):
            raise RuntimeError("SECRET_KEY must be a strong non-placeholder value of at least 32 characters")

        database_url = str(get("SQLALCHEMY_DATABASE_URI"))
        if database_url.startswith("sqlite:"):
            raise RuntimeError("Production DATABASE_URL must not use SQLite")

        public_url = urlsplit(str(get("PUBLIC_BASE_URL")))
        if public_url.scheme != "https" or not public_url.netloc or public_url.username or public_url.query or public_url.fragment or public_url.path not in {"", "/"}:
            raise RuntimeError("PUBLIC_BASE_URL must be an HTTPS origin in production")

        if not get("SESSION_COOKIE_SECURE"):
            raise RuntimeError("SESSION_COOKIE_SECURE must be true in production")

        if get("ASAAS_ENV") != "production":
            raise RuntimeError("ASAAS_ENV must be production in production")
        if get("ASAAS_API_BASE_URL") != "https://api.asaas.com/v3":
            raise RuntimeError("ASAAS_API_BASE_URL must match ASAAS_ENV exactly")

        for name in ("GEMINI_API_KEY", "ASAAS_API_KEY"):
            credential = get(name)
            if credential and (
                len(str(credential)) < 20
                or any(marker in str(credential).lower() for marker in ("replace", "change", "placeholder", "fake-key", "test-key"))
            ):
                raise RuntimeError(f"{name} must be a non-placeholder credential")

        if get("ASAAS_API_KEY") and not get("ASAAS_WEBHOOK_TOKEN"):
            raise RuntimeError("ASAAS_WEBHOOK_TOKEN is required when ASAAS_API_KEY is set")
        webhook_token = get("ASAAS_WEBHOOK_TOKEN")
        if get("ASAAS_API_KEY") and (
            len(str(webhook_token)) < 32
            or len(set(str(webhook_token))) < 12
            or any(marker in str(webhook_token).lower() for marker in ("replace", "change", "placeholder", "test-secret"))
        ):
            raise RuntimeError("ASAAS_WEBHOOK_TOKEN must be a strong non-placeholder value")

        cors_origins = get("CORS_ORIGINS")
        if not cors_origins:
            raise RuntimeError("CORS_ORIGINS must be configured in production")
        if any("*" in origin for origin in cors_origins):
            raise RuntimeError("Wildcard CORS is not allowed in production")

        if not get("CSRF_PROTECTION"):
            raise RuntimeError("CSRF_PROTECTION must be enabled in production")

        if get("AI_ASYNC_ENABLED") and not get("CELERY_BROKER_URL"):
            raise RuntimeError("CELERY_BROKER_URL or REDIS_URL is required for asynchronous AI jobs")

        metrics_token = str(get("METRICS_TOKEN"))
        if len(metrics_token) < 32 or len(set(metrics_token)) < 12:
            raise RuntimeError("METRICS_TOKEN must be a strong value of at least 32 characters")
