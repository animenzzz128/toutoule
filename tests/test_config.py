from pathlib import Path

import pytest

from toutoule.config import ConfigError, get_settings


@pytest.mark.usefixtures("valid_env")
def test_valid_settings_load() -> None:
    settings = get_settings(env_file=None)

    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-fake-test-key"
    assert settings.database_url == "sqlite:///:memory:"
    assert settings.match_threshold == 65
    assert settings.digest_email_to is None


@pytest.mark.usefixtures("valid_env")
def test_extraction_model_has_a_default() -> None:
    assert get_settings(env_file=None).extraction_model == "claude-haiku-4-5"


@pytest.mark.usefixtures("valid_env")
def test_extraction_model_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTION_MODEL", "claude-sonnet-5")

    assert get_settings(env_file=None).extraction_model == "claude-sonnet-5"


@pytest.mark.usefixtures("valid_env")
def test_api_key_is_hidden_when_printed() -> None:
    settings = get_settings(env_file=None)

    assert "sk-ant-fake-test-key" not in str(settings)
    assert "sk-ant-fake-test-key" not in repr(settings)


def test_settings_load_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=sk-ant-from-file\nDATABASE_URL=sqlite:///x.db\nMATCH_THRESHOLD=70\n"
    )

    settings = get_settings(env_file=env_file)

    assert settings.match_threshold == 70


@pytest.mark.usefixtures("valid_env")
def test_missing_api_key_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    with pytest.raises(ConfigError) as caught:
        get_settings(env_file=None)

    message = str(caught.value)
    assert message == (
        "Config error: ANTHROPIC_API_KEY is missing. Set it in .env (see .env.example)."
    )


@pytest.mark.usefixtures("valid_env")
def test_empty_api_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY is invalid"):
        get_settings(env_file=None)


@pytest.mark.usefixtures("valid_env")
@pytest.mark.parametrize("bad_value", ["150", "-1", "high"])
def test_bad_match_threshold_is_rejected(monkeypatch: pytest.MonkeyPatch, bad_value: str) -> None:
    monkeypatch.setenv("MATCH_THRESHOLD", bad_value)

    with pytest.raises(ConfigError) as caught:
        get_settings(env_file=None)

    message = str(caught.value)
    assert "MATCH_THRESHOLD is invalid (must be a whole number from 0 to 100)" in message
    assert bad_value not in message  # values are never echoed back


@pytest.mark.usefixtures("valid_env")
def test_owner_profile_settings_have_defaults() -> None:
    settings = get_settings(env_file=None)

    assert settings.owner_requires_sponsorship is True
    assert settings.owner_graduation == "2027-05"
    assert settings.owner_degree == "master"


@pytest.mark.usefixtures("valid_env")
@pytest.mark.parametrize("bad_value", ["2027-13", "2027-00", "2027-5", "May 2027", "2027-05-01"])
def test_bad_owner_graduation_is_rejected(monkeypatch: pytest.MonkeyPatch, bad_value: str) -> None:
    monkeypatch.setenv("OWNER_GRADUATION", bad_value)

    with pytest.raises(ConfigError) as caught:
        get_settings(env_file=None)

    assert str(caught.value) == (
        "Config error: OWNER_GRADUATION is invalid (must be a month as YYYY-MM, e.g. 2027-05)."
        " Set it in .env (see .env.example)."
    )


@pytest.mark.usefixtures("valid_env")
@pytest.mark.parametrize("bad_value", ["Master", "mba", ""])
def test_bad_owner_degree_is_rejected(monkeypatch: pytest.MonkeyPatch, bad_value: str) -> None:
    monkeypatch.setenv("OWNER_DEGREE", bad_value)

    with pytest.raises(ConfigError, match="OWNER_DEGREE is invalid"):
        get_settings(env_file=None)
