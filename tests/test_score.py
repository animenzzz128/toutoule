"""Scoring arithmetic and evidence verification. No network: every test uses FakeClient."""

import json

import pytest
from fakes import FakeClient

from toutoule import config, extract, schemas, score

POSTING = "We need someone to run pricing experiments and own a roadmap. SQL required."
RESUME = "Ran 14 pricing tests at a delivery app. Owned the merchant roadmap. Wrote SQL daily."

GOOD_PAIRS = [
    {"requirement": "SQL required", "experience": "Wrote SQL daily"},
    {"requirement": "run pricing experiments", "experience": "Ran 14 pricing tests"},
    {"requirement": "own a roadmap", "experience": "Owned the merchant roadmap"},
]


def dimensions(domain: int = 8, skills: int = 6, seniority: int = 7) -> schemas.Dimensions:
    return schemas.Dimensions(
        domain_fit=schemas.DimensionScore(score=domain, reason="r"),
        skills_overlap=schemas.DimensionScore(score=skills, reason="r"),
        seniority_fit=schemas.DimensionScore(score=seniority, reason="r"),
    )


def answer(pairs: list[dict[str, str]] | None = None, **scores: int) -> str:
    """One model reply as JSON text."""
    dims = dimensions(**scores)
    return json.dumps(
        {
            "dimensions": dims.model_dump(),
            "evidence_pairs": pairs if pairs is not None else GOOD_PAIRS,
            "gaps": ["no Mandarin", "no direct reports"],
        }
    )


# --- combine ------------------------------------------------------------------------------


def test_combine_matches_the_formula_in_d010() -> None:
    # 10 * (40*8 + 35*6 + 25*7) / 100 = 10 * 705 / 100 = 70.5 -> 70
    assert score.combine(dimensions(8, 6, 7), config.SCORE_WEIGHTS) == 70


def test_combine_spans_the_whole_range() -> None:
    assert score.combine(dimensions(0, 0, 0), config.SCORE_WEIGHTS) == 0
    assert score.combine(dimensions(10, 10, 10), config.SCORE_WEIGHTS) == 100


def test_combine_reads_the_weights_it_is_given_not_a_hard_coded_set() -> None:
    """The same dimensions under different weights must give a different total."""
    dims = dimensions(10, 0, 0)
    assert score.combine(dims, {"domain_fit": 40, "skills_overlap": 35, "seniority_fit": 25}) == 40
    assert score.combine(dims, {"domain_fit": 80, "skills_overlap": 10, "seniority_fit": 10}) == 80


def test_combine_does_not_require_weights_to_sum_to_100() -> None:
    """Dividing by the actual sum is what keeps a weight change from rescaling everything."""
    doubled = {name: w * 2 for name, w in config.SCORE_WEIGHTS.items()}
    assert score.combine(dimensions(8, 6, 7), doubled) == score.combine(
        dimensions(8, 6, 7), config.SCORE_WEIGHTS
    )


def test_combine_uses_pythons_round_so_halves_go_to_even() -> None:
    """Documents the rounding, rather than leaving it to be discovered during calibration.

    round() in Python rounds a .5 to the nearest even number, so 70.5 becomes 70, not 71.
    """
    assert score.combine(dimensions(8, 6, 7), config.SCORE_WEIGHTS) == 70  # 70.5


# --- verify_pairs -------------------------------------------------------------------------


def pair(requirement: str, experience: str) -> schemas.PairDraft:
    return schemas.PairDraft(requirement=requirement, experience=experience)


def test_an_honest_pair_is_verified() -> None:
    pairs = score.verify_pairs([pair("SQL required", "Wrote SQL daily")], POSTING, RESUME)
    assert [p.verified for p in pairs] == [True]


def test_a_fabricated_posting_quote_is_marked_unverified() -> None:
    quoted = "Mandarin fluency required"  # nowhere in POSTING
    pairs = score.verify_pairs([pair(quoted, "Wrote SQL daily")], POSTING, RESUME)
    assert [p.verified for p in pairs] == [False]
    assert pairs[0].requirement == quoted  # kept in the record, not deleted


