"""Exercise results come from performed sessions, independently of PR events."""
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from src.models.user import WorkoutSession, WorkoutSessionExerciseCompletion, WorkoutSetPerformance


def performed_exercises(user_id):
    rows = (
        WorkoutSessionExerciseCompletion.query.join(WorkoutSession)
        .filter(WorkoutSession.user_id == user_id, WorkoutSession.completed_at.isnot(None))
        .with_entities(WorkoutSessionExerciseCompletion.exercise_catalog_key,
                       WorkoutSessionExerciseCompletion.exercise_name, WorkoutSessionExerciseCompletion.workout_exercise_id)
        .order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc(), WorkoutSessionExerciseCompletion.id)
        .all()
    )
    options = {}
    for key, name, exercise_id in rows:
        key = key if key and key != "__unresolved__" else f"exercise-id:{exercise_id}"
        if key not in options:
            options[key] = {"key": key, "name": name or key}
    return list(options.values())


def _exercise_filter(key):
    if key.startswith('exercise-id:') and key.removeprefix('exercise-id:').isdigit():
        return (WorkoutSessionExerciseCompletion.workout_exercise_id == int(key.removeprefix('exercise-id:'))) & or_(
            WorkoutSessionExerciseCompletion.exercise_catalog_key.is_(None),
            WorkoutSessionExerciseCompletion.exercise_catalog_key.in_(['', '__unresolved__']),
        )
    return WorkoutSessionExerciseCompletion.exercise_catalog_key == key


def historical_load(user_id, key):
    value = (WorkoutSetPerformance.query.join(WorkoutSessionExerciseCompletion).join(WorkoutSession)
             .with_entities(func.max(WorkoutSetPerformance.load_kg))
             .filter(WorkoutSession.user_id == user_id, WorkoutSession.completed_at.isnot(None),
                     _exercise_filter(key), WorkoutSetPerformance.is_warmup.is_(False),
                     WorkoutSetPerformance.load_kg > 0, WorkoutSetPerformance.repetitions > 0).scalar())
    return float(value) if value is not None else None


def exercise_sessions(user_id, exercise_key, limit=20, offset=0):
    sessions = (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id, WorkoutSession.completed_at.isnot(None),
            WorkoutSession.completions.any(_exercise_filter(exercise_key)),
        )
        .options(selectinload(WorkoutSession.completions).selectinload(WorkoutSessionExerciseCompletion.performed_sets))
        .order_by(WorkoutSession.completed_at.desc(), WorkoutSession.id.desc())
        .offset(offset).limit(limit + 1).all()
    )
    items = []
    for session in sessions[:limit]:
        sets = []
        for completion in session.completions:
            key = completion.exercise_catalog_key
            key = key if key and key != "__unresolved__" else f"exercise-id:{completion.workout_exercise_id}"
            if key != exercise_key:
                continue
            for performed in completion.performed_sets:
                sets.append({"repetitions": performed.repetitions,
                             "load_kg": float(performed.load_kg) if performed.load_kg is not None else None,
                             "is_warmup": performed.is_warmup})
        items.append({"session_id": session.id, "completed_at": session.completed_at.isoformat(),
                      "local_date": session.completed_local_date.isoformat() if session.completed_local_date else None,
                      "sets": sets})
    return {"items": items, "has_more": len(sessions) > limit, "offset": offset, "limit": limit}
