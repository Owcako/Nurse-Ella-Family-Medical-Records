# View: src/library/browsing-flow.svg#R5
# Verify exact member/alias matching, collision rejection and evidence-preserving profile removal.
"""Member identity lifecycle through the real SQLite and HTTP contracts."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.storage import Conflict, Library
from backend.test_storage import add, ready


def named_document(library, name, key="report"):
    document = ready(library, add(library, key))
    def apply(data):
        evidence = dict(value=name, quote="original patient name")
        data["metadata"]["member"] = dict(status="known", values=[evidence], candidates=[evidence], provenance="documented")
    return library.change(document["id"], apply)


def test_profile_creation_links_saved_names_and_aliases_without_changing_text(tmp_path):
    library = Library(tmp_path / "members.sqlite3")
    first = named_document(library, " Alice   Chen ", "first")
    second = named_document(library, "A. Chen", "second")
    unrelated = named_document(library, "Bob", "third")
    profile = library.save_profile(dict(name="Alice Chen", aliases=["A. Chen"]))
    library.index_pending()
    for before in (first, second):
        after = library.get(before["id"])
        assert after["metadata"]["member"]["values"][0]["profile_id"] == profile["id"]
        assert after["metadata"]["member"]["values"][0]["value"] == before["metadata"]["member"]["values"][0]["value"]
        assert after["archive"]["patient_name"] == "Alice Chen"
        assert after["initial_text"] == before["initial_text"]
        assert after["text"] == before["text"]
        assert library.source(after["id"]) == library.source(before["id"])
        assert after["index"]["classifications"]["member"] == after["metadata"]["member"]
    assert "profile_id" not in library.get(unrelated["id"])["metadata"]["member"]["values"][0]
    renamed = library.save_profile(dict(name="Alice renamed", aliases=[]), profile["id"])
    assert library.get(first["id"])["archive"]["patient_name"] == renamed["name"]
    assert len(library.list()) == 3


def test_existing_profile_matches_new_document_and_stale_ids_are_not_kept(tmp_path):
    library = Library(tmp_path / "members.sqlite3")
    profile = library.save_profile(dict(name="Alice", aliases=["A. Example"]))
    document = named_document(library, " a. EXAMPLE ")
    assert document["metadata"]["member"]["values"][0]["profile_id"] == profile["id"]
    revision = document["revision"]
    library.delete_profile(profile["id"])
    after = library.get(document["id"])
    assert after["revision"] > revision
    assert "profile_id" not in after["metadata"]["member"]["values"][0]
    assert library.record(after["record_id"])["patient_id"] is None
    assert library.source(document["id"]) == b"source-report"


def test_duplicate_names_and_aliases_are_rejected_transactionally(tmp_path):
    library = Library(tmp_path / "members.sqlite3")
    first = library.save_profile(dict(name="Alice Chen", aliases=["A. Chen"]))
    other = library.save_profile(dict(name="Bob", aliases=[]))
    with pytest.raises(Conflict):
        library.save_profile(dict(name=" alice   CHEN ", aliases=[]))
    with pytest.raises(Conflict):
        library.save_profile(dict(name="Bob", aliases=["a. chen"]), other["id"])
    assert library.profiles()[0]["name"] == first["name"]
    assert library.profiles()[1]["aliases"] == []


def test_startup_links_old_reports_and_ambiguous_identity_stays_unassigned(tmp_path):
    path = tmp_path / "members.sqlite3"
    library = Library(path)
    document = named_document(library, "Alice")
    ambiguous = named_document(library, "Alice", "ambiguous")
    library.change(ambiguous["id"], lambda data: data["metadata"]["member"].update(status="ambiguous", values=[]))
    with library.connect() as db:
        db.execute("INSERT INTO patients VALUES (?, ?, NULL, ?, ?)", ("old-profile", "Alice", "[]", "2026-10-27"))
    reopened = Library(path)
    assert reopened.get(document["id"])["metadata"]["member"]["values"][0]["profile_id"] == "old-profile"
    field = reopened.get(ambiguous["id"])["metadata"]["member"]
    assert field["status"] == "ambiguous"
    assert all("profile_id" not in value for value in field["candidates"])


def test_http_remove_keeps_reports_and_updates_retrieval(tmp_path):
    app = create_app(tmp_path / "members.sqlite3")
    with TestClient(app) as client:
        library = app.state.library
        document = named_document(library, "Alice")
        profile = client.post("/api/profiles", json=dict(name="Alice", aliases=[])).json()
        assert len(client.get("/api/records", params=dict(patient_id=profile["id"])).json()) == 1
        before = client.get(f'/api/files/{document["id"]}').json()
        assert client.post("/api/profiles", json=dict(name="alice", aliases=[])).status_code == 409
        assert client.delete(f'/api/profiles/{profile["id"]}').status_code == 204
        assert client.get("/api/profiles").json() == []
        after = client.get(f'/api/files/{document["id"]}').json()
        assert after["text"] == before["text"]
        assert after["initial_text"] == before["initial_text"]
        assert client.get(f'/api/files/{document["id"]}/original').content == b"source-report"
        assert client.get("/api/records", params=dict(patient_id=profile["id"])).json() == []
        with library.connect() as db:
            classifications = json.loads(db.execute("SELECT content_json FROM document_indexes WHERE document_id=?", (document["id"],)).fetchone()[0])
            assert "profile_id" not in classifications["classifications"]["member"]["values"][0]
        assert client.delete(f'/api/profiles/{profile["id"]}').status_code == 404
