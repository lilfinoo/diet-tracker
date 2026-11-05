from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from src.models.user import (
    AchievementUnlock,
    ExerciseGoal,
    PersonalRecordEvent,
    WorkoutSession,
    WorkoutWeeklyGoal,
    db,
)
from src.services.workout_progress import backfill_session_weeks, user_timezone, weekly_progress
from src.services.gamification import gamification_metrics


ACHIEVEMENTS = {
    "first_step": {
        "title": "Primeiro passo",
        "description": "Conclua seu primeiro treino.",
        "category": "treino",
        "tier": "bronze",
        "track": "sessions",
        "threshold": 1,
    },
    "workout_10": {
        "title": "10 treinos",
        "description": "Conclua 10 treinos.",
        "category": "treino",
        "tier": "prata",
        "track": "sessions",
        "threshold": 10,
    },
    "workout_50": {
        "title": "50 treinos",
        "description": "Conclua 50 treinos.",
        "category": "treino",
        "tier": "ouro",
        "track": "sessions",
        "threshold": 50,
    },
    "workout_100": {
        "title": "100 treinos",
        "description": "Conclua 100 treinos.",
        "category": "treino",
        "tier": "platina",
        "track": "sessions",
        "threshold": 100,
    },
    "first_pr": {
        "title": "Primeiro recorde",
        "description": "Conquiste seu primeiro recorde pessoal.",
        "category": "recorde",
        "tier": "bronze",
        "track": "records",
        "threshold": 1,
    },
    "evolving": {
        "title": "Em evolu\u00e7\u00e3o",
        "description": "Conquiste 10 recordes pessoais.",
        "category": "recorde",
        "tier": "prata",
        "track": "records",
        "threshold": 10,
    },
    "big_day": {
        "title": "Grande dia",
        "description": "Conquiste 3 recordes pessoais no mesmo treino.",
        "category": "recorde",
        "tier": "ouro",
        "track": "records_same_session",
        "threshold": 3,
        "hidden": True,
        "hidden_hint": "Uma única sessão pode mudar muita coisa.",
    },
    "first_goal": {
        "title": "Meta alcan\u00e7ada",
        "description": "Alcance sua primeira meta de carga.",
        "category": "meta",
        "tier": "bronze",
        "track": "goals",
        "threshold": 1,
    },
    "consistent": {
        "title": "Consist\u00eancia",
        "description": "Cumpra a meta semanal por 4 semanas seguidas.",
        "category": "consistencia",
        "tier": "ouro",
        "track": "weekly_streak",
        "threshold": 4,
    },
}
ACHIEVEMENT_CATALOG = ACHIEVEMENTS


def _add_daily_milestones(track, category, entries):
    category_key = {
        "sessions": "treino", "records": "recorde", "goals": "meta",
        "weekly_streak": "consistencia", "meal_days": "alimentacao",
        "water_days": "hidratacao", "streak_days": "sequencia",
        "active_days": "presenca",
    }[track]
    for code, title, threshold, tier in entries:
        ACHIEVEMENTS[code] = {
            "title": title,
            "description": f"Alcance {threshold} {category}.",
            "category": category_key,
            "tier": tier,
            "track": track,
            "threshold": threshold,
        }


_add_daily_milestones("sessions", "treinos concluídos", [
    ("workout_5", "Pegando ritmo", 5, "prata"),
    ("workout_25", "Rotina em construção", 25, "prata"),
    ("workout_250", "Longa jornada", 250, "ouro"),
    ("workout_500", "História de treino", 500, "platina"),
])
_add_daily_milestones("records", "recordes pessoais", [("records_5", "Novas marcas", 5, "bronze")])
_add_daily_milestones("goals", "metas de carga", [("goals_5", "Metas em movimento", 5, "ouro")])
_add_daily_milestones("weekly_streak", "semanas seguidas cumprindo a meta", [
    ("weekly_1", "Semana cumprida", 1, "bronze"),
    ("weekly_2", "Duas no ritmo", 2, "bronze"),
    ("weekly_8", "Ritmo consolidado", 8, "prata"),
    ("weekly_12", "Trimestre consistente", 12, "ouro"),
    ("weekly_26", "Semestre de rotina", 26, "ouro"),
])
_add_daily_milestones("meal_days", "dias com alimentação registrada", [
    ("meal_1", "Primeiro registro", 1, "bronze"),
    ("meal_3", "Aprendendo a observar", 3, "bronze"),
    ("meal_7", "Uma semana registrada", 7, "bronze"),
    ("meal_14", "Duas semanas de atenção", 14, "prata"),
    ("meal_30", "Mês acompanhado", 30, "prata"),
    ("meal_60", "Rotina alimentar", 60, "ouro"),
    ("meal_100", "Cem dias de atenção", 100, "ouro"),
    ("meal_365", "Ano acompanhado", 365, "ouro"),
])
_add_daily_milestones("water_days", "dias com hidratação registrada", [
    ("water_1", "Primeiro gole registrado", 1, "bronze"),
    ("water_3", "Lembrando da água", 3, "bronze"),
    ("water_7", "Água na rotina", 7, "bronze"),
    ("water_14", "Duas semanas registradas", 14, "prata"),
    ("water_30", "Mês de hidratação", 30, "prata"),
    ("water_100", "Cem dias registrados", 100, "ouro"),
])
_add_daily_milestones("streak_days", "dias seguidos de constância", [
    ("streak_3", "Começou o ritmo", 3, "bronze"),
    ("streak_7", "Semana de constância", 7, "bronze"),
    ("streak_14", "Duas semanas no ritmo", 14, "prata"),
    ("streak_30", "Mês de constância", 30, "prata"),
    ("streak_60", "Constância crescendo", 60, "ouro"),
    ("streak_100", "Cem de constância", 100, "ouro"),
    ("streak_180", "Meio ano presente", 180, "ouro"),
    ("streak_365", "Ano de constância", 365, "ouro"),
])
_add_daily_milestones("active_days", "dias ativos", [
    ("active_7", "Uma semana presente", 7, "bronze"),
    ("active_30", "Trinta dias presentes", 30, "prata"),
    ("active_100", "Cem dias presentes", 100, "ouro"),
    ("active_365", "Um ano presente", 365, "ouro"),
])
ACHIEVEMENTS["return_after_break"] = {
    "title": "Recomeço", "description": "Volte a registrar depois de uma pausa.",
    "category": "presenca", "tier": "bronze", "track": "returns", "threshold": 1,
}
for code, title, description in [
    ("training_journey", "Jornada de treino", "Some 30 dias ativos e conclua 10 treinos."),
    ("meal_journey", "Jornada alimentar", "Some 60 dias ativos e registre alimentação em 30 dias."),
    ("integrated_routine", "Rotina integrada", "Cumpra metas de treino por 8 semanas e registre alimentação e água em 30 dias."),
]:
    ACHIEVEMENTS[code] = {
        "title": title, "description": description, "category": "colecao",
        "tier": "platina", "track": "collections", "threshold": 1,
    }


