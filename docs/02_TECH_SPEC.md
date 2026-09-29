# 02 — Technical Specification

**Read `01_PRD.md` first.** This document translates requirements into architecture. It is
prescriptive: an agent should follow it rather than re-derive it. Where it is wrong, say so
and propose an amendment as an ADR.

---

## 1. Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 | Owner already uses Python for analysis |
| Env + packages | `uv` | Single tool that installs Python itself and manages dependencies. Avoids the pyenv/conda/venv confusion that derails beginners. |
| Validation | Pydantic v2 | Rejects malformed LLM output at the boundary |
| Database | SQLite (Phase 1) → hosted Postgres (Phase 2), via SQLAlchemy | See ADR-002 |
| LLM | Anthropic API, structured output | See ADR-003 |
| UI | Streamlit | One file gives an interactive, deployable UI. No frontend framework to learn. |
| Scheduling | GitHub Actions cron | Free, versioned, and its run history is part of the portfolio |
| Email | Transactional email API (Resend or equivalent) | Verify current free-tier limits before committing |
| Spreadsheet | openpyxl | Must preserve the owner's existing 18-column format exactly |
| Testing | pytest | — |
| Lint/format | ruff | One tool for both |

**Explicitly not used:** React/Next.js, vector databases, fine-tuning, LangChain. Each
would add learning cost without serving a requirement. Record this in ADR-001.

## 2. Repository layout

```
toutoule/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                  # lint + test on every PR
│   │   └── daily_digest.yml        # Phase 2 scheduled job
│   └── ISSUE_TEMPLATE/task.md
├── docs/
│   ├── 00_START_HERE.md ... 05_EVAL_SPEC.md
│   └── adr/                        # architecture decision records
├── src/toutoule/
│   ├── config.py                   # settings from env
│   ├── schemas.py                  # pydantic models
│   ├── db.py                       # SQLAlchemy engine + session
│   ├── models.py                   # ORM tables
│   ├── extract.py                  # LLM extraction
│   ├── redflags.py                 # deterministic rules
│   ├── score.py                    # match scoring
│   ├── rewrite.py                  # F9, post-approval only
│   ├── rank.py                     # digest selection
│   ├── export_xlsx.py
│   ├── mailer.py                   # Phase 2
│   ├── sources/
│   │   ├── base.py                 # SourceAdapter protocol
│   │   ├── greenhouse.py           # Tier 1
│   │   ├── lever.py                # Tier 1
│   │   └── page_watch.py           # Tier 2
│   └── cli.py
├── app/streamlit_app.py
├── data/
│   ├── profile/                    # resume versions (real ones gitignored)
│   ├── eval/                       # 50 JDs + labels (committed)
│   └── prompts/                    # versioned prompt templates
├── tests/
├── .env.example
├── CLAUDE.md
├── CHANGELOG.md
├── pyproject.toml
└── README.md
```

## 3. Extraction schema

The core contract. Every field carries its own evidence and an explicit statedness flag.

```python
class ExtractedField(BaseModel):
    value: str | None          # null iff stated is False
    stated: bool               # did the source actually say this?
    evidence: str | None       # verbatim quote, max ~200 chars; null iff stated is False

class CriticalFields(BaseModel):
    deadline: ExtractedField              # ISO date or explicit relative phrasing
    visa_sponsorship: ExtractedField      # "yes" | "no" | "conditional"
    graduation_window: ExtractedField     # e.g. "2026-09 to 2027-08"
    application_cap: ExtractedField       # e.g. "2 per candidate"
    materials_required: ExtractedField    # e.g. "CV + cover letter as one anonymized file"

class ImportantFields(BaseModel):
    location: ExtractedField
    work_model: ExtractedField            # onsite | hybrid | remote
    language_requirement: ExtractedField
    start_date: ExtractedField
    degree_requirement: ExtractedField

class ReferenceFields(BaseModel):
    skills: list[str]
    responsibilities: list[str]
    team_or_function: str | None

class Extraction(BaseModel):
    schema_version: str
    prompt_version: str
    company: str
    title: str
    critical: CriticalFields
    important: ImportantFields
    reference: ReferenceFields
```

**Validation rules enforced in code, not trusted to the model:**

