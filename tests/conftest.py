"""Shared test setup. pytest loads this file automatically before any test runs."""

import pytest

SETTING_NAMES = ["ANTHROPIC_API_KEY", "DATABASE_URL", "MATCH_THRESHOLD", "DIGEST_EMAIL_TO"]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove real settings from the environment so no test sees the owner's values."""
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a complete, valid, fake configuration."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("MATCH_THRESHOLD", "65")
