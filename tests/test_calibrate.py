"""Calibration (Task 1.9 Part B). No network and no real resumes: every test uses a fake
client and a temporary profile directory whose text is deliberately unlike anything real.
"""

import json
from pathlib import Path

import pytest
from fakes import FakeClient

from toutoule import calibrate, calibratereport, config

# Strings that exist only in the fixture resume. If one reaches the public report, the
# report is leaking resume text.
RESUME_MARKERS = ["ZORBLAX CORPORATION", "quixotic underwater basketweaving", "17 kiloflops"]
RESUME_TEXT = (
    "DANA FIXTURE\nEDUCATION\nPROFESSIONAL EXPERIENCE\n"
    "ZORBLAX CORPORATION\n"
    "- Led quixotic underwater basketweaving across 17 kiloflops of throughput.\n"
)


def answer(domain: int = 8, skills: int = 6, seniority: int = 7) -> str:
    """A reply whose evidence quotes real spans of the fixture resume, so pairs verify."""
    return json.dumps(
        {
            "dimensions": {
                "domain_fit": {"score": domain, "reason": "ZORBLAX CORPORATION is the same field"},
                "skills_overlap": {"score": skills, "reason": "17 kiloflops of throughput"},
                "seniority_fit": {"score": seniority, "reason": "right level"},
            },
            "evidence_pairs": [
                {"requirement": "the", "experience": "ZORBLAX CORPORATION"},
                {"requirement": "a", "experience": "quixotic underwater basketweaving"},
                {"requirement": "to", "experience": "nowhere in the resume"},
            ],
            "gaps": ["no quixotic certification", "no kiloflop experience"],
        }
    )


def payload(case_id: str, human: int, system: int) -> dict:
    """A minimal stored case, with the recommended version carrying the system score."""
    result = {
        "resume_version": "ai_product",
        "score": system,
        "dimensions": {name: {"score": 5, "reason": "r"} for name in config.SCORE_WEIGHTS},
        "evidence_pairs": [{"requirement": "a", "experience": "b", "verified": True}] * 3,
        "gaps": ["g1", "g2"],
        "unverified_pairs": 0,
        "recommended_version": "ai_product",
        "prompt_version": "score_v1",
        "model": "m",
    }
    return {
        "case_id": case_id,
        "segment": "cn_campus",
        "human_score": human,
        "reason": "",
        "recommended_version": "ai_product",
        "system_score": system,
        "versions": {
            "ai_product": {
                "result": result,
                "raw_responses": [],
                "input_tokens": 0,
                "output_tokens": 0,
            }
        },
    }


