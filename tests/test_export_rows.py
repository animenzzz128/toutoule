"""Row building for the tracker export (Task 1.12, step 2). Pure: no files, no openpyxl.

Every mapping rule in D-011 is asserted here, where it can be read without a spreadsheet.
"""

import json
from datetime import UTC, datetime

import pytest
from postings import extraction_answer, field

from toutoule import export_xlsx, models, schemas
from toutoule.export_xlsx import NOT_STATED, TO_APPLY


def extraction(**critical_overrides: object) -> schemas.Extraction:
    """The shared posting's extraction, with any critical field replaced."""
    payload = json.loads(extraction_answer())
    payload["critical"].update(critical_overrides)
    return schemas.Extraction.model_validate(payload)


def match_result(score: int = 72, version: str = "ai_product") -> schemas.MatchResult:
    """One scored version, already marked as the recommended one."""
    pair = {"requirement": "SQL required", "experience": "Python, SQL", "verified": True}
    return schemas.MatchResult(
        resume_version=version,
        score=score,
        dimensions={
            "domain_fit": {"score": 8, "reason": "same work"},
            "skills_overlap": {"score": 7, "reason": "tools match"},
            "seniority_fit": {"score": 7, "reason": "right level"},
        },
        evidence_pairs=[pair, pair, pair],
        gaps=["no people management", "no payments experience"],
        unverified_pairs=0,
        recommended_version=version,
        prompt_version="score_v1",
        model="claude-sonnet-5-5",
    )


def job(**overrides: object) -> models.Job:
    """A jobs row, unsaved. build_row only reads attributes, so no database is needed."""
    defaults: dict[str, object] = {
        "company": "Example Co",
        "title": "AI Product Manager",
        "url": "https://example.com/job",
        "raw_text": "...",
        "content_hash": "abc",
        "source_id": 1,
        "last_seen_at": datetime(2026, 10, 3, 15, 0, tzinfo=UTC),
    }
    return models.Job(**(defaults | overrides))


def flag(rule_id: str, severity: str) -> models.RedFlag:
    return models.RedFlag(job_id=1, rule_id=rule_id, severity=severity, evidence="quoted")


def cell(row: list[object], header: str) -> object:
    """The value under one header, looked up by name rather than by a magic index."""
    return row[export_xlsx.COLUMNS.index(header)]


# --- the shape of a row ------------------------------------------------------------------


def test_row_has_one_value_per_column() -> None:
    assert len(export_xlsx.build_row(job(), extraction(), match_result(), [])) == 18
    assert len(export_xlsx.COLUMNS) == 18


def test_job_fields_go_where_they_belong() -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(), [])
    assert cell(row, "Company") == "Example Co"
    assert cell(row, "Title") == "AI Product Manager"
    assert cell(row, "Link") == "https://example.com/job"


def test_status_is_always_to_apply() -> None:
    # Only approved jobs are exportable, and "approved, not yet applied" is To Apply.
    row = export_xlsx.build_row(job(), extraction(), match_result(), [])
    assert cell(row, "Status") == TO_APPLY


@pytest.mark.parametrize(
    "header",
    ["Market", "Application Date", "Interview Stage", "Interviewer", "Urgency", "Next Action"],
)
def test_owner_only_columns_are_blank(header: str) -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(), [])
    assert cell(row, header) is None


# --- D-010: fit is not priority ----------------------------------------------------------


def test_match_score_goes_to_candidate_fit_and_priority_stays_blank() -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(score=84), [])
    assert cell(row, "Candidate Fit") == 84
    assert cell(row, "Priority Score") is None


def test_recommended_resume_is_the_stored_version_id() -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(version="strategy_bizops"), [])
    assert cell(row, "Recommended Resume") == "strategy_bizops"


# --- "Not stated" is a first-class value -------------------------------------------------


def test_stated_fields_are_written_verbatim() -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(), [])
    assert cell(row, "Deadline") == "2026-12-31"
    assert cell(row, "Geography") == "New York, NY"


def test_unstated_deadline_becomes_not_stated() -> None:
    row = export_xlsx.build_row(job(), extraction(deadline=field(None, None)), match_result(), [])
    assert cell(row, "Deadline") == NOT_STATED


def test_deadline_text_is_never_parsed() -> None:
    # The posting's own words reach the cell unchanged, whatever shape they are in.
    deadline = field("Rolling until filled", "Rolling until filled")
    row = export_xlsx.build_row(job(), extraction(deadline=deadline), match_result(), [])
    assert cell(row, "Deadline") == "Rolling until filled"


def test_field_text_covers_every_critical_and_important_field() -> None:
    # One rule, ten fields: the helper is written against ExtractedField, not field names.
    stated = schemas.ExtractedField(value="x", stated=True, evidence="x")
    missing = schemas.ExtractedField(value=None, stated=False, evidence=None)
    assert export_xlsx.field_text(stated) == "x"
    assert export_xlsx.field_text(missing) == NOT_STATED


# --- Notes -------------------------------------------------------------------------------


def test_no_flags_leaves_notes_empty() -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(), [])
    assert cell(row, "Notes") is None


def test_flags_are_listed_in_rule_order() -> None:
    flags = [flag("R5", "URGENT"), flag("R4", "SCARCE")]
    row = export_xlsx.build_row(job(), extraction(), match_result(), flags)
    assert cell(row, "Notes") == "toutoule flags: SCARCE R4; URGENT R5"


def test_a_hard_flag_records_that_it_was_overridden() -> None:
    flags = [flag("R1", "HARD"), flag("R5", "URGENT")]
    assert export_xlsx.notes_line(flags) == (
        "toutoule flags: HARD R1; URGENT R5 (approved after HARD confirm)"
    )


def test_non_hard_flags_get_no_confirm_suffix() -> None:
    assert "confirm" not in export_xlsx.notes_line([flag("R4", "SCARCE")])


# --- skills and dates --------------------------------------------------------------------


def test_skills_are_joined_and_an_empty_list_leaves_the_cell_blank() -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(), [])
    assert cell(row, "Main Skills Required") == "SQL"

    bare = extraction()
    bare.reference.skills = []
    blank = export_xlsx.build_row(job(), bare, match_result(), [])
    assert cell(blank, "Main Skills Required") is None


def test_last_verified_is_a_real_date_not_a_string() -> None:
    row = export_xlsx.build_row(job(), extraction(), match_result(), [])
    assert cell(row, "Last Verified") == datetime(2026, 10, 3, 11, 0).date()
    assert isinstance(cell(row, "Last Verified"), type(datetime(2026, 1, 1).date()))


def test_last_verified_uses_new_york_not_utc() -> None:
    # 01:30 UTC on the 6th is still 21:30 on the 5th in New York, which is the date a
    # human reading the tracker means by "last verified".
    late = job(last_seen_at=datetime(2026, 10, 6, 1, 30, tzinfo=UTC))
    row = export_xlsx.build_row(late, extraction(), match_result(), [])
    assert str(cell(row, "Last Verified")) == "2026-10-05"
