from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from toutoule.db import get_engine, get_session_factory, init_db
from toutoule.models import Extraction, Job, JobStatus, Source

SPEC_TABLES = {
    "sources",
    "jobs",
    "extractions",
    "extraction_violations",
    "scores",
    "red_flags",
    "digests",
    "decisions",
    "rewrites",
    "eval_runs",
    "config_changes",
}


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """A fresh, empty SQLite file per test. Never the owner's real database."""
    return get_engine(f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    init_db(engine)
    return get_session_factory(engine)


def add_source_and_job(session: Session) -> Job:
    source = Source(name="Acme Greenhouse", tier=1, url="https://example.com", adapter="gh")
    session.add(source)
    session.flush()  # sends the INSERT so source.id is filled in
    job = Job(
        source_id=source.id,
        company="Acme",
        title="AI Product Manager",
        url="https://example.com/jobs/1",
        raw_text="We sponsor visas.",
        content_hash="a" * 64,
    )
    session.add(job)
    session.flush()
    return job


def test_init_db_creates_exactly_the_spec_tables(engine: Engine) -> None:
    created = init_db(engine)

    assert set(created) == SPEC_TABLES
    assert set(inspect(engine).get_table_names()) == SPEC_TABLES


def test_content_hash_is_indexed(engine: Engine) -> None:
    init_db(engine)

    indexed = [i["column_names"] for i in inspect(engine).get_indexes("jobs")]
    assert ["content_hash"] in indexed


def test_init_db_twice_is_safe(engine: Engine) -> None:
    init_db(engine)

    assert init_db(engine) == []  # nothing new to create, and no error


def test_job_and_extraction_round_trip(sessions: sessionmaker[Session]) -> None:
    payload = {"company": "Acme", "critical": {"deadline": {"stated": False}}}
    with sessions() as session:
        job = add_source_and_job(session)
        session.add(
            Extraction(
                job_id=job.id,
                prompt_version="p1",
                schema_version="s1",
                payload_json=payload,
                model="small-model",
                input_tokens=1234,
                output_tokens=56,
            )
        )
        session.commit()

    with sessions() as session:  # a new session, so values come from the file
        job = session.query(Job).one()
        extraction = session.query(Extraction).one()

    assert job.title == "AI Product Manager"
    assert job.content_hash == "a" * 64
    assert job.status == JobStatus.DISCOVERED
    assert job.first_seen_at.tzinfo == UTC
    assert extraction.job_id == job.id
    assert extraction.payload_json == payload
    assert (extraction.input_tokens, extraction.output_tokens) == (1234, 56)
    assert extraction.created_at.tzinfo == UTC


def test_extraction_for_missing_job_is_rejected(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        session.add(
            Extraction(
                job_id=999,
                prompt_version="p1",
                schema_version="s1",
                payload_json={},
                model="small-model",
                input_tokens=0,
                output_tokens=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_naive_datetime_is_rejected(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        job = add_source_and_job(session)
        job.last_seen_at = datetime(2026, 9, 29, 7, 30)  # no time zone

        with pytest.raises(StatementError, match="naive datetime"):
            session.commit()


def test_get_engine_reads_database_url_from_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here, so only the fake env vars are read
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-test-key")
    monkeypatch.setenv("MATCH_THRESHOLD", "65")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'from_settings.db'}")

    engine = get_engine()

    assert engine.url.database == str(tmp_path / "from_settings.db")