@dataclass(frozen=True)
class _UnlockCandidate:
    unlocked_at: datetime
    workout_session_id: Optional[int] = None
    exercise_goal_id: Optional[object] = None


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
        )
        .order_by(PersonalRecordEvent.achieved_at.asc(), PersonalRecordEvent.id.asc())
        .all()
    )


def _consistent_candidates(user_id, thresholds=(4,)):
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
        return {}

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
        return {}

    sessions_by_week = defaultdict(list)
    for session in sessions:
        sessions_by_week[session.completed_week_start].append(session)

    week = goals[0].effective_week_start
    last_session_week = max(sessions_by_week)
    goal_index = 0
    active_goal = None
    streak = 0
    found = {}
    thresholds = set(thresholds)
    while week <= last_session_week:
        while goal_index < len(goals) and goals[goal_index].effective_week_start <= week:
            active_goal = goals[goal_index]
            goal_index += 1

        week_sessions = sessions_by_week.get(week, [])
        if active_goal and len(week_sessions) >= active_goal.target_sessions:
            streak += 1
            if streak in thresholds and streak not in found:
                milestone_session = week_sessions[active_goal.target_sessions - 1]
                found[streak] = _UnlockCandidate(
                    unlocked_at=milestone_session.completed_at,
                    workout_session_id=milestone_session.id,
                )
        else:
            streak = 0
        week += timedelta(days=7)
    return found