def test_a_fabricated_resume_quote_is_marked_unverified() -> None:
    quoted = "Managed a team of nine"  # nowhere in RESUME
    pairs = score.verify_pairs([pair("SQL required", quoted)], POSTING, RESUME)
    assert [p.verified for p in pairs] == [False]
    assert pairs[0].experience == quoted


def test_the_two_sides_are_checked_against_their_own_sources() -> None:
    """A resume quote must not pass by appearing in the posting, or the check means nothing."""
    pairs = score.verify_pairs([pair("SQL required", "SQL required")], POSTING, RESUME)
    assert [p.verified for p in pairs] == [False]


def test_verification_reuses_the_extraction_normalization() -> None:
    """Curly quotes and collapsed whitespace are formatting, not fabrication (ADR-003)."""
    posting = "The role needs a “data-driven” operator."
    resume = "I am a\n  data-driven   operator."
    pairs = score.verify_pairs(
        [pair('"data-driven" operator', "data-driven operator")], posting, resume
    )
    assert [p.verified for p in pairs] == [True]
    assert extract.normalize_text("“x”") == '"x"'  # the shared rule, not a private copy


# --- score_version -------------------------------------------------------------------------


def test_failed_pairs_are_counted_into_the_result() -> None:
    bad = [
        {"requirement": "Mandarin fluency required", "experience": "Wrote SQL daily"},
        {"requirement": "run pricing experiments", "experience": "Managed a team of nine"},
        {"requirement": "own a roadmap", "experience": "Owned the merchant roadmap"},
    ]
    got = score.score_version(POSTING, RESUME, "ai_product", FakeClient(answer(bad)), model="m")
    assert got.result.unverified_pairs == 2
    assert [p.verified for p in got.result.evidence_pairs] == [False, False, True]
    assert len(got.result.evidence_pairs) == 3  # still exactly 3: nothing was dropped


def test_the_total_is_computed_by_code_even_when_the_model_sends_one() -> None:
    """A reply carrying a total fails validation, so the retry is what the model sees."""
    with_total = json.loads(answer())
    with_total["score"] = 99
    client = FakeClient(json.dumps(with_total), answer())
    got = score.score_version(POSTING, RESUME, "ai_product", client, model="m")
    assert got.result.score == 70  # from combine(), not the 99 the model asked for
    assert len(client.requests) == 2


def test_tokens_are_summed_across_the_retry() -> None:
    client = FakeClient("not json at all", answer())
    got = score.score_version(POSTING, RESUME, "ai_product", client, model="m")
    assert (got.input_tokens, got.output_tokens) == (2000, 600)  # two calls at 1000/300


def test_two_bad_answers_raise_scoring_failed() -> None:
    client = FakeClient("not json", "still not json")
    with pytest.raises(score.ScoringFailed, match="failed validation twice"):
        score.score_version(POSTING, RESUME, "ai_product", client, model="m")


def test_recommended_version_is_none_until_all_versions_are_scored() -> None:
    got = score.score_version(POSTING, RESUME, "ai_product", FakeClient(answer()), model="m")
    assert got.result.recommended_version is None


# --- recommended version -------------------------------------------------------------------


def result(version: str, total: int) -> schemas.MatchResult:
    """A MatchResult with only the fields recommend() looks at made meaningful."""
    return schemas.MatchResult(
        resume_version=version,  # type: ignore[arg-type]
        score=total,
        dimensions=dimensions(),
        evidence_pairs=[
            schemas.EvidencePair(requirement="a", experience="b", verified=True) for _ in range(3)
        ],
        gaps=["g1", "g2"],
        unverified_pairs=0,
        prompt_version="score_v1",
        model="m",
    )


def test_the_highest_total_wins() -> None:
    results = [result("ai_product", 60), result("strategy_bizops", 80), result("consulting", 70)]
    assert score.recommend(results) == "strategy_bizops"


