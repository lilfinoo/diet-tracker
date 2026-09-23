import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from src.services.workoutx_classification import classify_workoutx_exercise
from src.services.workoutx_substitutions import substitution_options


CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "exercises.json"
GOALS = {"hypertrophy", "strength", "conditioning", "fat_loss", "mobility"}
EXPERIENCE_LEVELS = {"beginner", "intermediate", "advanced"}
SPLITS_BY_DAYS = {
    1: {"full_body"},
    2: {"full_body", "upper_lower"},
    3: {"full_body", "upper_lower", "abc"},
    4: {"full_body", "upper_lower", "abc", "abcd"},
    5: {"full_body", "upper_lower", "abc", "abcd", "abcde"},
    6: {"full_body", "upper_lower", "abc", "abcd", "abcde"},
    7: {"full_body"},
}
EQUIPMENT_GROUPS = {
    "pull_up_bar": {"pullup_bar"},
    "cardio_machine": {"elliptical", "stationary_bike", "treadmill"},
    "outdoor": {"bodyweight", "jump_rope"},
}
TRAINING_ROLE_BY_KEY = {
    "agachamento_livre": "bilateral_squat",
    "agachamento_goblet": "bilateral_squat",
    "agachamento_corporal": "bilateral_squat",
    "leg_press_45": "machine_knee_press",
    "agachamento_bulgaro": "unilateral_squat",
    "levantamento_terra_convencional": "deadlift_from_floor",
    "levantamento_terra_romeno": "romanian_deadlift",
    "stiff_com_halteres": "romanian_deadlift",
    "elevacao_pelvica_barra": "hip_thrust",
    "ponte_de_gluteos": "hip_thrust",
    "supino_reto_barra": "chest_flat_press",
    "supino_reto_halteres": "chest_flat_press",
    "supino_maquina": "chest_flat_press",
    "flexao_de_bracos": "chest_flat_press",
    "supino_inclinado_barra": "chest_incline_press",
    "supino_inclinado_halteres": "chest_incline_press",
    "supino_declinado_barra": "chest_decline_press",
    "flexao_inclinada": "chest_bodyweight_press",
    "crucifixo_halteres": "chest_fly",
    "crossover_cabo": "chest_cable_adduction",
    "desenvolvimento_militar_barra": "shoulder_overhead_press",
    "desenvolvimento_halteres": "shoulder_overhead_press",
    "desenvolvimento_arnold": "shoulder_overhead_press",
    "desenvolvimento_maquina": "shoulder_overhead_press",
    "flexao_pike": "shoulder_bodyweight_press",
    "remada_curvada_barra": "back_hip_hinge_row",
    "remada_unilateral_halter": "back_unilateral_row",
    "remada_baixa_cabo": "back_supported_row",
    "remada_maquina": "back_supported_row",
    "remada_invertida": "back_bodyweight_row",
    "puxada_alta_frente": "back_pulldown",
    "puxada_com_elastico": "back_pulldown",
    "barra_fixa_pronada": "back_pronated_pullup",
    "barra_fixa_assistida": "back_pronated_pullup",
    "barra_fixa_supinada": "back_chinup",
    "mesa_flexora": "lying_leg_curl",
    "cadeira_flexora": "seated_leg_curl",
    "rosca_direta_barra": "biceps_standing_supinated_curl",
    "rosca_no_cabo": "biceps_standing_supinated_curl",
    "rosca_alternada": "biceps_alternating_curl",
    "rosca_martelo": "biceps_neutral_curl",
    "rosca_scott": "biceps_preacher_curl",
    "triceps_na_polia": "triceps_pushdown",
    "triceps_frances_halter": "triceps_overhead_extension",
    "triceps_testa": "triceps_lying_extension",
    "mergulho_no_banco": "triceps_compound_press",
    "flexao_diamante": "triceps_compound_press",
    "elevacao_lateral_halteres": "shoulder_lateral_raise",
    "elevacao_lateral_cabo": "shoulder_lateral_raise",
    "elevacao_lateral_maquina": "shoulder_lateral_raise",
    "elevacao_lateral_inclinada": "shoulder_lateral_raise",
}


class PlanValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("Invalid plan data")
        self.errors = errors


def _normalized(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]+", " ", "".join(char for char in value if not unicodedata.combining(char)).lower()).strip()


@lru_cache(maxsize=1)
def exercise_catalog():
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


@lru_cache(maxsize=1)
def catalog_by_key():
    return {exercise["key"]: exercise for exercise in exercise_catalog()}


@lru_cache(maxsize=1)
def catalog_aliases():
    aliases = {}
    for exercise in exercise_catalog():
        for value in (exercise["name"], *exercise["aliases"]):
            aliases[_normalized(value)] = exercise
    return aliases


def resolve_catalog_exercise(catalog_key=None, name=None):
    if str(catalog_key or "").startswith("workoutx:"):
        from src.models.user import WorkoutXExercise, db

        provider_id = str(catalog_key).split(":", 1)[1]
        item = db.session.get(WorkoutXExercise, provider_id)
        if item:
            return _workoutx_catalog_item(item.data)
    if catalog_key and catalog_key in catalog_by_key():
        return catalog_by_key()[catalog_key]
    return catalog_aliases().get(_normalized(name))


def expand_equipment(equipment):
    expanded = set(equipment or [])
    for value in list(expanded):
        expanded.update(EQUIPMENT_GROUPS.get(value, set()))
    return expanded


def recommend_split(days_per_week, experience_level):
    if days_per_week in {1, 7}:
        return "full_body"
    if days_per_week == 2:
        return "full_body"
    if days_per_week == 3:
        return "full_body" if experience_level == "beginner" else "abc"
    if days_per_week == 4:
        return "upper_lower"
    if days_per_week == 5:
        return "abcde"
    return "abc"


