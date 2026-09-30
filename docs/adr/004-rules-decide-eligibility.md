# ADR-004: Rules, not the LLM, decide eligibility

**Status:** Accepted · 2026-09-30

## Context

Some jobs are ones the owner cannot apply to: the employer will not sponsor a US visa,
the graduation window misses the owner's graduation month, the role needs a PhD, or the
deadline has passed. Showing those jobs wastes attention. Hiding a job the owner *could*
apply to is worse, because nobody finds out it existed.

The simplest design asks the model "is this candidate eligible?" That is what the
scheduled-prompt baseline does (PRD §1a, D-004), and it has three problems:

- **It cannot be tested.** The same posting can get a different verdict on a different
  day or after a model upgrade. No test pins it down.
- **It cannot be explained.** A "no" comes with a fluent reason, but nothing ties that
  reason to a sentence in the posting.
- **It guesses in the costly direction.** Asked to decide, a model fills gaps. A posting
  that says nothing about sponsorship easily becomes "probably no sponsorship", and a
  real opportunity disappears.

## Decision

The model only extracts and cites (ADR-003). Six deterministic rules in `redflags.py`
decide (tech spec §4). R1, R2, R3 and R6 are HARD and exclude the job. R4 (SCARCE) and
R5 (URGENT) only change how it is shown.

- **Pure functions.** Each rule takes the extraction, the owner's profile, the market and
  today's date as arguments. It reads no database, no clock and no settings, so the same
  input always gives the same flags, and each rule is a one-line test.
- **The asymmetry.** A field with `stated: false` never fires any rule. That check is the
  first line of every rule. Unknown is shown to the human; it is never a reason to
  exclude.
- **Evidence travels with the flag.** Every flag carries the field's verbatim quote, which
  ADR-003 has already checked against the posting. A HARD flag can always be traced to
  words the employer actually wrote.

### Three kinds of "no flag"

A rule that returns nothing means one of three different things:

1. **Not stated.** The posting is silent. That is information, and the human sees it.
2. **Stated and fine.** The rule read the value and the owner passes: "conditional"
   sponsorship, a window that includes 2027-05, "Bachelor's or above".
3. **Stated but unreadable.** The value is not in a format the rule understands, e.g. a
   graduation window of "2027-06" alone or a deadline of "rolling basis". R2 logs a
   warning for this case. The deadline rules stay silent, because relative deadlines are
   normal.

All three leave the job in the digest. Only a positive, evidenced match excludes it.

## Consequences

- Every exclusion is reproducible and explainable: rule id, field, quote, one sentence.
- **Known limit: R3 is deliberately narrow.** It fires only when the normalized degree
  requirement exactly equals an entry on a short list (e.g. "phd required", "博士及以上",
  "undergraduates only"). "PhD degree required" or any other wording the list does not
  contain is missed, and the job reaches the human. That is the safe error. Widening the
  list is a code change with a test, never fuzzy or LLM-based matching.
- **Known limit: R2, R5 and R6 depend on the value format.** They read only the ISO forms
  extract_v1 asks for ("2026-10-31", "2026-09") and the ranges "A to B" / "A - B". The
  prompt does not pin down a range format, so model drift ("Sept 2026 – Aug 2027") turns
  R2 silent rather than wrong. Pinning the range format is a candidate for extract_v2,
  and the R2 warning count shows how often it happens.
- A month-only deadline fires R6 only after that whole month is over, and never fires R5.
- The market is an explicit input, not guessed from the location field. Until sources
  supply it, `None` means unknown, and R1 does not fire.
