# View: src/import/ui-flow.svg#U12
# Exercise human corrections and rechecks, including a source changing while AI works.
# The expected conflict protects new text from an old check result.
"""Saved correction and explicit checking contracts, without external AI calls."""

import pytest
from fastapi.testclient import TestClient

from backend import processing
from backend.api import create_app
from backend.test_storage import add, ready


@pytest.fixture
def viewer(tmp_path):
    app = create_app(tmp_path / 'viewer.sqlite3')
    with TestClient(app) as client:
        library = app.state.library
        file = ready(library, add(library, 'viewer'))
        file = library.change(file['id'], lambda row: row.update(
            concerns=[dict(quote='saved', reason='Review this wording', start=0, end=5)]))
        headers = {}
        yield client, library, file, headers


def test_open_never_checks_and_metadata_save_preserves_results(viewer, monkeypatch):
    client, library, file, _ = viewer
    monkeypatch.setattr(processing, 'check', lambda _: pytest.fail('Opening/saving must not check'))
    assert client.get(f"/api/files/{file['id']}").status_code == 200
    result = client.put(f"/api/files/{file['id']}/manual", json=dict(
        revision=file['revision'], text=file['text'], member_name='', date='2025', department=['眼科'], disease=['documented diagnosis']))
    assert result.status_code == 200
    saved = result.json()
    assert saved['check_status'] == 'checked'
    assert saved['concerns'] == file['concerns']
    assert saved['metadata']['date']['provenance'] == 'user_supplied'
    assert saved['initial_text'] == 'initial text'
    assert library.source(file['id']) == b'source-viewer'


def test_recheck_current_saved_text_then_failed_recheck_retains_stale_result(viewer, monkeypatch):
    client, library, file, headers = viewer
    saved = client.put(f"/api/files/{file['id']}/manual", json=dict(
        revision=file['revision'], text='Corrected text', date='2026', department=['眼科'])).json()
    assert saved['check_status'] == 'stale'
    assert saved['concerns'] == file['concerns']
    assert saved['checked_text_revision'] < saved['text_revision']

    def fail(text):
        assert text == 'Corrected text'
        raise processing.ProcessingError('Service unavailable')

    monkeypatch.setattr(processing, 'check', fail)
    failed = client.post(f"/api/files/{file['id']}/recheck", headers=headers, json=dict(revision=saved['revision'])).json()
    assert failed['check_status'] == 'failed'
    assert failed['check_error'] == 'Service unavailable'
    assert failed['concerns'] == file['concerns']
    assert failed['checked_text_revision'] == file['checked_text_revision']
    monkeypatch.setattr(processing, 'check', lambda text: [] if text == 'Corrected text' else pytest.fail('Wrong text'))
    checked = client.post(f"/api/files/{file['id']}/recheck", headers=headers, json=dict(revision=failed['revision'])).json()
    assert checked['check_status'] == 'checked'
    assert checked['check_error'] is None and checked['concerns'] == []
    assert checked['checked_text_revision'] == checked['text_revision']
    assert checked['metadata'] == saved['metadata']
    assert checked['initial_text'] == 'initial text'
    assert library.source(file['id']) == b'source-viewer'
    assert library.record(file['record_id'])['index_state'] == 'current'


@pytest.mark.parametrize('change', ['edit', 'delete'])
def test_concurrent_write_invalidates_recheck(viewer, monkeypatch, change):
    client, library, file, headers = viewer

    def check(_text):
        if change == 'delete':
            library.delete(file['id'])
        else:
            library.change(file['id'], lambda row: row.update(text='Newer correction', check_status='stale'))
        return []

    monkeypatch.setattr(processing, 'check', check)
    response = client.post(f"/api/files/{file['id']}/recheck", headers=headers, json=dict(revision=file['revision']))
    assert response.status_code == (404 if change == 'delete' else 409)
    if change == 'edit':
        assert library.get(file['id'])['check_status'] == 'stale'
        assert library.get(file['id'])['concerns'] == file['concerns']


def test_recheck_validates_revision_and_missing_text(viewer, monkeypatch):
    client, library, file, headers = viewer
    monkeypatch.setattr(processing, 'check', lambda _: pytest.fail('Invalid request must not check'))
    url = f"/api/files/{file['id']}/recheck"
    assert client.post(url, headers=headers, json=dict(revision=file['revision'] - 1)).status_code == 409
    empty = library.change(file['id'], lambda row: row.update(text=None))
    assert client.post(url, headers=headers, json=dict(revision=empty['revision'])).status_code == 400


def test_text_only_correction_keeps_unresolved_candidates(viewer):
    client, library, file, _ = viewer
    def ambiguous(row):
        row['metadata']['date'] = dict(status='ambiguous', values=[], candidates=[dict(value='2026', quote='2026?')], provenance='documented')
    file = library.change(file['id'], ambiguous)
    saved = client.put(f"/api/files/{file['id']}/manual", json=dict(
        revision=file['revision'], text='Correction', department=['眼科'], disease=['documented diagnosis'])).json()
    assert saved['metadata']['date'] == file['metadata']['date']
