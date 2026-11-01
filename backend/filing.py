"""Workflow container: routes stage results into library transactions.

Architecture: ../implementation-architecture.svg#O4; stages: import-pipeline.svg.
"""

import json
import re
from uuid import uuid4

from . import processing
from .debug_log import logger
from .storage import Conflict
from .members import match_profile


DIMENSIONS = ("member", "date", "department", "disease")


# View: backend/import-pipeline.svg#B6
# Normalize whitespace and paired legacy bold markers only for value matching.
# Do not normalize clinical signs, doses, numbers or punctuation into different facts.
def evidence_text(text):
    # Ignore paired Markdown bold delimiters only; retain all clinical punctuation.
    text = re.sub(r"(?<![\w*_])(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?![\w*_])", r"\2", text, flags=re.DOTALL)
    return " ".join(text.split())


# View: backend/import-pipeline.svg#B6
# First locate the quote in current source text, then require the proposed value inside it.
# Log rejected proposals for inspection; never accept a plausible-looking unsupported label.
def source_evidence(evidence, text, category):
    try:
        quote, _, _ = processing.locate_quote(text, evidence.quote)
        value = evidence_text(evidence.value)
        if not value or value not in evidence_text(quote):
            raise processing.ProcessingError(f"AI {category} value is not supported by its source quote. Retry is available.")
        return dict(value=evidence.value, quote=quote)
    except processing.ProcessingError as error:
        logger.error("[AI filing evidence rejected]\n%s", json.dumps(dict(
            field=category, value=evidence.value, quote=evidence.quote, error=str(error)),
            ensure_ascii=False, indent=2))
        raise


# View: AGENTS.svg#F2G
# Validate all categories and clinical index evidence before any filing commit.
# Collapse repeated identical values, retain distinct person/date candidates as ambiguous,
# and treat lab-report categorization as an explicit initial-text-based classification.
def validate_filing(result, text, profiles, initial_text=None):
    # import-pipeline.svg#B6: validate evidence/cardinality; profile links are optional.
    metadata = {}
    lab_quote = None
    if result.is_lab_report:
        lab_quote, _, _ = processing.locate_quote(text if initial_text is None else initial_text, result.lab_report_quote)
    for key in DIMENSIONS:
        if key == "department" and lab_quote is not None:
            evidence = dict(value="Laboratory Medicine", quote=lab_quote, source="initial_text")
            metadata[key] = dict(status="known", values=[evidence], candidates=[evidence], provenance="ai_classified")
            continue
        field = getattr(result, key)
        if (field.status == "missing") != (len(field.values) == 0):
            raise processing.ProcessingError("AI filing returned inconsistent missing-field values. Retry is available.")
        metadata[key] = dict(status=field.status, values=[], candidates=[], provenance="documented")
        seen = set()
        for evidence in field.values:
            value = source_evidence(evidence, text, key)
            # Repeating the same printed value is another citation, not another
            # person/date. Distinct supported values remain unresolved below.
            if evidence.value in seen:
                continue
            seen.add(evidence.value)
            if key == "member":
                profile = match_profile(evidence.value, profiles)
                if profile:
                    value["profile_id"] = profile["id"]
            metadata[key]["candidates"].append(value)
        if key in ("member", "date") and len(metadata[key]["candidates"]) > 1:
            # Conflicting identity/date evidence must not block archiving or be
            # accepted as certain merely because the model marked it "known".
            metadata[key]["status"] = "ambiguous"
        if metadata[key]["status"] == "known":
            metadata[key]["values"] = metadata[key]["candidates"]
    index = {}
    for key in ("symptoms", "history", "diagnoses", "treatments"):
        values = getattr(result, key)
        index[key] = [source_evidence(item, text, key) for item in values]
    return metadata, index


