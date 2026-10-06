# 06 — Decision Log

A dated record of product decisions, including the ones that were reversed. Append new
entries at the bottom; never edit old ones. A decision log that only contains good calls is
not credible.

This file answers the interview questions "how did you choose what to build?", "what did you
decide not to build?" and "tell me about a time you changed your mind."

---

## D-001 · 2026-09-09 · Build an AI side project for AI PM applications

**Context.** Candidate's resume shows strategy and business-ops experience with no AI product
work. Every AI PM screen asks about a shipped AI product and its eval set.

**Decision.** Build a portfolio project that produces a real evaluation, a real failure mode,
and real usage — not a demo.

---

## D-002 · 2026-09-09 · First concept: cross-border seller ad-diagnostic agent

**Idea.** Sellers upload ad/product data; an LLM diagnoses unprofitable SKUs and inverted
creator deals.

**Killed.** Required synthetic data (no real users reachable quickly), and the evaluation
would only ever run against data the builder planted himself — an eval of one's own
assumptions.

---

## D-003 · 2026-09-22 · Pivot to 投投乐: job-description triage

**Why.** Real user (the owner), real data (live job descriptions), real stakes, daily use.
Key insight: extraction errors here have asymmetric cost — inventing a deadline or missing a
"no sponsorship" clause costs an opportunity; missing a skill costs nothing.

**Scope decisions made at this point** (each became an ADR):
- Rules, not the model, decide eligibility.
- Threshold-based digest, not a fixed "5 per day" quota.
- Rewrite suggestions generated only after human approval.
- No login automation or CAPTCHA bypass; such sources are manual paste.

---

## D-004 · 2026-09-28 · Project nearly cancelled: "a scheduled assistant task already does this"

**Challenge.** The owner observed that a general assistant with a scheduled prompt can already
produce a daily job summary by email. If so, the project fails the "real user need" test.

**Alternatives explored.** Two further concepts were evaluated and set aside:
- *Southeast Asia market-access compliance checker* (e.g. Indonesia's October 2026 mandatory
  halal certification). Strong need and clear eval story, but too far from the owner's daily
  life to validate with real users quickly.
- *Consumer concepts* — family anti-scam assistant for parents abroad, group bill-splitting,
  campus resale, document explainer. Promising, but each needs user research before a line
  of code, and the recruiting window is open now.

**Decision.** Continue 投投乐, with the product claim narrowed and made testable:

> The scheduled prompt is the baseline. 投投乐 must beat it on verifiability — fixed schema,
> evidence quotes mechanically checked against the source, a measured hallucination rate, and
> deterministic eligibility rules — or report honestly that it does not.

**Consequences.**
- PRD §1a added: explicit comparison against the scheduled-prompt baseline.
- Task 1.7 now scores a plain-prompt baseline on the same 50 JDs. The delta is the project's
  headline number.
- Features that only reproduce the baseline (discovery, email formatting) are built as
  cheaply as possible. Engineering time goes to verification and evaluation.

**Why this is the right call, stated plainly.** The convenience layer is commoditized; the
reliability layer is not. That is also the actual job of an AI PM on a production surface:
not "can the model do it" but "how do we know it did it correctly, every time, and what
happens when it doesn't."

---

## D-005 · 2026-09-29 · Fill the eval set's unassigned 10 slots

**Context.** `05_EVAL_SPEC.md` §3 targets 50 job descriptions, but the four primary segments
sum to 40 (15 + 10 + 10 + 5). The "no stated deadline" and "bilingual" segments overlap the
others, so 10 slots had no assigned segment.

**Options.** (a) Shrink the set to 40. (b) Leave the 10 unassigned and fill ad hoc.
(c) Assign them to the segments closest to the owner's real applications.

**Decision.** (c): +5 China platform / e-commerce (primary target market) and +5 US tech
(AI PM roles). New composition: China platform 20, China campus 10, US consulting/finance
10, US tech 10. The ≥5 no-deadline and ≥5 bilingual guarantees are unchanged.

**Consequences.** The eval weights the markets the owner is actually applying to. The set
still skews toward China platform, which is stated as a limit in `05_EVAL_SPEC.md` §7.

---

## D-006 · 2026-09-29 · Report the scoring tier at Task 1.9, not 1.7

**Context.** Task 1.7's acceptance asks for "all four tiers" for both systems, but the fourth
tier (match-score agreement) depends on match scoring, which is built in Task 1.9.

**Decision.** Task 1.7 reports the three extraction tiers (critical, important, reference)
for both the plain-prompt baseline and the pipeline. The scoring tier is reported when
Task 1.9 lands, and the README shows all four at M1.

**Consequences.** Task 1.7 acceptance amended. No change to targets or to what M1 claims.

---

## D-007 · 2026-09-29 · Pull the M1 target forward to 2026-10-04

**Context.** The ByteDance TikTok Shop AI PM window opens 2026-10-06. The owner wants M1
done, and the resume bullet written from real numbers, before that window opens.

**Options.** (a) Keep 10-08 and apply late in the window. (b) Target 10-04 with a
pre-agreed cut and keep 10-08 as the fallback.

