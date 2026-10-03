"""Regression locks for the run reports in docs/eval/runs/.

Those reports are the project's evidence. Re-rendering one must reproduce it exactly, and
a system that was never run must never be rendered as a result — least of all a passing one.
No API calls: score_run() reads the committed run folders, labels and equivalences.
"""

from pathlib import Path

import pytest

from toutoule import evalreport, evalrun

REPO_ROOT = Path(__file__).parents[1]
RUN_IDS = sorted(p.name for p in (REPO_ROOT / "data" / "eval" / "runs").iterdir() if p.is_dir())


def rescore(run_id: str) -> dict[str, evalrun.RunScore]:
    """Score both systems of a committed run, exactly as `cli eval --rescore` does."""
    return {system: evalrun.score_run(run_id, system) for system in evalreport.SYSTEMS}


@pytest.mark.parametrize("run_id", RUN_IDS)
def test_rescoring_a_committed_run_reproduces_its_report_byte_for_byte(
    run_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = REPO_ROOT / "docs" / "eval" / "runs" / f"{run_id}.md"
    if not committed.exists():
        pytest.skip(f"no committed report for {run_id}")
    meta = evalrun.load_meta(evalrun.run_dir(run_id))
    monkeypatch.setattr(evalreport, "DOCS_RUNS_DIR", tmp_path)

    written = evalreport.write_report(run_id, meta, rescore(run_id))

    assert written.read_text(encoding="utf-8") == committed.read_text(encoding="utf-8")


@pytest.mark.parametrize("run_id", RUN_IDS)
def test_a_system_with_no_scored_cases_is_reported_as_not_run(run_id: str) -> None:
    """0 / 0 is not a result. A system that scored nothing gets "—" in every cell."""
    scores = rescore(run_id)
    not_run = [system for system, score in scores.items() if not score.scored_cases]
    if not not_run:
        pytest.skip(f"both systems ran in {run_id}")
    table = evalreport.tier_table(scores)
    for system in not_run:
        column = list(evalreport.SYSTEMS).index(system) + 3  # label, target, then the systems
        for line in table.splitlines()[2:]:
            cell = line.split("|")[column].strip()
            assert cell == "—", f"{system} scored no cases but renders {cell!r}"


@pytest.mark.parametrize("run_id", RUN_IDS)
def test_a_system_with_no_scored_cases_never_gets_a_tick(run_id: str) -> None:
    """The failure that prompted this: a baseline with 0 cases passing the 0% target."""
    scores = rescore(run_id)
    for system, score in scores.items():
        if score.scored_cases:
            continue
        column = list(evalreport.SYSTEMS).index(system) + 3
        cells = [line.split("|")[column] for line in evalreport.tier_table(scores).splitlines()[2:]]
        assert not any("✅" in cell or "❌" in cell for cell in cells), system


@pytest.mark.parametrize("run_id", RUN_IDS)
def test_a_system_with_no_scored_cases_gets_no_summary_or_failures_section(
    run_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scores = rescore(run_id)
    meta = evalrun.load_meta(evalrun.run_dir(run_id))
    monkeypatch.setattr(evalreport, "DOCS_RUNS_DIR", tmp_path)

    text = evalreport.write_report(run_id, meta, scores).read_text(encoding="utf-8")

    for system, score in scores.items():
        if score.scored_cases:
            continue
        assert f"- {system}: 0 cases scored" not in text
        assert f"## {system} failures" not in text