def workout_day_specs(split_type, days_per_week):
    if split_type == "upper_lower":
        occurrences = {"UPPER": 0, "LOWER": 0}
        specs = []
        for index in range(1, days_per_week + 1):
            code = "UPPER" if index % 2 else "LOWER"
            occurrences[code] += 1
            upper = code == "UPPER"
            specs.append({
                "code": f"{code}_{occurrences[code]}",
                "title": f"{'Upper' if upper else 'Lower'} {occurrences[code]}",
                "order": index,
                "focus_guidance": (
                    "membros superiores com empurrar e puxar"
                    if upper
                    else "pernas com dominante de joelho, cadeia posterior e flexão de joelho"
                ),
                "required_groups": (
                    [["horizontal_push", "vertical_push"], ["horizontal_pull", "vertical_pull"]]
                    if upper
                    else [["squat", "knee_extension"], ["hinge"], ["knee_flexion"]]
                ),
            })
        return specs
    if split_type == "full_body":
        return [
            {
                "code": f"FB_{index}",
                "title": f"Full Body {index}",
                "order": index,
                "focus_guidance": "corpo inteiro com um movimento de pernas, um empurrar e um puxar; varie a ênfase entre os dias",
                "required_groups": [["squat", "hinge", "knee_extension", "knee_flexion"], ["horizontal_push", "vertical_push"], ["horizontal_pull", "vertical_pull"]],
            }
            for index in range(1, days_per_week + 1)
        ]
    templates = {
        "abc": [
            ("A", "Peito, ombros e tríceps", "empurrar: peito em ângulos complementares, ombros e tríceps", [["horizontal_push"], ["vertical_push", "lateral_raise"], ["triceps"]]),
            ("B", "Costas e bíceps", "puxar: uma puxada vertical, uma remada e bíceps", [["vertical_pull"], ["horizontal_pull"], ["biceps"]]),
            ("C", "Pernas e core", "pernas completas: dominante de joelho, cadeia posterior, flexão de joelho e core", [["squat", "knee_extension"], ["hinge"], ["knee_flexion"], ["core_flexion", "core_stability"]]),
        ],
        "abcd": [
            ("A", "Peito e tríceps", "peito com ângulos complementares e tríceps", [["horizontal_push"], ["triceps"]]),
            ("B", "Costas e bíceps", "costas com puxada vertical, remada e bíceps", [["vertical_pull"], ["horizontal_pull"], ["biceps"]]),
            ("C", "Pernas", "pernas com dominante de joelho, cadeia posterior e flexão de joelho", [["squat", "knee_extension"], ["hinge"], ["knee_flexion"]]),
            ("D", "Ombros e core", "ombros com desenvolvimento, elevação lateral e core", [["vertical_push"], ["lateral_raise"], ["core_flexion", "core_stability"]]),
        ],
        "abcde": [
            ("A", "Peito", "peito com pressão reta, inclinada e adução; sem repetir o mesmo ângulo", [["horizontal_push"]]),
            ("B", "Costas", "costas com puxada vertical e remada", [["vertical_pull"], ["horizontal_pull"]]),
            ("C", "Pernas", "pernas com dominante de joelho, cadeia posterior e flexão de joelho", [["squat", "knee_extension"], ["hinge"], ["knee_flexion"]]),
            ("D", "Ombros", "ombros com desenvolvimento e elevação lateral", [["vertical_push"], ["lateral_raise"]]),
            ("E", "Braços e core", "bíceps, tríceps e core", [["biceps"], ["triceps"], ["core_flexion", "core_stability"]]),
        ],
    }
    base = templates[split_type]
    repeated = days_per_week > len(base)
    return [
        {
            "code": f"{code}_{cycle}" if repeated else code,
            "title": f"{title} {cycle}" if repeated else title,
            "order": index,
            "focus_guidance": guidance if cycle == 1 else f"{guidance}; use exercícios ou ênfases diferentes da primeira sessão",
            "required_groups": required_groups,
        }
        for index in range(1, days_per_week + 1)
        for cycle, (code, title, guidance, required_groups) in [
            ((index - 1) // len(base) + 1, base[(index - 1) % len(base)])
        ]
    ]


def allowed_groups_for_day(split_type, code):
    core = {"core_flexion", "core_stability", "cardio"}
    upper = {"horizontal_push", "vertical_push", "horizontal_pull", "vertical_pull", "lateral_raise", "biceps", "triceps"}
    lower = {"squat", "hinge", "knee_flexion", "knee_extension", "calf_raise"}
    base_code = code.split("_")[0]
    if split_type == "full_body":
        return upper | lower | core
    if split_type == "upper_lower":
        return (upper | core) if base_code == "UPPER" else (lower | core)
    groups = {
        "abc": {
            "A": {"horizontal_push", "vertical_push", "lateral_raise", "triceps"} | core,
            "B": {"horizontal_pull", "vertical_pull", "biceps"} | core,
            "C": lower | core,
        },
        "abcd": {
            "A": {"horizontal_push", "triceps"} | core,
            "B": {"horizontal_pull", "vertical_pull", "biceps"} | core,
            "C": lower | core,
            "D": {"vertical_push", "lateral_raise", "horizontal_pull"} | core,
        },
        "abcde": {
            "A": {"horizontal_push"} | core,
            "B": {"horizontal_pull", "vertical_pull"} | core,
            "C": lower | core,
            "D": {"vertical_push", "lateral_raise", "horizontal_pull"} | core,
            "E": {"biceps", "triceps"} | core,
        },
    }
    return groups[split_type][base_code]


def required_training_roles_for_day(split_type, code):
    if split_type == "abcde" and code.split("_")[0] == "A":
        return [
            {"chest_flat_press"},
            {"chest_incline_press"},
            {"chest_decline_press", "chest_fly", "chest_cable_adduction"},
        ]
    return []


def workout_selection_limits(split_type, code):
    allowed_groups = allowed_groups_for_day(split_type, code)
    dedicated_chest_day = split_type in {"abcd", "abcde"} and code.split("_")[0] == "A"
    return {
        "unique_catalog_keys": True,
        "max_per_group": {
            group: 4 if dedicated_chest_day and group == "horizontal_push" else 2
            for group in sorted(allowed_groups)
        },
        "max_per_training_role": 2,
    }


def invalid_workout_day_numbers(errors, days_per_week):
    day_numbers = {
        int(match.group(1))
        for field in errors
        if (match := re.match(r"^days\.(\d+)(?:\.|$)", field))
        and 1 <= int(match.group(1)) <= days_per_week
    }
    if not day_numbers or any(not field.startswith("days.") for field in errors):
        return list(range(1, days_per_week + 1))
    return sorted(day_numbers)


def merge_workout_day_repairs(previous_plan, repair, invalid_day_numbers, days_per_week):
    previous_days = previous_plan.get("days") if isinstance(previous_plan, dict) else None
    repaired_days = repair.get("days") if isinstance(repair, dict) else None
    if not isinstance(previous_days, list) or not isinstance(repaired_days, list):
        raise PlanValidationError({"days": "A IA retornou um reparo de treino inválido."})

    expected = set(invalid_day_numbers)
    replacements = {}
    for repaired_day in repaired_days:
        if not isinstance(repaired_day, dict):
            raise PlanValidationError({"days": "A IA retornou um reparo de treino inválido."})
        try:
            day_number = int(repaired_day.get("day_number"))
        except (TypeError, ValueError):
            raise PlanValidationError({"days": "O reparo não identificou o dia corrigido."}) from None
        if day_number not in expected or day_number in replacements:
            raise PlanValidationError({"days": "O reparo alterou um dia que já estava válido."})
        replacements[day_number] = {key: value for key, value in repaired_day.items() if key != "day_number"}

    if set(replacements) != expected:
        raise PlanValidationError({"days": "O reparo não corrigiu todos os dias inválidos."})

    merged = dict(previous_plan)
    merged_days = []
    for day_number in range(1, days_per_week + 1):
        if day_number in replacements:
            merged_days.append(replacements[day_number])
        elif day_number <= len(previous_days):
            merged_days.append(previous_days[day_number - 1])
        else:
            raise PlanValidationError({"days": "O plano anterior não contém todos os dias válidos."})
    merged["days"] = merged_days
    return merged


def validate_workout_exercise_selection(data, questionnaire, contract=None):
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, list):
        return

    errors = {}
    contract = contract or build_workout_contract(questionnaire)
    specs = contract["effective"]["days"]
    for day_index, (day, spec) in enumerate(zip(days, specs), start=1):
        exercises = day.get("exercises") if isinstance(day, dict) else None
        if not isinstance(exercises, list):
            continue
        limits = spec["selection_limits"]
        slots = spec["slots"]
        if slots:
            slot_by_id = {slot["slot_id"]: slot for slot in slots}
            seen_slots = set()
            if len(exercises) != len(slots):
                errors[f"days.{day_index}.slots.count"] = (
                    f"O dia deve preencher exatamente {len(slots)} slots, um exercício por slot."
                )
            for exercise_index, exercise in enumerate(exercises, start=1):
                if not isinstance(exercise, dict):
                    continue
                slot_id = str(exercise.get("slot_id") or "")
                if slot_id not in slot_by_id:
                    errors[f"days.{day_index}.exercises.{exercise_index}.slot_id"] = "Slot inválido ou ausente."
                    continue
                if slot_id in seen_slots:
                    errors[f"days.{day_index}.slots.{slot_id}"] = "Cada slot deve ser preenchido uma única vez."
                    continue
                seen_slots.add(slot_id)
                catalog_item = resolve_catalog_exercise(exercise.get("catalog_key"), exercise.get("name"))
                if catalog_item and catalog_item["key"] not in slot_by_id[slot_id]["allowed_catalog_keys"]:
                    errors[f"days.{day_index}.exercises.{exercise_index}.catalog_key"] = (
                        f"O exercício não atende ao contrato do slot {slot_id}."
                    )
            for missing_slot in set(slot_by_id) - seen_slots:
                errors[f"days.{day_index}.slots.{missing_slot}"] = "Slot obrigatório não preenchido."
        used_keys = {}
        group_counts = {}
        role_counts = {}
        for exercise_index, exercise in enumerate(exercises, start=1):
            if not isinstance(exercise, dict):
                continue
            catalog_item = resolve_catalog_exercise(exercise.get("catalog_key"), exercise.get("name"))
            if not catalog_item:
                continue
            catalog_key = catalog_item["key"]
            if catalog_key in used_keys:
                errors[f"days.{day_index}.duplicates.{catalog_key}"] = (
                    f"O exercício {catalog_key} está repetido nas posições "
                    f"{used_keys[catalog_key]} e {exercise_index}; catalog_key deve ser único no dia."
                )
                continue
            used_keys[catalog_key] = exercise_index

            group = catalog_item["substitution_group"]
            group_counts[group] = group_counts.get(group, 0) + 1
            group_limit = limits["max_per_group"].get(group, 2)
            if group_counts[group] > group_limit:
                errors[f"days.{day_index}.groups.{group}"] = (
                    f"O grupo {group} aparece {group_counts[group]} vezes; o máximo neste dia é {group_limit}."
                )

            role = training_role(catalog_item)
            if role:
                role_counts[role] = role_counts.get(role, 0) + 1
                role_limit = limits["max_per_training_role"]
                if role_counts[role] > role_limit:
                    errors[f"days.{day_index}.roles.{role}"] = (
                        f"A função {role} aparece {role_counts[role]} vezes; o máximo neste dia é {role_limit}."
                    )
    if errors:
        raise PlanValidationError(errors)


