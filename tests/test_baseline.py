"""Tests for baseline.py. No network: a fake client stands in for anthropic.Anthropic."""

from dataclasses import dataclass, field

from toutoule import baseline


@dataclass
class _FakeBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeResponse:
    content: list[_FakeBlock]
    usage: _FakeUsage
    stop_reason: str = "end_turn"


@dataclass
class _FakeMessages:
    reply_text: str
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(content=[_FakeBlock(self.reply_text)], usage=_FakeUsage(100, 20))


@dataclass
class _FakeClient:
    reply_text: str = "deadline: not stated\n"
    messages: _FakeMessages = field(init=False)

    def __post_init__(self):
        self.messages = _FakeMessages(self.reply_text)


def test_run_baseline_calls_the_model_plainly_no_structured_output():
    client = _FakeClient("deadline: 2026-10-31\n")
    text, input_tokens, output_tokens = baseline.run_baseline(client, "fake-model", "a posting")
    assert text == "deadline: 2026-10-31\n"
    assert (input_tokens, output_tokens) == (100, 20)
    call = client.messages.calls[0]
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
