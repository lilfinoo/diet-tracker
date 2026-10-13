from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

from flask import Flask

from src.services import ai


def install_client(monkeypatch, barrier=None):
    created = []
    requests = []

    class Client:
        def __init__(self, **kwargs):
            self.models = self
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

        def generate_content(self, **kwargs):
            assert not self.closed
            if barrier is not None:
                barrier.wait(timeout=2)
            requests.append(kwargs)
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason='STOP', content=SimpleNamespace(
                parts=[SimpleNamespace(text='{"ok":true}', thought=False)]))], usage_metadata=None)

    monkeypatch.setattr(ai.genai, 'Client', Client)
    return created, requests


def test_gemini_reuses_client_and_keeps_each_request_options(app, monkeypatch):
    created, requests = install_client(monkeypatch)
    with app.app_context():
        app.config['GEMINI_API_KEY'] = 'test-key'
        ai._gemini_completion('nutrition instructions', 'photo description', 1024, .3,
                              model='nutrition-model', request_timeout=10, image_bytes=b'photo', mime_type='image/jpeg')
        schema = {'type': 'object', 'properties': {'days': {'type': 'array', 'items': {'type': 'string'}}}}
        ai._gemini_completion('plan instructions', 'plan preferences', 12288, .2,
                              model='plan-model', request_timeout=25, json_response=True, json_schema=schema)
    assert len(created) == 1
    assert not created[0].closed
    first, second = requests
    assert first['model'] == 'nutrition-model'
    assert first['config'].system_instruction == 'nutrition instructions'
    assert first['config'].max_output_tokens == 1024
    assert first['config'].http_options.timeout == 10000
    assert first['contents'][0].inline_data.data == b'photo'
    assert second['model'] == 'plan-model'
    assert second['contents'] == 'plan preferences'
    assert second['config'].system_instruction.startswith('plan instructions\n')
    assert 'JSON compacto' in second['config'].system_instruction
    assert second['config'].response_json_schema == schema
    assert second['config'].max_output_tokens == 12288
    assert second['config'].http_options.timeout == 25000
    assert first['config'].http_options.retry_options.attempts == second['config'].http_options.retry_options.attempts == 1


def test_concurrent_requests_initialize_once_without_serializing_calls(app, monkeypatch):
    created, requests = install_client(monkeypatch, Barrier(4))
    app.config['GEMINI_API_KEY'] = 'test-key'

    def call(timeout):
        with app.app_context():
            return ai._gemini_completion('system', f'prompt-{timeout}', 100, .2, request_timeout=timeout)

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(call, [10, 15, 20, 25])) == ['{"ok":true}'] * 4
    assert len(created) == 1
    assert sorted(request['config'].http_options.timeout for request in requests) == [10000, 15000, 20000, 25000]


def test_clients_are_isolated_by_application_and_credential(monkeypatch):
    created, _ = install_client(monkeypatch)
    first, second = Flask('first'), Flask('second')
    for app in (first, second):
        with app.app_context():
            app.config['GEMINI_API_KEY'] = 'first-key'
            app.config['GEMINI_MODEL'] = 'test-model'
            ai._gemini_completion('system', 'prompt', 100, .2)
    with first.app_context():
        first.config['GEMINI_API_KEY'] = 'rotated-key'
        ai._gemini_completion('system', 'prompt', 100, .2)
    assert len(created) == 3


def test_sdk_keeps_wire_timeouts_separate_on_shared_connection(app, monkeypatch):
    import json
    import httpx
    from google import genai
    from google.genai import types

    real_client = genai.Client
    captured = []

    def handle(request):
        captured.append((json.loads(request.content), dict(request.headers), request.extensions['timeout']))
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP',
            'content': {'role': 'model', 'parts': [{'text': '{"ok":true}'}]}}]})

    def client(**kwargs):
        return real_client(**kwargs, http_options=types.HttpOptions(
            client_args={'transport': httpx.MockTransport(handle)}))

    monkeypatch.setattr(ai.genai, 'Client', client)
    with app.app_context():
        app.config['GEMINI_API_KEY'] = 'local-test'
        for timeout in (10, 25, 10):
            ai._gemini_completion('same instructions', 'same prompt', 100, .2,
                                  json_response=True, request_timeout=timeout)
    assert [headers['x-server-timeout'] for _, headers, _ in captured] == ['10', '25', '10']
    assert [timeout['read'] for _, _, timeout in captured] == [10, 25, 10]
    for payload, _, _ in captured:
        assert payload['contents'][0]['parts'][0]['text'] == 'same prompt'
        assert payload['generationConfig']['temperature'] == .2
        assert payload['generationConfig']['maxOutputTokens'] == 100
        assert payload['generationConfig']['responseMimeType'] == 'application/json'
        assert 'http_options' not in payload['generationConfig']
