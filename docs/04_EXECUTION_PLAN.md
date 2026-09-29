# 04 — Execution Plan

Phases → milestones → tasks. Each task is one GitHub issue, one branch, one pull request.

---

## Conventions

**Branch naming:** `<type>/<issue-number>-<short-slug>`
Example: `feat/12-extraction-schema`

**Commit format** (Conventional Commits):
```
<type>(<scope>): <subject>

feat:     new capability
fix:      bug fix
docs:     documentation only
test:     tests only
refactor: restructuring, no behavior change
chore:    tooling, dependencies, config
```

**Definition of Done — every task:**
1. Acceptance criteria met and explicitly confirmed, one by one
2. Tests written and passing
3. `ruff check` and `ruff format` clean
4. Documentation updated if behavior changed
5. PR opened, description references the issue, merged with squash
6. Issue closed, board card moved to Done

**Git checkpoints:** marked 🔖 below. At each one, `main` must be in a working state. These
are the points where a tag is created and a `CHANGELOG.md` entry is written.

**Estimates** are for an agent-assisted beginner and include the time to understand what was
built. If a task exceeds 2× its estimate, stop and reassess scope rather than pushing
through — that overrun is data about the plan, not a personal failing.

---

# PHASE 1 — Core Engine
**Milestone M1 · 2026-09-29 → 2026-10-08 · ~40 hours**

The deliverable that makes this a portfolio piece. Phase 1 is independently sufficient: if
the project stopped here, it would still be a credible interview showcase.

### Block A — Skeleton (Day 1)

**Task 1.1 — Project scaffolding** · `chore` · 2h
- `pyproject.toml` via `uv init`; dependencies: pydantic, sqlalchemy, anthropic, streamlit, openpyxl, pytest, ruff
- Package structure per tech spec §2
- `config.py` loading from `.env` with validation on startup
- `ci.yml`: ruff + pytest on every PR
- **Acceptance:** `uv run pytest` passes (one trivial test); CI green on the PR; missing env vars produce a clear startup error, not a traceback

**Task 1.2 — Data model and migrations** · `feat` · 3h
- ORM tables per tech spec §7
- `db.py` with engine, session factory, `init_db()`
- **Acceptance:** `init_db()` creates every table; a round-trip write/read test passes for `jobs` and `extractions`

🔖 **Checkpoint A** — tag `v0.0.2`, CHANGELOG entry "project skeleton and data model"

### Block B — Extraction (Days 2–3)

**Task 1.3 — Pydantic schemas** · `feat` · 3h
- `schemas.py` exactly per tech spec §3
- Validator enforcing `stated is False ⟹ value is None and evidence is None`
- **Acceptance:** tests cover valid payload, missing-evidence payload, and inconsistent-statedness payload; all three behave as specified

**Task 1.4 — Extraction with evidence verification** · `feat` · 6h
- Prompt template in `data/prompts/extract_v1.txt`, version-tagged
- Anthropic structured-output call
- **Post-hoc verbatim check:** every `evidence` string must appear in the normalized source
  text. Failures downgrade the field to `stated: False` and write to `extraction_violations`
- One retry on `ValidationError` with the error fed back; second failure marks
  `extraction_failed`
- Token counts logged
- **Acceptance:** a real JD extracts correctly; a synthetic JD with a fabricated quote
  injected is caught and downgraded; the retry path has a test

> This task is the technical heart of the project. Rule 2 in tech spec §3 is what makes the
> 0% hallucination claim mechanically true rather than a prompt aspiration. Do not shortcut
> it.

**Task 1.5 — Red-flag rules** · `feat` · 3h
- R1–R6 per tech spec §4, pure functions, no LLM
- **Acceptance:** every rule has a test including its negative case; a test explicitly
  confirms `stated: False` never triggers a HARD flag

🔖 **Checkpoint B** — tag `v0.0.3`, "extraction pipeline with evidence verification"

### Block C — Evaluation (Days 3–5)

**Task 1.6 — Build the eval set** · `test` · 6h
- 50 real job descriptions, source text committed to `data/eval/`
- Labels per `05_EVAL_SPEC.md` §3 — **label from the source document only**, never from
  prior tracker entries, which contain unverified assumptions
