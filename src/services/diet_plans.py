import math
import re
import unicodedata

from src.services.workout_plans import PlanValidationError


DIET_GOALS = {"fat_loss", "muscle_gain", "maintenance", "general_health"}
DIET_PATTERNS = {"omnivore", "vegetarian", "vegan", "pescatarian"}
BUDGETS = {"economical", "moderate", "flexible"}
CHANGE_PACES = {"conservative", "moderate"}
ACTIVITY_FACTORS = {
    "sedentario": 1.20,
    "leve": 1.30,
    "moderado": 1.40,
    "intenso": 1.50,
}
TRAINING_ADJUSTMENTS = {0: 0.0, 1: 0.05, 2: 0.05, 3: 0.10, 4: 0.10, 5: 0.15, 6: 0.15, 7: 0.20}
GOAL_ADJUSTMENTS = {
    "fat_loss": {"conservative": -0.10, "moderate": -0.15},
    "muscle_gain": {"conservative": 0.05, "moderate": 0.08},
    "maintenance": {"conservative": 0.0, "moderate": 0.0},
    "general_health": {"conservative": 0.0, "moderate": 0.0},
}
PROTEIN_PER_KG = {"fat_loss": 1.8, "muscle_gain": 1.8, "maintenance": 1.6, "general_health": 1.6}
NUTRITION_TOLERANCES = {"calories": 0.10, "protein": 0.15, "carbs": 0.20, "fat": 0.20}
MACRO_ENERGY_TOLERANCE = 0.20


def _text(value):
    return str(value or "").strip()


def _normalized(value):
    value = unicodedata.normalize("NFKD", _text(value))
    return "".join(char for char in value if not unicodedata.combining(char)).lower()


def _text_list(data, field, errors, max_items=12):
    values = data.get(field, [])
    if not isinstance(values, list) or len(values) > max_items:
        errors[field] = "Lista inválida ou muito extensa."
        return []
    return [_text(value)[:80] for value in values if _text(value)]


def _custom_targets(data, errors):
    values = data.get("custom_targets")
    if values is None:
        values = {}
    if not isinstance(values, dict):
        errors["custom_targets"] = "Metas nutricionais inválidas."
        return {key: None for key in ("calories", "protein", "carbs", "fat")}
    result = {}
    limits = {
        "calories": (800, 7000),
        "protein": (20, 500),
        "carbs": (20, 1200),
        "fat": (15, 300),
    }
    for key, (minimum, maximum) in limits.items():
        value = values.get(key)
        if value in (None, ""):
            result[key] = None
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            errors[f"target_{key}"] = "Informe um número válido."
            result[key] = None
            continue
        if not math.isfinite(value) or not minimum <= value <= maximum:
            errors[f"target_{key}"] = f"Informe um valor entre {minimum} e {maximum}."
        result[key] = round(value)
    return result


