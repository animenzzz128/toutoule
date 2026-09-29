# 01 — Product Requirements Document

**Product:** 投投乐 (TouTouLe)
**Version:** 1.1
**Date:** 2026-09-28
**Author:** Jiaqi Yao

---

## 1. Problem statement

A graduate applying across two markets (Greater China and the US) in a compressed
recruiting window faces a triage problem, not a writing problem. For every posting, the
same questions must be answered before anything else happens:

1. **Am I eligible at all?** Graduation window, visa sponsorship, degree type.
2. **Is this worth a slot?** Some employers cap applications per candidate — ByteDance
   permits two, with only one progressing at a time; Goldman Sachs caps business/location
   combinations at four. A slot spent badly cannot be recovered.
3. **When does it close?** Deadlines are inconsistently stated, often absent, and frequently
   the difference between an application and a missed opportunity.
4. **Which resume version?** Consulting, Strategy/BizOps, or AI Product.
5. **What do I actually have to submit?** Cover letter merged into one file, transcript,
   anonymized CV — requirements that vary per employer and are easy to miss.

Answering these manually takes 15–20 minutes per posting and is error-prone in exactly the
places where errors are most expensive. General-purpose chat assistants can answer these
questions, but offer no guarantee against fabrication, no fixed output shape, no memory
across postings, and no integration with the tracker where decisions actually live.

## 1a. Why not just a scheduled assistant task?

This is the first question an interviewer will ask, and it was a real reason the project was
nearly cancelled (see `06_DECISION_LOG.md`). A general assistant with a scheduled prompt
("every morning, find new jobs matching my resume and email me a summary") covers the
*convenience* layer of this product. It is a fair baseline, and the product must beat it on
things the baseline cannot provide, or it should not exist.

| Capability | Scheduled assistant prompt | 投投乐 |
|---|---|---|
| Daily job discovery + email summary | Yes | Yes |
| Fixed output schema every run | No — format drifts between runs | Yes — Pydantic-validated |
| Evidence quote for every critical field | Only if the model chooses to | Mandatory |
| **Mechanical check that quotes exist in the source** | No | **Yes — post-hoc verbatim verification** |
| Measured hallucination rate on a labeled set | No — unmeasured | Yes — 50-JD tiered eval |
| Deterministic eligibility rules, auditable and tested | No — model judgment | Yes |
| Memory of what was already seen, approved, rejected | Weak / ad hoc | Yes — database with job lifecycle |
| Structured feedback loop improving ranking | No | Yes — reject reasons |
| Writes into the owner's existing tracker format | No | Yes |
| Cost per job measured; unchanged pages skipped | No | Yes |

**Positioning in one sentence:** a scheduled prompt gives you a summary you have to trust;
投投乐 gives you a decision record you can verify, with a measured error rate on the fields
where an error costs an opportunity.

**Implication for scope.** Anything that only reproduces the left column (discovery, a
pleasant email) is table stakes and should be built as cheaply as possible. Engineering time
belongs in the rows where the right column differs. This is why the evaluation chain
(Tasks 1.4, 1.6–1.8) can never be cut, while Tier 2 page watching can.

**Measured comparison (required at M1).** Run the same 50-JD eval set through a
plain-prompt baseline — same model, asked in natural language to extract the same fields —
and report both. The delta on critical-field hallucination rate is the headline number of
this project. If there is no meaningful delta, report that honestly and narrow the
product's claim accordingly.

## 2. Users

**Primary (Phase 1–2):** The owner. Single user, real data, daily use during an active
recruiting cycle. This is deliberate — dogfooding produces real usage metrics, which a
synthetic demo cannot.

**Secondary (Phase 3):** Fellow graduate students running similar multi-market searches.
Roughly 10–20 testers, recruited from the owner's program.

**Explicit non-user:** Recruiters, employers, or anyone on the hiring side. This is a
candidate-side tool only.

## 3. Goals and success metrics

### North star
**Number of high-fit applications submitted per week.** Not jobs processed, not time
saved — applications actually submitted to roles worth applying to.

### Guardrail metrics (must be zero)
| Metric | Target |
|---|---|
| High-fit roles missed because a deadline passed unnoticed | 0 |
| Scarce application slots spent on roles that were ineligible | 0 |
| Fabricated values in critical fields | 0 |

### Process metrics
| Metric | Baseline | Target |
|---|---|---|
| Critical-field hallucination rate (eval set) | measure at M1 | 0% |
| Critical-field accuracy (eval set) | measure at M1 | ≥ 95% |
| Important-field accuracy (eval set) | measure at M1 | ≥ 90% |
| Reference-field recall (eval set) | measure at M1 | ≥ 80% |
| Match-score agreement with owner's manual rating | measure at M1 | ≥ 70% within ±10 points |
| Digest approval rate | measure week 1 of M2 | rising trend over 3 weeks |
| Time per job description | manual baseline, timed on 5 postings | ≤ 3 minutes |
| Source health (sources returning content) | — | ≥ 90% of enabled sources |

The approval-rate *trend* matters more than its level. A rising approval rate is evidence
that the reject-reason feedback loop is working; a flat one means the ranking is not
learning and the design needs revisiting.

## 4. Scope

### Phase 1 — Core engine (M1)

