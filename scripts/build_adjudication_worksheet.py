"""Build a manual adjudication worksheet for one eval run (Task 1.8, Part C).

Mechanical only: for every still-pending critical FieldResult, this prints the label and
system values plus a handful of raw-text lines for context. It never suggests a verdict —
the owner reads the raw lines and writes one in adjudications.csv themselves.

"Raw lines" means: every raw-text line containing the label's evidence quote or the
system's evidence quote, plus every line matching this field's keyword list below (kept
small and declared here, not hidden in a judgment call). This is a different, from-scratch
implementation of the same idea used for the Task 1.7 worksheet
(data/private/adjudication/2026-10-01T1940.md) — the original build script for that file
wasn't kept, so the keyword lists here are new and may not be character-for-character the
same lines that worksheet would have picked.

Usage: uv run python scripts/build_adjudication_worksheet.py <run_id>
"""

import sys
from pathlib import Path

from toutoule import evalrun, evalscore, evalset, extract

REPO = Path(__file__).resolve().parents[1]
RAW_DIR = evalset.EVAL_DIR / "raw"
OUT_DIR = REPO / "data" / "private" / "adjudication"

# One short, declared keyword list per critical field. These only add extra context
# lines around the evidence quotes already shown — they never decide a verdict.
FIELD_KEYWORDS: dict[str, list[str]] = {
    "deadline": ["deadline", "截止", "rolling basis", "until filled", "招满即止", "apply by"],
    "visa_sponsorship": [
        "sponsor",
        "visa",
        "签证",
        "工作许可",
        "immigration",
        "authorized to work",
    ],
    "graduation_window": ["graduat", "届", "毕业", "class of"],
    "application_cap": [
        "per candidate",
        "up to",
        "apply for up to",
        "每人",
        "仅可",
        "最多可选择",
        "只有1次",
        "志愿",
    ],
    "materials_required": ["resume", "cv", "cover letter", "transcript", "简历", "附件"],
}


def _matching_lines(
    raw_text: str, evidence_quotes: list[str], keywords: list[str]
) -> dict[int, str]:
    """1-indexed raw lines containing any evidence quote or any field keyword."""
    lines = raw_text.splitlines()
    normalized_lines = [extract.normalize_text(line) for line in lines]
    wanted: dict[int, str] = {}
    quotes_norm = [extract.normalize_text(q) for q in evidence_quotes if q]
    for i, line_norm in enumerate(normalized_lines, start=1):
        if not line_norm:
            continue
        hit = any(quote in line_norm for quote in quotes_norm) or any(
            keyword.casefold() in line_norm.casefold() for keyword in keywords
        )
        if hit:
            wanted[i] = lines[i - 1]
    return wanted


def _value_block(value: str | None, evidence: str | None) -> str:
    return f"{value or 'Not stated'} «{evidence or 'none'}»"


def build_worksheet(run_id: str) -> str:
    score = evalrun.score_run(run_id, "pipeline")
    pending = [r for r in score.results if r.tier == "critical" and evalscore._is_pending(r)]

    parts = [f"# Adjudication worksheet — run {run_id}", ""]
    for field in evalscore.CRITICAL_FIELDS:
        rows = sorted((r for r in pending if r.field == field), key=lambda r: r.case_id)
        parts.append(f"## {field} ({len(rows)} blocks)")
        parts.append("")
        for i, r in enumerate(rows, start=1):
            raw_text = (RAW_DIR / f"{r.case_id}.txt").read_text(encoding="utf-8-sig")
            quotes = [r.label_evidence, r.system_evidence]
            matches = _matching_lines(raw_text, quotes, FIELD_KEYWORDS[field])
            parts.append(f"[{i}] {r.case_id} · pipeline · {r.outcome}")
            parts.append(f"label: {_value_block(r.label_value, r.label_evidence)}")
            parts.append(f"system: {_value_block(r.system_value, r.system_evidence)}")
            parts.append(f"raw lines ({r.case_id}.txt):")
            if matches:
                for line_no in sorted(matches):
                    parts.append(f"  {line_no}: {matches[line_no]}")
            else:
                parts.append("  (none found)")
            parts.append("")
    return "\n".join(parts) + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_adjudication_worksheet.py <run_id>", file=sys.stderr)
        return 1
    run_id = sys.argv[1]
    text = build_worksheet(run_id)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{run_id}.md"
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