@pytest.fixture
def run_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Private run dir, public report dir and sample resumes, all in a temp folder."""
    profile = tmp_path / "profile"
    profile.mkdir()
    for version in config.RESUME_VERSIONS:
        (profile / f"sample_{version}.md").write_text(
            RESUME_TEXT + f"\nversion marker: {version}\n", encoding="utf-8"
        )
    monkeypatch.setattr(config, "SAMPLE_PROFILE_DIR", profile)
    monkeypatch.setattr(calibrate, "SCORE_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(calibrate, "PUBLIC_REPORT_DIR", tmp_path / "public")
    return tmp_path


def do_run(run_id: str, cases: int = 4) -> tuple[dict, FakeClient]:
    rows = calibrate.load_calibration_cases(limit=cases)
    client = FakeClient(*[answer()] * (len(rows) * 3))
    meta = calibrate.run_calibration(run_id, rows, client, "fake-model", sample=True)
    return meta, client


def report_for(run_id: str, meta: dict) -> tuple[str, calibrate.CalibrationMetrics]:
    payloads = calibrate.load_payloads(calibrate.run_dir(run_id), meta)
    metrics = calibrate.compute_metrics(list(payloads.values()))
    public, _ = calibratereport.write_reports(run_id, meta, metrics, payloads)
    return public.read_text(encoding="utf-8"), metrics


# --- agreement math -------------------------------------------------------------------------


def outcome(human: int, system: int) -> calibrate.CaseOutcome:
    return calibrate.CaseOutcome(
        case_id="x",
        segment="s",
        human=human,
        system=system,
        recommended="ai_product",
        dimensions={"domain_fit": 1, "skills_overlap": 1, "seniority_fit": 1},
        version_scores={"ai_product": system},
    )


def test_a_gap_of_exactly_ten_counts_as_agreement() -> None:
    """The tolerance is inclusive. 10 agrees, 11 does not, in both directions."""
    assert outcome(70, 80).agrees
    assert outcome(80, 70).agrees
    assert not outcome(70, 81).agrees
    assert not outcome(81, 70).agrees


def test_mean_signed_error_is_positive_when_the_system_rates_higher() -> None:
    metrics = calibrate.compute_metrics(
        [payload("a", human=50, system=70), payload("b", human=60, system=70)]
    )
    assert metrics.mean_signed_error == pytest.approx(15.0)
    assert metrics.mean_absolute_error == pytest.approx(15.0)


def test_mean_signed_error_is_negative_when_the_system_rates_lower() -> None:
    """Signed error has to keep its sign, or it cannot say which way the system leans."""
    metrics = calibrate.compute_metrics(
        [payload("a", human=90, system=70), payload("b", human=80, system=70)]
    )
    assert metrics.mean_signed_error == pytest.approx(-15.0)
    assert metrics.mean_absolute_error == pytest.approx(15.0)


def test_the_floor_is_computed_from_the_data() -> None:
    """Median of [20, 70, 70, 95] is 70; within 10 of 70 are the two 70s."""
    metrics = calibrate.compute_metrics(
        [
            payload("a", human=20, system=20),
            payload("b", human=70, system=70),
            payload("c", human=70, system=70),
            payload("d", human=95, system=95),
        ]
    )
    assert metrics.floor_guess == 70
    assert (metrics.floor.within, metrics.floor.total) == (2, 4)
    assert metrics.agreement.within == 4  # the system itself matched every one


# --- run handling ---------------------------------------------------------------------------


def test_a_case_with_no_raw_posting_fails_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(calibrate, "RAW_DIR", tmp_path / "empty")
    with pytest.raises(FileNotFoundError, match="cnc-01"):
        calibrate.load_calibration_cases(limit=1)


def test_rescore_makes_no_client_calls_and_reproduces_the_report(run_env: Path) -> None:
    """The fake is given exactly enough answers; a further call would exhaust it."""
    meta, client = do_run("r1")
    first, _ = report_for("r1", meta)
    assert client.answers == []  # every answer consumed by the run itself

    run_id, meta2 = calibrate.rescore_run("r1")

    assert run_id == "r1"
    assert meta2["api_calls"] == meta["api_calls"]
    again, _ = report_for("r1", meta2)
    assert again == first


def test_weights_create_a_derived_run_and_leave_the_original_alone(run_env: Path) -> None:
    meta, _ = do_run("r2")
    case_file = calibrate.run_dir("r2") / f"{meta['cases'][0]}.json"
    before = case_file.read_text(encoding="utf-8")

    derived_id, derived_meta = calibrate.rescore_run(
        "r2", {"domain_fit": 80, "skills_overlap": 10, "seniority_fit": 10}
    )

    assert derived_id == "r2-w2"
    assert derived_meta["derived_from"] == "r2"
    assert derived_meta["api_calls"] == 0
    assert case_file.read_text(encoding="utf-8") == before  # base run untouched
    _, base = report_for("r2", calibrate.load_meta(calibrate.run_dir("r2")))
    _, reweighted = report_for(derived_id, derived_meta)
    assert base.outcomes[0].system != reweighted.outcomes[0].system


def test_a_second_adjustment_is_refused(run_env: Path) -> None:
    """D-010 section 8 allows one adjustment per base run, of either kind."""
    do_run("r3")
    calibrate.rescore_run("r3", {"domain_fit": 80, "skills_overlap": 10, "seniority_fit": 10})

    with pytest.raises(calibrate.AdjustmentSpent, match="D-010"):
        calibrate.rescore_run("r3", {"domain_fit": 10, "skills_overlap": 10, "seniority_fit": 80})


def test_a_recorded_prompt_adjustment_also_spends_the_run(run_env: Path) -> None:
    do_run("r4")
    calibrate.record_adjustment("r4", "prompt", "r4-score_v2")

    with pytest.raises(calibrate.AdjustmentSpent, match="D-010"):
        calibrate.rescore_run("r4", {"domain_fit": 80, "skills_overlap": 10, "seniority_fit": 10})


# --- the public report leaks nothing ---------------------------------------------------------


def test_the_public_report_contains_no_resume_text(run_env: Path) -> None:
    meta, _ = do_run("r5")

    text, _ = report_for("r5", meta)

    for marker in RESUME_MARKERS:
        assert marker not in text, marker
    assert "no quixotic certification" not in text  # gaps stay private
    assert "nowhere in the resume" not in text  # evidence quotes stay private


def test_the_private_report_does_contain_it(run_env: Path) -> None:
    """The private report is where the detail lives, which is why it stays in data/private/."""
    meta, _ = do_run("r6")
    payloads = calibrate.load_payloads(calibrate.run_dir("r6"), meta)
    metrics = calibrate.compute_metrics(list(payloads.values()))

    _, private_path = calibratereport.write_reports("r6", meta, metrics, payloads)

    text = private_path.read_text(encoding="utf-8")
    assert "ZORBLAX CORPORATION" in text
    assert "no quixotic certification" in text
    assert "UNVERIFIED" in text
    assert private_path.parent == calibrate.run_dir("r6")
