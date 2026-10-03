"""Paste to decision, in one place (Task 1.11; PRD F1-F7, F10).

The Streamlit app is a view: every rule it appears to enforce lives here, in code that a
test can call without a browser. Nothing in this module extracts, verifies, judges
eligibility or scores — it calls extract.py, redflags.py and score.py in that order and
saves what they return, the way the CLI already does.
"""

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NamedTuple, get_args

from anthropic import Anthropic
from pydantic import BaseModel
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


# --- What the page reads -----------------------------------------------------------------
#
# The view models below are frozen: pydantic rejects assignment to their attributes, so a
# page that renders one cannot edit the record by accident. Nothing here decides anything;
# it reads what the pipeline already stored.


class FieldView(BaseModel, frozen=True):
    """One extracted field as the page shows it: name, value, statedness and the quote."""

    name: str
    value: str | None
    stated: bool
    evidence: str | None


class FlagView(BaseModel, frozen=True):
    """One stored red flag. The message is not stored, so the page renders the rule id."""

    rule_id: str
    severity: str
    evidence: str | None


class ScoreView(BaseModel, frozen=True):
    """One resume version's score. Only verified pairs are offered as evidence (D-010 §3)."""

    resume_version: str
    score: int
    dimensions: schemas.Dimensions
    verified_pairs: list[schemas.EvidencePair]
    unverified_pairs: int
    gaps: list[str]


class DecisionView(BaseModel, frozen=True):
    """The latest decision on a job, if a human has made one."""

    action: str
    reject_reason: str | None
    decided_at: datetime


class TriageView(BaseModel, frozen=True):
    """Everything one job's page needs, and nothing it could write back."""

    job_id: int
    company: str
    title: str
    url: str
    status: str
    critical: list[FieldView]
    other: list[FieldView]
    flags: list[FlagView]
    has_hard_flag: bool
    scores: list[ScoreView]
    recommended_version: str | None
    # The profile the page asked for, not one read off a stored row: scores is empty when
    # this job has never been scored against it.
    profile: score.ProfileKind
    decision: DecisionView | None


class JobNotFound(Exception):
    """No job with that id. The message names the id that was asked for."""


def _field_views(group: BaseModel) -> list[FieldView]:
    """Every field of one extraction group, in the order the schema declares them."""
    return [
        FieldView(
            name=name,
            value=getattr(group, name).value,
            stated=getattr(group, name).stated,
            evidence=getattr(group, name).evidence,
        )
        for name in type(group).model_fields
    ]


def _latest_scores(session: Session, job_id: int, profile: score.ProfileKind) -> list[models.Score]:
    """The newest score per resume version, from this profile only.

    Never falls back to the other profile's rows. The two sets of resumes give different
    totals and quote different documents, so showing one under the other's name would put
    the real resume's words on a page labelled "sample".
    """
    rows = session.scalars(
        select(models.Score).where(models.Score.job_id == job_id).order_by(models.Score.id)
    ).all()
    newest = {  # later rows overwrite earlier ones, so the newest per version survives
        row.resume_version: row for row in rows if row.payload_json.get("profile") == profile
    }
    return list(newest.values())


def load_triage(session: Session, job_id: int, sample: bool = False) -> TriageView:
    """Read one job's triage record, as scored against the active profile. Writes nothing.

    sample selects the profile the same way run_triage does, and .profile reports which one
    was asked for. A job with no scores from that profile comes back with scores empty —
    not with the other profile's — so the page can say it has not been scored yet.

    A job whose extraction failed has no fields and no scores; it still loads, so the page
    can say so rather than crash.
    """
    job = session.get(models.Job, job_id)
    if job is None:
        raise JobNotFound(f"no job with id {job_id}")

    stored = session.scalars(
        select(models.Extraction)
        .where(models.Extraction.job_id == job_id)
        .order_by(models.Extraction.id.desc())
    ).first()
    extraction = schemas.Extraction.model_validate(stored.payload_json) if stored else None

    flags = [
        FlagView(rule_id=row.rule_id, severity=row.severity, evidence=row.evidence)
        for row in session.scalars(select(models.RedFlag).where(models.RedFlag.job_id == job_id))
    ]
    profile = active_profile_dir(sample).kind
    score_rows = _latest_scores(session, job_id, profile)
    results = [schemas.MatchResult.model_validate(row.payload_json["result"]) for row in score_rows]
    decision = session.scalars(
        select(models.Decision)
        .where(models.Decision.job_id == job_id)
        .order_by(models.Decision.id.desc())
    ).first()

    return TriageView(
        job_id=job_id,
        company=job.company,
        title=job.title,
        url=job.url,
        status=job.status,
        critical=_field_views(extraction.critical) if extraction else [],
        other=_field_views(extraction.important) if extraction else [],
        flags=flags,
        has_hard_flag=any(flag.severity == models.FlagSeverity.HARD for flag in flags),
        scores=[
            ScoreView(
                resume_version=result.resume_version,
                score=result.score,
                dimensions=result.dimensions,
                verified_pairs=[pair for pair in result.evidence_pairs if pair.verified],
                unverified_pairs=result.unverified_pairs,
                gaps=result.gaps,
            )
            for result in results
        ],
        recommended_version=results[0].recommended_version if results else None,
        profile=profile,
        decision=DecisionView(
            action=decision.action,
            reject_reason=decision.reject_reason,
            decided_at=decision.decided_at,
        )
        if decision
        else None,
    )


