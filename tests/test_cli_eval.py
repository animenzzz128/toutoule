"""Tests for the `eval` CLI command. No network, no real data/eval/ or data/private/."""

from pathlib import Path

import pytest
from fakes import FakeClient
from sqlalchemy import select

from toutoule import evalreport, evalrun, evalset, models
from toutoule.cli import main
from toutoule.db import get_engine, get_session_factory

FIXTURES = Path(__file__).parent / "fixtures"
VALID_ANSWER = (FIXTURES / "extraction_valid.json").read_text(encoding="utf-8")
SOURCE = (FIXTURES / "jd_valid.txt").read_text(encoding="utf-8")


@pytest.fixture
def eval_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal, self-contained eval set — never the real data/eval/."""
    d = tmp_path / "eval"
    (d / "raw").mkdir(parents=True)
    (d / "labels").mkdir(parents=True)
    (d / "raw" / "cnp-01.txt").write_text(SOURCE, encoding="utf-8")
    (d / "cases.csv").write_text(
        "case_id,segment,company,title,url,retrieved_on,language,notes\n"
        "cnp-01,cn_platform,Acme,PM,https://example.com/jd,2026-09-30,en,\n",
        encoding="utf-8",
    )
    label = evalset.blank_label(evalset.load_cases(d / "cases.csv")[0])
    (d / "labels" / "cnp-01.json").write_text(label.model_dump_json(), encoding="utf-8")
    (d / "equivalences.csv").write_text("field,label_value,system_value,note\n", encoding="utf-8")
    (d / "adjudications.csv").write_text(
        "case_id,system,field,system_value,verdict,note\n", encoding="utf-8"
    )
    monkeypatch.setattr(evalset, "EVAL_DIR", d)
    monkeypatch.setattr(evalrun, "RUNS_DIR", d / "runs")
    monkeypatch.setattr(evalrun, "EVAL_DB_DIR", tmp_path / "private_eval")
    monkeypatch.setattr(evalreport, "DOCS_RUNS_DIR", tmp_path / "docs_runs")
    monkeypatch.setattr(evalrun, "new_run_id", lambda: "run1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'real.db'}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-test-key")
    monkeypatch.setenv("MATCH_THRESHOLD", "65")
    return d


def use_fake_client(monkeypatch: pytest.MonkeyPatch, *answers: str) -> FakeClient:
    fake = FakeClient(*answers)
    monkeypatch.setattr("toutoule.cli.Anthropic", lambda **_: fake)
    return fake


def real_jobs(tmp_path: Path) -> list[models.Job]:
    engine = get_engine(f"sqlite:///{tmp_path / 'real.db'}")
    with get_session_factory(engine)() as session:
        return list(session.scalars(select(models.Job)))


def test_eval_scores_a_fresh_run_and_writes_nothing_to_the_real_jobs_table(
    eval_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = use_fake_client(monkeypatch, VALID_ANSWER)

    exit_code = main(["eval", "--system", "pipeline", "--cases", "cnp-01"])

    assert exit_code == 0
    assert len(fake.requests) == 1
    assert real_jobs(tmp_path) == []  # the eval DB is separate from DATABASE_URL
    out = capsys.readouterr().out
    assert "Critical hallucination" in out
    assert (tmp_path / "docs_runs" / "run1.md").exists()


def test_eval_resume_skips_the_case_already_run(
    eval_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_fake_client(monkeypatch, VALID_ANSWER)
    assert main(["eval", "--system", "pipeline", "--cases", "cnp-01"]) == 0
    fake_resume = use_fake_client(monkeypatch)  # no answers: any call would fail

    assert main(["eval", "--system", "pipeline", "--resume", "run1"]) == 0

    assert fake_resume.requests == []


def test_eval_rescore_makes_no_client_call(eval_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_fake_client(monkeypatch, VALID_ANSWER)
    assert main(["eval", "--system", "pipeline", "--cases", "cnp-01"]) == 0

    def _unexpected_client(**_: object) -> FakeClient:
        raise AssertionError("rescore must not construct a client")

    monkeypatch.setattr("toutoule.cli.Anthropic", _unexpected_client)

    assert main(["eval", "--system", "pipeline", "--rescore", "run1"]) == 0


def test_eval_writes_provisional_and_rescore_flags_into_eval_runs(
    eval_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_fake_client(monkeypatch, VALID_ANSWER)
    main(["eval", "--system", "pipeline", "--cases", "cnp-01"])

    engine = get_engine(f"sqlite:///{tmp_path / 'real.db'}")
    with get_session_factory(engine)() as session:
        row = session.scalars(select(models.EvalRun)).one()

    assert row.metrics_json["run_id"] == "run1"
    assert row.metrics_json["rescore"] is False
    assert isinstance(row.metrics_json["provisional"], bool)
