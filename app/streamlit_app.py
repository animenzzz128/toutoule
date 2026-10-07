"""The page for Task 1.11 (PRD F10): paste a posting, read the evidence, decide.

A view and nothing else. Every rule it appears to enforce — which reasons a rejection may
carry, when an approval needs confirming, which profile's scores may be shown — lives in
triage.py, where a test can reach it without a browser. Wording that describes a rule
comes from the module that owns the rule, so the page cannot describe one the code no
longer applies.

Run it with: uv run streamlit run app/streamlit_app.py
"""

import streamlit as st

from toutoule import config, extract, redflags, score, triage
from toutoule.config import ConfigError, Settings, get_settings
from toutoule.db import get_engine, get_session_factory, init_db
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


# --- Resources ---------------------------------------------------------------------------
#
# st.cache_resource keeps one object alive across reruns, so a new engine is not built on
# every keystroke. An argument whose name starts with "_" is not hashed, which is how
# Settings — which holds a secret and is not hashable — can be passed in.


@st.cache_resource
def session_factory(database_url: str):  # type: ignore[no-untyped-def]
    engine = get_engine(database_url)
    init_db(engine)
    return get_session_factory(engine)


@st.cache_resource
def model_client(_settings: Settings) -> extract.ModelClient:
    return triage.build_client(_settings)


# --- Sidebar -----------------------------------------------------------------------------


def sidebar(session) -> bool:  # type: ignore[no-untyped-def]
    """Profile in use, the toggle that changes it, and the recent jobs. Returns the toggle."""
    st.sidebar.title("投投乐")
    # No real profile on disk means the deployed demo, where the samples are all there is
    # (D-010 §9). Disable the toggle rather than leave a control that cannot change anything.
    only_sample = not config.PROFILE_DIR.exists()
    use_sample = st.sidebar.toggle(
        "Use sample profile",
        key="use_sample",
        value=only_sample,
        disabled=only_sample,
        help="Score against the redacted sample resumes instead of the real ones.",
    )
    st.sidebar.caption(f"Profile in use: **{triage.active_profile_dir(use_sample).kind}**")
    if only_sample:
        st.sidebar.caption("This deployment has no real profile, so only the sample is available.")

    st.sidebar.subheader("Recent jobs")
    jobs = triage.recent_jobs(session)
    if not jobs:
        st.sidebar.caption("Nothing triaged yet.")
    for item in jobs:
        label = f"{item.company or '(no company)'} · {item.title or '(no title)'} — {item.status}"
        if st.sidebar.button(label, key=f"job-{item.job_id}"):
            st.session_state["job_id"] = item.job_id
    return use_sample


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
        submitted = st.form_submit_button("Triage")
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
                model_client(settings),
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
    except Exception as error:  # noqa: BLE001 — a page shows a message, never a traceback
        st.error(f"{type(error).__name__}: {error}")
        return
    st.session_state["job_id"] = job_id


# --- Result ------------------------------------------------------------------------------


def red_flag_banners(view: triage.TriageView) -> None:
    st.subheader("Red flags")
    if not view.flags:
        st.write("No red flags from the rules.")
        return
    for flag in view.flags:
        text = f"**{flag.severity} · {flag.rule_id}** — {redflags.RULE_DESCRIPTIONS[flag.rule_id]}"
        if flag.evidence:
            text += f"\n\n> {flag.evidence}"
        banner = st.error if flag.severity == "HARD" else st.warning
        banner(text)


def _field_row(item: triage.FieldView) -> dict[str, str]:
    """One table row. An unstated field says so and quotes nothing (F3)."""
    return {
        "field": item.name,
        "value": item.value if item.stated else "Not stated",
        "evidence": item.evidence or "",
    }


def field_tables(view: triage.TriageView) -> None:
    st.subheader("Critical fields")
    st.table([_field_row(item) for item in view.critical])
    with st.expander("All fields"):
        st.table([_field_row(item) for item in view.other])


def score_section(view: triage.TriageView) -> None:
    st.subheader("Match score")
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
        if st.button("Approve"):
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


def main() -> None:
    st.set_page_config(page_title="投投乐 · job triage", layout="wide")
    try:
        settings = get_settings()
    except ConfigError as error:
        st.error(str(error))
        st.stop()

    with session_factory(settings.database_url)() as session:
        use_sample = sidebar(session)
        st.title("Job triage")
        paste_form(session, settings, use_sample)

        job_id = st.session_state.get("job_id")
        if job_id is None:
            st.info("Paste a job description above, then click Triage.")
            return
        try:
            view = triage.load_triage(session, job_id, sample=use_sample)
        except triage.JobNotFound as error:
            st.error(str(error))
            return

        st.header(f"{view.company or '(no company)'} — {view.title or '(no title)'}")
        if view.url:
            st.markdown(view.url)
        red_flag_banners(view)
        field_tables(view)
        score_section(view)
        decision_section(session, view)


main()
