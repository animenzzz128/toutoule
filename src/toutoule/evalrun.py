"""The eval runner (Task 1.7, Part B): calls both systems on the eval set and writes a
run folder. Each case's raw API call is isolated so one failure never stops the run.

The pipeline side calls extract.extract_job() completely unchanged, against a fresh
per-run SQLite database (data/private/eval/<run_id>.db) — never the real DATABASE_URL
jobs table. extract_job() has no cache of its own (Task 1.4): it calls the model every
time it's invoked, regardless of content_hash. A fresh database per run is not working
around a hidden cache; it just keeps each run's rows from piling up across runs.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toutoule import baseline, evalset, extract, models

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
