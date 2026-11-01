# View: implementation-architecture.svg#O8
# Use simulated SDK HTTP responses to prove primary key/URL/model stay paired and
# 429 never switches to backup; exercise tool schema/quote parsing without external requests.
"""Primary-only requests use real SDK HTTP errors, without external network calls."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIStatusError

from backend import processing
from backend.api import create_app
from backend.chat import Question, chat
from backend.storage import Library
from backend.test_storage import add, ready


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    for name, value in dict(OPENAI_API_KEY='primary-test-key', OPENAI_BASE_URL='https://primary.invalid/v1',
                            OPENAI_MODEL='primary-model', BACKUP_API_KEY='backup-test-key',
                            BACKUP_BASE_URL='https://backup.invalid/v1', BACKUP_MODEL='backup-model').items():
        monkeypatch.setenv(name, value)


def transport(monkeypatch, handle):
    original = processing.OpenAI
    monkeypatch.setattr(processing, 'OpenAI', lambda **options: original(**options,
        http_client=httpx.Client(transport=httpx.MockTransport(handle))))


def completion(name, arguments):
    return httpx.Response(200, json=dict(id='test', created=0, object='chat.completion', model='test', choices=[dict(
        index=0, finish_reason='tool_calls', message=dict(role='assistant', content=None, tool_calls=[dict(
            id='test-call', type='function', function=dict(name=name, arguments=json.dumps(arguments)))]))]))


def test_primary_key_url_and_model_remain_selected_after_quota_error(monkeypatch):
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append((request.url.host, request.headers['authorization'], body['model']))
        return httpx.Response(429, json={'error': {'message': 'Quota exhausted'}})
    transport(monkeypatch, handle)
    for _ in range(2):
        with pytest.raises(processing.ProcessingError, match='429'):
            processing.check('A fictional record')
    assert requests == [('primary.invalid', 'Bearer primary-test-key', 'primary-model')] * 2


@pytest.mark.parametrize('status', [400, 401, 403, 500, 503])
def test_other_errors_do_not_switch_credentials(monkeypatch, status):
    hosts = []
    def handle(request):
        hosts.append(request.url.host)
        return httpx.Response(status, json={'error': {'message': 'Failure'}})
    transport(monkeypatch, handle)

    def ask():
        with processing.client() as api:
            return api.chat.completions.create(model=processing.model(), messages=[])

    with pytest.raises(APIStatusError):
        ask()
    assert hosts == ['primary.invalid']


def test_completion_options_follow_only_the_primary_endpoint(monkeypatch):
    monkeypatch.setenv('BACKUP_BASE_URL', 'https://api.deepseek.com')
    assert processing.completion_options() == {}
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://api.deepseek.com')
    assert processing.completion_options() == {'extra_body': {'thinking': {'type': 'disabled'}}}


@pytest.mark.parametrize('invalid_schema', [False, True])
def test_literal_ocr_controls_preserve_quotes_without_bypassing_schema(monkeypatch, invalid_schema):
    text = 'Patient\tJohn\nAge\t180'
    def handle(request):
        result = completion('report_concerns', dict(concerns=[dict(quote=text, reason='Age exceeds 150')]))
        body = result.json()
        call = body['choices'][0]['message']['tool_calls'][0]['function']
        call['arguments'] = call['arguments'].replace('\\t', '\t').replace('\\n', '\n')
        if invalid_schema:
            call['arguments'] = call['arguments'].replace('"concerns"', '"unexpected"')
        return httpx.Response(200, json=body)
    transport(monkeypatch, handle)
    if invalid_schema:
        with pytest.raises(processing.ProcessingError, match='invalid result'):
            processing.check(text)
    else:
        assert processing.check(text) == [dict(quote=text, reason='Age exceeds 150', start=0, end=len(text))]


def test_chat_quota_error_never_contacts_backup_or_changes_records(tmp_path, monkeypatch):
    library = Library(tmp_path / 'primary.sqlite3')
    file = ready(library, add(library, 'report'))
    hosts = []
    def handle(request):
        hosts.append(request.url.host)
        if len(hosts) == 1:
            return completion('read_documents', dict(file_ids=[file['id']]))
        return httpx.Response(429, json={'error': {'message': 'Quota exhausted'}})
    transport(monkeypatch, handle)
    with pytest.raises(processing.ProcessingError, match='429'):
        chat(library, Question(message='What is documented?'))
    assert hosts == ['primary.invalid', 'primary.invalid']
    assert library.get(file['id'])['revision'] == file['revision']


def test_config_names_only_primary_without_keys(tmp_path):
    with TestClient(create_app(tmp_path / 'config.sqlite3')) as client:
        config = client.get('/api/config').json()
    assert 'primary.invalid' in config['service'] and 'primary-model' in config['service']
    assert 'backup.invalid' not in config['service'] and 'backup-model' not in config['service']
    assert 'primary-test-key' not in str(config) and 'backup-test-key' not in str(config)
