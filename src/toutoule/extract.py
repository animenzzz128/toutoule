"""Extraction with evidence verification (tech spec §3, ADR-003).

The model reads a job posting and returns an Extraction. Code, not the prompt, then checks
that every quoted piece of evidence really appears in the posting.
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from anthropic import transform_schema
from pydantic import ValidationError

from toutoule import schemas

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parents[2] / "data" / "prompts" / "extract_v1.txt"


def load_prompt(path: Path = PROMPT_PATH) -> tuple[str, str]:
    """Return (version tag, prompt body). The tag is the file's first line."""
    version, _, body = path.read_text(encoding="utf-8").partition("\n")
    return version.strip(), body.strip()


PROMPT_VERSION, PROMPT_BODY = load_prompt()

# Typographic look-alikes that NFKC leaves alone. Each maps to its plain ASCII form.
_LOOKALIKES = str.maketrans(
    {
        "‘": "'",  # ‘
        "’": "'",  # ’
        "“": '"',  # “
        "”": '"',  # ”
        "–": "-",  # – en dash
        "—": "-",  # — em dash
    }
)
# In Python, \s covers every Unicode space: line breaks, tabs, non-breaking spaces.
_WHITESPACE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Normalize text so a faithful quote matches its source despite formatting noise.

    NFKC turns compatibility characters into their standard form (full-width "：" becomes
    ":"). Curly quotes and dashes become straight ones, and every run of whitespace becomes
    one space. Case and everything else are kept: see ADR-003 for why it stops there.
    """
    s = unicodedata.normalize("NFKC", s).translate(_LOOKALIKES)
    return _WHITESPACE.sub(" ", s).strip()


def quote_in_source(quote: str, source: str) -> bool:
    """True if the quote appears, after normalization, somewhere in the source."""
    return normalize_text(quote) in normalize_text(source)


# --- The model call ----------------------------------------------------------------------

# One extraction is roughly 1-2k output tokens; this leaves room without inviting rambling.
MAX_TOKENS = 8192
# Structured output: the API forces the reply into this JSON shape. It cannot express our
# statedness rule, so Extraction.model_validate_json below is still the real pass/fail gate.
OUTPUT_FORMAT = {"type": "json_schema", "schema": transform_schema(schemas.Extraction)}


class ExtractionFailed(Exception):
    """The model's answer failed validation twice. The job needs manual entry."""


class _Messages(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class ModelClient(Protocol):
    """Anything with .messages.create(...): the real anthropic.Anthropic, or a test fake."""

    messages: _Messages


def _call_model(
    client: ModelClient, model: str, messages: list[dict[str, str]]
) -> tuple[str, int, int]:
    """Make one API call. Return (reply text, input tokens, output tokens)."""
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=PROMPT_BODY,
        messages=messages,
        output_config={"format": OUTPUT_FORMAT},
    )
    usage = response.usage
    logger.info(
        "extraction call: model=%s stop_reason=%s input_tokens=%d output_tokens=%d",
        model,
        response.stop_reason,
        usage.input_tokens,
        usage.output_tokens,
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, usage.input_tokens, usage.output_tokens


def request_extraction(
    client: ModelClient, model: str, raw_text: str
) -> tuple[schemas.Extraction, int, int]:
    """Ask the model for an Extraction, retrying once if its answer fails validation.

    Returns (extraction, input tokens, output tokens), tokens summed over all calls.
    Raises ExtractionFailed on a second failure. Network and API errors are not retried
    here: the SDK already retries those itself.
    """
    messages = [{"role": "user", "content": f"<job_posting>\n{raw_text}\n</job_posting>"}]
    input_tokens = output_tokens = 0
    for attempt in (1, 2):
        text, used_in, used_out = _call_model(client, model, messages)
        input_tokens += used_in
        output_tokens += used_out
        try:
            return schemas.Extraction.model_validate_json(text), input_tokens, output_tokens
        except ValidationError as error:  # invalid JSON is a ValidationError too
            if attempt == 2:
                raise ExtractionFailed(f"model output failed validation twice: {error}") from None
            logger.warning("extraction failed validation, retrying once: %s", error)
            messages = [
                *messages,
                # The API rejects an empty assistant turn, so say that it was empty.
                {"role": "assistant", "content": text or "(empty response)"},
                {
                    "role": "user",
                    "content": f"Your answer failed validation:\n{error}\n"
                    "Return the corrected JSON object for the same posting.",
                },
            ]
    raise AssertionError("unreachable")  # the loop always returns or raises
