# View: backend/import-pipeline.svg#B8
# Synthetic extraction/check/filing tests exercise stored-source retention, quoted evidence,
# independent failures and HTTP retries without requiring a real provider.
"""Synthetic contract tests. Real report/model acceptance needs user configuration."""

import io
import json
import sqlite3
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI
from PIL import Image
from pypdf import PdfWriter

from backend import processing
from backend.api import create_app
from backend.filing import FilingWorkflow, validate_filing
from backend.models import Filing
from backend.storage import Conflict, Library


TEXT = "Patient: Mei. Date: 2026-10. Department: 内科. Symptom: knee pain. Age: 151."


def filing():
    def field(value=None):
        return dict(status="known" if value else "missing", values=[dict(value=value, quote=TEXT)] if value else [])
    return Filing.model_validate(dict(title="Visit report", is_lab_report=False, lab_report_quote="", member=field("Mei"), date=field("2026-10"),
                                     department=field("内科"), disease=field(), symptoms=[dict(value="knee pain", quote=TEXT)],
                                     history=[], diagnoses=[], treatments=[]))


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / "library.sqlite3")


@pytest.fixture
def services(monkeypatch):
    monkeypatch.setattr(processing, "check", lambda text: [dict(quote="151", reason="Suspected implausible age", start=text.index("151"), end=text.index("151") + 3)])
    monkeypatch.setattr(processing, "classify", lambda text, profiles, initial_text: filing())


def pending(library, operation="upload"):
    return library.create(operation=operation, source=TEXT.encode(), title="report.txt", media="text/plain", origin="imported")


def test_atomic_source_and_idempotent_replay(library):
    first = pending(library)
    assert pending(library)["id"] == first["id"]
    assert len(library.list()) == 1
    assert library.source(first["id"]) == TEXT.encode()
    with pytest.raises(Conflict):
        library.create(operation="upload", source=b"different", title="report.txt", media="text/plain", origin="imported")


def test_filing_uses_documented_member_without_profile(library, services):
    file = pending(library)
    FilingWorkflow(library).run(file["id"])
    saved = library.get(file["id"])
    assert saved["status"] == "filed"
    assert saved["metadata"]["disease"]["status"] == "missing"
    assert saved["metadata"]["member"]["status"] == "known"
    assert saved["metadata"]["member"]["values"] == [dict(value="Mei", quote=TEXT)]
    assert saved["archive"]["patient_name"] == "Mei"
    assert saved["archive"]["patient_status"] == "known"
    assert library.profiles() == []
    assert saved["initial_text"] == saved["text"] == TEXT
    assert saved["concerns"][0]["quote"] == "151"
    assert saved["index"]["symptoms"][0]["value"] == "knee pain"


def test_unique_documented_profile_match(library, services):
    profile = library.save_profile(dict(name="Mei", aliases=[]))
    file = pending(library)
    FilingWorkflow(library).run(file["id"])
    assert library.get(file["id"])["metadata"]["member"]["values"][0]["profile_id"] == profile["id"]


def test_lab_report_uses_initial_text_and_overrides_ordering_department(library, services, monkeypatch):
    initial = "Laboratory results\nGlucose: 105 mg/dL\n" + TEXT
    file = library.create(operation="lab", source=initial.encode(), title="lab.txt", media="text/plain", origin="imported")
    library.change(file["id"], lambda row: row.update(initial_text=initial, text=TEXT))

    def classify(text, profiles, initial_text):
        assert text == TEXT
        assert initial_text == initial
        result = filing()
        result.is_lab_report = True
        result.lab_report_quote = "Laboratory results\nGlucose: 105 mg/dL"
        return result

    monkeypatch.setattr(processing, "classify", classify)
    FilingWorkflow(library).run(file["id"])
    saved = library.get(file["id"])
    assert saved["status"] == "filed"
    field = saved["metadata"]["department"]
    assert field["status"] == "known"
    assert field["provenance"] == "ai_classified"
    assert field["mapping_status"] == "resolved"
    assert field["values"] == [dict(value="Laboratory Medicine", quote="Laboratory results\nGlucose: 105 mg/dL",
                                    source="initial_text", department_code="lab00000")]
    assert saved["archive"]["department_code"] == "lab00000"
    assert library.records(department_code="lab00000")[0]["id"] == saved["record_id"]
    assert saved["text"] == TEXT
    assert saved["initial_text"] == initial
    assert saved["metadata"]["member"]["values"][0]["value"] == "Mei"


