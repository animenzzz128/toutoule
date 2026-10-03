"""Match-score calibration (Task 1.9 Part B, D-010 §7).

The 20 hand scores in data/eval/human_scores.csv are the human baseline. This module
scores the same 20 postings with the real resumes, stores every raw response, and
recomputes agreement from those stored responses without calling the API again.

Everything a run produces lives under data/private/score_runs/<run_id>/, because a scored
posting carries quotes from the owner's real resume (D-010 §9). Only the public report in
docs/eval/scoring/ leaves that directory, and it carries no resume text at all.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from toutoule import config, evalrun, evalset, extract, score

# Private: raw responses, parsed results, resume snapshots, the full report.
SCORE_RUNS_DIR = Path(__file__).parents[2] / "data" / "private" / "score_runs"
# Public: the agreement report, which quotes nothing from a resume.
PUBLIC_REPORT_DIR = Path(__file__).parents[2] / "docs" / "eval" / "scoring"
HUMAN_SCORES = evalset.EVAL_DIR / "human_scores.csv"
RAW_DIR = evalset.EVAL_DIR / "raw"


def new_run_id(now: datetime | None = None) -> str:
    """A run id like "2026-10-02T2219-score": the eval format plus a suffix.

    The suffix keeps calibration runs from being mistaken for extraction runs in a
    directory listing, since the two have different report shapes.
    """
    return f"{evalrun.new_run_id(now)}-score"


def run_dir(run_id: str) -> Path:
    return SCORE_RUNS_DIR / run_id


def derived_run_id(run_id: str) -> str:
    """The one derived run D-010 §8 allows: a reweighting of an existing run."""
    return f"{run_id}-w2"


class RecordingClient:
    """Wraps a model client and keeps the text of every response it returns.

    score.py has no way to hand back the raw reply — it returns parsed objects — and
    calibration has to store exactly what the model said, including the answer that failed
    validation on a retry. Wrapping the client captures that without changing the scorer,
    so the code path under calibration is the same one production runs.
    """

    def __init__(self, inner: score.extract.ModelClient) -> None:
        self.inner = inner
        self.messages = self  # so client.messages.create(...) lands on create below
        self.api_calls = 0
        self._responses: list[str] = []

    def create(self, **kwargs: Any) -> Any:
        response = self.inner.messages.create(**kwargs)
        self.api_calls += 1
        self._responses.append(
            "".join(block.text for block in response.content if block.type == "text")
        )
        return response

    def take(self) -> list[str]:
        """Return the responses recorded since the last call, and start a new batch."""
        recorded, self._responses = self._responses, []
        return recorded


def default_meta(run_id: str, model: str, prompt_version: str, weights: dict[str, int]) -> dict:
    """The run's record of how it was produced. Read back by --rescore and both reports."""
    return {
        "run_id": run_id,
        "model": model,
        "prompt_version": prompt_version,
        "weights": dict(weights),
        "commit": evalrun.current_commit(),
        "model_settings": score.MODEL_SETTINGS,
        "resume_versions": list(config.RESUME_VERSIONS),
        "api_calls": 0,
        "tokens": {"input": 0, "output": 0},
        "cases": [],
        "failures": [],
    }


def load_meta(rdir: Path) -> dict[str, Any]:
    return json.loads((rdir / "meta.json").read_text(encoding="utf-8"))


def save_meta(rdir: Path, meta: dict[str, Any]) -> None:
    (rdir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def snapshot_resumes(rdir: Path, sample: bool = False) -> dict[str, str]:
    """Copy the resume each version was scored against into the run folder.

    --rescore re-runs verify_pairs, which checks quotes against the resume text. Without a
    snapshot, editing a resume later would silently change an old run's verified counts,
    and the run would no longer say what it measured.
    """
    directory = rdir / "resumes"
    directory.mkdir(parents=True, exist_ok=True)
    texts = {}
    for version in config.RESUME_VERSIONS:
        text = score.load_resume(version, sample=sample)
        (directory / f"{version}.md").write_text(text, encoding="utf-8")
        texts[version] = text
    return texts


def load_resume_snapshot(rdir: Path, version: str) -> str:
    path = rdir / "resumes" / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"no resume snapshot at {path}; was this run interrupted?")
    return path.read_text(encoding="utf-8")


def read_raw_posting(case_id: str) -> str:
    """The posting text for one calibration case, loaded the way the eval harness loads it."""
    path = RAW_DIR / f"{case_id}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"{case_id}: no posting at {path}. Every row of human_scores.csv needs one."
        )
    return path.read_text(encoding="utf-8-sig")


def current_prompt_version() -> str:
    version, _ = extract.load_prompt_by_name(config.SCORE_PROMPT)
    return version


def copy_run(source: Path, destination: Path) -> None:
    """Copy a run folder so a derived run starts from exactly what the base run saw."""
    shutil.copytree(source, destination, dirs_exist_ok=False)
