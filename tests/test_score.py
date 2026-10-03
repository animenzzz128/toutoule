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