def training_role(exercise):
    return TRAINING_ROLE_BY_KEY.get(exercise["key"])


def validate_workout_questionnaire(data):
    errors = {}
    goal = str(data.get("goal", "")).strip()
    experience = str(data.get("experience_level", "")).strip()
    try:
        days = int(data.get("days_per_week"))
    except (TypeError, ValueError):
        days = 0
    try:
        duration = int(data.get("session_duration"))
    except (TypeError, ValueError):
        duration = 0

    if goal not in GOALS:
        errors["goal"] = "Selecione um objetivo válido."
    if experience not in EXPERIENCE_LEVELS:
        errors["experience_level"] = "Selecione seu nível de experiência."
    if days not in SPLITS_BY_DAYS:
        errors["days_per_week"] = "Escolha entre 1 e 7 dias por semana."
    if duration not in {20, 30, 45, 60, 75, 90}:
        errors["session_duration"] = "Selecione uma duração válida."

    split_type = str(data.get("split_type") or recommend_split(days, experience)).strip()
    if days in SPLITS_BY_DAYS and split_type not in SPLITS_BY_DAYS[days]:
        errors["split_type"] = "Essa divisão não combina com a frequência selecionada."

    equipment = data.get("equipment", [])
    known_equipment = {exercise["equipment"] for exercise in exercise_catalog()} | {"full_gym", *EQUIPMENT_GROUPS}
    if not isinstance(equipment, list) or not equipment or len(equipment) > 12:
        errors["equipment"] = "Selecione ao menos uma opção de equipamento."
        equipment = []
    elif any(item not in known_equipment for item in equipment):
        errors["equipment"] = "Há um equipamento inválido na seleção."

    limitations = str(data.get("limitations", "")).strip()
    priorities = str(data.get("priorities", "")).strip()
    avoid_exercises = str(data.get("avoid_exercises", "")).strip()
    if len(limitations) > 500:
        errors["limitations"] = "Resuma as limitações em até 500 caracteres."
    if len(priorities) > 300:
        errors["priorities"] = "Resuma as prioridades em até 300 caracteres."
    if len(avoid_exercises) > 300:
        errors["avoid_exercises"] = "Resuma os exercícios a evitar em até 300 caracteres."
    questionnaire = {
        "goal": goal,
        "experience_level": experience,
        "days_per_week": days,
        "split_type": split_type,
        "session_duration": duration,
        "equipment": equipment,
        "limitations": limitations,
        "priorities": priorities,
        "avoid_exercises": avoid_exercises,
    }
    if errors:
        raise PlanValidationError(errors)
    return questionnaire


