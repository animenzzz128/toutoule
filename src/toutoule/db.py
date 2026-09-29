"""Database engine, sessions and table creation.

Nothing connects at import time: an engine only opens a connection when first used.
"""

from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from toutoule.config import get_settings
from toutoule.models import Base


def get_engine(url: str | None = None) -> Engine:
    """Create an engine for url, or for DATABASE_URL from settings if url is None."""
    engine = create_engine(url or get_settings().database_url)
    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless told otherwise, on every new connection.
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a factory that makes sessions bound to engine: `with factory() as s: ...`"""
    return sessionmaker(engine)


def init_db(engine: Engine) -> list[str]:
    """Create any missing tables and return the names of the ones it created.

    Existing tables are left untouched, so calling this twice is safe.
    """
    existing = set(inspect(engine).get_table_names())
    Base.metadata.create_all(engine)
    return sorted(set(Base.metadata.tables) - existing)
