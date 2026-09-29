# 投投乐 (TouTouLe) — Start Here

**An agentic job-search workflow: monitor career sources daily, extract evidence-backed
eligibility data from job descriptions, and deliver a ranked morning digest with
human-in-the-loop approval.**

| | |
|---|---|
| Owner | Jiaqi Yao (Jacky) |
| Status | Pre-development |
| Start date | 2026-09-29 |
| Target M1 | 2026-10-04 (fallback 2026-10-08, see D-007) |
| Target M2 | 2026-10-20 |
| Primary purpose | Portfolio showcase for AI Product Manager applications |
| Secondary purpose | Reduce the owner's own application triage time |

---

## 0. Read this first: what this project is really for

This project has two goals and they are **not equally weighted**.

The honest arithmetic: the owner will submit roughly 40–60 applications this recruiting
cycle. At ~15 minutes saved per job description, full automation pays back perhaps 12
hours of manual work — against 50+ hours of build time, most of which lands *after* the
peak application window has already closed.

**Therefore: when scope must be cut, cut toward what is demonstrable in an interview, not
toward what saves the owner time.** A feature that saves 20 minutes a week but produces no
metric, no design decision, and no story is a feature to drop. A feature that produces a
measurable claim ("critical-field hallucination rate: 0% across a 50-JD evaluation") stays
even if its time savings are marginal.

Every agent working on this repo should apply that test.

---

## 1. Document map

| File | What it covers | Read it when |
|---|---|---|
| `00_START_HERE.md` | This file. Orientation, handoff prompt, glossary. | Always first |
| `01_PRD.md` | Product requirements: users, problem, scope, metrics, non-goals | Before any feature work |
| `02_TECH_SPEC.md` | Architecture, data model, schemas, ranking logic, key decisions | Before writing code |
| `03_SETUP_FROM_ZERO.md` | Environment setup for a machine with nothing installed | Day 1, once |
| `04_EXECUTION_PLAN.md` | Phases → milestones → tasks → git checkpoints | Every working session |
| `05_EVAL_SPEC.md` | Evaluation design, labeling guide, metric definitions | Phase 1, Task 1.6 onward |
| `06_DECISION_LOG.md` | How the project was chosen, including the alternatives that were killed and why | Before interviews; when scope is questioned |
| `CLAUDE.md` | Repo-level standing instructions for coding agents | Copy to repo root |
| `PROJECT_INSTRUCTIONS.md` | Text to paste into a Claude Project's instructions field | Once, when creating the Project |

### Where each file goes

| Location | Files | Purpose |
|---|---|---|
| **Claude Project** (claude.ai, for planning and review) | Upload `00`–`06` and `CLAUDE.md` as project knowledge; paste `PROJECT_INSTRUCTIONS.md` into the instructions field | Thinking, PRD changes, interview prep, code review of diffs you paste in |
| **GitHub repo** (for building, with Claude Code) | `00`–`06` in `docs/`, `CLAUDE.md` at repo root | Claude Code reads `CLAUDE.md` automatically every session |

The repo is the source of truth. When a doc changes, change it in the repo via a PR, then
re-upload it to the Project. A Project holding a stale PRD will give confident advice
against requirements that no longer exist.

---

## 2. Handoff prompt (paste this into any new AI session)

> You are the engineering lead on **投投乐 (TouTouLe)**, an LLM-powered job-application
> triage system. The project owner is a coding beginner and a business-school student
> applying for AI Product Manager roles; this repository is part of his portfolio, so code
> quality, commit history, and documentation are themselves deliverables.
>
> Before writing any code, read `docs/01_PRD.md`, `docs/02_TECH_SPEC.md`, and
> `docs/04_EXECUTION_PLAN.md`. Then confirm which numbered task from the execution plan we
> are working on. Do not begin a task that is not in the plan without first proposing it as
> a plan amendment.
>
> Working rules:
> 1. One task per branch, one pull request per task. Never commit directly to `main`.
> 2. Follow Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`).
> 3. Every task has acceptance criteria in the execution plan. State explicitly whether
>    each one is met before opening the pull request.
> 4. Explain what you are doing in plain language as you go — the owner is learning, not
>    just shipping. When you introduce a new concept (a decorator, a migration, a fixture),
>    explain it in two sentences.
> 5. Never hardcode secrets. Everything sensitive goes in `.env`, which is gitignored.
> 6. Never write code that circumvents a website's access controls: no login automation, no
>    CAPTCHA solving, no ignoring `robots.txt`. Sources requiring any of these are handled
>    manually — this is a documented product decision, not a limitation to engineer around.
> 7. If a requirement in the docs appears wrong or infeasible, say so and propose an
>    alternative. Do not silently work around it.
>
> Ask me which task to start with.

---

## 3. Glossary for a first-time builder

Terms that appear throughout these docs, in plain language.

| Term | What it means here |
|---|---|
| **Repository (repo)** | The project folder, tracked by Git. Lives locally and on GitHub. |
| **Branch** | A parallel copy of the code where you work on one task without breaking `main`. |
| **`main`** | The branch that is always supposed to work. |
| **Commit** | A saved checkpoint with a message describing the change. |
| **Pull request (PR)** | A proposal to merge a branch into `main`, with a visible diff. Even solo, use them: they are your project history. |
| **Tag** | A permanent label on a commit, used here to mark milestones (`v0.1.0`). |
| **Issue** | A tracked unit of work on GitHub. One per task in the execution plan. |
| **Milestone** | A GitHub grouping of issues that together complete a phase. |
| **Schema** | The fixed shape data must take. Here, the JSON structure the LLM must return. |
| **Pydantic** | A Python library that rejects data not matching the schema. Our safety net against malformed LLM output. |
| **Structured output** | Asking the model to return JSON conforming to a schema rather than free text. |
| **Eval (evaluation set)** | Test cases with known-correct answers, used to measure whether the system works. |
| **Hallucination** | The model inventing a fact not present in the source. In this project, the single most important failure mode. |
| **Idempotent** | Safe to run twice. Running the digest job twice must not send two emails. |
| **Cron** | A schedule expression telling a server when to run a job. |
| **ADR** | Architecture Decision Record — a short note explaining why a technical choice was made. |
| **CI** | Continuous Integration — automated checks that run on every pull request. |

---

## 4. Core design principle (state this in interviews)

**Extraction errors in this domain have asymmetric cost.**

Missing a listed skill costs almost nothing. But inventing a deadline, missing a
"we are unable to sponsor" clause, or failing to flag a per-candidate application cap
costs a real opportunity — and in the case of employers who limit applications per
candidate, it wastes a scarce, non-renewable slot.

The product is therefore **not** optimized for extraction completeness. It is optimized so
that on a defined set of critical fields, the system **never fabricates**. When the source
document does not state something, the system must output `Not stated` and say so
explicitly. This principle drives the schema design, the evaluation weighting, and the
decision to keep rules (not the LLM) in charge of the final eligibility verdict.

---

## 5. Safety and compliance boundaries

These are product requirements, not suggestions. They are also interview material.

1. **Respect `robots.txt` and terms of service.** Sources that cannot be read within those
   boundaries are demoted to manual entry.
2. **No authentication bypass.** No login automation, no CAPTCHA handling, no session
   replay.
3. **Polite crawling.** One request per source per day, identifying User-Agent, exponential
   backoff on failure.
4. **Personal data stays local.** The owner's real resume, API keys, and application history
   are never committed. The public demo runs on a redacted sample resume.
5. **The human decides.** The system ranks and recommends; it never submits an application.