def catalog_for_prompt(questionnaire):
    equipment = expand_equipment(questionnaire["equipment"])
    full_gym = "full_gym" in equipment
    allowed_difficulty = {
        "beginner": {"beginner"},
        "intermediate": {"beginner", "intermediate"},
        "advanced": EXPERIENCE_LEVELS,
    }[questionnaire["experience_level"]]
    exercises = [
        item for item in exercise_catalog()
        if item["difficulty"] in allowed_difficulty
        and (full_gym or item["equipment"] in equipment or item["equipment"] == "bodyweight")
    ]
    return [
        {
            "key": item["key"],
            "name": item["name"],
            "group": item["substitution_group"],
            "training_role": training_role(item),
            "muscle": item["primary_muscle"],
            "secondary_muscles": item["secondary_muscles"],
            "equipment": item["equipment"],
            "difficulty": item["difficulty"],
        }
        for item in exercises
    ]


def _abcde_90_slot_definitions():
    return {
        "A": [
            ("A_flat_press", ["horizontal_push"], ["chest_flat_press"], "pressão reta"),
            ("A_incline_press", ["horizontal_push"], ["chest_incline_press"], "pressão inclinada"),
            ("A_third_chest", ["horizontal_push"], ["chest_decline_press", "chest_fly", "chest_cable_adduction"], "terceira função de peito"),
            ("A_core_flexion", ["core_flexion"], [], "core em flexão"),
            ("A_core_stability", ["core_stability"], [], "estabilidade de core"),
            ("A_cardio", ["cardio"], [], "condicionamento complementar"),
        ],
        "B": [
            ("B_vertical_pull_1", ["vertical_pull"], [], "puxada vertical 1"),
            ("B_vertical_pull_2", ["vertical_pull"], [], "puxada vertical 2"),
            ("B_horizontal_pull_1", ["horizontal_pull"], [], "remada horizontal 1"),
            ("B_horizontal_pull_2", ["horizontal_pull"], [], "remada horizontal 2"),
            ("B_core_stability", ["core_stability"], [], "estabilidade de core"),
            ("B_cardio", ["cardio"], [], "condicionamento complementar"),
        ],
        "C": [
            ("C_squat", ["squat"], [], "dominante de joelho"),
            ("C_knee_extension", ["knee_extension"], [], "extensão de joelho"),
            ("C_hinge", ["hinge"], [], "cadeia posterior"),
            ("C_knee_flexion", ["knee_flexion"], [], "flexão de joelho"),
            ("C_calf_raise", ["calf_raise"], [], "panturrilhas"),
            ("C_core_stability", ["core_stability"], [], "estabilidade de core"),
        ],
        "D": [
            ("D_vertical_push_1", ["vertical_push"], [], "desenvolvimento 1"),
            ("D_vertical_push_2", ["vertical_push"], [], "desenvolvimento 2"),
            ("D_lateral_raise_1", ["lateral_raise"], [], "deltoide lateral 1"),
            ("D_lateral_raise_2", ["lateral_raise"], [], "deltoide lateral 2"),
            ("D_rear_deltoid", ["horizontal_pull"], [], "deltoide posterior"),
            ("D_core_stability", ["core_stability"], [], "estabilidade de core"),
        ],
        "E": [
            ("E_biceps_1", ["biceps"], [], "bíceps 1"),
            ("E_biceps_2", ["biceps"], [], "bíceps 2"),
            ("E_triceps_1", ["triceps"], [], "tríceps 1"),
            ("E_triceps_2", ["triceps"], [], "tríceps 2"),
            ("E_core_flexion", ["core_flexion"], [], "core em flexão"),
            ("E_core_stability", ["core_stability"], [], "estabilidade de core"),
        ],
    }


_GROUP_FALLBACKS = {
    "horizontal_push": [["vertical_push"], ["triceps"], ["core_stability"], ["core_flexion"], ["cardio"]],
    "vertical_push": [["horizontal_push"], ["lateral_raise"], ["triceps"], ["core_stability"], ["cardio"]],
    "horizontal_pull": [["vertical_pull"], ["hinge"], ["core_stability"], ["core_flexion"], ["cardio"]],
    "vertical_pull": [["horizontal_pull"], ["hinge"], ["core_stability"], ["core_flexion"], ["cardio"]],
    "lateral_raise": [["vertical_push"], ["horizontal_pull"], ["core_stability"], ["cardio"]],
    "biceps": [["horizontal_pull", "vertical_pull"], ["core_stability"], ["core_flexion"], ["cardio"]],
    "triceps": [["horizontal_push", "vertical_push"], ["core_stability"], ["core_flexion"], ["cardio"]],
    "squat": [["knee_extension"], ["hinge"], ["core_stability"], ["cardio"]],
    "knee_extension": [["squat"], ["hinge"], ["core_stability"], ["cardio"]],
    "knee_flexion": [["hinge"], ["squat"], ["core_stability"], ["cardio"]],
    "hinge": [["knee_flexion"], ["squat"], ["core_stability"], ["cardio"]],
    "calf_raise": [["squat", "hinge"], ["cardio"], ["core_stability"]],
    "core_flexion": [["core_stability"], ["cardio"]],
    "core_stability": [["core_flexion"], ["cardio"]],
    "cardio": [["core_stability"], ["core_flexion"]],
}


