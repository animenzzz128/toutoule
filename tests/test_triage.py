"""The paste-to-decision module (Task 1.11). No network, no real resumes, no .env.

Every test drives a FakeClient against a throwaway SQLite file, so the whole loop the
Streamlit app performs is exercised here without a browser.
"""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from toutoule import config, extract, models, triage
from toutoule.config import Settings, get_settings
from toutoule.db import get_engine, get_session_factory, init_db

POSTING = (
    "Example Co is hiring an AI Product Manager.\n"
    "We do not sponsor work visas for this role.\n"
    "Applications close on 2026-12-31.\n"
    "You will own a roadmap, run pricing experiments, and work with data science. "
    "SQL required.\n"
    "Based in New York, NY. Hybrid, three days a week in the office.\n"
    "Please submit a resume and cover letter.\n"
)
RESUME = "Shipped an AI assistant used by 40 teams\nPython, SQL, R, Stata\nLed pricing research"
TODAY = date(2026, 10, 3)  # well before the posting's deadline: no R5, no R6


def field(value: str | None, evidence: str | None) -> dict[str, Any]:
    """One extracted field. value=None means the posting did not state it (F3)."""
    return {"value": value, "stated": value is not None, "evidence": evidence}


def extraction_answer(**overrides: dict[str, Any]) -> str:
    """One model reply for the extraction call. Every quote is a span of POSTING."""
    critical = {
        "deadline": field("2026-12-31", "Applications close on 2026-12-31."),
        "visa_sponsorship": field("no", "We do not sponsor work visas for this role."),
        "graduation_window": field(None, None),  # the posting really is silent on this
        "application_cap": field(None, None),
        "materials_required": field("resume + cover letter", "Please submit a resume and cover"),
    }
    return json.dumps(
        {
            "schema_version": "1.0",
            "prompt_version": "ignored, code sets this",
            "company": "Example Co",
            "title": "AI Product Manager",
            "critical": critical | overrides,
            "important": {
                "location": field("New York, NY", "Based in New York, NY."),
                "work_model": field("hybrid", "Hybrid, three days a week in the office."),
                "language_requirement": field(None, None),
                "start_date": field(None, None),
                "degree_requirement": field(None, None),
            },
            "reference": {
                "skills": ["SQL"],
                "responsibilities": ["own a roadmap"],
                "team_or_function": "Product",
            },
        }
    )


def score_answer(fabricate: bool = False) -> str:
    """One model reply for a scoring call. Both sides of every pair are real quotes.

    fabricate=True invents the third pair's resume quote, so verification must reject it.
    """
    invented = "Ran a team of nine data scientists"  # in neither the posting nor the resume
    return json.dumps(
        {
            "dimensions": {
                "domain_fit": {"score": 8, "reason": "same work"},
                "skills_overlap": {"score": 6, "reason": "most tools match"},
                "seniority_fit": {"score": 7, "reason": "right level"},
            },
            "evidence_pairs": [
                {"requirement": "SQL required", "experience": "Python, SQL, R, Stata"},
                {"requirement": "own a roadmap", "experience": "Led pricing research"},
                {
                    "requirement": "run pricing experiments",
                    "experience": invented
                    if fabricate
                    else "Shipped an AI assistant used by 40 teams",
                },
            ],
            "gaps": ["no people management", "no payments experience"],
        }
    )


def full_run() -> FakeClient:
    """A client with the four answers one full triage needs: one extract, three scores."""
    return FakeClient(extraction_answer(), score_answer(), score_answer(), score_answer())


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    """An empty database in a throwaway file. Closed after the test, pass or fail."""
    engine = get_engine(f"sqlite:///{tmp_path / 'triage.db'}")
    init_db(engine)
    with get_session_factory(engine)() as session:
        yield session


@pytest.fixture(autouse=True)
def profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point both profile folders at temporary files, in every test in this module.

    autouse means pytest applies it without a test asking, which is what keeps the owner's
    real resumes in data/private out of reach here even if a test forgets to say so.
    """
    real, sample = tmp_path / "real", tmp_path / "sample"
    for version in config.RESUME_VERSIONS:
        sample.mkdir(exist_ok=True)
        (sample / f"sample_{version}.md").write_text(RESUME, encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_DIR", real)
    monkeypatch.setattr(config, "SAMPLE_PROFILE_DIR", sample)
    return real


@pytest.fixture
def settings(valid_env: None) -> Settings:
    """Valid settings from the fake environment, never from the owner's .env file."""
    return get_settings(env_file=None)


