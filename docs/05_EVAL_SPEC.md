# 05 — Evaluation Specification

This document defines how the system is measured. It is the most important document in the
pack: the evaluation is what separates this project from a demo that calls an API.

---

## 1. Why tiered evaluation

A single accuracy number would be misleading here, because extraction errors in this domain
have wildly different costs.

| Error | Real cost |
|---|---|
| Missed one listed skill | Negligible |
| Missed "we are unable to sponsor visas" | A wasted application and hours of preparation |
| Invented a deadline that does not exist | A missed opportunity, discovered too late |
| Missed "maximum two applications per candidate" | A permanently spent, non-renewable slot |

Averaging these into one figure hides exactly the failures that matter. So fields are tiered
and each tier is measured differently, with the strictest treatment reserved for the fields
where fabrication is unrecoverable.

**This design decision is the single best thing to lead with in an AI PM interview.** It
demonstrates that you reasoned from cost of error to measurement design, rather than
reaching for accuracy because it is the default.

## 2. Tiers and targets

| Tier | Fields | Primary metric | Target |
|---|---|---|---|
| **Critical** | deadline, visa_sponsorship, graduation_window, application_cap, materials_required | **Hallucination rate** | **0%** |
| | | Accuracy (on stated fields) | ≥ 95% |
| | | False-negative rate (stated but marked not-stated) | ≤ 10% |
| **Important** | location, work_model, language_requirement, start_date, degree_requirement | Accuracy | ≥ 90% |
| **Reference** | skills, responsibilities, team_or_function | Recall | ≥ 80% |
| **Scoring** | match score | Agreement with human rating | ≥ 70% within ±10 |

### Metric definitions

**Hallucination** — the system returns `stated: true` with a value the source does not
support. This includes a correct-looking value that the source never actually stated. It is
counted per field, not per document, and the target is zero. Not "approximately zero".

**False negative** — the source does state the field, but the system returned
`stated: false`. Costly but recoverable: the human sees "Not stated" and can check. Hence
the looser 10% tolerance. **This asymmetry is deliberate and should be defended explicitly.**

**Accuracy** — among fields the system marked `stated: true` and did not hallucinate, the
fraction whose value matches the label after normalization (dates to ISO, sponsorship to a
three-value enum, whitespace and case collapsed).

**Recall** — for list fields, the fraction of labeled items captured. Precision is not a
target: extra plausible skills cost the reader nothing.

### Scoring implementation notes

- **Five outcomes per critical/important field:** `correct_absent` (neither side states
  it), `correct`, `mismatch` (both stated, values differ), `unsupported` (system stated,
  label did not), `missed` (label stated, system did not).
- **Denominators:** critical hallucination is counted over all scored critical fields
  (ambiguous excluded); critical accuracy over system-stated critical fields minus
  hallucinations; critical false-negative over label-stated critical fields; important
  accuracy over system-stated important fields (unsupported counts as an error there, no
  adjudication); reference recall over labeled list items, reported per field (skills,
  responsibilities, team_or_function) and as a combined total.
- **Provisional:** a run's metrics are provisional until every critical
  mismatch/unsupported/missed field has an owner verdict (or a matching equivalence). An
  unsupported field with no verdict yet counts as a hallucination by default, and a
  mismatch as wrong — the conservative assumption, so provisional numbers never
  understate the hallucination rate.
- **Verdicts:** `h` (hallucination), `w` (wrong — stated but imprecise/incomplete, not
  invented), `m` (missed — confirmed false negative), `le` (label_error — the label
  itself was wrong; fixed directly in the label file, not recorded as a verdict). An `h`
  verdict's note is prefixed `misfiled:` when the system attached a real, correctly
  quoted span to the wrong field (e.g. a start date reported as the graduation window),
  distinguishing it from a fabricated value with no textual basis at all.
- **Equivalences are system-independent:** one `equivalences.csv` row (field, label
  value, system value) applies to both the pipeline and the baseline, and to every case
  where that exact pair recurs.
- **Ambiguous fields are excluded for both systems** — never counted toward any metric,
  for either the pipeline or the baseline.
