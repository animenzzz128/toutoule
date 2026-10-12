"""The Streamlit page, driven by AppTest (Task 1.11). No browser, no network, no .env.

AppTest runs the script in this process and exposes the elements it produced, so a click
is a method call and a banner is a value to assert on. The fake client is injected by
replacing triage.build_client: the page looks that name up on the module at call time,
which a script AppTest executes in its own namespace still shares with this test.
"""

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from fakes import FakeClient
from postings import POSTING, RESUME, extraction_answer, field, score_answer
from sqlalchemy import select
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.errors import AppTestError

from toutoule import config, models, triage
from toutoule.db import get_engine, get_session_factory

APP = Path(__file__).parents[1] / "app" / "streamlit_app.py"
# A cold pandas import can take most of a minute on a first run; the default 3s timeout
# would make these tests flaky for a reason that has nothing to do with the page.
TIMEOUT = 60
REAL_LINE = "Built a pricing model for a payments team"
REAL_RESUME = f"{REAL_LINE}\nShipped a billing migration"

AppFactory = Callable[..., AppTest]


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A throwaway database, and a working folder with no .env to be read from."""
    url = f"sqlite:///{tmp_path / 'app.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.chdir(tmp_path)
    return url


@pytest.fixture
def profile_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Temporary real and sample profiles. The real folder is created only on request."""
    real, sample = tmp_path / "real", tmp_path / "sample"
    sample.mkdir()
    for version in config.RESUME_VERSIONS:
        (sample / f"sample_{version}.md").write_text(RESUME, encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_DIR", real)
    monkeypatch.setattr(config, "SAMPLE_PROFILE_DIR", sample)
    return real, sample


@pytest.fixture
def make_app(
    monkeypatch: pytest.MonkeyPatch,
    valid_env: None,
    database: str,
    profile_dirs: tuple[Path, Path],
) -> AppFactory:
    """Build the page with a fake client holding the answers this test will need."""

    def factory(*answers: str) -> AppTest:
        client = FakeClient(*answers)
        monkeypatch.setattr(triage, "build_client", lambda _settings: client)
        st.cache_resource.clear()  # or a previous test's engine and client would be reused
        return AppTest.from_file(str(APP), default_timeout=TIMEOUT).run()

    return factory


def full_answers() -> tuple[str, ...]:
    """One extraction and three scores: what one complete triage asks the model for."""
    return (extraction_answer(), score_answer(), score_answer(), score_answer())


def answers_quoting(line: str) -> tuple[str, ...]:
    """Three scoring answers whose resume side quotes `line`, so they verify against it."""
    data = json.loads(score_answer())
    for pair in data["evidence_pairs"]:
        pair["experience"] = line
    return (json.dumps(data),) * 3


def click(at: AppTest, label: str) -> AppTest:
    """Click the button with this label. Buttons have no key, so the label is the handle."""
    for button in at.button:
        if button.label == label:
            return button.click().run()
    raise AssertionError(f"no button labelled {label!r}; found {[b.label for b in at.button]}")


def triage_posting(at: AppTest, market: str = "Unknown", text: str = POSTING) -> AppTest:
    at.text_input(key="company").set_value("Example Co")
    at.text_area(key="posting").set_value(text)
    at.selectbox(key="market").select(market)
    return click(at, "Triage")


def field_cards(at: AppTest, group: str = "critical") -> dict[str, dict[str, Any]]:
    """Each field card, read back as the row the old st.table showed: field, value, evidence.

    A card is a keyed container, found by its key. Its value is "Not stated" when it carries
    that pill, otherwise its st.text; its evidence is its code block, or "" when it has none.
    """
    prefix = f"card-{group}-"
    rows: dict[str, dict[str, Any]] = {}
    for node in at.main:
        key = getattr(node, "key", None) or ""
        if not key.startswith(prefix):
            continue
        pill = any("badge[Not stated]" in item.value for item in node.markdown)
        name = key.removeprefix(prefix)
        rows[name] = {
            "field": name,
            "value": "Not stated" if pill else node.text[0].value,
            "evidence": node.code[0].value if node.code else "",
        }
    return rows


def page_text(at: AppTest) -> str:
    """Everything the page renders, as one string: element values, labels and tables."""
    chunks: list[str] = []
    for block in (at.main, at.sidebar):
        for element in block:
            for attribute in ("value", "label"):
                found = getattr(element, attribute, None)
                if found is not None and not isinstance(found, bool):
                    chunks.append(found if isinstance(found, str) else str(found))
    return "\n".join(chunks)


def decisions(database_url: str) -> list[models.Decision]:
    with get_session_factory(get_engine(database_url))() as session:
        return list(session.scalars(select(models.Decision)))


def jobs(database_url: str) -> list[models.Job]:
    with get_session_factory(get_engine(database_url))() as session:
        return list(session.scalars(select(models.Job)))


# --- Paste and read the evidence ---------------------------------------------------------


def test_the_critical_table_shows_not_stated_and_the_evidence_quote(
    make_app: AppFactory,
) -> None:
    at = triage_posting(make_app(*full_answers()))

    assert not at.exception
    rows = field_cards(at)
    assert rows["graduation_window"]["value"] == "Not stated"
    assert rows["graduation_window"]["evidence"] == ""
    assert rows["deadline"]["value"] == "2026-12-31"
    assert rows["deadline"]["evidence"] == "Applications close on 2026-12-31."


def test_an_unstated_field_is_a_not_stated_pill_and_nothing_else(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))

    for name in ("graduation_window", "application_cap"):  # the posting is silent on both
        card = at.get_by_key(f"card-critical-{name}")
        assert any("badge[Not stated]" in item.value for item in card.markdown)
        assert card.code == []  # no quote
        assert card.text == []  # no value, and no blank where one would be