def triage_once(session: Session, client: FakeClient, settings: Settings, **kwargs: Any) -> int:
    """run_triage with this module's defaults: the sample resumes and a fixed date."""
    return triage.run_triage(
        session,
        client,
        kwargs.pop("company", "Example Co"),
        kwargs.pop("title", "AI Product Manager"),
        kwargs.pop("url", "https://example.com/job"),
        kwargs.pop("raw_text", POSTING),
        sample=kwargs.pop("sample", True),
        today=kwargs.pop("today", TODAY),
        settings=settings,
        **kwargs,
    )


def rows(session: Session, table: Any, job_id: int) -> list[Any]:
    return list(session.scalars(select(table).where(table.job_id == job_id)))


# --- The full loop -----------------------------------------------------------------------


def test_run_triage_writes_job_extraction_flags_and_three_scores(
    session: Session, settings: Settings
) -> None:
    job_id = triage_once(session, full_run(), settings, market="US")

    job = session.get(models.Job, job_id)
    assert job is not None
    assert job.status == models.JobStatus.SCORED
    assert job.content_hash == extract.hash_content(POSTING)
    assert len(rows(session, models.Extraction, job_id)) == 1
    assert [flag.rule_id for flag in rows(session, models.RedFlag, job_id)] == ["R1"]
    scores = rows(session, models.Score, job_id)
    assert {row.resume_version for row in scores} == set(config.RESUME_VERSIONS)
    assert {row.payload_json["profile"] for row in scores} == {"sample"}


def test_blank_company_and_title_are_filled_from_the_extraction(
    session: Session, settings: Settings
) -> None:
    job_id = triage_once(session, full_run(), settings, company="  ", title="")

    job = session.get(models.Job, job_id)
    assert job is not None
    assert (job.company, job.title) == ("Example Co", "AI Product Manager")


def test_a_failed_extraction_saves_nothing_partial(session: Session, settings: Settings) -> None:
    """Two invalid answers: the attempt is recorded, but no extraction, flag or score is."""
    client = FakeClient("not json at all", "still not json")

    with pytest.raises(extract.ExtractionFailed):
        triage_once(session, client, settings)

    job = session.scalars(select(models.Job)).one()
    assert job.status == models.JobStatus.EXTRACTION_FAILED
    assert rows(session, models.Extraction, job.id) == []
    assert rows(session, models.RedFlag, job.id) == []
    assert rows(session, models.Score, job.id) == []


# --- Cost control: the content hash is the cache key (constraint 6) -----------------------


def test_the_same_text_again_makes_no_client_calls_and_returns_the_same_job_id(
    session: Session, settings: Settings
) -> None:
    first_id = triage_once(session, full_run(), settings)

    again = FakeClient()  # any call at all would raise IndexError: no answers to give
    second_id = triage_once(session, again, settings)

    assert second_id == first_id
    assert again.requests == []
    assert len(rows(session, models.Score, first_id)) == 3  # not scored a second time


def test_red_flags_are_re_evaluated_when_the_market_changes(
    session: Session, settings: Settings
) -> None:
    """The rules cost nothing, so they run again; a corrected market must change the answer.

    The posting says it does not sponsor visas. With an unknown market R1 cannot fire
    (tech spec §4); told the role is in the US, it must — without re-reading the posting.
    """
    job_id = triage_once(session, full_run(), settings, market=None)
    assert rows(session, models.RedFlag, job_id) == []

    again = FakeClient()
    assert triage_once(session, again, settings, market="US") == job_id

    assert again.requests == []
    flags = rows(session, models.RedFlag, job_id)
    assert [(flag.rule_id, flag.severity) for flag in flags] == [("R1", "HARD")]