**Decision.** (b). M1 target 2026-10-04. Pre-agreed first cut: Task 1.10 (rewrite
suggestions, P1) moves to after M1 if the schedule slips; ADR-007 is still written. The
evaluation chain (1.4, 1.6, 1.7, 1.8) is never cut. If M1 is not done by 10-04, the
original 10-08 date is the fallback, and the application goes in no later than 10-11.

**Consequences.** ~40 hours in 6 days, about 6–7 hours a day. Any task over 2× its
estimate triggers a re-plan, not longer nights.

---

## D-008 · 2026-10-01 · Model-drafted labels for the eval set

**Context.** `05_EVAL_SPEC.md` §3 assumes hand labeling (6–8 min per posting). To meet the
M1 target, the owner had a model from a different family than the extractor (GPT 6 Sol,
vs. Claude Haiku) draft labels from the raw text, following the conventions in
`data/eval/README.md`.

**Risk.** A drafting model shares the extractor's failure modes (inferring years, reading
work-authorization lines as sponsorship policy). Its errors, if accepted, would be scored
as correct and understate the critical-field hallucination rate, the project's headline
metric.

**Decision.** Model drafting with these guardrails:
1. Blind check: the owner hand-labeled 5 cases (one per segment plus one Chinese posting)
   before seeing model output. Agreement was 22/25 critical fields; all 3 disagreements
   were owner errors. The stop threshold (3+ disagreements) counts disagreements where the
   model was wrong; this was clarified after the check (0 model errors, 3 owner errors).
2. A drafting model from a different family than the extractor.
3. Ambiguous fields resolved by written conventions (13 flagged → 5 remain; 12 fields
   changed).
4. The planned field-by-field verification of every critical field was not done; the
   owner's review of the 45 drafted cases was a quick read-through with no further
   changes. In its place, Task 1.7 checks every extractor/label disagreement on a critical
   field against the raw text before counting it, and any label errors found are fixed and
   reported.

Priority Scores (`human_scores.csv`) are the owner's alone.

---

## D-009 · 2026-10-01 · Task 1.8 stopping rule

**Context.** Task 1.8's acceptance asks for all four extraction targets (critical
hallucination 0%, critical accuracy ≥95%, important accuracy ≥90%, reference recall ≥80%)
plus at least 3 logged iterations. The v1 pipeline (run 2026-10-01T1940) is far from all
four. The M1 target is 2026-10-04 and the ByteDance application window opens 2026-10-06.
Iterating until every target is met has no bounded cost.

**Options.** (a) Iterate until all targets are met. (b) Iterate under a stopping rule
decided before the first new run, and report unmet targets as results.

**Decision.** (b). Task 1.8 stops at the first of: all four targets met; 5 logged
versions after v1 (v2–v6); two consecutive versions that don't improve critical
hallucination; or end of day 2026-10-03. At least 3 versions are run regardless. The
shipped prompt is the version with the lowest critical hallucination whose critical
false-negative rate is ≤10%; if none qualifies, the lowest hallucination overall, with
the FN rate stated next to it. The shipped version is re-run once to check that its
numbers are stable. Changes are limited to general field definitions and rules: no eval
text, company names or dates go into prompts, and few-shot examples are written fresh,
not taken from the eval set.

**Consequences.** Task 1.8 acceptance becomes "≥3 logged versions with deltas, each
target reported as met or not met". Unmet targets are listed in the README as known
limits. Checkpoint C (v0.0.4) is tagged when the stopping rule fires. There is no
held-out set, so tuning on the eval set can overstate performance on new postings; the
README says so.

**Amendment (2026-10-02).** Stopped after v4, before any stop condition fired.
v4 (extract_v3 + materials support check) reached 6/249 critical hallucination with
FN 5/67. The remaining errors (3 misfiled graduation windows, 3 fabricated values)
suggested a further prompt change would move 1–2 fields, within observed run-to-run
noise, while M1 (Tasks 1.9, 1.11, 1.12) is due 2026-10-04. v4 ships under the ship
rule and is re-run once for stability as planned.

---

## D-010 · 2026-10-02 · Match scoring design and calibration rule

**Context.** Task 1.9 needs a 0–100 match score with 3 evidence pairs, 2 gaps and a
recommended resume version, calibrated against the owner's own scores. The plan named 13
tracker Priority Scores; on inspection (2026-10-02) the tracker holds 32 scores, all
assigned by an AI during an earlier job search, for postings outside this project. They are
not a human baseline and are not used. The owner's real scores are the 20 given by hand
during Task 1.6, before any system scoring. The target is ≥70% within ±10, or a written
analysis. Weights can be recomputed offline, so without a rule decided in advance it is
easy to tune until 20 points agree.

**Decision.**
1. *Scoring.* One model call per (posting, resume version). The model rates three
   dimensions, each 0–10 with a one-line reason: domain fit, skills overlap,
   seniority fit (level and experience, not visa or graduation rules). The model never
   outputs the total. Code computes total = round(10 × Σ wᵢ·sᵢ / Σ wᵢ) with weights from
   config (domain 40, skills 35, seniority 25, per tech spec §5).