_DAY_GROUP_PRIORITIES = {
    "full_body": ["core_stability", "hinge", "vertical_push", "vertical_pull", "knee_flexion", "squat", "horizontal_push", "horizontal_pull", "cardio"],
    "upper_lower:UPPER": ["horizontal_push", "horizontal_pull", "vertical_push", "vertical_pull", "lateral_raise", "biceps", "triceps", "core_stability"],
    "upper_lower:LOWER": ["squat", "hinge", "knee_flexion", "knee_extension", "calf_raise", "core_stability", "cardio"],
    "abc:A": ["horizontal_push", "vertical_push", "lateral_raise", "triceps", "core_stability", "cardio"],
    "abc:B": ["vertical_pull", "horizontal_pull", "biceps", "core_stability", "cardio"],
    "abc:C": ["squat", "hinge", "knee_flexion", "knee_extension", "calf_raise", "core_stability"],
    "abcd:A": ["horizontal_push", "triceps", "core_stability", "core_flexion", "cardio"],
    "abcd:B": ["vertical_pull", "horizontal_pull", "biceps", "core_stability", "cardio"],
    "abcd:C": ["squat", "hinge", "knee_flexion", "knee_extension", "calf_raise", "core_stability"],
    "abcd:D": ["vertical_push", "lateral_raise", "horizontal_pull", "core_stability", "core_flexion", "cardio"],
    "abcde:A": ["horizontal_push", "core_flexion", "core_stability", "cardio"],
    "abcde:B": ["vertical_pull", "horizontal_pull", "core_stability", "core_flexion", "cardio"],
    "abcde:C": ["squat", "hinge", "knee_flexion", "knee_extension", "calf_raise", "core_stability"],
    "abcde:D": ["vertical_push", "lateral_raise", "horizontal_pull", "core_stability", "cardio"],
    "abcde:E": ["biceps", "triceps", "core_flexion", "core_stability", "cardio"],
}


def _ideal_slot_definitions(questionnaire, spec):
    split_type = questionnaire["split_type"]
    base_code = spec["code"].split("_")[0]
    if split_type == "abcde" and questionnaire["session_duration"] == 90:
        return _abcde_90_slot_definitions()[base_code]

    definitions = []
    role_groups = {
        role: sorted({
            exercise["substitution_group"]
            for exercise in exercise_catalog()
            if training_role(exercise) == role
        })
        for alternatives in required_training_roles_for_day(split_type, spec["code"])
        for role in alternatives
    }
    covered_groups = set()
    for index, roles in enumerate(required_training_roles_for_day(split_type, spec["code"]), start=1):
        groups = sorted({group for role in roles for group in role_groups.get(role, [])})
        definitions.append((f"{spec['code']}_role_{index}", groups, sorted(roles), f"função obrigatória {index}"))
        covered_groups.update(groups)
    for index, groups in enumerate(spec.get("required_groups", []), start=1):
        if covered_groups.intersection(groups):
            continue
        definitions.append((f"{spec['code']}_coverage_{index}", list(groups), [], f"padrão obrigatório {index}"))

    minimum = 3 if questionnaire["session_duration"] <= 30 else 4 if questionnaire["session_duration"] <= 60 else 6
    target = max(minimum, len(definitions))
    priority_key = split_type if split_type == "full_body" else f"{split_type}:{base_code}"
    priorities = _DAY_GROUP_PRIORITIES[priority_key]
    position = 0
    while len(definitions) < target:
        group = priorities[position % len(priorities)]
        definitions.append((f"{spec['code']}_complement_{len(definitions) + 1}", [group], [], f"complemento {group}"))
        position += 1
    return definitions


def _slot_candidates(catalog, groups, roles, excluded):
    return [
        item
        for item in catalog
        if item["key"] not in excluded
        and item["group"] in groups
        and (not roles or item["training_role"] in roles)
    ]


def _fallback_tiers(groups):
    tiers = []
    for group in groups:
        for alternatives in _GROUP_FALLBACKS.get(group, []):
            if alternatives not in tiers:
                tiers.append(alternatives)
    return tiers


