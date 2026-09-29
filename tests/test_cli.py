import os
import subprocess
import sys
from pathlib import Path

import pytest

from toutoule.cli import main
from toutoule.config import Settings


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
