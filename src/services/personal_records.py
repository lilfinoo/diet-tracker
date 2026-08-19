from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import selectinload

from src.models.user import (
    PersonalRecordEvent,
    WorkoutSession,
    WorkoutSessionExerciseCompletion,
    db,
)


LOAD_PRECISION = Decimal("0.01")
VALUE_PRECISION = Decimal("0.0001")
E1RM_METRIC_KEY = "e1rm:epley:v1"
METRIC_PRIORITY = {"max_load": 0, "estimated_1rm": 1, "reps_at_load": 2}


def _decimal(value, precision):
    try:
        result = Decimal(str(value)).quantize(precision)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _event_value(event):
    return _decimal(event.new_value, VALUE_PRECISION) or Decimal("0")


def process_session_personal_records(session_record, backfilled=False):
    if session_record.completed_at is None:
        return []
    if (session_record.pr_processed_version or 0) >= 1:
        return PersonalRecordEvent.query.filter_by(
            workout_session_id=session_record.id
        ).order_by(PersonalRecordEvent.id).all()

    db.session.flush()
    candidates = {}

    def consider(completion, performed_set, metric_type, metric_key, value, load_kg):
        candidate = {
            "exercise_key": completion.exercise_catalog_key.strip(),
            "exercise_name": completion.exercise_name
            or (completion.exercise.name if completion.exercise else completion.exercise_catalog_key),
            "completion_id": completion.id,
            "set_id": performed_set.id,
            "metric_type": metric_type,
            "metric_key": metric_key,
            "value": value.quantize(VALUE_PRECISION),
            "load_kg": load_kg,
            "repetitions": performed_set.repetitions,
            "formula": "epley" if metric_type == "estimated_1rm" else None,
            "formula_version": 1 if metric_type == "estimated_1rm" else None,
        }
        key = (candidate["exercise_key"], metric_type, metric_key)
        current = candidates.get(key)
        rank = (candidate["value"], load_kg, candidate["repetitions"])
        if current is None or rank > (
            current["value"], current["load_kg"], current["repetitions"]
        ):
            candidates[key] = candidate

    for completion in session_record.completions:
        exercise_key = (completion.exercise_catalog_key or "").strip()
        if not exercise_key or exercise_key == "__unresolved__":
            continue
        for performed_set in completion.performed_sets:
            load_kg = _decimal(performed_set.load_kg, LOAD_PRECISION)
            repetitions = performed_set.repetitions
            if (
                load_kg is None
                or load_kg <= 0
                or repetitions is None
                or repetitions <= 0
                or performed_set.is_warmup is not False
            ):
                continue

            consider(completion, performed_set, "max_load", "max_load", load_kg, load_kg)
            if repetitions <= 12:
                estimated_1rm = load_kg if repetitions == 1 else load_kg * (
                    Decimal("1") + Decimal(repetitions) / Decimal("30")
                )
                consider(
                    completion,
                    performed_set,
                    "estimated_1rm",
                    E1RM_METRIC_KEY,
                    estimated_1rm,
                    load_kg,
                )
            consider(
                completion,
                performed_set,
                "reps_at_load",
                f"reps_at_load:{load_kg:.2f}",
                Decimal(repetitions),
                load_kg,
            )

    if not candidates:
        session_record.pr_processed_version = 1
        db.session.flush()
        return []

    exercise_keys = {candidate["exercise_key"] for candidate in candidates.values()}
    known_events = PersonalRecordEvent.query.filter(
        PersonalRecordEvent.user_id == session_record.user_id,
        PersonalRecordEvent.exercise_key.in_(exercise_keys),
    ).all()

    ordered_candidates = sorted(
        candidates.values(),
        key=lambda item: (
            item["exercise_key"],
            METRIC_PRIORITY[item["metric_type"]],
            -item["load_kg"],
        ),
    )
    for candidate in ordered_candidates:
        matching = [
            event
            for event in known_events
            if event.exercise_key == candidate["exercise_key"]
            and event.metric_type == candidate["metric_type"]
            and event.metric_key == candidate["metric_key"]
        ]
        if any(event.workout_session_id == session_record.id for event in matching):
            continue

        previous_events = [
            event
            for event in matching
            if event.achieved_at < session_record.completed_at
            or (
                event.achieved_at == session_record.completed_at
                and event.workout_session_id < session_record.id
            )
        ]
        previous = max(previous_events, key=_event_value, default=None)
        if previous is not None and candidate["value"] <= _event_value(previous):
            continue

        event = PersonalRecordEvent(
            user_id=session_record.user_id,
            exercise_key=candidate["exercise_key"],
            exercise_name=candidate["exercise_name"],
            workout_session_id=session_record.id,
            completion_id=candidate["completion_id"],
            set_id=candidate["set_id"],
            metric_type=candidate["metric_type"],
            metric_key=candidate["metric_key"],
            previous_value=previous.new_value if previous else None,
            new_value=candidate["value"],
            previous_load_kg=previous.load_kg if previous else None,
            previous_repetitions=previous.repetitions if previous else None,
            load_kg=candidate["load_kg"],
            repetitions=candidate["repetitions"],
            formula=candidate["formula"],
            formula_version=candidate["formula_version"],
            is_initial=previous is None,
            is_highlighted=False,
            is_backfilled=bool(backfilled),
            achieved_at=session_record.completed_at,
        )
        db.session.add(event)
        known_events.append(event)

    db.session.flush()
    session_events = PersonalRecordEvent.query.filter_by(
        workout_session_id=session_record.id
    ).all()
    by_exercise = defaultdict(list)
    for event in session_events:
        event.is_highlighted = False
        by_exercise[event.exercise_key].append(event)

    for events in by_exercise.values():
        eligible = [event for event in events if not event.is_initial]
        if eligible:
            highlighted = min(
                eligible,
                key=lambda event: (
                    METRIC_PRIORITY.get(event.metric_type, len(METRIC_PRIORITY)),
                    -(_decimal(event.load_kg, LOAD_PRECISION) or Decimal("0"))
                    if event.metric_type == "reps_at_load"
                    else Decimal("0"),
                    event.id,
                ),
            )
            highlighted.is_highlighted = True

    db.session.flush()
    session_record.pr_processed_version = 1
    return sorted(
        session_events,
        key=lambda event: (
            event.exercise_key,
            METRIC_PRIORITY.get(event.metric_type, len(METRIC_PRIORITY)),
            -(_decimal(event.load_kg, LOAD_PRECISION) or Decimal("0")),
            event.id,
        ),
    )