1. `stated is False` ⟹ `value is None` and `evidence is None`.
2. `stated is True` ⟹ `evidence` is non-empty **and appears verbatim in the source text**.
   Normalize whitespace before comparing. A quote that is not found in the source is
   treated as a hallucination: the field is downgraded to `stated: False` and the incident
   is logged to `extraction_violations`.
3. Any `ValidationError` triggers exactly one retry with the error appended to the prompt.
   A second failure marks the job `extraction_failed` and surfaces it for manual entry.

Rule 2 is the mechanical guarantee behind the 0% hallucination target. It is not a prompt
instruction — it is a post-hoc check. Prompts can be ignored; code cannot.

## 4. Red-flag rules (deterministic)

Implemented in `redflags.py`. No LLM involvement.

| ID | Condition | Severity | Effect |
|---|---|---|---|
| R1 | `visa_sponsorship.value == "no"` AND market is US AND owner requires sponsorship | HARD | Excluded from digest |
| R2 | `graduation_window` stated AND 2027-05 falls outside it | HARD | Excluded from digest |
| R3 | `degree_requirement` stated AND incompatible | HARD | Excluded from digest |
| R4 | `application_cap` stated | SCARCE | Ranking bonus; banner in the UI; never auto-recommended without a visible warning |
| R5 | `deadline` within 72 hours | URGENT | Ranking bonus; digest subject line flag |
| R6 | `deadline` stated but already passed | HARD | Excluded, logged |
| R7 | Source has ≥2 consecutive fetch failures | SYSTEM | Digest health notice |

**Critical asymmetry:** `stated: False` never triggers a HARD rule. Absence of a sponsorship
clause is not evidence of non-sponsorship. Unknown means "surface it and let the human
decide", never "discard".

## 5. Match scoring

`score.py`. Inputs: an `Extraction`, plus one resume version from `data/profile/`.

Output:
```python
class MatchResult(BaseModel):
    resume_version: Literal["consulting", "strategy_bizops", "ai_product"]
    score: int                       # 0-100
    evidence_pairs: list[EvidencePair]   # exactly 3: requirement -> resume experience
    gaps: list[str]                      # exactly 2
    recommended_version: str
```

Scored against three dimensions, weights configurable in `config.py`:
domain fit 40, skills overlap 35, seniority/eligibility fit 25.

Calibration is defined in `05_EVAL_SPEC.md` §4. The owner's existing tracker already
contains 13 manually assigned Priority Scores — these are the initial human baseline.

## 6. Ranking and digest selection (Phase 2)

`rank.py`.

```
candidates = jobs where:
    no HARD red flag
    AND no prior decision (not already approved/rejected/applied)
    AND match.score >= MATCH_THRESHOLD       # default 65, configurable

priority = 0.50 * (score / 100)
         + 0.30 * urgency_factor
         + 0.20 * scarcity_factor

urgency_factor:   deadline within 72h -> 1.0
                  within 7d  -> 0.7
                  within 14d -> 0.4
                  stated, further out -> 0.2
                  not stated -> 0.3      # unknown is mildly urgent, not ignorable

scarcity_factor:  application_cap stated -> 1.0, else 0.0

digest = top N by priority, where N = min(5, len(candidates))
if len(digest) == 0: send a "no new high-fit roles today" email
```

`MATCH_THRESHOLD` is the primary tuning lever. Start at 65, adjust based on approval rate.
Every change is logged to `config_changes` so the approval-rate trend can be interpreted
against it — a rising approval rate caused by a raised threshold is not the same finding as
one caused by better ranking.

## 7. Data model

SQLAlchemy ORM. Phase 1 SQLite, Phase 2 Postgres; use only portable types so migration is a
connection-string change.

```
sources(id, name, tier, url, adapter, enabled, last_ok_at, consecutive_failures)
jobs(id, source_id, external_id, company, title, url, raw_text, content_hash,
     first_seen_at, last_seen_at, status)
extractions(id, job_id, prompt_version, schema_version, payload_json, model,
            input_tokens, output_tokens, created_at)
extraction_violations(id, job_id, field_path, reason, created_at)
scores(id, job_id, resume_version, score, payload_json, created_at)
red_flags(id, job_id, rule_id, severity, evidence)
digests(id, sent_at, job_ids_json, delivered, error)
decisions(id, job_id, digest_id, action, reject_reason, decided_at)
rewrites(id, job_id, payload_json, created_at)
eval_runs(id, prompt_version, metrics_json, created_at)
config_changes(id, key, old_value, new_value, changed_at, note)
```

