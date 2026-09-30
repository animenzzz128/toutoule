import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from toutoule import models
from toutoule.config import get_settings
from toutoule.db import get_engine, get_session_factory, init_db
from toutoule.redflags import (
    Market,
    OwnerProfile,
    evaluate,
    has_hard_flag,
    rule_r1_visa,
    rule_r2_graduation,
    rule_r3_degree,
    rule_r4_cap,
    rule_r5_urgent,
    rule_r6_passed,
    save_red_flags,
)
from toutoule.schemas import CriticalFields, Extraction, ImportantFields

FIXTURE = Path(__file__).parent / "fixtures" / "extraction_valid.json"
PROFILE = OwnerProfile(requires_sponsorship=True, graduation=(2027, 5), degree="master")
TODAY = date(2026, 10, 1)
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


# --- R5 and R6: deadline (today is 2026-10-01) ----------------------------------------


def deadline_rules_fired(deadline: str) -> list[str]:
    """Which of R5 and R6 fire for this deadline value, as rule ids."""
    extraction = make_extraction(deadline=stated(deadline))
    flags = [rule_r5_urgent(extraction, TODAY), rule_r6_passed(extraction, TODAY)]
    return [flag.rule_id for flag in flags if flag is not None]


@pytest.mark.parametrize(
    ("days_from_today", "expected"),
    [
        (-1, ["R6"]),  # yesterday: passed
        (0, ["R5"]),  # today: still open, so urgent rather than passed
        (3, ["R5"]),  # the last urgent day
        (4, []),  # far enough away
    ],
)
def test_deadline_boundaries(days_from_today: int, expected: list[str]) -> None:
    deadline = (TODAY + timedelta(days=days_from_today)).isoformat()

    assert deadline_rules_fired(deadline) == expected


def test_r6_flag_carries_the_deadline_evidence() -> None:
    extraction = make_extraction(deadline=stated("2026-09-30", "Apply by 30 September 2026"))

    flag = rule_r6_passed(extraction, TODAY)

    assert flag is not None
    assert (flag.severity, flag.field_path) == ("HARD", "critical.deadline")
    assert flag.evidence == "Apply by 30 September 2026"


def test_month_only_deadline_in_a_past_month_has_passed() -> None:
    assert deadline_rules_fired("2026-09") == ["R6"]


def test_month_only_deadline_in_the_current_month_gives_no_flag() -> None:
    # It may be later this month, so it has not passed; and R5 never fires on a month.
    assert deadline_rules_fired("2026-10") == []


@pytest.mark.parametrize(
    "deadline", ["rolling basis", "ASAP", "within 2 weeks of posting", "2026-02-30"]
)
def test_unreadable_deadline_gives_no_flag(deadline: str) -> None:
    assert deadline_rules_fired(deadline) == []


# --- evaluate and the stated=False asymmetry ------------------------------------------


def test_evaluate_runs_the_rules_in_order() -> None:
    extraction = make_extraction(
        visa_sponsorship=stated("no"),
        graduation_window=stated("2027-06 to 2028-05"),
        degree_requirement=stated("PhD required"),
        deadline=stated("2026-09-30"),
    )

    flags = evaluate(extraction, PROFILE, "US", TODAY)

    assert [flag.rule_id for flag in flags] == ["R1", "R2", "R3", "R4", "R6"]
    assert has_hard_flag(flags)


def test_scarce_and_urgent_flags_are_not_hard() -> None:
    extraction = make_extraction(deadline=stated("2026-10-02"))

    flags = evaluate(extraction, PROFILE, "US", TODAY)

    assert [flag.rule_id for flag in flags] == ["R4", "R5"]
    assert not has_hard_flag(flags)


def test_not_stated_never_triggers_hard() -> None:
    # Every critical and important field, read from the schema so a new field is covered too.
    names = [*CriticalFields.model_fields, *ImportantFields.model_fields]
    extraction = make_extraction(**dict.fromkeys(names, NOT_STATED))

    flags = evaluate(extraction, PROFILE, "US", today=date(2100, 1, 1))

    assert not has_hard_flag(flags)
    assert flags == []


# Each HARD rule's positive case. Flipping only that field to stated=False must stop it.
HARD_CASES = [
    ("R1", "visa_sponsorship", stated("no")),
    ("R2", "graduation_window", stated("2027-06 to 2028-05")),
    ("R3", "degree_requirement", stated("PhD required")),
    ("R6", "deadline", stated("2026-09-30")),
]


@pytest.mark.parametrize(("rule_id", "name", "positive"), HARD_CASES)
def test_hard_rule_stops_when_its_field_is_not_stated(
    rule_id: str, name: str, positive: dict[str, Any]
) -> None:
    fired = evaluate(make_extraction(**{name: positive}), PROFILE, "US", TODAY)
    assert rule_id in [flag.rule_id for flag in fired]  # the positive case really fires

    flipped = evaluate(make_extraction(**{name: NOT_STATED}), PROFILE, "US", TODAY)
    assert rule_id not in [flag.rule_id for flag in flipped]


# --- save_red_flags -------------------------------------------------------------------


def test_save_red_flags_round_trip(tmp_path: Path) -> None:
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    extraction = make_extraction(visa_sponsorship=stated("no", "We do not sponsor visas."))
    flags = evaluate(extraction, PROFILE, "US", TODAY)  # R1 and R4

    with get_session_factory(engine)() as session:
        source = models.Source(name="Acme", tier=1, url="https://example.com", adapter="gh")
        session.add(source)
        session.flush()  # sends the INSERT so source.id is filled in
        job = models.Job(
            source_id=source.id,
            company="Acme",
            title="AI Product Manager",
            url="https://example.com/jobs/1",
            raw_text="We do not sponsor visas.",
            content_hash="a" * 64,
        )
        session.add(job)
        session.flush()
        save_red_flags(session, job.id, flags)
        session.commit()
        job_id = job.id

    with get_session_factory(engine)() as session:
        rows = session.scalars(select(models.RedFlag).order_by(models.RedFlag.id)).all()

    assert [(r.job_id, r.rule_id, r.severity, r.evidence) for r in rows] == [
        (job_id, "R1", "HARD", "We do not sponsor visas."),
        (job_id, "R4", "SCARCE", "Each candidate may apply to at most 2 positions"),
    ]


# --- OwnerProfile.from_settings -------------------------------------------------------


@pytest.mark.usefixtures("valid_env")
def test_owner_profile_from_default_settings() -> None:
    profile = OwnerProfile.from_settings(get_settings(env_file=None))

    assert profile == OwnerProfile(requires_sponsorship=True, graduation=(2027, 5), degree="master")


@pytest.mark.usefixtures("valid_env")
def test_owner_profile_from_overridden_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_REQUIRES_SPONSORSHIP", "false")
    monkeypatch.setenv("OWNER_GRADUATION", "2026-12")
    monkeypatch.setenv("OWNER_DEGREE", "phd")

    profile = OwnerProfile.from_settings(get_settings(env_file=None))

    assert profile == OwnerProfile(requires_sponsorship=False, graduation=(2026, 12), degree="phd")
