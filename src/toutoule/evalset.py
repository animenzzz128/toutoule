"""Tooling for the hand-labeled eval set (05_EVAL_SPEC.md §3, Task 1.6).

This module only builds and checks the eval set. It never calls the model and never
suggests a label value — the owner labels every case by hand, from the source text alone,
and this code just validates the result.
"""

import csv
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from toutoule import extract, schemas

EVAL_DIR = Path(__file__).parents[2] / "data" / "eval"
MIN_RAW_CHARS = 200

Segment = Literal["cn_platform", "cn_campus", "us_consulting_finance", "us_tech"]
Language = Literal["en", "zh", "bilingual"]

# 05_EVAL_SPEC.md §3 composition targets, amended by D-005.
SEGMENT_TARGETS: dict[str, int] = {
    "cn_platform": 20,
    "cn_campus": 10,
    "us_consulting_finance": 10,
    "us_tech": 10,
}
TOTAL_TARGET = 50
NO_DEADLINE_MIN = 5
BILINGUAL_MIN = 5
AMBIGUOUS_MAX = 8
HUMAN_SCORE_TARGET = 20

_PREFIX_BY_SEGMENT: dict[str, str] = {
    "cn_platform": "cnp",
    "cn_campus": "cnc",
    "us_consulting_finance": "usf",
    "us_tech": "ust",
}


class _StrictModel(BaseModel):
    """Local strict base: unknown keys are an error, not silently dropped.

    Mirrors schemas._StrictModel rather than importing it: the leading underscore there
    marks it private to that module.
    """

    model_config = ConfigDict(extra="forbid")


# --- Case rows (data/eval/cases.csv) ------------------------------------------------------


class CaseRow(_StrictModel):
    """One row of cases.csv, validated on load."""

    case_id: str
    segment: Segment
    company: str
    title: str
    url: str
    retrieved_on: date
    language: Language
    notes: str = ""

    @model_validator(mode="after")
    def _check_case_id_prefix(self) -> Self:
        expected = _PREFIX_BY_SEGMENT[self.segment]
        # Exactly two digits, so filenames sort in order: cnp-01, not cnp-1.
        if not re.fullmatch(rf"{expected}-\d{{2}}", self.case_id):
            raise ValueError(
                f"case_id {self.case_id!r} must look like {expected}-NN (two digits) "
                f"for segment {self.segment!r}"
            )
        return self


def load_cases(path: Path) -> list[CaseRow]:
    """Read cases.csv. Raises FileNotFoundError if missing, ValidationError on a bad row."""
    # utf-8-sig strips a leading BOM if present and behaves like plain utf-8 otherwise —
    # Windows tools often add a BOM, which would otherwise turn "case_id" into a header
    # pydantic doesn't recognize.
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [CaseRow.model_validate(row) for row in csv.DictReader(handle)]


# --- Labels (data/eval/labels/<case_id>.json) ---------------------------------------------


class LabeledField(schemas.ExtractedField):
    """One hand-labeled field: ExtractedField's shape, plus whether it was ambiguous."""

    ambiguous: bool = False
    note: str | None = None


class LabeledVisaSponsorshipField(schemas.VisaSponsorshipField):
    """visa_sponsorship keeps the "yes" | "no" | "conditional" vocabulary when labeled."""

    ambiguous: bool = False
    note: str | None = None


class LabeledWorkModelField(schemas.WorkModelField):
    """work_model keeps the "onsite" | "hybrid" | "remote" vocabulary when labeled."""

    ambiguous: bool = False
    note: str | None = None


class LabeledCriticalFields(_StrictModel):
    deadline: LabeledField
    visa_sponsorship: LabeledVisaSponsorshipField
    graduation_window: LabeledField
    application_cap: LabeledField
    materials_required: LabeledField


class LabeledImportantFields(_StrictModel):
    location: LabeledField
    work_model: LabeledWorkModelField
    language_requirement: LabeledField
    start_date: LabeledField
    degree_requirement: LabeledField


class Label(_StrictModel):
    """One hand-labeled case: data/eval/labels/<case_id>.json."""

    case_id: str
    company: str
    title: str
    critical: LabeledCriticalFields
    important: LabeledImportantFields
    reference: schemas.ReferenceFields


def load_label(case_id: str, labels_dir: Path) -> Label:
    """Read and validate one label file. Raises FileNotFoundError or ValidationError."""
    path = labels_dir / f"{case_id}.json"
    return Label.model_validate_json(path.read_text(encoding="utf-8"))


def blank_label(case: CaseRow) -> Label:
    """A template label: every field stated=false, company/title copied from cases.csv."""
    blank_field = LabeledField(value=None, stated=False, evidence=None)
    blank_visa = LabeledVisaSponsorshipField(value=None, stated=False, evidence=None)
    blank_work_model = LabeledWorkModelField(value=None, stated=False, evidence=None)
    return Label(
        case_id=case.case_id,
        company=case.company,
        title=case.title,
        critical=LabeledCriticalFields(
            deadline=blank_field,
            visa_sponsorship=blank_visa,
            graduation_window=blank_field,
            application_cap=blank_field,
            materials_required=blank_field,
        ),
        important=LabeledImportantFields(
            location=blank_field,
            work_model=blank_work_model,
            language_requirement=blank_field,
            start_date=blank_field,
            degree_requirement=blank_field,
        ),
        reference=schemas.ReferenceFields(skills=[], responsibilities=[], team_or_function=None),
    )


