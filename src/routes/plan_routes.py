from datetime import datetime

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.models.user import ChatMessage, DietAdherenceDay, DietMealCheckIn, DietMealDailyState, DietPlan, DietPlanMeal, ProfessionalReviewRequest, UserProfile, WorkoutDay, WorkoutExercise, WorkoutPlan, db
from src.routes.common import ai_consent_required, chat_plan_intent, coerce_numbers, json_body, login_required, page_query, premium_required
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
from src.services.analytics import record_event
from src.services.ai_queue import enqueue_ai_request
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
    build_workout_contract,
    invalid_workout_day_numbers,
    merge_workout_day_repairs,
    normalize_workout_output,
    recommend_workout_split,
    validate_workout_exercise_selection,
    validate_workout_questionnaire,
)
plan_bp = Blueprint("plan", __name__)


@plan_bp.route("/chat", methods=["POST"])
@rate_limit("ai", 8, 60)
@ai_consent_required
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
            queued = enqueue_ai_request("chat", data)
            if queued is not None:
                return queued
            response_text = generate_response(message, user, profile)
        db.session.add(ChatMessage(
            user_id=user.id,
            message=message,
            response=response_text,
            ai_task_id=getattr(g, "ai_task_id", None),
        ))
        record_event("ai_chat_completed", user_id=user.id)
        db.session.commit()
    except AIResponseError as error:
        current_app.logger.warning("Chat AI response was unusable")
        return jsonify({"error": str(error)}), 422
    except AIQuotaExceededError as error:
        current_app.logger.warning("Chat AI quota exceeded")
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
@ai_consent_required
@premium_required(allow_trial=True)
def create_guided_diet_plan():
    user = g.user
    data = json_body()
    try:
        questionnaire = validate_diet_questionnaire(data)
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências da dieta.", "fields": error.errors}), 400
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    try:
        questionnaire = merge_profile_restrictions(questionnaire, profile)
        nutrition_targets = calculate_nutrition_targets(profile, questionnaire)
    except PlanValidationError as error:
        return jsonify({"error": "Revise seu perfil e as metas nutricionais.", "fields": error.errors}), 400

    queued = enqueue_ai_request("diet_plan", data)
    if queued is not None:
        return queued

    correction = None
    max_attempts = current_app.config["GEMINI_DIET_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        try:
            generated = generate_diet_plan(questionnaire, profile, nutrition_targets, correction)
            plan_data = normalize_diet_output(generated, questionnaire, nutrition_targets)
            break
        except PlanValidationError as error:
            current_app.logger.warning(
                "Invalid generated diet plan (attempt %s/%s)",
                attempt,
                max_attempts,
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
            return jsonify({"error": "A IA está temporariamente indisponível. Tente gerar sua dieta novamente em alguns instantes."}), 503
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
            ai_task_id=getattr(g, "ai_task_id", None),
        )
        db.session.add(plan)
        db.session.flush()
        allowed = {"day_of_week", "meal_type", "description", "calories", "protein", "carbs", "fat", "notes", "items", "prep_instructions", "prep_minutes", "substitutions", "order"}
        for meal in plan_data["meals"]:
            db.session.add(DietPlanMeal(diet_plan_id=plan.id, **{key: meal[key] for key in allowed if key in meal}))
        record_event(
            "plan_generation_succeeded",
            user_id=user.id,
            properties={"plan_type": "diet"},
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save guided diet plan")
        return jsonify({"error": "Não foi possível salvar a dieta gerada."}), 422
    response = jsonify({"message": "Plano alimentar criado.", "plan_id": plan.id, "plan": plan.to_dict_full()})
    response.status_code = 201
    response.headers["Location"] = f"/api/diet_plans/{plan.id}"
    return response


@plan_bp.route("/workout_plans/recommendation", methods=["POST"])
@login_required
def get_workout_recommendation():
    try:
        questionnaire = validate_workout_questionnaire(json_body())
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências do treino.", "fields": error.errors}), 400

    contract = build_workout_contract(questionnaire)
    return jsonify({
        "recommended_split": recommend_workout_split(questionnaire),
        "selected_split": questionnaire["split_type"],
        "quality": contract["quality"],
        "quality_score": contract["quality_score"],
        "adaptation_count": len(contract["adaptations"]),
        "warnings": contract["warnings"],
    }), 200


@plan_bp.route("/workout_plans/generate", methods=["POST"])
@rate_limit("ai", 8, 60)
@ai_consent_required
@premium_required(allow_trial=True)
def create_guided_workout_plan():
    user = g.user
    data = json_body()
    try:
        questionnaire = validate_workout_questionnaire(data)
    except PlanValidationError as error:
        return jsonify({"error": "Revise as preferências do treino.", "fields": error.errors}), 400
    contract = build_workout_contract(questionnaire)
    recommended_split = recommend_workout_split(questionnaire)
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    queued = enqueue_ai_request("workout_plan", data)
    if queued is not None:
        return queued
    max_attempts = current_app.config["GEMINI_WORKOUT_VALIDATION_ATTEMPTS"]
    correction = None
    previous_generated = None
    for attempt in range(1, max_attempts + 1):
        generated = previous_generated
        try:
            response_data = generate_workout_plan(questionnaire, profile, correction, contract)
            generated = (
                merge_workout_day_repairs(
                    previous_generated,
                    response_data,
                    correction["invalid_day_numbers"],
                    questionnaire["days_per_week"],
                )
                if correction
                else response_data
            )
            validate_workout_exercise_selection(generated, questionnaire, contract)
            plan_data = normalize_workout_output(generated, questionnaire, contract)
            break
        except PlanValidationError as error:
            if generated is not None:
                previous_generated = generated
                correction = {
                    "previous_plan": generated,
                    "validation_errors": error.errors,
                    "invalid_day_numbers": invalid_workout_day_numbers(
                        error.errors,
                        questionnaire["days_per_week"],
                    ),
                }
            current_app.logger.warning(
                "Invalid generated workout plan (attempt %s/%s): %s",
                attempt,
                max_attempts,
                sorted(error.errors),
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
            questionnaire_data={
                **questionnaire,
                "contract_quality": contract["quality"],
                "contract_adaptations": contract["adaptations"],
                "contract_warnings": contract["warnings"],
                "recommended_split": recommended_split,
            },
            ai_task_id=getattr(g, "ai_task_id", None),
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
        record_event(
            "plan_generation_succeeded",
            user_id=user.id,
            properties={"plan_type": "workout"},
        )
        db.session.commit()
    except (IntegrityError, TypeError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Unable to save guided workout plan")
        return jsonify({"error": "Não foi possível salvar o treino gerado."}), 422
    response = jsonify({
        "message": "Plano de treino criado.",
        "plan_id": plan.id,
        "plan": plan.to_dict_full(),
        "quality": contract["quality"],
        "adaptations": contract["adaptations"],
        "warnings": contract["warnings"],
        "recommended_split": recommended_split,
    })
    response.status_code = 201
    response.headers["Location"] = f"/api/workout_plans/{plan.id}"
    return response


@plan_bp.route("/diet_plans", methods=["GET"])
@login_required
def get_diet_plans():
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    current_plan_id = profile.current_diet_plan_id if profile else None
    plans, _, _ = page_query(
        DietPlan.query.filter_by(user_id=g.user.id, status="published")
        .options(selectinload(DietPlan.meals))
        .order_by(DietPlan.created_at.desc()),
    )
    payload = []
    for plan in plans.all():
        data = plan.to_dict()
        data["is_current"] = plan.id == current_plan_id
        payload.append(data)
    return jsonify(payload), 200


@plan_bp.route("/diet_plans/current", methods=["GET"])
@login_required
def get_current_diet_plan():
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if not profile or not profile.current_diet_plan_id:
        return jsonify({"plan": None}), 200
    plan = DietPlan.query.filter_by(
        id=profile.current_diet_plan_id,
        user_id=g.user.id,
        status="published",
    ).options(selectinload(DietPlan.meals)).first()
    if not plan:
        profile.current_diet_plan_id = None
        db.session.commit()
        return jsonify({"plan": None}), 200
    data = plan.to_dict_full()
    data["is_current"] = True
    return jsonify({"plan": data}), 200


@plan_bp.route("/diet_plans/<int:plan_id>", methods=["GET"])
@login_required
def get_diet_plan_details(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").options(selectinload(DietPlan.meals)).first_or_404()
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    data = plan.to_dict_full()
    data["is_current"] = bool(profile and profile.current_diet_plan_id == plan.id)
    return jsonify(data), 200


@plan_bp.route("/diet_plans/<int:plan_id>/current", methods=["PUT"])
@login_required
def set_current_diet_plan(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if not profile:
        profile = UserProfile(user_id=g.user.id)
        db.session.add(profile)
    profile.current_diet_plan_id = plan.id
    record_event(
        "plan_set_current",
        user_id=g.user.id,
        properties={"plan_type": "diet"},
    )
    db.session.commit()
    data = plan.to_dict_full()
    data["is_current"] = True
    return jsonify({"message": "Plano alimentar definido como atual.", "plan": data}), 200


@plan_bp.route("/diet_plans/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_diet_plan(plan_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if profile and profile.current_diet_plan_id == plan.id:
        profile.current_diet_plan_id = None
    has_history = (
        DietAdherenceDay.query.filter_by(diet_plan_id=plan.id).first()
        or DietMealDailyState.query.filter_by(diet_plan_id=plan.id).first()
    )
    has_review = ProfessionalReviewRequest.query.filter(
        (ProfessionalReviewRequest.source_diet_plan_id == plan.id)
        | (ProfessionalReviewRequest.proposal_diet_plan_id == plan.id)
    ).first()
    if has_history or has_review:
        plan.status = "archived"
        db.session.commit()
        return jsonify({"message": "Plano removido. O histórico alimentar foi preservado."}), 200
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plano de dieta excluído com sucesso"}), 200


@plan_bp.route("/diet_plans/<int:plan_id>/meals/<int:meal_id>", methods=["PATCH"])
@login_required
def update_diet_plan_meal(plan_id, meal_id):
    plan = DietPlan.query.filter_by(id=plan_id, user_id=g.user.id, status="published").first_or_404()
    meal = DietPlanMeal.query.filter_by(id=meal_id, diet_plan_id=plan.id).first_or_404()
    data = coerce_numbers(json_body(), ("calories", "protein", "carbs", "fat"))
    if "description" in data:
        description = str(data.get("description", "")).strip()
        if not description:
            return jsonify({"error": "Descrição da refeição é obrigatória"}), 400
        meal.description = description
        if data.get("items") is None:
            meal.items = None
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
            maximum = 20_000 if field == "calories" else 5_000
            if not 0 <= data[field] <= maximum:
                return jsonify({"error": "Valor nutricional inválido."}), 400
            setattr(meal, field, data[field])
    db.session.commit()
    return jsonify({"message": "Refeição do plano atualizada", "meal": meal.to_dict()}), 200


@plan_bp.route("/diet_plans/<int:plan_id>/suggest", methods=["POST"])
@rate_limit("ai", 8, 60)
@ai_consent_required
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
    queued = enqueue_ai_request(
        "diet_day",
        data,
        {"plan_id": plan.id},
    )
    if queued is not None:
        return queued
    correction = None
    max_attempts = current_app.config["GEMINI_DIET_VALIDATION_ATTEMPTS"]
    for attempt in range(1, max_attempts + 1):
        try:
            generated = generate_diet_day(questionnaire, profile, existing_meals, feedback, nutrition_targets, correction)
            day_data = normalize_diet_day(generated, questionnaire, nutrition_targets)
            break
        except PlanValidationError as error:
            current_app.logger.warning("Invalid generated diet day (attempt %s/%s)", attempt, max_attempts)
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
    if old_meals and DietMealCheckIn.query.filter(
        DietMealCheckIn.diet_plan_meal_id.in_([meal.id for meal in old_meals])
    ).first():
        return jsonify({"error": "Este cardápio já possui acompanhamento. Crie uma nova versão para preservar o histórico."}), 409
    if old_meals and DietMealDailyState.query.filter(
        DietMealDailyState.selected_plan_meal_id.in_([meal.id for meal in old_meals])
    ).first():
        return jsonify({"error": "Este cardápio já possui acompanhamento. Crie uma nova versão para preservar o histórico."}), 409
    for meal in old_meals:
        db.session.delete(meal)
    for order, meal in enumerate(meals, start=1):
        meal_data = dict(meal)
        meal_data["order"] = order
        db.session.add(DietPlanMeal(diet_plan_id=plan.id, day_of_week=f"Dia {day_index}", **{key: meal_data[key] for key in allowed if key in meal_data}))
    db.session.commit()
    return jsonify({"message": "Cardápio do dia atualizado.", "plan": plan.to_dict_full()}), 200