def validate_diet_questionnaire(data):
    errors = {}
    goal = _text(data.get("goal"))
    pattern = _text(data.get("diet_pattern"))
    budget = _text(data.get("budget"))
    change_pace = _text(data.get("change_pace"))
    try:
        meals_per_day = int(data.get("meals_per_day"))
        prep_minutes = int(data.get("prep_minutes"))
        training_days = int(data.get("training_days_per_week"))
    except (TypeError, ValueError):
        meals_per_day = prep_minutes = training_days = -1
    if goal not in DIET_GOALS:
        errors["goal"] = "Selecione um objetivo válido."
    if pattern not in DIET_PATTERNS:
        errors["diet_pattern"] = "Selecione um padrão alimentar."
    if budget not in BUDGETS:
        errors["budget"] = "Selecione uma faixa de orçamento."
    if change_pace not in CHANGE_PACES:
        errors["change_pace"] = "Selecione um ritmo válido."
    if training_days not in range(8):
        errors["training_days_per_week"] = "Escolha entre 0 e 7 dias de treino."
    if meals_per_day not in {3, 4, 5}:
        errors["meals_per_day"] = "Escolha entre 3 e 5 refeições."
    if prep_minutes not in {15, 30, 45, 60}:
        errors["prep_minutes"] = "Selecione um tempo de preparo válido."
    allergies = _text_list(data, "allergies", errors)
    intolerances = _text_list(data, "intolerances", errors)
    disliked_foods = _text_list(data, "disliked_foods", errors)
    preferred_foods = _text_list(data, "preferred_foods", errors)
    available_ingredients = _text_list(data, "available_ingredients", errors, max_items=24)
    custom_targets = _custom_targets(data, errors)
    notes = _text(data.get("notes"))
    if len(notes) > 500:
        errors["notes"] = "Resuma as observações em até 500 caracteres."
    if errors:
        raise PlanValidationError(errors)
    return {
        "goal": goal,
        "meals_per_day": meals_per_day,
        "diet_pattern": pattern,
        "training_days_per_week": training_days,
        "change_pace": change_pace,
        "allergies": allergies,
        "intolerances": intolerances,
        "disliked_foods": disliked_foods,
        "preferred_foods": preferred_foods,
        "available_ingredients": available_ingredients,
        "custom_targets": custom_targets,
        "budget": budget,
        "prep_minutes": prep_minutes,
        "notes": notes,
        "rotation_days": 3,
    }


def _profile_value(profile, name):
    return getattr(profile, name, None) if profile is not None else None


def _round_calories(value):
    return math.floor(value + 0.5 + 1e-9)


def calculate_nutrition_targets(profile, questionnaire):
    errors = {}
    age = _profile_value(profile, "age")
    weight = _profile_value(profile, "weight")
    height = _profile_value(profile, "height")
    gender = _normalized(_profile_value(profile, "gender"))
    activity = _normalized(_profile_value(profile, "activity_level"))
    gender = {
        "masculino": "male", "homem": "male", "male": "male",
        "feminino": "female", "mulher": "female", "female": "female",
    }.get(gender)
    if age is None or not 18 <= age <= 120:
        errors["profile.age"] = "Informe uma idade adulta válida no perfil."
    if weight is None or not 30 <= weight <= 300:
        errors["profile.weight"] = "Informe um peso válido no perfil."
    if height is None or not 120 <= height <= 250:
        errors["profile.height"] = "Informe uma altura válida no perfil."
    if not gender:
        errors["profile.gender"] = "Informe o sexo usado no cálculo nutricional."
    if activity not in ACTIVITY_FACTORS:
        errors["profile.activity_level"] = "Informe o nível de atividade cotidiana no perfil."
    if errors:
        raise PlanValidationError(errors)

    sex_constant = 5 if gender == "male" else -161
    bmr = 10 * weight + 6.25 * height - 5 * age + sex_constant
    activity_factor = min(
        ACTIVITY_FACTORS[activity] + TRAINING_ADJUSTMENTS[questionnaire["training_days_per_week"]],
        1.70,
    )
    maintenance = bmr * activity_factor
    adjustment = GOAL_ADJUSTMENTS[questionnaire["goal"]][questionnaire["change_pace"]]
    automatic_calories = max(bmr, maintenance * (1 + adjustment))
    custom = questionnaire.get("custom_targets") or {}
    target_calories = custom.get("calories") or automatic_calories
    protein = custom.get("protein") or round(weight * PROTEIN_PER_KG[questionnaire["goal"]])
    base_fat = weight * 0.8
    default_fat = round(min(max(base_fat, target_calories * 0.20 / 9), target_calories * 0.30 / 9))
    carbs = custom.get("carbs")
    fat = custom.get("fat")
    if custom.get("calories") is None and carbs is not None and fat is not None:
        target_calories = protein * 4 + carbs * 4 + fat * 9
    elif carbs is None and fat is None:
        fat = default_fat
        carbs = round((target_calories - protein * 4 - fat * 9) / 4)
    elif carbs is None:
        carbs = round((target_calories - protein * 4 - fat * 9) / 4)
    elif fat is None:
        fat = round((target_calories - protein * 4 - carbs * 4) / 9)
    rounded_calories = _round_calories(target_calories)
    macro_calories = protein * 4 + carbs * 4 + fat * 9

    if carbs < 20 or fat < 15 or abs(macro_calories - rounded_calories) / rounded_calories > 0.10:
        raise PlanValidationError({"custom_targets": "As metas informadas não são compatíveis entre si."})
    if custom.get("calories") and rounded_calories < _round_calories(bmr):
        raise PlanValidationError({"target_calories": "A meta calórica não pode ficar abaixo da TMB estimada."})
    if questionnaire["goal"] == "muscle_gain" and rounded_calories <= _round_calories(maintenance):
        raise PlanValidationError({"nutrition_targets": "A meta de ganho precisa superar a manutenção."})
    if questionnaire["goal"] == "fat_loss" and rounded_calories >= _round_calories(maintenance):
        raise PlanValidationError({"nutrition_targets": "A meta de perda precisa ficar abaixo da manutenção."})
    return {
        "bmr": _round_calories(bmr),
        "activityFactor": round(activity_factor, 2),
        "maintenanceCalories": _round_calories(maintenance),
        "targetCalories": rounded_calories,
        "targetProtein": protein,
        "targetCarbs": carbs,
        "targetFat": fat,
    }


