"""Tests for evalscore.py (Task 1.7, Part A). Hand-built fixtures only — never the real
data/eval/, so these tests stay independent of whatever the eval set currently contains.
"""

from toutoule import evalscore, evalset, schemas

# --- Fixture helpers ---------------------------------------------------------------------


def _blank_field() -> evalset.LabeledField:
    return evalset.LabeledField(value=None, stated=False, evidence=None)


def _field(value: str, evidence: str = "quote", ambiguous: bool = False) -> evalset.LabeledField:
    return evalset.LabeledField(value=value, stated=True, evidence=evidence, ambiguous=ambiguous)


def make_label(case_id: str = "cnp-01", critical: dict | None = None, important: dict | None = None) -> evalset.Label:
    """A Label with every field blank=stated:false, except the overrides given."""
    crit_fields = {name: _blank_field() for name in evalscore.CRITICAL_FIELDS}
    crit_fields["visa_sponsorship"] = evalset.LabeledVisaSponsorshipField(value=None, stated=False, evidence=None)
    crit_fields.update(critical or {})
    imp_fields = {name: _blank_field() for name in evalscore.IMPORTANT_FIELDS}
    imp_fields["work_model"] = evalset.LabeledWorkModelField(value=None, stated=False, evidence=None)
    imp_fields.update(important or {})
    return evalset.Label(
        case_id=case_id,
        company="Acme",
        title="Product Manager",
        critical=evalset.LabeledCriticalFields(**crit_fields),
        important=evalset.LabeledImportantFields(**imp_fields),
        reference=schemas.ReferenceFields(skills=[], responsibilities=[], team_or_function=None),
    )


def make_output(
    critical: dict | None = None,
    important: dict | None = None,
    skills: list[str] | None = None,
    responsibilities: list[str] | None = None,
    team_or_function: str | None = None,
) -> evalscore.SystemOutput:
    fields = {
        name: evalscore.FieldOutput(stated=False, value=None, evidence=None)
        for name in (*evalscore.CRITICAL_FIELDS, *evalscore.IMPORTANT_FIELDS)
    }
    fields.update(critical or {})
    fields.update(important or {})
    return evalscore.SystemOutput(
        fields=fields,
        skills=skills or [],
        responsibilities=responsibilities or [],
        team_or_function=team_or_function,
    )


def _stated(value: str, evidence: str | None = "quote") -> evalscore.FieldOutput:
    return evalscore.FieldOutput(stated=True, value=value, evidence=evidence)


def _score(label: evalset.Label, output: evalscore.SystemOutput, field: str = "deadline", tier: str = "critical"):
    results = evalscore.score_case(label, output, equivalences=set(), adjudications=[], system="pipeline")
    return next(r for r in results if r.field == field and r.tier == tier)


# --- One test per outcome -----------------------------------------------------------------


def test_correct_absent_when_neither_states_it():
    result = _score(make_label(), make_output())
    assert result.outcome == "correct_absent"


def test_correct_when_values_match_after_normalization():
    label = make_label(critical={"deadline": _field("2026-10-31")})
    output = make_output(critical={"deadline": _stated("2026-10-31")})
    assert _score(label, output).outcome == "correct"


def test_mismatch_when_both_stated_but_values_differ():
    label = make_label(critical={"deadline": _field("2026-10-31")})
    output = make_output(critical={"deadline": _stated("2026-11-01")})
    assert _score(label, output).outcome == "mismatch"


def test_unsupported_when_system_states_what_label_does_not():
    label = make_label()
    output = make_output(critical={"deadline": _stated("2026-10-31")})
    assert _score(label, output).outcome == "unsupported"


def test_missed_when_label_states_what_system_does_not():
    label = make_label(critical={"deadline": _field("2026-10-31")})
    output = make_output()
    assert _score(label, output).outcome == "missed"


def test_ambiguous_label_field_is_excluded_regardless_of_system():
    label = make_label(critical={"deadline": _field("2026-10-31", ambiguous=True)})
    output = make_output(critical={"deadline": _stated("2026-11-01")})
    result = _score(label, output)
    assert result.outcome == "excluded"
