"""The eval runner (Task 1.7, Part B): calls both systems on the eval set and writes a
run folder. Each case's raw API call is isolated so one failure never stops the run.

The pipeline side calls extract.extract_job() completely unchanged, against a fresh
per-run SQLite database (data/private/eval/<run_id>.db) — never the real DATABASE_URL
jobs table. extract_job() has no cache of its own (Task 1.4): it calls the model every
time it's invoked, regardless of content_hash. A fresh database per run is not working
around a hidden cache; it just keeps each run's rows from piling up across runs.
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from toutoule import baseline, db, evalset, extract, models

RUNS_DIR = evalset.EVAL_DIR / "runs"
EVAL_DB_DIR = Path(__file__).parents[2] / "data" / "private" / "eval"
SLEEP_SECONDS = 1.0


def new_run_id(now: datetime | None = None) -> str:
    """A run id like "2026-10-02T1430". Just a label: not used for DST-sensitive logic."""
    return (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H%M")


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def eval_db_path(run_id: str) -> Path:
    return EVAL_DB_DIR / f"{run_id}.db"


def eval_db_url(run_id: str) -> str:
    return f"sqlite:///{eval_db_path(run_id).as_posix()}"


# --- meta.json -----------------------------------------------------------------------------


def _default_meta(run_id: str, model: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "model": model,
        "prompt_versions": {
            "pipeline": extract.PROMPT_VERSION,
            "baseline": baseline.PROMPT_VERSION,
        },
        "cases": [],
        "tokens": {"pipeline": {"input": 0, "output": 0}, "baseline": {"input": 0, "output": 0}},
        "seconds": {"pipeline": {}, "baseline": {}},
        "violations": {},
        "failures": {"pipeline": [], "baseline": []},
    }


def load_meta(rdir: Path) -> dict[str, Any]:
    return json.loads((rdir / "meta.json").read_text(encoding="utf-8"))


def save_meta(rdir: Path, meta: dict[str, Any]) -> None:
    (rdir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _accumulate_tokens(
    meta: dict[str, Any], system: str, input_tokens: int, output_tokens: int
) -> None:
    meta["tokens"][system]["input"] += input_tokens
    meta["tokens"][system]["output"] += output_tokens


# --- One case, one system -------------------------------------------------------------------


def _eval_source(session: Session) -> models.Source:
    """The eval run's own Source row, separate from the real "manual" one (ADR-005)."""
    source = session.scalars(select(models.Source).where(models.Source.adapter == "eval")).first()
    if source is None:
        source = models.Source(name="eval", tier=3, url="", adapter="eval")
        session.add(source)
        session.commit()
    return source


def run_pipeline_case(
    session: Session,
    case: evalset.CaseRow,
    raw_text: str,
    client: extract.ModelClient,
    model: str,
    rdir: Path,
    meta: dict[str, Any],
    sleep_fn: Any = time.sleep,
) -> None:
    """Run one case through the pipeline, unless its output file already exists."""
    out_path = rdir / "pipeline" / f"{case.case_id}.json"
    if out_path.exists():
        return
    job = models.Job(
        source_id=_eval_source(session).id,
        company="",
        title="",
        url=case.url,
        raw_text=raw_text,
        content_hash=extract.hash_content(raw_text),
    )
    session.add(job)
    session.commit()

    start = time.monotonic()
    try:
        extraction = extract.extract_job(session, job, client, model)
    except Exception as error:  # an API error and a validation failure both end the case here
        elapsed = time.monotonic() - start
        out_path.write_text(
            json.dumps({"failed": True, "error": f"{type(error).__name__}: {error}"}),
            encoding="utf-8",
        )
        meta["failures"]["pipeline"].append(case.case_id)
    else:
        elapsed = time.monotonic() - start
        out_path.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
        stored = session.scalars(
            select(models.Extraction).where(models.Extraction.job_id == job.id)
        ).one()
        _accumulate_tokens(meta, "pipeline", stored.input_tokens, stored.output_tokens)
        violation_count = session.scalar(
            select(func.count())
            .select_from(models.ExtractionViolation)
            .where(models.ExtractionViolation.job_id == job.id)
        )
        meta["violations"][case.case_id] = violation_count or 0
    meta["seconds"]["pipeline"][case.case_id] = elapsed
    save_meta(rdir, meta)
    sleep_fn(SLEEP_SECONDS)


def run_baseline_case(
    case: evalset.CaseRow,
    raw_text: str,
    client: extract.ModelClient,
    model: str,
    rdir: Path,
    meta: dict[str, Any],
    sleep_fn: Any = time.sleep,
) -> None:
    """Run one case through the baseline, unless its output (success or failure) exists."""
    text_path = rdir / "baseline" / f"{case.case_id}.txt"
    failed_path = rdir / "baseline" / f"{case.case_id}.json"
    if text_path.exists() or failed_path.exists():
        return

    start = time.monotonic()
    try:
        text, input_tokens, output_tokens = baseline.run_baseline(client, model, raw_text)
    except Exception as error:
        elapsed = time.monotonic() - start
        failed_path.write_text(
            json.dumps({"failed": True, "error": f"{type(error).__name__}: {error}"}),
            encoding="utf-8",
        )
        meta["failures"]["baseline"].append(case.case_id)
    else:
        elapsed = time.monotonic() - start
        text_path.write_text(text, encoding="utf-8")
        _accumulate_tokens(meta, "baseline", input_tokens, output_tokens)
    meta["seconds"]["baseline"][case.case_id] = elapsed
    save_meta(rdir, meta)
    sleep_fn(SLEEP_SECONDS)


# --- Orchestration ---------------------------------------------------------------------------


def _read_raw(case: evalset.CaseRow) -> str:
    return (evalset.EVAL_DIR / "raw" / f"{case.case_id}.txt").read_text(encoding="utf-8-sig")


def run_eval(
    run_id: str,
    cases: list[evalset.CaseRow],
    systems: set[str],
    client: extract.ModelClient,
    model: str,
    sleep_fn: Any = time.sleep,
) -> Path:
    """Run (or resume) one eval run. Systems already-done for a case are skipped per-case,
    so re-running with the same run_id after a partial failure just finishes the rest."""
    rdir = run_dir(run_id)
    (rdir / "pipeline").mkdir(parents=True, exist_ok=True)
    (rdir / "baseline").mkdir(parents=True, exist_ok=True)
    meta = load_meta(rdir) if (rdir / "meta.json").exists() else _default_meta(run_id, model)
    meta["cases"] = sorted(set(meta["cases"]) | {case.case_id for case in cases})
    save_meta(rdir, meta)

    if "pipeline" in systems:
        EVAL_DB_DIR.mkdir(parents=True, exist_ok=True)
        engine = db.get_engine(eval_db_url(run_id))
        db.init_db(engine)
        with db.get_session_factory(engine)() as session:
            for case in cases:
                raw_text = _read_raw(case)
                run_pipeline_case(session, case, raw_text, client, model, rdir, meta, sleep_fn)
    if "baseline" in systems:
        for case in cases:
            run_baseline_case(case, _read_raw(case), client, model, rdir, meta, sleep_fn)
    return rdir
