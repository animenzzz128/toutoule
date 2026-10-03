"""Match-score calibration (Task 1.9 Part B, D-010 §7).

The 20 hand scores in data/eval/human_scores.csv are the human baseline. This module
scores the same 20 postings with the real resumes, stores every raw response, and
recomputes agreement from those stored responses without calling the API again.

Everything a run produces lives under data/private/score_runs/<run_id>/, because a scored
posting carries quotes from the owner's real resume (D-010 §9). Only the public report in
docs/eval/scoring/ leaves that directory, and it carries no resume text at all.
"""

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median
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
        self.input_tokens = 0
        self.output_tokens = 0
        self._recorded: list[tuple[str, str]] = []

    def create(self, **kwargs: Any) -> Any:
        response = self.inner.messages.create(**kwargs)
        self.api_calls += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        # The first user turn carries both the posting and the resume, which is what lets
        # a reply be attributed to the version that produced it, retries included.
        self._recorded.append(
            (
                str(kwargs["messages"][0]["content"]),
                "".join(block.text for block in response.content if block.type == "text"),
            )
        )
        return response

    def take(self) -> list[tuple[str, str]]:
        """Return (request, reply) pairs recorded since the last call, and start a batch."""
        recorded, self._recorded = self._recorded, []
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


# --- the calibration set ------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationCase:
    """One posting the owner scored by hand during Task 1.6, joined to its raw text."""

    case_id: str
    human_score: int
    reason: str
    segment: str


def load_calibration_cases(
    limit: int | None = None, case_ids: list[str] | None = None
) -> list[CalibrationCase]:
    """The rows of human_scores.csv, in file order, joined to cases.csv for the segment.

    Raises FileNotFoundError naming the case if a row has no posting in data/eval/raw/:
    a calibration set that silently drops a posting would report agreement over a
    different denominator than the one it claims.
    """
    segments = {
        case.case_id: case.segment for case in evalset.load_cases(evalset.EVAL_DIR / "cases.csv")
    }
    rows: list[CalibrationCase] = []
    with HUMAN_SCORES.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            case_id = row["case_id"].strip()
            if case_ids is not None and case_id not in case_ids:
                continue
            read_raw_posting(case_id)  # fail now, by name, rather than mid-run
            rows.append(
                CalibrationCase(
                    case_id=case_id,
                    human_score=int(row["score"]),
                    reason=(row.get("reason") or "").strip(),
                    segment=segments.get(case_id, "unknown"),
                )
            )
    if case_ids is not None:
        missing = [c for c in case_ids if c not in {r.case_id for r in rows}]
        if missing:
            raise KeyError(f"not in human_scores.csv: {', '.join(missing)}")
    return rows[:limit] if limit else rows


# --- running ------------------------------------------------------------------------------


def _attribute(recorded: list[tuple[str, str]], resumes: dict[str, str]) -> dict[str, list[str]]:
    """Group raw replies by the resume version whose text appears in their request."""
    by_version: dict[str, list[str]] = {version: [] for version in resumes}
    for request, reply in recorded:
        for version, text in resumes.items():
            if text in request:
                by_version[version].append(reply)
                break
    return by_version


