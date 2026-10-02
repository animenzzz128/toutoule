"""Red-flag rules (tech spec §4): deterministic checks that decide eligibility.

The model extracts and cites; these rules decide (ADR-004). Every rule is a pure function:
its result depends only on its arguments, and it reads no database, no clock and no
settings. So the same extraction always gets the same flags, and a rule can be tested in
one line with no setup.

A field with stated=False never fires a rule. Unknown is shown to the human, never used to
exclude a job.
"""

import logging
import re
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel
from sqlalchemy.orm import Session

from toutoule import models
from toutoule.config import Settings
from toutoule.extract import normalize_text
from toutoule.schemas import ExtractedField, Extraction

logger = logging.getLogger(__name__)

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


# The two date formats the extraction prompt asks for: "2026-10-31", or "2026-09".
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
# Range separators: " to " (tech spec §3) or " - " (dashes are "-" after normalize_text).
_RANGE_SEPARATOR = re.compile(r" (?:to|-) ")


def _parse_date(text: str) -> date | None:
    """Parse "2026-10-31" into a date. Anything else, e.g. "rolling basis", gives None."""
    # Checked first because fromisoformat also accepts forms like "20261031".
    if not _ISO_DAY.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:  # the right shape but an impossible day, e.g. "2026-02-30"
        return None


def _parse_month(text: str) -> tuple[int, int] | None:
    """Parse "2026-09" or "2026-09-15" into (2026, 9). Anything else gives None."""
    day = _parse_date(text)
    if day is not None:
        return day.year, day.month
    match = _ISO_MONTH.match(text)
    if match is None or not 1 <= int(match[2]) <= 12:
        return None
    return int(match[1]), int(match[2])


