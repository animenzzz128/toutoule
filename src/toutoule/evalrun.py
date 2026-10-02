"""The eval runner (Task 1.7, Part B): calls both systems on the eval set and writes a
run folder. Each case's raw API call is isolated so one failure never stops the run.

The pipeline side calls extract.extract_job() completely unchanged, against a fresh
per-run SQLite database (data/private/eval/<run_id>.db) — never the real DATABASE_URL
jobs table. extract_job() has no cache of its own (Task 1.4): it calls the model every
time it's invoked, regardless of content_hash. A fresh database per run is not working
around a hidden cache; it just keeps each run's rows from piling up across runs.
"""

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from toutoule import baseline, db, evalscore, evalset, extract, models, schemas

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


def current_commit() -> str | None:
    """The HEAD commit, with "-dirty" appended when the tree has uncommitted changes.

    Recorded per run so two runs of the same prompt under different code (v3 and v4 both
    run extract_v3) can be told apart. None when git isn't available or this isn't a
    checkout — a missing hash is better than a wrong one.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{head}-dirty" if status else head


def _default_meta(
    run_id: str, model: str, pipeline_prompt_version: str | None = None
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "model": model,
        "commit": current_commit(),
        "prompt_versions": {
            "pipeline": pipeline_prompt_version or extract.PROMPT_VERSION,
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
    prompt: tuple[str, str] | None = None,
) -> None:
    """Run one case through the pipeline, unless its output file already exists.

    prompt is (version, body); None means extract_job's own default (extract_v1).
    """
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

    prompt_version, prompt_body = prompt or (extract.PROMPT_VERSION, extract.PROMPT_BODY)
    start = time.monotonic()
    try:
        extraction = extract.extract_job(
            session, job, client, model, prompt_version=prompt_version, prompt_body=prompt_body
        )
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
    prompt: tuple[str, str] | None = None,
) -> Path:
    """Run (or resume) one eval run. Systems already-done for a case are skipped per-case,
    so re-running with the same run_id after a partial failure just finishes the rest.

    prompt is (version, body) for the pipeline system; None means extract_v1 (the
    module default). It only affects a freshly-created run: a resumed run keeps the
    prompt version recorded in its own meta.json.
    """
    prompt_version = prompt[0] if prompt else None
    rdir = run_dir(run_id)
    (rdir / "pipeline").mkdir(parents=True, exist_ok=True)
    (rdir / "baseline").mkdir(parents=True, exist_ok=True)
    if (rdir / "meta.json").exists():
        meta = load_meta(rdir)
    else:
        meta = _default_meta(run_id, model, prompt_version)
    meta["cases"] = sorted(set(meta["cases"]) | {case.case_id for case in cases})
    save_meta(rdir, meta)

    if "pipeline" in systems:
        EVAL_DB_DIR.mkdir(parents=True, exist_ok=True)
        engine = db.get_engine(eval_db_url(run_id))
        db.init_db(engine)
        with db.get_session_factory(engine)() as session:
            for case in cases:
                raw_text = _read_raw(case)
                run_pipeline_case(
                    session, case, raw_text, client, model, rdir, meta, sleep_fn, prompt
                )
    if "baseline" in systems:
        for case in cases:
            run_baseline_case(case, _read_raw(case), client, model, rdir, meta, sleep_fn)
    return rdir


# --- Scoring: run folder + labels + the two CSVs, never the API ----------------------------


def _load_pipeline_output(rdir: Path, case_id: str) -> evalscore.SystemOutput | None:
    path = rdir / "pipeline" / f"{case_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("failed"):
        return evalscore.failed_output()
    return evalscore.from_extraction(schemas.Extraction.model_validate(data))


def _load_baseline_output(rdir: Path, case_id: str) -> evalscore.SystemOutput | None:
    if (rdir / "baseline" / f"{case_id}.json").exists():  # a recorded failure
        return evalscore.failed_output()
    path = rdir / "baseline" / f"{case_id}.txt"
    if not path.exists():
        return None
    return baseline.parse_baseline(path.read_text(encoding="utf-8"))


def load_system_output(rdir: Path, system: str, case_id: str) -> evalscore.SystemOutput | None:
    """None means this case hasn't been run yet for this system — not scored, not failed."""
    if system == "pipeline":
        return _load_pipeline_output(rdir, case_id)
    return _load_baseline_output(rdir, case_id)


