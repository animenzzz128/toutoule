import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from toutoule import models, schemas
from toutoule.db import get_engine, get_session_factory, init_db
from toutoule.extract import (
    PROMPT_VERSION,
    ExtractionFailed,
    extract_job,
    load_prompt,
    normalize_text,
    quote_in_source,
    request_extraction,
)

FIXTURE = Path(__file__).parent / "fixtures" / "extraction_valid.json"
MODEL = "claude-test-model"


class FakeClient:
    """Stands in for anthropic.Anthropic. No network: it returns the answers it was given,
    in order, and records every request so tests can inspect what would have been sent."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []
        self.messages = self  # so that client.messages.create(...) lands on create below

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.answers.pop(0))],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=300),
            stop_reason="end_turn",
        )


@pytest.fixture
def valid_answer() -> dict[str, Any]:
    """The valid extraction fixture as a dict, for tests to modify."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# A posting that contains every quote in the fixture, with the formatting noise real pages
# have: line breaks inside sentences and a non-breaking space.
SOURCE = """Hexa Commerce (fictional) 2027届校招 - AI产品经理 / AI Product Manager, Campus 2027
网申截止时间：2026年10月31日
Open to candidates graduating between September 2026 and
August 2027. Each candidate may apply to at most 2 positions.
Base: Hangzhou. This is an on-site role at our Hangzhou campus.
Requirements: Master's degree or above. Fluent in Mandarin and English.
"""


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    """A fresh SQLite file per test, with the tables created. Never the real database.

    The test runs at the `yield`; the session is closed afterwards, even if the test fails.
    """
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    with get_session_factory(engine)() as session:
        yield session


def add_job(session: Session, raw_text: str = SOURCE) -> models.Job:
    source = models.Source(name="manual", tier=3, url="", adapter="manual")
    session.add(source)
    session.flush()  # sends the insert now, so source.id is filled in
    job = models.Job(
        source_id=source.id,
        company="",
        title="",
        url="file:///jd.txt",
        raw_text=raw_text,
        content_hash="not-checked-here",
    )
    session.add(job)
    session.commit()
    return job


def break_statedness(answer: dict[str, Any]) -> str:
    """A copy that says 'not stated' but still carries a value: must fail validation."""
    broken = json.loads(json.dumps(answer))
    broken["critical"]["deadline"]["stated"] = False
    return json.dumps(broken, ensure_ascii=False)


# --- (a) normalization -------------------------------------------------------------------


def test_full_width_colon_matches_ascii_colon() -> None:
    assert quote_in_source("网申截止时间:2026年10月31日", "网申截止时间：2026年10月31日")


def test_line_break_and_non_breaking_space_inside_quote_still_match() -> None:
    source = "Each candidate may\napply to at most 2 positions."

    assert quote_in_source("Each candidate may apply to at most 2 positions", source)


def test_different_date_does_not_match() -> None:
    assert not quote_in_source("10月31日", "网申截止时间：11月30日")


