"""Red-flag rules (tech spec §4): deterministic checks that decide eligibility.

The model extracts and cites; these rules decide (ADR-004). Every rule is a pure function:
its result depends only on its arguments, and it reads no database, no clock and no
settings. So the same extraction always gets the same flags, and a rule can be tested in
one line with no setup.

A field with stated=False never fires a rule. Unknown is shown to the human, never used to
exclude a job.
"""

from typing import Literal, Self

from pydantic import BaseModel

from toutoule.config import Settings
from toutoule.schemas import ExtractedField, Extraction

Market = Literal["US", "CN"] | None  # None means unknown, and never fires R1
RuleId = Literal["R1", "R2", "R3", "R4", "R5", "R6"]
Severity = Literal["HARD", "SCARCE", "URGENT"]


class OwnerProfile(BaseModel):
    """The facts about the owner that the rules compare each job against."""

    requires_sponsorship: bool
    graduation: tuple[int, int]  # (year, month). Tuples compare element by element.
    degree: Literal["bachelor", "master", "phd"]

    # A classmethod is called on the class itself, OwnerProfile.from_settings(...), not on
    # an instance. It is the usual way to write a second constructor.
    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        year, month = settings.owner_graduation.split("-")  # validated YYYY-MM in config
        return cls(
            requires_sponsorship=settings.owner_requires_sponsorship,
            graduation=(int(year), int(month)),
            degree=settings.owner_degree,
        )


class RedFlag(BaseModel):
    """One rule that fired for one job, with the posting's own words as evidence."""

    rule_id: RuleId
    severity: Severity
    field_path: str  # e.g. "critical.visa_sponsorship"
    evidence: str  # the field's verbatim quote, unchanged
    message: str  # one plain English sentence for the digest and the app


def _stated_value(field: ExtractedField) -> str:
    """The value of a stated field. schemas.py guarantees it is a non-empty string."""
    if field.value is None:
        raise ValueError("a stated field has no value; schemas.py should have rejected it")
    return field.value


def _flag(
    rule_id: RuleId, severity: Severity, field_path: str, field: ExtractedField, message: str
) -> RedFlag:
    """Build a flag for a stated field, copying its evidence unchanged."""
    if field.evidence is None:
        raise ValueError(f"{field_path} is stated but has no evidence")
    return RedFlag(
        rule_id=rule_id,
        severity=severity,
        field_path=field_path,
        evidence=field.evidence,
        message=message,
    )


def rule_r1_visa(extraction: Extraction, profile: OwnerProfile, market: Market) -> RedFlag | None:
    """R1 HARD: the posting says "no" sponsorship, the job is in the US, the owner needs it."""
    field = extraction.critical.visa_sponsorship
    if not field.stated:
        return None
    # "conditional" is not "no", and an unknown market is not the US.
    if field.value == "no" and market == "US" and profile.requires_sponsorship:
        return _flag(
            "R1",
            "HARD",
            "critical.visa_sponsorship",
            field,
            "The posting says it does not sponsor visas, and you need sponsorship for a US role.",
        )
    return None


def rule_r4_cap(extraction: Extraction) -> RedFlag | None:
    """R4 SCARCE: the posting limits how many applications one candidate may send."""
    field = extraction.critical.application_cap
    if not field.stated:
        return None
    return _flag(
        "R4",
        "SCARCE",
        "critical.application_cap",
        field,
        f"Applications are capped ({field.value}), so spend this one deliberately.",
    )
