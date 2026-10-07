# ADR-001: Stack minimalism

**Status:** Accepted · 2026-10-06

## Context

TouTouLe is built by one person who is learning to code, as a portfolio project for AI
Product Manager applications. Every tool in the stack is something the owner must
understand well enough to explain and defend in an interview. The product's hard problems
are extraction accuracy, evidence verification and deterministic eligibility rules
(PRD, tech spec §3–5). None of them is a UI, retrieval or orchestration problem.

Common "AI app" stacks add a frontend framework (React/Next.js), a vector database, an
orchestration library (LangChain or similar) and sometimes fine-tuning. Each carries real
learning and maintenance cost (CLAUDE.md, "Do not add").

## Decision

Use the smallest stack that meets the requirements (tech spec §1):

- **Python 3.12 + uv** for the language, interpreter and dependencies, in one tool.
- **Pydantic v2** to validate every external boundary: config, LLM output (`schemas.py`).
- **SQLAlchemy** over SQLite in Phase 1, moving to hosted Postgres in Phase 2 (ADR-002).
- **Anthropic API** called directly, with structured output (ADR-003).
- **Streamlit** for the UI, **openpyxl** for the tracker export.
- **pytest** and **ruff** for tests, lint and formatting; **GitHub Actions** for CI.

Explicitly **not** used:

| Not used | Why not |
|---|---|
| React / Next.js / any frontend framework | Streamlit gives an interactive, deployable UI from one Python file. |
| Vector database | Nothing needs semantic retrieval: each posting is processed on its own, and the resume set is a handful of versions. |
| Orchestration library (e.g. LangChain) | The LLM calls are a short, fixed pipeline. Plain function calls are easier to read, test and debug. |
| Fine-tuning | Prompting plus code-level verification (ADR-003) is what the 50-JD eval set measures; fine-tuning adds data, cost and opacity. |

## Consequences

- **Positive:** the owner can read and explain every layer. Fewer dependencies to break,
  and eval results reflect design choices, not framework behaviour.
- **Negative:** the UI is limited to what Streamlit can do. Retries, logging and prompt
  versioning are written by hand instead of coming from a framework.
- **Negative, specific and scheduled:** SQLite has no real concurrent-writer story. Once
  Phase 2 adds a scheduled job that writes alongside the running web app, two writers can
  corrupt the same file (tech spec, "Known hazards: Concurrent writers"). This is accepted
  for Phase 1, where only the Streamlit app writes, and is the reason Phase 2 opens with
  Task 2.1: migrate to hosted Postgres before any scheduled writer exists (ADR-002).
- **Revisit when:** a requirement truly needs one of the excluded tools, e.g. retrieval
  over thousands of past postings. Adding it requires a new ADR first (CLAUDE.md, "Stack").
