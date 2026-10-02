"""Tests for evalscore.py (Task 1.7, Part A). Hand-built fixtures only — never the real
data/eval/, so these tests stay independent of whatever the eval set currently contains.
"""

import pytest

from toutoule import evalscore, evalset, schemas

# --- Fixture helpers ---------------------------------------------------------------------


def _blank_field() -> evalset.LabeledField:
    return evalset.LabeledField(value=None, stated=False, evidence=None)


def _field(value: str, evidence: str = "quote", ambiguous: bool = False) -> evalset.LabeledField:
    return evalset.LabeledField(value=value, stated=True, evidence=evidence, ambiguous=ambiguous)


def make_label(
    case_id: str = "cnp-01", critical: dict | None = None, important: dict | None = None
) -> evalset.Label:
    """A Label with every field blank=stated:false, except the overrides given."""
    crit_fields = {name: _blank_field() for name in evalscore.CRITICAL_FIELDS}
    crit_fields["visa_sponsorship"] = evalset.LabeledVisaSponsorshipField(
        value=None, stated=False, evidence=None
    )
    crit_fields.update(critical or {})
    imp_fields = {name: _blank_field() for name in evalscore.IMPORTANT_FIELDS}
    imp_fields["work_model"] = evalset.LabeledWorkModelField(
        value=None, stated=False, evidence=None
    )
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


def _score(
    label: evalset.Label,
    output: evalscore.SystemOutput,
    field: str = "deadline",
    tier: str = "critical",
):
    results = evalscore.score_case(
        label, output, equivalences=set(), adjudications=[], system="pipeline"
    )
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


# --- Equivalences --------------------------------------------------------------------------


def test_equivalence_turns_mismatch_into_correct_for_both_systems():
    label = make_label(important={"degree_requirement": _field("Bachelor's or above")})
    output = make_output(important={"degree_requirement": _stated("本科及以上")})
    equivalences = {
        (
            "degree_requirement",
            evalscore.normalize_value("degree_requirement", "Bachelor's or above"),
            evalscore.normalize_value("degree_requirement", "本科及以上"),
        )
    }
    for system in ("pipeline", "baseline"):  # system-independent: applies to both equally
        results = evalscore.score_case(label, output, equivalences, adjudications=[], system=system)
        result = next(r for r in results if r.field == "degree_requirement")
        assert result.outcome == "correct"


def test_deadline_with_and_without_year_is_a_mismatch_not_correct():
    # "October 15" (no year, per README convention) vs "2026-10-15": dates compare as
    # written, never completed with a year, so this must not be treated as equal.
    label = make_label(critical={"deadline": _field("October 15")})
    output = make_output(critical={"deadline": _stated("2026-10-15")})
    assert _score(label, output).outcome == "mismatch"


def test_alias_table_matches_until_filled_to_its_chinese_phrasing():
    label = make_label(critical={"deadline": _field("until filled")})
    output = make_output(critical={"deadline": _stated("招满即止")})
    assert _score(label, output).outcome == "correct"


def test_deadline_month_day_is_never_converted_like_graduation_window():
    # Only graduation_window gets "Month YYYY" -> "YYYY-MM" conversion. A deadline that
    # differs only by an added year must still be a mismatch, not silently equal.
    label = make_label(critical={"deadline": _field("August 17")})
    output = make_output(critical={"deadline": _stated("2027-08-17")})
    assert _score(label, output).outcome == "mismatch"


# --- List-like field normalization -----------------------------------------------------


def test_materials_required_matches_across_different_separators():
    label_value = "resume + cover letter + transcript + writing sample"
    label = make_label(critical={"materials_required": _field(label_value)})
    output = make_output(
        critical={"materials_required": _stated("Resume, Cover letter, Transcript, Writing Sample")}
    )
    assert _score(label, output, field="materials_required").outcome == "correct"


def test_location_strips_us_state_codes_and_normalizes_washington_dc():
    label = make_label(
        important={
            "location": _field(
                "Boston / Chicago / Los Angeles / New York / Oakland / Tallahassee / Washington DC"
            )
        }
    )
    output = make_output(
        important={
            "location": _stated(
                "Boston, MA; Chicago, IL; Los Angeles, CA; New York, NY; Oakland, CA; "
                "Tallahassee, FL; Washington, DC"
            )
        }
    )
    assert _score(label, output, field="location", tier="important").outcome == "correct"


def test_graduation_window_converts_month_year_regardless_of_separator():
    label = make_label(critical={"graduation_window": _field("2026-12 / Summer 2027")})
    for system_value in ("December 2026/Summer 2027", "December 2026; Summer 2027"):
        output = make_output(critical={"graduation_window": _stated(system_value)})
        assert _score(label, output, field="graduation_window").outcome == "correct"


def test_graduation_window_nnnn_jie_shortcut_matches_label_graduates_phrasing():
    # cnp-05: label "2027 graduates", system (pipeline) literally "2027届". Before the
    # fix, the shortcut returned a plain string while every other value is a frozenset,
    # so the two could never compare equal even when they meant the same thing.
    label = make_label(critical={"graduation_window": _field("2027 graduates")})
    output = make_output(critical={"graduation_window": _stated("2027届")})
    assert _score(label, output, field="graduation_window").outcome == "correct"