- Manual timing of 5 postings to establish the time baseline
- **Acceptance:** 50 labeled cases; the label file validates against the schema; baseline
  timing recorded in `docs/eval/baseline.md`

**Task 1.7 — Eval harness and baseline run** · `test` · 4h
- `uv run python -m toutoule.cli eval` produces a tiered metrics report
- Results written to `eval_runs` and a markdown report per run
- **Plain-prompt baseline:** same model, same 50 JDs, asked in natural language with no
  schema, no evidence requirement, no verification — i.e. what a scheduled assistant prompt
  would do. Scored with the same harness. See PRD §1a.
- **Acceptance:** numbers recorded for all four tiers for **both** the plain-prompt baseline
  and the 投投乐 pipeline; failure cases listed individually with field, expected, actual

**Task 1.8 — Iteration to target** · `fix` · 5h
- Improve prompts and rules against observed failures
- **Every version logged** to `docs/eval/iteration_log.md`: version, change made, resulting
  metrics
- **Acceptance:** critical-field hallucination 0%; critical accuracy ≥95%; important ≥90%;
  reference recall ≥80%. At least 3 logged iterations, each with its metric delta.

🔖 **Checkpoint C** — tag `v0.0.4`, "evaluation harness and tuned extraction"

> Checkpoint C is the most important moment in the project. Everything after it is product
> surface; this is the part that produces a defensible number.

### Block D — Scoring and surface (Days 6–7)

**Task 1.9 — Match scoring** · `feat` · 4h
- Three resume versions in `data/profile/` (redacted sample committed, real gitignored)
- Score, 3 evidence pairs, 2 gaps, recommended version
- **Acceptance:** calibration against the owner's 13 existing manual Priority Scores; ≥70%
  agreement within ±10 points, or a written analysis of why not and what was adjusted

**Task 1.10 — Rewrite suggestions (F9)** · `feat` · 3h
- 3 bullet suggestions, **only callable for jobs with an approved decision** — enforced in
  code, not by convention
- **Acceptance:** a test asserts that calling it for a non-approved job raises

**Task 1.11 — Streamlit app** · `feat` · 5h
- Paste JD → extract → red flags → score → approve/reject with structured reject reasons
- Evidence quotes visible next to every critical field
- **Acceptance:** full loop works end to end; a rejection writes a `decisions` row with a
  reason

**Task 1.12 — Tracker export** · `feat` · 3h
- Write to the owner's existing 18-column format, preserving header text, column order, and
  styling
- **Acceptance:** exported file opens in Excel with formatting intact; a round-trip test
  compares headers against a reference copy

🔖 **Checkpoint D** — tag `v0.1.0`

---

## 🏁 MILESTONE M1 — Core Engine
**Due 2026-10-08**

- [ ] Paste-to-decision loop works end to end
- [ ] Critical-field hallucination rate: 0% on 50 cases
- [ ] Plain-prompt baseline scored on the same 50 cases; delta reported in the README
- [ ] Iteration log with ≥3 documented versions and metric deltas
- [ ] Export preserves the tracker format
- [ ] ADRs 001, 003, 004, 007 written
- [ ] README with screenshots and metrics
- [ ] Deployed to Streamlit Community Cloud on the redacted sample profile
- [ ] Repository made public
- [ ] Tagged `v0.1.0`

**At M1 the project is resume-ready.** Write the bullet now, with the real numbers.

---

# PHASE 2 — Automation
**Milestone M2 · 2026-10-09 → 2026-10-20 · ~30 hours**

> **Scheduling note:** the ByteDance application window falls between 2026-10-06 and
> 2026-10-12, with a hard gate at 10-12. Phase 2 work stops for any day where it conflicts
> with that application or its interview preparation. Interview preparation outranks this
> project without exception.

**Task 2.1 — Database migration to hosted Postgres** · `chore` · 4h
- Provision a free-tier hosted Postgres; move the connection string to secrets
- **Acceptance:** identical test suite passes against both backends; ADR-002 written

**Task 2.2 — Source adapter interface + Tier 1** · `feat` · 5h
- `SourceAdapter` protocol; Greenhouse and Lever adapters
- **Acceptance:** real postings retrieved from at least 2 employers; `SourceUnavailable`
  raised rather than partial results returned

