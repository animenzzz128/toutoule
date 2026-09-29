"""The extraction contract (tech spec §3): what the model must return for one job posting.

Every field says whether the source actually stated it, and if so, quotes the source.
These rules are checked here, in code, so a model that ignores its prompt still fails.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

SCHEMA_VERSION = "1.0"


class _StrictModel(BaseModel):
    """Base for every schema model: unknown keys are an error, not silently dropped."""

    model_config = ConfigDict(extra="forbid")


class ExtractedField(_StrictModel):
    """One extracted value, with its statedness flag and a verbatim quote as evidence."""

    value: str | None
    stated: bool
    evidence: str | None

    @model_validator(mode="after")
    def _check_statedness(self) -> Self:
        # Not stated means nothing else is filled in: no guessed value, no quote.
        if not self.stated:
            if self.value is not None or self.evidence is not None:
                raise ValueError("stated is false, so value and evidence must both be null")
            return self
        # Stated means a real value and a real quote. Blank strings count as missing.
        if self.value is None or not self.value.strip():
            raise ValueError("stated is true, so value must be a non-empty string")
        if self.evidence is None or not self.evidence.strip():
            raise ValueError("stated is true, so evidence must be a non-empty quote")
        # Whether the quote really appears in the source is checked in Task 1.4
        # (extract.py), because that check needs the source text, which this model
        # does not have.
        return self


# Fields that the red-flag rules (tech spec §4) compare against a fixed vocabulary.
# The allowed values are part of the type, so they also appear in the JSON schema the
# model is given. Case is strict: "Yes" is rejected, not quietly lowercased.


class VisaSponsorshipField(ExtractedField):
    """Visa sponsorship: "yes", "no" or "conditional" when stated."""

    value: Literal["yes", "no", "conditional"] | None


class WorkModelField(ExtractedField):
    """Work model: "onsite", "hybrid" or "remote" when stated."""

    value: Literal["onsite", "hybrid", "remote"] | None


class CriticalFields(_StrictModel):
    """Fields where a wrong value can cost an application. Target: 0% hallucination."""

    deadline: ExtractedField
    visa_sponsorship: VisaSponsorshipField
    graduation_window: ExtractedField
    application_cap: ExtractedField
    materials_required: ExtractedField


class ImportantFields(_StrictModel):
    """Fields that shape fit and logistics."""

    location: ExtractedField
    work_model: WorkModelField
    language_requirement: ExtractedField
    start_date: ExtractedField
    degree_requirement: ExtractedField


class ReferenceFields(_StrictModel):
    """Context for scoring and rewrites. No evidence needed; measured by recall."""

    skills: list[str]
    responsibilities: list[str]
    team_or_function: str | None


class Extraction(_StrictModel):
    """Everything extracted from one job posting. Stored in extractions.payload_json."""

    schema_version: str
    prompt_version: str
    company: str
    title: str
    critical: CriticalFields
    important: ImportantFields
    reference: ReferenceFields
