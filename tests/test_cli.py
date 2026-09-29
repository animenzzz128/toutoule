import os
import subprocess
import sys
from pathlib import Path

import pytest
from fakes import FakeClient
from sqlalchemy import select

from toutoule import extract, models
from toutoule.cli import main
from toutoule.config import Settings
from toutoule.db import get_engine, get_session_factory

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def run_in_empty_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run from a folder with no .env, so the owner's real .env is never read."""
    monkeypatch.chdir(tmp_path)


@pytest.mark.usefixtures("valid_env")
def test_check_config_ok(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["check-config"])

    assert exit_code == 0
    assert capsys.readouterr().out == "Config OK\n"


@pytest.mark.usefixtures("valid_env")
def test_check_config_reports_missing_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    exit_code = main(["check-config"])

    assert exit_code == 1
    error_output = capsys.readouterr().err
    assert error_output.count("\n") == 1  # exactly one line
    assert "ANTHROPIC_API_KEY is missing" in error_output


def test_real_command_exits_without_traceback(tmp_path: Path) -> None:
    """Run the actual command in a fresh process with no settings at all."""
    env = {k: v for k, v in os.environ.items() if k.lower() not in Settings.model_fields}

    result = subprocess.run(
        [sys.executable, "-m", "toutoule.cli", "check-config"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith("Config error: ANTHROPIC_API_KEY is missing.")


@pytest.mark.usefixtures("valid_env")
def test_init_db_creates_tables_then_reports_none_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")

    assert main(["init-db"]) == 0
    first = capsys.readouterr().out
    assert first.startswith("Created tables: ")
    assert "jobs" in first and "extractions" in first

    assert main(["init-db"]) == 0
    assert capsys.readouterr().out == "All tables already exist.\n"


def test_init_db_without_settings_gives_one_line_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init-db"]) == 1
    error_output = capsys.readouterr().err
    assert error_output.count("\n") == 1
    assert error_output.startswith("Config error:")


# --- extract -----------------------------------------------------------------------------


@pytest.fixture
def jd_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A posting on disk and a throwaway database; settings come from valid_env."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    path = tmp_path / "jd.txt"
    path.write_text((FIXTURES / "jd_valid.txt").read_text(encoding="utf-8"), encoding="utf-8")
    return path


def use_fake_client(monkeypatch: pytest.MonkeyPatch, *answers: str) -> FakeClient:
    """Make the CLI build our fake instead of the real Anthropic client."""
    fake = FakeClient(*answers)
    monkeypatch.setattr("toutoule.cli.Anthropic", lambda **_: fake)
    return fake


def valid_answer() -> str:
    return (FIXTURES / "extraction_valid.json").read_text(encoding="utf-8")


def read_jobs(tmp_path: Path) -> list[models.Job]:
    with get_session_factory(get_engine(f"sqlite:///{tmp_path / 'cli.db'}"))() as session:
        return list(session.scalars(select(models.Job)))


@pytest.mark.usefixtures("valid_env")
def test_extract_prints_fields_violations_and_tokens(
    jd_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = use_fake_client(monkeypatch, valid_answer())

    assert main(["extract", str(jd_file)]) == 0

    out = capsys.readouterr().out
    assert "critical.deadline" in out and "2026-10-31" in out
    assert "critical.visa_sponsorship        False   Not stated" in out
    assert "Violations: none" in out
    assert "Tokens: input 1000, output 300" in out
    assert len(fake.requests) == 1
    (job,) = read_jobs(tmp_path)
    assert job.status == models.JobStatus.EXTRACTED
    assert job.company == "Hexa Commerce (fictional)"
    assert job.url.startswith("file:///")
    assert job.content_hash == extract.hash_content(jd_file.read_text(encoding="utf-8"))


@pytest.mark.usefixtures("valid_env")
def test_same_text_prompt_and_model_makes_no_call(
    jd_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    use_fake_client(monkeypatch, valid_answer())
    main(["extract", str(jd_file)])
    second = use_fake_client(monkeypatch)  # no answers: any call would fail

    assert main(["extract", str(jd_file)]) == 0

    assert second.requests == []
    assert "no API call" in capsys.readouterr().out
    assert len(read_jobs(tmp_path)) == 1


@pytest.mark.usefixtures("valid_env")
@pytest.mark.parametrize("change", ["model", "prompt_version"])
def test_new_model_or_prompt_version_re_extracts(
    change: str, jd_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_fake_client(monkeypatch, valid_answer())
    main(["extract", str(jd_file)])
    if change == "model":
        monkeypatch.setenv("EXTRACTION_MODEL", "claude-sonnet-5")
    else:
        monkeypatch.setattr(extract, "PROMPT_VERSION", "extract_v2")
    second = use_fake_client(monkeypatch, valid_answer())

    assert main(["extract", str(jd_file)]) == 0

    assert len(second.requests) == 1


@pytest.mark.usefixtures("valid_env")
def test_extract_failure_exits_1_and_marks_job(
    jd_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    use_fake_client(monkeypatch, "not json", "still not json")

    assert main(["extract", str(jd_file)]) == 1

    assert "Extraction failed" in capsys.readouterr().err
    (job,) = read_jobs(tmp_path)
    assert job.status == models.JobStatus.EXTRACTION_FAILED


@pytest.mark.usefixtures("valid_env")
def test_extract_missing_file_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["extract", "no_such_file.txt"]) == 1
    assert "no_such_file.txt" in capsys.readouterr().err


@pytest.mark.usefixtures("valid_env")
def test_extract_output_survives_a_non_utf8_pipe(
    jd_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chinese evidence must print even where Python would default to cp1252 (Windows).

    Forcing PYTHONIOENCODING=cp1252 reproduces that failure on any OS, including Linux CI.
    """
    use_fake_client(monkeypatch, valid_answer())
    main(["extract", str(jd_file)])  # in-process, with the fake: fills the cache
    env = {k: v for k, v in os.environ.items() if k.lower() not in Settings.model_fields}
    env |= {
        "ANTHROPIC_API_KEY": "sk-ant-fake-test-key",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'cli.db'}",
        "MATCH_THRESHOLD": "65",
        "PYTHONIOENCODING": "cp1252",
        # Belt and braces: if the cache ever missed, a call would fail locally, not bill.
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:9",
    }

    result = subprocess.run(
        [sys.executable, "-m", "toutoule.cli", "extract", str(jd_file)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    out = result.stdout.decode("utf-8")
    assert "no API call" in out
    assert "网申截止时间：2026年10月31日" in out
