import json
import re
import time
from typing import Optional

from flask import current_app
from google import genai
from google.genai import types

from src.services.diet_plans import diet_restriction_policy
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


class AIServiceUnavailableError(AIServiceError):
    """Raised when Gemini temporarily cannot accept a request."""


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
    image_bytes=None,
    mime_type=None,
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
    timeout_ms = timeout * 1000
    try:
        # Keep the HTTP client alive until the synchronous request has completed.
        with genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms)) as client:
            if image_bytes and mime_type:
                contents = [
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    types.Part.from_text(text=prompt),
                ]
            else:
                contents = prompt
            response = client.models.generate_content(
                model=model or current_app.config["GEMINI_MODEL"],
                contents=contents,
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
        status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
        if status_code == 429 or "RESOURCE_EXHAUSTED" in error_text:
            delay_match = re.search(r"retry in\s+(\d+)", error_text, re.IGNORECASE)
            delay = f" em cerca de {delay_match.group(1)} segundos" if delay_match else " mais tarde"
            raise AIQuotaExceededError(f"A cota da IA foi atingida. Tente novamente{delay}.") from error
        if status_code == 503 or "UNAVAILABLE" in error_text:
            raise AIServiceUnavailableError("A IA está temporariamente com alta demanda.") from error
        raise AIServiceError("Gemini provider request failed") from error


def calculate_nutrition(
    food_description: str,
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> dict:
    has_image = bool(image_bytes and mime_type)
    is_vague = not re.search(
        r"\d|grama|colher|concha|fatia|ml|xícara|porção|unidade",
        food_description,
        re.IGNORECASE,
    )
    if food_description:
        prompt = f"""Analise a seguinte descrição de alimentos e forneça informações nutricionais.
Descrição: {food_description}
Responda somente com JSON: {{"calories": número, "protein": número, "carbs": número, "fat": número}}.
Seja preciso e considere porções típicas mencionadas."""
        if is_vague:
            prompt += "\nSe não houver quantidades, assuma porções médias brasileiras."
    else:
        prompt = """Analise a foto do prato e forneça informações nutricionais.
Responda somente com JSON: {"calories": número, "protein": número, "carbs": número, "fat": número}.
Assuma porções médias brasileiras se não houver referência de tamanho."""
    if has_image:
        prompt += "\nA foto do prato está anexada: identifique os alimentos e estime as quantidades."
    data = _json_object(
        _completion(
            "Você é nutricionista. Retorne somente JSON válido.",
            prompt,
            512,
            0.3,
            json_response=True,
            model=current_app.config["GEMINI_STRUCTURED_MODEL"],
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
    )
    try:
        return {
            "calories": float(data["calories"]),
            "protein": float(data["protein"]),
            "carbs": float(data["carbs"]),
            "fat": float(data["fat"]),
            "precision": "alta" if has_image or not is_vague else "baixa",
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
    system_instruction = """Você monta programas individualizados de musculação em português com base em treinamento resistido e anatomia funcional.
Use SOMENTE catalog_key presente em exercise_catalog. Siga exatamente required_days, focus_guidance, required_groups, allowed_groups e a ordem dos dias. Nunca invente exercício, ID ou equipamento.

RACIOCÍNIO SILENCIOSO OBRIGATÓRIO:
Antes de responder, determine objetivo, experiência, frequência, duração, prioridades, manutenção, volume semanal por músculo, distribuição do volume, padrões necessários, sobreposição entre compostos e isoladores e capacidade de recuperação. Depois selecione o menor conjunto de exercícios capaz de entregar estímulo suficiente. Não exponha esse raciocínio na resposta.

VOLUME, FREQUÊNCIA E RECUPERAÇÃO:
- Para hipertrofia, use aproximadamente 10 séries efetivas semanais por grande grupo como referência inicial, não como obrigação. Iniciantes normalmente precisam de menos; aumente apenas músculos prioritários quando experiência e recuperação permitirem.
- Conte aproximadamente 1 série para o motor principal e 0,5 para sinergistas relevantes: supinos também treinam tríceps e deltoide anterior; remadas e puxadas também treinam flexores do cotovelo; desenvolvimentos também treinam tríceps.
- Quando a rotina permitir, distribua grandes grupos em cerca de duas exposições semanais. Frequência serve para distribuir volume e fadiga, não para criar dias desnecessários.
- Evite alto volume consecutivo para o mesmo músculo e volume direto redundante de braços/deltoide anterior quando compostos já fornecem estímulo suficiente.

SELEÇÃO E COBERTURA:
- Cada exercício deve acrescentar função, região, comprimento muscular ou estímulo relevante. Trocar barra por halter ou máquina sem mudar o estímulo não conta como variedade.
- Quando training_role não for nulo, não repita a mesma função no dia. Use no máximo dois exercícios do mesmo group, exceto em dia específico de peito com funções biomecânicas diferentes.
- Peito: combine pressão horizontal e inclinada; adicione declinado, fly ou crossover apenas quando o volume justificar. Supino declinado é uma opção útil para ênfase esternocostal/inferior, não uma obrigação. Não empilhe variações equivalentes de supino.
- Costas: cubra puxada vertical e remada horizontal; considere extensão do ombro/dorsal e deltoide posterior quando o catálogo e o volume permitirem. Não use várias remadas equivalentes.
- Ombros: considere anterior, lateral e posterior. Supinos já contam para anterior; normalmente priorize trabalho específico lateral/posterior em vez de elevação frontal redundante.
- Tríceps: pressões já contam indiretamente; quando houver volume direto suficiente, combine extensão junto ao corpo e acima da cabeça para a cabeça longa.
- Bíceps: puxadas contam indiretamente; poucas variações complementares são suficientes, podendo combinar flexão tradicional e pegada neutra.
- Quadríceps: combine dominante de joelho e, quando útil, extensão isolada. Posteriores: inclua flexão de joelho e hinge; agachamento não substitui esses dois padrões.
- Glúteos: distribua agachar/afundar, extensão de quadril e hinge conforme prioridade. Panturrilhas prioritárias podem alternar joelho estendido e flexionado.
- Core: use volume moderado entre flexão, anti-extensão/estabilidade e controle lateral/rotacional; não prescreva dezenas de repetições diárias.

ESFORÇO, REPETIÇÕES E DESCANSO:
- Hipertrofia: em geral 1–3 RIR; 0–1 RIR apenas ocasionalmente em isoladores seguros para experientes. Iniciantes ficam mais longe da falha enquanto aprendem técnica.
- Compostos: normalmente 5–12 repetições e 120–240 s de descanso. Máquinas/intermediários: 6–15 e 90–180 s. Isoladores: 8–20, ocasionalmente 15–30, e 60–120 s.
- Força: movimento prioritário cedo, geralmente 1–6 repetições e 120–300 s; acessórios preservam hipertrofia e equilíbrio. Não transforme todo o treino em séries pesadas.
- Perda de gordura mantém estrutura de hipertrofia, carga e progressão; não transforme musculação em cardio. Condicionamento/resistência pode usar repetições maiores sem sacrificar técnica.
- Priorize amplitude completa e confortável. Não reduza amplitude para aumentar carga.

ORDEM, TEMPO E PROGRESSÃO:
- Coloque primeiro o músculo ou movimento prioritário, depois compostos importantes, complementares e isoladores. Um exercício prioritário pode vir antes do maior composto.
- Respeite rigorosamente programming_constraints: 20–30 min = 3–5 exercícios; 45–60 = 4–7; 75–90 = 6–8. Não gere sessões inviáveis.
- Prescreva progressão dupla nas orientações: manter carga até alcançar o topo da faixa em todas as séries no RIR indicado, então aumentar moderadamente e retornar à parte baixa da faixa.
- Em cada exercício: sets de 1 a 6; rest_seconds de 20 a 300; reps curto, específico e com no máximo 30 caracteres; effort_guidance deve informar RIR; notes deve trazer orientação técnica útil e curta.

NÍVEL E SEGURANÇA:
- Iniciante: poucos movimentos estáveis, volume moderado, técnica e progressão simples; sem técnicas avançadas, falha constante ou complexidade de fisiculturista.
- Intermediário: aumente gradualmente especificidade, volume e variedade útil. Avançado: refine prioridade, fadiga, comprimentos musculares e especialização sem confundir complexidade com qualidade.
- Respeite equipamentos, exercícios evitados e limitações. Não diagnostique nem trate lesão. Evite movimentos declaradamente problemáticos e oriente avaliação profissional para dor relevante ou persistente.

AUDITORIA SILENCIOSA FINAL:
Confirme objetivo, volume direto e indireto, frequência, cobertura regional, redundância, recuperação, prioridades, nível, duração, equipamentos e limitações. Corrija qualquer falha antes de retornar somente o JSON do schema."""
    contents = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    primary_model = current_app.config["GEMINI_WORKOUT_MODEL"]
    fallback_model = current_app.config["GEMINI_WORKOUT_FALLBACK_MODEL"]
    try:
        response = _completion(
            system_instruction,
            contents,
            current_app.config["GEMINI_PLAN_MAX_TOKENS"],
            0.25,
            json_response=True,
            model=primary_model,
            json_schema=schema,
        )
    except AIServiceUnavailableError:
        if not fallback_model or fallback_model == primary_model:
            raise
        current_app.logger.warning(
            "Workout model %s unavailable; trying fallback %s",
            primary_model,
            fallback_model,
        )
        response = _completion(
            system_instruction,
            contents,
            current_app.config["GEMINI_PLAN_MAX_TOKENS"],
            0.2,
            json_response=True,
            model=fallback_model,
            json_schema=schema,
        )
    return _json_object(response)


def _diet_meal_schema(include_optional=True):
    properties = {
        "meal_type": {"type": "string"},
        "items": {"type": "array", "items": {"type": "string"}},
        "calories": {"type": "number"},
        "protein": {"type": "number"},
        "carbs": {"type": "number"},
        "fat": {"type": "number"},
    }
    if include_optional:
        properties.update({
            "prep": {"type": "string"},
            "prep_minutes": {"type": "integer"},
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
        })
    return {
        "type": "object",
        "required": ["meal_type", "items", "calories", "protein", "carbs", "fat"],
        "properties": properties,
    }


def _generate_diet_json(system_instruction, payload, schema):
    attempts = max(1, current_app.config["GEMINI_DIET_RETRY_ATTEMPTS"])
    for attempt in range(1, attempts + 1):
        try:
            return _json_object(_completion(
                system_instruction,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                current_app.config["GEMINI_DIET_PLAN_MAX_TOKENS"],
                0.2,
                json_response=True,
                model=current_app.config["GEMINI_DIET_PLAN_MODEL"],
                json_schema=schema,
            ))
        except AIServiceUnavailableError:
            if attempt == attempts:
                raise
            delay = 2 ** (attempt - 1)
            current_app.logger.warning("Diet generation unavailable; retrying in %ss (%s/%s)", delay, attempt, attempts)
            time.sleep(delay)


def generate_diet_plan(questionnaire: dict, profile, nutrition_targets: dict, correction=None) -> dict:
    payload = {
        "questionnaire": questionnaire,
        "profile": _profile_context(profile),
        "nutritionTargets": nutrition_targets,
        "restrictionPolicy": diet_restriction_policy(questionnaire),
    }
    if correction:
        payload["correction"] = correction
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
                    "properties": {"meals": {"type": "array", "items": _diet_meal_schema(False)}},
                },
            },
        },
    }
    system_instruction = """Você monta planos alimentares gerais e educativos em português a partir de metas calculadas pelo sistema.
Gere exatamente 3 dias rotativos e exatamente a quantidade de refeições solicitada em cada dia.
Respeite alergias, intolerâncias, padrão alimentar, orçamento, preferências e tempo de preparo.
Use porções claras, alimentos realistas e os macros solicitados. Some calorias, proteína, carboidratos e gordura de cada dia antes de responder. Os valores de nutritionTargets são restrições do sistema.
Nunca use itens de restrictionPolicy.prohibited. Produtos explicitamente sem lactose e alternativas vegetais são permitidos.
Evite restrictionPolicy.avoid_when_possible, mas eles são preferências, não alergias. Retorne somente campos do schema.
Se correction existir, use correction.previous_plan como rascunho, corrija todos os validation_errors e mantenha cada total dentro de correction.allowed_daily_ranges."""
    return _generate_diet_json(system_instruction, payload, schema)