def test_every_stated_critical_card_shows_its_verbatim_quote(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))

    quotes = {
        "deadline": "Applications close on 2026-12-31.",
        "visa_sponsorship": "We do not sponsor work visas for this role.",
        "materials_required": "Please submit a resume and cover",
    }
    for name, quote in quotes.items():
        card = at.get_by_key(f"card-critical-{name}")
        assert [block.value for block in card.code] == [quote]
        assert any("Found in source" in item.value for item in card.markdown)


def test_markup_in_a_posting_is_shown_as_text_and_never_rendered(
    make_app: AppFactory,
) -> None:
    markup = "<script>alert(1)</script>"
    line = f"One application per candidate {markup}."
    answer = extraction_answer(application_cap=field(f"one per candidate {markup}", line))

    at = triage_posting(make_app(answer, *full_answers()[1:]), text=f"{POSTING}{line}\n")

    card = field_cards(at)["application_cap"]
    assert card["value"] == f"one per candidate {markup}"  # st.text shows it as written
    assert card["evidence"] == line  # and so does the code block
    banner = at.warning[0].value  # R4 SCARCE quotes the same line, through Markdown
    assert markup not in banner
    assert r"\<script\>alert\(1\)\</script\>" in banner


def test_a_posting_too_short_to_be_real_is_refused_before_any_call(
    make_app: AppFactory,
) -> None:
    at = make_app()  # no answers queued: a model call would raise

    at = triage_posting(at, text="Product Manager wanted.")

    assert not at.exception
    assert "too short" in at.error[0].value
    assert jobs(f"sqlite:///{Path.cwd() / 'app.db'}") == []


def test_the_company_is_required(make_app: AppFactory) -> None:
    at = make_app()
    at.text_area(key="posting").set_value(POSTING)

    at = click(at, "Triage")

    assert "required" in at.error[0].value


# --- Red flags ---------------------------------------------------------------------------


def test_a_hard_flag_is_an_error_banner_and_approve_without_the_checkbox_saves_nothing(
    make_app: AppFactory, database: str
) -> None:
    at = triage_posting(make_app(*full_answers()), market="United States")

    banner = at.error[0].value
    assert "HARD · R1" in banner
    assert "We do not sponsor work visas for this role." in banner

    at = click(at, "Approve")

    assert "confirm_hard" in at.error[-1].value
    assert decisions(database) == []  # the rule refused it; the page stored nothing


def test_a_posting_with_no_flags_says_so(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))  # market unknown, so R1 cannot fire

    assert "No red flags from the rules." in page_text(at)
    assert at.error == []


def test_a_flag_banner_says_which_rule_decided_it(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()), market="United States")

    assert "decided by rule R1" in at.error[0].value


# --- Summary and layout ------------------------------------------------------------------


def test_the_summary_strip_shows_stated_fields_flags_and_the_best_fit(
    make_app: AppFactory,
) -> None:
    at = triage_posting(make_app(*full_answers()), market="United States")

    strip = {metric.label: metric.value for metric in at.metric[:3]}
    recommended = at.metric[3]  # the Résumé fit tab's own headline number
    assert strip == {
        "Critical fields stated": "3 / 5",  # graduation_window and application_cap are not
        "Rule flags": "1 HARD",
        "Best résumé fit": recommended.value,
    }
    assert at.caption[0].value.startswith("Fit to resume only.")  # right under the strip


def test_the_decision_controls_sit_together_in_one_card(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()), market="United States")

    card = at.get_by_key("card-decision")
    assert [button.label for button in card.button] == ["Approve", "Reject"]
    assert card.checkbox[0].label == "I've read the HARD flag above"
    assert card.selectbox(key="reason") is not None