def test_a_passed_deadline_flags_the_same_job_the_next_day(
    session: Session, settings: Settings
) -> None:
    """Same text, later date: R6 appears because the rules are re-run, not cached."""
    job_id = triage_once(session, full_run(), settings)

    triage_once(session, FakeClient(), settings, today=date(2027, 1, 1))

    assert [flag.rule_id for flag in rows(session, models.RedFlag, job_id)] == ["R6"]


def test_a_job_scored_on_the_sample_profile_is_scored_again_for_the_real_one(
    session: Session, settings: Settings, profiles: Path
) -> None:
    """The two profiles give different numbers, so one's scores never stand in for the other."""
    profiles.mkdir()
    for version in config.RESUME_VERSIONS:
        (profiles / f"{version}.md").write_text(RESUME, encoding="utf-8")
    job_id = triage_once(session, full_run(), settings, sample=True)

    client = FakeClient(score_answer(), score_answer(), score_answer())  # no extraction call
    triage_once(session, client, settings, sample=False)

    assert len(client.requests) == 3
    by_profile = [row.payload_json["profile"] for row in rows(session, models.Score, job_id)]
    assert sorted(by_profile) == ["real"] * 3 + ["sample"] * 3


def test_scores_written_before_profiles_were_recorded_do_not_count_as_a_match(
    session: Session, settings: Settings
) -> None:
    """An older row has no "profile" key; reusing it would show scores from an unknown set."""
    job_id = triage_once(session, full_run(), settings)
    for row in rows(session, models.Score, job_id):
        row.payload_json = {k: v for k, v in row.payload_json.items() if k != "profile"}
    session.commit()

    client = FakeClient(score_answer(), score_answer(), score_answer())
    triage_once(session, client, settings)

    assert len(client.requests) == 3  # scored again, rather than trusted


# --- Which profile is active -------------------------------------------------------------


def test_the_sample_profile_is_used_when_the_private_folder_is_missing() -> None:
    assert not config.PROFILE_DIR.exists()
    assert triage.active_profile_dir() == (config.SAMPLE_PROFILE_DIR, "sample")


def test_the_real_profile_is_used_when_it_exists(profiles: Path) -> None:
    profiles.mkdir()
    assert triage.active_profile_dir() == (profiles, "real")


def test_force_sample_wins_over_a_present_real_profile(profiles: Path) -> None:
    profiles.mkdir()
    assert triage.active_profile_dir(force_sample=True) == (config.SAMPLE_PROFILE_DIR, "sample")


# --- What the page reads -----------------------------------------------------------------


def test_load_triage_shows_every_critical_field_with_its_quote(
    session: Session, settings: Settings
) -> None:
    view = triage.load_triage(session, triage_once(session, full_run(), settings))

    assert [item.name for item in view.critical] == [
        "deadline",
        "visa_sponsorship",
        "graduation_window",
        "application_cap",
        "materials_required",
    ]
    deadline = view.critical[0]
    assert (deadline.value, deadline.stated) == ("2026-12-31", True)
    assert deadline.evidence == "Applications close on 2026-12-31."
    assert view.other[0].name == "location" and view.other[0].value == "New York, NY"


def test_a_field_the_posting_never_stated_shows_as_not_stated_with_no_value(
    session: Session, settings: Settings
) -> None:
    """F3: absence is shown as absence, never as a plausible default."""
    view = triage.load_triage(session, triage_once(session, full_run(), settings))

    window = next(item for item in view.critical if item.name == "graduation_window")
    assert window.stated is False
    assert window.value is None
    assert window.evidence is None


def test_load_triage_offers_only_verified_pairs_but_still_counts_the_rest(
    session: Session, settings: Settings
) -> None:
    """D-010 §3: an unverified quote is hidden from the page, not deleted from the record."""
    client = FakeClient(extraction_answer(), *[score_answer(fabricate=True)] * 3)

    view = triage.load_triage(session, triage_once(session, client, settings))

    first = view.scores[0]
    assert [pair.verified for pair in first.verified_pairs] == [True, True]
    assert first.unverified_pairs == 1
    assert len(first.gaps) == 2


