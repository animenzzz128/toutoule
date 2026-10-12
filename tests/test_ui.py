"""The page's render helpers and theme (Task 1.13), tested without a browser."""

import tomllib
from pathlib import Path

import pytest
import ui
from streamlit import config as streamlit_config

CONFIG = Path(__file__).parents[1] / ".streamlit" / "config.toml"


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("[click](https://evil.example)", r"\[click\]\(https\://evil.example\)"),
        ("![](https://evil.example/pixel.png)", r"\!\[\]\(https\://evil.example/pixel.png\)"),
        (":red[urgent]", r"\:red\[urgent\]"),
        ("$5 to $10", r"\$5 to \$10"),
        ("<script>alert(1)</script>", r"\<script\>alert\(1\)\</script\>"),
        ("**bold** _slanted_", r"\*\*bold\*\* \_slanted\_"),
    ],
)
def test_md_escape_neutralises_links_images_directives_math_html_and_emphasis(
    text: str, escaped: str
) -> None:
    assert ui.md_escape(text) == escaped


def test_md_escape_escapes_a_backslash_so_it_cannot_cancel_the_next_escape() -> None:
    assert ui.md_escape(r"\[x]") == r"\\\[x\]"


@pytest.mark.parametrize(
    "text", ["Applications close on 2026-12-31.", "投递简历，截止日期 10月15日", "Sr. PM - Growth"]
)
def test_md_escape_leaves_ordinary_sentences_and_dates_alone(text: str) -> None:
    assert ui.md_escape(text) == text


def test_field_label_reads_as_words() -> None:
    assert ui.field_label("graduation_window") == "Graduation window"


def test_every_theme_key_is_an_option_the_installed_streamlit_knows() -> None:
    """Streamlit ignores a misspelled key without a word, so the theme would quietly lose it."""
    theme = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]
    known = streamlit_config.get_config_options()

    assert [key for key in theme if f"theme.{key}" not in known] == []