def test_non_lab_report_retains_documented_department():
    metadata, _ = validate_filing(filing(), TEXT + " Repeat blood tests next month.", [])
    assert metadata["department"]["values"][0]["value"] == "内科"
    assert metadata["department"]["provenance"] == "documented"


@pytest.mark.parametrize("initial", [TEXT, ""])
def test_lab_report_evidence_must_exist_in_initial_not_just_saved_text(initial):
    result = filing()
    result.is_lab_report = True
    result.lab_report_quote = "Laboratory results"
    with pytest.raises(processing.ProcessingError, match="quotes text absent"):
        validate_filing(result, TEXT + " Laboratory results", [], initial)


def test_duplicate_profiles_do_not_make_documented_name_ambiguous(library, services):
    library.save_profile(dict(name="Mei", aliases=[]))
    # Older libraries may already contain duplicate aliases. Do not guess which
    # identity owns a new report even though new duplicates are now rejected.
    with library.connect() as db:
        db.execute("INSERT INTO patients VALUES (?, ?, NULL, ?, ?)",
                   ("legacy-duplicate", "Another member", '["Mei"]', "2026-10-27"))
    file = pending(library)
    FilingWorkflow(library).run(file["id"])
    member = library.get(file["id"])["metadata"]["member"]
    assert member["status"] == "known"
    assert member["values"] == [dict(value="Mei", quote=TEXT)]


def test_competing_documented_names_remain_unresolved():
    result = filing()
    result.member.values.append(result.member.values[0].model_copy(update={"value": "Lin", "quote": "Patient: Lin"}))
    metadata, _ = validate_filing(result, TEXT + " Patient: Lin", [])
    assert metadata["member"]["status"] == "ambiguous"
    assert metadata["member"]["values"] == []
    assert len(metadata["member"]["candidates"]) == 2


def test_retry_retains_text_identity_and_original(library, monkeypatch, services):
    def fail(*_args):
        raise processing.ProcessingError("Forced classification failure")
    monkeypatch.setattr(processing, "classify", fail)
    file = pending(library)
    workflow = FilingWorkflow(library)
    workflow.run(file["id"])
    failed = library.get(file["id"])
    assert failed["status"] == "failed" and failed["text"] == TEXT
    monkeypatch.setattr(processing, "classify", lambda text, profiles, initial_text: filing())
    workflow.retry(file["id"])
    workflow.run(file["id"])
    assert library.get(file["id"])["status"] == "filed"
    assert len(library.list()) == 1
    assert library.source(file["id"]) == TEXT.encode()


def test_check_failure_is_not_no_issues(library, monkeypatch, services):
    def fail(_text):
        raise processing.ProcessingError("Forced check failure")
    monkeypatch.setattr(processing, "check", fail)
    file = pending(library)
    FilingWorkflow(library).run(file["id"])
    result = library.get(file["id"])
    assert result["status"] == "filed"
    assert result["check_status"] == "failed"
    assert result["check_error"] == "Forced check failure"


def test_unreadable_text_preserves_original(library):
    file = library.create(operation="bad", source=b"\xff\xfe\x00", title="bad.txt", media="text/plain", origin="imported")
    FilingWorkflow(library).run(file["id"])
    result = library.get(file["id"])
    assert result["status"] == "failed" and result["text"] is None
    assert result["extraction_status"] == "failed"
    assert library.source(file["id"]) == b"\xff\xfe\x00"


