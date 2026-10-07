"""requirements.txt, the file Streamlit Community Cloud installs the deployed app from.

Cloud ignores uv.lock, so this generated file is the deploy's only dependency source.
CI regenerates it and fails on any diff; these tests cover what a regeneration could
silently get wrong.
"""

from pathlib import Path

REQUIREMENTS = Path(__file__).parents[1] / "requirements.txt"


def test_requirements_exists_for_streamlit_cloud() -> None:
    assert REQUIREMENTS.is_file(), "Cloud installs from requirements.txt, never from uv.lock"


def test_requirements_installs_the_project_itself_and_keeps_it_editable() -> None:
    """Without "-e .", the deployed app breaks twice over.

    Plain dependencies leave `import toutoule` failing outright. A non-editable "." would
    import but move __file__ into site-packages, so config.py's parents[2] would no longer
    be the repo root and data/profile and data/prompts would vanish at runtime.
    """
    lines = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()]
    assert "-e ." in lines, f"expected an editable install of the project; got {lines[:4]}"
