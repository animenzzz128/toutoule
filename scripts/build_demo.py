"""Run `uv run python scripts/build_demo.py` to rebuild the three offline examples."""

import logging
from datetime import UTC, datetime
from pathlib import Path

from toutoule import demo, evalset, extract, triage
from toutoule.config import Settings, get_settings
from toutoule.db import get_engine, get_session_factory, init_db

CASE_IDS = ("cnc-01", "cnp-01", "ust-01")


def build_demo(
    client: extract.ModelClient, settings: Settings, output: Path = demo.DEMO_DIR
) -> list[triage.TriageView]:
    """Use an isolated in-memory database, ignoring DATABASE_URL and private resumes."""
    today = datetime.now(UTC).date()
    cases = {case.case_id: case for case in evalset.load_cases(evalset.EVAL_DIR / "cases.csv")}
    engine = get_engine("sqlite:///:memory:")
    views = []
    try:
        init_db(engine)
        with get_session_factory(engine)() as session:
            for case_id in CASE_IDS:
                case = cases[case_id]
                market = "US" if case.segment.startswith("us_") else "CN"
                raw = (evalset.EVAL_DIR / "raw" / f"{case_id}.txt").read_text(encoding="utf-8")
                job_id = triage.run_triage(
                    session,
                    client,
                    case.company,
                    case.title,
                    case.url,
                    raw,
                    sample=True,
                    market=market,
                    today=today,
                    settings=settings,
                )
                view = triage.load_triage(session, job_id, sample=True)
                record = demo.DemoRecord(
                    case=demo.DemoCase(
                        id=case_id, company=view.company, title=view.title, market=market
                    ),
                    view=view,
                    built_on=today,
                    extraction_model=settings.extraction_model,
                    score_model=settings.score_model,
                )
                output.mkdir(parents=True, exist_ok=True)
                (output / f"{case_id}.json").write_text(
                    record.model_dump_json(indent=2) + "\n", encoding="utf-8"
                )
                views.append(view)
    finally:
        engine.dispose()
    return views


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    build_demo(triage.build_client(settings), settings)