def test_a_three_way_tie_goes_to_the_first_version_in_config_order() -> None:
    results = [result("consulting", 75), result("strategy_bizops", 75), result("ai_product", 75)]
    assert score.recommend(results) == "ai_product"


def test_a_tie_below_ai_product_goes_to_strategy_bizops() -> None:
    results = [result("ai_product", 60), result("strategy_bizops", 75), result("consulting", 75)]
    assert score.recommend(results) == "strategy_bizops"


def test_a_tie_between_ai_product_and_consulting_goes_to_ai_product() -> None:
    results = [result("consulting", 75), result("ai_product", 75), result("strategy_bizops", 60)]
    assert score.recommend(results) == "ai_product"


def test_the_tie_break_does_not_depend_on_the_order_the_versions_were_scored() -> None:
    """Otherwise the recommendation would depend on which call happened to finish first."""
    tied = [result("ai_product", 75), result("strategy_bizops", 75), result("consulting", 75)]
    for rotation in range(3):
        rotated = tied[rotation:] + tied[:rotation]
        assert score.recommend(rotated) == "ai_product"


def test_the_tie_break_order_is_the_one_config_declares() -> None:
    """Pins the behaviour to config, not to a list repeated inside score.py."""
    assert config.RESUME_VERSIONS[0] == "ai_product"
    results = [result(version, 75) for version in config.RESUME_VERSIONS]
    assert score.recommend(results) == config.RESUME_VERSIONS[0]


# --- score_job -----------------------------------------------------------------------------


@pytest.fixture
def sample_profiles(tmp_path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Three throwaway sample resumes, so score_job does not read the owner's real ones."""
    for version in config.RESUME_VERSIONS:
        (tmp_path / f"sample_{version}.md").write_text(
            f"Wrote SQL daily. Ran 14 pricing tests. Owned the merchant roadmap. ({version})",
            encoding="utf-8",
        )
    monkeypatch.setattr(config, "SAMPLE_PROFILE_DIR", tmp_path)
    return tmp_path


def test_score_job_scores_every_version_once(sample_profiles) -> None:  # type: ignore[no-untyped-def]
    client = FakeClient(answer(), answer(), answer())
    scored = score.score_job(POSTING, client, sample=True, model="m")
    assert len(scored) == 3
    assert len(client.requests) == 3
    assert [item.result.resume_version for item in scored] == list(config.RESUME_VERSIONS)


def test_score_job_puts_the_same_recommendation_on_every_result(sample_profiles) -> None:  # type: ignore[no-untyped-def]
    client = FakeClient(
        answer(domain=5, skills=5, seniority=5),  # ai_product     -> 50
        answer(domain=9, skills=9, seniority=9),  # strategy_bizops -> 90
        answer(domain=1, skills=1, seniority=1),  # consulting      -> 10
    )
    scored = score.score_job(POSTING, client, sample=True, model="m")
    assert [item.result.score for item in scored] == [50, 90, 10]
    assert {item.result.recommended_version for item in scored} == {"strategy_bizops"}


def test_score_job_reads_the_sample_resumes_when_asked(sample_profiles) -> None:  # type: ignore[no-untyped-def]
    client = FakeClient(answer(), answer(), answer())
    score.score_job(POSTING, client, sample=True, model="m")
    sent = [request["messages"][0]["content"] for request in client.requests]
    assert all("<resume>" in content for content in sent)
    assert sum("(consulting)" in content for content in sent) == 1


def test_a_missing_resume_names_the_path_it_tried(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Points at an empty directory on purpose: this must fail for the right reason once
    the real sample_*.md files exist, not pass because they happen to be missing."""
    monkeypatch.setattr(config, "SAMPLE_PROFILE_DIR", tmp_path)
    with pytest.raises(score.ResumeNotFound, match="sample_ai_product.md"):
        score.load_resume("ai_product", sample=True)
