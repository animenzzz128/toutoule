"""Paste to decision, in one place (Task 1.11; PRD F1-F7, F10).

The Streamlit app is a view: every rule it appears to enforce lives here, in code that a
test can call without a browser. Nothing in this module extracts, verifies, judges
eligibility or scores — it calls extract.py, redflags.py and score.py in that order and
saves what they return, the way the CLI already does.
"""

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from toutoule import config, extract, models, redflags, schemas, score
from toutoule.config import Settings, get_settings

logger = logging.getLogger(__name__)


# --- Which resumes to score against ------------------------------------------------------


class ProfileChoice(NamedTuple):
    """The resume folder in use and its one-word name, for display and for storage."""

    directory: Path
    kind: score.ProfileKind


def active_profile_dir(force_sample: bool = False) -> ProfileChoice:
    """The real profile when it is present, otherwise the redacted sample (D-010 §9).

    The real resumes live in data/private/profile and are never committed, so a clone —
    or the deployed demo — has only the samples. force_sample=True picks the samples even
    on the owner's own machine, which is what the app's toggle sets.
    """
    if not force_sample and config.PROFILE_DIR.exists():
        return ProfileChoice(config.PROFILE_DIR, "real")
    return ProfileChoice(config.SAMPLE_PROFILE_DIR, "sample")


# --- The pipeline ------------------------------------------------------------------------


def manual_source(session: Session) -> models.Source:
    """The single 'manual' source for pasted postings (ADR-005), created on first use."""
    source = session.scalars(select(models.Source).where(models.Source.adapter == "manual")).first()
    if source is None:
        source = models.Source(name="manual", tier=3, url="", adapter="manual")
        session.add(source)
        session.commit()
    return source


def _scored_for_profile(session: Session, job_id: int, profile: score.ProfileKind) -> bool:
    """True if this job already has a score for every resume version on this profile.

    A row written before scores recorded their profile has no "profile" key, and .get()
    returns None, which matches neither kind: such a job is scored again rather than shown
    under a profile it may not have been scored against.
    """
    rows = session.scalars(select(models.Score).where(models.Score.job_id == job_id)).all()
    versions = {row.resume_version for row in rows if row.payload_json.get("profile") == profile}
    return set(config.RESUME_VERSIONS) <= versions


def _replace_red_flags(
    session: Session,
    job_id: int,
    extraction: schemas.Extraction,
    profile: redflags.OwnerProfile,
    market: redflags.Market,
    today: date,
) -> None:
    """Re-run the rules and replace this job's flags. Does not commit.

    The rules cost nothing — no model call — and their answer depends on the market and on
    today's date, so they are run on every pass. Keeping the old rows would leave a job
    showing no sponsorship flag after its market was corrected, or no passed-deadline flag
    the day after its deadline passed.
    """
    flags = redflags.evaluate(extraction, profile, market, today)
    session.execute(delete(models.RedFlag).where(models.RedFlag.job_id == job_id))
    redflags.save_red_flags(session, job_id, flags)


def run_triage(
    session: Session,
    client: extract.ModelClient,
    company: str,
    title: str,
    url: str,
    raw_text: str,
    *,
    sample: bool = False,
    market: redflags.Market = None,
    today: date | None = None,
    settings: Settings | None = None,
) -> int:
    """Extract, flag and score one pasted posting. Returns its jobs.id.

    market is an explicit input, never guessed from the location field (tech spec §4);
    None means unknown and never fires R1.

    Cost control (non-negotiable constraint 6): the content hash is the cache key. A
    posting whose text was already extracted by this prompt and model reuses the stored
    extraction, and one already scored on this profile reuses the stored scores, so the
    same paste twice makes no model call at all.

    If extraction fails validation twice, ExtractionFailed is raised and nothing partial is
    stored: no extraction, no flags, no scores. The job row itself stays, marked
    extraction_failed by extract_job, as the record of the attempt.
    """
    settings = settings or get_settings()
    today = today or datetime.now(UTC).date()
    profile = active_profile_dir(sample).kind
    content_hash = extract.hash_content(raw_text)

    cached = extract.find_cached(
        session, content_hash, extract.PROMPT_VERSION, settings.extraction_model
    )
    if cached is not None:
        logger.info("same text, prompt and model as job %s: no extraction call", cached.job_id)
        job = session.get(models.Job, cached.job_id)
        assert job is not None  # extractions.job_id is a foreign key
        extraction = schemas.Extraction.model_validate(cached.payload_json)
    else:
        job = models.Job(
            source_id=manual_source(session).id,
            company=company.strip(),
            title=title.strip(),
            url=url.strip(),
            raw_text=raw_text,
            content_hash=content_hash,
        )
        session.add(job)
        session.commit()  # the id is needed by every row written below
        extraction = extract.extract_job(session, job, client, settings.extraction_model)

    # What the human typed wins; blanks fall back to what the model read, as the CLI does.
    job.company = company.strip() or job.company or extraction.company
    job.title = title.strip() or job.title or extraction.title
    job.url = url.strip() or job.url
    job.last_seen_at = models.utc_now()

    owner = redflags.OwnerProfile.from_settings(settings)
    _replace_red_flags(session, job.id, extraction, owner, market, today)

    if _scored_for_profile(session, job.id, profile):
        logger.info(
            "job %s already scored against the %s profile: no scoring calls", job.id, profile
        )
    else:
        scored = score.score_job(
            job.raw_text, client, sample=profile == "sample", model=settings.score_model
        )
        score.save_scores(session, job, scored, profile)

    job.status = models.JobStatus.SCORED
    session.commit()
    return job.id
