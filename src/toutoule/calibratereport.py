"""The two reports for one calibration run (Task 1.9 Part B item 3).

The public report goes to docs/eval/scoring/ and carries numbers only. The private one
goes in the run folder and carries everything, including quotes from the owner's real
resume — which is why it never leaves data/private/ (D-010 §9).

Pure formatting, no API calls, and no timestamp anywhere: a rescore of the same run must
reproduce its report byte for byte, the same property the Task 1.8 reports have.
"""

from pathlib import Path
from typing import Any

from toutoule import calibrate, config


def _header(run_id: str, meta: dict[str, Any]) -> list[str]:
    weights = ", ".join(f"{name} {value}" for name, value in meta["weights"].items())
    settings = ", ".join(f"{k} {v}" for k, v in meta["model_settings"].items())
    lines = [f"# Match-score calibration {run_id}", ""]
    if meta.get("derived_from"):
        lines += [
            f"Derived from run {meta['derived_from']} by recomputing the stored replies under "
            f"different weights ({meta['api_calls']} API calls).",
            "",
        ]
    lines += [
        f"- Model: {meta['model']}",
        f"- Prompt version: {meta['prompt_version']}",
        f"- Weights: {weights}",
        f"- Settings: {settings}",
    ]
    if meta.get("commit"):
        lines.append(f"- Code commit: {meta['commit']}")
    lines += [
        f"- API calls: {meta['api_calls']}",
        f"- Tokens: input {meta['tokens']['input']}, output {meta['tokens']['output']}",
    ]
    return lines


def public_report(run_id: str, meta: dict[str, Any], m: calibrate.CalibrationMetrics) -> str:
    """Agreement and per-case scores. No resume text, no evidence, no gaps, no reasons."""
    lines = _header(run_id, meta)
    lines += [
        "",
        "## Agreement with the owner's scores",
        "",
        "Human baseline: the 20 scores given by hand during Task 1.6, before any system",
        "scoring (D-010 §7). A posting's system score is its recommended version's score.",
        "",
        f"- Agreement within ±10: {m.agreement}",
        f"- Constant guess ({m.floor_guess}) within ±10: {m.floor.within} / {m.floor.total}",
        f"- Mean signed error (system − human): {m.mean_signed_error:+.1f}",
        f"- Mean absolute error: {m.mean_absolute_error:.1f}",
        f"- Evidence pairs verified (all versions): "
        f"{m.evidence_verified[0]} / {m.evidence_verified[1]}",
        "",
        "The constant guess is the rounded median of the human scores: what a system that",
        "reads nothing would achieve. The system is credited only with agreement above it.",
        "",
        "## By segment",
        "",
        "| Segment | Agreement | Mean signed error | Mean absolute error |",
        "|---|---|---|---|",
    ]
    for segment, agreement in m.by_segment.items():
        signed, absolute = m.segment_errors[segment]
        lines.append(
            f"| {segment} | {agreement.within} / {agreement.total} "
            f"| {signed:+.1f} | {absolute:.1f} |"
        )
    lines += [
        "",
        "Counts, not percentages: the smallest segment here has too few postings for a",
        "percentage to mean anything, and one posting would move it by a quarter.",
        "",
        "## Recommended version",
        "",
    ]
    for version in config.RESUME_VERSIONS:
        lines.append(f"- {version}: {m.recommended_counts.get(version, 0)}")
    lines += [
        "",
        "## Per case",
        "",
        "| Case | Human | System | Diff | Recommended | domain_fit | skills_overlap "
        "| seniority_fit |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for o in m.outcomes:
        lines.append(
            f"| {o.case_id} | {o.human} | {o.system} | {o.diff:+d} | {o.recommended} "
            f"| {o.dimensions['domain_fit']} | {o.dimensions['skills_overlap']} "
            f"| {o.dimensions['seniority_fit']} |"
        )
    return "\n".join(lines) + "\n"


def private_report(
    run_id: str, meta: dict[str, Any], m: calibrate.CalibrationMetrics, payloads: dict[str, Any]
) -> str:
    """Every posting, largest disagreement first, with everything that produced it."""
    lines = _header(run_id, meta)
    lines += [
        "",
        "**Private.** Quotes the owner's real resumes. Never leaves data/private/.",
        "",
        f"Agreement within ±10: {m.agreement}. Sorted by |system − human|, largest first.",
        "",
    ]
    for outcome in sorted(m.outcomes, key=lambda o: abs(o.diff), reverse=True):
        payload = payloads[outcome.case_id]
        flag = "" if outcome.agrees else "  ← outside ±10"
        lines += [
            f"## {outcome.case_id} · human {outcome.human} · system {outcome.system} "
            f"· diff {outcome.diff:+d}{flag}",
            "",
            f"- Segment: {outcome.segment}",
            f"- Owner's reason: {payload['reason'] or '(none given)'}",
            f"- Recommended version: {outcome.recommended}",
            "- Score by version: "
            + ", ".join(f"{v} {s}" for v, s in outcome.version_scores.items()),
            "",
        ]
        for version, stored in payload["versions"].items():
            result = stored["result"]
            lines.append(f"### {version} — {result['score']}/100")
            for name in config.SCORE_WEIGHTS:
                dimension = result["dimensions"][name]
                lines.append(f"- {name} {dimension['score']}/10 — {dimension['reason']}")
            for pair in result["evidence_pairs"]:
                mark = "verified" if pair["verified"] else "UNVERIFIED"
                lines.append(
                    f"- [{mark}] posting: {pair['requirement']!r} ← resume: {pair['experience']!r}"
                )
            for gap in result["gaps"]:
                lines.append(f"- gap: {gap}")
            lines.append("")
    return "\n".join(lines) + "\n"


def write_reports(
    run_id: str, meta: dict[str, Any], m: calibrate.CalibrationMetrics, payloads: dict[str, Any]
) -> tuple[Path, Path]:
    """Write both reports and return (public path, private path)."""
    public_path = calibrate.PUBLIC_REPORT_DIR / f"{run_id}.md"
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(public_report(run_id, meta, m), encoding="utf-8")
    private_path = calibrate.run_dir(run_id) / "report_full.md"
    private_path.write_text(private_report(run_id, meta, m, payloads), encoding="utf-8")
    return public_path, private_path
