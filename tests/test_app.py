"""The Streamlit page, driven by AppTest (Task 1.11). No browser, no network, no .env.

AppTest runs the script in this process and exposes the elements it produced, so a click
is a method call and a banner is a value to assert on. The fake client is injected by
replacing triage.build_client: the page looks that name up on the module at call time,
which a script AppTest executes in its own namespace still shares with this test.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from fakes import FakeClient
from postings import POSTING, RESUME, extraction_answer, score_answer
from sqlalchemy import select
from streamlit.testing.v1 import AppTest

from toutoule import config, models, triage
from toutoule.db import get_engine, get_session_factory

APP = Path(__file__).parents[1] / "app" / "streamlit_app.py"
# A cold pandas import can take most of a minute on a first run; the default 3s timeout
# would make these tests flaky for a reason that has nothing to do with the page.
TIMEOUT = 60
REAL_LINE = "Built a pricing model for a payments team"
REAL_RESUME = f"{REAL_LINE}\nShipped a billing migration"

AppFactory = Callable[..., AppTest]


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A throwaway database, and a working folder with no .env to be read from."""
    url = f"sqlite:///{tmp_path / 'app.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.chdir(tmp_path)
    return url


@pytest.fixture
def profile_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Temporary real and sample profiles. The real folder is created only on request."""
    real, sample = tmp_path / "real", tmp_path / "sample"
    sample.mkdir()
    for version in config.RESUME_VERSIONS:
        (sample / f"sample_{version}.md").write_text(RESUME, encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_DIR", real)
    monkeypatch.setattr(config, "SAMPLE_PROFILE_DIR", sample)
    return real, sample


@pytest.fixture
def make_app(
    monkeypatch: pytest.MonkeyPatch,
    valid_env: None,
    database: str,
    profile_dirs: tuple[Path, Path],
) -> AppFactory:
    """Build the page with a fake client holding the answers this test will need."""

    def factory(*answers: str) -> AppTest:
        client = FakeClient(*answers)
        monkeypatch.setattr(triage, "build_client", lambda _settings: client)
        st.cache_resource.clear()  # or a previous test's engine and client would be reused
        return AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    return factory


def full_answers() -> tuple[str, ...]:
    """One extraction and three scores: what one complete triage asks the model for."""
    return (extraction_answer(), score_answer(), score_answer(), score_answer())


def answers_quoting(line: str) -> tuple[str, ...]:
    """Three scoring answers whose resume side quotes `line`, so they verify against it."""
    data = json.loads(score_answer())
    for pair in data["evidence_pairs"]:
        pair["experience"] = line
    return (json.dumps(data),) * 3


def click(at: AppTest, label: str) -> AppTest:
    """Click the button with this label. Buttons have no key, so the label is the handle."""
    for button in at.button:
        if button.label == label:
            return button.click().run()
    raise AssertionError(f"no button labelled {label!r}; found {[b.label for b in at.button]}")


def triage_posting(at: AppTest, market: str = "Unknown", text: str = POSTING) -> AppTest:
    at.text_input(key="company").set_value("Example Co")
    at.text_area(key="posting").set_value(text)
    at.selectbox(key="market").select(market)
    return click(at, "Triage")


def table_rows(at: AppTest, index: int = 0) -> list[dict[str, Any]]:
    return at.table[index].value.to_dict("records")  # type: ignore[no-any-return]


def page_text(at: AppTest) -> str:
    """Everything the page renders, as one string: element values, labels and tables."""
    chunks: list[str] = []
    for block in (at.main, at.sidebar):
        for element in block:
            for attribute in ("value", "label"):
                found = getattr(element, attribute, None)
                if found is not None and not isinstance(found, bool):
                    chunks.append(found if isinstance(found, str) else str(found))
    return "\n".join(chunks)


def decisions(database_url: str) -> list[models.Decision]:
    with get_session_factory(get_engine(database_url))() as session:
        return list(session.scalars(select(models.Decision)))


def jobs(database_url: str) -> list[models.Job]:
    with get_session_factory(get_engine(database_url))() as session:
        return list(session.scalars(select(models.Job)))


# --- Paste and read the evidence ---------------------------------------------------------


def test_the_critical_table_shows_not_stated_and_the_evidence_quote(
    make_app: AppFactory,
) -> None:
    at = triage_posting(make_app(*full_answers()))

    assert not at.exception
    rows = {row["field"]: row for row in table_rows(at)}
    assert rows["graduation_window"]["value"] == "Not stated"
    assert rows["graduation_window"]["evidence"] == ""
    assert rows["deadline"]["value"] == "2026-12-31"
    assert rows["deadline"]["evidence"] == "Applications close on 2026-12-31."


def test_a_posting_too_short_to_be_real_is_refused_before_any_call(
    make_app: AppFactory,
) -> None:
    at = make_app()  # no answers queued: a model call would raise

    at = triage_posting(at, text="Product Manager wanted.")

    assert not at.exception
    assert "too short" in at.error[0].value
    assert jobs(f"sqlite:///{Path.cwd() / 'app.db'}") == []


def test_the_company_is_required(make_app: AppFactory) -> None:
    at = make_app()
    at.text_area(key="posting").set_value(POSTING)

    at = click(at, "Triage")

    assert "required" in at.error[0].value


# --- Red flags ---------------------------------------------------------------------------


def test_a_hard_flag_is_an_error_banner_and_approve_without_the_checkbox_saves_nothing(
    make_app: AppFactory, database: str
) -> None:
    at = triage_posting(make_app(*full_answers()), market="United States")

    banner = at.error[0].value
    assert "HARD · R1" in banner
    assert "We do not sponsor work visas for this role." in banner

    at = click(at, "Approve")

    assert "confirm_hard" in at.error[-1].value
    assert decisions(database) == []  # the rule refused it; the page stored nothing


def test_a_posting_with_no_flags_says_so(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))  # market unknown, so R1 cannot fire

    assert "No red flags from the rules." in page_text(at)
    assert at.error == []


# --- The acceptance test, end to end -----------------------------------------------------


def test_rejecting_with_wrong_location_writes_one_decisions_row(
    make_app: AppFactory, database: str
) -> None:
    """Task 1.11's acceptance criterion, driven through the page itself."""
    at = triage_posting(make_app(*full_answers()))

    at.selectbox(key="reason").select("wrong_location")
    at = click(at, "Reject")

    assert "Saved: rejected (Wrong location)." in at.success[0].value
    stored = decisions(database)
    assert len(stored) == 1
    assert (stored[0].action, stored[0].reject_reason) == ("rejected", "wrong_location")
    assert jobs(database)[0].status == models.JobStatus.REJECTED
    assert "Status: **rejected**" in page_text(at)


