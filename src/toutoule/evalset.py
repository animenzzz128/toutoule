"""Tooling for the hand-labeled eval set (05_EVAL_SPEC.md §3, Task 1.6).

This module only builds and checks the eval set. It never calls the model and never
suggests a label value — the owner labels every case by hand, from the source text alone,
and this code just validates the result.
"""

import csv
import re
from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from toutoule import schemas

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
