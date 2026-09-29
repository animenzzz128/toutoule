import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from toutoule.extract import (
    PROMPT_VERSION,
    ExtractionFailed,
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
