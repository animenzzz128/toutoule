# CLAUDE.md

Standing instructions for coding agents working in this repository. Read before any task.

## What this is

**投投乐 (TouTouLe)** — an LLM-powered job-application triage system. Reads job
descriptions, extracts eligibility-critical fields with verbatim evidence, flags hard
blockers, scores fit against resume versions, and delivers a ranked daily digest that a
human approves before anything enters the tracker.

The owner is a coding beginner and a business student applying for AI Product Manager
roles. **This repository is part of his portfolio.** Commit history, documentation, and
decision records are deliverables, not overhead.

## Before you start

1. Read `docs/01_PRD.md`, `docs/02_TECH_SPEC.md`, `docs/04_EXECUTION_PLAN.md`.
   `docs/06_DECISION_LOG.md` explains why the project exists at all — in particular D-004,
   which defines the scheduled-prompt baseline the product must beat (PRD §1a).
2. Confirm which numbered task you are on. Do not start work outside the plan without
   proposing it as an amendment first.
3. For anything non-trivial, propose the approach and wait for confirmation before writing
   code.

## Working rules

**Git**
- One task, one branch, one PR. Never commit to `main`.
- Branch: `<type>/<issue-number>-<slug>` · Commits: Conventional Commits.
- Before opening a PR, restate each acceptance criterion and whether it is met.

**Code**
- Type hints everywhere. Pydantic at every external boundary.
- Tests for every behavior, including the failure paths. An untested error path is an
  untested system.
- `ruff check` and `ruff format` must be clean.
- No secrets in code, logs, or commits. Everything sensitive lives in `.env`.

**Teaching**
The owner is learning. When you introduce an unfamiliar concept — a decorator, an ORM
session, a fixture, a context manager — explain it in two sentences inline. Do not produce
large volumes of code the owner cannot read. If a task requires more than ~150 lines of new
code, split it.

**Pushback**
If a requirement in the docs is wrong, infeasible, or would produce bad architecture, say so
and propose an alternative. Do not silently work around it, and do not implement something
you believe is wrong because it is written down.

## Non-negotiable constraints

**1. Evidence verification is mandatory.**
Every extracted field marked `stated: true` must carry a verbatim quote that is then
verified to appear in the source text. A quote not found in the source is a hallucination:
downgrade the field to `stated: false` and log to `extraction_violations`. This check lives
in code. It is never replaced by a prompt instruction, because prompts can be ignored and
code cannot.

**2. `Not stated` is a first-class value.**
Never guess, never infer from context, never fill a plausible default. Absence of
information is information.

**3. Rules decide eligibility, not the LLM.**
The model extracts and cites. Deterministic rules in `redflags.py` decide hard ineligibility
and scarcity. A model's confidence is not grounds for discarding an opportunity.

**4. `stated: false` never triggers a HARD flag.**
Absence of a sponsorship clause is not evidence of non-sponsorship. Unknown means surface it
to the human, never discard it.

**5. Compliance boundary.**
No login automation. No CAPTCHA solving. No ignoring `robots.txt`. One request per source
per day, identifying User-Agent. Sources requiring any bypass are handled by manual paste —
a documented product decision (ADR-005), not an engineering gap to close.

**6. Cost control.**
Unchanged content hash means no LLM call — assert this in tests. Small model for extraction
and screening; large model only for the daily shortlist and post-approval rewrites. Log
input and output tokens on every call.

**7. Rewrite suggestions only after approval.**
`rewrite.py` must raise if called for a job without an approved decision. Enforced in code,
not by convention.

**8. The system never submits an application.**
It ranks and recommends. The human decides. Removing that step removes the product.

## Stack

Python 3.12 · uv · Pydantic v2 · SQLAlchemy (SQLite → Postgres) · Anthropic API ·
Streamlit · openpyxl · pytest · ruff · GitHub Actions

**Do not add:** React or any frontend framework, vector databases, fine-tuning,
orchestration libraries. Each adds learning cost without serving a requirement (ADR-001).
If you believe one is genuinely needed, propose it as an ADR first.

## Commands

```bash
uv sync                                   # install dependencies
uv run pytest                             # tests
uv run ruff check --fix && uv run ruff format
uv run streamlit run app/streamlit_app.py
uv run python -m toutoule.cli eval        # evaluation harness
uv run python -m toutoule.cli digest --dry-run
```

## Known hazards

- **Daylight saving.** 07:30 America/New_York is 11:30 UTC under EDT and 12:30 UTC under
  EST; the switch falls on 2026-11-01. Two cron entries, with a local-hour guard in the
  job. Test both regimes.
- **Concurrent writers.** The scheduled job and the web app must not both write SQLite.
  Phase 2 moves to hosted Postgres (ADR-002).
- **Tracker format.** The export must preserve the owner's existing 18-column layout
  exactly — header text, order, and styling. Compare against the reference copy in tests.
- **Silent source failure.** An adapter returning partial results is worse than one that
  fails loudly; partial results are indistinguishable from "no new jobs". Raise
  `SourceUnavailable`.

## Priority when constraints conflict

1. Correctness on critical fields (never fabricate)
2. Compliance boundaries
3. Cost control
4. The owner's comprehension
5. Feature completeness

Feature completeness is last. A smaller system the owner understands and can defend in an
interview beats a larger one he cannot.
