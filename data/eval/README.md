# Eval set

50 hand-labeled job descriptions used to measure extraction quality (`05_EVAL_SPEC.md`).
This README documents the tooling and conventions; it does not decide label values — see
"Patterns the prompt does not define" below for the calls still open.

## How the labels were made

- **Drafted by GPT 6 Sol from raw text only**, following the conventions in this file.
- **Blind check first.** The owner hand-labeled 5 cases (cnc-01, cnp-01, cnp-11, usf-01,
  ust-01) before seeing any model output, to avoid anchoring. The model then drafted the
  same 5 cases independently. On the 5 critical fields across those 5 cases (25 total),
  the model agreed with the owner's hand labels on 22/25. All 3 disagreements were owner
  errors, not model errors — adjudicated by rereading the raw source for each.
- **13 fields across the 50 cases were flagged `ambiguous: true`** by the model. The owner
  reviewed all 13, wrote 7 general conventions covering the patterns behind them (see
  "Patterns the prompt does not define"), and applied those conventions mechanically. That
  resolved 12 of the 13 fields (2 critical, 10 important); the 13th is still open.
- **Owner review of the other 45 drafted cases was a quick read-through, not a
  field-by-field check.** It changed no further fields. These labels are
  **model-drafted, owner-reviewed — not hand-verified** the way the 5 blind-check cases
  were.
- **Mitigation for Task 1.7:** every disagreement the eval harness finds between the
  extractor and a label, on a critical field, is checked against the raw text before it
  is counted. A label error found there is fixed and reported, not silently absorbed into
  the extractor's error rate.
- **Priority scores (`human_scores.csv`) are the owner's alone** — no model involvement.

## Labeling conventions

Decided 2026-09-30, before any case was labeled. One principle covers all of them:
**copy what the posting says; never complete what it leaves out** (a year, a month, a
policy). Where `extract_v1.txt` defines a format, labels follow it exactly. Where it only
says "a short plain value", the formats below keep labels consistent across 50 cases.

### Patterns the prompt leaves open

| On the page | Label | Why |
|---|---|---|
| "2027届" / "2027 graduates", no months | `graduation_window` stated, value `2027 graduates` | The posting states a cohort, not a month range. Turning 2027届 into `2026-09 to 2027-08` would be using outside knowledge. |
| An explicit month range, e.g. "2026年9月-2027年8月毕业" | value `2026-09 to 2027-08` | Tech spec §3 example format; the format R2 parses. |
| A deadline with no year, e.g. "10月15日截止" | `deadline` stated, value `October 15` (no year) | ISO needs a year the posting doesn't give. Adding one is inference. If the model writes `2026-10-15`, the eval should count it as unsupported: that is a real finding for Task 1.8, not a labeling error. |
| "Rolling basis", "滚动招聘" | `deadline` stated, value `rolling basis` | `extract_v1.txt` line 34 keeps relative phrasing as written and uses this exact example. Such a posting does **not** count toward the ≥5 "no stated deadline" cases. |
| "Until filled", "招满即止" | `deadline` stated, value `until filled` | Same rule as rolling basis. |
| "Must be legally authorized to work in the US", nothing about sponsorship | `visa_sponsorship` `stated: false`, note `work authorization only` | It states a work-authorization requirement, not a sponsorship policy. An F-1/OPT holder can be authorized to work. |
| "…without sponsorship now or in the future" | `visa_sponsorship` `no` | That is an explicit sponsorship statement. |
| An application-form question, e.g. "Will you now or in the future require sponsorship?" | `visa_sponsorship` `stated: false`, note `question only` | A question is not a policy. |
| A location list cut off with "+ N More" | `location` = the listed cities + ` / +N more`, keeping the truncation marker, `ambiguous: false` | Copy what is shown; the posting itself declines to name the rest. |
| A multi-role posting where a field differs by role and no single statement covers the whole posting | value `varies by role`, evidence = one representative span, `ambiguous: true`, note names the split | A single quote can't honestly represent every role; the note records what the chosen span actually covers. |
| A remote role whose header names one city but eligibility is restricted to a list of states/regions | `location` = the posting's own location field as written, `ambiguous: false`, residency limit goes in `note` | The posting does state a location field; the residency restriction is separate information, not a contradiction of it. |
| "In office at least N days/week" with N < 5 | `work_model` `hybrid`, `ambiguous: false` | A role-specific in-office day count below 5 is hybrid by definition; a role-specific statement beats a company-wide policy statement. |
| "本科以上" (degree level) | `degree_requirement` value `Bachelor's or above`, `ambiguous: false` | Common usage reads 以上 as inclusive ("bachelor's and above"), not "strictly above a bachelor's." |
| An explicit deadline plus "may close before/after this date" | `deadline` = that date, `ambiguous: false`, note `may close early` | The posting gives one concrete date; the caveat is a note, not a second value. |
| Two explicit deadlines (primary + secondary) | `deadline` = the primary date, `ambiguous: true`, note names the secondary date | Both dates are real; the primary is the one the posting recommends acting on, so it is the value, not an average or a range. |
| "\<year\> Start" in a title, with no other graduation/start statement in the body | `start_date` stated from the title span, value the year, `ambiguous: false` | The title is part of the posting text; a bare year from it is a precise value, not an inferred one. |

