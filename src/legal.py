from datetime import datetime


TERMS_VERSION = "draft-2026-08-29"
PRIVACY_VERSION = "draft-2026-08-29"
AI_CONSENT_VERSION = "draft-2026-08-29"
PROFESSIONAL_SHARING_VERSION = "draft-2026-08-29"


def record_consent(user, document_type, version, granted, source):
    from src.models.user import ConsentRecord, db

    now = datetime.utcnow()
    db.session.add(ConsentRecord(
        user_id=user.id,
        document_type=document_type,
        version=version,
        granted=granted,
        source=source,
        created_at=now,
    ))
    if document_type == "terms" and granted:
        user.terms_version = version
        user.terms_accepted_at = now
    elif document_type == "privacy" and granted:
        user.privacy_version = version
        user.privacy_accepted_at = now
    elif document_type == "ai":
        user.ai_consent_version = version if granted else None
        user.ai_consent_at = now if granted else None


def legal_versions_payload():
    return {
        "terms": {"version": TERMS_VERSION, "url": "/terms.html"},
        "privacy": {"version": PRIVACY_VERSION, "url": "/privacy.html"},
        "ai": {"version": AI_CONSENT_VERSION},
        "professional_sharing": {"version": PROFESSIONAL_SHARING_VERSION},
    }
