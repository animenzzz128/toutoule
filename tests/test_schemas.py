import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from toutoule.schemas import (
    SCHEMA_VERSION,
    ExtractedField,
    Extraction,
    ReferenceFields,
    VisaSponsorshipField,
    WorkModelField,
)

FIXTURE = Path(__file__).parent / "fixtures" / "extraction_valid.json"


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    """A fresh copy of the valid fixture, so a test can modify it without affecting others."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_stated_field_with_value_and_evidence_is_accepted() -> None:
    field = ExtractedField(value="2026-10-15", stated=True, evidence="Apply by Oct 15, 2026")
    assert field.stated is True


def test_not_stated_field_with_nothing_filled_in_is_accepted() -> None:
    field = ExtractedField(value=None, stated=False, evidence=None)
    assert field.value is None


# (b) Missing evidence.
@pytest.mark.parametrize("evidence", [None, "", "   "])
def test_stated_true_without_evidence_is_rejected(evidence: str | None) -> None:
    with pytest.raises(ValidationError, match="evidence must be a non-empty quote"):
        ExtractedField(value="2026-10-15", stated=True, evidence=evidence)


# (c) Inconsistent statedness.
@pytest.mark.parametrize(
    ("value", "evidence"),
    [("yes", None), (None, "We sponsor visas"), ("yes", "We sponsor visas")],
)
def test_stated_false_with_value_or_evidence_is_rejected(
    value: str | None, evidence: str | None
) -> None:
    with pytest.raises(ValidationError, match="value and evidence must both be null"):
        ExtractedField(value=value, stated=False, evidence=evidence)


# (d) Stated but no value, including blank strings.
@pytest.mark.parametrize("value", [None, "", "   "])
def test_stated_true_without_value_is_rejected(value: str | None) -> None:
    with pytest.raises(ValidationError, match="value must be a non-empty string"):
        ExtractedField(value=value, stated=True, evidence="Apply by Oct 15, 2026")


# (e) Controlled values, only when stated.
@pytest.mark.parametrize("value", ["yes", "no", "conditional"])
def test_visa_sponsorship_accepts_allowed_values(value: str) -> None:
    field = VisaSponsorshipField(value=value, stated=True, evidence="We sponsor H-1B visas")
    assert field.value == value


@pytest.mark.parametrize("value", ["maybe", "Yes", "sponsorship available"])
def test_visa_sponsorship_rejects_other_values(value: str) -> None:
    with pytest.raises(ValidationError):
        VisaSponsorshipField(value=value, stated=True, evidence="We sponsor H-1B visas")


def test_visa_sponsorship_not_stated_is_accepted() -> None:
    field = VisaSponsorshipField(value=None, stated=False, evidence=None)
    assert field.stated is False


def test_visa_sponsorship_still_enforces_statedness() -> None:
    with pytest.raises(ValidationError, match="evidence must be a non-empty quote"):
        VisaSponsorshipField(value="no", stated=True, evidence=None)


@pytest.mark.parametrize("value", ["onsite", "hybrid", "remote"])
def test_work_model_accepts_allowed_values(value: str) -> None:
    field = WorkModelField(value=value, stated=True, evidence="Hybrid, 3 days in office")
    assert field.value == value


@pytest.mark.parametrize("value", ["Remote", "wfh"])
def test_work_model_rejects_other_values(value: str) -> None:
    with pytest.raises(ValidationError):
        WorkModelField(value=value, stated=True, evidence="Hybrid, 3 days in office")


def test_work_model_not_stated_is_accepted() -> None:
    assert WorkModelField(value=None, stated=False, evidence=None).value is None


# (f) Unknown keys are rejected at every level.
def test_unknown_key_on_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExtractedField.model_validate(
            {"value": None, "stated": False, "evidence": None, "confidence": 0.9}
        )


def test_unknown_key_on_reference_fields_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReferenceFields.model_validate(
            {"skills": [], "responsibilities": [], "team_or_function": None, "salary": "1"}
        )


# (a) The valid fixture loads.
def test_valid_fixture_loads(valid_payload: dict[str, Any]) -> None:
    extraction = Extraction.model_validate(valid_payload)
    assert extraction.schema_version == SCHEMA_VERSION
    assert extraction.critical.deadline.evidence == "网申截止时间：2026年10月31日"
    assert extraction.critical.visa_sponsorship.stated is False
    assert extraction.important.work_model.value == "onsite"


def test_unknown_top_level_key_is_rejected(valid_payload: dict[str, Any]) -> None:
    valid_payload["salary"] = "30k"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Extraction.model_validate(valid_payload)


def test_unknown_field_inside_critical_is_rejected(valid_payload: dict[str, Any]) -> None:
    valid_payload["critical"]["referral_bonus"] = {"value": None, "stated": False, "evidence": None}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Extraction.model_validate(valid_payload)


def test_invalid_visa_value_inside_payload_is_rejected(valid_payload: dict[str, Any]) -> None:
    valid_payload["critical"]["visa_sponsorship"] = {
        "value": "maybe",
        "stated": True,
        "evidence": "Sponsorship may be considered",
    }
    with pytest.raises(ValidationError, match="critical.visa_sponsorship.value"):
        Extraction.model_validate(valid_payload)


# (g) Round trip through JSON, the way it is stored in extractions.payload_json.
def test_json_round_trip_gives_equal_object(valid_payload: dict[str, Any]) -> None:
    original = Extraction.model_validate(valid_payload)
    restored = Extraction.model_validate_json(original.model_dump_json())
    assert restored == original


# (h) The JSON schema builds. Task 1.4 hands it to the API.
def test_json_schema_builds_with_vocabulary_and_no_extra_keys() -> None:
    schema = Extraction.model_json_schema()
    text = json.dumps(schema)
    assert '"conditional"' in text and '"hybrid"' in text
    assert schema["additionalProperties"] is False