2. *Recommended version.* Code picks the version with the highest total (ties by the order
   ai_product, strategy_bizops, consulting). The posting's score is that version's score.
3. *Evidence.* Each evidence pair quotes the posting and the resume verbatim; code checks
   both sides with the same normalization as the extraction verifier. Pairs that fail are
   dropped from what is shown and counted. Gaps (exactly 2) are free text.
4. *Inputs.* The scorer reads the raw posting text and one resume, not the Extraction
   (tech spec §5 amended): evidence must quote the posting, and one dependency fewer.
5. *Eligibility.* The score never excludes a job. HARD red flags stay separate (rules decide
   eligibility).
6. *Model.* SCORE_MODEL in config = claude-sonnet-5-5 (larger model for scoring, PRD
   risk table). No temperature is sent (the model rejects a non-default value) and
   thinking stays at the model default; both settings are recorded in each run's
   meta.json. Runs are therefore not bit-identical, which the optional repeat run
   measures.
7. *Calibration.* The 20 Task 1.6 hand scores (`data/eval/human_scores.csv`). Agreement =
   |system − human| ≤ 10, reported as N / D, with mean signed error (system − human).
   *Floor:* the report also shows the agreement of a constant guess (the median human
   score); the system is credited only with agreement above it. Plan acceptance amended:
   "13 tracker Priority Scores" becomes these 20 hand scores. No held-out set (owner's
   choice, to save time before the ByteDance window).
8. *Adjustment rule.* Human scores are never edited after system scores are seen, and no
   posting is dropped for disagreeing. After the first full run, at most **one** adjustment
   (weights offline, or a rubric change as score_v2 with a re-run), chosen by reading the
   20 disagreements, with its hypothesis committed before it is applied. Before and after
   are both reported, on the same 20, and the report says so. No grid
   search over weights. After that one adjustment, stop and report, whatever the number.
9. *Privacy.* Real resumes and any output that quotes them stay in `data/private/`. The repo
   gets redacted sample resumes, numbers, and per-case numbers for the eval postings only.

**Consequences.** One run of 3 × 20 calls, plus at most one re-run. Any gain from the
adjustment is measured on the postings it was chosen from, so it is an upper bound. The
AI-assigned tracker scores stay out of the repo and out of every metric; the tracker file is
kept only for Task 1.12's format.

2026-10-03: first run 3/20 vs floor 10/20; no adjustment made, see docs/eval/scoring.md.

## D-011 · 2026-10-06 · Tracker export mapping

**Context.** Task 1.12 writes into the owner's existing 18-column tracker. Which column
each stored field goes to is a product decision, not an implementation detail: the file is
his, and a value in the wrong column is worse than no value.

**Decision.**
1. *Nine columns are filled by the system*: Company, Title, Link, Geography, Deadline,
   Candidate Fit, Main Skills Required, Recommended Resume, Last Verified. Status is a
   constant. Notes is written only when a job has red flags.
2. *Fit is not priority.* The match score goes to **Candidate Fit**. **Priority Score stays
   blank**, always. D-010 measured the two as different scales (3 / 20 agreement); writing
   a fit number into a priority column would assert an equivalence the data denies.
3. *Status is translated, not copied.* `JobStatus` and the tracker's dropdown are different
   vocabularies. Every exported job gets **"To Apply"** — the tracker's words for "decided
   yes, not yet applied" — which is also a member of the column's own dropdown, asserted in
   a test that reads the list out of the file.
4. *Market is deferred.* The market is an argument to the red-flag rules and is never
   persisted, so at export time it is unrecoverable. The column is left blank; no schema
   change in M1. Listed under README known limits.
5. *Six columns are the owner's* and are always blank: Application Date, Interview Stage,
   Interviewer, Next Action, Urgency, Market. The flags go in Notes, so Urgency stays his.
6. *Approved only*, enforced in code. Decisions are append-only, so the latest one per job
   decides. A job named in `--jobs` that is not approved raises, as does one with no
   extraction or no score for the active profile — a blank fit column would be
   indistinguishable from a real one.
7. *Verbatim.* Deadline is written exactly as extracted, with no date parsing; an unstated
   field writes "Not stated", for all five critical and all five important fields.
   Last Verified is our own timestamp, converted to America/New_York before the date is
   taken.
8. *Never writes in place.* The export reads the owner's file and writes a new one.

**Consequences.** The fixture `tests/fixtures/tracker_template.xlsx` carries the owner's
header row, styling, widths, dropdowns and conditional formatting with fabricated data
rows, and the round-trip test compares against it. Two format notes from building it: new
rows copy the base row's font, border, alignment and number format but never its fill,
because the real tracker's first data row carries a one-off highlight that would otherwise
repeat forever; and the worksheet-level autoFilter was moved onto the table, because the
two covered the same range, which is invalid OOXML and made Excel offer to repair the
file. Nothing should restore it.

---

## Template for new entries

```markdown
## D-00X · YYYY-MM-DD · <one-line decision>

**Context.** What prompted this.
**Options.** What was considered.
**Decision.** What was chosen.
**Consequences.** What changes in the PRD, plan, or code. What we now accept as a cost.
```
