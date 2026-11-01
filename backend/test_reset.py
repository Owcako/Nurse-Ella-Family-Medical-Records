"""Shared demo reset deletes owned evidence atomically, without external AI calls."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import processing
from backend.api import create_app
from backend.filing import FilingWorkflow
from backend.storage import Library
from backend.test_storage import add, ready


# View: backend/library-storage.svg#S12
# Exercise cascades across the actual schema, not just the visible file list.
def test_reset_requires_confirmation_and_clears_all_owned_data(tmp_path):
    with TestClient(create_app(tmp_path / 'reset.sqlite3')) as client:
        library = client.app.state.library
        patient = library.save_profile(dict(name='Demo person', aliases=['Demo alias']))
        document = ready(library, add(library, 'one'), patient)
        add(library, 'pending', document['record_id'])
        library.index_pending()
        for body in ({}, {'confirm': False}):
            assert client.post('/api/library/reset', json=body).status_code == 422
            assert len(library.list()) == 2
        assert client.post('/api/library/reset', json={'confirm': True}).status_code == 204
        assert client.get('/api/files').json() == []
        assert client.get('/api/profiles').json() == []
        assert client.get('/api/records').json() == []
        assert client.get(f"/api/files/{document['id']}/original").status_code == 404
        with library.connect() as db:
            for table in ('patients', 'medical_records', 'documents', 'document_sources', 'document_texts',
                          'document_processing', 'document_metadata', 'document_indexes',
                          'record_abstracts', 'index_jobs', 'record_departments', 'record_diseases'):
                assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM departments').fetchone()[0] > 0
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        # Empty resets are safe; the retained catalog supports a fresh demo afterward.
        assert client.post('/api/library/reset', json={'confirm': True}).status_code == 204
        fresh = add(library, 'one')
        assert fresh['id'] != document['id']


def test_failed_reset_rolls_back_documents_and_profiles(tmp_path):
    library = Library(tmp_path / 'rollback.sqlite3')
    patient = library.save_profile(dict(name='Demo person', aliases=[]))
    document = ready(library, add(library, 'one'), patient)
    with library.connect() as db:
        db.execute("CREATE TRIGGER block_reset BEFORE DELETE ON patients BEGIN SELECT RAISE(ABORT, 'Test storage failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        library.reset()
    assert len(library.list()) == 1
    assert library.source(document['id']) == b'source-one'
    assert library.profiles()[0]['id'] == patient['id']


def test_reset_during_processing_prevents_late_result_resurrection(tmp_path, monkeypatch):
    library = Library(tmp_path / 'worker.sqlite3')
    document = add(library, 'one')
    monkeypatch.setattr(processing, 'check', lambda text: library.reset() or [])
    monkeypatch.setattr(processing, 'classify', lambda *args: pytest.fail('Deleted work must not continue filing'))
    FilingWorkflow(library).run(document['id'])
    assert library.list() == []
    with library.connect() as db:
        assert db.execute('SELECT count(*) FROM index_jobs').fetchone()[0] == 0
