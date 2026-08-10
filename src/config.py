import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _csv(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'diet_tracker.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
    CORS_ORIGINS = _csv("CORS_ORIGINS")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-flash-lite-latest")
    GEMINI_STRUCTURED_MODEL = os.getenv("GEMINI_STRUCTURED_MODEL", "gemini-flash-lite-latest")
    GEMINI_PLAN_MODEL = os.getenv("GEMINI_PLAN_MODEL", "gemini-flash-latest")
    GEMINI_CHAT_MAX_TOKENS = int(os.getenv("GEMINI_CHAT_MAX_TOKENS", "768"))
    GEMINI_PLAN_MAX_TOKENS = int(os.getenv("GEMINI_PLAN_MAX_TOKENS", "12288"))
    GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "240"))


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SESSION_COOKIE_SECURE = False
    GEMINI_API_KEY = None
    RATE_LIMITS = {"login": (100, 60), "register": (100, 60), "ai": (100, 60)}


class ProductionConfig(Config):
    @classmethod
    def validate(cls) -> None:
        missing = [
            name
            for name, value in (
                ("SECRET_KEY", cls.SECRET_KEY),
                ("DATABASE_URL", os.getenv("DATABASE_URL")),
                ("GEMINI_API_KEY", cls.GEMINI_API_KEY),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")
