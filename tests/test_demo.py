"""Offline examples round-trip the live pipeline without using private resumes."""

import importlib.util
from pathlib import Path

import pytest
from fakes import FakeClient
from postings import extraction_answer, score_answer
from pydantic import ValidationError

from toutoule import config, db, demo, extract, triage
from toutoule.config import get_settings


def test_build_round_trip_and_sample_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valid_env: None
) -> None:
    spec = importlib.util.spec_from_file_location("build_demo", "scripts/build_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(demo, "DEMO_DIR", tmp_path)
    original = config.profile_path

    def sample_path(version: str, sample: bool = False) -> Path:
        assert sample, "private profile must never be read"
        return original(version, sample=True)

    monkeypatch.setattr(config, "profile_path", sample_path)
    client = FakeClient(*([extraction_answer(), *([score_answer()] * 3)] * 3))
    views = module.build_demo(client, get_settings(env_file=None), tmp_path)
    assert len(client.requests) == 12
    assert [demo.load(case_id) for case_id in module.CASE_IDS] == views
    assert [case.id for case in demo.list_cases()] == sorted(module.CASE_IDS)
    client = FakeClient("invalid", "invalid")
    with pytest.raises(extract.ExtractionFailed, match="validation"):
        module.build_demo(client, get_settings(env_file=None), tmp_path / "failed")
    assert not (tmp_path / "failed").exists()


def test_committed_examples_need_no_client_or_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("demo loading must not construct a client or open a database")

    monkeypatch.setattr(triage, "Anthropic", forbidden)
    monkeypatch.setattr(db, "get_engine", forbidden)
    monkeypatch.setattr(triage, "Session", forbidden)
    cases = demo.list_cases()
    assert len(cases) == 3
    assert all(demo.load(case.id).profile == "sample" for case in cases)


@pytest.mark.parametrize("case_id", ["missing-99", "../cnp-01", "", "/tmp/cnp-01"])
def test_unknown_ids(case_id: str) -> None:
    with pytest.raises(ValueError, match="unknown demo case"):
        demo.load(case_id)


def test_invalid_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = demo._read(demo.DEMO_DIR / "cnp-01.json")
    monkeypatch.setattr(demo, "DEMO_DIR", tmp_path)
    path = tmp_path / "cnp-01.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValidationError):
        demo.list_cases()
    for update in ({"profile": "real"}, {"company": "wrong company"}):
        payload = record.model_dump(mode="json")
        payload["view"].update(update)
        with pytest.raises(ValidationError):
            demo.DemoRecord.model_validate(payload)
    path.write_text(record.model_dump_json().replace('"cnp-01"', '"cnp-02"'), encoding="utf-8")
    with pytest.raises(ValueError, match="filename"):
        demo.load("cnp-01")
