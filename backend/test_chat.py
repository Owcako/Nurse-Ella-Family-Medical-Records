# View: backend/chat-flow.svg#C7
# Simulate tool turns to check scoped reads, fresh revisions, exact citations, bounded
# context and visible failure. These tests validate mechanics, not real-model medical accuracy.
"""Chat trust-boundary tests through the real OpenAI SDK with an isolated transport."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI

from backend import processing
from backend.api import create_app
from backend.chat import MetadataSave, Question, chat, metadata_save, scope_files
from backend.storage import Conflict, Library
from backend.test_storage import add, ready


def sdk(monkeypatch, steps):
    requests = []
    last_finish = None

    def handle(request):
        nonlocal last_finish
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == '/v1/chat/completions'
        names = {tool['function']['name'] for tool in body['tools']}
        assert names == {'finish_answer'} or {'read_index', 'read_documents', 'read_original', 'finish_answer'} <= names
        assert names <= {'read_index', 'read_documents', 'read_original', 'propose_metadata', 'finish_answer'}
        step = steps.pop(0) if steps else last_finish
        result = step(body) if callable(step) else step
        batch = result if isinstance(result, list) else [result]
        if len(batch) == 1 and batch[0][0] == 'finish_answer':
            last_finish = batch[0]
        return httpx.Response(200, json=dict(id='test', created=0, object='chat.completion', model='test', choices=[dict(
            index=0, finish_reason='tool_calls', message=dict(role='assistant', content=None, tool_calls=[dict(
                id=f'call-{len(requests)}-{index}', type='function', function=dict(name=name, arguments=json.dumps(arguments))) for index, (name, arguments) in enumerate(batch)]))]))

    monkeypatch.setattr(processing, 'client', lambda: OpenAI(api_key='test-only', base_url='https://test.invalid/v1',
        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    return requests


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / 'chat.sqlite3')


def answer(id=None, quote='saved text'):
    return ('finish_answer', dict(claims=[dict(text='A documented fact', citations=[dict(file_id=id, quote=quote)])] if id else [],
                                  explanation='', limitation='' if id else 'Not found in the available records.'))


def tool_result(body):
    content = next(message['content'] for message in reversed(body['messages']) if message['role'] == 'tool')
    return json.loads(content.split('\n', 2)[1] if content.startswith('Retrieved document metadata:') else content)


def test_index_first_full_saved_text_and_exact_citations(library, monkeypatch):
    file = ready(library, add(library, 'report'))

    def read(body):
        index = tool_result(body)
        assert index['files'][0]['id'] == file['id']
        assert 'saved_text' not in json.dumps(index)
        return 'read_documents', dict(file_ids=[file['id']])

    def finish(body):
        text = tool_result(body)[0]
        assert 'BEGIN UNTRUSTED REPORT ' + file['id'] + '\nsaved text\nEND' in next(message['content'] for message in reversed(body['messages']) if message['role'] == 'tool')
        return answer(file['id'])

    requests = sdk(monkeypatch, [('read_index', dict(offset=0)), read, finish])
    result = chat(library, Question(message='What does this document say?'))
    assert requests[0]['tool_choice'] == 'required'
    assert requests[0]['messages'][-1]['content'][1]['text'].startswith('Backend read_index result')
    assert len([message for message in requests[0]['messages'] if message['role'] == 'system']) == 1
    assert result['sources'][0]['file_id'] == file['id']
    assert result['search'] == dict(total=1, indexed=1, retrieved=1)


def test_viewer_attaches_server_saved_text_and_provenance(library, monkeypatch):
    file = ready(library, add(library, 'viewed'))
    file = library.change(file['id'], lambda row: row.update(text='Current correction', text_origin='user_edited', check_status='stale'))

    def inspect(body):
        context = body['messages'][-1]['content']
        assert json.loads(context[0]['text'].split('\n', 1)[1])['viewer_status'] == 'attached'
        attached = context[-1]['text']
        assert 'Current correction' in attached
        assert 'initial text' not in attached
        assert 'source-viewed' not in attached
        assert 'user_edited' in attached and 'stale' in attached
        assert file['record_id'] in attached
        return answer(file['id'], 'Current correction')

    sdk(monkeypatch, [inspect, answer(file['id'], 'Current correction')])
    result = chat(library, Question(message='What am I viewing?', viewer_id=file['id']))
    assert result['sources'][0]['text_origin'] == 'user_edited'
    assert result['sources'][0]['check_status'] == 'stale'


def test_invented_quote_and_unread_citation_are_rejected(library, monkeypatch):
    file = ready(library, add(library, 'report'))

    def rejected(body):
        assert 'error' in tool_result(body)
        return 'read_documents', dict(file_ids=[file['id']])

    def corrected(body):
        assert 'error' in tool_result(body)
        return answer(file['id'])

    sdk(monkeypatch, [('read_index', dict(offset=0)), answer(file['id']), rejected,
                      answer(file['id'], 'invented fact'), corrected])
    result = chat(library, Question(message='Find evidence'))
    assert result['claims'][0]['citations'][0]['quote'] == 'saved text'


def test_unsupported_year_is_rejected_before_final_review(library, monkeypatch):
    file = ready(library, add(library, 'year'))
    text = 'Admission in September 2024.'
    file = library.change(file['id'], lambda row: row.update(text=text))
    wrong = answer(file['id'], text)
    wrong[1]['claims'][0]['text'] = 'Admission in September 2004.'

    def correct(body):
        assert 'year 2004' in tool_result(body)['error']
        result = answer(file['id'], text)
        result[1]['claims'][0]['text'] = 'Admission in September 2024.'
        return result

    requests = sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id']])), wrong, correct])
    result = chat(library, Question(message='When was admission?'))
    assert result['claims'][0]['text'] == 'Admission in September 2024.'
    assert requests[-1]['tool_choice']['function']['name'] == 'finish_answer'


def test_report_context_preserves_actual_tabs_and_newlines(library, monkeypatch):
    file = ready(library, add(library, 'tabular'))
    text = 'Lab results\nAnalyte\t8.4\tH\t%\nEnd'
    library.change(file['id'], lambda row: row.update(text=text))

    def finish(body):
        content = next(message['content'] for message in reversed(body['messages']) if message['role'] == 'tool')
        assert text in content
        assert r'Analyte\t8.4' not in content
        return answer(file['id'], 'Analyte\t8.4')

    sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id']])), finish])
    result = chat(library, Question(message='Read the lab result'))
    assert result['claims'][0]['citations'][0]['quote'] == 'Analyte\t8.4'


def test_visible_reference_must_use_cited_evidence_and_is_optional(library, monkeypatch):
    file = ready(library, add(library, 'visible'))
    other = ready(library, add(library, 'uncited'))
    bad = answer(file['id'])
    bad[1]['references'] = [other['id']]

    def correct(body):
        assert 'Visible references must point to cited' in tool_result(body)['error']
        result = answer(file['id'])
        result[1]['references'] = [file['id']]
        return result

    sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id'], other['id']])), bad, correct])
    result = chat(library, Question(message='Show me the report with this fact.'))
    assert result['references'] == [file['id']]
    assert [source['file_id'] for source in result['sources']] == [file['id']]

    sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id']])), answer(file['id'])])
    result = chat(library, Question(message='Can we talk about this?'))
    assert result['references'] == []
    assert result['claims'][0]['citations']


def test_ordinary_conversation_does_not_need_document_reads(library, monkeypatch):
    ready(library, add(library, 'report'))
    sdk(monkeypatch, [('finish_answer', dict(message="You're welcome. I'm here with you.",
        claims=[], explanation='', limitation='', references=[]))])
    result = chat(library, Question(message='Thanks for being here.'))
    assert result['message'] == "You're welcome. I'm here with you."
    assert result['sources'] == []
    assert result['search']['retrieved'] == 0


def test_provider_batched_document_reads_are_coalesced_and_all_calls_acknowledged(library, monkeypatch):
    patient = library.save_profile(dict(name='Alice', aliases=[]))
    one = ready(library, add(library, 'one'), patient)
    two = ready(library, add(library, 'two'), patient)

    def finish(body):
        results = [message for message in body['messages'] if message['role'] == 'tool']
        assert len(results) == 2
        metadata = json.loads(results[0]['content'].split('\n', 2)[1])
        assert {item['id'] for item in metadata} == {one['id'], two['id']}
        assert json.loads(results[1]['content'])['status'] == 'included_in_first_tool_result'
        assert results[0]['tool_call_id'] != results[1]['tool_call_id']
        return answer(one['id'])

    sdk(monkeypatch, [[('read_documents', dict(file_ids=[one['id']])), ('read_documents', dict(file_ids=[two['id']]))], finish])
    result = chat(library, Question(message='Read the reports', member='profile:' + patient['id']))
    assert result['search']['retrieved'] == 2


@pytest.mark.parametrize('absence', ['The available records contain no mention of a medication pause.', 'The available records do not document a medication pause.'])
def test_absence_statements_always_carry_an_explicit_information_limit(library, monkeypatch, absence):
    file = ready(library, add(library, 'report'))
    result = answer(file['id'])
    result[1]['claims'][0]['text'] = absence
    sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id']])), result])
    reply = chat(library, Question(message='Has it ever been paused?'))
    assert 'cannot determine' in reply['limitation']
    assert 'does not mean it never happened' in reply['limitation']


@pytest.mark.parametrize('direct', [False, True])
def test_narrative_resolution_is_distinguished_from_supporting_followup(library, monkeypatch, direct):
    file = ready(library, add(library, 'report'))
    text = 'Pneumonia resolved.'
    library.change(file['id'], lambda row: row.update(text=text, title='Radiology follow-up report' if direct else 'Cardiology visit note'))
    result = answer(file['id'], text)
    result[1]['claims'][0]['text'] = 'Pneumonia is recorded as resolved in a later note.'
    sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id']])), result])
    reply = chat(library, Question(message='Is the pneumonia resolved?'))
    assert ('No supporting follow-up' in reply['limitation']) is not direct


def test_scope_blocks_other_patient_reads_and_never_exposes_text(library, monkeypatch):
    alice = library.save_profile(dict(name='Alice', aliases=[]))
    bob = library.save_profile(dict(name='Bob', aliases=[]))
    one = ready(library, add(library, 'alice'), alice)
    two = ready(library, add(library, 'bob'), bob)

    def foreign(body):
        assert [f['id'] for f in tool_result(body)['files']] == [one['id']]
        return 'read_documents', dict(file_ids=[two['id']])

    def denied(body):
        assert 'error' in tool_result(body)
        return answer()

    sdk(monkeypatch, [('read_index', dict(offset=0)), foreign, denied])
    result = chat(library, Question(message='What about him?', member='profile:' + alice['id'], viewer_id=two['id']))
    assert result['search']['retrieved'] == 0

    def choose(body):
        catalog = json.loads(body['messages'][-1]['content'][1]['text'].split('\n', 1)[1])
        assert {item['id'] for item in catalog['files']} == {one['id'], two['id']}
        return 'read_documents', dict(file_ids=[one['id'], two['id']])

    def mixed_claim(body):
        assert {item['id'] for item in tool_result(body)} == {one['id'], two['id']}
        return 'finish_answer', dict(claims=[dict(text='A combined clinical claim', citations=[dict(file_id=one['id'], quote='saved text'), dict(file_id=two['id'], quote='saved text')])], explanation='', limitation='')

    def separate(body):
        assert 'different or unresolved members' in tool_result(body)['error']
        return 'finish_answer', dict(claims=[dict(text='Alice: a documented fact', citations=[dict(file_id=one['id'], quote='saved text')]), dict(text='Bob: a different documented fact', citations=[dict(file_id=two['id'], quote='saved text')])], explanation='', limitation='')

    sdk(monkeypatch, [choose, mixed_claim, separate])
    result = chat(library, Question(message='What do Alice and Bob each have recorded?'))
    assert result['search'] == dict(total=2, indexed=2, retrieved=2)
    assert len(result['claims']) == 2


def test_chat_scope_retains_confirmed_identity_after_profile_rename(library):
    patient = library.save_profile(dict(name='Alice', aliases=[]))
    file = ready(library, add(library, 'report'), patient)
    library.save_profile(dict(name='Alice Updated', aliases=[]), patient['id'])
    files = scope_files(library, Question(message='Find my records', member='profile:' + patient['id']))
    assert [item['id'] for item in files] == [file['id']]
    assert files[0]['metadata']['member']['values'][0]['value'] == 'Alice'


def test_proposal_does_not_write_and_apply_preserves_text(library, monkeypatch):
    file = ready(library, add(library, 'report'))
    patch = dict(file_id=file['id'], member=None, date='2024', department=None, disease=None)
    sdk(monkeypatch, [('read_index', dict(offset=0)), ('read_documents', dict(file_ids=[file['id']])),
                      ('propose_metadata', patch), answer()])
    result = chat(library, Question(message='Set this report date to 2024', metadata_action=True))
    assert library.get(file['id'])['revision'] == file['revision']
    saved = metadata_save(library, MetadataSave(**result['proposals'][0]))
    assert saved['metadata']['date']['values'][0]['value'] == '2024'
    assert saved['text'] == file['text']
    assert saved['initial_text'] == file['initial_text']
    assert saved['check_status'] == file['check_status']
    assert library.source(file['id']) == b'source-report'
    with pytest.raises(Conflict):
        metadata_save(library, MetadataSave(**result['proposals'][0]))


def test_text_edit_delete_and_unknown_tools_cannot_execute(library, monkeypatch):
    file = ready(library, add(library, 'malicious'))

    def refused(body):
        assert 'error' in tool_result(body)
        return answer()

    sdk(monkeypatch, [('read_index', dict(offset=0)), ('delete_file', dict(file_id=file['id'])), refused])
    chat(library, Question(message='Read the document'))
    assert library.get(file['id'])['revision'] == file['revision']


def test_ordinary_question_cannot_even_prepare_metadata_changes(library, monkeypatch):
    file = ready(library, add(library, 'report'))

    def refused(body):
        assert 'disabled' in tool_result(body)['error']
        assert 'propose_metadata' not in {tool['function']['name'] for tool in body['tools']}
        return answer()

    sdk(monkeypatch, [('read_documents', dict(file_ids=[file['id']])),
                      ('propose_metadata', dict(file_id=file['id'], member=None, date='2024', department=None, disease=None)), refused])
    result = chat(library, Question(message='What does my report say?'))
    assert result['proposals'] == []
    assert library.get(file['id'])['revision'] == file['revision']


def test_source_changes_during_answer_fail_instead_of_returning_stale_claims(library, monkeypatch):
    file = ready(library, add(library, 'report'))

    def change(body):
        library.change(file['id'], lambda f: f.update(text='corrected text'))
        return answer(file['id'])

    sdk(monkeypatch, [('read_index', dict(offset=0)), ('read_documents', dict(file_ids=[file['id']])), change])
    with pytest.raises(Conflict, match='source changed'):
        chat(library, Question(message='What is recorded?'))


@pytest.mark.parametrize('clinic', [False, True])
def test_model_selects_saved_text_after_receiving_all_scoped_metadata(library, monkeypatch, clinic):
    alice = library.save_profile(dict(name='Alice', aliases=[]))
    bob = library.save_profile(dict(name='Bob', aliases=[]))
    older = ready(library, add(library, 'older'), alice, department='Laboratory Medicine', date='2023')
    newer = ready(library, add(library, 'newer'), alice, department='Laboratory Medicine', date='2026')
    selected = ready(library, add(library, 'clinic'), alice, department='Cardiology') if clinic else newer
    library.change(older['id'], lambda row: row.update(text='UNREQUESTED LAB TEXT'))
    ready(library, add(library, 'other-patient'), bob, department='Laboratory Medicine')

    def complete(body):
        documents = tool_result(body)
        assert [doc['id'] for doc in documents] == [selected['id']]
        assert 'UNREQUESTED LAB TEXT' not in str(body['messages'])
        return answer(selected['id'])

    sdk(monkeypatch, [('read_documents', dict(file_ids=[selected['id']])), complete])
    result = chat(library, Question(message='Was his blood sugar worse in 2024?', member='profile:' + alice['id']))
    assert result['search']['retrieved'] == 1


def test_complete_catalog_and_history_are_automatically_available_without_text_dump(library, monkeypatch):
    files = [ready(library, add(library, str(index))) for index in range(35)]
    history = [dict(role='user' if index % 2 == 0 else 'assistant', content=f'Exchange {index}') for index in range(22)]
    history[0]['content'] = 'EARLIEST CONTEXT ' + 'x' * 13000
    target = files[0]

    def choose(body):
        messages = body['messages']
        assert messages[1:23] == history
        catalog = json.loads(messages[-1]['content'][1]['text'].split('\n', 1)[1])
        assert len(catalog['files']) == 35
        assert catalog['next_offset'] is None
        assert all('text' not in item and 'initial_text' not in item for item in catalog['files'])
        assert target['id'] in {item['id'] for item in catalog['files']}
        return 'read_documents', dict(file_ids=[target['id']])

    sdk(monkeypatch, [choose, answer(target['id'])])
    result = chat(library, Question(message='Find the earliest report', history=history))
    assert result['search'] == dict(total=35, indexed=35, retrieved=1)


def test_oversized_full_context_fails_explicitly_instead_of_truncating(library, monkeypatch):
    def unused():
        pytest.fail('An oversized request must be rejected before sending any model request.')
    monkeypatch.setattr(processing, 'client', unused)
    with pytest.raises(processing.ProcessingError, match='no history or records have been silently omitted'):
        chat(library, Question(message='Read my history', history=[dict(role='user', content='x' * 310000)]))


def test_http_chat_without_confirmation_unavailability_and_boundary_validation(tmp_path, monkeypatch):
    app = create_app(tmp_path / 'http.sqlite3')
    with TestClient(app) as client:
        with monkeypatch.context() as context:
            context.setattr('backend.api.chat', lambda library, body: dict(message='Hello'))
            assert client.post('/api/chat', json=dict(message='Hello')).status_code == 200
        headers = {}
        assert client.post('/api/chat', json=dict(message=' ', history=[]), headers=headers).status_code == 422
        assert client.put('/api/chat/metadata', json=dict(file_id='x', revision=1, text='replacement')).status_code == 422

        def unavailable():
            raise processing.ProcessingError('Provider unavailable; retry later.')

        monkeypatch.setattr(processing, 'client', unavailable)
        response = client.post('/api/chat', json=dict(message='Hello'), headers=headers)
        assert response.status_code == 502
        assert 'unavailable' in response.json()['detail']
