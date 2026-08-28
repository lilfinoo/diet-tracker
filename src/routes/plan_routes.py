from datetime import datetime

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.models.user import ChatMessage, DietPlan, DietPlanMeal, UserProfile, WorkoutDay, WorkoutExercise, WorkoutPlan, db
from src.routes.common import _csrf_protect_request, chat_plan_intent, json_body, login_required, page_query, premium_required
from src.services.ai import (
    AIQuotaExceededError,
    AIResponseError,
    AIServiceError,
    AIServiceUnavailableError,
    generate_diet_day,
    generate_diet_plan,
    generate_response,
    generate_workout_plan,
)
from src.services.diet_plans import (
    calculate_nutrition_targets,
    correction_feedback,
    merge_profile_restrictions,
    normalize_diet_day,
    normalize_diet_output,
    profile_snapshot,
    validate_diet_questionnaire,
)
from src.services.rate_limit import rate_limit
from src.services.workout_plans import (
    PlanValidationError,
    normalize_workout_output,
    validate_workout_questionnaire,
)
plan_bp = Blueprint("plan", __name__)


@plan_bp.before_request
def protect_plan_mutations():
    return _csrf_protect_request()


@plan_bp.route("/chat", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required(allow_trial=True)
def chat():
    user = g.user
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    data = json_body()
    message = str(data.get("message", "")).strip()

    if not message or len(message) > 2_000:
        return jsonify({"error": "Mensagem vazia"}), 400
    try:
        plan_intent = chat_plan_intent(data, message)
        action = None
        if plan_intent == "diet_plan":
            response_text = "Vamos personalizar sua dieta. Responda ao questionário rápido para eu montar três dias rotativos."
            action = {"type": "open_diet_plan_questionnaire"}
        elif plan_intent == "workout_plan":
            response_text = "Vamos montar seu treino. Informe sua frequência, experiência e equipamentos no questionário rápido."
            action = {"type": "open_workout_questionnaire"}
        else:
            response_text = generate_response(message, user, profile)
        db.session.add(ChatMessage(user_id=user.id, message=message, response=response_text))
        db.session.commit()
    except AIResponseError as error:
        current_app.logger.warning("Chat AI response was unusable: %s", error)
        return jsonify({"error": str(error)}), 422
    except AIQuotaExceededError as error:
        current_app.logger.warning("Chat AI quota exceeded: %s", error)
        return jsonify({"error": str(error)}), 429
    except AIServiceError:
        current_app.logger.exception("Chat AI request failed")
        return jsonify({"error": "A IA está indisponível no momento"}), 503
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to persist AI response")
        return jsonify({"error": "Não foi possível salvar o resultado gerado"}), 422

    return jsonify({"response": response_text, "action": action}), 200


@plan_bp.route("/chat/history", methods=["GET"])
@premium_required
def chat_history():
    messages, _, _ = page_query(ChatMessage.query.filter_by(user_id=g.user.id).order_by(ChatMessage.created_at.asc()))
    return jsonify([msg.to_dict() for msg in messages.all()]), 200


@plan_bp.route("/diet_plans/generate", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required(allow_trial=True)
def create_guided_diet_plan():
    user = g.user
    try:
        questionnaire = validate_diet_questionnaire(json_body())
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências da dieta.", "fields": error.errors}), 400
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    try:
        questionnaire = merge_profile_restrictions(questionnaire, profile)
        nutrition_targets = calculate_nutrition_targets(profile, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise seu perfil e as metas nutricionais.", "fields": error.errors}), 400

    correction = None
    max_attempts = current_app.config["GEMINI_DIET_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        try:
            generated = generate_diet_plan(questionnaire, profile, nutrition_targets, correction)
            plan_data = normalize_diet_output(generated, questionnaire, nutrition_targets)
            break
        except PlanValidationError as error:
            current_app.logger.warning(
                "Invalid generated diet plan (attempt %s/%s): %s",
                attempt,
                max_attempts,
                list(error.errors)[:8],
            )
            if attempt == max_attempts:
                return jsonify({"error": "A dieta não atingiu as metas nutricionais. Tente novamente."}), 502
            correction = correction_feedback(error, generated, nutrition_targets)
        except AIResponseError:
            current_app.logger.warning("Diet plan AI returned invalid output (attempt %s/%s)", attempt, max_attempts)
            if attempt == max_attempts:
                return jsonify({"error": "A dieta gerada ficou incompleta. Tente novamente."}), 502
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceUnavailableError:
            current_app.logger.warning("Diet plan generation unavailable after retries")
            return jsonify({"error": "A IA está com alta demanda. Tente gerar sua dieta novamente em alguns instantes."}), 503
        except AIServiceError:
            current_app.logger.exception("Diet plan generation failed")
            return jsonify({"error": "A IA não conseguiu gerar a dieta agora."}), 503

    try:
        plan = DietPlan(
            user_id=user.id,
            author_user_id=user.id,
            published_by_user_id=user.id,
            status="published",
            source="ai",
            published_at=datetime.utcnow(),
            title=plan_data["title"],
            description=plan_data["description"],
            schema_version=3,
            plan_mode="rotation_3_day",
            goal_code=questionnaire["goal"],
            meals_per_day=questionnaire["meals_per_day"],
            generation_context={
                "questionnaire": questionnaire,
                "profile_snapshot": profile_snapshot(profile),
                "nutrition_targets": nutrition_targets,
            },
        )
        db.session.add(plan)
        db.session.flush()
        allowed = {"day_of_week", "meal_type", "description", "calories", "protein", "carbs", "fat", "notes", "items", "prep_instructions", "prep_minutes", "substitutions", "order"}
        for meal in plan_data["meals"]:
            db.session.add(DietPlanMeal(diet_plan_id=plan.id, **{key: meal[key] for key in allowed if key in meal}))
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save guided diet plan")
        return jsonify({"error": "Não foi possível salvar a dieta gerada."}), 422
    response = jsonify({"message": "Plano alimentar criado.", "plan_id": plan.id, "plan": plan.to_dict_full()})
    response.status_code = 201
    response.headers["Location"] = f"/api/diet_plans/{plan.id}"
    return response


@plan_bp.route("/workout_plans/generate", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required(allow_trial=True)
def create_guided_workout_plan():
    user = g.user
    try:
        questionnaire = validate_workout_questionnaire(json_body())
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências do treino.", "fields": error.errors}), 400
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    max_attempts = current_app.config["GEMINI_WORKOUT_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        try:
            generated = generate_workout_plan(questionnaire, profile)
            plan_data = normalize_workout_output(generated, questionnaire)
            break
        except PlanValidationError as error:
            current_app.logger.warning(
                "Invalid generated workout plan (attempt %s/%s): %s",
                attempt,
                max_attempts,
                list(error.errors)[:5],
            )
            if attempt < max_attempts:
                continue
            return jsonify({"error": "O treino gerado ficou incompleto. Tente novamente."}), 502
        except AIResponseError:
            current_app.logger.warning("Workout plan AI returned invalid/truncated output (attempt %s/%s)", attempt, max_attempts)
            if attempt < max_attempts:
                continue
            return jsonify({"error": "O treino gerado ficou incompleto. Tente novamente."}), 502
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceError:
            current_app.logger.exception("Workout plan generation failed")
            return jsonify({"error": "A IA não conseguiu gerar o treino agora."}), 503

    try:
        plan = WorkoutPlan(
            user_id=user.id,
            author_user_id=user.id,
            published_by_user_id=user.id,
            status="published",
            source="ai",
            published_at=datetime.utcnow(),
            title=plan_data["title"],
            description=plan_data["description"],
            split_type=questionnaire["split_type"],
            days_per_week=questionnaire["days_per_week"],
            goal=questionnaire["goal"],
            experience_level=questionnaire["experience_level"],
            session_duration=questionnaire["session_duration"],
            questionnaire_data=questionnaire,
        )
        db.session.add(plan)
        db.session.flush()
        exercise_fields = {"catalog_key", "name", "movement_pattern", "primary_muscle", "equipment", "difficulty", "sets", "reps", "weight", "rest_seconds", "effort_guidance", "notes", "order"}
        for day_data in plan_data["days"]:
            day = WorkoutDay(workout_plan_id=plan.id, code=day_data["code"], title=day_data["title"], focus=day_data["focus"], order=day_data["order"])
            db.session.add(day)
            db.session.flush()
            for exercise in day_data["exercises"]:
                db.session.add(WorkoutExercise(workout_plan_id=plan.id, workout_day_id=day.id, **{key: exercise[key] for key in exercise_fields if key in exercise}))
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save guided workout plan")
        return jsonify({"error": "Não foi possível salvar o treino gerado."}), 422
    response = jsonify({"message": "Plano de treino criado.", "plan_id": plan.id, "plan": plan.to_dict_full()})
    response.status_code = 201
    response.headers["Location"] = f"/api/workout_plans/{plan.id}"
    return response


@plan_bp.route("/diet_plans", methods=["GET"])
@login_required
def get_diet_plans():
    plans, _, _ = page_query(
        DietPlan.query.filter_by(user_id=g.user.id, status="published")
        .options(selectinload(DietPlan.meals))
        .order_by(DietPlan.created_at.desc()),
    )
    return jsonify([plan.to_dict() for plan in plans.all()]), 200


@plan_bp.route("/diet_plans/<int:plan_id>", methods=["GET"])
@login_required
def get_diet_plan_details(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").options(selectinload(DietPlan.meals)).first_or_404()
    return jsonify(plan.to_dict_full()), 200


@plan_bp.route("/diet_plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_diet_plan(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plano de dieta excluído com sucesso"}), 200


@plan_bp.route("/diet_plans/<int:plan_id>/meals/<int:meal_id>", methods=["PATCH"])
@login_required
def update_diet_plan_meal(plan_id, meal_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    meal = DietPlanMeal.query.filter_by(id=meal_id, diet_plan_id=plan.id).first_or_404()
    data = json_body()
    description = str(data.get("description", "")).strip() or None
    if description is not None and not description:
        return jsonify({"error": "Descrição da refeição é obrigatória"}), 400
    if description:
        meal.description = description
    if data.get("items") is not None:
        items = data.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 8:
            return jsonify({"error": "Ingredientes inválidos"}), 400
        cleaned = [str(item).strip()[:160] for item in items if str(item).strip()]
        if not cleaned:
            return jsonify({"error": "A refeição precisa de ingredientes"}), 400
        meal.items = cleaned
        meal.description = ", ".join(cleaned)
    for field in ("meal_type", "notes"):
        if data.get(field) is not None:
            setattr(meal, field, data[field])
    for field in ("calories", "protein", "carbs", "fat"):
        if data.get(field) is not None:
            setattr(meal, field, data[field])
    db.session.commit()
    return jsonify({"message": "Refeição do plano atualizada", "meal": meal.to_dict()}), 200


@plan_bp.route("/diet_plans/<int:plan_id>/suggest", methods=["POST"])
@rate_limit("ai", 8, 60)
@premium_required(allow_trial=True)
def suggest_diet_day(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    data = json_body()
    try:
        day_index = int(data.get("day"))
    except (TypeError, ValueError):
        return jsonify({"error": "Dia inválido."}), 400
    if day_index not in {1, 2, 3}:
        return jsonify({"error": "Escolha um dia entre 1 e 3."}), 400
    feedback = str(data.get("feedback", "")).strip()[:500]
    generation_context = plan.generation_context or {}
    questionnaire = generation_context.get("questionnaire", generation_context)
    nutrition_targets = generation_context.get("nutrition_targets")
    if not questionnaire or not nutrition_targets:
        return jsonify({"error": "Este plano não possui contexto para sugestões."}), 422
    existing_meals = [
        {"meal_type": meal.meal_type, "items": meal.items or [], "description": meal.description}
        for meal in plan.meals
        if meal.day_of_week == f"Dia {day_index}"
    ]
    if not existing_meals:
        return jsonify({"error": "Nenhuma refeição encontrada para este dia."}), 404
    if not feedback:
        return jsonify({"error": "Descreva a mudança desejada."}), 400

    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    correction = None
    max_attempts = current_app.config["GEMINI_DIET_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        try:
            generated = generate_diet_day(questionnaire, profile, existing_meals, feedback, nutrition_targets, correction)
            day_data = normalize_diet_day(generated, questionnaire, nutrition_targets)
            break
        except PlanValidationError as error:
            current_app.logger.warning("Invalid generated diet day (attempt %s/%s): %s", attempt, max_attempts, list(error.errors)[:8])
            if attempt == max_attempts:
                return jsonify({"error": "A sugestão não atingiu as metas nutricionais."}), 502
            correction = correction_feedback(error, generated, nutrition_targets)
        except AIResponseError:
            if attempt == max_attempts:
                return jsonify({"error": "A sugestão ficou incompleta. Tente novamente."}), 502
        except AIQuotaExceededError as error:
            return jsonify({"error": str(error)}), 429
        except AIServiceError:
            current_app.logger.exception("Diet day generation failed")
            return jsonify({"error": "A IA não conseguiu sugerir mudanças agora."}), 503
    return jsonify({"day": day_index, "meals": day_data["meals"]}), 200


@plan_bp.route("/diet_plans/<int:plan_id>/days/<int:day_index>", methods=["PUT"])
@login_required
def replace_diet_day(plan_id, day_index):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    if day_index not in {1, 2, 3}:
        return jsonify({"error": "Escolha um dia entre 1 e 3."}), 400
    data = json_body()
    meals = data.get("meals")
    generation_context = plan.generation_context or {}
    questionnaire = generation_context.get("questionnaire")
    nutrition_targets = generation_context.get("nutrition_targets")
    if not questionnaire or not nutrition_targets:
        return jsonify({"error": "Este plano antigo não pode ser recalculado com segurança."}), 422
    raw_day = {
        "type": "diet_plan_day",
        "meals": [
            {
                "meal_type": meal.get("meal_type"),
                "items": meal.get("items"),
                "prep": meal.get("prep_instructions"),
                "prep_minutes": meal.get("prep_minutes"),
                "calories": meal.get("calories"),
                "protein": meal.get("protein"),
                "carbs": meal.get("carbs"),
                "fat": meal.get("fat"),
                "notes": meal.get("notes"),
                "substitutions": meal.get("substitutions"),
            }
            for meal in meals
            if isinstance(meal, dict)
        ] if isinstance(meals, list) else None,
    }
    try:
        meals = normalize_diet_day(raw_day, questionnaire, nutrition_targets)["meals"]
    except PlanValidationError as error:
        return jsonify({"error": "O cardápio informado não é nutricionalmente válido.", "fields": error.errors}), 400
    allowed = {"meal_type", "description", "calories", "protein", "carbs", "fat", "notes", "items", "prep_instructions", "prep_minutes", "substitutions", "order"}
    old_meals = [meal for meal in plan.meals if meal.day_of_week == f"Dia {day_index}"]
    for meal in old_meals:
        db.session.delete(meal)
    for order, meal in enumerate(meals, start=1):
        meal_data = dict(meal)
        meal_data["order"] = order
        db.session.add(DietPlanMeal(diet_plan_id=plan.id, day_of_week=f"Dia {day_index}", **{key: meal_data[key] for key in allowed if key in meal_data}))
    db.session.commit()
    return jsonify({"message": "Cardápio do dia atualizado.", "plan": plan.to_dict_full()}), 200
