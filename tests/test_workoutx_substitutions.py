from types import SimpleNamespace

from src.models.user import WorkoutXExercise, db
from src.services.workout_plans import replacement_options
from src.services.workoutx_substitutions import classify_exercise, substitution_options


def exercise(identifier, name, target, equipment, mechanic="compound", **extra):
    return {
        "id": identifier,
        "name": name,
        "target": target,
        "equipment": equipment,
        "mechanic": mechanic,
        "force": "push",
        "difficulty": "intermediate",
        "secondaryMuscles": ["triceps"],
        **extra,
    }


def test_classification_preserves_substitution_attributes():
    result = classify_exercise(exercise("1", "Barbell Bench Press", "Pectorals", "Barbell"))

    assert result["primary_muscle"] == "pectorals"
    assert result["movement_pattern"] == "horizontal_press"
    assert result["training_role"] == "primary_compound"
    assert result["secondary_muscles"] == {"triceps"}


def test_substitution_prefers_same_pattern_and_excludes_present_exercises():
    source = exercise("1", "Barbell Bench Press", "Pectorals", "Barbell")
    matching = exercise("2", "Dumbbell Bench Press", "Pectorals", "Dumbbell")
    other = exercise("3", "Dumbbell Incline Bench Press", "Pectorals", "Dumbbell")
    duplicate = exercise("4", "Barbell Bench Press", "Pectorals", "Barbell")

    options = substitution_options(
        source,
        [source, matching, other, duplicate],
        available_equipment={"Dumbbell"},
        present_ids={"3"},
    )

    assert [item["id"] for item in options] == ["2"]


def test_substitution_requires_a_quality_match_for_press_and_core():
    bench = exercise("1", "Barbell Bench Press", "Pectorals", "Barbell")
    dumbbell_bench = exercise("2", "Dumbbell Bench Press", "Pectorals", "Dumbbell")
    archer_push_up = exercise("3", "Archer Push Up", "Pectorals", "Body Weight")
    crunch = exercise("4", "Cable Kneeling Crunch", "Abs", "Cable", "isolation")
    reverse_crunch = exercise("5", "Cable Reverse Crunch", "Abs", "Cable", "isolation")
    side_bend = exercise("6", "Dumbbell Side Bend", "Abs", "Dumbbell", "isolation")

    assert [item["id"] for item in substitution_options(bench, [bench, dumbbell_bench, archer_push_up])] == ["2"]
    assert [item["id"] for item in substitution_options(crunch, [crunch, reverse_crunch, side_bend])] == ["5"]


def test_leg_press_accepts_glute_tagged_leg_press_before_squats():
    leg_press = exercise("1", "Lever Leg Press", "Quads", "Leverage Machine")
    smith_leg_press = exercise("2", "Smith Leg Press", "Glutes", "Smith Machine")
    squat = exercise("3", "Barbell Squat", "Quads", "Barbell")

    assert [item["id"] for item in substitution_options(leg_press, [leg_press, smith_leg_press, squat])] == ["2"]


def active_exercise(identifier, name, target, equipment, mechanic="compound"):
    return {
        "id": identifier,
        "name": name,
        "target": target,
        "bodyPart": "Upper Legs",
        "equipment": equipment,
        "mechanic": mechanic,
        "force": "push",
        "difficulty": "intermediate",
        "secondaryMuscles": ["triceps"],
    }


def workout_exercise(identifier, name, catalog_key=None):
    return SimpleNamespace(
        catalog_key=catalog_key or f"workoutx:{identifier}",
        name=name,
        sets=3,
        reps="8-12",
        rest_seconds=90,
        effort_guidance=None,
    )


def test_active_catalog_excludes_self_and_exercises_already_in_the_workout(app):
    source = workout_exercise("1", "Barbell Bench Press")
    present = workout_exercise("2", "Dumbbell Bench Press")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="1", data=active_exercise("1", "Barbell Bench Press", "Pectorals", "Barbell")),
            WorkoutXExercise(provider_id="2", data=active_exercise("2", "Dumbbell Bench Press", "Pectorals", "Dumbbell")),
            WorkoutXExercise(provider_id="3", data=active_exercise("3", "Cable Bench Press", "Pectorals", "Cable")),
        ])
        db.session.commit()

        options = replacement_options(source, present_exercises=[source, present])

    assert [item["catalog_key"] for item in options] == ["workoutx:3"]


def test_active_catalog_maps_legacy_exercises_through_catalog_aliases(app):
    source = workout_exercise("legacy", "Supino reto com barra", "supino_reto_barra")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="1", data=active_exercise("1", "Barbell Bench Press", "Pectorals", "Barbell")),
            WorkoutXExercise(provider_id="2", data=active_exercise("2", "Dumbbell Bench Press", "Pectorals", "Dumbbell")),
        ])
        db.session.commit()

        options = replacement_options(source, present_exercises=[source])

    assert [item["catalog_key"] for item in options] == ["workoutx:2"]


def test_active_catalog_prefers_leg_press_and_rejects_distant_core_matches(app):
    leg_press = workout_exercise("1", "Lever Leg Press")
    crunch = workout_exercise("4", "Cable Kneeling Crunch")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="1", data=active_exercise("1", "Lever Leg Press", "Quads", "Leverage Machine")),
            WorkoutXExercise(provider_id="2", data=active_exercise("2", "Smith Leg Press", "Glutes", "Smith Machine")),
            WorkoutXExercise(provider_id="3", data=active_exercise("3", "Barbell Squat", "Quads", "Barbell")),
            WorkoutXExercise(provider_id="4", data=active_exercise("4", "Cable Kneeling Crunch", "Abs", "Cable", "isolation")),
            WorkoutXExercise(provider_id="5", data=active_exercise("5", "Cable Reverse Crunch", "Abs", "Cable", "isolation")),
            WorkoutXExercise(provider_id="6", data=active_exercise("6", "Dumbbell Side Bend", "Abs", "Dumbbell", "isolation")),
        ])
        db.session.commit()

        leg_press_options = replacement_options(leg_press)
        crunch_options = replacement_options(crunch)

    assert [item["catalog_key"] for item in leg_press_options] == ["workoutx:2"]
    assert [item["catalog_key"] for item in crunch_options] == ["workoutx:5"]
