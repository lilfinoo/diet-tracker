from src.services.workoutx_classification import classify_workoutx_exercise, movement_pattern


def exercise(name, target, body_part, mechanic, force):
    return {
        "name": name,
        "target": target,
        "bodyPart": body_part,
        "mechanic": mechanic,
        "force": force,
    }


def test_synonyms_refine_structured_movement_classification():
    assert movement_pattern(exercise("Cable Side Raise", "Delts", "Shoulders", "isolation", "pull")) == "shoulder_abduction"
    assert movement_pattern(exercise("Lever Knee Extension", "Quads", "Upper Legs", "isolation", "push")) == "knee_extension"
    assert movement_pattern(exercise("Leg Press Machine", "Quads", "Upper Legs", "compound", "push")) == "leg_press"
    assert movement_pattern(exercise("Lat Pull Down", "Lats", "Back", "compound", "pull")) == "vertical_pull"
    assert movement_pattern(exercise("Military Press", "Delts", "Shoulders", "compound", "push")) == "vertical_press"


def test_structured_metadata_classifies_role_without_name_match():
    result = classify_workoutx_exercise(exercise("Machine Movement", "Pectorals", "Chest", "compound", "push"))

    assert result["movement_pattern"] == "horizontal_press"
    assert result["training_role"] == "primary_compound"
