"""Tests for the eval-set tooling (Task 1.6).

Every test builds its own eval directory under tmp_path — a fixture pytest hands each test
a fresh, empty, automatically-cleaned-up directory for — so nothing here ever reads or
writes the real data/eval/. The one exception is the acceptance test at the bottom, which
checks the real folder deliberately.
"""

import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from toutoule import evalset
from toutoule.evalset import (
    LabeledField,
    LabeledVisaSponsorshipField,
    check_eval_set,
    load_cases,
    write_blank_labels,
)

CASES_HEADER = [
    "case_id",
    "segment",
    "company",
    "title",
    "url",
    "retrieved_on",
    "language",
    "notes",
]

RAW_TEXT = (
    "Acme Corp is hiring a Product Manager for our e-commerce platform team. The role is "
    "based in Shanghai and follows a hybrid work model. Candidates must hold a bachelor's "
    "degree or above. 网申截止时间：2026年10月31日. We offer visa sponsorship for qualified "
    "candidates. Please submit a resume and a cover letter merged into one anonymized file."
)


@pytest.fixture
def eval_dir(tmp_path: Path) -> Path:
    (tmp_path / "raw").mkdir()
    (tmp_path / "labels").mkdir()
    return tmp_path


def write_cases_csv(eval_dir: Path, rows: list[dict[str, str]], bom: bool = False) -> None:
    encoding = "utf-8-sig" if bom else "utf-8"
    with (eval_dir / "cases.csv").open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASES_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def case_row(**overrides: str) -> dict[str, str]:
    row = {
        "case_id": "cnp-01",
        "segment": "cn_platform",
        "company": "Acme",
        "title": "Product Manager",
        "url": "https://example.com/acme-pm",
        "retrieved_on": "2026-09-20",
        "language": "en",
        "notes": "",
    }
    row.update(overrides)
    return row


def _blank() -> dict:
    return {"value": None, "stated": False, "evidence": None, "ambiguous": False, "note": None}


def _stated(value: str, evidence: str) -> dict:
    return {"value": value, "stated": True, "evidence": evidence, "ambiguous": False, "note": None}


def full_label() -> dict:
    """A label matching RAW_TEXT exactly, including a full-width-colon quote."""
    return {
        "case_id": "cnp-01",
        "company": "Acme",
        "title": "Product Manager",
        "critical": {
            "deadline": _stated("2026-10-31", "网申截止时间:2026年10月31日"),
            "visa_sponsorship": _stated("yes", "visa sponsorship for qualified candidates"),
            "graduation_window": _blank(),
            "application_cap": _blank(),
            "materials_required": _blank(),
        },
        "important": {
            "location": _stated("Shanghai", "based in Shanghai"),
            "work_model": _stated("hybrid", "hybrid work model"),
            "language_requirement": _blank(),
            "start_date": _blank(),
            "degree_requirement": _stated("Bachelor's or above", "bachelor's degree or above"),
        },
        "reference": {"skills": [], "responsibilities": [], "team_or_function": None},
    }


def write_raw(eval_dir: Path, text: str, case_id: str = "cnp-01") -> None:
    (eval_dir / "raw" / f"{case_id}.txt").write_text(text, encoding="utf-8")


def write_label(eval_dir: Path, label: dict, case_id: str = "cnp-01") -> None:
    (eval_dir / "labels" / f"{case_id}.json").write_text(
        json.dumps(label, ensure_ascii=False), encoding="utf-8"
    )


# --- Label schema (reuses the 1.3 validator) ----------------------------------------------


def test_valid_label_passes() -> None:
    evalset.Label.model_validate(full_label())


def test_stated_false_with_value_fails() -> None:
    with pytest.raises(ValidationError, match="value and evidence must both be null"):
        LabeledField(value="yes", stated=False, evidence=None)


def test_stated_true_with_empty_evidence_fails() -> None:
    with pytest.raises(ValidationError, match="evidence must be a non-empty quote"):
        LabeledField(value="yes", stated=True, evidence="")


def test_misspelled_key_fails() -> None:
    payload = full_label()
    payload["critical"]["dealine"] = payload["critical"]["deadline"]  # typo, not a real field

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        evalset.Label.model_validate(payload)


