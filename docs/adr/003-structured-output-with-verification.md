# ADR-003: Structured output with post-hoc verbatim-quote verification

**Status:** Accepted · 2026-10-06

## Context

TouTouLe's core promise is that a critical field (deadline, visa sponsorship, graduation
window, application cap, required materials) is never fabricated. The target is a 0%
hallucination rate (eval spec §2) — a person decides whether to apply based on these
values.

A language model can be *asked* to return JSON, quote its sources and say "not stated"
when unsure, and it will usually comply. "Usually" does not give 0%. The plain-prompt
baseline (PRD §1a, D-004) is "ask nicely", and it is the thing this product has to beat.

## Decision (as built)

1. **Structured output (API).** The request carries the JSON schema of the Pydantic
   `Extraction` model. The API guarantees the *shape*: every key present, no extra keys,
   `visa_sponsorship`/`work_model` restricted to their allowed values.
2. **Pydantic validation (code).** `Extraction.model_validate_json` enforces
   `stated: false` ⟹ `value`/`evidence` null, `stated: true` ⟹ both non-empty
   (`schemas.py`). One retry on failure, error fed back; a second failure marks the job
   `extraction_failed`.
3. **Verbatim check (code, `extract.verify_evidence`).** Every stated critical/important
   field's `evidence` must be a substring of the source after `normalize_text` (NFKC,
   straight quotes, collapsed whitespace — formatting only, never meaning; case and
   punctuation are kept). A failed check downgrades the field to not-stated and logs to
   `extraction_violations`. No retry: the model already failed to quote.
4. **Materials support check (code, `extract.check_materials_support`, added in v4).**
   The verbatim check only proves a quote exists, not that it supports the value next to
   it. For `materials_required`, each item (e.g. "resume", "cover letter") must be named
   by its own quote via a keyword table (`MATERIAL_KEYWORDS`); an unsupported item is
   dropped, and the field becomes not-stated if none remain.

## Consequences

**What the check proves, and what it does not.** Rule 2 is the mechanical guarantee
behind the project's hallucination claim (`docs/04_EXECUTION_PLAN.md`, Task 1.4: "Rule 2
... is what makes the 0% hallucination claim mechanically true rather than a prompt
aspiration"). That sentence is about **quote existence**, and the measured results below
show plainly that it does not make the *overall* hallucination rate 0%:

- It proves the quote **exists** in the source. It does not prove the quote **supports**
  the value, or that the value belongs to the **field** it was attached to.
- v1 found this directly: 8 of 14 critical hallucinations (249 fields total) were
  "misfiled" — a real, correctly quoted span attached to the wrong field (a start date
  reported as `graduation_window`), which the verbatim check cannot catch because nothing
  was fabricated (`docs/eval/iteration_log.md`, v1).
- v3 found the same gap in a new field: hallucinations rose from 5/249 (v2) to 10/249
  because the model started quoting real, unrelated sentences as evidence for
  `materials_required: "resume"` — four of them from quotes that never mention a resume,
  for example the sentence "we look forward to seeing your application"
  (`docs/eval/iteration_log.md`, v3). The check passed them because the quote existed, not
  because it said anything about a resume.
- The materials support check (above) addressed **that one case**: applying it to v3's
  saved outputs cut critical hallucination from 10/249 to 6/249 by dropping exactly those
  four unsupported items. It does not address misfiling in other fields, which is
  unfixed.

**Measured results (`docs/eval/iteration_log.md`):**

| Run | Critical hallucination (of 249) |
|---|---|
| Baseline (plain prompt) | 20 |
| v1 (schema + evidence + verbatim check) | 14 |
| v4 derived (+ materials support check) | 6 |
| v4 repeat (fresh run, stability check) | 8 |

The hallucination rate is **not 0%** on the shipped version. 6–8 of 249 critical fields
remain hallucinated after three layers of checking. v4 was not reached because any of
D-009's stop conditions fired — it was an early stop, recorded as the D-009 amendment of
2026-10-02, made because the remaining errors (3 misfiled graduation windows, 3
fabricated values) looked like run-to-run noise against the 2026-10-04 M1 target, not
because all four targets were met or any other stop condition triggered.

- Every rejected quote (and dropped materials item) is logged to
  `extraction_violations`; the violation rate per prompt version is a metric in its own
  right.
- A retry roughly doubles the tokens for that job; tokens are summed and stored on the
  extraction row.
- The structured-output requirement limits the extraction model to one that supports it
  (default `claude-haiku-4-5`).