- **Normalization rules:** `location`, `materials_required` and `graduation_window`
  compare as order-insensitive sets after splitting on their field-specific separators;
  English month names convert to `YYYY-MM` (`graduation_window` only); `NNNN届` converts
  to the label's `NNNN graduates` phrasing; `-`/`–`/`—`/至 between two dates normalize to
  `to`. Dates are otherwise compared as written — a year is never added where the source
  didn't give one.
- **Recall is ≥50% content-word coverage** (stopwords and domain words dropped, pooled
  across a field's system items). This under-counts a real paraphrase that shares few
  words with the label, and under-counts a Chinese system answer against an English
  label even when they mean the same thing, since the words literally don't overlap.
- **The baseline is `extract_v1.txt` minus three things:** the JSON schema, the evidence
  requirement, and the verbatim-verification check. Same field definitions, same value
  formats, same model.

## 3. Building the eval set

**Size:** 50 job descriptions.

**Composition** — deliberately skewed toward the cases that break things:

| Segment | Count | Why |
|---|---|---|
| China platform / e-commerce | 20 | Primary target; bilingual postings (see D-005) |
| China campus programs | 10 | Where application caps appear |
| US consulting / finance | 10 | Where sponsorship clauses appear |
| US tech | 10 | AI PM roles (see D-005) |
| **Postings with no stated deadline** | 5 | Tests the `Not stated` path — the most common hallucination trigger |
| **Bilingual or Chinese-only postings** | 5 | Tests language handling |

The last two segments overlap the first four; the point is to guarantee their presence
rather than hope for it.

**Sourcing:** copy the full source text from the official posting. Commit it to
`data/eval/raw/`. Record the URL and retrieval date — postings change and disappear, and an
unreproducible eval set is worthless six weeks later.

### Labeling rules

1. **Label from the source document only.** Do not use prior tracker entries. The existing
   tracker contains values marked "Not stated" and "Verify on site" that were inferred
   rather than read — importing them would contaminate the ground truth with the system's
   own assumptions.
2. **If the document does not state it, the label is `stated: false`.** Even when you
   personally know the answer. The system is being measured on reading, not on knowledge.
3. **Record the verbatim quote in the label** for every `stated: true` critical field. This
   is what the post-hoc verification checks against.
4. **Normalize dates to ISO 8601** in labels. Preserve the original phrasing in the quote.
5. **When a field is genuinely ambiguous, mark it `ambiguous: true`** and exclude it from
   scoring. Do not force a judgment call into the ground truth — roughly 2–4 such cases out
   of 50 is normal, and more than 8 means the schema needs refining.

**Labeling cost:** roughly 6–8 minutes per posting, so 5–7 hours total. This is the single
largest time investment in Phase 1 and it is not optional. Everything the project claims
rests on it.

## 4. Match-score calibration

Unlike extraction, match scoring has no objective ground truth. The human baseline is the
owner's own judgment.

1. The human baseline is the 20 manual scores given during Task 1.6
   (`data/eval/human_scores.csv`); the tracker's scores were AI-assigned and are not used
   (D-010).
2. Score 20 more eval postings manually **before** running the system, to avoid anchoring.
3. Measure agreement: the fraction of postings where system and human are within ±10.
4. Target ≥70%. Below that, inspect the largest disagreements — they usually reveal a
   weighting problem, not a model problem.

Disagreements are more informative than the agreement rate. A systematic gap (the system
consistently overrating consulting roles, say) points directly at a weight to adjust.

## 5. Iteration protocol

Every change is logged to `docs/eval/iteration_log.md`:

```markdown
## v3 — 2026-10-04

**Hypothesis:** deadline hallucinations come from postings that state a start date but no
application deadline; the model conflates the two.

**Change:** added an explicit instruction distinguishing application deadline from role
start date; added 3 few-shot examples of deadline-absent postings.

**Result:**
| Metric | v2 | v3 |
|---|---|---|
| Critical hallucination | 6% | 2% |
| Critical accuracy | 89% | 93% |
| False negative | 8% | 11% |

**Read:** hallucination halved, but false negatives rose — the model is now over-cautious on
deadlines. Acceptable under the stated asymmetry, but at the tolerance limit. v4 should try
to recover precision without reintroducing fabrication.
```

Three rules:

- **One change per version.** Two simultaneous changes make the result uninterpretable.
- **Write the hypothesis before running.** Otherwise the log becomes post-hoc
  rationalization, which is both bad science and obvious to an interviewer.
- **Log regressions.** A version that made things worse is the most credible evidence that
  the log is honest. Deleting failures is the tell that a portfolio has been curated.

The log is a deliverable, not a byproduct. Expect an interviewer to read it.

## 6. Production metrics

Eval measures correctness on a fixed set. These measure whether it works in real use.

| Metric | How | Why it matters |
|---|---|---|
| Time per job description | Manual baseline on 5 postings before building; system time from logs | The efficiency claim |
| Digest approval rate | approvals ÷ recommendations, weekly | Ranking quality |
| **Approval-rate trend** | Week over week, annotated with threshold changes | Whether the feedback loop works |
| Reject-reason distribution | Grouped counts | Points at which filter to fix next |
| Cost per processed job | Token logs × current pricing | Unit economics |
| Source health | Sources returning content ÷ enabled sources | Guardrail on silent failure |
| **Deadlines missed** | Manual audit, weekly | The one number that must stay at zero |

Always report the approval-rate trend alongside threshold changes. A rise caused by raising
the threshold is a different finding from a rise caused by better ranking, and conflating
them is the kind of claim an interviewer will probe.

## 7. What this project does not claim

State these limits plainly. Volunteering them is more persuasive than being caught by them.

- **No claim about interview or offer rates.** n is too small and the confounds are
  overwhelming.
- **No claim of complete market coverage.** WeChat-only postings are outside the compliance
  boundary (PD-6). Coverage is high-value, not exhaustive.
- **No claim of generalization beyond campus recruiting.** The eval set is one candidate's
  target market in one cycle.
- **The eval set skews toward China platform / e-commerce** (20 of 50, see D-005). Results
  weight the owner's primary market and may not reflect performance on other segments.
- **Match scoring is calibrated to one person.** It reflects the owner's judgment, including
  its biases. Phase 3's external pilot is the first real test of whether it transfers.
- **No held-out set:** prompts were tuned on the same 50 postings they are scored on, so
  results may overstate performance on new postings (D-009).

## Scoring harness normalization rules (Task 1.7 Part E)

Found and fixed after the first real run (`2026-10-01T1920`), which surfaced false
mismatches that were punctuation and phrasing differences, not real extraction errors.
These are harness rules only — they never touch `extract_v1.txt`, `baseline_plain_v1.txt`,
or any label, and every rule applies identically to both systems.

**List-like text fields, compared as order-insensitive sets after normalization:**
- `materials_required` splits on `+`, `;`, `,`, `/` and the word "and".
- `location` splits on `;` and `/`. "Washington, DC" and "Washington D.C." are folded to
  "washington dc" *before* a trailing `, XX` US state code is stripped — otherwise the "DC"
  reads as a state abbreviation and the city name is lost. Any comma still remaining after
  that is then split too.
- `graduation_window` splits on `/` and `;` (treated as the same separator) and converts an
  English "Month YYYY" token (full or short name) to `YYYY-MM` on either side. "to" ranges
  are left as written. A year is never added where the source didn't give one.

**`degree_requirement`** drops a trailing "degree"/"degrees" before comparing, so
"Bachelor's or Master's" and "Bachelor's or Master's degree" are the same value.

**Reference recall** tokenizes each item into lowercase content words, dropping a short
English stopword list plus "ability", "skills", "strong" and "experience" (generic enough
in this domain that nearly every item carries one). A label item counts as captured if at
least 50% of its content words appear anywhere in that field's system items, pooled
together rather than matched one item at a time. `team_or_function` keeps the original
substring rule instead, since it's a single string, not a list. Recall is reported per
field (skills / responsibilities / team_or_function) as well as the combined total that
§2's ≥80% target applies to.