def write_blank_labels(eval_dir: Path) -> tuple[int, int]:
    """Write a blank label for every cases.csv row that doesn't have one yet.

    Never overwrites an existing label file. Returns (written, already_existed).
    """
    labels_dir = eval_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(eval_dir / "cases.csv")
    written = 0
    for case in cases:
        label_path = labels_dir / f"{case.case_id}.json"
        if label_path.exists():
            continue
        label_path.write_text(blank_label(case).model_dump_json(indent=2) + "\n", encoding="utf-8")
        written += 1
    return written, len(cases) - written


# --- Human scores (data/eval/human_scores.csv) ---------------------------------------------


class HumanScoreRow(_StrictModel):
    """One row of human_scores.csv: the owner's manual priority score (05_EVAL_SPEC §4)."""

    case_id: str
    score: int = Field(ge=0, le=100)
    reason: str

    @model_validator(mode="after")
    def _check_reason_not_empty(self) -> Self:
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
        return self


# --- Checking the whole set ----------------------------------------------------------------


def _describe_validation_error(case_id: str, error: ValidationError) -> list[str]:
    lines = []
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"]) or "(whole label)"
        lines.append(f"{case_id}: {where}: {problem['msg']}")
    return lines


def _check_evidence(case_id: str, label: Label, raw_text: str) -> list[str]:
    problems = []
    for group_name in ("critical", "important"):
        group = getattr(label, group_name)
        for field_name in type(group).model_fields:
            labeled_field = getattr(group, field_name)
            if labeled_field.stated and not extract.quote_in_source(
                labeled_field.evidence, raw_text
            ):
                problems.append(
                    f"{case_id}: {group_name}.{field_name} evidence not found in raw text: "
                    f"{labeled_field.evidence!r}"
                )
    return problems


def _check_human_scores(eval_dir: Path, case_ids: set[str]) -> list[str]:
    problems: list[str] = []
    path = eval_dir / "human_scores.csv"
    if not path.exists():
        return problems
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):  # header is line 1
            try:
                parsed = HumanScoreRow.model_validate(row)
            except ValidationError as error:
                for problem in error.errors():
                    where = ".".join(str(part) for part in problem["loc"]) or "(row)"
                    problems.append(
                        f"human_scores.csv line {line_number}: {where}: {problem['msg']}"
                    )
                continue
            if parsed.case_id in seen:
                problems.append(
                    f"human_scores.csv line {line_number}: duplicate case_id {parsed.case_id!r}"
                )
            seen.add(parsed.case_id)
            if parsed.case_id not in case_ids:
                problems.append(
                    f"human_scores.csv line {line_number}: case_id {parsed.case_id!r} "
                    "is not in cases.csv"
                )
    return problems


def check_eval_set(eval_dir: Path = EVAL_DIR) -> list[str]:
    """Every problem with the eval set so far, one plain-English line per problem.

    Never raises: a missing cases.csv means zero cases, not a problem, since the set is
    built incrementally. Safe to run against the real data/eval/ at any point.
    """
    problems: list[str] = []
    try:
        cases = load_cases(eval_dir / "cases.csv")
    except FileNotFoundError:
        cases = []
    except ValidationError as error:
        problems.extend(_describe_validation_error("cases.csv", error))
        cases = []

    for case_id, count in Counter(case.case_id for case in cases).items():
        if count > 1:
            problems.append(f"cases.csv: duplicate case_id {case_id!r} appears {count} times")
    for url, count in Counter(case.url for case in cases).items():
        if count > 1:
            problems.append(f"cases.csv: duplicate url {url!r} appears {count} times")

    raw_dir = eval_dir / "raw"
    labels_dir = eval_dir / "labels"
    raw_ids = {path.stem for path in raw_dir.glob("*.txt")}
    label_ids = {path.stem for path in labels_dir.glob("*.json")}
    case_ids = {case.case_id for case in cases}

    for case in cases:
        if case.case_id not in raw_ids:
            problems.append(f"{case.case_id}: missing raw file data/eval/raw/{case.case_id}.txt")
        if case.case_id not in label_ids:
            problems.append(
                f"{case.case_id}: missing label file data/eval/labels/{case.case_id}.json"
            )
    for orphan in sorted(raw_ids - case_ids):
        problems.append(f"{orphan}: raw file has no matching row in cases.csv")
    for orphan in sorted(label_ids - case_ids):
        problems.append(f"{orphan}: label file has no matching row in cases.csv")

    for case in cases:
        raw_path = raw_dir / f"{case.case_id}.txt"
        if not raw_path.exists():
            continue
        try:
            raw_text = raw_path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            problems.append(f"{case.case_id}: raw file is not valid UTF-8")
            continue
        normalized_len = len(extract.normalize_text(raw_text))
        if normalized_len < MIN_RAW_CHARS:
            problems.append(
                f"{case.case_id}: raw file is only {normalized_len} normalized characters, "
                f"need at least {MIN_RAW_CHARS}"
            )

        label_path = labels_dir / f"{case.case_id}.json"
        if not label_path.exists():
            continue
        try:
            label = load_label(case.case_id, labels_dir)
        except ValidationError as error:
            problems.extend(_describe_validation_error(case.case_id, error))
            continue
        if label.case_id != case.case_id:
            problems.append(
                f"{case.case_id}: label case_id is {label.case_id!r}, expected {case.case_id!r}"
            )
        problems.extend(_check_evidence(case.case_id, label, raw_text))

    problems.extend(_check_human_scores(eval_dir, case_ids))
    return problems


