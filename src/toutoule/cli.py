"""Command-line entry point. Run: uv run python -m toutoule.cli <command>"""

import argparse
import io
import logging
import sys
from pathlib import Path

from anthropic import Anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from toutoule import extract, models, schemas
from toutoule.config import ConfigError, get_settings
from toutoule.db import get_engine, get_session_factory, init_db

# Below this, a "posting" is an empty or failed paste. Sending it would cost tokens and
# come back all "not stated", which looks like a real answer. Counted after normalization.
MIN_POSTING_CHARS = 200


def check_config() -> int:
    """Validate settings and report the result. Returns the process exit code."""
    try:
        get_settings()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    print("Config OK")
    return 0


def init_database() -> int:
    """Create any missing tables at DATABASE_URL and list them. Returns the exit code."""
    try:
        engine = get_engine()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    created = init_db(engine)
    if created:
        print("Created tables: " + ", ".join(created))
    else:
        print("All tables already exist.")
    return 0


def extract_file(path: str) -> int:
    """Extract one pasted job description from a UTF-8 text file. Returns the exit code."""
    try:
        settings = get_settings()
        raw_text = Path(path).read_text(encoding="utf-8")
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    length = len(extract.normalize_text(raw_text))
    if length < MIN_POSTING_CHARS:
        print(f"File looks empty or too short: {length} characters", file=sys.stderr)
        return 1
    engine = get_engine(settings.database_url)
    init_db(engine)
    model = settings.extraction_model
    content_hash = extract.hash_content(raw_text)

    with get_session_factory(engine)() as session:
        stored = extract.find_cached(session, content_hash, extract.PROMPT_VERSION, model)
        if stored is not None:
            print("Same text, prompt and model as before: showing the stored result, no API call.")
            _print_report(session, stored, cached=True)
            return 0

        job = models.Job(
            source_id=_manual_source(session).id,
            company="",  # filled from the extraction below
            title="",
            url=Path(path).resolve().as_uri(),
            raw_text=raw_text,
            content_hash=content_hash,
        )
        session.add(job)
        session.commit()
        client = Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        try:
            result = extract.extract_job(session, job, client, model)
        except extract.ExtractionFailed as error:
            print(f"Extraction failed for job {job.id}: {error}", file=sys.stderr)
            return 1
        job.company, job.title = result.company, result.title
        session.commit()
        stored = extract.find_cached(session, content_hash, extract.PROMPT_VERSION, model)
        assert stored is not None  # extract_job just saved it
        _print_report(session, stored)
    return 0


def _manual_source(session: Session) -> models.Source:
    """The single 'manual' source for pasted postings (ADR-005), created on first use."""
    source = session.scalars(select(models.Source).where(models.Source.adapter == "manual")).first()
    if source is None:
        source = models.Source(name="manual", tier=3, url="", adapter="manual")
        session.add(source)
        session.commit()
    return source


def _print_report(session: Session, row: models.Extraction, cached: bool = False) -> None:
    """Print the 10 evidence fields, the violations and the token counts.

    cached=True labels the tokens as the stored run's, so they don't read as new spend.
    """
    result = schemas.Extraction.model_validate(row.payload_json)
    print(f"{result.company} | {result.title}\n")
    print(f"{'field':<32} {'stated':<7} {'value':<24} evidence")
    for group_name in extract.EVIDENCE_GROUPS:
        group = getattr(result, group_name)
        for field_name in type(group).model_fields:
            field = getattr(group, field_name)
            name = f"{group_name}.{field_name}"
            value = field.value or "Not stated"
            print(f"{name:<32} {field.stated!s:<7} {value:<24} {field.evidence or ''}")

    violations = session.scalars(
        select(models.ExtractionViolation).where(models.ExtractionViolation.job_id == row.job_id)
    ).all()
    print("\nViolations:" + ("" if violations else " none"))
    for violation in violations:
        print(f"  {violation.field_path}: {violation.reason}")
    print(f"\nModel {row.model}, prompt {row.prompt_version}")
    label = "Tokens (from the stored run)" if cached else "Tokens"
    print(f"{label}: input {row.input_tokens}, output {row.output_tokens}")


def _use_utf8_output() -> None:
    """Write stdout and stderr as UTF-8, so Chinese text prints on every platform.

    On Windows, output sent to a pipe or file defaults to cp1252, which cannot encode
    Chinese, and print() would crash after the extraction was already saved.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):  # test capture objects may not be
            stream.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _use_utf8_output()
    parser = argparse.ArgumentParser(prog="python -m toutoule.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-config", help="validate settings in .env")
    commands.add_parser("init-db", help="create the database tables at DATABASE_URL")
    extract_parser = commands.add_parser("extract", help="extract one job posting from a file")
    extract_parser.add_argument("path", help="UTF-8 text file with the pasted job posting")

    args = parser.parse_args(argv)
    # Warnings from everything; info (per-call tokens, stop_reason) only from our own code,
    # so library chatter stays out of the output. Logs go to stderr.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("toutoule").setLevel(logging.INFO)
    if args.command == "extract":
        return extract_file(args.path)
    handlers = {"check-config": check_config, "init-db": init_database}
    return handlers[args.command]()


if __name__ == "__main__":
    sys.exit(main())