def profile_snapshot(profile):
    return {
        "age": _profile_value(profile, "age"),
        "gender": _profile_value(profile, "gender"),
        "activity_level": _profile_value(profile, "activity_level"),
        "dietary_restrictions": _profile_value(profile, "dietary_restrictions"),
        "weight": _profile_value(profile, "weight"),
        "height": _profile_value(profile, "height"),
    }


def merge_profile_restrictions(questionnaire, profile):
    questionnaire = dict(questionnaire)
    restriction = _text(_profile_value(profile, "dietary_restrictions"))
    normalized = _normalized(restriction)
    if normalized.startswith("nao gosto de "):
        preferences = normalized.removeprefix("nao gosto de ")
        questionnaire["profile_restrictions"] = []
        questionnaire["profile_avoidances"] = [
            part.strip()[:80]
            for part in re.split(r"[,;\n]|\s+(?:e|ou)\s+", preferences, flags=re.IGNORECASE)
            if part.strip()
        ][:12]
    else:
        questionnaire["profile_restrictions"] = [
            part.strip()[:80]
            for part in re.split(r"[,;\n]|\s+e\s+", restriction, flags=re.IGNORECASE)
            if part.strip()
        ][:12]
        questionnaire["profile_avoidances"] = []
    return questionnaire


def _macro(value, field, errors):
    try:
        result = float(value)
    except (TypeError, ValueError):
        errors[field] = "Valor nutricional estimado inválido."
        return 0.0
    if not math.isfinite(result) or result < 0:
        errors[field] = "Valor nutricional estimado inválido."
        return 0.0
    return round(result, 1)


def _restriction_terms(questionnaire):
    values = (
        questionnaire.get("allergies", [])
        + questionnaire.get("intolerances", [])
        + questionnaire.get("profile_restrictions", [])
    )
    aliases = {
        "gluten": ("trigo", "pao", "macarrao", "biscoito", "bolo", "centeio", "cevada"),
        "amendoim": ("amendoim", "pasta de amendoim"),
    }
    terms = set()
    for value in values:
        normalized = _normalized(value)
        if normalized:
            for prefix in ("nao consumir ", "nao comer ", "evitar ", "sem ", "alergia a ", "intolerancia a "):
                if normalized.startswith(prefix):
                    normalized = normalized.removeprefix(prefix).strip()
                    break
            terms.add(normalized)
            terms.update(aliases.get(normalized, ()))
    return terms


