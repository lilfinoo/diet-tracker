"""OpenAI transport used only after an authorized Gemini failure."""
import base64
import copy

import httpx
from flask import current_app

from src.services.ai import AIQuotaExceededError, AIResponseError, AIServiceError, AIServiceUnavailableError


def _strict_schema(schema):
    result = copy.deepcopy(schema)

    def close(node):
        if not isinstance(node, dict):
            return
        if node.get('type') == 'object':
            properties = node.get('properties', {})
            required = set(node.get('required', []))
            for name, value in list(properties.items()):
                close(value)
                if name not in required:
                    properties[name] = {'anyOf': [value, {'type': 'null'}]}
            node['required'] = list(properties)
            node['additionalProperties'] = False
        else:
            for value in node.values():
                if isinstance(value, dict):
                    close(value)
                elif isinstance(value, list):
                    for item in value:
                        close(item)

    close(result)
    return result


def completion(system_instruction, prompt, max_tokens, temperature, *, json_response=False,
               json_schema=None, image_bytes=None, mime_type=None, timeout=60):
    api_key = current_app.config.get('OPENAI_API_KEY')
    if not api_key:
        raise AIServiceError('OpenAI fallback is not configured')
    content = [{'type': 'input_text', 'text': prompt}]
    if image_bytes and mime_type:
        encoded = base64.b64encode(image_bytes).decode('ascii')
        content.append({'type': 'input_image', 'image_url': f'data:{mime_type};base64,{encoded}'})
    payload = {
        'model': current_app.config['OPENAI_FALLBACK_MODEL'],
        'instructions': system_instruction,
        'input': [{'role': 'user', 'content': content}],
        'max_output_tokens': max_tokens,
        'temperature': temperature,
        'store': False,
    }
    if json_response:
        payload['text'] = {'format': (
            {'type': 'json_schema', 'name': 'fit_tracker_result', 'strict': True,
             'schema': _strict_schema(json_schema)} if json_schema else {'type': 'json_object'}
        )}
    try:
        # No transport retries: the owning generation controls attempts.
        with httpx.Client(timeout=timeout) as client:
            response = client.post('https://api.openai.com/v1/responses', json=payload,
                                   headers={'Authorization': f'Bearer {api_key}'})
    except httpx.HTTPError as error:
        current_app.logger.warning('OpenAI fallback transport failed type=%s', type(error).__name__)
        raise AIServiceUnavailableError('A IA está temporariamente indisponível.') from error
    if response.status_code != 200:
        current_app.logger.warning('OpenAI fallback failed http_status=%s', response.status_code)
        if response.status_code == 429:
            raise AIQuotaExceededError('O serviço de IA está temporariamente sobrecarregado. Seu acesso não foi alterado. Tente novamente em instantes.')
        if response.status_code >= 500 or response.status_code == 408:
            raise AIServiceUnavailableError('A IA está temporariamente indisponível.')
        raise AIServiceError('OpenAI fallback request failed')
    try:
        result = response.json()
        if result.get('status') != 'completed':
            raise AIResponseError('OpenAI returned an incomplete response')
        parts = [part for item in result.get('output', []) if item.get('type') == 'message'
                 for part in item.get('content', [])]
        if any(part.get('type') == 'refusal' for part in parts):
            raise AIResponseError('OpenAI refused this generation')
        text = ''.join(part['text'] for part in parts if part.get('type') == 'output_text').strip()
        if not text:
            raise AIResponseError('OpenAI returned no usable output')
        return text
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise AIResponseError('OpenAI returned invalid output') from error
