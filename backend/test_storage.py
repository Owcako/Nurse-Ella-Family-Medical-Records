# View: backend/library-storage.svg#S5
# Temporary SQLite libraries verify atomic uploads, immutable evidence, revision guards,
# archive indexes and deletion boundaries. Tests never edit the demonstration library.
"""Hierarchy, migration and preservation tests; no AI service calls."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from backend.storage import Conflict, Library


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / "library.sqlite3")


def add(library, key, record_id=None):
    return library.create(operation=key, source=("source-" + key).encode(), title=key + ".txt",
                          media="text/plain", origin="imported", record_id=record_id)


def ready(library, document, patient=None, department="眼科", date="2026-10-26"):
    def field(value, **extra):
        values = [dict(value=value, quote="source", **extra)] if value else []
        return dict(status="known" if values else "missing", values=values, candidates=values, provenance="documented")
    metadata = dict(member=field(patient["name"], profile_id=patient["id"]) if patient else field(None),
                    date=field(date), department=field(department), disease=field("documented diagnosis"))
    return library.change(document["id"], lambda row: row.update(status="filed", stage="complete", text="saved text",
        initial_text="initial text", check_status="checked", metadata=metadata,
        index=dict(symptoms=[], history=[], diagnoses=[], treatments=[]), index_status="current"))


def test_schema_splits_authoritative_data_and_has_foreign_keys(library):
    document = add(library, "one")
    with library.connect() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"patients", "medical_records", "documents", "document_sources", "document_texts",
                "document_processing", "document_metadata", "document_indexes", "record_abstracts", "index_jobs"} <= tables
        assert "files" not in tables and "profiles" not in tables
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("SELECT content FROM document_sources WHERE document_id=?", (document["id"],)).fetchone()[0] == b"source-one"
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE document_sources SET content=? WHERE document_id=?", (b"changed", document["id"]))


def test_catalog_revision_invalidates_saved_archive_without_reextracting(library):
    from backend import departments
    document = ready(library, add(library, "catalog"))
    library.index_pending()
    before = library.record(document["record_id"])
    with library.connect() as db:
        db.execute("UPDATE document_metadata SET department_catalog_version='old'")
    reopened = Library(library.path)
    after = reopened.record(document["record_id"])
    assert after["revision"] > before["revision"]
    assert after["index_state"] == "pending"
    assert after["abstract"]["status"] == "stale"
    assert reopened.get(document["id"])["department_catalog_version"] == departments.VERSION
    assert reopened.source(document["id"]) == b"source-catalog"
    assert reopened.get(document["id"])["initial_text"] == "initial text"
    reopened.index_pending()
    assert reopened.record(document["record_id"])["index_state"] == "current"


def test_failed_index_keeps_stale_abstract_and_can_resume(library, monkeypatch):
    document = ready(library, add(library, "index"))
    library.index_pending()
    library.change(document["id"], lambda data: data.update(title="Corrected title"))
    read = library._read_document
    with monkeypatch.context() as patch:
        def fail(*_args):
            raise sqlite3.OperationalError("Injected index write failure")
        patch.setattr(library, "_read_document", fail)
        library.index_pending()
    archive = library.record(document["record_id"])
    assert archive["index_state"] == "failed"
    assert archive["index_error"]
    assert archive["abstract"]["status"] == "stale"
    assert library._read_document == read
    library.index_pending()
    archive = library.record(document["record_id"])
    assert archive["index_state"] == "current"
    assert archive["abstract"]["based_on_revision"] == archive["revision"]


def test_archive_owns_multiple_independent_documents(library):
    patient = library.save_profile(dict(name="Patient", aliases=[]))
    record = library.create_record("One confirmed visit", patient["id"])
    one = ready(library, add(library, "one", record["id"]), patient)
    two = ready(library, add(library, "two", record["id"]), patient)
    assert one["id"] != two["id"]
    assert one["record_id"] == two["record_id"] == record["id"]
    assert library.source(one["id"]) == b"source-one"
    assert library.source(two["id"]) == b"source-two"
    assert library.record(record["id"])["document_count"] == 2
    assert len(library.records(patient_id=patient["id"], department_code="ophth000")) == 1
    assert library.records(department_code="pedim000") == []
    assert len(library.records(disease="documented diagnosis")) == 1


def test_same_date_and_patient_never_auto_merge(library):
    patient = library.save_profile(dict(name="Patient", aliases=[]))
    one = ready(library, add(library, "one"), patient)
    two = ready(library, add(library, "two"), patient)
    assert one["record_id"] != two["record_id"]
    assert len(library.records(patient_id=patient["id"])) == 2


def test_catalog_codes_are_backend_derived(library):
    known = ready(library, add(library, "known"), department="小儿内科全科")
    assert known["metadata"]["department"]["values"][0]["department_code"] == "pedim000"
    assert known["archive"]["department_code"] == "pedim000"
    unknown = ready(library, add(library, "unknown"), department="屈光不正")
    assert unknown["metadata"]["department"]["values"][0]["department_code"] is None
    assert unknown["metadata"]["department"]["values"][0]["value"] == "屈光不正"
    assert unknown["archive"]["department_code"] == "unknown0"


def test_index_invalidation_revision_and_manual_text_refresh(library):
    document = ready(library, add(library, "one"))
    archive_id = document["record_id"]
    assert library.record(archive_id)["index_state"] == "pending"
    library.index_pending()
    indexed = library.record(archive_id)
    assert indexed["abstract"]["status"] == "current"
    assert indexed["indexed_revision"] == indexed["revision"]
    saved = library.change(document["id"], lambda row: row.update(text="user correction", text_origin="user_edited",
        check_status="stale", index={"saved_text": "user correction"}, index_status="current"))
    stale = library.record(archive_id)
    assert stale["index_state"] == "pending" and stale["abstract"]["status"] == "stale"
    assert saved["text_revision"] == document["text_revision"] + 1
    assert saved["checked_text_revision"] == document["text_revision"]
    library.index_pending()
    current = library.record(archive_id)
    assert current["abstract"]["based_on_revision"] == current["revision"]
    assert current["abstract"]["status"] == "partial"  # No fabricated regenerated AI summary.
    assert "user correction" in json.dumps(current["abstract"])
    assert saved["initial_text"] == "initial text"
    assert library.source(document["id"]) == b"source-one"


def test_initial_text_cannot_be_overwritten(library):
    document = ready(library, add(library, "one"))
    with pytest.raises(sqlite3.IntegrityError):
        library.change(document["id"], lambda row: row.update(initial_text="rewritten"))
    assert library.get(document["id"])["initial_text"] == "initial text"
    assert library.get(document["id"])["revision"] == document["revision"]


def test_delete_preserves_siblings_and_removes_last_empty_archive(library):
    one = ready(library, add(library, "one"))
    two = ready(library, add(library, "two", one["record_id"]))
    library.index_pending()
    library.delete(one["id"])
    library.index_pending()
    assert library.record(two["record_id"])["document_count"] == 1
    assert one["id"] not in json.dumps(library.record(two["record_id"])["abstract"])
    assert library.source(two["id"]) == b"source-two"
    with pytest.raises(KeyError):
        library.source(one["id"])
    library.delete(two["id"])
    with pytest.raises(KeyError):
        library.record(two["record_id"])
    with library.connect() as db:
        for table in ("documents", "document_sources", "document_texts", "document_metadata", "record_abstracts", "index_jobs"):
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0


def test_explicit_move_preserves_identity_and_rejects_patient_mixing(library):
    one = library.save_profile(dict(name="One", aliases=[]))
    two = library.save_profile(dict(name="Two", aliases=[]))
    source = ready(library, add(library, "source"), one)
    target = library.create_record("Confirmed archive", one["id"])
    moved = library.move_document(source["id"], target["id"], source["revision"])
    assert moved["id"] == source["id"] and moved["record_id"] == target["id"]
    assert library.source(moved["id"]) == b"source-source"
    with pytest.raises(KeyError):
        library.record(source["record_id"])
    foreign = ready(library, add(library, "foreign"), two)
    with pytest.raises(Conflict, match="different family member"):
        library.move_document(foreign["id"], target["id"], foreign["revision"])
    assert library.get(foreign["id"])["record_id"] == foreign["record_id"]


def test_profile_update_preserves_record_relationships(library):
    patient = library.save_profile(dict(name="Name", aliases=[]))
    document = ready(library, add(library, "one"), patient)
    library.save_profile(dict(name="Corrected", aliases=["Name"]), patient["id"])
    assert library.record(document["record_id"])["patient_id"] == patient["id"]
    assert library.record(document["record_id"])["patient_name"] == "Corrected"
    with pytest.raises(KeyError):
        library.save_profile(dict(name="Missing", aliases=[]), "missing-id")


def legacy_database(path):
    document = dict(id="legacy-document", title="Legacy report", media="image/jpeg", origin="imported",
        created="2026-01-01T00:00:00+00:00", revision=9, status="filed", stage="complete", error=None,
        attempt=None, initial_text="initial report", text="corrected report", text_origin="user_edited",
        extraction_status="extracted", extraction_error=None, check_status="stale", check_error=None,
        concerns=[dict(quote="initial", reason="Check this", start=0, end=7)], metadata=None,
        index={"saved_text": "corrected report"}, index_status="current")
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE files(id TEXT PRIMARY KEY, operation TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, source BLOB NOT NULL, record TEXT NOT NULL); CREATE TABLE profiles(id TEXT PRIMARY KEY, record TEXT NOT NULL);")
        db.execute("INSERT INTO profiles VALUES (?, ?)", ("patient", json.dumps(dict(id="patient", name="Name", aliases=[]))))
        db.execute("INSERT INTO files VALUES (?, ?, ?, ?, ?)", (document["id"], "operation", "fingerprint", b"original bytes", json.dumps(document)))
    return document


def test_legacy_migration_preserves_bytes_and_has_recoverable_backup(tmp_path):
    path = tmp_path / "old.sqlite3"
    before = legacy_database(path)
    library = Library(path)
    assert Path(library.migration_backup).is_file()
    assert library.get(before["id"])["id"] == before["id"]
    assert library.get(before["id"])["original_filename"] is None  # Old schema did not retain it; do not invent one.
    for key in ("revision", "title", "text", "initial_text", "text_origin", "concerns", "check_status"):
        assert library.get(before["id"])[key] == before[key]
    assert hashlib.sha256(library.source(before["id"])).digest() == hashlib.sha256(b"original bytes").digest()
    assert Library(path).migration_backup is None
    with sqlite3.connect(library.migration_backup) as db:
        assert db.execute("SELECT count(*) FROM files").fetchone()[0] == 1
    with library.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_failed_migration_rolls_back_schema_and_data(tmp_path, monkeypatch):
    path = tmp_path / "old.sqlite3"
    legacy_database(path)
    def fail(*_args):
        raise RuntimeError("Injected migration failure")
    monkeypatch.setattr(Library, "_insert_document", fail)
    with pytest.raises(RuntimeError, match="Injected migration failure"):
        Library(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT source FROM files").fetchone()[0] == b"original bytes"
        assert db.execute("SELECT count(*) FROM profiles").fetchone()[0] == 1
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='documents'").fetchone()
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0
