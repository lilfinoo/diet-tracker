"""Offline WorkoutX exercise classification and substitution scoring."""

from src.services.workoutx_classification import classify_workoutx_exercise


MINIMUM_SUBSTITUTION_SCORE = 180


def _value(exercise, key):
    return str(exercise.get(key) or "").strip().lower()


def classify_exercise(exercise):
    return {"provider_id": str(exercise["id"]), **classify_workoutx_exercise(exercise)}


def substitution_options(exercise, catalog, available_equipment=None, present_ids=(), minimum_score=MINIMUM_SUBSTITUTION_SCORE):
    source = classify_exercise(exercise)
    source_name = _value(exercise, "name")
    present_ids = {str(provider_id) for provider_id in present_ids}
    allowed = {_value({"value": equipment}, "value") for equipment in available_equipment or []}
    options = []

    for candidate in catalog:
        candidate_data = classify_exercise(candidate)
        if (
            candidate_data["provider_id"] == source["provider_id"]
            or candidate_data["provider_id"] in present_ids
            or _value(candidate, "name") == source_name
        ):
            continue
        same_primary_muscle = candidate_data["primary_muscle"] == source["primary_muscle"]
        compatible_leg_press = (
            source["movement_pattern"] == candidate_data["movement_pattern"] == "leg_press"
            and {source["primary_muscle"], candidate_data["primary_muscle"]} <= {"quads", "glutes"}
        )
        if not same_primary_muscle and not compatible_leg_press:
            continue
        if candidate_data["training_role"] != source["training_role"]:
            continue
        if allowed and candidate_data["equipment"] not in allowed and candidate_data["equipment"] != "body weight":
            continue

        score = 100 if same_primary_muscle else 85
        if candidate_data["movement_pattern"] == source["movement_pattern"]:
            score += 50
        if candidate_data["training_role"] == source["training_role"]:
            score += 30
        if candidate_data["mechanic"] == source["mechanic"]:
            score += 15
        if candidate_data["equipment"] == source["equipment"]:
            score += 12
        elif allowed:
            score += 8
        score += 5 * len(source["secondary_muscles"] & candidate_data["secondary_muscles"])
        if source["unilateral"] is not None and candidate_data["unilateral"] == source["unilateral"]:
            score += 5
        if source["difficulty"] and candidate_data["difficulty"] == source["difficulty"]:
            score += 3
        if any(marker in _value(candidate, "name") for marker in ("push-up", "push up")):
            score -= 30
        if score >= minimum_score:
            options.append((score, candidate))

    options.sort(key=lambda item: (-item[0], str(item[1].get("name", "")).lower(), str(item[1]["id"])))
    return [candidate for _, candidate in options[:3]]