def build_workout_contract(questionnaire):
    catalog = catalog_for_prompt(questionnaire)
    ideal_days = []
    effective_days = []
    adaptations = []
    warnings = []
    severe_adaptation = False

    for spec in workout_day_specs(questionnaire["split_type"], questionnaire["days_per_week"]):
        day_adaptation_start = len(adaptations)
        definitions = _ideal_slot_definitions(questionnaire, spec)
        ideal_slots = [
            {
                "slot_id": slot_id,
                "purpose": purpose,
                "allowed_groups": groups,
                "allowed_training_roles": roles,
            }
            for slot_id, groups, roles, purpose in definitions
        ]
        ideal_days.append({**spec, "slots": ideal_slots})

        selected_keys = set()
        group_counts = {}
        role_counts = {}
        effective_slots = []
        dedicated_chest_day = questionnaire["split_type"] in {"abcd", "abcde"} and spec["code"].split("_")[0] == "A"
        for slot_id, ideal_groups, ideal_roles, purpose in definitions:
            tiers = [(ideal_groups, ideal_roles, "ideal")]
            tiers.extend((groups, [], "fallback") for groups in _fallback_tiers(ideal_groups))
            resolved = None
            for groups, roles, resolution in tiers:
                eligible_groups = [
                    group
                    for group in groups
                    if group_counts.get(group, 0) < (4 if dedicated_chest_day and group == "horizontal_push" else 2)
                ]
                candidates = [
                    item
                    for item in _slot_candidates(catalog, eligible_groups, roles, selected_keys)
                    if not item["training_role"] or role_counts.get(item["training_role"], 0) < 2
                ]
                if candidates:
                    chosen_group = candidates[0]["group"]
                    resolved = (
                        [chosen_group],
                        roles,
                        resolution,
                        [item for item in candidates if item["group"] == chosen_group],
                    )
                    break
            if resolved is None:
                adaptations.append({
                    "day_code": spec["code"],
                    "slot_id": slot_id,
                    "from_groups": ideal_groups,
                    "from_roles": ideal_roles,
                    "to_groups": [],
                    "resolution": "omitted",
                })
                severe_adaptation = True
                continue
            groups, roles, resolution, candidates = resolved
            selected_keys.add(candidates[0]["key"])
            group_counts[groups[0]] = group_counts.get(groups[0], 0) + 1
            representative_role = candidates[0]["training_role"]
            if representative_role:
                role_counts[representative_role] = role_counts.get(representative_role, 0) + 1
            effective_slots.append({
                "slot_id": slot_id,
                "purpose": purpose,
                "ideal_groups": ideal_groups,
                "ideal_training_roles": ideal_roles,
                "allowed_groups": groups,
                "allowed_training_roles": roles,
                "allowed_catalog_keys": [
                    item["key"]
                    for item in _slot_candidates(catalog, groups, roles, set())
                ],
                "resolution": resolution,
            })
            if resolution != "ideal":
                adaptations.append({
                    "day_code": spec["code"],
                    "slot_id": slot_id,
                    "from_groups": ideal_groups,
                    "from_roles": ideal_roles,
                    "to_groups": groups,
                    "resolution": resolution,
                })
                if any(group in {"horizontal_pull", "vertical_pull", "biceps"} for group in ideal_groups):
                    severe_adaptation = True

        minimum = 3 if questionnaire["session_duration"] <= 30 else 4 if questionnaire["session_duration"] <= 60 else 6
        if len(effective_slots) < minimum:
            warnings.append(f"{spec['title']}: a sessão pode ficar mais curta que {questionnaire['session_duration']} minutos.")
        effective_groups = sorted(
            set(allowed_groups_for_day(questionnaire["split_type"], spec["code"]))
            | {group for slot in effective_slots for group in slot["allowed_groups"]}
        )
        duration_maximum = 5 if questionnaire["session_duration"] <= 30 else 7 if questionnaire["session_duration"] <= 60 else 8
        effective_days.append({
            **spec,
            "focus_guidance": spec["focus_guidance"] if len(adaptations) == day_adaptation_start else f"{spec['focus_guidance']}; adapte ao catálogo disponível sem inventar exercícios",
            "required_groups": [],
            "required_training_roles": [],
            "allowed_groups": effective_groups,
            "selection_limits": {
                "unique_catalog_keys": True,
                "max_per_group": {
                    group: 4 if dedicated_chest_day and group == "horizontal_push" else 2
                    for group in effective_groups
                },
                "max_per_training_role": 2,
            },
            "slots": effective_slots,
            "minimum_exercises": len(effective_slots),
            "maximum_exercises": max(len(effective_slots), duration_maximum),
        })

    quality = "limited" if severe_adaptation else "adapted" if adaptations else "ideal"
    if quality == "adapted":
        warnings.insert(0, "Alguns padrões foram adaptados aos equipamentos disponíveis.")
    elif quality == "limited":
        warnings.insert(0, "A divisão escolhida tem cobertura limitada com os equipamentos disponíveis.")
    ideal_slot_count = sum(len(day["slots"]) for day in ideal_days)
    score = round(100 * (ideal_slot_count - len(adaptations)) / ideal_slot_count) if ideal_slot_count else 0
    prompt_keys = {
        key
        for day in effective_days
        for slot in day["slots"]
        for key in slot["allowed_catalog_keys"]
    }
    return {
        "split_type": questionnaire["split_type"],
        "ideal": {"days": ideal_days},
        "effective": {"days": effective_days},
        "quality": quality,
        "quality_score": score,
        "adaptations": adaptations,
        "warnings": warnings,
        "exercise_catalog": [item for item in catalog if item["key"] in prompt_keys],
    }


def recommend_workout_split(questionnaire):
    candidates = []
    for split_type in SPLITS_BY_DAYS[questionnaire["days_per_week"]]:
        candidate_questionnaire = {**questionnaire, "split_type": split_type}
        contract = build_workout_contract(candidate_questionnaire)
        candidates.append((contract["quality_score"], split_type))
    best_score = max(score for score, _ in candidates)
    best_splits = {split_type for score, split_type in candidates if score == best_score}
    preferred = recommend_split(questionnaire["days_per_week"], questionnaire["experience_level"])
    if questionnaire["equipment"] == ["bodyweight"] and "full_body" in best_splits:
        return "full_body"
    return preferred if preferred in best_splits else sorted(best_splits)[0]


def workout_day_slots(questionnaire, spec, catalog=None):
    contract = build_workout_contract(questionnaire)
    return next(day["slots"] for day in contract["effective"]["days"] if day["code"] == spec["code"])


