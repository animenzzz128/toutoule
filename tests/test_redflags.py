import json
from pathlib import Path
from typing import Any

import pytest

from toutoule.redflags import Market, OwnerProfile, rule_r1_visa, rule_r4_cap
from toutoule.schemas import Extraction

FIXTURE = Path(__file__).parent / "fixtures" / "extraction_valid.json"
PROFILE = OwnerProfile(requires_sponsorship=True, graduation=(2027, 5), degree="master")
NOT_STATED: dict[str, Any] = {"value": None, "stated": False, "evidence": None}


def stated(value: str, evidence: str = "quoted from the posting") -> dict[str, Any]:
    return {"value": value, "stated": True, "evidence": evidence}


def make_extraction(**fields: dict[str, Any]) -> Extraction:
    """The valid fixture with some fields replaced: make_extraction(deadline=stated("...")).

    **fields collects the keyword arguments into a dict of field name -> new field. The
    result goes through model_validate, so the schema validators from Task 1.3 still run.
    """
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for name, field in fields.items():
        group = "critical" if name in data["critical"] else "important"
        data[group][name] = field
    return Extraction.model_validate(data)


# --- R1: visa sponsorship -------------------------------------------------------------


def test_r1_fires_on_no_sponsorship_for_us_role() -> None:
    quote = "We are unable to sponsor visas for this role."
    extraction = make_extraction(visa_sponsorship=stated("no", quote))

    flag = rule_r1_visa(extraction, PROFILE, market="US")

    assert flag is not None
    assert (flag.rule_id, flag.severity) == ("R1", "HARD")
    assert flag.field_path == "critical.visa_sponsorship"
    assert flag.evidence == quote  # copied unchanged


# parametrize runs this one test once per row below, and reports each row separately.
@pytest.mark.parametrize(
    ("value", "market", "requires_sponsorship"),
    [
        ("conditional", "US", True),  # "conditional" is not "no"
        ("yes", "US", True),
        ("no", "CN", True),  # R1 is about US work visas only
        ("no", None, True),  # unknown market never fires
        ("no", "US", False),  # the owner does not need sponsorship
    ],
)
def test_r1_does_not_fire(value: str, market: Market, requires_sponsorship: bool) -> None:
    extraction = make_extraction(visa_sponsorship=stated(value))
    profile = PROFILE.model_copy(update={"requires_sponsorship": requires_sponsorship})

    assert rule_r1_visa(extraction, profile, market) is None


# --- R4: application cap --------------------------------------------------------------


def test_r4_fires_when_cap_is_stated() -> None:
    flag = rule_r4_cap(make_extraction())  # the fixture states "2 per candidate"

    assert flag is not None
    assert (flag.rule_id, flag.severity) == ("R4", "SCARCE")
    assert flag.evidence == "Each candidate may apply to at most 2 positions"


def test_r4_does_not_fire_when_cap_is_not_stated() -> None:
    # R4 fires on any stated cap, so its only negative case is an unstated one.
    assert rule_r4_cap(make_extraction(application_cap=NOT_STATED)) is None
