"""One job posting and the fake model answers that match it, shared by the tests.

A single posting keeps the module tests and the app tests honest about the same text:
a quote that verifies in one has to verify in the other.
"""

import json
from datetime import date
from typing import Any

POSTING = (
    "Example Co is hiring an AI Product Manager.\n"
    "We do not sponsor work visas for this role.\n"
    "Applications close on 2026-12-31.\n"
    "You will own a roadmap, run pricing experiments, and work with data science. "
    "SQL required.\n"
    "Based in New York, NY. Hybrid, three days a week in the office.\n"
    "Please submit a resume and cover letter.\n"
)
RESUME = "Shipped an AI assistant used by 40 teams\nPython, SQL, R, Stata\nLed pricing research"
TODAY = date(2026, 10, 3)  # well before the posting's deadline: no R5, no R6


def field(value: str | None, evidence: str | None) -> dict[str, Any]:
    """One extracted field. value=None means the posting did not state it (F3)."""
    return {"value": value, "stated": value is not None, "evidence": evidence}


def extraction_answer(**overrides: dict[str, Any]) -> str:
    """One model reply for the extraction call. Every quote is a span of POSTING."""
    critical = {
        "deadline": field("2026-12-31", "Applications close on 2026-12-31."),
        "visa_sponsorship": field("no", "We do not sponsor work visas for this role."),
        "graduation_window": field(None, None),  # the posting really is silent on this
        "application_cap": field(None, None),
        "materials_required": field("resume + cover letter", "Please submit a resume and cover"),
    }
    return json.dumps(
        {
            "schema_version": "1.0",
            "prompt_version": "ignored, code sets this",
            "company": "Example Co",
            "title": "AI Product Manager",
            "critical": critical | overrides,
            "important": {
                "location": field("New York, NY", "Based in New York, NY."),
                "work_model": field("hybrid", "Hybrid, three days a week in the office."),
                "language_requirement": field(None, None),
                "start_date": field(None, None),
                "degree_requirement": field(None, None),
            },
            "reference": {
                "skills": ["SQL"],
                "responsibilities": ["own a roadmap"],
                "team_or_function": "Product",
            },
        }
    )


def score_answer(fabricate: bool = False) -> str:
    """One model reply for a scoring call. Both sides of every pair are real quotes.

    fabricate=True invents the third pair's resume quote, so verification must reject it.
    """
    invented = "Ran a team of nine data scientists"  # in neither the posting nor the resume
    return json.dumps(
        {
            "dimensions": {
                "domain_fit": {"score": 8, "reason": "same work"},
                "skills_overlap": {"score": 6, "reason": "most tools match"},
                "seniority_fit": {"score": 7, "reason": "right level"},
            },
            "evidence_pairs": [
                {"requirement": "SQL required", "experience": "Python, SQL, R, Stata"},
                {"requirement": "own a roadmap", "experience": "Led pricing research"},
                {
                    "requirement": "run pricing experiments",
                    "experience": invented
                    if fabricate
                    else "Shipped an AI assistant used by 40 teams",
                },
            ],
            "gaps": ["no people management", "no payments experience"],
        }
    )
