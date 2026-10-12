"""The app's entry point (Task 1.13): page setup, the sidebar, and the page menu.

Run it with: uv run streamlit run app/streamlit_app.py

st.navigation takes the list of pages, draws the menu, and returns the page the visitor
chose; .run() then executes that page's file. This file runs first on every page, which is
why the sidebar lives here: a widget that is not drawn on a run loses its value, so a
profile toggle drawn by one page alone would reset whenever the visitor left that page.
"""

import resources
import streamlit as st
import ui

from toutoule import config, triage

TRIAGE = st.Page("views/triage.py", title="Triage", icon=":material/fact_check:", default=True)
HISTORY = st.Page("views/history.py", title="History", icon=":material/history:")
HOW_IT_WORKS = st.Page("views/how_it_works.py", title="How it works", icon=":material/info:")


def sidebar(session) -> None:  # type: ignore[no-untyped-def]
    """Profile in use, the toggle that changes it, and the recent jobs."""
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
        company = ui.md_escape(item.company) if item.company else "(no company)"
        title = ui.md_escape(item.title) if item.title else "(no title)"
        label = f"{company} · {title} — {item.status}"
        if st.sidebar.button(label, key=f"job-{item.job_id}"):
            st.session_state["job_id"] = item.job_id
            st.switch_page(TRIAGE)  # a job opens on Triage, whichever page it was picked on


def main() -> None:
    st.set_page_config(page_title="投投乐 · job triage", layout="wide")
    st.html(ui.CARD_CSS)
    settings = resources.settings()
    page = st.navigation([TRIAGE, HISTORY, HOW_IT_WORKS])
    with resources.session_factory(settings.database_url)() as session:
        sidebar(session)
    page.run()


main()
