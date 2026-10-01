# Eval set

50 hand-labeled job descriptions used to measure extraction quality (`05_EVAL_SPEC.md`).
This README documents the tooling and conventions; it does not decide label values — see
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
