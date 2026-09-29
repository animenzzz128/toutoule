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

## Template for new entries

```markdown
## D-00X · YYYY-MM-DD · <one-line decision>

**Context.** What prompted this.
**Options.** What was considered.
**Decision.** What was chosen.
**Consequences.** What changes in the PRD, plan, or code. What we now accept as a cost.
```
