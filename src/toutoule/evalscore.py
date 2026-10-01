"""The pure scorer for Task 1.7 (05_EVAL_SPEC.md §2): no API calls, no database.

Both the 投投乐 pipeline and the plain-prompt baseline convert their answers into
SystemOutput, a shape this module never has to special-case. score_case() then compares
one SystemOutput against one hand label and produces a FieldResult per critical/important
field; compute_metrics() turns those into the tiered report.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from toutoule import evalset, schemas

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
            fields[name] = FieldOutput(
                stated=field.stated, value=field.value, evidence=field.evidence
            )
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
    return SystemOutput(
        fields=fields, skills=[], responsibilities=[], team_or_function=None, failed=True
    )


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


# --- Equivalences (data/eval/equivalences.csv) -----------------------------------------

Equivalence = tuple[str, str | frozenset[str] | None, str | frozenset[str] | None]


def load_equivalences(path: Path) -> set[Equivalence]:
    """Load (field, normalized label value, normalized system value) triples.

    System-independent on purpose: the same table applies to both the pipeline and the
    baseline, and to every case.
    """
    entries: set[Equivalence] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            field = row["field"]
            entries.add(
                (
                    field,
                    normalize_value(field, row["label_value"]),
                    normalize_value(field, row["system_value"]),
                )
            )
    return entries


# --- Adjudications (data/eval/adjudications.csv) ---------------------------------------


class AdjudicationRow(BaseModel):
    """One row of adjudications.csv, validated on load."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    system: str
    field: str
    system_value: str | None
    verdict: Literal["hallucination", "wrong", "missed", "label_error"]
    note: str = ""


