"""The How it works page: the pipeline, the measured results, and what they do not claim.

Every sentence and number here is copied from README.md, so the page cannot claim more than
the README does; a test checks that each number on this page appears there. Links point at
GitHub, because the deployed app serves no docs/ folder for a relative link to reach.
"""

import streamlit as st

DOCS = "https://github.com/animenzzz128/toutoule/blob/main/docs"

INTRO = (
    "TouTouLe reads a pasted job description and pulls out the fields that decide whether a "
    "posting is worth an application, each with a quote from the posting that code checks "
    "against the source. Deterministic rules then flag hard ineligibility, and the posting "
    "is scored against my three résumé versions. A job only goes into my tracker once I've "
    "approved it. Nothing is ever submitted for me."
)

STEPS = [
    (
        "Extract with evidence",
        "The model fills a fixed Pydantic schema. Every stated field carries a verbatim quote, "
        'and "Not stated" is a value of its own. The same text pasted twice makes no second '
        "model call.",
    ),
    (
        "Verify in code",
        "Each quote must appear in the posting, after formatting-only normalization, and each "
        'required-materials item must be named in its own quote. A field that fails becomes "Not '
        'stated" and is logged. '
        f"See [ADR-003]({DOCS}/adr/003-structured-output-with-verification.md).",
    ),
    (
        "Rules decide eligibility",
        "Six deterministic rules flag visa, graduation-window, degree and deadline problems and "
        "application caps. A field that isn't stated never excludes a job, and approving past a "
        "HARD flag needs explicit confirmation. "
        f"See [ADR-004]({DOCS}/adr/004-rules-decide-eligibility.md).",
    ),
    (
        "Score fit, then decide",
        "The model rates three dimensions for each résumé version, and code computes the 0–100 "
        "total, checks both quotes of every evidence pair, and recommends a version. Approve the "
        "job, or reject it with one of five structured reasons.",
    ),
]

RESULTS = f"""
The same 50 real job descriptions were run through a plain-prompt baseline (same model,
same field definitions, no schema, no evidence, no verification) and through the pipeline.

| Metric | Target | Plain-prompt baseline | v1 | v4 shipped (derived / fresh) | Met? |
|---|---|---|---|---|---|
| Critical hallucination | 0 / 249 | 20 / 249 (8.0%) | 14 / 249 (5.6%) | 6 / 249 (2.4%) · 8 / 249 (3.2%) | No |
| Critical false negative | ≤ 10% of 67 | 5 / 67 (7.5%) | 13 / 67 (19.4%) | 5 / 67 (7.5%) · 6 / 67 (9.0%) | **Yes** |
| Critical accuracy | ≥ 95% of stated fields | 54 / 57 (94.7%) | 47 / 50 (94.0%) | 55 / 62 (88.7%) · 54 / 57 (94.7%) | No |
| Important accuracy | ≥ 90% of stated fields | 61 / 133 (45.9%) | 45 / 136 (33.1%) | 51 / 131 (38.9%) · 43 / 130 (33.1%) | No |
| Reference recall | ≥ 80% of 552 | 353 / 552 (63.9%) | 254 / 552 (46.0%) | 250 / 552 (45.3%) · 256 / 552 (46.4%) | No |
| Match score within ±10 of my score | 14 / 20 (70%) | — | — | 3 / 20 (15%); constant-guess floor 10 / 20 (50%) | No |

What improved is fabrication: values with no basis in the posting fell from 17 of the
baseline's 20 critical hallucinations to 3 of 6 (derived) and 5 of 8 (fresh) in v4.
Every version, hypothesis and result: [iteration log]({DOCS}/eval/iteration_log.md).
"""  # noqa: E501 — a Markdown table row cannot be wrapped

DOES_NOT_CLAIM = f"""
- **Not zero hallucination.** The shipped version still has 6–8 of 249 critical fields
  hallucinated (invented, or a real quote attached to the wrong field).
- **The match score does not agree with my own ratings** (3 / 20). Read it as résumé fit
  only.
- **No held-out set.** Prompts were tuned on the same 50 postings they're scored on, so
  these results may overstate performance on new postings.
- **Labels are model-drafted and owner-reviewed** ([D-008]({DOCS}/06_DECISION_LOG.md)). A
  model from another family drafted them. I labeled five cases blind first as a check
  (22 of 25 critical fields agreed; the 3 disagreements were my errors), and every
  critical-field disagreement was checked against the posting before it counted.
- **One candidate, one market, one cycle.** There's no claim of generalization beyond
  campus recruiting, and none about interview or offer rates. 20 of the 50 postings are
  China platform / e-commerce, my primary market.
- **Coverage is incomplete by design.** WeChat-only postings sit outside the compliance
  boundary and are pasted by hand.
- **Not built yet:** daily discovery, the email digest and ranking from reject reasons are
  planned for M2/M3. Rewrite suggestions (Task 1.10) moved after M1.
"""


def main() -> None:
    st.title("How it works")
    st.markdown(INTRO)

    for column, (number, (heading, text)) in zip(
        st.columns(len(STEPS)), enumerate(STEPS, start=1), strict=True
    ):
        with column.container(border=True, key=f"card-step-{number}"):
            st.markdown(f"**{number} · {heading}**")
            st.markdown(text)

    st.header("Results")
    st.markdown(RESULTS)
    st.header("What this does not claim")
    st.markdown(DOES_NOT_CLAIM)


main()