def diet_restriction_policy(questionnaire):
    return {
        "prohibited": sorted(_restriction_terms(questionnaire)),
        "avoid_when_possible": sorted({
            _normalized(value)
            for value in questionnaire.get("disliked_foods", []) + questionnaire.get("profile_avoidances", [])
            if _normalized(value)
        }),
        "lactose_safe_alternatives_allowed": "lactose" in _restriction_terms(questionnaire),
    }


def _lactose_violation(food_text):
    text = _normalized(food_text)
    safe_markers = (
        "sem lactose", "zero lactose", "lacfree", "vegetal", "vegano",
        "leite de coco", "leite de aveia", "leite de amendoa", "leite de soja",
    )
    if any(marker in text for marker in safe_markers):
        return False
    return any(term in text for term in ("leite", "queijo", "iogurte", "requeijao", "creme de leite"))


def _food_restriction_violation(food_values, restrictions):
    for value in food_values:
        normalized = _normalized(value)
        if "lactose" in restrictions and _lactose_violation(normalized):
            return value, "lactose"
        for restriction in restrictions - {"lactose"}:
            if restriction in normalized:
                return value, restriction
    return None


def _pattern_violation(pattern, food_text):
    text = _normalized(food_text)
    meat = ("carne", "frango", "galinha", "peru", "porco", "suino", "bovino", "linguica", "presunto", "mortadela")
    fish = ("peixe", "atum", "sardinha", "salmao", "camarao", "bacalhau", "tilapia")
    animal = meat + fish + ("leite", "queijo", "iogurte", "ovo", "manteiga", "requeijao")
    if pattern == "vegan":
        return any(term in text for term in animal)
    if pattern == "vegetarian":
        return any(term in text for term in meat + fish)
    if pattern == "pescatarian":
        return any(term in text for term in meat)
    return False


def _normalize_substitutions(raw_substitutions, field, errors):
    if raw_substitutions is None:
        return [], []
    if not isinstance(raw_substitutions, list) or len(raw_substitutions) > 2:
        errors[field] = "Substituições inválidas."
        return [], []
    result = []
    food_text = []
    for index, substitution in enumerate(raw_substitutions, start=1):
        alternatives = substitution.get("alternatives") if isinstance(substitution, dict) else None
        if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= 2:
            errors[f"{field}.{index}"] = "Substituição inválida."
            continue
        alternatives = [_text(item)[:160] for item in alternatives if _text(item)]
        replacement = _text(substitution.get("replace"))[:160]
        if not replacement or not alternatives:
            errors[f"{field}.{index}"] = "Substituição inválida."
            continue
        result.append({"replace": replacement, "alternatives": alternatives})
        food_text.extend(alternatives)
    return result, food_text


def _validate_day_totals(totals, targets, field, errors):
    target_names = {
        "calories": "targetCalories", "protein": "targetProtein",
        "carbs": "targetCarbs", "fat": "targetFat",
    }
    for nutrient, tolerance in NUTRITION_TOLERANCES.items():
        target = targets[target_names[nutrient]]
        if abs(totals[nutrient] - target) / target > tolerance:
            difference = target - totals[nutrient]
            errors[f"{field}.{nutrient}"] = f"Ajuste {difference:+.1f} de {nutrient} para atingir a meta."
    macro_energy = totals["protein"] * 4 + totals["carbs"] * 4 + totals["fat"] * 9
    if totals["calories"] and abs(macro_energy - totals["calories"]) / totals["calories"] > MACRO_ENERGY_TOLERANCE:
        errors[f"{field}.macro_energy"] = "As estimativas de macros são incompatíveis com as calorias informadas."
    if totals["calories"] < targets["bmr"] * 0.90:
        errors[f"{field}.bmr"] = "O dia ficou perigosamente abaixo da TMB estimada."


