from types import SimpleNamespace

import pytest

from src.models.user import WorkoutSessionExerciseOverride, WorkoutXExercise, db
from src.services.workout_plans import replacement_options, workoutx_display_name
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


@pytest.fixture(autouse=True)
def synthetic_workoutx_names(monkeypatch):
    from src.services import workout_plans

    actual_name = workout_plans.workoutx_display_name
    monkeypatch.setattr(
        workout_plans,
        "workoutx_display_name",
        lambda provider_id: f"Exercício {provider_id}" if str(provider_id) in {"1", "2", "3", "4", "5", "6"} else actual_name(provider_id),
    )


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


def test_workoutx_replacement_uses_brazilian_name_and_preserves_gif_key(app):
    source = workout_exercise("0201", "Cable Pushdown")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="0201", data=active_exercise("0201", "Cable Pushdown", "Triceps", "Cable", "isolation")),
            WorkoutXExercise(provider_id="0241", data=active_exercise("0241", "Cable Triceps Pushdown (v-bar)", "Triceps", "Cable", "isolation")),
        ])
        db.session.commit()

        options = replacement_options(source, present_exercises=[source])

    assert [(item["catalog_key"], item["name"]) for item in options] == [
        ("workoutx:0241", "Tríceps na polia com barra V")
    ]
    assert workoutx_display_name("999999") is None


def test_untranslated_workoutx_candidate_falls_back_to_local_catalog(app):
    source = workout_exercise("0025", "Supino reto com barra", "supino_reto_barra")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="0025", data=active_exercise("0025", "Barbell Bench Press", "Pectorals", "Barbell")),
            WorkoutXExercise(provider_id="999999", data=active_exercise("999999", "Cable Bench Press", "Pectorals", "Cable")),
        ])
        db.session.commit()

        options = replacement_options(source, present_exercises=[source])

    assert options
    assert all(not item["catalog_key"].startswith("workoutx:") for item in options)
    assert all(item["name"] for item in options)


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


def test_workoutx_replacement_weight_fits_persisted_field_limit(app):
    source = workout_exercise("1", "Cable Pulldown")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="1", data=active_exercise("1", "Cable Pulldown", "Lats", "Cable")),
            WorkoutXExercise(provider_id="2", data=active_exercise("2", "Band Pulldown", "Lats", "Resistance Band")),
        ])
        db.session.commit()

        options = replacement_options(source, present_exercises=[source])

    assert options
    assert len(options[0]["weight"]) <= WorkoutSessionExerciseOverride.weight.type.length


def test_workoutx_replacements_add_bodyweight_and_free_weight_recommendations(app, monkeypatch):
    source = workout_exercise("1", "Cable Seated Row")
    with app.app_context():
        app.config["WORKOUTX_API_KEY"] = "wx_test"
        db.session.add(WorkoutXExercise(
            provider_id="1",
            data=active_exercise("1", "Cable Seated Row", "Lats", "Cable"),
        ))
        db.session.commit()

        monkeypatch.setattr(
            "src.services.workoutx.recommended_exercises",
            lambda _provider_id, kind: ([
                {"id": "2", "name": "Bodyweight Standing Row", "equipment": "Body Weight", "target": "Lats", "score": 95},
            ] if kind == "similar" else [
                {"id": "3", "name": "Dumbbell One Arm Row", "equipment": "Dumbbell", "target": "Lats", "score": 90},
            ]),
        )
        monkeypatch.setattr(
            "src.services.workoutx.get_exercise",
            lambda provider_id: active_exercise(
                provider_id,
                "Bodyweight Standing Row" if provider_id == "2" else "Dumbbell One Arm Row",
                "Lats",
                "Body Weight" if provider_id == "2" else "Dumbbell",
            ),
        )

        options = replacement_options(source, present_exercises=[source])

    assert {option["equipment"] for option in options} >= {"Body Weight", "Dumbbell"}


