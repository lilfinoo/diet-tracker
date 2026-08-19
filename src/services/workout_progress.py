from datetime import date, datetime, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_

from src.models.user import (
    ExerciseGoal,
    PersonalRecordEvent,
    UserProfile,
    WorkoutSession,
    WorkoutWeeklyGoal,
    db,
)


DEFAULT_TIMEZONE = "UTC"
_CURRENT_MAX_UNSET = object()


def validate_timezone(value):
    """Return a validated IANA timezone name."""
    if isinstance(value, ZoneInfo):
        value = value.key
    if not isinstance(value, str):
        raise ValueError("Timezone must be a valid IANA name")
    value = value.strip()
    if not value or len(value) > 64:
        raise ValueError("Timezone must be a valid IANA name")
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("Timezone must be a valid IANA name") from error
    return value


def user_timezone(user_id):
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if profile and profile.timezone:
        return validate_timezone(profile.timezone)

    latest_goal = (
        WorkoutWeeklyGoal.query.filter_by(user_id=user_id)
        .order_by(
            WorkoutWeeklyGoal.effective_week_start.desc(),
            WorkoutWeeklyGoal.created_at.desc(),
            WorkoutWeeklyGoal.id.desc(),
        )
        .first()
    )
    return validate_timezone(latest_goal.timezone) if latest_goal else DEFAULT_TIMEZONE


def confirmed_user_timezone(user_id):
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if profile and profile.timezone:
        return validate_timezone(profile.timezone)
    latest_goal = WorkoutWeeklyGoal.query.filter_by(user_id=user_id).order_by(
        WorkoutWeeklyGoal.effective_week_start.desc(),
        WorkoutWeeklyGoal.id.desc(),
    ).first()
    return validate_timezone(latest_goal.timezone) if latest_goal else None


def _aware_utc(value=None):
    if value is None:
        return datetime.now(datetime_timezone.utc)
    if not isinstance(value, datetime):
        raise ValueError("now must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime_timezone.utc)
    return value.astimezone(datetime_timezone.utc)


def _monday(value):
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise ValueError("Week start must be a date")
    return value - timedelta(days=value.weekday())


def week_start_for(value, timezone=DEFAULT_TIMEZONE):
    timezone_name = validate_timezone(timezone)
    local_date = _aware_utc(value).astimezone(ZoneInfo(timezone_name)).date()
    return _monday(local_date)


def is_qualifying_session(session):
    return bool(session and session.completed_at and session.completions)


def _timezone_from_user(user, user_id):
    if user is not None:
        profile = getattr(user, "profile", None)
        if profile and profile.timezone:
            return validate_timezone(profile.timezone)
        if isinstance(user, UserProfile) and user.timezone:
            return validate_timezone(user.timezone)

    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if profile and profile.timezone:
        return validate_timezone(profile.timezone)
    return user_timezone(user_id)


def snapshot_session_week(session, user=None, timezone=None):
    """Freeze a qualifying session's local completion day and Monday week start."""
    if not is_qualifying_session(session):
        return session
    if (
        session.completed_timezone
        and session.completed_local_date
        and session.completed_week_start
    ):
        return session

    if timezone is None and isinstance(user, (str, ZoneInfo)):
        timezone = user
        user = None

    timezone_name = session.completed_timezone
    if timezone_name:
        timezone_name = validate_timezone(timezone_name)
    elif timezone is not None:
        timezone_name = validate_timezone(timezone)
    else:
        timezone_name = _timezone_from_user(user, session.user_id)

    local_date = session.completed_local_date
    if local_date is None:
        local_date = (
            _aware_utc(session.completed_at).astimezone(ZoneInfo(timezone_name)).date()
        )

    if session.completed_timezone is None:
        session.completed_timezone = timezone_name
    if session.completed_local_date is None:
        session.completed_local_date = local_date
    if session.completed_week_start is None:
        session.completed_week_start = _monday(local_date)
    return session


def backfill_session_weeks(user_id, timezone):
    timezone_name = validate_timezone(timezone)
    sessions = (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.completions.any(),
            or_(
                WorkoutSession.completed_timezone.is_(None),
                WorkoutSession.completed_local_date.is_(None),
                WorkoutSession.completed_week_start.is_(None),
            ),
        )
        .order_by(WorkoutSession.completed_at.asc(), WorkoutSession.id.asc())
        .all()
    )
    changed = 0
    for session in sessions:
        before = (
            session.completed_timezone,
            session.completed_local_date,
            session.completed_week_start,
        )
        snapshot_session_week(session, timezone=timezone_name)
        after = (
            session.completed_timezone,
            session.completed_local_date,
            session.completed_week_start,
        )
        changed += before != after
    return changed


