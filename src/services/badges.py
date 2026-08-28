from datetime import datetime

from src.models.user import AchievementUnlock, User, UserBadge, ProfileHighlight, db
from src.services.achievements import ACHIEVEMENTS, serialize_unlock


BADGE_CODES = {
    "pioneiro": {
        "title": "Pioneiro",
        "description": "Uma das 100 primeiras contas do Fit-Tracker.AI.",
    },
    "desde_sempre": {
        "title": "Desde Sempre",
        "description": "Conta criada até o fim de 2026.",
    },
}

PROFILE_HIGHLIGHT_LIMIT = 3

# 2026-12-31 23:59:59 no horário de Brasília (UTC-03:00), convertido para UTC.
EARLY_ADOPTER_CUTOFF_UTC = datetime(2027, 1, 1, 2, 59, 59)
PIONEER_LIMIT = 100


def badge_definition(code):
    return BADGE_CODES.get(code, {})


def serialize_badge(badge):
    definition = badge_definition(badge.badge_code)
    return {
        "id": badge.id,
        "code": badge.badge_code,
        "title": definition.get("title", badge.badge_code),
        "description": definition.get("description", ""),
        "badge_rank": badge.badge_rank,
        "source": badge.source,
        "granted_at": badge.granted_at.isoformat() if badge.granted_at else None,
    }


def serialize_badges(items):
    return [serialize_badge(item) for item in items]


def _achievement_catalog_item(code, definition, unlocked=None):
    return {
        "kind": "achievement",
        "code": code,
        "title": definition.get("title", code),
        "description": definition.get("description", ""),
        "unlocked": serialize_unlock(unlocked) if unlocked else None,
    }


def _badge_catalog_item(code, definition, badge=None):
    return {
        "kind": "badge",
        "code": code,
        "title": definition.get("title", code),
        "description": definition.get("description", ""),
        "badge": serialize_badge(badge) if badge else None,
    }


def serialize_profile_highlight(highlight):
    if highlight.target_kind == "achievement" and highlight.achievement_unlock:
        item = serialize_unlock(highlight.achievement_unlock)
    elif highlight.target_kind == "badge" and highlight.user_badge:
        item = serialize_badge(highlight.user_badge)
    else:
        item = None
    return {
        "id": highlight.id,
        "position": highlight.position,
        "target_kind": highlight.target_kind,
        "achievement_unlock_id": highlight.achievement_unlock_id,
        "user_badge_id": highlight.user_badge_id,
        "item": item,
        "created_at": highlight.created_at.isoformat() if highlight.created_at else None,
    }


def serialize_profile_highlights(items):
    return [serialize_profile_highlight(item) for item in items]


def _grant_badge(user, code, badge_rank=None, source="backfill"):
    existing = UserBadge.query.filter_by(user_id=user.id, badge_code=code).first()
    if existing:
        return existing
    badge = UserBadge(
        user_id=user.id,
        badge_code=code,
        badge_rank=badge_rank,
        source=source,
    )
    db.session.add(badge)
    return badge


def _eligible_since_always(user):
    return bool(user.created_at and user.created_at <= EARLY_ADOPTER_CUTOFF_UTC)


def _pioneer_rank_for_user(user):
    ordered_ids = [
        item[0]
        for item in User.query.with_entities(User.id)
        .order_by(User.created_at.asc(), User.id.asc())
        .limit(PIONEER_LIMIT)
        .all()
    ]
    try:
        return ordered_ids.index(user.id) + 1
    except ValueError:
        return None


def grant_signup_badges(user):
    granted = []
    if _eligible_since_always(user):
        granted.append(_grant_badge(user, "desde_sempre", source="signup"))
    rank = _pioneer_rank_for_user(user)
    if rank is not None and rank <= PIONEER_LIMIT:
        granted.append(_grant_badge(user, "pioneiro", badge_rank=rank, source="signup"))
    db.session.flush()
    return granted


def backfill_historical_badges():
    granted = []
    pioneer_users = (
        User.query.order_by(User.created_at.asc(), User.id.asc()).limit(PIONEER_LIMIT).all()
    )
    for rank, user in enumerate(pioneer_users, start=1):
        granted.append(_grant_badge(user, "pioneiro", badge_rank=rank, source="backfill"))

    early_adopters = User.query.filter(User.created_at <= EARLY_ADOPTER_CUTOFF_UTC).all()
    for user in early_adopters:
        granted.append(_grant_badge(user, "desde_sempre", source="backfill"))

    db.session.flush()
    return granted


def available_profile_items(user):
    achievement_unlocks = {
        item.achievement_code: item
        for item in AchievementUnlock.query.filter_by(user_id=user.id).all()
    }
    badges = {item.badge_code: item for item in UserBadge.query.filter_by(user_id=user.id).all()}
    achievement_items = [
        _achievement_catalog_item(code, definition, achievement_unlocks.get(code))
        for code, definition in ACHIEVEMENTS.items()
        if achievement_unlocks.get(code)
    ]
    badge_items = [
        _badge_catalog_item(code, definition, badges.get(code))
        for code, definition in BADGE_CODES.items()
        if badges.get(code)
    ]
    return achievement_items + badge_items


def apply_profile_highlights(user, selections):
    normalized = []
    seen = set()
    for item in selections:
        kind = str(item.get("kind", "")).strip()
        code = str(item.get("code", "")).strip()
        if kind not in {"achievement", "badge"} or not code:
            continue
        token = (kind, code)
        if token in seen:
            continue
        seen.add(token)
        normalized.append({"kind": kind, "code": code})
    if len(normalized) > PROFILE_HIGHLIGHT_LIMIT:
        raise ValueError("É possível fixar no máximo 3 destaques.")

    achievement_unlocks = {
        item.achievement_code: item
        for item in AchievementUnlock.query.filter_by(user_id=user.id).all()
    }
    badges = {item.badge_code: item for item in UserBadge.query.filter_by(user_id=user.id).all()}

    current = {highlight.position: highlight for highlight in ProfileHighlight.query.filter_by(user_id=user.id).all()}
    desired_items = []
    for index, item in enumerate(normalized, start=1):
        if item["kind"] == "achievement":
            target = achievement_unlocks.get(item["code"])
            if target is None:
                raise ValueError("Você só pode fixar conquistas que já desbloqueou.")
            desired_items.append((index, "achievement", target, None))
        else:
            target = badges.get(item["code"])
            if target is None:
                raise ValueError("Você só pode fixar insígnias que já possui.")
            desired_items.append((index, "badge", None, target))

    # Remove highlights not requested anymore.
    requested_positions = {position for position, *_ in desired_items}
    for position, highlight in list(current.items()):
        if position not in requested_positions:
            db.session.delete(highlight)

    # Upsert requested highlights.
    for position, kind, achievement, badge in desired_items:
        highlight = current.get(position)
        if highlight is None:
            highlight = ProfileHighlight(user_id=user.id, position=position, target_kind=kind)
            db.session.add(highlight)
        highlight.target_kind = kind
        highlight.achievement_unlock_id = achievement.id if achievement else None
        highlight.user_badge_id = badge.id if badge else None

    db.session.flush()
    return ProfileHighlight.query.filter_by(user_id=user.id).order_by(ProfileHighlight.position.asc()).all()
