import pytest
from pydantic import ValidationError

from toutoule.schemas import (
    ExtractedField,
    ReferenceFields,
    VisaSponsorshipField,
    WorkModelField,
)


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