def serialize_weekly_goal(goal):
    if goal is None:
        return None
    return {
        "id": goal.id,
        "user_id": str(goal.user_id),
        "target_sessions": goal.target_sessions,
        "effective_week_start": goal.effective_week_start.isoformat(),
        "timezone": goal.timezone,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }


def current_weekly_goal(user_id, week_start=None, *, now=None, timezone=None):
    if isinstance(week_start, datetime) and now is None:
        now = week_start
        week_start = None
    if week_start is None:
        timezone_name = validate_timezone(timezone or user_timezone(user_id))
        week_start = week_start_for(now, timezone_name)
    else:
        week_start = _monday(week_start)

    return (
        WorkoutWeeklyGoal.query.filter(
            WorkoutWeeklyGoal.user_id == user_id,
            WorkoutWeeklyGoal.effective_week_start <= week_start,
        )
        .order_by(
            WorkoutWeeklyGoal.effective_week_start.desc(),
            WorkoutWeeklyGoal.created_at.desc(),
            WorkoutWeeklyGoal.id.desc(),
        )
        .first()
    )


def _target_sessions(value):
    if isinstance(value, bool):
        raise ValueError("target_sessions must be between 1 and 14")
    try:
        target = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("target_sessions must be between 1 and 14") from error
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("target_sessions must be between 1 and 14")
    if not 1 <= target <= 14:
        raise ValueError("target_sessions must be between 1 and 14")
    return target


def create_weekly_goal(
    user_id,
    target_sessions,
    timezone=None,
    *,
    now=None,
    effective_week_start=None,
):
    target = _target_sessions(target_sessions)
    timezone_name = validate_timezone(timezone or user_timezone(user_id))
    if effective_week_start is None:
        effective_week_start = week_start_for(now, timezone_name)
    else:
        if isinstance(effective_week_start, datetime):
            effective_week_start = effective_week_start.date()
        if not isinstance(effective_week_start, date) or effective_week_start.weekday() != 0:
            raise ValueError("effective_week_start must be a Monday")

    goal = WorkoutWeeklyGoal.query.filter_by(
        user_id=user_id,
        effective_week_start=effective_week_start,
    ).first()
    if goal is None:
        goal = WorkoutWeeklyGoal(
            user_id=user_id,
            target_sessions=target,
            effective_week_start=effective_week_start,
            timezone=timezone_name,
        )
        db.session.add(goal)
    else:
        goal.target_sessions = target
        goal.timezone = timezone_name
    db.session.flush()
    return goal


def suggested_days_per_week(user_id):
    recent_session = (
        WorkoutSession.query.filter_by(user_id=user_id)
        .order_by(WorkoutSession.started_at.desc(), WorkoutSession.id.desc())
        .first()
    )
    if recent_session is None or recent_session.plan is None:
        return None
    days_per_week = recent_session.plan.days_per_week
    if isinstance(days_per_week, int) and 1 <= days_per_week <= 14:
        return days_per_week
    return None


def suggest_weekly_target(user_id):
    return suggested_days_per_week(user_id)


def _goal_for_week(goals, week_start):
    applicable = None
    for goal in goals:
        if goal.effective_week_start > week_start:
            break
        applicable = goal
    return applicable