def test_rejecting_without_choosing_a_reason_is_refused(
    make_app: AppFactory, database: str
) -> None:
    at = triage_posting(make_app(*full_answers()))

    at = click(at, "Reject")

    assert at.error  # the message comes from triage.record_decision, not from the page
    assert decisions(database) == []


# --- The score section -------------------------------------------------------------------


def test_the_score_caption_says_it_is_not_calibrated(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))

    captions = [caption.value for caption in at.caption]
    assert any("not calibrated to the owner's judgment" in text for text in captions)
    assert any("docs/eval/scoring.md" in text for text in captions)


def test_the_page_never_claims_to_be_calibrated(make_app: AppFactory) -> None:
    """Every mention of the word has to be a denial of it, wherever it appears."""
    text = page_text(at := triage_posting(make_app(*full_answers())))

    assert "calibrated" in text  # the caption is there to be found
    for position in range(len(text)):
        if text.startswith("calibrated", position):
            assert text[max(0, position - 4) : position] == "not "
    assert not at.exception


def test_only_verified_pairs_are_offered_as_evidence(make_app: AppFactory) -> None:
    answers = (extraction_answer(), *(score_answer(fabricate=True),) * 3)

    at = triage_posting(make_app(*answers))

    text = page_text(at)
    assert "Ran a team of nine data scientists" not in text  # the invented quote
    assert "1 pair(s) hidden: quote not found in source." in text


# --- The profile the page shows ----------------------------------------------------------


def test_flipping_to_the_sample_profile_hides_the_real_resumes_words(
    make_app: AppFactory, profile_dirs: tuple[Path, Path]
) -> None:
    """Evidence pairs quote the résumé, so a stale score would put private words on screen."""
    real, _ = profile_dirs
    real.mkdir()
    for version in config.RESUME_VERSIONS:
        (real / f"{version}.md").write_text(REAL_RESUME, encoding="utf-8")
    at = triage_posting(make_app(extraction_answer(), *answers_quoting(REAL_LINE)))
    assert REAL_LINE in page_text(at)  # scored against the real profile

    at.toggle(key="use_sample").set_value(True).run()

    text = page_text(at)
    assert REAL_LINE not in text
    assert "Not scored with the sample profile yet." in text


def test_a_sidebar_entry_reopens_its_job(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))
    job_id = at.session_state["job_id"]
    del at.session_state["job_id"]
    at = at.run()
    assert "Paste a job description above" in page_text(at)

    at = click(at, "Example Co · AI Product Manager — scored")

    assert at.session_state["job_id"] == job_id
    assert "Critical fields" in page_text(at)