def test_only_the_primary_actions_take_the_accent_colour(make_app: AppFactory) -> None:
    """Teal marks primary actions and nothing else (D-013): Triage and Approve, not Reject."""
    at = triage_posting(make_app(*full_answers()))

    kinds = {button.label: button.proto.type for button in at.main.button}
    assert kinds == {"Triage": "primary", "Approve": "primary", "Reject": "secondary"}


# --- The acceptance test, end to end -----------------------------------------------------


def test_rejecting_with_wrong_location_writes_one_decisions_row(
    make_app: AppFactory, database: str
) -> None:
    """Task 1.11's acceptance criterion, driven through the page itself."""
    at = triage_posting(make_app(*full_answers()))

    at.selectbox(key="reason").select("wrong_location")
    at = click(at, "Reject")

    assert "Saved: rejected (Wrong location)." in at.success[0].value
    stored = decisions(database)
    assert len(stored) == 1
    assert (stored[0].action, stored[0].reject_reason) == ("rejected", "wrong_location")
    assert jobs(database)[0].status == models.JobStatus.REJECTED
    assert "Status: **rejected**" in page_text(at)


def test_rejecting_without_choosing_a_reason_is_refused(
    make_app: AppFactory, database: str
) -> None:
    at = triage_posting(make_app(*full_answers()))

    at = click(at, "Reject")

    assert at.error  # the message comes from triage.record_decision, not from the page
    assert decisions(database) == []


# --- The score section -------------------------------------------------------------------


def test_the_score_caption_says_it_is_not_calibrated(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))

    captions = [caption.value for caption in at.caption]
    assert any("not calibrated to the owner's judgment" in text for text in captions)
    assert any("docs/eval/scoring.md" in text for text in captions)


def test_the_page_never_claims_to_be_calibrated(make_app: AppFactory) -> None:
    """Every mention of the word has to be a denial of it, wherever it appears."""
    text = page_text(at := triage_posting(make_app(*full_answers())))

    assert "calibrated" in text  # the caption is there to be found
    for position in range(len(text)):
        if text.startswith("calibrated", position):
            assert text[max(0, position - 4) : position] == "not "
    assert not at.exception


def test_only_verified_pairs_are_offered_as_evidence(make_app: AppFactory) -> None:
    answers = (extraction_answer(), *(score_answer(fabricate=True),) * 3)

    at = triage_posting(make_app(*answers))

    text = page_text(at)
    assert "Ran a team of nine data scientists" not in text  # the invented quote
    assert "1 pair(s) hidden: quote not found in source." in text


# --- The profile the page shows ----------------------------------------------------------


def test_flipping_to_the_sample_profile_hides_the_real_resumes_words(
    make_app: AppFactory, profile_dirs: tuple[Path, Path]
) -> None:
    """Evidence pairs quote the résumé, so a stale score would put private words on screen."""
    real, _ = profile_dirs
    real.mkdir()
    for version in config.RESUME_VERSIONS:
        (real / f"{version}.md").write_text(REAL_RESUME, encoding="utf-8")
    at = triage_posting(make_app(extraction_answer(), *answers_quoting(REAL_LINE)))
    assert REAL_LINE in page_text(at)  # scored against the real profile

    at.toggle(key="use_sample").set_value(True).run()

    text = page_text(at)
    assert REAL_LINE not in text
    assert "Not scored with the sample profile yet." in text


def test_with_no_real_profile_the_toggle_is_disabled_and_the_page_says_which(
    make_app: AppFactory,
) -> None:
    """The deployed demo: data/private/ is gitignored, so the samples are all there is."""
    at = make_app()  # profile_dirs leaves the real folder uncreated

    toggle = at.toggle(key="use_sample")
    assert toggle.disabled
    assert toggle.value is True
    text = page_text(at)
    assert "Profile in use: **sample**" in text
    assert "no real profile" in text
    # AppTest refuses interactions a browser user could not perform, so this is the real
    # guarantee: there is no way to reach the real profile from the deployed page.
    with pytest.raises(AppTestError):
        toggle.set_value(False)


def test_with_a_real_profile_the_toggle_still_works_and_starts_on_real(
    make_app: AppFactory, profile_dirs: tuple[Path, Path]
) -> None:
    real, _ = profile_dirs
    real.mkdir()

    at = make_app()

    toggle = at.toggle(key="use_sample")
    assert not toggle.disabled
    assert toggle.value is False
    text = page_text(at)
    assert "Profile in use: **real**" in text
    assert "no real profile" not in text


def test_a_sidebar_entry_reopens_its_job(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))
    job_id = at.session_state["job_id"]
    del at.session_state["job_id"]
    at = at.run()
    assert "Paste a job description above" in page_text(at)

    at = click(at, "Example Co · AI Product Manager — scored")

    assert at.session_state["job_id"] == job_id
    assert "Critical fields" in page_text(at)


# --- Pages and the posting link ----------------------------------------------------------
#
# AppTest renders one page per run, starting from the entry point; switch_page picks which
# page file the next run() shows. The sidebar comes from the entry point on every page.

