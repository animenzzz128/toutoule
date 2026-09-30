import json
import logging
from pathlib import Path
from typing import Any

import pytest

from toutoule.redflags import (
    Market,
    OwnerProfile,
    rule_r1_visa,
    rule_r2_graduation,
    rule_r3_degree,
    rule_r4_cap,
)
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


# --- R2: graduation window (owner graduates 2027-05) ----------------------------------


@pytest.mark.parametrize(
    "window",
    [
        "2026-09 to 2027-04",  # ends the month before
        "2027-06 to 2028-05",  # starts the month after
        "2026-09 – 2027-04",  # en dash, which normalize_text turns into "-"
    ],
)
def test_r2_fires_when_graduation_is_outside_window(window: str) -> None:
    flag = rule_r2_graduation(make_extraction(graduation_window=stated(window)), PROFILE)

    assert flag is not None
    assert (flag.rule_id, flag.severity) == ("R2", "HARD")
    assert flag.field_path == "critical.graduation_window"


@pytest.mark.parametrize(
    "window",
    [
        "2027-05 to 2027-08",  # inclusive start edge
        "2026-09 to 2027-05",  # inclusive end edge
        "2026-09 - 2027-08",  # the " - " form
        "2027-05-31 to 2027-08-31",  # days are reduced to their month
    ],
)
def test_r2_does_not_fire_when_graduation_is_inside_window(window: str) -> None:
    assert rule_r2_graduation(make_extraction(graduation_window=stated(window)), PROFILE) is None


@pytest.mark.parametrize("window", ["2027-06", "before 2027-06", "2028-08 to 2027-09"])
def test_r2_unreadable_window_warns_and_does_not_fire(
    window: str, caplog: pytest.LogCaptureFixture
) -> None:
    # caplog is a pytest fixture that records log messages so the test can inspect them.
    with caplog.at_level(logging.WARNING):
        flag = rule_r2_graduation(make_extraction(graduation_window=stated(window)), PROFILE)

    assert flag is None
    assert "R2 skipped" in caplog.text


# --- R3: degree requirement -----------------------------------------------------------


@pytest.mark.parametrize(
    ("requirement", "degree"),
    [
        ("PhD required", "master"),
        ("PhD  Required.", "master"),  # case, spacing and a trailing period are ignored
        ("博士及以上", "master"),
        ("Undergraduates only", "master"),
        ("仅限本科", "phd"),
        ("Master’s or above", "bachelor"),  # curly apostrophe
    ],
)
def test_r3_fires_when_requirement_excludes_owner(requirement: str, degree: str) -> None:
    extraction = make_extraction(degree_requirement=stated(requirement))
    profile = PROFILE.model_copy(update={"degree": degree})

    flag = rule_r3_degree(extraction, profile)

    assert flag is not None
    assert (flag.rule_id, flag.severity) == ("R3", "HARD")
    assert flag.field_path == "important.degree_requirement"


@pytest.mark.parametrize(
    ("requirement", "degree"),
    [
        ("Bachelor's or above", "master"),
        ("本科及以上", "master"),
        ("PhD preferred", "master"),
        ("博士优先", "master"),
        ("MBA", "master"),
        ("Master's or above", "master"),
        ("Master's or above", "phd"),
        ("PhD required", "phd"),
        ("PhD", "master"),  # bare degree names are deliberately not on the list
        ("博士", "master"),
    ],
)
def test_r3_does_not_fire(requirement: str, degree: str) -> None:
    extraction = make_extraction(degree_requirement=stated(requirement))
    profile = PROFILE.model_copy(update={"degree": degree})

    assert rule_r3_degree(extraction, profile) is None
