"""Saved, sample-profile triage views; reading them needs no client or database."""

import re
from datetime import date
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from toutoule import redflags, triage

DEMO_DIR = Path(__file__).parents[2] / "data" / "demo"


class DemoCase(BaseModel, frozen=True):
    id: str = Field(pattern=r"^[a-z]+-\d{2}$")
    company: str
    title: str
    market: redflags.Market


class DemoRecord(BaseModel, frozen=True):
    case: DemoCase
    view: triage.TriageView
    built_on: date
    extraction_model: str
    score_model: str

    @model_validator(mode="after")
    def sample_only(self) -> Self:
        if self.view.profile != "sample":
            raise ValueError("demo views must use the sample profile")
        if (self.case.company, self.case.title) != (self.view.company, self.view.title):
            raise ValueError("demo metadata must match the triage view")
        return self


def _read(path: Path) -> DemoRecord:
    record = DemoRecord.model_validate_json(path.read_text(encoding="utf-8"))
    if record.case.id != path.stem:
        raise ValueError(f"demo id does not match filename: {path.name}")
    return record


def list_cases() -> list[DemoCase]:
    return [_read(path).case for path in sorted(DEMO_DIR.glob("*.json"))]


def load(case_id: str) -> triage.TriageView:
    if not re.fullmatch(r"[a-z]+-\d{2}", case_id):
        raise ValueError(f"unknown demo case: {case_id!r}")
    path = DEMO_DIR / f"{case_id}.json"
    if not path.is_file():
        raise ValueError(f"unknown demo case: {case_id!r}")
    return _read(path).view
