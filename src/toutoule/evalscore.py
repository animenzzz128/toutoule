"""The pure scorer for Task 1.7 (05_EVAL_SPEC.md §2): no API calls, no database.

Both the 投投乐 pipeline and the plain-prompt baseline convert their answers into
SystemOutput, a shape this module never has to special-case. score_case() then compares
one SystemOutput against one hand label and produces a FieldResult per critical/important
field; compute_metrics() turns those into the tiered report.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from toutoule import schemas

CRITICAL_FIELDS = (
    "deadline",
    "visa_sponsorship",
    "graduation_window",
    "application_cap",
    "materials_required",
)
IMPORTANT_FIELDS = (
    "location",
    "work_model",
    "language_requirement",
    "start_date",
    "degree_requirement",
)


@dataclass
class FieldOutput:
    """One field as a system answered it: schemas.ExtractedField, without the pydantic class."""

    stated: bool
    value: str | None
    evidence: str | None


@dataclass
class SystemOutput:
    """The neutral shape both systems convert into before scoring.

    `fields` holds all 10 critical+important fields by name. Evidence may be None even
    when stated=True: the plain-prompt baseline has no evidence requirement at all.
    """

    fields: dict[str, FieldOutput]
    skills: list[str]
    responsibilities: list[str]
    team_or_function: str | None
    failed: bool = False


def from_extraction(extraction: schemas.Extraction) -> SystemOutput:
    """Convert one pipeline Extraction into a SystemOutput."""
    fields: dict[str, FieldOutput] = {}
    for group_name, names in (("critical", CRITICAL_FIELDS), ("important", IMPORTANT_FIELDS)):
        group = getattr(extraction, group_name)
        for name in names:
            field = getattr(group, name)
            fields[name] = FieldOutput(stated=field.stated, value=field.value, evidence=field.evidence)
    return SystemOutput(
        fields=fields,
        skills=list(extraction.reference.skills),
        responsibilities=list(extraction.reference.responsibilities),
        team_or_function=extraction.reference.team_or_function,
    )


def failed_output() -> SystemOutput:
    """A failed extraction (ExtractionFailed): everything not stated, so it scores as
    missed, never as a hallucination — it never claimed a value to begin with."""
    fields = {
        name: FieldOutput(stated=False, value=None, evidence=None)
        for name in (*CRITICAL_FIELDS, *IMPORTANT_FIELDS)
    }
    return SystemOutput(fields=fields, skills=[], responsibilities=[], team_or_function=None, failed=True)


# --- normalize_value ------------------------------------------------------------------

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCT = re.compile(r"[.,;:!?。，；：！？]+$")
_GRADUATION_YEAR = re.compile(r"^(\d{4})届$")

# Fixed phrasing conventions already decided in data/eval/README.md ("Patterns the prompt
# leaves open"). Each maps a source-language span a system might echo verbatim to the
# canonical English value the labels use. Nothing else goes in this table: a value format
# decision (like "本科以上" -> "Bachelor's or above") is not a phrase alias and goes through
# data/eval/equivalences.csv instead, case by case.
ALIASES: dict[tuple[str, str], str] = {
    ("deadline", "滚动招聘"): "rolling basis",
    ("deadline", "招满即止"): "until filled",
    ("start_date", "滚动招聘"): "rolling basis",
    ("start_date", "招满即止"): "until filled",
}


def _basic_normalize(value: str) -> str:
    """NFKC, casefold, strip, collapse whitespace, strip trailing punctuation.

    casefold() is a more aggressive lowercase: it also folds characters like German ß to
    "ss" so that case-insensitive comparison is consistent across languages. We only need
    it here for the ASCII- and CJK-mixed short values these fields hold.
    """
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = _WHITESPACE.sub(" ", value)
    return _TRAILING_PUNCT.sub("", value).strip()


def normalize_value(field: str, value: str | None) -> str | frozenset[str] | None:
    """Normalize one field's value for comparison. None in, None out.

    Returns a frozenset for `location` (order-insensitive city set) and a plain string for
    everything else, including dates — compared as written, never completed with a year.
    """
    if value is None:
        return None

    key = unicodedata.normalize("NFKC", value).strip()
    graduation_match = _GRADUATION_YEAR.match(key) if field == "graduation_window" else None
    if graduation_match:
        return _basic_normalize(f"{graduation_match.group(1)} graduates")
    alias = ALIASES.get((field, key))
    if alias is not None:
        return _basic_normalize(alias)

    if field == "location":
        parts = re.split(r"[/,]", value)
        return frozenset(_basic_normalize(part) for part in parts if _basic_normalize(part))
    return _basic_normalize(value)
