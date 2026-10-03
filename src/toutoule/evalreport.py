"""The markdown report for one eval run (05_EVAL_SPEC.md §2), written to
docs/eval/runs/<run_id>.md. Pure formatting: everything it needs is already computed by
evalrun.score_run() and meta.json — no API calls, no database.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from toutoule import evalscore
from toutoule.evalrun import RunScore

DOCS_RUNS_DIR = Path(__file__).parents[2] / "docs" / "eval" / "runs"
SYSTEMS = ("pipeline", "baseline")


@dataclass
class MetricSpec:
    label: str
    target_text: str
    get_ratio: Callable[[RunScore], evalscore.Ratio]
    # None means "no target, just report the number" — used for the per-field recall
    # breakdown rows, which exist for visibility, not grading (only the total is graded).
    passes: Callable[[evalscore.Ratio], bool] | None


def _hallucination(score: RunScore) -> evalscore.Ratio:
    return score.metrics.critical_hallucination


def _critical_accuracy(score: RunScore) -> evalscore.Ratio:
    return score.metrics.critical_accuracy


def _false_negative(score: RunScore) -> evalscore.Ratio:
    return score.metrics.critical_false_negative


def _important_accuracy(score: RunScore) -> evalscore.Ratio:
    return score.metrics.important_accuracy


def _recall_total(score: RunScore) -> evalscore.Ratio:
    return score.recall.total


def _recall_skills(score: RunScore) -> evalscore.Ratio:
    return score.recall.skills


def _recall_responsibilities(score: RunScore) -> evalscore.Ratio:
    return score.recall.responsibilities


def _recall_team(score: RunScore) -> evalscore.Ratio:
    return score.recall.team_or_function


METRIC_SPECS = [
    MetricSpec("Critical hallucination", "0%", _hallucination, lambda r: r.count == 0),
    MetricSpec("Critical accuracy", "≥95%", _critical_accuracy, lambda r: r.percent >= 95),
    MetricSpec("Critical false-negative", "≤10%", _false_negative, lambda r: r.percent <= 10),
    MetricSpec("Important accuracy", "≥90%", _important_accuracy, lambda r: r.percent >= 90),
    MetricSpec("Reference recall (total)", "≥80%", _recall_total, lambda r: r.percent >= 80),
    MetricSpec("Reference recall — skills", "no target", _recall_skills, None),
    MetricSpec("Reference recall — responsibilities", "no target", _recall_responsibilities, None),
    MetricSpec("Reference recall — team_or_function", "no target", _recall_team, None),
]


def was_run(score: RunScore | None) -> bool:
    """True only if this system actually scored cases in this run.

    score_run() returns a RunScore for a system whose run folder is empty, with every
    ratio at 0 / 0. Rendered as a result that reads as 0.0%, and "0 critical hallucinations
    out of 0 fields" then satisfies the 0% target and earns a ✅ — a system that never ran
    appearing to beat one that did. A system with no scored cases is reported as "—".
    """
    return score is not None and bool(score.scored_cases)


def tier_table(scores: dict[str, RunScore]) -> str:
    lines = ["| Metric | Target | pipeline | baseline |", "|---|---|---|---|"]
    for spec in METRIC_SPECS:
        cells = [spec.label, spec.target_text]
        for system in SYSTEMS:
            score = scores.get(system)
            if not was_run(score):
                cells.append("—")
                continue
            ratio = spec.get_ratio(score)
            if spec.passes is None:
                cells.append(str(ratio))
            else:
                cells.append(f"{ratio} {'✅' if spec.passes(ratio) else '❌'}")
        lines.append("| " + " | ".join(cells) + " |")
    missed_cells = ["Important missed", "no target"]
    for system in SYSTEMS:
        score = scores.get(system)
        missed_cells.append(str(score.metrics.important_missed) if was_run(score) else "—")
    lines.append("| " + " | ".join(missed_cells) + " |")
    return "\n".join(lines)


def _header(run_id: str, meta: dict[str, Any], scores: dict[str, RunScore]) -> list[str]:
    lines = [f"# Eval run {run_id}", ""]
    total_pending = sum(score.metrics.pending for score in scores.values())
    if total_pending > 0:
        banner = f"**PROVISIONAL — {total_pending} critical disagreements not yet adjudicated**"
        lines.append(banner)
        lines.append("")
    lines.append(f"- Model: {meta['model']}")
    # Only printed when the run recorded them, so reports written before these keys
    # existed re-render byte for byte.
    if meta.get("commit"):
        lines.append(f"- Code commit: {meta['commit']}")
    if meta.get("derived_from"):
        lines.append(
            f"- Derived from run {meta['derived_from']} by re-running verification in code"
            f" ({meta.get('api_calls', 0)} API calls)"
        )
    versions = meta["prompt_versions"]
    lines.append(
        f"- Prompt versions: pipeline={versions['pipeline']}, baseline={versions['baseline']}"
    )
    lines.append("- Temperature: not set for either system (API default). One run per system.")
    lines.append(f"- Cases in this run: {len(meta['cases'])}")
    for system in SYSTEMS:
        score = scores.get(system)
        if not was_run(score):
            continue
        critical_scored = sum(
            1 for r in score.results if r.tier == "critical" and r.outcome != "excluded"
        )
        important_scored = sum(
            1 for r in score.results if r.tier == "important" and r.outcome != "excluded"
        )
        excluded = sum(1 for r in score.results if r.outcome == "excluded")
        failures = len(meta["failures"][system])
        tokens = meta["tokens"][system]
        seconds = list(meta["seconds"][system].values())
        avg_seconds = mean(seconds) if seconds else 0.0
        lines.append(
            f"- {system}: {len(score.scored_cases)} cases scored, {critical_scored} critical "
            f"fields, {important_scored} important fields, {excluded} excluded (ambiguous), "
            f"{failures} failed extractions, tokens in {tokens['input']} / out {tokens['output']}, "
            f"avg {avg_seconds:.1f}s/JD"
        )
    if was_run(scores.get("pipeline")):
        violations = sum(meta["violations"].values())
        lines.append(f"- extraction_violations caught by the verbatim check: {violations}")
    return lines


def _failure_rows(score: RunScore) -> list[str]:
    rows = [r for r in score.results if r.outcome not in ("correct", "correct_absent", "excluded")]
    if not rows:
        return ["No disagreements."]
    lines = [
        "| Case | Tier | Field | Outcome | Verdict | Expected | Actual |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        expected = f"{r.label_value or 'Not stated'} ({r.label_evidence or '—'})"
        actual = f"{r.system_value or 'Not stated'} ({r.system_evidence or '—'})"
        lines.append(
            f"| {r.case_id} | {r.tier} | {r.field} | {r.outcome} | {r.verdict or '—'} "
            f"| {expected} | {actual} |"
        )
    return lines


def write_report(run_id: str, meta: dict[str, Any], scores: dict[str, RunScore]) -> Path:
    """Write (or overwrite) docs/eval/runs/<run_id>.md and return its path."""
    parts = [*_header(run_id, meta, scores), "", "## Tier table", "", tier_table(scores), ""]
    for system in SYSTEMS:
        score = scores.get(system)
        if not was_run(score):
            continue
        parts.append(f"## {system} failures")
        parts.append("")
        parts.extend(_failure_rows(score))
        parts.append("")
    path = DOCS_RUNS_DIR / f"{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path