def test_legacy_replacement_keeps_the_movement_when_primary_muscle_labels_differ(app):
    source = workout_exercise("legacy", "Rosca martelo", "rosca_martelo")

    with app.app_context():
        options = replacement_options(source, unavailable_equipment=[], available_equipment=[])

    assert options
    assert all(option["movement_pattern"] == "biceps" for option in options)


def test_substitution_omits_bands_when_a_compatible_preferred_option_exists():
    source = exercise("1", "Band Seated Row", "Lats", "Resistance Band")
    band = exercise("2", "Band One Arm Row", "Lats", "Resistance Band")
    dumbbell = exercise("3", "Dumbbell One Arm Row", "Lats", "Dumbbell")

    options = substitution_options(source, [band, dumbbell], provider_scores={"2": 100})

    assert [item["id"] for item in options] == ["3"]


def test_substitution_keeps_band_fallback_after_compatibility_and_availability_filters():
    source = exercise("1", "Cable Seated Row", "Lats", "Cable")
    band = exercise("2", "Band Seated Row", "Lats", "Resistance Band")
    dumbbell = exercise("3", "Dumbbell One Arm Row", "Lats", "Dumbbell")
    incompatible = exercise("4", "Cable Pulldown", "Lats", "Cable")

    assert [item["id"] for item in substitution_options(source, [band, incompatible])] == ["2"]
    assert [item["id"] for item in substitution_options(
        source, [band, dumbbell], available_equipment={"Resistance Band"},
    )] == ["2"]
    assert [item["id"] for item in substitution_options(
        source, [band, dumbbell], present_ids={"3"},
    )] == ["2"]


def test_active_catalog_prioritizes_free_weights_machines_and_bodyweight_without_bands(app):
    source = workout_exercise("1", "Cable Seated Row")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="1", data=active_exercise("1", "Cable Seated Row", "Lats", "Cable")),
            WorkoutXExercise(provider_id="2", data=active_exercise("2", "Band Seated Row", "Lats", "Resistance Band")),
            WorkoutXExercise(provider_id="3", data=active_exercise("3", "Dumbbell One Arm Row", "Lats", "Dumbbell")),
            WorkoutXExercise(provider_id="4", data=active_exercise("4", "Lever Seated Row", "Lats", "Leverage Machine")),
            WorkoutXExercise(provider_id="5", data=active_exercise("5", "Bodyweight Standing Row", "Lats", "Body Weight")),
        ])
        db.session.commit()

        options = replacement_options(source, limit=5)
        restricted = replacement_options(
            source, unavailable_equipment=["dumbbell", "machine", "bodyweight", "cable"],
        )

    assert [option["equipment"] for option in options] == ["Dumbbell", "Leverage Machine", "Body Weight"]
    assert [option["equipment"] for option in restricted] == ["Resistance Band"]


def test_active_catalog_accepts_questionnaire_equipment_names_for_band_fallback(app):
    source = workout_exercise("1", "Cable Pulldown")
    with app.app_context():
        db.session.add_all([
            WorkoutXExercise(provider_id="1", data=active_exercise("1", "Cable Pulldown", "Lats", "Cable")),
            WorkoutXExercise(provider_id="2", data=active_exercise("2", "Band Pulldown", "Lats", "Resistance Band")),
            WorkoutXExercise(provider_id="3", data=active_exercise("3", "Lever Pulldown", "Lats", "Leverage Machine")),
        ])
        db.session.commit()

        bands = replacement_options(source, available_equipment=["resistance_band"])
        machines = replacement_options(source, available_equipment=["machine", "resistance_band"])

    assert [option["equipment"] for option in bands] == ["Resistance Band"]
    assert [option["equipment"] for option in machines] == ["Leverage Machine"]


def test_legacy_catalog_uses_bands_only_when_preferred_equipment_is_unavailable(app):
    source = workout_exercise("legacy", "Puxada alta pela frente", "puxada_alta_frente")
    with app.app_context():
        options = replacement_options(source, unavailable_equipment=[], limit=10)
        fallback = replacement_options(source, available_equipment=["resistance_band"])

    assert options
    assert all(option["equipment"] != "resistance_band" for option in options)
    assert [option["equipment"] for option in fallback] == ["resistance_band"]
