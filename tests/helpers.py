from src.legal import AI_CONSENT_VERSION


def consent_payload(*, ai_consent=True):
    return {
        "ai_consent": ai_consent,
        "ai_consent_version": AI_CONSENT_VERSION,
    }


def registration_payload(username, password="strong-password", *, ai_consent=True, **extra):
    return {
        "username": username,
        "password": password,
        **consent_payload(ai_consent=ai_consent),
        **extra,
    }