`jobs.status` lifecycle:
`discovered → extracted → scored → queued → digested → approved | rejected | snoozed → applied`

`content_hash` is a SHA-256 of normalized page text. **Unchanged hash ⟹ no LLM call.** This
is the single most important cost control in the system.

## 8. Source tiers

| Tier | Sources | Method | Expected stability |
|---|---|---|---|
| 1 | Employers on Greenhouse / Lever (the tracker already contains at least one Lever posting) | Public job-board JSON endpoints | High |
| 2 | ~30 career pages from the tracker | Daily fetch, normalize, hash, diff | Medium — expect breakage |
| 3 | Login-gated, CAPTCHA-protected, or WeChat-only | Manual paste via F1 | N/A |

`SourceAdapter` protocol:
```python
class SourceAdapter(Protocol):
    name: str
    tier: int
    def fetch(self) -> list[RawPosting]: ...
```
Every adapter: 1 request/day, identifying User-Agent, respects `robots.txt`, exponential
backoff, and raises `SourceUnavailable` rather than returning partial results. Partial
results are worse than none — they look like "no new jobs".

## 9. Scheduling and delivery (Phase 2)

**Daylight saving is a real bug here, not a detail.** 07:30 America/New_York is 11:30 UTC
during EDT and 12:30 UTC during EST, and the switch falls on 2026-11-01 — inside the
project's life.

```yaml
on:
  schedule:
    - cron: "30 11 * * *"   # 07:30 EDT
    - cron: "30 12 * * *"   # 07:30 EST
```
The job's first action is to check the current hour in `America/New_York` and exit
immediately unless it is 7. Both crons fire year-round; only the correct one proceeds.

**Idempotency:** before sending, check whether a digest already exists for today's local
date. GitHub Actions cron can fire late or, rarely, twice.

**Email:** plain HTML, no external CSS. Each entry shows company, title, score, deadline,
red-flag banners, the three evidence pairs, and two links — Approve and Reject — pointing
to the Streamlit app with `?job=<id>&action=<action>&token=<hmac>`. The HMAC is signed with
a server-side secret so a leaked link cannot be forged or replayed. Reject opens a reason
picker rather than recording immediately.

## 10. Cost control

Ordered by impact:

1. **Change detection** — unchanged pages never reach the LLM. Most days, most sources are
   unchanged.
2. **Model tiering** — a small, fast model for extraction and initial screening; the larger
   model only for scoring the daily shortlist and for post-approval rewrites (PD-3).
3. **Prompt caching** — the resume versions and the extraction instructions are stable
   context reused across every call.
4. **Truncation** — cap raw JD text at a configured character limit; job descriptions have
   long boilerplate tails that carry no extractable signal.

Log `input_tokens` and `output_tokens` on every extraction. Cost per processed job is a
reportable metric and an interview answer. Confirm current model pricing at
`https://docs.claude.com` before estimating a budget — do not rely on remembered figures.

## 11. Security

| Item | Handling |
|---|---|
| API keys | `.env` locally, GitHub Actions secrets in CI. Never in code, never in logs. |
| Real resume | `data/profile/` gitignored. A redacted sample is committed for the demo. |
| Database | Gitignored locally; Phase 2 hosted DB uses a connection string from secrets. |
| Approve links | HMAC-signed, single-use, 7-day expiry. |
| Public demo | Runs on the sample resume and sample jobs only. The owner's real application history is never publicly reachable. |

## 12. Architecture Decision Records to write

Create these in `docs/adr/` as they are implemented. Format: Context / Decision /
Consequences, under one page each.

| ADR | Title |
|---|---|
| 001 | Stack minimalism: no frontend framework, no vector DB, no orchestration library |
| 002 | SQLite locally, hosted Postgres in Phase 2 — avoiding concurrent-writer corruption between the scheduled job and the web app |
| 003 | Structured output with post-hoc verbatim-quote verification, rather than trusting prompt instructions |
| 004 | Rules, not the LLM, decide eligibility |
| 005 | Compliance boundary: manual Tier 3 instead of authentication bypass |
| 006 | Threshold-based digests rather than a fixed daily quota |
| 007 | Post-approval-only generation of rewrite suggestions |
