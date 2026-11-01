"""Stage receipts must describe real work and never expose draft answers."""

import json

from fastapi.testclient import TestClient
import pytest

from backend.api import create_app
from backend.chat import Question, chat
from backend.processing import ProcessingError
from backend.storage import Library
from backend.test_chat import answer, sdk
from backend.test_storage import add, ready


def test_real_tool_flow_reports_stages_in_order(tmp_path, monkeypatch):
    library = Library(tmp_path / 'progress.sqlite3')
    file = ready(library, add(library, 'report'))
    sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id']])), answer(file['id']), answer(file['id'])])
    stages = []
    result = chat(library, Question(message='What does my report say?'), lambda stage, count=None: stages.append((stage, count)))
    assert stages == [('preparing', None), ('searching', None), ('reading', 1), ('answering', None), ('reviewing', None)]
    assert result['sources'][0]['file_id'] == file['id']


@pytest.mark.parametrize('failed', [False, True])
def test_stream_returns_stage_receipts_and_only_final_result_or_error(tmp_path, monkeypatch, failed):
    def respond(library, body, progress):
        progress('searching')
        progress('reading', 2)
        progress('reviewing')
        if failed:
            raise ProcessingError('Provider unavailable; retry later.')
        return dict(message='Reviewed answer')

    monkeypatch.setattr('backend.api.chat', respond)
    with TestClient(create_app(tmp_path / 'http.sqlite3')) as client:
        response = client.post('/api/chat', headers={'Accept': 'application/x-ndjson'}, json={'message': 'Hello'})
    assert response.status_code == 200
    assert response.headers['x-accel-buffering'] == 'no'
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event['stage'] for event in events[:-1]] == ['searching', 'reading', 'reviewing']
    assert all('result' not in event and 'message' not in event for event in events[:-1])
    assert events[-1] == (dict(type='error', detail='Provider unavailable; retry later.') if failed
                          else dict(type='result', result={'message': 'Reviewed answer'}))
