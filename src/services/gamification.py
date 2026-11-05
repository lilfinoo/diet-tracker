from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func

from src.models.user import GamificationDay, GamificationProfile, User, db
from src.services.workout_progress import user_timezone


XP_PER_ACTION = {"meal": 20, "water": 10, "workout": 30}


def level_for_xp(total_xp):
    level = 1
    remaining = max(0, int(total_xp or 0))
    while remaining >= 100 + 25 * (level - 1):
        remaining -= 100 + 25 * (level - 1)
        level += 1
    return level, remaining, 100 + 25 * (level - 1)


def rank_for_level(level):
    if level >= 50:
        return "Mestre"
    if level >= 30:
        return "Diamante"
    if level >= 20:
        return "Platina"
    if level >= 10:
        return "Ouro"
    if level >= 5:
        return "Prata"
    return "Bronze"


def record_gamification_action(user_id, action, local_date, timezone_name=None):
    if action not in XP_PER_ACTION or not isinstance(local_date, date):
        return 0
    timezone_name = timezone_name or user_timezone(user_id)
    today = datetime.now(ZoneInfo(timezone_name)).date()
    if local_date != today:
        return 0

    # Serialize awards without upgrading foreign-key locks held by concurrent logs.
    User.query.filter_by(id=user_id).with_for_update(key_share=True).first()
    profile = GamificationProfile.query.filter_by(user_id=user_id).with_for_update().first()
    if profile is None:
        profile = GamificationProfile(user_id=user_id)
        db.session.add(profile)
        db.session.flush()
    day = GamificationDay.query.filter_by(user_id=user_id, local_date=local_date).with_for_update().first()
    if day is None:
        day = GamificationDay(user_id=user_id, local_date=local_date, timezone=timezone_name)
        db.session.add(day)
        db.session.flush()

    if getattr(day, action):
        return 0
    newly_qualified = not (day.meal or day.water or day.workout)
    setattr(day, action, True)
    gained = XP_PER_ACTION[action]
    day.xp += gained
    if newly_qualified:
        day.first_action_bonus = True
        day.xp += 20
        gained += 20
        if profile.last_active_date is None:
            profile.current_streak = 1
        elif local_date > profile.last_active_date:
            gap = (local_date - profile.last_active_date).days - 1
            if gap and gap <= profile.available_protections:
                profile.available_protections -= gap
                profile.current_streak += 1
            elif gap == 0:
                profile.current_streak += 1
            else:
                if gap >= 7:
                    day.return_earned = True
                profile.current_streak = 1
            profile.last_active_date = local_date
        profile.active_days += 1
        profile.best_streak = max(profile.best_streak, profile.current_streak)
        if profile.active_days % 7 == 0:
            profile.available_protections = min(2, profile.available_protections + 1)
        if profile.last_active_date is None:
            profile.last_active_date = local_date
    return gained


def gamification_summary(user_id):
    timezone_name = user_timezone(user_id)
    today = datetime.now(ZoneInfo(timezone_name)).date()
    profile = GamificationProfile.query.filter_by(user_id=user_id).first()
    today_row = GamificationDay.query.filter_by(user_id=user_id, local_date=today).first()
    total_xp = int(db.session.query(func.coalesce(func.sum(GamificationDay.xp), 0)).filter_by(user_id=user_id).scalar() or 0)
    level, level_xp, next_level_xp = level_for_xp(total_xp)
    current_streak = profile.current_streak if profile and profile.last_active_date and (today - profile.last_active_date).days <= max(1, profile.available_protections + 1) else 0
    recent = GamificationDay.query.filter(
        GamificationDay.user_id == user_id,
        GamificationDay.local_date >= today - timedelta(days=27),
    ).order_by(GamificationDay.local_date.asc()).all()
    by_date = {item.local_date: item for item in recent}
    return {
        "total_xp": total_xp,
        "level": level,
        "rank": rank_for_level(level),
        "level_xp": level_xp,
        "next_level_xp": next_level_xp,
        "next_level": level + 1,
        "current_streak": current_streak,
        "best_streak": profile.best_streak if profile else 0,
        "active_days": profile.active_days if profile else 0,
        "available_protections": profile.available_protections if profile else 0,
        "today": {
            "qualified": bool(today_row and (today_row.meal or today_row.water or today_row.workout)),
            "meal": bool(today_row and today_row.meal),
            "water": bool(today_row and today_row.water),
            "workout": bool(today_row and today_row.workout),
            "xp": today_row.xp if today_row else 0,
        },
        "days": [
            {"date": day.isoformat(), "qualified": bool(by_date.get(day) and (by_date[day].meal or by_date[day].water or by_date[day].workout))}
            for day in (today - timedelta(days=offset) for offset in range(27, -1, -1))
        ],
    }


def gamification_metrics(user_id):
    days = GamificationDay.query.filter_by(user_id=user_id).order_by(GamificationDay.local_date.asc()).all()
    meals = sum(bool(day.meal) for day in days)
    waters = sum(bool(day.water) for day in days)
    active = [day.local_date for day in days if day.meal or day.water or day.workout]
    max_streak = streak = 0
    previous = None
    for item in active:
        streak = streak + 1 if previous and item == previous + timedelta(days=1) else 1
        max_streak = max(max_streak, streak)
        previous = item
    return {
        "meal_days": meals,
        "water_days": waters,
        "active_days": len(active),
        "streak_days": max_streak,
        "returns": sum(bool(day.return_earned) for day in days),
    }
