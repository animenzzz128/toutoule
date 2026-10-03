"""Database tables (tech spec §7), written as SQLAlchemy ORM classes.

Only portable column types are used, so the same classes work on SQLite now and on
Postgres later (Task 2.1): switching databases is a connection-string change.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class JobStatus(StrEnum):
    """Where a job is in its lifecycle. Stored in jobs.status as the plain string."""

    DISCOVERED = "discovered"
    EXTRACTED = "extracted"
    EXTRACTION_FAILED = "extraction_failed"  # two failed attempts; needs manual entry
    SCORED = "scored"
    QUEUED = "queued"
    DIGESTED = "digested"
    APPROVED = "approved"
    REJECTED = "rejected"
    SNOOZED = "snoozed"
    APPLIED = "applied"


class FlagSeverity(StrEnum):
    """Severity of a red flag (tech spec §4). Stored in red_flags.severity."""

    HARD = "HARD"
    SCARCE = "SCARCE"
    URGENT = "URGENT"
    SYSTEM = "SYSTEM"


class UTCDateTime(TypeDecorator[datetime]):
    """A timestamp that is always UTC, on every database.

    SQLite forgets time zones, so without this it would hand back 'naive' datetimes while
    Postgres hands back UTC ones. Naive datetimes are rejected on the way in, because we
    cannot know which time zone they meant.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected; use datetime.now(UTC)")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:  # SQLite: the value was stored as UTC, so label it UTC
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Parent of every table class. It collects them all in Base.metadata."""

    # Python type -> column type, for any column declared with these annotations.
    type_annotation_map = {
        datetime: UTCDateTime(),
        dict[str, Any]: JSON,
        list[int]: JSON,
    }


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    tier: Mapped[int]
    url: Mapped[str]
    adapter: Mapped[str]
    enabled: Mapped[bool] = mapped_column(default=True)
    last_ok_at: Mapped[datetime | None]
    consecutive_failures: Mapped[int] = mapped_column(default=0)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str | None]  # careers pages have no stable id
    company: Mapped[str]
    title: Mapped[str]
    url: Mapped[str]
    raw_text: Mapped[str] = mapped_column(Text)
    # Indexed: looked up on every fetch to decide whether the page changed.
    content_hash: Mapped[str] = mapped_column(index=True)
    first_seen_at: Mapped[datetime] = mapped_column(default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(default=utc_now)
    status: Mapped[str] = mapped_column(default=JobStatus.DISCOVERED)


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    prompt_version: Mapped[str]
    schema_version: Mapped[str]
    payload_json: Mapped[dict[str, Any]]
    model: Mapped[str]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class ExtractionViolation(Base):
    """A quote the model cited that is not in the source text (a hallucination)."""

    __tablename__ = "extraction_violations"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    field_path: Mapped[str]  # e.g. "critical.visa_sponsorship"
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    resume_version: Mapped[str]
    score: Mapped[int]  # 0-100, compared against MATCH_THRESHOLD
    payload_json: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class RedFlag(Base):
    __tablename__ = "red_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    rule_id: Mapped[str]  # "R1" ... "R7"
    severity: Mapped[str]  # a FlagSeverity value
    evidence: Mapped[str | None] = mapped_column(Text)


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(default=utc_now)
    job_ids_json: Mapped[list[int]]
    delivered: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    # Empty for jobs decided outside a digest, e.g. pasted in by hand.
    digest_id: Mapped[int | None] = mapped_column(ForeignKey("digests.id"))
    action: Mapped[str]  # a DecisionAction: "approved" or "rejected"
    reject_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(default=utc_now)


class Rewrite(Base):
    __tablename__ = "rewrites"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    payload_json: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_version: Mapped[str]
    metrics_json: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class ConfigChange(Base):
    __tablename__ = "config_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str]
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(default=utc_now)
    note: Mapped[str | None] = mapped_column(Text)
