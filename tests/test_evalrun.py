"""Tests for evalrun.py. No network: fakes.FakeClient stands in for the Anthropic client.

monkeypatch is a built-in pytest fixture: it lets a test temporarily replace an attribute
(here, evalrun's and evalset's module-level path constants) and automatically restores the
original value afterward, even if the test fails — so tests never touch the real
data/eval/ or data/private/.
"""

import json
from pathlib import Path

from fakes import FakeClient
from sqlalchemy import select

from toutoule import evalrun, evalscore, evalset, models
from toutoule.db import get_engine, get_session_factory, init_db

FIXTURE = Path(__file__).parent / "fixtures" / "extraction_valid.json"
VALID_ANSWER = FIXTURE.read_text(encoding="utf-8")
SOURCE = (Path(__file__).parent / "fixtures" / "jd_valid.txt").read_text(encoding="utf-8")
MODEL = "claude-test-model"


def _write_blank_label(eval_dir: Path, case_id: str) -> None:
    label = evalset.blank_label(_case())
    (eval_dir / "labels").mkdir(parents=True, exist_ok=True)
    (eval_dir / "labels" / f"{case_id}.json").write_text(label.model_dump_json(), encoding="utf-8")
    (eval_dir / "equivalences.csv").write_text(
        "field,label_value,system_value,note\n", encoding="utf-8"
    )
    (eval_dir / "adjudications.csv").write_text(
        "case_id,system,field,system_value,verdict,note\n", encoding="utf-8"
    )


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


def test_score_run_reads_only_the_run_folder_labels_and_csvs(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    _write_blank_label(tmp_path, "cnp-01")
    client = FakeClient(VALID_ANSWER)
    evalrun.run_eval("run1", [_case()], {"pipeline"}, client, MODEL, sleep_fn=lambda _: None)

    score = evalrun.score_run("run1", "pipeline", cases=[_case()])

    assert client.requests == [client.requests[0]]  # score_run made no further calls
    assert score.scored_cases == ["cnp-01"]
    assert score.metrics.critical_hallucination.denominator == len(evalscore.CRITICAL_FIELDS)


def test_score_run_treats_a_recorded_pipeline_failure_as_missed(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    _write_blank_label(tmp_path, "cnp-01")
    rdir = evalrun.run_dir("run1")
    (rdir / "pipeline").mkdir(parents=True)
    (rdir / "pipeline" / "cnp-01.json").write_text(
        '{"failed": true, "error": "ExtractionFailed: boom"}', encoding="utf-8"
    )

    score = evalrun.score_run("run1", "pipeline", cases=[_case()])

    assert score.scored_cases == ["cnp-01"]
    assert score.metrics.critical_hallucination.count == 0


def test_score_run_skips_a_case_not_yet_run(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    _write_blank_label(tmp_path, "cnp-01")
    (evalrun.run_dir("run1") / "baseline").mkdir(parents=True)

    score = evalrun.score_run("run1", "baseline", cases=[_case()])

    assert score.scored_cases == []
    assert score.results == []


def test_save_eval_run_writes_run_id_model_system_and_rescore_into_metrics_json(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'real.db'}")
    init_db(engine)
    score = evalrun.RunScore(
        system="pipeline",
        results=[],
        metrics=evalscore.compute_metrics([]),
        recall=evalscore.Ratio(0, 0),
        scored_cases=[],
    )

    with get_session_factory(engine)() as session:
        evalrun.save_eval_run(session, "run1", MODEL, score, rescore=True)
        row = session.scalars(select(models.EvalRun)).one()

    assert row.metrics_json["run_id"] == "run1"
    assert row.metrics_json["model"] == MODEL
    assert row.metrics_json["system"] == "pipeline"
    assert row.metrics_json["rescore"] is True
    assert row.prompt_version == evalrun.extract.PROMPT_VERSION