Relative-phrasing values are written in English (`rolling basis`, `until filled`) even for
Chinese postings. The evidence keeps the original Chinese. Whether Task 1.7 should accept
the Chinese phrasing from the model as a match is a harness decision, recorded there.

### Formats for "short plain value" fields

| Field | Format | Example |
|---|---|---|
| `materials_required` | Required items only, joined with ` + `, in the posting's order. Optional items are left out. | `resume + cover letter` |
| `application_cap` | `N per candidate`, or the posting's unit if different | `2 per candidate`, `1 per season` |
| `location` | City names in English, several joined with ` / ` | `Shanghai / Beijing` |
| `language_requirement` | Short English phrase | `fluent English and Mandarin` |
| `degree_requirement` | Short English phrase, mirroring `extract_v1.txt` line 37 | `Master's or above`, `Bachelor's or above` |
| `start_date` | Same as `deadline` (ISO, `YYYY-MM`, or phrasing as written) | `2027-07`, `upon graduation` |

When a new pattern appears that this table doesn't cover, stop, decide it once, add a row
here, and re-check earlier labels that hit it.

## Sourcing rules (05_EVAL_SPEC.md §3)

1. **Label from the source document only.** Never from the owner's existing tracker —
   the tracker contains "Not stated" and "Verify on site" values that were inferred, not
   read, and importing them would contaminate the ground truth with the system's own
   assumptions.
2. **If the document does not state a field, the label is `stated: false`** — even when
   the owner personally knows the answer. The system is measured on reading, not on
   knowledge.
3. **Every `stated: true` critical field carries a verbatim quote**, copied exactly from
   the source, checked against the source by `check_eval_set()`.
4. **Dates are normalized to ISO 8601** in the label's `value`; the quote in `evidence`
   keeps the original phrasing.
5. **A genuinely ambiguous field is marked `ambiguous: true`** and excluded from scoring,
   rather than forcing a judgment call into the ground truth. Roughly 2–4 out of 50 is
   normal; more than 8 means the schema needs refining.
6. Copy the full source text into `raw/<case_id>.txt`, and record the posting's URL and
   retrieval date in `cases.csv` — postings change and disappear, and an unreproducible
   eval set is worthless six weeks later.

## Set summary

**Segment:** cn_platform 20 · cn_campus 10 · us_consulting_finance 10 · us_tech 10 (50 total)

**Language:** en 30 · zh 19 · bilingual 1

**No stated deadline:** 37 of 50

**Human scores:** 20 of 50 (`data/eval/human_scores.csv`)

**Raw text sourcing:** 10 fetched via ATS public APIs (Greenhouse/Lever, `scripts/fetch_eval_raw.py`) · 40 copied manually

**Role mix** (from `cases.csv` notes; the 5 "timing" cases carry no role tag): pm 10 ·
analyst 8 · ai_pm 8 · consulting 7 · strategy_bizops 6 · other 6