def weekly_progress(user_id, now=None):
    timezone_name = user_timezone(user_id)
    current_week_start = week_start_for(now, timezone_name)
    confirmed_timezone = confirmed_user_timezone(user_id)
    if confirmed_timezone:
        backfill_session_weeks(user_id, confirmed_timezone)

    goals = (
        WorkoutWeeklyGoal.query.filter(
            WorkoutWeeklyGoal.user_id == user_id,
            WorkoutWeeklyGoal.effective_week_start <= current_week_start,
        )
        .order_by(
            WorkoutWeeklyGoal.effective_week_start.asc(),
            WorkoutWeeklyGoal.created_at.asc(),
            WorkoutWeeklyGoal.id.asc(),
        )
        .all()
    )
    counts = dict(
        db.session.query(
            WorkoutSession.completed_week_start,
            func.count(WorkoutSession.id),
        )
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.completed_week_start.isnot(None),
            WorkoutSession.completed_week_start <= current_week_start,
            WorkoutSession.completions.any(),
        )
        .group_by(WorkoutSession.completed_week_start)
        .all()
    )

    current_goal = _goal_for_week(goals, current_week_start)
    completed = int(counts.get(current_week_start, 0))
    target = current_goal.target_sessions if current_goal else None
    fulfilled = target is not None and completed >= target

    streak = 0
    week = current_week_start if fulfilled else current_week_start - timedelta(days=7)
    earliest_goal_week = goals[0].effective_week_start if goals else None
    while earliest_goal_week is not None and week >= earliest_goal_week:
        goal = _goal_for_week(goals, week)
        if goal is None or int(counts.get(week, 0)) < goal.target_sessions:
            break
        streak += 1
        week -= timedelta(days=7)

    suggested_target = suggested_days_per_week(user_id)
    return {
        "timezone": timezone_name,
        "current": {
            "week_start": current_week_start.isoformat(),
            "week_end": (current_week_start + timedelta(days=6)).isoformat(),
            "completed": completed,
            "target": target,
            "fulfilled": fulfilled,
            "streak": streak,
        },
        "goal": serialize_weekly_goal(current_goal),
        "suggestion": (
            {
                "days_per_week": suggested_target,
                "target_sessions": suggested_target,
            }
            if suggested_target is not None
            else None
        ),
    }


def _current_max_load(user_id, exercise_key):
    value = (
        db.session.query(func.max(PersonalRecordEvent.new_value))
        .filter(
            PersonalRecordEvent.user_id == user_id,
            PersonalRecordEvent.exercise_key == exercise_key,
            PersonalRecordEvent.metric_type == "max_load",
        )
        .scalar()
    )
    return float(value) if value is not None else None


def current_max_load(user_id, exercise_key):
    return _current_max_load(user_id, exercise_key)


def current_exercise_goal(user_id):
    return (
        ExerciseGoal.query.filter_by(user_id=user_id, status="active")
        .order_by(ExerciseGoal.created_at.desc(), ExerciseGoal.id.desc())
        .first()
    )


def current_active_exercise_goal(user_id):
    return current_exercise_goal(user_id)


def serialize_exercise_goal(goal, current_max_load=_CURRENT_MAX_UNSET):
    if goal is None:
        return None
    if current_max_load is _CURRENT_MAX_UNSET:
        current_max_load = _current_max_load(goal.user_id, goal.exercise_key)
    return {
        "id": str(goal.id) if goal.id else None,
        "user_id": str(goal.user_id),
        "exercise_key": goal.exercise_key,
        "exercise_name": goal.exercise_name,
        "target_load_kg": float(goal.target_load_kg),
        "current_max_load": (
            float(current_max_load) if current_max_load is not None else None
        ),
        "status": goal.status,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "achieved_at": goal.achieved_at.isoformat() if goal.achieved_at else None,
        "achieved_session_id": goal.achieved_session_id,
    }


def complete_exercise_goal(session):
    if not is_qualifying_session(session):
        return None
    goal = (
        ExerciseGoal.query.filter_by(user_id=session.user_id, status="active")
        .with_for_update()
        .first()
    )
    if goal is None:
        return None

    event = (
        PersonalRecordEvent.query.filter(
            PersonalRecordEvent.user_id == session.user_id,
            PersonalRecordEvent.workout_session_id == session.id,
            PersonalRecordEvent.exercise_key == goal.exercise_key,
            PersonalRecordEvent.metric_type == "max_load",
            PersonalRecordEvent.new_value >= goal.target_load_kg,
        )
        .order_by(PersonalRecordEvent.achieved_at.asc(), PersonalRecordEvent.id.asc())
        .first()
    )
    if event is None:
        return None

    goal.status = "achieved"
    goal.achieved_at = event.achieved_at or session.completed_at
    goal.achieved_session_id = session.id
    return goal
