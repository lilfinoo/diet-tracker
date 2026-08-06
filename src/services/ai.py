import json
import re

from flask import current_app
from google import genai
from google.genai import types

from src.services.workout_plans import (
    allowed_groups_for_day,
    catalog_by_key,
    catalog_for_prompt,
    required_training_roles_for_day,
    workout_day_specs,
)


class AIServiceError(Exception):
    """Raised when Gemini cannot return a usable response."""


class AIResponseError(AIServiceError):
    """Raised when Gemini returns a response that does not match the expected contract."""


class AITruncatedResponseError(AIResponseError):
    """Raised when Gemini reaches the configured output limit."""


class AIQuotaExceededError(AIServiceError):
    """Raised when the configured Gemini model has no remaining request quota."""


def _json_object(content: str) -> dict:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise AIResponseError("Gemini response did not contain JSON")
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as error:
            raise AIResponseError("Gemini response contained invalid JSON") from error
    if not isinstance(data, dict):
        raise AIResponseError("Gemini response JSON must be an object")
    return data


def _completion(
    system_instruction: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    json_response=False,
    model=None,
    json_schema=None,
) -> str:
    api_key = current_app.config["GEMINI_API_KEY"]
    if not api_key:
        raise AIServiceError("GEMINI_API_KEY is not configured")

    config_options = {
        "system_instruction": system_instruction,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
        "response_mime_type": "application/json" if json_response else "text/plain",
    }
    if json_schema:
        config_options["response_json_schema"] = json_schema
    config = types.GenerateContentConfig(**config_options)
    timeout = current_app.config.get("GEMINI_TIMEOUT", 90)
    try:
        # Keep the HTTP client alive until the synchronous request has completed.
        with genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout)) as client:
            response = client.models.generate_content(
                model=model or current_app.config["GEMINI_MODEL"],
                contents=prompt,
                config=config,
            )
        candidate = next(iter(response.candidates or []), None)
        finish_reason = getattr(candidate, "finish_reason", None)
        finish_reason_name = getattr(finish_reason, "name", str(finish_reason))
        usage = getattr(response, "usage_metadata", None)
        current_app.logger.info(
            "Gemini response model=%s finish_reason=%s usage=%s",
            model or current_app.config["GEMINI_MODEL"],
            finish_reason_name,
            usage,
        )
        if "MAX_TOKENS" in finish_reason_name:
            raise AITruncatedResponseError("Gemini response reached the output token limit")

        text_parts = [
            part.text
            for part in getattr(getattr(candidate, "content", None), "parts", []) or []
            if part.text and not getattr(part, "thought", False)
        ]
        text = "".join(text_parts).strip()
        if not text:
            raise AIResponseError("Gemini returned an empty response")
        return text
    except AIServiceError:
        raise
    except Exception as error:
        error_text = str(error)
        if getattr(error, "status_code", None) == 429 or getattr(error, "code", None) == 429 or "RESOURCE_EXHAUSTED" in error_text:
            delay_match = re.search(r"retry in\s+(\d+)", error_text, re.IGNORECASE)
            delay = f" em cerca de {delay_match.group(1)} segundos" if delay_match else " mais tarde"
            raise AIQuotaExceededError(f"A cota da IA foi atingida. Tente novamente{delay}.") from error
        raise AIServiceError("Gemini provider request failed") from error


def calculate_nutrition(food_description: str) -> dict:
    is_vague = not re.search(
        r"\d|grama|colher|concha|fatia|ml|xícara|porção|unidade",
        food_description,
        re.IGNORECASE,
    )
    prompt = f"""Analise a seguinte descrição de alimentos e forneça informações nutricionais.
Descrição: {food_description}
Responda somente com JSON: {{"calories": número, "protein": número, "carbs": número, "fat": número}}.
Seja preciso e considere porções típicas mencionadas."""
    if is_vague:
        prompt += "\nSe não houver quantidades, assuma porções médias brasileiras."
    data = _json_object(
        _completion(
            "Você é nutricionista. Retorne somente JSON válido.",
            prompt,
            512,
            0.3,
            json_response=True,
            model=current_app.config["GEMINI_STRUCTURED_MODEL"],
        )
    )
    try:
        return {
            "calories": float(data["calories"]),
            "protein": float(data["protein"]),
            "carbs": float(data["carbs"]),
            "fat": float(data["fat"]),
            "precision": "baixa" if is_vague else "alta",
        }
    except (KeyError, TypeError, ValueError) as error:
        raise AIResponseError("Gemini nutrition response had invalid values") from error


