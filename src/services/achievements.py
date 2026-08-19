from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.models.user import (
    AchievementUnlock,
    ExerciseGoal,
    PersonalRecordEvent,
    WorkoutSession,
    WorkoutWeeklyGoal,
    db,
)
from src.services.workout_progress import backfill_session_weeks, user_timezone


ACHIEVEMENTS = {
    "first_step": {
        "title": "Primeiro passo",
        "description": "Conclua seu primeiro treino.",
    },
    "workout_10": {
        "title": "10 treinos",
        "description": "Conclua 10 treinos.",
    },
    "workout_50": {
        "title": "50 treinos",
        "description": "Conclua 50 treinos.",
    },
    "workout_100": {
        "title": "100 treinos",
        "description": "Conclua 100 treinos.",
    },
    "first_pr": {
        "title": "Primeiro recorde",
        "description": "Conquiste seu primeiro recorde pessoal.",
    },
    "evolving": {
        "title": "Em evolu\u00e7\u00e3o",
        "description": "Conquiste 10 recordes pessoais.",
    },
    "big_day": {
        "title": "Grande dia",
        "description": "Conquiste 3 recordes pessoais no mesmo treino.",
    },
    "first_goal": {
        "title": "Meta alcan\u00e7ada",
        "description": "Alcance sua primeira meta de carga.",
    },
    "consistent": {
        "title": "Consist\u00eancia",
        "description": "Cumpra a meta semanal por 4 semanas seguidas.",
    },
}
ACHIEVEMENT_CATALOG = ACHIEVEMENTS


@dataclass(frozen=True)
class _UnlockCandidate:
    unlocked_at: datetime
    workout_session_id: int | None = None
    exercise_goal_id: object | None = None


def _qualifying_sessions(user_id):
    return (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.completions.any(),
        )
        .order_by(WorkoutSession.completed_at.asc(), WorkoutSession.id.asc())
        .all()
    )


def _highlighted_events(user_id):
    return (
        PersonalRecordEvent.query.filter(
            PersonalRecordEvent.user_id == user_id,
            PersonalRecordEvent.is_highlighted.is_(True),
            PersonalRecordEvent.is_initial.is_(False),
        )
        .order_by(PersonalRecordEvent.achieved_at.asc(), PersonalRecordEvent.id.asc())
        .all()
    )


def _consistent_candidate(user_id):
    goals = (
        WorkoutWeeklyGoal.query.filter_by(user_id=user_id)
        .order_by(
            WorkoutWeeklyGoal.effective_week_start.asc(),
            WorkoutWeeklyGoal.created_at.asc(),
            WorkoutWeeklyGoal.id.asc(),
        )
        .all()
    )
    if not goals:
        return None

    backfill_session_weeks(user_id, user_timezone(user_id))
    sessions = (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.completed_week_start.isnot(None),
            WorkoutSession.completions.any(),
        )
        .order_by(
            WorkoutSession.completed_week_start.asc(),
            WorkoutSession.completed_at.asc(),
            WorkoutSession.id.asc(),
        )
        .all()
    )
    if not sessions:
        return None

    sessions_by_week = defaultdict(list)
    for session in sessions:
        sessions_by_week[session.completed_week_start].append(session)

    week = goals[0].effective_week_start
    last_session_week = max(sessions_by_week)
    goal_index = 0
    active_goal = None
    streak = 0
    while week <= last_session_week:
        while goal_index < len(goals) and goals[goal_index].effective_week_start <= week:
            active_goal = goals[goal_index]
            goal_index += 1

        week_sessions = sessions_by_week.get(week, [])
        if active_goal and len(week_sessions) >= active_goal.target_sessions:
            streak += 1
            if streak == 4:
                milestone_session = week_sessions[active_goal.target_sessions - 1]
                return _UnlockCandidate(
                    unlocked_at=milestone_session.completed_at,
                    workout_session_id=milestone_session.id,
                )
        else:
            streak = 0
        week += timedelta(days=7)
    return None


