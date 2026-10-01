"""Tests for evalreport.py. Pure formatting: no API, no database."""

from toutoule import evalreport, evalrun, evalscore


def _score(system: str, pending: int = 0, hallucinations: int = 0) -> evalrun.RunScore:
    results = [
        evalscore.FieldResult(
            case_id="cnp-01",
            tier="critical",
            field="deadline",
            outcome="correct_absent",
            label_value=None,
            label_evidence=None,
            system_value=None,
            system_evidence=None,
        )
    ]
    metrics = evalscore.Metrics(
        critical_hallucination=evalscore.Ratio(hallucinations, 5),
        critical_accuracy=evalscore.Ratio(4, 5),
        critical_false_negative=evalscore.Ratio(0, 3),
        important_accuracy=evalscore.Ratio(4, 5),
        important_missed=1,
        pending=pending,
        provisional=pending > 0,
    )
    return evalrun.RunScore(
        system=system,
        results=results,
        metrics=metrics,
        recall=evalscore.ReferenceRecall(
            skills=evalscore.Ratio(5, 6),
            responsibilities=evalscore.Ratio(2, 3),
            team_or_function=evalscore.Ratio(1, 1),
            total=evalscore.Ratio(8, 10),
        ),
        scored_cases=["cnp-01"],
    )


def _meta() -> dict:
    return {
        "model": "claude-test-model",
        "prompt_versions": {"pipeline": "extract_v1", "baseline": "baseline_plain_v1"},
        "cases": ["cnp-01"],
        "tokens": {
            "pipeline": {"input": 100, "output": 20},
            "baseline": {"input": 80, "output": 15},
        },
        "seconds": {"pipeline": {"cnp-01": 2.0}, "baseline": {"cnp-01": 1.0}},
        "violations": {"cnp-01": 1},
        "failures": {"pipeline": [], "baseline": []},
    }


def test_tier_table_marks_targets_met_and_missed():
    scores = {"pipeline": _score("pipeline", hallucinations=0), "baseline": _score("baseline")}
    table = evalreport.tier_table(scores)
    assert "0 / 5 (0.0%) ✅" in table  # hallucination target met
    assert "4 / 5 (80.0%) ❌" in table  # accuracy target (>=95%) missed


def test_write_report_includes_provisional_banner_when_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(evalreport, "DOCS_RUNS_DIR", tmp_path)
    scores = {"pipeline": _score("pipeline", pending=2)}

    path = evalreport.write_report("run1", _meta(), scores)

    text = path.read_text(encoding="utf-8")
    assert "PROVISIONAL — 2 critical disagreements not yet adjudicated" in text
    assert "pipeline" in text


def test_write_report_no_banner_when_nothing_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(evalreport, "DOCS_RUNS_DIR", tmp_path)
    scores = {"pipeline": _score("pipeline", pending=0)}

    path = evalreport.write_report("run1", _meta(), scores)

    assert "PROVISIONAL" not in path.read_text(encoding="utf-8")


def test_header_reports_temperature_default_and_single_run():
    scores = {"pipeline": _score("pipeline")}
    header = "\n".join(evalreport._header("run1", _meta(), scores))
    assert "not set for either system (API default)" in header
    assert "One run per system" in header
