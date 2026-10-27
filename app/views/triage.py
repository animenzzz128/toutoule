"""The Triage page (Task 1.11, PRD F10): paste a posting, read the evidence, decide.

A view and nothing else. Every rule it appears to enforce — which reasons a rejection may
carry, when an approval needs confirming, which profile's scores may be shown — lives in
triage.py, where a test can reach it without a browser. Wording that describes a rule
comes from the module that owns the rule, so the page cannot describe one the code no
longer applies.

The sidebar and the page menu live in app/streamlit_app.py, which runs this file.
"""

import anthropic
import resources
import streamlit as st
import ui
from pydantic import ValidationError

from toutoule import config, demo, extract, redflags, score, triage
from toutoule.config import ConfigError, Settings
from toutoule.schemas import REJECT_REASON_LABELS

# Below this, a paste is an empty or failed copy. Sending it would cost tokens and come
# back all "not stated", which looks like a real answer. The same guard the CLI applies.
MIN_POSTING_CHARS = 200

# The market is an explicit choice, never read off the location field (tech spec §4):
# unknown is the default, and it never fires the sponsorship rule.
MARKETS: dict[str, redflags.Market] = {"Unknown": None, "United States": "US", "China": "CN"}

SCORE_CAPTION = (
    "Fit to resume only. Not a priority score and not calibrated to the owner's "
    "judgment; see docs/eval/scoring.md."
)

# Failures with a message worth showing as written. Everything else is caught below and
# shown as its type and message, because a traceback on the page helps nobody.
PIPELINE_ERRORS = (extract.ExtractionFailed, score.ScoringFailed, score.ResumeNotFound, ConfigError)

# The live demo has a monthly API budget; once it is spent, every call fails. The examples
# are saved outputs of the same pipeline (#42), so the page still shows what it does.
API_DOWN = (
    "The live model didn't answer ({error}). The examples below are precomputed and need "
    "no model call."
)
DEMO_NOTICE = (
    "Precomputed example: the saved output of this pipeline on the redacted sample profile. "
    "Nothing on this view calls the model, and there is no decision to record."
)


# --- Paste and triage --------------------------------------------------------------------


def paste_form(session, settings: Settings, use_sample: bool) -> None:  # type: ignore[no-untyped-def]
    """The input form. On success, the new job's id goes into the session state."""
    with st.form("paste"):
        company = st.text_input("Company *", key="company")
        title = st.text_input("Title", key="title")
        url = st.text_input("URL", key="url")
        market = st.selectbox(
            "Market", list(MARKETS), key="market", help="Decides whether rule R1 can fire."
        )
        raw_text = st.text_area("Job description *", height=240, key="posting")
        submitted = st.form_submit_button("Triage", type="primary")
    if not submitted:
        return

    if not company.strip() or not raw_text.strip():
        st.error("Company and job description are both required.")
        return
    length = len(extract.normalize_text(raw_text))
    if length < MIN_POSTING_CHARS:
        st.error(f"That looks too short to be a job description: {length} characters.")
        return

    try:
        with st.spinner("Extracting, checking the rules and scoring…"):
            job_id = triage.run_triage(
                session,
                resources.model_client(settings),
                company,
                title,
                url,
                raw_text,
                sample=use_sample,
                market=MARKETS[market],
                settings=settings,
            )
    except PIPELINE_ERRORS as error:
        st.error(str(error))
        return
    except anthropic.APIError as error:  # budget spent, key revoked, network down
        st.warning(API_DOWN.format(error=type(error).__name__), icon=":material/cloud_off:")
        st.session_state["api_down"] = True
        return
    except Exception as error:  # noqa: BLE001 — a page shows a message, never a traceback
        st.error(f"{type(error).__name__}: {error}")
        return
    st.session_state["job_id"] = job_id
    st.session_state.pop("demo_case", None)  # a live result replaces an example


# --- Precomputed examples ----------------------------------------------------------------


def demo_picker(expanded: bool) -> None:
    """Saved examples that need no API call. Picking one replaces whatever job is shown."""
    try:
        cases = demo.list_cases()
    except (ValueError, ValidationError) as error:  # one bad file must not take the page down
        st.caption(f"The saved examples could not be read: {type(error).__name__}.")
        return
    if not cases:
        return
    labels = {case.id: f"{case.company} · {case.title}" for case in cases}
    with st.expander("Try a sample posting, no API call", expanded=expanded):
        case_id = st.selectbox(
            "Example", list(labels), format_func=labels.__getitem__, key="demo_pick"
        )
        if st.button("Show example"):
            st.session_state.pop("job_id", None)
            st.session_state["demo_case"] = case_id


def show_demo(case_id: str) -> None:
    try:
        view = demo.load(case_id)
    except (ValueError, ValidationError) as error:
        st.error(f"That example could not be loaded: {error}")
        return
    st.info(DEMO_NOTICE, icon=":material/inventory_2:")
    show_result(view)


# --- Result ------------------------------------------------------------------------------


def posting_link(url: str) -> None:
    """A link to the posting, but only to a web address. Anything else, a "javascript:"
    URL for one, is shown as plain text, so pasting a URL can never run code on click."""
    if url.startswith(("https://", "http://")):
        st.link_button("Open the posting", url, icon=":material/open_in_new:")
    else:
        st.text(url)


