"""Match scoring (tech spec §5, D-010).

The model rates three dimensions and cites two quotes per evidence pair. Code computes the
total, checks both quotes against their sources, and picks the recommended resume version.
The model never sees the weights and never returns a total, so it cannot aim at one.

Unlike extraction, the scorer reads the raw posting text rather than the Extraction
(D-010 §4): evidence has to quote the posting, and that is one dependency fewer.
"""

import logging
from typing import NamedTuple

from anthropic import transform_schema
from pydantic import ValidationError

from toutoule import config, extract, schemas

logger = logging.getLogger(__name__)

# One score is a few hundred output tokens; this leaves room without inviting an essay.
MAX_TOKENS = 4096
OUTPUT_FORMAT = {"type": "json_schema", "schema": transform_schema(schemas.ScoreDraft)}

# D-010 §6. claude-sonnet-5-5 rejects a non-default temperature with a 400, so none is sent,
# and thinking is left at whatever the model defaults to. Recorded with every run — in the
# score payload now, and in the calibration run's meta.json in Part B — from this one dict,
# so the two can never disagree about how a number was produced. Runs are therefore not
# bit-identical; the optional repeat run is what measures that.
MODEL_SETTINGS: dict[str, str] = {"temperature": "not sent", "thinking": "model default"}

# The raw posting is sent whole, exactly as extraction sends it. Neither path truncates, so
# neither can score a posting the other read in full.


class ScoringFailed(Exception):
    """The model's answer failed validation twice. No score is stored for this version."""


class VersionScore(NamedTuple):
    """One scored version and what the call cost.

    A NamedTuple is a tuple whose parts also have names, so this unpacks like the tuples
    extract.py returns while still reading as .result and .input_tokens at the call site.
    """

    result: schemas.MatchResult
    input_tokens: int
    output_tokens: int


def combine(dimensions: schemas.Dimensions, weights: dict[str, int]) -> int:
    """Weighted 0-10 dimension scores to a 0-100 total (D-010 §1).

    round(10 * sum(w*s) / sum(w)). Dividing by the actual sum means the weights need not
    add up to 100, so changing one does not silently rescale every score.
    """
    weighted = sum(weights[name] * getattr(dimensions, name).score for name in weights)
    return round(10 * weighted / sum(weights.values()))


def verify_pairs(
    drafts: list[schemas.PairDraft], raw_text: str, resume_text: str
) -> list[schemas.EvidencePair]:
    """Check both quotes of every pair against their own source (D-010 §3).

    Uses extract.quote_in_source, so a quote is normalized the same way here as in the
    extraction verifier: one rule for what "copied verbatim" means, in one place.

    Every pair is returned whatever the outcome. Nothing is deleted from the record, so a
    fabricated quote stays auditable; the display layer hides the unverified ones.
    """
    pairs = []
    for draft in drafts:
        posting_ok = extract.quote_in_source(draft.requirement, raw_text)
        resume_ok = extract.quote_in_source(draft.experience, resume_text)
        if not posting_ok:
            logger.warning("evidence not in posting: %r", draft.requirement[:120])
        if not resume_ok:
            logger.warning("evidence not in resume: %r", draft.experience[:120])
        pairs.append(
            schemas.EvidencePair(
                requirement=draft.requirement,
                experience=draft.experience,
                verified=posting_ok and resume_ok,
            )
        )
    return pairs


def _call_model(
    client: extract.ModelClient, model: str, messages: list[dict[str, str]], prompt_body: str
) -> tuple[str, int, int]:
    """One scoring call. Returns (reply text, input tokens, output tokens)."""
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=prompt_body,
        messages=messages,
        output_config={"format": OUTPUT_FORMAT},
    )
    usage = response.usage
    logger.info(
        "scoring call: model=%s stop_reason=%s input_tokens=%d output_tokens=%d",
        model,
        response.stop_reason,
        usage.input_tokens,
        usage.output_tokens,
    )
    return (
        "".join(b.text for b in response.content if b.type == "text"),
        (usage.input_tokens),
        usage.output_tokens,
    )


def request_draft(
    client: extract.ModelClient, model: str, raw_text: str, resume_text: str, prompt_body: str
) -> tuple[schemas.ScoreDraft, int, int]:
    """Ask for a ScoreDraft, retrying once if the answer fails validation.

    Same shape as extract.request_extraction, including showing the model its own
    validation errors. Tokens are summed over both attempts.
    """
    messages = [
        {
            "role": "user",
            "content": f"<job_posting>\n{raw_text}\n</job_posting>\n\n"
            f"<resume>\n{resume_text}\n</resume>",
        }
    ]
    input_tokens = output_tokens = 0
    for attempt in (1, 2):
        text, used_in, used_out = _call_model(client, model, messages, prompt_body)
        input_tokens += used_in
        output_tokens += used_out
        try:
            return schemas.ScoreDraft.model_validate_json(text), input_tokens, output_tokens
        except ValidationError as error:
            if attempt == 2:
                raise ScoringFailed(f"model output failed validation twice: {error}") from None
            logger.warning("scoring failed validation, retrying once: %s", error)
            messages = [
                *messages,
                {"role": "assistant", "content": text or "(empty response)"},
                {
                    "role": "user",
                    "content": f"Your answer failed validation:\n"
                    f"{extract.describe_errors(error)}\n"
                    "Return the corrected JSON object for the same posting and resume.",
                },
            ]
    raise AssertionError("unreachable")  # the loop always returns or raises


def score_version(
    raw_text: str,
    resume_text: str,
    version: str,
    client: extract.ModelClient,
    model: str | None = None,
    prompt_version: str | None = None,
    prompt_body: str | None = None,
) -> VersionScore:
    """Score one posting against one resume version. One model call, or two on a retry.

    recommended_version is left None here: it is only knowable once all three versions have
    been scored, so score_job fills it in.
    """
    model = model or config.get_settings().score_model
    if prompt_body is None:
        prompt_version, prompt_body = extract.load_prompt_by_name(config.SCORE_PROMPT)
    draft, input_tokens, output_tokens = request_draft(
        client, model, raw_text, resume_text, prompt_body
    )
    pairs = verify_pairs(draft.evidence_pairs, raw_text, resume_text)
    result = schemas.MatchResult(
        resume_version=version,  # type: ignore[arg-type]  # checked by the Literal
        score=combine(draft.dimensions, config.SCORE_WEIGHTS),
        dimensions=draft.dimensions,
        evidence_pairs=pairs,
        gaps=draft.gaps,
        unverified_pairs=sum(not pair.verified for pair in pairs),
        prompt_version=prompt_version or config.SCORE_PROMPT,
        model=model,
    )
    return VersionScore(result, input_tokens, output_tokens)
