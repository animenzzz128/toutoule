# ADR-004: Rules, not the LLM, decide eligibility

**Status:** Accepted · 2026-10-06

## Context

Some jobs are ones the owner cannot apply to: no US visa sponsorship, a graduation window
that misses his month, a PhD-only requirement, a passed deadline. Showing those wastes
attention; hiding a job he *could* apply to is worse, because nobody finds out it existed.

Asking the model "is this candidate eligible?" — what the scheduled-prompt baseline does
(PRD §1a, D-004) — cannot be tested (the same posting can get a different verdict on a
different day), cannot be explained (a fluent "no" ties to no sentence in the posting),
and guesses in the costly direction (silence on sponsorship easily becomes "probably no").

## Decision

The model only extracts and cites (ADR-003). Six deterministic rules in `redflags.py`
decide (tech spec §4). R1, R2, R3, R6 are HARD and exclude the job; R4 (SCARCE) and R5
(URGENT) only change how it is shown.

- **Pure functions.** Each rule takes the extraction, the owner's profile, the market and
  today's date as arguments — no database, no clock, no settings — so the same input
  always gives the same flags.
- **"Not stated" never excludes.** A field with `stated: false` never fires a rule; this
  is the first check in every rule function and is pinned down by
  `tests/test_redflags.py::test_not_stated_never_triggers_hard`.
- **A HARD flag can be overridden, but not silently.** `triage.record_decision` refuses an
  `approved` decision on a job with any HARD flag unless the caller passes
  `confirm_hard=True` — so discarding the rules' verdict is a deliberate, logged act, not
  a mis-click.
- **Evidence travels with the flag.** Every flag carries the field's verbatim quote,
  already checked against the posting by ADR-003.

## Consequences

- Every exclusion is reproducible and explainable: rule id, field, quote, one sentence.
- **Known limit: R3 is deliberately narrow.** It fires only on an exact match against a
  short list of excluding requirements (e.g. "phd required", "博士及以上"). Any other
  wording is missed, and the job reaches the human — the safe direction.
- **Finding (fixed in Task 1.11): R1 depended on an input that, in practice, never
  arrived until the app supplied it.** `market` was always an explicit parameter (never
  read off the `location` field), but the only caller that supplies a real value — the
  Streamlit app's market selector (`app/streamlit_app.py`) — did not exist until Task
  1.11. Before it, every real call to `run_triage` left `market=None`, so R1 could never
  fire outside a test that passed a market directly, however the input data looked.
- A month-only deadline fires R6 only after that whole month is over, and never fires R5.
- Rules only know what the model extracted and verified; a field the extractor misses or
  misfiles (ADR-003) is invisible to every rule, whatever the posting actually says.
