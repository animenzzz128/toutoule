"""Tests for evalrun.py. No network: fakes.FakeClient stands in for the Anthropic client.

monkeypatch is a built-in pytest fixture: it lets a test temporarily replace an attribute
(here, evalrun's and evalset's module-level path constants) and automatically restores the
original value afterward, even if the test fails — so tests never touch the real
data/eval/ or data/private/.
"""

import json
from pathlib import Path

from fakes import FakeClient

from toutoule import evalrun, evalset
from toutoule.db import get_engine, get_session_factory, init_db

FIXTURE = Path(__file__).parent / "fixtures" / "extraction_valid.json"
VALID_ANSWER = FIXTURE.read_text(encoding="utf-8")
SOURCE = (Path(__file__).parent / "fixtures" / "jd_valid.txt").read_text(encoding="utf-8")
MODEL = "claude-test-model"


def _redirect_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(evalset, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(evalrun, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(evalrun, "EVAL_DB_DIR", tmp_path / "private_eval")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "cnp-01.txt").write_text(SOURCE, encoding="utf-8")


def _case() -> evalset.CaseRow:
    return evalset.CaseRow(
        case_id="cnp-01",
        segment="cn_platform",
        company="Acme",
        title="PM",
        url="https://example.com/jd",
        retrieved_on="2026-09-30",
        language="en",
    )


def test_run_pipeline_case_skips_if_output_already_exists(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    engine = get_engine(f"sqlite:///{tmp_path / 'eval.db'}")
    init_db(engine)
    rdir = evalrun.run_dir("run1")
    (rdir / "pipeline").mkdir(parents=True)
    (rdir / "pipeline" / "cnp-01.json").write_text("{}", encoding="utf-8")
    client = FakeClient(VALID_ANSWER)
    meta = evalrun._default_meta("run1", MODEL)

    with get_session_factory(engine)() as session:
        evalrun.run_pipeline_case(
            session, _case(), SOURCE, client, MODEL, rdir, meta, sleep_fn=lambda _: None
        )

    assert client.requests == []  # never called: the output file already existed


def test_run_pipeline_case_records_failure_and_does_not_raise(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    engine = get_engine(f"sqlite:///{tmp_path / 'eval.db'}")
    init_db(engine)
    rdir = evalrun.run_dir("run1")
    (rdir / "pipeline").mkdir(parents=True)
    client = FakeClient("not json at all", "still not json")  # fails validation twice
    meta = evalrun._default_meta("run1", MODEL)

    with get_session_factory(engine)() as session:
        evalrun.run_pipeline_case(
            session, _case(), SOURCE, client, MODEL, rdir, meta, sleep_fn=lambda _: None
        )

    saved = json.loads((rdir / "pipeline" / "cnp-01.json").read_text(encoding="utf-8"))
    assert saved["failed"] is True
    assert "ExtractionFailed" in saved["error"]
    assert meta["failures"]["pipeline"] == ["cnp-01"]


def test_run_baseline_case_skips_if_output_already_exists(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    rdir = evalrun.run_dir("run1")
    (rdir / "baseline").mkdir(parents=True)
    (rdir / "baseline" / "cnp-01.txt").write_text("deadline: not stated\n", encoding="utf-8")
    client = FakeClient("deadline: 2026-10-31\n")
    meta = evalrun._default_meta("run1", MODEL)

    evalrun.run_baseline_case(_case(), SOURCE, client, MODEL, rdir, meta, sleep_fn=lambda _: None)

    assert client.requests == []


def test_two_runs_on_the_same_posting_both_call_the_client(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    client = FakeClient(VALID_ANSWER, VALID_ANSWER)

    evalrun.run_eval("run1", [_case()], {"pipeline"}, client, MODEL, sleep_fn=lambda _: None)
    evalrun.run_eval("run2", [_case()], {"pipeline"}, client, MODEL, sleep_fn=lambda _: None)

    assert len(client.requests) == 2  # a fresh eval database per run: no cross-run caching
    assert evalrun.eval_db_path("run1") != evalrun.eval_db_path("run2")
    assert evalrun.eval_db_path("run1").exists()
    assert evalrun.eval_db_path("run2").exists()