def test_graduation_window_range_separators_match_to():
    # cnc-03: label "2025-01-01 to 2026-07-31", system (pipeline) "2025-01-01至2026-07-31"
    # — same range, written with the Chinese "至" instead of the English "to".
    label = make_label(critical={"graduation_window": _field("2025-01-01 to 2026-07-31")})
    output = make_output(critical={"graduation_window": _stated("2025-01-01至2026-07-31")})
    assert _score(label, output, field="graduation_window").outcome == "correct"


def test_degree_requirement_drops_trailing_degree_word():
    label = make_label(important={"degree_requirement": _field("Bachelor's or Master's")})
    output = make_output(important={"degree_requirement": _stated("Bachelor's or Master's degree")})
    assert _score(label, output, field="degree_requirement", tier="important").outcome == "correct"


# --- Adjudications -------------------------------------------------------------------------


def _adjudication(
    field: str,
    system_value: str | None,
    verdict: str,
    case_id: str = "cnp-01",
    system: str = "pipeline",
    line: int = 2,
) -> tuple[int, evalscore.AdjudicationRow]:
    return (
        line,
        evalscore.AdjudicationRow(
            case_id=case_id, system=system, field=field, system_value=system_value, verdict=verdict
        ),
    )


def test_stale_adjudication_is_ignored():
    label = make_label(critical={"deadline": _field("2026-10-31")})
    output = make_output(critical={"deadline": _stated("2026-11-01")})
    # Recorded against a value the system no longer gives: stale.
    adjudications = [_adjudication("deadline", "2026-12-01", "wrong")]
    results = evalscore.score_case(
        label, output, equivalences=set(), adjudications=adjudications, system="pipeline"
    )
    result = next(r for r in results if r.field == "deadline")
    assert result.outcome == "mismatch"
    assert result.verdict is None


def test_stale_adjudication_across_a_changed_outcome_is_ignored_not_raised():
    # A v1-style row: recorded as "wrong" against a mismatch. A new prompt version (v2)
    # now doesn't state the field at all, so the outcome is "missed", for which "wrong"
    # isn't a valid verdict. The row no longer matches the current system_value, so it
    # must be treated as stale before that validity check ever runs.
    label = make_label(critical={"deadline": _field("2026-10-31")})
    output = make_output()  # v2 doesn't state it: outcome is "missed"
    adjudications = [_adjudication("deadline", "2026-11-01", "wrong")]

    results = evalscore.score_case(
        label, output, equivalences=set(), adjudications=adjudications, system="pipeline"
    )

    result = next(r for r in results if r.field == "deadline")
    assert result.outcome == "missed"
    assert result.verdict is None


def test_invalid_verdict_for_outcome_raises_with_line_number():
    label = make_label(critical={"deadline": _field("2026-10-31")})
    output = make_output()  # system never stated it: outcome is "missed"
    # "wrong" is only valid for mismatch/unsupported, not missed.
    adjudications = [_adjudication("deadline", None, "wrong", line=7)]
    with pytest.raises(ValueError, match="line 7"):
        evalscore.score_case(
            label, output, equivalences=set(), adjudications=adjudications, system="pipeline"
        )


def test_confirmed_hallucination_verdict_counts_in_metrics():
    label = make_label()  # deadline not stated
    output = make_output(critical={"deadline": _stated("2026-10-31")})  # system invents it
    adjudications = [_adjudication("deadline", "2026-10-31", "hallucination")]
    results = evalscore.score_case(
        label, output, equivalences=set(), adjudications=adjudications, system="pipeline"
    )
    metrics = evalscore.compute_metrics(results)
    assert metrics.critical_hallucination.count == 1
    assert metrics.critical_hallucination.denominator == len(evalscore.CRITICAL_FIELDS)
    assert metrics.pending == 0


def test_label_error_keeps_field_pending_until_label_is_actually_fixed():
    label = make_label(critical={"deadline": _field("2026-10-31")})
    output = make_output(critical={"deadline": _stated("2026-11-01")})
    adjudications = [_adjudication("deadline", "2026-11-01", "label_error")]

    results = evalscore.score_case(label, output, set(), adjudications, "pipeline")
    metrics = evalscore.compute_metrics(results)
    result = next(r for r in results if r.field == "deadline")
    assert result.verdict == "label_error"
    assert metrics.pending == 1
    assert metrics.provisional is True
    # A mismatch's conservative default counts as "wrong", never as a hallucination.
    assert metrics.critical_hallucination.count == 0

    # Now the label is actually fixed to match what the system said.
    fixed_label = make_label(critical={"deadline": _field("2026-11-01")})
    fixed_results = evalscore.score_case(fixed_label, output, set(), adjudications, "pipeline")
    fixed_metrics = evalscore.compute_metrics(fixed_results)
    fixed_result = next(r for r in fixed_results if r.field == "deadline")
    assert fixed_result.outcome == "correct"
    assert fixed_metrics.pending == 0
    assert fixed_metrics.provisional is False


