import pytest
from pydantic import ValidationError

from toutoule.schemas import ExtractedField


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