def generate_response(message: str, user, profile) -> str:
    context = f"Você é um assistente fitness especializado em nutrição e treino. O usuário se chama {user.username}. "
    if profile:
        for label, value, suffix in (
            ("Idade", profile.age, "anos"),
            ("Gênero", profile.gender, ""),
            ("Objetivo", profile.goal, ""),
            ("Nível de atividade", profile.activity_level, ""),
            ("Restrições alimentares", profile.dietary_restrictions, ""),
            ("Peso", profile.weight, "kg"),
            ("Altura", profile.height, "cm"),
        ):
            if value is not None:
                context += f"{label}: {value} {suffix}. "
    context += """Responda de forma amigável, útil e personalizada em português.
Seja objetivo: use no máximo 120 palavras, priorize uma ação prática e use no máximo 4 tópicos curtos quando necessário.
Não repita o perfil, não gere planos completos sem pedido explícito e faça uma pergunta curta quando faltar informação essencial."""
    try:
        return _completion(
            context,
            message,
            current_app.config["GEMINI_CHAT_MAX_TOKENS"],
            0.5,
            model=current_app.config["GEMINI_CHAT_MODEL"],
        )
    except AITruncatedResponseError:
        concise_context = context + "\nA resposta anterior excedeu o limite. Responda agora em no máximo 60 palavras e uma única ação principal."
        try:
            return _completion(
                concise_context,
                message,
                1024,
                0.3,
                model=current_app.config["GEMINI_CHAT_MODEL"],
            )
        except AITruncatedResponseError:
            return "Diga seu objetivo principal e eu envio uma orientação curta e prática."


def _profile_context(profile):
    if not profile:
        return {}
    return {
        "age": profile.age,
        "gender": profile.gender,
        "goal": profile.goal,
        "activity_level": profile.activity_level,
        "dietary_restrictions": profile.dietary_restrictions,
        "weight": profile.weight,
        "height": profile.height,
    }


