# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Task 1.9 — Match scoring (#10):** 0–100 score against three résumé versions with 3 verified evidence pairs, 2 gaps and a recommended version; the model rates three dimensions and code computes the total. Calibration against the owner's 20 hand scores returned 3 / 20 within ±10 against a constant-guess floor of 10 / 20; no adjustment was made, because the two scales measure different things — see [`docs/eval/scoring.md`](docs/eval/scoring.md) and D-010.

## [0.0.4] - 2026-10-02

Checkpoint C: evaluation harness and tuned extraction.

### Added
- **Task 1.6 — Build the eval set (#7):** 50 real job descriptions with hand-checked labels, each `stated: true` critical field carrying a verbatim quote; drafted by a model from another family and owner-reviewed, with the method and its risk recorded as D-008.
- **Task 1.7 — Eval harness and baseline run (#8):** `eval` scores both the pipeline and a plain-prompt baseline on the same 50 postings, reporting the three extraction tiers per run with every disagreement listed; adjudications and equivalences keep a verdict applying to later runs until the system's answer changes.
- **Task 1.8 — Iteration to target (#9):** four logged versions with hypotheses written before each run. Shipped v4 — `extract_v3` plus a code check that every `materials_required` item be named by its own quote — at 6–8 / 249 critical hallucination and 5–6 / 67 missed across two runs, against the plain-prompt baseline's 20 / 249. Four of the five targets are not met and are reported as results under D-009's stopping rule, not iterated away.

## [0.0.3] - 2026-09-30

Checkpoint B: extraction pipeline with evidence verification.

### Added
- **Task 1.3 — Pydantic schemas (#4):** the extraction contract, where every field says whether it was stated and quotes its evidence.
- **Task 1.4 — Extraction with evidence verification (#5):** a structured-output call with one retry; quotes not found in the posting are downgraded and logged to `extraction_violations`.
- **Task 1.5 — Red-flag rules (#6):** deterministic rules R1–R6 in `redflags.py`, where `stated: false` never excludes a job; owner profile settings; ADR-004.

## [0.0.2] - 2026-09-29

Project skeleton and data model (Checkpoint A).

### Added
- **Task 1.1 — Project scaffolding (#2):** uv project on Python 3.12, package layout per
  tech spec §2, settings loaded from `.env` with one-line errors, `check-config` command,
  CI running ruff and pytest, ADR-001 (stack minimalism).
- **Task 1.2 — Data model (#3):** SQLAlchemy models for the 11 tables in tech spec §7,
  using only portable types so the same models run on SQLite and Postgres. Timestamps are
  always UTC, and SQLite enforces foreign keys. `db.py` provides the engine, the session
  factory and a repeat-safe `init_db()`. New `init-db` command.
