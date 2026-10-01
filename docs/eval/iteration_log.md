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

**Result:**

| Metric | Target | pipeline | baseline |
|---|---|---|---|
| Critical hallucination | 0% | 14 / 249 (5.6%) | 20 / 249 (8.0%) |
| — of which fabricated | — | 6 / 14 (42.9%) | 17 / 20 (85.0%) |
| — of which misfiled | — | 8 / 14 (57.1%) | 3 / 20 (15.0%) |
| Critical accuracy | ≥95% | 47 / 50 (94.0%) | 54 / 57 (94.7%) |
| Critical false-negative | ≤10% | 13 / 67 (19.4%) | 5 / 67 (7.5%) |
| Important accuracy | ≥90% | 45 / 136 (33.1%) | 61 / 133 (45.9%) |
| Reference recall | ≥80% | 254 / 552 (46.0%) | 353 / 552 (63.9%) |

**Read:** The baseline matched my prediction (20 vs ~20); the pipeline did much worse
than predicted (14 vs ~5). Splitting hallucinations explains why: the evidence
requirement cut fabricated values from 17 to 6, but the pipeline put real, correctly
quoted text in the wrong field 8 times (start dates as graduation windows, a publish
date as a deadline), and the verbatim check cannot catch that. Graduation window, not
deadline, was the biggest driver. The pipeline also misses more (19.4% FN vs 7.5%),
mainly rolling-basis deadlines and resume requirements. v2 should tighten the field
definitions for graduation_window and deadline in extract_v1, the single change with
the largest expected effect on hallucination.

Checked R2 against day-level graduation windows (cnp-11): already handled since the
rule's first commit; regression test added, no behaviour change.