@dataclass
class RunScore:
    system: str
    results: list[evalscore.FieldResult]
    metrics: evalscore.Metrics
    recall: evalscore.ReferenceRecall
    scored_cases: list[str]


def _sum_ratios(ratios: list[evalscore.Ratio]) -> evalscore.Ratio:
    return evalscore.Ratio(sum(r.count for r in ratios), sum(r.denominator for r in ratios))


def score_run(run_id: str, system: str, cases: list[evalset.CaseRow] | None = None) -> RunScore:
    """Score one system's half of a run. No API calls: reads the run folder, the labels,
    and equivalences.csv/adjudications.csv only."""
    rdir = run_dir(run_id)
    if cases is None:
        meta = load_meta(rdir)
        all_cases = evalset.load_cases(evalset.EVAL_DIR / "cases.csv")
        cases = [case for case in all_cases if case.case_id in meta["cases"]]
    equivalences = evalscore.load_equivalences(evalset.EVAL_DIR / "equivalences.csv")
    adjudications = evalscore.load_adjudications(evalset.EVAL_DIR / "adjudications.csv")

    results: list[evalscore.FieldResult] = []
    scored_cases: list[str] = []
    recalls: list[evalscore.ReferenceRecall] = []
    for case in cases:
        output = load_system_output(rdir, system, case.case_id)
        if output is None:
            continue
        label = evalset.load_label(case.case_id, evalset.EVAL_DIR / "labels")
        results.extend(evalscore.score_case(label, output, equivalences, adjudications, system))
        recalls.append(evalscore.reference_recall(label, output))
        scored_cases.append(case.case_id)

    recall = evalscore.ReferenceRecall(
        skills=_sum_ratios([r.skills for r in recalls]),
        responsibilities=_sum_ratios([r.responsibilities for r in recalls]),
        team_or_function=_sum_ratios([r.team_or_function for r in recalls]),
        total=_sum_ratios([r.total for r in recalls]),
    )
    return RunScore(
        system=system,
        results=results,
        metrics=evalscore.compute_metrics(results),
        recall=recall,
        scored_cases=scored_cases,
    )


# --- eval_runs (the real DATABASE_URL: this table tracks eval history, not eval postings) --


def _ratio_json(ratio: evalscore.Ratio) -> dict[str, int]:
    return {"count": ratio.count, "denominator": ratio.denominator}


def eval_run_metrics_json(
    run_id: str, model: str, score: RunScore, rescore: bool
) -> dict[str, Any]:
    """metrics_json for one models.EvalRun row. No new columns (per the owner's call):
    run_id, model, system and rescore all live inside this JSON blob instead."""
    metrics = score.metrics
    return {
        "run_id": run_id,
        "model": model,
        "system": score.system,
        "rescore": rescore,
        "critical_hallucination": _ratio_json(metrics.critical_hallucination),
        "critical_accuracy": _ratio_json(metrics.critical_accuracy),
        "critical_false_negative": _ratio_json(metrics.critical_false_negative),
        "important_accuracy": _ratio_json(metrics.important_accuracy),
        "important_missed": metrics.important_missed,
        "reference_recall": {
            "skills": _ratio_json(score.recall.skills),
            "responsibilities": _ratio_json(score.recall.responsibilities),
            "team_or_function": _ratio_json(score.recall.team_or_function),
            "total": _ratio_json(score.recall.total),
        },
        "pending": metrics.pending,
        "provisional": metrics.provisional,
    }


def save_eval_run(
    session: Session, run_id: str, model: str, score: RunScore, rescore: bool, prompt_version: str
) -> models.EvalRun:
    """Insert one eval_runs row for one system. The caller's session decides which
    database — this is the real DATABASE_URL in practice, since eval_runs tracks eval
    history, not eval postings.

    prompt_version is the one actually used for this run (meta.json's record of it), not
    necessarily the current module default — a run can be scored long after a newer
    prompt version has replaced it as the default.
    """
    row = models.EvalRun(
        prompt_version=prompt_version,
        metrics_json=eval_run_metrics_json(run_id, model, score, rescore),
    )
    session.add(row)
    session.commit()
    return row
