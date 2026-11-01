from fastapi.testclient import TestClient

from backend import demo_samples
from backend.api import create_app
from backend.filing import FilingWorkflow


def test_fixed_samples_import_originals_and_use_live_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_samples, 'DIRECTORY', tmp_path)
    scheduled = []
    monkeypatch.setattr(FilingWorkflow, 'run', lambda self, file_id: scheduled.append(file_id))
    contents = {name: b'%PDF-test-' + key.encode() if media == 'application/pdf' else b'\xff\xd8\xfftest-image'
                for key, (name, media) in demo_samples.SAMPLES.items()}
    for name, content in contents.items():
        (tmp_path / name).write_bytes(content)
    app = create_app(tmp_path / 'library.sqlite3')
    with TestClient(app) as client:
        choices = client.get('/api/demo/samples').json()
        assert len(choices) == 3
        assert all(choice['available'] for choice in choices)
        for choice in choices:
            url = f"/api/demo/samples/{choice['id']}/import"
            headers = {'Idempotency-Key': f"sample:{choice['id']}"}
            response = client.post(url, headers=headers)
            assert response.status_code == 202
            file = response.json()
            assert file['text'] is None and file['metadata'] is None
            assert file['status'] == 'pending'
            assert file['text_origin'] != 'demo_prepared'
            assert app.state.library.source(file['id']) == contents[choice['filename']]
            assert client.post(url, headers=headers).json()['id'] == file['id']
        assert len(app.state.library.list()) == 3
    assert scheduled


def test_missing_unknown_and_invalid_sample_never_import(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_samples, 'DIRECTORY', tmp_path)
    with TestClient(create_app(tmp_path / 'library.sqlite3')) as client:
        assert not any(item['available'] for item in client.get('/api/demo/samples').json())
        headers = {'Idempotency-Key': 'sample:test'}
        assert client.post('/api/demo/samples/pdf-1/import', headers=headers).status_code == 404
        assert client.post('/api/demo/samples/environment/import', headers=headers).status_code == 404
        (tmp_path / demo_samples.SAMPLES['pdf-1'][0]).write_bytes(b'wrong file type')
        assert client.post('/api/demo/samples/pdf-1/import', headers=headers).status_code == 415
        assert client.app.state.library.list() == []
