# View: backend/library-storage.svg#S11
# Check archive/document API compatibility and ownership moves without rewriting original bytes.
"""Exercise archive contracts through HTTP without contacting an AI provider."""

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.test_storage import add, ready


def test_archive_http_ownership_move_delete_and_filters(tmp_path):
    app = create_app(tmp_path / "records.sqlite3")
    with TestClient(app) as client:
        patient = client.post("/api/profiles", json=dict(name="Patient", aliases=[])).json()
        archive = client.post("/api/records", json=dict(title="Confirmed visit", patient_id=patient["id"]))
        assert archive.status_code == 201
        target = archive.json()
        assert target["abstract"]["status"] == "partial"
        library = app.state.library
        one = ready(library, add(library, "one"), patient)
        old_archive = one["record_id"]
        two = ready(library, add(library, "two", target["id"]), patient)
        moved = client.put(f'/api/files/{one["id"]}/record', json=dict(record_id=target["id"], revision=one["revision"]))
        assert moved.status_code == 200
        assert moved.json()["archive"]["document_count"] == 2
        assert moved.json()["archive"]["index_state"] == "current"
        assert client.get(f"/api/records/{old_archive}").status_code == 404
        assert client.get(f'/api/files/{one["id"]}/original').content == b"source-one"
        records = client.get("/api/records", params=dict(patient_id=patient["id"], department_code="ophth000")).json()
        assert [row["id"] for row in records] == [target["id"]]
        assert client.get("/api/records", params=dict(department_code="pedim000")).json() == []
        detail = client.get(f'/api/records/{target["id"]}').json()
        assert {row["id"] for row in detail["documents"]} == {one["id"], two["id"]}
        assert detail["abstract"]["status"] == "current"
        stale = client.put(f'/api/files/{one["id"]}/record', json=dict(record_id=target["id"], revision=one["revision"]))
        assert stale.status_code == 409
        assert client.delete(f'/api/files/{one["id"]}').status_code == 204
        remaining = client.get(f'/api/records/{target["id"]}').json()
        assert [doc["id"] for doc in remaining["documents"]] == [two["id"]]
        assert remaining["abstract"]["based_on_revision"] == remaining["revision"]
        assert client.get(f'/api/files/{two["id"]}/original').content == b"source-two"
        assert client.get("/api/departments").status_code == 200


def test_explicit_attachment_uses_existing_archive(tmp_path, monkeypatch):
    app = create_app(tmp_path / "attachment.sqlite3")
    with TestClient(app) as client:
        # Keep work pending: this test checks intake ownership, not AI extraction.
        monkeypatch.setattr(app.state.executor, "submit", lambda *_args: None)
        archive = client.post("/api/records", json=dict(title="Visit")).json()
        headers = {"Idempotency-Key": "text"}
        body = dict(title="Note", text="Document text", record_id=archive["id"])
        text = client.post("/api/texts", json=body, headers=headers)
        assert text.status_code == 202
        assert text.json()["record_id"] == archive["id"]
        assert client.post("/api/texts", json=body, headers=headers).json()["id"] == text.json()["id"]
        headers["Idempotency-Key"] = "upload"
        upload = client.post("/api/imports", files={"file": ("report.txt", b"report", "text/plain")},
                             data={"record_id": archive["id"]}, headers=headers)
        assert upload.status_code == 202
        assert upload.json()["record_id"] == archive["id"]
        assert upload.json()["original_filename"] == "report.txt"
        assert client.get(f'/api/records/{archive["id"]}').json()["document_count"] == 2
        assert len(client.get("/api/records").json()) == 1
