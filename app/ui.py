"""Small render helpers for the Streamlit page (Task 1.13, D-013).

Posting text, quotes, company and title come from outside, so none of them reaches a
Markdown sink as written. They go through st.text and st.code, which show text exactly as
given, or through md_escape first. Cards use native elements rather than HTML strings so
AppTest can read them: the evidence rules stay testable (D-013).
"""

import re
from collections import Counter

import streamlit as st

from toutoule import redflags, triage

# Every character that can open a link, an image, an HTML tag, emphasis, inline code, a
# table cell, or one of Streamlit's own extensions (":red[...]" directives, "$...$" LaTeX).
# A backslash in front makes CommonMark render the character as itself. "." and "-" are
# left alone: they only shape lists at the start of a line, and escaping them would
# clutter every date and sentence for no safety gain.
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!<>|~:$&])")

# A key on st.container becomes the CSS class "st-key-<key>" in the browser, which is how
# this one static rule finds the cards. It holds no outside text, so there is nothing in it
# to escape. The theme has no option for a bordered container's background.
CARD_KEY_PREFIX = "card-"
CARD_CSS = f"<style>[class*='st-key-{CARD_KEY_PREFIX}'] {{ background: #FFFFFF; }}</style>"


def md_escape(text: str) -> str:
    """Text that renders as itself when passed to a Markdown sink (st.markdown, st.error…)."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def field_label(name: str) -> str:
    """'graduation_window' -> 'Graduation window'. Field names are ours, not the posting's."""
    return name.replace("_", " ").capitalize()


def field_card(item: triage.FieldView, key: str) -> None:
    """One extracted field: its value with the verbatim quote, or a Not stated pill.

    A stated field always has a non-empty value and quote, and that quote passed the
    verbatim check in code before it was stored (constraint 1), which is what "Found in
    source" claims. An unstated field shows the pill and nothing else: no value, no quote,
    never a blank (constraint 2).
    """
    with st.container(border=True, key=f"{CARD_KEY_PREFIX}{key}"):
        st.caption(field_label(item.name))
        if not item.stated:
            st.badge("Not stated", color="gray")
            return
        st.text(item.value)
        st.code(item.evidence, language=None, wrap_lines=True)
        st.badge("Found in source", icon=":material/check:", color="primary")


def field_grid(items: list[triage.FieldView], group: str) -> None:
    """Cards two to a row, in the order the schema declares the fields."""
    left, right = st.columns(2)
    for index, item in enumerate(items):
        with left if index % 2 == 0 else right:
            field_card(item, key=f"{group}-{item.name}")


# --- Flags and summary -------------------------------------------------------------------

SEVERITIES = ("HARD", "SCARCE", "URGENT")


def banner_kind(severity: str) -> str:
    """Which st alert draws a flag. One colour per meaning: red is HARD only and amber is
    SCARCE only, so URGENT (the deadline rules) takes the theme's neutral slate."""
    return {"HARD": "error", "SCARCE": "warning"}.get(severity, "info")


def flag_banner_text(flag: triage.FlagView) -> str:
    """The banner names the rule that decided it, so it reads as a rule's call, not the
    model's (constraint 3). The quote comes from the posting, so it is escaped."""
    text = (
        f"**{flag.severity} · {flag.rule_id}** — decided by rule {flag.rule_id}. "
        f"{redflags.RULE_DESCRIPTIONS[flag.rule_id]}"
    )
    if flag.evidence:
        text += f"\n\n> {md_escape(flag.evidence)}"
    return text


def flag_banner(flag: triage.FlagView) -> None:
    getattr(st, banner_kind(flag.severity))(flag_banner_text(flag))


def summary_values(view: triage.TriageView) -> list[tuple[str, str]]:
    """The three numbers at the top of a job: how much the posting states, what the rules
    flagged, and the best résumé fit. Each is a count or a score, never a verdict."""
    stated = sum(item.stated for item in view.critical)
    counts = Counter(flag.severity for flag in view.flags)
    flags = " · ".join(f"{counts[name]} {name}" for name in SEVERITIES if counts[name])
    best = max((item.score for item in view.scores), default=None)
    return [
        ("Critical fields stated", f"{stated} / {len(view.critical)}"),
        ("Rule flags", flags or "None"),
        ("Best résumé fit", "Not scored" if best is None else f"{best} / 100"),
    ]


def summary_strip(view: triage.TriageView) -> None:
    for column, (label, value) in zip(st.columns(3), summary_values(view), strict=True):
        column.metric(label, value, border=True)
