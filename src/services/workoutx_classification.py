"""Structured WorkoutX exercise classification for catalog curation and offline matching."""


def _value(value):
    return str(value or "").strip().lower()


def _name_has(name, *patterns):
    return any(pattern in name for pattern in patterns)


def movement_pattern(exercise):
    target = _value(exercise.get("target"))
    body_part = _value(exercise.get("bodyPart"))
    mechanic = _value(exercise.get("mechanic"))
    force = _value(exercise.get("force"))
    name = _value(exercise.get("name"))

    if target == "calves":
        return "plantar_flexion"
    if target in {"quads", "glutes"} and _name_has(name, "leg press", "press machine"):
        return "leg_press"
    if target == "quads":
        if mechanic == "isolation" or _name_has(name, "leg extension", "knee extension"):
            return "knee_extension"
        if _name_has(name, "lunge", "split squat", "step-up", "step up"):
            return "unilateral_knee_dominant"
        return "squat"
    if target == "hamstrings":
        if mechanic == "isolation" or _name_has(name, "leg curl", "hamstring curl", "knee flexion"):
            return "knee_flexion"
        return "hip_hinge"
    if target == "glutes":
        if _name_has(name, "hip thrust", "glute bridge"):
            return "hip_extension"
        if _name_has(name, "lunge", "split squat", "step-up", "step up"):
            return "unilateral_knee_dominant"
        return "squat" if mechanic == "compound" else "hip_extension"
    if target == "pectorals":
        return "chest_adduction" if mechanic == "isolation" else "horizontal_press"
    if target == "lats":
        return "horizontal_pull" if _name_has(name, "row", "rowing") else "vertical_pull"
    if target in {"upper back", "traps", "spine"}:
        return "vertical_pull" if _name_has(name, "pulldown", "pull down", "lat pull") else "horizontal_pull"
    if target == "delts":
        if _name_has(name, "lateral raise", "side raise", "lateral arm raise"):
            return "shoulder_abduction"
        if _name_has(name, "upright row"):
            return "shoulder_elevation"
        if _name_has(name, "rear delt", "reverse fly", "face pull"):
            return "shoulder_extension"
        return "vertical_press" if mechanic == "compound" or force == "push" else "shoulder_isolation"
    if target == "biceps":
        return "elbow_flexion"
    if target == "triceps":
        return "elbow_extension"
    if target == "forearms":
        return "grip_or_wrist"
    if target in {"abs", "serratus anterior"}:
        if _name_has(name, "plank", "rollout"):
            return "anti_extension"
        if _name_has(name, "twist", "rotation", "woodchop"):
            return "rotation"
        if _name_has(name, "crunch", "sit-up", "sit up", "leg raise"):
            return "trunk_flexion"
        if _name_has(name, "side bend", "lateral flexion"):
            return "lateral_flexion"
        return "core_general"
    if body_part == "chest" and force == "push":
        return "horizontal_press"
    if body_part == "back" and force == "pull":
        return "horizontal_pull"
    return "general"


def classify_workoutx_exercise(exercise):
    mechanic = _value(exercise.get("mechanic"))
    primary_muscle = _value(exercise.get("target"))
    pattern = movement_pattern(exercise)
    if mechanic == "compound":
        role = "primary_compound"
    elif primary_muscle in {"abs", "serratus anterior"}:
        role = "core"
    else:
        role = "isolation"
    unilateral = exercise.get("isUnilateral")
    return {
        "primary_muscle": primary_muscle,
        "secondary_muscles": frozenset(_value(value) for value in exercise.get("secondaryMuscles") or []),
        "movement_pattern": pattern,
        "training_role": role,
        "mechanic": mechanic,
        "force": _value(exercise.get("force")),
        "equipment": _value(exercise.get("equipment")),
        "unilateral": unilateral if isinstance(unilateral, bool) else None,
        "difficulty": _value(exercise.get("difficulty")),
    }