def load_adjudications(path: Path) -> list[tuple[int, AdjudicationRow]]:
    """Read adjudications.csv as (line number, row) pairs. Line numbers start at 2 (the
    header is line 1), so a validation error can point the owner at the exact row."""
    rows: list[tuple[int, AdjudicationRow]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, raw in enumerate(csv.DictReader(handle), start=2):
            raw = {**raw, "system_value": raw.get("system_value") or None}
            try:
                rows.append((line_number, AdjudicationRow.model_validate(raw)))
            except ValidationError as error:
                raise ValueError(f"adjudications.csv line {line_number}: {error}") from error
    return rows


# --- score_case --------------------------------------------------------------------------

Outcome = Literal["correct_absent", "correct", "mismatch", "unsupported", "missed", "excluded"]
Verdict = Literal["hallucination", "wrong", "missed", "label_error"]

# Which verdicts make sense for which outcome. A verdict outside this set for its outcome
# is a data-entry error in adjudications.csv, not a judgment call, so it's rejected rather
# than silently applied.
VALID_VERDICTS: dict[str, set[Verdict]] = {
    "unsupported": {"hallucination", "label_error"},
    "mismatch": {"hallucination", "wrong", "label_error"},
    "missed": {"missed", "label_error"},
}


@dataclass
class FieldResult:
    """The scored outcome for one critical/important field of one case."""

    case_id: str
    tier: Literal["critical", "important"]
    field: str
    outcome: Outcome
    label_value: str | None
    label_evidence: str | None
    system_value: str | None
    system_evidence: str | None
    verdict: Verdict | None = None


def _classify(
    field: str, label_field: Any, sys_field: FieldOutput, equivalences: set[Equivalence]
) -> Outcome:
    if not label_field.stated and not sys_field.stated:
        return "correct_absent"
    if not label_field.stated and sys_field.stated:
        return "unsupported"
    if label_field.stated and not sys_field.stated:
        return "missed"
    label_norm = normalize_value(field, label_field.value)
    system_norm = normalize_value(field, sys_field.value)
    if label_norm == system_norm:
        return "correct"
    if (field, label_norm, system_norm) in equivalences:
        return "correct"
    return "mismatch"


def score_case(
    label: evalset.Label,
    output: SystemOutput,
    equivalences: set[Equivalence],
    adjudications: list[tuple[int, AdjudicationRow]],
    system: str,
) -> list[FieldResult]:
    """Score one case's SystemOutput against its hand label.

    `system` names which column of adjudications.csv applies ("pipeline" or "baseline"),
    since one case can be adjudicated differently for each. Fields whose label is
    ambiguous=true are returned as outcome="excluded" and never counted in metrics.
    """
    results: list[FieldResult] = []
    for group_name, names, tier in (
        ("critical", CRITICAL_FIELDS, "critical"),
        ("important", IMPORTANT_FIELDS, "important"),
    ):
        label_group = getattr(label, group_name)
        for name in names:
            label_field = getattr(label_group, name)
            sys_field = output.fields[name]
            if label_field.ambiguous:
                outcome: Outcome = "excluded"
            else:
                outcome = _classify(name, label_field, sys_field, equivalences)

            verdict: Verdict | None = None
            if outcome in VALID_VERDICTS:
                for line_number, row in adjudications:
                    if row.case_id != label.case_id or row.system != system or row.field != name:
                        continue
                    if row.verdict not in VALID_VERDICTS[outcome]:
                        raise ValueError(
                            f"adjudications.csv line {line_number}: verdict {row.verdict!r} "
                            f"is not valid for outcome {outcome!r} ({label.case_id}.{name})"
                        )
                    current = normalize_value(name, sys_field.value)
                    recorded = normalize_value(name, row.system_value)
                    if current == recorded:
                        verdict = row.verdict
                    # else: stale — the system's answer changed since this was adjudicated;
                    # the field needs a new verdict, so it stays pending.

            results.append(
                FieldResult(
                    case_id=label.case_id,
                    tier=tier,
                    field=name,
                    outcome=outcome,
                    label_value=label_field.value,
                    label_evidence=label_field.evidence,
                    system_value=sys_field.value,
                    system_evidence=sys_field.evidence,
                    verdict=verdict,
                )
            )
    return results


# --- Metrics (05_EVAL_SPEC.md §2) -------------------------------------------------------


@dataclass
class Ratio:
    """One reported number: "count / denominator (percent)"."""

    count: int
    denominator: int

    @property
    def percent(self) -> float:
        return (self.count / self.denominator * 100) if self.denominator else 0.0

    def __str__(self) -> str:
        return f"{self.count} / {self.denominator} ({self.percent:.1f}%)"


@dataclass
class Metrics:
    """Critical and important tiers only. Reference recall is computed separately by
    reference_recall() below, since it's not a per-field outcome but a set comparison —
    the caller sums counts/denominators across cases to get the eval-set-wide recall."""

    critical_hallucination: Ratio
    critical_accuracy: Ratio
    critical_false_negative: Ratio
    important_accuracy: Ratio
    important_missed: int
    pending: int
    provisional: bool


def _is_pending(result: FieldResult) -> bool:
    """No confirmed verdict yet. label_error counts as pending too: the label hasn't
    actually been fixed, so the field's true status is still unknown (point 4)."""
    if result.outcome not in ("mismatch", "unsupported", "missed"):
        return False
    return result.verdict is None or result.verdict == "label_error"


def compute_metrics(results: list[FieldResult]) -> Metrics:
    """Tally FieldResults from score_case() (one system, one eval set) into Metrics.

    Before a pending field is adjudicated, an unsupported field counts as a hallucination
    and a mismatch counts as wrong — the conservative default per 05_EVAL_SPEC.md §5 — so
    the provisional numbers never understate the hallucination rate.
    """
    critical = [r for r in results if r.tier == "critical" and r.outcome != "excluded"]
    important = [r for r in results if r.tier == "important" and r.outcome != "excluded"]

    pending = sum(1 for r in critical if _is_pending(r))

    hallucinations = sum(
        1
        for r in critical
        if (r.outcome == "unsupported" and (r.verdict == "hallucination" or _is_pending(r)))
        or (r.outcome == "mismatch" and r.verdict == "hallucination")
    )
    critical_system_stated = sum(
        1 for r in critical if r.outcome in ("correct", "mismatch", "unsupported")
    )
    critical_correct = sum(1 for r in critical if r.outcome == "correct")
    critical_label_stated = sum(
        1 for r in critical if r.outcome in ("correct", "mismatch", "missed")
    )
    critical_missed = sum(1 for r in critical if r.outcome == "missed")

    important_system_stated = sum(
        1 for r in important if r.outcome in ("correct", "mismatch", "unsupported")
    )
    important_correct = sum(1 for r in important if r.outcome == "correct")
    important_missed = sum(1 for r in important if r.outcome == "missed")

    return Metrics(
        critical_hallucination=Ratio(hallucinations, len(critical)),
        critical_accuracy=Ratio(critical_correct, critical_system_stated - hallucinations),
        critical_false_negative=Ratio(critical_missed, critical_label_stated),
        important_accuracy=Ratio(important_correct, important_system_stated),
        important_missed=important_missed,
        pending=pending,
        provisional=pending > 0,
    )


# --- Reference-field recall (05_EVAL_SPEC.md §2) ----------------------------------------


def _is_captured(label_item: str, system_items: list[str]) -> bool:
    """One labeled item counts as captured if a system item says at least as much about
    it, in either direction, after normalization.

    Weaknesses, both deliberate trade-offs: a short or generic label item (e.g. "Excel")
    is "captured" by any system item that merely contains it, inflating recall. Going the
    other way, a system item only counts if it's at least half the label item's length, so
    a vague system item like "data" doesn't capture a specific one like "data analysis and
    SQL" — but a real paraphrase that shares few characters with the label (different
    wording, same meaning) is missed, deflating recall.
    """
    label_norm = _basic_normalize(label_item)
    if not label_norm:
        return False
    for system_item in system_items:
        system_norm = _basic_normalize(system_item)
        if not system_norm:
            continue
        if label_norm in system_norm:
            return True
        if system_norm in label_norm and len(system_norm) >= len(label_norm) / 2:
            return True
    return False


def reference_recall(label: evalset.Label, output: SystemOutput) -> Ratio:
    """Recall over skills, responsibilities and team_or_function combined."""
    label_items = [*label.reference.skills, *label.reference.responsibilities]
    if label.reference.team_or_function:
        label_items.append(label.reference.team_or_function)
    system_items = [*output.skills, *output.responsibilities]
    if output.team_or_function:
        system_items.append(output.team_or_function)
    captured = sum(1 for item in label_items if _is_captured(item, system_items))
    return Ratio(captured, len(label_items))