def _consistent_candidate(user_id, threshold=4):
    return _consistent_candidates(user_id, (threshold,)).get(threshold)


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

    weekly_thresholds = {
        "consistent": 4, "weekly_1": 1, "weekly_2": 2,
        "weekly_8": 8, "weekly_12": 12, "weekly_26": 26,
    }
    weekly_candidates = _consistent_candidates(user_id, weekly_thresholds.values())
    for code, threshold in weekly_thresholds.items():
        milestone = weekly_candidates.get(threshold)
        if milestone:
            candidates[code] = milestone

    from src.models.user import GamificationDay
    daily_rows = GamificationDay.query.filter_by(user_id=user_id).order_by(
        GamificationDay.local_date.asc()
    ).all()
    daily_metrics = gamification_metrics(user_id)
    for code, definition in ACHIEVEMENTS.items():
        if code in candidates:
            continue
        track, threshold = definition.get("track"), int(definition.get("threshold") or 1)
        if track == "sessions" and len(sessions) >= threshold:
            session = sessions[threshold - 1]
            candidates[code] = _UnlockCandidate(session.completed_at, workout_session_id=session.id)
        elif track == "records" and len(events) >= threshold:
            event = events[threshold - 1]
            candidates[code] = _UnlockCandidate(event.achieved_at, workout_session_id=event.workout_session_id)
        elif track == "goals" and achieved_goal and ExerciseGoal.query.filter_by(user_id=user_id, status="achieved").count() >= threshold:
            goal = ExerciseGoal.query.filter_by(user_id=user_id, status="achieved").order_by(ExerciseGoal.achieved_at.asc()).offset(threshold - 1).first()
            if goal:
                candidates[code] = _UnlockCandidate(goal.achieved_at, workout_session_id=goal.achieved_session_id, exercise_goal_id=goal.id)
        elif track in {"meal_days", "water_days", "active_days"}:
            field = {"meal_days": "meal", "water_days": "water"}.get(track)
            eligible = [row for row in daily_rows if (getattr(row, field) if field else row.meal or row.water or row.workout)]
            if len(eligible) >= threshold:
                candidates[code] = _UnlockCandidate(datetime.combine(eligible[threshold - 1].local_date, datetime.min.time()))
        elif track == "streak_days" and daily_metrics["streak_days"] >= threshold:
            run = 0
            previous = None
            for row in daily_rows:
                active = row.meal or row.water or row.workout
                run = run + 1 if active and previous and row.local_date == previous + timedelta(days=1) else 1 if active else 0
                previous = row.local_date if active else None
                if run >= threshold:
                    candidates[code] = _UnlockCandidate(datetime.combine(row.local_date, datetime.min.time()))
                    break
        elif track == "returns" and daily_metrics["returns"] >= threshold:
            row = next((row for row in daily_rows if row.return_earned), None)
            if row:
                candidates[code] = _UnlockCandidate(datetime.combine(row.local_date, datetime.min.time()))
        elif track == "collections":
            eight_week_streak = weekly_candidates.get(8) is not None
            ready = {
                "training_journey": daily_metrics["active_days"] >= 30 and len(sessions) >= 10,
                "meal_journey": daily_metrics["active_days"] >= 60 and daily_metrics["meal_days"] >= 30,
                "integrated_routine": daily_metrics["meal_days"] >= 30 and daily_metrics["water_days"] >= 30 and eight_week_streak,
            }.get(code, False)
            if ready and daily_rows:
                candidates[code] = _UnlockCandidate(datetime.combine(daily_rows[-1].local_date, datetime.min.time()))
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
        "tier": definition.get("tier", "bronze"),
        "unlocked_at": unlock.unlocked_at.isoformat() if unlock.unlocked_at else None,
        "workout_session_id": unlock.workout_session_id,
        "exercise_goal_id": (
            str(unlock.exercise_goal_id) if unlock.exercise_goal_id else None
        ),
        "is_backfilled": unlock.is_backfilled,
    }


def serialize_unlocks(items):
    return [serialize_unlock(item) for item in items]


def achievement_catalog(user_id):
    unlocked = {
        item.achievement_code: item
        for item in AchievementUnlock.query.filter_by(user_id=user_id).all()
    }
    sessions = _qualifying_sessions(user_id)
    records = _highlighted_events(user_id)
    records_by_session = defaultdict(int)
    for event in records:
        records_by_session[event.workout_session_id] += 1
    metrics = {
        "sessions": len(sessions),
        "records": len(records),
        "records_same_session": max(records_by_session.values(), default=0),
        "goals": ExerciseGoal.query.filter_by(user_id=user_id, status="achieved").count(),
        "weekly_streak": ((weekly_progress(user_id).get("current") or {}).get("streak") or 0),
        **gamification_metrics(user_id),
    }

    items = []
    for code, definition in ACHIEVEMENTS.items():
        unlock = unlocked.get(code)
        hidden = bool(definition.get("hidden"))
        current = int(metrics.get(definition.get("track"), 0))
        target = int(definition.get("threshold") or 1)
        item = {
            "code": code,
            "title": definition.get("title", code),
            "description": definition.get("description", ""),
            "category": definition.get("category", "geral"),
            "tier": definition.get("tier", "bronze"),
            "hidden": hidden,
            "hidden_hint": definition.get("hidden_hint"),
            "progress": {
                "current": min(current, target),
                "target": target,
                "percentage": min(100, round((current / target) * 100)) if target else 100,
            },
            "unlocked": serialize_unlock(unlock) if unlock else None,
        }
        if hidden and unlock is None:
            item["title"] = "Conquista oculta"
            item["description"] = definition.get("hidden_hint") or "Continue evoluindo para revelar esta conquista."
            item["progress"] = None
        items.append(item)
    return items


def unlocks(user_id):
    items = (
        AchievementUnlock.query.filter_by(user_id=user_id)
        .order_by(AchievementUnlock.unlocked_at.asc(), AchievementUnlock.id.asc())
        .all()
    )
    return serialize_unlocks(items)


def achievement_unlocks(user_id):
    return unlocks(user_id)


def reconcile_achievements(user_id):
    """Keep only milestones supported by the surviving history, preserving valid IDs."""
    from src.models.user import ProfileHighlight

    candidates = _candidates(user_id)
    for unlock in AchievementUnlock.query.filter_by(user_id=user_id).all():
        if unlock.achievement_code not in ACHIEVEMENTS:
            continue
        candidate = candidates.get(unlock.achievement_code)
        if candidate is None:
            ProfileHighlight.query.filter_by(achievement_unlock_id=unlock.id).delete(synchronize_session="fetch")
            db.session.delete(unlock)
        else:
            unlock.unlocked_at = candidate.unlocked_at
            unlock.workout_session_id = candidate.workout_session_id
            unlock.exercise_goal_id = candidate.exercise_goal_id
    db.session.flush()
    evaluate_achievements(user_id, backfilled=True)