def _normalize_meals(raw_meals, questionnaire, targets, prefix, day_label=None):
    errors = {}
    meals = []
    day_totals = {key: 0.0 for key in NUTRITION_TOLERANCES}
    restrictions = _restriction_terms(questionnaire)
    if not isinstance(raw_meals, list) or len(raw_meals) != questionnaire["meals_per_day"]:
        raise PlanValidationError({prefix: "Quantidade de refeições incorreta."})
    for meal_index, meal in enumerate(raw_meals, start=1):
        field = f"{prefix}.meals.{meal_index}"
        if not isinstance(meal, dict):
            errors[field] = "Refeição inválida."
            continue
        raw_items = meal.get("items")
        if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 8:
            errors[f"{field}.items"] = "A refeição precisa ter entre 1 e 8 alimentos."
            continue
        items = [_text(item)[:160] for item in raw_items if _text(item)]
        if not items:
            errors[f"{field}.items"] = "A refeição precisa de alimentos."
            continue
        substitutions, alternative_text = _normalize_substitutions(
            meal.get("substitutions"), f"{field}.substitutions", errors
        )
        food_values = items + alternative_text
        combined_food = _normalized(" ".join(food_values))
        violation = _food_restriction_violation(food_values, restrictions)
        if violation:
            food, restriction = violation
            errors[f"{field}.restrictions"] = f"'{food}' viola a restrição '{restriction}'."
        elif _pattern_violation(questionnaire["diet_pattern"], combined_food):
            errors[f"{field}.restrictions"] = f"A refeição não segue o padrão {questionnaire['diet_pattern']}."
        if any(term in combined_food for term in ("aguardente", "cerveja", "vinho", "licor")):
            errors[f"{field}.restrictions"] = "Bebidas alcoólicas não são usadas no plano."
        prep_minutes = meal.get("prep_minutes", questionnaire["prep_minutes"])
        try:
            prep_minutes = int(prep_minutes)
        except (TypeError, ValueError):
            prep_minutes = questionnaire["prep_minutes"]
        if not 0 <= prep_minutes <= questionnaire["prep_minutes"]:
            errors[f"{field}.prep_minutes"] = "O preparo excede o tempo escolhido."
        totals = {
            nutrient: _macro(meal.get(nutrient), f"{field}.{nutrient}", errors)
            for nutrient in NUTRITION_TOLERANCES
        }
        for nutrient in day_totals:
            day_totals[nutrient] += totals[nutrient]
        if totals["calories"] < targets["targetCalories"] * 0.03:
            errors[f"{field}.nutrition"] = "A refeição ficou praticamente vazia."
        meal_data = {
            "meal_type": _text(meal.get("meal_type"))[:50] or f"Refeição {meal_index}",
            "description": ", ".join(items),
            "items": items,
            "prep_instructions": _text(meal.get("prep"))[:500],
            "prep_minutes": prep_minutes,
            "calories": totals["calories"],
            "protein": totals["protein"],
            "carbs": totals["carbs"],
            "fat": totals["fat"],
            "notes": _text(meal.get("notes"))[:500] or None,
            "substitutions": substitutions,
            "order": meal_index,
        }
        if day_label:
            meal_data["day_of_week"] = day_label
        meals.append(meal_data)
    _validate_day_totals(day_totals, targets, f"{prefix}.nutrition", errors)
    if errors:
        raise PlanValidationError(errors)
    return meals


def normalize_diet_day(data, questionnaire, targets):
    if not isinstance(data, dict) or data.get("type") != "diet_plan_day":
        raise PlanValidationError({"plan": "A IA retornou um formato alimentar inválido."})
    return {"meals": _normalize_meals(data.get("meals"), questionnaire, targets, "day")}


