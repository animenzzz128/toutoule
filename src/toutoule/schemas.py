"""The extraction contract (tech spec §3): what the model must return for one job posting.

Every field says whether the source actually stated it, and if so, quotes the source.
These rules are checked here, in code, so a model that ignores its prompt still fails.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


# --- Match scoring (tech spec §5, D-010) -------------------------------------------------
#
# Two schemas, not one. ScoreDraft is what the model is allowed to return; MatchResult is
# what code builds from it. The split is what makes D-010 §1 ("the model never outputs the
# total") a rule the code enforces rather than a sentence in a prompt: ScoreDraft has no
# score field, and extra="forbid" turns a model that writes one anyway into a
# ValidationError.


class DimensionScore(_StrictModel):
    """One rated dimension: 0-10 with a one-line reason. The rubric defines the anchors."""

    score: int = Field(ge=0, le=10)
    reason: str = Field(min_length=1)


class Dimensions(_StrictModel):
    """The three dimensions of tech spec §5. Weights live in config, never here."""

    domain_fit: DimensionScore
    skills_overlap: DimensionScore
    # Level and experience only. Visa, location and graduation windows are decided by the
    # red-flag rules, never by a score (D-010 §5, non-negotiable constraint 3).
    seniority_fit: DimensionScore


class PairDraft(_StrictModel):
    """An evidence pair as the model returns it: two quotes, no verdict on either."""

    requirement: str = Field(min_length=1)  # quoted from the posting
    experience: str = Field(min_length=1)  # quoted from the resume


class EvidencePair(PairDraft):
    """A pair after code checked both quotes against their sources.

    verified is set by score.verify_pairs(), never by the model: a model that could mark
    its own quote verified could mark a fabricated one verified too.
    """

    verified: bool = False


class ScoreDraft(_StrictModel):
    """Exactly what one model call must return. No total, no version tags, no verdicts."""

    dimensions: Dimensions
    # min_length/max_length are part of the JSON schema the model is given, as well as
    # being checked here, so "exactly 3" is stated twice and enforced once.
    evidence_pairs: list[PairDraft] = Field(min_length=3, max_length=3)
    gaps: list[str] = Field(min_length=2, max_length=2)


class MatchResult(_StrictModel):
    """One resume version scored against one posting. Stored in scores.payload_json.

    All 3 evidence pairs are kept whatever their verified flag, so a fabricated quote stays
    auditable; the display layer hides the unverified ones and unverified_pairs records how
    many there were (D-010 §3).
    """

    resume_version: Literal["consulting", "strategy_bizops", "ai_product"]
    score: int = Field(ge=0, le=100)  # computed by score.combine(), never by the model
    dimensions: Dimensions
    evidence_pairs: list[EvidencePair] = Field(min_length=3, max_length=3)
    gaps: list[str] = Field(min_length=2, max_length=2)
    unverified_pairs: int = Field(ge=0, le=3)
    # None until score_job() has scored all three versions and can compare them.
    recommended_version: str | None = None
    prompt_version: str
    model: str

    @model_validator(mode="after")
    def _check_unverified_count(self) -> Self:
        # Kept in step with the flags, so the stored count can never drift from the pairs.
        actual = sum(not pair.verified for pair in self.evidence_pairs)
        if self.unverified_pairs != actual:
            raise ValueError(f"unverified_pairs is {self.unverified_pairs}, but {actual} failed")
        return self


# --- Decisions (PRD F10, PD-4) -----------------------------------------------------------
#
# PD-4: a reject reason is a training signal, not UI politeness. It is the feedback for F18
# and the source of the approval-rate trend, so the five reasons are a closed vocabulary
# checked in code — free text would be unusable for either.

RejectReason = Literal[
    "no_sponsorship",
    "wrong_location",
    "wrong_function",
    "already_applied",
    "not_interested",
]

# Display text, kept beside the values so the app never invents its own wording. The keys
# are exactly the RejectReason members; a test holds the two in step.
REJECT_REASON_LABELS: dict[str, str] = {
    "no_sponsorship": "No visa sponsorship",
    "wrong_location": "Wrong location",
    "wrong_function": "Wrong function",
    "already_applied": "Already applied",
    "not_interested": "Not interested",
}

# What a human can decide in the app. These are also the two JobStatus values a decision
# writes to jobs.status, so the action needs no translation on the way to the database.
# "snoozed" is a status the app does not yet offer; it is deliberately not an action here.
DecisionAction = Literal["approved", "rejected"]