| # | Requirement | Priority |
|---|---|---|
| F1 | Accept a job description as pasted text, with company and URL | P0 |
| F2 | Extract structured fields, each with a verbatim evidence quote from the source | P0 |
| F3 | Output `Not stated` — never a guess — for any field the source does not contain | P0 |
| F4 | Apply deterministic red-flag rules for hard ineligibility, scarce slots, and urgency | P0 |
| F5 | Produce a 0–100 match score against a selected resume version, with 3 supporting evidence pairs and 2 stated gaps | P0 |
| F6 | Recommend a resume version | P0 |
| F7 | Persist everything to a local database | P0 |
| F8 | Export to the owner's existing 18-column tracker spreadsheet, format preserved | P0 |
| F9 | Generate 3 targeted resume-bullet rewrite suggestions — **only for roles the owner has approved** | P1 |
| F10 | Streamlit interface for paste, review, approve/reject | P0 |

### Phase 2 — Automation (M2)

| # | Requirement | Priority |
|---|---|---|
| F11 | Tier 1 source adapters: public job-board APIs (Greenhouse, Lever) | P0 |
| F12 | Tier 2 source adapters: daily fetch of ~30 career pages with content-hash change detection; only changed content is sent to the LLM | P0 |
| F13 | Deduplication: same role across multiple sources counted once; roles already in the tracker skipped | P0 |
| F14 | Ranking and selection: filter hard-ineligible, rank by match × urgency × scarcity, return **at most** 5 above a configurable threshold | P0 |
| F15 | Scheduled daily run delivering an email digest by 08:00 America/New_York | P0 |
| F16 | Approve / reject from the digest, with one-click structured reject reasons | P0 |
| F17 | Source health monitoring surfaced in the digest when a source goes stale | P1 |

### Phase 3 — Learning and expansion (M3)

| # | Requirement | Priority |
|---|---|---|
| F18 | Use accumulated approve/reject signal to adjust ranking weights | P1 |
| F19 | Search-based discovery of employers not yet in the source list | P2 |
| F20 | Multi-user support with isolated profiles | P2 |
| F21 | External user pilot, 10–20 testers | P1 |

### Explicit non-goals

Stated here because deliberately excluded scope is itself a product artifact.

| Not building | Why |
|---|---|
| Automatic application submission | The human decides. Removing approval removes the product's core safety property. |
| Cover-letter generation | Crowded, low-differentiation, and the owner's cover letters need to be genuinely his. |
| Full resume rewriting | Would drift the product into the saturated "resume optimizer" category. F9 is deliberately capped at 3 bullet suggestions. |
| Scraping sources behind login or CAPTCHA | Compliance boundary. Demoted to manual entry (F1 covers this permanently). |
| Interview preparation features | Different problem, different product. |
| Mobile app | Email plus a mobile-responsive web page is sufficient. |
| A fixed "5 jobs per day" quota | **Deliberately rejected.** A fixed count forces low-quality recommendations once the source pool is exhausted, producing notification fatigue. The system recommends *at most* 5 above a quality threshold, and sends "no new high-fit roles today" when appropriate. |

## 5. Key product decisions

Each of these should be recorded as an ADR in `docs/adr/` and each is interview material.

**PD-1 — Asymmetric error cost drives the schema.**
Fields are tiered (critical / important / reference) and evaluated with different metrics
and thresholds. The schema forces an explicit `stated: false` rather than allowing a null
that could be confused with an extracted empty value.

**PD-2 — Rules decide eligibility; the LLM only reads.**
The LLM extracts and cites. Deterministic rules then decide hard ineligibility, scarcity,
and urgency. A language model's confidence is not an acceptable basis for discarding an
opportunity, and rules are auditable and testable.

**PD-3 — Expensive computation happens only after a human signal.**
Rewrite suggestions (F9) are the most token-expensive operation in the system. Generating
them for every discovered posting would be costly and almost entirely wasted. They are
generated only after approval — roughly an order of magnitude fewer calls, and every one
of them useful.

**PD-4 — Reject reasons are training data, not UI politeness.**
Every rejection captures a structured reason (no sponsorship / wrong location / wrong
function / already applied / not interested). This is the feedback signal for F18 and the
source of the approval-rate trend metric.

**PD-5 — Threshold, not quota.**
See non-goals. The system may send two recommendations, or none.

**PD-6 — Coverage will be incomplete, and this is documented.**
In the China market, campus postings frequently appear first on WeChat Official Accounts,
which cannot be accessed within the compliance boundary. Tier 3 (manual paste) exists
permanently for this reason. The product claims *high-value* coverage, never *complete*
coverage.

## 6. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Tier 2 pages change structure and break silently | Missed opportunities — a guardrail failure | Source health monitoring (F17); surface staleness in the digest rather than failing quietly |
| Build time displaces interview preparation | The project succeeds and the job search fails | Phase 1 is independently sufficient as a portfolio piece. Phase 2 is an enhancement, not a prerequisite. Hard stop on any task exceeding 2× its estimate. |
| Recruiting window closes before Phase 2 delivers value | Automation serves only ~3 weeks | Accepted. The showcase value does not expire; Phase 3 extends the product's life beyond the owner's own search. |
| LLM cost overruns | Budget | Small model for extraction and screening, large model only for the daily shortlist; prompt caching for the resume context; strict change-detection so unchanged pages cost nothing |
| Owner is a coding beginner | Slow progress, low code quality | Agent-assisted development with mandatory explanation (handoff rule 4); small tasks with explicit acceptance criteria; CI enforcing tests |

## 7. Out of scope for measurement

The project does **not** claim to improve interview or offer rates. The sample size is too
small and the confound too large. Claims are limited to triage quality, latency, and
volume.