def test_provisional_false_when_no_pending_fields():
    label = make_label()
    output = make_output()
    metrics = evalscore.compute_metrics(evalscore.score_case(label, output, set(), [], "pipeline"))
    assert metrics.pending == 0
    assert metrics.provisional is False


def test_failed_extraction_counts_as_missed_never_as_hallucination():
    visa = evalset.LabeledVisaSponsorshipField(value="no", stated=True, evidence="quote")
    label = make_label(critical={"deadline": _field("2026-10-31"), "visa_sponsorship": visa})
    output = evalscore.failed_output()
    results = evalscore.score_case(label, output, set(), [], "pipeline")
    outcomes = {r.field: r.outcome for r in results if r.tier == "critical"}
    assert outcomes["deadline"] == "missed"
    assert outcomes["visa_sponsorship"] == "missed"
    assert outcomes["application_cap"] == "correct_absent"
    metrics = evalscore.compute_metrics(results)
    assert metrics.critical_hallucination.count == 0


# --- Reference recall ----------------------------------------------------------------------


def test_recall_on_a_small_list_example():
    label = make_label()
    label.reference.skills.extend(["Python", "SQL", "A/B testing"])
    output = make_output(skills=["Python", "Advanced SQL", "Excel"])
    recall = evalscore.reference_recall(label, output)
    # "Python" and "SQL" are single content words, fully covered by the system's items;
    # "A/B testing"'s content words ("b", "testing") appear in neither.
    assert recall.skills.count == 2
    assert recall.skills.denominator == 3


def test_recall_weakness_generic_single_word_label_item_inflates_recall():
    label = make_label()
    label.reference.skills.append("data")
    output = make_output(skills=["Data Analysis and SQL"])
    # A one-word label item only needs that one word to appear anywhere in the system's
    # items to count as 100% covered, even though the system never said anything specific
    # to the label's actual skill.
    assert evalscore.reference_recall(label, output).skills.count == 1


def test_recall_requires_at_least_half_the_label_items_content_words():
    label = make_label()
    label.reference.skills.append("data analysis and SQL")
    output = make_output(skills=["data"])
    # Content words: {"data", "analysis", "sql"} ("and" is a stopword). Only "data"
    # appears in the system's items: 1/3 < 50%, so this is not captured.
    assert evalscore.reference_recall(label, output).skills.count == 0


def test_recall_captures_a_label_item_whose_words_are_split_across_system_items():
    label = make_label()
    label.reference.skills.append("Strong learning, execution, communication skills")
    output = make_output(skills=["learning ability", "execution ability", "communication"])
    # "strong"/"skills" are dropped as domain stopwords; the remaining words (learning,
    # execution, communication) each appear in a different system item, pooled together.
    assert evalscore.reference_recall(label, output).skills.count == 1


def test_recall_not_captured_when_only_one_of_three_words_is_covered():
    label = make_label()
    label.reference.skills.append("logical analytical creative")
    output = make_output(skills=["logical thinking"])
    assert evalscore.reference_recall(label, output).skills.count == 0


def test_recall_team_or_function_keeps_the_substring_rule():
    label = make_label()
    label.reference.team_or_function = "TikTok Shop"
    output = make_output(team_or_function="TikTok Shop US operation team")
    recall = evalscore.reference_recall(label, output)
    assert recall.team_or_function == evalscore.Ratio(1, 1)
    assert recall.total.count == 1
    assert recall.total.denominator == 1


# --- Loading equivalences.csv / adjudications.csv ------------------------------------------
# tmp_path is a built-in pytest fixture: pytest creates a fresh, empty directory for each
# test and passes it in as a pathlib.Path, so file-based tests never touch real project
# files and never need their own cleanup.


def test_load_equivalences_from_csv(tmp_path):
    path = tmp_path / "equivalences.csv"
    path.write_text(
        "field,label_value,system_value,note\n"
        "degree_requirement,Bachelor's or above,本科及以上,common phrasing\n",
        encoding="utf-8",
    )
    entries = evalscore.load_equivalences(path)
    assert (
        "degree_requirement",
        evalscore.normalize_value("degree_requirement", "Bachelor's or above"),
        evalscore.normalize_value("degree_requirement", "本科及以上"),
    ) in entries


def test_load_adjudications_reports_line_numbers(tmp_path):
    path = tmp_path / "adjudications.csv"
    path.write_text(
        "case_id,system,field,system_value,verdict,note\n"
        "cnp-01,pipeline,deadline,2026-10-31,hallucination,\n",
        encoding="utf-8",
    )
    rows = evalscore.load_adjudications(path)
    assert rows == [
        (
            2,
            evalscore.AdjudicationRow(
                case_id="cnp-01",
                system="pipeline",
                field="deadline",
                system_value="2026-10-31",
                verdict="hallucination",
            ),
        )
    ]


def test_load_adjudications_rejects_invalid_verdict(tmp_path):
    path = tmp_path / "adjudications.csv"
    path.write_text(
        "case_id,system,field,system_value,verdict,note\ncnp-01,pipeline,deadline,2026-10-31,bogus,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 2"):
        evalscore.load_adjudications(path)
