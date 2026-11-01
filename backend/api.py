"""HTTP interface. Run one process: python -m uvicorn backend.api:app --port 8000.

Architecture: ../implementation-architecture.svg#O3 (HTTP boundary).
"""

import asyncio
import json
import os
import sqlite3
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .filing import DIMENSIONS, FilingWorkflow
from .models import ConcernReview, DocumentMove, LibraryReset, ManualSave, NewText, Profile, RecordCreate, Recheck
from .departments import CATALOG
from .processing import MAX_BYTES, MAX_PAGES, MAX_TEXT, MEDIA
from .storage import Conflict, Library
from .members import match_profile
from .chat import Question, MetadataSave, chat, metadata_save
from .processing import ProcessingError
from . import processing
from . import demo
from . import demo_samples


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


# View: implementation-architecture.svg#O3
# Construct the HTTP boundary around one Library and FilingWorkflow.
# HTTP schemas validate shape; handlers validate state and establish explicit write intent.
def create_app(path=None):
    library = Library(Path(path or os.getenv("LIBRARY_PATH", "data/library.sqlite3")))
    workflow = FilingWorkflow(library)

    # View: backend/import-pipeline.svg#B12
    # Recover interrupted attempts before serving requests, rebuild pending indexes,
    # and own one filing worker for the lifetime of this process. Shutdown waits for that worker.
    @asynccontextmanager
    async def lifespan(app):
        # import-pipeline.svg#B12: interrupted work becomes retryable on startup.
        library.recover()
        library.index_pending()
        app.state.executor = ThreadPoolExecutor(max_workers=1)
        yield
        app.state.executor.shutdown(wait=True)

    app = FastAPI(title="Family Medical Records", lifespan=lifespan)
    app.state.library = library

    # View: backend/library-storage.svg#S4
    # Translate missing/deleted identities to 404; an evidence link must not silently open a different file.
    @app.exception_handler(KeyError)
    async def missing(_request, _error):
        return JSONResponse(status_code=404, content={"detail": "This file or profile is unavailable."})

    # View: backend/library-storage.svg#S5
    # A revision/identity conflict is 409, not a successful save. The UI retains the draft for review.
    @app.exception_handler(Conflict)
    async def conflict(_request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    # View: AGENTS.svg#F1G
    # A database error leaves persistence unconfirmed. Return 503 so the caller can retry
    # with the same operation key instead of assuming the original was archived.
    @app.exception_handler(sqlite3.Error)
    async def storage_error(_request, _error):
        return JSONResponse(status_code=503, content={"detail": "Storage failed. The action is not confirmed. Retry before assuming this content is stored."})

    # View: implementation-architecture.svg#O8
    # Disclose the configured primary service and input limits without exposing API credentials.
    # There is no processing-consent gate or backup-provider routing.
    def config():
        service = "OpenAI-compatible API · " + processing.service_name()
        return dict(service=service, configured=bool(os.getenv("OPENAI_API_KEY")),
                    max_bytes=MAX_BYTES, max_pages=MAX_PAGES, max_text=MAX_TEXT, extensions=list(MEDIA), demo=demo.catalog())

    # View: backend/library-storage.svg#S2
    # Require a bounded, stable client operation key before accepting source bytes.
    def operation(value):
        if not value or len(value) > 100:
            raise HTTPException(400, "A stable upload operation key is required.")

    # View: backend/import-pipeline.svg#B1
    # Queue only a committed pending identity. Replayed uploads and already-filed documents
    # return their receipt without creating a second queue identity.
    def schedule(record):
        # import-pipeline.svg#B1: one in-process worker; SQLite retains pending state.
        if record["status"] == "pending":
            app.state.executor.submit(workflow.run, record["id"])
        return record

    # View: implementation-architecture.svg#O8
    # Return processing capabilities for the browser; the primary key remains server-side.
    @app.get("/api/config")
    def get_config():
        return config()

    # View: AGENTS.svg#F5
    # Run evidence retrieval synchronously for this question. Convert provider failures
    # to a visible API error rather than returning an unsupported answer.
    @app.post("/api/chat")
    async def ask(body: Question, accept: str = Header(default='')):
        # Stream stage receipts, never unreviewed answer text. Existing JSON clients
        # retain the same response contract and do not create a second AI operation.
        if 'application/x-ndjson' in accept:
            async def events():
                queue = asyncio.Queue()
                loop = asyncio.get_running_loop()
                stopped = Event()

                def emit(value):
                    if not stopped.is_set():
                        loop.call_soon_threadsafe(queue.put_nowait, value)

                def progress(stage, count=None):
                    if stopped.is_set():
                        raise ProcessingError('The chat connection was closed.')
                    emit(dict(type='status', stage=stage, count=count))

                def run():
                    try:
                        emit(dict(type='result', result=chat(library, body, progress)))
                    except (ProcessingError, Conflict) as error:
                        emit(dict(type='error', detail=str(error)))
                    except Exception:
                        emit(dict(type='error', detail='Chat could not complete. Your records are unchanged. Please retry.'))

                task = asyncio.create_task(asyncio.to_thread(run))
                try:
                    while True:
                        try:
                            event = await asyncio.wait_for(queue.get(), timeout=10)
                        except asyncio.TimeoutError:
                            event = dict(type='heartbeat')
                        yield json.dumps(event, ensure_ascii=False) + '\n'
                        if event['type'] in ('result', 'error'):
                            break
                finally:
                    stopped.set()
                    task.cancel()

            return StreamingResponse(events(), media_type='application/x-ndjson',
                                     headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
        try:
            return await asyncio.to_thread(chat, library, body)
        except ProcessingError as error:
            raise HTTPException(502, str(error)) from error

    # View: backend/chat-flow.svg#C10
    # This is an explicit mutation endpoint, separate from ordinary read-only chat.
    # Its target and revision come from a reviewed action, not an autonomous model write.
    @app.put("/api/chat/metadata")
    def chat_metadata(body: MetadataSave):
        # Diagram 07: only an explicit, reviewable UI action commits metadata.
        return metadata_save(library, body)

    # View: AGENTS.svg#F4
    # Read stored document snapshots for the Library without calling the AI service.
    @app.get("/api/files")
    def list_files():
        return library.list()

    # database-schema.svg#D2: archive ownership is explicit; dates never merge files.
    # View: backend/library-storage.svg#S9
    # Expose organizational archive filters separately from the document browsing contract.
    # An archive can contain multiple documents; shared labels do not establish a clinical connection.
    @app.get("/api/records")
    def records(patient_id: str | None = None, department_code: str | None = None, disease: str | None = None):
        return library.records(patient_id=patient_id, department_code=department_code, disease=disease)

    # View: backend/database-schema.svg#D2
    # Return one archive, its document list and current evidence-index status.
    @app.get("/api/records/{record_id}")
    def get_record(record_id: str):
        return library.record(record_id)

    # View: backend/database-schema.svg#D2
    # Validate a user-supplied archive title before creating an explicit organizational container.
    @app.post("/api/records", status_code=201)
    def create_record(body: RecordCreate):
        record = library.create_record(body.title.strip(), body.patient_id)
        library.index_pending()
        return library.record(record["id"])

    # View: backend/database-schema.svg#D11
    # Return registered department names/codes; arbitrary model text cannot create a catalog entry.
    @app.get("/api/departments")
    def department_catalog():
        return CATALOG

    # View: backend/library-storage.svg#S11
    # Delegate explicit ownership changes to the revision- and patient-aware storage operation,
    # then refresh the affected archive indexes.
    @app.put("/api/files/{file_id}/record")
    def move_document(file_id: str, body: DocumentMove):
        library.move_document(file_id, body.record_id, body.revision)
        library.index_pending()
        return library.get(file_id)

    # View: AGENTS.svg#F6
    # A source link resolves one stable document snapshot; opening it is read-only.
    @app.get("/api/files/{file_id}")
    def get_file(file_id: str):
        return library.get(file_id)

    # View: src/import/ui-flow.svg#U9
    # Return preserved source bytes with their media type. Disable caching and MIME sniffing
    # so browser preview uses the actual stored report without rewriting it.
    @app.get("/api/files/{file_id}/original")
    def original(file_id: str):
        record = library.get(file_id)
        return Response(library.source(file_id), media_type=record["media"],
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    # View: AGENTS.svg#F1
    # Validate the extension and bounded source size, commit original bytes and pending state,
    # then schedule processing. Selecting a file starts this operation without a second confirmation.
    @app.post("/api/imports", status_code=202)
    async def upload(file: UploadFile = File(), record_id: str | None = Form(None), idempotency_key: str = Header()):
        # library-storage.svg#S2: validate input before the atomic source/pending save.
        operation(idempotency_key)
        title = Path(file.filename or "document").name[:200]
        media = MEDIA.get(Path(title).suffix.lower())
        if not media:
            raise HTTPException(415, "Choose JPEG, PNG, WebP, PDF, or UTF-8 .txt. HEIC is not supported in this draft.")
        source = await file.read(MAX_BYTES + 1)
        await file.close()
        if not source or len(source) > MAX_BYTES:
            raise HTTPException(413, "Choose a nonempty file of at most 20 MiB.")
        return schedule(library.create(operation=idempotency_key, source=source,
                                       title=title, media=media, origin="imported", record_id=record_id))

    @app.get("/api/demo/samples")
    def demo_sample_catalog():
        return demo_samples.catalog()

    @app.post("/api/demo/samples/{sample_id}/import", status_code=202)
    def import_demo_sample(sample_id: str, idempotency_key: str = Header()):
        operation(idempotency_key)
        if sample_id not in demo_samples.SAMPLES:
            raise HTTPException(404, "This demo sample is unavailable.")
        try:
            title, media, source = demo_samples.source(sample_id)
        except FileNotFoundError:
            raise HTTPException(404, "This demo sample has not been installed yet.") from None
        if not source or len(source) > MAX_BYTES:
            raise HTTPException(413, "Choose a nonempty file of at most 20 MiB.")
        if not source.startswith(b"%PDF-" if media == "application/pdf" else b"\xff\xd8\xff"):
            raise HTTPException(415, "The installed sample does not match its file type.")
        return schedule(library.create(operation=idempotency_key, source=source,
                                       title=title, media=media, origin="imported"))

    # View: src/import/ui-flow.svg#U2
    # Save-and-file converts a local text draft into a durable source. Whitespace and size
    # limits are checked before saving; repeated operation keys remain idempotent.
    @app.post("/api/texts", status_code=202)
    def new_text(body: NewText, idempotency_key: str = Header()):
        # ../src/import/ui-flow.svg#U2: this endpoint is reached only after explicit Save.
        operation(idempotency_key)
        if not body.text.strip() or len(body.text) > MAX_TEXT:
            raise HTTPException(413, f"Enter nonblank text of at most {MAX_TEXT:,} characters.")
        return schedule(library.create(operation=idempotency_key, source=body.text.encode(),
                                       title=body.title, media="text/plain", origin="user_entered", record_id=body.record_id))

    # View: backend/import-pipeline.svg#B9
    # Resume the existing failed document, preserving identity and already-extracted text.
    @app.post("/api/files/{file_id}/retry", status_code=202)
    def retry(file_id: str):
        return schedule(workflow.retry(file_id))

    # View: src/import/ui-flow.svg#U7
    # This user-driven path saves current text/details without asking AI to rewrite them.
    # Resolve a supplied member against existing profiles, then mutate under a revision guard.
    @app.put("/api/files/{file_id}/manual")
    def manual(file_id: str, body: ManualSave):
        # ../src/import/ui-flow.svg#U7: an explicit correction has its own write path.
        if not body.text.strip() or len(body.text) > MAX_TEXT:
            raise HTTPException(413, f"Enter nonblank text of at most {MAX_TEXT:,} characters.")
        profile = next((item for item in library.profiles() if item["id"] == body.member_id), None)
        if body.member_id and not profile:
            raise HTTPException(400, "Choose an existing family member or leave unassigned.")
        member_name = body.member_name.strip() if body.member_name is not None else profile["name"] if profile else ""
        if body.member_name is not None:
            profile = match_profile(member_name, library.profiles())

        # View: AGENTS.svg#F3G
        # Compare the editor revision before changing evidence. Preserve unchanged provenance,
        # clear the worker attempt, and stale old checks only when text changed. Rebuild retrieval
        # from saved text so obsolete AI clinical terms cannot survive a human correction.
        def apply(record):
            # library-storage.svg#S5: reject a stale editor revision before changing data.
            if record["revision"] != body.revision:
                raise Conflict("This record changed. Reopen it before saving your draft.")
            changed = record["text"] != body.text
            metadata = {}
            values = dict(member=[member_name] if member_name else [], date=[body.date] if body.date.strip() else [],
                          department=body.department, disease=body.disease)
            for key in DIMENSIONS:
                entries = [dict(value=value.strip(), quote="", **({"profile_id": profile["id"]} if key == "member" and profile else {}))
                           for value in values[key] if value.strip()]
                metadata[key] = dict(status="known" if entries else "missing", values=entries, candidates=[], provenance="user_supplied")
            if record["metadata"]:
                for key in DIMENSIONS:
                    if ([value["value"] for value in metadata[key]["values"]] ==
                        [value["value"] for value in record["metadata"][key]["values"]]):
                        metadata[key] = record["metadata"][key]
            record.update(text=body.text, metadata=metadata, status="filed", stage="complete", error=None, attempt=None)
            if changed:
                for concern in record["concerns"]:
                    concern.pop("reviewed", None)
                # library-storage.svg#S5: preserve source/initial text; stale checks stay visible.
                record.update(text_origin="user_edited", check_status="stale", index={"saved_text": body.text})
            # Rebuild retrieval from saved text and current fields in this transaction.
            # Drop old AI clinical terms when their supporting text has changed.
            record["index"] = {**(record["index"] or {}), "saved_text": body.text, "classifications": metadata}
            record["index_status"] = "current"

        library.change(file_id, apply)
        library.index_pending()
        return library.get(file_id)

    # View: src/import/ui-flow.svg#U12
    # Check a stable saved-text snapshot outside a database transaction; do not hold a write
    # lock during a network call. Store a failed-check outcome separately from filing status.
    @app.post("/api/files/{file_id}/recheck")
    def recheck(file_id: str, body: Recheck):
        record = library.get(file_id)
        if record["revision"] != body.revision or record["status"] in ("pending", "processing"):
            raise Conflict("This record changed or is processing. Reopen its saved text before checking.")
        if not record["text"] or not record["text"].strip():
            raise HTTPException(400, "Save document text before requesting Recheck.")
        if len(record["text"]) > MAX_TEXT:
            raise HTTPException(413, f"Checking is limited to {MAX_TEXT:,} characters.")
        # Check outside the storage transaction. A concurrent edit/deletion must
        # invalidate this result, never attach it to different saved evidence.
        try:
            values = dict(check_status="checked", check_error=None, concerns=processing.check(record["text"]))
        except ProcessingError as error:
            values = dict(check_status="failed", check_error=str(error))

        # View: backend/library-storage.svg#S5
        # Compare the revision again after AI returns: an edit/delete during the request
        # must prevent attaching old concerns to a new document version.
        def apply(current):
            if current["revision"] != body.revision:
                raise Conflict("This record changed during Recheck. Check its current saved text again.")
            current.update(**values)

        library.change(file_id, apply)
        library.index_pending()
        return library.get(file_id)

    @app.put("/api/files/{file_id}/concerns/{index}")
    def review_concern(file_id: str, index: int, body: ConcernReview):
        def apply(record):
            if record["revision"] != body.revision or record["status"] in ("pending", "processing") or record["check_status"] != "checked":
                raise Conflict("This record changed or its text check is not current. Reopen and review its saved text.")
            if index < 0 or index >= len(record["concerns"]):
                raise HTTPException(404, "This text concern is unavailable.")
            record["concerns"][index]["reviewed"] = body.reviewed

        library.change(file_id, apply)
        library.index_pending()
        return library.get(file_id)

    # View: src/import/ui-flow.svg#U10
    # Delete this selected identity and rebuild affected indexes only after storage confirms it.
    @app.delete("/api/files/{file_id}", status_code=204)
    def delete(file_id: str):
        # library-storage.svg#S7: delete the selected identity and every stored derivative.
        library.delete(file_id)
        library.index_pending()
        return Response(status_code=204)

    # View: backend/library-storage.svg#S8
    # Family profiles organize evidence; they are not authentication accounts.
    @app.get("/api/profiles")
    def profiles():
        return library.profiles()

    # View: src/import/ui-flow.svg#U13
    # Validate the reviewed name/aliases, create a managed member and relink exact matches.
    @app.post("/api/profiles", status_code=201)
    def create_profile(body: Profile):
        # library-storage.svg#S8: profiles are shared family labels, not user accounts.
        if not body.name.strip() or any(not alias.strip() for alias in body.aliases):
            raise HTTPException(400, "Enter a name and nonblank aliases.")
        profile = library.save_profile(body.model_dump())
        library.index_pending()
        return profile

    # View: backend/library-storage.svg#S8
    # Correct one existing member without inventing another identity or rewriting reports.
    @app.put("/api/profiles/{profile_id}")
    def update_profile(profile_id: str, body: Profile):
        # library-storage.svg#S8: correct the existing profile without inventing a new identity.
        if not body.name.strip() or any(not alias.strip() for alias in body.aliases):
            raise HTTPException(400, "Enter a name and nonblank aliases.")
        profile = library.save_profile(body.model_dump(), profile_id)
        library.index_pending()
        return profile

    # View: backend/library-storage.svg#S8
    # Detach a removed profile while preserving its reports for later reassignment.
    @app.delete("/api/profiles/{profile_id}", status_code=204)
    def delete_profile(profile_id: str):
        library.delete_profile(profile_id)
        library.index_pending()
        return Response(status_code=204)

    # View: src/import/ui-flow.svg#U15
    # This explicit demo action clears the shared library atomically; it never runs
    # as part of import/chat. The strict body requires confirmed destructive intent.
    @app.post("/api/library/reset", status_code=204)
    def reset_library(body: LibraryReset):
        library.reset()
        return Response(status_code=204)

    @app.post("/api/demo/import", status_code=202)
    def import_demo():
        profiles, sources = demo.sources()
        documents = library.import_demo(profiles, sources)
        library.index_pending()
        return [schedule(library.get(document["id"])) for document in documents]

    @app.post("/api/demo/reset", status_code=202)
    def reset_demo(body: LibraryReset):
        profiles, sources = demo.sources()
        documents = library.import_demo(profiles, sources, reset=True)
        library.index_pending()
        return [schedule(library.get(document["id"])) for document in documents]

    return app


app = create_app()