def _candidates(user_id):
    candidates = {}
    sessions = _qualifying_sessions(user_id)
    session_thresholds = {
        "first_step": 1,
        "workout_10": 10,
        "workout_50": 50,
        "workout_100": 100,
    }
    for code, threshold in session_thresholds.items():
        if len(sessions) >= threshold:
            session = sessions[threshold - 1]
            candidates[code] = _UnlockCandidate(
                unlocked_at=session.completed_at,
                workout_session_id=session.id,
            )

    events = _highlighted_events(user_id)
    if events:
        event = events[0]
        candidates["first_pr"] = _UnlockCandidate(
            unlocked_at=event.achieved_at,
            workout_session_id=event.workout_session_id,
        )
    if len(events) >= 10:
        event = events[9]
        candidates["evolving"] = _UnlockCandidate(
            unlocked_at=event.achieved_at,
            workout_session_id=event.workout_session_id,
        )

    events_by_session = defaultdict(list)
    for event in events:
        events_by_session[event.workout_session_id].append(event)
    third_events = [
        session_events[2]
        for session_events in events_by_session.values()
        if len(session_events) >= 3
    ]
    if third_events:
        event = min(third_events, key=lambda item: (item.achieved_at, item.id))
        candidates["big_day"] = _UnlockCandidate(
            unlocked_at=event.achieved_at,
            workout_session_id=event.workout_session_id,
        )

    achieved_goal = (
        ExerciseGoal.query.filter(
            ExerciseGoal.user_id == user_id,
            ExerciseGoal.status == "achieved",
            ExerciseGoal.achieved_at.isnot(None),
        )
        .order_by(ExerciseGoal.achieved_at.asc(), ExerciseGoal.created_at.asc())
        .first()
    )
    if achieved_goal:
        candidates["first_goal"] = _UnlockCandidate(
            unlocked_at=achieved_goal.achieved_at,
            workout_session_id=achieved_goal.achieved_session_id,
            exercise_goal_id=achieved_goal.id,
        )

    consistent = _consistent_candidate(user_id)
    if consistent:
        candidates["consistent"] = consistent
    return candidates


def evaluate_achievements(user_id, related_session=None, backfilled=False):
    candidates = _candidates(user_id)
    existing_codes = {
        code
        for code, in db.session.query(AchievementUnlock.achievement_code).filter_by(
            user_id=user_id
        )
    }
    fallback_at = None
    if related_session is not None and related_session.user_id == user_id:
        fallback_at = related_session.completed_at

    created = []
    for code in ACHIEVEMENTS:
        candidate = candidates.get(code)
        if candidate is None or code in existing_codes:
            continue
        unlock = AchievementUnlock(
            user_id=user_id,
            achievement_code=code,
            unlocked_at=candidate.unlocked_at or fallback_at or datetime.utcnow(),
            workout_session_id=candidate.workout_session_id,
            exercise_goal_id=candidate.exercise_goal_id,
            is_backfilled=bool(backfilled),
        )
        db.session.add(unlock)
        created.append(unlock)
        existing_codes.add(code)
    db.session.flush()
    return created


def serialize_unlock(unlock):
    definition = ACHIEVEMENTS.get(unlock.achievement_code, {})
    return {
        "id": unlock.id,
        "code": unlock.achievement_code,
        "title": definition.get("title", unlock.achievement_code),
        "description": definition.get("description", ""),
        "unlocked_at": unlock.unlocked_at.isoformat() if unlock.unlocked_at else None,
        "workout_session_id": unlock.workout_session_id,
        "exercise_goal_id": (
            str(unlock.exercise_goal_id) if unlock.exercise_goal_id else None
        ),
        "is_backfilled": unlock.is_backfilled,
    }


def serialize_unlocks(items):
    return [serialize_unlock(item) for item in items]


def unlocks(user_id):
    items = (
        AchievementUnlock.query.filter_by(user_id=user_id)
        .order_by(AchievementUnlock.unlocked_at.asc(), AchievementUnlock.id.asc())
        .all()
    )
    return serialize_unlocks(items)


def achievement_unlocks(user_id):
    return unlocks(user_id)