# --- Decisions (PRD F10, PD-4) -----------------------------------------------------------

REJECT_REASONS = get_args(schemas.RejectReason)
DECISION_ACTIONS = get_args(schemas.DecisionAction)


class DecisionRefused(Exception):
    """The decision breaks one of the rules below. Nothing was written."""


def record_decision(
    session: Session,
    job_id: int,
    action: str,
    reject_reason: str | None = None,
    confirm_hard: bool = False,
) -> int:
    """Record one human decision and return its decisions.id. Commits.

    Append-only: every call inserts a row, and no earlier row is ever updated or deleted,
    so changing one's mind leaves both decisions in the record. jobs.status follows the
    newest action; digest_id is NULL, because a job triaged in the app came from a paste
    rather than from a digest.

    The rules, all enforced here rather than in the page:
      - a rejection carries one of the five PD-4 reasons; anything else is refused;
      - an approval carries no reason;
      - approving a job with a HARD red flag needs confirm_hard=True, so discarding the
        rules is a deliberate act and not a mis-click (constraint 3);
      - an unknown job id is refused.
    Each refusal raises before anything is added to the session, so a refused decision
    writes nothing at all.
    """
    job = session.get(models.Job, job_id)
    if job is None:
        raise JobNotFound(f"no job with id {job_id}")
    if action not in DECISION_ACTIONS:
        raise DecisionRefused(f"action must be one of {DECISION_ACTIONS}, not {action!r}")
    if action == "rejected" and reject_reason not in REJECT_REASONS:
        raise DecisionRefused(
            f"a rejection needs a reason, one of {REJECT_REASONS}, not {reject_reason!r}"
        )
    if action == "approved" and reject_reason is not None:
        raise DecisionRefused(f"an approval has no reject reason, but got {reject_reason!r}")
    if action == "approved" and not confirm_hard and load_triage(session, job_id).has_hard_flag:
        raise DecisionRefused(
            f"job {job_id} has a HARD red flag; approve again with confirm_hard=True to override"
        )

    decision = models.Decision(
        job_id=job_id,
        digest_id=None,
        action=action,
        reject_reason=reject_reason,
        decided_at=models.utc_now(),
    )
    session.add(decision)
    job.status = models.JobStatus(action)
    session.commit()
    logger.info("job %s %s (%s)", job_id, action, reject_reason or "no reason needed")
    return decision.id


# --- What the app needs that is not a rule -----------------------------------------------


class JobSummary(BaseModel, frozen=True):
    """One line in the sidebar's recent list."""

    job_id: int
    company: str
    title: str
    status: str


def recent_jobs(session: Session, limit: int = 10) -> list[JobSummary]:
    """The most recently seen jobs, newest first. Keeps queries out of the app file."""
    rows = session.scalars(
        select(models.Job)
        .order_by(models.Job.last_seen_at.desc(), models.Job.id.desc())
        .limit(limit)
    )
    return [
        JobSummary(job_id=row.id, company=row.company, title=row.title, status=row.status)
        for row in rows
    ]


def build_client(settings: Settings) -> extract.ModelClient:
    """The real Anthropic client, with the key read exactly as the CLI reads it.

    This is also the seam the app's tests replace: they swap this function for one that
    returns a fake, which works because the app looks the name up on this module at call
    time rather than holding its own copy.
    """
    return Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
