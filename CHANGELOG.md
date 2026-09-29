# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions
follow [Semantic Versioning](https://semver.org/).

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
