"""Tests for baseline.py. No network: a fake client stands in for anthropic.Anthropic."""

from fakes import FakeClient

from toutoule import baseline


def test_run_baseline_calls_the_model_plainly_no_structured_output():
    client = FakeClient("deadline: 2026-10-31\n")
    text, input_tokens, output_tokens = baseline.run_baseline(client, "fake-model", "a posting")
    assert text == "deadline: 2026-10-31\n"
    assert (input_tokens, output_tokens) == (1000, 300)
    call = client.requests[0]
    assert "output_config" not in call
    assert "temperature" not in call
    assert call["max_tokens"] == baseline.extract.MAX_TOKENS


def test_parse_baseline_well_formed_answer():
    text = "deadline: 2026-10-31\nvisa_sponsorship: yes\nskills: Python; SQL\n"
    output = baseline.parse_baseline(text)
    assert output.fields["deadline"].stated is True
    assert output.fields["deadline"].value == "2026-10-31"
    assert output.fields["deadline"].evidence is None
    assert output.skills == ["Python", "SQL"]


def test_parse_baseline_missing_line_is_not_stated():
    output = baseline.parse_baseline("deadline: 2026-10-31\n")
    assert output.fields["visa_sponsorship"].stated is False
    assert output.fields["visa_sponsorship"].value is None


def test_parse_baseline_not_stated_phrasing_variants():
    text = "deadline: not stated\nstart_date: N/A\ndegree_requirement: not mentioned\n"
    output = baseline.parse_baseline(text)
    assert output.fields["deadline"].stated is False
    assert output.fields["start_date"].stated is False
    assert output.fields["degree_requirement"].stated is False


def test_parse_baseline_free_text_visa_answer_is_kept_as_is():
    # Doesn't start with yes/no/conditional: kept raw so it shows up as a mismatch to judge.
    output = baseline.parse_baseline("visa_sponsorship: must be authorized to work in the US\n")
    field = output.fields["visa_sponsorship"]
    assert field.stated is True
    assert field.value == "must be authorized to work in the US"


def test_parse_baseline_list_line_splits_on_semicolon():
    output = baseline.parse_baseline("responsibilities: Own the roadmap; Run standups\n")
    assert output.responsibilities == ["Own the roadmap", "Run standups"]