HISTORY = "views/history.py"


def link_buttons(at: AppTest) -> list[Any]:
    """AppTest has no reader for st.link_button, so take the raw element and its fields."""
    return [node.proto for node in at.main if getattr(node, "type", None) == "link_button"]


def test_history_lists_each_triaged_job_with_its_status(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))

    at = at.switch_page(HISTORY).run()

    assert not at.exception
    rows = at.dataframe[0].value.to_dict("records")
    assert [(row["company"], row["title"], row["status"]) for row in rows] == [
        ("Example Co", "AI Product Manager", "scored")
    ]


def test_history_with_nothing_triaged_says_so(make_app: AppFactory) -> None:
    at = make_app().switch_page(HISTORY).run()

    assert "Nothing triaged yet." in at.info[0].value
    assert at.dataframe == []


def test_the_profile_toggle_keeps_its_value_across_pages(
    make_app: AppFactory, profile_dirs: tuple[Path, Path]
) -> None:
    profile_dirs[0].mkdir()  # a real profile, so the toggle can be changed
    at = make_app()
    at.toggle(key="use_sample").set_value(True).run()

    at = at.switch_page(HISTORY).run()
    at = at.switch_page("views/triage.py").run()

    assert at.toggle(key="use_sample").value is True
    assert "Profile in use: **sample**" in page_text(at)


def test_a_recent_job_picked_on_another_page_opens_on_triage(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()))
    at = at.switch_page(HISTORY).run()

    at = click(at, "Example Co · AI Product Manager — scored")

    assert at.dataframe == []  # no longer on History
    assert at.get_by_key("card-critical-deadline") is not None


def test_a_web_address_becomes_a_link_and_anything_else_stays_text(make_app: AppFactory) -> None:
    at = make_app(*full_answers())
    at.text_input(key="url").set_value("https://example.com/jobs/1")
    at = triage_posting(at)
    assert [(link.label, link.url) for link in link_buttons(at)] == [
        ("Open the posting", "https://example.com/jobs/1")
    ]

    at = make_app(*full_answers())
    at.text_input(key="url").set_value("javascript:alert(1)")
    at = triage_posting(at)
    assert link_buttons(at) == []
    assert "javascript:alert(1)" in [text.value for text in at.text]


# --- Across every page -------------------------------------------------------------------

HOW_IT_WORKS = "views/how_it_works.py"
README = Path(__file__).parents[1] / "README.md"
# A number as the docs write it, with the count it is out of when there is one: "6 / 249",
# "3 of 6", "6–8 of 249", "45.3%", "0–100". Matching the whole phrase matters: a lone "3"
# or "6" is somewhere in any README, so "2 of 6" checked digit by digit would pass.
NUMBER = re.compile(
    r"\d+(?:\.\d+)?%?(?:\s*[–-]\s*\d+(?:\.\d+)?%?)?(?:\s*/\s*\d+(?:\.\d+)?|\s+of\s+\d+)?"
)


def every_page(at: AppTest) -> Iterator[AppTest]:
    """The page as it stands, then each other page in turn. AppTest changes in place."""
    yield at
    for path in (HISTORY, HOW_IT_WORKS):
        yield at.switch_page(path).run()


def test_every_number_on_how_it_works_is_one_the_readme_states(make_app: AppFactory) -> None:
    """The page copies the README; a number found only here would be a claim made only here."""
    at = make_app().switch_page(HOW_IT_WORKS).run()

    assert not at.exception
    readme = " ".join(README.read_text(encoding="utf-8").split())
    text = re.sub(r"\]\([^)]*\)", "]", page_text(at))  # a link's address is not a claim
    numbers = {" ".join(found.group().split()) for found in NUMBER.finditer(text)}
    assert {"6 / 249", "3 / 20", "6–8 of 249", "3 of 6", "5 of 8"} <= numbers  # not empty
    assert sorted(number for number in numbers if number not in readme) == []


def test_no_page_uses_marketing_words_or_calls_the_score_calibrated(make_app: AppFactory) -> None:
    at = triage_posting(make_app(*full_answers()), market="United States")

    for page in every_page(at):
        text = page_text(page).lower()
        assert "ai-powered" not in text
        assert re.search(r"\bsmart", text) is None
        for found in re.finditer("calibrated", text):
            assert text[max(0, found.start() - 4) : found.start()] == "not "


def test_no_page_offers_an_apply_or_submit_control(make_app: AppFactory) -> None:
    """The system ranks and recommends; the human applies, elsewhere (constraint 8)."""
    at = triage_posting(make_app(*full_answers()), market="United States")

    for page in every_page(at):
        labels = [button.label for button in page.button]
        labels += [link.label for link in link_buttons(page)]
        assert [label for label in labels if re.search("apply|submit", label, re.I)] == []