# --- Composition summary ---------------------------------------------------------------


@dataclass
class CompositionSummary:
    segment_counts: dict[str, int]
    language_counts: dict[str, int]
    total: int
    no_deadline_count: int
    ambiguous_count: int
    human_score_count: int


def composition_summary(eval_dir: Path = EVAL_DIR) -> CompositionSummary:
    """Counts used by eval-check to report progress toward the 05_EVAL_SPEC §3 targets."""
    try:
        cases = load_cases(eval_dir / "cases.csv")
    except (FileNotFoundError, ValidationError):
        cases = []

    segment_counts = {segment: 0 for segment in SEGMENT_TARGETS}
    language_counts: dict[str, int] = {"en": 0, "zh": 0, "bilingual": 0}
    for case in cases:
        segment_counts[case.segment] += 1
        language_counts[case.language] += 1

    labels_dir = eval_dir / "labels"
    no_deadline_count = 0
    ambiguous_count = 0
    for case in cases:
        try:
            label = load_label(case.case_id, labels_dir)
        except (FileNotFoundError, ValidationError):
            continue
        if not label.critical.deadline.stated:
            no_deadline_count += 1
        for group_name in ("critical", "important"):
            group = getattr(label, group_name)
            for field_name in type(group).model_fields:
                if getattr(group, field_name).ambiguous:
                    ambiguous_count += 1

    human_scores_path = eval_dir / "human_scores.csv"
    human_score_count = 0
    if human_scores_path.exists():
        with human_scores_path.open(encoding="utf-8-sig", newline="") as handle:
            human_score_count = sum(1 for _ in csv.DictReader(handle))

    return CompositionSummary(
        segment_counts=segment_counts,
        language_counts=language_counts,
        total=len(cases),
        no_deadline_count=no_deadline_count,
        ambiguous_count=ambiguous_count,
        human_score_count=human_score_count,
    )


def target_report(summary: CompositionSummary) -> list[str]:
    """One progress line per target, e.g. "cn_platform: 3/20". Always informational."""
    bilingual = summary.language_counts["zh"] + summary.language_counts["bilingual"]
    lines = [
        f"{segment}: {summary.segment_counts[segment]}/{target}"
        for segment, target in SEGMENT_TARGETS.items()
    ]
    lines.append(f"total: {summary.total}/{TOTAL_TARGET}")
    lines.append(f"no stated deadline: {summary.no_deadline_count}/{NO_DEADLINE_MIN} (target >=)")
    lines.append(f"zh or bilingual: {bilingual}/{BILINGUAL_MIN} (target >=)")
    lines.append(f"ambiguous fields: {summary.ambiguous_count}/{AMBIGUOUS_MAX} (target <=)")
    lines.append(f"human scores: {summary.human_score_count}/{HUMAN_SCORE_TARGET}")
    return lines


def unmet_targets(summary: CompositionSummary) -> list[str]:
    """Targets not yet met, in plain English. Only used by eval-check --final."""
    problems = []
    for segment, target in SEGMENT_TARGETS.items():
        if summary.segment_counts[segment] < target:
            problems.append(
                f"segment {segment} has {summary.segment_counts[segment]}, needs {target}"
            )
    if summary.total < TOTAL_TARGET:
        problems.append(f"total cases is {summary.total}, needs {TOTAL_TARGET}")
    if summary.no_deadline_count < NO_DEADLINE_MIN:
        problems.append(
            f"no-stated-deadline cases is {summary.no_deadline_count}, needs >= {NO_DEADLINE_MIN}"
        )
    bilingual = summary.language_counts["zh"] + summary.language_counts["bilingual"]
    if bilingual < BILINGUAL_MIN:
        problems.append(f"zh/bilingual cases is {bilingual}, needs >= {BILINGUAL_MIN}")
    if summary.ambiguous_count > AMBIGUOUS_MAX:
        problems.append(
            f"ambiguous fields is {summary.ambiguous_count}, must be <= {AMBIGUOUS_MAX}"
        )
    if summary.human_score_count < HUMAN_SCORE_TARGET:
        problems.append(f"human scores is {summary.human_score_count}, needs {HUMAN_SCORE_TARGET}")
    return problems
