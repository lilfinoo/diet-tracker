import math
import unicodedata

from src.services.workout_plans import PlanValidationError


DIET_GOALS = {"fat_loss", "muscle_gain", "maintenance", "general_health"}
DIET_PATTERNS = {"omnivore", "vegetarian", "vegan", "pescatarian"}
BUDGETS = {"economical", "moderate", "flexible"}


def _text(value):
    return str(value or "").strip()


def _text_list(data, field, errors, max_items=12):
    values = data.get(field, [])
    if not isinstance(values, list) or len(values) > max_items:
        errors[field] = "Lista inválida ou muito extensa."
        return []
    result = [_text(value)[:80] for value in values if _text(value)]
    return result


def validate_diet_questionnaire(data):
    errors = {}
    goal = _text(data.get("goal"))
    pattern = _text(data.get("diet_pattern"))
    budget = _text(data.get("budget"))
    try:
        meals_per_day = int(data.get("meals_per_day"))
        prep_minutes = int(data.get("prep_minutes"))
    except (TypeError, ValueError):
        meals_per_day = prep_minutes = 0
    if goal not in DIET_GOALS:
        errors["goal"] = "Selecione um objetivo válido."
    if pattern not in DIET_PATTERNS:
        errors["diet_pattern"] = "Selecione um padrão alimentar."
    if budget not in BUDGETS:
        errors["budget"] = "Selecione uma faixa de orçamento."
    if meals_per_day not in {3, 4, 5}:
        errors["meals_per_day"] = "Escolha entre 3 e 5 refeições."
    if prep_minutes not in {15, 30, 45, 60}:
        errors["prep_minutes"] = "Selecione um tempo de preparo válido."
    allergies = _text_list(data, "allergies", errors)
    intolerances = _text_list(data, "intolerances", errors)
    disliked_foods = _text_list(data, "disliked_foods", errors)
    preferred_foods = _text_list(data, "preferred_foods", errors)
    available_ingredients = _text_list(data, "available_ingredients", errors, max_items=24)
    notes = _text(data.get("notes"))
    if len(notes) > 500:
        errors["notes"] = "Resuma as observações em até 500 caracteres."
    if errors:
        raise PlanValidationError(errors)
    return {
        "goal": goal,
        "meals_per_day": meals_per_day,
        "diet_pattern": pattern,
        "allergies": allergies,
        "intolerances": intolerances,
        "disliked_foods": disliked_foods,
        "preferred_foods": preferred_foods,
        "available_ingredients": available_ingredients,
        "budget": budget,
        "prep_minutes": prep_minutes,
        "notes": notes,
        "rotation_days": 3,
    }


def _normalized(value):
    value = unicodedata.normalize("NFKD", _text(value))
    return "".join(char for char in value if not unicodedata.combining(char)).lower()


def _macro(value, field, errors):
    try:
        result = float(value)
    except (TypeError, ValueError):
        errors[field] = "Valor nutricional inválido."
        return 0.0
    if not math.isfinite(result) or result < 0:
        errors[field] = "Valor nutricional inválido."
    return round(result, 1)


def normalize_diet_day(data, questionnaire):
    if not isinstance(data, dict) or data.get("type") != "diet_plan_day":
        raise PlanValidationError({"plan": "A IA retornou um formato alimentar inválido."})
    day_meals = data.get("meals")
    if not isinstance(day_meals, list) or len(day_meals) != questionnaire["meals_per_day"]:
        raise PlanValidationError({"meals": "Quantidade de refeições incorreta."})
    errors = {}
    meals = []
    exclusions = questionnaire["allergies"] + questionnaire["intolerances"] + questionnaire["disliked_foods"]
    normalized_exclusions = [_normalized(value) for value in exclusions]
    for meal_index, meal in enumerate(day_meals, start=1):
        if not isinstance(meal, dict):
            errors[f"meals.{meal_index}"] = "Refeição inválida."
            continue
        items = meal.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 8:
            errors[f"meals.{meal_index}.items"] = "A refeição precisa de ingredientes."
            continue
        items = [_text(item)[:160] for item in items if _text(item)]
        substitutions = meal.get("substitutions", [])
        if not isinstance(substitutions, list) or len(substitutions) > 2:
            substitutions = []
        safe_substitutions = []
        all_food_text = list(items)
        for substitution in substitutions:
            alternatives = substitution.get("alternatives", []) if isinstance(substitution, dict) else []
            if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= 2:
                continue
            safe = {
                "replace": _text(substitution.get("replace"))[:120],
                "alternatives": [_text(item)[:120] for item in alternatives if _text(item)],
            }
            all_food_text.extend(safe["alternatives"])
            safe_substitutions.append(safe)
        normalized_food = _normalized(" ".join(all_food_text))
        for exclusion in normalized_exclusions:
            if exclusion and exclusion in normalized_food:
                errors[f"meals.{meal_index}.restrictions"] = "A refeição contém um alimento evitado."
        prep_minutes = meal.get("prep_minutes", questionnaire["prep_minutes"])
        try:
            prep_minutes = int(prep_minutes)
        except (TypeError, ValueError):
            prep_minutes = questionnaire["prep_minutes"]
        if prep_minutes > questionnaire["prep_minutes"]:
            errors[f"meals.{meal_index}.prep_minutes"] = "O preparo excede o tempo escolhido."
        macro_prefix = f"meals.{meal_index}"
        meals.append({
            "meal_type": _text(meal.get("meal_type"))[:50] or f"Refeição {meal_index}",
            "description": ", ".join(items),
            "items": items,
            "prep_instructions": _text(meal.get("prep"))[:500],
            "prep_minutes": prep_minutes,
            "calories": _macro(meal.get("calories"), f"{macro_prefix}.calories", errors),
            "protein": _macro(meal.get("protein"), f"{macro_prefix}.protein", errors),
            "carbs": _macro(meal.get("carbs"), f"{macro_prefix}.carbs", errors),
            "fat": _macro(meal.get("fat"), f"{macro_prefix}.fat", errors),
            "notes": _text(meal.get("notes"))[:500] or None,
            "substitutions": safe_substitutions,
            "order": meal_index,
        })
    if errors:
        raise PlanValidationError(errors)
    return {"meals": meals}