def test_load_triage_reports_the_scores_the_recommendation_and_the_profile(
    session: Session, settings: Settings
) -> None:
    view = triage.load_triage(session, triage_once(session, full_run(), settings, market="US"))

    assert {item.resume_version for item in view.scores} == set(config.RESUME_VERSIONS)
    assert view.recommended_version == config.RESUME_VERSIONS[0]  # a three-way tie
    assert view.profile == "sample"
    assert [(flag.rule_id, flag.severity) for flag in view.flags] == [("R1", "HARD")]
    assert view.has_hard_flag is True
    assert view.decision is None


def test_load_triage_refuses_an_unknown_job_id(session: Session) -> None:
    with pytest.raises(triage.JobNotFound, match="404"):
        triage.load_triage(session, 404)


def test_a_view_cannot_be_written_through(session: Session, settings: Settings) -> None:
    """Frozen models: the page renders the record, it does not edit it."""
    view = triage.load_triage(session, triage_once(session, full_run(), settings))

    with pytest.raises(ValidationError):
        view.status = "approved"  # type: ignore[misc]


# --- Decisions (PD-4) --------------------------------------------------------------------


def decisions(session: Session, job_id: int) -> list[models.Decision]:
    return rows(session, models.Decision, job_id)


def test_a_rejection_writes_one_decisions_row_with_its_reason(
    session: Session, settings: Settings
) -> None:
    """The plan's acceptance test for Task 1.11."""
    job_id = triage_once(session, full_run(), settings)

    decision_id = triage.record_decision(session, job_id, "rejected", "wrong_location")

    stored = decisions(session, job_id)
    assert [row.id for row in stored] == [decision_id]
    assert (stored[0].action, stored[0].reject_reason) == ("rejected", "wrong_location")
    assert stored[0].digest_id is None  # a pasted job was never in a digest
    assert stored[0].decided_at.tzinfo is not None  # stored as UTC, not a naive timestamp
    assert session.get(models.Job, job_id).status == models.JobStatus.REJECTED


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        ("rejected", None),  # a rejection must say why
        ("rejected", "changed_my_mind"),  # not one of the five
        ("approved", "wrong_location"),  # an approval has no reason
        ("snoozed", None),  # not an action the app offers
    ],
)
def test_a_decision_that_breaks_a_rule_is_refused_and_writes_nothing(
    session: Session, settings: Settings, action: str, reason: str | None
) -> None:
    job_id = triage_once(session, full_run(), settings)

    with pytest.raises(triage.DecisionRefused):
        triage.record_decision(session, job_id, action, reason)

    assert decisions(session, job_id) == []
    assert session.get(models.Job, job_id).status == models.JobStatus.SCORED


def test_a_decision_on_an_unknown_job_is_refused(session: Session) -> None:
    with pytest.raises(triage.JobNotFound, match="404"):
        triage.record_decision(session, 404, "rejected", "not_interested")


def test_approving_a_job_with_a_hard_flag_needs_confirmation(
    session: Session, settings: Settings
) -> None:
    """Constraint 3: the rules decide eligibility, so overriding one is a deliberate act."""
    job_id = triage_once(session, full_run(), settings, market="US")  # R1 HARD

    with pytest.raises(triage.DecisionRefused, match="confirm_hard"):
        triage.record_decision(session, job_id, "approved")

    assert decisions(session, job_id) == []
    assert triage.record_decision(session, job_id, "approved", confirm_hard=True) > 0
    assert session.get(models.Job, job_id).status == models.JobStatus.APPROVED


def test_changing_a_decision_adds_a_row_and_leaves_the_first_one_untouched(
    session: Session, settings: Settings
) -> None:
    """Append-only: the reject reasons are the F18 signal, and an overwrite is not a signal."""
    job_id = triage_once(session, full_run(), settings)
    first_id = triage.record_decision(session, job_id, "rejected", "already_applied")
    before = decisions(session, job_id)[0]
    original = (before.action, before.reject_reason, before.decided_at)

    second_id = triage.record_decision(session, job_id, "approved")

    stored = decisions(session, job_id)
    assert [row.id for row in stored] == [first_id, second_id]
    assert (stored[0].action, stored[0].reject_reason, stored[0].decided_at) == original
    assert (stored[1].action, stored[1].reject_reason) == ("approved", None)
    assert session.get(models.Job, job_id).status == models.JobStatus.APPROVED
    latest = triage.load_triage(session, job_id).decision
    assert latest is not None and latest.action == "approved"