def test_restart_pending_is_recoverable(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    file = pending(Library(path))
    restarted = Library(path)
    restarted.recover()
    assert restarted.get(file["id"])["status"] == "failed"
    assert restarted.source(file["id"]) == TEXT.encode()


def test_unsupported_evidence_and_extra_tool_authority_are_rejected():
    result = filing()
    result.date.values[0].quote = "not in report"
    with pytest.raises(processing.ProcessingError):
        validate_filing(result, TEXT, [])
    payload = filing().model_dump()
    payload["target_file_id"] = "another-file"
    with pytest.raises(ValueError):
        Filing.model_validate(payload)


def test_repeated_printed_date_is_one_classification():
    result = filing()
    result.date.values.append(result.date.values[0].model_copy())
    metadata, _ = validate_filing(result, TEXT, [])
    assert metadata["date"]["status"] == "known"
    assert len(metadata["date"]["values"]) == 1


def test_competing_dates_remain_unresolved_instead_of_blocking_archive():
    result = filing()
    result.date.values.append(result.date.values[0].model_copy(update={"value": "2026-11", "quote": "Another printed date: 2026-11"}))
    metadata, _ = validate_filing(result, TEXT + " Another printed date: 2026-11", [])
    assert metadata["date"]["status"] == "ambiguous"
    assert metadata["date"]["values"] == []
    assert len(metadata["date"]["candidates"]) == 2


def test_quote_formatting_matches_actual_source_without_rewriting_text():
    result = filing()
    result.symptoms[0].quote = "Symptom: knee pain."
    text = TEXT.replace("knee pain", "knee\n  pain")
    metadata, index = validate_filing(result, text, [])
    assert index["symptoms"][0]["quote"] == "Symptom: knee\n  pain."
    assert metadata["date"]["values"][0]["quote"] == text


def test_paraphrased_index_value_is_still_rejected():
    result = filing()
    result.symptoms[0].value = "leg injury"
    with pytest.raises(processing.ProcessingError, match="symptoms value is not supported"):
        validate_filing(result, TEXT, [])


@pytest.mark.parametrize("category,value,quote", [
    ("treatments", "Start apixaban 5 mg by mouth twice daily for stroke prevention",
     "Start **apixaban 5 mg by mouth twice daily** for stroke prevention"),
    ("diagnoses", "Atrial fibrillation, new onset, rapid ventricular response, hemodynamically stable",
     "1. **Atrial fibrillation, new onset**, rapid ventricular response, hemodynamically stable."),
    ("history", "Prior appendectomy in 1978", "Prior __appendectomy__ in 1978"),
    ("symptoms", "Reports knee pain", "Reports **knee pain**"),
])
def test_clinical_index_values_allow_bold_markers_without_rewriting_evidence(category, value, quote):
    result = filing()
    setattr(result, category, [result.member.values[0].model_copy(update=dict(value=value, quote=quote))])
    _, index = validate_filing(result, TEXT + "\n" + quote, [])
    assert index[category] == [dict(value=value, quote=quote)]


@pytest.mark.parametrize("value,quote", [
    ("Start apixaban 50 mg daily", "Start **apixaban 5 mg** daily"),
    ("Start apixaban 25 mg daily", "Start **apixaban 2.5 mg** daily"),
    ("Sphere 2.50 D", "Sphere **-2.50 D**"),
    ("Dose 5 mg", "Dose **<5 mg**"),
    ("Start apixaban daily", "Start **apixaban 5 mg** daily"),
    ("HER2 negative", "**HER2-positive**"),
    ("Result positive", "Result **positive*"),
])
def test_bold_tolerance_still_rejects_clinical_changes_and_unpaired_markers(value, quote):
    result = filing()
    result.treatments = [result.member.values[0].model_copy(update=dict(value=value, quote=quote))]
    with pytest.raises(processing.ProcessingError, match="treatments value is not supported"):
        validate_filing(result, TEXT + "\n" + quote, [])


def test_bold_tolerance_does_not_accept_a_quote_rewritten_from_saved_text():
    result = filing()
    result.treatments = [result.member.values[0].model_copy(update=dict(
        value="apixaban 5 mg", quote="Start apixaban 5 mg daily"))]
    with pytest.raises(processing.ProcessingError, match="quotes text absent"):
        validate_filing(result, TEXT + "\nStart **apixaban 5 mg** daily", [])


def test_provider_unavailability_is_not_misreported_as_configuration(monkeypatch):
    def handle(request):
        return httpx.Response(503, json={"error": {"message": "High demand", "type": "unavailable"}})
    monkeypatch.setattr(processing, "client", lambda: OpenAI(api_key="test-only", base_url="https://test.invalid/v1",
        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    with pytest.raises(processing.ProcessingError, match="temporarily unavailable.*HTTP 503"):
        processing.classify(TEXT, [])


def test_delete_during_ai_does_not_resurrect(library, monkeypatch, services):
    file = pending(library)
    def classify(_text, _profiles, _initial_text):
        library.delete(file["id"])
        return filing()
    monkeypatch.setattr(processing, "classify", classify)
    FilingWorkflow(library).run(file["id"])
    assert library.list() == []
    with pytest.raises(KeyError):
        library.source(file["id"])


def test_missing_key_fails_truthfully(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(processing.ProcessingError, match="OPENAI_API_KEY"):
        processing.classify(TEXT, [])


def test_sdk_uses_chat_completions_and_constrained_save_tool(monkeypatch):
    report = TEXT + "\nSecond source line."
    initial = "Laboratory results\nGlucose: 105 mg/dL"
    def handle(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert "store" not in body
        assert body["tool_choice"] == {"type": "function", "function": {"name": "save_current_content"}}
        assert body["tools"][0]["function"]["strict"] is True
        assert "target_file_id" not in body["tools"][0]["function"]["parameters"]["properties"]
        # The model must receive actual line breaks, not JSON-escaped report text.
        assert body["messages"][1]["content"][1]["text"] == report
        assert body["messages"][1]["content"][2]["text"].endswith(initial)
        assert "lab_report_quote" in body["tools"][0]["function"]["parameters"]["required"]
        return httpx.Response(200, json=dict(id="chat_test", object="chat.completion", created=0,
            model="test", choices=[dict(index=0, finish_reason="tool_calls", message=dict(role="assistant", content=None,
            tool_calls=[dict(type="function", id="call_test", function=dict(name="save_current_content", arguments=filing().model_dump_json()))]))]))
    monkeypatch.setattr(processing, "client", lambda: OpenAI(api_key="test-only", base_url="https://test.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    assert processing.classify(report, [], initial).title == "Visit report"


@pytest.mark.parametrize("media", ["image/png", "application/pdf"])
def test_photo_and_pdf_use_chat_image_inputs(monkeypatch, media):
    output = io.BytesIO()
    if media == "image/png":
        Image.new("RGB", (10, 10), "white").save(output, format="PNG")
    else:
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(output)
    def handle(request):
        body = json.loads(request.content)
        content = body["messages"][1]["content"]
        assert content[0]["text"] == "Document page 1 of 1"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/")
        assert request.url.path == "/v1/chat/completions"
        assert "store" not in body
        return httpx.Response(200, json=dict(id="chat_test", object="chat.completion", created=0, model="test",
            choices=[dict(index=0, finish_reason="stop", message=dict(role="assistant", content=TEXT))]))
    monkeypatch.setattr(processing, "client", lambda: OpenAI(api_key="test-only", base_url="https://test.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    assert processing.extract(output.getvalue(), media) == TEXT


def terminal(client, file_id):
    for _ in range(100):
        file = client.get(f"/api/files/{file_id}").json()
        if file["status"] not in ("pending", "processing"):
            return file
        time.sleep(.02)
    pytest.fail("Processing did not complete")


def test_http_new_text_without_confirmation_manual_save_and_deletion(tmp_path, services):
    app = create_app(tmp_path / "http.sqlite3")
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        headers = {"Idempotency-Key": "new-text"}
        assert client.get("/api/files").json() == []
        response = client.post("/api/texts", headers=headers, json=dict(title="Draft", text=TEXT))
        assert response.status_code == 202
        file_id = response.json()["id"]
        file = terminal(client, file_id)
        assert client.post("/api/texts", headers=headers, json=dict(title="Draft", text=TEXT)).json()["id"] == file_id
        saved = client.put(f"/api/files/{file_id}/manual", json=dict(revision=file["revision"], text="User correction", date="2026", department=[], disease=[]))
        assert saved.status_code == 200
        assert saved.json()["check_status"] == "stale"
        assert saved.json()["initial_text"] == TEXT
        assert "151" not in json.dumps(saved.json()["index"])
        assert client.get(f"/api/files/{file_id}/original").content == TEXT.encode()
        assert client.put(f"/api/files/{file_id}/manual", json=dict(revision=file["revision"], text="Stale edit")).status_code == 409
        assert client.delete(f"/api/files/{file_id}").status_code == 204
        assert client.get(f"/api/files/{file_id}/original").status_code == 404
        assert client.get("/api/files").json() == []


@pytest.mark.parametrize("name", ["Mei", "Corrected patient"])
def test_manual_save_accepts_name_without_profile_and_preserves_unchanged_evidence(tmp_path, services, name):
    app = create_app(tmp_path / "names.sqlite3")
    with TestClient(app) as client:
        file = pending(app.state.library)
        FilingWorkflow(app.state.library).run(file["id"])
        file = client.get(f"/api/files/{file['id']}").json()
        response = client.put(f"/api/files/{file['id']}/manual", json=dict(
            revision=file["revision"], text=file["text"], member_name=name,
            date="2026-10", department=["内科"], disease=[]))
        assert response.status_code == 200
        saved = response.json()
        member = saved["metadata"]["member"]
        assert member["status"] == "known"
        assert member["values"][0]["value"] == name
        assert saved["archive"]["patient_name"] == name
        assert client.get("/api/profiles").json() == []
        if name == "Mei":
            assert member == file["metadata"]["member"]
        else:
            assert member["provenance"] == "user_supplied"
            assert member["values"][0]["quote"] == ""


def test_source_save_failure_does_not_claim_pending(tmp_path, monkeypatch):
    app = create_app(tmp_path / "failure.sqlite3")
    def fail(**_args):
        raise sqlite3.OperationalError("Forced storage failure")
    monkeypatch.setattr(app.state.library, "create", fail)
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        response = client.post("/api/imports", files={"file": ("report.txt", TEXT.encode())},
            headers={"Idempotency-Key": "upload"})
        assert response.status_code == 503
        assert "id" not in response.json()
        assert client.get("/api/files").json() == []


def test_final_save_failure_keeps_work_retryable(library, services, monkeypatch):
    original_change = library.change
    failed = False
    def change(file_id, edit):
        def apply(record):
            nonlocal failed
            edit(record)
            if record["status"] == "filed" and not failed:
                failed = True
                raise sqlite3.OperationalError("Forced final save failure")
        return original_change(file_id, apply)
    monkeypatch.setattr(library, "change", change)
    file = pending(library)
    workflow = FilingWorkflow(library)
    workflow.run(file["id"])
    record = library.get(file["id"])
    assert record["status"] == "failed" and record["text"] == TEXT
    assert record["metadata"] is None
    assert library.source(file["id"]) == TEXT.encode()
    workflow.retry(file["id"])
    workflow.run(file["id"])
    assert library.get(file["id"])["status"] == "filed"
    assert len(library.list()) == 1


@pytest.mark.parametrize("filename,media", [("photo.jpg", "image/jpeg"), ("scan.pdf", "application/pdf"), ("notes.txt", "text/plain")])
def test_http_uploaded_sources_keep_one_identity(tmp_path, services, monkeypatch, filename, media):
    monkeypatch.setattr(processing, "extract", lambda source, media: TEXT)
    app = create_app(tmp_path / "upload.sqlite3")
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        headers = {"Idempotency-Key": "same-upload"}
        content = b"synthetic adapter fixture"
        result = client.post("/api/imports", headers=headers, files={"file": (filename, content, media)})
        assert result.status_code == 202
        file_id = result.json()["id"]
        saved = terminal(client, file_id)
        assert saved["status"] == "filed" and saved["media"] == media
        assert client.get(f"/api/files/{file_id}/original").content == content
        replay = client.post("/api/imports", headers=headers, files={"file": (filename, content, media)})
        assert replay.json()["id"] == file_id
        assert len(client.get("/api/files").json()) == 1