def normalize_diet_output(data, questionnaire):
    if not isinstance(data, dict) or data.get("type") != "diet_plan":
        raise PlanValidationError({"plan": "A IA retornou um formato alimentar inválido."})
    days = data.get("days")
    if not isinstance(days, list) or len(days) != 3:
        raise PlanValidationError({"days": "A dieta deve conter exatamente três dias rotativos."})
    errors = {}
    meals = []
    exclusions = questionnaire["allergies"] + questionnaire["intolerances"] + questionnaire["disliked_foods"]
    normalized_exclusions = [_normalized(value) for value in exclusions]
    for day_index, day in enumerate(days, start=1):
        day_meals = day.get("meals") if isinstance(day, dict) else None
        if not isinstance(day_meals, list) or len(day_meals) != questionnaire["meals_per_day"]:
            errors[f"days.{day_index}"] = "Quantidade de refeições incorreta."
            continue
        for meal_index, meal in enumerate(day_meals, start=1):
            if not isinstance(meal, dict):
                errors[f"days.{day_index}.meals.{meal_index}"] = "Refeição inválida."
                continue
            items = meal.get("items")
            if not isinstance(items, list) or not 1 <= len(items) <= 8:
                errors[f"days.{day_index}.meals.{meal_index}.items"] = "A refeição precisa de ingredientes."
                continue
            items = [_text(item)[:160] for item in items if _text(item)]
            substitutions = meal.get("substitutions", [])
            if not isinstance(substitutions, list) or len(substitutions) > 2:
                errors[f"days.{day_index}.meals.{meal_index}.substitutions"] = "Substituições inválidas."
                substitutions = []
            safe_substitutions = []
            all_food_text = list(items)
            for substitution in substitutions:
                alternatives = substitution.get("alternatives", []) if isinstance(substitution, dict) else []
                if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= 2:
                    continue
                safe = {
                    "replace": _text(substitution.get("replace"))[:120],
                    "alternatives": [_text(item)[:120] for item in alternatives if _text(item)],
                }
                all_food_text.extend(safe["alternatives"])
                safe_substitutions.append(safe)
            normalized_food = _normalized(" ".join(all_food_text))
            for exclusion in normalized_exclusions:
                if exclusion and exclusion in normalized_food:
                    errors[f"days.{day_index}.meals.{meal_index}.restrictions"] = "A refeição contém um alimento evitado."
            prep_minutes = meal.get("prep_minutes", questionnaire["prep_minutes"])
            try:
                prep_minutes = int(prep_minutes)
            except (TypeError, ValueError):
                prep_minutes = questionnaire["prep_minutes"]
            if prep_minutes > questionnaire["prep_minutes"]:
                errors[f"days.{day_index}.meals.{meal_index}.prep_minutes"] = "O preparo excede o tempo escolhido."
            macro_prefix = f"days.{day_index}.meals.{meal_index}"
            meals.append({
                "day_of_week": f"Dia {day_index}",
                "meal_type": _text(meal.get("meal_type"))[:50] or f"Refeição {meal_index}",
                "description": ", ".join(items),
                "items": items,
                "prep_instructions": _text(meal.get("prep"))[:500],
                "prep_minutes": prep_minutes,
                "calories": _macro(meal.get("calories"), f"{macro_prefix}.calories", errors),
                "protein": _macro(meal.get("protein"), f"{macro_prefix}.protein", errors),
                "carbs": _macro(meal.get("carbs"), f"{macro_prefix}.carbs", errors),
                "fat": _macro(meal.get("fat"), f"{macro_prefix}.fat", errors),
                "notes": _text(meal.get("notes"))[:500] or None,
                "substitutions": safe_substitutions,
                "order": meal_index,
            })
    if errors:
        raise PlanValidationError(errors)
    return {
        "title": _text(data.get("title"))[:100] or "Plano alimentar de 3 dias",
        "description": _text(data.get("description"))[:1000] or "Três dias para alternar durante a semana.",
        "meals": meals,
    }
