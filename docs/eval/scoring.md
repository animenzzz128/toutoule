# Match scoring: calibration and what it showed

Task 1.9. Design and calibration rule: [D-010](../06_DECISION_LOG.md). Run report:
[2026-10-03T0132-score](scoring/2026-10-03T0132-score.md).

**Headline: the first calibration run scored 3 / 20 within ±10 of the owner's own scores,
against 10 / 20 for a constant guess. The target was 14 / 20. It was not met, and no
adjustment was made.** What follows is why, and what the disagreement turned out to measure.

## What the scorer does

One model call per (posting, resume version), three versions per posting. The model rates
three dimensions 0–10 with a one-line reason each — domain fit, skills overlap, seniority
fit — and returns exactly three evidence pairs and two gaps. It never returns a total and
is never told the weights.

Code does the rest. It computes the total as `round(10 × Σ wᵢ·sᵢ / Σ wᵢ)` with weights from
config (40 / 35 / 25), checks both quotes of every evidence pair against the posting and the
résumé with the same normalisation the extraction verifier uses, and picks the recommended
version by highest total with a fixed tie-break order. A posting's score is its recommended
version's score.

Seniority fit rates level and experience only. Visa sponsorship, work authorisation,
location and graduation windows are decided by the red-flag rules, never by the score
(D-010 §5). This matters for the analysis below.

## The calibration set

Twenty postings the owner scored by hand during Task 1.6, before any system scoring
existed, stored in `data/eval/human_scores.csv` with a free-text reason for each. They are
drawn from the 50-posting eval set: 4 cn_campus, 7 cn_platform, 4 us_consulting_finance,
5 us_tech.

**Why not the tracker's scores.** The execution plan originally named "the owner's 13
existing manual Priority Scores". On inspection the tracker holds 32 scores, all assigned
by an AI during an earlier job search, for postings outside this project. They are not a
human baseline, so they are not used anywhere in this project and contribute to no metric
(D-010).

**No held-out set.** All 20 are used for calibration, by the owner's choice, to save time
before a recruiting deadline. Any adjustment measured on them would be an upper bound, not
an estimate — which is part of why no adjustment was made.

## Results

| | |
|---|---|
| Agreement within ±10 | **3 / 20 (15%)** |
| Constant guess (75) within ±10 | **10 / 20** |
| Target | 14 / 20 — **not met** |
| Mean signed error (system − human) | −11.95 |
| Mean absolute error | 24.35 |
| Pearson correlation, all 20 | **+0.048** |
| Pearson correlation, excluding 3 single-condition postings | +0.386 |
| Evidence pairs verified | **180 / 180** |

| | Mean | Min | Max | SD |
|---|---|---|---|---|
| Human | 67.35 | 20 | 95 | 23.25 |
| System | 55.40 | 31 | 74 | 10.86 |

Two things stand out before any interpretation. The system's scores are **less than half as
spread out** as the human's (SD 10.86 against 23.25) and sit about 12 points lower. And the
correlation is essentially zero: the system is not a biased version of the human ranking,
it is ranking something else.

Evidence verification held completely: 180 of 180 pairs across all three versions quoted
text that really appears in the posting and the résumé.

## Analysis: the two numbers measure different things

The owner's 20 scores are **priority** — how much he wants to spend an application on this
posting. The system's score is **résumé fit**. The reasons he wrote at the time say so
directly, and one of them says it in as many words:

> **ust-08** (human 80, system 62): *"not that familiar with the company, so the priority is
> not that high, but the job fits"*

Here the owner records fit and priority as two different judgements in one sentence, and the
number he wrote down is the priority one.

Grouping the 17 disagreements by the reason he gave. The groups overlap — several postings
carry two of these — so the counts below describe tags, not buckets.

**Hard conditions (3 postings, and the only three where the system scored higher).**
A single disqualifying fact drove the human score to the floor while the system, correctly,
rated the fit of the work itself.

- **cnp-01** (20 → 74, +54): *"this is for mba only"*
- **usf-06** (30 → 62, +32): *"this is an internship program, but in us and fits my current skill"*
- **cnc-01** (20 → 44, +24): *"this is an intern not a full time"*

These are not scoring failures. They are rule failures: a posting that excludes the
candidate should be flagged by `redflags.py`, not scored low.

**AI PM interest (6 postings).** The reason prioritises by whether the role is AI product
management, which the rubric has no dimension for.

- **usf-08** (75 → 42): *"fits my consulting track, but not that prioritized as aipm"*
- **cnp-09** (85 → 54): *"fits product manager with innovation, and include AI stuff, in shanghai"*
- **cnp-05** (95 → 68): *"fits my experience in ops and include ai product,also with shanghai workspace"*
- **cnp-14** (92 → 65): *"fits ai product manager and include shanghai"*
- **cnp-16** (85 → 58): *"city not specified, but JD fits my aipm role"*
- **ust-01** (70 → 58): *"fits my current preparation in product manager"*

