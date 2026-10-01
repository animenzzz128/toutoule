"""The markdown report for one eval run (05_EVAL_SPEC.md §2), written to
docs/eval/runs/<run_id>.md. Pure formatting: everything it needs is already computed by
evalrun.score_run() and meta.json — no API calls, no database.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from toutoule import evalscore
from toutoule.evalrun import RunScore

DOCS_RUNS_DIR = Path(__file__).parents[2] / "docs" / "eval" / "runs"
SYSTEMS = ("pipeline", "baseline")


@dataclass
class MetricSpec:
    label: str
    target_text: str
    get_ratio: Callable[[RunScore], evalscore.Ratio]
    passes: Callable[[evalscore.Ratio], bool]


def _hallucination(score: RunScore) -> evalscore.Ratio:
    return score.metrics.critical_hallucination


def _critical_accuracy(score: RunScore) -> evalscore.Ratio:
    return score.metrics.critical_accuracy


def _false_negative(score: RunScore) -> evalscore.Ratio:
    return score.metrics.critical_false_negative


def _important_accuracy(score: RunScore) -> evalscore.Ratio:
    return score.metrics.important_accuracy


def _recall(score: RunScore) -> evalscore.Ratio:
    return score.recall


METRIC_SPECS = [
    MetricSpec("Critical hallucination", "0%", _hallucination, lambda r: r.count == 0),
    MetricSpec("Critical accuracy", "≥95%", _critical_accuracy, lambda r: r.percent >= 95),
    MetricSpec("Critical false-negative", "≤10%", _false_negative, lambda r: r.percent <= 10),
    MetricSpec("Important accuracy", "≥90%", _important_accuracy, lambda r: r.percent >= 90),
    MetricSpec("Reference recall", "≥80%", _recall, lambda r: r.percent >= 80),
]


def _tier_table(scores: dict[str, RunScore]) -> str:
    lines = ["| Metric | Target | pipeline | baseline |", "|---|---|---|---|"]
    for spec in METRIC_SPECS:
        cells = [spec.label, spec.target_text]
        for system in SYSTEMS:
            score = scores.get(system)
            if score is None:
                cells.append("—")
                continue
            ratio = spec.get_ratio(score)
            cells.append(f"{ratio} {'✅' if spec.passes(ratio) else '❌'}")
        lines.append("| " + " | ".join(cells) + " |")
    missed_cells = ["Important missed", "no target"]
    for system in SYSTEMS:
        score = scores.get(system)
        missed_cells.append(str(score.metrics.important_missed) if score else "—")
    lines.append("| " + " | ".join(missed_cells) + " |")
    return "\n".join(lines)