def generate_workout_plan(questionnaire: dict, profile) -> dict:
    day_specs = workout_day_specs(questionnaire["split_type"], questionnaire["days_per_week"])
    for spec in day_specs:
        spec["allowed_groups"] = sorted(allowed_groups_for_day(questionnaire["split_type"], spec["code"]))
        spec["required_training_roles"] = [
            sorted(alternatives)
            for alternatives in required_training_roles_for_day(questionnaire["split_type"], spec["code"])
        ]
    payload = {
        "questionnaire": questionnaire,
        "profile": _profile_context(profile),
        "required_days": day_specs,
        "exercise_catalog": catalog_for_prompt(questionnaire),
        "programming_constraints": {
            "20_30_minutes": "3 a 5 exercícios",
            "45_60_minutes": "4 a 7 exercícios",
            "75_90_minutes": "6 a 8 exercícios",
        },
    }
    schema = {
        "type": "object",
        "required": ["type", "title", "description", "days"],
        "properties": {
            "type": {"type": "string", "enum": ["workout_plan"]},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["focus", "exercises"],
                    "properties": {
                        "focus": {"type": "string"},
                        "exercises": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["catalog_key", "sets", "reps", "rest_seconds"],
                                "properties": {
                                    "catalog_key": {"type": "string"},
                                    "sets": {"type": "integer"},
                                    "reps": {"type": "string"},
                                    "weight": {"type": "string"},
                                    "rest_seconds": {"type": "integer"},
                                    "effort_guidance": {"type": "string"},
                                    "notes": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }
    system_instruction = """Você é um treinador experiente e monta programas gerais, coerentes e seguros em português.
Use somente catalog_key fornecida no catálogo e siga exatamente required_days, focus_guidance e a ordem dos dias.
Respeite experiência, objetivo, equipamentos, limitações, duração e prioridades do usuário.

REGRAS DE SELEÇÃO:
- Cada exercício precisa cumprir uma função distinta. Trocar barra por halter ou máquina sem mudar ângulo, padrão ou estímulo não conta como variedade.
- Quando training_role não for nulo, nunca o repita no mesmo dia. Use no máximo dois exercícios do mesmo group, exceto em um dia específico de peito, que pode ter até quatro exercícios de horizontal_push se todos tiverem training_role diferentes.
- Em treino de peito, use no máximo uma pressão reta. Depois priorize pressão inclinada e, conforme duração e objetivo, pressão declinada ou adução/isolamento (crucifixo/crossover). Não gere três supinos retos.
- Em costas, combine puxada vertical e remada antes de adicionar outra variação.
- Em dias específicos de pernas, combine dominante de joelho, cadeia posterior e ao menos uma flexão de joelho; use extensão de joelho quando contribuir para o objetivo. Não preencha o treino com variações de agachamento.
- Em ombros, combine desenvolvimento, elevação lateral e trabalho complementar; não repita desenvolvimentos equivalentes.
- Ordene exercícios compostos e tecnicamente exigentes primeiro, acessórios depois e core/cardio por último.
- Nos dias repetidos da semana, mantenha a função muscular, mas varie exercício, faixa de repetições ou ênfase quando isso for seguro.

PRESCRIÇÃO:
- Adeque a quantidade de exercícios à duração indicada em programming_constraints.
- Use séries, repetições, descanso e esforço coerentes com objetivo e experiência; iniciantes não devem receber volume ou técnicas avançadas excessivas.
- Escreva em notes uma orientação técnica curta e específica, não frases genéricas.
Cada dia deve ter entre 3 e 8 exercícios. Não faça diagnóstico, tratamento, promessa de resultado ou prescrição para dor/lesão."""
    return _json_object(_completion(
        system_instruction,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        current_app.config["GEMINI_PLAN_MAX_TOKENS"],
        0.25,
        json_response=True,
        model=current_app.config["GEMINI_STRUCTURED_MODEL"],
        json_schema=schema,
    ))


def generate_diet_plan(questionnaire: dict, profile) -> dict:
    payload = {"questionnaire": questionnaire, "profile": _profile_context(profile)}
    schema = {
        "type": "object",
        "required": ["type", "title", "description", "days"],
        "properties": {
            "type": {"type": "string", "enum": ["diet_plan"]},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["meals"],
                    "properties": {
                        "meals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["meal_type", "items", "prep", "prep_minutes", "calories", "protein", "carbs", "fat"],
                                "properties": {
                                    "meal_type": {"type": "string"},
                                    "items": {"type": "array", "items": {"type": "string"}},
                                    "prep": {"type": "string"},
                                    "prep_minutes": {"type": "integer"},
                                    "calories": {"type": "number"},
                                    "protein": {"type": "number"},
                                    "carbs": {"type": "number"},
                                    "fat": {"type": "number"},
                                    "notes": {"type": "string"},
                                    "substitutions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "required": ["replace", "alternatives"],
                                            "properties": {
                                                "replace": {"type": "string"},
                                                "alternatives": {"type": "array", "items": {"type": "string"}},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }
    system_instruction = """Você cria planos alimentares gerais e educativos em português.
Gere exatamente 3 dias rotativos e exatamente a quantidade de refeições solicitada em cada dia.
Respeite alergias, intolerâncias, padrão alimentar, orçamento, preferências e tempo de preparo.
Quando o usuário informar ingredientes disponíveis (available_ingredients), monte o plano usando principalmente esses ingredientes.
Use porções claras, macros como estimativas e no máximo duas substituições curtas por refeição.
Não prescreva tratamento, suplementos, dietas extremas ou resultados garantidos."""
    return _json_object(_completion(
        system_instruction,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        current_app.config["GEMINI_PLAN_MAX_TOKENS"],
        0.2,
        json_response=True,
        model=current_app.config["GEMINI_STRUCTURED_MODEL"],
        json_schema=schema,
    ))


def generate_diet_day(questionnaire: dict, profile, existing_meals: list, feedback: str) -> dict:
    payload = {
        "questionnaire": questionnaire,
        "profile": _profile_context(profile),
        "existing_meals": existing_meals,
        "requested_change": feedback,
    }
    schema = {
        "type": "object",
        "required": ["type", "meals"],
        "properties": {
            "type": {"type": "string", "enum": ["diet_plan_day"]},
            "meals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["meal_type", "items", "prep", "prep_minutes", "calories", "protein", "carbs", "fat"],
                    "properties": {
                        "meal_type": {"type": "string"},
                        "items": {"type": "array", "items": {"type": "string"}},
                        "prep": {"type": "string"},
                        "prep_minutes": {"type": "integer"},
                        "calories": {"type": "number"},
                        "protein": {"type": "number"},
                        "carbs": {"type": "number"},
                        "fat": {"type": "number"},
                        "notes": {"type": "string"},
                        "substitutions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["replace", "alternatives"],
                                "properties": {
                                    "replace": {"type": "string"},
                                    "alternatives": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        },
                    },
                },
            },
        },
    }
    system_instruction = """Você ajusta o cardápio de UM dia de um plano alimentar em português.
    Reescreva exatamente a quantidade de refeições informada no questionnaire, incorporando somente o pedido do usuário (requested_change) e mantendo os demais dias intactos.
    Respeite alergias, intolerâncias, padrão alimentar, orçamento, equipamentos e tempo de preparo existentes.
    Use porções claras, macros como estimativas e no máximo duas substituições curtas por refeição.
    Não prescreva tratamento, suplementos, dietas extremas ou resultados garantidos."""
    return _json_object(_completion(
        system_instruction,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        current_app.config["GEMINI_PLAN_MAX_TOKENS"],
        0.35,
        json_response=True,
        model=current_app.config["GEMINI_STRUCTURED_MODEL"],
        json_schema=schema,
    ))


def classify_exercise_catalog_key(exercise_name: str) -> str | None:
    catalog = [{"key": item["key"], "name": item["name"]} for item in catalog_by_key().values()]
    schema = {
        "type": "object",
        "required": ["catalog_key"],
        "properties": {"catalog_key": {"type": "string"}},
    }
    result = _json_object(_completion(
        "Associe o exercício informado a uma chave do catálogo. Retorne uma string vazia se não houver correspondência segura.",
        json.dumps({"exercise": exercise_name, "catalog": catalog}, ensure_ascii=False, separators=(",", ":")),
        256,
        0.0,
        json_response=True,
        model=current_app.config["GEMINI_STRUCTURED_MODEL"],
        json_schema=schema,
    ))
    catalog_key = result.get("catalog_key")
    return catalog_key if catalog_key in catalog_by_key() else None