def normalize_diet_output(data, questionnaire, targets):
    if not isinstance(data, dict) or data.get("type") != "diet_plan":
        raise PlanValidationError({"plan": "A IA retornou um formato alimentar inválido."})
    days = data.get("days")
    if not isinstance(days, list) or len(days) != 3:
        raise PlanValidationError({"days": "A dieta deve conter exatamente três dias rotativos."})
    meals = []
    errors = {}
    for day_index, day in enumerate(days, start=1):
        try:
            day_meals = day.get("meals") if isinstance(day, dict) else None
            meals.extend(_normalize_meals(day_meals, questionnaire, targets, f"days.{day_index}", f"Dia {day_index}"))
        except PlanValidationError as error:
            errors.update(error.errors)
    if errors:
        raise PlanValidationError(errors)
    return {
        "title": _text(data.get("title"))[:100] or "Plano alimentar de 3 dias",
        "description": _text(data.get("description"))[:1000] or "Três dias para alternar durante a semana.",
        "meals": meals,
    }


def normalize_manual_diet(data, questionnaire):
    errors = {}
    if not isinstance(data, dict) or data.get("type") != "diet_plan":
        raise PlanValidationError({"plan": "Informe uma estrutura alimentar válida."})
    days = data.get("days")
    if not isinstance(days, list) or len(days) != 3:
        raise PlanValidationError({"days": "O plano deve conter três dias rotativos."})
    meals = []
    for day_index, day in enumerate(days, start=1):
        raw_meals = day.get("meals") if isinstance(day, dict) else None
        if not isinstance(raw_meals, list) or len(raw_meals) != questionnaire["meals_per_day"]:
            errors[f"days.{day_index}"] = "A quantidade de refeições está incorreta."
            continue
        for meal_index, meal in enumerate(raw_meals, start=1):
            field = f"days.{day_index}.meals.{meal_index}"
            if not isinstance(meal, dict):
                errors[field] = "Refeição inválida."
                continue
            raw_items = meal.get("items")
            items = [_text(item)[:160] for item in raw_items if _text(item)] if isinstance(raw_items, list) else []
            if not items or len(items) > 8:
                errors[f"{field}.items"] = "Informe entre 1 e 8 alimentos."
                continue
            macros = {
                nutrient: _macro(meal.get(nutrient), f"{field}.{nutrient}", errors)
                for nutrient in NUTRITION_TOLERANCES
            }
            try:
                prep_minutes = int(meal.get("prep_minutes") or 0)
            except (TypeError, ValueError):
                prep_minutes = 0
            meals.append({
                "day_of_week": f"Dia {day_index}",
                "meal_type": _text(meal.get("meal_type"))[:50] or f"Refeição {meal_index}",
                "description": ", ".join(items),
                "items": items,
                "prep_instructions": _text(meal.get("prep"))[:500],
                "prep_minutes": min(max(prep_minutes, 0), 240),
                **macros,
                "notes": _text(meal.get("notes"))[:500] or None,
                "substitutions": [],
                "order": meal_index,
            })
    if errors:
        raise PlanValidationError(errors)
    return {
        "title": _text(data.get("title"))[:100] or "Plano alimentar",
        "description": _text(data.get("description"))[:1000] or None,
        "meals": meals,
    }


def correction_feedback(error, candidate=None, targets=None):
    feedback = {
        "instruction": "Ajuste porções e refeições para aproximar os totais das metas, preservando preferências e restrições.",
        "validation_errors": dict(list(error.errors.items())[:20]),
    }
    if candidate:
        feedback["previous_plan"] = candidate
    if targets:
        target_names = {
            "calories": "targetCalories",
            "protein": "targetProtein",
            "carbs": "targetCarbs",
            "fat": "targetFat",
        }
        feedback["allowed_daily_ranges"] = {
            nutrient: {
                "min": round(targets[target_name] * (1 - NUTRITION_TOLERANCES[nutrient]), 1),
                "max": round(targets[target_name] * (1 + NUTRITION_TOLERANCES[nutrient]), 1),
            }
            for nutrient, target_name in target_names.items()
        }
    return feedback