def red_flag_banners(view: triage.TriageView) -> None:
    st.subheader("Red flags")
    if not view.flags:
        st.write("No red flags from the rules.")
        return
    for flag in view.flags:
        ui.flag_banner(flag)


def evidence_tabs(view: triage.TriageView) -> None:
    # st.tabs draws every tab's contents on each run and only hides the inactive ones, so
    # switching tabs costs nothing and the tests can read all three.
    critical, other, fit = st.tabs(["Critical fields", "All fields", "Résumé fit"])
    with critical:
        ui.field_grid(view.critical, group="critical")
    with other:
        ui.field_grid(view.other, group="other")
    with fit:
        score_section(view)


def score_section(view: triage.TriageView) -> None:
    if not view.scores:
        st.info(f"Not scored with the {view.profile} profile yet. Click Triage to score it.")
        return

    best = max(view.scores, key=lambda item: item.score)
    st.metric(f"Recommended résumé: {view.recommended_version}", f"{best.score} / 100")
    st.table([{"version": item.resume_version, "score": item.score} for item in view.scores])

    for item in view.scores:
        with st.expander(
            f"{item.resume_version} — {item.score} / 100",
            expanded=item.resume_version == view.recommended_version,
        ):
            for name in config.SCORE_WEIGHTS:
                dimension = getattr(item.dimensions, name)
                st.markdown(f"**{name}** {dimension.score}/10 — {dimension.reason}")
            # Only verified pairs are offered as evidence; the rest stay in the record
            # and are counted here, never shown as if they were quotes (D-010 §3).
            if item.verified_pairs:
                st.table(
                    [
                        {"requirement": pair.requirement, "experience": pair.experience}
                        for pair in item.verified_pairs
                    ]
                )
            if item.unverified_pairs:
                st.caption(f"{item.unverified_pairs} pair(s) hidden: quote not found in source.")
            for gap in item.gaps:
                st.markdown(f"- gap: {gap}")
    st.caption(SCORE_CAPTION)


# --- Decision ----------------------------------------------------------------------------


def _save_decision(session, job_id: int, action: str, reason: str | None, confirmed: bool) -> None:  # type: ignore[no-untyped-def]
    """Record one decision, then rerun so the page redraws with the new status."""
    try:
        triage.record_decision(session, job_id, action, reason, confirm_hard=confirmed)
    except (triage.DecisionRefused, triage.JobNotFound) as error:
        st.error(str(error))
        return
    label = f" ({REJECT_REASON_LABELS[reason]})" if reason else ""
    st.session_state["flash"] = f"Saved: {action}{label}."
    st.rerun()


def decision_section(session, view: triage.TriageView) -> None:  # type: ignore[no-untyped-def]
    with st.container(border=True, key=f"{ui.CARD_KEY_PREFIX}decision"):
        st.subheader("Decision")
        flash = st.session_state.pop("flash", None)
        if flash:
            st.success(flash)
        st.markdown(f"Status: **{view.status}**")

        approve_column, reject_column = st.columns(2)
        with approve_column:
            confirmed = False
            if view.has_hard_flag:
                confirmed = st.checkbox("I've read the HARD flag above", key="confirm_hard")
            if st.button("Approve", type="primary"):
                _save_decision(session, view.job_id, "approved", None, confirmed)
        with reject_column:
            reason = st.selectbox(
                "Reason",
                list(REJECT_REASON_LABELS),
                key="reason",
                index=None,  # nothing preselected: the reason is a signal, not a default
                format_func=lambda key: REJECT_REASON_LABELS[key],
                placeholder="Choose a reason",
            )
            if st.button("Reject"):
                _save_decision(session, view.job_id, "rejected", reason, False)


# --- Page --------------------------------------------------------------------------------


def show_result(view: triage.TriageView) -> None:
    """One job's evidence, flags and scores: the same for a live job and a saved example."""
    company = ui.md_escape(view.company) if view.company else "(no company)"
    title = ui.md_escape(view.title) if view.title else "(no title)"
    st.header(f"{company} — {title}")
    if view.url:
        posting_link(view.url)
    ui.summary_strip(view)
    if view.scores:  # a score is never shown without saying what it is not
        st.caption(SCORE_CAPTION)
    red_flag_banners(view)
    evidence_tabs(view)


def main() -> None:
    settings = resources.settings()
    use_sample = st.session_state["use_sample"]  # the sidebar toggle, drawn before this page
    with resources.session_factory(settings.database_url)() as session:
        st.title("Job triage")
        paste_form(session, settings, use_sample)

        job_id = st.session_state.get("job_id")
        empty = job_id is None and "demo_case" not in st.session_state
        demo_picker(expanded=empty or st.session_state.pop("api_down", False))

        if "demo_case" in st.session_state:
            show_demo(st.session_state["demo_case"])
            return
        job_id = st.session_state.get("job_id")  # "Show example" may have just cleared it
        if job_id is None:
            st.info("Paste a job description above, then click Triage.")
            return
        try:
            view = triage.load_triage(session, job_id, sample=use_sample)
        except triage.JobNotFound as error:
            st.error(str(error))
            return
        show_result(view)
        decision_section(session, view)


main()
