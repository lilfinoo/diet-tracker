import logging
import re


_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_INVITATION_TOKEN = re.compile(r"(/api/invitations/)[^/?\s]+")
_SECRET = re.compile(
    r"(?i)(access[_-]?token|authorization|api[_-]?key|credential|password)(\s*[=:]\s*)([^\s,;]+)"
)


def _redact(value):
    text = _EMAIL.sub("[redacted-email]", str(value))
    text = _UUID.sub("[redacted-uuid]", text)
    text = _INVITATION_TOKEN.sub(r"\1[redacted]", text)
    return _SECRET.sub(r"\1\2[redacted]", text)


class PrivacyLogFilter(logging.Filter):
    def filter(self, record):
        record.msg = _redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            exception_type = record.exc_info[0].__name__
            record.msg = f"{record.msg} exception={exception_type}"
            record.exc_info = None
            record.exc_text = None
        return True


def install_privacy_log_filter(app):
    privacy_filter = PrivacyLogFilter()
    loggers = (
        app.logger,
        logging.getLogger(),
        logging.getLogger("werkzeug"),
        logging.getLogger("gunicorn.error"),
        logging.getLogger("gunicorn.access"),
        logging.getLogger("celery"),
    )
    for logger in loggers:
        logger.addFilter(privacy_filter)
        for handler in logger.handlers:
            handler.addFilter(privacy_filter)
