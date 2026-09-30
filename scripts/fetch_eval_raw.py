"""Fetch ATS postings for eval cases via public job-board APIs (Task 1.6, Part C).

Only Greenhouse and Lever are used. Both have a documented, unauthenticated,
single-posting endpoint, confirmed against their own public docs:
  - Greenhouse: https://docs.greenhouse.io/job-board.html
  - Lever:      https://github.com/lever/postings-api
Ashby's public job-board API (api.ashbyhq.com/posting-api/job-board/{name}) returns
every posting on a board in one response with no confirmed single-job endpoint, and
its reference docs 404'd on every page fetched while checking this. Per the brief
("if you can't confirm an endpoint is public and documented, skip that ATS"), Ashby
postings are left for manual copy instead of guessed at.

Only stdlib is used (urllib, html.parser, csv) — no new dependency, and nothing here
calls the Anthropic API. Never prints or logs posting text: only case_id, status, and
character count.
"""

import csv
import html.parser
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
CASES_PATH = REPO / "data" / "eval" / "cases.csv"
RAW_DIR = REPO / "data" / "eval" / "raw"

USER_AGENT = "toutoule-eval/0.1 (personal research project)"
REQUEST_PAUSE_SECONDS = 2

_GREENHOUSE_HOST_RE = re.compile(r"^(?:job-boards|boards)\.greenhouse\.io$")
_GREENHOUSE_PATH_RE = re.compile(r"^/([^/]+)/jobs/(\d+)")
_LEVER_HOST = "jobs.lever.co"
_LEVER_PATH_RE = re.compile(r"^/([^/]+)/([0-9a-fA-F-]{36})")

# Block elements become line breaks; script/style content is skipped entirely (it was
# never part of the posting's words). Nothing else is rewritten, shortened or reordered.
_BLOCK_TAGS = {"p", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "div"}
_SKIP_TAGS = {"script", "style"}


class _HTMLToText(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # entities arrive already unescaped
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(markup: str) -> str:
    """Deterministic HTML -> plain text: every word kept, block tags become line
    breaks, runs of blank lines collapsed to at most one.
    """
    parser = _HTMLToText()
    parser.feed(markup)
    parser.close()
    lines = [line.strip() for line in parser.text().splitlines()]
    collapsed: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            collapsed.append(line)
        else:
            blank_run += 1
            if blank_run == 1:
                collapsed.append(line)
    return "\n".join(collapsed).strip("\n")


def detect_ats(url: str) -> tuple[str, str, str] | None:
    """Return (ats_name, org, posting_id) for a supported ATS URL, else None."""
    parts = urlsplit(url)
    if _GREENHOUSE_HOST_RE.match(parts.netloc):
        match = _GREENHOUSE_PATH_RE.match(parts.path)
        if match:
            return ("greenhouse", match.group(1), match.group(2))
    elif parts.netloc == _LEVER_HOST:
        match = _LEVER_PATH_RE.match(parts.path)
        if match:
            return ("lever", match.group(1), match.group(2))
    return None


def _get_json(url: str) -> dict:
    """One HTTP GET, always followed by the required pause before the next request."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    finally:
        time.sleep(REQUEST_PAUSE_SECONDS)


def fetch_greenhouse(board_token: str, job_id: str) -> tuple[str, str, str]:
    """Return (title, location, html_description). docs.greenhouse.io/job-board.html"""
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}")
    return data["title"], data.get("location", {}).get("name", ""), data["content"]


def fetch_lever(site: str, posting_id: str) -> tuple[str, str, str]:
    """Return (title, location, html_description). github.com/lever/postings-api"""
    data = _get_json(f"https://api.lever.co/v0/postings/{site}/{posting_id}")
    location = data.get("categories", {}).get("location", "")
    return data["text"], location, data["description"]


_FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever}


def _fetch_with_one_retry(fetch_fn, *args: str) -> tuple[str, str, str]:
    """At most one retry, and only for non-404 failures: a 404 means the posting is
    gone, not that the request should be repeated.
    """
    try:
        return fetch_fn(*args)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise
        return fetch_fn(*args)
    except (urllib.error.URLError, TimeoutError, OSError):
        return fetch_fn(*args)


def main() -> None:
    with CASES_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)

    changed = False
    for row in rows:
        case_id = row["case_id"]
        raw_path = RAW_DIR / f"{case_id}.txt"
        if raw_path.exists() and raw_path.read_text(encoding="utf-8").strip():
            continue  # already has real content from elsewhere; never overwrite

        ats = detect_ats(row["url"])
        if ats is None:
            print(f"{case_id} manual 0")
            continue
        ats_name, org, posting_id = ats

        try:
            title, location, description_html = _fetch_with_one_retry(
                _FETCHERS[ats_name], org, posting_id
            )
        except urllib.error.HTTPError as error:
            print(f"{case_id} {'manual' if error.code == 404 else f'error-http-{error.code}'} 0")
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(f"{case_id} error-{type(error).__name__} 0")
            continue

        body = html_to_text(description_html)
        text = f"{title}\n{location}\n\n{body}"
        raw_path.write_text(text, encoding="utf-8")
        row["notes"] = f"{row['notes']}; raw via {ats_name} api"
        changed = True
        print(f"{case_id} ok {len(text)}")

    if changed:
        with CASES_PATH.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
