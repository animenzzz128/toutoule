"""The scoring contract (tech spec §5, D-010): what a model may return, and what it may not.

Every test here is pure validation. No client, no network, no files.
"""

import json

import pytest
from pydantic import ValidationError

from toutoule import config, schemas


def draft_json(**overrides: object) -> str:
    """A valid ScoreDraft as JSON text, with any part swapped out by keyword."""
    payload: dict[str, object] = {
        "dimensions": {
            "domain_fit": {"score": 8, "reason": "same industry"},
            "skills_overlap": {"score": 6, "reason": "most tools match"},
            "seniority_fit": {"score": 7, "reason": "right level"},
        },
        "evidence_pairs": [
            {"requirement": "SQL required", "experience": "wrote SQL daily"},
            {"requirement": "A/B testing", "experience": "ran 12 experiments"},
            {"requirement": "stakeholder work", "experience": "led weekly reviews"},
        ],
        "gaps": ["no Mandarin", "no people management"],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_a_valid_draft_parses() -> None:
    draft = schemas.ScoreDraft.model_validate_json(draft_json())
    assert draft.dimensions.domain_fit.score == 8
    assert len(draft.evidence_pairs) == 3
    assert len(draft.gaps) == 2


def test_two_evidence_pairs_is_rejected() -> None:
    pairs = [
        {"requirement": "SQL required", "experience": "wrote SQL daily"},
        {"requirement": "A/B testing", "experience": "ran 12 experiments"},
    ]
    with pytest.raises(ValidationError, match="at least 3"):
        schemas.ScoreDraft.model_validate_json(draft_json(evidence_pairs=pairs))


def test_four_evidence_pairs_is_rejected() -> None:
    pair = {"requirement": "SQL required", "experience": "wrote SQL daily"}
    with pytest.raises(ValidationError, match="at most 3"):
        schemas.ScoreDraft.model_validate_json(draft_json(evidence_pairs=[pair] * 4))


def test_three_gaps_is_rejected() -> None:
    gaps = ["no Mandarin", "no people management", "no finance"]
    with pytest.raises(ValidationError, match="at most 2"):
        schemas.ScoreDraft.model_validate_json(draft_json(gaps=gaps))


def test_a_dimension_score_of_eleven_is_rejected() -> None:
    dimensions = {
        "domain_fit": {"score": 11, "reason": "better than perfect"},
        "skills_overlap": {"score": 6, "reason": "most tools match"},
        "seniority_fit": {"score": 7, "reason": "right level"},
    }
    with pytest.raises(ValidationError, match="less than or equal to 10"):
        schemas.ScoreDraft.model_validate_json(draft_json(dimensions=dimensions))


def test_a_negative_dimension_score_is_rejected() -> None:
    dimensions = {
        "domain_fit": {"score": -1, "reason": "worse than nothing"},
        "skills_overlap": {"score": 6, "reason": "most tools match"},
        "seniority_fit": {"score": 7, "reason": "right level"},
    }
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        schemas.ScoreDraft.model_validate_json(draft_json(dimensions=dimensions))


def test_a_draft_containing_a_total_is_rejected_not_ignored() -> None:
    """D-010 §1: the model never outputs the total. A model that writes one anyway fails.

    Rejected, not ignored: _StrictModel sets extra="forbid", so the key raises instead of
    being dropped. extract.py's retry loop then shows the model this very error.
    """
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        schemas.ScoreDraft.model_validate_json(draft_json(score=97))


def test_a_draft_cannot_preset_verified() -> None:
    pairs = [
        {"requirement": "SQL required", "experience": "wrote SQL daily", "verified": True},
        {"requirement": "A/B testing", "experience": "ran 12 experiments"},
        {"requirement": "stakeholder work", "experience": "led weekly reviews"},
    ]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        schemas.ScoreDraft.model_validate_json(draft_json(evidence_pairs=pairs))


def test_weights_come_from_config_and_cover_every_dimension() -> None:
    """A dimension without a weight, or a weight without a dimension, is a silent bug."""
    assert set(config.SCORE_WEIGHTS) == set(schemas.Dimensions.model_fields)
    assert config.SCORE_WEIGHTS == {"domain_fit": 40, "skills_overlap": 35, "seniority_fit": 25}
    assert config.RESUME_VERSIONS == ("ai_product", "strategy_bizops", "consulting")
