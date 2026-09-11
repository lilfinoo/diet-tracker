"""Daily consistency: one dietary source per date, never combined counters."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.models.user import DietAdherenceDay, DietEntry, DietMealDailyState, WorkoutSession
from src.services.workout_progress import user_timezone


def consistency_days(user_id, now=None):
    zone = ZoneInfo(user_timezone(user_id))
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    today = instant.astimezone(zone).date()
    start = today - timedelta(days=today.weekday(), weeks=7)
    days = {}
    for offset in range((today - start).days + 1):
        day = start + timedelta(days=offset)
        days[day] = {"date": day.isoformat(), "workout": False, "diet_tracked": False, "diet_source": None, "diet_states": ["no_information"]}
    # Keep the recorded local date. For pre-snapshot sessions use the user's timezone.
    sessions = WorkoutSession.query.filter(
        WorkoutSession.user_id == user_id,
        WorkoutSession.completed_at.isnot(None),
        WorkoutSession.completed_at >= datetime.combine(start - timedelta(days=1), datetime.min.time()),
        WorkoutSession.completions.any(),
    ).all()
    for session in sessions:
        day = session.completed_local_date or session.completed_at.replace(tzinfo=timezone.utc).astimezone(zone).date()
        if day in days and session.completed_at <= instant.astimezone(timezone.utc).replace(tzinfo=None):
            days[day]["workout"] = True
    states = DietMealDailyState.query.filter(
        DietMealDailyState.user_id == user_id,
        DietMealDailyState.local_date.between(start, today),
    ).order_by(DietMealDailyState.local_date, DietMealDailyState.slot_key).all()
    for state in states:
        day = days[state.local_date]
        if day["diet_source"] is None:
            day["diet_source"] = "daily_state"
            day["diet_states"] = []
        if state.result not in day["diet_states"]:
            day["diet_states"].append(state.result)
        day["diet_tracked"] = any(value != "pending" for value in day["diet_states"])
    legacy = DietAdherenceDay.query.filter(
        DietAdherenceDay.user_id == user_id,
        DietAdherenceDay.local_date.between(start, today),
    ).all()
    mapping = {"completed": "consumed_planned", "substituted": "consumed_different", "skipped": "skipped"}
    for record in legacy:
        day = days[record.local_date]
        if day["diet_source"] is not None:
            continue
        day["diet_source"] = "legacy_adherence"
        day["diet_states"] = sorted({mapping[item.status] for item in record.meal_checkins})
        day["diet_tracked"] = bool(record.meal_checkins)
        if record.status == "in_progress":
            day["diet_states"].append("pending")
        if not day["diet_states"]:
            day["diet_states"] = ["no_information"]
    # Manual entries are evidence of tracking only, never of following a plan.
    manual_dates = DietEntry.query.with_entities(DietEntry.date).filter(
        DietEntry.user_id == user_id, DietEntry.date.between(start, today),
        DietEntry.daily_meal_state_id.is_(None),
    ).distinct().all()
    for (day_date,) in manual_dates:
        day = days[day_date]
        if day["diet_source"] is None:
            day.update(diet_source="manual_entry", diet_tracked=True, diet_states=["recorded_unclassified"])
    return {"start_date": start.isoformat(), "end_date": today.isoformat(), "days": list(days.values())}