**Location (4 postings).** Shanghai raises the human score; the rubric is forbidden from
reading location at all (D-010 §5).

- **cnc-05** (80 → 41, −39): *"workplace is shanghai, and my major and skill fits"*
- **cnp-05**, **cnp-14**, **cnp-16** as above, each naming the city

**Company (4 postings).** Prestige and familiarity, which appear nowhere in a résumé-to-
posting comparison.

- **ust-04** (90 → 58): *"nice working place, pm work, google as dream company"*
- **cnc-06** (65 → 42): *"citi is good, but not familiar with marketing work"*
- **cnc-04** (50 → 31): *"not that into the company, and the major is not fitting"*
- **ust-08** (80 → 62): quoted above

**Salary and odds (1 posting).**

- **ust-06** (85 → 51): *"high salary, ai pm work, but low probability to get the job according to jd"*

**Plain fit misses (2 postings).** These are the only disagreements the scorer can fairly be
blamed for.

- **usf-05** (85 → 55, −30): *"fits my former experience in doing SPA in TikTok"* — the
  owner saw a direct match to prior work and the scorer did not find it. This is the clearest
  single case where the rubric underrated genuine fit.
- **usf-01** (50 → 61, +11): *"my major and degree fits, probably too quantitative for my
  current ability"* — a self-assessment of difficulty the scorer has no way to see.

So of 17 disagreements, **15 are explained by something the scorer is not allowed to or not
designed to read**, and 2 are fit judgements where it was wrong.

## Why no adjustment was made

D-010 §8 permits at most one adjustment and permits zero. Zero was chosen.

**Re-weighting would chase the wrong signal.** Correlation of each dimension with the human
score, over the recommended version:

| Dimension | Weight | r with human score |
|---|---|---|
| domain_fit | 40 | −0.057 |
| skills_overlap | 35 | −0.097 |
| seniority_fit | 25 | **+0.483** |

The two dimensions carrying 75% of the weight have slightly *negative* correlation with the
owner's scores. The only one that tracks them is seniority fit — and it tracks them because
it partly captures the hard conditions above: an internship or an MBA-only programme shows
up as a level mismatch. Re-weighting toward seniority fit would raise the correlation by
encoding an **eligibility veto inside a fit score**, which is exactly what D-010 §5 and the
project's third non-negotiable constraint forbid. It would also be fitted on the same 20
postings it was chosen from, with nothing held out.

**A rubric v2 would have the same problem.** A `score_v2` written to reward AI PM roles,
Shanghai and well-known companies would be written *from these 20 reasons* and then
evaluated *on these 20 postings*. The number it produced would measure how well it had
memorised them.

The honest result is the one above: the target was missed, and the reason is a
specification error, not a tuning error.

## What this implies for the product

1. **Keep the match score as fit.** It does the job it was specified to do, and 180/180
   verified evidence pairs say it does it from the documents rather than from priors.
2. **Hard conditions belong to the rules.** cnp-01, cnc-01 and usf-06 are MBA-only and
   internship postings. Those are red-flag rules in `redflags.py`, which decide eligibility
   deterministically — not a low score the human has to interpret.
3. **Preferences belong elsewhere.** Location, company, salary and AI PM interest are
   ranking inputs and reject reasons, not fit. The PRD already has the mechanism: structured
   reject reasons (PD-4) feeding ranking weights (F18), and Phase 2 ranking by
   match × urgency × scarcity. Priority is a function of fit, not a replacement for it.

## Next experiment, not yet run

Collect a **new, held-out** set of hand scores that rate *résumé fit only*, with the owner
told explicitly to ignore location, company, salary and how much he wants the job, and to
score those separately as priority. Calibrate fit against the fit scores. That would test
the scorer against what it was built to do, on data it has never seen. Until that exists,
the 3 / 20 number above should be read as "these two scales disagree", not as "the scorer
is 15% accurate".

## Known limits

- **N = 20, one rater.** No inter-rater agreement is possible, and a single posting moves
  the headline by 5 points.
- **No held-out set.** Every number here is in-sample.
- **No temperature control.** `claude-sonnet-5-5` rejects a non-default temperature, so runs
  are not bit-identical and small differences between runs are not meaningful. This run was
  not repeated.
- **Verified evidence is not strong evidence.** The check confirms a quote exists in the
  source, not that it supports the claim built on it — the same gap Task 1.8 found in
  `materials_required`, where a real quote supported a value it never mentioned. 180/180
  verified means no quote was fabricated, not that every pairing was apt.
- **Segment counts are small.** The smallest segment has 4 postings; per-segment rows in the
  run report are counts, not percentages, for that reason.
