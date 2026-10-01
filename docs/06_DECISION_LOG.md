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

## Template for new entries

```markdown
## D-00X · YYYY-MM-DD · <one-line decision>

**Context.** What prompted this.
**Options.** What was considered.
**Decision.** What was chosen.
**Consequences.** What changes in the PRD, plan, or code. What we now accept as a cost.
```