def test_visa_sponsorship_wrong_case_fails() -> None:
    with pytest.raises(ValidationError):
        LabeledVisaSponsorshipField(value="No", stated=True, evidence="We sponsor visas")


# --- check_eval_set: evidence verification -------------------------------------------------


def test_evidence_not_in_raw_text_is_reported(eval_dir: Path) -> None:
    write_cases_csv(eval_dir, [case_row()])
    write_raw(eval_dir, RAW_TEXT)
    label = full_label()
    label["critical"]["application_cap"] = _stated(
        "2 per candidate", "fabricated cap, not in source"
    )
    write_label(eval_dir, label)

    problems = check_eval_set(eval_dir)

    assert any("critical.application_cap" in p and "evidence not found" in p for p in problems)


def test_evidence_matching_despite_fullwidth_punctuation_and_linebreak_is_accepted(
    eval_dir: Path,
) -> None:
    write_cases_csv(eval_dir, [case_row()])
    # The deadline quote in full_label() uses a straight colon; RAW_TEXT uses a full-width
    # one. Here the work_model quote is also split across a line break in the source.
    write_raw(eval_dir, RAW_TEXT.replace("hybrid work model", "hybrid\nwork model"))
    write_label(eval_dir, full_label())

    assert check_eval_set(eval_dir) == []


def test_case_with_no_raw_file_is_reported(eval_dir: Path) -> None:
    write_cases_csv(eval_dir, [case_row()])

    problems = check_eval_set(eval_dir)

    assert any("missing raw file" in p and "cnp-01" in p for p in problems)


# --- eval-init: blank templates --------------------------------------------------------


def test_eval_init_never_overwrites(eval_dir: Path) -> None:
    write_cases_csv(eval_dir, [case_row()])
    existing_label = eval_dir / "labels" / "cnp-01.json"
    existing_label.write_text('{"marker": "do-not-touch"}', encoding="utf-8")

    written, already_existed = write_blank_labels(eval_dir)

    assert (written, already_existed) == (0, 1)
    assert existing_label.read_text(encoding="utf-8") == '{"marker": "do-not-touch"}'


def test_eval_init_writes_blank_template_for_new_case(eval_dir: Path) -> None:
    write_cases_csv(eval_dir, [case_row()])

    written, already_existed = write_blank_labels(eval_dir)

    assert (written, already_existed) == (1, 0)
    label = evalset.load_label("cnp-01", eval_dir / "labels")
    assert label.company == "Acme"
    assert label.critical.deadline.stated is False


# --- cases.csv: BOM and duplicates -----------------------------------------------------


def test_bom_in_cases_csv_is_read_correctly(eval_dir: Path) -> None:
    write_cases_csv(eval_dir, [case_row()], bom=True)

    cases = load_cases(eval_dir / "cases.csv")

    assert cases[0].case_id == "cnp-01"  # not "﻿case_id" mis-parsed as the key


def test_duplicate_case_id_and_url_are_reported(eval_dir: Path) -> None:
    write_cases_csv(
        eval_dir,
        [
            case_row(case_id="cnp-01", url="https://example.com/a"),
            case_row(case_id="cnp-01", url="https://example.com/b"),
            case_row(case_id="cnp-02", url="https://example.com/a"),
        ],
    )

    problems = check_eval_set(eval_dir)

    assert any("duplicate case_id 'cnp-01'" in p for p in problems)
    assert any("duplicate url 'https://example.com/a'" in p for p in problems)


# --- human_scores.csv --------------------------------------------------------------------


def test_human_scores_out_of_range_score_is_reported(eval_dir: Path) -> None:
    write_cases_csv(eval_dir, [case_row()])
    (eval_dir / "human_scores.csv").write_text(
        "case_id,score,reason\ncnp-01,150,strong culture fit\n", encoding="utf-8"
    )

    problems = check_eval_set(eval_dir)

    assert any("human_scores.csv" in p and "score" in p for p in problems)


# --- Acceptance: the real eval set validates (trivially, until cases are added) ------------


def test_real_eval_set_has_no_problems() -> None:
    assert check_eval_set() == []
