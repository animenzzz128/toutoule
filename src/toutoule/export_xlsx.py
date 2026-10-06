"""Export approved jobs into the owner's existing 18-column tracker (PRD F8, D-011).

The tracker is the owner's file and the system is a guest in it. Six columns are his
alone and are always written blank; one more, Priority Score, stays blank because the
match score is a measure of fit and must never be presented as a priority (D-010).

This half of the module is pure: it turns stored rows into the eighteen values a
spreadsheet row holds, and knows nothing about openpyxl, files or styling.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from toutoule import models, schemas

# The owner's header row, in his order. The export never invents, reorders or renames a
# column; it checks the file it is given against this and refuses if they differ.
COLUMNS: tuple[str, ...] = (
    "Company",
    "Title",
    "Status",
    "Link",
    "Market",
    "Geography",
    "Application Date",
    "Interview Stage",
    "Interviewer",
    "Notes",
    "Deadline",
    "Urgency",
    "Candidate Fit",
    "Priority Score",
    "Main Skills Required",
    "Recommended Resume",
    "Next Action",
    "Last Verified",
)

# What a field says when the posting did not state it. Never a guess, never a blank cell:
# a blank is ambiguous between "the posting was silent" and "the system never looked"
# (PRD F3, non-negotiable constraint 2).
NOT_STATED = "Not stated"

# The one value the export writes into Status. The tracker's vocabulary is the owner's,
# not JobStatus: "approved but not yet applied" is what he calls "To Apply". It is also a
# member of the column's dropdown, which a test checks against the file itself.
TO_APPLY = "To Apply"

# jobs.last_seen_at is UTC. The tracker is read by a human in New York, so a job triaged
# at 21:00 on the 5th must not be stamped the 6th (the DST hazard in CLAUDE.md, in small).
TRACKER_TZ = ZoneInfo("America/New_York")


def field_text(field: schemas.ExtractedField) -> str:
    """One extracted field as a cell value: its verbatim value, or "Not stated".

    Written against ExtractedField rather than against any one field name, so the rule is
    identical for all five critical and all five important fields.
    """
    if not field.stated or field.value is None:
        return NOT_STATED
    return field.value


def notes_line(flags: list[models.RedFlag]) -> str:
    """One line naming every rule that fired, or "" when none did.

    Only approved jobs are exported, and approving past a HARD flag already requires an
    explicit confirmation (triage.record_decision), so a HARD flag on an exported job is
    by construction one the owner overrode on purpose. The suffix records that in the
    tracker, where he will read it months later.
    """
    if not flags:
        return ""
    ordered = sorted(flags, key=lambda flag: flag.rule_id)
    body = "; ".join(f"{flag.severity} {flag.rule_id}" for flag in ordered)
    line = f"toutoule flags: {body}"
    if any(flag.severity == models.FlagSeverity.HARD for flag in ordered):
        line += " (approved after HARD confirm)"
    return line


def last_verified(seen_at: datetime) -> date:
    """The tracker's "Last Verified" date: when the system last saw the posting, in New York.

    ZoneInfo is the standard library's time-zone database; .astimezone moves the instant
    into that zone before the date is taken, which is the whole point of the conversion.
    """
    return seen_at.astimezone(TRACKER_TZ).date()


def build_row(
    job: models.Job,
    extraction: schemas.Extraction,
    result: schemas.MatchResult,
    flags: list[models.RedFlag],
) -> list[object]:
    """The eighteen values for one job, in COLUMNS order. None means an empty cell.

    Six columns are the owner's to fill (Application Date, Interview Stage, Interviewer,
    Next Action, Urgency, Market) and one is blank by decision (Priority Score, D-010).
    Market has no source at all: the market is an argument to the red-flag rules and is
    never persisted, so there is nothing to write (D-011, README known limits).
    """
    return [
        job.company,  # Company
        job.title,  # Title
        TO_APPLY,  # Status
        job.url,  # Link
        None,  # Market — not persisted
        field_text(extraction.important.location),  # Geography
        None,  # Application Date — owner only
        None,  # Interview Stage — owner only
        None,  # Interviewer — owner only
        notes_line(flags) or None,  # Notes
        field_text(extraction.critical.deadline),  # Deadline — verbatim, never parsed
        None,  # Urgency — owner only; the flags are in Notes
        result.score,  # Candidate Fit — the match score belongs here, not in Priority
        None,  # Priority Score — blank by D-010
        ", ".join(extraction.reference.skills) or None,  # Main Skills Required
        result.recommended_version,  # Recommended Resume
        None,  # Next Action — owner only
        last_verified(job.last_seen_at),  # Last Verified
    ]
