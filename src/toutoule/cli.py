"""Command-line entry point. Run: uv run python -m toutoule.cli <command>"""

import argparse
import io
import logging
import sys
from pathlib import Path

from anthropic import Anthropic
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from toutoule import evalreport, evalrun, evalset, extract, models, schemas
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


def eval_init() -> int:
    """Write a blank label template for every data/eval/cases.csv row without one yet."""
    try:
        written, existing = evalset.write_blank_labels(evalset.EVAL_DIR)
    except FileNotFoundError:
        print("data/eval/cases.csv not found", file=sys.stderr)
        return 1
    except ValidationError as error:
        print(extract.describe_errors(error), file=sys.stderr)
        return 1
    print(f"Wrote {written} new label template(s); {existing} already existed.")
    return 0


def eval_check(final: bool) -> int:
    """Print every eval-set problem, then composition progress. See evalset.py."""
    problems = evalset.check_eval_set()
    if problems:
        print("Problems:")
        for problem in problems:
            print(f"  {problem}")
    else:
        print("No problems.")

    summary = evalset.composition_summary()
    print("\nComposition:")
    for line in evalset.target_report(summary):
        print(f"  {line}")

    exit_code = 1 if problems else 0
    if final:
        missing = evalset.unmet_targets(summary)
        if missing:
            print("\nTargets not met (--final):")
            for line in missing:
                print(f"  {line}")
            exit_code = 1
    return exit_code


def eval_command(
    system: str,
    cases_arg: str | None,
    resume: str | None,
    rescore: str | None,
    prompt_name: str,
) -> int:
    """Run and score the eval set, or resume/rescore an existing run. Returns the exit code."""
    try:
        settings = get_settings()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    systems = {"pipeline", "baseline"} if system == "both" else {system}

    if rescore:
        run_id = rescore
    else:
        try:
            prompt = extract.load_prompt_by_name(prompt_name)
        except extract.PromptNotFound as error:
            print(error, file=sys.stderr)
            return 1
        run_id = resume or evalrun.new_run_id()
        try:
            cases = _select_cases(run_id, resume, cases_arg)
        except FileNotFoundError:
            print(f"No run folder for {run_id!r}: nothing to resume", file=sys.stderr)
            return 1
        client = Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        evalrun.run_eval(run_id, cases, systems, client, settings.extraction_model, prompt=prompt)

    engine = get_engine(settings.database_url)
    init_db(engine)
    meta = evalrun.load_meta(evalrun.run_dir(run_id))
    scores: dict[str, evalrun.RunScore] = {}
    with get_session_factory(engine)() as session:
        for name in ("pipeline", "baseline"):
            if name not in systems:
                continue
            score = evalrun.score_run(run_id, name)
            scores[name] = score
            evalrun.save_eval_run(
                session,
                run_id,
                settings.extraction_model,
                score,
                rescore=bool(rescore),
                prompt_version=meta["prompt_versions"][name],
            )

    report_path = evalreport.write_report(run_id, meta, scores)
    print(evalreport.tier_table(scores))
    print(f"\nReport: {report_path}")
    total_pending = sum(score.metrics.pending for score in scores.values())
    if total_pending > 0:
        print(f"PENDING: {total_pending} critical disagreements need a verdict")
    return 0


def _select_cases(run_id: str, resume: str | None, cases_arg: str | None) -> list[evalset.CaseRow]:
    """Which cases.csv rows this run covers. Resuming reuses the run's own case list,
    ignoring --cases, so a resumed run never silently drops or adds cases."""
    all_cases = evalset.load_cases(evalset.EVAL_DIR / "cases.csv")
    if resume:
        wanted = set(evalrun.load_meta(evalrun.run_dir(run_id))["cases"])
    elif cases_arg:
        wanted = set(cases_arg.split(","))
    else:
        return all_cases
    return [case for case in all_cases if case.case_id in wanted]


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
    commands.add_parser("eval-init", help="write blank label templates for new cases.csv rows")
    eval_check_parser = commands.add_parser(
        "eval-check", help="check the eval set and report composition progress"
    )
    eval_check_parser.add_argument(
        "--final", action="store_true", help="treat unmet composition targets as failures"
    )
    eval_parser = commands.add_parser("eval", help="run and score the eval set")
    eval_parser.add_argument("--system", choices=["pipeline", "baseline", "both"], default="both")
    eval_parser.add_argument("--cases", help="comma-separated case ids, default all")
    eval_parser.add_argument(
        "--prompt",
        default="extract_v1",
        help="pipeline prompt version to run, loaded from data/prompts/<name>.txt",
    )
    eval_run_group = eval_parser.add_mutually_exclusive_group()
    eval_run_group.add_argument("--resume", metavar="RUN_ID", help="continue an interrupted run")
    eval_run_group.add_argument(
        "--rescore", metavar="RUN_ID", help="rescore an existing run, no API calls"
    )

    args = parser.parse_args(argv)
    # Warnings from everything; info (per-call tokens, stop_reason) only from our own code,
    # so library chatter stays out of the output. Logs go to stderr.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("toutoule").setLevel(logging.INFO)
    if args.command == "extract":
        return extract_file(args.path)
    if args.command == "eval-init":
        return eval_init()
    if args.command == "eval-check":
        return eval_check(args.final)
    if args.command == "eval":
        return eval_command(args.system, args.cases, args.resume, args.rescore, args.prompt)
    handlers = {"check-config": check_config, "init-db": init_database}
    return handlers[args.command]()


if __name__ == "__main__":
    sys.exit(main())
