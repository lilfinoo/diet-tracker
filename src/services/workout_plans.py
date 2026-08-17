import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "exercises.json"
GOALS = {"hypertrophy", "strength", "conditioning", "fat_loss", "mobility"}
EXPERIENCE_LEVELS = {"beginner", "intermediate", "advanced"}
SPLITS_BY_DAYS = {
    2: {"full_body", "upper_lower"},
    3: {"full_body", "upper_lower", "abc"},
    4: {"full_body", "upper_lower", "abc", "abcd"},
    5: {"full_body", "upper_lower", "abc", "abcd", "abcde"},
    6: {"full_body", "upper_lower", "abc", "abcd", "abcde"},
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
    "flexao_joelhos_bola": "bodyweight_leg_curl",
    "flexao_joelhos_deslizante": "bodyweight_leg_curl",
    "flexao_nordica": "nordic_leg_curl",
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
    "elevacao_lateral_elastico": "shoulder_lateral_raise",
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
    if catalog_key and catalog_key in catalog_by_key():
        return catalog_by_key()[catalog_key]
    return catalog_aliases().get(_normalized(name))


def expand_equipment(equipment):
    expanded = set(equipment or [])
    for value in list(expanded):
        expanded.update(EQUIPMENT_GROUPS.get(value, set()))
    return expanded


def recommend_split(days_per_week, experience_level):
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
            "D": {"vertical_push", "lateral_raise"} | core,
        },
        "abcde": {
            "A": {"horizontal_push"} | core,
            "B": {"horizontal_pull", "vertical_pull"} | core,
            "C": lower | core,
            "D": {"vertical_push", "lateral_raise"} | core,
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
        errors["days_per_week"] = "Escolha entre 2 e 6 dias por semana."
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
    if not errors:
        available_catalog = catalog_for_prompt(questionnaire)
        available_groups = {item["group"] for item in available_catalog}
        available_roles = {item["training_role"] for item in available_catalog if item["training_role"]}
        specs = workout_day_specs(split_type, days)
        required_groups = [
            alternatives
            for spec in specs
            for alternatives in spec.get("required_groups", [])
        ]
        required_roles = [
            alternatives
            for spec in specs
            for alternatives in required_training_roles_for_day(split_type, spec["code"])
        ]
        if (
            any(not available_groups.intersection(alternatives) for alternatives in required_groups)
            or any(not available_roles.intersection(alternatives) for alternatives in required_roles)
        ):
            errors["equipment"] = "Os equipamentos selecionados não cobrem todos os movimentos dessa divisão. Adicione mais opções ou escolha academia completa."
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


def normalize_workout_output(data, questionnaire):
    errors = {}
    if not isinstance(data, dict) or data.get("type") != "workout_plan":
        raise PlanValidationError({"plan": "A IA retornou um formato de treino inválido."})
    days = data.get("days")
    specs = workout_day_specs(questionnaire["split_type"], questionnaire["days_per_week"])
    if not isinstance(days, list) or len(days) != len(specs):
        raise PlanValidationError({"days": "A quantidade de treinos gerada está incorreta."})

    normalized_days = []
    allowed_keys = {item["key"] for item in catalog_for_prompt(questionnaire)}
    allowed_difficulty = {
        "beginner": {"beginner"},
        "intermediate": {"beginner", "intermediate"},
        "advanced": EXPERIENCE_LEVELS,
    }[questionnaire["experience_level"]]
    for day_index, (day, spec) in enumerate(zip(days, specs, strict=True), start=1):
        exercises = day.get("exercises") if isinstance(day, dict) else None
        duration = questionnaire["session_duration"]
        minimum, maximum = (3, 5) if duration <= 30 else (4, 7) if duration <= 60 else (6, 8)
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
            dedicated_chest_day = (
                questionnaire["split_type"] in {"abcd", "abcde"}
                and spec["code"].split("_")[0] == "A"
            )
            group_limit = 4 if dedicated_chest_day and group == "horizontal_push" and role else 2
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
        allowed_groups = allowed_groups_for_day(questionnaire["split_type"], spec["code"])
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
        for requirement_index, alternatives in enumerate(
            required_training_roles_for_day(questionnaire["split_type"], spec["code"]),
            start=1,
        ):
            if not selected_roles.intersection(alternatives):
                errors[f"days.{day_index}.roles.{requirement_index}"] = "O treino de peito não variou adequadamente os ângulos e estímulos."
        normalized_days.append({
            **{key: value for key, value in spec.items() if key not in {"focus_guidance", "required_groups"}},
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
            if not catalog_item or catalog_item["key"] in used_keys:
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
            used_keys.add(catalog_item["key"])
            normalized_exercises.append({
                "catalog_key": catalog_item["key"],
                "name": catalog_item["name"],
                "movement_pattern": catalog_item["movement_pattern"],
                "primary_muscle": catalog_item["primary_muscle"],
                "equipment": catalog_item["equipment"],
                "difficulty": catalog_item["difficulty"],
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


def replacement_options(exercise, unavailable_equipment=None, available_equipment=None, limit=3):
    source = resolve_catalog_exercise(exercise.catalog_key, exercise.name)
    if not source or not source.get("auto_replaceable", False):
        return []
    blocked = set([source["equipment"]] if unavailable_equipment is None else unavailable_equipment)
    available = expand_equipment(available_equipment)
    full_gym = not available or "full_gym" in available
    difficulty_order = {"beginner": 0, "intermediate": 1, "advanced": 2}
    candidates = []
    for candidate in exercise_catalog():
        if candidate["key"] == source["key"] or not candidate.get("auto_replaceable", False):
            continue
        if candidate["substitution_group"] != source["substitution_group"]:
            continue
        if candidate["primary_muscle"] != source["primary_muscle"]:
            continue
        if candidate["equipment"] in blocked:
            continue
        if not full_gym and candidate["equipment"] not in available and candidate["equipment"] != "bodyweight":
            continue
        difficulty_distance = abs(difficulty_order[candidate["difficulty"]] - difficulty_order[source["difficulty"]])
        overlap = len(set(candidate["secondary_muscles"]) & set(source["secondary_muscles"]))
        candidates.append((difficulty_distance, -overlap, candidate["name"], candidate))
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
            "weight": "Escolha uma carga que deixe 2 repetições em reserva",
            "rest_seconds": exercise.rest_seconds,
            "effort_guidance": exercise.effort_guidance or "Termine com 2 repetições em reserva",
            "notes": "Ajuste a carga e mantenha a execução controlada.",
            "rationale": f"Mantém o padrão {candidate['movement_pattern']} para {candidate['primary_muscle']}.",
        }
        for _, _, _, candidate in candidates[:limit]
    ]