def score_one_case(
    rdir: Path,
    case: CalibrationCase,
    client: RecordingClient,
    resumes: dict[str, str],
    model: str,
    sample: bool = False,
) -> dict[str, Any]:
    """Score one posting against all three versions and write <case_id>.json. 3 calls."""
    raw_text = read_raw_posting(case.case_id)
    client.take()  # drop anything left from a previous case
    scored = score.score_job(raw_text, client, sample=sample, model=model)
    by_version = _attribute(client.take(), resumes)
    recommended = scored[0].result.recommended_version
    system_score = next(s.result.score for s in scored if s.result.resume_version == recommended)
    payload = {
        "case_id": case.case_id,
        "segment": case.segment,
        "human_score": case.human_score,
        "reason": case.reason,
        "recommended_version": recommended,
        "system_score": system_score,
        "versions": {
            item.result.resume_version: {
                "result": item.result.model_dump(mode="json"),
                "raw_responses": by_version.get(item.result.resume_version, []),
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
            }
            for item in scored
        },
    }
    (rdir / f"{case.case_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def load_case_payload(rdir: Path, case_id: str) -> dict[str, Any]:
    return json.loads((rdir / f"{case_id}.json").read_text(encoding="utf-8"))


# --- agreement (D-010 §7) -------------------------------------------------------------------

# |system − human| ≤ 10 counts as agreement. The boundary is inclusive: a 10-point gap
# agrees, an 11-point gap does not.
AGREEMENT_TOLERANCE = 10


@dataclass(frozen=True)
class Agreement:
    within: int
    total: int

    @property
    def percent(self) -> float:
        return 100.0 * self.within / self.total if self.total else 0.0

    def __str__(self) -> str:
        return f"{self.within} / {self.total} ({self.percent:.0f}%)"


@dataclass(frozen=True)
class CaseOutcome:
    """One posting's human score beside the system's, with what produced it."""

    case_id: str
    segment: str
    human: int
    system: int
    recommended: str
    dimensions: dict[str, int]
    version_scores: dict[str, int]

    @property
    def diff(self) -> int:
        """system − human: positive means the system rated the posting higher."""
        return self.system - self.human

    @property
    def agrees(self) -> bool:
        return abs(self.diff) <= AGREEMENT_TOLERANCE


@dataclass(frozen=True)
class CalibrationMetrics:
    outcomes: list[CaseOutcome]
    agreement: Agreement
    floor_guess: int
    floor: Agreement
    mean_signed_error: float
    mean_absolute_error: float
    by_segment: dict[str, Agreement]
    segment_errors: dict[str, tuple[float, float]]
    recommended_counts: dict[str, int]
    evidence_verified: tuple[int, int]


def constant_guess(human_scores: list[int]) -> int:
    """The score a system that does no work would give every posting: the human median.

    D-010 §7 credits the system only with agreement above this floor. Without it, a
    calibration set clustered around one value can be half-matched by a constant.
    """
    return round(median(human_scores))


def _agreement(outcomes: list[CaseOutcome]) -> Agreement:
    return Agreement(sum(1 for o in outcomes if o.agrees), len(outcomes))


def compute_metrics(payloads: list[dict[str, Any]]) -> CalibrationMetrics:
    """Everything both reports need, from the saved per-case files. No API calls."""
    outcomes = [
        CaseOutcome(
            case_id=p["case_id"],
            segment=p["segment"],
            human=p["human_score"],
            system=p["system_score"],
            recommended=p["recommended_version"],
            dimensions={
                name: p["versions"][p["recommended_version"]]["result"]["dimensions"][name]["score"]
                for name in config.SCORE_WEIGHTS
            },
            version_scores={v: d["result"]["score"] for v, d in p["versions"].items()},
        )
        for p in payloads
    ]
    humans = [o.human for o in outcomes]
    guess = constant_guess(humans)
    diffs = [o.diff for o in outcomes]

    segments = sorted({o.segment for o in outcomes})
    by_segment, segment_errors = {}, {}
    for segment in segments:
        rows = [o for o in outcomes if o.segment == segment]
        by_segment[segment] = _agreement(rows)
        segment_errors[segment] = (
            mean(o.diff for o in rows),
            mean(abs(o.diff) for o in rows),
        )

    verified = sum(
        1
        for p in payloads
        for version in p["versions"].values()
        for pair in version["result"]["evidence_pairs"]
        if pair["verified"]
    )
    pairs_total = sum(
        len(version["result"]["evidence_pairs"])
        for p in payloads
        for version in p["versions"].values()
    )
    counts = {version: 0 for version in config.RESUME_VERSIONS}
    for outcome in outcomes:
        counts[outcome.recommended] = counts.get(outcome.recommended, 0) + 1

    return CalibrationMetrics(
        outcomes=outcomes,
        agreement=_agreement(outcomes),
        floor_guess=guess,
        floor=Agreement(
            sum(1 for h in humans if abs(guess - h) <= AGREEMENT_TOLERANCE), len(humans)
        ),
        mean_signed_error=mean(diffs) if diffs else 0.0,
        mean_absolute_error=mean(abs(d) for d in diffs) if diffs else 0.0,
        by_segment=by_segment,
        segment_errors=segment_errors,
        recommended_counts=counts,
        evidence_verified=(verified, pairs_total),
    )
