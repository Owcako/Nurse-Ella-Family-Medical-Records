"""The demo kit supplies original PDFs; the ordinary workflow still processes them."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend import demo
from backend.api import create_app
from backend.filing import FilingWorkflow
from backend.storage import Library
from backend.test_storage import add


def test_demo_catalog_has_questions_without_expected_answers():
    catalog = demo.catalog()
    assert catalog["file_count"] == 13
    assert len(catalog["questions"]) == 20
    assert all(set(question) == {"id", "group", "question"} for question in catalog["questions"])
    assert any(item["question"] == "What is his blood type?" for item in catalog["questions"])


def test_demo_api_preserves_normal_records_replays_sources_and_restores_kit(tmp_path, monkeypatch):
    scheduled = []
    monkeypatch.setattr(FilingWorkflow, "run", lambda self, file_id: scheduled.append(file_id))
    with TestClient(create_app(tmp_path / "demo.sqlite3")) as client:
        library = client.app.state.library
        old = add(library, "old")
        response = client.post("/api/demo/import")
        assert response.status_code == 202
        documents = response.json()
        assert len(documents) == 13
        ids = {document["id"] for document in documents}
        assert len(library.list()) == 14
        assert {profile["name"] for profile in library.profiles()} == {"John Smith", "Mary Smith"}
        for document in documents:
            assert document["status"] == "pending"
            assert document["text"] is None
            assert document["metadata"] is None
            assert library.source(document["id"]) == (demo.KIT / document["original_filename"]).read_bytes()
        assert {item["id"] for item in client.post("/api/demo/import").json()} == ids
        assert len(library.list()) == 14
        assert client.post("/api/demo/reset", json={"confirm": False}).status_code == 422
        assert client.post("/api/demo/reset", json={}).status_code == 422
        assert len(library.list()) == 14
        restored = client.post("/api/demo/reset", json={"confirm": True})
        assert restored.status_code == 202
        new_ids = {item["id"] for item in restored.json()}
        assert len(new_ids) == 13
        assert not ids.intersection(new_ids)
        assert len(library.list()) == 13
        assert client.get(f"/api/files/{old['id']}").status_code == 404
        assert {item["id"] for item in client.post("/api/demo/import").json()} == new_ids
    assert ids.issubset(scheduled)
    assert new_ids.issubset(scheduled)


def test_demo_restore_rolls_back_if_a_kit_insert_fails(tmp_path):
    library = Library(tmp_path / "rollback.sqlite3")
    old = add(library, "old")
    profiles, sources = demo.sources()
    with library.connect() as db:
        db.execute("CREATE TRIGGER block_demo BEFORE INSERT ON documents BEGIN SELECT RAISE(ABORT, 'Test demo failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        library.import_demo(profiles, sources, reset=True)
    assert [file["id"] for file in library.list()] == [old["id"]]
    assert library.source(old["id"]) == b"source-old"
    assert library.profiles() == []


def test_concurrent_demo_imports_share_the_same_document_ids(tmp_path):
    library = Library(tmp_path / "concurrent.sqlite3")
    profiles, sources = demo.sources()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: library.import_demo(profiles, sources), range(2)))
    assert {file["id"] for file in results[0]} == {file["id"] for file in results[1]}
    assert len(library.list()) == 13
    assert len(library.profiles()) == 2


def test_demo_reuses_a_surname_first_profile_without_overwriting_it(tmp_path):
    library = Library(tmp_path / "existing.sqlite3")
    original = library.save_profile(dict(name="SMITH, JOHN", aliases=[]))
    profiles, sources = demo.sources()
    library.import_demo(profiles, sources)
    john = next(profile for profile in library.profiles() if profile["id"] == original["id"])
    assert john["name"] == "SMITH, JOHN"
    assert john["aliases"] == []
    assert len(library.profiles()) == 2
