"""Extraction with evidence verification (tech spec §3, ADR-003).

The model reads a job posting and returns an Extraction. Code, not the prompt, then checks
that every quoted piece of evidence really appears in the posting.
"""

import re
import unicodedata
from pathlib import Path

PROMPT_PATH = Path(__file__).parents[2] / "data" / "prompts" / "extract_v1.txt"


def load_prompt(path: Path = PROMPT_PATH) -> tuple[str, str]:
    """Return (version tag, prompt body). The tag is the file's first line."""
    version, _, body = path.read_text(encoding="utf-8").partition("\n")
    return version.strip(), body.strip()


PROMPT_VERSION, PROMPT_BODY = load_prompt()

# Typographic look-alikes that NFKC leaves alone. Each maps to its plain ASCII form.
_LOOKALIKES = str.maketrans(
    {
        "‘": "'",  # ‘
        "’": "'",  # ’
        "“": '"',  # “
        "”": '"',  # ”
        "–": "-",  # – en dash
        "—": "-",  # — em dash
    }
)
# In Python, \s covers every Unicode space: line breaks, tabs, non-breaking spaces.
_WHITESPACE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Normalize text so a faithful quote matches its source despite formatting noise.

    NFKC turns compatibility characters into their standard form (full-width "：" becomes
    ":"). Curly quotes and dashes become straight ones, and every run of whitespace becomes
    one space. Case and everything else are kept: see ADR-003 for why it stops there.
    """
    s = unicodedata.normalize("NFKC", s).translate(_LOOKALIKES)
    return _WHITESPACE.sub(" ", s).strip()


def quote_in_source(quote: str, source: str) -> bool:
    """True if the quote appears, after normalization, somewhere in the source."""
    return normalize_text(quote) in normalize_text(source)
