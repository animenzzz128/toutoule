# ADR-003: Structured output with post-hoc verbatim-quote verification

**Status:** Accepted · 2026-09-29

## Context

投投乐's core promise is that a critical field (deadline, visa sponsorship, graduation
window, application cap, required materials) is never fabricated. The target is a 0%
hallucination rate (eval spec §2). A person decides whether to apply based on these values.

A language model can be *asked* to return JSON, quote its sources and say "not stated"
when unsure. It will usually comply. "Usually" does not give 0%. A prompt is a request.
Nothing enforces it, and a quote that looks plausible but was never in the posting is
exactly the failure we cannot afford. The plain-prompt baseline (PRD §1a, D-004) is
essentially "ask nicely", and it is the thing this product has to beat.

## Decision

Split the job into three layers. Each one catches what the layer before it cannot.

1. **Structured output (API).** The request carries the JSON schema of our Pydantic
   `Extraction` model (`output_config.format`). The API then guarantees the *shape*: every
   key is present, there are no extra keys, and `visa_sponsorship` / `work_model` stay
   inside their allowed values.
2. **Pydantic validation (our code).** `Extraction.model_validate_json` enforces what JSON
   Schema cannot express: `stated: false` ⟹ `value` and `evidence` are null, and
   `stated: true` ⟹ both are non-empty. On failure we retry exactly once, sending the
   error back. A second failure marks the job `extraction_failed` for manual entry. We
   use `messages.create`, not the SDK's `messages.parse`, so that this retry path belongs
   to us and has tests.
3. **Verbatim check (our code).** For all 10 critical and important fields, a stated
   field's `evidence` must be a substring of the source text after both have been
   normalized. If it is not, the field is downgraded to not stated and a row is written
   to `extraction_violations`. A violation never triggers a retry: the model already
   failed to quote, and asking again invites a better-looking fabrication.

`schema_version` and `prompt_version` are set by code after validation. They describe
our system, so the model's copy is ignored.

### Normalization, and why it stops where it does

`normalize_text` does exactly four things:

- Unicode NFKC. Full-width "：" becomes ":" and "２０２６" becomes "2026".
- Curly quotes become straight quotes.
- En and em dashes become "-".
- Every run of whitespace (line breaks, tabs, non-breaking spaces) becomes one space,
  and the ends are trimmed.

Each rule removes a difference in *formatting* that a faithful copy picks up from a web
page or a paste. None of them changes *meaning*. Each rule we might add next would change
meaning:

- **Case folding** is not needed, because a faithful copy already has the right case. It
  can also carry meaning: "US citizens" and "us" are different claims.
- **Punctuation stripping** would make "2 positions." equal "2 positions", and "10.31"
  equal "1031".
- **Fuzzy matching** (edit distance) would accept "10月31日" for "11月30日". That is one
  character apart, and it is the exact error that costs an application.

The line is drawn so that a normalization failure produces a false negative (a real quote
is rejected and the human sees "Not stated"), never a false positive. Eval spec §2 accepts
up to 10% false negatives on critical fields and 0% hallucinations. The asymmetry is
deliberate.

**Known limit: Chinese line wraps.** Chinese has no spaces between words. A posting that
wraps "网申截止\n时间" normalizes to "网申截止 时间", so a model quoting "网申截止时间" is
rejected. This is a false negative, the safe direction, so we accept it for now. If the
eval (Task 1.7) shows it causing false negatives on Chinese postings, removing whitespace
between CJK characters becomes a Task 1.8 iteration.

## Consequences

- The 0% hallucination claim for *quotes* is mechanical. A quote that is not in the
  posting cannot survive into the database, whatever the prompt says or the model does.
- **What the check does not prove.** It proves the quote *exists* in the source. It does
  not prove the *value* follows from the quote. A model can quote the real sentence
  "网申截止时间：2026年10月31日" and still write `value: "2026-11-30"`. A very short quote
  ("Yes") will also be found in almost any text. Value correctness is measured by the eval
  harness (Tasks 1.6–1.7) against human labels, and it is not claimed by this check.
- Every rejected quote is recorded in `extraction_violations`. The violation rate per
  prompt version becomes a metric in its own right.
- A retry roughly doubles the tokens for that job. Tokens are summed across both calls and
  stored on the extraction row, so this cost is visible.
- The structured-output requirement limits the choice of extraction model. The default is
  `claude-haiku-4-5` (small, supports structured output). A different model is a config
  change (`EXTRACTION_MODEL`), checked against the current Anthropic docs at that time.