# View: implementation-architecture.svg#O4
# Own the progression and guarded commits for one document. Processing functions return
# values; this coordinator decides what becomes durable and which stage failed.
class FilingWorkflow:
    def __init__(self, library):
        self.library = library

    # View: AGENTS.svg#F2
    # Claim → extract → persist text → check → classify → verify → commit.
    # Finally refresh committed archive indexes, including when an intermediate stage fails.
    def run(self, file_id):
        token = str(uuid4())

        # View: backend/import-pipeline.svg#B1
        # Only pending work may claim a new attempt token. A duplicate executor task stops here.
        def claim(record):
            # import-pipeline.svg#B1: claim only pending work and attach an attempt token.
            if record["status"] != "pending":
                raise Conflict("This file is already processing or filed.")
            record.update(status="processing", attempt=token, error=None)

        # View: backend/import-pipeline.svg#B10
        # Route every stage result through a transaction-bound attempt comparison.
        def update(**values):
            # View: backend/import-pipeline.svg#B10
            # A manual save/deletion supersedes the attempt. Stop stale writes instead of
            # allowing late AI output to overwrite or resurrect human-controlled evidence.
            def apply(record):
                # import-pipeline.svg#B10: stale workers must not overwrite a human save.
                if record["attempt"] != token:
                    raise Conflict("Processing was superseded.")
                record.update(**values)
            return self.library.change(file_id, apply)

        try:
            record = self.library.change(file_id, claim)
        except (KeyError, Conflict):
            return
        try:
            if record["text"] is None:
                # import-pipeline.svg#B2: retries reuse available text instead of re-extracting.
                update(stage="extraction")
                text = processing.extract(self.library.source(file_id), record["media"])
                if not text or not text.replace("[unreadable]", "").strip():
                    raise processing.ProcessingError("No usable text was extracted. View the original, Retry, or enter text manually.")
                # import-pipeline.svg#B3: persist initial/current text before further AI calls.
                record = update(text=text, initial_text=text, extraction_status="extracted", extraction_error=None,
                                text_origin="ai_extracted" if record["media"] != "text/plain" else record["origin"])
            text = record["text"]
            initial_text = record["initial_text"] if record["initial_text"] is not None else text
            if max(len(text), len(initial_text)) > processing.MAX_TEXT:
                raise processing.ProcessingError(f"AI processing is limited to {processing.MAX_TEXT:,} characters in this demo; the source and available text are stored.")
            update(stage="checking")
            # import-pipeline.svg#B4: suspected-error checking is separate from classification.
            try:
                concerns = processing.check(text)
                update(check_status="checked", concerns=concerns, check_error=None)
            except processing.ProcessingError as error:
                # import-pipeline.svg#B11: check failure stays visible but filing may continue.
                update(check_status="failed", check_error=str(error))
            update(stage="filing")
            # import-pipeline.svg#B5: request the single allowed metadata save tool.
            profiles = self.library.profiles()
            result = processing.classify(text, profiles, initial_text)
            metadata, index = validate_filing(result, text, profiles, initial_text)
            # The only AI mutation tool is bound to this pending file and attempt.
            # The model supplies metadata, never a target identity or replacement text.
            # import-pipeline.svg#B7: only this successful commit establishes filed status.
            update(title=result.title, metadata=metadata, index=index, index_status="current",
                   status="filed", stage="complete", error=None, attempt=None)
        except (KeyError, Conflict):
            # import-pipeline.svg#B10: deletion or another write invalidated this attempt.
            return  # Deletion/explicit human save won the race. Never resurrect it.
        except Exception as error:
            # import-pipeline.svg#B8: retain source/text and identify the failed stage.
            message = str(error) if isinstance(error, processing.ProcessingError) else "Saving or processing failed. Available work is stored; Retry is available."
            try:
                latest = self.library.get(file_id)
                extra = dict(extraction_status="failed", extraction_error=message) if latest["stage"] == "extraction" else {}
                update(status="failed", error=message, attempt=None, **extra)
            except (KeyError, Conflict):
                pass
        finally:
            # database-schema.svg#D10: rebuild only committed archive revisions.
            self.library.index_pending()

    # View: backend/import-pipeline.svg#B9
    # Retry changes failed status back to pending on the same document, not a new upload.
    def retry(self, file_id):
        # import-pipeline.svg#B9: reuse the existing file identity; never create another row.
        # View: backend/import-pipeline.svg#B9
        # Pending, processing and filed rows are not restarted. Available text and source remain intact.
        def apply(record):
            if record["status"] in ("processing", "pending", "filed"):
                return
            record.update(status="pending", error=None, attempt=None)
        return self.library.change(file_id, apply)
