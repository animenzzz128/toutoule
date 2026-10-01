"""The plain-prompt baseline (PRD §1a, Task 1.7): what a scheduled-assistant prompt would
do. Same model, same reading task, no schema, no evidence, no verification.
"""

import logging
from pathlib import Path
from typing import Any

from toutoule import evalscore, extract

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parents[2] / "data" / "prompts" / "baseline_plain_v1.txt"
PROMPT_VERSION, PROMPT_BODY = extract.load_prompt(PROMPT_PATH)

# The exact label field names (05_EVAL_SPEC.md), spelled out in baseline_plain_v1.txt's
# own field list, so parsing needs no name-mapping table between prompt and schema.
FIELD_NAMES = (*evalscore.CRITICAL_FIELDS, *evalscore.IMPORTANT_FIELDS)
LIST_FIELDS = ("skills", "responsibilities")
ENUM_WORDS: dict[str, tuple[str, ...]] = {
    "visa_sponsorship": ("yes", "no", "conditional"),
    "work_model": ("onsite", "hybrid", "remote"),
}
_NOT_STATED = {"not stated", "not mentioned", "n/a", ""}


def run_baseline(client: extract.ModelClient, model: str, raw_text: str) -> tuple[str, int, int]:
    """One plain-text call: same model, same max_tokens as extract.py, no structured
    output and no temperature override (the API default, exactly as extract.py leaves it).

    Returns (reply text, input tokens, output tokens).
    """
    messages = [{"role": "user", "content": f"<job_posting>\n{raw_text}\n</job_posting>"}]
    response = client.messages.create(
        model=model, max_tokens=extract.MAX_TOKENS, system=PROMPT_BODY, messages=messages
    )
    usage = response.usage
    logger.info(
        "baseline call: model=%s stop_reason=%s input_tokens=%d output_tokens=%d",
        model,
        response.stop_reason,
        usage.input_tokens,
        usage.output_tokens,
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, usage.input_tokens, usage.output_tokens


def _parse_lines(text: str) -> dict[str, str]:
    """Turn `field: answer` lines into a dict, keyed by casefolded field name."""
    answers: dict[str, str] = {}
    for line in text.splitlines():
        name, sep, value = line.partition(":")
        if sep:
            answers[name.strip().casefold()] = value.strip()
    return answers


def parse_baseline(text: str) -> evalscore.SystemOutput:
    """Turn the baseline's raw reply into a SystemOutput. Evidence is always None: the
    baseline was never asked for a quote, so there is nothing to verify against."""
    answers = _parse_lines(text)
    fields: dict[str, Any] = {}
    for name in FIELD_NAMES:
        raw = answers.get(name)
        if raw is None or raw.casefold() in _NOT_STATED:
            fields[name] = evalscore.FieldOutput(stated=False, value=None, evidence=None)
            continue
        value = raw
        enum_words = ENUM_WORDS.get(name)
        if enum_words:
            lowered = raw.casefold()
            # Take the enum word if the answer starts with it; otherwise keep the raw
            # answer as is, so a free-text non-enum answer shows up as a mismatch to judge.
            value = next((word for word in enum_words if lowered.startswith(word)), raw)
        fields[name] = evalscore.FieldOutput(stated=True, value=value, evidence=None)

    def _list_field(name: str) -> list[str]:
        raw = answers.get(name)
        if raw is None or raw.casefold() in _NOT_STATED:
            return []
        return [item.strip() for item in raw.split(";") if item.strip()]

    team_raw = answers.get("team_or_function")
    team_or_function = None if team_raw is None or team_raw.casefold() in _NOT_STATED else team_raw

    return evalscore.SystemOutput(
        fields=fields,
        skills=_list_field("skills"),
        responsibilities=_list_field("responsibilities"),
        team_or_function=team_or_function,
    )
