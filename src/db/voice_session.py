"""
voice_session.py — SQLAlchemy (sync) setup for the VOICE side (Pipeline A).

WHY A SECOND SESSION MODULE?
The clerk side already has db/session.py, but it is ASYNC (asyncpg) and points at
the clerk DATABASE_URL. The voice side is fully synchronous and talks to a
DIFFERENT database (Cloud SQL, via CLOUD_SQL_HOST/CLOUD_SQL_PASSWORD). Mixing the
two would force the whole voice path (pipeline.py + routes) to go async. So the
voice side gets its OWN synchronous engine + declarative base here. The driver is
psycopg2 — the same library db_context.py already uses for raw SQL — so no new
dependency is needed.

This is the ORM equivalent of db_context._connect(): one place that knows how to
reach the voice DB. ORM models (db/models/voice.py) hang off VoiceBase; callers
get a Session from get_session().
"""

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class VoiceBase(DeclarativeBase):
    """Declarative base for all VOICE (Pipeline A) ORM models.

    Kept separate from the clerk side's Base (db/session.py) because the two
    sides map different tables in different databases.
    """


# The engine is a connection POOL, created once and reused. We build it lazily
# (on first use) rather than at import time so that importing this module never
# requires the Cloud SQL env vars to be present — tests and tooling can import
# the models without a live DB. db_context.py loads the voice .env at its import,
# so by the time a query runs the credentials are in os.environ.
_engine = None
_SessionFactory: sessionmaker | None = None


def _build_engine():
    """Create the sync SQLAlchemy engine for the voice Cloud SQL database.

    URL.create handles escaping (e.g. special characters in the password), and
    sslmode=require is passed through to psycopg2 — the same connection options
    db_context._connect() uses for the raw psycopg2 connection.
    """
    url = URL.create(
        "postgresql+psycopg2",
        username="postgres",
        password=os.environ["CLOUD_SQL_PASSWORD"],
        host=os.environ["CLOUD_SQL_HOST"],
        port=5432,
        database="claimpilot",
    )
    return create_engine(url, connect_args={"sslmode": "require"}, echo=False)


def get_session() -> Session:
    """Return a new SQLAlchemy Session bound to the voice engine.

    Use as a context manager so the session is always closed:

        with get_session() as session:
            ...

    The engine/session factory are initialized on first call.
    """
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = _build_engine()
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _SessionFactory()
