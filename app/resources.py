"""What every page shares: the settings, the database and the model client.

st.cache_resource keeps one object alive across reruns and pages, so a new engine is not
built on every keystroke. An argument whose name starts with "_" is not hashed, which is
how Settings — which holds a secret and is not hashable — can be passed in.
"""

import streamlit as st

from toutoule import extract, triage
from toutoule.config import ConfigError, Settings, get_settings
from toutoule.db import get_engine, get_session_factory, init_db


def settings() -> Settings:
    """The settings, or the reason they failed and a stop: no page can work without them."""
    try:
        return get_settings()
    except ConfigError as error:
        st.error(str(error))
        st.stop()


@st.cache_resource
def session_factory(database_url: str):  # type: ignore[no-untyped-def]
    engine = get_engine(database_url)
    init_db(engine)
    return get_session_factory(engine)


@st.cache_resource
def model_client(_settings: Settings) -> extract.ModelClient:
    return triage.build_client(_settings)
