from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from src.models.user import GamificationAward, GamificationDay, GamificationProfile, User, db
from src.services.workout_progress import user_timezone


XP_PER_ACTION = {"meal": 20, "water": 10, "workout": 100}


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
    newly_qualified = not (day.first_action_bonus or day.meal or day.water or day.workout or day.rest_checkin)
    setattr(day, action, True)
    gained = XP_PER_ACTION[action]
    day.xp += gained
    if newly_qualified:
        day.first_action_bonus = True
        if action == "water":
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


def record_meal_xp(user_id, local_date, source_key, planned_meals=3, analysis=False, timezone_name=None):
    """Award up to 100 meal-related XP per local day, once per confirmed source."""
    timezone_name = timezone_name or user_timezone(user_id)
    today = datetime.now(ZoneInfo(timezone_name)).date()
    if local_date != today or not source_key:
        return 0
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
    if GamificationAward.query.filter_by(user_id=user_id, action="meal", source_key=source_key).first():
        return 0
    already_awarded = db.session.query(func.coalesce(func.sum(GamificationAward.xp), 0)).filter_by(
        user_id=user_id, action="meal", local_date=local_date,
    ).scalar() or 0
    meal_share = max(1, 100 // max(1, min(10, int(planned_meals or 3))))
    requested = min(100, max(meal_share + 1, 80)) if analysis else meal_share
    gained = max(0, min(requested, 100 - int(already_awarded)))
    db.session.add(GamificationAward(user_id=user_id, action="meal", source_key=source_key,
                                     local_date=local_date, xp=gained))
    _activate_day(profile, day, local_date)
    day.meal = True
    day.xp += gained
    return gained


def record_water_xp(user_id, local_date, source_key, timezone_name=None):
    """Reward each hydration entry, capped at 40 XP per local day."""
    timezone_name = timezone_name or user_timezone(user_id)
    today = datetime.now(ZoneInfo(timezone_name)).date()
    if local_date != today or not source_key:
        return 0
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
    if GamificationAward.query.filter_by(user_id=user_id, action="water", source_key=source_key).first():
        return 0
    already_awarded = db.session.query(func.coalesce(func.sum(GamificationAward.xp), 0)).filter_by(
        user_id=user_id, action="water", local_date=local_date,
    ).scalar() or 0
    first_action = not (day.first_action_bonus or day.meal or day.water or day.workout or day.rest_checkin)
    requested = 30 if first_action else 10
    gained = max(0, min(requested, 40 - int(already_awarded)))
    db.session.add(GamificationAward(user_id=user_id, action="water", source_key=source_key,
                                     local_date=local_date, xp=gained))
    if first_action:
        _activate_day(profile, day, local_date)
    day.water = True
    day.xp += gained
    return gained


def award_plan_generation(user_id, plan_type, source_key):
    if plan_type not in {"diet", "workout"}:
        return 0
    timezone_name = user_timezone(user_id)
    today = datetime.now(ZoneInfo(timezone_name)).date()
    now = datetime.utcnow()
    User.query.filter_by(id=user_id).with_for_update(key_share=True).first()
    profile = GamificationProfile.query.filter_by(user_id=user_id).with_for_update().first()
    if profile is None:
        profile = GamificationProfile(user_id=user_id)
        db.session.add(profile)
        db.session.flush()
    if not source_key or GamificationAward.query.filter_by(
        user_id=user_id, action=f"plan_{plan_type}", source_key=source_key,
    ).first():
        return 0
    field = f"last_{plan_type}_plan_xp_at"
    last_award = getattr(profile, field)
    if last_award and now - last_award < timedelta(days=30):
        return 0
    gained = 500
    day = GamificationDay.query.filter_by(user_id=user_id, local_date=today).with_for_update().first()
    if day is None:
        day = GamificationDay(user_id=user_id, local_date=today, timezone=timezone_name)
        db.session.add(day)
        db.session.flush()
    db.session.add(GamificationAward(user_id=user_id, action=f"plan_{plan_type}", source_key=source_key,
                                     local_date=today, xp=gained))
    day.xp += gained
    setattr(profile, field, now)
    _activate_day(profile, day, today)
    return gained


def award_rest_day_checkin(user_id):
    timezone_name = user_timezone(user_id)
    today = datetime.now(ZoneInfo(timezone_name)).date()
    User.query.filter_by(id=user_id).with_for_update(key_share=True).first()
    profile = GamificationProfile.query.filter_by(user_id=user_id).with_for_update().first()
    if profile is None:
        profile = GamificationProfile(user_id=user_id)
        db.session.add(profile)
        db.session.flush()
    day = GamificationDay.query.filter_by(user_id=user_id, local_date=today).with_for_update().first()
    if day is None:
        day = GamificationDay(user_id=user_id, local_date=today, timezone=timezone_name)
        db.session.add(day)
        db.session.flush()
    if day.rest_checkin:
        return 0
    _activate_day(profile, day, today)
    day.rest_checkin = True
    day.xp += 100
    return 100


def _activate_day(profile, day, local_date):
    if day.first_action_bonus or day.meal or day.water or day.workout or day.rest_checkin:
        # The daily fields already identify an active day; plan and meal awards
        # can arrive after the first action without extending the streak twice.
        return
    day.first_action_bonus = True
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
        # Builds 32/33 decode these acronym properties without snake-case conversion.
        "totalXP": total_xp,
        "levelXP": level_xp,
        "nextLevelXP": next_level_xp,
        "next_level": level + 1,
        "current_streak": current_streak,
        "best_streak": profile.best_streak if profile else 0,
        "active_days": profile.active_days if profile else 0,
        "available_protections": profile.available_protections if profile else 0,
        "today": {
            "qualified": bool(today_row and (today_row.meal or today_row.water or today_row.workout or today_row.rest_checkin or today_row.xp > 0)),
            "meal": bool(today_row and today_row.meal),
            "water": bool(today_row and today_row.water),
            "workout": bool(today_row and today_row.workout),
            "rest_checkin": bool(today_row and today_row.rest_checkin),
            "xp": today_row.xp if today_row else 0,
        },
        "days": [
            {"date": day.isoformat(), "qualified": bool(by_date.get(day) and (by_date[day].meal or by_date[day].water or by_date[day].workout or by_date[day].rest_checkin or by_date[day].xp > 0))}
            for day in (today - timedelta(days=offset) for offset in range(27, -1, -1))
        ],
    }


def gamification_metrics(user_id):
    days = GamificationDay.query.filter_by(user_id=user_id).order_by(GamificationDay.local_date.asc()).all()
    meals = sum(bool(day.meal) for day in days)
    waters = sum(bool(day.water) for day in days)
    active = [day.local_date for day in days if day.meal or day.water or day.workout or day.rest_checkin or day.xp > 0]
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
