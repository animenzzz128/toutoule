"""The page's render helpers and theme (Task 1.13), tested without a browser."""

import tomllib
from pathlib import Path

import pytest
import ui
from streamlit import config as streamlit_config
from streamlit.proto.NewSession_pb2 import CustomThemeConfig
from streamlit.runtime.theme_util import parse_fonts_with_source

from toutoule import redflags, triage

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


def test_the_theme_fonts_parse_the_way_a_browser_session_parses_them() -> None:
    """Fonts are only parsed when a browser connects, so a bad one passes every other check.

    This calls the parser Streamlit runs for each new session. It is internal to Streamlit,
    which is the point: it is the code that raised on the first font setting tried here.
    """
    theme = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]

    message = parse_fonts_with_source(
        CustomThemeConfig(),
        body_font_config=theme.get("font"),
        code_font_config=theme.get("codeFont"),
        heading_font_config=theme.get("headingFont"),
        section="theme",
    )

    assert message.body_font == "Inter"


# --- Flags and summary -------------------------------------------------------------------


def view(flags: list[triage.FlagView]) -> triage.TriageView:
    """A job with two critical fields, one stated, and no scores."""
    critical = [
        triage.FieldView(
            name="deadline", value="2026-12-31", stated=True, evidence="By 2026-12-31."
        ),
        triage.FieldView(name="application_cap", value=None, stated=False, evidence=None),
    ]
    return triage.TriageView(
        job_id=1,
        company="Example Co",
        title="PM",
        url="",
        status="scored",
        critical=critical,
        other=[],
        flags=flags,
        has_hard_flag=False,
        scores=[],
        recommended_version=None,
        profile="sample",
        decision=None,
    )


@pytest.mark.parametrize(
    ("severity", "kind"), [("HARD", "error"), ("SCARCE", "warning"), ("URGENT", "info")]
)
def test_each_severity_has_its_own_banner_and_only_hard_is_red(severity: str, kind: str) -> None:
    assert ui.banner_kind(severity) == kind


def test_a_banner_names_the_rule_that_decided_and_escapes_the_quote() -> None:
    flag = triage.FlagView(rule_id="R4", severity="SCARCE", evidence="One [application](x)")

    text = ui.flag_banner_text(flag)

    assert text.startswith("**SCARCE · R4** — decided by rule R4. ")
    assert redflags.RULE_DESCRIPTIONS["R4"] in text
    assert text.endswith(r"> One \[application\]\(x\)")


def test_the_summary_counts_stated_fields_and_flags_and_says_when_nothing_is_scored() -> None:
    flags = [
        triage.FlagView(rule_id="R1", severity="HARD", evidence=None),
        triage.FlagView(rule_id="R4", severity="SCARCE", evidence=None),
        triage.FlagView(rule_id="R5", severity="URGENT", evidence=None),
    ]

    assert ui.summary_values(view(flags)) == [
        ("Critical fields stated", "1 / 2"),
        ("Rule flags", "1 HARD · 1 SCARCE · 1 URGENT"),
        ("Best résumé fit", "Not scored"),
    ]
    assert ui.summary_values(view([]))[1] == ("Rule flags", "None")