def normalize_workout_output(data, questionnaire, contract=None):
    errors = {}
    if not isinstance(data, dict) or data.get("type") != "workout_plan":
        raise PlanValidationError({"plan": "A IA retornou um formato de treino inválido."})
    days = data.get("days")
    contract = contract or build_workout_contract(questionnaire)
    specs = contract["effective"]["days"]
    if not isinstance(days, list) or len(days) != len(specs):
        raise PlanValidationError({"days": "A quantidade de treinos gerada está incorreta."})

    normalized_days = []
    allowed_keys = {item["key"] for item in catalog_for_prompt(questionnaire)}
    allowed_difficulty = {
        "beginner": {"beginner"},
        "intermediate": {"beginner", "intermediate"},
        "advanced": EXPERIENCE_LEVELS,
    }[questionnaire["experience_level"]]
    for day_index, (day, spec) in enumerate(zip(days, specs), start=1):
        exercises = day.get("exercises") if isinstance(day, dict) else None
        duration = questionnaire["session_duration"]
        minimum = spec["minimum_exercises"]
        maximum = spec["maximum_exercises"]
        if isinstance(exercises, list) and len(exercises) > maximum:
            # The generator orders accessories and core last, so retain the primary work.
            exercises = exercises[:maximum]
        if not isinstance(exercises, list) or len(exercises) < minimum:
            errors[f"days.{day_index}"] = f"Para {duration} minutos, cada treino deve ter entre {minimum} e {maximum} exercícios."
            continue
        normalized_exercises = []
        used_keys = set()
        training_role_counts = {}
        group_counts = {}
        for exercise_index, exercise in enumerate(exercises, start=1):
            if not isinstance(exercise, dict):
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "Exercício inválido."
                continue
            catalog_item = resolve_catalog_exercise(exercise.get("catalog_key"), exercise.get("name"))
            if not catalog_item:
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "Exercício desconhecido."
                continue
            if catalog_item["key"] in used_keys:
                continue
            if catalog_item["key"] not in allowed_keys:
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "O exercício exige equipamento indisponível ou não combina com o nível informado."
                continue
            if catalog_item["difficulty"] not in allowed_difficulty:
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "Exercício avançado demais para o nível informado."
                continue
            role = training_role(catalog_item)
            group = catalog_item["substitution_group"]
            if role and training_role_counts.get(role, 0) >= 2:
                continue
            group_limit = spec["selection_limits"]["max_per_group"].get(group, 2)
            if group_counts.get(group, 0) >= group_limit:
                continue
            try:
                sets = int(exercise.get("sets"))
                rest_seconds = int(exercise.get("rest_seconds", 60))
            except (TypeError, ValueError):
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "Séries ou descanso inválidos."
                continue
            reps = str(exercise.get("reps", "")).strip()
            if not 1 <= sets <= 6 or not reps or len(reps) > 30 or not 20 <= rest_seconds <= 300:
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "Prescrição de exercício inválida."
                continue
            used_keys.add(catalog_item["key"])
            if role:
                training_role_counts[role] = training_role_counts.get(role, 0) + 1
            group_counts[group] = group_counts.get(group, 0) + 1
            normalized_exercises.append({
                "catalog_key": catalog_item["key"],
                "name": catalog_item["name"],
                "movement_pattern": catalog_item["movement_pattern"],
                "primary_muscle": catalog_item["primary_muscle"],
                "equipment": catalog_item["equipment"],
                "difficulty": catalog_item["difficulty"],
                "sets": sets,
                "reps": reps,
                "weight": str(exercise.get("weight", "Carga confortável")).strip()[:50],
                "rest_seconds": rest_seconds,
                "effort_guidance": str(exercise.get("effort_guidance", "Termine com 2 repetições em reserva")).strip()[:100],
                "notes": str(exercise.get("notes", "")).strip()[:500] or None,
                "order": exercise_index,
            })
        if len(normalized_exercises) < minimum:
            errors[f"days.{day_index}.volume"] = (
                f"Após remover redundâncias, o treino precisa manter ao menos {minimum} exercícios."
            )
        selected_groups = {item["substitution_group"] for item in (catalog_by_key()[exercise["catalog_key"]] for exercise in normalized_exercises)}
        allowed_groups = set(spec["allowed_groups"])
        if selected_groups - allowed_groups:
            errors[f"days.{day_index}.focus"] = "O treino contém exercícios que não pertencem ao foco deste dia."
        for requirement_index, alternatives in enumerate(spec.get("required_groups", []), start=1):
            if not selected_groups.intersection(alternatives):
                errors[f"days.{day_index}.coverage.{requirement_index}"] = "O treino não cobriu todos os padrões necessários para o foco do dia."
        selected_roles = {
            role
            for exercise in normalized_exercises
            if (role := training_role(catalog_by_key()[exercise["catalog_key"]]))
        }
        for requirement_index, alternatives in enumerate(spec["required_training_roles"], start=1):
            if not selected_roles.intersection(alternatives):
                errors[f"days.{day_index}.roles.{requirement_index}"] = "O treino de peito não variou adequadamente os ângulos e estímulos."
        normalized_days.append({
            **{key: value for key, value in spec.items() if key in {"code", "title", "order"}},
            "focus": str(day.get("focus", "Treino equilibrado")).strip()[:200],
            "exercises": normalized_exercises,
        })
    if errors:
        raise PlanValidationError(errors)
    return {
        "title": str(data.get("title", "Plano de treino personalizado")).strip()[:100],
        "description": str(data.get("description", "Plano criado de acordo com sua rotina.")).strip()[:1000],
        "days": normalized_days,
    }


def normalize_manual_workout(data, questionnaire):
    errors = {}
    if not isinstance(data, dict) or data.get("type") != "workout_plan":
        raise PlanValidationError({"plan": "Informe uma estrutura de treino válida."})
    days = data.get("days")
    if not isinstance(days, list) or len(days) != questionnaire["days_per_week"]:
        raise PlanValidationError({"days": "A quantidade de dias deve corresponder à frequência semanal."})
    normalized_days = []
    for day_index, day in enumerate(days, start=1):
        exercises = day.get("exercises") if isinstance(day, dict) else None
        if not isinstance(exercises, list) or not 1 <= len(exercises) <= 12:
            errors[f"days.{day_index}"] = "Adicione entre 1 e 12 exercícios neste dia."
            continue
        normalized_exercises = []
        used_keys = set()
        for exercise_index, exercise in enumerate(exercises, start=1):
            item = exercise if isinstance(exercise, dict) else {}
            catalog_item = resolve_catalog_exercise(item.get("catalog_key"), item.get("name"))
            custom_key = str(item.get("catalog_key") or "")
            custom_name = str(item.get("name") or "").strip()
            is_custom = custom_key.startswith("custom:") and 2 <= len(custom_name) <= 100
            stable_key = custom_key if is_custom else catalog_item["key"] if catalog_item else None
            if not stable_key or stable_key in used_keys:
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "Exercício inválido ou repetido."
                continue
            try:
                sets = int(item.get("sets"))
                rest_seconds = int(item.get("rest_seconds", 60))
            except (TypeError, ValueError):
                sets = rest_seconds = 0
            reps = str(item.get("reps", "")).strip()
            if not 1 <= sets <= 10 or not reps or len(reps) > 30 or not 0 <= rest_seconds <= 600:
                errors[f"days.{day_index}.exercises.{exercise_index}"] = "Séries, repetições ou descanso inválidos."
                continue
            used_keys.add(stable_key)
            normalized_exercises.append({
                "catalog_key": stable_key,
                "name": custom_name if is_custom else catalog_item["name"],
                "movement_pattern": "custom" if is_custom else catalog_item["movement_pattern"],
                "primary_muscle": str(item.get("primary_muscle") or "")[:50] or None if is_custom else catalog_item["primary_muscle"],
                "equipment": str(item.get("equipment") or "")[:50] or None if is_custom else catalog_item["equipment"],
                "difficulty": str(item.get("difficulty") or "")[:20] or None if is_custom else catalog_item["difficulty"],
                "sets": sets,
                "reps": reps,
                "weight": str(item.get("weight", "")).strip()[:50] or None,
                "rest_seconds": rest_seconds,
                "effort_guidance": str(item.get("effort_guidance", "")).strip()[:100] or None,
                "notes": str(item.get("notes", "")).strip()[:500] or None,
                "order": exercise_index,
            })
        normalized_days.append({
            "code": str(day.get("code") or chr(64 + day_index))[:20],
            "title": str(day.get("title") or f"Treino {day_index}").strip()[:100],
            "focus": str(day.get("focus") or "").strip()[:200] or None,
            "order": day_index,
            "exercises": normalized_exercises,
        })
    if errors:
        raise PlanValidationError(errors)
    return {
        "title": str(data.get("title") or "Plano de treino").strip()[:100],
        "description": str(data.get("description") or "").strip()[:1000] or None,
        "days": normalized_days,
    }


