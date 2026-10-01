"""Extraction with evidence verification (tech spec §3, ADR-003).

The model reads a job posting and returns an Extraction. Code, not the prompt, then checks
that every quoted piece of evidence really appears in the posting.
"""

import hashlib
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from anthropic import transform_schema
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from toutoule import models, schemas

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parents[2] / "data" / "prompts" / "extract_v1.txt"
PROMPTS_DIR = PROMPT_PATH.parent


def load_prompt(path: Path = PROMPT_PATH) -> tuple[str, str]:
    """Return (version tag, prompt body). The tag is the file's first line."""
    version, _, body = path.read_text(encoding="utf-8").partition("\n")
    return version.strip(), body.strip()


class PromptNotFound(Exception):
    """No file named data/prompts/<name>.txt."""


def load_prompt_by_name(name: str) -> tuple[str, str]:
    """Load a prompt by its file name, e.g. "extract_v2" -> data/prompts/extract_v2.txt.

    Used by the eval CLI (Task 1.8) to select which prompt version the pipeline runs
    against, without editing extract_v1.txt or the extraction code path itself.
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise PromptNotFound(f"no prompt file at {path}")
    return load_prompt(path)


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


def hash_content(raw_text: str) -> str:
    """SHA-256 of the normalized text: formatting-only changes keep the same hash."""
    return hashlib.sha256(normalize_text(raw_text).encode("utf-8")).hexdigest()


def find_cached(
    session: Session, content_hash: str, prompt_version: str, model: str
) -> models.Extraction | None:
    """The newest stored extraction of this exact text by this prompt and model, if any.

    All three are the cache key: a new prompt version or model must re-extract, so that
    evaluation runs (Task 1.8) can compare versions on the same postings.
    """
    query = (
        select(models.Extraction)
        .join(models.Job, models.Job.id == models.Extraction.job_id)
        .where(
            models.Job.content_hash == content_hash,
            models.Extraction.prompt_version == prompt_version,
            models.Extraction.model == model,
        )
        .order_by(models.Extraction.id.desc())
    )
    return session.scalars(query).first()


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
    client: ModelClient, model: str, messages: list[dict[str, str]], prompt_body: str
) -> tuple[str, int, int]:
    """Make one API call. Return (reply text, input tokens, output tokens)."""
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=prompt_body,
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


def describe_errors(error: ValidationError) -> str:
    """One line per problem, "- field.path: message", for the retry message to the model.

    Pydantic's own message is kept word for word. Its input echo and docs URL are left out:
    the model gets its whole previous answer back anyway.
    """
    lines = []
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"]) or "(whole answer)"
        lines.append(f"- {where}: {problem['msg']}")
    return "\n".join(lines)


def request_extraction(
    client: ModelClient, model: str, raw_text: str, prompt_body: str | None = None
) -> tuple[schemas.Extraction, int, int]:
    """Ask the model for an Extraction, retrying once if its answer fails validation.

    prompt_body=None resolves to the current PROMPT_BODY at call time (not def time), so
    a test or caller that monkeypatches extract.PROMPT_BODY still takes effect.

    Returns (extraction, input tokens, output tokens), tokens summed over all calls.
    Raises ExtractionFailed on a second failure. Network and API errors are not retried
    here: the SDK already retries those itself.
    """
    prompt_body = prompt_body if prompt_body is not None else PROMPT_BODY
    messages = [{"role": "user", "content": f"<job_posting>\n{raw_text}\n</job_posting>"}]
    input_tokens = output_tokens = 0
    for attempt in (1, 2):
        text, used_in, used_out = _call_model(client, model, messages, prompt_body)
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
                    "content": f"Your answer failed validation:\n{describe_errors(error)}\n"
                    "Return the corrected JSON object for the same posting.",
                },
            ]
    raise AssertionError("unreachable")  # the loop always returns or raises


# --- Verification and saving -------------------------------------------------------------

# The groups whose fields carry evidence. Reference fields have no quotes to check.
EVIDENCE_GROUPS = ("critical", "important")
REASON_QUOTE_LIMIT = 200


def verify_evidence(
    extraction: schemas.Extraction, raw_text: str
) -> tuple[schemas.Extraction, list[tuple[str, str]]]:
    """Downgrade every stated field whose quote is not in the source (tech spec §3 rule 2).

    Returns (verified copy, [(field_path, reason), ...]). A downgraded field keeps its class,
    so a VisaSponsorshipField stays one. The input extraction is not changed.
    """
    violations: list[tuple[str, str]] = []
    new_groups: dict[str, Any] = {}
    for group_name in EVIDENCE_GROUPS:
        group = getattr(extraction, group_name)
        downgraded: dict[str, schemas.ExtractedField] = {}
        for field_name in type(group).model_fields:
            field = getattr(group, field_name)
            quote = field.evidence or ""  # never empty when stated: the schema forbids it
            if field.stated and not quote_in_source(quote, raw_text):
                downgraded[field_name] = type(field)(value=None, stated=False, evidence=None)
                reason = f"quote not found in source: {quote[:REASON_QUOTE_LIMIT]!r}"
                violations.append((f"{group_name}.{field_name}", reason))
        new_groups[group_name] = group.model_copy(update=downgraded)
    return extraction.model_copy(update=new_groups), violations


def extract_job(
    session: Session,
    job: models.Job,
    client: ModelClient,
    model: str,
    prompt_version: str | None = None,
    prompt_body: str | None = None,
) -> schemas.Extraction:
    """Extract, verify and save one job. Commits the session.

    prompt_version/prompt_body=None resolve to the current extract_v1 PROMPT_VERSION/
    PROMPT_BODY at call time (not def time), so a monkeypatch of those module attributes
    still takes effect. The eval harness (Task 1.8) passes an explicit pair to run the
    same code against another prompt version without touching this function's callers
    in production.

    On success: one extractions row, one extraction_violations row per rejected quote, and
    job.status "extracted". On ExtractionFailed: job.status "extraction_failed", no
    extractions row, and the error is raised again for the caller to report.
    """
    prompt_version = prompt_version if prompt_version is not None else PROMPT_VERSION
    try:
        extraction, input_tokens, output_tokens = request_extraction(
            client, model, job.raw_text, prompt_body
        )
    except ExtractionFailed:
        job.status = models.JobStatus.EXTRACTION_FAILED
        session.commit()
        raise
    # Versions describe our code, so code sets them; whatever the model wrote is ignored.
    extraction = extraction.model_copy(
        update={"schema_version": schemas.SCHEMA_VERSION, "prompt_version": prompt_version}
    )
    extraction, violations = verify_evidence(extraction, job.raw_text)
    for field_path, reason in violations:
        logger.warning("job %s: %s downgraded, %s", job.id, field_path, reason)
        session.add(models.ExtractionViolation(job_id=job.id, field_path=field_path, reason=reason))
    session.add(
        models.Extraction(
            job_id=job.id,
            prompt_version=extraction.prompt_version,
            schema_version=extraction.schema_version,
            payload_json=extraction.model_dump(mode="json"),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    )
    job.status = models.JobStatus.EXTRACTED
    session.commit()
    return extraction
