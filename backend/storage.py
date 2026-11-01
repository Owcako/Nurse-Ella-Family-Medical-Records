"""SQLite-only patient -> medical record -> document persistence.

Architecture: ../implementation-architecture.svg#O6; library-storage.svg;
database-schema.svg. Public document IDs and /api/files contracts stay stable.
"""

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import departments
from .members import match_profile, normalized_name


# View: backend/library-storage.svg#S5
# Signal a stale or inconsistent mutation; callers must reopen/review rather than overwrite.
class Conflict(Exception):
    pass


# View: backend/database-schema.svg#D3
# Generate archive-operation timestamps in UTC. These are not documented medical dates.
def now():
    return datetime.now(timezone.utc).isoformat()


# View: implementation-architecture.svg#O6
# Own SQLite persistence and derived archive indexes. Every public document view is
# reconstructed from normalized tables; source bytes remain inside the database.
class Library:
    # View: backend/library-storage.svg#S1
    # Create the library directory and initialize schema/catalogs before accepting records.
    def __init__(self, path: Path):
        # library-storage.svg#S1: schema owns relationships, source, text and state separately.
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_backup = None
        self._initialize()

    # View: backend/library-storage.svg#S5
    # Enable foreign keys for every connection. Commit only if the whole operation
    # succeeds, roll back exceptions, and always release the database handle.
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    # View: backend/library-storage.svg#S1
    # Apply schema/catalog changes transactionally. Before migrating legacy JSON rows,
    # create a consistent backup and verify copied text, bytes and row counts. Unsupported
    # future schema versions stop startup rather than risk destructive interpretation.
    def _initialize(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("This library requires a newer application version.")
            legacy = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='files'").fetchone()
            if legacy:
                # Freeze writers while a separate reader takes a consistent pre-migration backup.
                backup = self.path.with_name(self.path.name + ".before-v2-" + uuid4().hex[:8] + ".bak")
                source = sqlite3.connect(self.path)
                target = sqlite3.connect(backup)
                try:
                    source.backup(target)
                finally:
                    source.close()
                    target.close()
                self.migration_backup = str(backup)
            # executescript commits an existing transaction; execute complete statements
            # individually so schema creation, copying and legacy removal roll back together.
            statement = ""
            schema = Path(__file__).resolve().parents[1] / "backend" / "schema.sql"
            for line in schema.read_text(encoding="utf-8").splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    db.execute(statement)
                    statement = ""
            for item in departments.CATALOG["departments"]:
                db.execute("""INSERT INTO departments VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET name_en=excluded.name_en,
                    name_zh=excluded.name_zh, aliases_json=excluded.aliases_json,
                    catalog_version=excluded.catalog_version""", (item["code"], item["name_en"], item["name_zh"],
                    json.dumps([*item["aliases_en"], *item["aliases_zh"]]), departments.VERSION))
            if legacy:
                for row in db.execute("SELECT * FROM profiles").fetchall():
                    profile = json.loads(row["record"])
                    db.execute("INSERT INTO patients VALUES (?, ?, ?, ?, ?)",
                               (profile["id"], profile["name"], profile.get("slug"), json.dumps(profile["aliases"]), now()))
                rows = db.execute("SELECT * FROM files ORDER BY rowid").fetchall()
                for row in rows:
                    data = json.loads(row["record"])
                    record_id = self._new_record(db, data["title"], created=data["created"])
                    filename = data["title"] if Path(data["title"]).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt") else None
                    self._insert_document(db, data, record_id, row["operation"], row["fingerprint"], row["source"], filename)
                    saved = self._read_document(db, data["id"])
                    if saved["text"] != data["text"] or saved["initial_text"] != data["initial_text"]:
                        raise RuntimeError("Migration text verification failed; transaction rolled back.")
                    if self._source(db, data["id"]) != row["source"]:
                        raise RuntimeError("Migration source verification failed; transaction rolled back.")
                if db.execute("SELECT count(*) FROM documents").fetchone()[0] != len(rows):
                    raise RuntimeError("Migration document count verification failed.")
                db.execute("DROP TABLE files")
                db.execute("DROP TABLE profiles")
            # database-schema.svg#D11: catalog changes remap saved source labels,
            # invalidate affected archives, and leave unsupported labels unresolved.
            outdated = db.execute("SELECT document_id FROM document_metadata WHERE department_catalog_version<>?",
                                  (departments.VERSION,)).fetchall()
            for row in outdated:
                data = self._read_document(db, row[0])
                self._write_document(db, data)
                self._touch_record(db, data["record_id"], "department_catalog_changed")
            self._relink_members(db)
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Library relationship validation failed.")
            db.execute("PRAGMA user_version=2")

    # View: backend/database-schema.svg#D2
    # Create one organizational archive, with an optional existing patient. Explicit
    # user labels have separate provenance from labels later aggregated from documents.
    def _new_record(self, db, title, patient_id=None, created=None, explicit=False):
        if patient_id and not db.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone():
            raise KeyError(patient_id)
        record_id = str(uuid4())
        stamp = created or now()
        db.execute("""INSERT INTO medical_records
            (id, patient_id, patient_status, patient_provenance, title, title_provenance, revision, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""", (record_id, patient_id,
            "known" if patient_id else "missing", "user_supplied" if patient_id else "documents",
            title, "user_supplied" if explicit else "documents", stamp, stamp))
        return record_id

    # View: backend/library-storage.svg#S3
    # Insert document identity and immutable source in the same transaction as derived
    # state, then invalidate its owning archive for deterministic reindexing.
    def _insert_document(self, db, data, record_id, operation, fingerprint, source, filename):
        db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (data["id"], record_id, operation, fingerprint, data["title"], filename,
                    data["media"], data["origin"], data["revision"], data["created"]))
        db.execute("INSERT INTO document_sources VALUES (?, ?, ?)",
                   (data["id"], hashlib.sha256(source).hexdigest(), source))
        self._write_document(db, data)
        self._touch_record(db, record_id, "document_added")

    # View: backend/library-storage.svg#S2
    # Compare a repeated operation key and fingerprint under BEGIN IMMEDIATE.
    # A valid replay returns the same document; conflicting content is rejected before
    # creating another archive, source, or pending task.
    def create(self, *, operation, source, title, media, origin, record_id=None):
        # library-storage.svg#S2: replay the same operation, never create another archive/document.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._create(db, operation=operation, source=source, title=title, media=media, origin=origin, record_id=record_id)

    def _create(self, db, *, operation, source, title, media, origin, record_id=None):
        fingerprint = hashlib.sha256(source + media.encode() + origin.encode() + title.encode()).hexdigest()
        old = db.execute("SELECT id, record_id, fingerprint FROM documents WHERE operation=?", (operation,)).fetchone()
        if old:
            if old["fingerprint"] != fingerprint or record_id and old["record_id"] != record_id:
                raise Conflict("This upload operation already belongs to different content or archive.")
            return self._read_document(db, old["id"])
        if record_id and not db.execute("SELECT 1 FROM medical_records WHERE id=?", (record_id,)).fetchone():
            raise KeyError(record_id)
        # library-storage.svg#S3: parent, immutable source and pending document commit together.
        record_id = record_id or self._new_record(db, title)
        data = dict(id=str(uuid4()), title=title, media=media, origin=origin, created=now(), revision=1,
                    status="pending", stage="source", error=None, initial_text=None, text=None,
                    text_origin=origin, check_status="pending", check_error=None, concerns=[], metadata=None,
                    index=None, index_status="missing", attempt=None, extraction_status="pending", extraction_error=None)
        self._insert_document(db, data, record_id, operation, fingerprint, source,
                              title if origin == "imported" else None)
        return self._read_document(db, data["id"])

    # View: backend/database-schema.svg#D5
    # Split a document snapshot into current/initial text, independent processing state,
    # metadata and index tables. Advance text revision only on actual text changes; retain
    # the revision checked by old results. Resolve only registered department aliases.
    def _write_document(self, db, data):
        old = db.execute("SELECT * FROM document_texts WHERE document_id=?", (data["id"],)).fetchone()
        text_revision = (old["revision"] if old else 0) + int((old["current_text"] if old else None) != data["text"])
        db.execute("UPDATE documents SET title=?, revision=? WHERE id=?", (data["title"], data["revision"], data["id"]))
        db.execute("""INSERT INTO document_texts VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET initial_text=excluded.initial_text,
            current_text=excluded.current_text, text_origin=excluded.text_origin, revision=excluded.revision""",
            (data["id"], data["initial_text"], data["text"], data["text_origin"], text_revision))
        prior_check = db.execute("SELECT checked_text_revision FROM document_processing WHERE document_id=?", (data["id"],)).fetchone()
        checked_revision = text_revision if data["check_status"] == "checked" else prior_check[0] if prior_check else None
        db.execute("""INSERT INTO document_processing VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET status=excluded.status, stage=excluded.stage,
            attempt=excluded.attempt, error=excluded.error, extraction_status=excluded.extraction_status,
            extraction_error=excluded.extraction_error, check_status=excluded.check_status,
            check_error=excluded.check_error, checked_text_revision=excluded.checked_text_revision, concerns_json=excluded.concerns_json""",
            (data["id"], data["status"], data["stage"], data.get("attempt"), data.get("error"),
             data.get("extraction_status", "extracted" if data["text"] is not None else "pending"), data.get("extraction_error"),
             data["check_status"], data.get("check_error"), checked_revision, json.dumps(data["concerns"])))
        metadata = json.loads(json.dumps(data["metadata"])) if data["metadata"] is not None else None
        if metadata:
            self._link_member(db, metadata)
            field = metadata["department"]
            for evidence in [*field["values"], *field["candidates"]]:
                evidence["department_code"] = departments.resolve(evidence["value"])
            field["mapping_status"] = "resolved" if field["status"] == "known" and field["values"] and all(item["department_code"] for item in field["values"]) else "unresolved"
        db.execute("""INSERT INTO document_metadata VALUES (?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET classifications_json=excluded.classifications_json,
            department_catalog_version=excluded.department_catalog_version""",
            (data["id"], json.dumps(metadata) if metadata is not None else None, departments.VERSION))
        content = data.get("index")
        if content is not None:
            content = {**content, "classifications": metadata}
        db.execute("""INSERT INTO document_indexes VALUES (?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET content_json=excluded.content_json,
            text_revision=excluded.text_revision, status=excluded.status""",
            (data["id"], json.dumps(content) if content is not None else None, text_revision,
             data.get("index_status", "current" if content is not None else "missing")))

    # View: backend/library-storage.svg#S4
    # Join authoritative tables to preserve the stable /api/files response contract.
    # Attach a current archive summary rather than storing a second mutable file record.
    def _read_document(self, db, file_id):
        row = db.execute("""SELECT d.*, t.initial_text, t.current_text, t.text_origin, t.revision AS text_revision,
            p.status, p.stage, p.attempt, p.error, p.extraction_status, p.extraction_error,
            p.check_status, p.check_error, p.checked_text_revision, p.concerns_json,
            m.classifications_json, m.department_catalog_version, i.content_json, i.status AS index_status
            FROM documents d JOIN document_texts t ON t.document_id=d.id
            JOIN document_processing p ON p.document_id=d.id JOIN document_metadata m ON m.document_id=d.id
            JOIN document_indexes i ON i.document_id=d.id WHERE d.id=?""", (file_id,)).fetchone()
        if not row:
            raise KeyError(file_id)
        return dict(id=row["id"], record_id=row["record_id"], title=row["title"], original_filename=row["original_filename"],
                    media=row["media_type"], origin=row["origin"], created=row["created_at"], revision=row["revision"],
                    initial_text=row["initial_text"], text=row["current_text"], text_origin=row["text_origin"], text_revision=row["text_revision"],
                    status=row["status"], stage=row["stage"], attempt=row["attempt"], error=row["error"],
                    extraction_status=row["extraction_status"], extraction_error=row["extraction_error"],
                    check_status=row["check_status"], check_error=row["check_error"], checked_text_revision=row["checked_text_revision"],
                    concerns=json.loads(row["concerns_json"]), metadata=json.loads(row["classifications_json"]) if row["classifications_json"] else None,
                    index=json.loads(row["content_json"]) if row["content_json"] else None, index_status=row["index_status"],
                    department_catalog_version=row["department_catalog_version"], archive=self._record_summary(db, row["record_id"]))

    # View: backend/library-storage.svg#S4
    # Read one stable document ID; a missing/deleted report raises instead of returning a substitute.
    def get(self, file_id):
        # library-storage.svg#S4: compose the public document view from authoritative tables.
        with self.connect() as db:
            return self._read_document(db, file_id)

    # View: backend/database-schema.svg#D4
    # Fetch the immutable original BLOB for this identity. No extracted text can replace it.
    def _source(self, db, file_id):
        row = db.execute("SELECT content FROM document_sources WHERE document_id=?", (file_id,)).fetchone()
        if not row:
            raise KeyError(file_id)
        return row[0]

    # View: backend/library-storage.svg#S4
    # Read original bytes without a temporary exported file or an AI request.
    def source(self, file_id):
        # library-storage.svg#S4: source reads do not unpack or modify a file on disk.
        with self.connect() as db:
            return self._source(db, file_id)

    # View: backend/library-storage.svg#S4
    # Return document snapshots in archive insertion order; browsing builds medical-date groups separately.
    def list(self):
        # library-storage.svg#S4: existing evidence links continue to resolve document IDs.
        with self.connect() as db:
            return [self._read_document(db, row[0]) for row in db.execute("SELECT id FROM documents ORDER BY rowid DESC").fetchall()]

    # View: backend/library-storage.svg#S5
    # Lock the write transaction, load the current snapshot, and run the caller guard/edit.
    # Protect identity/ownership fields, increment revision and invalidate the archive atomically.
    def change(self, file_id, edit):
        # library-storage.svg#S5: workflow/editor guards run before normalized writes commit.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            data = self._read_document(db, file_id)
            immutable = {key: data[key] for key in ("id", "record_id", "media", "origin", "created")}
            edit(data)
            if any(data[key] != value for key, value in immutable.items()):
                raise Conflict("Use the explicit archive move operation to change document ownership.")
            data["revision"] += 1
            self._write_document(db, data)
            self._touch_record(db, data["record_id"], "document_changed")
            return self._read_document(db, file_id)

    # View: backend/library-storage.svg#S9
    # Recompute archive labels and lookup links from committed document classifications.
    # Keep partial/missing/ambiguous/conflicting states visible; enqueue indexing at the new
    # archive revision instead of inventing an integrated clinical narrative.
    def _touch_record(self, db, record_id, reason):
        record = db.execute("SELECT * FROM medical_records WHERE id=?", (record_id,)).fetchone()
        docs = db.execute("""SELECT d.id, d.title, m.classifications_json FROM documents d
            JOIN document_metadata m ON m.document_id=d.id WHERE d.record_id=?""", (record_id,)).fetchall()
        metadata = [json.loads(row["classifications_json"]) if row["classifications_json"] else {} for row in docs]
        known_patients = {row[0] for row in db.execute("SELECT id FROM patients")}

        # View: backend/library-storage.svg#S9
        # A single value is known only if every participating document supports it.
        # Multiple supported values remain ambiguous; incomplete agreement remains partial.
        def consensus(key, attribute):
            values = set()
            complete = bool(metadata)
            ambiguous = False
            for item in metadata:
                field = item.get(key) or {}
                complete = complete and field.get("status") == "known" and bool(field.get("values"))
                ambiguous = ambiguous or field.get("status") == "ambiguous"
                for value in field.get("values", []):
                    value = value.get(attribute)
                    if value and (key != "member" or value in known_patients):
                        values.add(value)
                    else:
                        complete = False
            state = "ambiguous" if ambiguous or len(values) > 1 else "known" if complete and len(values) == 1 else "partial" if values else "missing"
            return next(iter(values)) if state == "known" else None, state, values

        patient_id, patient_status, patient_values = consensus("member", "profile_id")
        if record["patient_provenance"] == "user_supplied" and record["patient_id"]:
            patient_id = record["patient_id"]
            patient_status = "conflict" if any(value != patient_id for value in patient_values) else "known"
        date, date_status, _ = consensus("date", "value")
        precision = "day" if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else "month" if date and re.fullmatch(r"\d{4}-\d{2}", date) else "year" if date and re.fullmatch(r"\d{4}", date) else "printed" if date else None
        codes, diseases = set(), set()
        unresolved = not bool(metadata)
        for item in metadata:
            field = item.get("department") or {}
            unresolved = unresolved or field.get("mapping_status") != "resolved"
            codes.update(value["department_code"] for value in field.get("values", []) if value.get("department_code"))
            diseases.update(value["value"] for value in (item.get("disease") or {}).get("values", []))
        db.execute("DELETE FROM record_departments WHERE record_id=?", (record_id,))
        db.executemany("INSERT INTO record_departments VALUES (?, ?)", [(record_id, code) for code in sorted(codes)])
        db.execute("DELETE FROM record_diseases WHERE record_id=?", (record_id,))
        db.executemany("INSERT INTO record_diseases VALUES (?, ?)", [(record_id, value) for value in sorted(diseases)])
        title = docs[0]["title"] if len(docs) == 1 and record["title_provenance"] == "documents" else record["title"]
        revision = record["revision"] + 1
        db.execute("""UPDATE medical_records SET patient_id=?, patient_status=?, title=?, date_label=?,
            date_status=?, date_precision=?, department_status=?, revision=?, updated_at=? WHERE id=?""",
            (patient_id, patient_status, title, date, date_status, precision, "partial" if codes and unresolved else "missing" if not codes else "known", revision, now(), record_id))
        db.execute("""INSERT INTO index_jobs VALUES (?, ?, NULL, 'pending', ?, NULL, ?)
            ON CONFLICT(record_id) DO UPDATE SET target_revision=excluded.target_revision,
            state='pending', reason=excluded.reason, error=NULL, updated_at=excluded.updated_at""", (record_id, revision, reason, now()))
        db.execute("UPDATE record_abstracts SET status='stale' WHERE record_id=?", (record_id,))

    # View: backend/library-storage.svg#S9
    # Combine archive state, patient label, department/disease links and index status.
    # A clearly printed name can be displayed even before a managed family profile exists.
    def _record_summary(self, db, record_id):
        row = db.execute("""SELECT r.*, p.name AS patient_name, j.state AS index_state,
            j.indexed_revision, j.error AS index_error,
            (SELECT count(*) FROM documents WHERE record_id=r.id) AS document_count
            FROM medical_records r LEFT JOIN patients p ON p.id=r.patient_id
            LEFT JOIN index_jobs j ON j.record_id=r.id WHERE r.id=?""", (record_id,)).fetchone()
        if not row:
            raise KeyError(record_id)
        result = dict(row)
        if not result["patient_id"]:
            # A documented report name does not require a managed family profile.
            fields = []
            for item in db.execute("""SELECT m.classifications_json FROM document_metadata m
                JOIN documents d ON d.id=m.document_id WHERE d.record_id=?""", (record_id,)):
                fields.append((json.loads(item[0]) if item[0] else {}).get("member", {}))
            names = {value["value"] for field in fields for value in field.get("values", [])}
            if any(field.get("status") == "ambiguous" for field in fields) or len(names) > 1:
                result["patient_status"] = "ambiguous"
            elif len(names) == 1:
                result["patient_name"] = next(iter(names))
                result["patient_status"] = "known" if all(field.get("status") == "known" for field in fields) else "partial"
        result["departments"] = [dict(item) for item in db.execute("""SELECT d.code, d.name_en, d.name_zh FROM departments d
            JOIN record_departments rd ON rd.department_code=d.code WHERE rd.record_id=? ORDER BY d.code""", (record_id,))]
        result["department_code"] = (result["departments"][0]["code"] if len(result["departments"]) == 1 else "multi000") if result["department_status"] == "known" else "unknown0"
        result["diseases"] = [item[0] for item in db.execute("SELECT value FROM record_diseases WHERE record_id=? ORDER BY value", (record_id,))]
        return result

    # View: backend/database-schema.svg#D2
    # Query archive lookup links with bound parameters; this does not perform model-based retrieval.
    def records(self, patient_id=None, department_code=None, disease=None):
        with self.connect() as db:
            sql = "SELECT r.id FROM medical_records r WHERE 1=1"
            args = []
            for value, clause in ((patient_id, "r.patient_id=?"),
                                  (department_code, "EXISTS(SELECT 1 FROM record_departments rd WHERE rd.record_id=r.id AND rd.department_code=?)"),
                                  (disease, "EXISTS(SELECT 1 FROM record_diseases x WHERE x.record_id=r.id AND x.value=?)")):
                if value:
                    sql += " AND " + clause
                    args.append(value)
            return [self._record_summary(db, row[0]) for row in db.execute(sql + " ORDER BY r.created_at DESC", args).fetchall()]

    # View: backend/database-schema.svg#D9
    # Read an archive with its actual document list and revision-labeled evidence summary.
    def record(self, record_id):
        with self.connect() as db:
            result = self._record_summary(db, record_id)
            result["documents"] = [dict(row) for row in db.execute("""SELECT d.id, d.title, d.original_filename, d.media_type,
                d.revision, p.status FROM documents d JOIN document_processing p ON p.document_id=d.id
                WHERE d.record_id=? ORDER BY d.created_at, d.id""", (record_id,))]
            abstract = db.execute("SELECT * FROM record_abstracts WHERE record_id=?", (record_id,)).fetchone()
            result["abstract"] = dict(content=json.loads(abstract["content_json"]), based_on_revision=abstract["based_on_revision"], status=abstract["status"]) if abstract else None
            return result

    # View: backend/database-schema.svg#D2
    # Create and invalidate an explicitly requested archive within one transaction.
    def create_record(self, title, patient_id=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record_id = self._new_record(db, title, patient_id, explicit=True)
            self._touch_record(db, record_id, "record_created")
        return self.record(record_id)

    # View: backend/library-storage.svg#S11
    # Move only a stable, nonprocessing document after checking patient compatibility.
    # Retain its document ID/source and touch both old/new archives so evidence links survive.
    def move_document(self, file_id, record_id, revision):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            document = self._read_document(db, file_id)
            target = self._record_summary(db, record_id)
            if document["revision"] != revision or document["status"] in ("pending", "processing"):
                raise Conflict("This document changed or is processing. Reopen it before moving.")
            if document["record_id"] == record_id:
                return document
            member = (document["metadata"] or {}).get("member", {})
            owners = {value.get("profile_id") for value in member.get("values", []) if value.get("profile_id")}
            target_owners = {target["patient_id"]} if target["patient_id"] else set()
            for row in db.execute("""SELECT m.classifications_json FROM document_metadata m
                JOIN documents d ON d.id=m.document_id WHERE d.record_id=?""", (record_id,)):
                metadata = json.loads(row[0]) if row[0] else {}
                target_owners.update(value["profile_id"] for value in (metadata.get("member") or {}).get("values", []) if value.get("profile_id"))
            if owners and target_owners and len(owners | target_owners) > 1:
                raise Conflict("This document identifies a different family member. Resolve its identity before grouping.")
            old_record = document["record_id"]
            db.execute("UPDATE documents SET record_id=?, revision=revision+1 WHERE id=?", (record_id, file_id))
            self._remove_or_touch(db, old_record)
            self._touch_record(db, record_id, "document_moved")
            return self._read_document(db, file_id)

    # View: backend/library-storage.svg#S10
    # Rebuild deterministic evidence indexes from committed documents, without calling AI.
    # Mark a job current only for its target revision; retain failed jobs for later recovery.
    def index_pending(self):
        # database-schema.svg#D10: deterministic indexing uses saved content, never AI calls.
        with self.connect() as db:
            pending = [row[0] for row in db.execute("SELECT record_id FROM index_jobs WHERE state IN ('pending','failed')")]
        for record_id in pending:
            try:
                with self.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    record = db.execute("SELECT * FROM medical_records WHERE id=?", (record_id,)).fetchone()
                    if not record:
                        continue
                    docs = [self._read_document(db, row[0]) for row in db.execute("SELECT id FROM documents WHERE record_id=?", (record_id,)).fetchall()]
                    content = dict(record_id=record_id, kind="evidence_index", documents=[dict(
                        document_id=doc["id"], title=doc["title"], text_revision=doc["text_revision"],
                        metadata=doc["metadata"], index=doc["index"], text_origin=doc["text_origin"],
                        processing_status=doc["status"], check_status=doc["check_status"], concerns=doc["concerns"])
                        for doc in docs])
                    complete = bool(docs) and all(doc["status"] == "filed" and doc["index"] is not None and
                                   all(key in doc["index"] for key in ("symptoms", "history", "diagnoses", "treatments")) for doc in docs)
                    db.execute("""INSERT INTO record_abstracts VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(record_id) DO UPDATE SET content_json=excluded.content_json,
                        based_on_revision=excluded.based_on_revision, status=excluded.status, catalog_version=excluded.catalog_version""",
                        (record_id, json.dumps(content), record["revision"], "current" if complete else "partial", departments.VERSION))
                    db.execute("UPDATE index_jobs SET indexed_revision=?, state='current', error=NULL, updated_at=? WHERE record_id=? AND target_revision=?",
                               (record["revision"], now(), record_id, record["revision"]))
            except (sqlite3.Error, ValueError) as error:
                with self.connect() as db:
                    db.execute("UPDATE index_jobs SET state='failed', error=?, updated_at=? WHERE record_id=?",
                               ("Index refresh failed: " + type(error).__name__, now(), record_id))

    # View: backend/library-storage.svg#S6
    # A dead process cannot finish its in-memory queue. Invalidate interrupted attempts
    # and expose an explicit Retry state while preserving originals and already-saved text.
    def recover(self):
        # library-storage.svg#S6: restart retains originals and marks interrupted stages retryable.
        for document in self.list():
            if document["status"] in ("pending", "processing"):
                self.change(document["id"], lambda item: item.update(status="failed", attempt=None,
                            error="Processing was interrupted. The original is stored; choose Retry."))

    # View: backend/library-storage.svg#S7
    # Keep an archive and refresh it if siblings remain; remove only an empty archive.
    def _remove_or_touch(self, db, record_id):
        if db.execute("SELECT 1 FROM documents WHERE record_id=?", (record_id,)).fetchone():
            self._touch_record(db, record_id, "document_removed")
        else:
            db.execute("DELETE FROM medical_records WHERE id=?", (record_id,))

    # View: backend/library-storage.svg#S7
    # Delete this document and its owned derivatives by foreign-key cascade.
    # Sibling reports are outside that deletion boundary.
    def delete(self, file_id):
        # library-storage.svg#S7: cascade only this document; siblings keep their evidence.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            document = self._read_document(db, file_id)
            db.execute("DELETE FROM documents WHERE id=?", (file_id,))
            self._remove_or_touch(db, document["record_id"])

    # View: backend/library-storage.svg#S12
    # Delete archives and their owned evidence, then family profiles in one transaction.
    # Catalogs remain available for the next import. Deleted identities invalidate queued
    # workers, so late stage results cannot resurrect the previous demo's documents.
    def reset(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM medical_records")
            db.execute("DELETE FROM patients")

    def import_demo(self, profiles, sources, *, reset=False):
        # Publish the whole kit together. A failed restore keeps the previous library;
        # deleted document IDs invalidate old workers through their existing guards.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if reset:
                db.execute("DELETE FROM medical_records")
                db.execute("DELETE FROM patients")
            for profile in profiles:
                names = {normalized_name(value) for value in [profile["name"], *profile["aliases"]]}
                existing = db.execute("SELECT name, aliases_json FROM patients").fetchall()
                if any(names.intersection(normalized_name(value) for value in [row["name"], *json.loads(row["aliases_json"])]) for row in existing):
                    continue
                db.execute("INSERT INTO patients VALUES (?, ?, NULL, ?, ?)",
                           (str(uuid4()), profile["name"], json.dumps(profile["aliases"]), now()))
            documents = []
            for source in sources:
                existing = db.execute("SELECT id FROM documents WHERE operation=?", (source["operation"],)).fetchone()
                data = self._create(db, **{key: value for key, value in source.items() if key != "prepared"})
                preset = source.get("prepared")
                # Prepared fixtures apply only to new demo imports. Never replace an
                # existing document's edits, immutable extraction, or in-flight work.
                if preset and not existing:
                    data.update(title=preset["title"], text=preset["text"], initial_text=preset["text"],
                                text_origin="demo_prepared", metadata=preset["metadata"], index=preset["index"],
                                concerns=preset["concerns"], check_status=preset["check_status"],
                                status="filed", stage="complete", extraction_status="extracted", index_status="current")
                    data["revision"] += 1
                    self._write_document(db, data)
                    self._touch_record(db, data["record_id"], "demo_prepared")
                documents.append(data)
            self._relink_members(db)
            return [self._read_document(db, document["id"]) for document in documents]

    # View: backend/library-storage.svg#S8
    # Read managed family names/aliases from patients; these are organizational identities.
    def profiles(self):
        # library-storage.svg#S8: public profile identity is backed by patients, not duplicate JSON.
        with self.connect() as db:
            return [dict(id=row["id"], name=row["name"], slug=row["slug"], aliases=json.loads(row["aliases_json"]))
                    for row in db.execute("SELECT * FROM patients ORDER BY created_at, id")]

    # View: backend/library-storage.svg#S8
    # Reject overlapping normalized names/aliases before saving a profile. Relink exact
    # confirmed document names and invalidate affected archives without changing original text.
    def save_profile(self, profile, profile_id=None):
        # library-storage.svg#S8: update in place; REPLACE would destroy referenced identities.
        existing_id = profile_id is not None
        profile_id = profile_id or str(uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM patients WHERE id=?", (profile_id,)).fetchone()
            if existing_id and not old:
                raise KeyError(profile_id)
            names = {normalized_name(value) for value in [profile["name"], *profile["aliases"]]}
            for row in db.execute("SELECT * FROM patients WHERE id<>?", (profile_id,)).fetchall():
                if names.intersection(normalized_name(value) for value in [row["name"], *json.loads(row["aliases_json"])]):
                    raise Conflict("This name or alias already belongs to another member. Select that member to update it.")
            slug = profile.get("slug") or (old["slug"] if old else None)
            db.execute("""INSERT INTO patients VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, slug=excluded.slug, aliases_json=excluded.aliases_json""",
                (profile_id, profile["name"], slug, json.dumps(profile["aliases"]), old["created_at"] if old else now()))
            affected = self._relink_members(db)
            for row in db.execute("SELECT id FROM medical_records WHERE patient_id=?", (profile_id,)).fetchall():
                if row[0] in affected:
                    continue
                self._touch_record(db, row[0], "patient_changed")
        return dict(id=profile_id, name=profile["name"], aliases=profile["aliases"], slug=slug)

    # View: backend/library-storage.svg#S8
    # Only a confirmed single patient name may link to a profile. Remove stale IDs
    # and use exact unique names/aliases; ambiguous candidates never acquire ownership.
    def _link_member(self, db, metadata):
        profiles = [dict(id=row["id"], name=row["name"], aliases=json.loads(row["aliases_json"]))
                    for row in db.execute("SELECT * FROM patients")]
        field = metadata["member"]
        confirmed = field["status"] == "known" and len(field["values"]) == 1
        for value in [*field["values"], *field["candidates"]]:
            profile = next((item for item in profiles if item["id"] == value.get("profile_id")), None) if confirmed else None
            profile = profile or (match_profile(value["value"], profiles) if confirmed else None)
            value.pop("profile_id", None)
            if profile:
                value["profile_id"] = profile["id"]

    # View: backend/library-storage.svg#S8
    # After profile changes, rewrite only changed member links and advance affected
    # document/archive revisions so old source snapshots are visibly stale.
    def _relink_members(self, db):
        affected = set()
        for row in db.execute("SELECT document_id, classifications_json FROM document_metadata WHERE classifications_json IS NOT NULL").fetchall():
            metadata = json.loads(row["classifications_json"])
            prior = json.dumps(metadata, sort_keys=True)
            self._link_member(db, metadata)
            if json.dumps(metadata, sort_keys=True) == prior:
                continue
            data = self._read_document(db, row["document_id"])
            data.update(metadata=metadata, revision=data["revision"] + 1)
            self._write_document(db, data)
            affected.add(data["record_id"])
        for record_id in affected:
            self._touch_record(db, record_id, "member_link_changed")
        return affected

    # View: backend/library-storage.svg#S8
    # Detach the removed profile, relink remaining exact identities and refresh indexes.
    # Deleting a member is not permission to delete that person's stored medical reports.
    def delete_profile(self, profile_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM patients WHERE id=?", (profile_id,)).fetchone():
                raise KeyError(profile_id)
            affected = {row[0] for row in db.execute("SELECT id FROM medical_records WHERE patient_id=?", (profile_id,))}
            db.execute("UPDATE medical_records SET patient_id=NULL, patient_provenance='documents' WHERE patient_id=?", (profile_id,))
            db.execute("DELETE FROM patients WHERE id=?", (profile_id,))
            relinked = self._relink_members(db)
            for record_id in affected - relinked:
                self._touch_record(db, record_id, "member_removed")
