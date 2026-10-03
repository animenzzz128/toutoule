"""Application settings, read from environment variables and the .env file.

Nothing is read at import time. Call get_settings() when settings are needed, so tests
and CI can import this module without a .env file.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# What each setting must look like. Shown to the user when a value is invalid.
# Never include the actual value in a message: it might be the API key.
_RULES: dict[str, str] = {
    "ANTHROPIC_API_KEY": "must be your Anthropic API key",
    "DATABASE_URL": "must be a database URL, e.g. sqlite:///data/toutoule.db",
    "MATCH_THRESHOLD": "must be a whole number from 0 to 100",
    "EXTRACTION_MODEL": "must be a Claude model id, e.g. claude-haiku-4-5",
    "SCORE_MODEL": "must be a Claude model id, e.g. claude-sonnet-5-5",
    "DIGEST_EMAIL_TO": "must be an email address",
    "OWNER_REQUIRES_SPONSORSHIP": "must be true or false",
    "OWNER_GRADUATION": "must be a month as YYYY-MM, e.g. 2027-05",
    "OWNER_DEGREE": "must be bachelor, master or phd",
}


class ConfigError(Exception):
    """A setting is missing or invalid. The message is one line and safe to print."""


class Settings(BaseSettings):
    """Validated settings. Field names match env var names, case-insensitively."""

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    # SecretStr prints as '**********', so the key cannot leak through print or logs.
    anthropic_api_key: SecretStr = Field(min_length=1)
    database_url: str = Field(min_length=1)
    match_threshold: int = Field(ge=0, le=100)
    # Small, cheap model for extraction (tech spec §10). It must support structured output.
    extraction_model: str = Field(default="claude-haiku-4-5", min_length=1)
    # Larger model for scoring (PRD risk table, D-010 §6). Overridable by env var like
    # EXTRACTION_MODEL, so a cheaper model can be tried without editing code.
    score_model: str = Field(default="claude-sonnet-5-5", min_length=1)
    # Optional until the mailer lands in Task 2.6.
    digest_email_to: str | None = None

    # The owner's profile, compared against each job by the red-flag rules (tech spec §4).
    owner_requires_sponsorship: bool = True
    # The pattern only accepts months 01-12, so "2027-13" is a config error at startup.
    owner_graduation: str = Field(default="2027-05", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    owner_degree: Literal["bachelor", "master", "phd"] = "master"


def get_settings(env_file: Path | str | None = ".env") -> Settings:
    """Load and validate settings, raising ConfigError if any setting is bad.

    Real environment variables take priority over values in env_file.
    Pass env_file=None to read only the environment (the tests do this).
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as error:
        # 'from None' drops the long pydantic error chain; our message says it all.
        raise ConfigError(_describe(error)) from None


def _describe(error: ValidationError) -> str:
    """Turn the first validation error into one plain-language line."""
    first = error.errors()[0]
    name = str(first["loc"][0]).upper()
    if first["type"] == "missing":
        problem = "is missing"
    else:
        problem = f"is invalid ({_RULES.get(name, 'check its value')})"
    return f"Config error: {name} {problem}. Set it in .env (see .env.example)."


# --- Match scoring (tech spec §5, D-010) -------------------------------------------------
#
# These are code-level facts, not user settings, so they are plain constants rather than
# Settings fields: changing a weight changes what a score means, which belongs in a commit
# and a decision-log entry, not in someone's .env.

SCORE_PROMPT = "score_v1"

# Tech spec §5. combine() divides by the sum, so these need not add up to 100; they do.
SCORE_WEIGHTS: dict[str, int] = {"domain_fit": 40, "skills_overlap": 35, "seniority_fit": 25}

# Tie-break order for the recommended version (D-010 §2): on an equal total, the earlier
# entry wins. Ordered by how the owner wants to be read first, not alphabetically.
RESUME_VERSIONS: tuple[str, ...] = ("ai_product", "strategy_bizops", "consulting")

_REPO_ROOT = Path(__file__).parents[2]
# The real resumes, gitignored and never quoted in anything the repo keeps (D-010 §9).
PROFILE_DIR = _REPO_ROOT / "data" / "private" / "profile"
# The redacted samples, committed, used by the demo and by every test.
SAMPLE_PROFILE_DIR = _REPO_ROOT / "data" / "profile"


def profile_path(version: str, sample: bool = False) -> Path:
    """Path to one resume version, real by default or the redacted sample when sample=True."""
    directory = SAMPLE_PROFILE_DIR if sample else PROFILE_DIR
    name = f"sample_{version}.md" if sample else f"{version}.md"
    return directory / name