def serialize_personal_record(event):
    number = lambda value: float(value) if value is not None else None
    return {
        "id": event.id,
        "workout_session_id": event.workout_session_id,
        "completion_id": event.completion_id,
        "set_id": event.set_id,
        "exercise_key": event.exercise_key,
        "exercise_name": event.exercise_name,
        "metric_type": event.metric_type,
        "metric_key": event.metric_key,
        "previous_value": number(event.previous_value),
        "new_value": number(event.new_value),
        "previous_load_kg": number(event.previous_load_kg),
        "previous_repetitions": event.previous_repetitions,
        "load_kg": number(event.load_kg),
        "repetitions": event.repetitions,
        "formula": event.formula,
        "formula_version": event.formula_version,
        "is_initial": event.is_initial,
        "is_highlighted": event.is_highlighted,
        "is_backfilled": event.is_backfilled,
        "achieved_at": event.achieved_at.isoformat(),
    }


def ensure_personal_record_history(user_id, exclude_session_id=None):
    query = (
        WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.pr_processed_version.is_(None),
        )
        .options(
            selectinload(WorkoutSession.completions).selectinload(
                WorkoutSessionExerciseCompletion.performed_sets
            )
        )
        .order_by(WorkoutSession.completed_at, WorkoutSession.id)
    )
    if exclude_session_id is not None:
        query = query.filter(WorkoutSession.id != exclude_session_id)

    events = []
    for session_record in query.all():
        events.extend(process_session_personal_records(session_record, backfilled=True))
    return events


def current_max_load(user_id, exercise_key):
    event = (
        PersonalRecordEvent.query.filter_by(
            user_id=user_id,
            exercise_key=exercise_key,
            metric_type="max_load",
            metric_key="max_load",
        )
        .order_by(PersonalRecordEvent.new_value.desc())
        .first()
    )
    return _decimal(event.new_value, LOAD_PRECISION) if event else None


def exercise_progress(user_id, exercise_key):
    events = (
        PersonalRecordEvent.query.filter_by(user_id=user_id, exercise_key=exercise_key)
        .order_by(
            PersonalRecordEvent.achieved_at,
            PersonalRecordEvent.workout_session_id,
            PersonalRecordEvent.id,
        )
        .all()
    )
    return [serialize_personal_record(event) for event in events]