**Task 2.3 — Tier 2 page watching** · `feat` · 6h
- ~30 career pages; fetch, normalize, SHA-256 hash, diff
- **Unchanged hash must not trigger an LLM call** — assert this in a test
- `robots.txt` respected; 1 request/source/day; identifying User-Agent; exponential backoff
- **Acceptance:** two consecutive runs over unchanged pages produce zero LLM calls; ADR-005
  written

**Task 2.4 — Deduplication** · `feat` · 3h
- Same role across sources counted once; roles already in `decisions` skipped
- **Acceptance:** tests cover cross-source duplicates and already-decided roles

**Task 2.5 — Ranking and selection** · `feat` · 3h
- Per tech spec §6, including the empty-digest path
- **Acceptance:** a test asserts fewer than 5 are returned when fewer qualify, and that an
  empty candidate set produces the "no new roles" digest rather than a crash

**Task 2.6 — Email delivery** · `feat` · 5h
- HTML digest; HMAC-signed approve/reject links with 7-day expiry
- **Acceptance:** email renders in Gmail and on mobile; a tampered token is rejected; an
  expired token is rejected

**Task 2.7 — Scheduled run** · `feat` · 4h
- `daily_digest.yml` with both cron entries; local-hour guard; idempotency check
- **Acceptance:** a test simulates both DST regimes and asserts exactly one run proceeds;
  a second invocation on the same local date sends nothing

**Task 2.8 — Source health monitoring** · `feat` · 2h
- ≥2 consecutive failures surfaces a health notice in the digest
- **Acceptance:** a simulated failing source appears in the digest body

🔖 **Checkpoint E** — tag `v0.2.0`

## 🏁 MILESTONE M2 — Automation
**Due 2026-10-20**

- [ ] 5 consecutive days of successful scheduled digests
- [ ] Approve/reject from email works, reject reasons captured
- [ ] Zero LLM calls on unchanged sources, verified in logs
- [ ] Cost per processed job measured and recorded
- [ ] ADRs 002, 005, 006 written
- [ ] Tagged `v0.2.0`

---

# PHASE 3 — Learning and Pilot
**Milestone M3 · 2026-11-01 → 2026-11-30**

Lower intensity, after the recruiting peak. **Task 3.3 is the one that matters** — it turns
an n=1 tool into a product with external users, which changes what the project demonstrates.

**Task 3.1 — Feedback-driven ranking** · `feat` · 6h
- Adjust weights from accumulated approve/reject signal
- **Acceptance:** approval-rate trend reported against threshold changes, so the two effects
  are distinguishable

**Task 3.2 — Multi-user profiles** · `feat` · 8h

**Task 3.3 — External pilot** · 10h
- 10–20 testers from the owner's program
- **Acceptance:** ≥10 active users over 2 weeks; feedback synthesized into a prioritized
  backlog — itself a PM artifact worth showing

**Task 3.4 — Search-based discovery** · `feat` · 6h · P2

🔖 **Checkpoint F** — tag `v0.3.0`

---

## Weekly rhythm

| | |
|---|---|
| Monday | Review the board; pick the week's tasks; note anything blocked |
| Daily | One task, one branch, one PR. Do not stack unmerged branches. |
| Friday | Merge, tag if at a checkpoint, update CHANGELOG, write one paragraph of retrospective in `docs/retro/` |

The retrospective file is not ceremony. At the end of the project it is the raw material for
the interview answer to "what would you do differently", which is asked in nearly every PM
interview and which most candidates answer badly because they never wrote anything down.

---

## Scope-cut order

If time runs short, cut in this order. Decided in advance so the decision is not made under
pressure:

1. Task 3.4 — search discovery
2. Task 3.2 — multi-user
3. Task 2.8 — health monitoring
4. Task 2.3 — Tier 2 watching (Tier 1 plus manual paste still demonstrates the full concept)
5. Task 1.10 — rewrite suggestions

**Never cut:** 1.4 (evidence verification), 1.6, 1.7, 1.8 (the evaluation chain). Those four
are the project. Everything else is surface.