def generate_diet_day(questionnaire: dict, profile, existing_meals: list, feedback: str, nutrition_targets: dict, correction=None) -> dict:
    payload = {
        "questionnaire": questionnaire,
        "profile": _profile_context(profile),
        "existing_meals": existing_meals,
        "requested_change": feedback,
        "nutritionTargets": nutrition_targets,
        "restrictionPolicy": diet_restriction_policy(questionnaire),
    }
    if correction:
        payload["correction"] = correction
    schema = {
        "type": "object",
        "required": ["type", "meals"],
        "properties": {
            "type": {"type": "string", "enum": ["diet_plan_day"]},
            "meals": {"type": "array", "items": _diet_meal_schema()},
        },
    }
    system_instruction = """Você ajusta o cardápio de UM dia de um plano alimentar em português.
Reescreva exatamente a quantidade de refeições informada no questionnaire, incorporando o pedido e mantendo os demais dias intactos.
Os valores de nutritionTargets são restrições do sistema, não sugestões. NÃO recalcule calorias ou macronutrientes.
Use porções claras e estime calorias e macros de cada refeição. Respeite restrições, preferências e tempo de preparo.
As estimativas não precisam ser milimétricas, mas o total diário deve ficar próximo das metas.
Se correction existir, corrija exatamente as diferenças informadas. Não prescreva tratamento, suplementos ou dietas extremas."""
    return _generate_diet_json(system_instruction, payload, schema)


def classify_exercise_catalog_key(exercise_name: str) -> Optional[str]:
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