**Ambiguous fields remaining (5 of 50 cases, resolved per the conventions above where a
general rule applied — these 5 did not fit one):**

| case | field | note |
|---|---|---|
| cnc-02 | important.location | Location varies by business unit (10+ units each list their own cities); this span covers 信息科技运营中心 only. |
| cnc-03 | important.degree_requirement | Degree requirement varies by recruitment category; this span states the requirement for A01 Accounting only. |
| cnc-04 | important.degree_requirement | Development/product and IT governance require a master's; testing and operations require a bachelor's. |
| usf-09 | critical.deadline | secondary deadline 2026-10-12 |
| ust-05 | important.work_model | The role says in-person at the listed offices; the company-wide policy allows flexibility but may vary by team. |

ByteDance has 5 cases across the 50: 3 English-language postings from the overseas
TikTok careers site (`lifeattiktok.com`) and 2 Chinese-language postings from the
domestic campus site (`jobs.bytedance.com`). Kept as separate cases rather than
deduplicated, because the two sites use different templates and languages — they
exercise genuinely different extraction conditions, not the same posting twice.

## Folder layout

```
data/eval/
├── cases.csv              one row per case: case_id, segment, company, title, url,
│                           retrieved_on (YYYY-MM-DD), language, notes
├── raw/<case_id>.txt       source text, exactly as copied, UTF-8
├── labels/<case_id>.json   hand labels, validated against evalset.Label
├── human_scores.csv        case_id, score, reason — 20 rows for Task 1.9 calibration
└── README.md               this file
```

`case_id` looks like `cnp-01`, `cnc-01`, `usf-01`, `ust-01` — a two-digit number, prefixed
by segment (`cn_platform` → `cnp`, `cn_campus` → `cnc`, `us_consulting_finance` → `usf`,
`us_tech` → `ust`).

## Commands

```bash
uv run python -m toutoule.cli eval-init    # write a blank label template for every new
                                            # cases.csv row; never overwrites an existing one
uv run python -m toutoule.cli eval-check   # report every problem with the set so far, plus
                                            # composition progress against the §3 targets;
                                            # add --final once the set is complete, to turn
                                            # unmet targets into failures (exit code 1)
```

`eval-check` without `--final` never fails just because the set isn't done yet — composition
targets are shown as progress (e.g. `cn_platform: 3/20`), not errors, until `--final` is
passed.

## Value formats

Labels must use the same value format the model is instructed to produce
(`data/prompts/extract_v1.txt`), or Task 1.7's harness will count a correct label as wrong.

| Field | Format, quoted from `extract_v1.txt` |
|---|---|
| `deadline` | Line 33: "Absolute dates as ISO 8601, e.g. `2026-10-31`, or `2026-09` when only the month is given." Line 34: "Relative phrasing is kept as written, e.g. `rolling basis` or `within 2 weeks of posting`." |
| `visa_sponsorship` | Line 35: "only `yes`, `no` or `conditional` (lowercase)." |
| `graduation_window` | Line 37 generic rule only: "a short plain value" — the prompt gives no field-specific example or format for this field. |
| `application_cap` | Line 37: "a short plain value, e.g. `2 per candidate`." |
| `materials_required` | Line 37 generic rule only: "a short plain value" — no field-specific example. |
| `location` | Line 37 generic rule only: "a short plain value" — no field-specific example. |
| `work_model` | Line 36: "only `onsite`, `hybrid` or `remote` (lowercase)." |
| `language_requirement` | Line 37 generic rule only: "a short plain value" — no field-specific example. |
| `start_date` | Same as `deadline`: lines 33–34. |
| `degree_requirement` | Line 37: "a short plain value, e.g. `Master's or above`." |

## Patterns the prompt does not define

The prompt (`extract_v1.txt`) leaves these open. They are listed here, not decided — the
owner sets the convention when labeling a case that hits one:

- `"2027届"` with no months stated
- a deadline with no year
- `"rolling basis"`
- `"must be legally authorized to work in the US"` with nothing said about sponsorship
- `"until filled"`
- application questions like `"Will you require sponsorship?"`
