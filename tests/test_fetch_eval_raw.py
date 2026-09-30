"""Tests for the HTML-to-text conversion used by scripts/fetch_eval_raw.py."""

import importlib.util
from pathlib import Path

# scripts/ is a one-off utility, not part of the src/toutoule package, so it's loaded
# directly from its file path rather than imported as a normal module.
_SPEC = importlib.util.spec_from_file_location(
    "fetch_eval_raw", Path(__file__).parents[1] / "scripts" / "fetch_eval_raw.py"
)
_fetch_eval_raw = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_fetch_eval_raw)
html_to_text = _fetch_eval_raw.html_to_text


def test_html_to_text_converts_block_tags_entities_and_lists() -> None:
    markup = (
        "<div><h2>Role</h2><p>We need someone with 5+ years &amp; a car.</p>"
        "<ul><li>Python</li><li>SQL</li></ul></div>"
    )

    assert html_to_text(markup) == (
        "Role\n\nWe need someone with 5+ years & a car.\n\nPython\n\nSQL"
    )


def test_html_to_text_leaves_chinese_text_unchanged() -> None:
    text = "上海证券交易所2026年员工招聘启事"

    assert html_to_text(f"<p>{text}</p>") == text


def test_html_to_text_collapses_runs_of_blank_lines(tmp_path: Path) -> None:
    fixture = tmp_path / "posting.html"
    fixture.write_text(
        "<div><p>Location: Shanghai</p><br><p>Apply &#39;today&#39;.</p></div>",
        encoding="utf-8",
    )

    markup = fixture.read_text(encoding="utf-8")

    assert html_to_text(markup) == "Location: Shanghai\n\nApply 'today'."


def test_html_to_text_skips_script_and_style_content() -> None:
    markup = "<div><style>.a{color:red}</style><p>Real text</p><script>doStuff()</script></div>"

    assert html_to_text(markup) == "Real text"
