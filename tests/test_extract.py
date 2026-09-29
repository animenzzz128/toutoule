from pathlib import Path

import pytest

from toutoule.extract import PROMPT_VERSION, load_prompt, normalize_text, quote_in_source

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
