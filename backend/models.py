"""Contracts shared by storage, processing, filing, and HTTP interfaces.

Architecture: ../implementation-architecture.svg#O7 (validated boundary contracts).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# View: implementation-architecture.svg#O7
# Reject unknown tool/request fields instead of accepting hidden model-supplied actions.
# Downstream evidence/revision checks are still required after schema validation.
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    value: str = Field(min_length=1, max_length=500, description="Plain-text source wording contained in quote. Do not add Markdown, HTML/XML tags, or RTF formatting. Paired bold delimiters from older source text may be omitted in the value only. Preserve all words, clinical punctuation, numbers, signs, and units. Do not translate, paraphrase, or join separated passages.")
    quote: str = Field(min_length=1, description="One exact contiguous substring of raw report text, preferably a shorter span without formatting markup. Never add formatting or remove internal source characters. Preserve words, punctuation, capitalization, medical symbols, and units; older source markup must be retained if inside the chosen span.")


class Classification(StrictModel):
    status: Literal["known", "missing", "ambiguous"]
    values: list[Evidence]


# View: backend/import-pipeline.svg#B5
# Constrain the one allowed filing result: categories, evidence-backed clinical terms,
# and an initial-text lab-report decision. The workflow owns the target and commit.
class Filing(StrictModel):
    title: str = Field(min_length=1, max_length=200, description="Short source-grounded title in plain text, without Markdown, HTML/XML tags, or RTF formatting.")
    is_lab_report: bool = Field(description="Determine from the initial extraction whether this document is a laboratory results report. A visit note that only orders, mentions, or discusses lab tests is not a lab report. Return a JSON boolean.")
    lab_report_quote: str = Field(description="If is_lab_report is true, copy one short exact supporting substring from initial text, preferably without formatting markup; never add formatting or remove internal characters. Otherwise return an empty string, not null or the word null.")
    member: Classification
    date: Classification
    department: Classification
    disease: Classification
    symptoms: list[Evidence]
    history: list[Evidence]
    diagnoses: list[Evidence]
    treatments: list[Evidence]


class Concern(StrictModel):
    quote: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=1000, description="Plain-text explanation, without Markdown, HTML/XML tags, or RTF formatting.")


class Check(StrictModel):
    concerns: list[Concern]


class NewText(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    record_id: str | None = None


class RecordCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200, pattern=r"\S")
    patient_id: str | None = None


class DocumentMove(StrictModel):
    record_id: str
    revision: int = Field(ge=1)


class Profile(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list, max_length=20)


# View: src/import/ui-flow.svg#U7
# Human corrections carry the editor revision. An unchanged original/initial extraction
# is stored separately; this request edits only current text and supplied details.
class ManualSave(StrictModel):
    revision: int
    text: str = Field(min_length=1)
    member_id: str | None = None
    member_name: str | None = Field(default=None, max_length=500)
    date: str = ""
    department: list[str] = Field(default_factory=list)
    disease: list[str] = Field(default_factory=list)


# View: src/import/ui-flow.svg#U12
# Bind an expensive check to the exact saved document revision the user reviewed.
class Recheck(StrictModel):
    revision: int = Field(ge=1)


class ConcernReview(StrictModel):
    revision: int = Field(ge=1)
    reviewed: bool


# View: src/import/ui-flow.svg#U15
# Require explicit destructive intent in addition to the browser confirmation.
# This endpoint is not exposed as an AI tool or invoked by ordinary processing.
class LibraryReset(StrictModel):
    confirm: Literal[True]