def test_case_is_kept() -> None:
    assert not quote_in_source("master's degree", "Master's degree or above")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("“Hybrid” – 2 days", '"Hybrid" - 2 days'),
        ("it’s — fine", "it's - fine"),
        ("  a \t\r\n  b  ", "a b"),
        ("２０２６", "2026"),
    ],
)
def test_normalize_text_rules(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


# --- prompt version ----------------------------------------------------------------------


def test_prompt_version_comes_from_the_file_tag() -> None:
    assert PROMPT_VERSION == "extract_v1"


def test_load_prompt_splits_tag_from_body(tmp_path: Path) -> None:
    prompt_file = tmp_path / "extract_v9.txt"
    prompt_file.write_text("extract_v9\nDo the thing.\n", encoding="utf-8")

    assert load_prompt(prompt_file) == ("extract_v9", "Do the thing.")


# --- (d), (e) retry ----------------------------------------------------------------------


def test_request_sends_schema_and_posting(valid_answer: dict[str, Any]) -> None:
    client = FakeClient(json.dumps(valid_answer))

    request_extraction(client, MODEL, "the posting text")

    request = client.requests[0]
    assert request["model"] == MODEL
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert "the posting text" in request["messages"][0]["content"]


def test_retry_succeeds_after_one_invalid_answer(valid_answer: dict[str, Any]) -> None:
    client = FakeClient(break_statedness(valid_answer), json.dumps(valid_answer))

    extraction, input_tokens, output_tokens = request_extraction(client, MODEL, "posting")

    assert len(client.requests) == 2
    retry_messages = client.requests[1]["messages"]
    assert retry_messages[1]["role"] == "assistant"  # the previous answer is sent back
    assert "value and evidence must both be null" in retry_messages[2]["content"]
    assert (input_tokens, output_tokens) == (2000, 600)  # summed over both calls
    assert extraction.critical.deadline.value == "2026-10-31"


def test_invalid_json_is_retried_too(valid_answer: dict[str, Any]) -> None:
    client = FakeClient('{"company": "cut off', json.dumps(valid_answer))

    request_extraction(client, MODEL, "posting")

    assert len(client.requests) == 2


def test_second_failure_raises_extraction_failed(valid_answer: dict[str, Any]) -> None:
    client = FakeClient(break_statedness(valid_answer), "not json at all")

    with pytest.raises(ExtractionFailed, match="failed validation twice"):
        request_extraction(client, MODEL, "posting")

    assert len(client.requests) == 2  # exactly one retry, never a third call


def test_every_call_logs_its_tokens(
    valid_answer: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeClient(break_statedness(valid_answer), json.dumps(valid_answer))

    with caplog.at_level("INFO", logger="toutoule.extract"):
        request_extraction(client, MODEL, "posting")

    token_lines = [r.message for r in caplog.records if "input_tokens=1000" in r.message]
    assert len(token_lines) == 2
    assert "output_tokens=300" in token_lines[0] and "stop_reason=end_turn" in token_lines[0]


# --- (b), (c), (e), (f) verification and saving ------------------------------------------


def test_happy_path_saves_one_extraction_and_no_violations(
    session: Session, valid_answer: dict[str, Any]
) -> None:
    job = add_job(session)

    result = extract_job(session, job, FakeClient(json.dumps(valid_answer)), MODEL)

    assert result.critical.deadline.stated is True
    assert session.scalars(select(models.ExtractionViolation)).all() == []
    row = session.scalars(select(models.Extraction)).one()
    assert (row.job_id, row.model, row.prompt_version) == (job.id, MODEL, PROMPT_VERSION)
    assert (row.input_tokens, row.output_tokens) == (1000, 300)
    assert row.payload_json == result.model_dump(mode="json")
    assert job.status == models.JobStatus.EXTRACTED


def test_fabricated_quote_is_downgraded_and_logged(
    session: Session, valid_answer: dict[str, Any]
) -> None:
    job = add_job(
        session, raw_text=SOURCE.replace("网申截止时间：2026年10月31日", "网申截止时间：待定")
    )

    result = extract_job(session, job, FakeClient(json.dumps(valid_answer)), MODEL)

    deadline = result.critical.deadline
    assert (deadline.stated, deadline.value, deadline.evidence) == (False, None, None)
    violation = session.scalars(select(models.ExtractionViolation)).one()
    assert violation.field_path == "critical.deadline"
    assert "网申截止时间：2026年10月31日" in violation.reason
    # Every other field is exactly what the model returned.
    expected = json.loads(json.dumps(valid_answer))
    expected["critical"]["deadline"] = {"value": None, "stated": False, "evidence": None}
    saved = session.scalars(select(models.Extraction)).one().payload_json
    assert saved == expected  # the saved payload is the verified one


def test_downgraded_field_keeps_its_class(session: Session, valid_answer: dict[str, Any]) -> None:
    valid_answer["critical"]["visa_sponsorship"] = {
        "value": "yes",
        "stated": True,
        "evidence": "We sponsor visas",  # not in SOURCE
    }
    job = add_job(session)

    result = extract_job(session, job, FakeClient(json.dumps(valid_answer)), MODEL)

    assert type(result.critical.visa_sponsorship) is schemas.VisaSponsorshipField
    assert result.critical.visa_sponsorship.stated is False


def test_violation_reason_cuts_long_quote(session: Session, valid_answer: dict[str, Any]) -> None:
    valid_answer["important"]["location"]["evidence"] = "x" * 500
    job = add_job(session)

    extract_job(session, job, FakeClient(json.dumps(valid_answer)), MODEL)

    reason = session.scalars(select(models.ExtractionViolation)).one().reason
    assert "x" * 200 in reason and "x" * 201 not in reason


def test_two_failures_mark_job_failed_and_save_nothing(
    session: Session, valid_answer: dict[str, Any]
) -> None:
    job = add_job(session)
    client = FakeClient(break_statedness(valid_answer), break_statedness(valid_answer))

    with pytest.raises(ExtractionFailed):
        extract_job(session, job, client, MODEL)

    session.refresh(job)  # re-read from the database: the status must really be saved
    assert job.status == models.JobStatus.EXTRACTION_FAILED
    assert session.scalars(select(models.Extraction)).all() == []


def test_model_supplied_versions_are_overwritten(
    session: Session, valid_answer: dict[str, Any]
) -> None:
    valid_answer["prompt_version"] = "made_up_v99"
    valid_answer["schema_version"] = "9.9"
    job = add_job(session)

    result = extract_job(session, job, FakeClient(json.dumps(valid_answer)), MODEL)

    assert (result.prompt_version, result.schema_version) == (
        PROMPT_VERSION,
        schemas.SCHEMA_VERSION,
    )
    row = session.scalars(select(models.Extraction)).one()
    assert row.payload_json["prompt_version"] == PROMPT_VERSION
