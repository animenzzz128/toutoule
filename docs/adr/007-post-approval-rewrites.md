# ADR-007: Post-approval-only generation of rewrite suggestions

**Status:** Accepted, not yet implemented (Task 1.10 moved after M1, D-007) · 2026-10-06

## Context

F9 generates up to 3 resume-bullet rewrite suggestions per job. It is the most
token-expensive operation planned for the system (PRD, PD-3): a large-model call against
the posting and the chosen resume, for every job the pipeline has ever seen, would spend
tokens on roles that are never applied to as readily as on ones that are.

D-007 pulled the M1 target forward to 2026-10-04 to clear the ByteDance window opening
2026-10-06, and pre-agreed that Task 1.10 (P1, rewrite suggestions) is the first thing cut
if the schedule slips, while the evaluation chain (1.4, 1.6–1.8) is never cut. M1 was not
done by 2026-10-04, so per D-007 Task 1.10 moved after M1. This ADR is written now, as
planned, even though the code is not.

## Decision

Rewrite suggestions are generated **only for a job with an approved decision**. When Task
1.10 is built, `rewrite.py` must raise if called for a job without one, enforced in code
rather than left to the caller (CLAUDE.md, non-negotiable constraint 7; PRD, PD-3), and a
test must assert that calling it for a non-approved job raises.

- **Why cost.** Approval is expected to be a small fraction of all jobs seen. Spending the
  expensive call only there, instead of on every discovered posting, is the point of
  gating it on approval — PD-3 names this as the project's most token-expensive
  operation.
- **Why human-in-the-loop.** Generating rewrites before a decision exists would spend
  tokens optimizing bullets for roles the owner may never apply to, and implicitly treats
  "discovered" as "worth rewriting for" — a judgment the rules and the human, not the
  rewrite step, are supposed to make.
- **Bounded output.** At most 3 bullet suggestions (PRD F9, non-goals: "F9 is deliberately
  capped at 3 bullet suggestions") — this is a targeted suggestion feature, not a resume
  optimizer; "Full resume rewriting" is explicitly out of scope.
- **Never auto-applied.** The suggestions are shown to the owner; nothing in the system is
  to write them into a resume file. The human decides, same as every other output
  (CLAUDE.md constraint 8).

## Consequences

- Once built with the check above, no rewrite can exist for a job the owner has not
  approved, so the project's most expensive call is never spent on a role never decided
  on.
- Enforcing this inside `rewrite.py` itself, rather than in each caller, means any future
  caller (CLI, app, Phase 2 digest) inherits the restriction without having to repeat the
  check.
- Deferred cost: Task 1.10 is unimplemented at M1. The README and M1 checklist should show
  this as a known gap, not a silent omission, with the pointer back to D-007 and this ADR.
