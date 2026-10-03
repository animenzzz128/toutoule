"""`cli score` end to end against a fake client, plus the repo-hygiene rules it depends on.

No network and no real resumes: every test here scores with --sample.
"""

import json
import subprocess
from pathlib import Path

import pytest
from fakes import FakeClient
from sqlalchemy import select

from toutoule import config, models, score
from toutoule.cli import main
from toutoule.db import get_engine, get_session_factory

REPO_ROOT = Path(__file__).parents[1]

POSTING = (
    "Growth Product Manager. You will run pricing experiments, own a roadmap, and work "
    "with data science. SQL required. Based in Singapore."
)


@pytest.fixture(autouse=True)
def run_in_empty_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run from a folder with no .env, so the owner's real .env is never read."""
    monkeypatch.chdir(tmp_path)


def answer(domain: int = 8, skills: int = 6, seniority: int = 7) -> str:
    """One model reply: two honest pairs, and one whose resume quote is invented.

    The honest quotes are spans of POSTING and of all three sample resumes; the third
    experience quote appears in none of them, so verification must mark it unverified.
    """
    return json.dumps(
        {
            "dimensions": {
                "domain_fit": {"score": domain, "reason": "same work"},
                "skills_overlap": {"score": skills, "reason": "most tools match"},
                "seniority_fit": {"score": seniority, "reason": "right level"},
            },
            "evidence_pairs": [
                {"requirement": "SQL required", "experience": "Python, SQL, R, Stata"},
                {"requirement": "own a roadmap", "experience": "ALEX MORGAN"},
                {"requirement": "run pricing experiments", "experience": "Managed a team of nine"},
            ],
            "gaps": ["no people management", "no payments experience"],
        }
    )


@pytest.fixture
def stored_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """One job already in a throwaway database. Returns its id."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'score.db'}")
    engine = get_engine(f"sqlite:///{tmp_path / 'score.db'}")
    models.Base.metadata.create_all(engine)
    with get_session_factory(engine)() as session:
        source = models.Source(name="manual", tier=3, url="manual://", adapter="manual")
        session.add(source)
        session.commit()
        job = models.Job(
            source_id=source.id,
            company="Example Co",
            title="Growth Product Manager",
            url="https://example.com/job",
            raw_text=POSTING,
            content_hash="hash",
        )
        session.add(job)
        session.commit()
        return job.id


def stored_scores(tmp_path: Path) -> list[models.Score]:
    engine = get_engine(f"sqlite:///{tmp_path / 'score.db'}")
    with get_session_factory(engine)() as session:
        return list(session.scalars(select(models.Score).order_by(models.Score.id)))


@pytest.mark.usefixtures("valid_env")
def test_score_writes_one_row_per_resume_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stored_job: int
) -> None:
    monkeypatch.setattr("toutoule.cli.Anthropic", lambda **_: FakeClient(*[answer()] * 3))

    exit_code = main(["score", str(stored_job), "--sample"])

    assert exit_code == 0
    rows = stored_scores(tmp_path)
    assert len(rows) == 3
    assert [row.resume_version for row in rows] == list(config.RESUME_VERSIONS)
    assert {row.score for row in rows} == {70}


@pytest.mark.usefixtures("valid_env")
def test_the_payload_records_weights_tokens_and_model_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stored_job: int
) -> None:
    """A stored score has to say how it was produced without anyone having to remember."""
    monkeypatch.setattr("toutoule.cli.Anthropic", lambda **_: FakeClient(*[answer()] * 3))

    main(["score", str(stored_job), "--sample"])

    payload = stored_scores(tmp_path)[0].payload_json
    assert payload["weights"] == config.SCORE_WEIGHTS
    assert payload["input_tokens"] == 1000
    assert payload["output_tokens"] == 300
    assert payload["model_settings"] == score.MODEL_SETTINGS
    assert payload["model_settings"]["temperature"] == "not sent"
    assert len(payload["result"]["evidence_pairs"]) == 3  # unverified ones kept, not dropped


@pytest.mark.usefixtures("valid_env")
def test_score_marks_the_job_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stored_job: int
) -> None:
    monkeypatch.setattr("toutoule.cli.Anthropic", lambda **_: FakeClient(*[answer()] * 3))

    main(["score", str(stored_job), "--sample"])

    engine = get_engine(f"sqlite:///{tmp_path / 'score.db'}")
    with get_session_factory(engine)() as session:
        assert session.get(models.Job, stored_job).status == models.JobStatus.SCORED


@pytest.mark.usefixtures("valid_env")
def test_an_unknown_job_id_is_an_error_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, stored_job: int, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("toutoule.cli.Anthropic", lambda **_: FakeClient())

    exit_code = main(["score", "999", "--sample"])

    assert exit_code == 1
    assert "No job with id 999" in capsys.readouterr().err


@pytest.mark.usefixtures("valid_env")
def test_only_verified_evidence_is_printed(
    monkeypatch: pytest.MonkeyPatch, stored_job: int, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third pair's resume quote is invented, so it must not be shown as evidence."""
    monkeypatch.setattr("toutoule.cli.Anthropic", lambda **_: FakeClient(*[answer()] * 3))

    main(["score", str(stored_job), "--sample"])

    out = capsys.readouterr().out
    assert "1 evidence pair(s) hidden" in out
    assert "Managed a team of nine" not in out  # the fabricated pair is not offered
    assert "SQL required" in out  # the verified pairs still are
    assert "Recommended version:" in out
    assert "temperature not sent" in out


# --- the sample resumes and repo hygiene ---------------------------------------------------


def test_every_sample_resume_loads() -> None:
    for version in config.RESUME_VERSIONS:
        text = score.load_resume(version, sample=True)
        assert len(text) > 500
        assert "EDUCATION" in text and "PROFESSIONAL EXPERIENCE" in text


def test_no_real_resume_is_tracked_by_git() -> None:
    """data/private/ must contribute nothing to the repo, and data/profile/ only samples."""
    tracked = subprocess.run(
        ["git", "ls-files", "data/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert [path for path in tracked if path.startswith("data/private/")] == []
    in_profile = [path for path in tracked if path.startswith("data/profile/")]
    assert in_profile, "expected the sample resumes to be committed"
    for path in in_profile:
        name = path.removeprefix("data/profile/")
        assert name == ".gitkeep" or name.startswith("sample_"), path
