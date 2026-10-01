# Iteration log

One change per version. Hypothesis written before running. Regressions are kept.

## v1 — 2026-10-01 — extract_v1 vs. baseline_plain_v1 (Task 1.7)

**Hypothesis (written before running):**
1. The plain-prompt baseline hallucinates about 20 of ~245 critical fields; the pipeline
   about 5. The gap comes mostly from the evidence requirement: without a quote to anchor
   on, the baseline fills fields from what postings usually say.
2. Deadline drives both systems' hallucinations. 37 of 50 postings state no deadline,
   and the likely errors are adding a year to day-month dates ("10月15日" → 2026-10-15),
   reporting a start date or posting date as the deadline, and filling a date where none
   exists. Graduation window is second ("2027届" turned into a month range), visa third
   (a work-authorization line read as "no sponsorship").
3. The pipeline is not at zero. The verbatim check stops invented quotes, but not a real
   quote with an inferred value (a correct "10月15日" quote with a year added). That is
   the first target for Task 1.8.
4. The pipeline's critical false-negative rate is higher than the baseline's (around 10%
   vs. 5%), because downgrades and evidence demands make it more cautious. This is the
   intended trade-off, so it should stay within the 10% tolerance.
5. Important-tier accuracy is below 90% for both systems, driven by location and
   language values returned in Chinese for Chinese postings: extract_v1 doesn't ask for
   English values, and the labels are in English.

**Change:** none. First measurement of the pipeline (extract_v1: schema + evidence +
verbatim check) and the plain-prompt baseline (same field definitions and formats, no
schema, no evidence, no verification), same model, same 50 postings, single run each.

**Result:** (filled in after adjudication)

**Read:** (filled in after adjudication)
