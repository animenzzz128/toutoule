"""The History page: the jobs triaged so far, newest first. It reads and never writes.

column_config tells st.dataframe how to show each column (its heading, width, help text)
without changing the data. A dataframe draws every cell as plain text, so a company name
or title from a posting cannot be read as Markdown or HTML here.
"""

import resources
import streamlit as st

from toutoule import triage

SHOWN = 50

STATUS_HELP = (
    "extracted: fields read, not yet scored · scored: ready for a decision · "
    "approved / rejected: decided by you · extraction_failed: paste it again or enter it by hand"
)


def main() -> None:
    settings = resources.settings()
    st.title("History")
    with resources.session_factory(settings.database_url)() as session:
        jobs = triage.recent_jobs(session, limit=SHOWN)
    if not jobs:
        st.info("Nothing triaged yet. Paste a posting on the Triage page.")
        return

    st.dataframe(
        [job.model_dump() for job in jobs],
        column_order=["company", "title", "status"],
        column_config={
            "company": st.column_config.TextColumn("Company", width="medium"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "status": st.column_config.TextColumn("Status", help=STATUS_HELP),
        },
        hide_index=True,
    )
    st.caption(
        f"Up to the {SHOWN} most recent jobs. The newest ten are also under Recent jobs in "
        "the sidebar, which opens them."
    )


main()