def _parse_window(value: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Parse "2026-09 to 2027-08" or "2026-09 - 2027-08" into ((2026, 9), (2027, 8))."""
    parts = _RANGE_SEPARATOR.split(normalize_text(value))
    if len(parts) != 2:
        return None
    start, end = _parse_month(parts[0]), _parse_month(parts[1])
    if start is None or end is None or start > end:
        return None
    return start, end


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


def rule_r2_graduation(extraction: Extraction, profile: OwnerProfile) -> RedFlag | None:
    """R2 HARD: the owner's graduation month is outside the stated window (ends included)."""
    field = extraction.critical.graduation_window
    if not field.stated:
        return None
    value = _stated_value(field)
    window = _parse_window(value)
    if window is None:
        # Could be "2027-06" alone or "before 2027-06": too ambiguous to exclude a job on.
        logger.warning("R2 skipped: cannot read graduation window %r", value)
        return None
    start, end = window
    if start <= profile.graduation <= end:
        return None
    year, month = profile.graduation
    return _flag(
        "R2",
        "HARD",
        "critical.graduation_window",
        field,
        f"You graduate in {year}-{month:02d}, outside the posting's window of {value}.",
    )


# R3 is deliberately narrow (ADR-004): a requirement fires only if, after _normalize_degree,
# it equals one of these entries exactly. Anything else, e.g. "phd preferred", "本科及以上",
# "mba", never fires. Each entry maps to the owner degrees it rules out.
_PHD_ONLY = frozenset({"bachelor", "master"})
_UNDERGRADUATE_ONLY = frozenset({"master", "phd"})
_MASTER_OR_ABOVE = frozenset({"bachelor"})
_EXCLUDING_REQUIREMENTS: dict[str, frozenset[str]] = {
    "phd required": _PHD_ONLY,
    "ph.d. required": _PHD_ONLY,
    "phd only": _PHD_ONLY,
    "phd or above": _PHD_ONLY,
    "doctorate required": _PHD_ONLY,
    "doctoral degree required": _PHD_ONLY,
    "博士及以上": _PHD_ONLY,
    "博士学历": _PHD_ONLY,
    "博士学位": _PHD_ONLY,
    "仅限博士": _PHD_ONLY,
    "要求博士": _PHD_ONLY,
    "undergraduates only": _UNDERGRADUATE_ONLY,
    "undergraduate only": _UNDERGRADUATE_ONLY,
    "bachelor's only": _UNDERGRADUATE_ONLY,
    "仅限本科": _UNDERGRADUATE_ONLY,
    "仅限本科生": _UNDERGRADUATE_ONLY,
    "master's or above": _MASTER_OR_ABOVE,
    "master's required": _MASTER_OR_ABOVE,
    "master's degree required": _MASTER_OR_ABOVE,
    "硕士及以上": _MASTER_OR_ABOVE,
    "硕士研究生及以上": _MASTER_OR_ABOVE,
}


def _normalize_degree(value: str) -> str:
    """Lowercase, straight quotes, single spaces, no trailing period: "PhD  Required." ->
    "phd required", so small formatting differences cannot hide a match.
    """
    return normalize_text(value).lower().removesuffix(".")


def rule_r3_degree(extraction: Extraction, profile: OwnerProfile) -> RedFlag | None:
    """R3 HARD: the degree requirement is on the short list and rules out the owner's degree."""
    field = extraction.important.degree_requirement
    if not field.stated:
        return None
    value = _stated_value(field)
    excluded = _EXCLUDING_REQUIREMENTS.get(_normalize_degree(value), frozenset())
    if profile.degree not in excluded:
        return None
    return _flag(
        "R3",
        "HARD",
        "important.degree_requirement",
        field,
        f"The posting's degree requirement ({value}) rules out your {profile.degree} degree.",
    )


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


# today is a parameter, not date.today(): a rule that read the clock would give different
# answers on different days, and its tests would start failing once a deadline passed.
# 72 hours is counted as 3 calendar days, because a deadline value has no time of day.
URGENT_DAYS = 3


def rule_r5_urgent(extraction: Extraction, today: date) -> RedFlag | None:
    """R5 URGENT: the deadline is an exact date from today up to 3 days ahead."""
    field = extraction.critical.deadline
    if not field.stated:
        return None
    # Relative phrasing ("rolling basis") and month-only deadlines are never urgent.
    deadline = _parse_date(_stated_value(field))
    if deadline is None or not 0 <= (deadline - today).days <= URGENT_DAYS:
        return None
    return _flag(
        "R5",
        "URGENT",
        "critical.deadline",
        field,
        f"The deadline, {deadline.isoformat()}, is {URGENT_DAYS} days away or less.",
    )


def rule_r6_passed(extraction: Extraction, today: date) -> RedFlag | None:
    """R6 HARD: the deadline has passed. A deadline of today is R5, not R6."""
    field = extraction.critical.deadline
    if not field.stated:
        return None
    value = _stated_value(field)
    deadline = _parse_date(value)
    if deadline is not None:
        passed = deadline < today
    else:
        # A month-only deadline has passed only once that whole month is over.
        month = _parse_month(value)
        passed = month is not None and month < (today.year, today.month)
    if not passed:
        return None
    return _flag(
        "R6",
        "HARD",
        "critical.deadline",
        field,
        f"The deadline, {value}, has already passed.",
    )


def evaluate(
    extraction: Extraction, profile: OwnerProfile, market: Market, today: date
) -> list[RedFlag]:
    """Run R1 to R6 in order and return the flags that fired."""
    results = [
        rule_r1_visa(extraction, profile, market),
        rule_r2_graduation(extraction, profile),
        rule_r3_degree(extraction, profile),
        rule_r4_cap(extraction),
        rule_r5_urgent(extraction, today),
        rule_r6_passed(extraction, today),
    ]
    return [flag for flag in results if flag is not None]


def has_hard_flag(flags: list[RedFlag]) -> bool:
    """True if any flag excludes the job from the digest."""
    return any(flag.severity == "HARD" for flag in flags)


def save_red_flags(session: Session, job_id: int, flags: list[RedFlag]) -> None:
    """Add one red_flags row per flag. The caller commits, together with its other work."""
    session.add_all(
        models.RedFlag(
            job_id=job_id,
            rule_id=flag.rule_id,
            severity=models.FlagSeverity(flag.severity),
            evidence=flag.evidence,
        )
        for flag in flags
    )