def _workoutx_catalog_item(exercise):
    classification = classify_workoutx_exercise(exercise)
    return {
        "key": f"workoutx:{exercise['id']}",
        "name": exercise["name"],
        "aliases": [exercise["name"]],
        "movement_pattern": classification["movement_pattern"],
        "primary_muscle": classification["primary_muscle"],
        "secondary_muscles": list(classification["secondary_muscles"]),
        "equipment": exercise.get("equipment") or "",
        "difficulty": classification["difficulty"] or None,
        "substitution_group": classification["movement_pattern"],
        "auto_replaceable": True,
        "image_category": "workoutx",
    }


def _active_workoutx_source(exercise, source, catalog):
    if not source:
        return None
    if str(exercise.catalog_key or "").startswith("workoutx:"):
        provider_id = str(exercise.catalog_key).split(":", 1)[1]
        return next((item for item in catalog if str(item["id"]) == provider_id), None)
    names = {_normalized(exercise.name), _normalized(source["name"])}
    names.update(_normalized(alias) for alias in source.get("aliases", []))
    exact = next((item for item in catalog if _normalized(item.get("name")) in names), None)
    if exact:
        return exact
    source_equipment = str(source.get("equipment") or "").lower()
    for name in names:
        words = set(name.split())
        if len(words) < 2:
            continue
        for item in catalog:
            if words <= set(_normalized(item.get("name")).split()) and (
                not source_equipment or str(item.get("equipment") or "").lower() == source_equipment
            ):
                return item
    return None


def _workoutx_equipment_available(exercise, blocked, available, full_gym):
    equipment = str(exercise.get("equipment") or "").lower()
    if any(value == equipment or (value == "machine" and "machine" in equipment) for value in blocked):
        return False
    return full_gym or equipment in available or (equipment == "body weight" and "bodyweight" in available)


def _workoutx_replacement_options(exercise, source, unavailable_equipment, available_equipment, present_exercises, limit):
    from src.models.user import WorkoutXExercise

    catalog = [item.data for item in WorkoutXExercise.query.all()]
    source_item = _active_workoutx_source(exercise, source, catalog)
    if not source_item:
        return None
    blocked = {str(value).strip().lower() for value in unavailable_equipment or []}
    available = {str(value).strip().lower() for value in expand_equipment(available_equipment)}
    full_gym = not available or "full_gym" in available
    candidates = [
        item for item in catalog
        if _workoutx_equipment_available(item, blocked, available, full_gym)
    ]
    present_ids = set()
    for present in present_exercises or []:
        present_item = _active_workoutx_source(present, resolve_catalog_exercise(present.catalog_key, present.name), catalog)
        if present_item:
            present_ids.add(str(present_item["id"]))
    options = substitution_options(source_item, candidates, present_ids=present_ids)[:limit]
    return [
        {
            "catalog_key": f"workoutx:{candidate['id']}",
            "name": candidate["name"],
            "movement_pattern": classify_workoutx_exercise(candidate)["movement_pattern"],
            "primary_muscle": classify_workoutx_exercise(candidate)["primary_muscle"],
            "equipment": candidate.get("equipment") or "",
            "difficulty": candidate.get("difficulty") or None,
            "image_category": "workoutx",
            "sets": exercise.sets,
            "reps": exercise.reps,
            "weight": "Carga que deixe 2 repetições em reserva",
            "rest_seconds": exercise.rest_seconds,
            "effort_guidance": exercise.effort_guidance or "Termine com 2 repetições em reserva",
            "notes": "Ajuste a carga e mantenha a execução controlada.",
            "rationale": f"Mantém o padrão {classify_workoutx_exercise(candidate)['movement_pattern']} para {classify_workoutx_exercise(candidate)['primary_muscle']}.",
        }
        for candidate in options
    ]


def replacement_options(exercise, unavailable_equipment=None, available_equipment=None, limit=3, present_exercises=None):
    source = resolve_catalog_exercise(exercise.catalog_key, exercise.name)
    if not source or not source.get("auto_replaceable", False):
        return []
    workoutx_options = _workoutx_replacement_options(
        exercise,
        source,
        unavailable_equipment,
        available_equipment,
        present_exercises,
        limit,
    )
    if workoutx_options is not None:
        return workoutx_options
    blocked = set([source["equipment"]] if unavailable_equipment is None else unavailable_equipment)
    available = expand_equipment(available_equipment)
    full_gym = not available or "full_gym" in available
    difficulty_order = {"beginner": 0, "intermediate": 1, "advanced": 2}
    candidates = []
    for candidate in exercise_catalog():
        if candidate["key"] == source["key"] or candidate["key"] in {
            item.catalog_key for item in present_exercises or []
        } or not candidate.get("auto_replaceable", False):
            continue
        if candidate["substitution_group"] != source["substitution_group"]:
            continue
        if candidate["equipment"] in blocked:
            continue
        if not full_gym and candidate["equipment"] not in available and candidate["equipment"] != "bodyweight":
            continue
        difficulty_distance = abs(difficulty_order[candidate["difficulty"]] - difficulty_order[source["difficulty"]])
        overlap = len(set(candidate["secondary_muscles"]) & set(source["secondary_muscles"]))
        primary_muscle_distance = candidate["primary_muscle"] != source["primary_muscle"]
        candidates.append((primary_muscle_distance, difficulty_distance, -overlap, candidate["name"], candidate))
    candidates.sort(key=lambda item: item[:3])
    return [
        {
            "catalog_key": candidate["key"],
            "name": candidate["name"],
            "movement_pattern": candidate["movement_pattern"],
            "primary_muscle": candidate["primary_muscle"],
            "equipment": candidate["equipment"],
            "difficulty": candidate["difficulty"],
            "image_category": candidate["image_category"],
            "sets": exercise.sets,
            "reps": exercise.reps,
            "weight": "Carga que deixe 2 repetições em reserva",
            "rest_seconds": exercise.rest_seconds,
            "effort_guidance": exercise.effort_guidance or "Termine com 2 repetições em reserva",
            "notes": "Ajuste a carga e mantenha a execução controlada.",
            "rationale": f"Mantém o padrão {candidate['movement_pattern']} para {candidate['primary_muscle']}.",
        }
        for _, _, _, _, candidate in candidates[:limit]
    ]
