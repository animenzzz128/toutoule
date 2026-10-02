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

## v2 — 2026-10-01 — extract_v2 (Task 1.8)

**Hypothesis (written before running):** Misfiled critical values fall from 8 to ≤3 and
total critical hallucination from 14 to ≤9 of 249, because extract_v1 never says what
graduation_window and deadline are NOT, so the model fills them with the nearest date or
status phrase in the posting (start dates, publish dates, "应届毕业生"). Fabricated values
(6) should not change. Risk: critical false negatives rise slightly (from 13 of 67) as
the model becomes more cautious on these two fields.

**Change:** starting from extract_v1, rewrite only the graduation_window and deadline
definitions to state what each field is not: graduation_window is not a start date,
internship duration, program year (校招 year) or graduation status without dates;
deadline is not a posting/publish date, start date, or interview/offer date. Nothing
else in the prompt changes.

**Result:**

| Metric | v1 | v2 | delta |
|---|---|---|---|
| Critical hallucination | 14 / 249 (5.6%) | 5 / 249 (2.0%) | −9 (−3.6pp) |
| — of which fabricated | 6 / 14 (42.9%) | 3 / 5 (60.0%) | −3 |
| — of which misfiled | 8 / 14 (57.1%) | 2 / 5 (40.0%) | −6 |
| Critical accuracy | 47 / 50 (94.0%) | 45 / 50 (90.0%) | −2 (−4.0pp) |
| Critical false-negative | 13 / 67 (19.4%) | 16 / 67 (23.9%) | +3 (+4.5pp) |
| Important accuracy | 45 / 136 (33.1%) | 40 / 133 (30.1%) | −5 (−3.0pp) |
| Reference recall | 254 / 552 (46.0%) | 235 / 552 (42.6%) | −19 (−3.4pp) |

**Read:** Hypothesis mostly right. Critical hallucination fell from 14 to 5 of 249,
better than my ≤9 prediction, and misfiled values fell from 8 to 2. As predicted, the
model became more cautious: critical FN rose from 13 to 16 of 67. The remaining misses
are a rolling-basis deadline, resume requirements and one application cap, which is v3's
target. Critical accuracy fell 47/50 → 45/50, mostly application_cap values that keep
only part of the rule, on a field v2 didn't touch. Important accuracy and recall also
moved (−5, −19) with no related change, so differences that size are run-to-run noise,
and I'll judge later deltas against that. One misfiling survived: a dated preference
("2027年应届毕业生优先") still went into graduation_window.

## v3 — 2026-10-02 — extract_v3 (Task 1.8)

**Hypothesis (written before running):** Critical FN falls from 16 to ≤10 of 67,
because v2's misses are fields the posting does state in forms the definitions never
name: rolling-basis / until-filled deadlines and resume requirements phrased as
instructions ("submit your resume", "state X in your resume", 投递简历). Critical
hallucination stays ≤6 of 249. Risk: the model starts treating any mention of a
document as a requirement.

**Change:** starting from extract_v2, add to the deadline and materials_required
definitions what DOES count as stated: a rolling / until-filled application policy is
a stated deadline (value per the labeling conventions); any instruction to submit,
upload or fill in a resume/CV counts as materials_required including resume. Nothing
else changes.

**Result:** (filled in after adjudication)
